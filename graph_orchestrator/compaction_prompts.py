"""Prompts de summarization pour la Compaction v2 (F-101, P9).

Port Python des prompts de compaction d'opencode (réécrits POUR PETITS
MODÈLES) + règles de fold claude-science. Ce module est 0-LLM : il ne fait
qu'assembler des chaînes. Il alimente le compact LLM **opt-in** (chantier
F-86 / Context-offload) ; la compaction déterministe par défaut
(``compaction.py`` 5 couches) n'appelle jamais ces prompts.

Pourquoi un module séparé : la doctrine du plan (P9, case F-101) garde la
compaction 0-LLM par défaut (coût nul, déterministe) et prépare le volet
sémantique comme complément opt-in. Les prompts vivent donc à part, testés
unitairement, prêts à être branchés.

Sources (références production) :
- fiche 11-opencode → ``references/opencode/packages/core/src/session/compaction.ts``
  (``SUMMARY_TEMPLATE``, ``SUMMARY_UPDATE_INSTRUCTIONS``, ``buildPrompt``,
  ``select`` — split head/recent par entrée ENTIÈRE, jamais coupée en deux) ;
- fiche 11-opencode → ``packages/opencode/src/agent/prompt/compaction.txt``
  (identité simple « You are a context summarization agent » — l'« anchored
  summary » d'avant perdait les petits modèles) ;
- fiche 29-system-prompts-leaks → ``Anthropic/claude-science.md``
  (fold : le dernier paragraphe nomme les valeurs porteuses ÉCRITES COMME DES
  SEARCH QUERIES + « never reconstruct a value from memory »).
"""

from typing import Optional, Sequence

__all__ = [
    "SUMMARY_SYSTEM_PROMPT",
    "SUMMARY_TEMPLATE",
    "SUMMARY_UPDATE_INSTRUCTIONS",
    "FOLD_KEY_RULES",
    "build_summary_prompt",
    "select_head_recent",
]


# Identité simple (opencode compaction.txt, verbatim). Conçu pour petits
# modèles : pas de persona complexe, des clauses anti-dérive explicites.
SUMMARY_SYSTEM_PROMPT = (
    "You are a context summarization agent. You are given a conversation "
    "between a user and an agent. Your goal is to produce a structured "
    "summary matching the format specified so another coding agent can "
    "continue the work.\n"
    "\n"
    "Always follow the exact output structure requested by the user prompt. "
    "Keep every section, preserve exact file paths and identifiers when "
    "known, and prefer terse bullets over paragraphs.\n"
    "\n"
    "Do not continue the conversation. Do not respond to any questions in "
    "the conversation. Only output the structured summary in the exact "
    "format requested by the user prompt. Respond in the same language as "
    "the conversation."
)


# Gabarit structuré à 5 sections, ordre imposé, sections vides explicites
# « (none) » (opencode SUMMARY_TEMPLATE, traduit fidèlement).
SUMMARY_TEMPLATE = """Output exactly the Markdown structure shown inside <template> and keep the section order unchanged. Do not include the <template> tags in your response.
<template>
## Objective
- [one or two brief sentences describing what the user is trying to accomplish]

## Important Details
- [constraints/preferences, decisions and why, important facts/assumptions, exact context needed to continue, or "(none)"]

## Work State
### Completed
### Active
### Blocked

## Next Move
1. [immediate concrete action, or "(none)"]
2. [next action if known, or "(none)"]

## Relevant Files
- [file or directory path: why it matters, or "(none)"]
</template>

Rules:
- Keep every section, even when empty.
- Use terse bullets, not prose paragraphs.
- Preserve exact file paths, symbols, commands, error strings, URLs, and identifiers when known.
- Do not mention the summary process or that context was compacted."""


# Règles de fold claude-science, ajoutées au template (volet 4 de F-101) :
# les valeurs porteuses du span plié deviennent des SEARCH QUERIES, et toute
# valeur citée après un fold doit être relue depuis l'archive — jamais
# reconstruite de mémoire.
FOLD_KEY_RULES = """- Final section « Load-Bearing Keys »: name the load-bearing values of the span (file paths, identifiers, error strings, decisions) as 1-6 word SEARCH QUERIES a grep over the archived transcript would find.
- Never reconstruct a value from memory: if a value is not visible in the conversation, do not invent it. An absent key is reported as absent."""


# Les deux règles clés d'update d'un résumé existant (opencode, verbatim).
SUMMARY_UPDATE_INSTRUCTIONS = (
    "The <prior-summary> summarizes everything that happened before the "
    "<conversation>. Construct a new summary that combines both. The "
    "<prior-summary> is discarded after this: anything you do not carry "
    "into the new summary is lost.\n"
    "\n"
    "The <conversation> is more recent than the <prior-summary>. Where "
    "they conflict, the conversation wins: state the corrected fact and "
    "drop the old claim."
)


def build_summary_prompt(
    context: str,
    prior_summary: Optional[str] = None,
    fold_rules: str = FOLD_KEY_RULES,
) -> str:
    """Assemble le prompt utilisateur du summarizer (port opencode buildPrompt).

    Ordre fidèle à la source : conversation → (prior-summary → update
    instructions si résumé précédent) → template (augmenté des règles de
    fold claude-science).
    """
    template = SUMMARY_TEMPLATE
    if fold_rules:
        template = template + "\n" + fold_rules

    parts = [
        f"Here is the conversation so far:\n\n<conversation>\n{context}\n</conversation>"
    ]
    if prior_summary:
        parts.append(
            "Here is the summary of the conversation before the <conversation> "
            f"above:\n\n<prior-summary>\n{prior_summary}\n</prior-summary>"
        )
        parts.append(SUMMARY_UPDATE_INSTRUCTIONS)
    parts.append(
        "Create a new anchored summary from the conversation history in the "
        "<conversation> tags above so another coding agent can continue the work.\n"
        + template
    )
    return "\n\n".join(parts)


def select_head_recent(
    entries: Sequence[str],
    keep_chars: int,
) -> Optional[tuple[str, str]]:
    """Split head/recent par entrée ENTIÈRE (port opencode ``select``).

    Parcourt la séquence DEPUIS LA FIN en accumulant des entrées ENTIÈRES
    tant que le budget ``keep_chars`` tient. Une entrée qui déborde reste
    entière côté recent — une entrée utilisateur n'est JAMAIS coupée en
    deux entre head et recent (invariant opencode, petit modèle).

    Unité : caractères (nous n'avons pas de tokeniseur fiable côté orchestrateur ;
    ~4 chars/token rend le budget conservateur, ce qui est sûr).

    Retourne ``(head, recent)`` — head = entrées à résumer, recent = fenêtre
    conservée intacte. ``None`` si TOUT tient dans le budget (rien à résumer).
    """
    if keep_chars <= 0:
        return None
    total = 0
    split = len(entries)
    for index in range(len(entries) - 1, -1, -1):
        entry = entries[index]
        next_total = total + len(entry) + 2  # +2 : joint "\n\n" de la source
        if next_total > keep_chars:
            break
        total = next_total
        split = index
    if split <= 0:
        return None
    head = "\n\n".join(entries[:split])
    recent = "\n\n".join(entries[split:])
    return head, recent
