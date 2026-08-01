"""Orphan Repair — Anti-corruption d'historique (Priorité 8, P8).

Lors d'un rechargement de checkpoint ou d'un replay, un appel d'outil
(`tool_use`) peut se retrouver SANS réponse (`tool_result`) associée : le modèle
a émis l'appel, mais le processus a été interrompu avant que le résultat soit
enregistré. Renvoyé tel quel à l'API LLM, ce couple asymétrique fait crasher le
graphe entier (erreur 400 / échec de validation conversationnelle) — le pire
scénario décrit dans `plan_usine_logicielle.md` Priorité 8.

Ce module est la couche *Orphan Repair* : il scanne l'historique et, pour chaque
appel d'outil orphelin, injecte une fausse réponse
`{"status": "error", "error": "Interrompu"}` pour permettre à l'agent de reprendre
au lieu de planter.

Inspiré de la référence **16-learn-claude-code** s08_context_compact
(préservation explicite des paires `tool_use`/`tool_result`, test
`assert_no_orphan_tool_results`) et du blueprint qm (compaction qui conserve les
paires). 100 % Python natif, 0 LLM, déterministe et testable isolément.

Deux niveaux d'application :
- `repair_orphan_tool_results(messages)` : opère sur la forme "messages"
  générique (liste de dicts `{role, content}` avec blocs `tool_use`/`tool_result`)
  — le format sérialisé envoyé à l'API et celui des checkpoints.
- `repair_orphan_steps(steps)` : opère sur les objets mémoire smolagents
  (`memory.steps` : list[ActionStep] avec `.tool_calls` / `.observations` /
  `.error` / `.is_final_answer`). C'est le point d'accroche de `run_with_retry`.
"""

from __future__ import annotations

from typing import Any, List, Tuple

# Fausse réponse injectée pour un appel d'outil orphelin. Écho du message
# "Interrompu" préconisé dans le plan pour permettre à l'agent de reprendre.
FAKE_INTERRUPTED = '{"status": "error", "error": "Interrompu"}'


# ==========================================
# Niveau 1 : forme "messages" générique (API / checkpoint)
# ==========================================
def _as_blocks(content: Any) -> List[dict]:
    """Normalise un `content` en liste de blocs (dict). Tout autre type -> []."""
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    if isinstance(content, dict):
        return [content]
    return []


def _is_tool_use_block(block: dict) -> bool:
    """Un bloc représente un appel d'outil s'il n'est PAS une réponse et qu'il
    porte un identifiant + un nom d'outil. Détecte :
    - la forme `{"type": "tool_use", "id": ..., "name": ...}` (Anthropic) ;
    - la forme sérialisée `{"type": "function", "id": ..., "function": {name...}}`
      (OpenAI / smolagents ToolCall.dict()).
    """
    if block.get("type") == "tool_result":
        return False
    if block.get("type") == "tool_use":
        return True
    has_id = block.get("id") is not None
    has_name = block.get("name") is not None or (
        isinstance(block.get("function"), dict)
        and block.get("function", {}).get("name") is not None
    )
    return has_id and has_name


def _tool_result_call_id(block: dict) -> str | None:
    """Identifiant de l'appel que ce bloc de réponse répond, ou None.

    Gère les trois clés rencontrées : `tool_use_id` (Anthropic), `tool_call_id`
    (OpenAI) et `id` (forme générique / sérialisée)."""
    cid = block.get("tool_use_id") or block.get("tool_call_id") or block.get("id")
    return str(cid) if cid is not None else None

def repair_orphan_tool_results(messages: List[dict]) -> Tuple[List[dict], int]:
    """Répare les appels d'outil sans réponse dans une liste de messages.

    Scan les blocs `tool_result` pour construire l'ensemble des appels déjà
    répondus, puis injecte une fausse réponse `FAKE_INTERRUPTED` pour chaque bloc
    `tool_use` sans réponse associée (directement dans la même liste `content`
    du message, pour conserver l'ordre de conversation).

    Mutates et renvoie `(messages, nb_reparations)`. Idempotent et déterministe.
    """
    # 1. Collecte des appels déjà répondus.
    answered: set[str] = set()
    for msg in messages:
        for block in _as_blocks(msg.get("content")):
            if block.get("type") == "tool_result":
                cid = _tool_result_call_id(block)
                if cid:
                    answered.add(cid)

    # 2. Injection d'une fausse réponse pour chaque appel orphelin.
    repaired = 0
    for msg in messages:
        blocks = msg.get("content")
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict) or not _is_tool_use_block(block):
                continue
            cid = block.get("id")
            if cid is None or str(cid) in answered:
                continue
            blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": cid,
                    "content": FAKE_INTERRUPTED,
                }
            )
            answered.add(str(cid))
            repaired += 1

    return messages, repaired


# ==========================================
# Niveau 2 : objets mémoire smolagents (memory.steps / ActionStep)
# ==========================================
def _is_orphan_step(step: Any) -> bool:
    """Un ActionStep est orphelin si un appel d'outil a été émis sans réponse
    (ni `observations`, ni `error`) et sans être une réponse finale."""
    if not bool(getattr(step, "tool_calls", None)):
        return False
    if getattr(step, "observations", None) is not None:
        return False
    if getattr(step, "error", None) is not None:
        return False
    if getattr(step, "is_final_answer", False):
        return False
    return True


def repair_orphan_steps(steps: List[Any]) -> int:
    """Répare les appels d'outil orphelins dans `memory.steps`.

    Pour chaque ActionStep avec des `tool_calls` mais sans `observations` ni
    `error`, injecte la fausse observation `FAKE_INTERRUPTED`. Ainsi
    `step.to_messages()` produira bien la paire `tool_call`/`tool_response` et
    l'API LLM ne crashera pas au replay.

    Renvoie le nombre d'étapes réparées. Idempotent et déterministe.
    """
    repaired = 0
    for step in steps:
        if _is_orphan_step(step):
            step.observations = FAKE_INTERRUPTED
            repaired += 1
    return repaired

