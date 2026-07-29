"""Workflows de plus haut niveau : one-shot (défaut) et exploration (loop-until-dry).

Le mode exploration (§5 du guide) boucle tant que de nouveaux éléments émergent.
Trois garanties anti-boucle-infinie :
  1. MAX_ITERATIONS — hard cap, sortie forcée.
  2. Critère "dry" — un tour n'apporte aucun nouvel insight (après dédup) => arrêt.
  3. Dédup contre TOUT le déjà-vu, y compris rejets — sinon on reboucle sur les dead-ends.

Phase 5 : la dédup est désormais PERSISTANTE via le Knowledge Graph (DuckDB) — l'état
des insights déjà vus survit à l'effacement du contexte et aux redémarrages.
"""

import asyncio
import json
from typing import List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel

from .config import Settings, settings as default_settings
from .hitl import hitl_checkpoint, should_trigger_hitl
from .knowledge_graph import KnowledgeGraph
from .logging_utils import NodeMetrics, render_observability_table
from .models import FinalSynthesis, WorkerOutput
from .nodes import (
    aggregate_adversary_verdicts,
    build_fast_model,
    build_reasoning_model,
    execute_adversary_node,
    execute_reduce_node,
    execute_synth_node,
    execute_worker_node,
    execute_coder_node,
)

console = Console()


async def run_exploration_workflow(
    seed_tasks: List[dict],
    settings: Settings = default_settings,
) -> Tuple[Optional[FinalSynthesis], List[NodeMetrics]]:
    """Mode exploration : loop-until-dry sur les angles non explorés.

    À chaque itération :
      - Fan-out sur les tâches de l'itération courante
      - Reduce + adversaires
      - On ne conserve que les insights NOUVEAUX (non vus dans le KG)
      - Si rien de nouveau => "dry" => on s'arrête et on synthétise

    La dédup est persistante : le KG (DuckDB) garde trace de TOUT ce qui a été vu,
    y compris les rejets (règle d'or §5). L'état survit aux redémarrages.
    """
    fast_model = build_fast_model(settings)
    reasoning_model = build_reasoning_model(settings)
    all_metrics: List[NodeMetrics] = []

    # Knowledge Graph persistant : remplace les Set en mémoire (seen_ids/seen_summaries).
    # L'état de dédup survit désormais entre runs (Phase 5).
    kg = KnowledgeGraph(settings.kg_path)
    run_id = f"exploration_{id(kg)}"
    print(f"[*] Knowledge Graph : {settings.kg_path}")

    accumulated: List[WorkerOutput] = []
    current_tasks = seed_tasks
    iteration = 0

    while iteration < settings.max_iterations:
        iteration += 1
        print(f"\n{'='*60}")
        print(f"  EXPLORATION — Itération {iteration}/{settings.max_iterations}")
        print(f"  Tâches ce tour : {[t['id'] for t in current_tasks]}")
        print(f"{'='*60}")

        # --- Fan-out ---
        worker_pairs = await asyncio.gather(
            *[execute_worker_node(t, fast_model, settings) for t in current_tasks]
        )
        raw = []
        for result, metrics in worker_pairs:
            if result is not None:
                raw.append(result)
            if metrics is not None:
                all_metrics.append(metrics)

        # --- Reduce ---
        reduced = execute_reduce_node(raw)
        candidates = reduced.kept

        # --- Dédup persistante via le KG (remplace les Set en mémoire) ---
        # On écrit chaque observation dans le KG ; add_claim() renvoie None si doublon.
        new_outputs: List[WorkerOutput] = []
        for w in candidates:
            entity_id = f"task:{w.task_id}"
            kg.add_entity(entity_id, kind="task", name=None)
            claim_id = kg.add_claim(
                entity_id=entity_id,
                content=w.summary,
                kind="observation",
                confidence=w.confidence_score,
                source=f"worker_{w.task_id}",
                model_id=settings.fast_model_id,
                run_id=run_id,
            )
            if claim_id is not None:
                # Nouveau (non vu) => on le garde pour la suite
                new_outputs.append(w)

        if not new_outputs:
            print(f"\n[*] Itération {iteration} : RIEN de nouveau (dry). Fin de l'exploration.")
            break

        # --- Adversaires sur les nouveaux ---
        verdicts, adv_metrics = await execute_adversary_node(
            new_outputs, current_tasks, reasoning_model, settings
        )
        all_metrics.extend(adv_metrics)

        if verdicts:
            judge = aggregate_adversary_verdicts(
                verdicts, new_outputs, settings.adversary_count, settings.adversary_threshold
            )
            print(f"[+] Itération {iteration} : {judge.reason}")
            for a in judge.assessments:
                tag = "[green][OK][/green]" if a.verdict == "approved" else "[red][FAIL][/red]"
                console.print(f"    {tag} [bold]{a.task_id}[/bold] — {a.reason[:100]}")

            # Marque le statut dans le KG + trace les réfutations
            for w in new_outputs:
                entity_id = f"task:{w.task_id}"
                claims = kg.get_claims(entity_id, status="open")
                if not claims:
                    continue
                obs_id = claims[-1]["id"]
                assessment = next((a for a in judge.assessments if a.task_id == w.task_id), None)
                if assessment is None:
                    continue
                if assessment.verdict == "approved":
                    kg.mark_status(obs_id, "approved")
                else:
                    # Rejet : on marque l'obs rejetée MAIS elle reste vue (règle d'or)
                    kg.mark_status(obs_id, "rejected")
                    ref_id = kg.add_claim(
                        entity_id=entity_id, content=assessment.reason, kind="refutation",
                        confidence=None, source="adversary_panel",
                        model_id=settings.reasoning_model_id, run_id=run_id,
                    )
                    if ref_id is not None:
                        kg.add_edge(ref_id, obs_id, "REFUTES")

            approved_this_round = [w for w in new_outputs if w.task_id in judge.approved_tasks]
            accumulated.extend(approved_this_round)
        else:
            # Sceptiques échoués : on accumule quand même (isolation des échecs, §5)
            print(f"[!] Itération {iteration} : sceptiques indisponibles, accumulation directe.")
            accumulated.extend(new_outputs)

        print(f"[*] Insights accumulés : {len(accumulated)} au total.")

    else:
        print(f"\n[*] Hard cap atteint ({settings.max_iterations} itérations). Arrêt forcé.")

    if not accumulated:
        print("[-] Aucun insight accumulé au cours de l'exploration.")
        return None, all_metrics

    # --- HITL stratégique (Phase 6) ---
    if should_trigger_hitl("synth", settings):
        if not hitl_checkpoint(accumulated, node_name="synth"):
            print("[-] Synthèse refusée par l'opérateur. Arrêt propre.")
            return None, all_metrics

    # --- Synthèse finale ---
    print(f"\n[*] Synthèse finale sur {len(accumulated)} insights accumulés...")
    final_result, synth_metrics = await execute_synth_node(accumulated, reasoning_model, settings)
    if synth_metrics is not None:
        all_metrics.append(synth_metrics)

    # Trace les insights finaux dans le KG
    if final_result is not None:
        for insight in final_result.key_insights:
            kg.add_claim(
                entity_id="synthesis", content=insight, kind="insight",
                confidence=None, source="synth",
                model_id=settings.reasoning_model_id, run_id=run_id,
            )

    return final_result, all_metrics


