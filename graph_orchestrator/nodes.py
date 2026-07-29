"""Nœuds du graphe : Worker (Fan-out), Judge (vérification qualitative), Synth (synthèse).

Chaque nœud :
- instancie son propre ToolCallingAgent (stateless),
- exécute avec retry automatique sur échec de parsing JSON,
- collecte les métriques (tokens/durée) via return_full_result=True.
"""

import asyncio
import json
import os
from typing import List, Optional, Tuple

from pydantic import BaseModel, ValidationError
from smolagents import OpenAIServerModel, ToolCallingAgent, tool

from .config import Settings
from .logging_utils import NodeMetrics, resolve_verbosity
from .models import (
    AdversaryVerdict,
    FinalSynthesis,
    JudgeOutput,
    ReduceOutput,
    TaskAssessment,
    WorkerOutput,
    CoderOutput,
    RouterOutput,
    ArchitectOutput,
    SecurityOutput,
    CodeJudgeOutput,
    extract_and_validate,
)
from .tools import read_file, write_file, edit_file, bash_command, list_directory

@tool
def query_duckdb_knowledge_graph(sql_query: str) -> str:
    """Execute une requête SQL (SELECT) sur le Graphe de Connaissances (DuckDB) pour chercher d'anciens bugs, failles ou feedbacks de l'équipe IA.
    
    Schéma de la base :
    - entity(id VARCHAR, kind VARCHAR, name VARCHAR)
    - claim(id BIGINT, entity_id VARCHAR, content VARCHAR, kind VARCHAR, status VARCHAR) : contient les bugs (kind='refutation') ou le code (kind='observation')
    - provenance(claim_id BIGINT, source VARCHAR, model_id VARCHAR, run_id VARCHAR)
    
    Exemple: "SELECT content FROM claim WHERE kind = 'refutation' ORDER BY created_at DESC LIMIT 10"
    
    Args:
        sql_query: La requête SQL commençant par SELECT.
    """
    import duckdb
    from graph_orchestrator.config import settings
    if not sql_query.strip().upper().startswith("SELECT"):
        return "Erreur: Seules les requêtes SELECT sont autorisées."
        
    try:
        conn = duckdb.connect(settings.kg_path, read_only=True)
        results = conn.execute(sql_query).df()
        conn.close()
        return results.to_markdown(index=False) if not results.empty else "Aucun résultat."
    except Exception as e:
        return f"Erreur SQL: {str(e)}"

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
        api_base=settings.ollama_reasoning_api_base,
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
            
        # FIX TOKEN EXPLOSION: Si on est arrivé ici (erreur ou JSON invalide),
        # l'agent a gardé tout son historique d'échec dans sa mémoire interne.
        # Au prochain tour de la boucle for, si on rappelle agent.run, il va TOUT renvoyer !
        # On doit purger la mémoire de l'agent avant le prochain essai.
        if hasattr(agent, "memory") and hasattr(agent.memory, "steps"):
            agent.memory.steps = []


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
        name=f"worker_{task['id'].replace('-', '_')}",
        description="Analyse une tâche d'infrastructure et produit un summary + score de confiance.",
        verbosity_level=resolve_verbosity(settings.log_level),
    )

    prompt = f"""Analyse cette tâche et retourne le résultat STRICTEMENT en utilisant l'outil 'final_answer'.
    N'ajoute AUCUN texte avant ou après le JSON.
    Ton JSON DOIT absolument respecter ce format exact pour appeler l'outil final_answer :
    {{
      "name": "final_answer",
      "arguments": {{
        "answer": {{
          "task_id": "{task['id']}",
          "summary": "ton résumé détaillé de la tache",
          "confidence_score": 0.95
        }}
      }}
    }}
    Contenu de la tâche : {task['content']}
    """
    return await run_with_retry(local_worker, prompt, WorkerOutput, settings.worker_max_retries)

