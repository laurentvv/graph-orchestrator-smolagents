"""Tests unitaires du Linter (F-30, Shift Left).

Déterministes, 0 LLM, 0 réseau. Couvre le contrat complet :
- Détection multi-langue (Python/HTML/CSS/JS/TS/TSX).
- Complémentarité tree-sitter (SyntaxError) + py_compile (IndentationError Python).
- Vérifs structurelles HTML (le bug dashboard : contenu après </html>).
- Dégradation gracieuse (extension inconnue, fichier absent, fichier illisible).
- Le nœud execute_linter_node (verdict binaire + détails exploitables).
"""

from graph_orchestrator.linter import (
    execute_linter_node,
    lint_file,
    _detect_language,
)


def _write(tmp_path, name, content):
    """Helper : écrit un fichier de test et retourne son chemin."""
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return str(f)


# ==========================================
# Détection de langue (extension → langage)
# ==========================================
def test_detect_language_extensions():
    assert _detect_language("foo.py") == "python"
    assert _detect_language("foo.html") == "html"
    assert _detect_language("foo.htm") == "html"
    assert _detect_language("foo.css") == "css"
    assert _detect_language("foo.js") == "javascript"
    assert _detect_language("foo.mjs") == "javascript"
    assert _detect_language("foo.ts") == "typescript"
    assert _detect_language("foo.tsx") == "tsx"
    assert _detect_language("foo.txt") == "unknown"
    assert _detect_language("foo.md") == "unknown"
    assert _detect_language("noext") == "unknown"
    # Insensible à la casse
    assert _detect_language("FOO.PY") == "python"


# ==========================================
# Python : tree-sitter + py_compile
# ==========================================
def test_python_valid(tmp_path):
    p = _write(tmp_path, "ok.py", "def f():\n    return 1\n")
    r = lint_file(p)
    assert r.language == "python"
    assert r.is_valid


def test_python_syntax_error(tmp_path):
    """SyntaxError détectée par tree-sitter + py_compile."""
    p = _write(tmp_path, "bad.py", "def f(:\n    pass\n")
    r = lint_file(p)
    assert r.language == "python"
    assert not r.is_valid
    assert any("tree-sitter" in e or "py_compile" in e for e in r.errors)


def test_python_indentation_error(tmp_path):
    """IndentationError — le POINT NOIR. tree-sitter le raterait seul, py_compile le voit."""
    p = _write(tmp_path, "indent.py", "def f():\nreturn 1\n")
    r = lint_file(p)
    assert r.language == "python"
    assert not r.is_valid
    assert any("py_compile" in e and "IndentationError" in e for e in r.errors)


def test_python_unclosed_string(tmp_path):
    """String non fermée — le bug 'triple-quote' observé au step 6 du run CodeAgent."""
    p = _write(tmp_path, "unclosed.py", 'x = """debut\nfin sans fermer')
    r = lint_file(p)
    assert not r.is_valid


# ==========================================
# HTML : vérifs structurelles (le bug dashboard)
# ==========================================
def test_html_valid(tmp_path):
    p = _write(tmp_path, "ok.html", "<!DOCTYPE html>\n<html><head></head><body><p>hi</p></body></html>\n")
    r = lint_file(p)
    assert r.language == "html"
    assert r.is_valid


def test_html_content_after_close(tmp_path):
    """Le bug EXACT du dashboard cassé : contenu appendé après </html>."""
    p = _write(tmp_path, "casse.html", "<!DOCTYPE html><html><head></head><body></body></html>\n<style>body{margin:0}</style>\n")
    r = lint_file(p)
    assert r.language == "html"
    assert not r.is_valid
    # Le feedback doit mentionner le contenu après </html> (exploitable par le Coder)
    assert any("APRÈS </html>" in e or "APRES" in e.upper() for e in r.errors)


def test_html_unbalanced_tags(tmp_path):
    """Balise body non fermée."""
    p = _write(tmp_path, "unbal.html", "<!DOCTYPE html><html><head></head><body><p>hi</p></html>")
    r = lint_file(p)
    assert not r.is_valid
    assert any("body" in e.lower() and ("déséquilibr" in e.lower() or "desequilibr" in e.lower()) for e in r.errors)


# ==========================================
# CSS / JS / TS / TSX : tree-sitter
# ==========================================
def test_css_valid_and_invalid(tmp_path):
    ok = _write(tmp_path, "ok.css", "body { margin: 0; padding: 1rem; }")
    bad = _write(tmp_path, "bad.css", "body { margin: 0 ")
    assert lint_file(ok).is_valid
    assert not lint_file(bad).is_valid


def test_javascript_valid_and_invalid(tmp_path):
    ok = _write(tmp_path, "ok.js", "function f() {\n  return 1;\n}\n")
    bad = _write(tmp_path, "bad.js", "function f( {\n  return 1;\n}\n")
    assert lint_file(ok).is_valid
    assert not lint_file(bad).is_valid


def test_typescript_valid_and_invalid(tmp_path):
    ok = _write(tmp_path, "ok.ts", "const x: number = 1;\nfunction f(a: string): void {}\n")
    bad = _write(tmp_path, "bad.ts", "const x number = 1;\nfunction f(\n")
    assert lint_file(ok).is_valid
    assert not lint_file(bad).is_valid


