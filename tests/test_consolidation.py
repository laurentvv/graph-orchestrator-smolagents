"""Tests du cycle F-68 Phase 1 : Consolidation mémoire KG + Oubli par rétention.

3 tiers (miroir test_escalation.py / test_idempotency.py) :
  Tier 1 — Applier + méthodes KG (déterministe, 0 LLM).
  Tier 2 — Nœud DSPy mocké (success, dégradation, skip sous seuil).
  Tier 3 — Workflow E2E (consolidation branchée en fin de run + prune).
"""

import asyncio
import os
import tempfile
from dataclasses import replace
from unittest.mock import MagicMock, patch


from graph_orchestrator.knowledge_graph import (
    KnowledgeGraph,
    apply_consolidation_actions,
)
from graph_orchestrator.models import (
    ArchitectOutput,
    CodeJudgeOutput,
    CoderOutput,
    ConsolidationAction,
    ConsolidationOutput,
    EscalationOutput,
    RouterOutput,
    SecurityOutput,
)
from graph_orchestrator.models import ArchitectTask


# ==========================================
# Helpers
# ==========================================

def _make_kg(tmp_path=None):
    """KG en RAM (tests rapides) ou sur disque (tests persistance)."""
    if tmp_path is not None:
        return KnowledgeGraph(str(tmp_path / "kg_consol.db"))
    return KnowledgeGraph(":memory:")


def _populate_claims(kg, entity_id, run_id, contents, kind="refutation"):
    """Peuple le KG avec N claims sur une entité pour un run."""
    kg.add_entity(entity_id, kind="file")
    ids = []
    for i, content in enumerate(contents):
        cid = kg.add_claim(
            entity_id=entity_id,
            content=content,
            kind=kind,
            confidence=0.5,
            source="test",
            run_id=run_id,
        )
        ids.append(cid)
    return ids


# ==========================================
# Tier 1 — Applier + méthodes KG (déterministe, 0 LLM)
# ==========================================