async def execute_router_node(
    task_content: str,
    fast_model: OpenAIServerModel,
    settings: Settings,
) -> Tuple[Optional[RouterOutput], Optional[NodeMetrics]]:
    """Nœud Routeur : Utilise un petit modèle via l'API Ollama (Structured Outputs) pour classifier la requête."""
    import requests
    import time
    
    prompt = f"""Tu es un nœud de routage (Router Node) ultra-rapide et hautement spécialisé. Ton unique rôle est d'analyser la requête de l'utilisateur pour déterminer la technologie principale requise.

CONSIGNES DE ROUTAGE (VALEURS AUTORISÉES) :
- "python" : Si la tâche concerne de l'analyse de données, du script système, du scraping, du traitement de fichiers ou de l'IA.
- "javascript" : Si la tâche concerne du développement web, des interfaces utilisateur, du frontend, du backend Node.js ou des applications de navigateur.

Requête de l'utilisateur actuelle : {task_content}
"""

    schema = RouterOutput.model_json_schema()
    payload = {
        "model": settings.fast_model_id,
        "messages": [
            {"role": "system", "content": "Tu es un routeur technique. Réponds STRICTEMENT en JSON."},
            {"role": "user", "content": prompt}
        ],
        "format": schema,
        "stream": False,
        "options": {"temperature": 0.0}
    }
    
    start_time = time.time()
    try:
        api_url = settings.ollama_api_base.replace("/v1", "/api/chat")
        response = await asyncio.to_thread(requests.post, api_url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        raw_json = data["message"]["content"]
        validated = RouterOutput.model_validate_json(raw_json)
        
        metrics = NodeMetrics(
            node="router",
            model=settings.fast_model_id,
            duration_s=data.get("total_duration", 0) / 1e9 or (time.time() - start_time),
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )
        return validated, metrics
        
    except Exception as e:
        print(f"[-] Erreur de l'API Ollama (Router) : {e}")
        return None, None

async def execute_architect_node(
    task: dict,
    reasoning_model: OpenAIServerModel,
    settings: Settings,
) -> Tuple[Optional[ArchitectOutput], Optional[NodeMetrics]]:
    """Nœud Architecte : planifie et décompose une tâche globale en sous-tâches isolées."""
    from smolagents import DuckDuckGoSearchTool, CodeAgent
    local_architect = CodeAgent(
        tools=[list_directory, read_file, bash_command, DuckDuckGoSearchTool(), query_duckdb_knowledge_graph],
        model=reasoning_model,
        name=f"architect_{task['id'].replace('-', '_')}",
        description="Architecte Logiciel Senior qui analyse le projet et décompose la tâche en modules JSON.",
        verbosity_level=resolve_verbosity("HIGH"),
    )

    prompt = f"""Tu es un Architecte Logiciel Senior (Architect Node). Ton rôle n'est PAS de coder, mais de PLANIFIER.
Contenu de la tâche globale : {task['content']}

MÉTHODOLOGIE :
1. Recherche sur DuckDB : utilise l'outil 'query_duckdb_knowledge_graph' avec une requête SQL (ex: "SELECT content FROM claim WHERE kind='refutation'") pour lire les bugs/failles (XSS, logique...) rencontrés par l'équipe sur les projets précédents, afin de ne pas refaire les mêmes erreurs d'architecture.
2. Explore le projet (via 'list_directory' ou 'bash_command').
3. Cherche sur internet les best practices (via DuckDuckGoSearchTool) si nécessaire.
4. Réfléchis à l'architecture globale pour accomplir cette tâche.
5. Découpe la tâche en petites sous-tâches très précises.
6. Pour chaque sous-tâche, liste les fichiers cibles qui seront modifiés.

Retourne ton plan STRICTEMENT en utilisant l'outil 'final_answer'.
Ton JSON DOIT absolument respecter ce format exact pour appeler l'outil final_answer :
{{
  "name": "final_answer",
  "arguments": {{
    "answer": {{
      "plan_id": "architect_plan",
      "global_architecture": "Explication de ton choix d'architecture",
      "subtasks": [{{"task_id": "sub_1", "description": "Créer le fichier index.html avec...", "target_files": ["index.html"]}}]
    }}
  }}
}}
"""
    return await run_with_retry(local_architect, prompt, ArchitectOutput, settings.worker_max_retries)


async def execute_coder_node(
    task: dict,
    fast_model: OpenAIServerModel,
    settings: Settings,
) -> Tuple[Optional[CoderOutput], Optional[NodeMetrics]]:
    """Nœud Coder : utilise des outils pour créer/éditer des fichiers et exécuter des commandes bash."""
    from smolagents import DuckDuckGoSearchTool, CodeAgent
    local_coder = ToolCallingAgent(
        tools=[list_directory, read_file, write_file, edit_file, DuckDuckGoSearchTool()],
        model=fast_model,
        name=f"coder_{task['id'].replace('-', '_')}",
        description="Agent développeur capable d'explorer le projet, d'écrire, lire, modifier du code.",
        verbosity_level=resolve_verbosity("HIGH"),
        max_steps=10,  # Augmenté à 10 pour laisser le temps de lire, écrire et tester
    )

    import sys
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

    import os
    
    # Liste uniquement les chemins des SKILL.md pour éviter de surcharger le contexte du LLM
    skills_content = ""
    skills_dir = "skills"
    if os.path.exists(skills_dir):
        skills_content += "Tu peux utiliser l'outil 'read_file' pour lire les instructions détaillées de ces compétences si tu en as besoin :\n"
        for root, dirs, files in os.walk(skills_dir):
            if "SKILL.md" in files:
                skill_path = os.path.join(root, "SKILL.md").replace("\\", "/")
                skills_content += f"- {skill_path}\n"

    target_files_instruction = ""
    if "target_files" in task and task["target_files"]:
        files_list = "\n".join([f"- {f}" for f in task["target_files"]])
        target_files_instruction = f"\nFICHIERS CIBLES (TU DOIS IMPÉRATIVEMENT CRÉER/MODIFIER CES FICHIERS) :\n{files_list}\n"

    prompt = f"""Tu es un Agent Développeur Senior autonome. Ta mission est d'accomplir la tâche suivante en utilisant tes outils de manière itérative.

MÉTHODOLOGIE OBLIGATOIRE :
1. ÉDITION : Préfère 'edit_file' pour modifier chirurgicalement un fichier existant. N'utilise 'write_file' que pour créer de nouveaux fichiers.
2. AUCUN MOCK OU PLACEHOLDER : Tu dois écrire une implémentation COMPLÈTE, RÉELLE et FONCTIONNELLE. Il est strictement interdit d'écrire des simulations (mocks), des carrés vides ou des commentaires du type "Logique ici". Si on te demande un Tetris, code un vrai Tetris avec les vraies règles.
{target_files_instruction}
### TES COMPÉTENCES (SKILLS)
Voici les instructions et compétences que tu DOIS respecter et utiliser selon la situation :
{skills_content}

Contenu de la tâche : {task['content']}

IMPORTANT : Prends ton temps, tu peux utiliser tes outils autant de fois que nécessaire.
Une fois que tu as terminé, vérifie ton travail. Puis retourne ton résultat final STRICTEMENT en utilisant l'outil 'final_answer'.
Ton JSON DOIT absolument respecter ce format exact pour appeler l'outil final_answer :
{{
  "name": "final_answer",
  "arguments": {{
    "answer": {{
      "task_id": "{task['id']}",
      "status": "success ou failure",
      "details": "Un résumé technique détaillé des fichiers modifiés et des actions effectuées."
    }}
  }}
}}
"""
    # max_retries can be slightly higher for coding since it involves tool use steps
    return await run_with_retry(local_coder, prompt, CoderOutput, settings.worker_max_retries)


async def execute_tester_node(
    task: dict,
    reasoning_model: OpenAIServerModel,
    settings: Settings,
) -> Tuple[Optional[CoderOutput], Optional[NodeMetrics]]:
    """Nœud Testeur : utilise Chrome DevTools via MCP pour tester les applications web."""
    import os
    from mcp import StdioServerParameters
    from smolagents import ToolCollection

    # Configure the MCP server for Chrome DevTools
    env = os.environ.copy()
    env["PUPPETEER_EXECUTABLE_PATH"] = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    
    server_parameters = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-puppeteer"],
        env=env
    )

    # Note: Using the context manager ensures the MCP server is properly closed after the run
    # For now, we load tools inside the execution loop
    with ToolCollection.from_mcp(server_parameters, trust_remote_code=True) as tool_collection:
        local_tester = ToolCallingAgent(
            tools=[*tool_collection.tools],
            model=reasoning_model,
            name=f"tester_{task['id'].replace('-', '_')}",
            description="Agent QA chargé de tester les interfaces web avec le MCP Chrome DevTools.",
            verbosity_level=resolve_verbosity("HIGH"),
        )

        skill_path = os.path.join("skills", "web-tester", "SKILL.md")
        skill_content = ""
        if os.path.exists(skill_path):
            with open(skill_path, "r", encoding="utf-8") as f:
                skill_content = f.read()

        workspace_url = "file:///" + os.path.abspath(os.getcwd()).replace("\\", "/")
        
        target_files_urls = ""
        if "target_files" in task and task["target_files"]:
            target_files_urls = "Les fichiers cibles de cette tâche se trouvent aux adresses suivantes :\n"
            for fpath in task["target_files"]:
                file_url = f"{workspace_url}/{fpath.replace('\\', '/')}"
                target_files_urls += f"- {file_url}\n"
        
        prompt = f"""Tu es un agent QA autonome (Web Tester Node).
        
Voici tes instructions obligatoires (Skill) :
{skill_content}

Contenu de la tâche d'origine : {task['content']}

ATTENTION - Le dossier de travail absolu est : {workspace_url}
{target_files_urls}
Pour utiliser 'puppeteer_navigate', tu dois lui passer l'URL complète du fichier principal, par exemple : {workspace_url}/index.html ou l'une des adresses ci-dessus.

Vérifie l'application web générée. Utilise tes outils MCP pour naviguer, inspecter et interagir.
Une fois terminé, retourne ton résultat final STRICTEMENT en utilisant l'outil 'final_answer'.
Ton JSON DOIT absolument respecter ce format exact pour appeler l'outil final_answer :
{{
  "name": "final_answer",
  "arguments": {{
    "answer": {{
      "task_id": "{task['id']}",
      "status": "success ou failure",
      "details": "Un résumé détaillé de tes tests visuels et interactifs."
    }}
  }}
}}
"""
        return await run_with_retry(local_tester, prompt, CoderOutput, settings.worker_max_retries)


