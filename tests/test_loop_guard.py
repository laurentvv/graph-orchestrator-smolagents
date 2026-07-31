"""Tests unitaires de l'Anti-Loop Cryptographique (Priorité 3 du plan usine logicielle).

Valide le circuit-breaker par hash SHA256 des tool calls. Déterministe, 0 LLM.

Couvre :
- Empreinte SHA256 stable (ToolName + Input normalisé), indépendante de l'ordre des clés.
- Détection de répétition : N appels identiques → déclenchement au seuil.
- Différenciation : même outil, arguments différents → PAS de boucle.
- Différenciation : outils différents, mêmes arguments → PAS de boucle.
- Seuil paramétrable + opt-out (enabled=False → jamais déclenché).
- reset() entre les retries (comportement aligné sur run_with_retry).
- extract_tool_calls_from_step pour ToolCallingAgent (tool_calls) ET CodeAgent (code_action).
- Intégration : run_with_retry interrompt bien sur boucle (mock agent qui boucle).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from graph_orchestrator.loop_guard import (
    LoopGuard,
    compute_tool_call_fingerprint,
    extract_tool_calls_from_step,
)
from graph_orchestrator.models import CoderOutput


# ==========================================
# Empreinte SHA256 (compute_tool_call_fingerprint)
# ==========================================
def test_fingerprint_is_stable():
    """Même (tool, args) → même empreinte, sur plusieurs appels."""
    fp1 = compute_tool_call_fingerprint("write_file", {"path": "a.txt", "content": "x"})
    fp2 = compute_tool_call_fingerprint("write_file", {"path": "a.txt", "content": "x"})
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA256 hex


def test_fingerprint_independent_of_key_order():
    """L'ordre des clés d'un dict d'arguments ne casse pas la détection (sort_keys)."""
    fp1 = compute_tool_call_fingerprint("write_file", {"path": "a", "content": "b"})
    fp2 = compute_tool_call_fingerprint("write_file", {"content": "b", "path": "a"})
    assert fp1 == fp2


def test_fingerprint_different_tools_not_loop():
    """Deux outils différents avec les mêmes args ne sont PAS une boucle."""
    fp1 = compute_tool_call_fingerprint("write_file", {"path": "a"})
    fp2 = compute_tool_call_fingerprint("edit_file", {"path": "a"})
    assert fp1 != fp2


def test_fingerprint_different_args_not_loop():
    """Même outil, args différents → empreintes différentes."""
    fp1 = compute_tool_call_fingerprint("write_file", {"path": "a.txt"})
    fp2 = compute_tool_call_fingerprint("write_file", {"path": "b.txt"})
    assert fp1 != fp2


def test_fingerprint_whitespace_tolerant():
    """Le whitespace de tête/queue sur les valeurs ne doit pas casser la détection
    (les petits LLM ajoutent/suppriment des espaces au hasard)."""
    fp1 = compute_tool_call_fingerprint("write_file", {"content": "  hello  "})
    fp2 = compute_tool_call_fingerprint("write_file", {"content": "hello"})
    assert fp1 == fp2


def test_fingerprint_string_arguments():
    """Arguments passés en JSON-string (cas ToolCallingAgent smolagents)."""
    fp1 = compute_tool_call_fingerprint("write_file", '{"path": "a", "content": "b"}')
    fp2 = compute_tool_call_fingerprint("write_file", {"path": "a", "content": "b"})
    assert fp1 == fp2


# ==========================================
# LoopGuard : détection de répétition
# ==========================================
def test_guard_triggers_at_threshold():
    """Seuil atteint → repeated_action() renvoie un message non-None."""
    guard = LoopGuard(threshold=3, enabled=True)
    assert guard.repeated_action() is None  # rien au départ

    guard.record("write_file", {"path": "a"})
    assert guard.repeated_action() is None  # 1 < 3

    guard.record("write_file", {"path": "a"})
    assert guard.repeated_action() is None  # 2 < 3

    guard.record("write_file", {"path": "a"})
    msg = guard.repeated_action()  # 3 = seuil
    assert msg is not None
    assert "CIRCUIT BREAKER" in msg
    assert "CHANGE D'APPROCHE" in msg


def test_guard_no_trigger_for_varied_actions():
    """Actions variées → jamais de déclenchement, même au-delà du seuil d'appels."""
    guard = LoopGuard(threshold=3, enabled=True)
    for i in range(10):
        guard.record("write_file", {"path": f"file_{i}.txt"})
    assert guard.repeated_action() is None


def test_guard_threshold_configurable():
    """Seuil personnalisé : déclenchement à 2 si threshold=2."""
    guard = LoopGuard(threshold=2, enabled=True)
    guard.record("write_file", {"path": "a"})
    assert guard.repeated_action() is None
    guard.record("write_file", {"path": "a"})
    assert guard.repeated_action() is not None


