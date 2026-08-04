"""Tests du Nœud d'Escalade (Priorité 3, F-23).

Valide le post-mortem automatique quand le Circuit Breaker s'active (3 itérations
Coder↔Tester↔Judge toutes rejetées) :
  - Nœud DSPy isolé : signature, échec gracieux, métriques.
  - Branchement workflow E2E : une sous-tâche qui épuise max_iterations déclenche
    l'escalade (status="escalated"), persiste un diagnostic dans le KG
    (kind="escalation") et le relie aux réfutations (arêtes ESCALATES).
  - Toggle ESCALATION_ENABLED=False → repli sur le statut historique
    "max_iterations_reached".
  - Troncature : un historique d'échec très long ne fait pas crasher le nœud.

Aucun appel LLM réel : le nœud isolé monkeypatche _configure_dspy + ChainOfThought ;
le workflow E2E monkeypatche tous les nœuds (pattern de test_checkpoint.py).
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from graph_orchestrator.dspy_nodes import execute_escalation_node
from graph_orchestrator.models import ArchitectOutput, ArchitectTask, CodeJudgeOutput, EscalationOutput
from graph_orchestrator.workflows import run_coding_workflow


# ==========================================
# 1. Nœud DSPy isolé (mock ChainOfThought, 0 réseau)
# ==========================================

@pytest.fixture
def mock_settings():
    """Settings mocké — les champs de troncature DOIVENT être des int réels
    (sinon truncate_output crash). Même convention que test_dspy_nodes.py."""
    settings = MagicMock()
    settings.fast_model_id = "mock-fast-model"
    settings.reasoning_model_id = "mock-reasoning-model"
    settings.reasoning_no_think_model_id = "mock-reasoning-model"
    settings.local_api_base = "http://localhost:11434/v1"
    
    settings.fast_spec = MagicMock(backend="external", model="mock-fast-model", api_base="http://localhost:11434/v1", api_key="sk-mock")
    settings.reasoning_spec = MagicMock(backend="external", model="mock-reasoning-model", api_base="http://localhost:11434/v1", api_key="sk-mock")
    settings.no_think_spec = MagicMock(backend="external", model="", api_base="http://localhost:11434/v1", api_key="sk-mock")

    settings.stderr_head_lines = 20
    settings.stderr_tail_lines = 20
    settings.feedback_max_chars = 2000
    settings.llm_timeout_s = 1.0
    return settings


@patch("graph_orchestrator.dspy_nodes._configure_dspy")
@patch("graph_orchestrator.dspy_nodes.dspy.ChainOfThought")
def test_escalation_node_success(mock_cot, mock_configure, mock_settings):
    """Le nœud produit un EscalationOutput structuré (cause racine + leçon)."""
    mock_instance = MagicMock()
    mock_prediction = MagicMock()
    mock_prediction.output = EscalationOutput(
        task_id="T1",
        root_cause="Le Coder n'a jamais injecté le tri avant de marquer sorted.",
        attempted_fixes=["Réécriture du DOM", "Ajout d'un setTimeout"],
        lesson="Exiger une assertion fonctionnelle vérifiant l'état final async.",
        severity="high",
    )
    mock_instance.return_value = mock_prediction
    mock_cot.return_value = mock_instance

    subtask = {"id": "T1", "description": "Visualiseur Bubble Sort", "target_files": []}
    output, metrics = asyncio.run(execute_escalation_node(
        subtask, "[BUG] tableau non trié", mock_settings.reasoning_model_id, mock_settings
    ))

    assert output is not None
    assert output.task_id == "T1"
    assert "tri" in output.root_cause.lower()
    assert output.severity == "high"
    assert metrics is not None
    assert metrics.node == "escalation_dspy"
    assert metrics.model == "mock-reasoning-model"


@patch("graph_orchestrator.dspy_nodes._configure_dspy")
@patch("graph_orchestrator.dspy_nodes.dspy.ChainOfThought")
def test_escalation_node_graceful_failure(mock_cot, mock_configure, mock_settings):
    """Une exception LLM → (None, None), pas de crash (dégradation gracieuse).

    C'est ce qui permet au workflow de replier sur 'max_iterations_reached' si
    l'endpoint de raisonnement est indisponible."""
    mock_instance = MagicMock()
    mock_instance.side_effect = RuntimeError("LLM endpoint muet")
    mock_cot.return_value = mock_instance

    subtask = {"id": "T1", "target_files": []}
    output, metrics = asyncio.run(execute_escalation_node(
        subtask, "historique", mock_settings.reasoning_model_id, mock_settings
    ))

    assert output is None
    assert metrics is None


