"""Verrous FS coopératifs + écritures atomiques (F-95, Priorité 8-bis).

Port de ``references/OpenKB/openkb/locks.py`` (fiche **32-OpenKB**, Hall of Fame
🟢 Haute). Complète le Mutex intra-process F-20 (``tools._FILE_LOCKS``,
``threading.Lock`` par fichier) par une coordination CROSS-PROCESS :

1. **Verrou OS advisory** sur un fichier lock (``<root>/.fs_tx/dir.lock``) —
   POSIX ``fcntl.flock`` (bloquant), Windows ``msvcrt.locking`` (retry borné
   puis exception). Deux process ne peuvent pas muter le même dossier de run
   simultanément (ex : deux reprises du même checkpoint lancées en parallèle).
2. **RW lock intra-process** (``_LocalRwLock``) — plusieurs lecteurs OU un
   écrivain, pour que les threads d'un même process ne se marchent pas dessus
   pendant que le verrou OS est tenu.
3. **Réentrance par thread** — un même thread peut ré-acquérir (compteurs de
   profondeur) ; l'upgrade read→write est refusé explicitement (RuntimeError),
   comme la référence.
4. **Drain des journaux** — la PREMIÈRE acquisition exclusive d'un process
   déclenche ``fs_tx.recover_pending_journals`` : toute transaction laissée
   "active" par un process mort est roulée back AVANT toute nouvelle mutation
   (sinon un replay écraserait les edits d'un run intermédiaire).
5. **Écritures atomiques** (``atomic_write_bytes/text/json``) — temp + ``os.replace``
   + fsync : un état intermédiaire déchiré n'est JAMAIS observable au chemin
   final. Consommateur principal : les journaux de ``fs_tx`` (un journal à moitié
   écrit = rollback impossible).

Écarts consciencieux vs la référence (documentés) :
- **Pas de dépendance portalocker** — verrou OS implémenté en stdlib pur
  (``fcntl``/``msvcrt``), qui est exactement ce que portalocker enveloppe.
  Le projet minimise ses dépendances (cf. dom_filter F-37 sans BeautifulSoup).
- **Lock timeout Windows configurable** — msvcrt.locking ne bloque pas ; la
  référence délègue à portalocker (~10s de retry). Ici : retry LK_NBLCK +
  sleep jusqu'à ``lock_timeout_s`` (défaut 10s) puis ``FsLockTimeout``.
- **Chemin du lock** ``<root>/.fs_tx/dir.lock`` (la référence :
  ``<kb>/.openkb/ingest.lock``) — namespace neutre, pas de présupposé produit.
- Le protocole reste ADVISORY : coordination entre process qui coopèrent (nos
  runs), pas une frontière de sécurité contre un processus hostile.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import IO, Iterator

logger = logging.getLogger(__name__)

# Fenêtre de retry du verrou exclusif sous Windows (msvcrt ne bloque pas).
# Miroir du comportement portalocker (~10s) documenté dans la référence.
LOCK_TIMEOUT_S = 10.0
_LOCK_RETRY_INTERVAL_S = 0.05

# Racine du namespace FS transactionnel dans un dossier verrouillé.
FS_TX_DIRNAME = ".fs_tx"
LOCK_FILENAME = "dir.lock"


class FsLockTimeout(RuntimeError):
    """Le verrou OS n'a pas pu être acquis dans la fenêtre de retry."""


# ---------------------------------------------------------------------------
# Verrou OS advisory (cross-process), stdlib pur
# ---------------------------------------------------------------------------

def _flock_posix(fh: IO, *, exclusive: bool) -> None:
    import fcntl  # noqa: PLC0415 — POSIX seulement

    fcntl.flock(fh.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)


def _flock_windows(fh: IO, *, exclusive: bool, timeout_s: float) -> None:
    import msvcrt  # noqa: PLC0415 — Windows seulement

    # Écart consciencieux : msvcrt.locking ne connaît que des verrous de plage
    # d'octets EXCLUSIFS. La référence délègue les shared locks à pywin32
    # (LockFileEx). Pour rester stdlib pur, un read lock prend lui aussi un
    # verrou OS exclusif sous Windows — sûreté conservée (jamais 2 détenteurs
    # cross-process), seule la concurrence lecteurs×lecteurs INTER-process est
    # sacrifiée (sans objet pour nous : 1 lock exclusif par run). La vraie
    # concurrence lecteurs reste assurée INTRA-process par _LocalRwLock.
    del exclusive
    deadline = time.monotonic() + timeout_s
    fh.seek(0)
    while True:
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise FsLockTimeout(
                    f"FS lock non acquis en {timeout_s}s (tenu par un autre process)"
                ) from None
            time.sleep(_LOCK_RETRY_INTERVAL_S)


