"""F-171 — Vérificateurs déterministes autour du Coder (mandat run v5).

Run v5 (2026-08-25, logs/run_coding_20260825_135356) : itération 2 tuée à 40
pas avec un bug runtime ``init()`` (récursion infinie → ``RangeError``) que
NI la syntaxe NI le lint ne voient — seul un chargement navigateur le révèle ;
et le finding d'assertion du Tester restait lossy partout. Deux briques
testées ici sans LLM :

- **A** : capability Hooks ``after_tool_execute`` (filtre outils d'écriture)
  qui appose findings statiques CONSULTATIFS au retour d'outil — intégration
  RÉELLE via ``TestModel`` pydantic-ai (le hook est exercé par le moteur,
  pas mocké) ;
- **B** : smoke navigateur déterministe (Chrome headless stderr) branché au
  chemin verdict F-170 — tour correctif borné après un run réussi, findings
  injectés dans le sauvetage post-budget. Parser testé sur la ligne EXACTE
  du bug run v5.
"""

import asyncio
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from graph_orchestrator.coder_pydantic import (
    _SMOKE_FEEDBACK_PROMPT,
    _run_agent_with_budget_salvage,
)
from graph_orchestrator.coder_verifier import (
    WRITE_TOOL_NAMES,
    build_verifier_hooks,
    parse_console_errors,
    resolve_smoke_targets,
    run_smoke_check,
    run_static_verify,
)
from graph_orchestrator.models import CoderOutput

# Ligne EXACTE capturée en live sur le livrable buggé du run v5 (Chrome
# headless stderr, 2026-08-25 15:04) — régression guard du parser.
_V5_REAL_LINE = (
    '[19104:24904:0825/150421.402:INFO:CONSOLE:25] '
    '"Uncaught RangeError: Maximum call stack size exceeded", '
    'source: file:///D:/GIT/graph-orchestrator-smolagents/runs/x/script.js (25)'
)


# ==========================================
# B — parser console stderr Chrome
# ==========================================

class TestParseConsoleErrors:
    def test_real_v5_line_is_caught(self):
        findings = parse_console_errors(_V5_REAL_LINE)
        assert len(findings) == 1
        assert "Uncaught RangeError" in findings[0]
        assert "script.js:25" in findings[0]

    def test_old_console_paren_format(self):
        line = '[1:2:3:INFO:CONSOLE(0)] "Uncaught TypeError: x is not a function", source: file:///a/app.js (42)'
        findings = parse_console_errors(line)
        assert len(findings) == 1
        assert "app.js:42" in findings[0]

    def test_benign_console_log_ignored(self):
        line = '[1:2:3:INFO:CONSOLE(0)] "hello from console.log", source: file:///x/s.js (10)'
        assert parse_console_errors(line) == []

    def test_chrome_internal_warning_ignored(self):
        line = '[1:2:0825/150420.110:WARNING:chrome\\browser\\x.cc:236] Error observing HKLM: Accès refusé. (0x5)'
        assert parse_console_errors(line) == []

    def test_dedup_and_cap(self):
        spam = "\n".join([_V5_REAL_LINE] * 9)
        assert len(parse_console_errors(spam)) == 1


# ==========================================
# A — vérification statique post-écriture
# ==========================================

_BAD_JS = "const grid = [(1, 2), (3, 4)];\nconsole.log(grid);\n"  # tuple Python → fuite détectée
_GOOD_JS = "'use strict';\nconst xs = [[1, 2]];\nconsole.log(xs);\n"


