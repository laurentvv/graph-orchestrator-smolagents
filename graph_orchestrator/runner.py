"""Orchestration du graphe : Fan-out -> Reduce -> Adversaire -> (HITL) -> Synth.

Topologie Diamant (guide §3) + fiabilité §5 + mémoire persistante (Phase 5) :
  1. Fan-out : asyncio.gather sur les workers (parallélisation)
  2. Reduce  : dédup + filtre (code pur, 0 token)
  3. Adversaire : flotte de N sceptiques qui votent (vérification contradictoire)
  4. HITL stratégique (conditionnel) : approbation humaine sur les nœuds à enjeu
  5. Synth : réduction finale des données approuvées

Le Knowledge Graph (Phase 5) trace chaque claim avec sa provenance : les workers
écrivent leurs observations, les adversaires leurs réfutations (+arêtes), le
vote marque le statut (approved/rejected). L'état survit à l'effacement du contexte.
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
from .models import FinalSynthesis, JudgeOutput, TaskAssessment, WorkerOutput
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


def _record_workers_in_kg(
    kg: KnowledgeGraph, worker_results: List[WorkerOutput], tasks: List[dict], run_id: str, fast_model_id: str
) -> None:
    """Écrit les observations des workers comme claims dans le KG (avec provenance)."""
    content_by_id = {t["id"]: t["content"] for t in tasks}
    for w in worker_results:
        entity_id = f"task:{w.task_id}"
        kg.add_entity(entity_id, kind="task", name=content_by_id.get(w.task_id))
        kg.add_claim(
            entity_id=entity_id,
            content=w.summary,
            kind="observation",
            confidence=w.confidence_score,
            source=f"worker_{w.task_id}",
            model_id=fast_model_id,
            run_id=run_id,
        )


def _record_adversary_in_kg(
    kg: KnowledgeGraph, judge_verdict: JudgeOutput, worker_results: List[WorkerOutput], run_id: str, reasoning_model_id: str
) -> None:
    """Marque le statut des claims selon le vote, et trace les rejets comme réfutations."""
    # Map task_id -> claim_id de l'observation (la dernière claim ouverte de l'entité)
    summary_by_id = {w.task_id: w.summary for w in worker_results}
    for w in worker_results:
        entity_id = f"task:{w.task_id}"
        claims = kg.get_claims(entity_id, status="open")
        if not claims:
            continue
        obs_id = claims[-1]["id"]  # dernière observation ouverte
        assessment = next((a for a in judge_verdict.assessments if a.task_id == w.task_id), None)
        if assessment is None:
            continue
        if assessment.verdict == "approved":
            kg.mark_status(obs_id, "approved")
        else:
            kg.mark_status(obs_id, "rejected")
            # Trace la réfutation comme claim + arête REFUTES
            ref_id = kg.add_claim(
                entity_id=entity_id,
                content=assessment.reason,
                kind="refutation",
                confidence=None,
                source="adversary_panel",
                model_id=reasoning_model_id,
                run_id=run_id,
            )
            if ref_id is not None:
                kg.add_edge(ref_id, obs_id, "REFUTES")


async def run_graph_workflow(
    tasks: List[dict],
    settings: Settings = default_settings,
) -> Tuple[Optional[FinalSynthesis], List[NodeMetrics]]:
    """Exécute le graphe one-shot. Retourne (synthèse_finale, métriques_par_nœud)."""
    print(f"\n[*] Démarrage du graphe avec {len(tasks)} tâches...")

    fast_model = build_fast_model(settings)
    reasoning_model = build_reasoning_model(settings)
    all_metrics: List[NodeMetrics] = []

    # Knowledge Graph persistant (Phase 5)
    kg = KnowledgeGraph(settings.kg_path)
    run_id = f"run_{id(kg)}"  # identifiant de run pour la provenance
    print(f"[*] Knowledge Graph : {settings.kg_path}")

    # ==========================================
    # 1. Fan-out (parallélisation async)
    # ==========================================
    print("[*] Lancement du Fan-out asynchrone...")
    worker_pairs = await asyncio.gather(
        *[execute_worker_node(t, fast_model, settings) for t in tasks]
    )
    raw_results: List[WorkerOutput] = []
    for result, metrics in worker_pairs:
        if result is not None:
            raw_results.append(result)
        if metrics is not None:
            all_metrics.append(metrics)

    # ==========================================
    # 2. Reduce (dédup + filtre, code pur)
    # ==========================================
    reduced = execute_reduce_node(raw_results)
    print(
        f"[*] Reduce : {len(reduced.kept)} gardées, "
        f"{reduced.dropped_count} écartée(s). {reduced.reason}"
    )
    worker_results = reduced.kept

    if not worker_results:
        raise RuntimeError("Arrêt du graphe : Aucun worker n'a renvoyé de données valides.")

    print(f"[*] Fan-in (Barrière) atteint : {len(worker_results)} résultats consolidés.")

    # Trace les observations dans le KG
    _record_workers_in_kg(kg, worker_results, tasks, run_id, settings.fast_model_id)

    # ==========================================
    # 3. Vérification Adversaire (N sceptiques votent)
    # ==========================================
    print(f"[*] Lancement de la vérification adversaire ({settings.adversary_count} sceptiques)...")
    verdicts, adv_metrics = await execute_adversary_node(
        worker_results, tasks, reasoning_model, settings
    )
    for m in adv_metrics:
        all_metrics.append(m)

    if not verdicts:
        # Tous les sceptiques ont échoué — fallback : tout approuver (isolation des échecs, §5)
        print("[-] Les sceptiques n'ont pas pu produire de verdict. Validation par défaut.")
        judge_verdict = JudgeOutput(
            is_valid=True,
            reason="Sceptiques indisponibles, approbation par défaut.",
            approved_tasks=[w.task_id for w in worker_results],
            assessments=[
                TaskAssessment(
                    task_id=w.task_id, verdict="approved", reason="fallback (sceptiques échoués)"
                )
                for w in worker_results
            ],
        )
    else:
        judge_verdict = aggregate_adversary_verdicts(
            verdicts, worker_results, settings.adversary_count, settings.adversary_threshold
        )

    # Trace le verdict dans le KG (statut + réfutations + arêtes)
    _record_adversary_in_kg(kg, judge_verdict, worker_results, run_id, settings.reasoning_model_id)

    # Affiche le verdict agrégé
    if not judge_verdict.is_valid:
        print(f"[-] Rejet global par les sceptiques. Motif : {judge_verdict.reason}")
        return None, all_metrics

    print(f"[+] Verdict adversaire : {judge_verdict.reason}")
    for a in judge_verdict.assessments:
        tag = "[green]✓[/green]" if a.verdict == "approved" else "[red]✗[/red]"
        console.print(f"    {tag} [bold]{a.task_id}[/bold] — {a.reason}")

    approved_data = [w for w in worker_results if w.task_id in judge_verdict.approved_tasks]
    if not approved_data:
        print("[-] Plus aucune tâche valide après les sceptiques. Arrêt.")
        return None, all_metrics

    # ==========================================
    # 4. Human-in-the-loop stratégique (Phase 6)
    # ==========================================
    if should_trigger_hitl("synth", settings):
        # Récupère la provenance des claims approuvées pour l'affichage contextuel
        provenance = []
        for w in approved_data:
            claims = kg.get_claims(f"task:{w.task_id}", status="approved")
            for c in claims:
                provenance.extend(kg.get_provenance(c["id"]))
        approved = hitl_checkpoint(approved_data, node_name="synth", provenance=provenance)
        if not approved:
            print("[-] Synthèse refusée par l'opérateur humain. Arrêt propre.")
            return None, all_metrics
        print("[+] Synthèse approuvée par l'opérateur.")

    # ==========================================
    # 5. Synthèse (réduction finale)
    # ==========================================
    print(f"[*] Lancement de la synthèse finale sur {len(approved_data)} tâches...")
    final_result, synth_metrics = await execute_synth_node(
        approved_data, reasoning_model, settings
    )
    if synth_metrics is not None:
        all_metrics.append(synth_metrics)

    # Trace le résultat final comme insight dans le KG
    if final_result is not None:
        for insight in final_result.key_insights:
            kg.add_claim(
                entity_id="synthesis",
                content=insight,
                kind="insight",
                confidence=None,
                source="synth",
                model_id=settings.reasoning_model_id,
                run_id=run_id,
            )

    return final_result, all_metrics


def main() -> None:
    """Point d'entrée one-shot : tâches d'exemple + exécution + affichage."""
    sample_tasks = [
        {"id": "t1", "content": "La charge CPU du serveur DB a atteint 95% pendant 10 minutes."},
        {"id": "t2", "content": "Le reverse proxy a retourné 45 erreurs 502 dans la dernière heure."},
        {"id": "t3", "content": "L'espace disque sur /var/log est à 12%."},
    ]

    final_output, metrics = asyncio.run(run_graph_workflow(sample_tasks))

    if metrics:
        render_observability_table(metrics, console)

    if final_output:
        console.print(Panel(
            json.dumps(final_output.model_dump(), indent=4, ensure_ascii=False),
            title="[bold green]RÉSULTAT FINAL DU GRAPHE[/bold green]",
            border_style="green",
        ))


if __name__ == "__main__":
    main()
