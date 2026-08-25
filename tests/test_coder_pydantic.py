"""Tests F-158 — Coder pydantic-ai-harness (phase 3.1-3.2), 0 LLM / 0 réseau.

Couvre : instructions (protocole natif × stratégies × skills × fichiers cibles),
user prompt (fichiers courants × itération), délégation des custom tools vers les
implémentations canoniques tools.py, assemblage de l'Agent (outils présents,
output CoderOutput) et l'aiguillage CODER_ENGINE dans execute_coder_node.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graph_orchestrator.coder_pydantic import (
    append_file,
    build_coder_agent,
    build_coder_custom_tools,
    build_coder_instructions,
    build_coder_user_prompt,
    check_run_state,
    multi_replace,
    run_coder_pydantic,
    search_replace,
)
from graph_orchestrator.config import load_settings
from graph_orchestrator.models import CoderOutput
from graph_orchestrator.prompts import ROLE_BLOCKS, UNIVERSAL_INVARIANTS


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
# build_coder_instructions
# ============================================================

class TestBuildCoderInstructions:
    def test_role_and_invariants_present(self):
        instructions = build_coder_instructions(_base_task())
        assert "SENIOR SOFTWARE ENGINEER" in instructions
        assert "UNIVERSAL INVARIANTS" in instructions
        assert ROLE_BLOCKS["coder"] in instructions
        assert UNIVERSAL_INVARIANTS in instructions

    def test_native_protocol_not_codeagent(self):
        """Le protocole annonce des tool calls natifs — plus de blocs ```python
        CodeAgent dans le PROTOCOLE ; la sortie passe par l'outil final_result.
        (Les corps de skills peuvent légitiment contenir leurs propres exemples
        de code — on ne teste que le protocole.)"""
        from graph_orchestrator.coder_pydantic import _PROTOCOL_BLOCK

        assert "native tool calls" in _PROTOCOL_BLOCK
        assert "```python" not in _PROTOCOL_BLOCK
        assert "final_answer" not in _PROTOCOL_BLOCK
        instructions = build_coder_instructions(_base_task())
        assert "final_result" in instructions

    def test_target_files_block(self):
        instructions = build_coder_instructions(_base_task())
        assert "TARGET FILES" in instructions
        for f in ("index.html", "styles.css", "script.js"):
            assert f"- {f}" in instructions
        # Chemins relatifs (chdir F-40 du workflow)
        assert "RELATIVE" in instructions or "relative" in instructions

    def test_task_id_in_final_result_block(self):
        instructions = build_coder_instructions(_base_task(id="ts-xyz"))
        assert '"ts-xyz"' in instructions

    def test_strategy_simple(self):
        instructions = build_coder_instructions(_base_task(strategy="simple"))
        assert "SIMPLE strategy" in instructions

    def test_strategy_incremental_lists_sections(self):
        instructions = build_coder_instructions(
            _base_task(strategy="incremental", sections=["CSS", "board", "JS"])
        )
        assert "INCREMENTAL strategy" in instructions
        assert "CSS, board, JS" in instructions

    def test_strategy_multifile(self):
        instructions = build_coder_instructions(_base_task(strategy="multifile"))
        assert "MULTIFILE strategy" in instructions

    def test_correction_mode_iteration_gt_1(self):
        instructions = build_coder_instructions(_base_task(iteration=2))
        assert "CORRECTION MODE (Iteration 2" in instructions
        assert "DO NOT RESTART FROM SCRATCH" in instructions

    def test_no_browser_tools_promised(self):
        """Parité 3.1-3.2 : pas de MCP navigateur — le moteur pydantic ne doit
        pas coller devtools-preview (rituel navigate_page/screenshot sur outils
        absents = modèle induit en erreur)."""
        instructions = build_coder_instructions(_base_task(), browser_tools_available=False)
        assert "### SKILL: devtools-preview" not in instructions
        assert "navigate_page" not in instructions.split("### Task Content")[0]

    def test_browser_skill_injected_when_tools_available(self):
        """Flip phase 3.5/3.6 : avec les outils navigateur, le pré-scotchage
        devtools-preview sur tâche web redevient actif (parité nodes.py)."""
        instructions = build_coder_instructions(_base_task(), browser_tools_available=True)
        assert "### SKILL: devtools-preview" in instructions

    def test_skills_eager_injected(self):
        instructions = build_coder_instructions(_base_task(skills=["coding"]))
        assert "SPECIALIZED SKILLS" in instructions
        assert "### SKILL: coding" in instructions

    def test_web_task_gets_devtools_preview_prepended(self):
        """Miroir nodes.py : tâche web + skills Architect → devtools-preview
        garanti en tête (décision user F-116-9b)."""
        instructions = build_coder_instructions(_base_task(skills=["coding"]))
        assert "### SKILL: devtools-preview" in instructions

    def test_available_tools_documents_filesystem_and_customs(self):
        instructions = build_coder_instructions(_base_task())
        for name in ("write_file", "edit_file", "search_replace", "multi_replace",
                     "check_js_syntax", "load_skill"):
            assert name in instructions

    def test_no_placeholder_parts(self):
        """Toutes les sections optionnelles absentes → instructions valides sans
        trous (join sur parties non vides)."""
        instructions = build_coder_instructions(
            {"id": "t1", "content": "x", "target_files": [], "iteration": 1}
        )
        assert instructions.strip()
        assert "None" not in instructions


