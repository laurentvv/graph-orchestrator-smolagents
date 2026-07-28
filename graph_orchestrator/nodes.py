"""Nœuds du graphe : Worker (Fan-out), Judge (vérification qualitative), Synth (synthèse).

Chaque nœud :
- instancie son propre ToolCallingAgent (stateless),
- exécute avec retry automatique sur échec de parsing JSON,
- collecte les métriques (tokens/durée) via return_full_result=True.
"""

import asyncio
import json
from typing import List, Optional, Tuple

from pydantic import BaseModel
from smolagents import OpenAIServerModel, ToolCallingAgent

from .config import Settings
from .logging_utils import NodeMetrics, resolve_verbosity
from .models import (
    AdversaryVerdict,
    FinalSynthesis,
    JudgeOutput,
    ReduceOutput,
    TaskAssessment,
    WorkerOutput,
    extract_and_validate,
)


# ==========================================
# Modèles (construits une fois depuis la config)
# ==========================================

def build_fast_model(settings: Settings) -> OpenAIServerModel:
    return OpenAIServerModel(
        model_id=settings.fast_model_id,
        api_base=settings.ollama_api_base,
        api_key=settings.ollama_api_key,
    )


def build_reasoning_model(settings: Settings) -> OpenAIServerModel:
    # max_tokens généreux obligatoire pour Gemma : sans ça, Ollama renvoie
    # finish_reason=length sans tool_calls (le raisonnement interne consomme tout).
    return OpenAIServerModel(
        model_id=settings.reasoning_model_id,
        api_base=settings.ollama_api_base,
        api_key=settings.ollama_api_key,
        max_tokens=settings.reasoning_max_tokens,
    )


# ==========================================
# Retry + métriques
# ==========================================

async def run_with_retry(
    agent: ToolCallingAgent,
    prompt: str,
    model_class: type,
    max_retries: int,
) -> Tuple[Optional[object], Optional[NodeMetrics]]:
    """Exécute un agent avec retry. Retourne (données_validées, métriques).

    Les métriques (tokens/durée) viennent du RunResult de smolagents
    (return_full_result=True). En cas d'échec définitif, les métriques du dernier
    essai sont quand même renvoyées pour l'observabilité.
    """
    last_metrics: Optional[NodeMetrics] = None

    for attempt in range(max_retries):
        try:
            # asyncio.to_thread : smolagents est synchrone, on le déporte hors de la loop.
            # IMPORTANT : return_full_result doit être nommé — sinon `True` positionnel
            # tombe sur `stream` (2e paramètre) et renvoie un générateur au lieu d'un RunResult.
            run_result = await asyncio.to_thread(
                agent.run, prompt, stream=False, return_full_result=True
            )

            # smolagents renvoie un RunResult quand return_full_result=True
            raw_output = run_result.output if hasattr(run_result, "output") else run_result
            validated = extract_and_validate(raw_output, model_class)

            # Collecte métriques depuis le RunResult
            last_metrics = _metrics_from_run(agent, run_result)

            if validated:
                return validated, last_metrics

            print(
                f"[!] Tentative {attempt + 1}/{max_retries} échouée pour "
                f"{model_class.__name__}. Nouvelle tentative..."
            )
            prompt += (
                f"\n\nRAPPEL CRITIQUE: Tu as échoué au dernier essai. Renvoie STRICTEMENT "
                f"un JSON valide pour ce schéma : {model_class.model_json_schema()} "
                f"via l'outil final_answer."
            )
        except Exception as e:
            print(f"[-] Erreur interne (Tentative {attempt + 1}/{max_retries}): {e}")

    print(f"[-] Échec définitif pour {model_class.__name__} après {max_retries} tentatives.")
    return None, last_metrics


def _metrics_from_run(agent: ToolCallingAgent, run_result) -> NodeMetrics:
    """Extrait les métriques d'un RunResult smolagents."""
    model_id = getattr(getattr(agent, "model", None), "model_id", "?")
    node_name = getattr(agent, "name", "agent")

    duration = None
    in_tok = None
    out_tok = None

    timing = getattr(run_result, "timing", None)
    if timing is not None:
        duration = getattr(timing, "duration", None)

    token_usage = getattr(run_result, "token_usage", None)
    if token_usage is not None:
        in_tok = getattr(token_usage, "input_tokens", None)
        out_tok = getattr(token_usage, "output_tokens", None)

    return NodeMetrics(
        node=node_name,
        model=model_id,
        duration_s=duration,
        input_tokens=in_tok,
        output_tokens=out_tok,
    )