async def run_coding_workflow(
    seed_tasks: List[dict],
    settings: Settings = default_settings,
) -> Tuple[Optional[dict], List[NodeMetrics]]:
    """Mode coding : Architect -> Fan-out Coder -> Parallel Validation -> Judge (loop)."""
    reasoning_model = build_reasoning_model(settings)
    fast_model = build_fast_model(settings)
    all_metrics: List[NodeMetrics] = []

    # Knowledge Graph persistant : Phase 5 appliquée au codage
    kg = KnowledgeGraph(settings.kg_path)
    run_id = f"coding_{id(kg)}"
    print(f"[*] Knowledge Graph branché : {settings.kg_path}")

    print(f"\n{'='*60}")
    print(f"  CODING WORKFLOW (Multi-Agent Playbook)")
    print(f"{'='*60}")
    
    results = []
    from .nodes import execute_tester_node, execute_coder_node
    from .dspy_nodes import (
        execute_architect_node,
        execute_security_reviewer_node, 
        execute_code_judge_node, 
        execute_router_node
    )
    
    # Routine initiale de routage
    task_content = seed_tasks[0]['content'] if seed_tasks else ""
    print(f"[*] Analyse de la requête par le routeur ultra-rapide ({settings.fast_model_id})...")
    router_res, m0 = await execute_router_node(task_content, fast_model, settings)
    if m0: all_metrics.append(m0)
    
    if router_res:
        print(f"[*] Le routeur a classifié la technologie principale : {router_res.language.upper()}")
        if seed_tasks:
            seed_tasks[0]['content'] += f"\n\n[ROUTER DIRECTIVE : The primary technology to use is {router_res.language.upper()}]"
    
    async def process_subtask_loop(subtask) -> Tuple[dict, List[NodeMetrics]]:
        sub_metrics = []
        entity_id = f"file:{subtask.task_id}"
        kg.add_entity(entity_id, kind="file", name=subtask.task_id)
        
        max_iter = 3
        
        for iteration in range(1, max_iter + 1):
            print(f"    [>] Itération {iteration}/{max_iter} pour {subtask.task_id} (Coder)...")
            
            # Reconstruction du prompt en lisant l'historique de DuckDB
            # Au lieu d'accumuler dans le contexte, on fait une requête "Bug Tracker" propre
            historique = ""
            if iteration > 1:
                claims = kg.get_claims(entity_id)
                refutations = [c for c in claims if c.get('kind') == 'refutation']
                if refutations:
                    historique = "\n\n[TICKETS DE BUGS ACTIFS (LU DEPUIS DUCKDB)] :\n"
                    for ref in refutations:
                        historique += f"- {ref['content']}\n"
            
            sub_dict = {
                "id": subtask.task_id, 
                "content": subtask.description + historique,
                "target_files": subtask.target_files
            }
            
            # 1. Coder (Qwen-2B)
            coder_res, m1 = await execute_coder_node(sub_dict, fast_model, settings)
            if m1: sub_metrics.append(m1)
            
            if not coder_res or coder_res.status == "failure":
                print(f"    [-] Le Coder a échoué techniquement sur {subtask.task_id}.")
                return {"status": "failure", "reason": "Coder crash"}, sub_metrics
                
            print(f"    [>] Coder terminé. Déclenchement des Audits parallèles (Tester & Sécurité)...")
            
            # On enregistre l'observation du Coder dans DuckDB
            obs_id = kg.add_claim(
                entity_id=entity_id,
                content=f"Code généré (Itération {iteration}): {coder_res.details}",
                kind="observation",
                confidence=1.0,
                source="coder",
                model_id=settings.reasoning_model_id,
                run_id=run_id,
            )
            
            # 2. Vérifications Contradictoires (Parallèle)
            t_task = execute_tester_node(sub_dict, reasoning_model, settings)
            s_task = execute_security_reviewer_node(sub_dict, reasoning_model, settings)
            
            (test_res, m2), (sec_res, m3) = await asyncio.gather(t_task, s_task)
            if m2: sub_metrics.append(m2)
            if m3: sub_metrics.append(m3)
            
            # 3. Judge Panel (Fan-in)
            print(f"    [>] Audits terminés. Juge (Qwen-2B JSON) en cours d'évaluation...")
            judge_res, m4 = await execute_code_judge_node(sub_dict, test_res, sec_res, fast_model, settings)
            if m4: sub_metrics.append(m4)
            
            if judge_res and judge_res.is_approved:
                print(f"    [+] {subtask.task_id} APPROUVÉ par le Juge ! 🚀")
                if obs_id: kg.mark_status(obs_id, "approved")
                return {"status": "success", "task_id": subtask.task_id}, sub_metrics
            else:
                feedback = judge_res.final_feedback if judge_res else "Erreur système du juge."
                print(f"    [-] {subtask.task_id} REJETÉ. Sauvegarde du bug dans DuckDB...")
                if obs_id: kg.mark_status(obs_id, "rejected")
                
                # Le Juge écrit la faille ou le bug dans DuckDB (le Knowledge Graph)
                ref_id = kg.add_claim(
                    entity_id=entity_id, 
                    content=feedback, 
                    kind="refutation",
                    confidence=None, 
                    source="judge_panel",
                    model_id=settings.reasoning_model_id, 
                    run_id=run_id
                )
                if ref_id and obs_id:
                    kg.add_edge(ref_id, obs_id, "REFUTES")
                
        print(f"    [!] Max itérations atteintes pour {subtask.task_id}.")
        return {"status": "max_iterations_reached", "task_id": subtask.task_id}, sub_metrics

    for task in seed_tasks:
        print(f"\n[*] 1. Exécution de l'Architecte pour la tâche globale : {task['id']}")
        architect_result, arch_metrics = await execute_architect_node(task, reasoning_model, settings)
        if arch_metrics:
            all_metrics.append(arch_metrics)
            
        if architect_result is None:
            print(f"[-] L'Architecte a échoué à planifier la tâche {task['id']}.")
            continue
            
        print(f"[+] Plan de l'Architecte reçu : {architect_result.global_architecture}")
        print(f"[*] 2. Fan-out : Lancement des boucles d'ingénierie parallèles sur {len(architect_result.subtasks)} sous-tâches...\n")
        
        # Exécution Séquentielle (Pipeline) pour éviter les Race Conditions sur les fichiers
        for i, st in enumerate(architect_result.subtasks):
            print(f"[*] Traitement de la sous-tâche {i+1}/{len(architect_result.subtasks)}...")
            res, metrics = await process_subtask_loop(st)
            all_metrics.extend(metrics)
            results.append(res)
            
        print(f"\n[*] 3. Fusion des sous-tâches terminée pour {task['id']}.")

    return {"architect_plans": len(seed_tasks), "final_results": results}, all_metrics