class TestApplyConsolidationActions:
    """Tests de apply_consolidation_actions (port qm, 0 LLM)."""

    def test_update_action_replaces_content(self, tmp_path):
        """UPDATE <index>: <text> remplace le contenu du claim à l'index 1-based."""
        kg = _make_kg(tmp_path)
        try:
            ids = _populate_claims(kg, "file:t1", "run1", ["claim A", "claim B"])
            numbered = [
                {"id": ids[0], "content": "claim A"},
                {"id": ids[1], "content": "claim B"},
            ]
            actions = [ConsolidationAction(kind="update", index=1, text="claim A fusionnée")]
            result = apply_consolidation_actions(kg, numbered, actions, "file:t1")
            assert result["updated"] == 1
            claims = kg.get_claims("file:t1")
            assert claims[0]["content"] == "claim A fusionnée"
        finally:
            kg.close()

    def test_delete_action_removes_claim(self, tmp_path):
        """DELETE <index> supprime le claim (cascade provenance + edges)."""
        kg = _make_kg(tmp_path)
        try:
            ids = _populate_claims(kg, "file:t1", "run1", ["claim A", "claim B"])
            numbered = [
                {"id": ids[0], "content": "claim A"},
                {"id": ids[1], "content": "claim B"},
            ]
            actions = [ConsolidationAction(kind="delete", index=2)]
            result = apply_consolidation_actions(kg, numbered, actions, "file:t1")
            assert result["deleted"] == 1
            claims = kg.get_claims("file:t1")
            assert len(claims) == 1
            assert claims[0]["content"] == "claim A"
        finally:
            kg.close()

    def test_add_action_creates_insight(self, tmp_path):
        """ADD: <text> ajoute une nouvelle claim kind='insight' source='consolidation'."""
        kg = _make_kg(tmp_path)
        try:
            ids = _populate_claims(kg, "file:t1", "run1", ["claim A"])
            numbered = [{"id": ids[0], "content": "claim A"}]
            actions = [ConsolidationAction(kind="add", text="Pattern transversal découvert")]
            result = apply_consolidation_actions(kg, numbered, actions, "file:t1", run_id="run1")
            assert result["added"] == 1
            claims = kg.get_claims("file:t1")
            insights = [c for c in claims if c["kind"] == "insight"]
            assert len(insights) == 1
            assert insights[0]["content"] == "Pattern transversal découvert"
        finally:
            kg.close()

    def test_mixed_actions(self, tmp_path):
        """Mix UPDATE + DELETE + ADD sur le même lot de claims."""
        kg = _make_kg(tmp_path)
        try:
            ids = _populate_claims(
                kg, "file:t1", "run1",
                ["dup A", "dup A (variante)", "claim C", "bruit"],
            )
            numbered = [{"id": ids[i], "content": c} for i, c in
                        enumerate(["dup A", "dup A (variante)", "claim C", "bruit"])]
            actions = [
                ConsolidationAction(kind="update", index=1, text="dup A fusionné"),
                ConsolidationAction(kind="delete", index=2),  # variante supprimée
                ConsolidationAction(kind="delete", index=4),  # bruit supprimé
                ConsolidationAction(kind="add", text="Leçon globale"),
            ]
            result = apply_consolidation_actions(kg, numbered, actions, "file:t1")
            assert result["updated"] == 1
            assert result["deleted"] == 2
            assert result["added"] == 1
            # Il reste : claim C + dup A (fusionné) + Leçon globale = 3 claims
            claims = kg.get_claims("file:t1")
            assert len(claims) == 3
        finally:
            kg.close()

    def test_index_out_of_bounds_skipped(self, tmp_path):
        """Index invalide (> N ou < 1) → skip, jamais crash (fail-open)."""
        kg = _make_kg(tmp_path)
        try:
            ids = _populate_claims(kg, "file:t1", "run1", ["claim A"])
            numbered = [{"id": ids[0], "content": "claim A"}]
            actions = [
                ConsolidationAction(kind="delete", index=99),  # hors-borne
                ConsolidationAction(kind="delete", index=0),   # hors-borne (1-based)
                ConsolidationAction(kind="update", index=99, text="x"),
            ]
            result = apply_consolidation_actions(kg, numbered, actions, "file:t1")
            assert result["deleted"] == 0
            assert result["updated"] == 0
            assert result["skipped"] == 3
            # Rien n'a bougé
            claims = kg.get_claims("file:t1")
            assert len(claims) == 1
            assert claims[0]["content"] == "claim A"
        finally:
            kg.close()

    def test_actions_as_dicts(self, tmp_path):
        """Les actions peuvent être des dicts (flexibilité) au lieu de Pydantic."""
        kg = _make_kg(tmp_path)
        try:
            ids = _populate_claims(kg, "file:t1", "run1", ["claim A"])
            numbered = [{"id": ids[0], "content": "claim A"}]
            actions = [{"kind": "update", "index": 1, "text": "via dict"}]
            result = apply_consolidation_actions(kg, numbered, actions, "file:t1")
            assert result["updated"] == 1
            assert kg.get_claims("file:t1")[0]["content"] == "via dict"
        finally:
            kg.close()

    def test_add_duplicate_is_skipped(self, tmp_path):
        """ADD d'un contenu en doublon exact (dedup_key) → skip (add_claim retourne None)."""
        kg = _make_kg(tmp_path)
        try:
            ids = _populate_claims(kg, "file:t1", "run1", ["claim A"])
            numbered = [{"id": ids[0], "content": "claim A"}]
            # ADD du MÊME contenu qu'un claim déjà ouvert → add_claim retourne None (doublon).
            actions = [ConsolidationAction(kind="add", text="claim A")]
            result = apply_consolidation_actions(kg, numbered, actions, "file:t1")
            assert result["added"] == 0
            assert result["skipped"] == 1
        finally:
            kg.close()


