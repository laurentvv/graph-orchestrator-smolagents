import json
import re
import asyncio
from typing import List, Optional, Any
from pydantic import BaseModel, ValidationError
from smolagents import ToolCallingAgent, OpenAIServerModel

# ==========================================
# 1. Contrats de Données (Pydantic)
# ==========================================

class WorkerOutput(BaseModel):
    task_id: str
    summary: str
    confidence_score: float

class JudgeOutput(BaseModel):
    is_valid: bool
    reason: str
    approved_tasks: List[str]

class FinalSynthesis(BaseModel):
    global_summary: str
    key_insights: List[str]

def extract_and_validate(response: Any, model_class: type[BaseModel]) -> Optional[BaseModel]:
    """Extrait et valide le JSON, qu'il soit retourné sous forme de dict natif ou de string."""
    try:
        if isinstance(response, model_class):
            return response

        if isinstance(response, dict):
            raw_json = json.dumps(response)
        else:
            match = re.search(r'```(?:json)?\s*(.*?)\s*```', str(response), re.DOTALL | re.IGNORECASE)
            raw_json = match.group(1).strip() if match else str(response).strip()

            if not raw_json.startswith('{'):
                match = re.search(r'(\{.*\})', str(response), re.DOTALL)
                if match:
                    raw_json = match.group(1).strip()

        return model_class.model_validate_json(raw_json)
    except (ValidationError, json.JSONDecodeError) as e:
        print(f"[-] Échec de validation du contrat de données pour {model_class.__name__} : {e}")
        return None

# ==========================================
# 2. Configuration & Tiering des Modèles
# ==========================================

# Modèle rapide et léger pour le Fan-out (ex: Qwen2.5-7B, Llama3-8B)
fast_model = OpenAIServerModel(
    model_id="qwen2.5:7b",
    api_base="http://localhost:11434/v1",
    api_key="sk-local"
)

# Modèle lourd et avancé pour le Juge et la Synthèse (ex: Llama3-70B, Mixtral)
reasoning_model = OpenAIServerModel(
    model_id="llama3:70b",
    api_base="http://localhost:11434/v1",
    api_key="sk-local"
)

# ==========================================
# 3. Nœuds du Graphe avec Mécanisme de Retry
# ==========================================

async def run_with_retry(agent: ToolCallingAgent, prompt: str, model_class: type[BaseModel], max_retries: int = 3) -> Optional[BaseModel]:
    """Exécute un agent avec plusieurs tentatives en cas d'échec de parsing JSON."""
    for attempt in range(max_retries):
        try:
            raw_result = await asyncio.to_thread(agent.run, prompt)
            validated_data = extract_and_validate(raw_result, model_class)

            if validated_data:
                return validated_data

            print(f"[!] Tentative {attempt + 1}/{max_retries} échouée pour {model_class.__name__}. Nouvelle tentative...")
            prompt += f"\n\nRAPPEL CRITIQUE: Tu as échoué au dernier essai. Renvoyez STRICTEMENT un JSON valide pour ce schéma : {model_class.model_json_schema()} via l'outil final_answer."
        except Exception as e:
            print(f"[-] Erreur interne (Tentative {attempt + 1}/{max_retries}): {e}")

    print(f"[-] Échec définitif pour {model_class.__name__} après {max_retries} tentatives.")
    return None


async def execute_worker_node(task: dict) -> Optional[WorkerOutput]:
    """Nœud Fan-out : analyse une tâche de manière isolée."""
    local_worker = ToolCallingAgent(tools=[], model=fast_model)

    prompt = f"""Analyse cette tâche et retourne le résultat STRICTEMENT au format JSON via l'outil 'final_answer'.
    N'ajoute AUCUN texte avant ou après le JSON.
    Schéma exact attendu: {{"task_id": "{task['id']}", "summary": "ton résumé de la tache", "confidence_score": 0.95}}
    Contenu de la tâche : {task['content']}
    """
    return await run_with_retry(local_worker, prompt, WorkerOutput)


