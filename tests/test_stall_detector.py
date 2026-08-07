"""Tests du Stall Detector (F-88, Priorité 3-bis du plan usine logicielle).

Couverture (~22 tests, style test_loop_guard.py — une fonction par cas, pas de
parametrize, @pytest.mark.anyio pour async, SimpleNamespace pour les mocks) :

  - enum DeliveryOutcome + frozenset ACCOUNTABLE_OUTCOMES
  - classify_turn (ACCOUNTABLE / PROGRESS / IDLE)
  - compute_material_fingerprint (write/edit/append/multi_replace, non-écriture)
  - StallDetector (threshold floor, record/reset/is_stalled/signal, reproduction,
    disabled, configurable)
  - thread-safety
  - intégration run_with_retry (stall déclenché, validated prime sur stall, no-op)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from graph_orchestrator.models import CoderOutput
from graph_orchestrator.stall_detector import (
    ACCOUNTABLE_OUTCOMES,
    WRITE_TOOLS,
    DeliveryOutcome,
    StallDetector,
    classify_turn,
    compute_material_fingerprint,
)


# ==========================================
# Helpers (mocks step / tool_call, pattern test_loop_guard.py)
# ==========================================

def _make_toolcall(name: str, arguments: dict) -> SimpleNamespace:
    """Mock un ToolCall smolagents (chemin ToolCallingAgent)."""
    return SimpleNamespace(name=name, arguments=arguments)


def _make_step(tool_calls=None, code_action=None) -> SimpleNamespace:
    """Mock un ActionStep smolagents."""
    return SimpleNamespace(tool_calls=tool_calls, code_action=code_action)


def _make_agent_of_type(type_name: str, steps: list) -> MagicMock:
    """Mock un agent dont type(agent).__name__ == type_name.

    Pattern éprouvé test_coder_hardening.py:33-46 : MagicMock().__class__ assign
    NE change PAS type().__name__ — il faut une vraie sous-classe dynamique.
    """
    cls = type(type_name, (MagicMock,), {})
    agent = cls()
    agent.name = f"{type_name.lower()}_test"
    agent.model = MagicMock(model_id="test-model", api_base="http://test")
    agent.memory = SimpleNamespace(steps=steps)
    return agent


# ==========================================
# Enum + frozenset
# ==========================================

def test_delivery_outcome_values():
    """DeliveryOutcome expose 3 valeurs canoniques (accountable/progress/idle)."""
    assert DeliveryOutcome.ACCOUNTABLE.value == "accountable"
    assert DeliveryOutcome.PROGRESS.value == "progress"
    assert DeliveryOutcome.IDLE.value == "idle"


def test_accountable_outcomes_contains_only_accountable():
    """ACCOUNTABLE_OUTCOMES = {ACCOUNTABLE} (seul le matériel compte)."""
    assert ACCOUNTABLE_OUTCOMES == frozenset({DeliveryOutcome.ACCOUNTABLE})
    assert DeliveryOutcome.ACCOUNTABLE in ACCOUNTABLE_OUTCOMES
    assert DeliveryOutcome.PROGRESS not in ACCOUNTABLE_OUTCOMES
    assert DeliveryOutcome.IDLE not in ACCOUNTABLE_OUTCOMES


# ==========================================
# classify_turn
# ==========================================

def test_classify_turn_accountable_for_write():
    """Un turn avec un write_file = ACCOUNTABLE (matériel)."""
    tcs = [("write_file", {"path": "a.txt", "content": "x"})]
    assert classify_turn(tcs) == DeliveryOutcome.ACCOUNTABLE


def test_classify_turn_progress_for_read_only():
    """Un turn avec seulement read/bash = PROGRESS (avance sans livrable)."""
    tcs = [("read_file", {"path": "a.txt"}), ("bash_command", {"command": "ls"})]
    assert classify_turn(tcs) == DeliveryOutcome.PROGRESS


def test_classify_turn_idle_for_empty():
    """Aucun tool call = IDLE."""
    assert classify_turn([]) == DeliveryOutcome.IDLE
    assert classify_turn(None) == DeliveryOutcome.IDLE  # type: ignore[arg-type]


def test_classify_turn_accountable_wins_over_read():
    """Un turn mixte (read + write) = ACCOUNTABLE (le write prime)."""
    tcs = [
        ("read_file", {"path": "a.txt"}),
        ("append_file", {"path": "a.txt", "content": "y"}),
    ]
    assert classify_turn(tcs) == DeliveryOutcome.ACCOUNTABLE


# ==========================================
# compute_material_fingerprint
# ==========================================

def test_material_fingerprint_stable():
    """Même contenu → même hash (stable sur 16 hex chars)."""
    args = {"path": "a.txt", "content": "hello"}
    h1 = compute_material_fingerprint("write_file", args)
    h2 = compute_material_fingerprint("write_file", args)
    assert h1 == h2
    assert len(h1) == 16  # tronqué à 16 hex chars (loopx)


def test_material_fingerprint_differs_on_content():
    """Contenu différent → hash différent (le cœur de la détection de reproduction)."""
    h1 = compute_material_fingerprint("write_file", {"path": "a", "content": "AAA"})
    h2 = compute_material_fingerprint("write_file", {"path": "a", "content": "BBB"})
    assert h1 != h2


def test_material_fingerprint_empty_for_non_write_tool():
    """Un outil non-écriture (read/bash) → '' (pas de matériel)."""
    assert compute_material_fingerprint("read_file", {"path": "a"}) == ""
    assert compute_material_fingerprint("bash_command", {"command": "ls"}) == ""
    assert compute_material_fingerprint("take_screenshot", {}) == ""
    assert compute_material_fingerprint("", {}) == ""


def test_material_fingerprint_search_replace():
    """search_replace hashe old_string + new_string."""
    h1 = compute_material_fingerprint(
        "search_replace", {"path": "a", "old_string": "foo", "new_string": "bar"}
    )
    h2 = compute_material_fingerprint(
        "search_replace", {"path": "a", "old_string": "foo", "new_string": "baz"}
    )
    assert h1 != h2
    assert len(h1) == 16


def test_material_fingerprint_multi_replace():
    """multi_replace hashe la concaténation des (old, new) du list replacements."""
    args = {"path": "a", "replacements": [
        {"old_string": "foo", "new_string": "bar"},
        {"old_string": "baz", "new_string": "qux"},
    ]}
    h1 = compute_material_fingerprint("multi_replace", args)
    # Même contenu réordonné dans le même ordre → même hash.
    h2 = compute_material_fingerprint("multi_replace", args)
    assert h1 == h2
    assert len(h1) == 16


def test_material_fingerprint_string_arguments():
    """Arguments sérialisés en JSON-string (cas ToolCallingAgent) → parsés OK."""
    import json

    args_str = json.dumps({"path": "a", "content": "hello"})
    h1 = compute_material_fingerprint("write_file", {"path": "a", "content": "hello"})
    h2 = compute_material_fingerprint("write_file", args_str)
    assert h1 == h2


# ==========================================
# StallDetector
# ==========================================

def test_stall_detector_rejects_threshold_below_1():
    """threshold < 1 → ValueError (hard floor, loopx safe_threshold = max(1, ...))."""
    with pytest.raises(ValueError):
        StallDetector(threshold=0)


def test_stall_detector_no_stall_initially():
    """Detector fraîchement créé = pas de stall."""
    sd = StallDetector(threshold=2)
    assert sd.is_stalled() is False
    assert sd.signal() is None


def test_stall_detector_progress_turns_trigger_stall():
    """N turns PROGRESS consécutifs (sans matériel) → stall au seuil."""
    sd = StallDetector(threshold=2)
    sd.record(DeliveryOutcome.PROGRESS, "")  # 1 tour gratuit
    assert sd.is_stalled() is False
    sd.record(DeliveryOutcome.PROGRESS, "")  # 2e tour gratuit = stall
    assert sd.is_stalled() is True
    assert sd.signal() is not None
    assert "CIRCUIT BREAKER" in sd.signal()


def test_stall_detector_idle_turns_trigger_stall():
    """N turns IDLE consécutifs → stall ( Idle = pas de matériel nouveau)."""
    sd = StallDetector(threshold=2)
    sd.record(DeliveryOutcome.IDLE, "")
    sd.record(DeliveryOutcome.IDLE, "")
    assert sd.is_stalled() is True


def test_stall_detector_new_material_resets():
    """ACCOUNTABLE avec hash DIFFÉRENT → reset du compteur (matériel nouveau)."""
    sd = StallDetector(threshold=2)
    sd.record(DeliveryOutcome.PROGRESS, "")  # 1
    sd.record(DeliveryOutcome.ACCOUNTABLE, "hashA")  # matériel nouveau → reset
    assert sd.is_stalled() is False


def test_stall_detector_reproduction_triggers_stall():
    """ACCOUNTABLE avec hash IDENTIQUE au précédent → incrément (reproduction).

    C'est le cas que F-36 rate : un write_file rejoué avec contenu identique mais
    input cosmétiquement différent. Le hash d'output le détecte.
    """
    sd = StallDetector(threshold=2)
    sd.record(DeliveryOutcome.ACCOUNTABLE, "hashA")  # 1er write, matériel nouveau → reset
    assert sd.is_stalled() is False
    sd.record(DeliveryOutcome.ACCOUNTABLE, "hashA")  # reproduction → incrément (1)
    assert sd.is_stalled() is False
    sd.record(DeliveryOutcome.ACCOUNTABLE, "hashA")  # 2e reproduction → stall
    assert sd.is_stalled() is True


def test_stall_detector_disabled_never_triggers():
    """enabled=False → record no-op, is_stalled/signal toujours False/None."""
    sd = StallDetector(threshold=2, enabled=False)
    for _ in range(10):
        sd.record(DeliveryOutcome.PROGRESS, "")
    assert sd.is_stalled() is False
    assert sd.signal() is None


def test_stall_detector_threshold_configurable():
    """threshold=3 → stall à 3, pas avant."""
    sd = StallDetector(threshold=3)
    sd.record(DeliveryOutcome.PROGRESS, "")
    sd.record(DeliveryOutcome.PROGRESS, "")
    assert sd.is_stalled() is False
    sd.record(DeliveryOutcome.PROGRESS, "")
    assert sd.is_stalled() is True


def test_stall_detector_reset_clears_state():
    """reset() remet le compteur et le hash à zéro (entre deux retries)."""
    sd = StallDetector(threshold=2)
    sd.record(DeliveryOutcome.PROGRESS, "")
    sd.record(DeliveryOutcome.PROGRESS, "")
    assert sd.is_stalled() is True
    sd.reset()
    assert sd.is_stalled() is False
    # Après reset, un write identique à avant n'est PAS une reproduction
    # (last_material_hash est None → nouveau matériel → reset compteur).
    sd.record(DeliveryOutcome.ACCOUNTABLE, "hashA")
    assert sd.is_stalled() is False


# ==========================================
# Thread-safety (pattern test_read_gate.py / test_idempotency.py)
# ==========================================

def test_stall_detector_thread_safe_concurrent_records():
    """20 threads record concurrent → pas d'exception, état final cohérent."""
    sd = StallDetector(threshold=1000)  # seuil haut pour ne pas déclencher mid-run
    errors: list[Exception] = []

    import threading

    def worker():
        try:
            for i in range(50):
                sd.record(DeliveryOutcome.PROGRESS, "")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    # 20 threads × 50 PROGRESS = 1000 incrémentations → is_stalled True au seuil 1000.
    assert sd.is_stalled() is True


