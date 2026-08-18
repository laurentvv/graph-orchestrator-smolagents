"""F-120 — Matérialisation du plan : plan.md + task.md dans le run dir.

Transposition déterministe de la compétence « planning-with-files »
(OthmanAdi — https://github.com/OthmanAdi/planning-with-files : task_plan.md /
progress.md / réinjection du plan avant chaque action). Notre usine n'a PAS
besoin des hooks de rappel de la référence : workflows.py CONNAÎT l'état
exact du run, les fichiers sont donc des VUES régénérées à chaque transition
(0 LLM, best-effort, jamais bloquantes).

- plan.md  : miroir FIDÈLE de TOUT l'ArchitectOutput — global_architecture,
  sous-tâches avec description, stratégie (+ sections incremental), checklist
  des fichiers cibles, critères visuels du Coder / fonctionnels du Tester /
  rubric du Judge (F-82), skills sélectionnés (F-57) + statuts de progression.
- task.md  : checklist vivante dérivée de plan.md + journal daté des verdicts
  (miroir du Error Log de la référence : « logger immédiatement, ne jamais
  répéter une action échouée sans muter l'approche »).
- anchor   : bloc COURT réinjecté dans le prompt Coder à chaque itération
  (Goal + sous-tâche courante + checklist fichiers + pointeur plan.md).
  NON redondant : les critères visuels restent injectés par le bloc F-82
  existant (nodes.py build_visual_criteria_block).

BÉNÉFICIAIRE runtime : workflows.py (sync aux transitions) + nodes.py
(anchor dans le prompt Coder). Source de vérité INCHANGÉE : coding_state /
checkpoint F-24 — ces fichiers sont régénérables et ne sont JAMAIS lus par
la logique de run (lecture humaine / post-mortem + ancrage Coder).

ÉCARTS CONSCIENTS vs la référence :
- Pas de findings.md : nos findings = réfutations du KG, déjà réinjectées au
  Coder via feedback_utils (F-47).
- Pas de réinjection par tool-call (hooks PreToolUse) : l'anchor est injecté
  une fois par itération Coder, suffisant à notre granularité.
- Journal task.md tenu en mémoire de run : après crash/reprise, la checklist
  est régénérée depuis le checkpoint mais le journal repart vide (vue non
  critique, documentée).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

PLAN_FILENAME = "plan.md"
TASK_FILENAME = "task.md"

# Bornes de taille : l'anchor doit rester COURT (levier de convergence du 4B —
# post-mortems runs #10/#11 : une référence stable et brève vaut mieux qu'un
# contexte qui gonfle), le journal ne doit pas croître sans limite.
_MAX_GOAL_CHARS = 200
_MAX_DESC_CHARS = 160
_MAX_EVENT_DETAIL_CHARS = 160
_MAX_JOURNAL_ROWS = 50

# Statuts affichés dans plan.md (miroir du vocabulaire planning-with-files).
_STATUS_PENDING = "pending"
_STATUS_IN_PROGRESS = "in_progress"
_STATUS_COMPLETE = "complete"

# Événements du journal task.md (libellés courts, stables pour le post-mortem).
_EVENT_LABELS = {
    "started": "démarrage",
    "lint_refuted": "rejet linter",
    "static_refuted": "rejet static tester",
    "coder_failed": "coder KO",
    "rejected": "rejet juge",
    "approved": "APPROUVÉ",
    "escalated": "escaladé",
    "max_iterations": "max itérations",
}


def derive_goal(task_content: str, max_chars: int = _MAX_GOAL_CHARS) -> str:
    """Goal = cahier des charges aplati et tronqué (1 « phrase » lisible)."""
    flat = " ".join((task_content or "").split())
    if len(flat) <= max_chars:
        return flat
    return flat[:max_chars].rstrip() + "…"


def _one_line(text: str, max_chars: int) -> str:
    flat = " ".join((text or "").split())
    if len(flat) <= max_chars:
        return flat
    return flat[:max_chars].rstrip() + "…"


def _as_arch_dict(architect_result: Any) -> Dict[str, Any]:
    """Normalise ArchitectOutput (modèle Pydantic) ou dict en dict."""
    if not architect_result:
        return {}
    if hasattr(architect_result, "model_dump"):
        return architect_result.model_dump()
    return dict(architect_result)


def _subtask_status(
    subtask: Dict[str, Any], completed_ids: Iterable[str], in_progress_id: Optional[str]
) -> str:
    tid = subtask.get("task_id", "")
    if tid and tid in set(completed_ids or ()):
        return _STATUS_COMPLETE
    if in_progress_id and tid == in_progress_id:
        return _STATUS_IN_PROGRESS
    return _STATUS_PENDING


def make_event(
    subtask_id: str, iteration: Any, event: str, detail: str = ""
) -> Dict[str, Any]:
    """Construit une entrée de journal pour task.md (cap sur le détail)."""
    return {
        "ts": datetime.now().strftime("%H:%M:%S"),
        "subtask": str(subtask_id or "?"),
        "iter": iteration if iteration != "" else "-",
        "event": event,
        "detail": _one_line(detail, _MAX_EVENT_DETAIL_CHARS),
    }


def build_plan_markdown(
    task_content: str,
    architect_result: Any,
    completed_ids: Iterable[str] = (),
    in_progress_id: Optional[str] = None,
) -> str:
    """Markdown de plan.md — miroir fidèle de TOUT l'ArchitectOutput.

    Aucun champ d'ArchitectTask n'est omis : si l'Architecte ajoute un jour un
    critère, il apparaîtra ici (test anti-perte tests/test_plan_files.py).
    """
    arch = _as_arch_dict(architect_result)
    subtasks: List[Dict[str, Any]] = list(arch.get("subtasks") or [])
    lines: List[str] = ["# Plan de l'Architecte", ""]

    plan_id = arch.get("plan_id")
    if plan_id:
        lines.append(f"*Plan ID :* `{plan_id}`")
        lines.append("")

    lines.append(f"**Goal :** {derive_goal(task_content) or '—'}")
    lines.append("")

    global_arch = (arch.get("global_architecture") or "").strip()
    if global_arch:
        lines.extend(["## Architecture globale", "", global_arch, ""])

    lines.extend(["## Sous-tâches", ""])
    for i, st in enumerate(subtasks, 1):
        status = _subtask_status(st, completed_ids, in_progress_id)
        lines.append(f"### {i}. {st.get('task_id', '?')} — **Status:** {status}")
        lines.append("")

        desc = (st.get("description") or "").strip()
        if desc:
            lines.append(desc)
            lines.append("")

        target_files = st.get("target_files") or []
        if target_files:
            lines.append("**Fichiers cibles :**")
            done = status == _STATUS_COMPLETE
            for path in target_files:
                mark = "x" if done else " "
                lines.append(f"- [{mark}] `{path}`")
            lines.append("")

        lines.append(f"**Stratégie :** `{st.get('strategy') or 'simple'}`")
        sections = st.get("sections") or []
        if sections:
            lines.append(
                "**Sections (incremental) :** " + ", ".join(f"`{s}`" for s in sections)
            )

        for key, label in (
            ("skills", "Skills Coder"),
            ("tester_skills", "Skills Tester"),
            ("judge_skills", "Skills Judge"),
        ):
            vals = st.get(key) or []
            if vals:
                lines.append(f"**{label} :** " + ", ".join(f"`{v}`" for v in vals))

        vsc = st.get("visual_success_criteria") or []
        if vsc:
            lines.extend(["", "**Critères visuels (Coder) :**"])
            lines.extend(f"- {c}" for c in vsc)

        ftc = st.get("functional_test_criteria") or []
        if ftc:
            lines.extend(["", "**Critères fonctionnels (Tester) :**"])
            lines.extend(f"- {c}" for c in ftc)

        rubric = (st.get("acceptance_rubric") or "").strip()
        if rubric:
            lines.extend(["", f"**Rubric Judge :** {rubric}"])

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_task_markdown(
    architect_result: Any,
    completed_ids: Iterable[str] = (),
    in_progress_id: Optional[str] = None,
    events: Iterable[Dict[str, Any]] = (),
) -> str:
    """Markdown de task.md — checklist vivante dérivée de plan.md + journal."""
    arch = _as_arch_dict(architect_result)
    subtasks: List[Dict[str, Any]] = list(arch.get("subtasks") or [])
    completed = set(completed_ids or ())
    done = sum(1 for st in subtasks if st.get("task_id") in completed)

    lines = [
        "# Task Checklist",
        "",
        f"**Progression :** {done}/{len(subtasks)} sous-tâche(s) approuvée(s)",
        "",
        "Dérivé de `plan.md` — régénéré par l'usine à chaque transition (F-120).",
        "",
    ]
    for i, st in enumerate(subtasks, 1):
        tid = st.get("task_id", "?")
        mark = "x" if tid in completed else " "
        files = ", ".join(f"`{f}`" for f in (st.get("target_files") or []))
        suffix = f" ({files})" if files else ""
        state = ""
        if mark == " " and in_progress_id and tid == in_progress_id:
            state = " — in_progress"
        lines.append(f"- [{mark}] **{i}. {tid}**{suffix}{state}")
    lines.append("")

    journal = list(events or ())
    if journal:
        lines.extend(
            [
                "## Journal du run",
                "",
                "| Heure | Sous-tâche | Itér | Événement | Détail |",
                "|---|---|---|---|---|",
            ]
        )
        for ev in journal[-_MAX_JOURNAL_ROWS:]:
            label = _EVENT_LABELS.get(ev.get("event", ""), ev.get("event", "?"))
            detail = str(ev.get("detail", "")).replace("|", "\\|")
            lines.append(
                f"| {ev.get('ts', '')} | {ev.get('subtask', '')} | "
                f"{ev.get('iter', '-')} | {label} | {detail} |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_plan_files(
    run_output_dir: str,
    task_content: str,
    architect_result: Any,
    completed_ids: Iterable[str] = (),
    in_progress_id: Optional[str] = None,
    events: Iterable[Dict[str, Any]] = (),
) -> Tuple[Optional[str], Optional[str]]:
    """Écrit/réécrit plan.md + task.md dans le run dir. Best-effort total :
    toute erreur IO est tracée puis avalée — JAMAIS d'exception, JAMAIS
    bloquant pour le run (les fichiers sont des vues régénérables).

    Retour : (chemin plan.md ou None si échec, chemin task.md ou None).
    """
    plan_path: Optional[str] = None
    task_path: Optional[str] = None

    try:
        plan_path = os.path.join(run_output_dir, PLAN_FILENAME)
        content = build_plan_markdown(
            task_content,
            architect_result,
            completed_ids=completed_ids,
            in_progress_id=in_progress_id,
        )
        with open(plan_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as exc:  # best-effort : vue régénérable, jamais fatale
        print(f"    [~] F-120 : écriture {PLAN_FILENAME} ignorée ({exc})")
        plan_path = None

    try:
        task_path = os.path.join(run_output_dir, TASK_FILENAME)
        content = build_task_markdown(
            architect_result,
            completed_ids=completed_ids,
            in_progress_id=in_progress_id,
            events=events,
        )
        with open(task_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as exc:
        print(f"    [~] F-120 : écriture {TASK_FILENAME} ignorée ({exc})")
        task_path = None

    return plan_path, task_path


def build_coder_anchor(
    task_id: str,
    description: str,
    target_files: Iterable[str] = (),
    strategy: str = "simple",
    goal: str = "",
) -> str:
    """Bloc COURT réinjecté dans le prompt Coder à CHAQUE itération.

    Stable par construction (mêmes entrées → même bloc) : c'est le point fixe
    du post-mortem #10/#11 — le 4B garde une référence qui ne gonfle pas.
    Volontairement SANS les critères visuels : le bloc F-82 existant les
    injecte déjà (anti-redondance, testée).
    """
    files = list(target_files or [])
    lines = ["### PLAN GLOBAL (ancrage stable — F-120, identique à chaque itération)"]
    derived = derive_goal(goal)
    if derived:
        lines.append(f"**Goal :** {derived}")
    lines.append(
        f"**Sous-tâche courante :** `{task_id}` — {_one_line(description, _MAX_DESC_CHARS)}"
    )
    if files:
        lines.append("**Checklist fichiers :** " + ", ".join(f"`{f}`" for f in files))
    lines.append(
        f"**Stratégie :** `{strategy or 'simple'}` — plan complet et critères : `{PLAN_FILENAME}`"
    )
    return "\n".join(lines) + "\n"
