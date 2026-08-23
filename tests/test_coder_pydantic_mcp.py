"""Tests F-160 — MCP navigateur & doc du Coder pydantic (phase 3.5), 0 LLM / 0 réseau.

Couvre : transformations per-tool (_prepare_tool_args F-50/F-90/F-127,
_enrich_console F-126, make_process_tool_call via faux call_tool), builders de
toolsets (chrome-devtools stdio / Context7 HTTP — construction SANS connexion),
12 helpers DOM (interpolation/clampage/rejets, corps JS identiques à
devtools_dom_tools), blocs d'instructions (LIVE VERIFICATION, tools browser,
ligne Context7, skill devtools-preview) et assemblage de l'Agent avec toolsets.
"""

import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graph_orchestrator.coder_pydantic import build_coder_agent, build_coder_instructions
from graph_orchestrator.coder_pydantic_mcp import (
    _enrich_console,
    _prepare_tool_args,
    build_context7_mcp_toolset,
    build_devtools_mcp_toolset,
    build_dom_helper_toolset,
    make_process_tool_call,
    render_mcp_result,
)
from graph_orchestrator.config import load_settings


def _base_task(**overrides) -> dict:
    task = {
        "id": "ts-001",
        "content": "Crée un visualiseur Bubble Sort en HTML/CSS/JS vanilla sur 3 fichiers.",
        "target_files": ["index.html", "styles.css", "script.js"],
        "strategy": "multifile",
        "sections": [],
        "skills": ["coding"],
        "iteration": 1,
    }
    task.update(overrides)
    return task


# ============================================================
# _prepare_tool_args — F-50/F-90 (filePath) + F-127 (types)
# ============================================================


class TestPrepareToolArgs:
    def test_take_screenshot_filepath_stripped(self):
        args = _prepare_tool_args(
            "take_screenshot", {"filePath": "shot.png", "format": "jpeg"}
        )
        assert "filePath" not in args
        assert args["format"] == "jpeg"

    def test_take_snapshot_file_path_snake_stripped(self):
        args = _prepare_tool_args("take_snapshot", {"file_path": "s.png"})
        assert args == {}

    def test_evaluate_script_untouched(self):
        """Seuls les outils screenshot sont touchés — evaluate_script garde tout."""
        args = _prepare_tool_args(
            "evaluate_script", {"function": "() => 1", "args": [1]}
        )
        assert args == {"function": "() => 1", "args": [1]}

    def test_console_types_invalid_values_dropped(self):
        """F-127 : valeurs d'enum inventées retirées (absence = tous les types)."""
        args = _prepare_tool_args(
            "list_console_messages", {"types": ["exception", "fatal"]}
        )
        assert "types" not in args

    def test_console_types_valid_kept(self):
        args = _prepare_tool_args(
            "list_console_messages", {"types": ["ERROR", "warn", "bogus"]}
        )
        assert args["types"] == ["ERROR", "warn"]


# ============================================================
# _enrich_console — F-126 (stacks + directive ciblée)
# ============================================================

_CONSOLE_TXT = (
    "## Console Messages\n"
    "- msgid=1 [error] Uncaught TypeError: boom (2 args)\n"
    "- msgid=2 [log] rien d'important\n"
    "- msgid=7 [error] Uncaught SyntaxError: Unexpected token '}'\n"
)

_DETAIL = (
    "### Message 7\n[error] ...\n### Stack trace\n"
    "  at drawGhost (index.html:352:58)\n"
    "  at gameLoop (index.html:410:5)\n"
    "Note: mapped"
)


