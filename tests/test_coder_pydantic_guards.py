"""Tests F-159 — gardes & compaction du Coder pydantic (phases 3.3-3.4), 0 LLM / 0 réseau.

Couvre : LoopGuard v2 (fenêtre/nudges/abort), StallDetector porté, churn/gels
navigateur (F-125/129), IdleBreaker, GoalGate (continuation ModelRetry + waive),
ReviveRetry (classification + revive + échange de modèle), SystemReminders
dynamiques (pop-once, wind-down F-131, checklist F-114), assemblage des
capabilities (guards on/off), et un run d'intégration FunctionModel qui rejoue
une boucle d'édition stérile à travers le VRAI build_coder_agent.
"""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graph_orchestrator.coder_pydantic_guards import (
    LOOP_ABORT,
    LOOP_NUDGE_APPROACH,
    LOOP_NUDGE_CANON,
    LOOP_WINDOW,
    CoderGuardState,
    GoalGateCapability,
    GuardAbort,
    IdleBreakerCapability,
    ReviveRetryCapability,
    ToolGuardsCapability,
    _fingerprint,
    as_capabilities,
    build_compaction_capabilities,
    build_guard_reminders,
    read_file_key,
)
from graph_orchestrator.config import load_settings
from graph_orchestrator.llm_retry import RetryPolicy
from graph_orchestrator.models import CoderOutput


def _state_with_guard(**kwargs) -> tuple:
    state = CoderGuardState()
    guard = ToolGuardsCapability(state, **kwargs)
    return state, guard


def _repeat(guard, tool: str, args: dict, result, n: int):
    for _ in range(n):
        guard._record(tool, dict(args), result)


# ============================================================
# État partagé & fingerprint
# ============================================================

class TestGuardStateAndFingerprint:
    def test_reset_clears_everything(self):
        state, guard = _state_with_guard()
        _repeat(guard, "search_replace", {"path": "a"}, "err", 3)
        state.reset()
        assert state.total_calls == 0
        assert state.fingerprints == {}
        assert state.loop_nudge is None

    def test_fingerprint_same_call_same_result(self):
        a = _fingerprint("write_file", {"path": "x"}, "ok")
        b = _fingerprint("write_file", {"path": "x"}, "ok")
        assert a == b

    def test_fingerprint_different_result_differs(self):
        """Vol crush : un résultat différent = pas une boucle stérile."""
        a = _fingerprint("list_directory", {"path": "."}, "avant")
        b = _fingerprint("list_directory", {"path": "."}, "après")
        assert a != b


# ============================================================
# LoopGuard v2 — nudges à 3/5, abort à 8, fenêtre 10, exemptions
# ============================================================

class TestLoopGuardV2:
    def test_nudge_canonicalize_at_3(self):
        state, guard = _state_with_guard()
        _repeat(guard, "search_replace", {"path": "a.js", "old_string": "x"}, "not found", LOOP_NUDGE_CANON)
        assert state.loop_nudge and "Canonicalize" in state.loop_nudge

    def test_nudge_change_approach_at_5(self):
        state, guard = _state_with_guard()
        _repeat(guard, "search_replace", {"path": "a.js"}, "not found", LOOP_NUDGE_APPROACH)
        assert state.loop_nudge and "CHANGE YOUR APPROACH" in state.loop_nudge

    def test_hard_stop_at_8(self):
        state, guard = _state_with_guard()
        with pytest.raises(GuardAbort, match="Loop guard"):
            _repeat(guard, "search_replace", {"path": "a.js"}, "not found", LOOP_ABORT)

    def test_different_results_no_abort(self):
        state, guard = _state_with_guard()
        for i in range(12):
            guard._record("list_directory", {"path": "."}, f"listing v{i}")
        assert state.total_calls == 12
        assert "Loop guard" not in (state.loop_nudge or "")

    def test_observational_tool_exempt(self):
        """read_file répété (F-130) : exempté du LoopGuard — pris en charge
        STRUCTURELLEMENT par DeduplicateFileReads (plan §3.4)."""
        state, guard = _state_with_guard()
        _repeat(guard, "read_file", {"path": "a.js"}, "contenu", LOOP_ABORT + 5)
        assert state.loop_nudge is None

    def test_window_prunes_old_occurrences(self):
        """Fenêtre glissante : 6 répétitions, 5 appels différents, 1 de plus
        → compteur raboté par la fenêtre, pas d'abort."""
        state, guard = _state_with_guard()
        _repeat(guard, "search_replace", {"path": "a.js"}, "not found", 6)
        for i in range(5):
            guard._record("search_replace", {"path": f"f{i}.js"}, "not found")
        # les 6 anciennes occurrences sont partiellement hors fenêtre (10)
        guard._record("search_replace", {"path": "a.js"}, "not found")
        assert state.total_calls == 12  # aucun abort levé = fenêtre effective