class TestKGConsolidationMethods:
    """Tests des nouvelles méthodes KG (update_claim_content, delete_claim,
    get_claims_by_run, get_entities_by_run, prune_old_claims)."""

    def test_update_claim_content_recalculates_dedup_key(self, tmp_path):
        """update_claim_content recalcule dedup_key (anti-réinsertion du vieux contenu)."""
        kg = _make_kg(tmp_path)
        try:
            kg.add_entity("file:t1", kind="file")
            cid = kg.add_claim("file:t1", "original", "observation", 0.5, "test", run_id="r1")
            assert cid is not None
            ok = kg.update_claim_content(cid, "modifié")
            assert ok is True
            # Le nouveau contenu peut être réinséré (dedup_key différent) — l'ancien non.
            assert kg.seen("file:t1", "modifié") is True
            assert kg.seen("file:t1", "original") is False
        finally:
            kg.close()

    def test_update_claim_content_nonexistent_returns_false(self, tmp_path):
        """update_claim_content sur un id inexistant → False (no-op)."""
        kg = _make_kg(tmp_path)
        try:
            ok = kg.update_claim_content(99999, "texte")
            assert ok is False
        finally:
            kg.close()

    def test_delete_claim_cascades_provenance_and_edges(self, tmp_path):
        """delete_claim supprime provenance + edges (src ET dst) + claim."""
        kg = _make_kg(tmp_path)
        try:
            kg.add_entity("file:t1", kind="file")
            cid1 = kg.add_claim("file:t1", "obs", "observation", 0.5, "test", run_id="r1")
            cid2 = kg.add_claim("file:t1", "ref", "refutation", 0.5, "test", run_id="r1")
            kg.add_edge(cid2, cid1, "REFUTES")
            # Vérifie qu'il y a une edge.
            edges_before = kg.conn.execute("SELECT count(*) FROM edge").fetchone()[0]
            assert edges_before == 1
            # Supprime la réfutation (src de l'edge).
            ok = kg.delete_claim(cid2)
            assert ok is True
            # L'edge a disparu (cascade).
            edges_after = kg.conn.execute("SELECT count(*) FROM edge").fetchone()[0]
            assert edges_after == 0
            # La provenance a disparu.
            prov = kg.conn.execute(
                "SELECT count(*) FROM provenance WHERE claim_id = ?", [cid2]
            ).fetchone()[0]
            assert prov == 0
            # La claim a disparu.
            claims = kg.get_claims("file:t1")
            assert len(claims) == 1
            assert claims[0]["content"] == "obs"
        finally:
            kg.close()

    def test_delete_claim_nonexistent_returns_false(self, tmp_path):
        """delete_claim sur un id inexistant → False, jamais d'exception."""
        kg = _make_kg(tmp_path)
        try:
            ok = kg.delete_claim(99999)
            assert ok is False
        finally:
            kg.close()

    def test_get_claims_by_run(self, tmp_path):
        """get_claims_by_run retourne les claims via JOIN provenance.run_id."""
        kg = _make_kg(tmp_path)
        try:
            _populate_claims(kg, "file:t1", "run_A", ["a1", "a2"])
            _populate_claims(kg, "file:t2", "run_A", ["b1"])
            _populate_claims(kg, "file:t3", "run_B", ["c1"])
            claims_a = kg.get_claims_by_run("run_A")
            claims_b = kg.get_claims_by_run("run_B")
            assert len(claims_a) == 3
            assert len(claims_b) == 1
            entities_a = {c["entity_id"] for c in claims_a}
            assert entities_a == {"file:t1", "file:t2"}
        finally:
            kg.close()

    def test_get_entities_by_run(self, tmp_path):
        """get_entities_by_run retourne les entity_id distincts d'un run."""
        kg = _make_kg(tmp_path)
        try:
            _populate_claims(kg, "file:t1", "run_A", ["a1"])
            _populate_claims(kg, "file:t2", "run_A", ["b1", "b2"])
            entities = kg.get_entities_by_run("run_A")
            assert set(entities) == {"file:t1", "file:t2"}
            assert kg.get_entities_by_run("run_X") == []
        finally:
            kg.close()

    def test_prune_old_claims_by_age(self, tmp_path):
        """prune_old_claims supprime les claims > N jours."""
        kg = _make_kg(tmp_path)
        try:
            kg.add_entity("file:t1", kind="file")
            kg.add_claim("file:t1", "récent", "observation", 0.5, "test", run_id="r1")
            # Insère un claim ancien en bidouillant created_at via SQL direct.
            cid_old = kg.add_claim("file:t1", "ancien", "observation", 0.5, "test", run_id="r1")
            kg.conn.execute(
                "UPDATE claim SET created_at = ? WHERE id = ?",
                ["2020-01-01 00:00:00", cid_old],
            )
            kg.conn.commit()
            pruned = kg.prune_old_claims(retention_days=30)
            assert pruned == 1
            claims = kg.get_claims("file:t1")
            assert len(claims) == 1
            assert claims[0]["content"] == "récent"
        finally:
            kg.close()

    def test_prune_preserves_escalation_and_insight(self, tmp_path):
        """prune_old_claims préserve escalation + insight (leçons durables)."""
        kg = _make_kg(tmp_path)
        try:
            kg.add_entity("file:t1", kind="file")
            cid_ref = kg.add_claim("file:t1", "refuté", "refutation", 0.5, "test", run_id="r1")
            cid_esc = kg.add_claim("file:t1", "diag", "escalation", 0.5, "test", run_id="r1")
            cid_ins = kg.add_claim("file:t1", "leçon", "insight", 0.5, "test", run_id="r1")
            # Tous anciens.
            for cid in [cid_ref, cid_esc, cid_ins]:
                kg.conn.execute(
                    "UPDATE claim SET created_at = ? WHERE id = ?",
                    ["2020-01-01 00:00:00", cid],
                )
            kg.conn.commit()
            pruned = kg.prune_old_claims(retention_days=30)
            assert pruned == 1  # seulement la réfutation
            claims = kg.get_claims("file:t1")
            kinds = {c["kind"] for c in claims}
            assert kinds == {"escalation", "insight"}
        finally:
            kg.close()

    def test_prune_nothing_to_delete(self, tmp_path):
        """prune_old_claims avec retention très courte et claims récents → 0 supprimé."""
        kg = _make_kg(tmp_path)
        try:
            _populate_claims(kg, "file:t1", "r1", ["récent"])
            pruned = kg.prune_old_claims(retention_days=365 * 10)
            assert pruned == 0
        finally:
            kg.close()


