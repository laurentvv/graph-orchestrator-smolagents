"""Tests F-162 — Tester (runner web) pydantic-ai-harness (phase 3.7), 0 LLM / 0 réseau.

Couvre : instructions (protocole natif × skills forcés × doc outils conditionnée),
user prompt (spec/checklist F-46-F-82 × re-test ciblé F-47 × URLs exactes),
délégation des custom tools lecture seule + fix_known_error, processor Puppeteer
(strippage filePath), dégradation open_tester_mcp, capabilities du profil (PAS de
GoalGate/FileSystem, hint IdleBreaker Tester, WarnNearLimits calibré max_steps
Tester), assemblage Agent (tool_choice auto, CoderOutput) et l'aiguillage
TESTER_ENGINE dans WebTestRunner + le timeout wall-clock de run_tester_pydantic.
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager, contextmanager

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graph_orchestrator.config import load_settings
from graph_orchestrator.models import CoderOutput
from graph_orchestrator.prompts import ROLE_BLOCKS, UNIVERSAL_INVARIANTS
from graph_orchestrator.tester_pydantic import (
    _TESTER_PROTOCOL_BLOCK,
    build_tester_agent,
    build_tester_capabilities,
    build_tester_custom_tools,
    build_tester_instructions,
    build_tester_user_prompt,
    fix_known_error,
    list_directory,
    make_tester_process_tool_call,
    open_tester_mcp,
    read_file,
)


def _base_task(**overrides) -> dict:
    task = {
        "id": "bs-001",
        "content": "Implémente le visualiseur Bubble Sort (index.html, styles.css, script.js).",
        "target_files": ["index.html", "styles.css", "script.js"],
        "original_content": (
            "## Objective\nBubble Sort visualizer.\n\n"
            "## Expected Features\n- Start button launches the animated sort\n"
            "- Comparison counter increments and is DISPLAYED\n"
            "- Reset button generates a new random array\n"
        ),
        "tester_skills": ["web-tester"],
        "iteration": 1,
    }
    task.update(overrides)
    return task


# ============================================================
# build_tester_instructions
# ============================================================

class TestBuildTesterInstructions:
    def test_role_and_invariants_present(self):
        instructions = build_tester_instructions(_base_task(), load_settings())
        assert ROLE_BLOCKS["web_tester"] in instructions
        assert UNIVERSAL_INVARIANTS in instructions

    def test_native_protocol_not_codeagent(self):
        """Le protocole annonce des tool calls natifs — plus de bloc ```python
        CodeAgent ; la sortie passe par l'outil final_result."""
        assert "native tool calls" in _TESTER_PROTOCOL_BLOCK
        assert "```python" not in _TESTER_PROTOCOL_BLOCK
        assert "final_answer" not in _TESTER_PROTOCOL_BLOCK
        instructions = build_tester_instructions(_base_task(), load_settings())
        assert "final_result" in instructions

    def test_protocol_carries_tester_doctrines(self):
        """Navigation-first + preuve temporelle + isolation des sondes + budget —
        les règles 3-6-7 du prompt smolagents F-152 portées au natif."""
        for marker in (
            "NAVIGATION FIRST",
            "TEMPORAL TEST",
            "PROBE ISOLATION",
            "probe_sort_state",
            "CONVERGE RAPIDLY",
            "fix_known_error",
        ):
            assert marker in _TESTER_PROTOCOL_BLOCK, marker

    def test_task_id_in_final_result_block(self):
        instructions = build_tester_instructions(_base_task(id="bs-xyz"), load_settings())
        assert 'task_id: "bs-xyz"' in instructions

    def test_devtools_preview_skill_forced(self):
        """Garantie déterministe goulot 2026-08-21 : devtools-preview PRÉ-COLLÉ
        même si la sélection Architect ne l'inclut pas ; web-tester conservé."""
        task = _base_task(tester_skills=["web-tester"])
        instructions = build_tester_instructions(task, load_settings())
        assert "### SKILL: devtools-preview" in instructions
        assert "### SKILL: web-tester" in instructions
        # Pas de mutation du dict de tâche (review Kilo PR #102)
        assert task["tester_skills"] == ["web-tester"]

    def test_devtools_hint_conditioned_on_availability(self):
        settings = load_settings()
        with_hint = build_tester_instructions(_base_task(), settings, browser_tools_available=True)
        assert "BROWSER TOOLS" in with_hint
        assert "filePath" in with_hint  # DANGER FATAL F-50/F-90
        assert "DOM PROBES & HELPERS" in with_hint
        without = build_tester_instructions(_base_task(), settings, browser_tools_available=False)
        assert "BROWSER TOOLS" not in without
        assert "DOM PROBES & HELPERS" not in without

    def test_vision_note_conditioned(self):
        settings = load_settings()
        vision_on = build_tester_instructions(_base_task(), settings, vision_available=True)
        assert "AS AN IMAGE" in vision_on
        assert "vision disabled" not in vision_on
        vision_off = build_tester_instructions(_base_task(), settings, vision_available=False)
        assert "vision disabled" in vision_off

    def test_puppeteer_and_context7_notes_conditioned(self):
        settings = load_settings()
        instructions = build_tester_instructions(
            _base_task(), settings, puppeteer_available=True, context7_available=True
        )
        assert "LEGACY Puppeteer tools" in instructions
        assert "query_docs" in instructions
        plain = build_tester_instructions(_base_task(), settings)
        assert "LEGACY Puppeteer tools" not in plain
        assert "query_docs" not in plain