# ==========================================
# Nœuds
# ==========================================

async def execute_worker_node(
    task: dict,
    fast_model: OpenAIServerModel,
    settings: Settings,
) -> Tuple[Optional[WorkerOutput], Optional[NodeMetrics]]:
    """Nœud Fan-out : analyse une tâche de manière isolée et parallèle."""
    # name affiché dans le panneau "New run - worker_t1" ; verbosity réduite pour
    # éviter l'entrelacement des logs quand plusieurs workers tournent en parallèle.
    # smolagents exige un identifiant Python valide (pas de crochets).
    local_worker = ToolCallingAgent(
        tools=[],
        model=fast_model,
        name=f"worker_{task['id']}",
        description="Analyse une tâche d'infrastructure et produit un summary + score de confiance.",
        verbosity_level=resolve_verbosity(settings.log_level),
    )

    prompt = f"""Analyse cette tâche et retourne le résultat STRICTEMENT au format JSON via l'outil 'final_answer'.
    N'ajoute AUCUN texte avant ou après le JSON.
    Schéma exact attendu: {{"task_id": "{task['id']}", "summary": "ton résumé de la tache", "confidence_score": 0.95}}
    Contenu de la tâche : {task['content']}
    """
    return await run_with_retry(local_worker, prompt, WorkerOutput, settings.worker_max_retries)


async def execute_judge_node(
    worker_results: List[WorkerOutput],
    original_tasks: List[dict],
    reasoning_model: OpenAIServerModel,
    settings: Settings,
) -> Tuple[Optional[JudgeOutput], Optional[NodeMetrics]]:
    """Nœud Juge : évaluation QUALITATIVE (fidélité, actionnabilité), pas seulement le score.

    Reçoit les tâches originales pour comparer le summary du worker au contenu source,
    et détecter les hallucinations ou summaries creux/incohérents.
    """
    local_judge = ToolCallingAgent(
        tools=[],
        model=reasoning_model,
        name="judge",
        description="Juge impitoyable : évalue fidélité et actionnabilité des summaries.",
        verbosity_level=resolve_verbosity("HIGH"),  # séquentiel : verbose OK
    )

    # Map task_id -> contenu original pour permettre la comparaison fidélité.
    original_by_id = {t["id"]: t["content"] for t in original_tasks}

    prompt = f"""Tu es un juge expert en monitoring/DevOps. Pour chaque résultat de worker, évalue sa QUALITÉ RÉELLE,
pas seulement le confidence_score. Tu reçois le contenu original de chaque tâche pour comparer.

Pour chaque tâche, vérifie 3 critères :
1. FIDÉLITÉ : le summary reflète-t-il fidèlement le contenu original ? (rejeter si hallucination, contresens, ou omission de l'info clé)
2. ACTIONNABILITÉ : le summary est-il diagnostique et utile ? (rejeter s'il est creux, générique, ou se contente de paraphraser la consigne)
3. CONFIANCE : confidence_score >= {settings.judge_confidence_threshold} ? (rejeter si inférieur)

Retourne ton verdict STRICTEMENT au format JSON via l'outil 'final_answer'.
Schéma exact attendu : {{
  "is_valid": true,
  "reason": "résumé global du verdict",
  "approved_tasks": ["task_id1", "task_id2"],
  "assessments": [
    {{"task_id": "t1", "verdict": "approved", "reason": "fidèle et actionnable"}},
    {{"task_id": "t2", "verdict": "rejected", "reason": "hallucination sur la cause"}}
  ]
}}
Une tâche est rejetée si elle échoue à L'UN AU MOINS des 3 critères.
Si toutes les tâches sont rejetées, is_valid = false. Si au moins une est approuvée, is_valid = true.

Résultats des workers : {json.dumps([r.model_dump() for r in worker_results], ensure_ascii=False)}
Contenus originaux : {json.dumps(original_by_id, ensure_ascii=False)}
"""
    return await run_with_retry(local_judge, prompt, JudgeOutput, settings.worker_max_retries)