class TestEnrichConsole:
    def test_no_error_unchanged(self):
        text = "- msgid=3 [log] hello"
        assert _enrich_console(text, []) is text

    def test_stacks_appended_with_guidance(self):
        out = _enrich_console(_CONSOLE_TXT, [_DETAIL, "", _DETAIL])
        assert "STACK TRACES COMPLÈTES" in out
        assert "drawGhost (index.html:352:58)" in out
        # Directive read_file ciblée sur la 1re frame (F-126)
        assert 'read_file(path="index.html", offset=344, limit=20)' in out
        # Anti-réécriture complète (leçon run 2026-08-19_1552)
        assert "NE réécris PAS tout le fichier" in out

    def test_no_frames_fail_open(self):
        out = _enrich_console(_CONSOLE_TXT, ["pas de stack ici", "", "non plus"])
        assert out is _CONSOLE_TXT

    def test_extra_errors_note(self):
        text = "\n".join(f"- msgid={i} [error] err{i}" for i in range(1, 8))
        out = _enrich_console(text, [_DETAIL] * 7)
        assert "(+3 erreur(s) non détaillée(s)" in out


# ============================================================
# make_process_tool_call — intégration via faux call_tool
# ============================================================


class _FakeCallTool:
    """Faux canal MCP : enregistre les appels, réponses enregistrables."""

    def __init__(self, responses=None):
        self.calls = []
        self._responses = responses or {}

    async def __call__(self, name, args, meta=None):
        self.calls.append((name, dict(args)))
        resp = self._responses.get(name, "")
        return resp() if callable(resp) else resp


class TestProcessToolCall:
    def _run(self, cb, name, args, responses=None):
        fake = _FakeCallTool(responses)
        out = asyncio.run(cb(None, fake, name, args))
        return out, fake

    def test_screenshot_args_sanitized_before_delegate(self):
        cb = make_process_tool_call()
        out, fake = self._run(
            cb, "take_screenshot", {"filePath": "x.png", "format": "jpeg"},
            responses={"take_screenshot": "Screenshot captured (1280x800)"},
        )
        assert fake.calls == [("take_screenshot", {"format": "jpeg"})]
        assert "Screenshot captured" in out

    def test_console_enriched_via_detail_calls(self):
        cb = make_process_tool_call()
        out, fake = self._run(
            cb, "list_console_messages", {"types": ["exception"]},
            responses={
                "list_console_messages": _CONSOLE_TXT,
                "get_console_message": _DETAIL,
            },
        )
        # types invalide retiré AVANT délégation (F-127)
        assert fake.calls[0] == ("list_console_messages", {})
        # détail demandé pour chaque msgid [error] (borné 4)
        detail_calls = [c for c in fake.calls if c[0] == "get_console_message"]
        assert [c[1]["msgid"] for c in detail_calls] == [1, 7]
        assert "drawGhost (index.html:352:58)" in out

    def test_non_console_passthrough(self):
        cb = make_process_tool_call()
        out, fake = self._run(
            cb, "navigate_page", {"url": "file:///index.html", "type": "url"},
            responses={"navigate_page": "Navigated to file:///index.html"},
        )
        assert out == "Navigated to file:///index.html"
        assert fake.calls[0][1]["url"] == "file:///index.html"


class TestRenderMcpResult:
    def test_str_passthrough(self):
        assert render_mcp_result("plain") == "plain"

    def test_none_empty(self):
        assert render_mcp_result(None) == ""

    def test_content_blocks(self):
        class Block:
            def __init__(self, t):
                self.text = t

        class Res:
            content = [Block("a"), Block("b")]

        assert render_mcp_result(Res()) == "a\nb"

    def test_data_fallback_json(self):
        class Res:
            content = None
            data = {"verdict": "SORTED_AFTER_WAIT"}

        assert "SORTED_AFTER_WAIT" in render_mcp_result(Res())


# ============================================================
# Builders de toolsets — construction SANS connexion (0 réseau)
# ============================================================