# ============================================================
# build_tester_user_prompt
# ============================================================

class TestBuildTesterUserPrompt:
    def test_full_mode_spec_and_checklist(self):
        settings = load_settings()
        prompt = build_tester_user_prompt(_base_task(), settings, use_targeted=False)
        assert "COMPREHENSIVE SPECIFICATION" in prompt
        # Checklist F-46 : les fonctionnalités parsées de la spec sont listées
        assert "Comparison counter increments and is DISPLAYED" in prompt

    def test_architect_criteria_override_f46(self):
        """F-82 : les critères de l'Architecte remplacent la checklist regex."""
        settings = load_settings()
        task = _base_task(functional_test_criteria=["Après clic Start, le compteur > 0"])
        prompt = build_tester_user_prompt(task, settings, use_targeted=False)
        assert "Après clic Start, le compteur > 0" in prompt
        assert "CHECKLIST DE FONCTIONNALITÉS" not in prompt

    def test_targeted_mode_replaces_spec_and_checklist(self):
        """F-47/F-52 : itération > 1 + réfutations → re-test ciblé, PAS de spec
        complète ni de checklist générique (double travail interdit)."""
        settings = load_settings()
        task = _base_task(
            iteration=2,
            refutations=[{"content": "BUG: le compteur reste figé à 0 pendant le tri"}],
        )
        prompt = build_tester_user_prompt(task, settings, use_targeted=True)
        assert "RE-TEST CIBLÉ" in prompt
        assert "le compteur reste figé" in prompt
        assert "COMPREHENSIVE SPECIFICATION" not in prompt
        assert "CHECKLIST DE FONCTIONNALITÉS" not in prompt

    def test_urls_exact_and_path_format(self, monkeypatch, tmp_path):
        """URL primaire = PREMIER fichier cible (pas la racine du run) + blocs
        PATH FORMAT / MANDATORY NAVIGATION porteurs de l'URL exacte."""
        monkeypatch.chdir(tmp_path)
        settings = load_settings()
        prompt = build_tester_user_prompt(_base_task(), settings, use_targeted=False)
        expected_url = ("file:///" + str(tmp_path).replace("\\", "/") + "/index.html")
        assert expected_url in prompt
        assert f'navigate_page(url="{expected_url}")' in prompt
        assert "PATH FORMAT FOR DIFFERENT TOOLS" in prompt
        # Les fichiers cibles sont listés en URLs
        assert "script.js" in prompt

    def test_subtask_content_included(self):
        prompt = build_tester_user_prompt(_base_task(), load_settings(), use_targeted=False)
        assert "### Description of the subtask under test" in prompt
        assert "Bubble Sort" in prompt


# ============================================================
# Custom tools (délégation aux implémentations canoniques)
# ============================================================