class TestRunStaticVerify:
    def test_python_tuple_leak_in_js_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.js")
            with open(p, "w", encoding="utf-8") as f:
                f.write(_BAD_JS)
            findings = run_static_verify(p)
            assert findings, "la fuite de syntaxe Python doit être détectée"

    def test_clean_js_has_no_finding(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "good.js")
            with open(p, "w", encoding="utf-8") as f:
                f.write(_GOOD_JS)
            assert run_static_verify(p) == []

    def test_unsupported_extension_fail_open(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "note.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write("du texte")
            assert run_static_verify(p) == []


class TestBuildVerifierHooks:
    def test_disabled_returns_none(self):
        s = SimpleNamespace(coder_static_verify=False)
        assert build_verifier_hooks(s) is None

    def test_enabled_returns_hooks(self):
        s = SimpleNamespace(coder_static_verify=True)
        hooks = build_verifier_hooks(s)
        assert hooks is not None

    def test_write_tool_names_cover_coder_writes(self):
        assert set(WRITE_TOOL_NAMES) == {"append_file", "search_replace", "multi_replace"}

    def test_hook_appends_advisory_to_tool_result_real_agent(self):
        """Intégration RÉELLE : Agent pydantic-ai + FunctionModel (tool_call
        scripté avec les EXACTS arguments) — le hook doit apposer le bloc
        F-171 au résultat du tool d'écriture d'un mauvais fichier JS."""
        from pydantic_ai import Agent
        from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
        from pydantic_ai.models.function import FunctionModel, AgentInfo

        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "app.js")

            def append_file(path: str, content: str) -> str:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(_BAD_JS)
                return "written."

            calls = {"n": 0}

            def model_fn(messages, info: AgentInfo) -> ModelResponse:
                calls["n"] += 1
                if calls["n"] == 1:
                    return ModelResponse(
                        parts=[ToolCallPart(
                            "append_file",
                            {"path": bad, "content": "x"},
                            tool_call_id="c1",
                        )]
                    )
                return ModelResponse(parts=[TextPart(content='done')])

            agent = Agent(
                FunctionModel(model_fn),
                capabilities=[build_verifier_hooks(SimpleNamespace(coder_static_verify=True))],
                tools=[append_file],
            )
            result = agent.run_sync("build the file")
            all_text = str(result.all_messages())
            assert "F-171 vérificateur" in all_text, (
                "le retour d'outil doit porter le bloc consultatif F-171"
            )

    def test_hook_silent_on_clean_write_real_agent(self):
        from pydantic_ai import Agent
        from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
        from pydantic_ai.models.function import FunctionModel, AgentInfo

        with tempfile.TemporaryDirectory() as d:
            clean = os.path.join(d, "ok.js")

            def append_file(path: str, content: str) -> str:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(_GOOD_JS)
                return "written."

            calls = {"n": 0}

            def model_fn(messages, info: AgentInfo) -> ModelResponse:
                calls["n"] += 1
                if calls["n"] == 1:
                    return ModelResponse(
                        parts=[ToolCallPart(
                            "append_file",
                            {"path": clean, "content": "x"},
                            tool_call_id="c1",
                        )]
                    )
                return ModelResponse(parts=[TextPart(content='done')])

            agent = Agent(
                FunctionModel(model_fn),
                capabilities=[build_verifier_hooks(SimpleNamespace(coder_static_verify=True))],
                tools=[append_file],
            )
            result = agent.run_sync("build the file")
            assert "F-171 vérificateur" not in str(result.all_messages())


# ==========================================
# B — smoke navigateur
# ==========================================

class TestRunSmokeCheck:
    def test_skips_without_chrome(self):
        with patch("graph_orchestrator.browser_pool.find_chrome_executable", return_value=None):
            res = run_smoke_check(["whatever.html"])
            assert res.skipped
            assert res.findings == []

    def test_skips_without_targets_on_disk(self):
        res = run_smoke_check([os.path.join(tempfile.gettempdir(), "absent_f171.html")])
        assert res.skipped

    @pytest.mark.skipif(
        not pytest.importorskip("graph_orchestrator.browser_pool", reason="module")
        or not __import__(
            "graph_orchestrator.browser_pool", fromlist=["find_chrome_executable"]
        ).find_chrome_executable(),
        reason="Chrome non disponible",
    )
    def test_live_buggy_page_flagged_clean_page_silent(self):
        """Boucle récursive infinie (famille init() run v5) → finding ;
        page saine → silence (garde anti faux positifs)."""
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.html")
            with open(bad, "w", encoding="utf-8") as f:
                f.write(
                    "<!DOCTYPE html><html><body><script>function r(){return r();} "
                    "r();</script></body></html>"
                )
            res = run_smoke_check([bad])
            assert not res.skipped
            assert res.findings and "Uncaught" in res.findings[0]

            clean = os.path.join(d, "clean.html")
            with open(clean, "w", encoding="utf-8") as f:
                f.write(
                    '<!DOCTYPE html><html><body><div id="ok"></div>'
                    '<script>document.getElementById("ok").textContent = "done";'
                    "</script></body></html>"
                )
            res2 = run_smoke_check([clean])
            assert not res2.skipped
            assert res2.findings == []


class TestResolveSmokeTargets:
    def test_only_html_targets_kept(self):
        task = {"target_files": ["index.html", "styles.css", "script.js", "page.htm"]}
        assert resolve_smoke_targets(task) == ["index.html", "page.htm"]

    def test_no_targets(self):
        assert resolve_smoke_targets({"target_files": ["main.py"]}) == []
        assert resolve_smoke_targets({}) == []