async def execute_security_reviewer_node(
    task: dict,
    reasoning_model: OpenAIServerModel,
    settings: Settings,
) -> Tuple[Optional[SecurityOutput], Optional[NodeMetrics]]:
    """Nœud Auditeur de Sécurité : paranoïaque, inspecte le code à la recherche de failles."""
    local_security = ToolCallingAgent(
        tools=[read_file, bash_command], # Peut lire le code et lancer des linters de sécurité
        model=reasoning_model,
        name=f"security_{task['id'].replace('-', '_')}",
        description="Auditeur de sécurité paranoïaque qui cherche des vulnérabilités dans le code.",
        verbosity_level=resolve_verbosity("HIGH"),
    )

    prompt = f"""Tu es un Auditeur de Sécurité (Security Reviewer Agent). Tu es PARANOÏAQUE.
Ton seul but est de prouver que le code écrit par le Coder n'est pas sécurisé.

Contenu de la tâche d'origine : {task['content']}

MÉTHODOLOGIE :
1. Utilise 'read_file' pour lire les fichiers qui ont été modifiés ou créés.
2. Traque les vulnérabilités classiques (injections, XSS, authentification manquante, données exposées, etc.).
3. N'hésite pas à être très strict.

Retourne ton verdict STRICTEMENT en utilisant l'outil 'final_answer'.
Ton JSON DOIT absolument respecter ce format exact pour appeler l'outil final_answer :
{{
  "name": "final_answer",
  "arguments": {{
    "answer": {{
      "task_id": "{task['id']}",
      "is_secure": true,
      "vulnerabilities": ["faille 1 expliquée", "faille 2 expliquée"]
    }}
  }}
}}
"""
    return await run_with_retry(local_security, prompt, SecurityOutput, settings.worker_max_retries)