# ==========================================
# Intégration run_with_retry
# ==========================================

@pytest.mark.anyio
async def test_run_with_retry_emits_stall_signal():
    """2 steps sans matériel nouveau dans UN run → run_with_retry émet le log stall.

    Même modèle que test_run_with_retry_triggers_loop_breaker (F-36) : on mocke un
    agent qui produit plusieurs steps PROGRESS (read seulement) dans le même run,
    max_retries=1. Au seuil 2, le stall detector doit émettre son log.
    """
    from graph_orchestrator.nodes import run_with_retry

    # 2 steps PROGRESS (read seulement, pas de write = pas de matériel) = stall au seuil 2.
    tc = _make_toolcall("read_file", {"path": "a.txt"})
    steps = [_make_step(tool_calls=[tc]) for _ in range(2)]

    agent = _make_agent_of_type("CodeAgent", steps)

    run_result = MagicMock()
    run_result.output = "invalide"  # extract_and_validate → None
    run_result.timing = MagicMock(duration=1.0)
    run_result.token_usage = MagicMock(input_tokens=10, output_tokens=5)

    sd = StallDetector(threshold=2, enabled=True)

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=AsyncMock(return_value=run_result)):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
            with patch("builtins.print") as mock_print:
                await run_with_retry(
                    agent, "PROMPT", CoderOutput, max_retries=1, stall_detector=sd,
                )

    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "Stall Detector" in printed, (
        f"le log stall detector doit être émis après 2 steps sans matériel. Printed: {printed}"
    )


