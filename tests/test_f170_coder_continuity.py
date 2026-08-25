"""F-170 — Le Coder n'a pas autorité pour arrêter un run (mandat run v4).

Run v4 (2026-08-25, logs/run_coding_2026-08-25_121003) : UsageLimitExceeded à
40 requêtes après 27 min → ``return {"status": "failure", "reason": "Coder
crash"}`` → Linter/Static/Tester/Judge JAMAIS exécutés alors que le livrable
était écrit sur disque (compteur comparaisons corrigé, testé navigateur).

Deux garde-fous, testés ici sans LLM :

- α (coder_pydantic) : sur UsageLimitExceeded, le verdict final est ARRACHÉ
  dans un appel borné (historique capturé rejoué, aucun outil, budget propre
  de 3 requêtes) au lieu de rendre None ;
- ε (workflows) : plus AUCUN ``return`` sur mort du Coder — le graphe continue
  (synthèse CoderOutput honnête + événement DuckDB ``coder/error``) vers
  Linter/Static/audits/Judge ; une réfutation déterministe relance le Coder à
  l'itération suivante (mécanisme existant).
"""

import asyncio
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from graph_orchestrator.coder_pydantic import (
    _BUDGET_SALVAGE_PROMPT,
    _run_agent_with_budget_salvage,
)
from graph_orchestrator.models import (
    ArchitectOutput,
    ArchitectTask,
    CodeJudgeOutput,
    CoderOutput,
    RouterOutput,
    SecurityOutput,
)
from graph_orchestrator.workflows import run_coding_workflow


# ==========================================
# 1. α — sauvetage post-budget (helper isolé, fake agent)
# ==========================================

class _FakeUsageLimits:
    """Capture les UsageLimits passées à agent.run (assertion request_limit)."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _fake_settings(max_steps=40):
    s = SimpleNamespace(coder_max_steps=max_steps)
    return s


class TestBudgetSalvage:
    def test_prompt_forces_honest_toolless_verdict(self):
        """Le prompt de sauvetage interdit les outils et exige l'honnêteté
        sur les vérifications non faites (leçon run v4 : le rituel visuel
        non convergent ne doit pas devenir un mensonge de synthèse)."""
        p = _BUDGET_SALVAGE_PROMPT
        assert "NO TOOLS" in p
        assert "final_result" in p
        assert "linter_ok=false" in p and "vision_ok=false" in p
        assert "files already written on disk" in p

    def test_budget_exceeded_salvages_final_verdict(self):
        """UsageLimitExceeded au run principal → 2e appel borné avec
        l'historique rejoué → verdict CoderOutput retourné (pas None)."""
        from pydantic_ai.exceptions import UsageLimitExceeded

        verdict = CoderOutput(
            task_id="st1", status="failure",
            details="budget épuisé, fichiers écrits mais rituel visuel inachevé",
        )
        calls = []

        class FakeAgent:
            async def run(self, user_prompt, usage_limits=None, message_history=None):
                calls.append({"prompt": user_prompt, "limits": usage_limits,
                              "history": message_history})
                if len(calls) == 1:
                    raise UsageLimitExceeded(
                        "The next request would exceed the request_limit of 40")
                return SimpleNamespace(output=verdict)

        result = asyncio.run(_run_agent_with_budget_salvage(
            FakeAgent(), "prompt initial", _fake_settings(40)))

        assert result is not None and result.output is verdict
        assert len(calls) == 2
        # 2e appel : prompt de sauvetage, historique rejoué, budget propre borné.
        assert calls[1]["prompt"] == _BUDGET_SALVAGE_PROMPT
        assert calls[1]["history"] == []           # capture vide : fake agent sans instrumentation
        assert calls[1]["limits"].request_limit == 3
        # 1er appel : le budget nominal du Coder.
        assert calls[0]["limits"].request_limit == 40
        assert calls[0]["limits"].tool_calls_limit == 120

    def test_salvage_failure_returns_none(self):
        """Budget épuisé PUIS sauvetage qui crash → None (le graphe ε continue
        sur l'état disque — jamais d'exception vers le workflow)."""
        from pydantic_ai.exceptions import UsageLimitExceeded

        class FakeAgent:
            async def run(self, user_prompt, usage_limits=None, message_history=None):
                if "NO TOOLS" in user_prompt:
                    raise RuntimeError("llama-server mort pendant le sauvetage")
                raise UsageLimitExceeded("request_limit of 40")

        result = asyncio.run(_run_agent_with_budget_salvage(
            FakeAgent(), "prompt", _fake_settings(40)))
        assert result is None

    def test_guard_abort_returns_none_without_salvage(self):
        """GuardAbort (boucle stérile) reste un échec propre immédiat : le
        sauvetage n'est PAS déclenché (1 seul appel)."""
        from graph_orchestrator.coder_pydantic_guards import GuardAbort

        calls = []

        class FakeAgent:
            async def run(self, user_prompt, usage_limits=None, message_history=None):
                calls.append(user_prompt)
                raise GuardAbort("idle breaker : 3 tours stériles")

        result = asyncio.run(_run_agent_with_budget_salvage(
            FakeAgent(), "prompt", _fake_settings(40)))
        assert result is None and len(calls) == 1

    def test_transport_crash_returns_none_without_salvage(self):
        """Un crash transport quelconque n'active pas le sauvetage (seul le
        budget épuisé est sauvable — les autres échecs restent historiques)."""
        calls = []

        class FakeAgent:
            async def run(self, user_prompt, usage_limits=None, message_history=None):
                calls.append(user_prompt)
                raise ConnectionError("API injoignable")

        result = asyncio.run(_run_agent_with_budget_salvage(
            FakeAgent(), "prompt", _fake_settings(40)))
        assert result is None and len(calls) == 1

    def test_normal_result_returned_asis(self):
        """Sans exception, le résultat du run principal est retourné tel quel
        (1 seul appel — le sauvetage ne perturbe pas le chemin nominal)."""
        nominal = SimpleNamespace(output=CoderOutput(
            task_id="st1", status="success", details="ok"))
        calls = []

        class FakeAgent:
            async def run(self, user_prompt, usage_limits=None, message_history=None):
                calls.append(user_prompt)
                return nominal

        result = asyncio.run(_run_agent_with_budget_salvage(
            FakeAgent(), "prompt", _fake_settings(60)))
        assert result is nominal and len(calls) == 1


