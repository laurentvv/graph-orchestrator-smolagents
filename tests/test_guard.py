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
# Message contextuel (fix TIMINGS_ANALYSE — node_kind="tester")
# ==========================================
def test_detect_idle_step_tester_message_mentions_puppeteer():
    """node_kind='tester' → le message cite les outils Puppeteer, PAS write_file.

    Le Tester souffrait du failure mode 'does not contain any JSON blob' (modèle thinking
    sans tool call). Le message idle historique ne parlait que de write_file/search_replace
    (outils du Coder) → non pertinent pour le Tester. Désormais node_kind='tester' produit
    un message qui guide vers puppeteer_evaluate/final_answer.
    """
    agent = _make_agent([_make_step()])  # idle
    msg = _detect_idle_step(agent, node_kind="tester")
    assert msg is not None
    assert "puppeteer_evaluate" in msg
    assert "puppeteer_navigate" in msg
    assert "final_answer" in msg
    # Le message tester ne doit PAS parler des outils du Coder (sinon confusion).
    assert "write_file" not in msg
    assert "append_file" not in msg


def test_detect_idle_step_coder_message_keeps_write_file():
    """node_kind='coder' (défaut) → message historique préservé (write_file/search_replace).

    Rétro-compatibilité : le Coder ne doit pas voir son message changer.
    """
    agent = _make_agent([_make_step()])  # idle
    msg_coder = _detect_idle_step(agent, node_kind="coder")
    msg_default = _detect_idle_step(agent)  # défaut = coder
    assert msg_coder is not None
    assert "write_file" in msg_coder
    assert msg_coder == msg_default  # le défaut est bien 'coder'


def test_detect_idle_step_tester_productive_step_no_message():
    """node_kind='tester' mais step productif → None (le contexte ne change rien à la détection)."""
    agent = _make_agent([_make_step(tool_calls=[{"name": "puppeteer_evaluate"}])])
    assert _detect_idle_step(agent, node_kind="tester") is None


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


# ==========================================
# run_with_retry : node_kind="tester" active le guard idle Puppeteer
# ==========================================
@pytest.mark.anyio
async def test_run_with_retry_tester_idle_routes_to_fallback():
    """node_kind='tester' + output invalide + step idle → fallback max_steps F-90.

    Évolution F-90 : un Tester qui rend un output invalide (typiquement over-
    exploration du 9B sans final_answer structuré) ne boucle plus sur le guard
    idle (message puppeteer réinjecté N fois en vain). Désormais le fallback
    ``_tester_max_steps_fallback`` dérive un verdict comportemental depuis le
    step history (status=failure par défaut sur step idle sans signal) et
    court-circuite — c'est le fix qui a tué le hang du Tester (post-mortem run9).
    Le guard idle (message puppeteer, unit-testé par ``test_detect_idle_step_*``)
    reste actif pour les nœuds non-tester et les cas sans fallback.
    """
    agent = MagicMock()
    agent.__class__ = type("ToolCallingAgent", (), {})
    agent.name = "tester_test"
    agent.model = MagicMock(model_id="test")
    agent.memory = SimpleNamespace(steps=[_make_step()])  # idle

    run_result = MagicMock()
    run_result.output = "invalide"
    run_result.timing = MagicMock(duration=1.0)
    run_result.token_usage = MagicMock(input_tokens=10, output_tokens=5)

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=AsyncMock(return_value=run_result)):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
            with patch("builtins.print") as mock_print:
                await run_with_retry(
                    agent, "PROMPT", MagicMock, max_retries=1, node_kind="tester"
                )

    # F-90 : le fallback dérive un verdict au lieu d'attendre l'idle message
    # (qui ne serait imprimé qu'au retry suivant, jamais atteint grâce au fallback).
    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "Tester max_steps fallback activé" in printed


# ==========================================
# run_with_retry : timeout wall-clock (fix blocage Tester Chrome DevTools)
# ==========================================
@pytest.mark.anyio
async def test_run_with_retry_timeout_returns_none(monkeypatch):
    """timeout_s expiré → rend (None, None) sans bloquer (fix blocage Chrome DevTools).

    Simule un agent.run qui bloque (sleep long, façon Chrome hung). Sans timeout, le
    test bloquerait indéfiniment. Avec timeout_s=0.1, run_with_retry doit rendre un
    échec propre après ~0.1s pour que le graphe continue (Judge → itération suivante).
    """
    import asyncio as _asyncio

    agent = MagicMock()
    agent.__class__ = type("ToolCallingAgent", (), {})
    agent.name = "tester_test"
    agent.model = MagicMock(model_id="test-model")
    agent.memory = SimpleNamespace(steps=[])

    # Mock asyncio.to_thread : simule un agent.run qui bloque (sleep 10s > timeout).
    async def blocking_to_thread(fn, *args, **kwargs):
        await _asyncio.sleep(10)  # bien au-delà du timeout_s=0.1
        return MagicMock()

    monkeypatch.setattr("graph_orchestrator.nodes.asyncio.to_thread", blocking_to_thread)

    result, metrics = await run_with_retry(
        agent, "PROMPT", MagicMock, max_retries=1,
        node_kind="tester", timeout_s=0.1,
    )

    assert isinstance(result, str) and "TIMEOUT ERROR" in result  # échec propre (pas de blocage)
    assert metrics is None  # aucune métrique collectée (rien n'a terminé)


@pytest.mark.anyio
async def test_run_with_retry_no_timeout_when_unset(monkeypatch):
    """timeout_s=None (défaut) → pas de timeout, comportement historique préservé.

    Les nœuds qui ne passent pas timeout_s (Coder, Judge, Synth) ne doivent pas être
    affectés par le mécanisme de timeout.
    """
    run_result = MagicMock()
    run_result.output = "invalide"
    run_result.timing = MagicMock(duration=1.0)
    run_result.token_usage = MagicMock(input_tokens=10, output_tokens=5)

    agent = MagicMock()
    agent.__class__ = type("CodeAgent", (), {})
    agent.name = "coder_test"
    agent.model = MagicMock(model_id="test-model")
    agent.memory = SimpleNamespace(steps=[])

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=AsyncMock(return_value=run_result)):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
            # timeout_s non fourni (défaut None) → pas de timeout, s'exécute normalement.
            result, metrics = await run_with_retry(agent, "PROMPT", MagicMock, max_retries=1)

    assert result is None  # échec de validation normal (pas un timeout)
    assert metrics is not None  # métriques collectées (le run a terminé)

