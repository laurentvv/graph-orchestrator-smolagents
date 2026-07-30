"""Nœuds du graphe cognitif implémentés avec DSPy (Declarative Self-improving Python).

Ce module constitue le cœur de la nouvelle architecture "Cerveaux vs Mains".
Il remplace les anciens nœuds basés sur des prompts manuels dans smolagents (qui échouaient souvent
à formater correctement le JSON) par des nœuds DSPy fortement typés.

Concepts clés utilisés :
1. **Signatures (dspy.Signature)** : Définit mathématiquement l'entrée (InputField) et la sortie attendue (OutputField).
2. **Pydantic Models** : L'OutputField est typé avec des objets Pydantic (importés de models.py), forçant le JSON Mode.
3. **ChainOfThought** : Module DSPy qui injecte une étape de réflexion ('reasoning') avant la génération du JSON, ce qui prévient les boucles infinies et les erreurs de token sur les petits modèles (Qwen, Gemma).

Les agents d'exécution (Codeur, Testeur) restent sous la responsabilité de `smolagents` car ils nécessitent
un bac à sable d'exécution interactif (navigateur MCP, bash).
"""

import asyncio
import time
from typing import List, Optional, Tuple, Any
import dspy

from .config import Settings
from .feedback_utils import truncate_output
from .logging_utils import NodeMetrics
from .models import (
    ArchitectOutput,
    CodeJudgeOutput,
    RouterOutput,
    SecurityOutput,
)


# ==========================================
# Signatures DSPy (Contrats Déclaratifs)
# ==========================================

class RouterSignature(dspy.Signature):
    """Analyse la requête de l'utilisateur pour déterminer la technologie principale requise et la stratégie de routage.
    
    Cette signature agit comme le premier filtre de l'orchestrateur. Elle détermine :
    - Si l'architecture nécessite une phase de planification (architect_plan_required).
    - Si une revue de sécurité stricte est requise.
    - Quel langage de programmation principal est concerné (ex: 'python', 'javascript').
    """
    task_content: str = dspy.InputField(desc="La requête initiale ou directive de l'utilisateur fournie au graphe")
    output: RouterOutput = dspy.OutputField(desc="Décision de routage structurée, typée strictement par le schéma Pydantic RouterOutput")


class ArchitectSignature(dspy.Signature):
    """Analyse une tâche et génère un plan d'architecture en sous-tâches UNITAIRES (1 fichier = 1 sous-tâche).

    RÈGLE DE DÉCOUPAGE (très important) :
    - Une sous-tâche = UN seul fichier cible à créer de façon autonome et complète.
    - N'invente PAS de sous-tâches redondantes (ex: une sous-tâche "setup" + une "structure" pour
      le même fichier). Chaque fichier = exactement UNE sous-tâche.
    - Vise le MINIMUM de sous-tâches : si la tâche mentionne 3 fichiers (index.html, styles.css,
      script.js), génère EXACTEMENT 3 sous-tâches (une par fichier), pas 5.
    - Le découpage granulaire (5+ sous-tâches) est contre-productif : chaque sous-tâche déclenche
      un agent Coder complet (coûteux). Privilégie 2-4 sous-tâches cohérentes par fichier.

    L'Architecte planifie, il ne code pas.
    """
    task_content: str = dspy.InputField(desc="Le cahier des charges global de la fonctionnalité ou du projet à développer")
    output: ArchitectOutput = dspy.OutputField(desc="Plan : liste de sous-tâches (1 par fichier cible, 2-4 max). Chaque ArchitectPlanItem a un target_files=[fichier_unique].")


class SecuritySignature(dspy.Signature):
    """Audite le code source fourni pour détecter des vulnérabilités de sécurité potentielles.
    
    Agit comme un hacker éthique / auditeur paranoïaque.
    L'objectif est d'identifier de potentielles failles (XSS, injections, fuite de mémoire, etc.)
    dans le bloc de code généré par le CodeAgent.
    """
    task_id: str = dspy.InputField(desc="L'identifiant unique de la tâche pour la traçabilité")
    code: str = dspy.InputField(desc="Le bloc de code source brut généré par le Coder à inspecter")
    output: SecurityOutput = dspy.OutputField(desc="Liste stricte des vulnérabilités trouvées via le schéma SecurityVulnerability")