# ==========================================
# Tâches d'exemple selon le mode
# ==========================================

ONE_SHOT_TASKS = [
    {"id": "t1", "content": "La charge CPU du serveur DB a atteint 95% pendant 10 minutes."},
    {"id": "t2", "content": "Le reverse proxy a retourné 45 erreurs 502 dans la dernière heure."},
    {"id": "t3", "content": "L'espace disque sur /var/log est à 12%."},
]

EXPLORATION_SEED_TASKS = [
    {
        "id": "e1",
        "content": (
            "Identifie TOUTES les causes possibles d'une charge CPU à 95% sur un serveur de base "
            "de données. Explore chaque piste : requêtes, locks, index manquants, paramétrage, "
            "concurrence, fuites."
        ),
    },
    {
        "id": "e2",
        "content": (
            "Identifie TOUTES les causes possibles de 45 erreurs HTTP 502 sur un reverse proxy. "
            "Explore chaque piste : backend down, timeouts, saturation de connexions, DNS, TLS, "
            "config."
        ),
    },
]

CODING_SEED_TASKS = [
    {
        "id": "T004",
        "content": "Crée un jeu de Tetris simple mais complet en HTML, CSS et JavaScript pur (pas de framework). Le jeu doit être jouable directement dans le navigateur, avec des flèches directionnelles. L'architecture doit comporter au moins 3 fichiers : index.html, style.css et tetris.js.",
        "target_files": ["index.html", "style.css", "tetris.js"]
    }
]


