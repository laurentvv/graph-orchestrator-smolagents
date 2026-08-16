"""Checkpoints git par itération Coder, sans contaminer le worktree. F-102.

Port Python natif (Windows-safe, 0 shell) de ``references/open-swe/agent/utils/
turn_checkpoint.py`` : un « tour » = une itération Coder. Au DÉBUT de l'itération
on snapshotte le worktree du run dans la base d'objets sous
``refs/graph-orchestrator/turns/<key>`` — SANS toucher HEAD, l'index réel, ni le
worktree — pour que le Judge relise CE QUE GIT DIT de l'itération (diff structuré
numstat + name-status + contenus base/head par fichier) au lieu de rejouer les
tool-calls du Coder.

POURQUOI UNE REF ET PAS UN SIMPLE COMMIT (complément de F-53 ``git_snapshot``) :
F-53 committe à chaque itération (mute HEAD/index) — c'est sa force (diff texte
HEAD~1..HEAD pour le Tester ciblé) mais ça l'expose à 3 angles morts que ce module
comble : (1) un commit vide ``--allow-empty`` pollue l'historique quand le Coder
n'a rien produit ; (2) l'index réel est verrouillé pendant l'opération (contention
si le Coder lance des commandes git en parallèle) ; (3) un ``git gc`` mi-run peut
récolter un tree nu. Ici : index SCRATCH (``GIT_INDEX_FILE`` temporaire) +
``commit-tree`` + ``update-ref`` — une REF survit à un ``git gc`` mi-run, et le
worktree/HEAD/index restent intouchés.

BEST-EFFORT total (doctrine open-swe) : tout échec → ``None`` / ``status="error"`` /
``status="missing"`` — l'appelur dégrade silencieusement, le workflow ne casse jamais.

ÉCARTS CONSCIENTS vs la référence (documentés) :
- Pas de script POSIX (``mktemp``/boucles for/``printf \\x1e`` séparateurs) : la
  référence exécute TOUT via un sandbox shell distant. Ici chaque étape est un
  subprocess Python natif avec ``cwd=repo_path`` + ``env`` explicite (Windows).
- ``merge_checkpoint`` (registry de thread borné à 100, « earliest wins ») NON
  porté : nous n'avons pas de thread dashboard. Son INVARIANT est encodé au
  niveau de la ref : ``record_turn_checkpoint`` n'avance JAMAIS une ref existante
  (une reprise après crash rejouerait le début d'itération — le premier snapshot
  est le vrai départ du tour, sinon la base du diff glisserait en avant).
- ``_cd_repo`` (découverte d'un repo quelconque) remplacé par ``repo_path``
  explicite + garde d'isolation F-53 (``_is_isolated``) : on refuse TOUTE écriture
  de ref si le repo git découvert n'est pas le run dir (anti-pollution repo
  principal — doctrine F-53, absente de la référence).
- Les blobs ne passent PAS par base64+JSON stdout (transport sandbox python3) :
  ``cat-file --batch`` natif, octets bruts décodés UTF-8 directement.
- Param ``include_contents`` AJOUTÉ : le runtime Judge n'a besoin que du résumé
  numstat/name-status (il a déjà les fichiers complets) — sauter ``cat-file``
  évite de lire jusqu'à 200 blobs pour rien.

BÉNÉFICIAIRE runtime : ``workflows.py`` (snapshot début d'itération + résumé
structuré post-Coder dans ``sub_dict["turn_diff_summary"]``) → ``judge_diff.py``
(bloc « CE QUE GIT DIT » en tête du champ code du Judge). Fonctionne dès
l'itération 1 (base = snapshot pré-Coder, même vide), là où F-53 n'a pas de diff
(< 2 commits).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from typing import Any, List, Mapping, Optional, Sequence, Tuple, Union

from .git_snapshot import _git_dirpath, _is_isolated

logger = logging.getLogger(__name__)

CHECKPOINT_TIMEOUT_SECONDS = 15
DIFF_TIMEOUT_SECONDS = 30

_MAX_FILES = 200
_MAX_FILE_BYTES = 400_000
_UNSAFE_KEY = re.compile(r"[^A-Za-z0-9._-]")

# Namespace de refs propre au projet (jamais poussée, greppable, survit au gc).
_TURNS_NS = "refs/graph-orchestrator/turns"


def _run_git(
    args: List[str],
    cwd: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    timeout: int = 10,
) -> Tuple[int, str]:
    """Exécute git, retourne (exit_code, stdout). Tolérant : jamais d'exception."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode, result.stdout
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        logger.debug("git %s échoué (%s) — ignoré.", args[0], e)
        return 1, ""