# ==========================================
# 2. ε — continuation du graphe (workflow E2E, nœuds mockés)
#    Pattern tests/test_escalation.py (aucun appel LLM réel).
# ==========================================

def _seed_tasks():
    return [{
        "id": "T1",
        "content": "Crée un visualiseur Bubble Sort en HTML/JS vanilla.",
        "target_files": ["index.html"],
    }]


def _settings(escalation_enabled=True):
    from graph_orchestrator.config import Settings
    return Settings(
        output_dir=tempfile.mkdtemp(prefix="f170_runs_"),
        local_api_base="http://x/v1", local_reasoning_api_base="http://x/v1",
        local_api_key="sk", fast_model_id="m", reasoning_model_id="m",
        reasoning_max_tokens=8, fast_max_tokens=8, coder_temperature=0.2,
        llm_timeout_s=1.0, judge_confidence_threshold=0.5,
        worker_max_retries=1, adversary_count=1, adversary_threshold=0.5,
        max_iterations=3, hitl_enabled=False, hitl_nodes="synth",
        kg_path=":memory:", workflow_mode="coding", log_level="LOW",
        fresh_start=True,
        test_timeout_s=120, stderr_head_lines=20, stderr_tail_lines=20,
        feedback_max_chars=2000, escalation_enabled=escalation_enabled,
    )


def _setup_workflow_mocks(monkeypatch, coder_behavior=None, linter_fails=False,
                          approve=True):
    """Mocke tous les nœuds. ``coder_behavior`` contrôle le Coder :
    None (crash technique), 'failure' (verdict échec honnête), 'success'."""
    import graph_orchestrator.dspy_nodes as dspy_mod
    import graph_orchestrator.linter as linter_mod
    import graph_orchestrator.nodes as nodes_mod
    import graph_orchestrator.static_tester as static_mod
    import graph_orchestrator.workflows as wf_mod

    monkeypatch.setattr(wf_mod, "build_fast_model", lambda s: "FAKE_FAST")
    monkeypatch.setattr(wf_mod, "build_reasoning_model", lambda s: "FAKE_REASON")

    counters = {"coder": 0, "tester": 0, "judge": 0, "linter": 0}

    async def fake_router(content, model, s):
        return RouterOutput(language="HTML"), None
    monkeypatch.setattr(dspy_mod, "execute_router_node", fake_router)

    async def fake_prompt_refiner(raw, model, s):
        return None, None
    monkeypatch.setattr(dspy_mod, "execute_prompt_refiner_node", fake_prompt_refiner)

    async def fake_drafter(sub, model, s):
        return None, None  # pas de draft → Coder sans plan injecté (échec gracieux)
    monkeypatch.setattr(dspy_mod, "execute_drafter_node", fake_drafter)

    async def fake_architect(task, model, s):
        return ArchitectOutput(
            plan_id="p1", global_architecture="1 fichier",
            subtasks=[ArchitectTask(task_id="st1", description="Bubble Sort",
                                    target_files=["index.html"])],
        ), None
    monkeypatch.setattr(dspy_mod, "execute_architect_node", fake_architect)

    async def fake_coder(sub, model, s):
        counters["coder"] += 1
        if coder_behavior is None:
            return None, None  # crash technique (run v4)
        return CoderOutput(
            task_id=sub["id"],
            status=coder_behavior,
            details=("budget épuisé (verdict arraché)" if coder_behavior == "failure"
                     else "code généré"),
        ), None
    monkeypatch.setattr(nodes_mod, "execute_coder_node", fake_coder)

    def fake_linter(sub, s):
        counters["linter"] += 1
        status = "failure" if linter_fails else "success"
        return SimpleNamespace(status=status, details=f"lint {status}"), None
    monkeypatch.setattr(linter_mod, "execute_linter_node", fake_linter)

    def fake_static(sub, s):
        return SimpleNamespace(status="success", details="static ok"), None
    monkeypatch.setattr(static_mod, "execute_static_tester_node", fake_static)

    async def fake_tester(sub, model, s):
        counters["tester"] += 1
        return CoderOutput(task_id=sub["id"], status="success", details="tests ok"), None
    async def fake_security(sub, model, s):
        return SecurityOutput(task_id=sub["id"], is_secure=True, vulnerabilities=[]), None
    monkeypatch.setattr(nodes_mod, "execute_tester_node", fake_tester)
    monkeypatch.setattr(dspy_mod, "execute_security_reviewer_node", fake_security)

    async def fake_judge(sub, test_res, sec_res, model, s):
        counters["judge"] += 1
        return CodeJudgeOutput(
            task_id=sub["id"], is_approved=approve, final_feedback="ok structuré."
        ), None
    monkeypatch.setattr(dspy_mod, "execute_code_judge_node", fake_judge)

    async def fake_escalation(sub, failure_history, model, s):
        return None, None
    monkeypatch.setattr(dspy_mod, "execute_escalation_node", fake_escalation)

    return counters


