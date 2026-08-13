import pytest

from graph_orchestrator.tools import (
    check_js_syntax,
    edit_file,
    list_directory,
    read_file,
    write_file,
)

def test_edit_file(tmp_path):
    # Setup
    test_file = tmp_path / "test.txt"
    write_file(str(test_file), "Hello World\nHello World\nLine 3")

    # Test ambiguous (multiple occurrences)
    res = edit_file(str(test_file), "Hello World", "Hi World")
    assert "appears 2 times" in res or "Error" in res

    # Test exact match
    res = edit_file(str(test_file), "Line 3", "Line 4")
    assert "Successfully updated" in res

    with open(str(test_file), 'r') as f:
        content = f.read()
        assert "Line 4" in content
        assert "Line 3" not in content

    # Test replace_all
    res = edit_file(str(test_file), "Hello World", "Hi World", replace_all=True)
    assert "Successfully updated" in res

    with open(str(test_file), 'r') as f:
        content = f.read()
        assert content.count("Hi World") == 2


# === F-97 / MA-5 : read_file / list_directory normalisent les chemins file:/// ===

def test_read_file_accepts_file_scheme_url(tmp_path):
    """Un LLM qui passe un `file:///...` URL à read_file ne doit plus crasher (Errno 22)."""
    f = tmp_path / "page.html"
    f.write_text("<html>ok</html>", encoding="utf-8")
    url = "file:///" + str(f).replace("\\", "/")
    res = read_file(url)
    assert "Error reading file" not in res
    assert "<html>ok</html>" in res


def test_list_directory_accepts_file_scheme_url(tmp_path):
    """Un LLM qui passe un `file:///...` URL à list_directory ne doit plus crasher (WinError 123)."""
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    url = "file:///" + str(tmp_path).replace("\\", "/")
    res = list_directory(url)
    assert "Error listing directory" not in res
    assert "index.html" in res


# === F-72 : check_js_syntax (Prompt Offloading — outil Coder verify-after) ===

import shutil  # noqa: E402

_NODE_AVAILABLE = shutil.which("node") is not None
node_required = pytest.mark.skipif(
    not _NODE_AVAILABLE, reason="node.js non installé sur cette machine"
)


@node_required
def test_check_js_syntax_valid(tmp_path):
    """Fichier JS valide → message ✅."""
    f = tmp_path / "app.js"
    f.write_text("const x = [3, 1, 2].sort(); console.log(x);", encoding="utf-8")
    res = check_js_syntax(path=str(f))
    assert "valide" in res.lower()
    assert "Erreur" not in res


@node_required
def test_check_js_syntax_syntax_error(tmp_path):
    """Fichier JS avec SyntaxError → message ❌ contenant l'erreur du parseur."""
    f = tmp_path / "buggy.js"
    f.write_text("const x = 1 + ;", encoding="utf-8")  # expression incomplète
    res = check_js_syntax(path=str(f))
    assert "Erreur de syntaxe" in res
    assert "buggy.js" in res


def test_check_js_syntax_missing_file(tmp_path):
    """Fichier absent → message d'erreur de lecture (jamais d'exception)."""
    res = check_js_syntax(path=str(tmp_path / "nope.js"))
    assert "Erreur de lecture" in res


def test_check_js_syntax_node_absent(tmp_path, monkeypatch):
    """node absent du PATH (mock shutil.which) → message informatif (pas de mensonge ✅)."""
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    f = tmp_path / "app.js"
    f.write_text("const x = 1;", encoding="utf-8")
    res = check_js_syntax(path=str(f))
    assert "non disponible" in res
    assert "valide" not in res.lower(), "Ne doit PAS affirmer 'valide' sans avoir vérifié."