# ============================================================
# StallDetector (F-88 porté) — hash du livrable matériel
# ============================================================

class TestStallDetectorPort:
    def test_identical_material_stalls(self):
        """Sémantique F-88 : seuil 2 = 2 incrémentS consécutifs → 3 écritures
        identiques au total (la 1re pose le hash de référence)."""
        state, guard = _state_with_guard(stall_threshold=2)
        for _ in range(3):
            guard._record("write_file", {"path": "a.js", "content": "let x = 1;"}, "ok")
        assert state.stall_nudge and "IDENTICAL material" in state.stall_nudge

    def test_different_material_resets(self):
        state, guard = _state_with_guard(stall_threshold=2)
        guard._record("write_file", {"path": "a.js", "content": "v1"}, "ok")
        guard._record("write_file", {"path": "a.js", "content": "v2"}, "ok")
        assert state.stall_nudge is None

    def test_verification_tool_resets(self):
        """Exemption F-151 : un tour de vérification (check_js_syntax) remet
        le compteur de stall à zéro."""
        state, guard = _state_with_guard(stall_threshold=2)
        guard._record("write_file", {"path": "a.js", "content": "v1"}, "ok")
        guard._record("check_js_syntax", {"path": "a.js"}, "no error")
        guard._record("write_file", {"path": "a.js", "content": "v1"}, "ok")
        assert state.stall_nudge is None
        assert state.verify_calls == 1


# ============================================================
# Churn d'édition + gels navigateur (F-125/129 — détection portée)
# ============================================================

class TestChurnAndBrowserStall:
    def test_edit_churn_nudge_at_5(self):
        state, guard = _state_with_guard()
        _repeat(guard, "search_replace", {"path": "a.js", "old_string": "z"}, "introuvable", 5)
        assert state.churn_nudge and "EDIT CHURN" in state.churn_nudge

    def test_edit_success_resets_churn(self):
        state, guard = _state_with_guard()
        _repeat(guard, "search_replace", {"path": "a.js", "old_string": "z"}, "introuvable", 4)
        guard._record("search_replace", {"path": "a.js", "old_string": "y"}, "Successfully edited")
        assert state.churn_fail == 0
        assert state.churn_nudge is None

    def test_nav_freeze_immediate_f129(self):
        """F-129 : « Navigation timeout » → nudge immédiat (1re occurrence)."""
        state, guard = _state_with_guard()
        guard._record("navigate_page", {"url": "index.html"}, "Navigation timeout of 30000 ms exceeded")
        assert state.browser_nudge and "NAV FREEZE" in state.browser_nudge

    def test_browser_stall_threshold_f125(self):
        state, guard = _state_with_guard(browser_stall_threshold=3)
        guard._record("take_screenshot", {}, "Operation timed out")
        guard._record("take_screenshot", {}, "Operation timed out")
        assert state.browser_nudge is None  # 2 < seuil 3
        guard._record("take_screenshot", {}, "Protocol error: timed out")
        assert state.browser_nudge and "BROWSER STALL" in state.browser_nudge

    def test_healthy_result_resets_browser_stall(self):
        state, guard = _state_with_guard(browser_stall_threshold=3)
        guard._record("navigate_page", {"url": "a"}, "timed out")
        guard._record("navigate_page", {"url": "a"}, "ok loaded")  # sain → reset
        guard._record("navigate_page", {"url": "a"}, "timed out")
        assert state.browser_nudge is None


# ============================================================
# IdleBreaker (F-61)
# ============================================================

