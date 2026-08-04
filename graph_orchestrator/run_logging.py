"""Capture automatique des logs de run dans ``logs/`` (Priorité 13-bis).

Chaque exécution d'un workflow (one_shot / exploration / coding) journalise son
stdout+stderr dans ``logs/run-<timestamp>-<mode>.log`` via un *Tee* posé sur
``sys.stdout`` / ``sys.stderr`` dès ``workflows.main()``. Fini la redirection
manuelle (``> logs/...log``) et le chemin hardcodé dans ``run_analyzer.py``.

Compatible Rich
---------------
Les ``Console()`` module-level (``workflows.py``, ``runner.py``, ``hitl.py``)
sont construites avec ``_file=None`` : la propriété ``console.file`` résout
``sys.stdout`` paresseusement à CHAQUE print, tandis que ``is_terminal`` est figé
à l'import depuis le vrai terminal. Un Tee sur ``sys.stdout`` est donc capté
automatiquement : les couleurs ANSI sont préservées sur le terminal (rendu) et
stripées pour la copie fichier (log lisible). L'analyzer cible des patterns
``print()`` plats (``[Step N: Duration ...]``, ``[*] Coder``, ``Traceback (``) —
non affectés par Rich — donc sa compatibilité est préservée par construction.
"""

import io
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime
from typing import IO, Iterator

# Séquences d'échappement ANSI (SGR couleurs + CSI large). Stripées de la copie
# fichier pour garder un log lisible en plain-text (le terminal reçoit le raw).
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


class _TeeIO(io.TextIOBase):
    """Stream bidirectionnel : écrit raw sur le terminal, ANSI-stripé sur fichier.

    Se comporte comme un ``sys.stdout`` transparent pour Rich et ``print()`` :
      - ``isatty()`` délègue au flux réel → Rich émet bien les codes couleurs ;
      - ``write()`` renvoie le nombre de caractères de l'entrée (convention
        ``TextIOBase.write``) pour ne pas perturber les consommateurs amont.
    """

    def __init__(self, real_stream: IO[str], log_file: IO[str]):
        self._real = real_stream
        self._log = log_file

    # --- API principale ------------------------------------------------------
    def write(self, chunk: str) -> int:
        if chunk:
            # Terminal : raw (couleurs préservées). BrokenPipeError gobé pour
            # survivre aux fermetures de pipe (ex: | head, CI tronquée).
            try:
                self._real.write(chunk)
            except (BrokenPipeError, ValueError):
                pass
            # Fichier : ANSI stripé (log lisible en plain-text).
            stripped = _ANSI_RE.sub("", chunk)
            if stripped:
                self._log.write(stripped)
        return len(chunk)

    def flush(self) -> None:
        try:
            self._real.flush()
        except (BrokenPipeError, ValueError):
            pass
        try:
            self._log.flush()
        except (ValueError, OSError):
            pass

    # --- Caractérisation du flux (délègue au réel) ---------------------------
    def isatty(self) -> bool:
        try:
            return self._real.isatty()
        except Exception:
            return False

    def fileno(self) -> int:
        return self._real.fileno()

    @property
    def encoding(self) -> str:
        return getattr(self._real, "encoding", "utf-8") or "utf-8"

    def reconfigure(self, **kwargs) -> None:
        # Pass-through best-effort vers le flux réel. Le line-buffering est déjà
        # posé à l'import de workflows.py (avant main()), donc ce no-op n'est
        # qu'un filet de sécurité pour les appels tardifs éventuels.
        rc = getattr(self._real, "reconfigure", None)
        if callable(rc):
            try:
                rc(**kwargs)
            except Exception:
                pass

    # --- Stoïque face aux sondes de smolagents/stdlib ------------------------
    def writable(self) -> bool:
        return True

    def readable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return False


@contextmanager
def tee_run_logging(log_path: str, enabled: bool = True) -> Iterator[None]:
    """Redirige stdout+stderr vers le terminal ET ``log_path`` pendant le run.

    Restaure les flux originaux même en cas d'exception (critical pour les tests
    E2E qui enchaînent plusieurs runs dans le même process). Si ``enabled`` est
    False, devient un no-op pur (opt-out ``LOG_TO_FILE=0``).
    """
    if not enabled:
        yield
        return

    # Crée le répertoire parent (logs/) si besoin. ``os.path.dirname`` peut
    # renvoyer '' si log_path est un simple nom de fichier → fallback '.'.
    parent = os.path.dirname(log_path) or "."
    os.makedirs(parent, exist_ok=True)

    real_out, real_err = sys.stdout, sys.stderr
    # buffering=1 (line-buffered) : permet le `tail -f` en temps réel sur un
    # run long (plusieurs minutes) sans attendre la fin du process.
    log_file = open(log_path, "w", encoding="utf-8", buffering=1)
    sys.stdout = _TeeIO(real_out, log_file)
    sys.stderr = _TeeIO(real_err, log_file)
    try:
        yield
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        sys.stdout, sys.stderr = real_out, real_err
        try:
            log_file.flush()
        except (ValueError, OSError):
            pass
        log_file.close()


def resolve_log_path(mode: str, logs_dir: str) -> str:
    """Construit un chemin de log horodaté : ``<logs_dir>/run_<mode>_<stamp>/run_full.log``.

    Cross-plateforme (``os.path.join``). Le mode est slugifié pour rester sûr
    comme nom de dossier. Convention d'horodatage : ``YYYY-MM-DD_HHMMSS`` (triable
    chronologiquement par simple ordre lexicographique).
    """
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    safe_mode = re.sub(r"[^a-z0-9]+", "_", (mode or "").strip().lower()).strip("_") or "run"
    return os.path.join(logs_dir, f"run_{safe_mode}_{stamp}", "run_full.log")
