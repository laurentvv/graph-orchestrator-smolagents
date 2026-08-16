"""Tests unitaires du cloisonnement IO par allowlist de chemins (F-95).

Port du pattern ``references/OpenKB/openkb/agent/tools.py`` (« Access denied:
path escapes root. »). Déterministe, 0 LLM.

Couvre :
- Fail-open : sans racine enregistrée, tout passe (tests/debug/scripts isolation).
- Racine unique : chemins internes autorisés (relatifs via cwd, absolus,
  imbriqués), chemins externes refusés.
- Attaque par traversal : ``sub/../../evil.txt`` résolu puis refusé.
- Frontière stricte : ``run2`` n'est pas dans ``run`` (pas de préfixe naif).
- Windows : insensibilité à la casse (normcase), séparateurs mixtes.
- Lifecycle : set/clear/scoped (restaure les racines précédentes).
- Opt-out settings (IO_ALLOWLIST_ENABLED=false).
- Intégration OUTILS : write_file/read_file/list_directory/search_replace/
  append_file/edit_file/multi_replace/read_python_skeleton bloqués dehors,
  fonctionnels dedans — sans jamais lever d'exception.
"""
import os
from pathlib import Path

import pytest

from graph_orchestrator import io_guard
from graph_orchestrator.io_guard import (
    clear_allowed_roots,
    ensure_read_allowed,
    ensure_write_allowed,
    get_allowed_roots,
    path_allowed,
    scoped_allowed_roots,
    set_allowed_roots,
)


@pytest.fixture(autouse=True)
def _clean_roots():
    """Aucune racine résiduelle entre les tests (le module est à état global)."""
    clear_allowed_roots()
    yield
    clear_allowed_roots()


# ==========================================
# Fail-open sans racine
# ==========================================
def test_no_roots_everything_allowed(tmp_path: Path):
    outside = tmp_path / "ailleurs.txt"
    assert path_allowed(outside)[0] is True
    assert ensure_write_allowed(outside) is None
    assert ensure_read_allowed(outside) is None
    assert get_allowed_roots() == []


# ==========================================
# Autorisations / refus
# ==========================================
def test_inside_root_allowed(tmp_path: Path, monkeypatch):
    root = tmp_path / "run"
    root.mkdir()
    set_allowed_roots([root])
    monkeypatch.chdir(root)
    allowed, reason = path_allowed("sub/f.txt")
    assert allowed, reason
    assert path_allowed(root / "index.html")[0] is True
    assert path_allowed(str(root) + "/a/b/c.js")[0] is True


def test_outside_root_denied(tmp_path: Path):
    root = tmp_path / "run"
    root.mkdir()
    outside = tmp_path / "factory" / "tools.py"
    set_allowed_roots([root])
    allowed, reason = path_allowed(outside)
    assert allowed is False
    assert "Access denied" in reason
    assert ensure_write_allowed(outside) is not None
    assert ensure_read_allowed(outside) is not None


def test_traversal_escape_denied(tmp_path: Path, monkeypatch):
    root = tmp_path / "run"
    root.mkdir()
    set_allowed_roots([root])
    monkeypatch.chdir(root)
    # Chaque composant semble "dedans", la résolution complète sort de la racine.
    allowed, _ = path_allowed("sub/../../evil.txt")
    assert allowed is False


def test_sibling_prefix_dir_denied(tmp_path: Path):
    """run2 n'est PAS dans run : frontière de répertoire stricte (pas de
    startswith naif sur la chaîne)."""
    run = tmp_path / "run"
    run2 = tmp_path / "run2"
    run.mkdir()
    run2.mkdir()
    set_allowed_roots([run])
    assert path_allowed(run2 / "f.txt")[0] is False


def test_windows_case_and_separators(tmp_path: Path):
    root = tmp_path / "MiXeD" / "Run"
    root.mkdir(parents=True)
    set_allowed_roots([root])
    candidate = str(root).replace("/", os.sep) + os.sep + "F.TXT"
    if os.name == "nt":
        candidate = candidate.swapcase()  # NTFS insensible à la casse
    assert path_allowed(candidate)[0] is True


def test_multiple_roots(tmp_path: Path):
    r1 = tmp_path / "run1"
    r2 = tmp_path / "run2"
    r1.mkdir()
    r2.mkdir()
    set_allowed_roots([r1, r2])
    assert path_allowed(r1 / "a.txt")[0] is True
    assert path_allowed(r2 / "b.txt")[0] is True
    assert path_allowed(tmp_path / "run3" / "c.txt")[0] is False