class TestIdleBreaker:
    @pytest.mark.anyio
    async def test_consecutive_idle_turns_abort(self):
        from pydantic_ai.messages import ModelResponse, TextPart

        state = CoderGuardState()
        breaker = IdleBreakerCapability(state, threshold=3)
        for i in range(2):
            response = await breaker.after_model_request(
                None, request_context=None,
                response=ModelResponse(parts=[TextPart(f"parle sans agir {i}")]),
            )
            assert state.idle_nudge and "[IDLE]" in state.idle_nudge
        with pytest.raises(GuardAbort, match="Idle breaker"):
            await breaker.after_model_request(
                None, request_context=None,
                response=ModelResponse(parts=[TextPart("encore")]),
            )

    @pytest.mark.anyio
    async def test_tool_call_resets_idle(self):
        from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart

        state = CoderGuardState()
        breaker = IdleBreakerCapability(state, threshold=3)
        await breaker.after_model_request(
            None, request_context=None, response=ModelResponse(parts=[TextPart("blabla")])
        )
        await breaker.after_model_request(
            None, request_context=None,
            response=ModelResponse(parts=[ToolCallPart("write_file", {"path": "x"}, tool_call_id="c1")]),
        )
        assert state.idle_count == 0


# ============================================================
# GoalGate (F-99) — continuation ModelRetry + waive
# ============================================================

def _goal_agent(task, settings, cwd):
    """Agent minimal équipé du GoalGate ; le modèle sort success immédiatement."""
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel, AgentInfo

    state = CoderGuardState()
    caps = [
        ToolGuardsCapability(state),
        GoalGateCapability(state, task=task, settings=settings, cwd=cwd),
    ]

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        out = CoderOutput(
            task_id=task["id"], status="success", details="done",
            linter_ok=True, vision_ok=False,
        )
        return ModelResponse(
            parts=[ToolCallPart("final_result", out.model_dump(mode="json"), tool_call_id="c1")]
        )

    return Agent(FunctionModel(model_fn), capabilities=caps, output_type=CoderOutput), state