class TestCustomTools:
    def test_read_file_delegates_with_line_numbers(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "script.js").write_text("const a = 1;\nconst b = 2;\n", encoding="utf-8")
        out = read_file(path="script.js")
        assert "1\tconst a = 1;" in out or "const a = 1;" in out

    def test_list_directory_delegates(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
        out = list_directory(path=".")
        assert "index.html" in out

    def test_fix_known_error_delegates_const_reassignment(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "script.js").write_text(
            "const speed = 300;\nspeed = 200;\n", encoding="utf-8"
        )
        out = fix_known_error(
            path="script.js",
            error_message="TypeError: Assignment to constant variable 'speed'",
        )
        assert "let speed" in (tmp_path / "script.js").read_text(encoding="utf-8")
        assert out  # feedback non vide (fix appliqué ou explication)

    def test_custom_tools_exactly_three_readonly_plus_fixer(self):
        """Parité smolagents : lecture seule + fix_known_error — PAS de write."""
        tools = build_tester_custom_tools()
        assert len(tools) == 3
        assert {t.__name__ for t in tools} == {"read_file", "list_directory", "fix_known_error"}


# ============================================================
# Processor Puppeteer (strippage filePath + délégation au socle)
# ============================================================

class TestTesterProcessToolCall:
    @pytest.mark.anyio
    async def test_puppeteer_screenshot_filepath_stripped(self):
        """F-50/F-90 parité vision_callback._FILEPATH_TOOLS : le strippage
        couvrait les DEUX pilotes — puppeteer_screenshot est strippé aussi."""
        processor = make_tester_process_tool_call(vision=False)
        captured: dict = {}

        async def fake_call_tool(name, args):
            captured["name"] = name
            captured["args"] = args
            return "shot ok"

        result = await processor(
            None, fake_call_tool, "puppeteer_screenshot",
            {"filePath": "shot.png", "width": 800},
        )
        assert captured["name"] == "puppeteer_screenshot"
        assert "filePath" not in captured["args"]
        assert "file_path" not in captured["args"]
        assert captured["args"].get("width") == 800
        assert result == "shot ok"

    @pytest.mark.anyio
    async def test_devtools_tools_still_sanitized_by_base(self):
        """La délégation au processor commun conserve le strippage DevTools
        (take_screenshot) — pas de régression F-160."""
        processor = make_tester_process_tool_call(vision=False)
        captured: dict = {}

        async def fake_call_tool(name, args):
            captured["args"] = args
            return "ok"

        await processor(None, fake_call_tool, "take_screenshot", {"filePath": "x.png"})
        assert "filePath" not in captured["args"]


# ============================================================
# open_tester_mcp (dégradation individuelle par serveur)
# ============================================================

class _FakeAsyncCM:
    def __init__(self, fail: bool = False, client=None):
        self.fail = fail
        self.client = client

    async def __aenter__(self):
        if self.fail:
            raise RuntimeError("npx timeout")
        return self

    async def __aexit__(self, *exc):
        return False


class TestOpenTesterMCP:
    @pytest.mark.anyio
    async def test_devtools_ok_puppeteer_degrades_individually(self, monkeypatch):
        """Puppeteer en échec (timeout npx) ne casse PAS le run : DevTools
        (pilote primaire) reste connecté, helpers présents."""
        import graph_orchestrator.coder_pydantic_mcp as cpm
        import graph_orchestrator.tester_pydantic as tp

        sentinel_helpers = object()
        monkeypatch.setattr(cpm, "build_devtools_mcp_toolset", lambda s: _FakeAsyncCM(client=object()))
        monkeypatch.setattr(cpm, "build_dom_helper_toolset", lambda c: sentinel_helpers)
        monkeypatch.setattr(cpm, "build_context7_mcp_toolset", lambda s: None)
        monkeypatch.setattr(tp, "build_puppeteer_mcp_toolset", lambda s: _FakeAsyncCM(fail=True))

        async with tp.open_tester_mcp(load_settings()) as mcp:
            assert mcp.browser_tools_available is True
            assert mcp.puppeteer_available is False
            assert mcp.context7_available is False
            assert sentinel_helpers in mcp.toolsets
            assert len(mcp.toolsets) == 2  # devtools + helpers, puppeteer exclu

    @pytest.mark.anyio
    async def test_devtools_absent_no_helpers(self, monkeypatch):
        import graph_orchestrator.coder_pydantic_mcp as cpm
        import graph_orchestrator.tester_pydantic as tp

        monkeypatch.setattr(cpm, "build_devtools_mcp_toolset", lambda s: None)
        monkeypatch.setattr(cpm, "build_dom_helper_toolset", lambda c: None)
        monkeypatch.setattr(cpm, "build_context7_mcp_toolset", lambda s: None)
        monkeypatch.setattr(tp, "build_puppeteer_mcp_toolset", lambda s: None)

        async with tp.open_tester_mcp(load_settings()) as mcp:
            assert mcp.browser_tools_available is False
            assert mcp.toolsets == []


# ============================================================
# Capabilities du profil Tester
# ============================================================

class TestTesterCapabilities:
    def _classes(self, caps) -> set:
        return {type(c).__name__ for c in caps}

    def test_profil_tester_sans_goalgate_ni_filesystem(self):
        """Le Tester ne produit pas de livrable : PAS de GoalGate (preuves F-99
        sans objet) ni de FileSystem en écriture (lecture via custom tools)."""
        caps = build_tester_capabilities(_base_task(), load_settings(), max_steps=12)
        names = self._classes(caps)
        assert "GoalGateCapability" not in names
        assert "FileSystem" not in names
        assert "ToolGuardsCapability" in names
        assert "IdleBreakerCapability" in names
        assert "SystemReminders" in names  # build_tester_reminders
        assert "ProcessHistory" in names  # vision F-161 (purge images)
        assert "TieredCompaction" in names

    def test_guards_off_comportement_minimal(self):
        """CODER_PYDANTIC_GUARDS=false (toggle socle partagé) : pas de gardes
        ni compaction — ClearToolResults standalone, vision conservée."""
        import dataclasses

        settings = dataclasses.replace(load_settings(), coder_pydantic_guards=False)
        caps = build_tester_capabilities(_base_task(), settings, max_steps=12)
        names = self._classes(caps)
        assert "ClearToolResults" in names
        assert "ToolGuardsCapability" not in names
        assert "TieredCompaction" not in names
        assert "ProcessHistory" in names  # purge image inconditionnelle (F-161)

    def test_warn_near_limits_calibrated_on_tester_steps(self):
        """WarnNearLimits doit suivre tester_max_steps (ou TARGETED_MAX_STEPS),
        PAS coder_max_steps — paramètre max_steps de build_compaction_capabilities."""
        from pydantic_ai_harness import WarnNearLimits

        from graph_orchestrator.coder_pydantic_guards import build_compaction_capabilities

        settings = load_settings()
        caps = build_compaction_capabilities(settings, max_steps=6)
        warn = next(c for c in caps if isinstance(c, WarnNearLimits))
        assert warn.max_iterations == 6
        # Rétrocompat Coder : défaut = coder_max_steps
        caps_default = build_compaction_capabilities(settings)
        warn_default = next(c for c in caps_default if isinstance(c, WarnNearLimits))
        assert warn_default.max_iterations == int(settings.coder_max_steps)

    @pytest.mark.anyio
    async def test_idle_breaker_hint_tester(self):
        """F-162 : le nudge idle du Tester cite navigate/evaluate/final_result
        (pas write_file/search_replace = vocabulaire Coder)."""
        from pydantic_ai.messages import ModelResponse, TextPart

        from graph_orchestrator.coder_pydantic_guards import CoderGuardState, IdleBreakerCapability

        state = CoderGuardState()
        breaker = IdleBreakerCapability(
            state, threshold=3,
            action_hint="navigate_page / evaluate_script / probe_* , or finish with final_result",
        )
        await breaker.after_model_request(
            None, request_context=None, response=ModelResponse(parts=[TextPart("je réfléchis")])
        )
        assert "navigate_page" in state.idle_nudge
        assert "write_file" not in state.idle_nudge

    @pytest.mark.anyio
    async def test_idle_breaker_default_hint_unchanged(self):
        """Rétrocompat F-159 : sans action_hint, le texte Coder d'origine."""
        from pydantic_ai.messages import ModelResponse, TextPart

        from graph_orchestrator.coder_pydantic_guards import CoderGuardState, IdleBreakerCapability

        state = CoderGuardState()
        breaker = IdleBreakerCapability(state, threshold=3)
        await breaker.after_model_request(
            None, request_context=None, response=ModelResponse(parts=[TextPart("blabla")])
        )
        assert "write_file" in state.idle_nudge

    def test_reminders_tester_sans_checklist_ni_winddown_coder(self):
        """Les reminders du Tester n'embarquent PAS les callbacks Coder
        (checklist/wind-down portés par visual_check, outil Coder) ; le
        wind-down TESTER (run 3 F-162) n'entre que si le budget est passé."""
        from pydantic_ai_harness.system_reminders import GoalReanchor

        from graph_orchestrator.coder_pydantic_guards import (
            CoderGuardState,
            build_guard_reminders,
            build_tester_reminders,
        )

        state = CoderGuardState()
        tester_rem = build_tester_reminders(state)
        assert len(tester_rem.dynamic_reminders) == 5  # GoalReanchor + 4 pops
        tester_rem_budget = build_tester_reminders(state, max_requests=32)
        assert len(tester_rem_budget.dynamic_reminders) == 6  # + wind-down F-131
        coder_rem = build_guard_reminders(state, _base_task(), load_settings())
        assert len(tester_rem_budget.dynamic_reminders) < len(coder_rem.dynamic_reminders)

    def test_tester_wind_down_fires_near_budget(self):
        """Le wind-down Tester tire à ≤6 requêtes restantes (run 3 F-162 :
        30 tours sans convergence → timeout) et pousse final_result."""
        from graph_orchestrator.coder_pydantic_guards import (
            CoderGuardState,
            build_tester_reminders,
        )

        state = CoderGuardState()
        rem = build_tester_reminders(state, max_requests=32)

        class _Ctx:
            def __init__(self, run_step: int):
                self.run_step = run_step

        wind_down = rem.dynamic_reminders[-1]
        assert wind_down(_Ctx(10)) is None  # 22 restantes : rien
        fired = wind_down(_Ctx(27))  # 5 restantes
        assert fired and "final_result" in fired and "verdict" in fired
        assert wind_down(_Ctx(32)) is None  # budget épuisé : plus de nudge


# ============================================================
# Assemblage de l'Agent
# ============================================================

class TestAgentAssembly:
    def _agent(self, settings=None, **kwargs):
        from pydantic_ai.models.test import TestModel

        kwargs.setdefault("browser_tools_available", True)
        return build_tester_agent(
            TestModel(), _base_task(), settings or load_settings(), 12, **kwargs
        )

    def test_constructs_with_output_coderoutput(self):
        from pydantic_ai._output import DEFAULT_OUTPUT_TOOL_NAME

        agent = self._agent()
        assert agent is not None
        assert agent._output_type is CoderOutput
        instructions = build_tester_instructions(_base_task(), load_settings())
        assert f"`{DEFAULT_OUTPUT_TOOL_NAME}`" in instructions

    def test_tool_choice_auto_only_with_toolsets(self):
        """F-160 : grammaire GBNF au-delà de ~45-60 outils — le Tester en porte
        ~50 avec Puppeteer → 'auto' dès qu'un toolset est attaché."""
        toolset = _FakeAsyncCM(client=object())
        agent_with = self._agent(toolsets=[toolset])
        assert agent_with.model_settings["tool_choice"] == "auto"
        agent_without = self._agent()
        assert "tool_choice" not in agent_without.model_settings

    def test_model_settings_reasoning_profile(self):
        """max_tokens = no_think_max_tokens (F-168 : cap dédié 4096 au spec
        no-think — avant reasoning_max_tokens=16384 laissait une réponse
        dégénérée courir ~50 min sur le 9B à 5 t/s, run 1835) et PAS de
        température forcée (parité smolagents : défaut serveur)."""
        settings = load_settings()
        agent = self._agent(settings)
        assert agent.model_settings["max_tokens"] == settings.no_think_max_tokens
        assert "temperature" not in agent.model_settings

    @pytest.mark.anyio
    async def test_progress_capability_registers_and_runs(self, capsys):
        """Leçon run 2 F-162 : le harness APPELLE les capabilities à
        l'enregistrement — un duck-typing sans héritage AbstractCapability
        lève ``'object' is not callable`` au 1er run (invisible à la
        construction). Ce test EXÉCUTE le vrai agent (TestModel, 0 LLM / 0
        réseau) pour prouver l'enregistrement + la sortie CoderOutput native."""
        from pydantic_ai.models.test import TestModel

        agent = build_tester_agent(
            TestModel(), _base_task(), load_settings(), 12
        )
        async with agent:
            result = await agent.run("isolation test")
        assert isinstance(result.output, CoderOutput)
        out = capsys.readouterr().out
        assert "[T] tour" in out  # progression imprimée (observabilité)


# ============================================================
# Aiguillage TESTER_ENGINE
# ============================================================

class TestTesterEngineDispatch:
    def test_config_default_smolagents(self, monkeypatch):
        monkeypatch.delenv("TESTER_ENGINE", raising=False)
        settings = load_settings()
        assert settings.tester_engine == "smolagents"

    def test_config_env_override_pydantic(self, monkeypatch):
        monkeypatch.setenv("TESTER_ENGINE", "pydantic")
        settings = load_settings()
        assert settings.tester_engine == "pydantic"

    @pytest.mark.anyio
    async def test_webtestrunner_dispatches_to_pydantic(self, monkeypatch):
        """TESTER_ENGINE=pydantic → WebTestRunner.run délègue à
        run_tester_pydantic (lazy import → patch au niveau module)."""
        import dataclasses

        import graph_orchestrator.tester_pydantic as tp
        from graph_orchestrator.testers.web_tester import WebTestRunner

        calls: list = []

        async def _fake_run(task, settings):
            calls.append(task)
            return None, None

        monkeypatch.setattr(tp, "run_tester_pydantic", _fake_run)
        settings = dataclasses.replace(load_settings(), tester_engine="pydantic")
        await WebTestRunner().run(_base_task(), model=None, settings=settings)
        assert len(calls) == 1
        assert calls[0]["id"] == "bs-001"

    @pytest.mark.anyio
    async def test_unknown_engine_falls_back_with_warning(self, monkeypatch, capsys):
        """Valeur inconnue → avertissement + chemin smolagents (on intercepte
        AVANT la connexion MCP pour rester 0-réseau)."""
        import dataclasses
        import types

        from graph_orchestrator.testers.web_tester import WebTestRunner

        settings = dataclasses.replace(load_settings(), tester_engine="turbo")
        fake_mcp = types.ModuleType("mcp")

        def _getattr(name):
            if name == "StdioServerParameters":
                raise RuntimeError("SMOLAGENTS_PATH_REACHED")
            raise AttributeError(name)

        fake_mcp.__getattr__ = _getattr
        monkeypatch.setitem(sys.modules, "mcp", fake_mcp)

        with pytest.raises(RuntimeError, match="SMOLAGENTS_PATH_REACHED"):
            await WebTestRunner().run(_base_task(), model=None, settings=settings)
        assert "TESTER_ENGINE inconnu" in capsys.readouterr().out


# ============================================================
# run_tester_pydantic (timeout wall-clock + mode ciblé) — fakes complets
# ============================================================

class _FakeSrv:
    api_base = "http://127.0.0.1:19999"
    api_key = "test-key"
    model_id = "fake-9b"

    @staticmethod
    def revive():
        return None


def _patch_run_env(monkeypatch, agent_factory):
    """Patche le strict minimum de run_tester_pydantic : lifecycle serveur,
    MCP (aucun), assemblage (fake). Le modèle OpenAIChatModel reste construit
    (0 réseau à la construction)."""
    import graph_orchestrator.llama_server as ls
    import graph_orchestrator.tester_pydantic as tp

    @contextmanager
    def fake_lifecycle(spec):
        yield _FakeSrv()

    monkeypatch.setattr(ls, "model_lifecycle", fake_lifecycle)

    class _NoMCP:
        toolsets: list = []
        browser_tools_available: bool = False
        puppeteer_available: bool = False
        context7_available: bool = False

    @asynccontextmanager
    async def fake_mcp(settings=None):
        yield _NoMCP()

    monkeypatch.setattr(tp, "open_tester_mcp", fake_mcp)
    monkeypatch.setattr(tp, "build_tester_agent", agent_factory)


class TestRunTesterPydantic:
    @pytest.mark.anyio
    async def test_wall_clock_timeout_clean_failure(self, monkeypatch):
        """TESTER_TIMEOUT_S dépassé → (None, NodeMetrics) échec PROPRE, pas
        d'exception qui remonte (parité run_with_retry timeout_s)."""
        import dataclasses

        import graph_orchestrator.tester_pydantic as tp

        captured: dict = {}

        class _SlowAgent:
            async def run(self, user_prompt, usage_limits=None):
                captured["usage_limits"] = usage_limits
                await asyncio.sleep(30)
                raise AssertionError("ne doit jamais finir")

        _patch_run_env(monkeypatch, lambda *a, **k: _SlowAgent())
        settings = dataclasses.replace(load_settings(), tester_timeout_s=1)
        output, metrics = await tp.run_tester_pydantic(_base_task(), settings)
        assert output is None
        assert metrics is not None and metrics.node.startswith("tester[")
        # Budget requêtes = tester_max_steps × 2 (leçon run 1 F-162 : 1 requête
        # pydantic ≈ 1 tool call vs 1 step CodeAgent = plusieurs calls).
        assert captured["usage_limits"].request_limit == settings.tester_max_steps * 2
        assert captured["usage_limits"].tool_calls_limit == settings.tester_max_steps * 6

    @pytest.mark.anyio
    async def test_targeted_mode_uses_targeted_max_steps(self, monkeypatch):
        """Itération > 1 + réfutations → UsageLimits borné à TARGETED_MAX_STEPS
        (F-47) et build_tester_agent assemblé pour ce budget."""
        import dataclasses

        import graph_orchestrator.tester_pydantic as tp
        from graph_orchestrator.targeted_retest import TARGETED_MAX_STEPS

        captured: dict = {}

        class _FastAgent:
            async def run(self, user_prompt, usage_limits=None):
                captured["request_limit"] = usage_limits.request_limit
                return _FakeResult()

        def _fake_build(model, task, settings, tester_max_steps, **kwargs):
            captured["agent_max_steps"] = tester_max_steps
            return _FastAgent()

        _patch_run_env(monkeypatch, _fake_build)
        settings = dataclasses.replace(load_settings(), tester_timeout_s=60)
        task = _base_task(
            iteration=2,
            refutations=[{"content": "BUG: compteur figé à 0"}],
        )
        output, _ = await tp.run_tester_pydantic(task, settings)
        assert output is not None and output.status == "success"
        assert captured["agent_max_steps"] == TARGETED_MAX_STEPS
        assert captured["request_limit"] == TARGETED_MAX_STEPS * 2

    @pytest.mark.anyio
    async def test_spawn_failure_clean_none(self, monkeypatch):
        """llama-server ne spawn pas → échec propre (None, None), le graphe
        continue (parité smolagents)."""
        import dataclasses

        import graph_orchestrator.llama_server as ls
        import graph_orchestrator.tester_pydantic as tp

        class _DeadSrv:
            api_base = None
            api_key = "k"
            model_id = "m"

        @contextmanager
        def dead_lifecycle(spec):
            yield _DeadSrv()

        monkeypatch.setattr(ls, "model_lifecycle", dead_lifecycle)
        settings = dataclasses.replace(load_settings(), tester_timeout_s=60)
        output, metrics = await tp.run_tester_pydantic(_base_task(), settings)
        assert output is None
        assert metrics is None


class _FakeResult:
    """Resultat minimal : usage propriété + output CoderOutput valide."""

    @property
    def usage(self):
        return None

    output = CoderOutput(task_id="bs-001", status="success", details="ok")