async def execute_judge_node(worker_results: List[WorkerOutput]) -> Optional[JudgeOutput]:
    """Nœud Vérificateur : filtre et valide les résultats des workers."""
    local_judge = ToolCallingAgent(tools=[], model=reasoning_model)

    prompt = f"""Tu es un juge impitoyable. Analyse les résultats fournis et retourne ton verdict STRICTEMENT au format JSON via l'outil 'final_answer'.
    Schéma exact attendu : {{"is_valid": true, "reason": "raison du choix", "approved_tasks": ["task_id1", "task_id2"]}}
    Tu dois rejeter toute tâche dont le confidence_score < 0.7.
    Si toutes les tâches sont rejetées, is_valid = false. Si au moins une est gardée, is_valid = true.
    Résultats des workers : {json.dumps([r.model_dump() for r in worker_results], ensure_ascii=False)}
    """
    return await run_with_retry(local_judge, prompt, JudgeOutput)


async def execute_synth_node(approved_data: List[WorkerOutput]) -> Optional[FinalSynthesis]:
    """Nœud de Synthèse : agrège les résultats approuvés."""
    local_synth = ToolCallingAgent(tools=[], model=reasoning_model)

    prompt = f"""Tu es un synthétiseur expert. Rédige une synthèse globale à partir des données fournies et retourne-la STRICTEMENT au format JSON via l'outil 'final_answer'.
    Schéma exact attendu : {{"global_summary": "ton résumé global des problèmes", "key_insights": ["insight 1", "insight 2"]}}
    Données validées : {json.dumps([r.model_dump() for r in approved_data], ensure_ascii=False)}
    """
    return await run_with_retry(local_synth, prompt, FinalSynthesis)

# ==========================================
# 4. Orchestration du Graphe (Arêtes et Routage)
# ==========================================

async def run_graph_workflow(tasks: List[dict]):
    print(f"\n[*] Démarrage du graphe avec {len(tasks)} tâches...")

    # 1. Motif Diamant - Fan-out (Parallélisation Async)
    print("[*] Lancement du Fan-out asynchrone...")
    worker_coroutines = [execute_worker_node(t) for t in tasks]
    worker_results_raw = await asyncio.gather(*worker_coroutines)
    worker_results = [r for r in worker_results_raw if r is not None]

    if not worker_results:
        raise RuntimeError("Arrêt du graphe : Aucun worker n'a renvoyé de données valides.")

    print(f"[*] Fan-in (Barrière) atteint : {len(worker_results)} résultats consolidés.")

    # 2. Vérification Contradictoire (Le Juge)
    print("[*] Lancement du Juge...")
    judge_verdict = await execute_judge_node(worker_results)

    match judge_verdict:
        case None:
            print("[-] Erreur fatale : Le Juge a échoué à produire un JSON valide.")
            return None
        case JudgeOutput(is_valid=False, reason=reason):
            print(f"[-] Le Juge a rejeté l'ensemble du lot. Motif : {reason}")
            return None
        case JudgeOutput(is_valid=True, approved_tasks=approved):
            print(f"[+] Juge valide. Tâches conservées pour la synthèse : {approved}")

    approved_data = [r for r in worker_results if r.task_id in judge_verdict.approved_tasks]

    if not approved_data:
        print("[-] Plus aucune tâche valide après le passage du Juge. Arrêt.")
        return None

    # 3. Motif Diamant - Synthesize (Réduction finale)
    print(f"[*] Lancement de la synthèse finale sur {len(approved_data)} tâches...")
    final_result = await execute_synth_node(approved_data)
    return final_result


if __name__ == "__main__":
    sample_tasks = [
        {"id": "t1", "content": "La charge CPU du serveur DB a atteint 95% pendant 10 minutes."},
        {"id": "t2", "content": "Le reverse proxy a retourné 45 erreurs 502 dans la dernière heure."},
        {"id": "t3", "content": "L'espace disque sur /var/log est à 12%."}
    ]

    final_output = asyncio.run(run_graph_workflow(sample_tasks))

    if final_output:
        print("\n" + "="*50)
        print("         RÉSULTAT FINAL DU GRAPHE")
        print("="*50)
        print(json.dumps(final_output.model_dump(), indent=4, ensure_ascii=False))
