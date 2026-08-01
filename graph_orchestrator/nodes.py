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
from .tools import read_file, write_file, append_file, edit_file, bash_command, list_directory, search_replace
from .skills_loader import build_skills_block
from .loop_guard import LoopGuard, extract_tool_calls_from_step
from .orphan_repair import repair_orphan_steps
from .sanitizer import sanitize_tools

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
    # max_tokens généreux OBLIGATOIRE pour le Coder : un fichier HTML/CSS/JS complet
    # dépasse facilement 2000-4000 tokens. Sans budget suffisant, Ollama coupe la
    # génération en plein milieu d'un tool_call JSON (finish_reason=length) et le
    # contenu du fichier est corrompu/tronqué (cf. bug run #3 : garbage échappé).
    # NOTE : les Qwen3.5 ont un mode "thinking" qui consomme une partie du budget ;
    # on le laisse activé (aide au raisonnement tool-calling) mais le budget haut
    # garantit qu'il reste assez de tokens pour le contenu réel du fichier.
    # Timeout : sans lui, un endpoint Ollama distant muet fige le workflow.
    # Température BASSE (0.2) : CRITIQUE pour le code. Le défaut serveur de
    # qwen3.5:4b est temperature=1.0 (chat créatif) → choix de tokens aléatoires
    # qui corrompent la syntaxe HTML/JSON. Une température basse rend le Coder
    # quasi-déterministe : code cohérent, moins d'hallucinations de format.
    return OpenAIServerModel(
        model_id=settings.fast_model_id,
        api_base=settings.ollama_api_base,
        api_key=settings.ollama_api_key,
        max_tokens=settings.fast_max_tokens,
        temperature=settings.coder_temperature,
        client_kwargs={"timeout": settings.llm_timeout_s},
    )


def build_reasoning_model(settings: Settings) -> OpenAIServerModel:
    # max_tokens généreux obligatoire pour Gemma : sans ça, Ollama renvoie
    # finish_reason=length sans tool_calls (le raisonnement interne consomme tout).
    return OpenAIServerModel(
        model_id=settings.reasoning_model_id,
        api_base=settings.ollama_reasoning_api_base,
        api_key=settings.ollama_api_key,
        max_tokens=settings.reasoning_max_tokens,
        client_kwargs={"timeout": settings.llm_timeout_s},
    )


# ==========================================
# Retry + métriques
# ==========================================

def _detect_idle_step(agent) -> Optional[str]:
    """F-33 (guard logiciel) : détecte un tour SANS tool call exécuté (modèle réfléchit sans agir).

    Inspecte le dernier step de agent.memory.steps. Si ce step n'a produit AUCUN appel
    d'outil (uniquement du text/reasoning), c'est le failure mode "reasoning-action dilemma"
    observé sur gemma (le modèle dit "I will start by generating the CSS" mais n'émet
    jamais l'appel). On renvoie un message pédagogique à ré-injecter (style openfox
    FORMAT_CORRECTION_PROMPT) ; sinon None.

    Un ActionStep smolagents est "productif" s'il a : tool_calls (TCA), code_action
    (CodeAgent), ou des observations (résultat d'outil). Un step "idle" = aucun des 3.
    """
    try:
        steps = getattr(getattr(agent, "memory", None), "steps", None)
        if not steps:
            return None
        last = steps[-1]
        # Champs réels d'un ActionStep smolagents (dataclass) :
        # tool_calls (TCA) | code_action (CodeAgent) | observations (résultat d'outil).
        has_tool_use = (
            bool(getattr(last, "tool_calls", None))
            or bool(getattr(last, "code_action", None))
            or bool(getattr(last, "observations", None))
        )
        if not has_tool_use:
            return (
                "ATTENTION : ta dernière réponse ne contenait AUCUN appel d'outil exécuté "
                "(tu as réfléchi sans agir). Tu DOIS appeler un outil (write_file, append_file, "
                "search_replace) ou final_answer dans ton prochain bloc de code. Une réponse "
                "sans action est un ÉCHEC."
            )
    except Exception:
        pass
    return None