# ============================================================
# build_coder_user_prompt
# ============================================================

class TestBuildCoderUserPrompt:
    def test_task_content_and_recap(self):
        prompt = build_coder_user_prompt(_base_task())
        assert "### Contenu de la tâche" in prompt
        assert "Bubble Sort" in prompt
        assert "RAPPEL (récence)" in prompt

    def test_optional_blocks_injected_when_present(self):
        prompt = build_coder_user_prompt(
            _base_task(
                draft_instruction="### DRAFT\nUse flex row.",
                original_content="Cahier des charges initial complet.",
                lessons="### LEÇONS\ninitialiser à 20 barres.",
                plan_anchor="### PLAN (anchor)\n- step 1\n",
            )
        )
        assert "### DRAFT" in prompt
        assert "Cahier des charges initial complet." in prompt
        assert "### LEÇONS" in prompt
        assert "### PLAN (anchor)" in prompt

    def test_iteration_1_no_current_files_block(self):
        prompt = build_coder_user_prompt(_base_task(iteration=1))
        assert "CURRENT CODE OF TARGET FILES" not in prompt

    def test_iteration_gt_1_injects_existing_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "index.html").write_text("<html>existing</html>", encoding="utf-8")
        prompt = build_coder_user_prompt(_base_task(iteration=2))
        assert "CURRENT CODE OF TARGET FILES" in prompt
        assert "<html>existing</html>" in prompt
        assert "NO read_file NEEDED" in prompt


# ============================================================
# Custom tools : délégation vers tools.py (gardes conservées)
# ============================================================