def load_tasks_from_json(mode: str, fallback_tasks: List[dict]) -> List[dict]:
    import os
    tasks_file = "tasks.json"
    if os.path.exists(tasks_file):
        try:
            with open(tasks_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if mode in data and isinstance(data[mode], list):
                    print(f"[*] Chargement des tâches '{mode}' depuis {tasks_file}")
                    return data[mode]
        except Exception as e:
            print(f"[!] Erreur lors de la lecture de {tasks_file}: {e}")
    return fallback_tasks

def run_workflow(mode: str, settings: Settings = default_settings) -> None:
    """Lance le workflow selon le mode (one_shot / exploration / coding)."""
    if mode == "exploration":
        tasks = load_tasks_from_json(mode, EXPLORATION_SEED_TASKS)
        final_output, metrics = asyncio.run(run_exploration_workflow(tasks, settings))
    elif mode == "coding":
        tasks = load_tasks_from_json(mode, CODING_SEED_TASKS)
        final_output, metrics = asyncio.run(run_coding_workflow(tasks, settings))
    else:
        from .runner import run_graph_workflow
        tasks = load_tasks_from_json(mode, ONE_SHOT_TASKS)
        final_output, metrics = asyncio.run(run_graph_workflow(tasks, settings))

    if metrics:
        render_observability_table(metrics, console)

    if final_output:
        data = final_output.model_dump() if hasattr(final_output, "model_dump") else final_output
        console.print(Panel(
            json.dumps(data, indent=4, ensure_ascii=False),
            title="[bold green]RÉSULTAT FINAL DU GRAPHE[/bold green]",
            border_style="green",
        ))


def main() -> None:
    """Point d'entrée dispatchant selon WORKFLOW_MODE."""
    settings = default_settings
    run_workflow(settings.workflow_mode, settings)


if __name__ == "__main__":
    main()