def _funlock_windows(fh: IO) -> None:
    import msvcrt  # noqa: PLC0415 — Windows seulement

    try:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        # Handle fermé / verrou déjà libéré : libérer au mieux, jamais bloquer.
        pass


def flock(fh: IO, *, exclusive: bool, timeout_s: float = LOCK_TIMEOUT_S) -> None:
    """Acquiert un verrou advisory sur un fichier OUVERT (cross-plateforme)."""
    if os.name == "nt":
        _flock_windows(fh, exclusive=exclusive, timeout_s=timeout_s)
    else:
        _flock_posix(fh, exclusive=exclusive)


def funlock(fh: IO) -> None:
    """Libère un verrou acquis via :func:`flock`."""
    if os.name == "nt":
        _funlock_windows(fh)
    else:
        import fcntl  # noqa: PLC0415

        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# RW lock intra-process (plusieurs lecteurs OU un écrivain)
# ---------------------------------------------------------------------------

class _LocalRwLock:
    """RW lock par condition — miroir exact de la référence OpenKB."""

    def __init__(self) -> None:
        self._condition = threading.Condition(threading.Lock())
        self._readers = 0
        self._writer = False

    @contextlib.contextmanager
    def read(self) -> Iterator[None]:
        with self._condition:
            while self._writer:
                self._condition.wait()
            self._readers += 1
        try:
            yield
        finally:
            with self._condition:
                self._readers -= 1
                if self._readers == 0:
                    self._condition.notify_all()

    @contextlib.contextmanager
    def write(self) -> Iterator[None]:
        with self._condition:
            while self._writer or self._readers:
                self._condition.wait()
            self._writer = True
        try:
            yield
        finally:
            with self._condition:
                self._writer = False
                self._condition.notify_all()


_LOCKS_GUARD = threading.Lock()
_LOCAL_LOCKS: dict[Path, _LocalRwLock] = {}
_HELD_LOCKS = threading.local()


def _held_locks() -> dict[Path, tuple[int, int]]:
    held = getattr(_HELD_LOCKS, "counts", None)
    if held is None:
        held = {}
        _HELD_LOCKS.counts = held
    return held


def _local_lock(lock_path: Path) -> _LocalRwLock:
    resolved = lock_path.resolve()
    with _LOCKS_GUARD:
        lock = _LOCAL_LOCKS.get(resolved)
        if lock is None:
            lock = _LocalRwLock()
            _LOCAL_LOCKS[resolved] = lock
        return lock


def _drain_pending_journals(root_dir: Path) -> None:
    """Roule back les journaux laissés "actifs" par un process interrompu.

    Le drain fait partie de la PRISE du verrou exclusif, pas d'une commande :
    un process qui acquiert l'exclusif doit restaurer l'état connu AVANT de
    muter. Sinon, un run crashé mi-commit laisserait un journal actif qu'un run
    ultérieur roulerait back PAR-DESSUS des edits intermédiaires.

    Import différé : casse le cycle locks ↔ fs_tx (fs_tx importe les helpers
    d'écriture atomique de ce module au top level). N'est appelé que sur la
    première acquisition OS exclusive — jamais sur un read lock.
    """
    from .fs_tx import recover_pending_journals

    for message in recover_pending_journals(root_dir):
        logger.warning(message)


def _lock_file_path(root_dir: Path) -> Path:
    return root_dir / FS_TX_DIRNAME / LOCK_FILENAME


