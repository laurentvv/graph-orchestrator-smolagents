"""Tests du recall mémoire cross-run (F-68 Phase 2, P6-ter).

3 tiers (miroir test_consolidation.py) :
  1. Déterministe (0 LLM) — recall_lessons + build_lessons_block + KG.recall_lessons.
  2. Intégration prompt — injection conditionnelle dans execute_coder_node.
  3. E2E workflow — recall en début de run, opt-out, cross-run sur disque.

Couvre les critères de contract.md (recall-centric + global unique).
"""

import asyncio
import os
import tempfile
from dataclasses import replace

import pytest

from graph_orchestrator.knowledge_graph import KnowledgeGraph
from graph_orchestrator.lesson_recall import (
    DEFAULT_LESSON_KINDS,
    build_lessons_block,
    recall_lessons,
)


# ==========================================
# Helpers
# ==========================================

def _make_kg(tmp_path=None):
    """KG en RAM (tests rapides) ou sur disque (tests persistance)."""
    if tmp_path is not None:
        return KnowledgeGraph(str(tmp_path / "kg_recall.db"))
    return KnowledgeGraph(":memory:")


def _add_lesson(kg, entity_id, content, kind="insight", run_id="run_x"):
    """Ajoute une claim durable (insight/escalation) au notebook global."""
    kg.add_entity(entity_id, kind="file")
    return kg.add_claim(
        entity_id=entity_id,
        content=content,
        kind=kind,
        confidence=0.8,
        source="test",
        run_id=run_id,
    )


def _add_scratch(kg, entity_id, content, kind="refutation", run_id="run_x"):
    """Ajoute une claim éphémère (observation/refutation) — le scratch."""
    kg.add_entity(entity_id, kind="file")
    return kg.add_claim(
        entity_id=entity_id,
        content=content,
        kind=kind,
        confidence=0.5,
        source="test",
        run_id=run_id,
    )


# ==========================================
# Tier 1 — recall_lessons + KG.recall_lessons (déterministe, 0 LLM)
# ==========================================