def checkpoint_ref(turn_key: str) -> str:
    """Ref du checkpoint pour ``turn_key`` (caractères unsafe → '-', cap 100)."""
    return f"{_TURNS_NS}/{_UNSAFE_KEY.sub('-', turn_key)[:100]}"


def _git_ready(repo_path: Optional[str]) -> bool:
    """True si le run dir a un .git ET que le repo découvert est bien lui-même.

    Garde F-53 : on n'écrit JAMAIS de ref dans un repo parent (cwd erroné, .git
    absent, GIT_DIR, etc.) — même cause racine que le commit « Iteration 1 »
    atterri dans le repo principal (reflog 9e860af).
    """
    if not os.path.isdir(_git_dirpath(repo_path)):
        return False
    if not _is_isolated(repo_path):
        logger.warning(
            "turn_checkpoint refusé : toplevel git ≠ run dir (%s) — pollution du repo parent évitée.",
            repo_path,
        )
        return False
    return True


def _write_worktree_tree(repo_path: Optional[str]) -> Optional[str]:
    """Construit un tree du worktree dans un INDEX SCRATCH. Retourne le sha, ou None.

    ``GIT_INDEX_FILE`` pointe vers un tempfile : le vrai index, HEAD et le worktree
    ne sont JAMAIS touchés (pas de contention de lock avec les git du Coder), et
    les fichiers untracked-non-ignorés comptent (comme ``git add -A`` F-53).
    """
    fd, index_path = tempfile.mkstemp(prefix="go-turn-index-")
    os.close(fd)
    env = {**os.environ, "GIT_INDEX_FILE": index_path}
    try:
        code, _ = _run_git(
            ["rev-parse", "--verify", "-q", "HEAD"],
            cwd=repo_path, env=env, timeout=CHECKPOINT_TIMEOUT_SECONDS,
        )
        read_args = ["read-tree", "HEAD"] if code == 0 else ["read-tree", "--empty"]
        code, _ = _run_git(read_args, cwd=repo_path, env=env, timeout=CHECKPOINT_TIMEOUT_SECONDS)
        if code != 0:
            return None
        # add -A . : tous les changements (nouveaux, modifiés, supprimés).
        _run_git(["add", "-A", "."], cwd=repo_path, env=env, timeout=CHECKPOINT_TIMEOUT_SECONDS)
        code, tree = _run_git(["write-tree"], cwd=repo_path, env=env, timeout=CHECKPOINT_TIMEOUT_SECONDS)
        if code != 0 or not tree.strip():
            return None
        return tree.strip()
    finally:
        try:
            os.remove(index_path)
        except OSError:
            pass


