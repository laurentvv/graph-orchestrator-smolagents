"""Tests unitaires de l'Orphan Repair (Priorité 8 — anti-corruption d'historique).

Un appel d'outil (`tool_use`) sans réponse (`tool_result`) associée fait crasher
l'API LLM au replay d'un checkpoint. Ce test valide que :

1. `repair_orphan_tool_results` (forme "messages" dict) injecte une fausse
   réponse `FAKE_INTERRUPTED` pour chaque appel orphelin, et seulement ceux-là.
2. `repair_orphan_steps` (objets mémoire smolagents / ActionStep) répare les
   étapes avec `tool_calls` sans observation ni erreur.

Déterministes, 0 LLM. Inspiré du blueprint `assert_no_orphan_tool_results`
(référence 16-learn-claude-code s08_context_compact).
"""
from types import SimpleNamespace

from graph_orchestrator.orphan_repair import (
    FAKE_INTERRUPTED,
    repair_orphan_steps,
    repair_orphan_tool_results,
)


def _tool_use(call_id, name="write_file"):
    return {"type": "tool_use", "id": call_id, "name": name}


def _tool_result(call_id, content="ok"):
    return {"type": "tool_result", "tool_use_id": call_id, "content": content}


def _msg(content):
    return {"role": "user", "content": content}


# ==========================================
# Niveau 1 : messages génériques (dict)
# ==========================================
def test_no_orphan_no_change():
    """Historique sain (chaque tool_use a son tool_result) => 0 réparation."""
    messages = [
        _msg([_tool_use("c1"), _tool_result("c1")]),
        _msg([_tool_use("c2"), _tool_result("c2")]),
    ]
    repaired_messages, n = repair_orphan_tool_results(messages)
    assert n == 0
    assert repaired_messages is messages  # même liste, pas de copie


def test_single_orphan_injected():
    """Un tool_use sans réponse => une fausse réponse injectée dans SON message."""
    messages = [_msg([_tool_use("c1"), _tool_use("c2"), _tool_result("c1")])]
    _, n = repair_orphan_tool_results(messages)
    assert n == 1
    # On retrouve la fausse réponse à la fin de la liste de blocs du message.
    blocks = messages[0]["content"]
    last = blocks[-1]
    assert last["type"] == "tool_result"
    assert last["tool_use_id"] == "c2"
    assert last["content"] == FAKE_INTERRUPTED
    # La réponse existante de c1 n'a pas été dupliquée.
    assert sum(1 for b in blocks if b.get("tool_use_id") == "c1") == 1


def test_multiple_orphans_repaired():
    """Plusieurs appels orphelins (y compris sur des messages différents)."""
    messages = [
        _msg([_tool_use("a"), _tool_use("b")]),
        _msg([_tool_use("c"), _tool_result("c"), _tool_use("d")]),
    ]
    _, n = repair_orphan_tool_results(messages)
    assert n == 3  # a, b (msg 0) et d (msg 1) sont orphelins ; c est déjà répondu
    # Le message 0 contenait 2 orphelins (a, b) => 2 fausses réponses ajoutées.
    assert len(messages[0]["content"]) == 4
    # Le message 1 avait 1 orphelin (d).
    assert any(b.get("tool_use_id") == "d" for b in messages[1]["content"])


def test_idempotent_second_pass_no_change():
    """Ré-appliquer sur un historique déjà réparé ne répare plus rien."""
    messages = [_msg([_tool_use("c1")])]
    _, n1 = repair_orphan_tool_results(messages)
    _, n2 = repair_orphan_tool_results(messages)
    assert n1 == 1
    assert n2 == 0


def test_block_with_id_and_name_is_tool_use():
    """Bloc imbriqué (id+name sans type tool_use) est bien détecté comme appel."""
    messages = [
        _msg(
            [
                {"type": "function", "id": "call_x",
                 "function": {"name": "read_file", "arguments": "{}"}}
            ]
        )
    ]
    _, n = repair_orphan_tool_results(messages)
    assert n == 1
    assert messages[0]["content"][-1]["tool_use_id"] == "call_x"


def test_string_content_ignored():
    """Message dont le content est une simple chaîne : pas de crash, pas de change."""
    messages = [{"role": "assistant", "content": "je réfléchis..."}]
    _, n = repair_orphan_tool_results(messages)
    assert n == 0


# ==========================================
# Niveau 2 : objets mémoire smolagents (ActionStep)
# ==========================================
def _step(tool_calls=None, observations=None, error=None, is_final_answer=False):
    return SimpleNamespace(
        tool_calls=tool_calls,
        observations=observations,
        error=error,
        is_final_answer=is_final_answer,
    )


def test_orphan_step_repaired():
    """Étape avec tool_calls mais sans observation/erreur => réparée."""
    steps = [_step(tool_calls=[SimpleNamespace(id="t1", name="write_file", arguments={})])]
    n = repair_orphan_steps(steps)
    assert n == 1
    assert steps[0].observations == FAKE_INTERRUPTED


