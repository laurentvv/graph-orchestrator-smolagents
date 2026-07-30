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

    def test_no_llm_rescue_under_pytest(self, monkeypatch):
        """Sous pytest (PYTEST_CURRENT_TEST posé), le sauvetage LLM est désactivé :
        un JSON cassé retourne None SANS déclencher d'appel LLM (rapide, hors réseau).

        Ce test verrouille la correction d'une régression : le fallback DSPy hallucinait
        un objet au lieu de retourner None (modèle par défaut), et le test mettait ~6s
        (tentative de connexion Ollama) au lieu de <1s.
        """
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test (call)")
        import time
        start = time.time()
        result = extract_and_validate("ceci n'est pas du json", WorkerOutput)
        elapsed = time.time() - start
        assert result is None
        # Garde-fou perf : le court-circuit doit être quasi instantané (< 2s, alors
        # qu'une tentative LLM prendrait plusieurs secondes).
        assert elapsed < 2.0, "Le sauvetage LLM ne devrait pas être déclenché en test"


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
