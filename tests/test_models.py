"""Tests des contrats de données Pydantic (validation, valeurs par défaut, contraintes)."""

import pytest
from pydantic import ValidationError

from graph_orchestrator.models import (
    FinalSynthesis,
    JudgeOutput,
    TaskAssessment,
    WorkerOutput,
)


class TestWorkerOutput:
    def test_valid_worker_output(self):
        w = WorkerOutput(task_id="t1", summary="CPU à 95%", confidence_score=0.95)
        assert w.task_id == "t1"
        assert w.confidence_score == 0.95

    def test_confidence_score_can_be_zero(self):
        w = WorkerOutput(task_id="t2", summary="ok", confidence_score=0.0)
        assert w.confidence_score == 0.0

    def test_missing_field_raises(self):
        with pytest.raises(ValidationError):
            WorkerOutput(task_id="t1", summary="x")  # confidence_score manquant

    def test_wrong_type_raises(self):
        with pytest.raises(ValidationError):
            WorkerOutput(task_id="t1", summary="x", confidence_score="pas_un_float")


class TestJudgeOutput:
    def test_valid_judge_with_assessments(self):
        j = JudgeOutput(
            is_valid=True,
            reason="tout bon",
            approved_tasks=["t1", "t2"],
            assessments=[
                TaskAssessment(task_id="t1", verdict="approved", reason="fidèle"),
                TaskAssessment(task_id="t2", verdict="approved", reason="actionnable"),
            ],
        )
        assert j.is_valid is True
        assert len(j.assessments) == 2

    def test_rejected_batch(self):
        j = JudgeOutput(
            is_valid=False,
            reason="tout rejeté",
            approved_tasks=[],
            assessments=[
                TaskAssessment(task_id="t1", verdict="rejected", reason="hallucination"),
            ],
        )
        assert j.is_valid is False
        assert j.approved_tasks == []

    def test_assessment_verdict_invalid_value_raises(self):
        with pytest.raises(ValidationError):
            TaskAssessment(task_id="t1", verdict="maybe", reason="bof")


class TestFinalSynthesis:
    def test_valid_synthesis(self):
        s = FinalSynthesis(
            global_summary="Problèmes d'infra critiques",
            key_insights=["CPU critique", "Erreurs 502"],
        )
        assert len(s.key_insights) == 2

    def test_empty_insights_allowed(self):
        s = FinalSynthesis(global_summary="RAS", key_insights=[])
        assert s.key_insights == []