def test_tsx_valid_and_invalid(tmp_path):
    ok = _write(tmp_path, "ok.tsx", "const App = () => <div>hello</div>;\n")
    bad = _write(tmp_path, "bad.tsx", "const App = () => <div>hello;\n")
    assert lint_file(ok).is_valid
    assert not lint_file(bad).is_valid


# ==========================================
# Dégradation gracieuse
# ==========================================
def test_unknown_extension_is_valid(tmp_path):
    """Extension non supportée → ne valide pas négativement (pas de faux positif)."""
    p = _write(tmp_path, "notes.txt", "du texte quelconque")
    r = lint_file(p)
    assert r.language == "unknown"
    assert r.is_valid  # on laisse le Tester/Judge juger


def test_missing_file_is_valid(tmp_path):
    """Fichier absent → valide (défense : ne pas bloquer le workflow, le Coder peut être en
    cours ou avoir écrit sous un autre chemin) MAIS avertissement non bloquant (F-56/P14-E)
    pour l'observabilité — détecte l'échec silencieux du Coder (success sans write_file)."""
    r = lint_file(str(tmp_path / "absent.py"))
    assert r.language == "missing"
    assert r.is_valid  # non bloquant (conserve la défense historique, pas de court-circuit)
    assert r.errors  # F-56 : avertissement remonté pour l'observabilité
    assert any("non trouvé" in e.lower() or "absent" in e.lower() or "créé" in e.lower()
               for e in r.errors)


def test_missing_file_warning_in_details(tmp_path):
    """F-56/P14-E : le nœud execute_linter_node remonte les fichiers absents comme
    AVERTISSEMENTS non bloquants dans details (statut reste success). Permet au Judge/humain
    de voir qu'un fichier attendu n'a pas été créé, sans court-circuiter le Tester."""
    ok = _write(tmp_path, "ok.py", "x = 1\n")
    absent = str(tmp_path / "absent.html")
    subtask = {"id": "st1", "target_files": [ok, absent]}
    res, _ = execute_linter_node(subtask, settings=None)
    assert res.status == "success"  # non bloquant
    assert "AVERTISSEMENTS" in res.details  # mais visible
    assert "absent.html" in res.details


# ==========================================
# Nœud execute_linter_node
# ==========================================
def test_execute_linter_node_success(tmp_path):
    """Tous les fichiers valides → CoderOutput status='success'."""
    p = _write(tmp_path, "ok.py", "x = 1\n")
    subtask = {"id": "st1", "target_files": [p]}
    res, metrics = execute_linter_node(subtask, settings=None)
    assert res.status == "success"
    assert metrics.model == "tree-sitter-linter"
    assert metrics.node == "linter"
    assert metrics.input_tokens == 0  # 0 LLM


def test_execute_linter_node_failure_with_exploitable_feedback(tmp_path):
    """Au moins un fichier invalide → status='failure' + détails exploitables par le Coder."""
    ok = _write(tmp_path, "ok.py", "x = 1\n")
    bad = _write(tmp_path, "bad.py", "def f(:\n    pass\n")
    subtask = {"id": "st1", "target_files": [ok, bad]}
    res, metrics = execute_linter_node(subtask, settings=None)
    assert res.status == "failure"
    assert "bad.py" in res.details  # le Coder sait QUEL fichier corriger
    assert "tree-sitter" in res.details or "py_compile" in res.details  # et QUELLE erreur


def test_execute_linter_node_empty_targets(tmp_path):
    """Pas de fichiers cibles → success (rien à linter, ne bloque pas)."""
    res, metrics = execute_linter_node({"id": "st1", "target_files": []}, settings=None)
    assert res.status == "success"


# ==========================================
# HTML Inline JS / CSS & Détection Fuites Python
# ==========================================
def test_html_inline_js_python_tuples(tmp_path):
    """HTML contenant du JS avec des tuples Python [(0,0), ...] → rejeté."""
    html = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <script>
        const kicks = [(0,0), (1,0), (-1,0)];
    </script>
</body>
</html>"""
    p = _write(tmp_path, "index.html", html)
    r = lint_file(p)
    assert r.language == "html"
    assert not r.is_valid
    assert any("Tuples Python" in e for e in r.errors)


def test_html_inline_js_valid(tmp_path):
    """HTML contenant du JS vanilla valide → accepté."""
    html = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <script>
        'use strict';
        const kicks = [[0, 0], [1, 0], [-1, 0]];
        console.log(kicks.length);
    </script>
</body>
</html>"""
    p = _write(tmp_path, "index.html", html)
    r = lint_file(p)
    assert r.language == "html"
    assert r.is_valid
    assert len(r.errors) == 0


def test_js_python_keywords_leak(tmp_path):
    """JS pur contenant des mots-clés Python → rejeté."""
    js = """
    let x = None;
    if (x == True) {
        console.log("bad");
    }
    """
    p = _write(tmp_path, "app.js", js)
    r = lint_file(p)
    assert r.language == "javascript"
    assert not r.is_valid
    assert any("None" in e or "True" in e for e in r.errors)