def test_garbage_path_denied_not_crashed(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    set_allowed_roots([root])
    allowed, reason = path_allowed(None)  # type: ignore[arg-type]
    assert allowed is False
    assert "Access denied" in reason


# ==========================================
# Lifecycle
# ==========================================
def test_clear_restores_fail_open(tmp_path: Path):
    root = tmp_path / "run"
    root.mkdir()
    set_allowed_roots([root])
    assert path_allowed(tmp_path / "outside.txt")[0] is False
    clear_allowed_roots()
    assert path_allowed(tmp_path / "outside.txt")[0] is True


def test_scoped_restores_previous_roots(tmp_path: Path):
    outer = tmp_path / "outer"
    outer.mkdir()
    inner = tmp_path / "inner"
    inner.mkdir()
    set_allowed_roots([outer])
    with scoped_allowed_roots([inner]):
        assert path_allowed(inner / "f")[0] is True
        assert path_allowed(outer / "f")[0] is False
    # Sortie du scope → racine précédente restaurée (pas un simple clear).
    assert path_allowed(outer / "f")[0] is True
    assert path_allowed(inner / "f")[0] is False


def test_opt_out_setting_disables_guard(tmp_path: Path):
    """IO_ALLOWLIST_ENABLED=false → garde contournée (pattern bash_guard : on
    patch le settings À LA SOURCE car _enabled() fait `from .config import
    settings` à chaque appel ; Settings est frozen → dataclasses.replace)."""
    import dataclasses
    from unittest.mock import patch

    from graph_orchestrator import config

    root = tmp_path / "run"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    set_allowed_roots([root])
    relaxed = dataclasses.replace(config.settings, io_allowlist_enabled=False)
    with patch("graph_orchestrator.config.settings", relaxed):
        assert ensure_write_allowed(outside) is None
        assert ensure_read_allowed(outside) is None
    # Hors patch : la garde est réactive (opt-out bien scoppé au settings).
    assert ensure_write_allowed(outside) is not None
    # path_allowed reste factuel (utilisé par ensure_* uniquement) :
    assert path_allowed(outside)[0] is False


# ==========================================
# Intégration outils (tools.py)
# ==========================================
CONTENT = "console.log('hello'); // contenu réel suffisant"


def test_write_file_outside_denied_not_created(tmp_path: Path):
    from graph_orchestrator.tools import write_file

    root = tmp_path / "run"
    root.mkdir()
    victim = tmp_path / "factory_file.py"
    set_allowed_roots([root])
    result = write_file(str(victim), CONTENT)
    assert "Access denied" in result
    assert victim.exists() is False


def test_write_file_inside_works(tmp_path: Path, monkeypatch):
    from graph_orchestrator.tools import write_file

    root = tmp_path / "run"
    root.mkdir()
    monkeypatch.chdir(root)
    set_allowed_roots([root])
    result = write_file("app.js", CONTENT)  # contenu réel > 5 chars, pas un squelette HTML
    assert result.startswith("Successfully wrote")
    assert (root / "app.js").is_file()


def test_read_file_outside_denied(tmp_path: Path):
    from graph_orchestrator.tools import read_file

    root = tmp_path / "run"
    root.mkdir()
    secret = tmp_path / "AGENTS.md"
    secret.write_text("directives internes de l'usine", encoding="utf-8")
    set_allowed_roots([root])
    result = read_file(str(secret))
    assert "Access denied" in result


def test_read_file_inside_works(tmp_path: Path, monkeypatch):
    from graph_orchestrator.tools import read_file

    root = tmp_path / "run"
    root.mkdir()
    (root / "app.js").write_text(CONTENT, encoding="utf-8")
    monkeypatch.chdir(root)
    set_allowed_roots([root])
    assert "console.log" in read_file("app.js")


def test_list_directory_outside_denied(tmp_path: Path):
    from graph_orchestrator.tools import list_directory

    root = tmp_path / "run"
    root.mkdir()
    set_allowed_roots([root])
    assert "Access denied" in list_directory(str(tmp_path))


def test_edit_tools_outside_denied(tmp_path: Path):
    from graph_orchestrator.tools import append_file, edit_file, multi_replace, search_replace

    root = tmp_path / "run"
    root.mkdir()
    victim = tmp_path / "victim.js"
    victim.write_text(CONTENT, encoding="utf-8")
    set_allowed_roots([root])
    assert "Access denied" in search_replace(str(victim), "hello", "world")
    assert "Access denied" in edit_file(str(victim), "hello", "world")
    assert "Access denied" in append_file(str(victim), "// suite réelle du code")
    assert "Access denied" in multi_replace(
        str(victim), [{"old_string": "hello", "new_string": "world"}]
    )
    assert victim.read_text(encoding="utf-8") == CONTENT  # rien n'a bougé


def test_read_python_skeleton_outside_denied(tmp_path: Path):
    from graph_orchestrator.tools import read_python_skeleton

    root = tmp_path / "run"
    root.mkdir()
    victim = tmp_path / "module.py"
    victim.write_text("def f():\n    return 1\n", encoding="utf-8")
    set_allowed_roots([root])
    assert "Access denied" in read_python_skeleton(str(victim))


def test_tools_fail_open_without_roots(tmp_path: Path):
    """Hors run (tests unitaires historiques, scripts debug/) : rien ne change."""
    from graph_orchestrator.tools import read_file

    f = tmp_path / "libre.txt"
    f.write_text(CONTENT, encoding="utf-8")
    assert "console.log" in read_file(str(f))
