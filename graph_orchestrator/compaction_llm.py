"""Compact LLM sémantique opt-in (F-116 volet C, ex-F-86).

Branche enfin les briques dormantes F-101 :
- ``compaction_prompts`` (prompts opencode réécrits POUR PETITS MODÈLES :
  identité simple, 5 sections ordonnées, règles de fold claude-science en
  SEARCH QUERIES, ``select_head_recent`` par entrée ENTIÈRE) ;
- ``CompactionBudget`` (hermes : verdict d'efficacité rendu UNIQUEMENT par
  l'usage provider réel — remboursement sur ``prompt_tokens`` vérifié,
  breaker 2 strikes/fallbacks).

DÉSACTIVÉ par défaut (``COMPACTION_LLM_ENABLED=false``) : la compaction
déterministe 0-LLM (``compaction.py`` v3) reste la défaut — coût nul,
déterminisme. Ce volet ne s'active que dans le chemin de RÉCUPÉRATION
overflow de ``run_with_retry`` : résumer sémantiquement l'historique au
lieu de le compacter mécaniquement, pour préserver les décisions/intentions
qu'un clip ne garde pas. Échec quelconque → repli immédiat sur le
déterministe (``apply_soft_retry_reset``).

Écarts consciencieux vs ex-F-86 (documentés) : pas de graphe Mermaid L2 ni
de cascade par score L1 (TencentDB) ce cycle — le résumé textuel 5 sections
+ les tombstones déterministes (``collect_dead_ends``) couvrent le besoin ;
à rouvrir si un run réel montre une perte sémantique.
"""

from typing import List, Optional, Tuple

from .compaction import ActionStep, _synthetic_action_step
from .compaction_guards import CompactionBudget
from .compaction_prompts import (
    SUMMARY_SYSTEM_PROMPT,
    build_summary_prompt,
    select_head_recent,
)

__all__ = ["llm_compact_history", "_steps_to_entries"]

# Fenêtre récente conservée intacte (chars ≈ 3k tokens) — cohérente avec le
# preserveRecentBudget kilocode borné [2k, 8k] tokens pour un contexte 32k.
KEEP_RECENT_CHARS = 12_000
# Cap défensif du contexte envoyé au summarizer (le prompt LLM doit rester
# bien plus petit que la fenêtre qu'on cherche à libérer).
CONTEXT_CAP_CHARS = 40_000
KEEP_TAIL_STEPS = 4
# Un résumé plus court que ça est suspect (réponse tronquée/dérive) → refus.
MIN_SUMMARY_CHARS = 80


def _steps_to_entries(memory) -> List[str]:
    """Sérialise l'historique en entrées texte (une par step, ordre préservé)."""
    entries: List[str] = []
    for step in memory.steps:
        if isinstance(step, ActionStep):
            mo = str(getattr(step, "model_output", "") or "")
            obs = str(getattr(step, "observations", "") or "")
            err = getattr(step, "error", None)
            entry = f"assistant: {mo}"
            if obs:
                entry += f"\nobservation: {obs}"
            if err:
                entry += f"\nerror: {err}"
            entries.append(entry)
        else:
            task = str(getattr(step, "task", "") or "")
            if task:
                entries.append(f"user: {task}")
    return entries


def _extract_text(response) -> str:
    """Extraction défensive du texte d'une réponse modèle smolagents."""
    if response is None:
        return ""
    if isinstance(response, str):
        return response.strip()
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts).strip()
    return str(response).strip()


def llm_compact_history(
    agent,
    budget: Optional[CompactionBudget] = None,
    keep_recent_chars: int = KEEP_RECENT_CHARS,
    keep_tail: int = KEEP_TAIL_STEPS,
) -> Tuple[bool, str]:
    """Compacte l'historique de l'agent en un résumé LLM structuré (opt-in).

    Retourne ``(ok, note)`` : ``ok=True`` = historique réécrit (TaskSteps +
    step-résumé + queue intacte), ``ok=False`` = échec — l'appelant replie
    sur ``apply_soft_retry_reset`` (déterministe). Ne lève JAMAIS (fail-open).

    Verdict d'efficacité (hermes) : ``budget.charge()`` au départ réel,
    ``on_compaction_committed(made_progress)`` au commit ; le remboursement
    viendra de ``on_real_usage(prompt_tokens)`` alimenté par la requête
    suivante (câblé dans ``run_with_retry`` après un run réussi).
    """
    try:
        from .config import settings

        max_tokens = int(settings.compaction_llm_max_tokens)
    except Exception:
        max_tokens = 1024

    memory = getattr(agent, "memory", None)
    model = getattr(agent, "model", None)
    if memory is None or model is None or not hasattr(model, "generate"):
        return False, "agent sans mémoire ou sans modèle"
    if not memory.steps:
        return False, "mémoire vide"

    if budget is not None and (budget.exhausted() or budget.blocked()):
        return False, "budget de compaction épuisé ou bloqué (breaker hermes)"

    entries = _steps_to_entries(memory)
    split = select_head_recent(entries, keep_recent_chars)
    if split is None:
        return True, "rien à résumer (tout tient dans la fenêtre récente)"
    head, _recent = split

    prompt = build_summary_prompt(context=head[:CONTEXT_CAP_CHARS])
    messages = [
        {"role": "system", "content": [{"type": "text", "text": SUMMARY_SYSTEM_PROMPT}]},
        {"role": "user", "content": [{"type": "text", "text": prompt}]},
    ]

    if budget is not None:
        budget.charge()
    try:
        try:
            response = model.generate(messages=messages, max_tokens=max_tokens)
        except TypeError:
            response = model.generate(messages=messages)
    except Exception as exc:
        if budget is not None:
            budget.on_compaction_committed(False, used_fallback=True)
        return False, f"échec génération : {exc}"

    summary_text = _extract_text(response)
    if len(summary_text) < MIN_SUMMARY_CHARS:
        if budget is not None:
            budget.on_compaction_committed(False, used_fallback=True)
        return False, f"résumé vide/tronqué ({len(summary_text)} chars)"

    # Commit : TaskSteps conservés + step-résumé + queue intacte.
    steps = list(memory.steps)
    action_steps = [s for s in steps if isinstance(s, ActionStep)]
    tail_first = action_steps[-max(1, min(keep_tail, len(action_steps)))]
    tail_start = steps.index(tail_first)
    head_steps = steps[:tail_start]
    tail_steps = steps[tail_start:]

    summary_step = _synthetic_action_step(getattr(steps[-1], "step_number", 0) + 1)
    summary_step.model_output = (
        "[Context compacted by LLM summary (F-116 opt-in)]\n" + summary_text
    )
    summary_step.observations = (
        "Résumé sémantique de l'historique. Les valeurs précises vivent dans "
        "le résumé ci-dessus — ne les reconstruis pas de mémoire, relis-les "
        "si nécessaire."
    )

    kept_head = [s for s in head_steps if not isinstance(s, ActionStep)]
    memory.steps = kept_head + [summary_step] + tail_steps
    if budget is not None:
        budget.on_compaction_committed(True, used_fallback=False)
    return True, summary_text
