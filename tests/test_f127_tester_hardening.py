"""Tests F-127 (post-mortem run 2026-08-19_2104) : durcissements Testers.

Run 2026-08-19_2104 (Tetris) : livrable SAIN (0 erreur console, vérifié en
direct) rejeté 2× par des verdicts Tester fantômes :
1. Web Tester (8 steps) : 4 steps perdus à découvrir l'ID du canvas + 2 erreurs
   MCP -32602 (enum `types` inventé « exception ») → max steps → final_answer
   en prose → verdict générique « problème de syntaxe JS » (faux).
2. Re-test ciblé (6 steps) : le Tester consigne sa PROPRE erreur (NameError
   evaluate_script, probe null sur mauvais ID) → max steps → failure.

Fixes testés :
- TARGETED_MAX_STEPS 6 → 10 (TESTER_MAX_STEPS 8 → 16 déjà fait via .env).
- `_tester_max_steps_fallback` : les erreurs d'OUTILS du Tester (MCP -32602,
  NameError sandbox, probe null) ne comptent plus comme FAIL de l'app ; les
  erreurs « Uncaught » de l'app restent des FAIL.
- `_sanitize_console_kwargs` : l'enum `types` de list_console_messages est
  filtré sur les valeurs valides avant délégation MCP.
- Helper `discover_ui` (inventaire UI en 1 appel, registre factory).
"""

from types import SimpleNamespace

from graph_orchestrator.devtools_dom_tools import (
    DevToolsDiscoverUiTool,
    _DISCOVER_UI_JS,
    build_devtools_helper_tools,
)
from graph_orchestrator.nodes import _tester_max_steps_fallback
from graph_orchestrator.targeted_retest import TARGETED_MAX_STEPS
from graph_orchestrator.vision_callback import (
    _ConsoleEnrichingTool,
    _sanitize_console_kwargs,
)

_PROMPT = 'final_answer({"task_id": "tetris-html-v1", "status": "success", "details": "..."})'


def _step(obs: str):
    return SimpleNamespace(observations=obs, error=None)


# ==========================================
# Budget du re-test ciblé
# ==========================================

class TestTargetedBudget:
    def test_targeted_max_steps_is_16(self):
        """F-127 : 6 tuait le re-test ciblé en découverte d'UI → 10.
        F-141 (run 2026-08-20_1817) : 10 coupait le re-test EN PLEINE vérification
        d'un vrai bug (pause au chargement) → timeout + Judge fail-closed → 16."""
        assert TARGETED_MAX_STEPS == 16


# ==========================================
# Fallback max-steps : erreurs d'outils ≠ FAIL de l'app
# ==========================================

class TestFallbackToolErrorExclusion:

    def test_tool_errors_only_with_pass_is_success(self):
        """Run 2104 rejet 1 : probes null + MCP -32602 mais assertion PASS → SUCCESS.

        Avant F-127 : les marqueurs « typeerror »/« failed » des lignes d'erreur
        d'outils déclenchaient failure → rejet fantôme d'un livrable sain.
        """
        steps = [
            _step("Out: Error: Cannot read properties of null (reading 'width')"),
            _step("Out: MCP error -32602: Input validation error: Invalid enum value. "
                  "Expected 'log' | 'debug', received 'exception'"),
            _step('{"canvasExists": true, "score": 0} — assertion passed'),
        ]
        out = _tester_max_steps_fallback(steps, _PROMPT)
        assert out is not None and out.status == "success"

    def test_nameerror_of_tester_code_not_a_fail(self):
        """Run 2104 rejet 2 : « evaluate_script is not defined » = erreur du Tester."""
        steps = [
            _step("Traceback (most recent call last): NameError: name 'evaluate_script' "
                  "is not defined"),
            _step("verdict: pass — le canvas affiche des pièces"),
        ]
        out = _tester_max_steps_fallback(steps, _PROMPT)
        assert out is not None and out.status == "success"

    def test_real_uncaught_app_error_still_fails(self):
        """Une erreur console de l'APP (« Uncaught ») reste un FAIL valide."""
        steps = [
            _step("## Console messages\nmsgid=1 [error] Uncaught TypeError: Cannot read "
                  "properties of undefined (reading '0')"),
        ]
        out = _tester_max_steps_fallback(steps, _PROMPT)
        assert out is not None and out.status == "failure"
        assert "Uncaught" in out.details

    def test_uncaught_null_error_not_masked_by_probe_rule(self):
        """Garde-frontière : « Uncaught TypeError ... properties of NULL » (app) ne doit
        PAS être exclu par la règle du probe (préfixe « Error: » ancré)."""
        steps = [
            _step("msgid=1 [error] Uncaught TypeError: Cannot read properties of null "
                  "(reading 'x')"),
        ]
        out = _tester_max_steps_fallback(steps, _PROMPT)
        assert out is not None and out.status == "failure"

    def test_explicit_assertion_fail_still_fails(self):
        steps = [_step("Assertion failed: le compteur de lignes reste à 0 après 1 ligne complétée")]
        out = _tester_max_steps_fallback(steps, _PROMPT)
        assert out is not None and out.status == "failure"

    def test_no_signal_still_failure(self):
        """0 observation → failure (ne valide pas à l'aveugle) — comportement F-61 conservé."""
        out = _tester_max_steps_fallback([], _PROMPT)
        assert out is not None and out.status == "failure"


