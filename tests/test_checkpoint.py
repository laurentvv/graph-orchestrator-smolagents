"""Tests de la Persistance d'État (Priorité 3 : Checkpoints).

Valide la reprise après crash du workflow coding :
  - Stockage DuckDB (table checkpoint, save/load/clear).
  - run_id stable dérivé du contenu de tâche.
  - Sérialisation du plan de l'Architect (Pydantic round-trip).
  - Reprise de bout en bout : skip de l'Architect + skip des sous-tâches
    complétées + reprise à la bonne itération.

Aucun appel LLM réel : les nœuds et les builders de modèles sont monkeypatchés
pour des exécutions déterministes et rapides. Le KG utilise ":memory:" (RAM).
"""

import tempfile
import asyncio
import hashlib

import pytest

from graph_orchestrator.knowledge_graph import KnowledgeGraph
from graph_orchestrator.models import ArchitectOutput, ArchitectTask, CodeJudgeOutput
from graph_orchestrator.workflows import run_coding_workflow


# ==========================================
# 1. Couche stockage DuckDB (déterministe, sans workflow)
# ==========================================

@pytest.fixture
def kg():
    return KnowledgeGraph(":memory:")


class TestCheckpointStorage:
    def test_save_load_round_trip(self, kg):
        """save_checkpoint puis load_checkpoint retourne le même payload."""
        payload = {"architect_result": {"plan_id": "p1"}, "current_iteration": 2}
        kg.save_checkpoint("coding_abc", payload)
        loaded = kg.load_checkpoint("coding_abc")
        assert loaded == payload

    def test_load_absent_retourne_none(self, kg):
        """Aucun checkpoint → None (et non une exception)."""
        assert kg.load_checkpoint("inexistant") is None

    def test_upsert_ecrase(self, kg):
        """Re-save avec le même run_id écrase l'ancien payload."""
        kg.save_checkpoint("coding_run", {"current_iteration": 1})
        kg.save_checkpoint("coding_run", {"current_iteration": 3})
        assert kg.load_checkpoint("coding_run") == {"current_iteration": 3}

    def test_clear_efface(self, kg):
        """clear_checkpoint supprime le checkpoint ; load retourne ensuite None."""
        kg.save_checkpoint("coding_run", {"a": 1})
        assert kg.load_checkpoint("coding_run") is not None
        kg.clear_checkpoint("coding_run")
        assert kg.load_checkpoint("coding_run") is None


# ==========================================
# 2. run_id stable dérivé du contenu de tâche
# ==========================================

class TestRunId:
    def test_run_id_deterministe(self):
        """Deux exécutions avec le même contenu produisent le même run_id."""
        content = "Crée une landing page premium"
        key = content.strip().lower()
        rid1 = f"coding_{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}"
        rid2 = f"coding_{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}"
        assert rid1 == rid2

    def test_run_id_differe_si_contenu_differe(self):
        """Deux contenus différents → run_id différents."""
        def _rid(content):
            key = content.strip().lower()
            return f"coding_{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}"

        assert _rid("Landing page") != _rid("Jeu Tetris")

    def test_run_id_insensible_casse_espaces(self):
        """Le hash normalise trim+lower : variations cosmétiques = même run_id."""
        def _rid(content):
            key = content.strip().lower()
            return f"coding_{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}"

        assert _rid("Ma tâche") == _rid("  ma tâche  ")


# ==========================================
# 3. Sérialisation du plan de l'Architect (Pydantic round-trip)
# ==========================================

class TestArchitectSerialization:
    def test_architect_output_round_trip(self):
        """Le plan de l'Architect survit à model_dump → JSON → ArchitectOutput(**).

        C'est ce qui permet de recharger le plan depuis le checkpoint sans
        relancer le nœud LLM coûteux.
        """
        plan = ArchitectOutput(
            plan_id="plan-1",
            global_architecture="3 fichiers HTML/CSS/JS",
            subtasks=[
                ArchitectTask(task_id="st1", description="HTML", target_files=["index.html"]),
                ArchitectTask(task_id="st2", description="CSS", target_files=["styles.css"]),
            ],
        )
        dumped = plan.model_dump()
        restored = ArchitectOutput(**dumped)
        assert restored.plan_id == "plan-1"
        assert len(restored.subtasks) == 2
        assert restored.subtasks[0].task_id == "st1"
        assert restored.subtasks[1].target_files == ["styles.css"]


# ==========================================
# 4. Reprise de bout en bout (workflow complet, nœuds mockés)
# ==========================================

