"""Tests unitaires de la journalisation auto des runs (Priorité 13-bis).

Valide le Tee posé sur stdout/stderr par ``workflows.main()`` : capture de
``print()`` dans un fichier, stripping ANSI (log lisible en plain-text),
restauration des flux originaux même en cas d'exception, et opt-out.

Déterministes, 0 LLM.
"""
import io
import os
import sys

import pytest

from graph_orchestrator.run_logging import (
    _TeeIO,
    resolve_log_path,
    tee_run_logging,
)


# ==========================================
# resolve_log_path
# ==========================================
def test_resolve_log_path_format():
    """Format : <logs_dir>/run-<YYYYMMDD-HHMMSS>-<mode>.log."""
    path = resolve_log_path("coding", "logs")
    norm = path.replace("\\", "/")
    assert norm.startswith("logs/run-")
    assert norm.endswith("-coding.log")
    # Le timestamp est bien au format attendu (8 digits date, tiret, 6 digits heure).
    import re
    assert re.search(r"run-\d{8}-\d{6}-coding\.log$", norm)


def test_resolve_log_path_slugifies_mode():
    """Mode avec espaces/casse → slugifié (sûr comme nom de fichier)."""
    path = resolve_log_path("One Shot", "logs")
    assert "-one-shot.log" in path.replace("\\", "/")


def test_resolve_log_path_cross_platform():
    """os.path.join → séparateur natif (pas de / hardcodé)."""
    path = resolve_log_path("x", os.path.join("a", "b"))
    # Le chemin utilise bien le séparateur de l'OS.
    assert os.path.join("a", "b", "") in path or path.startswith(os.path.join("a", "b"))


def test_resolve_log_path_empty_mode_fallback():
    """Mode vide → fallback 'run'."""
    path = resolve_log_path("", "logs")
    assert "-run.log" in path.replace("\\", "/")


# ==========================================
# _TeeIO : écriture + stripping ANSI
# ==========================================
def test_teeio_writes_raw_to_real_and_stripped_to_log():
    """Le terminal reçoit le raw (couleurs), le fichier l'ANSI-stripé."""
    real = io.StringIO()
    log = io.StringIO()
    tee = _TeeIO(real, log)
    # 'hello' + code couleur rouge ANSI.
    tee.write("hel\x1b[31mlo\x1b[0m")
    assert real.getvalue() == "hel\x1b[31mlo\x1b[0m"  # raw préservé
    assert log.getvalue() == "hello"  # ANSI stripé


def test_teeio_write_returns_input_length():
    """Convention TextIOBase.write : renvoie le nombre de caractères de l'entrée."""
    real = io.StringIO()
    log = io.StringIO()
    tee = _TeeIO(real, log)
    msg = "some message"
    assert tee.write(msg) == len(msg)


def test_teeio_write_empty_chunk_noop():
    """write('') n'écrit rien nulle part et renvoie 0."""
    real = io.StringIO()
    log = io.StringIO()
    tee = _TeeIO(real, log)
    assert tee.write("") == 0
    assert real.getvalue() == ""
    assert log.getvalue() == ""


def test_teeio_flush_propagates():
    """flush() appelle flush() sur les deux flux (sans erreur)."""
    real = io.StringIO()
    log = io.StringIO()
    tee = _TeeIO(real, log)
    tee.write("x")
    tee.flush()  # ne doit pas lever
    assert real.getvalue() == "x"
    assert log.getvalue() == "x"


def test_teeio_isatty_delegates_to_real():
    """isatty() délègue au flux réel (Rich a besoin de ça pour émettre les couleurs)."""
    class FakeStream:
        encoding = "utf-8"
        def isatty(self): return True
        def write(self, s): return len(s)
        def flush(self): pass
    tee = _TeeIO(FakeStream(), io.StringIO())
    assert tee.isatty() is True


def test_teeio_isatty_non_tty_real():
    """Avec un StringIO (non-TTY), isatty() retourne False."""
    tee = _TeeIO(io.StringIO(), io.StringIO())
    assert tee.isatty() is False


def test_teeio_encoding_from_real():
    """encoding hérite du flux réel (fallback utf-8)."""
    tee = _TeeIO(io.StringIO(), io.StringIO())
    assert tee.encoding == "utf-8"


def test_teeio_gobbles_broken_pipe_on_real():
    """BrokenPipeError sur le terminal (ex: | head) ne fait pas crasher le run."""
    class BrokenStream:
        encoding = "utf-8"
        def write(self, s): raise BrokenPipeError("pipe closed")
        def flush(self): pass
        def isatty(self): return False
    log = io.StringIO()
    tee = _TeeIO(BrokenStream(), log)
    # Ne doit pas lever malgré le BrokenPipeError côté terminal.
    tee.write("survives broken pipe")
    # Le fichier reçoit quand même les données (log complet pour post-mortem).
    assert log.getvalue() == "survives broken pipe"


# ==========================================
# tee_run_logging : intégration context-manager
# ==========================================
def test_tee_run_logging_captures_print(tmp_path, capfd):
    """Un print() dans le contexte est capturé dans le fichier log."""
    log_path = str(tmp_path / "logs" / "run-test.log")
    msg = "ligne capturee par le tee"
    with tee_run_logging(log_path, enabled=True):
        print(msg)
    with open(log_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert msg in content


def test_tee_run_logging_creates_logs_dir(tmp_path):
    """Le répertoire parent (logs/) est créé s'il n'existe pas."""
    log_path = str(tmp_path / "nested" / "deep" / "run.log")
    assert not os.path.exists(tmp_path / "nested")
    with tee_run_logging(log_path, enabled=True):
        print("x")
    assert os.path.exists(log_path)


def test_tee_run_logging_restores_stdout(tmp_path):
    """sys.stdout est restauré à la sortie du contexte (critical pour tests E2E)."""
    original = sys.stdout
    log_path = str(tmp_path / "run.log")
    with tee_run_logging(log_path, enabled=True):
        assert sys.stdout is not original  # remplacé pendant
    assert sys.stdout is original  # restauré après


def test_tee_run_logging_restores_on_exception(tmp_path):
    """Restauration des flux même en cas d'exception mid-bloc."""
    original = sys.stdout
    log_path = str(tmp_path / "run.log")
    with pytest.raises(RuntimeError):
        with tee_run_logging(log_path, enabled=True):
            print("avant crash")
            raise RuntimeError("boom")
    assert sys.stdout is original


def test_tee_run_logging_disabled_is_noop(tmp_path):
    """enabled=False → aucun fichier créé, stdout non touché."""
    original = sys.stdout
    log_path = str(tmp_path / "should_not_exist.log")
    with tee_run_logging(log_path, enabled=False):
        assert sys.stdout is original  # inchangé
    assert not os.path.exists(log_path)


def test_tee_run_logging_strips_ansi_in_file(tmp_path):
    """Les codes ANSI sont stripés dans le fichier (log lisible en plain-text)."""
    log_path = str(tmp_path / "run.log")
    with tee_run_logging(log_path, enabled=True):
        # Simule une sortie colorée Rich/ANSI.
        sys.stdout.write("[\x1b[32mOK\x1b[0m] done\n")
    with open(log_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "[OK] done" in content
    assert "\x1b[" not in content  # aucun code ANSI


def test_tee_run_logging_captures_stderr(tmp_path):
    """sys.stderr est aussi capturé par le Tee."""
    log_path = str(tmp_path / "run.log")
    with tee_run_logging(log_path, enabled=True):
        sys.stderr.write("erreur capturée\n")
    with open(log_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "erreur capturée" in content
