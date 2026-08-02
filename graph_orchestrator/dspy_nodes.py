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
from .prompts import with_invariants


# ==========================================
# Signatures DSPy (Contrats Déclaratifs)
# ==========================================

class RouterSignature(dspy.Signature):
    __doc__ = with_invariants(
        "router",
        """Analyse la requête de l'utilisateur pour déterminer la technologie principale requise.

        Cette signature agit comme le premier filtre de l'orchestrateur. Elle détermine :
        - Quel langage de programmation principal est concerné (ex: 'python', 'javascript').
        """,
    )
    task_content: str = dspy.InputField(desc="La requête initiale ou directive de l'utilisateur fournie au graphe")
    output: RouterOutput = dspy.OutputField(desc="Décision de routage structurée, typée strictement par le schéma Pydantic RouterOutput")


class PromptRefinerSignature(dspy.Signature):
    __doc__ = with_invariants(
        "prompt_refiner",
        """Pipeline obligatoire :
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
        - Si une exigence est absente du prompt brut, ne la fabrique pas — contente-toi de la
          signaler comme manquante dans une section 'À clarifier'.
        - CONCISION : ~30 lignes max. Une spec est un brief, pas un roman.
        - PRÉSERVE toute exigence EXPLICITE du prompt brut (stack imposée, format, nb d'éléments...).
        - Si le prompt brut est DÉJÀ clair et structuré, renvoie une spec quasi identique (ne dégrade
          pas une bonne entrée).
        """,
    )
    raw_prompt: str = dspy.InputField(desc="Le prompt utilisateur brut, souvent vague ou incomplet")
    available_capabilities: str = dspy.InputField(desc="Catalogue des capacités disponibles (skills, statut Context7, testers) pour orienter la spec vers ce qui est faisable")
    output: PromptRefinerOutput = dspy.OutputField(desc="Spec structurée (refined_prompt) + termes vagues détectés (ambiguities_detected)")


class ArchitectSignature(dspy.Signature):
    __doc__ = with_invariants(
        "architect",
        """Analyse une tâche et génère un plan d'architecture en sous-tâches UNITAIRES.

        RÈGLE DE DÉCOUPAGE (1 LIVRABLE TESTABLE = 1 SOUS-TÂCHE) :
        - Une sous-tâche = un ENSEMBLE COHÉRENT de fichiers que le Tester va valider ENSEMBLE.
          Ne JAMAIS découper un livrable en sous-tâches par fichier — sinon le Tester teste des
          fichiers isolés qui ne marchent pas seuls (ex: index.html sans styles.css → REJETÉ
          systématique, boucle infinie). C'est le failure mode n°1 observé en prod.
        - CAS TYPIQUES :
          * 1 fichier unique (Bubble Sort dans index.html) → 1 sous-tâche, target_files=[ce fichier].
          * Site HTML+CSS+JS liés (landing_page/) → 1 sous-tâche, target_files=[index.html,
            styles.css, script.js] (le Coder crée les 3, le Tester valide l'ensemble rendu).
          * App Python 3 modules indépendants (models.py/api.py/utils.py) → 1 sous-tâche
            multifile si les modules se testent ensemble, OU plusieurs sous-tâches UNIQUEMENT
            si chaque module est réellement testable isolément (rare).
        - Vise le MINIMUM de sous-tâches. Chaque sous-tâche déclenche un agent Coder + Tester +
          Judge complets (coûteux). Le découpage granulaire est contre-productif.

        RÈGLE DE STRATÉGIE (F-29 — très important, dicte COMMENT le Coder doit construire) :
        Pour CHAQUE sous-tâche, choisis une 'strategy' parmi :
        - 'simple' : UN seul write_file par fichier (contenu COMPLET). C'est la stratégie PAR
          DÉFAUT. Pour une sous-tâche multifile, le Coder enchaîne plusieurs write_file (un par
          fichier cible) dans le même run. Convient pour tout fichier < ~500 lignes.
        - 'incremental' : RÉSERVÉ aux GROS fichiers monolithiques (> ~500 lignes, ex: un
          dashboard admin complet dans un seul index.html imposé par la spec). Le Coder
          construira le squelette PUIS remplira section par section via append_file. Dans ce
          cas, fournis 'sections' = liste des sections (ex: ['css', 'sidebar', 'kpi', 'js']).
          N'utilise JAMAIS incremental sur un fichier < ~500 lignes — ça crée des bugs de
          structure (contenu après </html>) pour aucun bénéfice.
        - 'multifile' : quand une sous-tâche porte PLUSIEURS fichiers liés (index.html +
          styles.css + script.js). Le Coder crée chaque fichier via write_file autonome.
          Même logique que 'simple' (contenu complet par fichier), juste pour signaler
          qu'il y a plusieurs fichiers dans la sous-tâche.

        QUAND UTILISER QUOI :
        - HTML/CSS/JS dans 1 seul fichier → 'simple'.
        - HTML/CSS/JS en fichiers séparés liés → 'multifile' (1 sous-tâche, tous les fichiers).
        - Python/TS 1 module → 'simple'. Plusieurs modules liés → 'multifile'.
        - Gros monolithe (> 500 lignes) imposé → 'incremental' (dernier recours).

        Le Coder suivra ta stratégie à la lettre. Chaque sous-tâche doit avoir des critères
        d'acceptation vérifiables (comportements attendus testables, pas juste un nom de fichier).
        """,
    )
    task_content: str = dspy.InputField(desc="Le cahier des charges global de la fonctionnalité ou du projet à développer")
    output: ArchitectOutput = dspy.OutputField(desc="Plan : liste de sous-tâches (2-4 max). Chaque ArchitectTask a target_files + strategy ('simple'|'incremental'|'multifile') + sections (si incremental).")


