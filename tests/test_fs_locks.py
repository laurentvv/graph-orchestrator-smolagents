"""Tests unitaires des verrous FS coopératifs + écritures atomiques (F-95).

Port de ``references/OpenKB/openkb/locks.py``. Déterministe, 0 LLM.

Couvre :
- atomic_write_bytes/text/json : création, remplacement intégral, UTF-8,
  parents créés, aucun temp résiduel.
- _LocalRwLock : lecteurs concurrents autorisés, écrivain exclusif.
- dir_lock : fichier lock créé, réentrance même thread, upgrade read→write
  refusé, write_lock_held par thread.
- Verrou OS cross-process : un subprocess qui tient le lock → FsLockTimeout
  côté parent, acquisition OK après libération.
"""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from graph_orchestrator.fs_locks import (
    FsLockTimeout,
    _LocalRwLock,
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    dir_lock,
    write_lock,
    write_lock_held,
)


# ==========================================
# Écritures atomiques
# ==========================================
def test_atomic_write_bytes_creates_file_with_parents(tmp_path: Path):
    target = tmp_path / "sub" / "dir" / "f.bin"
    atomic_write_bytes(target, b"\x00\x01\x02")
    assert target.read_bytes() == b"\x00\x01\x02"


def test_atomic_write_bytes_replaces_content_entirely(tmp_path: Path):
    target = tmp_path / "f.txt"
    target.write_text("ancien contenu long " * 10, encoding="utf-8")
    atomic_write_bytes(target, b"nouveau")
    assert target.read_text(encoding="utf-8") == "nouveau"


def test_atomic_write_text_utf8(tmp_path: Path):
    target = tmp_path / "f.txt"
    atomic_write_text(target, "héllo wörld ✨")
    assert target.read_text(encoding="utf-8") == "héllo wörld ✨"


def test_atomic_write_json_parses_with_trailing_newline(tmp_path: Path):
    target = tmp_path / "j.json"
    atomic_write_json(target, {"a": 1, "b": ["x", "y"]})
    raw = target.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert json.loads(raw) == {"a": 1, "b": ["x", "y"]}


def test_atomic_write_leaves_no_temp_file(tmp_path: Path):
    target = tmp_path / "f.txt"
    for i in range(3):
        atomic_write_text(target, f"v{i}")
    leftovers = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


