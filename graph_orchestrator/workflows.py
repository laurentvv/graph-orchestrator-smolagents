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
                tag = "[green]✓[/green]" if a.verdict == "approved" else "[red]✗[/red]"
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


def run_workflow(mode: str, settings: Settings = default_settings) -> None:
    """Lance le workflow selon le mode (one_shot / exploration)."""
    if mode == "exploration":
        final_output, metrics = asyncio.run(
            run_exploration_workflow(EXPLORATION_SEED_TASKS, settings)
        )
    else:
        from .runner import run_graph_workflow
        final_output, metrics = asyncio.run(run_graph_workflow(ONE_SHOT_TASKS, settings))

    if metrics:
        render_observability_table(metrics, console)

    if final_output:
        console.print(Panel(
            json.dumps(final_output.model_dump(), indent=4, ensure_ascii=False),
            title="[bold green]RÉSULTAT FINAL DU GRAPHE[/bold green]",
            border_style="green",
        ))


def main() -> None:
    """Point d'entrée dispatchant selon WORKFLOW_MODE."""
    settings = default_settings
    run_workflow(settings.workflow_mode, settings)


if __name__ == "__main__":
    main()
