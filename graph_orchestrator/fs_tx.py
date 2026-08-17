"""Transactions FS avec rollback par hardlinks (F-95, Priorité 8-bis).

Port de ``references/OpenKB/openkb/mutation.py`` (fiche **32-OpenKB**, Hall of
Fame 🟢 Haute). Complète l'idempotence F-43 (les replays ne RÉAPPLIQUENT pas
deux fois un effet) par l'ANNULATION des effets partiellement appliqués :

1. ``snapshot_paths`` — snapshot O(touched) des chemins qu'une mutation VA
   toucher : fichiers copiés atomiquement, répertoires hardlinkés (O(1) par
   fichier, partage d'inode — cf. ``hardlink_dirs``) vers
   ``<root>/.fs_tx/backup/<id>/``.
2. **Journal actif** — ``<root>/.fs_tx/journal/<id>.json`` écrit AVANT la
   mutation ("active") : c'est le signal de récupération. Un process qui meurt
   mi-mutation laisse un journal actif que le prochain process roule back au
   moment de prendre le verrou exclusif (``fs_locks._drain_pending_journals``).
3. ``MutationSnapshot.rollback`` — restaure l'état pré-mutation : les fichiers
   modifiés/supprimés sont restaurés depuis le backup, les fichiers CRÉÉS
   (``track_new``) sont supprimés. Pour un dossier hardlinké, restauration
   O(touched) par diff d'inode : les fichiers jamais touchés partagent encore
   l'inode du backup → on ne les recopie pas.
4. ``recover_pending_journals`` — draine les journaux : "active" → rollback,
   terminal ("committed"/"rolled_back") → discard, corrompu → suppression
   bruyante (sinon il re-échouerait à CHAQUE acquisition du lock, briquant le
   dossier), rollback réellement défaillant → retry borné
   (``MAX_ROLLBACK_ATTEMPTS``) puis abandon bruyant.

Écarts consciencieux vs la référence (documentés) :
- **Namespace** ``<root>/.fs_tx/{journal,backup}`` (la référence :
  ``<kb>/.openkb/{journal,staging}``) — neutre, partagé avec fs_locks.
- **``publish_staged_tree``/``_publish_staged_file`` NON portés** — spécifiques
  au staging raw/wiki-sources d'OpenKB (aucun consommateur ici). Le flux
  transactionnel (snapshot → mutation → commit/rollback → drain) est intégral.
- **Journal noms relatifs** : les chemins ABSOLUS du run au moment du snapshot
  sont conservés (fidèle à la référence) ; un run dir déplacé entre crash et
  reprise casse le replay — jamais le cas chez nous (chemin persisté au
  checkpoint F-24).

Contrat d'appelant pour ``hardlink_dirs`` (AVERTISSEMENT référence) : un
répertoire n'est sûr à hardlinker que si TOUS ses écrivains font du
temp+replace atomique (nouvel inode) ou de l'append-only. Un écrivain
in-place corromprait silencieusement le backup (rollback no-op pour ce
fichier). Nos outils (write_file open('w') + truncate/replace) créent un
nouvel inode par réécriture complète — mais append_file est in-place →
NE JAMAIS lister un dossier cible du Coder en hardlink_dirs ; les appels
production passent hardlink_dirs=None (copies réelles, sûres).
"""

from __future__ import annotations

import errno
import json
import logging
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .fs_locks import FS_TX_DIRNAME, _fsync_directory, _target_mode, atomic_write_json

logger = logging.getLogger(__name__)

# Cap le nombre de retries de recover_pending_journals sur un journal actif
# dont le rollback échoue de façon déterministe (ex: ENOSPC persistant). Sans
# cap, il serait retenté à CHAQUE acquisition du lock, refaisant le travail
# échoué indéfiniment sans jamais libérer le backup + le journal.
MAX_ROLLBACK_ATTEMPTS = 5


def _apply_mode(path: Path, mode: int) -> None:
    """Applique les bits de permission (no-op si ``os.chmod`` est absent)."""
    if hasattr(os, "chmod"):
        os.chmod(path, mode)


def _fsync_file(path: Path) -> None:
    """Fsync best-effort des données d'un fichier (durabilité post-rename).

    Ouvert en read+write pour que ``FlushFileBuffers`` marche sous Windows
    (un handle read-only peut être refusé). Best-effort : un échec n'affaiblit
    que la durabilité d'octets déjà écrits — il ne doit jamais faire échouer
    l'opération.
    """
    try:
        with open(path, "r+b") as fh:
            os.fsync(fh.fileno())
    except OSError:
        pass