@contextlib.contextmanager
def dir_lock(
    root_dir: Path | str, *, exclusive: bool, timeout_s: float = LOCK_TIMEOUT_S
) -> Iterator[None]:
    """Tient un verrou advisory au niveau du dossier ``root_dir``.

    Réentrant par thread (compteurs). L'upgrade d'un read lock existant vers
    write lève ``RuntimeError`` (comme la référence) : lever l'ambiguïté à la
    compilation plutôt que de deadlocker le lecteur contre lui-même.
    """
    root = Path(root_dir)
    lock_path = _lock_file_path(root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    resolved = lock_path.resolve()
    held = _held_locks()
    exclusive_depth, shared_depth = held.get(resolved, (0, 0))

    if exclusive_depth or shared_depth:
        if exclusive and not exclusive_depth:
            raise RuntimeError("Cannot upgrade an existing read lock to a write lock")
        held[resolved] = (
            exclusive_depth + (1 if exclusive else 0),
            shared_depth + (0 if exclusive else 1),
        )
        try:
            yield
        finally:
            current_exclusive, current_shared = held[resolved]
            next_counts = (
                current_exclusive - (1 if exclusive else 0),
                current_shared - (0 if exclusive else 1),
            )
            if next_counts == (0, 0):
                del held[resolved]
            else:
                held[resolved] = next_counts
        return

    local_lock = _local_lock(lock_path)
    local_context = local_lock.write() if exclusive else local_lock.read()
    with local_context:
        with lock_path.open("a+", encoding="utf-8") as fh:
            flock(fh, exclusive=exclusive, timeout_s=timeout_s)
            held[resolved] = (1, 0) if exclusive else (0, 1)
            try:
                if exclusive:
                    _drain_pending_journals(root.resolve())
                yield
            finally:
                held.pop(resolved, None)
                funlock(fh)


def write_lock(
    root_dir: Path | str, timeout_s: float = LOCK_TIMEOUT_S
) -> "contextlib._GeneratorContextManager[None]":
    """Tient le verrou EXCLUSIF de ``root_dir`` (mutation)."""
    return dir_lock(root_dir, exclusive=True, timeout_s=timeout_s)


def read_lock(
    root_dir: Path | str, timeout_s: float = LOCK_TIMEOUT_S
) -> "contextlib._GeneratorContextManager[None]":
    """Tient le verrou PARTAGÉ de ``root_dir`` (lecture)."""
    return dir_lock(root_dir, exclusive=False, timeout_s=timeout_s)


def write_lock_held(root_dir: Path | str) -> bool:
    """True ssi le thread COURANT tient le verrou exclusif de ``root_dir``.

    Le suivi est par thread (``threading.local``) : un worker renvoie False
    même quand le main thread tient le verrou — les primitives de mutation
    peuvent ainsi s'assurer qu'elles tournent sur le thread propriétaire
    plutôt que de deadlocker silencieusement sur un second flock OS.
    """
    held = _held_locks()
    resolved = _lock_file_path(Path(root_dir)).resolve()
    exclusive_depth, _ = held.get(resolved, (0, 0))
    return exclusive_depth > 0


# ---------------------------------------------------------------------------
# Écritures atomiques (temp + os.replace + fsync)
# ---------------------------------------------------------------------------

def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        # Windows ne peut pas ouvrir un handle de dossier pour le fsyncer.
        # os.replace est atomique sur NTFS (pas d'état déchiré) ; sans le flush
        # du dossier, la durabilité du rename au crash est plus faible qu'en
        # POSIX. Comportement identique à la référence.
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _default_file_mode() -> int:
    current_umask = os.umask(0)
    os.umask(current_umask)
    return 0o666 & ~current_umask


def _target_mode(path: Path) -> int:
    try:
        return path.stat().st_mode & 0o777
    except FileNotFoundError:
        return _default_file_mode()


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Remplace atomiquement ``path`` par ``content`` (binaire).

    Écrit dans un temp du MÊME dossier puis ``os.replace`` : un observateur ne
    voit jamais un état intermédiaire partiel au chemin final. Le mode du
    fichier existant est préservé (un nouveau fichier reçoit le mode umask,
    pas le 0600 de ``mkstemp``).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            if hasattr(os, "fchmod"):  # indisponible sous Windows
                os.fchmod(fh.fileno(), _target_mode(path))
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
        _fsync_directory(path.parent)
    finally:
        tmp_path.unlink(missing_ok=True)


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Remplace atomiquement ``path`` par ``content`` (texte)."""
    atomic_write_bytes(path, content.encode(encoding))


def atomic_write_json(
    path: Path,
    data: object,
    *,
    ensure_ascii: bool = True,
    default=None,
) -> None:
    """Remplace atomiquement ``path`` par du JSON formaté."""
    atomic_write_text(
        path,
        json.dumps(data, indent=2, ensure_ascii=ensure_ascii, default=default) + "\n",
    )
