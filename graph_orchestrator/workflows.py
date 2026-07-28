"""Workflows de plus haut niveau : one-shot (défaut) et exploration (loop-until-dry).

Le mode exploration (§5 du guide) boucle tant que de nouveaux éléments émergent.
Trois garanties anti-boucle-infinie :
  1. MAX_ITERATIONS — hard cap, sortie forcée.
  2. Critère "dry" — un tour n'apporte aucun nouvel insight (après dédup) => arrêt.
  3. Dédup contre TOUT le déjà-vu, y compris rejets — sinon on reboucle sur les dead-ends.
"""

import asyncio
import json
from typing import List, Optional, Set, Tuple

from rich.console import Console
from rich.panel import Panel

from .config import Settings, settings as default_settings
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
    hitl_checkpoint,
)

console = Console()


def _hash_summary(w: WorkerOutput) -> str:
    """Empreinte stable d'un summary pour la dédup (normalisée)."""
    import hashlib
    norm = (w.summary or "").strip().lower()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


async def run_exploration_workflow(
    seed_tasks: List[dict],
    settings: Settings = default_settings,
) -> Tuple[Optional[FinalSynthesis], List[NodeMetrics]]:
    """Mode exploration : loop-until-dry sur les angles non explorés.

    À chaque itération :
      - Fan-out sur les tâches de l'itération courante
      - Reduce + adversaires
      - On ne conserve que les insights NOUVEAUX (non vus)
      - Si rien de nouveau => "dry" => on s'arrête et on synthétise
    """
    fast_model = build_fast_model(settings)
    reasoning_model = build_reasoning_model(settings)
    all_metrics: List[NodeMetrics] = []

    # État du cycle : accumule TOUT ce qui a été vu (règle d'or §5 : y compris rejets)
    seen_ids: Set[str] = set()
    seen_summaries: Set[str] = set()
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

        # --- Dédup contre le déjà-vu (y compris les summaries rejetés auparavant) ---
        new_outputs: List[WorkerOutput] = []
        for w in candidates:
            h = _hash_summary(w)
            if w.task_id in seen_ids or h in seen_summaries:
                # dead-end : on marque comme vu MAIS on ne l'ajoute pas (règle d'or)
                continue
            new_outputs.append(w)
            seen_ids.add(w.task_id)
            seen_summaries.add(h)

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

            # On accumule seulement les approuvés ; MAIS les rejets sont déjà marqués vus
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

    # --- HITL optionnel ---
    if settings.hitl_enabled:
        if not hitl_checkpoint(accumulated):
            print("[-] Synthèse refusée par l'opérateur. Arrêt propre.")
            return None, all_metrics

    # --- Synthèse finale ---
    print(f"\n[*] Synthèse finale sur {len(accumulated)} insights accumulés...")
    final_result, synth_metrics = await execute_synth_node(accumulated, reasoning_model, settings)
    if synth_metrics is not None:
        all_metrics.append(synth_metrics)

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