class SecuritySignature(dspy.Signature):
    __doc__ = with_invariants(
        "security",
        """Audite le code source fourni pour détecter des vulnérabilités de sécurité.

        TAXONOMIE OWASP Top 10 : couvre XSS, injection (SQL/commande), broken auth, data
        exposure, security misconfig, etc. Sois exhaustif mais PRIORISE par sévérité.

        RUBRIC DE SÉVÉRITÉ (rubrique ``findings``, échelle CVSS) :
        - 'critical' : exploitable sans interaction, fuite de données / RCE / crash.
        - 'high'     : faille fonctionnelle sérieuse (auth bypass, injection nécessitant un vecteur).
        - 'medium'   : robustesse sécurité (validation manquante, info leak mineure).
        - 'low'      : durcissement (en-tête manquant, pratique sous-optimale).

        Chaque finding doit porter un ``location`` (fichier + ligne/fragment) et une ``suggestion``
        de correction actionnable. Remplis aussi ``vulnerabilities`` (liste plate de strings,
        pour compatibilité avec le Judge qui la consomme). ``is_secure=True`` si et seulement
        si AUCUNE vulnérabilité critical/high.
        """,
    )
    task_id: str = dspy.InputField(desc="L'identifiant unique de la tâche pour la traçabilité")
    code: str = dspy.InputField(desc="Le bloc de code source brut généré par le Coder à inspecter")
    output: SecurityOutput = dspy.OutputField(desc="Verdict de sécurité : is_secure bool + vulnerabilities (liste plate) + findings (rubric structurée sévérité/location/suggestion)")


class CodeJudgeSignature(dspy.Signature):
    __doc__ = with_invariants(
        "judge",
        """Évalue l'implémentation globale d'un CodeAgent en fusionnant toutes les métriques
        et rapports. Tu es le dernier rempart avant la validation de la sous-tâche.

        RUBRIC DE SÉVÉRITÉ (rubrique ``findings``, échelle identique au Security Reviewer) :
        - 'critical' : crash, perte de données, faille de sécurité exploitable, non-respect
          d'une exigence FONCTIONNELLE clé du cahier des charges.
        - 'high'     : bug fonctionnel sérieux, test échouant, faille de sécurité confirmée.
        - 'medium'   : robustesse (edge case non géré, gestion d'erreur manquante).
        - 'low'      : nit / style / lisibilité (NE FAIS PAS REJETER POUR ÇA — signale juste).

        RÈGLES D'ÉVALUATION :
        - IN-DIFF ONLY : juge le code soumis (``code``), pas un fichier hypothétique plus large.
        - ANTI-NITS : ne REJETTE JAMAIS pour des critiques de style/nommage pur. Un 'low' seul
          ne justifie pas un rejet.
        - VÉRIFICATION COMPORTEMENTALE : utilise ``task_requirements`` et ``test_results`` pour
          confirmer que les comportements clés sont implémentés ET testés (pas juste l'absence
          de crash). Un test qui passe sans couvrir le comportement attendu = échec de couverture.
        - ``is_approved=True`` si et seulement si AUCUN finding critical/high.

        Remplis ``findings`` (structuré) ET ``final_feedback`` (résumé actionnable pour le Coder
        à la prochaine itération, si rejet).
        """,
    )
    task_id: str = dspy.InputField(desc="Identifiant de la tâche examinée")
    code: str = dspy.InputField(desc="Le code source final soumis par le CodeAgent")
    security_vulnerabilities: List[str] = dspy.InputField(desc="Liste des problèmes de sécurité soulevés par le Security Reviewer")
    test_results: str = dspy.InputField(desc="Sortie brute des tests fonctionnels exécutés par l'agent QA")
    task_requirements: str = dspy.InputField(desc="Le cahier des charges complet (comportements attendus). Sert à vérifier que le test_results couvre bien les comportements clés et que le code les implémente — pas seulement qu'il ne crash pas.")
    output: CodeJudgeOutput = dspy.OutputField(desc="Verdict final (is_approved) + findings (rubric sévérité) + final_feedback (résumé actionnable si rejet)")