async def execute_synth_node(
    approved_data: List[WorkerOutput],
    reasoning_model: OpenAIServerModel,
    settings: Settings,
) -> Tuple[Optional[FinalSynthesis], Optional[NodeMetrics]]:
    """Nœud de Synthèse : agrège les résultats approuvés."""
    local_synth = ToolCallingAgent(
        tools=[],
        model=reasoning_model,
        name="synth",
        description="Synthétise les résultats approuvés en un résumé global + insights clés.",
        verbosity_level=resolve_verbosity("HIGH"),
    )

    prompt = f"""Tu es un synthétiseur expert. Rédige une synthèse globale à partir des données fournies et retourne-la STRICTEMENT au format JSON via l'outil 'final_answer'.
Schéma exact attendu : {{"global_summary": "ton résumé global des problèmes", "key_insights": ["insight 1", "insight 2"]}}
Données validées : {json.dumps([r.model_dump() for r in approved_data], ensure_ascii=False)}
"""
    return await run_with_retry(local_synth, prompt, FinalSynthesis, settings.worker_max_retries)


# ==========================================
# Nœud Reduce (§3 : flatten + dedupe + filter, code pur, 0 token)
# ==========================================

def execute_reduce_node(
    worker_results: List[WorkerOutput],
) -> ReduceOutput:
    """Nœud Reduce : déduplique sur task_id et filtre les None/doublons.

    Code déterministe, aucun appel LLM. Implémente le pattern du guide §3 :
    on garde la première occurrence de chaque task_id, on jette le reste.
    """
    seen_ids: set[str] = set()
    kept: List[WorkerOutput] = []
    dropped = 0
    for r in worker_results:
        if r is None or r.task_id in seen_ids:
            dropped += 1
            continue
        seen_ids.add(r.task_id)
        kept.append(r)
    return ReduceOutput(
        kept=kept,
        dropped_count=dropped,
        reason=f"Dédupliqué sur task_id ; {dropped} doublon(s)/None écarté(s).",
    )


# ==========================================
# Nœud Adversaire (§5 : flotte de N sceptiques indépendants)
# ==========================================

# Personas divergents : chacun cherche une faille différente pour forcer le désaccord.
_ADVERSARY_PERSONAS = [
    "Tu es un détecteur d'hallucinations : traque toute affirmation du summary NON justifiée par le contenu original.",
    "Tu es un vérificateur de contre-sens : cherche les interprétations erronées ou inversion du sens des chiffres/mots.",
    "Tu es un chasseur d'omissions : identifie les informations CLÉS du contenu original absentes du summary.",
    "Tu es un critique d'actionnabilité : rejette si le summary est creux, générique, ou paraphrase la consigne sans diagnostiquer.",
    "Tu es un contrôleur de cohérence : cherche les contradictions internes du summary ou scores absurdes.",
]


async def execute_adversary_node(
    worker_results: List[WorkerOutput],
    original_tasks: List[dict],
    reasoning_model: OpenAIServerModel,
    settings: Settings,
) -> Tuple[Optional[List[AdversaryVerdict]], Optional[List[NodeMetrics]]]:
    """Lance N sceptiques en parallèle pour tenter de réfuter chaque tâche.

    Renvoie (liste_agrégée_de_verdicts, liste_de_métriques). Chaque sceptique évalue
    TOUTES les tâches d'un coup ; les verdicts sont ensuite agrégés par vote (cf.
    aggregate_adversary_verdicts dans le runner).
    """
    original_by_id = {t["id"]: t["content"] for t in original_tasks}
    n = max(1, settings.adversary_count)
    personas = [_ADVERSARY_PERSONAS[i % len(_ADVERSARY_PERSONAS)] for i in range(n)]

    async def run_one_skeptic(idx: int, persona: str):
        # name doit être un identifiant Python valide ; verbosity HIGH (séquentiel après fan-out).
        skeptic = ToolCallingAgent(
            tools=[],
            model=reasoning_model,  # partagé entre sceptiques — sûr (aucun état mutable muté)
            name=f"skeptic_{idx}",
            description="Sceptique indépendant qui tente de réfuter les summaries.",
            verbosity_level=resolve_verbosity("HIGH"),
        )
        prompt = f"""{persona}

Pour chaque résultat de worker ci-dessous, décide si tu PEUX le réfuter (refuted=true) ou non (refuted=false).
Un summary est réfutable s'il contient une hallucination, un contre-sens, une omission clé, ou manque d'actionnabilité.

Retourne ton verdict STRICTEMENT au format JSON via l'outil 'final_answer'.
Schéma : un objet avec une clé "verdicts" contenant la liste :
{{"verdicts": [
  {{"task_id": "t1", "refuted": false, "reason": "fidèle au contenu"}},
  {{"task_id": "t2", "refuted": true, "reason": "hallucination : chiffre inventé"}}
]}}

Résultats des workers : {json.dumps([r.model_dump() for r in worker_results], ensure_ascii=False)}
Contenus originaux : {json.dumps(original_by_id, ensure_ascii=False)}
"""
        # run_with_retry attend un contrat à un seul objet ; on enveloppe la liste dans un contrat wrapper.
        validated, metrics = await run_with_retry(
            skeptic, prompt, _AdversaryBatch, settings.worker_max_retries
        )
        return validated, metrics

    pairs = await asyncio.gather(*[run_one_skeptic(i, p) for i, p in enumerate(personas)])

    # Aplatit les verdicts de tous les sceptiques + collecte les métriques
    all_verdicts: List[AdversaryVerdict] = []
    all_metrics: List[NodeMetrics] = []
    for batch, metrics in pairs:
        if batch is not None:
            all_verdicts.extend(batch.verdicts)
        if metrics is not None:
            all_metrics.append(metrics)
    return all_verdicts, all_metrics