class TestBuildDevtoolsToolset:
    def test_disabled_returns_none(self, monkeypatch):
        monkeypatch.setenv("CHROME_DEVTOOLS_ENABLED", "0")
        assert build_devtools_mcp_toolset(load_settings()) is None

    def test_enabled_builds_mcp_toolset(self, monkeypatch):
        from pydantic_ai.mcp import MCPToolset

        monkeypatch.setenv("CHROME_DEVTOOLS_ENABLED", "1")
        ts = build_devtools_mcp_toolset(load_settings())
        assert isinstance(ts, MCPToolset)
        assert ts.id == "chrome-devtools"
        # La commande vient de agent_server.mcp (source unique de vérité)
        transport = ts.client.transport
        assert transport.command == "npx"
        joined = " ".join(transport.args)
        assert "chrome-devtools-mcp" in joined
        assert "--isolated" in joined
        assert "--viewport 1280x800" in joined
        assert "--screenshot-format jpeg" in joined

    def test_process_tool_call_attached(self, monkeypatch):
        monkeypatch.setenv("CHROME_DEVTOOLS_ENABLED", "1")
        ts = build_devtools_mcp_toolset(load_settings())
        assert callable(ts.process_tool_call)


class TestBuildContext7Toolset:
    def test_no_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("CONTEXT7_API_KEY", raising=False)
        assert build_context7_mcp_toolset(load_settings()) is None

    def test_with_key_builds_renamed_toolset(self, monkeypatch):
        from pydantic_ai.mcp import MCPToolset
        from pydantic_ai.toolsets.renamed import RenamedToolset

        monkeypatch.setenv("CONTEXT7_API_KEY", "test-key-123")
        ts = build_context7_mcp_toolset(load_settings())
        assert isinstance(ts, RenamedToolset)
        # Parité noms smolagents : les prompts/skills citent les underscores,
        # le serveur Context7 expose des tirets.
        assert ts.name_map == {
            "resolve_library_id": "resolve-library-id",
            "query_docs": "query-docs",
        }
        inner = ts.wrapped
        assert isinstance(inner, MCPToolset)
        assert inner.id == "context7"
        assert inner.client.transport.headers.get("CONTEXT7_API_KEY") == "test-key-123"


# ============================================================
# 12 helpers DOM — parité devtools_dom_tools (corps JS identiques)
# ============================================================


class _RecordingClient:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, args):
        self.calls.append((name, dict(args)))
        return json.dumps({"ok": True})


@pytest.fixture()
def helpers():
    client = _RecordingClient()
    toolset = build_dom_helper_toolset(client)
    return toolset, client


class TestDomHelperToolset:
    def test_none_client_returns_none(self):
        assert build_dom_helper_toolset(None) is None

    def test_twelve_helpers_exact_names(self, helpers):
        toolset, _ = helpers
        assert sorted(toolset.tools) == [
            "add_visual_tags",
            "clean_dom",
            "discover_ui",
            "dump_function_source",
            "expose_game_state",
            "force_advance",
            "fuzz_click_all_buttons",
            "fuzz_keyboard_controls",
            "heal_selector",
            "instrument_calls",
            "probe_canvas_activity",
            "probe_sort_state",
        ]

    def test_all_have_description(self, helpers):
        toolset, _ = helpers
        assert all(t.description for t in toolset.tools.values())

    def test_clean_dom_delegates_to_evaluate_script(self, helpers):
        toolset, client = helpers
        asyncio.run(toolset.tools["clean_dom"].function())
        name, args = client.calls[-1]
        assert name == "evaluate_script"
        assert "cloneNode(true)" in args["function"]

    def test_probe_canvas_window_clamped(self, helpers):
        toolset, client = helpers
        asyncio.run(toolset.tools["probe_canvas_activity"].function(window_ms=99999))
        fn = client.calls[-1][1]["function"]
        assert "Math.min(10000, Number('10000'))" in fn

    def test_probe_canvas_default_2400(self, helpers):
        toolset, client = helpers
        asyncio.run(toolset.tools["probe_canvas_activity"].function())
        assert "Number('2400')" in client.calls[-1][1]["function"]

    def test_probe_sort_default_and_clamp(self, helpers):
        toolset, client = helpers
        asyncio.run(toolset.tools["probe_sort_state"].function())
        assert "Number('180000')" in client.calls[-1][1]["function"]
        asyncio.run(toolset.tools["probe_sort_state"].function(max_wait_ms=1))
        assert "Math.max(1000, Math.min(300000, Number('1000')))" in client.calls[-1][1]["function"]

    def test_force_advance_rejects_bad_identifier_without_call(self, helpers):
        toolset, client = helpers
        out = asyncio.run(toolset.tools["force_advance"].function(fn="bad();"))
        assert out.startswith("ERROR (force_advance)")
        assert client.calls == []

    def test_force_advance_interpolates(self, helpers):
        toolset, client = helpers
        asyncio.run(toolset.tools["force_advance"].function(fn="updateBoard", times=600))
        fn = client.calls[-1][1]["function"]
        assert "const fname = 'updateBoard';" in fn
        assert "Math.min(500, Number('500'))" in fn

    def test_expose_game_state_rejects_non_identifiers(self, helpers):
        toolset, client = helpers
        out = asyncio.run(toolset.tools["expose_game_state"].function(names="score, x.y"))
        assert "ERROR (expose_game_state)" in out
        assert client.calls == []

    def test_instrument_calls_and_dump_reject_bad_names(self, helpers):
        toolset, client = helpers
        for tool, kwargs in (
            ("instrument_calls", {"names": "draw, do()"}),
            ("dump_function_source", {"names": "draw, <b>"}),
        ):
            out = asyncio.run(toolset.tools[tool].function(**kwargs))
            assert "ERROR" in out
        assert client.calls == []

    def test_heal_selector_passes_args_list(self, helpers):
        toolset, client = helpers
        asyncio.run(
            toolset.tools["heal_selector"].function(tag="button", text_hint="Go", attr_hint="")
        )
        args = client.calls[-1][1]
        assert args["args"] == ["button", "Go", ""]
        assert args["function"].strip().startswith("(tag, textHint, attrHint) =>")