# ==========================================
# Tier 2 — Nœud DSPy mocké (miroir test_escalation.py)
# ==========================================

def _mock_settings():
    """Settings mocké pour les tests du nœud (pas d'appel réseau)."""
    ms = MagicMock()
    ms.memory_consolidation_enabled = True
    ms.memory_consolidation_after = 5
    ms.no_think_spec = MagicMock()
    ms.no_think_spec.model = "mock-model"
    ms.stderr_head_lines = 20
    ms.stderr_tail_lines = 20
    ms.feedback_max_chars = 2000
    ms.llm_timeout_s = 1.0
    ms.local_api_base = "http://x/v1"
    ms.local_reasoning_api_base = "http://x/v1"
    ms.local_api_key = "sk"
    ms.reasoning_model_id = "m"
    return ms


class TestConsolidationNode:
    """Tests du nœud execute_consolidation_node avec DSPy mocké."""

    def test_consolidation_applies_actions_to_kg(self, tmp_path):
        """Le nœud émet des actions et l'applier les applique au KG (claims réduits)."""
        from graph_orchestrator.dspy_nodes import execute_consolidation_node

        kg = _make_kg(tmp_path)
        try:
            # 6 claims redondants sur une entité (au-dessus du seuil 5).
            contents = [f"Bug: SyntaxError ligne 5 (variante {i})" for i in range(6)]
            _populate_claims(kg, "file:t1", "run1", contents)

            cons_output = ConsolidationOutput(
                entity_id="file:t1",
                actions=[
                    ConsolidationAction(kind="update", index=1, text="SyntaxError ligne 5 (fusionné)"),
                    ConsolidationAction(kind="delete", index=2),
                    ConsolidationAction(kind="delete", index=3),
                    ConsolidationAction(kind="delete", index=4),
                    ConsolidationAction(kind="delete", index=5),
                    ConsolidationAction(kind="delete", index=6),
                ],
                summary="Fusion de 6 doublons en 1.",
            )

            with patch("graph_orchestrator.dspy_nodes._configure_dspy"), \
                 patch("graph_orchestrator.dspy_nodes.dspy.ChainOfThought") as mock_cot:
                mock_cot.return_value = MagicMock()
                mock_cot.return_value.return_value = MagicMock(output=cons_output)
                with patch("graph_orchestrator.dspy_nodes.model_lifecycle") as mock_ml:
                    mock_ml.return_value.__enter__ = lambda s: MagicMock()
                    mock_ml.return_value.__exit__ = lambda s, *a: None
                    summary, metrics = asyncio.run(
                        execute_consolidation_node(kg, "run1", _mock_settings())
                    )

            assert summary is not None
            assert "file:t1" in summary
            assert summary["file:t1"]["deleted"] == 5
            assert summary["file:t1"]["updated"] == 1
            claims = kg.get_claims("file:t1")
            assert len(claims) == 1
            assert "fusionné" in claims[0]["content"]
        finally:
            kg.close()

    def test_consolidation_skips_entities_below_threshold(self, tmp_path):
        """Entité avec < memory_consolidation_after claims → skip (pas d'appel LLM)."""
        from graph_orchestrator.dspy_nodes import execute_consolidation_node

        kg = _make_kg(tmp_path)
        try:
            # Seulement 2 claims (sous le seuil 5).
            _populate_claims(kg, "file:t1", "run1", ["a", "b"])

            with patch("graph_orchestrator.dspy_nodes._configure_dspy") as mock_cfg:
                summary, metrics = asyncio.run(
                    execute_consolidation_node(kg, "run1", _mock_settings())
                )
                # Pas d'appel LLM.
                assert mock_cfg.call_count == 0
            assert summary is None
            # KG intact.
            assert len(kg.get_claims("file:t1")) == 2
        finally:
            kg.close()

    def test_consolidation_llm_failure_leaves_kg_intact(self, tmp_path):
        """Si le LVM est down →KG intact, dégradation gracieuse (None, None)."""
        from graph_orchestrator.dspy_nodes import execute_consolidation_node

        kg = _make_kg(tmp_path)
        try:
            contents = [f"claim {i}" for i in range(6)]
            _populate_claims(kg, "file:t1", "run1", contents)

            with patch("graph_orchestrator.dspy_nodes._configure_dspy"), \
                 patch("graph_orchestrator.dspy_nodes.dspy.ChainOfThought") as mock_cot:
                # Le predictor (instance ChainOfThought) est appelé via
                # asyncio.to_thread(predictor, **kwargs) dans _run_dspy_node.
                # Pour faire lever une exception, c'est l'INSTANCE (mock_cot.return_value)
                # qui doit avoir le side_effect, pas son return_value.
                mock_cot.return_value = MagicMock(side_effect=RuntimeError("LLM down"))
                with patch("graph_orchestrator.dspy_nodes.model_lifecycle") as mock_ml:
                    mock_ml.return_value.__enter__ = lambda s: MagicMock()
                    mock_ml.return_value.__exit__ = lambda s, *a: None
                    summary, metrics = asyncio.run(
                        execute_consolidation_node(kg, "run1", _mock_settings())
                    )
            # Dégradation : summary None (aucune entité n'a abouti), KG intact.
            assert summary is None
            assert len(kg.get_claims("file:t1")) == 6
        finally:
            kg.close()

    def test_consolidation_disabled_returns_none(self, tmp_path):
        """memory_consolidation_enabled=False → retour immédiat (None, None)."""
        from graph_orchestrator.dspy_nodes import execute_consolidation_node

        kg = _make_kg(tmp_path)
        try:
            ms = _mock_settings()
            ms.memory_consolidation_enabled = False
            summary, metrics = asyncio.run(
                execute_consolidation_node(kg, "run1", ms)
            )
            assert summary is None
            assert metrics is None
        finally:
            kg.close()

    def test_consolidation_no_entities_returns_none(self, tmp_path):
        """Run sans entités → retour (None, None) propre."""
        from graph_orchestrator.dspy_nodes import execute_consolidation_node

        kg = _make_kg(tmp_path)
        try:
            summary, metrics = asyncio.run(
                execute_consolidation_node(kg, "run_sans_claims", _mock_settings())
            )
            assert summary is None
            assert metrics is None
        finally:
            kg.close()