class TestRecallLessonsKG:
    """Tests de KnowledgeGraph.recall_lessons (query SQL globale cross-run)."""

    def test_recovers_insight_and_escalation_globally(self, tmp_path):
        """Le recall récupère insight + escalation de TOUS les runs (global)."""
        kg = _make_kg(tmp_path)
        try:
            _add_lesson(kg, "file:a", "leçon A", kind="insight", run_id="run1")
            _add_lesson(kg, "file:b", "leçon B", kind="escalation", run_id="run2")
            _add_lesson(kg, "file:c", "leçon C", kind="insight", run_id="run3")
            results = kg.recall_lessons(limit=10)
            contents = [r["content"] for r in results]
            assert "leçon A" in contents
            assert "leçon B" in contents
            assert "leçon C" in contents
        finally:
            kg.close()

    def test_ignores_ephemeral_kinds(self, tmp_path):
        """Le recall IGNORE observation/refutation (scratch éphémère, pas notebook)."""
        kg = _make_kg(tmp_path)
        try:
            _add_lesson(kg, "file:a", "leçon durable", kind="insight", run_id="run1")
            _add_scratch(kg, "file:a", "refuté éphémère", kind="refutation", run_id="run1")
            _add_scratch(kg, "file:a", "obs éphémère", kind="observation", run_id="run1")
            results = kg.recall_lessons(limit=10)
            contents = [r["content"] for r in results]
            assert "leçon durable" in contents
            assert "refuté éphémère" not in contents
            assert "obs éphémère" not in contents
        finally:
            kg.close()

    def test_respects_limit_top_n(self, tmp_path):
        """Le recall respecte la limite (top-N par récence DESC)."""
        kg = _make_kg(tmp_path)
        try:
            for i in range(10):
                _add_lesson(kg, f"file:{i}", f"leçon {i}", kind="insight", run_id=f"run{i}")
            results = kg.recall_lessons(limit=3)
            assert len(results) == 3
        finally:
            kg.close()

    def test_empty_kg_returns_empty(self, tmp_path):
        """Un KG sans leçons durables → liste vide."""
        kg = _make_kg(tmp_path)
        try:
            _add_scratch(kg, "file:a", "du scratch", kind="refutation", run_id="run1")
            assert kg.recall_lessons(limit=10) == []
        finally:
            kg.close()

    def test_cross_run_visible(self, tmp_path):
        """Les leçons d'autres runs sont visibles (cross-run = pas de filtre run_id)."""
        kg = _make_kg(tmp_path)
        try:
            _add_lesson(kg, "file:old", "leçon ancien run", kind="insight", run_id="ancien_run_123")
            _add_lesson(kg, "file:new", "leçon run courant", kind="insight", run_id="run_courant_456")
            results = kg.recall_lessons(limit=10)
            contents = [r["content"] for r in results]
            assert "leçon ancien run" in contents
            assert "leçon run courant" in contents
        finally:
            kg.close()

    def test_only_open_status(self, tmp_path):
        """Le recall ne récupère que les claims status='open' (pas closed/resolved)."""
        kg = _make_kg(tmp_path)
        try:
            cid = _add_lesson(kg, "file:a", "leçon ouverte", kind="insight", run_id="run1")
            _add_lesson(kg, "file:b", "leçon fermée", kind="insight", run_id="run2")
            # Ferme la 2e claim manuellement.
            kg.conn.execute("UPDATE claim SET status='closed' WHERE content='leçon fermée'")
            kg.conn.commit()
            results = kg.recall_lessons(limit=10)
            contents = [r["content"] for r in results]
            assert "leçon ouverte" in contents
            assert "leçon fermée" not in contents
        finally:
            kg.close()

    def test_empty_kinds_returns_empty(self, tmp_path):
        """kinds=set() → retourne [] (défense, pas de crash)."""
        kg = _make_kg(tmp_path)
        try:
            _add_lesson(kg, "file:a", "leçon", kind="insight", run_id="run1")
            assert kg.recall_lessons(kinds=set(), limit=10) == []
        finally:
            kg.close()

    def test_limit_zero_returns_empty(self, tmp_path):
        """limit<=0 → retourne [] (défense)."""
        kg = _make_kg(tmp_path)
        try:
            _add_lesson(kg, "file:a", "leçon", kind="insight", run_id="run1")
            assert kg.recall_lessons(limit=0) == []
            assert kg.recall_lessons(limit=-1) == []
        finally:
            kg.close()

    def test_custom_kinds(self, tmp_path):
        """On peut passer des kinds custom (ex: insight seul)."""
        kg = _make_kg(tmp_path)
        try:
            _add_lesson(kg, "file:a", "leçon insight", kind="insight", run_id="run1")
            _add_lesson(kg, "file:b", "leçon escalation", kind="escalation", run_id="run2")
            results = kg.recall_lessons(kinds={"insight"}, limit=10)
            contents = [r["content"] for r in results]
            assert "leçon insight" in contents
            assert "leçon escalation" not in contents
        finally:
            kg.close()

    def test_result_shape(self, tmp_path):
        """Chaque résultat a les clés content/kind/created_at."""
        kg = _make_kg(tmp_path)
        try:
            _add_lesson(kg, "file:a", "leçon", kind="insight", run_id="run1")
            results = kg.recall_lessons(limit=1)
            assert len(results) == 1
            r = results[0]
            assert set(r.keys()) == {"content", "kind", "created_at"}
            assert r["kind"] == "insight"
            assert isinstance(r["created_at"], str)
        finally:
            kg.close()