@pytest.mark.anyio
async def test_valid_final_answer_wins_over_stall_signal():
    """Un final_answer valide prime sur le signal stall (même principe que F-36).

    Contrat critique : si validated est non-None, le succès est conservé même si
    le stall_detector signale un stall. C'est le miroir de
    test_valid_final_answer_wins_over_loop_guard (test_coder_hardening.py:289).
    """
    from graph_orchestrator.nodes import run_with_retry

    # 2 steps avec write_file identiques (reproduction = stall potentiel au seuil 2).
    tc = _make_toolcall("write_file", {"path": "index.html", "content": "x"})
    steps = [_make_step(tool_calls=[tc]) for _ in range(2)]

    agent = _make_agent_of_type("CodeAgent", steps)

    valid_output = CoderOutput(
        task_id="ts-001", status="success", details="ok",
        linter_ok=True, vision_ok=True,
    )

    run_result = MagicMock()
    run_result.output = valid_output.model_dump_json()
    run_result.timing = MagicMock(duration=1.0)
    run_result.token_usage = MagicMock(input_tokens=10, output_tokens=5)

    call_count = {"n": 0}

    async def counting_to_thread(*a, **kw):
        call_count["n"] += 1
        return run_result

    sd = StallDetector(threshold=1, enabled=True)  # seuil 1 = stall au 1er tour sans matériel nouveau

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=counting_to_thread):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=valid_output):
            result, _metrics = await run_with_retry(
                agent, "PROMPT", CoderOutput, max_retries=3, stall_detector=sd,
            )

    assert result is valid_output, "un final_answer valide doit primer sur le signal stall"
    assert call_count["n"] == 1, "succès au 1er attempt, aucun retry consommé"


