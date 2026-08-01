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