@patch("graph_orchestrator.dspy_nodes._configure_dspy")
@patch("graph_orchestrator.dspy_nodes.dspy.ChainOfThought")
def test_escalation_node_truncates_long_history(mock_cot, mock_configure, mock_settings):
    """Un failure_history énorme ne fait pas crasher le nœud (troncature amont)."""
    mock_instance = MagicMock()
    mock_prediction = MagicMock()
    mock_prediction.output = EscalationOutput(
        task_id="T1", root_cause="cause", attempted_fixes=[], lesson="leçon", severity="low"
    )
    mock_instance.return_value = mock_prediction
    mock_cot.return_value = mock_instance

    # Historique démesuré (50k caractères) — truncate_output borne le code lu.
    huge_history = "BUG " * 10000
    subtask = {"id": "T1", "target_files": []}
    output, metrics = asyncio.run(execute_escalation_node(
        subtask, huge_history, mock_settings.reasoning_model_id, mock_settings
    ))

    assert output is not None  # pas de crash
    # Le predictor a bien été appelé (le mock capture l'appel).
    mock_instance.assert_called_once()


@patch("graph_orchestrator.dspy_nodes._configure_dspy")
@patch("graph_orchestrator.dspy_nodes.dspy.ChainOfThought")
def test_escalation_node_empty_history(mock_cot, mock_configure, mock_settings):
    """Un failure_history vide ne plante pas (fallback texte injecté)."""
    mock_instance = MagicMock()
    mock_prediction = MagicMock()
    mock_prediction.output = EscalationOutput(
        task_id="T1", root_cause="inconnue", attempted_fixes=[], lesson="rien", severity="low"
    )
    mock_instance.return_value = mock_prediction
    mock_cot.return_value = mock_instance

    subtask = {"id": "T1", "target_files": []}
    output, _ = asyncio.run(execute_escalation_node(
        subtask, "", mock_settings.reasoning_model_id, mock_settings
    ))
    assert output is not None


# ==========================================
# 2. Branchement workflow E2E (nœuds mockés)
# ==========================================

def _seed_tasks():
    return [{
        "id": "T1",
        "content": "Crée un visualiseur Bubble Sort en HTML/JS vanilla.",
        "target_files": ["index.html"],
    }]


def _setup_workflow_mocks(monkeypatch, approve=True, escalation_output=None,
                          escalation_side_effect=None):
    """Mocke tous les nœuds du workflow. Quand approve=False, la sous-tâche épuise
    max_iterations et déclenche le nœud d'escalade (mocké ici)."""
    import graph_orchestrator.nodes as nodes_mod
    import graph_orchestrator.dspy_nodes as dspy_mod
    import graph_orchestrator.workflows as wf_mod

    monkeypatch.setattr(wf_mod, "build_fast_model", lambda s: "FAKE_FAST")
    monkeypatch.setattr(wf_mod, "build_reasoning_model", lambda s: "FAKE_REASON")

    from graph_orchestrator.models import RouterOutput, CoderOutput, SecurityOutput
    async def fake_router(content, model, s):
        return RouterOutput(language="HTML"), None
    monkeypatch.setattr(dspy_mod, "execute_router_node", fake_router)

    # F-39 : mocke le PromptRefiner pour ne pas joindre l'API LLM en test E2E.
    # Passe-through None → repli sur prompt brut (comportement historique des tests).
    async def fake_prompt_refiner(raw, model, s):
        return None, None
    monkeypatch.setattr(dspy_mod, "execute_prompt_refiner_node", fake_prompt_refiner)

    async def fake_architect(task, model, s):
        return ArchitectOutput(
            plan_id="p1", global_architecture="1 fichier",
            subtasks=[ArchitectTask(task_id="st1", description="Bubble Sort",
                                     target_files=["index.html"])],
        ), None
    monkeypatch.setattr(dspy_mod, "execute_architect_node", fake_architect)

    async def fake_coder(sub, model, s):
        return CoderOutput(task_id=sub["id"], status="success", details="code généré"), None
    monkeypatch.setattr(nodes_mod, "execute_coder_node", fake_coder)

    async def fake_tester(sub, model, s):
        return CoderOutput(task_id=sub["id"], status="success", details="tests ok"), None
    async def fake_security(sub, model, s):
        return SecurityOutput(task_id=sub["id"], is_secure=True, vulnerabilities=[]), None
    monkeypatch.setattr(nodes_mod, "execute_tester_node", fake_tester)
    monkeypatch.setattr(dspy_mod, "execute_security_reviewer_node", fake_security)

    async def fake_judge(sub, test_res, sec_res, model, s):
        return CodeJudgeOutput(
            task_id=sub["id"], is_approved=approve, final_feedback="Bug non résolu."
        ), None
    monkeypatch.setattr(dspy_mod, "execute_code_judge_node", fake_judge)

    escalation_calls = {"n": 0}

    async def fake_escalation(sub, failure_history, model, s):
        escalation_calls["n"] += 1
        if escalation_side_effect is not None:
            raise escalation_side_effect
        return escalation_output, None
    monkeypatch.setattr(dspy_mod, "execute_escalation_node", fake_escalation)

    return escalation_calls


