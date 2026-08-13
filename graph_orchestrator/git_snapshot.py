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
passe ``run_output_dir`` explicitement à chaque fonction (cwd-indépendant depuis le
fix F-53) — en plus du ``_scoped_chdir(run_output_dir)`` historique.

GARDE ANTI-POLLUTION F-53 : git remonte l'arborescence pour découvrir un repo. Si pour
quelque raison que ce soit (cwd erroné, .git non créé, env GIT_DIR, etc.) le repo
découvert n'est PAS le run dir, toute opération d'écriture est REFUSÉE (``_is_isolated``
compare le ``show-toplevel`` au run dir attendu). Un run E2E avait créé un commit vide
« Iteration 1 » dans le repo principal (reflog 9e860af) — cette garde empêche tout
récidive, indépendamment de la cause racine.

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


def _git_dirpath(repo_path: Optional[str]) -> str:
    """Chemin du ``.git`` à vérifier (relatif si repo_path None, sinon absolu sous repo_path)."""
    return os.path.join(repo_path, ".git") if repo_path else ".git"


def _cwd_for(repo_path: Optional[str]) -> Optional[str]:
    """Traduit repo_path en cwd pour _run_git (None = hérite du cwd process, rétrocompat)."""
    return repo_path


def _resolved_toplevel(repo_path: Optional[str]) -> Optional[str]:
    """Toplevel absolu du repo git DÉCOUVERT depuis repo_path (ou le cwd process).

    git remonte l'arborescence pour trouver un repo : depuis un sous-dossier sans .git
    propre, il découvre le repo PARENT. C'est exactement le failure mode F-53 (commit
    « Iteration 1 » atterri dans le repo principal). Expose ce toplevel pour que la
    garde défensive le compare au run dir attendu.
    """
    code, out = _run_git(["rev-parse", "--show-toplevel"], cwd=_cwd_for(repo_path))
    if code != 0 or not out.strip():
        return None
    return os.path.abspath(out.strip())


def _is_isolated(repo_path: Optional[str]) -> bool:
    """True si le repo git découvert a son toplevel == repo_path (ou le cwd process).

    Garantie d'isolation F-53 : on n'écrit JAMAIS dans un repo parent. Comparaison
    insensible à la casse + normalisée (Windows-safe : mixed separators, casse du
    lecteur, slash finaux).
    """
    base = os.path.abspath(repo_path) if repo_path else os.getcwd()
    toplevel = _resolved_toplevel(repo_path)
    if toplevel is None:
        return False
    return os.path.normcase(os.path.normpath(toplevel)) == os.path.normcase(
        os.path.normpath(base)
    )


def init_run_git(repo_path: Optional[str] = None) -> bool:
    """Initialise un git local isolé dans le run dir (dossier du run).

    À appeler UNE FOIS au début du run (avant le premier Coder). Idempotent : si .git
    existe déjà, ne fait rien (safe pour les reprises après crash).

    Args:
        repo_path: Chemin du dossier du run. Si fourni, toutes les opérations git
            utilisent ce chemin comme cwd (cwd-indépendant — recommandé en production,
            on passe ``run_output_dir``). Si None, utilise le cwd process (rétrocompat
            pour tests/standalone ayant déjà ``chdir``-é dans le run dir).

    Returns:
        True si le git est opérationnel ET isolé (toplevel == run dir), False sinon.
        Refuse de « réussir » si git init n'a pas créé un repo isolé (garde F-53).
    """
    # .git déjà présent → en principe isolé (créé par un init_run_git précédent sur ce
    # même run dir). On vérifie l'isolation par sécurité (catch .git worktree pointer).
    if os.path.isdir(_git_dirpath(repo_path)):
        if not _is_isolated(repo_path):
            logger.warning(
                "init_run_git: .git présent mais toplevel ≠ run dir (%s). Refus d'utiliser un repo parent.",
                _resolved_toplevel(repo_path),
            )
            return False
        return True
    code, _ = _run_git(["init", "--quiet"], cwd=_cwd_for(repo_path))
    if code != 0:
        logger.debug("git init échoué — git local indisponible pour ce run.")
        return False
    # Config minimale (git requiert user.email/name pour commit). Valeurs neutres,
    # non persistantes (locales au .git du run, pas global).
    for cfg_args in (
        ["config", "user.email", "coder@graph-orchestrator.local"],
        ["config", "user.name", "Graph Orchestrator Coder"],
        ["config", "commit.gpgsign", "false"],  # pas de signature (CI/headless)
    ):
        _run_git(cfg_args, cwd=_cwd_for(repo_path))
    # GARDE F-53 : le repo créé doit être isolé (toplevel == run dir). Si git init
    # n'a pas créé un repo isolé (découvrirait un parent), on refuse plutôt que de
    # risquer un commit dans le repo principal.
    if not _is_isolated(repo_path):
        logger.warning(
            "init_run_git: git init n'a pas produit un repo isolé (toplevel=%s ≠ run dir). Refus.",
            _resolved_toplevel(repo_path),
        )
        return False
    return True


