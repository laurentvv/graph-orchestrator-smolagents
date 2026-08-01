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
import re
import time
from typing import List, Optional, Tuple, Any
import dspy

from .config import Settings
from .feedback_utils import truncate_output
from .logging_utils import NodeMetrics
from .models import (
    ArchitectOutput,
    CodeJudgeOutput,
    EscalationOutput,
    PromptRefinerOutput,
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


class PromptRefinerSignature(dspy.Signature):
    """Tu es un PromptRefiner : tu reformules le prompt utilisateur brut en une SPEC STRUCTURÉE
    et NON-AMBIGUË, directement exploitable par un Architect logiciel. Inspiré du pattern
    "Enhance Prompt" (Kilo Code / Cline / Roo Code).

    Pipeline obligatoire :
    1. CLARTÉ & DÉSAMBIGUÏSATION : détecte les termes VAGUES du prompt brut (ex: 'rapide',
       'user-friendly', 'flexible', 'moderne', 'optimisé', 'beau') et liste-les dans
       `ambiguities_detected`. Reformule-les en exigences mesurables (ex: 'rapide' →
       'temps de réponse < 200ms' SI chiffrable, sinon supprime/nuance).
    2. CONTEXTE : utilise `available_capabilities` pour ORIENTER la spec vers ce qui est
       faisable (web-tester → critères testables via navigateur ; python-tester → critères
       pytest ; context7 → note 'consulter la doc de la lib'). Tu ne fais que CITER, tu ne
       consommes pas ces capacités toi-même.
    3. FORMATAGE : structure la spec en sections fixes EXACTES :
         ## Objectif (1-3 phrases : outcome visible attendu)
         ## Fonctionnalités attendues (puces, chacune testable)
         ## Contraintes techniques (stack, format imposé, taille max si précisée)
         ## Critères de validation (Given/When/Then quand pertinent, sinon puces concrètes)
    4. COMPLÉTION LÉGÈRE : ajoute UNIQUEMENT les manques évidents et basiques (edge cases
       types : champ vide, données invalides, cas limite). N'AJOUTE JAMAIS de fonctionnalité
       que l'utilisateur n'a pas demandée (anti-hallucination de scope).

    RÈGLES CRITIQUES :
    - Tu STRUCTURES, tu n'INVENTES PAS. Si une exigence est absente du prompt brut, ne la
      fabrique pas — contente-toi de la signaler comme manquante dans une section 'À clarifier'.
    - CONCISION : ~30 lignes max. Une spec est un brief, pas un roman.
    - PRÉSERVE toute exigence EXPLICITE du prompt brut (stack imposée, format, nb d'éléments...).
    - Si le prompt brut est DÉJÀ clair et structuré, renvoie une spec quasi identique (ne dégrade
      pas une bonne entrée).
    """
    raw_prompt: str = dspy.InputField(desc="Le prompt utilisateur brut, souvent vague ou incomplet")
    available_capabilities: str = dspy.InputField(desc="Catalogue des capacités disponibles (skills, statut Context7, testers) pour orienter la spec vers ce qui est faisable")
    output: PromptRefinerOutput = dspy.OutputField(desc="Spec structurée (refined_prompt) + termes vagues détectés (ambiguities_detected)")


class ArchitectSignature(dspy.Signature):
    """Analyse une tâche et génère un plan d'architecture en sous-tâches UNITAIRES.

    RÈGLE DE DÉCOUPAGE :
    - Vise le MINIMUM de sous-tâches (2-4 max). Chaque sous-tâche déclenche un agent Coder
      complet (coûteux). Le découpage granulaire (5+) est contre-productif.

    RÈGLE DE STRATÉGIE (F-29 — très important, dicte COMMENT le Coder doit construire) :
    Pour CHAQUE sous-tâche, choisis une 'strategy' parmi :
    - 'simple' : petit fichier isolé, faisable en UN seul write_file. Utilise-la pour un
      script Python < ~200 lignes, un petit fichier autonome, un algorithme borné.
    - 'incremental' : gros fichier monolithique imposé par la spec (ex: un dashboard HTML
      complet dans un seul index.html). Le Coder construira le squelette PUIS remplira
      section par section via append_file. Dans ce cas, fournis aussi 'sections' = la liste
      des sections à construire (ex: ['css', 'sidebar', 'kpi', 'table', 'js']).
    - 'multifile' : projet multi-fichiers (ex: app Python avec models.py + api.py + utils.py,
      ou un site index.html + styles.css + script.js séparés). Chaque target_file reste
      petit (< ~200 lignes) et autonome. Utilise-la quand la spec ne force pas un monolithe.

    QUAND UTILISER QUOI :
    - HTML/CSS/JS : 'multifile' (index.html + styles.css + script.js séparés) PAR DÉFAUT,
      sauf si la spec impose explicitement un seul fichier → alors 'incremental'.
    - Python/TS   : 'multifile' (1 module logique = 1 fichier) PAR DÉFAUT.
    - Petit algo/fichier isolé : 'simple'.

    L'Architecte planifie, il ne code pas. Le Coder suivra ta stratégie à la lettre.
    """
    task_content: str = dspy.InputField(desc="Le cahier des charges global de la fonctionnalité ou du projet à développer")
    output: ArchitectOutput = dspy.OutputField(desc="Plan : liste de sous-tâches (2-4 max). Chaque ArchitectTask a target_files + strategy ('simple'|'incremental'|'multifile') + sections (si incremental).")


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
    task_requirements: str = dspy.InputField(desc="Le cahier des charges complet (comportements attendus). Sert à vérifier que le test_results couvre bien les comportements clés et que le code les implémente — pas seulement qu'il ne crash pas.")
    output: CodeJudgeOutput = dspy.OutputField(desc="Le verdict final, approuvant ou rejetant le code avec justifications")


class EscalationSignature(dspy.Signature):
    """Post-mortem d'une sous-tâche qui a épuisé le Circuit Breaker (3 itérations
    Coder↔Tester↔Judge toutes rejetées).

    Tu es un ingénieur principal menant une rétrospective d'incident. Tu reçois
    l'historique COMPLET des réfutations émises par le Juge (les bugs récurrents
    qui n'ont pas pu être résolus) et l'état actuel du code sur disque. Tu dois
    produire un diagnostic STRUCTURÉ et ACTIONNABLE — pas une simple description.

    Ton diagnostic doit permettre à un run futur (ou à un humain) de ne pas
    répéter les mêmes erreurs. Identifie la cause racine profonde (pas le
    symptôme de surface), liste objectivement ce qui a été tenté (anti-répétition),
    et formule une leçon concrète.
    """
    task_id: str = dspy.InputField(desc="Identifiant de la sous-tâche en échec")
    task_description: str = dspy.InputField(desc="Le cahier des charges / description de la sous-tâche")
    failure_history: str = dspy.InputField(desc="Historique concaténé des réfutations du Juge (bugs non résolus sur les 3 itérations). C'est la matière première du diagnostic.")
    current_code: str = dspy.InputField(desc="L'état actuel du code sur disque après le dernier échec")
    output: EscalationOutput = dspy.OutputField(desc="Diagnostic post-mortem structuré : cause racine, tentatives, leçon, gravité")


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


def _build_capabilities_summary(settings: Settings) -> str:
    """Construit le résumé des capacités disponibles injecté au PromptRefiner.

    Le PromptRefiner oriente la spec vers ce qui est faisable : pour ça il doit connaître
    le catalogue des skills + le statut Context7 + les testers. On construit une chaîne
    compacte (~15-25 lignes) à partir de 3 sources :

    1. SKILLS — on veut le catalogue COMPLET (choix utilisateur). La source la plus légère
       est `agent_server.skills.list_skills()` qui renvoie [{name, description}] en parsant
       le frontmatter (sans charger le corps complet, trop lourd pour ce nœud).
       COUPLAGE : `agent_server` est un package SÉPARÉ de `graph_orchestrator` (l'UI WebSocket
       vs le graphe). L'import est donc DÉFENSIF (local + try/except) pour ne jamais casser
       le graphe si l'UI est absente. Repli : lecture directe du dossier `skills/` via
       `skills_loader.SKILLS_DIR` + parse du frontmatter name/description.
    2. CONTEXT7 — statut dispo via la clé API (sans connexion réseau, juste un getenv).
       L'Architect fait déjà le pré-fetch Context7 (dspy_nodes.py:225) ; le PromptRefiner ne
       fait que CITER sa disponibilité (pas de duplication).
    3. TESTERS — statiques (capacités fixes du graphe) : Puppeteer web + pytest subprocess.

    Dégradation gracieuse : si tout échoue, renvoie "" (le PromptRefiner tourne sans
    catalogue — il structure quand même, juste sans orienter par les capacités).
    """
    lines: List[str] = []

    # 1. Skills (catalogue complet).
    skills_items: list[tuple[str, str]] = []  # [(name, description)]
    try:
        # Source privilégiée : agent_server.skills.list_skills (parse frontmatter propre).
        from agent_server.skills import list_skills  # type: ignore
        for s in list_skills() or []:
            name = (s.get("name") or "").strip()
            desc = (s.get("description") or "").strip()
            if name:
                skills_items.append((name, desc))
    except Exception:
        # Repli : lecture directe du dossier skills/ (même logique, indépendante de agent_server).
        try:
            from .skills_loader import SKILLS_DIR, _strip_frontmatter
            import os as _os
            if SKILLS_DIR and _os.path.isdir(SKILLS_DIR):
                for d in sorted(_os.listdir(SKILLS_DIR)):
                    skill_md = _os.path.join(SKILLS_DIR, d, "SKILL.md")
                    if not _os.path.isfile(skill_md):
                        continue
                    with open(skill_md, "r", encoding="utf-8") as f:
                        raw = f.read()
                    # Parse léger du frontmatter name/description (les 2 champs clés).
                    name, desc = "", ""
                    if raw.startswith("---"):
                        end = raw.find("---", 3)
                        if end != -1:
                            front = raw[3:end]
                            for line in front.splitlines():
                                if line.lower().startswith("name:") and not name:
                                    name = line.split(":", 1)[1].strip()
                                elif line.lower().startswith("description:") and not desc:
                                    desc = line.split(":", 1)[1].strip()
                    if name:
                        skills_items.append((name, desc))
        except Exception:
            pass  # dossier skills/ inaccessible → skills_items reste vide

    for name, desc in skills_items:
        lines.append(f"- {name}" + (f": {desc}" if desc else ""))

    # 2. Context7 (statut dispo, sans connexion).
    import os as _os
    c7_on = bool(_os.getenv("CONTEXT7_API_KEY"))
    lines.append(f"- context7 (doc libs à jour): {'DISPONIBLE' if c7_on else 'désactivé (pas de clé)'}")

    # 3. Testers (capacités fixes du graphe).
    lines.append("- web-tester: test navigateur (Puppeteer + assertions fonctionnelles)")
    lines.append("- python-tester: test pytest subprocess (déterministe)")

    header = "### CAPACITÉS DISPONIBLES (oriente la spec vers ce qui est faisable, ne les consomme pas toi-même)"
    return header + "\n" + "\n".join(lines)


async def execute_prompt_refiner_node(
    raw_prompt: str,
    reasoning_model,
    settings: Settings,
) -> Tuple[Optional[PromptRefinerOutput], Optional[NodeMetrics]]:
    """Exécute le nœud PromptRefiner (modèle de raisonnement).

    Reformule le prompt brut en spec structurée AVANT l'Architect. Clone du pattern
    execute_router_node (dspy.ChainOfThought + asyncio.to_thread + dégradation gracieuse),
    mais sur le modèle REASONING (gemma, plus coûteux mais meilleur pour la reformulation)
    et avec 2 inputs (raw_prompt + available_capabilities).

    Args:
        raw_prompt: Le prompt utilisateur brut (souvent vague).
        reasoning_model: Le modèle de raisonnement (non utilisé directement — on lit
            settings.reasoning_model_id via _configure_dspy, comme les autres nœuds DSPy).
        settings: Configuration globale.

    Returns:
        (PromptRefinerOutput | None, NodeMetrics | None). None,None si le LLM down
        (dégradation gracieuse : l'appelant repliera sur le prompt brut).
    """
    print("[*] DSPy PromptRefiner en cours (reformulation du prompt brut en spec)...")
    lm = _configure_dspy(settings, settings.reasoning_model_id)
    capabilities = _build_capabilities_summary(settings)
    start_time = time.time()
    try:
        with dspy.context(lm=lm):
            predictor = dspy.ChainOfThought(PromptRefinerSignature)
            result = await asyncio.to_thread(
                predictor,
                raw_prompt=raw_prompt,
                available_capabilities=capabilities,
            )
        refined = result.output
        n_amb = len(refined.ambiguities_detected) if refined.ambiguities_detected else 0
        print(f"[+] PromptRefiner : spec produite ({len(refined.refined_prompt)} caractères"
              f"{f', {n_amb} ambiguïté(s) détectée(s)' if n_amb else ''}).")

        metrics = NodeMetrics(
            node="prompt_refiner_dspy",
            model=settings.reasoning_model_id,
            duration_s=time.time() - start_time,
            input_tokens=0,
            output_tokens=0,
        )
        return refined, metrics
    except Exception as e:
        print(f"[-] Erreur critique DSPy (PromptRefiner) : {e} — repli sur prompt brut.")
        return None, None


# Garde-fou : évite un appel réseau Context7 (et sa latence) sur les tâches
# vanilla/algorithmiques, où la doc n'apporte rien. Cohérent avec le skill
# context7-research qui reste dormant sur le vanilla. Le pattern est la source
# unique de vérité (skills_loader.EXTERNAL_LIB_PATTERN) pour éviter la dérive.
from .skills_loader import EXTERNAL_LIB_PATTERN as _EXTERNAL_LIB_PATTERN

_EXTERNAL_LIB_RE = re.compile(_EXTERNAL_LIB_PATTERN, re.IGNORECASE)


def _mentions_external_lib(text: str) -> bool:
    """True si `text` mentionne une lib/framework externe (déclencheur Context7)."""
    return bool(_EXTERNAL_LIB_RE.search(text or ""))


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

    # Pré-fetch doc Context7 : l'Architect (DSPy, pas de boucle d'outils) ne peut
    # pas appeler Context7 lui-même. On lui injecte donc un brief doc à jour QUAND
    # le contenu mentionne une lib/framework externe (sinon 0 appel réseau — l'Architect
    # planifie à partir du seul prompt, comme avant). Graceful : brief vide si pas de clé.
    task_content_raw = task.get("content", "")
    architect_input = task_content_raw
    if _mentions_external_lib(task_content_raw):
        from .context7_tool import fetch_context7_brief
        brief = await asyncio.to_thread(fetch_context7_brief, task_content_raw)
        if brief:
            architect_input = f"{brief}\n\n---\n\n{task_content_raw}"
            print(f"[+] Architect : brief Context7 injecté ({len(brief)} caractères).")
        else:
            print("[*] Architect : Context7 indisponible/non pertinent — planification sans brief.")
    try:
        with dspy.context(lm=lm):
            predictor = dspy.ChainOfThought(ArchitectSignature)
            result = await asyncio.to_thread(predictor, task_content=architect_input)
        
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
            # task_requirements : le cahier des charges complet, pour que le Juge
            # vérifie que les comportements clés sont testés ET corrects (pas juste
            # que le code ne crash pas). Tronqué pour protéger le contexte.
            task_requirements = truncate_output(
                subtask.get("original_content", "") or "Cahier des charges non disponible.",
                head_lines=30,
                tail_lines=10,
                max_chars=1500,
            )
            result = await asyncio.to_thread(
                predictor,
                task_id=subtask.get("id", "unknown"),
                code=code_content or "Code manquant",
                security_vulnerabilities=vulns,
                test_results=tests,
                task_requirements=task_requirements,
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


async def execute_escalation_node(subtask: dict, failure_history: str, reasoning_model, settings: Settings) -> Tuple[Optional[EscalationOutput], Optional[NodeMetrics]]:
    """Exécute le nœud d'escalade : post-mortem d'une sous-tâche en échec répété.

    Déclenché quand le Circuit Breaker s'active (3 itérations Coder↔Tester↔Judge
    toutes rejetées). Au lieu d'abandonner la sous-tâche sans retour, ce nœud
    synthétise les réfutations accumulées dans le Knowledge Graph en un diagnostic
    structuré (cause racine + leçon + gravité), persisté dans le KG et exploitable
    par un run futur (un agent peut interroger ces post-mortem via
    query_duckdb_knowledge_graph, comme les bugs existants).

    Args:
        subtask (dict): La sous-tâche en échec (doit contenir 'id', 'description'
            optionnelle, 'target_files').
        failure_history (str): Historique des réfutations concaténé et tronqué
            (déjà borné par truncate_history côté appelant pour protéger le contexte).
        reasoning_model: Modèle de raisonnement (pour le logging — le nœud config
            DSPy pointe sur settings.reasoning_model_id).
        settings (Settings): Configuration globale.

    Returns:
        Un tuple (EscalationOutput | None, NodeMetrics | None). En cas d'échec
        LLM, retourne (None, None) — l'appelant retombe alors sur le comportement
        historique 'max_iterations_reached' (dégradation gracieuse).
    """
    print(f"[*] DSPy Nœud d'Escalade sur la tâche {subtask.get('id')} (circuit breaker activé)...")
    lm = _configure_dspy(settings, settings.reasoning_model_id)

    # Lecture du code courant sur disque (état final après le dernier échec).
    # Comme pour le Judge, on tronque pour protéger le contexte.
    code_content = ""
    for file_path in subtask.get("target_files", []):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code_content += f"--- {file_path} ---\n{f.read()}\n\n"
        except Exception:
            pass
    current_code = truncate_output(
        code_content or "Code manquant",
        head_lines=settings.stderr_head_lines,
        tail_lines=settings.stderr_tail_lines,
        max_chars=settings.feedback_max_chars,
    )

    start_time = time.time()
    try:
        with dspy.context(lm=lm):
            predictor = dspy.ChainOfThought(EscalationSignature)
            result = await asyncio.to_thread(
                predictor,
                task_id=subtask.get("id", "unknown"),
                task_description=subtask.get("description") or subtask.get("content") or "Description non disponible.",
                failure_history=failure_history or "Aucun historique de réfutation enregistré.",
                current_code=current_code,
            )

        metrics = NodeMetrics(
            node="escalation_dspy",
            model=settings.reasoning_model_id,
            duration_s=time.time() - start_time,
            input_tokens=0,
            output_tokens=0
        )
        return result.output, metrics
    except Exception as e:
        print(f"[-] Erreur critique DSPy (Escalation) : {e}")
        return None, None