@pytest.mark.anyio
async def test_run_with_retry_noop_without_stall_detector():
    """Pas de stall_detector passé → run_with_retry fonctionne comme avant (no-op)."""
    from graph_orchestrator.nodes import run_with_retry

    tc = _make_toolcall("read_file", {"path": "a.txt"})
    steps = [_make_step(tool_calls=[tc])]
    agent = _make_agent_of_type("CodeAgent", steps)

    run_result = MagicMock()
    run_result.output = "invalide"
    run_result.timing = MagicMock(duration=1.0)
    run_result.token_usage = MagicMock(input_tokens=10, output_tokens=5)

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=AsyncMock(return_value=run_result)):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
            with patch("builtins.print"):
                # Pas de stall_detector= → défaut None → no-op, aucune exception.
                result, _metrics = await run_with_retry(
                    agent, "PROMPT", CoderOutput, max_retries=1,
                )

    assert result is None  # extract_and_validate mocké à None → échec attendu


# ==========================================
# Non-régression F-36 (contrats préservés)
# ==========================================

@pytest.mark.anyio
async def test_loop_guard_test_still_passes_with_stall_detector_module_loaded():
    """Charger stall_detector.py ne casse pas le contrat F-36 (LoopGuard intact).

    Vérifie que l'ajout du module ne pollue pas loop_guard.py (modules orthogonaux).
    On reproduit le test test_run_with_retry_triggers_loop_breaker sans stall_detector.
    """
    from graph_orchestrator.loop_guard import LoopGuard
    from graph_orchestrator.nodes import run_with_retry

    tc = _make_toolcall("write_file", {"path": "a.txt", "content": "x"})
    steps = [_make_step(tool_calls=[tc]) for _ in range(3)]

    agent = _make_agent_of_type("CodeAgent", steps)

    run_result = MagicMock()
    run_result.output = "invalide"
    run_result.timing = MagicMock(duration=1.0)
    run_result.token_usage = MagicMock(input_tokens=10, output_tokens=5)

    guard = LoopGuard(threshold=3, enabled=True)

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=AsyncMock(return_value=run_result)):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
            with patch("builtins.print") as mock_print:
                await run_with_retry(
                    agent, "PROMPT_INITIAL", CoderOutput, max_retries=1, loop_guard=guard,
                )

    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "Anti-Loop" in printed  # LoopGuard toujours actif
