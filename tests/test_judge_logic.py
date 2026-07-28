"""Tests de la logique de filtrage du Juge (approuvés / rejetés).

On teste la logique métier pure (filtrage des WorkerOutput par JudgeOutput),
SANS appel LLM — ces tests valident le contrat de données et le routage.
"""

import pytest

from graph_orchestrator.models import (
    JudgeOutput,
    TaskAssessment,
    WorkerOutput,
)


def _worker(task_id: str, score: float) -> WorkerOutput:
    return WorkerOutput(task_id=task_id, summary=f"summary {task_id}", confidence_score=score)


class TestFiltrageApprouves:
    def test_garde_uniquement_les_approuves(self):
        """La logique du runner : approved_data = [r for r in workers si r.task_id in approved]."""
        workers = [_worker("t1", 0.9), _worker("t2", 0.3), _worker("t3", 0.8)]
        verdict = JudgeOutput(
            is_valid=True,
            reason="seuil",
            approved_tasks=["t1", "t3"],
            assessments=[
                TaskAssessment(task_id="t1", verdict="approved", reason="ok"),
                TaskAssessment(task_id="t2", verdict="rejected", reason="score trop bas"),
                TaskAssessment(task_id="t3", verdict="approved", reason="ok"),
            ],
        )
        approved = [r for r in workers if r.task_id in verdict.approved_tasks]
        assert [w.task_id for w in approved] == ["t1", "t3"]

    def test_aucun_approuve(self):
        workers = [_worker("t1", 0.3)]
        verdict = JudgeOutput(
            is_valid=False,
            reason="tout rejeté",
            approved_tasks=[],
            assessments=[
                TaskAssessment(task_id="t1", verdict="rejected", reason="trop bas"),
            ],
        )
        approved = [r for r in workers if r.task_id in verdict.approved_tasks]
        assert approved == []

    def test_coharence_assessments_vs_approved_tasks(self):
        """Invariant : les task_id en verdict 'approved' doivent correspondre à approved_tasks."""
        verdict = JudgeOutput(
            is_valid=True,
            reason="ok",
            approved_tasks=["t1", "t2"],
            assessments=[
                TaskAssessment(task_id="t1", verdict="approved", reason="ok"),
                TaskAssessment(task_id="t2", verdict="approved", reason="ok"),
                TaskAssessment(task_id="t3", verdict="rejected", reason="ko"),
            ],
        )
        approved_from_assessments = {
            a.task_id for a in verdict.assessments if a.verdict == "approved"
        }
        assert approved_from_assessments == set(verdict.approved_tasks)

    def test_seuil_de_confiance_par_defaut(self):
        """Vérifie que le seuil 0.7 est bien le défaut dans la config."""
        from graph_orchestrator.config import load_settings
        # On recharge les settings sans env override (pas de .env en test).
        s = load_settings()
        assert s.judge_confidence_threshold == 0.7

    @pytest.mark.parametrize("score,expected_above_threshold", [
        (0.8, True),
        (0.7, True),  # >= seuil : inclus
        (0.69, False),
        (0.0, False),
    ])
    def test_comparaison_seuil(self, score, expected_above_threshold):
        """Logique de comparaison du seuil (inclusif à gauche)."""
        seuil = 0.7
        assert (score >= seuil) is expected_above_threshold
