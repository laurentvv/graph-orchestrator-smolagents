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


# ==========================================
# Extraction de blocs HTML
# ==========================================
def test_extract_script_blocks():
    html = """<!DOCTYPE html>
<html>
<head>
    <script type="application/json">{"data": 123}</script>
    <script>
        console.log("head script");
    </script>
</head>
<body>
    <script type="text/javascript">
        const x = 1;
    </script>
</body>
</html>"""
    scripts = js_utils.extract_script_blocks(html)
    assert len(scripts) == 2
    assert "console.log" in scripts[0]["code"]
    assert "const x = 1" in scripts[1]["code"]


def test_extract_style_blocks():
    html = """<!DOCTYPE html>
<html>
<head>
    <style>
        body { margin: 0; }
    </style>
</head>
</html>"""
    styles = js_utils.extract_style_blocks(html)
    assert len(styles) == 1
    assert "margin: 0" in styles[0]["code"]


# ==========================================
# Détection de fuites de syntaxe Python
# ==========================================
def test_detect_python_syntax_tuples():
    js = "const kicks = [(0,0), (1,0), (-1,0), (0,-1)];"
    errors = js_utils.detect_python_syntax_in_js(js)
    assert len(errors) == 1
    assert "Tuples Python" in errors[0]
    assert "[[x, y], ...]" in errors[0]


def test_detect_python_syntax_keywords():
    js = """
    let a = None;
    if (a === True) {
        def foo() {
            print("test");
        }
    }
    """
    errors = js_utils.detect_python_syntax_in_js(js)
    assert any("None" in e for e in errors)
    assert any("True" in e for e in errors)
    assert any("def" in e for e in errors)
    assert any("print" in e for e in errors)


def test_has_use_strict():
    assert js_utils.has_use_strict("'use strict';\nconst x = 1;")
    assert js_utils.has_use_strict('"use strict";\nconst x = 1;')
    assert not js_utils.has_use_strict("const x = 1;")


def test_detect_const_mutation():
    """Détecte les variables const incrémentées ou réassignées."""
    # 1. Incrément sur const (le bug du run Tetris)
    js_bug = """
    function draw() {
        const ghostY = currentPiece.y;
        while (!collide()) {
            ghostY++;
        }
    }
    """
    errors = js_utils.detect_const_mutation_in_js(js_bug)
    assert len(errors) == 1
    assert "ghostY" in errors[0]
    assert "ghostY++" in errors[0]
    assert "TypeError: Assignment to constant variable" in errors[0]

    # 2. Assignation composée sur const
    js_assign = """
    function score() {
        const total = 0;
        total += 100;
    }
    """
    errors_assign = js_utils.detect_const_mutation_in_js(js_assign)
    assert len(errors_assign) == 1
    assert "total" in errors_assign[0]

    # 3. Variable let -> aucune erreur
    js_valid = """
    function draw() {
        let ghostY = currentPiece.y;
        while (ghostY < ROWS && !collide(ghostY)) {
            ghostY++;
        }
    }
    """
    assert len(js_utils.detect_const_mutation_in_js(js_valid)) == 0


def test_detect_unbounded_while():
    """Vérifie la détection des boucles while dont la condition ne peut jamais changer.

    Goulot run 2026-08-21_1531 : l'ancienne logique (toute variable incrémentée
    absente de la condition = flag) produisait un faux positif sur le bubble
    sort canonique → 6+ réécritures du même bloc par le Coder. Nouvelle logique
    conservative : flag uniquement si AUCUNE variable de la condition n'est
    mutée dans le corps (assignation OU incrément), ou condition constante.
    """
    # 1. Boucle potentiellement infinie (Tetris) : la condition ne dépend d'aucune
    # variable mutée dans le corps (ghostY++ est invisible de collide(...))
    js_infinite = """
    function draw() {
        let ghostY = currentPiece.y;
        while (!collide({ x: 0, y: 1 })) {
            ghostY++;
        }
    }
    """
    errs = js_utils.detect_unbounded_while_in_js(js_infinite, start_line=10)
    assert len(errs) == 1
    assert "Ligne 13" in errs[0]
    assert "Boucle infinie JS" in errs[0]

    # 2. Boucle bornée valide : ghostY apparaît dans la condition
    js_bounded = """
    function draw() {
        let ghostY = currentPiece.y;
        while (ghostY < ROWS && !collideAt(shape, x, ghostY + 1)) {
            ghostY++;
        }
    }
    """
    assert len(js_utils.detect_unbounded_while_in_js(js_bounded)) == 0

    # 3. Bubble sort canonique (le faux positif du run 2026-08-21_1531) :
    # `swapped` (assigné =) et `comparisons` (++) conditionnent la sortie.
    js_bubble = """
    const maxIterations = 10000;
    let swapped = true, comparisons = 0, i = 0;
    while (swapped && comparisons < maxIterations) {
        swapped = false;
        for (let j = 0; j < 10 - i; j++) { comparisons++; }
        i++;
    }
    """
    assert js_utils.detect_unbounded_while_in_js(js_bubble) == []

    # 4. while(true) + incrément : condition constante → flag.
    assert len(js_utils.detect_unbounded_while_in_js("while (true) { ghostY++; }")) == 1

    # 5. Sortie par assignation simple : PAS de flag.
    js_assign = "let run = true; while (run) { doWork(); run = false; }"
    assert js_utils.detect_unbounded_while_in_js(js_assign) == []

