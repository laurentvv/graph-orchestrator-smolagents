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
import subprocess

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


# ======================================================================
# Auto-Résolution des Dépendances (F-26)
# ======================================================================
# Stratégie de test : on mocke `subprocess.run` (et `_install_module`) au niveau du
# module python_tester pour éviter d'installer de vrais packages sur le CI (réseau
# instable, lent, effet de bord). On simule des objets `CompletedProcess` avec le
# stderr/returncode attendus. La logique de dispatch (extract_missing_module) est
# testée de façon unitaire pure (0 subprocess).


from graph_orchestrator.testers import python_tester as pt


class _FakeCompletedProcess:
    """Stub minimal de subprocess.CompletedProcess (attributs lus par le runner)."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestExtractMissingModule:
    """Tests unitaires de extract_missing_module (0 subprocess, pur parsing)."""

    def test_extracts_simple_module(self):
        stderr = "Traceback...\nModuleNotFoundError: No module named 'requests'\n"
        assert pt.extract_missing_module(stderr) == "requests"

    def test_extracts_toplevel_from_submodule(self):
        """'requests.auth' → 'requests' (pip attend le top-level)."""
        stderr = "ModuleNotFoundError: No module named 'requests.auth'"
        assert pt.extract_missing_module(stderr) == "requests"

    def test_no_module_error_returns_none(self):
        """AssertionError, SyntaxError, etc. → None (pas un ModuleNotFoundError)."""
        assert pt.extract_missing_module("AssertionError: assert 1 == 2") is None
        assert pt.extract_missing_module("SyntaxError: invalid syntax") is None
        assert pt.extract_missing_module("ValueError: bad value") is None

    def test_empty_or_no_match_returns_none(self):
        assert pt.extract_missing_module("") is None
        assert pt.extract_missing_module("rien d'intéressant ici") is None

    def test_invalid_module_name_returns_none(self):
        """Défense en profondeur : un nom qui n'est pas un identifiant Python valide
        → None (jamais injecté dans la commande pip)."""
        # Cas extrême : un nom avec caractères spéciaux (injection potentielle).
        stderr = "ModuleNotFoundError: No module named 'evil; rm -rf /'"
        assert pt.extract_missing_module(stderr) is None


class TestAutoInstallBehavior:
    """Tests du branchement de l'auto-install dans PythonTestRunner.run().

    On mocke subprocess.run (et _install_module) au niveau du module pour éviter
    tout accès réseau/PyPI. Les compteurs vérifient le nombre d'appels (cap 1 retry).
    """

    def test_auto_install_retries_and_succeeds(self, tmp_path, monkeypatch):
        """1er run : ModuleNotFoundError → install mocké (succès) → 2e run : success."""
        (tmp_path / "test_x.py").write_text("def test_x(): assert True\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        # Le 1er subprocess.run (pytest) échoue avec ModuleNotFoundError ;
        # le 2e (relance après install) réussit. On retourne selon le n° d'appel.
        run_calls = {"count": 0}

        def fake_run(cmd, *a, **kw):
            run_calls["count"] += 1
            if run_calls["count"] == 1:
                return _FakeCompletedProcess(returncode=1, stderr="ModuleNotFoundError: No module named 'requests'")
            # 2e appel = relance après install → succès.
            return _FakeCompletedProcess(returncode=0, stdout="1 passed")

        monkeypatch.setattr(pt.subprocess, "run", fake_run)
        monkeypatch.setattr(pt, "_install_module", lambda m, **kw: True)  # install mockée OK

        runner = PythonTestRunner()
        out, _ = _run(runner, {"id": "t", "target_files": ["test_x.py"]}, _settings())

        assert out.status == "success"  # l'auto-install a sauvé le run
        assert "auto-install" in out.details.lower()
        assert "requests" in out.details
        assert run_calls["count"] == 2  # 1er run échec + 1 relance

    def test_auto_install_disabled_preserves_historical_behavior(self, tmp_path, monkeypatch):
        """opt-out (auto_install_deps=False) → pas d'install, failure normal."""
        (tmp_path / "test_x.py").write_text("def test_x(): assert True\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        run_calls = {"count": 0}

        def fake_run(cmd, *a, **kw):
            run_calls["count"] += 1
            return _FakeCompletedProcess(
                returncode=1, stderr="ModuleNotFoundError: No module named 'requests'"
            )

        monkeypatch.setattr(pt.subprocess, "run", fake_run)

        install_called = []
        monkeypatch.setattr(pt, "_install_module", lambda m, **kw: install_called.append(m) or True)

        runner = PythonTestRunner()
        out, _ = _run(
            runner, {"id": "t", "target_files": ["test_x.py"]},
            _settings(auto_install_deps=False),
        )

        assert out.status == "failure"  # comportement historique préservé
        assert install_called == []  # aucune install tentée
        assert run_calls["count"] == 1  # pas de relance

    def test_non_module_error_does_not_install(self, tmp_path, monkeypatch):
        """Un AssertionError (pas un ModuleNotFoundError) → pas d'install."""
        (tmp_path / "test_x.py").write_text("def test_x(): assert True\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        def fake_run(cmd, *a, **kw):
            return _FakeCompletedProcess(returncode=1, stderr="AssertionError: assert 1 == 2")

        monkeypatch.setattr(pt.subprocess, "run", fake_run)
        install_called = []
        monkeypatch.setattr(pt, "_install_module", lambda m, **kw: install_called.append(m) or True)

        runner = PythonTestRunner()
        out, _ = _run(runner, {"id": "t", "target_files": ["test_x.py"]}, _settings())

        assert out.status == "failure"
        assert install_called == []  # l'install n'est déclenchée QUE sur ModuleNotFoundError

    def test_install_failure_does_not_loop(self, tmp_path, monkeypatch):
        """Si l'install échoue (PyPI down), on NE boucle PAS (cap 1 retry)."""
        (tmp_path / "test_x.py").write_text("def test_x(): assert True\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        run_calls = {"count": 0}

        def fake_run(cmd, *a, **kw):
            run_calls["count"] += 1
            # Le 1er run échoue toujours (module absent).
            return _FakeCompletedProcess(
                returncode=1, stderr="ModuleNotFoundError: No module named 'ghostpkg'"
            )

        monkeypatch.setattr(pt.subprocess, "run", fake_run)
        # Install mockée en échec (PyPI down) → pas de relance.
        monkeypatch.setattr(pt, "_install_module", lambda m, **kw: False)

        runner = PythonTestRunner()
        out, _ = _run(runner, {"id": "t", "target_files": ["test_x.py"]}, _settings())

        assert out.status == "failure"  # échec normal
        assert "ghostpkg" in out.details
        assert "Échec" in out.details or "échec" in out.details.lower()
        # Cap anti-boucle : subprocess.run appelé 1 seule fois (pas de relance
        # puisque l'install a échoué).
        assert run_calls["count"] == 1


class TestInstallModule:
    """Tests unitaires de _install_module (contrat : jamais d'exception)."""

    def test_install_success_returns_true(self, monkeypatch):
        """pip install exit 0 → True."""
        monkeypatch.setattr(
            pt.subprocess, "run",
            lambda *a, **kw: _FakeCompletedProcess(returncode=0, stdout="Successfully installed requests"),
        )
        assert pt._install_module("requests") is True

    def test_install_failure_returns_false(self, monkeypatch):
        """pip install exit≠0 (package introuvable) → False, pas d'exception."""
        monkeypatch.setattr(
            pt.subprocess, "run",
            lambda *a, **kw: _FakeCompletedProcess(returncode=1, stderr="ERROR: No matching distribution"),
        )
        assert pt._install_module("ghostpkg") is False

    def test_install_exception_returns_false(self, monkeypatch):
        """Timeout réseau, pip absent, etc. → False, jamais d'exception propagée.

        C'est LE contrat critique : l'auto-install ne fait JAMAIS planter le run.
        Le runner appelle _install_module sans try/except car il lui fait confiance.
        """
        def boom(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="pip", timeout=1)

        monkeypatch.setattr(pt.subprocess, "run", boom)
        # Pas d'exception levée → False (absorbée par le try/except interne).
        assert pt._install_module("requests") is False