def _hardlink_or_copy(src: str, dst: str) -> None:
    """``copytree`` copy_function qui hardlink (O(1), partage l'inode).

    Réservé aux backups de répertoires que l'appelant a marqués hardlink-safe
    (cf. avertissement contrat en tête de module). Repli en copie réelle sur
    EXDEV/EPERM/EACCES — cross-device, FS qui interdit les hardlinks, ou
    (Windows) ACL / dossier cloud-sync (OneDrive/Dropbox) qui bloque
    CREATE_HARD_LINK. Si la copie échoue aussi, l'erreur réelle remonte.
    """
    src_path = Path(src)
    dst_path = Path(dst)
    try:
        os.link(src_path, dst_path)
    except OSError as exc:
        if exc.errno not in (errno.EXDEV, errno.EPERM, errno.EACCES):
            raise
        shutil.copy2(src_path, dst_path)


def _copy_file_atomic(src: Path, dest: Path) -> None:
    """Stream ``src`` vers ``dest`` via un temp file, puis replace atomique.

    Stream (jamais de buffer du fichier entier). Le temp + ``os.replace``
    garantit qu'aucun état intermédiaire déchiré n'est observable au chemin
    final. Le répertoire parent est fsyncé et le résultat porte le mode umask
    (pas le 0600 de ``mkstemp``).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Capture le mode de destination AVANT que le temp ne le masque : un
    # fichier neuf reçoit le mode umask du process, un fichier existant garde
    # son mode courant — la même règle qu'atomic_write_bytes.
    mode = _target_mode(dest)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=dest.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out, src.open("rb") as inp:
            shutil.copyfileobj(inp, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp_path, dest)
        _apply_mode(dest, mode)
        _fsync_directory(dest.parent)
    finally:
        tmp_path.unlink(missing_ok=True)


@dataclass
class MutationSnapshot:
    """Snapshot des chemins finaux touchés par une tentative de mutation."""

    root_dir: Path
    backup_dir: Path
    journal_path: Path
    operation: str
    details: dict = field(default_factory=dict)
    entries: dict[Path, Path | None] = field(default_factory=dict)
    attempts: int = 0
    # Dossiers dont le backup a été hardlinké (en-process seulement ; non
    # persisté — un snapshot reconstruit d'un journal laisse vide et le
    # rollback prend le chemin sûr de la copie complète). Piloté par le
    # restore O(touched) par diff d'inode.
    hardlinked_dirs: set[Path] = field(default_factory=set)

    def _journal_data(self, status: str) -> dict:
        return {
            "version": 1,
            "operation": self.operation,
            "status": status,
            "root_dir": str(self.root_dir),
            "backup_dir": str(self.backup_dir),
            "details": self.details,
            "attempts": self.attempts,
            "entries": [
                {
                    "target": str(target),
                    "backup": str(backup) if backup is not None else None,
                }
                for target, backup in self.entries.items()
            ],
        }

    def write_journal(self, status: str) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.journal_path, self._journal_data(status))

    def mark_committed(self) -> None:
        """Marque le journal "committed" SANS supprimer le backup.

        À appeler L'INSTANT où la mutation est durablement appliquée, pour
        qu'un ``recover_pending_journals`` ultérieur DISCARDE le journal au
        lieu de le rouler back. C'est le signal de commit ; ``discard`` est le
        nettoyage post-commit (backup + journal) qui doit rester best-effort —
        il tourne APRÈS le point de commit et son échec ne doit jamais
        déclencher un rollback.
        """
        self.write_journal("committed")

    def track_new(self, paths: list[Path]) -> None:
        """Enregistre des chemins CRÉÉS après le snapshot (supprimés au rollback).

        Certains artefacts n'ont leur nom définitif qu'une fois la mutation
        lancée. Plutôt que de snapshotter tout un arbre append-only à l'avance
        (O(total) à CHAQUE mutation), l'appelant enregistre les nouveaux
        chemins une fois créés : backup=None → rollback et replay de
        récupération suppriment exactement ces chemins, rien d'autre. Le
        journal actif est réécrit — un crash après création mais avant commit
        les nettoie aussi. Chemins déjà suivis ignorés ; chemins absents =
        no-op (rien n'a été créé).
        """
        changed = False
        for path in paths:
            target = path.resolve()
            if target not in self.entries:
                self.entries[target] = None
                changed = True
        if changed:
            self.write_journal("active")

    def rollback(self) -> None:
        # Restaure les enfants avant les parents : un delete de répertoire ne
        # peut pas retirer des chemins encore à restaurer d'un backup plus
        # spécifique.
        for target, backup in sorted(
            self.entries.items(),
            key=lambda item: len(item[0].parts),
            reverse=True,
        ):
            # Un backup de dossier hardlinké supporte un restore O(touched)
            # par diff d'inode (laisser les fichiers d'inode partagé intact,
            # ne toucher que les changés) — NE PAS rmtree d'abord : cela
            # détruirait les inodes partagés.
            if target.is_dir() and target in self.hardlinked_dirs:
                if backup is not None and backup.is_dir():
                    _restore_hardlinked_dir(backup, target)
                else:
                    shutil.rmtree(target, ignore_errors=True)  # nouveau dossier, pas de backup
                continue
            # Non-hardlinké (fichier, ou dossier copié) : remove + restore inconditionnels.
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)
            if backup is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if backup.is_dir():
                shutil.copytree(backup, target)
            else:
                _copy_file_atomic(backup, target)
        self.write_journal("rolled_back")

    def rollback_best_effort(self) -> Exception | None:
        try:
            self.rollback()
        except Exception as exc:
            logger.warning("Mutation rollback failed: %s", exc)
            return exc
        return None

    def discard(self) -> None:
        # Nettoyage best-effort post-commit/post-rollback : un statut terminal
        # a déjà été écrit, rien à réécrire ici — le faire serait du travail
        # mort et dégraderait silencieusement un journal "rolled_back" en
        # "committed" juste avant sa suppression.
        shutil.rmtree(self.backup_dir, ignore_errors=True)
        self.journal_path.unlink(missing_ok=True)

    def discard_best_effort(self) -> Exception | None:
        try:
            self.discard()
        except Exception as exc:
            logger.warning("Mutation journal cleanup failed: %s", exc)
            return exc
        return None


def _restore_hardlinked_dir(backup: Path, target: Path) -> None:
    """Restore O(touched) pour un backup de répertoire hardlinké.

    Le backup a été construit via ``os.link`` : les fichiers vivants que la
    mutation n'a jamais touchés partagent encore l'inode du backup → on les
    laisse. Seuls les fichiers changés demandent du travail : nouveaux
    fichiers (pas de pendant au backup) supprimés, fichiers modifiés
    (temp+replace atomique → nouvel inode) et supprimés restaurés depuis les
    octets pré-mutation du backup. Évite de recopier tout l'arbre au rollback.

    Dégradation gracieuse en copie complète si le backup n'est PAS réellement
    hardlinké (le repli EXDEV/EACCES a firing au snapshot) : chaque fichier a
    alors un inode différent → chaque fichier est traité comme modifié et
    recopié.
    """

    def _file_key(path: Path) -> tuple[int, int]:
        st = path.stat()  # suit les symlinks ; ces arbres ne contiennent que des fichiers réguliers
        return (st.st_dev, st.st_ino)

    backup_files = {p.relative_to(backup): p for p in backup.rglob("*") if p.is_file()}

    # Passe 1 : supprime les fichiers vivants nouveaux + modifiés ; laisse les
    # intacts (inode partagé avec le backup) en place.
    if target.exists():
        for live in list(target.rglob("*")):
            if not live.is_file():
                continue
            counterpart = backup_files.get(live.relative_to(target))
            if counterpart is None or _file_key(live) != _file_key(counterpart):
                live.unlink()

    # Passe 2 : restaure modifiés + supprimés depuis le backup.
    for rel, src in backup_files.items():
        dest = target / rel
        if not dest.exists() or _file_key(dest) != _file_key(src):
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    # Passe 3 : élague les répertoires créés par la mutation désormais vides.
    if target.exists():
        for d in sorted(
            (p for p in target.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True
        ):
            if not (backup / d.relative_to(target)).exists() and not any(d.iterdir()):
                d.rmdir()


def snapshot_paths(
    root_dir: Path | str,
    paths: list[Path],
    *,
    operation: str,
    details: dict | None = None,
    hardlink_dirs: set[Path] | None = None,
) -> MutationSnapshot:
    """Snapshot des chemins finaux AVANT qu'une mutation ne commence.

    ⚠️ Contrat ``hardlink_dirs`` : ne lister que des répertoires dont TOUS les
    écrivains font du temp+replace atomique ou de l'append-only (cf. tête de
    module). Tout écrivain in-place corromprait silencieusement le backup.

    Le journal "active" est le signal de récupération : une fois écrit, un
    process futur peut restaurer chaque cible enregistrée même si le process
    courant meurt.
    """
    root = Path(root_dir).resolve()
    hardlink_resolved = {p.resolve() for p in (hardlink_dirs or ())}
    journal_id = uuid.uuid4().hex
    backup_dir = root / FS_TX_DIRNAME / "backup" / f"rollback-{journal_id}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    snapshot = MutationSnapshot(
        root_dir=root,
        backup_dir=backup_dir,
        journal_path=root / FS_TX_DIRNAME / "journal" / f"{journal_id}.json",
        operation=operation,
        details=details or {},
    )
    try:
        for path in paths:
            target = path.resolve()
            if target in snapshot.entries:
                continue
            if not target.exists():
                snapshot.entries[target] = None
                continue
            rel = target.relative_to(root)
            backup = backup_dir / rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            if target.is_dir():
                if target in hardlink_resolved:
                    shutil.copytree(target, backup, copy_function=_hardlink_or_copy)
                    snapshot.hardlinked_dirs.add(target)
                else:
                    shutil.copytree(target, backup)
            else:
                _copy_file_atomic(target, backup)
            snapshot.entries[target] = backup
        # Le journal actif est le signal de récupération (cf. docstring).
        snapshot.write_journal("active")
    except Exception:
        # Snapshot partiel : le backup_dir existe sur disque mais aucun
        # journal n'a été écrit. recover_pending_journals ne scanne que les
        # journaux → retirer le backup orphelin ici, sinon il fuit pour
        # toujours sans que rien ne puisse l'atteindre ou le nettoyer.
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise
    return snapshot


def _snapshot_from_journal(path: Path, data: dict) -> MutationSnapshot:
    snapshot = MutationSnapshot(
        root_dir=Path(data["root_dir"]),
        backup_dir=Path(data["backup_dir"]),
        journal_path=path,
        operation=data.get("operation", "mutation"),
        details=data.get("details") or {},
    )
    snapshot.entries = {
        Path(item["target"]): Path(item["backup"]) if item.get("backup") else None
        for item in data.get("entries", [])
    }
    snapshot.attempts = int(data.get("attempts", 0) or 0)
    return snapshot


def recover_pending_journals(root_dir: Path | str) -> list[str]:
    """Roule back les journaux actifs laissés par un process interrompu.

    Retourne des messages de diagnostic (logués par l'appelant). C'est le
    point d'entrée du crash-recovery : branché sur la première acquisition du
    verrou exclusif (``fs_locks``), AVANT toute nouvelle mutation.
    """
    root = Path(root_dir)
    journal_dir = root / FS_TX_DIRNAME / "journal"
    if not journal_dir.is_dir():
        return []
    messages: list[str] = []
    for journal_path in sorted(journal_dir.glob("*.json")):
        snapshot: MutationSnapshot | None = None
        try:
            data = json.loads(journal_path.read_text(encoding="utf-8"))
            snapshot = _snapshot_from_journal(journal_path, data)
            status = data.get("status", "active")
            if status in {"committed", "rolled_back"}:
                snapshot.discard()
                messages.append(f"Cleaned terminal mutation journal {journal_path.name}.")
                continue
            snapshot.rollback()
            snapshot.discard()
            messages.append(
                f"Rolled back interrupted {snapshot.operation} journal {journal_path.name}."
            )
        except Exception as exc:
            if snapshot is None:
                # Journal illisible/reconstituable (corrompu/vide/JSON perdu,
                # ou clés root_dir/backup_dir manquantes). Rien à rouler back
                # ni retenter — et le laisser en place re-déclencherait cet
                # échec à CHAQUE acquisition du lock (le drain tourne à la
                # première acquisition exclusive), briquant tout le dossier.
                # Suppression best-effort + log bruyant ; un backup_dir qu'il
                # référençait devient inatteignable et peut fuir.
                journal_path.unlink(missing_ok=True)
                messages.append(
                    f"Unrecoverable mutation journal {journal_path.name} "
                    f"({type(exc).__name__}: {exc}); removed so it can't block "
                    f"recovery. The tree may need manual review."
                )
                continue
            # Rollback échoué. Retry borné à travers les runs de récupération
            # (une tentative ultérieure peut réussir une fois la cause
            # disparue, ex: espace disque libéré), puis abandon : discard du
            # journal + backup et log bruyant — pas de fuite infinie.
            snapshot.attempts += 1
            if snapshot.attempts >= MAX_ROLLBACK_ATTEMPTS:
                snapshot.discard()
                messages.append(
                    f"GAVE UP on {snapshot.operation} journal {journal_path.name} after "
                    f"{snapshot.attempts} failed rollback(s): {type(exc).__name__}: {exc}. "
                    f"The tree may be in a partially-rolled-back state — manual review needed."
                )
            else:
                snapshot.write_journal("active")  # persiste le compteur incrémenté
                messages.append(
                    f"Rollback of {snapshot.operation} journal {journal_path.name} failed "
                    f"(attempt {snapshot.attempts}/{MAX_ROLLBACK_ATTEMPTS}): "
                    f"{type(exc).__name__}: {exc}; retained for retry."
                )
    return messages
