"""Tests unitaires des transactions FS avec rollback hardlinks (F-95).

Port de ``references/OpenKB/openkb/mutation.py``. Déterministe, 0 LLM.

Couvre :
- snapshot_paths : backup + journal "active", chemins inexistants → entry None.
- rollback : fichier modifié restauré, fichier supprimé restauré, fichier
  créé (track_new) supprimé, dossier copié restauré.
- mark_committed + discard : backup et journal nettoyés, fichier conservé.
- Crash recovery : journal "active" → recover roule back ; "committed" →
  discard seul ; corrompu → suppression bruyante ; rollback défaillant →
  retry borné (attempts) puis GAVE UP.
- Restore hardlinké O(touched) : fichier intact garde son inode, modifié
  restauré, ajouté supprimé.
- _hardlink_or_copy : repli copy2 sur EACCES.
- Snapshot partiel en échec → backup orphelin retiré.
"""
import errno
import json
import os
import shutil
from pathlib import Path

import pytest

from graph_orchestrator.fs_tx import (
    MAX_ROLLBACK_ATTEMPTS,
    MutationSnapshot,
    _hardlink_or_copy,
    _restore_hardlinked_dir,
    recover_pending_journals,
    snapshot_paths,
)


def _journal_dir(root: Path) -> Path:
    return root / ".fs_tx" / "journal"