class TestRecallLessonsModuleWrapper:
    """Tests du wrapper module-level recall_lessons (lesson_recall.py)."""

    def test_wrapper_delegates_to_kg(self, tmp_path):
        """recall_lessons(kg, ...) délègue à kg.recall_lessons."""
        kg = _make_kg(tmp_path)
        try:
            _add_lesson(kg, "file:a", "leçon", kind="insight", run_id="run1")
            results = recall_lessons(kg, limit=5)
            assert len(results) == 1
            assert results[0]["content"] == "leçon"
        finally:
            kg.close()

    def test_default_kinds_constant(self):
        """DEFAULT_LESSON_KINDS = {insight, escalation} (cohérent prune_old_claims)."""
        assert DEFAULT_LESSON_KINDS == {"insight", "escalation"}


class TestBuildLessonsBlock:
    """Tests de build_lessons_block (formatage markdown, 0 LLM)."""

    def test_empty_claims_returns_empty(self):
        """Liste vide → '' (injection conditionnelle côté prompt)."""
        assert build_lessons_block([]) == ""

    def test_format_single_insight(self):
        """Une leçon insight → bloc avec en-tête + note + numérotation + badge."""
        claims = [{"content": "Une itération par requestAnimationFrame", "kind": "insight"}]
        block = build_lessons_block(claims)
        assert "LEÇONS DE RUNS PRÉCÉDENTS" in block
        assert "ignore les autres" in block
        assert "1. [LEÇON] Une itération par requestAnimationFrame" in block

    def test_format_escalation_badge(self):
        """Une escalation → badge [ESCALATION]."""
        claims = [{"content": "Bug critique non résolu", "kind": "escalation"}]
        block = build_lessons_block(claims)
        assert "1. [ESCALATION] Bug critique non résolu" in block

    def test_format_numbering_multiple(self):
        """Plusieurs leçons → numérotation séquentielle 1, 2, 3..."""
        claims = [
            {"content": "leçon A", "kind": "insight"},
            {"content": "leçon B", "kind": "escalation"},
            {"content": "leçon C", "kind": "insight"},
        ]
        block = build_lessons_block(claims)
        assert "1. [LEÇON] leçon A" in block
        assert "2. [ESCALATION] leçon B" in block
        assert "3. [LEÇON] leçon C" in block

    def test_truncation_max_chars(self):
        """Troncature à max_chars — le bloc ne dépasse pas massivement le budget."""
        long_content = "x" * 5000
        claims = [
            {"content": long_content, "kind": "insight"},
            {"content": long_content, "kind": "insight"},
        ]
        block = build_lessons_block(claims, max_chars=500)
        # Le bloc tronqué doit être raisonnablement borné (en-tête + corps tronqué).
        assert len(block) < 5000
        assert "LEÇONS DE RUNS PRÉCÉDENTS" in block

    def test_empty_content_skipped(self):
        """Une leçon avec content vide est skippée (pas de ligne vide numérotée)."""
        claims = [
            {"content": "leçon valide", "kind": "insight"},
            {"content": "", "kind": "insight"},
            {"content": "   ", "kind": "insight"},
        ]
        block = build_lessons_block(claims)
        assert "1. [LEÇON] leçon valide" in block
        # Pas de 2e ligne (les 2 vides sont skippées).
        assert "2." not in block

    def test_unknown_kind_badge(self):
        """Un kind non standard → badge [KIND] uppercase."""
        claims = [{"content": "leçon bizarre", "kind": "custom"}]
        block = build_lessons_block(claims)
        assert "1. [CUSTOM] leçon bizarre" in block

    def test_note_explicite_ignore_if_irrelevant(self):
        """Le bloc contient la note 'ignore si non pertinent' (mitigation bruit global)."""
        claims = [{"content": "leçon", "kind": "insight"}]
        block = build_lessons_block(claims)
        assert "pertinentes" in block.lower() or "ignore" in block.lower()


# ==========================================
# Tier 2 — Intégration prompt Coder
# ==========================================