class TestCoderCrashContinuity:
    def test_crash_then_judge_approves(self, monkeypatch):
        """Le cas du run v4 : Coder crashé (None) mais livrable écrit →
        Linter/Static/Tester/Judge exécutés → Judge approuve → SUCCESS.
        Avant F-170 : return immédiat 'Coder crash', 0 audit."""
        counters = _setup_workflow_mocks(monkeypatch, coder_behavior=None, approve=True)
        out, _ = asyncio.run(run_coding_workflow(_seed_tasks(), _settings()))

        assert out["final_results"][0]["status"] == "success"
        assert counters["coder"] == 1   # une seule itération : verdict direct
        assert counters["tester"] == 1  # le Tester a bien audité
        assert counters["judge"] == 1   # le Judge a rendu un verdict

    def test_crash_then_linter_refutes_retries_coder(self, monkeypatch):
        """Coder crashé + livrable cassé (Linter échoue) → réfutation
        déterministe → le Coder est RELANCÉ jusqu'à max_iterations (3) —
        le graphe ne meurt plus à la première mort du Coder."""
        counters = _setup_workflow_mocks(
            monkeypatch, coder_behavior=None, linter_fails=True, approve=True)
        out, _ = asyncio.run(run_coding_workflow(_seed_tasks(), _settings()))

        assert counters["coder"] == 3          # 3 itérations, pas 1
        assert counters["judge"] == 0          # court-circuit Shift Left respecté
        # Épuisement : status final ≠ success (escalation désactivée → repli
        # historique 'max_iterations_reached', escalade mockée à None).
        assert out["final_results"][0]["status"] != "success"

    def test_honest_failure_verdict_also_continues(self, monkeypatch):
        """Un verdict CoderOutput status='failure' (ex: arraché post-budget)
        ne tuait pas non plus le graphe avant F-170 — il le tuait. Désormais
        le graphe audite l'état disque comme pour un crash."""
        counters = _setup_workflow_mocks(monkeypatch, coder_behavior="failure", approve=True)
        out, _ = asyncio.run(run_coding_workflow(_seed_tasks(), _settings()))

        assert out["final_results"][0]["status"] == "success"
        assert counters["tester"] == 1 and counters["judge"] == 1

    def test_crash_journalised_in_duckdb(self, monkeypatch):
        """Post-mortem run v4 : la base était muette sur une mort Coder.
        F-170 journalise un événement (coder, error) au moment du crash."""
        logged = []

        class _StubDB:
            def log_event(self, run_id, node, event_type, message):
                logged.append((node, event_type, message))

        import graph_orchestrator.event_stream as ev_mod
        monkeypatch.setattr(ev_mod, "get_event_db", lambda: _StubDB())

        _setup_workflow_mocks(monkeypatch, coder_behavior=None, approve=True)
        asyncio.run(run_coding_workflow(_seed_tasks(), _settings()))

        assert any(node == "coder" and etype == "error" and "st1" in msg
                   for node, etype, msg in logged)