# ==========================================
# B — intégration chemin verdict F-170
# ==========================================

def _settings(smoke=True):
    return SimpleNamespace(coder_max_steps=60, coder_smoke_verdict=smoke)


class _FakeAgent:
    """Agent minimal : script d'exécutions piloté par une file de
    comportements (chaque entrée = (prompt_matcher, résultat ou exception))."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def run(self, user_prompt, usage_limits=None, message_history=None):
        self.calls.append(
            {
                "prompt": user_prompt,
                "usage_limits": usage_limits,
                "history": message_history,
            }
        )
        action = self.script.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


def _result(status="success"):
    return SimpleNamespace(output=CoderOutput(task_id="st1", status=status, details="x"))


class TestSalvageSmokeIntegration:
    def test_success_clean_smoke_single_call(self):
        agent = _FakeAgent([_result()])
        with patch(
            "graph_orchestrator.coder_verifier.run_smoke_check",
            return_value=SimpleNamespace(skipped="", checked=["index.html"], findings=[]),
        ):
            out = asyncio.run(
                _run_agent_with_budget_salvage(
                    agent, "go", _settings(), smoke_html_paths=["index.html"]
                )
            )
        assert out is not None and out.output.status == "success"
        assert len(agent.calls) == 1, "console propre → PAS de tour correctif"

    def test_success_smoke_findings_trigger_bounded_corrective_round(self):
        agent = _FakeAgent([_result(), _result()])
        with patch(
            "graph_orchestrator.coder_verifier.run_smoke_check",
            return_value=SimpleNamespace(
                skipped="", checked=["index.html"],
                findings=['index.html → "Uncaught RangeError: ..." (script.js:25)'],
            ),
        ):
            out = asyncio.run(
                _run_agent_with_budget_salvage(
                    agent, "go", _settings(), smoke_html_paths=["index.html"]
                )
            )
        assert len(agent.calls) == 2
        second = agent.calls[1]
        assert "DETERMINISTIC SMOKE TEST" in second["prompt"]
        assert "Uncaught RangeError" in second["prompt"]
        assert second["usage_limits"].request_limit == 5
        assert second["history"] is not None, "le tour correctif rejoue l'historique"
        assert out.output.status == "success"

    def test_success_smoke_corrective_failure_keeps_initial_verdict(self):
        agent = _FakeAgent([_result(), RuntimeError("boom")])
        with patch(
            "graph_orchestrator.coder_verifier.run_smoke_check",
            return_value=SimpleNamespace(
                skipped="", checked=["index.html"], findings=["index.html → x"]
            ),
        ):
            out = asyncio.run(
                _run_agent_with_budget_salvage(
                    agent, "go", _settings(), smoke_html_paths=["index.html"]
                )
            )
        assert out is not None and out.output.status == "success"

    def test_budget_exhausted_smoke_findings_injected_in_salvage_prompt(self):
        from pydantic_ai.exceptions import UsageLimitExceeded

        agent = _FakeAgent([UsageLimitExceeded("request limit"), _result(status="failure")])
        with patch(
            "graph_orchestrator.coder_verifier.run_smoke_check",
            return_value=SimpleNamespace(
                skipped="", checked=["index.html"],
                findings=['index.html → "Uncaught RangeError" (script.js:25)'],
            ),
        ):
            out = asyncio.run(
                _run_agent_with_budget_salvage(
                    agent, "go", _settings(), smoke_html_paths=["index.html"]
                )
            )
        salvage_call = agent.calls[1]
        assert "NO TOOLS" in salvage_call["prompt"], "prompt de sauvetage F-170 conservé"
        assert "SMOKE TEST F-171" in salvage_call["prompt"]
        assert "Uncaught RangeError" in salvage_call["prompt"]
        assert salvage_call["usage_limits"].request_limit == 3
        assert out.output.status == "failure"

    def test_smoke_disabled_by_setting(self):
        agent = _FakeAgent([_result()])
        with patch(
            "graph_orchestrator.coder_verifier.run_smoke_check"
        ) as smoke_mock:
            out = asyncio.run(
                _run_agent_with_budget_salvage(
                    agent, "go", _settings(smoke=False), smoke_html_paths=["index.html"]
                )
            )
        smoke_mock.assert_not_called()
        assert len(agent.calls) == 1
        assert out.output.status == "success"

    def test_smoke_feedback_prompt_contract(self):
        p = _SMOKE_FEEDBACK_PROMPT
        assert "{findings}" in p
        assert "search_replace" in p
        assert "check_js_syntax" in p