async def run_with_retry(
    agent: ToolCallingAgent,
    prompt: str,
    model_class: type,
    max_retries: int,
    loop_guard: Optional["LoopGuard"] = None,
) -> Tuple[Optional[object], Optional[NodeMetrics]]:
    """Exécute un agent avec retry. Retourne (données_validées, métriques).

    Les métriques (tokens/durée) viennent du RunResult de smolagents
    (return_full_result=True). En cas d'échec définitif, les métriques du dernier
    essai sont quand même renvoyées pour l'observabilité.

    F-33 (guard logiciel) : un prompt seul ne suffit jamais (leçon majeure des audits —
    les 5 projets matures couplent le prompt à un guard logiciel). On ajoute 2 détections :
    (1) tour sans tool call exécuté → message anti "reasoning sans action" ;
    (2) exception de parsing (code Python cassé) → message "découpe au lieu de recommencer"
        (inspiration deer-flow dangling_tool_call_middleware).

    P3 (Anti-Loop Cryptographique) : si un `loop_guard` est passé, on enregistre
    chaque tool call exécuté. Quand l'agent répète EXACTEMENT le même appel
    `threshold` fois, on interrompt immédiatement (circuit-breaker) au lieu de
    le laisser brûler des tokens. Inspiré de Crush.
    """
    last_metrics: Optional[NodeMetrics] = None
    # Détecte si l'agent est un CodeAgent (P1) pour adapter le message de retry
    # (final_answer en Python, pas en JSON). Le TCA garde son message historique.
    is_code_agent = type(agent).__name__ == "CodeAgent"

    for attempt in range(max_retries):
        # P8 (Orphan Repair) : avant chaque exécution, on répare les appels d'outil
        # orphelins de la mémoire (tool_calls sans observation/erreur). Un historique
        # restauré depuis un checkpoint peut contenir un appel interrompu ; renvoyé
        # tel quel à l'API, il ferait crasher le graphe. On injecte une fausse réponse
        # "Interrompu" pour permettre la reprise. Défensif (jamais bloquant).
        try:
            mem_steps = getattr(getattr(agent, "memory", None), "steps", None)
            if mem_steps:
                n_orphan = repair_orphan_steps(mem_steps)
                if n_orphan:
                    print(
                        f"[Orphan Repair] {n_orphan} appel(s) d'outil orphelin(s) "
                        f"réparé(s) avant exécution."
                    )
        except Exception:
            pass
        # F-33 (2) : tool call cassé (ex: triple-quote non fermée en CodeAgent).
        # On attrape l'exception de parsing et on renvoie un message "découpe" (deer-flow).
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

            # P3 (Anti-Loop) : enregistre les tool calls de CETTE exécution dans
            # le guard. On scanne tous les steps produits (un agent.run peut
            # enchaîner plusieurs ActionStep). Si une action dépasse le seuil de
            # répétition, on interrompt tout de suite — inutile de parser/valider
            # une sortie produite en bouclant.
            if loop_guard is not None:
                steps = getattr(getattr(agent, "memory", None), "steps", None) or []
                for step in steps:
                    for tname, targs in extract_tool_calls_from_step(step):
                        loop_guard.record(tname, targs)
                loop_msg = loop_guard.repeated_action()
                if loop_msg:
                    print(
                        f"[!] Anti-Loop (Tentative {attempt + 1}/{max_retries}) : "
                        f"action répétée {loop_guard.threshold}+ fois → circuit-breaker."
                    )
                    # On ne renvoie pas None silencieusement : on injecte le
                    # message dans le prompt pour un éventuel retry, qui aura
                    # une chance de casser la boucle (si retries restants).
                    prompt += f"\n\n{loop_msg}"
                else:
                    if validated:
                        return validated, last_metrics
            else:
                if validated:
                    return validated, last_metrics

            # F-33 (1) : tour sans tool call exécuté ? (modèle réfléchit sans agir)
            idle_msg = _detect_idle_step(agent)
            if idle_msg:
                print(
                    f"[!] Tentative {attempt + 1}/{max_retries} : tour sans appel d'outil "
                    f"({model_class.__name__}). Ré-injection d'une consigne d'action..."
                )
                prompt += f"\n\n{idle_msg}"
            else:
                print(
                    f"[!] Tentative {attempt + 1}/{max_retries} échouée pour "
                    f"{model_class.__name__}. Nouvelle tentative..."
                )
                # Message de retry adapté au type d'agent (Python pour CodeAgent, JSON pour TCA).
                if is_code_agent:
                    prompt += (
                        f"\n\nRAPPEL: ton dernier essai n'a pas abouti. Appelle final_answer(...) "
                        f"en PYTHON avec un dict conforme au schéma {model_class.__name__}."
                    )
                else:
                    prompt += (
                        f"\n\nRAPPEL CRITIQUE: Tu as échoué au dernier essai. Renvoie STRICTEMENT "
                        f"un JSON valide pour ce schéma : {model_class.model_json_schema()} "
                        f"via l'outil final_answer."
                    )
        except Exception as e:
            # F-33 (2) : exception pendant l'exécution (code Python cassé en CodeAgent,
            # payload invalide en TCA). On renvoie un message "découpe" au lieu de planter.
            msg = str(e)
            print(f"[-] Erreur interne (Tentative {attempt + 1}/{max_retries}): {msg}")
            if is_code_agent and ("Syntax" in msg or "parse" in msg.lower() or "unterminated" in msg.lower()):
                prompt += (
                    "\n\nATTENTION : ton dernier bloc de code Python a échoué (syntaxe invalide : "
                    "string non fermée, parenthèse manquante...). NE RECOMMENCE PAS le même gros "
                    "payload — DÉCOUPE en plus petits append_file, chaque bloc syntaxiquement complet."
                )

        # FIX TOKEN EXPLOSION: Si on est arrivé ici (erreur ou JSON invalide),
        # l'agent a gardé tout son historique d'échec dans sa mémoire interne.
        # Au prochain tour de la boucle for, si on rappelle agent.run, il va TOUT renvoyer !
        # On doit purger la mémoire de l'agent avant le prochain essai.
        if hasattr(agent, "memory") and hasattr(agent.memory, "steps"):
            agent.memory.steps = []
        # P3 : alignement du guard sur la purge — le retry repart d'un historique
        # vierge, donc les comptes de répétition doivent repartir de zéro aussi
        # (sinon un bug d'une tentative précédente fait déclencher la suivante).
        if loop_guard is not None:
            loop_guard.reset()


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