class CodeJudgeSignature(dspy.Signature):
    """Évalue l'implémentation globale d'un CodeAgent en fusionnant toutes les métriques et rapports.
    
    Le Juge est le dernier rempart avant la validation de la sous-tâche (Merge PR). 
    Il analyse le code source, les retours des tests unitaires (QA) et les rapports de sécurité, 
    puis tranche : soit il approuve (is_approved=True), soit il refuse et fournit un feedback pour la prochaine itération.
    """
    task_id: str = dspy.InputField(desc="Identifiant de la tâche examinée")
    code: str = dspy.InputField(desc="Le code source final soumis par le CodeAgent")
    security_vulnerabilities: List[str] = dspy.InputField(desc="Liste des problèmes de sécurité soulevés par le Security Reviewer")
    test_results: str = dspy.InputField(desc="Sortie brute des tests fonctionnels exécutés par l'agent QA")
    output: CodeJudgeOutput = dspy.OutputField(desc="Le verdict final, approuvant ou rejetant le code avec justifications")


# ==========================================
# Configuration DSPy
# ==========================================

def _configure_dspy(settings: Settings, model_id: str):
    """Configure dynamiquement DSPy pour pointer vers une instance locale Ollama.

    Timeout appliqué : sans lui, un endpoint Ollama distant muet fige le nœud DSPy
    (bug observé sur le serveur distant 10.201.12.50 qui répond au /api/tags mais
    timeout sur l'inférence). Le timeout permet à l'appel d'échouer proprement.
    """
    api_base = settings.ollama_reasoning_api_base if model_id == settings.reasoning_model_id else settings.ollama_api_base
    lm = dspy.LM(
        f"openai/{model_id}",
        api_base=api_base,
        api_key="sk-none",
        max_tokens=8192,
        temperature=0.3,
        timeout=settings.llm_timeout_s,
    )
    return lm


# ==========================================
# Exécuteurs de Nœuds (Wrappers Asynchrones)
# ==========================================

async def execute_router_node(task_content: str, fast_model, settings: Settings) -> Tuple[Optional[RouterOutput], Optional[NodeMetrics]]:
    """Exécute le nœud de routage avec un modèle rapide.
    
    Args:
        task_content (str): La requête brute de l'utilisateur.
        fast_model: Le modèle rapide issu de la configuration (utilisé ici pour le logging).
        settings (Settings): Configuration globale.
        
    Returns:
        Un tuple contenant l'objet Pydantic RouterOutput (ou None si échec) et les métriques du nœud.
    """
    print("[*] DSPy Routeur en cours...")
    lm = _configure_dspy(settings, settings.fast_model_id)
    start_time = time.time()
    try:
        with dspy.context(lm=lm):
            predictor = dspy.ChainOfThought(RouterSignature)
            # Exécution dans un thread séparé pour ne pas bloquer la boucle asynchrone (Event Loop) de smolagents
            result = await asyncio.to_thread(predictor, task_content=task_content)
        
        metrics = NodeMetrics(
            node="router_dspy", 
            model=settings.fast_model_id, 
            duration_s=time.time() - start_time, 
            input_tokens=0, 
            output_tokens=0
        )
        return result.output, metrics
    except Exception as e:
        print(f"[-] Erreur critique DSPy (Router) : {e}")
        return None, None


async def execute_architect_node(task: dict, reasoning_model, settings: Settings) -> Tuple[Optional[ArchitectOutput], Optional[NodeMetrics]]:
    """Exécute le nœud Architecte avec un modèle de raisonnement lourd.
    
    Args:
        task (dict): Dictionnaire contenant l'ID de la tâche et le contenu global.
        reasoning_model: Modèle lourd pour le logging.
        settings (Settings): Configuration globale.
        
    Returns:
        ArchitectOutput contenant la liste des sous-tâches pour le Fan-out des codeurs.
    """
    print("[*] DSPy Architecte en cours d'élaboration du plan...")
    lm = _configure_dspy(settings, settings.reasoning_model_id)
    start_time = time.time()
    try:
        with dspy.context(lm=lm):
            predictor = dspy.ChainOfThought(ArchitectSignature)
            result = await asyncio.to_thread(predictor, task_content=task.get("content", ""))
        
        metrics = NodeMetrics(
            node="architect_dspy", 
            model=settings.reasoning_model_id, 
            duration_s=time.time() - start_time, 
            input_tokens=0, 
            output_tokens=0
        )
        return result.output, metrics
    except Exception as e:
        print(f"[-] Erreur critique DSPy (Architect) : {e}")
        return None, None


