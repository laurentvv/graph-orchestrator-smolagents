"""Tests du PythonTestRunner (subprocess pytest) — Priorité 2.

Le runner Python est DÉTERMINISTE : il lance pytest en subprocess, capture
stdout/stderr/exit code, et en déduit un verdict. C'est la pièce la plus
testable du cycle (pas de LLM), on valide donc les vrais cas bout-en-bout :
test qui passe (exit 0 → success), test qui échoue (exit≠0 → failure +
traceback capturé), et la troncature sur un gros échec.

On crée des mini-projets Python factices dans tmp_path (fixtures pytest).
"""

import asyncio
import os

import pytest

from graph_orchestrator.models import CoderOutput
from graph_orchestrator.testers.python_tester import PythonTestRunner


def _settings(test_timeout_s=30, **kw):
    """Construit des Settings minimaux pour le runner Python."""
    from graph_orchestrator.config import Settings
    base = dict(
        ollama_api_base="http://x/v1", ollama_reasoning_api_base="http://x/v1",
        ollama_api_key="sk", fast_model_id="m", reasoning_model_id="m",
        reasoning_max_tokens=8, fast_max_tokens=8, coder_temperature=0.2,
        llm_timeout_s=1.0, judge_confidence_threshold=0.5,
        worker_max_retries=1, adversary_count=1, adversary_threshold=0.5,
        max_iterations=3, hitl_enabled=False, hitl_nodes="synth",
        kg_path=":memory:", workflow_mode="coding", log_level="LOW",
        fresh_start=False,
        test_timeout_s=test_timeout_s,
        stderr_head_lines=20, stderr_tail_lines=20, feedback_max_chars=2000,
    )
    base.update(kw)
    return Settings(**base)


def _run(runner, task, settings):
    """Petit helper : exécute le runner (async) de façon synchrone."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(runner.run(task, model=None, settings=settings))
    finally:
        loop.close()


class TestPythonRunnerVerdicts:

    def test_passing_test_returns_success(self, tmp_path, monkeypatch):
        """Un projet avec un test qui passe → status='success'."""
        # mini-projet : 1 module + 1 test qui passe.
        (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        (tmp_path / "test_calc.py").write_text(
            "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)

        runner = PythonTestRunner()
        out, metrics = _run(runner, {"id": "t1", "target_files": ["test_calc.py"]}, _settings())

        assert out is not None
        assert out.status == "success"
        assert metrics is not None
        assert metrics.model == "pytest-subprocess"

    def test_failing_test_returns_failure_with_traceback(self, tmp_path, monkeypatch):
        """Un test qui échoue → status='failure' + l'assertion capturée dans details."""
        (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")  # bug: soustrait
        (tmp_path / "test_calc.py").write_text(
            "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)

        runner = PythonTestRunner()
        out, _ = _run(runner, {"id": "t2", "target_files": ["test_calc.py"]}, _settings())

        assert out.status == "failure"
        # L'assertion échouée doit apparaître dans le feedback.
        assert "assert" in out.details.lower() or "AssertionError".lower() in out.details.lower()

    def test_syntax_error_returns_failure(self, tmp_path, monkeypatch):
        """Une erreur de syntaxe → failure (pytest ne collectionne pas)."""
        (tmp_path / "test_bad.py").write_text("def broken(:\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        runner = PythonTestRunner()
        out, _ = _run(runner, {"id": "t3", "target_files": ["test_bad.py"]}, _settings())

        assert out.status == "failure"
        assert "error" in out.details.lower()

    def test_no_py_files_falls_back_to_dir(self, tmp_path, monkeypatch):
        """Pas de .py dans target_files → on tente le dossier courant (discovery)."""
        (tmp_path / "test_x.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        runner = PythonTestRunner()
        out, _ = _run(runner, {"id": "t4", "target_files": []}, _settings())

        assert out.status == "success"


class TestPythonRunnerTruncation:

    def test_huge_traceback_truncated(self, tmp_path, monkeypatch):
        """Un échec générant un long output → details tronqué (anti Context Overflow)."""
        # Un test qui imprime énormément + échoue : le details doit être borné.
        (tmp_path / "test_big.py").write_text(
            "def test_big():\n"
            "    for i in range(500):\n"
            "        print(f'LIGNE NUMERO {i} DE BRUIT')\n"
            "    assert False, 'echec volontaire'\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        runner = PythonTestRunner()
        # Plafond strict pour forcer la troncature.
        out, _ = _run(
            runner, {"id": "t5", "target_files": ["test_big.py"]},
            _settings(feedback_max_chars=400),
        )

        assert out.status == "failure"
        assert len(out.details) <= 600  # borne respectée (+ marge marqueur)
        assert "tronquées" in out.details  # le marqueur signale la coupure
        # La cause racine (echec volontaire) doit être conservée (en queue).
        assert "echec volontaire" in out.details


class TestPythonRunnerEdgeCases:

    def test_timeout_handled_gracefully(self, tmp_path, monkeypatch):
        """Un test qui boucle → délai dépassé, pas de fige de l'usine."""
        (tmp_path / "test_loop.py").write_text(
            "import time\n\ndef test_loop():\n    while True:\n        time.sleep(1)\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        runner = PythonTestRunner()
        out, _ = _run(runner, {"id": "t6", "target_files": ["test_loop.py"]}, _settings(test_timeout_s=5))

        assert out.status == "failure"
        assert "DÉLAI" in out.details or "délai" in out.details.lower()

    def test_returns_coderoutput_type(self, tmp_path, monkeypatch):
        """Le runner respecte le contrat commun : retourne un CoderOutput."""
        (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        runner = PythonTestRunner()
        out, _ = _run(runner, {"id": "t7", "target_files": ["test_ok.py"]}, _settings())

        assert isinstance(out, CoderOutput)
        assert out.task_id == "t7"
