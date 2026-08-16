#!/usr/bin/env python3
"""Vérifie la taille des fichiers de guidance du projet (budgets soft/hard).

Port adapté de `references/deer-flow/scripts/check_agent_guidance.py` (F-103,
plan_usine_logicielle P0-bis « Linter de prompts + budgets de guidance »).
deer-flow borne ses chaînes hiérarchiques d'AGENTS.md ; notre équivalent :

- racine  : AGENTS.md                        — guidance assistant dev   (12/16 Ko soft/hard)
- module  : graph_orchestrator/prompts.py    — rôles + invariants LLM   (24/32 Ko)
- local   : skills/*/SKILL.md                — corps injecté au déclenchement (40/48 Ko)
- chaîne  : prompts.py + SKILL.md eager du Coder — charge system réelle  (80/96 Ko)

La chaîne Coder est la plus chargée du runtime : elle somme le module de
guidance et les corps des skills EAGER (ALWAYS_SKILLS_CODER, importés depuis
graph_orchestrator.skills_loader = source de vérité unique). Les SKILL.md
lazy ne paient leur taxe qu'au déclenchement, ils restent au budget local.
Limite documentée : le bloc prompt inline de nodes.py n'est pas mesurable
statiquement, il n'entre pas dans la chaîne.

Sémantique incrémentale (empruntée à deer-flow, pensée pour l'adoption sur un
repo déjà au-dessus des budgets) : avec --base-ref/--head-ref, un fichier
au-dessus du hard qui n'a PAS grossi vs base = warning (pas error) ; seuls
les dépassements qui croissent échouent. Sans refs (mode local), tout
dépassement du hard = error.

Volet prompt-audit (opt-in --audit-signals) : signaux greppables du framework
Anthropic `prompt-audit` (references/skills/skills/claude-api/shared/
prompt-audit.md). ATTENTION : ces signaux sont calibrés pour des modèles
très littéraux (Claude récents) ; nos petits modèles locaux (4B/9B)
sous-déclenchent et la pression y est souvent LOAD-BEARING. Les signaux sont
donc des warnings non bloquants, opt-in, et chaque message rappelle que le
jugement est requis avant toute suppression.

Usage :
    uv run python scripts/check_agent_guidance.py
    uv run python scripts/check_agent_guidance.py --base-ref origin/main --head-ref HEAD
    uv run python scripts/check_agent_guidance.py --audit-signals --strict-warnings
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Literal, NamedTuple

ROOT_SOFT = 12 * 1024
ROOT_HARD = 16 * 1024
MODULE_SOFT = 24 * 1024
MODULE_HARD = 32 * 1024
LOCAL_SOFT = 40 * 1024
LOCAL_HARD = 48 * 1024
CHAIN_SOFT = 80 * 1024
CHAIN_HARD = 96 * 1024

ROOT_PATH = PurePosixPath("AGENTS.md")
MODULE_PATH = PurePosixPath("graph_orchestrator/prompts.py")
# Ancrage des findings de chaîne (l'entrée module de la chaîne Coder).
CHAIN_ANCHOR = MODULE_PATH

# Volet (a) prompt-audit — signaux greppables, warnings non bloquants opt-in.
# Seuil calibré sur l'état réel du repo (max observé ~1.6 occ/Ko en 2026-08) :
# silencieux aujourd'hui, attrape le bloat futur.
PRESSURE_RE = re.compile(
    r"\b(MUST|NEVER|ALWAYS|CRITICAL|IMPORTANT|OBLIGATOIRES?|INTERDITE?S?|JAMAIS|TOUJOURS)\b"
)
PRESSURE_DENSITY_PER_KB = 4.0
HEDGE_RE = re.compile(
    r"(try to|if possible|ideally|si possible|essayez de|essaye de)", re.IGNORECASE
)
AUDIT_CAVEAT = (
    "signal heuristique prompt-audit : la pression est LEGITIME pour nos petits "
    "modeles locaux qui sous-declenchent - jugement requis avant suppression "
    "(references/skills/skills/claude-api/shared/prompt-audit.md)"
)


class Finding(NamedTuple):
    severity: Literal["error", "warning"]
    code: str
    path: PurePosixPath
    message: str


def normalized_utf8_size(text: str) -> int:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return len(normalized.encode("utf-8"))


def surface_budget(path: PurePosixPath) -> tuple[int, int] | None:
    """Budget (soft, hard) d'une surface de guidance, None si ce n'en est pas une."""
    if path == ROOT_PATH:
        return ROOT_SOFT, ROOT_HARD
    if path == MODULE_PATH:
        return MODULE_SOFT, MODULE_HARD
    if (
        len(path.parts) == 3
        and path.parts[0] == "skills"
        and path.parts[2] == "SKILL.md"
    ):
        return LOCAL_SOFT, LOCAL_HARD
    return None


def guidance_paths(paths: Iterable[PurePosixPath]) -> set[PurePosixPath]:
    return {path for path in paths if surface_budget(path) is not None}


def default_eager_skills() -> tuple[str, ...]:
    """Skills EAGER du Coder depuis la source de vérité (skills_loader)."""
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from graph_orchestrator.skills_loader import ALWAYS_SKILLS_CODER

    return tuple(sorted(ALWAYS_SKILLS_CODER))


def chain_paths(
    eager_skills: Sequence[str],
    available: Iterable[PurePosixPath],
) -> list[PurePosixPath]:
    """Composition de la chaîne Coder : module + corps des skills eager présents."""
    wanted = {PurePosixPath("skills") / name / "SKILL.md" for name in eager_skills}
    chain = {MODULE_PATH} & set(available)
    chain |= wanted & set(available)
    return sorted(chain, key=lambda item: item.as_posix())


def _relevant_change(
    paths: Iterable[PurePosixPath],
    changed_paths: set[PurePosixPath] | None,
) -> bool:
    return changed_paths is None or any(path in changed_paths for path in paths)


def _budget_finding(
    *,
    code: str,
    path: PurePosixPath,
    actual: int,
    soft: int,
    hard: int,
    base_actual: int | None,
    relevant_change: bool,
    label: str,
) -> Finding | None:
    if actual > hard:
        if base_actual is None or actual > base_actual:
            return Finding(
                "error",
                code,
                path,
                f"{label} is {actual} bytes; hard limit is {hard}. Remove inherited or local instructions.",
            )
        if relevant_change:
            return Finding(
                "warning",
                code,
                path,
                f"{label} remains above {hard} bytes at {actual}, but did not grow from {base_actual}.",
            )
        return None
    if actual > soft and relevant_change:
        return Finding(
            "warning",
            code,
            path,
            f"{label} is {actual} bytes; soft limit is {soft} and hard limit is {hard}.",
        )
    return None


def _audit_signal_findings(path: PurePosixPath, text: str) -> list[Finding]:
    """Signaux greppables prompt-audit (groupe 1a/1a-hedges), non bloquants.

    Un finding PAR FICHIER et par signal (agrégation des occurrences, comme
    les budgets) — pas un finding par occurrence, sinon le bruit noie CI.
    """
    findings: list[Finding] = []
    size_kb = max(normalized_utf8_size(text) / 1024, 0.1)
    pressure = len(PRESSURE_RE.findall(text))
    if pressure / size_kb > PRESSURE_DENSITY_PER_KB:
        findings.append(
            Finding(
                "warning",
                "AG101",
                path,
                f"pression {pressure / size_kb:.1f} occ/Ko (seuil {PRESSURE_DENSITY_PER_KB}) "
                f"sur {pressure} occurrences. {AUDIT_CAVEAT}",
            )
        )
    hedges = sorted({match.group(0).lower() for match in HEDGE_RE.finditer(text)})
    if hedges:
        findings.append(
            Finding(
                "warning",
                "AG102",
                path,
                f"{len(hedges)} forme(s) de hedge attachee(s) a des exigences ? "
                f"[{', '.join(hedges)}]. {AUDIT_CAVEAT}",
            )
        )
    return findings


def analyze(
    head_files: Mapping[PurePosixPath, str],
    *,
    base_files: Mapping[PurePosixPath, str] | None = None,
    changed_paths: set[PurePosixPath] | None = None,
    eager_skills: Sequence[str] | None = None,
    audit_signals: bool = False,
) -> list[Finding]:
    """Analyse les surfaces de guidance (contenus -> findings).

    ``head_files`` : mapping chemin -> contenu des surfaces présentes.
    ``base_files`` : état de référence pour la sémantique incrémentale.
    ``changed_paths`` : surfaces touchées (None = tout est considéré changé).
    """
    findings: list[Finding] = []
    surfaces = guidance_paths(head_files)
    base_files = base_files or {}
    base_surfaces = guidance_paths(base_files)
    if eager_skills is None:
        eager_skills = default_eager_skills()

    for path in sorted(surfaces):
        actual = normalized_utf8_size(head_files[path])
        soft, hard = surface_budget(path)  # type: ignore[misc]
        base_actual = (
            normalized_utf8_size(base_files[path]) if path in base_files else None
        )
        file_finding = _budget_finding(
            code="AG001",
            path=path,
            actual=actual,
            soft=soft,
            hard=hard,
            base_actual=base_actual,
            relevant_change=_relevant_change([path], changed_paths),
            label=str(path),
        )
        if file_finding:
            findings.append(file_finding)

        if audit_signals:
            findings.extend(_audit_signal_findings(path, head_files[path]))

    chain = chain_paths(eager_skills, surfaces)
    if chain:
        chain_actual = sum(normalized_utf8_size(head_files[item]) for item in chain)
        base_chain = chain_paths(eager_skills, base_surfaces)
        base_chain_actual = (
            sum(normalized_utf8_size(base_files[item]) for item in base_chain)
            if base_files
            else None
        )
        chain_finding = _budget_finding(
            code="AG002",
            path=CHAIN_ANCHOR,
            actual=chain_actual,
            soft=CHAIN_SOFT,
            hard=CHAIN_HARD,
            base_actual=base_chain_actual,
            relevant_change=_relevant_change(chain, changed_paths),
            label="Effective Coder guidance chain (prompts.py + eager skills)",
        )
        if chain_finding:
            findings.append(chain_finding)

    return sorted(findings, key=lambda finding: (finding.path.as_posix(), finding.code))


def _run_git(repo_root: Path, args: Sequence[str]) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def _parse_paths(output: bytes) -> set[PurePosixPath]:
    return {
        PurePosixPath(item.decode("utf-8", errors="surrogateescape"))
        for item in output.split(b"\0")
        if item
    }


def _worktree_paths(repo_root: Path) -> set[PurePosixPath]:
    return _parse_paths(
        _run_git(repo_root, ["ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    )


def _load_worktree_surfaces(repo_root: Path) -> dict[PurePosixPath, str]:
    files: dict[PurePosixPath, str] = {}
    for path in sorted(guidance_paths(_worktree_paths(repo_root))):
        local_path = repo_root / Path(path.as_posix())
        if local_path.is_file():
            files[path] = local_path.read_text(encoding="utf-8")
    return files


def _load_ref_surfaces(repo_root: Path, ref: str | None) -> dict[PurePosixPath, str]:
    if not ref or set(ref) == {"0"}:
        return {}
    paths = guidance_paths(
        _parse_paths(_run_git(repo_root, ["ls-tree", "-r", "--name-only", "-z", ref]))
    )
    return {
        path: _run_git(repo_root, ["show", f"{ref}:{path.as_posix()}"]).decode("utf-8")
        for path in sorted(paths)
    }


def _changed_paths(
    repo_root: Path,
    base_ref: str | None,
    head_ref: str | None,
    *,
    use_merge_base: bool,
) -> set[PurePosixPath]:
    if base_ref and head_ref:
        if set(base_ref) == {"0"}:
            return guidance_paths(_load_ref_surfaces(repo_root, head_ref))
        revision_range = (
            f"{base_ref}...{head_ref}" if use_merge_base else f"{base_ref}..{head_ref}"
        )
        return guidance_paths(
            _parse_paths(
                _run_git(repo_root, ["diff", "--name-only", "-z", revision_range, "--"])
            )
        )
    # Durcissement vs deer-flow : sur un repo sans commit (HEAD inexistant),
    # `git diff HEAD` échoue — on retombe sur les seuls non-trackés (tout ce
    # qui existe est alors "changé" de facto).
    try:
        tracked = _parse_paths(
            _run_git(repo_root, ["diff", "--name-only", "-z", "HEAD", "--"])
        )
    except RuntimeError:
        tracked = set()
    untracked = _parse_paths(
        _run_git(repo_root, ["ls-files", "--others", "--exclude-standard", "-z"])
    )
    return guidance_paths(tracked | untracked)


def _print_finding(finding: Finding, github_annotations: bool) -> None:
    if github_annotations:
        level = "error" if finding.severity == "error" else "warning"
        print(f"::{level} file={finding.path.as_posix()},line=1,title={finding.code}::{finding.message}")
    print(
        f"{finding.severity.upper()} {finding.code} {finding.path.as_posix()}:1 — {finding.message}"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--base-ref")
    parser.add_argument("--head-ref")
    parser.add_argument("--github-annotations", action="store_true")
    parser.add_argument("--strict-warnings", action="store_true")
    parser.add_argument(
        "--audit-signals",
        action="store_true",
        help="active les signaux greppables prompt-audit (warnings non bloquants)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if bool(args.base_ref) != bool(args.head_ref):
        raise SystemExit("--base-ref and --head-ref must be provided together")

    repo_root = args.repo_root.resolve()
    base_ref, head_ref = args.base_ref, args.head_ref
    try:
        if head_ref:
            head_files = _load_ref_surfaces(repo_root, head_ref)
            base_files = _load_ref_surfaces(repo_root, base_ref)
        else:
            head_files = _load_worktree_surfaces(repo_root)
            base_files = {}
        changed = _changed_paths(
            repo_root,
            base_ref,
            head_ref,
            use_merge_base=bool(args.base_ref),
        )
        findings = analyze(
            head_files,
            base_files=base_files if base_ref else None,
            changed_paths=changed,
            audit_signals=bool(args.audit_signals),
        )
    except (OSError, RuntimeError, UnicodeError) as exc:
        print(f"ERROR AG000 {exc}", file=sys.stderr)
        return 1

    for finding in findings:
        _print_finding(finding, args.github_annotations)
    errors = sum(finding.severity == "error" for finding in findings)
    warnings = sum(finding.severity == "warning" for finding in findings)
    print(f"Agent guidance check: {len(head_files)} surfaces, {errors} errors, {warnings} warnings.")
    return 1 if errors or (warnings and args.strict_warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