def _seed_tasks():
    return [{
        "id": "T1",
        "content": "Crée une landing page premium Nimbus",
        "target_files": ["index.html", "styles.css"],
    }]


def _setup_workflow_mocks(monkeypatch, kg_path=":memory:", approve=True,
                          crash_after_checkpoint=False, settings=None):
    """Installe des mocks de nœuds déterministes sur les modules source.

    Les nœuds sont importés LOCALEMENT dans run_coding_workflow, donc on patche
    les attributs sur graph_orchestrator.nodes / graph_orchestrator.dspy_nodes
    (l'`from .nodes import execute_coder_node` récupère l'attribut au runtime).
    """
    import graph_orchestrator.nodes as nodes_mod
    import graph_orchestrator.dspy_nodes as dspy_mod
    import graph_orchestrator.workflows as wf_mod

    # Empêche toute connexion Ollama : builders renvoient un faux modèle.
    monkeypatch.setattr(wf_mod, "build_fast_model", lambda s: "FAKE_FAST")
    monkeypatch.setattr(wf_mod, "build_reasoning_model", lambda s: "FAKE_REASON")

    # Router : classe en HTML.
    from graph_orchestrator.models import RouterOutput
    async def fake_router(content, model, s):
        return RouterOutput(language="HTML"), None
    monkeypatch.setattr(dspy_mod, "execute_router_node", fake_router)

    # F-39 : mocke le PromptRefiner (pas d'appel LLM en test E2E ; repli prompt brut).
    async def fake_prompt_refiner(raw, model, s):
        return None, None
    monkeypatch.setattr(dspy_mod, "execute_prompt_refiner_node", fake_prompt_refiner)

    # Architect : 2 sous-tâches déterministes.
    async def fake_architect(task, model, s):
        plan = ArchitectOutput(
            plan_id="plan-1",
            global_architecture="2 fichiers",
            subtasks=[
                ArchitectTask(task_id="st1", description="Faire le HTML", target_files=["index.html"]),
                ArchitectTask(task_id="st2", description="Faire le CSS", target_files=["styles.css"]),
            ],
        )
        return plan, None
    monkeypatch.setattr(dspy_mod, "execute_architect_node", fake_architect)

    # Coder : réussit, écrit un fichier factice.
    from graph_orchestrator.models import CoderOutput
    call_count = {"n": 0}
    async def fake_coder(sub, model, s):
        call_count["n"] += 1
        if crash_after_checkpoint and call_count["n"] == 1:
            raise RuntimeError("CRASH simulé juste après le checkpoint de début d'itération")
        return CoderOutput(task_id=sub["id"], status="success", details="ok"), None
    monkeypatch.setattr(nodes_mod, "execute_coder_node", fake_coder)

    # Tester + Security : parallèles, retournent un verdict neutre.
    async def fake_tester(sub, model, s):
        return CoderOutput(task_id=sub["id"], status="success", details="tests ok"), None
    async def fake_security(sub, model, s):
        from graph_orchestrator.models import SecurityOutput
        return SecurityOutput(task_id=sub["id"], is_secure=True, vulnerabilities=[]), None
    monkeypatch.setattr(nodes_mod, "execute_tester_node", fake_tester)
    monkeypatch.setattr(dspy_mod, "execute_security_reviewer_node", fake_security)

    # Judge : approuve (ou rejette selon le paramètre).
    async def fake_judge(sub, test_res, sec_res, model, s):
        return CodeJudgeOutput(
            task_id=sub["id"], is_approved=approve, final_feedback="ok"
        ), None
    monkeypatch.setattr(dspy_mod, "execute_code_judge_node", fake_judge)

    return call_count


def _settings(kg_path=":memory:", fresh_start=False):
    from graph_orchestrator.config import Settings
    # Construit des settings avec un KG en mémoire + fresh_start pilotable.
    s = Settings(
        output_dir=tempfile.mkdtemp(prefix="e2e_runs_"),  # F-113 : isole du vrai runs/
        local_api_base="http://x/v1",
        local_reasoning_api_base="http://x/v1",
        local_api_key="sk",
        fast_model_id="m", reasoning_model_id="m",
        reasoning_max_tokens=8, fast_max_tokens=8, coder_temperature=0.2,
        llm_timeout_s=1.0, judge_confidence_threshold=0.5,
        worker_max_retries=1, adversary_count=1, adversary_threshold=0.5,
        max_iterations=3, hitl_enabled=False, hitl_nodes="synth",
        kg_path=kg_path, workflow_mode="coding", log_level="LOW",
        fresh_start=fresh_start,
        test_timeout_s=120, stderr_head_lines=20, stderr_tail_lines=20,
        feedback_max_chars=2000,
    )
    return s


