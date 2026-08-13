"""Tests unitaires de ``js_utils.run_node_check`` (F-72 — Prompt Offloading).

Vérifie le partage DRY du ``node --check`` (extrait de ``static_tester.py``,
consommé par l'outil ``check_js_syntax`` du Coder + le Static Tester Tier 1a).

Stratégie = ``test_static_tester.py`` : vrais appels subprocess pour les cas
nominaux (syntaxe OK / syntax error), mock ``subprocess.run`` pour les cas de
dégradation (node absent, SubprocessError). Skip conditionnel si ``node`` n'est
pas installé (robustesse CI).
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from graph_orchestrator import js_utils

_NODE_AVAILABLE = shutil.which("node") is not None
node_required = pytest.mark.skipif(
    not _NODE_AVAILABLE, reason="node.js non installé sur cette machine"
)


# ==========================================
# Constante partagée
# ==========================================
def test_max_js_chars_constant_preserved():
    """La constante MAX_JS_CHARS migre fidèlement depuis static_tester (200_000)."""
    assert js_utils.MAX_JS_CHARS == 200_000


# ==========================================
# run_node_check — cas nominaux (vrai node si dispo)
# ==========================================
@node_required
def test_run_node_check_valid_syntax():
    """JS valide → exit code 0."""
    code, stderr = js_utils.run_node_check("const x = 1 + 2; console.log(x);")
    assert code == 0, f"JS valide devrait passer node --check. stderr={stderr!r}"


@node_required
def test_run_node_check_syntax_error():
    """JS invalide → exit code != 0, stderr mentionne une erreur de syntaxe."""
    code, stderr = js_utils.run_node_check("const x = 1 + ;")  # expression incomplète
    assert code != 0, "JS invalide devrait échouer node --check."
    assert (
        "SyntaxError" in stderr or "error" in stderr.lower()
    ), f"stderr devrait mentionner une erreur. stderr={stderr!r}"


# ==========================================
# run_node_check — dégradations (mock subprocess, toujours actifs)
# ==========================================
def test_run_node_check_node_absent(monkeypatch):
    """node absent du PATH (FileNotFoundError) → dégradation (0, ""), pas d'exception."""

    def raise_fnf(*a, **kw):
        raise FileNotFoundError("node: command not found")

    monkeypatch.setattr(subprocess, "run", raise_fnf)
    code, stderr = js_utils.run_node_check("const x = 1;")
    assert code == 0, "node absent → retour (0, '') pour skip silencieux."
    assert stderr == "", "node absent → stderr vide."


def test_run_node_check_subprocess_error(monkeypatch):
    """subprocess.SubprocessError → (1, ""), pas d'exception remontée."""

    def raise_subproc(*a, **kw):
        raise subprocess.SubprocessError("timeout")

    monkeypatch.setattr(subprocess, "run", raise_subproc)
    code, stderr = js_utils.run_node_check("const x = 1;")
    assert code == 1, "SubprocessError → code 1 (échec sans exception)."
    assert stderr == "", "SubprocessError → stderr vide."