async def execute_security_reviewer_node(subtask: dict, reasoning_model, settings: Settings) -> Tuple[Optional[SecurityOutput], Optional[NodeMetrics]]:
    """Exécute l'audit de sécurité sur le code produit par un Coder.
    
    Args:
        subtask (dict): La sous-tâche actuellement évaluée.
        reasoning_model: Modèle lourd.
        settings (Settings): Configuration globale.
    """
    print(f"[*] DSPy Security Reviewer sur la tâche {subtask.get('id')}...")
    lm = _configure_dspy(settings, settings.reasoning_model_id)
    
    # Lecture du code depuis le disque
    code_content = ""
    for file_path in subtask.get("target_files", []):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code_content += f"--- {file_path} ---\n{f.read()}\n\n"
        except Exception:
            pass
            
    start_time = time.time()
    try:
        with dspy.context(lm=lm):
            predictor = dspy.ChainOfThought(SecuritySignature)
            result = await asyncio.to_thread(predictor, task_id=subtask.get("id", "unknown"), code=code_content or "Code manquant")
        
        metrics = NodeMetrics(
            node="security_dspy", 
            model=settings.reasoning_model_id, 
            duration_s=time.time() - start_time, 
            input_tokens=0, 
            output_tokens=0
        )
        return result.output, metrics
    except Exception as e:
        print(f"[-] Erreur critique DSPy (Security) : {e}")
        return None, None


async def execute_code_judge_node(subtask: dict, test_res: Any, security_res: Optional[SecurityOutput], reasoning_model, settings: Settings) -> Tuple[Optional[CodeJudgeOutput], Optional[NodeMetrics]]:
    """Exécute le Juge final qui décide si la boucle de développement s'arrête.
    
    Args:
        subtask (dict): La sous-tâche évaluée.
        test_res (Any): La sortie de l'agent Testeur QA (smolagents).
        security_res (SecurityOutput): Les vulnérabilités identifiées à l'étape précédente.
        reasoning_model: Modèle lourd.
        settings (Settings): Configuration.
        
    Returns:
        CodeJudgeOutput dictant si le code est 'approved' ou s'il nécessite un feedback.
    """
    print(f"[*] DSPy Code Judge sur la tâche {subtask.get('id')}...")
    lm = _configure_dspy(settings, settings.reasoning_model_id)
    
    # Lecture du code depuis le disque
    code_content = ""
    for file_path in subtask.get("target_files", []):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code_content += f"--- {file_path} ---\n{f.read()}\n\n"
        except Exception:
            pass
            
    start_time = time.time()
    
    # Extraction sécurisée des tableaux pour éviter des erreurs Pydantic si les champs sont None
    vulns = security_res.vulnerabilities if security_res and hasattr(security_res, "vulnerabilities") else []
    # Le rapport du Tester peut être long (console JS, traceback). On le tronque AVANT
    # de l'injecter au Judge pour protéger le contexte (sinon overflow sur les gros échecs).
    tests_raw = str(test_res) if test_res else "Aucun résultat de test."
    tests = truncate_output(
        tests_raw,
        head_lines=settings.stderr_head_lines,
        tail_lines=settings.stderr_tail_lines,
        max_chars=settings.feedback_max_chars,
    )
    
    try:
        with dspy.context(lm=lm):
            predictor = dspy.ChainOfThought(CodeJudgeSignature)
            result = await asyncio.to_thread(
                predictor, 
                task_id=subtask.get("id", "unknown"), 
                code=code_content or "Code manquant", 
                security_vulnerabilities=vulns, 
                test_results=tests
            )
        
        metrics = NodeMetrics(
            node="code_judge_dspy", 
            model=settings.reasoning_model_id, 
            duration_s=time.time() - start_time, 
            input_tokens=0, 
            output_tokens=0
        )
        return result.output, metrics
    except Exception as e:
        print(f"[-] Erreur critique DSPy (CodeJudge) : {e}")
        return None, None
