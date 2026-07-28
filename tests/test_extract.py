"""Tests de robustesse de l'extraction / validation JSON.

Couvre les formats réellement renvoyés par les petits modèles via Ollama :
dict natif, string JSON nue, bloc markdown ```json```, JSON noyé dans du texte.
"""

from graph_orchestrator.models import (
    FinalSynthesis,
    JudgeOutput,
    WorkerOutput,
    extract_and_validate,
)


class TestExtractWorkerOutput:
    def test_from_dict(self):
        result = extract_and_validate(
            {"task_id": "t1", "summary": "CPU 95%", "confidence_score": 0.9},
            WorkerOutput,
        )
        assert isinstance(result, WorkerOutput)
        assert result.task_id == "t1"

    def test_from_json_string(self):
        result = extract_and_validate(
            '{"task_id": "t1", "summary": "CPU 95%", "confidence_score": 0.9}',
            WorkerOutput,
        )
        assert isinstance(result, WorkerOutput)

    def test_from_markdown_block(self):
        result = extract_and_validate(
            'Voici le résultat:\n```json\n{"task_id": "t1", "summary": "CPU 95%", "confidence_score": 0.9}\n```',
            WorkerOutput,
        )
        assert isinstance(result, WorkerOutput)
        assert result.confidence_score == 0.9

    def test_from_json_embedded_in_text(self):
        result = extract_and_validate(
            'Analyse terminée. {"task_id": "t1", "summary": "CPU 95%", "confidence_score": 0.9} Fin.',
            WorkerOutput,
        )
        assert isinstance(result, WorkerOutput)

    def test_already_validated_passthrough(self):
        original = WorkerOutput(task_id="t1", summary="x", confidence_score=0.5)
        result = extract_and_validate(original, WorkerOutput)
        assert result is original

    def test_invalid_json_returns_none(self):
        result = extract_and_validate("ceci n'est pas du json", WorkerOutput)
        assert result is None

    def test_schema_mismatch_returns_none(self):
        # manque un champ requis
        result = extract_and_validate('{"task_id": "t1"}', WorkerOutput)
        assert result is None


class TestExtractJudgeOutput:
    def test_judge_with_assessments(self):
        raw = """```json
        {
          "is_valid": true,
          "reason": "ok",
          "approved_tasks": ["t1"],
          "assessments": [{"task_id": "t1", "verdict": "approved", "reason": "fidèle"}]
        }
        ```"""
        result = extract_and_validate(raw, JudgeOutput)
        assert isinstance(result, JudgeOutput)
        assert result.assessments[0].verdict == "approved"


class TestExtractFinalSynthesis:
    def test_synthesis_from_string(self):
        result = extract_and_validate(
            '{"global_summary": "Problèmes infra", "key_insights": ["CPU", "502"]}',
            FinalSynthesis,
        )
        assert isinstance(result, FinalSynthesis)
        assert len(result.key_insights) == 2
