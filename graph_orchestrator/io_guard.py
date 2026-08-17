"""Cloisonnement IO des outils par allowlist de chemins (F-95, Priorité 8-bis).

Port du pattern ``references/OpenKB/openkb/agent/tools.py`` (fiche
**32-OpenKB**, Hall of Fame 🟢 Haute) : chaque outil FS d'un agent vérifie que
le chemin demandé reste DANS les racines autorisées, AVANT d'exécuter —
« Access denied: path escapes root. »

Complément orthogonal aux gardes existantes :
- ``bash_guard`` (F-38) = DENYLIST de COMMANDES (motif destructif) ;
- ``read_gate`` (F-67) = read-before-write par fichier ;
- ``io_guard`` (F-95) = ALLOWLIST de CHEMINS (périmètre) : le Coder ne peut
  plus écrire/lire HORS du dossier du run courant. Failure mode réel couvert :
  un LLM qui hallucine un chemin absolu vers le dépôt de l'usine elle-même
  (ex: ``D:\\GIT\\graph-orchestrator-smolagents\\graph_orchestrator\\tools.py``)
  et corrompt l'usine qui le fait tourner, ou qui lit le code source de
  l'usine (pollution de contexte + fuite de prompts système).

Sémantique (fidèle à la doctrine fail-open du projet) :
- **Scopé et opt-in au runtime** : sans racine enregistrée (tests, scripts
  d'isolation debug/, usage direct des outils), TOUT passe — aucun
  comportement historique n'est cassé. En run de production,
  ``workflows.run_coding_workflow`` enregistre le dossier du run comme racine
  unique et le libère en fin de run (context manager, comme
  ``_scoped_idempotency`` F-43).
- ``resolve()`` complet : suit les symlinks ET résout les ``..`` —
  ``sub/../../outside.txt`` est détecté même si chaque composant semble
  « dedans » (attaque par traversal classique).
- Windows-safe : comparaison ``os.path.normcase`` (insensible à la casse sur
  NTFS) + frontière de répertoire stricte (``D:\\run2`` n'est PAS dans
  ``D:\\run``).
- Messages pédagogiques renvoyés à l'agent (pattern openfox
  FORMAT_CORRECTION / read_gate) : l'agent est orienté vers le chemin relatif
  correct au lieu d'une erreur opaque.

Écarts consciencieux vs la référence :
- La référence retourne ``"Access denied: path escapes wiki root."`` par
  outil dupliqué ; ici un module central + une allowlist de N racines (le
  Coder hérite de [run_dir] ; un futur nœud pourrait recevoir davantage).
- ``bash_command`` n'est PAS couvert (commande shell arbitraire — les chemins
  y sont inextricables) : il reste couvert par ``bash_guard`` (denylist
  commandes). Cloisonnement = outils FS structurés uniquement, comme la
  référence (read_wiki_file/write_kb_file).
"""

from __future__ import annotations

import contextlib
import os
import threading
from pathlib import Path

_ALLOWED_ROOTS: list[Path] = []
_ROOTS_GUARD = threading.Lock()


# ---------------------------------------------------------------------------
# Allowlist scopée (contexte module-level, pattern _scoped_idempotency F-43)
# ---------------------------------------------------------------------------

def set_allowed_roots(roots: list[str | Path] | None) -> None:
    """Enregistre les racines autorisées (None/[] = fail-open, tout passe)."""
    with _ROOTS_GUARD:
        _ALLOWED_ROOTS.clear()
        if roots:
            _ALLOWED_ROOTS.extend(Path(os.path.realpath(str(r))) for r in roots)


def clear_allowed_roots() -> None:
    """Libère les racines (retour au mode fail-open)."""
    set_allowed_roots(None)


def get_allowed_roots() -> list[Path]:
    """Copie des racines actives (vide = mode fail-open)."""
    with _ROOTS_GUARD:
        return list(_ALLOWED_ROOTS)


@contextlib.contextmanager
def scoped_allowed_roots(roots: list[str | Path] | None):
    """Context manager : racines actives dans le bloc, libérées à la sortie."""
    previous = get_allowed_roots()
    set_allowed_roots(roots)
    try:
        yield
    finally:
        set_allowed_roots(previous)


# ---------------------------------------------------------------------------
# Vérification
# ---------------------------------------------------------------------------

def _normalize(path: Path) -> str:
    """Forme canonique de comparaison (normcase + realpath déjà résolus)."""
    return os.path.normcase(str(path))


def path_allowed(path: str | Path) -> tuple[bool, str]:
    """Vérifie que ``path`` reste dans une racine autorisée.

    Returns:
        (allowed, reason) — reason non vide seulement si refus. Ne lève
        JAMAIS d'exception (un chemin absurde est refusé, pas crashé, quand
        une racine est active ; passé en fail-open sinon).
    """
    roots = get_allowed_roots()
    if not roots:
        return True, ""
    try:
        candidate = Path(os.path.realpath(str(path)))
    except (TypeError, ValueError, OSError):
        return False, f"Access denied: '{path}' n'est pas un chemin exploitable."
    candidate_n = _normalize(candidate)
    for root in roots:
        root_n = _normalize(root)
        if candidate_n == root_n or candidate_n.startswith(root_n + os.sep):
            return True, ""
    listed = ", ".join(str(r) for r in roots)
    return False, (
        f"Access denied: path '{path}' escapes the allowed workspace root(s) "
        f"[{listed}]. Ton dossier de travail EST la racine autorisée : "
        f"utilise un chemin RELATIF à ton cwd (ex: 'index.html', "
        f"'assets/style.css')."
    )


def _enabled() -> bool:
    """Lecture du settings à l'appel (réactif aux changements d'env, cf. bash_guard)."""
    from .config import settings

    return getattr(settings, "io_allowlist_enabled", True)


def ensure_write_allowed(path: str | Path) -> str | None:
    """Garde pour les OUTILS D'ÉCRITURE.

    Returns:
        None si autorisé ; sinon un message pédagogique À RETOURNER à l'agent
        (pattern write_file/read_gate — l'appel est bloqué SANS exception).
    """
    if not _enabled():
        return None
    allowed, reason = path_allowed(path)
    return None if allowed else reason


def ensure_read_allowed(path: str | Path) -> str | None:
    """Garde pour les OUTILS DE LECTURE (même sémantique que l'écriture).

    La référence OpenKB confine aussi les lectures (``read_wiki_file`` :
    « Access denied: path escapes wiki root. ») — lire le code de l'usine
    hôte depuis un nœud LLM est une pollution de contexte et une fuite de
    prompts système, pas un besoin légitime du run.
    """
    if not _enabled():
        return None
    allowed, reason = path_allowed(path)
    return None if allowed else reason