def record_turn_checkpoint(turn_key: str, repo_path: Optional[str] = None) -> Optional[str]:
    """Snapshotte le worktree pour ``turn_key`` ; retourne la ref, ou ``None``.

    Best-effort : git absent / repo non isolé / échec de commande → ``None``.

    REPRISE APRÈS CRASH : si la ref existe déjà, elle N'EST PAS avancée (le premier
    snapshot est le vrai départ du tour — écart consciencieux portant l'invariant
    « earliest wins » de ``merge_checkpoint`` au niveau de la ref, cf. tête de module).
    """
    ref = checkpoint_ref(turn_key)
    if not _git_ready(repo_path):
        return None
    code, existing = _run_git(
        ["rev-parse", "--verify", "-q", ref],
        cwd=repo_path, timeout=CHECKPOINT_TIMEOUT_SECONDS,
    )
    if code == 0 and existing.strip():
        return ref
    tree = _write_worktree_tree(repo_path)
    if tree is None:
        logger.debug("turn checkpoint échoué pour %s (write-tree) — ignoré.", turn_key)
        return None
    # Parent = HEAD si un historique existe (premier snapshot d'un run vide → racine).
    code, _ = _run_git(
        ["rev-parse", "--verify", "-q", "HEAD"],
        cwd=repo_path, timeout=CHECKPOINT_TIMEOUT_SECONDS,
    )
    parent = ["-p", "HEAD"] if code == 0 else []
    code, commit = _run_git(
        ["commit-tree", tree] + parent + ["-m", "graph-orchestrator-turn"],
        cwd=repo_path, timeout=CHECKPOINT_TIMEOUT_SECONDS,
    )
    if code != 0 or not commit.strip():
        return None
    code, _ = _run_git(
        ["update-ref", ref, commit.strip()],
        cwd=repo_path, timeout=CHECKPOINT_TIMEOUT_SECONDS,
    )
    return ref if code == 0 else None


def parse_numstat(raw: str) -> List[Tuple[str, Optional[int], Optional[int]]]:
    """``git diff --numstat -z`` → ``[(path, additions, deletions)]`` ; ``None`` = binaire."""
    stats: List[Tuple[str, Optional[int], Optional[int]]] = []
    for record in raw.split("\0"):
        parts = record.split("\t", 2)
        if len(parts) != 3 or not parts[2]:
            continue
        added, removed, path = parts
        stats.append(
            (
                path,
                None if added == "-" else int(added),
                None if removed == "-" else int(removed),
            )
        )
    return stats


def parse_name_status(raw: str) -> dict:
    """``git diff --name-status -z`` → ``{path: added|removed|modified}``."""
    fields = [field for field in raw.split("\0") if field]
    kinds = {"A": "added", "D": "removed"}
    return {
        fields[i + 1]: kinds.get(fields[i][:1], "modified")
        for i in range(0, len(fields) - 1, 2)
    }


def _decode(value: Any) -> Tuple[Optional[str], bool]:
    """``(contenu, unrenderable)`` pour un côté du résultat ``cat-file`` d'un fichier.

    ``False`` = blob trop gros (>_MAX_FILE_BYTES) → unrenderable. ``None`` = absent.
    Octets bruts (pas de base64 — écart vs référence, cf. tête de module).
    """
    if value is False:
        return None, True
    if not isinstance(value, (bytes, bytearray)):
        return None, False
    try:
        return bytes(value).decode("utf-8"), False
    except UnicodeDecodeError:
        return None, True


def build_diff_files(
    numstat_raw: str,
    name_status_raw: str,
    contents: Optional[Mapping[str, Any]] = None,
) -> List[dict]:
    """Assemble le diff structuré : ``[{path, status, additions, deletions, …}]``."""
    statuses = parse_name_status(name_status_raw)
    files: List[dict] = []
    for path, additions, deletions in parse_numstat(numstat_raw)[:_MAX_FILES]:
        sides = contents.get(path) if isinstance(contents, Mapping) else None
        sides = sides if isinstance(sides, Mapping) else {}
        original, original_bad = _decode(sides.get("base"))
        modified, modified_bad = _decode(sides.get("head"))
        files.append(
            {
                "path": path,
                "previousPath": None,
                "status": statuses.get(path, "modified"),
                "additions": additions or 0,
                "deletions": deletions or 0,
                "originalContent": original,
                "modifiedContent": modified,
                "unrenderable": additions is None or original_bad or modified_bad,
            }
        )
    return files