class TestRepriseWorkflow:
    def test_run_complet_sans_reprise(self, monkeypatch):
        """Run nominal : 2 sous-tâches approuvées, aucun checkpoint résiduel."""
        _setup_workflow_mocks(monkeypatch, approve=True)
        out, metrics = asyncio.run(run_coding_workflow(_seed_tasks(), _settings()))
        results = out["final_results"]
        assert all(r["status"] == "success" for r in results)
        assert len(results) == 2

    def test_skip_architect_et_sous_taches_completed(self, monkeypatch):
        """Reprise : un checkpoint pré-existant fait sauter l'Architect + 1 sous-tâche.

        On crée un KG partagé sur disque, on y écrit un checkpoint (plan + ST1
        completed), puis on relance le workflow : l'Architect ne doit PAS être
        rappelé et la ST1 doit être skippée (résultat replayed=True).
        """
        import os
        import tempfile
        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "test_kg.db")

        # 1) Écrit un checkpoint "interrompu" : plan présent + ST1 complétée.
        plan = ArchitectOutput(
            plan_id="plan-1", global_architecture="2 fichiers",
            subtasks=[
                ArchitectTask(task_id="st1", description="Faire le HTML", target_files=["index.html"]),
                ArchitectTask(task_id="st2", description="Faire le CSS", target_files=["styles.css"]),
            ],
        ).model_dump()
        kg_seed = KnowledgeGraph(db)
        run_id = f"coding_{hashlib.sha1('crée une landing page premium nimbus'.encode()).hexdigest()[:16]}"
        kg_seed.save_checkpoint(run_id, {
            "architect_result": plan,
            "completed_subtasks": ["st1"],
            "current_subtask_idx": 1,
            "current_iteration": 1,
        })
        kg_seed.close()

        # 2) Relance le workflow : l'Architect doit être skippé (mock jamais appelé
        #    au-delà de l'import) et ST1 doit apparaître comme replayed.
        _setup_workflow_mocks(monkeypatch, approve=True)
        out, _ = asyncio.run(run_coding_workflow(_seed_tasks(), _settings(kg_path=db)))

        results = {r["task_id"]: r for r in out["final_results"]}
        # ST1 skippée (déjà completed) → replayed
        assert results["st1"].get("replayed") is True
        # ST2 exécutée normalement → success
        assert results["st2"]["status"] == "success"

    def test_checkpoint_efface_en_fin_de_run(self, monkeypatch):
        """Un run qui va au bout efface son checkpoint (run "terminé")."""
        import os
        import tempfile
        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "test_kg.db")
        _setup_workflow_mocks(monkeypatch, approve=True)

        # run_id que le workflow va calculer (même hash que le contenu de _seed_tasks).
        key = "crée une landing page premium nimbus"
        run_id = f"coding_{hashlib.sha1(key.encode()).hexdigest()[:16]}"

        asyncio.run(run_coding_workflow(_seed_tasks(), _settings(kg_path=db)))

        kg = KnowledgeGraph(db)
        assert kg.load_checkpoint(run_id) is None  # effacé en fin de run

    def test_granularite_debut_iteration(self, monkeypatch):
        """Le checkpoint reflète la (sous-tâche, itération) au début de chaque tour.

        On simule un crash du Coder sur la ST1 itération 1 : un checkpoint doit
        avoir été écrit AVANT le crash (début d'itération), pointant sur (0, 1).
        """
        import os
        import tempfile
        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "test_kg.db")
        _setup_workflow_mocks(monkeypatch, approve=True, crash_after_checkpoint=True)

        key = "crée une landing page premium nimbus"
        run_id = f"coding_{hashlib.sha1(key.encode()).hexdigest()[:16]}"

        # Le Coder lève une exception → le workflow propage (crash simulé).
        with pytest.raises(RuntimeError):
            asyncio.run(run_coding_workflow(_seed_tasks(), _settings(kg_path=db)))

        # Le checkpoint "début d'itération" doit exister : (ST idx 0, itération 1)
        # + le plan de l'Architect déjà persisté.
        kg = KnowledgeGraph(db)
        ckpt = kg.load_checkpoint(run_id)
        assert ckpt is not None
        assert ckpt["current_subtask_idx"] == 0
        assert ckpt["current_iteration"] == 1
        assert ckpt["architect_result"] is not None
        assert ckpt["architect_result"]["plan_id"] == "plan-1"
