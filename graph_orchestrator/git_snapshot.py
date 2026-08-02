"""Git local dans le dossier du run pour suivre les modifications du Coder. F-48.

PRINCIPE : à chaque itération du Coder, on commit l'état des fichiers générés dans un
git LOCAL (propre au dossier du run, isolé du repo principal). En itération N+1, on
peut extraire `git diff HEAD` pour obtenir les lignes EXACTES modifiées par le Coder.

BÉNÉFICIAIRES :
  - Tester (F-47 re-test ciblé) : ne tester QUE les zones modifiées (git diff = source
    de vérité du "qu'est-ce qui a changé", plus précise que les réfutations texte).
  - Judge : juger le diff réel au lieu du feedback texte (doctrine "in-diff-only").
  - Coder : auto-vérification (voir son propre diff après correction).

ISOLEMENT : le .git vit dans runs/<dated>/ (déjà gitignored du repo principal via
`runs/` dans .gitignore). Pas de conflit avec le git du repo principal. Le workflow
fait `_scoped_chdir(run_output_dir)` avant le Coder, donc le cwd pendant les opérations
git EST le dossier du run.

ROBUSTESSE : toutes les opérations sont tolérantes aux pannes (si git absent ou .git
corrompu, on yield "" — le workflow continue sans diff, fallback sur les réfutations).
Aucune cassure.
"""

import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# Limite de taille du diff injecté au LLM (pour ne pas saturer le contexte).
# Un diff de correction chirurgicale est typiquement < 5k cars. Au-delà, on tronque.
MAX_DIFF_CHARS = 4000


def _run_git(args: list, cwd: Optional[str] = None) -> tuple[int, str]:
    """Exécute une commande git, retourne (exit_code, stdout).

    cwd=None → utilise le cwd courant (le dossier du run si appelé pendant le workflow).
    Tolérant : jamais d'exception (subprocess peut échouer si git absent).
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode, result.stdout
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        logger.debug("git %s échoué (%s) — ignoré.", args[0], e)
        return 1, ""


def init_run_git() -> bool:
    """Initialise un git local dans le cwd courant (dossier du run).

    À appeler UNE FOIS au début du run (avant le premier Coder). Idempotent : si .git
    existe déjà, ne fait rien (safe pour les reprises après crash).

    Returns:
        True si le git est opérationnel (init réussi ou déjà existant), False sinon.
    """
    if os.path.isdir(".git"):
        return True
    code, _ = _run_git(["init", "--quiet"])
    if code != 0:
        logger.debug("git init échoué — git local indisponible pour ce run.")
        return False
    # Config minimale (git requiert user.email/name pour commit). Valeurs neutres,
    # non persistantes (locales au .git du run, pas global).
    _run_git(["config", "user.email", "coder@graph-orchestrator.local"])
    _run_git(["config", "user.name", "Graph Orchestrator Coder"])
    _run_git(["config", "commit.gpgsign", "false"])  # pas de signature (CI/headless)
    return True


def commit_iteration(iteration: int, message: str = "") -> bool:
    """Commit l'état courant des fichiers du dossier du run.

    À appeler APRÈS chaque exécution du Coder. Crée un commit avec tous les changements
    (ajouts + modifications + suppressions). Premier appel = commit initial (iter 1).

    Args:
        iteration: Numéro d'itération (pour le message de commit).
        message: Message optionnel (sinon auto-généré "Iteration N").

    Returns:
        True si le commit a réussi, False sinon (git absent, rien à committer, etc.).
    """
    if not os.path.isdir(".git"):
        return False
    # git add -A : tous les changements (nouveaux, modifiés, supprimés).
    _run_git(["add", "-A"])
    msg = message or f"Iteration {iteration}"
    # --allow-empty : au cas où le Coder n'a rien changé (ne fail pas).
    # On ne veut pas crasher le workflow si le commit est vide.
    code, _ = _run_git(["commit", "--quiet", "--allow-empty", "-m", msg])
    return code == 0


def get_last_diff(max_chars: int = MAX_DIFF_CHARS) -> str:
    """Retourne le diff entre l'avant-dernier et le dernier commit (= ce que le Coder
    vient de modifier à l'itération courante).

    À appeler APRÈS commit_iteration, AVANT le Tester/Judge. En itération 1 (1 seul
    commit), retourne "" (pas de diff — c'est la création initiale, le Tester fait un
    test complet). En itération N+1, retourne les hunks modifiés depuis l'iter N.

    Args:
        max_chars: Plafond de caractères (tronque au-delà avec marqueur [...]).

    Returns:
        Le diff texte (format git diff, hunks avec contexte), ou "" si :
          - git indisponible / .git absent
          - moins de 2 commits (itération 1)
          - diff vide (rien modifié)
    """
    if not os.path.isdir(".git"):
        return ""
    # HEAD~1..HEAD = diff entre l'avant-dernier et le dernier commit.
    # --stat d'abord pour vérifier qu'il y a des changements (évite un diff vide énorme).
    code_stat, stat = _run_git(["diff", "--stat", "HEAD~1", "HEAD"])
    if code_stat != 0 or not stat.strip():
        return ""  # moins de 2 commits, ou aucun changement
    # Diff complet avec contexte (hunks). --no-color pour éviter les codes ANSI.
    code, diff = _run_git(["diff", "HEAD~1", "HEAD", "--no-color"])
    if code != 0 or not diff.strip():
        return ""
    # Tronque si trop long (préserve le début = les changements les plus pertinents).
    if len(diff) > max_chars:
        diff = diff[:max_chars].rsplit("\n", 1)[0] + "\n[... diff tronqué]"
    return diff


def has_git_history() -> bool:
    """Indique si le git local a au moins 2 commits (= on peut extraire un diff).

    Utile pour décider si le Tester peut faire un re-test ciblé sur le diff (itération >1)
    ou doit faire un test complet (itération 1).
    """
    if not os.path.isdir(".git"):
        return False
    code, log = _run_git(["rev-list", "--count", "HEAD"])
    if code != 0:
        return False
    try:
        return int(log.strip()) >= 2
    except ValueError:
        return False