# ==========================================
# Sanitisation de l'enum types (list_console_messages)
# ==========================================

class TestConsoleTypesSanitizer:

    def test_invalid_value_filtered(self):
        """Run 2104 : types=["error", "exception"] → seul "error" survit."""
        out = _sanitize_console_kwargs({"types": ["error", "exception"]})
        assert out["types"] == ["error"]

    def test_all_invalid_removes_arg(self):
        out = _sanitize_console_kwargs({"types": ["exception", "fatal"]})
        assert "types" not in out  # absence = tous les types (défaut MCP)

    def test_case_insensitive_kept_normalized(self):
        out = _sanitize_console_kwargs({"types": ["ERROR", "Warn"]})
        assert out["types"] == ["ERROR", "Warn"]

    def test_non_list_untouched(self):
        out = _sanitize_console_kwargs({"types": "error", "pageSize": 20})
        assert out == {"types": "error", "pageSize": 20}

    def test_no_types_untouched(self):
        out = _sanitize_console_kwargs({"pageSize": 20})
        assert out == {"pageSize": 20}


class TestConsoleWrapperSanitizesBeforeDelegate:

    def test_forward_passes_sanitized_types(self):
        captured = {}

        class _FakeList:
            name = "list_console_messages"
            description = "liste"
            inputs = {}
            output_type = "string"

            def forward(self, *args, **kwargs):
                captured.update(kwargs)
                return "## Console messages\nShowing 0 of 0."

        class _FakeDetail:
            name = "get_console_message"

            def __call__(self, msgid):
                return "ID: 1\n"

        wrapped = _ConsoleEnrichingTool(_FakeList(), _FakeDetail())
        wrapped.forward(types=["error", "exception"], pageSize=10)
        assert captured["types"] == ["error"]
        assert captured["pageSize"] == 10


# ==========================================
# Helper discover_ui
# ==========================================

class _FakeEvalTool:
    name = "evaluate_script"
    description = "eval"
    inputs = {}
    output_type = "string"

    def __init__(self):
        self.received = None

    def __call__(self, *args, **kwargs):
        return self.forward(*args, **kwargs)

    def forward(self, *args, **kwargs):
        self.received = kwargs
        return '{"canvases": [{"id": "gameCanvas"}]}'


class TestDiscoverUi:

    def test_js_inventories_canvases_buttons_inputs(self):
        js = _DISCOVER_UI_JS
        assert "canvas" in js and "button" in js and "input, select" in js
        assert "JSON.stringify" in js

    def test_registered_first_in_factory(self):
        tools = build_devtools_helper_tools([_FakeEvalTool()])
        names = [t.name for t in tools]
        assert "discover_ui" in names
        assert names[0] == "discover_ui"  # poussé en tête (à appeler EN PREMIER)

    def test_forward_delegates_to_evaluate_script(self):
        fake = _FakeEvalTool()
        tool = DevToolsDiscoverUiTool(fake)
        out = tool.forward()
        assert fake.received is not None and "function" in fake.received
        assert "gameCanvas" in out

    def test_factory_failopen_without_eval(self):
        assert build_devtools_helper_tools([]) == []