class TestDevtoolsClientIntegration:
    """Intégration 0-réseau (fermeture review Kilo PR #111) : serveur FastMCP
    IN-PROCESS → VRAI MCPToolset → helpers déléguant via ``ts.client`` — prouve
    que le chemin ``open_coder_mcp → state.devtools_client = devtools.client →
    call_tool('evaluate_script', ...)`` est utilisable de bout en bout, pas
    seulement avec le client factice des tests unitaires."""

    def test_helpers_through_real_mcp_toolset_client(self):
        # Serveur in-process du SDK officiel mcp (dépendance de prod — le côté
        # serveur de fastmcp-slim[client] n'est pas installé) : même protocole.
        from mcp.server.fastmcp import FastMCP

        captured = {}

        fake_devtools = FastMCP("fake-devtools")

        @fake_devtools.tool()
        def evaluate_script(function: str, args=None) -> str:  # noqa: ANN001
            """Stand-in du vrai outil chrome-devtools (echo)."""
            captured["function"] = function
            captured["args"] = args
            return "echo:" + function[:40]

        async def scenario():
            from graph_orchestrator.coder_pydantic_mcp import build_dom_helper_toolset
            from pydantic_ai.mcp import MCPToolset

            ts = MCPToolset(fake_devtools)
            async with ts:
                helpers = build_dom_helper_toolset(ts.client)
                assert helpers is not None
                return await helpers.tools["clean_dom"].function()

        out = asyncio.run(scenario())
        # Le helper a bien transité par le VRAI client fastmcp du toolset.
        assert "cloneNode(true)" in captured["function"]
        assert out.startswith("echo:")

    def test_renamed_toolset_exposes_new_names(self):
        """Sécurise la direction du name_map ({nouveau: original} — doc pydantic
        « new names to original names » + source ``original_to_new = {v: k}``) :
        la clé est le nom EXPOSÉ au modèle (revue Kilo PR #111 suggérait
        l'inverse, ce qui casserait le renommage)."""
        from pydantic_ai import Agent
        from pydantic_ai.models.test import TestModel
        from pydantic_ai.toolsets import FunctionToolset
        from pydantic_ai.toolsets.renamed import RenamedToolset

        async def dash_named_tool(query: str) -> str:
            """fake c7."""
            return "ok"

        ts = RenamedToolset(
            FunctionToolset([dash_named_tool]), {"underscore_name": "dash_named_tool"}
        )
        agent = Agent(TestModel(), toolsets=[ts])

        async def scenario():
            async with agent:
                result = await agent.run("go")
            return {
                p.tool_name
                for m in result.all_messages()
                for p in getattr(m, "parts", [])
                if hasattr(p, "tool_name")
            }

        names = asyncio.run(scenario())
        assert names == {"underscore_name"}