class TestGoalGate:
    @pytest.mark.anyio
    async def test_missing_disk_proof_triggers_continuation_then_waive(self, tmp_path):
        """Création it.1 + fichier ABSENT → ModelRetry (RetryPromptPart dans
        l'historique) ; 2e success → WAIVE (le Judge arbitre)."""
        task = {"id": "st1", "content": "Build a page", "target_files": ["index.html"], "iteration": 1}
        settings = load_settings()
        agent, state = _goal_agent(task, settings, str(tmp_path))
        result = await agent.run("do it")
        assert result.output.status == "success"  # waivé, pas bloqué
        assert state.goal_gate_fired == 1
        kinds = [type(p).__name__ for m in result.all_messages() for p in getattr(m, "parts", [])]
        assert "RetryPromptPart" in kinds

    @pytest.mark.anyio
    async def test_disk_proof_passes_without_continuation(self, tmp_path):
        (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
        task = {"id": "st1", "content": "Build", "target_files": ["index.html"], "iteration": 1}
        settings = load_settings()
        agent, state = _goal_agent(task, settings, str(tmp_path))
        result = await agent.run("do it")
        assert state.goal_gate_fired == 0

    @pytest.mark.anyio
    async def test_disabled_gate_no_continuation(self, tmp_path):
        import dataclasses

        task = {"id": "st1", "content": "Build", "target_files": ["index.html"], "iteration": 1}
        settings = dataclasses.replace(load_settings(), goal_enforcement_enabled=False)
        agent, state = _goal_agent(task, settings, str(tmp_path))
        await agent.run("do it")
        assert state.goal_gate_fired == 0


# ============================================================
# ReviveRetry (F-104)
# ============================================================

def _fast_policy() -> RetryPolicy:
    return RetryPolicy(max_retries=2, base_delay_s=0.001, max_delay_s=0.002, jitter_factor=0.0)


class TestReviveRetry:
    @pytest.mark.anyio
    async def test_retryable_error_recovers_and_revives(self):
        attempts = {"n": 0}
        revive_calls = {"n": 0}
        bases = {"current": "http://old"}

        async def handler(request_context):
            attempts["n"] += 1
            if attempts["n"] <= 2:
                raise ConnectionError("connection refused")
            return "ok"

        def revive():
            revive_calls["n"] += 1
            return "http://new" if revive_calls["n"] == 1 else "http://new"

        cap = ReviveRetryCapability(
            policy=_fast_policy(), revive=revive,
            model_factory=lambda base: f"model@{base}",
            current_base=bases["current"],
        )
        result = await cap.wrap_model_request(None, request_context=SimpleNamespace(model="m0"), handler=handler)
        assert result == "ok"
        assert attempts["n"] == 3
        assert revive_calls["n"] == 2

    @pytest.mark.anyio
    async def test_model_swapped_when_base_changes(self):
        swaps = []

        async def handler(request_context):
            if not getattr(request_context, "_called", False):
                request_context._called = True
                raise ConnectionError("reset by peer")
            return "ok"

        cap = ReviveRetryCapability(
            policy=_fast_policy(),
            revive=lambda: "http://new-port",
            model_factory=lambda base: swaps.append(base) or f"model@{base}",
            current_base="http://old-port",
        )
        rc = SimpleNamespace(model="old-model")
        await cap.wrap_model_request(None, request_context=rc, handler=handler)
        assert rc.model == "model@http://new-port"
        assert swaps == ["http://new-port"]

    @pytest.mark.anyio
    async def test_fatal_error_raises_immediately(self):
        revive_calls = {"n": 0}

        async def handler(request_context):
            raise RuntimeError("Error code: 401 - Unauthorized")

        cap = ReviveRetryCapability(
            policy=_fast_policy(), revive=lambda: revive_calls.__setitem__("n", revive_calls["n"] + 1) or None
        )
        with pytest.raises(RuntimeError, match="401"):
            await cap.wrap_model_request(None, request_context=SimpleNamespace(), handler=handler)
        assert revive_calls["n"] == 0  # fatal → jamais de revive

    @pytest.mark.anyio
    async def test_exhaustion_raises_last(self):
        async def handler(request_context):
            raise ConnectionError("still down")

        cap = ReviveRetryCapability(policy=_fast_policy())
        with pytest.raises(ConnectionError, match="still down"):
            await cap.wrap_model_request(None, request_context=SimpleNamespace(), handler=handler)

    @pytest.mark.anyio
    async def test_policy_none_passthrough(self):
        calls = {"n": 0}

        async def handler(request_context):
            calls["n"] += 1
            return "direct"

        cap = ReviveRetryCapability(policy=None)
        assert await cap.wrap_model_request(None, request_context=None, handler=handler) == "direct"
        assert calls["n"] == 1


# ============================================================
# SystemReminders dynamiques (nudges) — pop-once, F-131, F-114
# ============================================================

class TestGuardReminders:
    def _settings_task(self, **task_overrides):
        task = {
            "id": "st1",
            "content": "Build",
            "target_files": ["index.html"],
            "iteration": 1,
            "visual_success_criteria": ["bars visible", "counter live", "sorted colors"],
        }
        task.update(task_overrides)
        return load_settings(), task

    def test_pending_nudge_pops_once(self):
        settings, task = self._settings_task()
        state = CoderGuardState()
        reminders = build_guard_reminders(state, task, settings)
        dynamics = list(reminders.dynamic_reminders)
        poppers = [d for d in dynamics if callable(d) and getattr(d, "__name__", "") == "_loop"]
        assert poppers, "reminder _loop absent de l'assemblage"
        state.loop_nudge = "[LOOP GUARD] test"
        ctx = SimpleNamespace(run_step=1)
        assert poppers[0](ctx) == "[LOOP GUARD] test"
        assert poppers[0](ctx) is None  # pop-once : pas d'accumulation

    def test_wind_down_fires_near_limit_with_incomplete_checklist(self, monkeypatch):
        settings, task = self._settings_task()
        monkeypatch.setattr(
            "graph_orchestrator.tools.get_visual_audit",
            lambda: [{"criterion_number": 1, "verdict": True, "observation": "ok"}],
        )
        state = CoderGuardState()
        reminders = build_guard_reminders(state, task, settings)
        dynamics = {getattr(d, "__name__", ""): d for d in reminders.dynamic_reminders}
        remaining_3 = SimpleNamespace(run_step=settings.coder_max_steps - 3)
        text = dynamics["_wind_down"](remaining_3)
        assert text and "WIND-DOWN" in text and "1/3" in text
        # trop tôt → rien
        assert dynamics["_wind_down"](SimpleNamespace(run_step=2)) is None

    def test_checklist_fires_when_criteria_missing(self, monkeypatch):
        settings, task = self._settings_task()
        monkeypatch.setattr("graph_orchestrator.tools.get_visual_audit", lambda: [])
        state = CoderGuardState()
        reminders = build_guard_reminders(state, task, settings)
        dynamics = {getattr(d, "__name__", ""): d for d in reminders.dynamic_reminders}
        text = dynamics["_checklist"](SimpleNamespace(run_step=7))
        assert text and "CHECKLIST" in text and "[1, 2, 3]" in text
        # audit complet → rien
        monkeypatch.setattr(
            "graph_orchestrator.tools.get_visual_audit",
            lambda: [{"criterion_number": i, "verdict": True, "observation": "ok"} for i in (1, 2, 3)],
        )
        assert dynamics["_checklist"](SimpleNamespace(run_step=7)) is None

    def test_goal_reanchor_present(self):
        from pydantic_ai_harness.system_reminders import GoalReanchor

        settings, task = self._settings_task()
        reminders = build_guard_reminders(CoderGuardState(), task, settings)
        assert any(isinstance(d, GoalReanchor) for d in reminders.dynamic_reminders)


# ============================================================
# Compaction (§3.4) — assemblage
# ============================================================

class TestCompactionAssembly:
    def test_default_tiers_deterministic_last(self):
        import dataclasses

        from pydantic_ai_harness import (
            ClampOversizedMessages,
            ClearToolResults,
            DeduplicateFileReads,
            SlidingWindowCompaction,
            SummarizingCompaction,
            TieredCompaction,
            WarnNearLimits,
        )

        settings = dataclasses.replace(load_settings(), compaction_llm_enabled=False)
        caps = build_compaction_capabilities(settings)
        names = [type(c).__name__ for c in caps]
        assert names == ["DeduplicateFileReads", "TieredCompaction", "WarnNearLimits"]
        tiers = list(caps[1].tiers)
        assert [type(t).__name__ for t in tiers] == [
            "ClampOversizedMessages",
            "ClearToolResults",
            "SlidingWindowCompaction",
        ]
        assert caps[1].target_tokens == settings.compaction_preflight_budget_tokens

    def test_llm_enabled_uses_summarizing_last_tier(self):
        import dataclasses

        from pydantic_ai_harness import SummarizingCompaction

        settings = dataclasses.replace(load_settings(), compaction_llm_enabled=True)
        caps = build_compaction_capabilities(settings)
        assert isinstance(list(caps[1].tiers)[-1], SummarizingCompaction)

    def test_read_file_key(self):
        from pydantic_ai.messages import ToolCallPart

        call = ToolCallPart("read_file", {"path": "src/app.js"}, tool_call_id="c1")
        assert read_file_key(call) == "src/app.js"
        call_skel = ToolCallPart("read_python_skeleton", {"path": "m.py"}, tool_call_id="c2")
        assert read_file_key(call_skel) == "m.py"
        assert read_file_key(ToolCallPart("write_file", {"path": "x"}, tool_call_id="c3")) is None


# ============================================================
# Assemblage build_coder_agent / build_coder_capabilities
# ============================================================

class TestCapabilitiesAssembly:
    def test_guards_on_full_arsenal(self):
        import dataclasses

        from graph_orchestrator.coder_pydantic import build_coder_capabilities
        from pydantic_ai_harness import (
            DeduplicateFileReads,
            FileSystem,
            SystemReminders,
            TieredCompaction,
            ToolOutputLimits,
            WarnNearLimits,
        )

        settings = dataclasses.replace(load_settings(), coder_pydantic_guards=True)
        caps = build_coder_capabilities(
            {"id": "st1", "content": "x", "target_files": ["index.html"], "iteration": 1},
            settings,
        )
        names = [type(c).__name__ for c in caps]
        # production 3.1 + arsenal F-159
        for expected in (
            "FileSystem",
            "ToolOutputLimits",
            "DeduplicateFileReads",
            "TieredCompaction",
            "WarnNearLimits",
            "ToolGuardsCapability",
            "IdleBreakerCapability",
            "GoalGateCapability",
            "SystemReminders",
        ):
            assert expected in names, f"{expected} absent : {names}"
        # extra_capabilities EN TÊTE (wrap le plus externe)
        marker = ToolGuardsCapability(CoderGuardState())
        caps2 = build_coder_capabilities(
            {"id": "s", "content": "x", "iteration": 1}, settings, extra_capabilities=[marker]
        )
        assert caps2[0] is marker

    def test_guards_off_exact_f158(self):
        import dataclasses

        from graph_orchestrator.coder_pydantic import build_coder_capabilities
        from pydantic_ai_harness import ClearToolResults

        settings = dataclasses.replace(load_settings(), coder_pydantic_guards=False)
        caps = build_coder_capabilities(
            {"id": "s", "content": "x", "iteration": 1}, settings, guards=False
        )
        names = [type(c).__name__ for c in caps]
        # F-161 : la ProcessHistory de purge images est INCONDITIONNELLE (elle
        # protège le contexte du nouveau flux image, A/B porté par
        # CODER_PYDANTIC_VISION, plus par guards). Le reste est F-158 exact.
        assert names == ["FileSystem", "ToolOutputLimits", "ProcessHistory", "ClearToolResults"]

    def test_config_flag_default_and_env(self, monkeypatch):
        monkeypatch.delenv("CODER_PYDANTIC_GUARDS", raising=False)
        assert load_settings().coder_pydantic_guards is True
        monkeypatch.setenv("CODER_PYDANTIC_GUARDS", "false")
        assert load_settings().coder_pydantic_guards is False


# ============================================================
# Intégration — run complet via le VRAI build_coder_agent (FunctionModel)
# ============================================================

class TestIntegrationRun:
    @pytest.mark.anyio
    async def test_sterile_edit_loop_aborts_through_full_agent(self, tmp_path, monkeypatch):
        """Rejeu du scénario de gel : le modèle répète le MÊME search_replace
        en échec → nudges (3/5) puis GuardAbort à 8, à travers l'assemblage
        COMPLET (FileSystem + compaction + gardes + reminders)."""
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        from pydantic_ai.models.function import FunctionModel, AgentInfo

        from graph_orchestrator.coder_pydantic import build_coder_agent

        monkeypatch.chdir(tmp_path)
        settings = load_settings()
        task = {
            "id": "st-loop",
            "content": "Build a page",
            "target_files": ["index.html"],
            "strategy": "simple",
            "iteration": 1,
        }
        fired: list = []
        turn = {"n": 0}

        def model_fn(messages, info: AgentInfo) -> ModelResponse:
            turn["n"] += 1
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "search_replace",
                        {"path": "index.html", "old_string": "a", "new_string": "b"},
                        tool_call_id=f"c{turn['n']}",
                    )
                ]
            )

        agent = build_coder_agent(
            FunctionModel(model_fn),
            task,
            settings,
            4096,
            browser_tools_available=False,
            guards=True,
            on_reminder_fired=fired.append,
        )
        with pytest.raises(GuardAbort, match="Loop guard"):
            await agent.run("do it")
        # les nudges de loop (3/5) ont bien été injectés AVANT l'abort
        loop_reminders = [t for t in fired if "LOOP GUARD" in t]
        assert len(loop_reminders) >= 1
        assert any("CHANGE YOUR APPROACH" in t for t in loop_reminders)

    @pytest.mark.anyio
    async def test_clean_run_passes_with_guards(self, tmp_path, monkeypatch):
        """Smoke non-régression happy path : write_file puis final_result
        success avec preuve disque — aucune garde ne doit déclencher."""
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        from pydantic_ai.models.function import FunctionModel, AgentInfo

        from graph_orchestrator.coder_pydantic import build_coder_agent

        monkeypatch.chdir(tmp_path)
        settings = load_settings()
        task = {
            "id": "st-ok",
            "content": "Build",
            "target_files": ["index.html"],
            "strategy": "simple",
            "iteration": 1,
        }
        turn = {"n": 0}

        def model_fn(messages, info: AgentInfo) -> ModelResponse:
            turn["n"] += 1
            if turn["n"] == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            "write_file",
                            {"path": "index.html", "content": "<html><body>ok</body></html>"},
                            tool_call_id="w1",
                        )
                    ]
                )
            out = CoderOutput(
                task_id="st-ok", status="success", details="done",
                linter_ok=True, vision_ok=False,
            )
            return ModelResponse(
                parts=[ToolCallPart("final_result", out.model_dump(mode="json"), tool_call_id="f1")]
            )

        agent = build_coder_agent(
            FunctionModel(model_fn), task, settings, 4096,
            browser_tools_available=False, guards=True,
        )
        result = await agent.run("do it")
        assert isinstance(result.output, CoderOutput)
        assert result.output.status == "success"
        assert (tmp_path / "index.html").exists()
