"""Tests F-172 — défaut pageId sur le bridge MCP chrome-devtools. 0 LLM / 0 réseau.

Contexte : chrome-devtools-mcp 1.8.0 (résolue par npx @latest) active
``pageIdRouting`` PAR DÉFAUT → ``pageId`` requis sur 27 outils page-scoped
(sonde live debug/f172_probe_pageid.py). Les modèles locaux ne connaissent pas
les ids → MCP -32602 « Required at pageId » → boucle de retries → mort du nœud
(Coder v5-it1, Tester v6-it1, 2026-08-25).

Couvre :
  - ``parse_selected_page_id`` : marqueur [selected] prioritaire, repli
    première page, formats hostiles → None (fail-open) ;
  - ``call_tool_with_page_id_fallback`` : injection réactive (uniquement sur
    « Required at pageId » sans pageId / « No page found » avec pageId=0),
    UNE retentative, erreurs d'origine PRESERVÉES sinon (résolution
    impossible, pageId>0 périmé, erreurs non liées) ;
  - ``make_process_tool_call`` de bout en bout : evaluate_script sauvé AVANT
    la barrière tool_error_behavior="retry", enrichissement console F-126
    (get_console_message lui aussi page-scoped) sauvé ;
  - helpers DOM (``_eval`` → evaluate_script avec pageId injecté) ;
  - épinglage de la version serveur (agent_server.mcp, 3e break d'@latest).
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graph_orchestrator.coder_pydantic_mcp import (
    build_dom_helper_toolset,
    call_tool_with_page_id_fallback,
    make_process_tool_call,
    parse_selected_page_id,
)


class _ToolError(Exception):
    """Mimique fastmcp.exceptions.ToolError (messages recopiés des runs v5/v6)."""


_REQUIRED_AT_PAGEID = (
    "MCP error -32602: Input validation error: Invalid arguments for tool "
    "evaluate_script: Required at pageId"
)
_REQUIRED_AT_PAGEID_NAV = (
    "MCP error -32602: Input validation error: Invalid arguments for tool "
    "navigate_page: Required at pageId"
)
_NO_PAGE_FOUND = "Error: No page found"

_PAGES_SELECTED_2 = (
    "## Pages\n1: about:blank\n2: file:///C:/run/index.html [selected]"
)
_PAGES_ONLY_1 = "## Pages\n1: about:blank [selected]"


# ============================================================
# parse_selected_page_id
# ============================================================


class TestParseSelectedPageId:
    def test_live_format_selected_on_single_page(self):
        # Format exact observé sur la 1.8.0 (sonde live).
        assert parse_selected_page_id(_PAGES_ONLY_1) == 1

    def test_selected_wins_over_first_listed(self):
        # 2 onglets : la page ACTIVE est la 2e — c'est elle qu'il faut cibler,
        # pas la première listée (doublon laissé ouvert).
        assert parse_selected_page_id(_PAGES_SELECTED_2) == 2

    def test_no_selected_marker_falls_back_to_first(self):
        assert parse_selected_page_id("## Pages\n1: http://a\n2: http://b") == 1

    def test_double_digit_id(self):
        assert parse_selected_page_id("## Pages\n1: http://a\n10: http://b [selected]") == 10

    def test_url_colons_do_not_confuse(self):
        # "1: http://…" : le regex ancre en début de ligne, les « : » des URLs
        # ne doivent pas matcher.
        assert parse_selected_page_id("## Pages\n1: http://127.0.0.1:5500/index.html") == 1

    def test_empty_and_garbage_return_none(self):
        assert parse_selected_page_id("") is None
        assert parse_selected_page_id(None) is None
        assert parse_selected_page_id("## Pages\n(aucune)") is None


# ============================================================
# call_tool_with_page_id_fallback — via faux call_tool
# ============================================================


class _ScriptedClient:
    """Faux canal MCP : un handler async (name, args) -> résultat ou raise."""

    def __init__(self, handler):
        self.calls = []
        self._handler = handler

    async def __call__(self, name, args, meta=None):
        self.calls.append((name, dict(args)))
        return await self._handler(name, dict(args))


def _client_requiring_page_id(pages_text=_PAGES_SELECTED_2, result="OK-RESULT"):
    """Serveur 1.8.0 simulé : pageId absent → -32602, pageId valide → résultat."""

    async def handler(name, args):
        if name == "list_pages":
            return pages_text
        if not args.get("pageId"):
            raise _ToolError(_REQUIRED_AT_PAGEID)
        return result

    return _ScriptedClient(handler)


class _AsFastmcpClient:
    """Adapte un _ScriptedClient en client fastmcp (expose .call_tool) — la
    forme attendue par ``build_dom_helper_toolset`` en production."""

    def __init__(self, inner):
        self._inner = inner

    async def call_tool(self, name, args):
        return await self._inner(name, args)


async def _ok(name, args, _result="ok"):
    return _result


class TestCallToolWithPageIdFallback:
    def test_success_first_try_no_resolution(self):
        client = _ScriptedClient(_ok)
        out = asyncio.run(call_tool_with_page_id_fallback(client, "evaluate_script", {"function": "() => 1"}))
        assert out == "ok"
        assert client.calls == [("evaluate_script", {"function": "() => 1"})]

    def test_missing_page_id_injected_then_retried_once(self):
        client = _client_requiring_page_id()
        out = asyncio.run(call_tool_with_page_id_fallback(
            client, "evaluate_script", {"function": "() => document.title"}
        ))
        assert out == "OK-RESULT"
        # Séquence exacte : échec SANS pageId → list_pages → retentative AVEC
        # la page sélectionnée (2, pas la première listée).
        assert client.calls == [
            ("evaluate_script", {"function": "() => document.title"}),
            ("list_pages", {}),
            ("evaluate_script", {"function": "() => document.title", "pageId": 2}),
        ]

    def test_zero_page_id_replaced_by_selected(self):
        async def handler(name, args):
            if name == "list_pages":
                return _PAGES_ONLY_1
            if args.get("pageId") in (None, 0):
                raise _ToolError(_NO_PAGE_FOUND)
            return "nav-OK"

        client = _ScriptedClient(handler)
        out = asyncio.run(call_tool_with_page_id_fallback(
            client, "navigate_page", {"url": "file:///index.html", "pageId": 0}
        ))
        assert out == "nav-OK"
        # pageId=0 (hallucination — les ids réels commencent à 1) REMPLACÉ,
        # pas juste complété.
        assert client.calls[-1] == ("navigate_page", {"url": "file:///index.html", "pageId": 1})

    def test_stale_page_id_gt_zero_reraises(self):
        """pageId>0 périmé (« No page found ») : on N'injecte PAS — le modèle
        doit voir l'erreur réelle (ciblage multi-onglets, pas un défaut)."""
        async def handler(name, args):
            if name == "list_pages":
                return _PAGES_ONLY_1
            raise _ToolError(_NO_PAGE_FOUND)

        client = _ScriptedClient(handler)
        with pytest.raises(_ToolError, match="No page found"):
            asyncio.run(call_tool_with_page_id_fallback(
                client, "evaluate_script", {"function": "() => 1", "pageId": 7}
            ))
        # AUCUNE résolution déclenchée : l'unique appel est l'échec d'origine.
        assert client.calls == [("evaluate_script", {"function": "() => 1", "pageId": 7})]

    def test_required_marker_with_page_id_present_reraises(self):
        async def handler(name, args):
            raise _ToolError(_REQUIRED_AT_PAGEID)

        client = _ScriptedClient(handler)
        with pytest.raises(_ToolError):
            asyncio.run(call_tool_with_page_id_fallback(
                client, "evaluate_script", {"function": "() => 1", "pageId": 3}
            ))
        assert client.calls == [("evaluate_script", {"function": "() => 1", "pageId": 3})]

    def test_unrelated_error_reraises_without_resolution(self):
        async def handler(name, args):
            raise _ToolError("MCP error -32603: Internal error")

        client = _ScriptedClient(handler)
        with pytest.raises(_ToolError, match="-32603"):
            asyncio.run(call_tool_with_page_id_fallback(
                client, "take_screenshot", {"format": "jpeg"}
            ))
        assert client.calls == [("take_screenshot", {"format": "jpeg"})]

    def test_list_pages_failure_preserves_original_error(self):
        async def handler(name, args):
            if name == "list_pages":
                raise _ToolError("MCP error -32603: boom list_pages")
            raise _ToolError(_REQUIRED_AT_PAGEID)

        client = _ScriptedClient(handler)
        # L'erreur remontée est celle D'ORIGINE (-32602), pas celle de la
        # résolution (le modèle doit voir sa vraie erreur).
        with pytest.raises(_ToolError, match="Required at pageId"):
            asyncio.run(call_tool_with_page_id_fallback(
                client, "evaluate_script", {"function": "() => 1"}
            ))

    def test_unparseable_list_pages_preserves_original_error(self):
        client = _client_requiring_page_id(pages_text="## Pages\n(none)")
        with pytest.raises(_ToolError, match="Required at pageId"):
            asyncio.run(call_tool_with_page_id_fallback(
                client, "evaluate_script", {"function": "() => 1"}
            ))

    def test_none_args_defensive(self):
        client = _ScriptedClient(_ok)
        out = asyncio.run(call_tool_with_page_id_fallback(client, "list_pages", None))
        assert out == "ok"
        assert client.calls == [("list_pages", {})]