def _settings(escalation_enabled=True):
    from graph_orchestrator.config import Settings
    return Settings(
        local_api_base="http://x/v1", local_reasoning_api_base="http://x/v1",
        local_api_key="sk", fast_model_id="m", reasoning_model_id="m",
        reasoning_max_tokens=8, fast_max_tokens=8, coder_temperature=0.2,
        llm_timeout_s=1.0, judge_confidence_threshold=0.5,
        worker_max_retries=1, adversary_count=1, adversary_threshold=0.5,
        max_iterations=3, hitl_enabled=False, hitl_nodes="synth",
        kg_path=":memory:", workflow_mode="coding", log_level="LOW",
        fresh_start=True,
        test_timeout_s=120, stderr_head_lines=20, stderr_tail_lines=20,
        feedback_max_chars=2000, escalation_enabled=escalation_enabled,
    )


class TestEscalationWorkflow:
    def test_escalation_fires_on_circuit_breaker(self, monkeypatch):
        """approve=False → 3 itérations rejetées → escalation déclenchée.

        Vérifie : status='escalated', diagnostic présent, nœud escalation appelé."""
        esc = EscalationOutput(
            task_id="st1", root_cause="tri async non attendu",
            attempted_fixes=["retry"], lesson="attendre la fin async", severity="high"
        )
        calls = _setup_workflow_mocks(monkeypatch, approve=False, escalation_output=esc)
        out, _ = asyncio.run(run_coding_workflow(_seed_tasks(), _settings()))

        result = out["final_results"][0]
        assert result["status"] == "escalated"
        assert result["diagnostic"]["root_cause"] == "tri async non attendu"
        assert calls["n"] == 1  # le nœud d'escalade a bien été invoqué une fois

    def test_escalation_persists_diagnostic_in_kg(self, monkeypatch):
        """Le diagnostic est persisté dans le KG (kind='escalation') + arêtes ESCALATES.

        On intercepte le KG via kg_path sur disque pour relire les claims après run."""
        import os, tempfile
        from graph_orchestrator.knowledge_graph import KnowledgeGraph

        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "kg_escal.db")

        esc = EscalationOutput(
            task_id="st1", root_cause="cause X", attempted_fixes=["a"],
            lesson="leçon Y", severity="medium"
        )
        _setup_workflow_mocks(monkeypatch, approve=False, escalation_output=esc)

        # Settings sur disque (le workflow ouvre son propre KG sur ce chemin).
        s = _settings()
        from dataclasses import replace
        s = replace(s, kg_path=db)

        asyncio.run(run_coding_workflow(_seed_tasks(), s))

        # Relit le KG pour vérifier la persistance.
        kg = KnowledgeGraph(db)
        claims = kg.get_claims("file:st1")
        escalation_claims = [c for c in claims if c["kind"] == "escalation"]
        refutation_claims = [c for c in claims if c["kind"] == "refutation"]

        assert len(escalation_claims) == 1, "exactement un diagnostic d'escalade persisté"
        diag = escalation_claims[0]
        assert "cause X" in diag["content"]
        assert "leçon Y" in diag["content"]
        assert len(refutation_claims) >= 1, "au moins une réfutation (le Judge a rejeté 3×)"

        # Arête ESCALATES : le diagnostic pointe vers les réfutations.
        edges = kg.conn.execute(
            "SELECT relation FROM edge WHERE src_claim_id = ?", [diag["id"]]
        ).fetchall()
        relations = [r[0] for r in edges]
        assert "ESCALATES" in relations, "le diagnostic doit être relié aux réfutations"
        kg.close()

    def test_escalation_disabled_falls_back_to_max_iterations(self, monkeypatch):
        """ESCALATION_ENABLED=False → ancien comportement, statut brut, pas de diag."""
        esc = EscalationOutput(
            task_id="st1", root_cause="x", attempted_fixes=[], lesson="y", severity="low"
        )
        _setup_workflow_mocks(monkeypatch, approve=False, escalation_output=esc)
        out, _ = asyncio.run(run_coding_workflow(_seed_tasks(), _settings(escalation_enabled=False)))

        result = out["final_results"][0]
        assert result["status"] == "max_iterations_reached"
        assert "diagnostic" not in result

    def test_escalation_node_failure_falls_back_gracefully(self, monkeypatch):
        """Si le nœud d'escalade LLM échoue → repli sur 'max_iterations_reached'.

        Garantit que la chaîne ne plante pas même si l'endpoint de raisonnement
        est indisponible au moment du post-mortem."""
        _setup_workflow_mocks(
            monkeypatch, approve=False, escalation_side_effect=RuntimeError("LLM down")
        )
        out, _ = asyncio.run(run_coding_workflow(_seed_tasks(), _settings()))

        result = out["final_results"][0]
        assert result["status"] == "max_iterations_reached"  # repli propre
        assert "diagnostic" not in result