def _read_blobs(
    repo_path: Optional[str],
    base: str,
    head: str,
    paths: Sequence[str],
) -> dict:
    """``git cat-file --batch`` natif → ``{path: {base: bytes|False|None, head: …}}``.

    Spécs ordonnées (base puis head par fichier), parsing du flux binaire en une
    passe. ``False`` = blob > ``_MAX_FILE_BYTES`` ; ``None`` = objet absent/corrompu.
    """
    specs = [f"{side}:{path}" for path in paths for side in (base, head)]
    try:
        proc = subprocess.run(
            ["git", "cat-file", "--batch"],
            cwd=repo_path,
            input=("\n".join(specs) + "\n").encode(),
            capture_output=True,
            timeout=DIFF_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        logger.debug("cat-file --batch échoué (%s) — contenus ignorés.", e)
        return {}
    buf = proc.stdout
    at = 0
    blobs: List[Union[bytes, bool, None]] = []
    for _ in specs:
        end = buf.find(b"\n", at)
        if end < 0:
            blobs.append(None)
            continue
        header = buf[at:end].decode(errors="replace").split()
        at = end + 1
        if len(header) < 3 or header[1] != "blob":
            blobs.append(None)
            continue
        try:
            size = int(header[2])
        except ValueError:
            blobs.append(None)
            continue
        body = buf[at:at + size]
        at = at + size + 1  # newline qui suit chaque blob
        blobs.append(body if size <= _MAX_FILE_BYTES else False)
    return {
        path: {"base": blobs[i * 2], "head": blobs[i * 2 + 1]}
        for i, path in enumerate(paths)
    }


def read_turn_diff(
    base: str,
    head: Optional[str] = None,
    repo_path: Optional[str] = None,
    include_contents: bool = True,
) -> dict:
    """Fichiers changés entre ``base`` et ``head`` (ou le worktree vivant si ``head=None``).

    Retour : ``{"status": ready|missing|error, "files": [...], "truncated": bool}``.
    ``missing`` = commande git KO (base inconnue…) ; ``error`` = repo indisponible
    ou worktree illisible. Best-effort : jamais d'exception.
    """
    if not _git_ready(repo_path):
        return {"status": "error", "files": [], "truncated": False}
    # head=None → tree du worktree VIVANT (scratch index, sans commit) — c'est le
    # « ce que le tour a changé » jusqu'à maintenant, fidèle à la référence.
    if head is None:
        tree = _write_worktree_tree(repo_path)
        if tree is None:
            return {"status": "error", "files": [], "truncated": False}
        head = tree
    diff_args = ["diff", "--numstat", "-z", "--no-renames", base, head]
    code, numstat_raw = _run_git(diff_args, cwd=repo_path, timeout=DIFF_TIMEOUT_SECONDS)
    if code != 0:
        return {"status": "missing", "files": [], "truncated": False}
    code, name_status_raw = _run_git(
        ["diff", "--name-status", "-z", "--no-renames", base, head],
        cwd=repo_path, timeout=DIFF_TIMEOUT_SECONDS,
    )
    if code != 0:
        return {"status": "missing", "files": [], "truncated": False}
    stats = parse_numstat(numstat_raw)
    paths = [path for path, _, _ in stats[:_MAX_FILES]]
    contents: Mapping[str, Any] = {}
    if include_contents and paths:
        contents = _read_blobs(repo_path, base, head, paths)
    return {
        "status": "ready",
        "files": build_diff_files(numstat_raw, name_status_raw, contents),
        "truncated": len(stats) > _MAX_FILES,
    }


def summarize_turn_diff(diff: Optional[Mapping[str, Any]]) -> List[dict]:
    """Résumé compact du diff structuré pour le Judge : ``[{path, status, +A/-D}]``.

    Retourne ``[]`` si le diff n'est pas ``ready`` (best-effort, jamais d'exception).
    C'est LA clé ``sub_dict["turn_diff_summary"]`` consommée par ``judge_diff.py``.
    """
    if not isinstance(diff, Mapping) or diff.get("status") != "ready":
        return []
    summary: List[dict] = []
    for f in diff.get("files", []):
        if not isinstance(f, Mapping):
            continue
        summary.append(
            {
                "path": str(f.get("path", "")),
                "status": str(f.get("status", "modified")),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "unrenderable": bool(f.get("unrenderable")),
            }
        )
    return summary