# ============================================================
# make_process_tool_call — sauvetage AVANT la barrière retry
# ============================================================


class TestProcessToolCallFallback:
    def test_evaluate_script_saved_end_to_end(self):
        client = _client_requiring_page_id(result="Script ran on page and returned:\n```json\n42\n```")
        cb = make_process_tool_call(vision=False)
        out = asyncio.run(cb(None, client, "evaluate_script", {"function": "() => 42"}))
        assert "42" in out
        # Le modèle n'a JAMAIS vu l'erreur -32602 : interceptée en amont de
        # tool_error_behavior="retry" (le chemin qui tuait Tester v6-it1).
        assert [c[0] for c in client.calls] == ["evaluate_script", "list_pages", "evaluate_script"]
        assert client.calls[-1][1]["pageId"] == 2

    def test_console_enrichment_detail_also_saved(self):
        """F-126 + F-172 : get_console_message exige AUSSI pageId en 1.8.0 —
        l'enrichissement console doit survivre au sauvetage."""

        async def handler(name, args):
            if name == "list_console_messages":
                return (
                    "## Console Messages\n"
                    "- msgid=1 [error] Uncaught TypeError: boom (2 args)\n"
                )
            if name == "list_pages":
                return _PAGES_ONLY_1
            if name == "get_console_message":
                if not args.get("pageId"):
                    raise _ToolError(
                        "MCP error -32602: Input validation error: Invalid arguments "
                        "for tool get_console_message: Required at pageId"
                    )
                return (
                    "### Message 1\n[error] boom\n### Stack trace\n"
                    "  at drawGhost (index.html:352:58)\nNote: mapped"
                )
            raise AssertionError(f"outil inattendu : {name}")

        client = _ScriptedClient(handler)
        cb = make_process_tool_call(vision=False)
        out = asyncio.run(cb(None, client, "list_console_messages", {}))
        # La stack enrichie est bien là (F-126 vivant grâce au fallback F-172).
        assert "drawGhost (index.html:352:58)" in out
        detail_calls = [c for c in client.calls if c[0] == "get_console_message"]
        assert len(detail_calls) == 2  # échec puis retentative sauvée
        assert detail_calls[-1][1] == {"msgid": 1, "pageId": 1}

    def test_navigate_saved_and_args_intact(self):
        async def handler(name, args):
            if name == "list_pages":
                return _PAGES_ONLY_1
            if not args.get("pageId"):
                raise _ToolError(_REQUIRED_AT_PAGEID_NAV)
            return "Navigated to file:///index.html"

        client = _ScriptedClient(handler)
        cb = make_process_tool_call(vision=False)
        out = asyncio.run(cb(None, client, "navigate_page", {"url": "file:///index.html"}))
        assert out == "Navigated to file:///index.html"
        assert client.calls[-1][1]["url"] == "file:///index.html"