def test_step_with_observation_not_touched():
    """Étape avec tool_calls ET observation => déjà complète, non-réparée."""
    steps = [_step(tool_calls=[object()], observations="résultat")]  # noqa: F401
    assert repair_orphan_steps(steps) == 0
    assert steps[0].observations == "résultat"


def test_step_with_error_not_touched():
    """Étape avec tool_calls mais error présente => le couple est complet."""
    steps = [_step(tool_calls=[object()], error=ValueError("boom"))]  # noqa: F401
    assert repair_orphan_steps(steps) == 0


def test_step_without_tool_calls_ignored():
    """Étape sans aucun appel d'outil => jamais réparée."""
    steps = [_step(tool_calls=None)]
    assert repair_orphan_steps(steps) == 0


def test_final_answer_step_not_touched():
    """Étape finale (is_final_answer) sans observation => non considérée orpheline."""
    steps = [_step(tool_calls=[object()], is_final_answer=True)]  # noqa: F401
    assert repair_orphan_steps(steps) == 0


# ==========================================
# Niveau 1-bis : forme top-level OpenAI tool_calls (F-104, leçon deer-flow)
# ==========================================
def test_top_level_tool_calls_orphelins_replies_par_message_tool():
    """F-104 : smolagents/OpenAI sérialisent les appels au niveau du message
    (``tool_calls``), pas en blocs de content. Un orphelin dans cette forme
    reçoit un message ``role=tool`` inséré juste après le message assistant."""
    messages = [
        {"role": "user", "content": "fais le tri"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "type": "function",
                 "function": {"name": "write_file", "arguments": "{}"}},
                {"id": "call_2", "type": "function",
                 "function": {"name": "read_file", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
    ]
    _, n = repair_orphan_tool_results(messages)
    assert n == 1  # call_2 orphelin seulement
    # Le message tool injecté est juste après l'assistant (ordre de conversation).
    assert messages[2]["role"] == "tool"
    assert messages[2]["tool_call_id"] == "call_2"
    assert messages[2]["content"] == FAKE_INTERRUPTED
    assert len(messages) == 4


def test_top_level_deux_orphelins_ordre_stable():
    """Deux orphelins top-level : les 2 messages tool sont insérés à la suite,
    indices décroissants (chaque insertion préserve les positions)."""
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "a", "arguments": "{}"}},
                {"id": "c2", "type": "function", "function": {"name": "b", "arguments": "{}"}},
            ],
        },
        {"role": "user", "content": "suite"},
    ]
    _, n = repair_orphan_tool_results(messages)
    assert n == 2
    roles = [m.get("role") for m in messages]
    # assistant, tool(c2), tool(c1), user — les insertions descendantes
    # préservent l'ordre d'appel c1 puis c2.
    assert roles == ["assistant", "tool", "tool", "user"]
    assert messages[1]["tool_call_id"] == "c1"
    assert messages[2]["tool_call_id"] == "c2"


def test_id_unique_meme_id_dans_les_deux_formes_une_seule_reponse():
    """Leçon deer-flow (DanglingToolCallMiddleware) : un appel visible dans les
    DEUX formes (bloc content + top-level) reçoit EXACTEMENT UNE réponse —
    jamais de double ToolMessage pour un même id (= 400 provider)."""
    messages = [
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "dup1", "name": "write_file"}],
            "tool_calls": [
                {"id": "dup1", "type": "function",
                 "function": {"name": "write_file", "arguments": "{}"}},
            ],
        },
    ]
    _, n = repair_orphan_tool_results(messages)
    assert n == 1
    # 1 tool_result en content, 0 message tool dupliqué.
    tool_results = [b for b in messages[0]["content"] if b.get("type") == "tool_result"]
    assert len(tool_results) == 1
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert tool_msgs == []


def test_top_level_entree_invalide_ignoree():
    """Entrées top-level sans id ou sans nom de fonction : ignorées (on ne peut
    pas répondre à un appel sans identifiant)."""
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"type": "function", "function": {"name": "a", "arguments": "{}"}},  # pas d'id
                {"id": "x1", "type": "function", "function": {"arguments": "{}"}},   # pas de nom
                "pas-un-dict",
            ],
        },
    ]
    _, n = repair_orphan_tool_results(messages)
    assert n == 0
    assert len(messages) == 1


def test_top_level_idempotent():
    """Deuxième passe : les messages tool injectés marquent les appels répondus."""
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "k1", "type": "function",
                 "function": {"name": "search_replace", "arguments": "{}"}},
            ],
        },
    ]
    _, n1 = repair_orphan_tool_results(messages)
    _, n2 = repair_orphan_tool_results(messages)
    assert n1 == 1
    assert n2 == 0
    assert len(messages) == 2