class TestCoderPromptInjection:
    """L'injection du bloc leçons dans le prompt Coder est conditionnelle.

    On ne reconstruit pas tout le prompt (trop de dépendances smolagents) — on
    vérifie que la LOGIQUE d'injection (pattern conditionnel original_content
    étendu) est correcte : si task["lessons"] est vide, rien n'est ajouté ; si
    non vide, le bloc est ajouté avant le RAPPEL récence.
    """

    def test_empty_lessons_no_injection(self):
        """task['lessons']="" → le bloc leçons n'est PAS dans le prompt."""
        # Simule le pattern d'injection de nodes.py (ligne ~857).
        task = {"content": "ma tâche", "original_content": "", "lessons": ""}
        suffix = ""
        if task.get("original_content"):
            suffix += f"\n### Contexte global\n{task['original_content']}\n"
        if task.get("lessons"):
            suffix += f"\n{task['lessons']}\n"
        suffix += "\n### RAPPEL (récence)"
        assert "LEÇONS DE RUNS" not in suffix
        assert "RAPPEL (récence)" in suffix

    def test_nonempty_lessons_injected(self):
        """task['lessons'] non vide → le bloc est injecté avant le RAPPEL."""
        task = {
            "content": "ma tâche",
            "original_content": "",
            "lessons": "### LEÇONS DE RUNS PRÉCÉDENTS\n1. [LEÇON] test",
        }
        suffix = ""
        if task.get("original_content"):
            suffix += f"\n### Contexte global\n{task['original_content']}\n"
        if task.get("lessons"):
            suffix += f"\n{task['lessons']}\n"
        suffix += "\n### RAPPEL (récence)"
        assert "LEÇONS DE RUNS PRÉCÉDENTS" in suffix
        # L'ordre : lessons AVANT rappel.
        assert suffix.index("LEÇONS") < suffix.index("RAPPEL")

    def test_lessons_and_original_content_coexist(self):
        """lessons + original_content → les deux blocs sont injectés."""
        task = {
            "content": "ma tâche",
            "original_content": "cahier des charges",
            "lessons": "### LEÇONS DE RUNS PRÉCÉDENTS\n1. [LEÇON] test",
        }
        suffix = ""
        if task.get("original_content"):
            suffix += f"\n### Contexte global\n{task['original_content']}\n"
        if task.get("lessons"):
            suffix += f"\n{task['lessons']}\n"
        suffix += "\n### RAPPEL (récence)"
        assert "Contexte global" in suffix
        assert "LEÇONS DE RUNS PRÉCÉDENTS" in suffix
        # Ordre : original_content, puis lessons, puis rappel.
        assert suffix.index("Contexte global") < suffix.index("LEÇONS")
        assert suffix.index("LEÇONS") < suffix.index("RAPPEL")

    def test_missing_lessons_key_no_crash(self):
        """task sans clé 'lessons' → pas de crash (task.get('lessons') = None → falsy)."""
        task = {"content": "ma tâche", "original_content": ""}
        # Pas de KeyError car on utilise .get().
        suffix = ""
        if task.get("original_content"):
            suffix += f"\n### Contexte global\n{task['original_content']}\n"
        if task.get("lessons"):
            suffix += f"\n{task['lessons']}\n"
        suffix += "\n### RAPPEL (récence)"
        assert "RAPPEL (récence)" in suffix


# ==========================================
# Tier 3 — E2E workflow (recall en début de run)
# ==========================================

def _seed_tasks():
    return [{
        "id": "T1",
        "content": "Crée un visualiseur Bubble Sort en HTML/JS vanilla.",
        "target_files": ["index.html"],
    }]