def commit_iteration(iteration: int, message: str = "", repo_path: Optional[str] = None) -> bool:
    """Commit l'état courant des fichiers du dossier du run.

    À appeler APRÈS chaque exécution du Coder. Crée un commit avec tous les changements
    (ajouts + modifications + suppressions). Premier appel = commit initial (iter 1).

    Args:
        iteration: Numéro d'itération (pour le message de commit).
        message: Message optionnel (sinon auto-généré "Iteration N").
        repo_path: Chemin du run dir (cwd-indépendant). Si None, utilise le cwd process.

    Returns:
        True si le commit a réussi, False sinon (git absent, rien à committer, ou
        **garde F-53 : repo découvert n'est pas le run dir → refus de committer dans un
        repo parent**).
    """
    if not os.path.isdir(_git_dirpath(repo_path)):
        return False
    # GARDE DÉFENSIVE F-53 (cœur du fix) : ne JAMAIS committer si git découvrirait un
    # repo parent (cwd erroné, .git non créé, etc.). Prévient la pollution du repo principal.
    if not _is_isolated(repo_path):
        logger.warning(
            "commit_iteration refusé : toplevel git (%s) ≠ run dir (%s). Pollution du repo parent évitée.",
            _resolved_toplevel(repo_path),
            os.path.abspath(repo_path) if repo_path else os.getcwd(),
        )
        return False
    # git add -A : tous les changements (nouveaux, modifiés, supprimés).
    _run_git(["add", "-A"], cwd=_cwd_for(repo_path))
    msg = message or f"Iteration {iteration}"
    # --allow-empty : au cas où le Coder n'a rien changé (ne fail pas).
    # On ne veut pas crasher le workflow si le commit est vide.
    code, _ = _run_git(["commit", "--quiet", "--allow-empty", "-m", msg], cwd=_cwd_for(repo_path))
    return code == 0


def get_last_diff(max_chars: int = MAX_DIFF_CHARS, repo_path: Optional[str] = None) -> str:
    """Retourne le diff entre l'avant-dernier et le dernier commit (= ce que le Coder
    vient de modifier à l'itération courante).

    À appeler APRÈS commit_iteration, AVANT le Tester/Judge. En itération 1 (1 seul
    commit), retourne "" (pas de diff — c'est la création initiale, le Tester fait un
    test complet). En itération N+1, retourne les hunks modifiés depuis l'iter N.

    Args:
        max_chars: Plafond de caractères (tronque au-delà avec marqueur [...]).
        repo_path: Chemin du run dir (cwd-indépendant). Si None, utilise le cwd process.

    Returns:
        Le diff texte (format git diff, hunks avec contexte), ou "" si :
          - git indisponible / .git absent
          - **garde F-53 : repo découvert ≠ run dir (évite d'injecter le diff du parent)**
          - moins de 2 commits (itération 1)
          - diff vide (rien modifié)
    """
    if not os.path.isdir(_git_dirpath(repo_path)):
        return ""
    # GARDE F-53 (lecture) : ne pas injecter le diff d'un repo parent dans le Tester.
    if not _is_isolated(repo_path):
        logger.debug("get_last_diff: repo non isolé (toplevel=%s) — diff ignoré.", _resolved_toplevel(repo_path))
        return ""
    # HEAD~1..HEAD = diff entre l'avant-dernier et le dernier commit.
    # --stat d'abord pour vérifier qu'il y a des changements (évite un diff vide énorme).
    code_stat, stat = _run_git(["diff", "--stat", "HEAD~1", "HEAD"], cwd=_cwd_for(repo_path))
    if code_stat != 0 or not stat.strip():
        return ""  # moins de 2 commits, ou aucun changement
    # Diff complet avec contexte (hunks). --no-color pour éviter les codes ANSI.
    code, diff = _run_git(["diff", "HEAD~1", "HEAD", "--no-color"], cwd=_cwd_for(repo_path))
    if code != 0 or not diff.strip():
        return ""
    # Tronque si trop long (préserve le début = les changements les plus pertinents).
    if len(diff) > max_chars:
        diff = diff[:max_chars].rsplit("\n", 1)[0] + "\n[... diff tronqué]"
    return diff


def has_git_history(repo_path: Optional[str] = None) -> bool:
    """Indique si le git local a au moins 2 commits (= on peut extraire un diff).

    Utile pour décider si le Tester peut faire un re-test ciblé sur le diff (itération >1)
    ou doit faire un test complet (itération 1).

    Args:
        repo_path: Chemin du run dir (cwd-indépendant). Si None, utilise le cwd process.
    """
    if not os.path.isdir(_git_dirpath(repo_path)):
        return False
    # GARDE F-53 : ne pas compter les commits d'un repo parent.
    if not _is_isolated(repo_path):
        return False
    code, log = _run_git(["rev-list", "--count", "HEAD"], cwd=_cwd_for(repo_path))
    if code != 0:
        return False
    try:
        return int(log.strip()) >= 2
    except ValueError:
        return False