class _AdversaryBatch(BaseModel):
    """Contrat wrapper : un sceptique renvoie une liste de verdicts."""
    verdicts: List[AdversaryVerdict]


def aggregate_adversary_verdicts(
    verdicts: List[AdversaryVerdict],
    worker_results: List[WorkerOutput],
    adversary_count: int,
    threshold: float,
) -> JudgeOutput:
    """Logique PURE de vote : une tâche est rejetée si >= threshold*N sceptiques l'ont réfutée.

    threshold=0.5 (défaut) => majorité requise pour réfuter.
    Construit un JudgeOutput (assessments agrégés) — pas d'appel LLM.
    """
    # Compte les réfutations par task_id
    refute_counts: dict[str, int] = {}
    reasons_by_task: dict[str, List[str]] = {}
    for v in verdicts:
        if v.refuted:
            refute_counts[v.task_id] = refute_counts.get(v.task_id, 0) + 1
        reasons_by_task.setdefault(v.task_id, []).append(v.reason)

    needed_to_reject = adversary_count * threshold  # ex: 3 * 0.5 = 1.5 => >=2 pour réfuter

    assessments: List[TaskAssessment] = []
    approved_tasks: List[str] = []
    for w in worker_results:
        refutes = refute_counts.get(w.task_id, 0)
        if refutes >= needed_to_reject:
            assessments.append(TaskAssessment(
                task_id=w.task_id,
                verdict="rejected",
                reason=f"{refutes}/{adversary_count} sceptiques l'ont réfutée : "
                       + " | ".join(reasons_by_task.get(w.task_id, []))[:200],
            ))
        else:
            assessments.append(TaskAssessment(
                task_id=w.task_id,
                verdict="approved",
                reason=f"{refutes}/{adversary_count} réfutations (sous le seuil {threshold}).",
            ))
            approved_tasks.append(w.task_id)

    return JudgeOutput(
        is_valid=len(approved_tasks) > 0,
        reason=f"Vote adversaire : {len(approved_tasks)}/{len(worker_results)} approuvées.",
        approved_tasks=approved_tasks,
        assessments=assessments,
    )


# ==========================================
# Human-in-the-loop (§5 : checkpoint bloquant, désactivable)
# ==========================================

def hitl_checkpoint(approved_data: List[WorkerOutput]) -> bool:
    """Point d'approbation humaine avant la synthèse. Retourne True si validé.

    Affiche les tâches approuvées et demande une confirmation (y/n) en console.
    Nœud purement synchrone ; à appeler uniquement si settings.hitl_enabled.
    """
    print("\n" + "=" * 50)
    print("  HUMAN-IN-THE-LOOP : validation requise")
    print("=" * 50)
    for w in approved_data:
        print(f"  • [{w.task_id}] (conf={w.confidence_score:.2f}) {w.summary}")
    print("=" * 50)
    try:
        answer = input("Approuver la synthèse de ces tâches ? [y/N] : ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in {"y", "yes", "o", "oui"}