# ==========================================
# Tier 3 — Workflow E2E (consolidation branchée en fin de run)
# ==========================================

def _seed_tasks():
    return [{
        "id": "T1",
        "content": "Crée un visualiseur Bubble Sort en HTML/JS vanilla.",
        "target_files": ["index.html"],
    }]


def _setup_workflow_mocks_consolidation(monkeypatch, approve=True):
    """Mocke tous les nœuds du workflow, incluant la consolidation."""
    import graph_orchestrator.nodes as nodes_mod
    import graph_orchestrator.dspy_nodes as dspy_mod
    import graph_orchestrator.workflows as wf_mod

    monkeypatch.setattr(wf_mod, "build_fast_model", lambda s: "FAKE_FAST")
    monkeypatch.setattr(wf_mod, "build_reasoning_model", lambda s: "FAKE_REASON")

    async def fake_router(content, model, s):
        return RouterOutput(language="HTML"), None
    monkeypatch.setattr(dspy_mod, "execute_router_node", fake_router)

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

    async def fake_escalation(sub, failure_history, model, s):
        return EscalationOutput(
            task_id=sub["id"], root_cause="x", attempted_fixes=[], lesson="y", severity="low"
        ), None
    monkeypatch.setattr(dspy_mod, "execute_escalation_node", fake_escalation)

    consolidation_calls = {"n": 0}

    async def fake_consolidation(kg, run_id, s):
        consolidation_calls["n"] += 1
        return {"file:st1": {"updated": 0, "deleted": 0, "added": 0, "skipped": 0}}, None
    monkeypatch.setattr(dspy_mod, "execute_consolidation_node", fake_consolidation)

    return consolidation_calls