class TestCustomToolsDelegation:
    def test_registry_complete(self):
        tools = build_coder_custom_tools()
        names = {t.__name__ for t in tools}
        assert names == {
            "search_replace", "multi_replace", "append_file", "check_js_syntax",
            "read_python_skeleton", "log_event", "visual_check", "check_run_state",
            "load_skill", "fix_known_error",
        }

    def test_search_replace_performs_surgical_edit(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "app.js").write_text(
            "const speed = 1;\nfunction start() {}\n", encoding="utf-8"
        )
        result = search_replace(
            path="app.js",
            old_string="function start() {}",
            new_string="function start() { beginSort(); }",
        )
        assert "edited" in result.lower()
        assert "beginSort();" in (tmp_path / "app.js").read_text(encoding="utf-8")

    def test_search_replace_rejects_noop(self, tmp_path, monkeypatch):
        """Garde F-132 conservée par délégation : old == new rejeté."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "app.js").write_text("let a = 1;\n", encoding="utf-8")
        result = search_replace(path="app.js", old_string="let a = 1;", new_string="let a = 1;")
        assert "ERROR" in result

    def test_multi_replace_applies_batch(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "app.js").write_text("var x = 1;\nvar y = 2;\n", encoding="utf-8")
        result = multi_replace(
            path="app.js",
            replacements=[
                {"old_string": "var x = 1;", "new_string": "let x = 1;"},
                {"old_string": "var y = 2;", "new_string": "let y = 2;"},
            ],
        )
        assert "2/2" in result
        content = (tmp_path / "app.js").read_text(encoding="utf-8")
        assert "let x" in content and "let y" in content

    def test_append_file_appends(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "out.txt").write_text("line1\n", encoding="utf-8")
        append_file(path="out.txt", content="line2\n")
        assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "line1\nline2\n"

    def test_check_run_state_returns_string(self):
        result = check_run_state()
        assert isinstance(result, str) and result


# ============================================================
# Assemblage Agent (0 LLM, 0 réseau — construction seule)
# ============================================================

class TestBuildCoderAgent:
    def _build(self, task=None):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        model = OpenAIChatModel(
            "test-model",
            provider=OpenAIProvider(base_url="http://127.0.0.1:9/v1", api_key="x"),
        )
        settings = load_settings()
        return build_coder_agent(model, task or _base_task(), settings, coder_max_tokens=4096)

    @staticmethod
    def _tool_names(agent) -> set:
        """Collecte les tools de tous les toolsets : agent.toolsets est une
        LISTE ; les toolsets de capabilities sont lazy et exposent le vrai
        toolset via `.wrapped` (FunctionToolset/FileSystemToolset ont `.tools`)."""
        names: set = set()
        stack = list(agent.toolsets)
        while stack:
            ts = stack.pop()
            wrapped = getattr(ts, "wrapped", None)
            if wrapped is not None and hasattr(wrapped, "tools"):
                names.update(wrapped.tools.keys())
            elif hasattr(ts, "tools"):
                names.update(ts.tools.keys())
            stack.extend(getattr(ts, "toolsets", []) or [])
        return names

    def test_agent_constructs_with_capabilities_and_output(self):
        agent = self._build()
        assert agent is not None

    def test_filesystem_and_custom_tools_registered(self):
        agent = self._build()
        names = self._tool_names(agent)
        # FileSystem 8 tools
        for name in ("read_file", "write_file", "edit_file", "list_directory",
                     "search_files", "find_files", "create_directory", "file_info"):
            assert name in names, f"FileSystem tool manquante : {name}"
        # Customs du profil Coder
        for name in ("search_replace", "multi_replace", "append_file", "check_js_syntax",
                     "read_python_skeleton", "log_event", "visual_check",
                     "check_run_state", "load_skill"):
            assert name in names, f"custom tool manquante : {name}"

    def test_output_tool_registered(self):
        """output_type=CoderOutput → sortie structurée forcée (remplace
        extract_and_validate + sauvetage DSPy). Cohérence des noms : le
        protocole promet `final_result`, le moteur enregistre
        DEFAULT_OUTPUT_TOOL_NAME sous le même nom."""
        from pydantic_ai._output import DEFAULT_OUTPUT_TOOL_NAME

        agent = self._build()
        assert agent.output_type is CoderOutput
        assert getattr(agent, "_output_toolset", None) is not None
        instructions = build_coder_instructions(_base_task())
        assert f"`{DEFAULT_OUTPUT_TOOL_NAME}`" in instructions


# ============================================================
# Moteur UNIQUE pydantic (F-169 — retrait du CodeAgent smolagents)
# ============================================================

class TestCoderEnginePydanticOnly:
    @pytest.mark.anyio
    async def test_execute_coder_node_delegates_to_pydantic_always(self, monkeypatch):
        """F-169 : execute_coder_node délègue TOUJOURS à run_coder_pydantic —
        l'exécution smolagents CodeAgent est retirée du graphe (décision user
        2026-08-24). Plus de setting CODER_ENGINE : rien à sélectionner."""
        import graph_orchestrator.coder_pydantic as cp
        from graph_orchestrator import nodes

        calls: list = []

        async def _fake_run(task, settings):
            calls.append(task)
            return None, None

        monkeypatch.setattr(cp, "run_coder_pydantic", _fake_run)
        await nodes.execute_coder_node(_base_task(), fast_model=None, settings=load_settings())
        assert len(calls) == 1
        assert calls[0]["id"] == "ts-001"

    def test_smolagents_codeagent_absent_du_noeud(self):
        """Le corps d'execute_coder_node ne référence PLUS CompactingCodeAgent
        ni les callbacks vision smolagents — source vérifiée, pas runtime."""
        import inspect
        from graph_orchestrator import nodes

        body = inspect.getsource(nodes.execute_coder_node)
        # On vise les CONSTRUCTIONS exécutables, pas la prose du docstring
        # (qui documente le retrait F-169).
        assert "local_coder = CompactingCodeAgent" not in body
        assert "make_screenshot_callback" not in body.replace(
            "callbacks vision smolagents", ""
        )
        assert "return await run_coder_pydantic" in body

    def test_settings_engine_retire(self):
        """CODER_ENGINE/TESTER_ENGINE n'existent plus dans Settings (F-169)."""
        import dataclasses
        from graph_orchestrator.config import Settings

        names = {f.name for f in dataclasses.fields(Settings)}
        assert "coder_engine" not in names
        assert "tester_engine" not in names