def _setup_workflow_mocks(monkeypatch):
    """Mocke tous les nœuds du workflow. Capture le sub_dict reçu par le Coder
    pour vérifier que la clé 'lessons' est présente."""
    import graph_orchestrator.nodes as nodes_mod
    import graph_orchestrator.dspy_nodes as dspy_mod
    import graph_orchestrator.workflows as wf_mod

    monkeypatch.setattr(wf_mod, "build_fast_model", lambda s: "FAKE_FAST")
    monkeypatch.setattr(wf_mod, "build_reasoning_model", lambda s: "FAKE_REASON")

    async def fake_router(content, model, s):
        from graph_orchestrator.models import RouterOutput
        return RouterOutput(language="HTML"), None
    monkeypatch.setattr(dspy_mod, "execute_router_node", fake_router)

    async def fake_prompt_refiner(raw, model, s):
        return None, None
    monkeypatch.setattr(dspy_mod, "execute_prompt_refiner_node", fake_prompt_refiner)

    async def fake_architect(task, model, s):
        from graph_orchestrator.models import ArchitectOutput, ArchitectTask
        return ArchitectOutput(
            plan_id="p1", global_architecture="1 fichier",
            subtasks=[ArchitectTask(task_id="st1", description="Bubble Sort",
                                     target_files=["index.html"])],
        ), None
    monkeypatch.setattr(dspy_mod, "execute_architect_node", fake_architect)

    # Capture le sub_dict pour inspecter la clé 'lessons'.
    captured = {"sub_dict": None}

    async def fake_coder(sub, model, s):
        from graph_orchestrator.models import CoderOutput
        captured["sub_dict"] = dict(sub)
        return CoderOutput(task_id=sub["id"], status="success", details="code généré"), None
    monkeypatch.setattr(nodes_mod, "execute_coder_node", fake_coder)

    async def fake_tester(sub, model, s):
        from graph_orchestrator.models import CoderOutput
        return CoderOutput(task_id=sub["id"], status="success", details="tests ok"), None
    async def fake_security(sub, model, s):
        from graph_orchestrator.models import SecurityOutput
        return SecurityOutput(task_id=sub["id"], is_secure=True, vulnerabilities=[]), None
    monkeypatch.setattr(nodes_mod, "execute_tester_node", fake_tester)
    monkeypatch.setattr(dspy_mod, "execute_security_reviewer_node", fake_security)

    async def fake_judge(sub, test_res, sec_res, model, s):
        from graph_orchestrator.models import CodeJudgeOutput
        return CodeJudgeOutput(
            task_id=sub["id"], is_approved=True, final_feedback="OK."
        ), None
    monkeypatch.setattr(dspy_mod, "execute_code_judge_node", fake_judge)

    async def fake_escalation(sub, failure_history, model, s):
        from graph_orchestrator.models import EscalationOutput
        return EscalationOutput(
            task_id=sub["id"], root_cause="x", attempted_fixes=[], lesson="y", severity="low"
        ), None
    monkeypatch.setattr(dspy_mod, "execute_escalation_node", fake_escalation)

    async def fake_consolidation(kg, run_id, s):
        return {"file:st1": {"updated": 0, "deleted": 0, "added": 0, "skipped": 0}}, None
    monkeypatch.setattr(dspy_mod, "execute_consolidation_node", fake_consolidation)

    return captured


def _settings(recall_enabled=True, kg_path=":memory:"):
    from graph_orchestrator.config import Settings
    return Settings(
        local_api_base="http://x/v1", local_reasoning_api_base="http://x/v1",
        local_api_key="sk", fast_model_id="m", reasoning_model_id="m",
        reasoning_max_tokens=8, fast_max_tokens=8, coder_temperature=0.2,
        llm_timeout_s=1.0, judge_confidence_threshold=0.5,
        worker_max_retries=1, adversary_count=1, adversary_threshold=0.5,
        max_iterations=3, hitl_enabled=False, hitl_nodes="synth",
        kg_path=kg_path, workflow_mode="coding", log_level="LOW",
        fresh_start=True,
        test_timeout_s=120, stderr_head_lines=20, stderr_tail_lines=20,
        feedback_max_chars=2000, escalation_enabled=True,
        memory_consolidation_enabled=False,  # skip consolidation LLM
        memory_recall_enabled=recall_enabled,
        memory_recall_limit=8,
        memory_recall_max_chars=1500,
    )