# ---------------------------------------------------------------------------
# DEPRECATED (mode coding) : les versions DSPy dans dspy_nodes.py sont désormais
# utilisées par run_coding_workflow (import local). Ces versions smolagents/
# API-Ollama-native sont conservées pour référence mais ne sont plus appelées
# dans le workflow coding. Ne pas supprimer sans vérifier les autres modes.
# ---------------------------------------------------------------------------
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
    # F-42 (Sanitizer) : les arguments d'outil du petit LLM (Architect sur gemma
    # local) sont coerce best-effort vers le type déclaré avant exécution, pour
    # éviter les retries gaspillés sur les erreurs de validation de type.
    local_architect = CodeAgent(
        tools=sanitize_tools(
            [list_directory, read_file, bash_command, DuckDuckGoSearchTool(), query_duckdb_knowledge_graph],
            enabled=settings.sanitizer_enabled,
        ),
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
    from .context7_tool import context7_tools

    import sys
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

    # La connexion Context7 (MCP) doit rester ouverte PENDANT tout le run de
    # l'agent (sinon les outils deviennent inertes). On englobe donc la création
    # ET l'exécution de l'agent dans le `with`. Tolérance aux pannes : si pas de
    # clé ou connexion échouée, c7 = [] et le Coder tourne sans doc (backward-compat).
    with context7_tools() as c7_tools:
        # Outils fichiers + recherche. Context7 (doc de libs à jour) est ajouté si
        # CONTEXT7_API_KEY est configurée. Le Coder décide QUAND l'utiliser via le
        # skill context7-research (dormant sur vanilla, actif sur libs externes).
        coder_tools = [list_directory, read_file, write_file, append_file, edit_file, search_replace, DuckDuckGoSearchTool()]
        coder_tools.extend(c7_tools)
        # F-42 (Sanitizer) : coerce best-effort les arguments malformés du petit
        # LLM (ex: offset="1, 80" → 80) avant l'appel d'outil → moins de retries
        # gaspillées sur les erreurs de validation de type. Opt-out via settings.
        coder_tools = sanitize_tools(coder_tools, enabled=settings.sanitizer_enabled)

        # P1 : migration ToolCallingAgent → CodeAgent. Les petits modèles locaux (gemma)
        # ne savent pas émettre de tool_call JSON fiable (tool_calls=None, finish_reason=
        # 'stop' — le modèle "parle" de l'action au lieu de l'exécuter). CodeAgent génère
        # du PYTHON qui appelle les outils (write_file(path=..., content=...)) — beaucoup
        # plus naturel. Preuves empiriques : cf. log.md (3 comparatifs, CodeAgent produit
        # jusqu'à 91× plus de contenu que le TCA sur une même tâche).
        # final_answer s'appelle maintenant en SYNTAXE PYTHON : final_answer({...}) ou
        # final_answer("texte"), pas en JSON. extract_and_validate gère les 2 (dict + str).
        local_coder = CodeAgent(
            tools=coder_tools,
            model=fast_model,
            name=f"coder_{task['id'].replace('-', '_')}",
            description="Agent développeur capable d'explorer le projet, d'écrire, lire, modifier du code.",
            verbosity_level=resolve_verbosity("HIGH"),
            # 12 steps : borne le temps total. Un step CodeAgent = un code block complet
            # (peut enchaîner plusieurs write_file/append_file), donc 12 steps couvrent
            # largement un gros projet multi-fichiers + final_answer.
            max_steps=12,
            # On gère nous-mêmes le set d'outils (pas de python_interpreter natif ajouté).
            add_base_tools=False,
        )

        target_files_instruction = ""
        if "target_files" in task and task["target_files"]:
            files_list = "\n".join([f"- {f}" for f in task["target_files"]])
            target_files_instruction = f"""
### ⚠️ FICHIERS CIBLES — TU DOIS CRÉER CES FICHIERS (priorité absolue)
{files_list}

- 'write_file' crée automatiquement les sous-répertoires manquants : tu peux appeler
  'write_file' avec le chemin complet (ex: "landing_page/index.html") MÊME SI le dossier
  n'existe pas encore. N'essaie PAS de lister un dossier qui n'existe pas.
- Chaque fichier cible DOIT être créé. Ne passe pas au reste avant."""

        # Skills ciblés pour cette tâche (socle coder + spécialisés selon le contenu).
        # Le contenu des SKILL.md est injecté directement (pas une liste de chemins à
        # explorer), pour éviter la dispersion stérile du Coder vers les fichiers .md.
        skills_block = build_skills_block(task.get("content", ""))

        # F-32 : prompt réécrit selon la structure canonique des audits (references aider/
        # crush/opencode/openfox/deer-flow + web Anthropic/OpenAI/Cline/SWE-agent) :
        # Rôle → Règles critiques → Format sortie → One-shot → Workflow (adapté stratégie)
        # → Rappels (double-marquage primacy/recency). Corrige les 2 bugs observés :
        # (1) "réfléchit sans agir" (reasoning-action dilemma, petits modèles overthinkent),
        # (2) triple-quote non fermée (limite fenêtre génération).
        strategy = task.get("strategy", "simple")
        sections = task.get("sections", [])

        # Section workflow adaptée à la stratégie dictée par l'Architect (F-29).
        if strategy == "incremental":
            sections_str = ", ".join(sections) if sections else "(sections à définir)"
            strategy_block = f"""### WORKFLOW (stratégie INCREMENTAL imposée par l'Architect)
Construis ce gros fichier monolithique EN PLUSIEURS PETITES ÉTAPES. NE TENTE PAS un seul
write_file massif (ça s'essouffle/tronque). Procède ainsi :
1. write_file(squelette) UNE SEULE FOIS : la structure HTML de base AVEC des MARQUEURS
   d'insertion ouverts (ex: <!-- INSERT_CSS -->, <!-- INSERT_JS -->). Le squelette ne doit
   PAS être fermé par </html> tant que les sections ne sont pas injectées — sinon les
   appends arrivent après </html> et le navigateur affiche du texte brut.
2. Pour CHAQUE section ({sections_str}) : append_file(content=section) qui remplace/ajoute
   le contenu au bon endroit. Chaque appel ≤ 60 lignes, chaque bloc syntaxiquement complet.
3. Une fois toutes les sections injectées, ferme proprement (</body></html>).
4. final_answer quand c'est terminé."""
        elif strategy == "multifile":
            strategy_block = """### WORKFLOW (stratégie MULTIFILE imposée par l'Architect)
Construis chaque fichier cible de façon autonome (1 module logique = 1 fichier, chacun
< ~200 lignes). Tu PEUX enchaîner plusieurs write_file dans le même bloc de code.
1. Pour chaque fichier cible : write_file(path=..., content=...) avec le contenu COMPLET.
2. final_answer quand tous les fichiers sont créés."""
        else:  # simple (défaut, rétro-compat)
            strategy_block = """### WORKFLOW (stratégie SIMPLE)
1. write_file(path=..., content=...) pour créer le fichier cible (contenu complet).
2. final_answer quand c'est terminé."""

        prompt = f"""Tu es un Agent Développeur Senior. Tu DOIS produire du code en appelant tes outils via du PYTHON. NE JAMAIS expliquer sans agir.

### RÈGLES CRITIQUES (numérotées)
1. AGIS, ne raconte pas : quand tu dis "je vais faire X", tu DOIS faire X dans la foulée.
   Une réponse sans appel d'outil est considérée comme une TÂCHE TERMINÉE (échec).
2. BLOCS COMPLETS : chaque appel write_file/append_file doit contenir un bloc SYNTAXIQUEMENT
   COMPLET (quotes/braces/parenthèses équilibrées). NE JAMAIS laisser une string/brace
   ouverte entre 2 appels. Si le contenu dépasse ~60 lignes, DÉCOUPE en plusieurs append_file.
3. PAS DE PLACEHOLDER : interdiction absolue de "TODO", "...", "Logique ici", fonctions vides
   ou mocks. Implémentation COMPLÈTE, RÉELLE et FONCTIONNELLE.
4. ANTI-BOUCLE : NE RE-ÉCRIS JAMAIS avec write_file un fichier déjà créé (ça l'écrase).
   Pour AJOUTER du contenu → append_file. Pour MODIFIER un fragment → search_replace.

### FORMAT DE SORTIE (obligatoire)
Tu écris du code Python dans un bloc ```python``` qui appelle tes outils. Exemple one-shot :
```python
# Thought courte (1 phrase) PUIS appel immédiat — pas de longue réflexion
resultat = write_file(path="index.html", content="<!DOCTYPE html>\\n<html>...</html>")
print(resultat)
# ... autres appels ...
final_answer({{"task_id": "{task['id']}", "status": "success", "details": "Fichiers créés."}})
```

{strategy_block}
{target_files_instruction}

### OUTILS DISPONIBLES
- `write_file(path, content)` : CRÉE/ÉCRASE un fichier complet. Sous-dossiers créés auto.
- `append_file(path, content)` : AJOUTE un bloc à la FIN d'un fichier existant (garde anti-doublon).
- `search_replace(path, search, replace)` : MODIFIE un fragment (matching tolérant). À utiliser après read_file.
- `read_file(path)` / `list_directory(path)` : lecture/exploration.
- `context7` (resolve_library_id/query_docs) : UNIQUEMENT pour une lib externe (React, Chart.js...). JAMAIS pour du vanilla.
- Évite DuckDuckGoSearchTool (lent/imprécis).

### EXIGENCE DE QUALITÉ
Code prêt pour la production, respectant les conventions du langage.
{skills_block}

### Contenu de la tâche
{task['content']}

### RAPPEL (récence)
- AGIS via des appels d'outils Python, ne raconte pas.
- Chaque bloc syntaxiquement complet, ≤ 60 lignes ou découpe via append_file.
- AUCUN placeholder. final_answer quand les fichiers cibles sont créés.
"""
        # P3 (Anti-Loop Cryptographique) : instancie un guard pour CETTE exécution
        # du Coder. Seul le Coder appelle des outils d'écriture → seul candidat
        # où la boucle "même tool call X fois" est un failure mode réel (le
        # failure mode classique : le modèle ré-écrit le même fichier à l'identique
        # en boucle jusqu'à épuisement des steps). Le guard est aussi réinitialisé
        # entre les retries dans run_with_retry (aligné sur la purge mémoire).
        guard = LoopGuard(
            threshold=settings.loop_guard_threshold,
            enabled=settings.loop_guard_enabled,
        )
        # max_retries can be slightly higher for coding since it involves tool use steps
        return await run_with_retry(
            local_coder, prompt, CoderOutput, settings.worker_max_retries, loop_guard=guard
        )


async def execute_tester_node(
    task: dict,
    reasoning_model: OpenAIServerModel,
    settings: Settings,
) -> Tuple[Optional[CoderOutput], Optional[NodeMetrics]]:
    """Nœud Testeur POLYVALENT : dispatche vers le runner adapté à la techno.

    Historiquement, ce nœud était 100% dédié au web (MCP Puppeteer). Il est
    désormais techno-agnostique : il détecte la techno de la sous-tâche
    (détection redondante Router + extensions) puis route vers le bon runner
    (WebTestRunner, PythonTestRunner, ...). Fallback web si techno inconnue
    (compatibilité arrière).

    La logique spécifique à chaque techno vit dans `graph_orchestrator/testers/`.
    """
    from .testers import detect_tech, get_runner

    # La techno peut être déjà fournie structurellement (ex: propagated depuis le
    # routeur), sinon on la détecte depuis les extensions + le lang routeur.
    tech = task.get("tech") or detect_tech(task, task.get("router_lang"))

    print(f"[*] Tester polyvalent : techno détectée = '{tech}' pour {task.get('id')}")

    runner = get_runner(tech)
    return await runner.run(task, reasoning_model, settings)


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


# DEPRECATED (mode coding) : voir la note ci-dessus. Version dspy_nodes utilisée
# par run_coding_workflow. Conservée pour référence.
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
