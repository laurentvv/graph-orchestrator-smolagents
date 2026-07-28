"""Tests de la logique adversaire (§5 : vote à la majorité, agrégation des sceptiques).

On teste UNIQUEMENT la logique pure d'agrégation (aggregate_adversary_verdicts),
SANS appel LLM — les verdicts des sceptiques sont mockés.
"""

import pytest

from graph_orchestrator.models import AdversaryVerdict, WorkerOutput
from graph_orchestrator.nodes import aggregate_adversary_verdicts


def _w(task_id: str) -> WorkerOutput:
    return WorkerOutput(task_id=task_id, summary=f"summary {task_id}", confidence_score=0.9)


def _v(task_id: str, refuted: bool, reason="r") -> AdversaryVerdict:
    return AdversaryVerdict(task_id=task_id, refuted=refuted, reason=reason)


class TestVoteAdversaire:
    def test_aucune_refutation_tout_approuve(self):
        workers = [_w("t1"), _w("t2")]
        # 3 sceptiques, aucun ne réfute
        verdicts = [_v("t1", False), _v("t1", False), _v("t1", False),
                    _v("t2", False), _v("t2", False), _v("t2", False)]
        judge = aggregate_adversary_verdicts(verdicts, workers, adversary_count=3, threshold=0.5)
        assert judge.is_valid is True
        assert set(judge.approved_tasks) == {"t1", "t2"}

    def test_majorite_refute_rejete(self):
        workers = [_w("t1")]
        # 2/3 sceptiques réfutent => >= 1.5 => rejet
        verdicts = [_v("t1", True), _v("t1", True), _v("t1", False)]
        judge = aggregate_adversary_verdicts(verdicts, workers, adversary_count=3, threshold=0.5)
        assert judge.is_valid is False  # plus rien d'approuvé
        assert "t1" not in judge.approved_tasks
        assert judge.assessments[0].verdict == "rejected"

    def test_minorite_refute_approuve(self):
        workers = [_w("t1")]
        # 1/3 sceptique réfute => < 1.5 => approuvé
        verdicts = [_v("t1", True), _v("t1", False), _v("t1", False)]
        judge = aggregate_adversary_verdicts(verdicts, workers, adversary_count=3, threshold=0.5)
        assert judge.is_valid is True
        assert "t1" in judge.approved_tasks
        assert judge.assessments[0].verdict == "approved"

    def test_mixte_approuve_et_rejete(self):
        workers = [_w("t1"), _w("t2"), _w("t3")]
        # t1 : 0 refute, t2 : 2/3 refute (rejet), t3 : 1/3 refute (approuvé)
        verdicts = [
            _v("t1", False), _v("t1", False), _v("t1", False),
            _v("t2", True), _v("t2", True), _v("t2", False),
            _v("t3", True), _v("t3", False), _v("t3", False),
        ]
        judge = aggregate_adversary_verdicts(verdicts, workers, adversary_count=3, threshold=0.5)
        assert set(judge.approved_tasks) == {"t1", "t3"}
        verdicts_by_task = {a.task_id: a.verdict for a in judge.assessments}
        assert verdicts_by_task == {"t1": "approved", "t2": "rejected", "t3": "approved"}

    def test_seuil_strict_50_pourcent(self):
        """Avec threshold=0.5 et 3 sceptiques, il faut >= 1.5 soit >= 2 réfutations."""
        workers = [_w("t1")]
        # exactement 1/3 refute => 1 < 1.5 => approuvé
        verdicts = [_v("t1", True), _v("t1", False), _v("t1", False)]
        judge = aggregate_adversary_verdicts(verdicts, workers, adversary_count=3, threshold=0.5)
        assert judge.approved_tasks == ["t1"]

    @pytest.mark.parametrize("n,threshold,refutes,rejected", [
        (3, 0.5, 0, False),   # 0 < 1.5
        (3, 0.5, 1, False),   # 1 < 1.5
        (3, 0.5, 2, True),    # 2 >= 1.5
        (3, 0.5, 3, True),    # 3 >= 1.5
        (5, 0.5, 2, False),   # 2 < 2.5
        (5, 0.5, 3, True),    # 3 >= 2.5
        (4, 0.5, 2, True),    # 2 >= 2.0
        (4, 0.5, 1, False),   # 1 < 2.0
    ])
    def test_tableau_de_verite(self, n, threshold, refutes, rejected):
        """Table de vérité du vote pour différentes tailles de flotte et seuils."""
        workers = [_w("t1")]
        verdicts = [_v("t1", True) for _ in range(refutes)] + \
                   [_v("t1", False) for _ in range(n - refutes)]
        judge = aggregate_adversary_verdicts(verdicts, workers, adversary_count=n, threshold=threshold)
        assert ("t1" not in judge.approved_tasks) is rejected
