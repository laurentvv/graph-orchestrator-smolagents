"""Test d'intégration de la troncature dans la boucle de feedback — Priorité 2.

Le scénario critique : un bug génère un GROS feedback (traceback de 500 lignes).
Ce feedback est écrit dans DuckDB par le Judge, puis relu et injecté au Coder à
l'itération suivante. On valide deux invariants :
  1. Le contenu écrit en DuckDB est INTÉGRAL (pas de collision de dedup_key).
  2. L'historique injecté au Coder est TRONQUÉ (≤ feedback_max_chars).

Sans la troncature, le contexte du Coder explose au bout du 3ème essai.
"""

import asyncio
import os

import pytest

import graph_orchestrator.nodes as nodes_mod
import graph_orchestrator.dspy_nodes as dspy_mod
import graph_orchestrator.workflows as wf_mod
from graph_orchestrator.models import (
    ArchitectOutput, ArchitectTask, CoderOutput, CodeJudgeOutput,
    RouterOutput, SecurityOutput,
)


def _settings(feedback_max_chars=500, kg_path=":memory:"):
    from graph_orchestrator.config import Settings
    return Settings(
        ollama_api_base="http://x/v1", ollama_reasoning_api_base="http://x/v1",
        ollama_api_key="sk", fast_model_id="m", reasoning_model_id="m",
        reasoning_max_tokens=8, fast_max_tokens=8, coder_temperature=0.2,
        llm_timeout_s=1.0, judge_confidence_threshold=0.5,
        worker_max_retries=1, adversary_count=1, adversary_threshold=0.5,
        max_iterations=3, hitl_enabled=False, hitl_nodes="synth",
        kg_path=kg_path, workflow_mode="coding", log_level="LOW",
        fresh_start=True,
        test_timeout_s=30, stderr_head_lines=20, stderr_tail_lines=20,
        feedback_max_chars=feedback_max_chars,
    )


class TestTruncationInLoop:

    def test_big_feedback_truncated_for_coder_but_intact_in_db(self, tmp_path, monkeypatch):
        """Gros feedback : tronqué à l'injection au Coder, intégral en base."""
        # Builders factices (pas de connexion Ollama).
        monkeypatch.setattr(wf_mod, "build_fast_model", lambda s: "FAKE_FAST")
        monkeypatch.setattr(wf_mod, "build_reasoning_model", lambda s: "FAKE_REASON")

        # Router : HTML (web).
        async def fake_router(content, model, s):
            return RouterOutput(language="HTML"), None
        monkeypatch.setattr(dspy_mod, "execute_router_node", fake_router)

        # Architect : 1 seule sous-tâche (on veut isoler la boucle de feedback).
        async def fake_architect(task, model, s):
            return ArchitectOutput(
                plan_id="p1", global_architecture="1 fichier",
                subtasks=[ArchitectTask(task_id="st1", description="HTML",
                                        target_files=["index.html"])],
            ), None
        monkeypatch.setattr(dspy_mod, "execute_architect_node", fake_architect)

        # Le GROS feedback : 400 lignes de "bug" (simule un gros traceback).
        BIG_BUG = "BUG CRITIQUE:\n" + "\n".join(f"ligne de stack {i}" for i in range(400))

        # On capture le content reçu par le Coder à chaque itération.
        coder_inputs = []
        async def fake_coder(sub, model, s):
            coder_inputs.append(sub["content"])  # ce que le Coder voit vraiment
            return CoderOutput(task_id=sub["id"], status="success", details="ok"), None
        monkeypatch.setattr(nodes_mod, "execute_coder_node", fake_coder)

        # Tester + Security neutres.
        async def fake_tester(sub, model, s):
            return CoderOutput(task_id=sub["id"], status="success", details="ok"), None
        async def fake_security(sub, model, s):
            return SecurityOutput(task_id=sub["id"], is_secure=True, vulnerabilities=[]), None
        monkeypatch.setattr(nodes_mod, "execute_tester_node", fake_tester)
        monkeypatch.setattr(dspy_mod, "execute_security_reviewer_node", fake_security)

        # Judge : rejette à l'itération 1 (gros feedback), approuve à l'itération 2.
        call = {"n": 0}
        async def fake_judge(sub, test_res, sec_res, model, s):
            call["n"] += 1
            if call["n"] == 1:
                return CodeJudgeOutput(task_id=sub["id"], is_approved=False,
                                       final_feedback=BIG_BUG), None
            return CodeJudgeOutput(task_id=sub["id"], is_approved=True,
                                   final_feedback="ok"), None
        monkeypatch.setattr(dspy_mod, "execute_code_judge_node", fake_judge)

        # KG réel dans un fichier temporaire PARTAGÉ : on ne peut pas utiliser
        # ":memory:" car run_coding_workflow crée SA PROPRE instance de KnowledgeGraph
        # (chaque instance ":memory:" est isolée). On pointe kg_path sur un fichier
        # pour que l'instance du workflow et celle de vérification voient les mêmes
        # données.
        from graph_orchestrator.knowledge_graph import KnowledgeGraph
        kg_path = str(tmp_path / "test_kg.duckdb")
        if os.path.exists(kg_path):
            os.remove(kg_path)

        # Exécution du workflow.
        settings = _settings(feedback_max_chars=500, kg_path=kg_path)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                wf_mod.run_coding_workflow(
                    seed_tasks=[{"id": "T1", "content": "crée index.html",
                                 "target_files": ["index.html"]}],
                    settings=settings,
                )
            )
        finally:
            loop.close()

        # 2 appels au Coder (itération 1 rejetée, itération 2 approuvée).
        assert len(coder_inputs) == 2

        # INVARIANT 1 : le 2e appel (itération 2) contient le feedback tronqué.
        second_input = coder_inputs[1]
        assert "TICKETS DE BUGS ACTIFS" in second_input
        # La troncature borne la taille injectée (le gros bug fait ~3500 chars).
        assert len(second_input) < len(BIG_BUG), (
            "Le feedback injecté au Coder devrait être tronqué, pas intégral"
        )
        assert "BUG CRITIQUE" in second_input  # la tête (l'erreur) est conservée

        # INVARIANT 2 : en base, le contenu est INTÉGRAL (pas de troncature à l'écriture).
        # On rouvre le KG sur le même fichier pour vérifier ce que le workflow a écrit.
        verify_kg = KnowledgeGraph(kg_path)
        claims = verify_kg.get_claims("file:st1")
        refutations = [c for c in claims if c.get("kind") == "refutation"]
        assert len(refutations) >= 1
        stored = refutations[0]["content"]
        assert stored == BIG_BUG, "Le contenu en DuckDB doit rester intégral (pas tronqué)"