async def execute_code_judge_node(
    task: dict,
    tester_result: Optional[CoderOutput],
    security_result: Optional[SecurityOutput],
    fast_model: OpenAIServerModel,
    settings: Settings,
) -> Tuple[Optional[CodeJudgeOutput], Optional[NodeMetrics]]:
    """Nœud Juge de Code (Fan-in) : utilise l'API Ollama native avec Structured Outputs pour garantir un JSON parfait."""
    import requests
    import json
    import time
    
    tester_data = tester_result.model_dump() if tester_result else {"status": "skipped", "details": "Pas de tests."}
    security_data = security_result.model_dump() if security_result else {"is_secure": True, "vulnerabilities": []}

    prompt = f"""Tu es le Juge Suprême de la Pull Request (Judge Panel). 
Tu te trouves à une barrière de convergence (Fan-in). Tu dois lire les rapports du Testeur et de l'Auditeur de Sécurité, et prendre une décision finale.

Contenu de la tâche d'origine : {task['content']}

Rapport du Testeur : {json.dumps(tester_data, ensure_ascii=False)}
Rapport de Sécurité : {json.dumps(security_data, ensure_ascii=False)}

RÈGLES DE JUGEMENT :
- Si le Testeur signale une erreur ("status": "error") -> REJET (is_approved=false).
- Si la Sécurité signale une faille (is_secure=false) -> REJET (is_approved=false).
- Sinon -> APPROBATION (is_approved=true).

Explique ta décision dans final_feedback.
"""
    
    # Payload natif pour Ollama API (bypass smolagents)
    schema = CodeJudgeOutput.model_json_schema()
    payload = {
        "model": settings.fast_model_id,
        "messages": [
            {"role": "system", "content": "Tu es un juge impitoyable. Réponds STRICTEMENT en JSON."},
            {"role": "user", "content": prompt}
        ],
        "format": schema,
        "stream": False,
        "options": {"temperature": 0.0}
    }
    
    start_time = time.time()
    try:
        # Appel direct à Ollama (on remplace /v1 par /api/chat pour l'API native)
        api_url = settings.ollama_api_base.replace("/v1", "/api/chat")
        response = await asyncio.to_thread(requests.post, api_url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        raw_json = data["message"]["content"]
        validated = CodeJudgeOutput.model_validate_json(raw_json)
        
        # Extraction manuelle des métriques Ollama
        metrics = NodeMetrics(
            node=f"code_judge_{task['id']}",
            model=settings.fast_model_id,
            duration_s=data.get("total_duration", 0) / 1e9 or (time.time() - start_time),
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )
        return validated, metrics
        
    except Exception as e:
        print(f"[-] Erreur de l'API Ollama (Code Judge) : {e}")
        return None, None


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

Retourne ton verdict STRICTEMENT en utilisant l'outil 'final_answer'.
Ton JSON DOIT absolument respecter ce format exact pour appeler l'outil final_answer :
{{
  "name": "final_answer",
  "arguments": {{
    "answer": {{
      "verdicts": [
        {{"task_id": "t1", "refuted": false, "reason": "fidèle au contenu"}},
        {{"task_id": "t2", "refuted": true, "reason": "hallucination : chiffre inventé"}}
      ]
    }}
  }}
}}

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


# NOTE: hitl_checkpoint a été déplacé vers graph_orchestrator/hitl.py (HITL stratégique,
# Phase 6) avec un routage conditionnel (should_trigger_hitl) et un affichage de provenance.