class EscalationSignature(dspy.Signature):
    __doc__ = with_invariants(
        "escalation",
        """Post-mortem d'une sous-tâche qui a épuisé le Circuit Breaker (3 itérations
        Coder↔Tester↔Judge toutes rejetées).

        Tu reçois l'historique COMPLET des réfutations émises par le Juge (les bugs récurrents
        qui n'ont pas pu être résolus) et l'état actuel du code sur disque.

        Ton diagnostic doit permettre à un run futur (ou à un humain) de ne pas répéter les
        mêmes erreurs. Identifie la cause racine profonde (pas le symptôme de surface), liste
        objectivement ce qui a été tenté (anti-répétition), et formule une leçon concrète.
        """,
    )
    task_id: str = dspy.InputField(desc="Identifiant de la sous-tâche en échec")
    task_description: str = dspy.InputField(desc="Le cahier des charges / description de la sous-tâche")
    failure_history: str = dspy.InputField(desc="Historique concaténé des réfutations du Juge (bugs non résolus sur les 3 itérations). C'est la matière première du diagnostic.")
    current_code: str = dspy.InputField(desc="L'état actuel du code sur disque après le dernier échec")
    output: EscalationOutput = dspy.OutputField(desc="Diagnostic post-mortem structuré : cause racine, tentatives, leçon, gravité")


# ==========================================
# Configuration DSPy
# ==========================================

def _configure_dspy(settings: Settings, model_id: str, think: bool = False):
    """Configure dynamiquement DSPy pour pointer vers une instance locale Ollama.

    Timeout appliqué : sans lui, un endpoint Ollama distant muet fige le nœud DSPy
    (bug observé sur le serveur distant 10.201.12.50 qui répond au /api/tags mais
    timeout sur l'inférence). Le timeout permet à l'appel d'échouer proprement.

    Provider ``ollama/`` (F-47, fix Gap 2) : on utilise le provider litellm ``ollama/``
    au lieu de ``openai/``. Pourquoi :
    - ``openai/`` parle l'endpoint OpenAI-compat ``/v1`` d'Ollama. Or sur Ollama 0.32.5
      (dernière version), le thinking Gemma 4 est **FORCÉ** sur ``/v1`` et AUCUN paramètre
      (think, chat_template_kwargs, Modelfile) ne le désactive côté /v1.
    - ``ollama/`` parle l'API native ``/api/chat`` d'Ollama, qui accepte le paramètre
      ``think`` (booléen top-level). Testé : ``think=False`` → 3.8s + 6 tokens + réponse
      directe (vs 23 min de thinking qui consomme tout max_tokens sans jamais émettre le
      verdict → hang du Judge).
    Le thinking est donc désactivé par défaut (``think=False``) pour les nœuds de verdict
    (Judge/Router/PromptRefiner/Security/Escalation) où il est du gaspi bloquant. Seul
    l'Architect le conserve (le raisonnement aide au découpage/stratégie) — voir appelant.

    ``think`` (F-47) : True = raisonnement étape-par-ante (Architect), False = réponse
    directe (tous les autres nœuds DSPy). Le thinking consomme le budget max_tokens ; sans
    borne stricte il peut faire hang le nœud (cf. debug/GAPS_TESTER_JUDGE.md Gap 2).

    Note : l'api_base Ollama ne doit PAS contenir le suffixe ``/v1`` pour le provider
    ``ollama/`` (litellm parle à la racine ``/api/chat``). On le retire si présent.
    """
    api_base = settings.ollama_reasoning_api_base if model_id == settings.reasoning_model_id else settings.ollama_api_base
    # Le provider ollama/ parle /api/chat à la racine — pas de /v1 (sinon 404).
    if api_base.endswith("/v1"):
        api_base = api_base[:-3]
    lm = dspy.LM(
        f"ollama/{model_id}",
        api_base=api_base,
        api_key="ollama",  # requis par litellm même si Ollama ne vérifie pas la clé
        max_tokens=8192,
        temperature=0.3,
        timeout=settings.llm_timeout_s,
        think=think,
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
    lm = _configure_dspy(settings, settings.fast_model_id, think=False)
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
    # Modèle dédié si setté (E4B recommandé : ~8× plus rapide que le 12B pour qualité
    # équivalente — voir log.md test comparatif). Fallback sur reasoning_model_id sinon.
    refiner_model_id = settings.prompt_refiner_model_id or settings.reasoning_model_id
    lm = _configure_dspy(settings, refiner_model_id, think=False)
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
            model=refiner_model_id,
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
    # F-47 : l'Architect est le SEUL nœud DSPy qui conserve le thinking (think=True). Le
    # raisonnement étape-par-étape aide au découpage/stratégie (simple/incremental/multifile,
    # sections, target_files). Tous les autres nœuds (Judge/Router/etc.) l'ont désactivé
    # car c'était du gaspi bloquant (thinking forcé sur /v1 → hang, cf. _configure_dspy).
    lm = _configure_dspy(settings, settings.reasoning_model_id, think=True)
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
    lm = _configure_dspy(settings, settings.reasoning_model_id, think=False)
    
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
    lm = _configure_dspy(settings, settings.reasoning_model_id, think=False)
    
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
    lm = _configure_dspy(settings, settings.reasoning_model_id, think=False)

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