# ==========================================
# RW lock intra-process
# ==========================================
def test_local_rwlock_concurrent_readers():
    lock = _LocalRwLock()
    both_in = threading.Barrier(2, timeout=5)
    ok = []

    def reader():
        with lock.read():
            both_in.wait()  # ne passe que si les 2 lecteurs sont dedans SIMULTANÉMENT
            ok.append(True)

    threads = [threading.Thread(target=reader) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert not any(t.is_alive() for t in threads)
    assert len(ok) == 2


def test_local_rwlock_writer_excludes_readers():
    lock = _LocalRwLock()
    in_write = threading.Event()
    release = threading.Event()
    reader_proceeded = []

    def writer():
        with lock.write():
            in_write.set()
            release.wait(timeout=5)

    def reader():
        if in_write.wait(timeout=5):
            with lock.read():
                reader_proceeded.append(True)

    tw = threading.Thread(target=writer)
    tr = threading.Thread(target=reader)
    tw.start()
    assert in_write.wait(timeout=5)
    tr.start()
    time.sleep(0.15)
    assert reader_proceeded == []  # lecteur bloqué pendant l'écriture
    release.set()
    tw.join(timeout=5)
    tr.join(timeout=5)
    assert reader_proceeded == [True]


# ==========================================
# dir_lock — réentrance / upgrade / état
# ==========================================
def test_dir_lock_creates_lock_file(tmp_path: Path):
    with write_lock(tmp_path):
        assert (tmp_path / ".fs_tx" / "dir.lock").is_file()


def test_dir_lock_reentrant_same_thread(tmp_path: Path):
    with write_lock(tmp_path):
        assert write_lock_held(tmp_path)
        with write_lock(tmp_path):  # réentrance : ne deadlock pas
            assert write_lock_held(tmp_path)
    assert not write_lock_held(tmp_path)


def test_dir_lock_read_to_write_upgrade_denied(tmp_path: Path):
    from graph_orchestrator.fs_locks import read_lock

    with read_lock(tmp_path):
        with pytest.raises(RuntimeError, match="upgrade"):
            with write_lock(tmp_path):
                pass


def test_write_lock_held_false_outside(tmp_path: Path):
    assert write_lock_held(tmp_path) is False


def test_dir_lock_drains_active_journal_on_first_exclusive(tmp_path: Path):
    """La 1re acquisition exclusive déclenche recover_pending_journals (F-95).

    On fabrique un journal "active" orphelin (process mort), puis on prend le
    verrou : le fichier modifié doit être roulé back au passage.
    """
    from graph_orchestrator.fs_tx import snapshot_paths

    victim = tmp_path / "v.txt"
    victim.write_text("avant", encoding="utf-8")
    snap = snapshot_paths(tmp_path, [victim], operation="test:crash")
    victim.write_text("APRES mutation crashée", encoding="utf-8")
    # Pas de rollback ni discard : on simule un process mort mi-mutation.

    with write_lock(tmp_path):  # le drain doit rouler back
        assert victim.read_text(encoding="utf-8") == "avant"
    assert snap.journal_path.exists() is False  # discard après rollback


# ==========================================
# Verrou OS cross-process (subprocess)
# ==========================================
_CHILD_SCRIPT = """
import sys, time
sys.path.insert(0, {repo!r})
from pathlib import Path
from graph_orchestrator.fs_locks import write_lock
root = Path({root!r})
with write_lock(root, timeout_s=30):
    (root / "CHILD_READY").write_text("held", encoding="utf-8")
    time.sleep({hold_s})
(root / "CHILD_DONE").write_text("released", encoding="utf-8")
"""


def test_cross_process_lock_blocks_then_releases(tmp_path: Path):
    """Un subprocess tient le lock → le parent time out, puis acquiert après libération."""
    repo = str(Path(__file__).resolve().parents[1])
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _CHILD_SCRIPT.format(repo=repo, root=str(tmp_path), hold_s=2.0),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        ready = tmp_path / "CHILD_READY"
        deadline = time.monotonic() + 15
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready.exists(), "le child n'a pas pris le lock (voir stderr du subprocess)"

        # Parent : le lock est tenu par le child → timeout borné (pas de blocage infini).
        with pytest.raises(FsLockTimeout):
            with write_lock(tmp_path, timeout_s=1.0):
                pass

        # Le child libère → le parent acquiert.
        done = tmp_path / "CHILD_DONE"
        deadline = time.monotonic() + 15
        while not done.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert done.exists()
        with write_lock(tmp_path, timeout_s=10.0):
            pass  # acquis sans exception
    finally:
        child.wait(timeout=30)


def test_read_lock_and_write_lock_mutual_exclusion_cross_process(tmp_path: Path):
    """Le read lock tient aussi le fichier OS sous Windows (écart documenté) :
    un writer d'un AUTRE process ne peut pas entrer."""
    repo = str(Path(__file__).resolve().parents[1])
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _CHILD_SCRIPT.format(repo=repo, root=str(tmp_path), hold_s=1.5),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        ready = tmp_path / "CHILD_READY"
        deadline = time.monotonic() + 15
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready.exists()
        from graph_orchestrator.fs_locks import read_lock

        # Même un read lock croisé est exclusif cross-process sous Windows
        # (LK_NBLCK) ; sous POSIX, flock partagé vs exclusif → conflit aussi.
        with pytest.raises(FsLockTimeout):
            with read_lock(tmp_path, timeout_s=1.0):
                pass
    finally:
        child.wait(timeout=30)