# ============================================================
# Instructions — bloc LIVE VERIFICATION + tools browser + Context7
# ============================================================


class TestInstructionsBrowser:
    def test_browser_block_present_on_web_task(self):
        instructions = build_coder_instructions(_base_task(), browser_tools_available=True)
        assert "LIVE VERIFICATION (Chrome DevTools" in instructions
        assert "list_console_messages()" in instructions
        assert "probe_sort_state()" in instructions
        # F-161 : vision livrée — screenshot = image dans le contexte (VISUAL
        # CHECK) ; le caveat « text confirmation only » n'existe plus en nominal.
        assert "VISUAL CHECK" in instructions
        assert "text confirmation only" not in instructions
        # URL file:/// absolue du 1er target
        assert "file:///" in instructions

    def test_browser_block_absent_on_non_web_task(self):
        task = _base_task(
            target_files=["solver.py"], content="Écris un solveur Python."
        )
        instructions = build_coder_instructions(task, browser_tools_available=True)
        assert "LIVE VERIFICATION" not in instructions

    def test_browser_block_absent_when_no_tools(self):
        instructions = build_coder_instructions(_base_task(), browser_tools_available=False)
        assert "LIVE VERIFICATION" not in instructions

    def test_browser_tools_line_conditioned(self):
        with_browser = build_coder_instructions(_base_task(), browser_tools_available=True)
        without = build_coder_instructions(_base_task(), browser_tools_available=False)
        assert "Browser (Chrome DevTools MCP)" in with_browser
        assert "Browser (Chrome DevTools MCP)" not in without
        assert "discover_ui" in with_browser

    def test_context7_line_conditioned(self):
        with_c7 = build_coder_instructions(_base_task(), context7_available=True)
        assert "ONLY for external libraries" in with_c7
        without = build_coder_instructions(_base_task())
        assert "resolve_library_id" not in without

    def test_devtools_preview_prepended_with_browser(self):
        instructions = build_coder_instructions(_base_task(), browser_tools_available=True)
        assert "### SKILL: devtools-preview" in instructions


# ============================================================
# Assemblage Agent avec toolsets (0 LLM)
# ============================================================


class TestAgentAssemblyWithToolsets:
    def test_agent_constructs_with_helpers_toolset(self, helpers):
        from pydantic_ai.models.test import TestModel

        toolset, _ = helpers
        agent = build_coder_agent(
            TestModel(),
            _base_task(),
            load_settings(),
            coder_max_tokens=2048,
            browser_tools_available=True,
            guards=False,
            toolsets=[toolset],
        )
        assert agent is not None

    def test_agent_constructs_without_toolsets(self):
        from pydantic_ai.models.test import TestModel

        agent = build_coder_agent(
            TestModel(),
            _base_task(),
            load_settings(),
            coder_max_tokens=2048,
            guards=False,
        )
        assert agent is not None

    def test_tool_choice_auto_only_with_toolsets(self, helpers):
        """F-160 : llama-server encode tool_choice='required' en grammaire GBNF
        d'union qui casse au-delà de ~45-60 outils (mesuré 45 OK / 62 KO) —
        avec des toolsets MCP on force 'auto' (pas de grammaire contrainte)."""
        from pydantic_ai.models.test import TestModel

        toolset, _ = helpers
        agent_with = build_coder_agent(
            TestModel(), _base_task(), load_settings(), coder_max_tokens=2048,
            guards=False, toolsets=[toolset],
        )
        assert agent_with.model_settings["tool_choice"] == "auto"

        agent_without = build_coder_agent(
            TestModel(), _base_task(), load_settings(), coder_max_tokens=2048,
            guards=False,
        )
        assert "tool_choice" not in agent_without.model_settings