def _settings(consolidation_enabled=True):
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
        feedback_max_chars=2000, escalation_enabled=True,
        memory_consolidation_enabled=consolidation_enabled,
    )


class TestConsolidationWorkflow:
    def test_consolidation_called_at_end_of_run(self, monkeypatch):
        """La consolidation est appelée en fin de run (même si sous-tâche approuvée)."""
        calls = _setup_workflow_mocks_consolidation(monkeypatch, approve=True)
        from graph_orchestrator.workflows import run_coding_workflow
        out, _ = asyncio.run(run_coding_workflow(_seed_tasks(), _settings()))
        assert out is not None
        assert calls["n"] == 1, "le nœud de consolidation doit être appelé une fois en fin de run"

    def test_consolidation_disabled_not_called(self, monkeypatch):
        """memory_consolidation_enabled=False → consolidation non appelée, prune quand même."""
        calls = _setup_workflow_mocks_consolidation(monkeypatch, approve=True)
        from graph_orchestrator.workflows import run_coding_workflow
        s = replace(_settings(consolidation_enabled=False), memory_consolidation_enabled=False)
        out, _ = asyncio.run(run_coding_workflow(_seed_tasks(), s))
        assert out is not None
        assert calls["n"] == 0, "consolidation ne doit pas être appelée si désactivée"

    def test_prune_runs_even_if_consolidation_disabled(self, monkeypatch):
        """Le prune_old_claims tourne toujours (même si consolidation désactivée).

        Vérifie qu'une claim ancienne est prunée après le run."""
        _setup_workflow_mocks_consolidation(monkeypatch, approve=True)

        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "kg_prune.db")
        from graph_orchestrator.knowledge_graph import KnowledgeGraph
        # Pré-peuple le KG avec une claim ancienne sur disque avant le run.
        pre_kg = KnowledgeGraph(db)
        pre_kg.add_entity("file:old", kind="file")
        old_cid = pre_kg.add_claim("file:old", "ancien refuté", "refutation", 0.5, "test", run_id="old_run")
        pre_kg.conn.execute(
            "UPDATE claim SET created_at = ? WHERE id = ?",
            ["2020-01-01 00:00:00", old_cid],
        )
        pre_kg.conn.commit()
        pre_kg.close()

        from graph_orchestrator.workflows import run_coding_workflow
        s = replace(_settings(consolidation_enabled=False), kg_path=db, memory_retention_days=30)
        asyncio.run(run_coding_workflow(_seed_tasks(), s))

        # Relit le KG : la claim ancienne doit avoir été prunée.
        post_kg = KnowledgeGraph(db)
        old_claims = post_kg.get_claims("file:old")
        post_kg.close()
        assert len(old_claims) == 0, "la claim ancienne doit être prunée par rétention"
