"""Tests F-109 — audit visuel matérialisé (outil visual_check + enforcement).

Couverture (0 LLM, 0 réseau) :
  - store _VISUAL_AUDIT : reset / get / append via l'outil
  - _visual_checklist_error : checklist incomplète / verdict False /
    observation creuse / conforme
  - run_with_retry : enforcement au final_answer (checklist vide → bloqué) et
    rappel INJECTÉ au boundary d'attempt (F-109-bis)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from graph_orchestrator.models import CoderOutput
from graph_orchestrator.tools import (
    _VISUAL_AUDIT,
    get_visual_audit,
    reset_visual_audit,
)
from graph_orchestrator.nodes import _visual_checklist_error


def _fill_audit(n: int, verdict: bool = True, observation: str = "30 barres grises visibles dans le canvas"):
    reset_visual_audit()
    for i in range(1, n + 1):
        _VISUAL_AUDIT.append(
            {"criterion_number": i, "verdict": verdict, "observation": observation}
        )


# ==========================================
# Store + helper
# ==========================================

def test_store_reset_et_get():
    reset_visual_audit()
    assert get_visual_audit() == []
    _VISUAL_AUDIT.append({"criterion_number": 1, "verdict": True, "observation": "ok"})
    assert len(get_visual_audit()) == 1
    reset_visual_audit()
    assert get_visual_audit() == []


def test_checklist_error_incomplete():
    reset_visual_audit()
    msg = _visual_checklist_error(6)
    assert msg and "INCOMPLÈTE" in msg and "[1, 2, 3, 4, 5, 6]" in msg


def test_checklist_error_verdict_false():
    _fill_audit(6)
    _VISUAL_AUDIT[2]["verdict"] = False
    msg = _visual_checklist_error(6)
    assert msg and "ÉCHEC" in msg and "3" in msg


def test_checklist_error_observation_creuse():
    _fill_audit(6, observation="ok")
    msg = _visual_checklist_error(6)
    assert msg and "courte" in msg


def test_checklist_conforme():
    _fill_audit(6)
    assert _visual_checklist_error(6) is None


# ==========================================
# Intégration run_with_retry
# ==========================================

def _make_agent(steps):
    agent = MagicMock()
    agent.memory = SimpleNamespace(steps=steps)
    return agent


def _run_result(valid_output):
    rr = MagicMock()
    rr.output = valid_output
    rr.timing = MagicMock(duration=1.0)
    rr.token_usage = MagicMock(input_tokens=10, output_tokens=5)
    return rr


@pytest.mark.anyio
async def test_enforcement_bloque_final_answer_sans_checklist():
    """Le coder loop 1 (60 steps, 0 visual_check) : final_answer valide MAIS
    checklist vide → bloqué + message injecté, pas de retour immédiat."""
    from graph_orchestrator.nodes import run_with_retry

    reset_visual_audit()
    agent = _make_agent([SimpleNamespace(code_action="take_screenshot()", tool_calls=None)])
    # agent.tools contient take_screenshot → is_frontend True (via MagicMock vide : non)
    # → on force en peuplant tools d'un vrai objet nommé.
    shot_tool = SimpleNamespace(name="take_screenshot")
    agent.tools = {"take_screenshot": shot_tool}

    valid_output = CoderOutput(
        task_id="c1", status="success", details="ok", linter_ok=True, vision_ok=True,
    )
    rr = _run_result(valid_output)
    calls = {"n": 0}

    async def counting_to_thread(*a, **kw):
        calls["n"] += 1
        return rr

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=counting_to_thread), \
         patch("graph_orchestrator.nodes.extract_and_validate", return_value=valid_output), \
         patch("builtins.print") as mock_print:
        result, _ = await run_with_retry(
            agent, "PROMPT", CoderOutput, max_retries=2,
            visual_criteria_count=6,
        )

    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "checklist" in printed.lower() or "Checklist" in printed
    # Avec 2 attempts et checklist jamais remplie : le 2e attempt est aussi bloqué
    # → échec du nœud (None) OU waivé selon le chemin — l'essentiel : PAS de
    # retour immédiat au 1er attempt.
    assert calls["n"] >= 2, "le blocage checklist doit consommer un attempt (retry)"


@pytest.mark.anyio
async def test_enforcement_accepte_avec_checklist_complete():
    from graph_orchestrator.nodes import run_with_retry

    _fill_audit(6)
    agent = _make_agent([SimpleNamespace(code_action="take_screenshot()", tool_calls=None)])
    agent.tools = {"take_screenshot": SimpleNamespace(name="take_screenshot")}

    valid_output = CoderOutput(
        task_id="c1", status="success", details="ok", linter_ok=True, vision_ok=True,
    )
    rr = _run_result(valid_output)
    calls = {"n": 0}

    async def counting_to_thread(*a, **kw):
        calls["n"] += 1
        return rr

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=counting_to_thread), \
         patch("graph_orchestrator.nodes.extract_and_validate", return_value=valid_output):
        result, _ = await run_with_retry(
            agent, "PROMPT", CoderOutput, max_retries=2,
            visual_criteria_count=6,
        )

    assert result is valid_output, "checklist complète → succès immédiat"
    assert calls["n"] == 1


@pytest.mark.anyio
async def test_rappel_checklist_injecte_au_boundary():
    """F-109-bis : tentative sans verdict + checklist vide → le rappel
    'CHECKLIST VISUELLE INCOMPLÈTE' est imprimé/injecté au prompt de retry."""
    from graph_orchestrator.nodes import run_with_retry

    reset_visual_audit()
    agent = _make_agent([])
    rr = _run_result("invalide")  # extract_and_validate → None (1er attempt)

    async def to_thread(*a, **kw):
        return rr

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=to_thread), \
         patch("graph_orchestrator.nodes.extract_and_validate", side_effect=[None, None]), \
         patch("builtins.print") as mock_print:
        await run_with_retry(
            agent, "PROMPT", CoderOutput, max_retries=2,
            visual_criteria_count=6,
        )

    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "Visual audit" in printed and "rappel checklist injecté" in printed
