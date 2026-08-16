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


def _top_level_tool_call_id(entry: Any) -> str | None:
    """F-104 (leçon deer-flow) : id d'une entrée top-level ``message["tool_calls"]``.

    OpenAI/smolagents sérialisent aussi les appels d'outil au niveau du MESSAGE
    (pas en blocs de content) : ``{"id": ..., "type": "function", "function":
    {"name": ..., "arguments": ...}}``. Le niveau 1 doit les voir aussi — sinon
    un historique dans cette forme (celle de smolagents ``to_messages``)
    garderait ses orphelins.
    """
    if not isinstance(entry, dict):
        return None
    cid = entry.get("id")
    function = entry.get("function")
    has_name = entry.get("name") is not None or (
        isinstance(function, dict) and function.get("name") is not None
    )
    if cid is None or not has_name:
        return None
    return str(cid)


def repair_orphan_tool_results(messages: List[dict]) -> Tuple[List[dict], int]:
    """Répare les appels d'outil sans réponse dans une liste de messages.

    Détecte les appels sous DEUX formes (une seule passe, dédup par id —
    leçon deer-flow DanglingToolCallMiddleware : ne JAMAIS émettre deux
    réponses pour un même id, quelle que soit la source de détection) :
    - blocs de content ``tool_use`` (Anthropic) / ``function`` (sérialisée) ;
    - entrées top-level ``message["tool_calls"]`` (OpenAI / smolagents).

    Collecte les ids déjà répondus (blocs ``tool_result`` ET messages
    ``role="tool"``), puis injecte une fausse réponse ``FAKE_INTERRUPTED`` pour
    chaque appel orphelin : bloc ``tool_result`` dans le même content pour la
    forme bloc ; message ``{"role": "tool", "tool_call_id": ...}`` inséré juste
    après le message assistant pour la forme top-level.

    Mutates et renvoie ``(messages, nb_reparations)``. Idempotent et déterministe.
    """
    # 1. Collecte des appels déjà répondus (blocs tool_result + messages role=tool).
    answered: set[str] = set()
    for msg in messages:
        for block in _as_blocks(msg.get("content")):
            if block.get("type") == "tool_result":
                cid = _tool_result_call_id(block)
                if cid:
                    answered.add(cid)
        if msg.get("role") == "tool":
            cid = msg.get("tool_call_id")
            if cid is not None:
                answered.add(str(cid))

    # 2. Injection d'une fausse réponse pour chaque appel orphelin. Les ids
    # réparés entrent immédiatement dans `answered` : un appel présent dans les
    # DEUX formes ne reçoit qu'UNE seule réponse (leçon deer-flow).
    repaired = 0
    insertions: List[Tuple[int, int, dict]] = []  # (index d'insertion, séq, message tool)
    seq = 0
    for msg_index, msg in enumerate(messages):
        blocks = msg.get("content")
        if isinstance(blocks, list):
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
        # Forme top-level OpenAI : réponse = message role=tool séparé, inséré
        # juste après le message assistant porteur (ordre de conversation).
        top_calls = msg.get("tool_calls")
        if isinstance(top_calls, list):
            for entry in top_calls:
                cid = _top_level_tool_call_id(entry)
                if cid is None or cid in answered:
                    continue
                insertions.append(
                    (
                        msg_index + 1,
                        seq,
                        {
                            "role": "tool",
                            "tool_call_id": cid,
                            "content": FAKE_INTERRUPTED,
                        },
                    )
                )
                seq += 1
                answered.add(cid)
                repaired += 1

    # Application des insertions en indice DÉCROISSANT, et en séquence
    # DÉCROISSANTE à indice égal : insérer c2 puis c1 au même indice préserve
    # l'ordre d'appel c1→c2 malgré les décalages induits par chaque insertion.
    for index, _seq, tool_msg in sorted(insertions, key=lambda t: (-t[0], -t[1])):
        messages.insert(index, tool_msg)

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