# ============================================================
# Helpers DOM — _eval → evaluate_script avec pageId injecté
# ============================================================


class TestDomHelperFallback:
    def test_discover_ui_delegates_with_injected_page_id(self):
        async def handler(name, args):
            if name == "list_pages":
                return _PAGES_SELECTED_2
            if not args.get("pageId"):
                raise _ToolError(_REQUIRED_AT_PAGEID)
            return '{"canvases": [], "buttons": [{"id": "start"}]}'

        client = _ScriptedClient(handler)
        toolset = build_dom_helper_toolset(_AsFastmcpClient(client))
        assert toolset is not None
        out = asyncio.run(toolset.tools["discover_ui"].function())
        assert "start" in out
        name, args = client.calls[-1]
        assert name == "evaluate_script"
        assert args["pageId"] == 2  # page sélectionnée, pas la première listée

    def test_clean_dom_silent_when_server_tolerant(self):
        """Serveur SANS pageIdRouting (vieux/flag off) : fallback inert — un
        seul appel, aucun list_pages (parité comportementale préservée)."""
        client = _ScriptedClient(_ok)
        toolset = build_dom_helper_toolset(_AsFastmcpClient(client))
        asyncio.run(toolset.tools["clean_dom"].function())
        assert len(client.calls) == 1
        assert client.calls[0][0] == "evaluate_script"


# ============================================================
# Épinglage de la version serveur (agent_server.mcp)
# ============================================================


class TestServerVersionPinned:
    def test_devtools_spawn_pins_1_8_0(self, monkeypatch):
        """3e break d'@latest (F-50 filePath, F-127 enum, F-172 pageIdRouting) :
        la commande npx doit être épinglée — la surface d'outils documentée
        dans les skills ne doit plus bouger sous les pieds du run."""
        from agent_server.mcp import build_chrome_devtools_params

        monkeypatch.setenv("CHROME_DEVTOOLS_ENABLED", "1")
        params = build_chrome_devtools_params()
        assert params is not None
        pkg = [a for a in params.args if a.startswith("chrome-devtools-mcp@")]
        assert pkg == ["chrome-devtools-mcp@1.8.0"]