def test_guard_rejects_threshold_below_2():
    """Seuil < 2 n'a pas de sens (1 = déclenchement au 1er appel = toujours)."""
    with pytest.raises(ValueError):
        LoopGuard(threshold=1)


def test_guard_disabled_never_triggers():
    """Opt-out : enabled=False → aucune détection, même en boucle manifeste."""
    guard = LoopGuard(threshold=3, enabled=False)
    for _ in range(100):
        guard.record("write_file", {"path": "a"})
    assert guard.repeated_action() is None
    assert guard.record("write_file", {"path": "a"}) == ""  # no-op


def test_guard_reset_clears_counts():
    """reset() vide le compteur (entre deux retries d'agent)."""
    guard = LoopGuard(threshold=3, enabled=True)
    guard.record("write_file", {"path": "a"})
    guard.record("write_file", {"path": "a"})
    guard.reset()
    guard.record("write_file", {"path": "a"})
    assert guard.repeated_action() is None  # compteur reparti de 0


# ==========================================
# extract_tool_calls_from_step (lecture des ActionStep smolagents)
# ==========================================
def _make_toolcall(name, arguments):
    """Mock d'un ToolCall smolagents (objet avec .name / .arguments)."""
    return SimpleNamespace(name=name, arguments=arguments)


def _make_step(tool_calls=None, code_action=None):
    return SimpleNamespace(tool_calls=tool_calls, code_action=code_action)


def test_extract_tool_calls_from_toolcalling_agent_step():
    """ToolCallingAgent : step.tool_calls (liste structurée) → liste (name, args)."""
    step = _make_step(tool_calls=[
        _make_toolcall("write_file", {"path": "a.txt", "content": "x"}),
        _make_toolcall("read_file", {"path": "b.txt"}),
    ])
    calls = extract_tool_calls_from_step(step)
    assert len(calls) == 2
    assert calls[0] == ("write_file", {"path": "a.txt", "content": "x"})
    assert calls[1] == ("read_file", {"path": "b.txt"})


def test_extract_tool_calls_from_codeagent_step():
    """CodeAgent : step.code_action (source Python) → noms d'outils détectés."""
    step = _make_step(code_action=(
        "result = write_file(path='index.html', content='<!DOCTYPE html>')\n"
        "print(result)\n"
        "append_file(path='index.html', content='<body></body>')\n"
    ))
    calls = extract_tool_calls_from_step(step)
    # On récupère bien les 2 appels (write_file + append_file).
    names = [c[0] for c in calls]
    assert "write_file" in names
    assert "append_file" in names


def test_extract_tool_calls_empty_step():
    """Step sans tool_calls ni code_action → liste vide (pas de boucle possible)."""
    step = _make_step(tool_calls=None, code_action=None)
    assert extract_tool_calls_from_step(step) == []


# ==========================================
# Intégration : run_with_retry interrompt sur boucle détectée
# ==========================================
@pytest.mark.anyio
async def test_run_with_retry_triggers_loop_breaker():
    """Boucle manifeste (même write_file 3x) → run_with_retry doit l'attraper.

    On mock un agent qui produit 3 steps contenant chacun le même write_file.
    Le LoopGuard doit détecter la répétition et émettre le log "Anti-Loop".
    On patche asyncio.to_thread et extract_and_validate selon le pattern éprouvé
    de test_guard.py (projet utilise anyio, pas pytest-asyncio).
    """
    from graph_orchestrator.loop_guard import LoopGuard
    from graph_orchestrator.nodes import run_with_retry

    # 3 steps identiques = boucle manifeste au seuil 3.
    tc = _make_toolcall("write_file", {"path": "a.txt", "content": "x"})
    steps = [_make_step(tool_calls=[tc]) for _ in range(3)]

    agent = MagicMock()
    agent.__class__ = type("CodeAgent", (), {})  # type(agent).__name__ == "CodeAgent"
    agent.name = "coder_test"
    agent.model = MagicMock(model_id="test-model")
    agent.memory = SimpleNamespace(steps=steps)

    run_result = MagicMock()
    run_result.output = "invalide"  # extract_and_validate retournera None
    run_result.timing = MagicMock(duration=1.0)
    run_result.token_usage = MagicMock(input_tokens=10, output_tokens=5)

    guard = LoopGuard(threshold=3, enabled=True)

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=AsyncMock(return_value=run_result)):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
            with patch("builtins.print") as mock_print:
                await run_with_retry(
                    agent, "PROMPT_INITIAL", CoderOutput, max_retries=1, loop_guard=guard
                )

    # Le log "Anti-Loop" doit être émis (circuit-breaker déclenché).
    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "Anti-Loop" in printed