# ==========================================
# snapshot_paths — structure
# ==========================================
def test_snapshot_writes_active_journal_and_backup(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("contenu A", encoding="utf-8")
    snap = snapshot_paths(tmp_path, [f], operation="op1")
    assert snap.journal_path.is_file()
    data = json.loads(snap.journal_path.read_text(encoding="utf-8"))
    assert data["status"] == "active"
    assert data["operation"] == "op1"
    backup = snap.entries[Path(f).resolve()]
    assert backup is not None and backup.is_file()
    assert backup.read_text(encoding="utf-8") == "contenu A"


def test_snapshot_missing_path_tracked_as_none(tmp_path: Path):
    missing = tmp_path / "not_yet.txt"
    snap = snapshot_paths(tmp_path, [missing], operation="op2")
    assert snap.entries[missing.resolve()] is None
    assert snap.journal_path.is_file()  # journal actif quand même (création à annuler)


def test_snapshot_failure_removes_orphan_backup(tmp_path: Path, monkeypatch):
    f1 = tmp_path / "ok.txt"
    f1.write_text("x", encoding="utf-8")
    f2 = tmp_path / "boom.txt"
    f2.write_text("y", encoding="utf-8")

    from graph_orchestrator import fs_tx

    real = fs_tx._copy_file_atomic

    def flaky(src, dest):
        if "boom" in str(src):
            raise OSError("boom")
        return real(src, dest)

    monkeypatch.setattr(fs_tx, "_copy_file_atomic", flaky)
    with pytest.raises(OSError, match="boom"):
        snapshot_paths(tmp_path, [f1, f2], operation="op3")
    backups = list((tmp_path / ".fs_tx" / "backup").glob("*")) if (tmp_path / ".fs_tx" / "backup").exists() else []
    assert backups == []  # pas de backup orphelin ingérable
    assert list(_journal_dir(tmp_path).glob("*.json")) == []


# ==========================================
# rollback — fichiers
# ==========================================
def test_rollback_restores_modified_file(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("AVANT", encoding="utf-8")
    snap = snapshot_paths(tmp_path, [f], operation="mod")
    f.write_text("APRES LA MUTATION", encoding="utf-8")
    snap.rollback()
    assert f.read_text(encoding="utf-8") == "AVANT"
    assert json.loads(snap.journal_path.read_text(encoding="utf-8"))["status"] == "rolled_back"


def test_rollback_restores_deleted_file(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("GARDER", encoding="utf-8")
    snap = snapshot_paths(tmp_path, [f], operation="del")
    f.unlink()
    snap.rollback()
    assert f.read_text(encoding="utf-8") == "GARDER"


def test_rollback_deletes_tracked_new_files(tmp_path: Path):
    created = tmp_path / "new.txt"
    snap = snapshot_paths(tmp_path, [created], operation="create")  # absent au snapshot
    created.write_text("généré par la mutation", encoding="utf-8")
    snap.track_new([created])
    snap.rollback()
    assert created.exists() is False


def test_rollback_restores_copied_directory(tmp_path: Path):
    d = tmp_path / "tree"
    (d / "sub").mkdir(parents=True)
    (d / "sub" / "f.txt").write_text("v1", encoding="utf-8")
    snap = snapshot_paths(tmp_path, [d], operation="dirmut")  # PAS de hardlink_dirs → copie
    (d / "sub" / "f.txt").write_text("v2", encoding="utf-8")
    (d / "extra.txt").write_text("nouveau", encoding="utf-8")
    snap.track_new([d / "extra.txt"])
    snap.rollback()
    assert (d / "sub" / "f.txt").read_text(encoding="utf-8") == "v1"
    assert (d / "extra.txt").exists() is False


def test_mark_committed_then_discard_keeps_files(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("v1", encoding="utf-8")
    snap = snapshot_paths(tmp_path, [f], operation="commit")
    f.write_text("v2", encoding="utf-8")
    snap.mark_committed()
    assert json.loads(snap.journal_path.read_text(encoding="utf-8"))["status"] == "committed"
    snap.discard()
    assert f.read_text(encoding="utf-8") == "v2"  # fichiers conservés
    assert snap.journal_path.exists() is False
    assert snap.backup_dir.exists() is False


def test_best_effort_helpers_swallow_exceptions(tmp_path: Path, monkeypatch):
    f = tmp_path / "a.txt"
    f.write_text("v1", encoding="utf-8")
    snap = snapshot_paths(tmp_path, [f], operation="best")
    monkeypatch.setattr(MutationSnapshot, "rollback", lambda self: 1 / 0)
    assert snap.rollback_best_effort() is not None  # ZeroDivisionError attrapée
    monkeypatch.setattr(MutationSnapshot, "discard", lambda self: 1 / 0)
    assert snap.discard_best_effort() is not None
    # Et les variantes saines retournent None :
    monkeypatch.undo()
    snap2 = snapshot_paths(tmp_path, [f], operation="best2")
    assert snap2.rollback_best_effort() is None
    assert snap2.discard_best_effort() is None


# ==========================================
# Restore hardlinké O(touched)
# ==========================================
def _hardlink_supported(tmp_path: Path) -> bool:
    a = tmp_path / "_cap_a.bin"
    b = tmp_path / "_cap_b.bin"
    a.write_bytes(b"x")
    try:
        os.link(a, b)
        return b.exists()
    except OSError:
        return False
    finally:
        a.unlink(missing_ok=True)
        b.unlink(missing_ok=True)


def test_hardlinked_dir_rollback_is_touched_only(tmp_path: Path):
    if not _hardlink_supported(tmp_path):
        pytest.skip("hardlinks non supportés sur ce filesystem")
    d = tmp_path / "blobstore"
    d.mkdir()
    untouched = d / "untouched.txt"
    modified = d / "modified.txt"
    deleted = d / "deleted.txt"
    for p, content in ((untouched, "u"), (modified, "m1"), (deleted, "d1")):
        p.write_text(content, encoding="utf-8")

    snap = snapshot_paths(
        tmp_path, [d], operation="blob", hardlink_dirs={d}
    )
    assert d in snap.hardlinked_dirs
    backup_untouched = snap.entries[d.resolve()] / "untouched.txt"
    # Le backup partage l'inode du fichier vivant (O(1), pas de copie d'octets).
    assert os.stat(untouched).st_ino == os.stat(backup_untouched).st_ino
    inode_untouched_avant = os.stat(untouched).st_ino

    # Mutation : modified réécrit via temp+replace (NOUVEL inode, contrat
    # hardlink-safe), added créé, deleted supprimé.
    tmp_mod = d / ".modified.tmp"
    tmp_mod.write_text("m2", encoding="utf-8")
    os.replace(tmp_mod, modified)
    added = d / "added.txt"
    added.write_text("a1", encoding="utf-8")
    deleted.unlink()

    snap.rollback()
    # Intact : JAMAIS recopié (même inode qu'avant la mutation).
    assert untouched.read_text(encoding="utf-8") == "u"
    assert os.stat(untouched).st_ino == inode_untouched_avant
    # Modifié : restauré depuis les octets pré-mutation.
    assert modified.read_text(encoding="utf-8") == "m1"
    # Supprimé : restauré.
    assert deleted.read_text(encoding="utf-8") == "d1"
    # Ajouté : retiré.
    assert added.exists() is False


def test_restore_hardlinked_dir_degrades_to_full_copy(tmp_path: Path):
    """Backup NON hardlinké (copie réelle) : chaque fichier = inode différent
    → tout est traité comme modifié et recopié (dégradation gracieuse)."""
    backup = tmp_path / "backup"
    target = tmp_path / "target"
    (backup / "s").mkdir(parents=True)
    (target / "s").mkdir(parents=True)
    (backup / "s" / "f.txt").write_text("b1", encoding="utf-8")
    (target / "s" / "f.txt").write_text("t1", encoding="utf-8")
    (target / "s" / "new.txt").write_text("n1", encoding="utf-8")

    _restore_hardlinked_dir(backup, target)
    assert (target / "s" / "f.txt").read_text(encoding="utf-8") == "b1"
    assert (target / "s" / "new.txt").exists() is False


def test_hardlink_or_copy_falls_back_on_eacces(tmp_path: Path, monkeypatch):
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("data", encoding="utf-8")

    def denied(*args, **kwargs):
        raise OSError(errno.EACCES, "permission denied (ACL / cloud-sync)")

    monkeypatch.setattr(os, "link", denied)
    _hardlink_or_copy(str(src), str(dst))
    assert dst.read_text(encoding="utf-8") == "data"


# ==========================================
# recover_pending_journals — crash recovery
# ==========================================
def test_recover_rolls_back_active_journal(tmp_path: Path):
    f = tmp_path / "v.txt"
    f.write_text("ETAT CONNU", encoding="utf-8")
    snap = snapshot_paths(tmp_path, [f], operation="coder:st1:iter1")
    f.write_text("MUTATION À MOITIÉ APPLIQUÉE", encoding="utf-8")
    # Process mort : ni rollback ni commit.

    messages = recover_pending_journals(tmp_path)
    assert any("Rolled back interrupted" in m for m in messages)
    assert f.read_text(encoding="utf-8") == "ETAT CONNU"
    assert snap.journal_path.exists() is False
    assert snap.backup_dir.exists() is False


def test_recover_discards_terminal_journal_without_touching_files(tmp_path: Path):
    f = tmp_path / "v.txt"
    f.write_text("v1", encoding="utf-8")
    snap = snapshot_paths(tmp_path, [f], operation="ok")
    f.write_text("v2", encoding="utf-8")
    snap.mark_committed()

    messages = recover_pending_journals(tmp_path)
    assert any("Cleaned terminal" in m for m in messages)
    assert f.read_text(encoding="utf-8") == "v2"  # conservé, PAS restauré
    assert snap.journal_path.exists() is False


def test_recover_removes_corrupt_journal_loudly(tmp_path: Path):
    journal_dir = _journal_dir(tmp_path)
    journal_dir.mkdir(parents=True)
    bad = journal_dir / "corrupt.json"
    bad.write_text("{pas du json", encoding="utf-8")

    messages = recover_pending_journals(tmp_path)
    assert any("Unrecoverable" in m for m in messages)
    assert bad.exists() is False  # sinon il re-échouerait à CHAQUE lock


def test_recover_retries_failing_rollback_then_gives_up(tmp_path: Path):
    f = tmp_path / "x.txt"
    f.write_text("present", encoding="utf-8")
    snap = snapshot_paths(tmp_path, [f], operation="willfail")
    # Sabotage : le backup référencé disparaît → rollback lève (restore impossible).
    shutil.rmtree(snap.backup_dir)

    messages = recover_pending_journals(tmp_path)
    assert any("retained for retry" in m for m in messages)
    assert snap.journal_path.exists() is True  # conservé pour retry
    data = json.loads(snap.journal_path.read_text(encoding="utf-8"))
    assert data["attempts"] == 1

    # On rejoue la récupération jusqu'au cap : abandon bruyant + discard.
    all_messages: list[str] = []
    for _ in range(MAX_ROLLBACK_ATTEMPTS):
        all_messages.extend(recover_pending_journals(tmp_path))
    assert any("GAVE UP" in m for m in all_messages)
    assert snap.journal_path.exists() is False


def test_recover_no_journal_dir_is_noop(tmp_path: Path):
    assert recover_pending_journals(tmp_path) == []


def test_snapshot_from_journal_roundtrip(tmp_path: Path):
    """Un journal seul (sans l'objet en RAM) suffit à reconstruire le snapshot —
    c'est le mécanisme de survie au crash du process."""
    from graph_orchestrator.fs_tx import _snapshot_from_journal

    f = tmp_path / "a.txt"
    f.write_text("v1", encoding="utf-8")
    snap = snapshot_paths(tmp_path, [f], operation="roundtrip")
    f.write_text("v2", encoding="utf-8")

    data = json.loads(snap.journal_path.read_text(encoding="utf-8"))
    rebuilt = _snapshot_from_journal(snap.journal_path, data)
    rebuilt.rollback()
    assert f.read_text(encoding="utf-8") == "v1"