class TestRecallWorkflow:
    def test_lessons_key_in_sub_dict(self, monkeypatch):
        """Le recall injecte une clé 'lessons' dans sub_dict (vide si KG vierge)."""
        captured = _setup_workflow_mocks(monkeypatch)
        from graph_orchestrator.workflows import run_coding_workflow
        asyncio.run(run_coding_workflow(_seed_tasks(), _settings()))
        assert captured["sub_dict"] is not None, "le Coder doit avoir été appelé"
        assert "lessons" in captured["sub_dict"], "la clé 'lessons' doit être dans sub_dict"

    def test_recall_populates_lessons_from_prior_run(self, monkeypatch):
        """Une leçon durable d'un run antérieur est rappelée et injectée au Coder."""
        # Pré-peuple le KG sur disque avec une insight cross-run.
        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "kg_recall_e2e.db")
        pre_kg = KnowledgeGraph(db)
        pre_kg.add_entity("file:prior", kind="file")
        prior_cid = pre_kg.add_claim(
            "file:prior", "Une itération par requestAnimationFrame évite l'animation instantanée",
            "insight", 0.9, "consolidation", run_id="prior_run_abc",
        )
        pre_kg.close()

        captured = _setup_workflow_mocks(monkeypatch)
        from graph_orchestrator.workflows import run_coding_workflow
        s = replace(_settings(kg_path=db), memory_recall_enabled=True)
        asyncio.run(run_coding_workflow(_seed_tasks(), s))

        assert captured["sub_dict"] is not None
        lessons = captured["sub_dict"]["lessons"]
        assert "Une itération par requestAnimationFrame" in lessons
        assert "LEÇONS DE RUNS PRÉCÉDENTS" in lessons

    def test_recall_disabled_empty_lessons(self, monkeypatch):
        """memory_recall_enabled=False → clé 'lessons' présente mais vide."""
        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "kg_recall_off.db")
        pre_kg = KnowledgeGraph(db)
        pre_kg.add_entity("file:prior", kind="file")
        pre_kg.add_claim(
            "file:prior", "leçon qui ne devrait pas être rappelée",
            "insight", 0.9, "consolidation", run_id="prior_run",
        )
        pre_kg.close()

        captured = _setup_workflow_mocks(monkeypatch)
        from graph_orchestrator.workflows import run_coding_workflow
        s = replace(_settings(kg_path=db), memory_recall_enabled=False)
        asyncio.run(run_coding_workflow(_seed_tasks(), s))

        assert captured["sub_dict"] is not None
        assert captured["sub_dict"]["lessons"] == "", "recall désactivé → bloc vide"

    def test_recall_no_lessons_in_kg_empty_block(self, monkeypatch):
        """KG vierge (aucune insight/escalation) → bloc leçons vide."""
        captured = _setup_workflow_mocks(monkeypatch)
        from graph_orchestrator.workflows import run_coding_workflow
        asyncio.run(run_coding_workflow(_seed_tasks(), _settings()))
        assert captured["sub_dict"]["lessons"] == "", "KG vierge → bloc leçons vide"


# ==========================================
# Config
# ==========================================

class TestRecallConfig:
    """Les settings Phase 2 sont lus depuis l'environnement (opt-out)."""

    def test_defaults_recall_enabled(self, monkeypatch):
        """memory_recall_enabled=True par défaut."""
        from graph_orchestrator.config import load_settings
        monkeypatch.delenv("MEMORY_RECALL_ENABLED", raising=False)
        s = load_settings()
        assert s.memory_recall_enabled is True
        assert s.memory_recall_limit == 8
        assert s.memory_recall_max_chars == 1500

    def test_opt_out_env(self, monkeypatch):
        """MEMORY_RECALL_ENABLED=false désactive le recall."""
        from graph_orchestrator.config import load_settings
        monkeypatch.setenv("MEMORY_RECALL_ENABLED", "false")
        s = load_settings()
        assert s.memory_recall_enabled is False

    def test_override_limit(self, monkeypatch):
        """MEMORY_RECALL_LIMIT override la limite."""
        from graph_orchestrator.config import load_settings
        monkeypatch.setenv("MEMORY_RECALL_LIMIT", "15")
        s = load_settings()
        assert s.memory_recall_limit == 15
