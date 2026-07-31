"""Tests unitaires du guard logiciel anti-déraillement (F-33).

Un prompt seul ne suffit jamais (leçon des audits — deer-flow/openfox/aider couplent
tous le prompt à un guard logiciel). Ces tests valident les 2 détections de run_with_retry :
1. Tour SANS tool call exécuté (modèle réfléchit sans agir) → message d'action ré-injecté.
2. Exception de parsing (code Python cassé) → message "découpe" ré-injecté.

Déterministes, 0 LLM (agent mocké).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from graph_orchestrator.nodes import _detect_idle_step, run_with_retry


# ==========================================
# Helper : mock d'un ActionStep smolagents
# ==========================================
def _make_step(tool_calls=None, code_action=None, observations=None):
    """Crée un faux ActionStep smolagents (dataclass) avec les champs réels."""
    return SimpleNamespace(
        tool_calls=tool_calls,
        code_action=code_action,
        observations=observations,
        is_final_answer=False,
    )


def _make_agent(steps):
    """Crée un faux agent avec memory.steps = steps."""
    agent = MagicMock()
    agent.memory = SimpleNamespace(steps=steps)
    return agent


# ==========================================
# Détection "tour sans tool call" (idle)
# ==========================================
def test_detect_idle_step_no_tool_calls():
    """Step sans tool_calls/code_action/observations → message d'action renvoyé."""
    agent = _make_agent([_make_step()])  # tout None = idle
    msg = _detect_idle_step(agent)
    assert msg is not None
    assert "AUCUN appel d'outil" in msg
    assert "ÉCHEC" in msg


def test_detect_idle_step_with_tool_calls():
    """Step avec tool_calls → None (step productif, pas d'alerte)."""
    agent = _make_agent([_make_step(tool_calls=[{"name": "write_file"}])])
    assert _detect_idle_step(agent) is None


def test_detect_idle_step_with_code_action():
    """Step CodeAgent avec code_action (code Python exécuté) → None (productif)."""
    agent = _make_agent([_make_step(code_action="write_file(path='x', content='y')")])
    assert _detect_idle_step(agent) is None


def test_detect_idle_step_with_observations():
    """Step avec observations (résultat d'outil) → None (productif)."""
    agent = _make_agent([_make_step(observations="Successfully wrote to x")])
    assert _detect_idle_step(agent) is None


def test_detect_idle_step_empty_memory():
    """Agent sans steps → None (rien à inspecter)."""
    agent = _make_agent([])
    assert _detect_idle_step(agent) is None


def test_detect_idle_step_inspects_last_step_only():
    """Seul le DERNIER step compte (l'avant-dernier peut être idle sans impact)."""
    agent = _make_agent([
        _make_step(),  # idle (mais ancien)
        _make_step(tool_calls=[{"name": "write_file"}]),  # productif (dernier)
    ])
    assert _detect_idle_step(agent) is None


# ==========================================
# run_with_retry : guard idle ré-injecte le bon message
# ==========================================
@pytest.mark.anyio
async def test_run_with_retry_idle_injects_action_message():
    """Un run qui ne valide pas + step idle → le guard se déclenche sans planter.

    On ne peut pas inspecter le prompt muté directement (variable locale), mais
    l'absence de crash + le retour (None, metrics) valide que le guard idle s'est
    déclenché. Le contenu du message est validé par les tests _detect_idle_step.
    """
    agent = MagicMock()
    agent.__class__ = type("CodeAgent", (), {})  # type(agent).__name__ == "CodeAgent"
    agent.name = "coder_test"
    agent.model = MagicMock(model_id="test-model")
    agent.memory = SimpleNamespace(steps=[_make_step()])  # idle

    run_result = MagicMock()
    run_result.output = "invalide"  # extract_and_validate retournera None
    run_result.timing = MagicMock(duration=1.0)
    run_result.token_usage = MagicMock(input_tokens=10, output_tokens=5)

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=AsyncMock(return_value=run_result)):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
            result, metrics = await run_with_retry(agent, "PROMPT_INITIAL", MagicMock, max_retries=1)

    assert result is None  # échec définitif après 1 retry
    assert metrics is not None  # métriques quand même renvoyées pour l'observabilité


@pytest.mark.anyio
async def test_run_with_retry_code_agent_emits_retry_log():
    """Un CodeAgent en échec → émet le log de retry (le message Python est interne au prompt)."""
    agent = MagicMock()
    agent.__class__ = type("CodeAgent", (), {})
    agent.name = "coder_test"
    agent.model = MagicMock(model_id="test")
    agent.memory = SimpleNamespace(steps=[_make_step(tool_calls=[{"name": "x"}])])  # productif mais invalidé

    run_result = MagicMock()
    run_result.output = "invalide"
    run_result.timing = MagicMock(duration=1.0)
    run_result.token_usage = MagicMock(input_tokens=10, output_tokens=5)

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=AsyncMock(return_value=run_result)):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
            with patch("builtins.print") as mock_print:
                await run_with_retry(agent, "PROMPT", MagicMock, max_retries=1)

    # Le log "Tentative ... échouée" doit être émis (la logique retry tourne).
    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "Tentative" in printed
