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
from .llama_server import model_lifecycle
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

        MOTS-CLÉS CANONIQUES (signaux forts — un seul suffit la plupart du temps) :
        - python/.py/pandas/numpy/pytest/flask/django/fastapi → 'python'
        - react/vue/svelte/next.js/.tsx/typescript/: type/interface → 'typescript'
        - .html/.htm/landing page/page web/HTML5/CSS3 (sans JS métier) → 'html'
        - vanilla js/javascript/DOM/navigateur/canvas/<script>/addEventListener → 'javascript'
        - rust/cargo/tokio/actix → 'rust' ; go/golang/gin/echo → 'go'
        - node.js/express/npm (backend) → 'javascript'

        RÈGLE DE PRIORITÉ : si la requête mentionne des EXTENSIONS de fichiers (.py/.ts/.html...),
        elles PRIMENT sur les mots-clés (l'extension est la source de vérité — comme la
        détection redondante F-27 côté Tester).

        ANTI-BIAIS (failure modes récurrents observés) :
        - NE déborde PAS vers 'javascript' par défaut — si python/.py apparaît ne serait-ce
          qu'une fois, c'est 'python', pas du web.
        - HTML/CSS pur SANS JS métier = 'html' (pas 'javascript') — le Linter traite les deux
          différemment (tree-sitter-html vs tree-sitter-javascript).
        - React/Next.js = 'typescript' (pas 'javascript') — sinon le Linter ne vérifie pas les
          annotations de type, perte d'un garde-fou.
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

        RÈGLES POUR 'incremental' (sections) :
        - La 1ère section DOIT être le squelette structural complet (ex: `<!DOCTYPE html>…
          </body></html>` pour HTML) — c'est le socle sur lequel les autres sections
          s'appendent via append_file. Sans ça, le Coder risque d'inventer du contenu après
          </html> (le bug dashboard observé en prod).
        - Vise 3-7 sections par fichier incremental, chacune ~50-100 lignes (gérable pour un
          petit Coder local). Ne fais pas de sections trop fines (surchauffe le nombre de
          steps) ni trop grosses (risque de troncature).

        ATTENTION — BIAIS 'incremental' vs 'multifile' (failure mode observé) :
        'incremental' = UN gros fichier monolithique construit par morceaux (ex: dashboard
        dans un seul index.html). 'multifile' = PLUSIEURS fichiers séparés (ex: app.py +
        utils.py). Ne mets JAMAIS 'incremental' sur un projet multifichier Python/TS —
        sinon le Coder écrirait un seul gros .py au lieu de le modulariser. 'incremental'
        est exclusif aux fichiers MONOLITHIQUES IMPOSÉS par la spec.

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

        PATTERNS DANGEREUX À CHERCHER ACTIVEMENT (par catégorie — ne te contente pas d'être
        « exhaustif » en abstrait, scanne ces patterns concrets dans le code) :
        - A03 XSS (DOM) : ``innerHTML``, ``outerHTML``, ``document.write``, ``insertAdjacentHTML``
          avec une donnée utilisateur.
        - A03 Injection commande : ``os.system``, ``subprocess.run(shell=True)``, ``eval()``,
          ``exec()`` sur une entrée externe → RCE (critical).
        - A03 Injection SQL : concaténation de string (``"... " + var``) ou f-string dans une
          requête SQL → critical si input externe.
        - A02 Crypto / secrets : ``hashlib.md5``/``sha1``, ``password = "..."``, ``api_key = "..."``
          en dur, ``random`` (pas ``secrets``) pour des tokens.
        - A08 Désérialisation : ``pickle.loads``, ``yaml.load`` (sans Loader safe).
        - A05 Misconfig : ``verify=False`` (TLS), ``CORS "*"``/``ALLOWED_HOSTS=['*']``,
          ``debug=True`` (Flask/Django prod).
        - A09 Logging : logs de données sensibles (mot de passe, token) → low/medium.

        DISCRIMINATION INPUT (élimine les faux positifs) : avant de flagger un pattern, confirme
        la SOURCE de la donnée. ``innerHTML = "<b>" + name`` où ``name`` vient de
        ``URLSearchParams``/utilisateur/base = vuln (high). ``innerHTML = "<b>Page</b>"``
        (constante littérale) = PAS une vuln (input contrôlé). La sévérité dépend de la source,
        pas seulement du pattern.

        ATTENTION FAUX POSITIFS : un pattern dangereux sur une CONSTANTE n'est pas une vuln.
        Le JS côté navigateur est par nature exposé — un ``eval`` sur une constante locale n'est
        pas une RCE serveur. Ajuste la sévérité au contexte (client vs serveur).

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

        PROCÉDURE OBLIGATOIRE (procède dans cet ordre, ne juge pas avant d'avoir vérifié) :
        1. LISTS chaque exigence de ``task_requirements`` (cahier des charges).
        2. Pour CHAQUE exigence, vérifie dans ``code`` : (a) Présente ? (b) Implémentée (pas
           juste déclarée) ? Atteste explicitement Présente/Implémentée pour chacune AVANT de
           conclure — une exigence absente du code = finding critical/high.
        3. CROISE avec ``test_results`` : ne fais PAS confiance aveugle au test. Si
           ``test_results`` dit PASS mais qu'une exigence n'est pas implémentée dans ``code``
           → finding critical, ``is_approved=False``. Le test peut rater des choses ou faire
           des faux PASS ; ton œil sur le code est l'arbitre final.
        4. APPLIQUE ``security_vulnerabilities`` : toute vuln critical/high = ``is_approved=False``.
        5. DÉCIDE : ``is_approved`` ssi 0 critical/high.

        LOCALISATION OBLIGATOIRE : chaque finding DOIT citer la ligne ou le fragment exact du
        code soumis (ancre in-diff) — pas de remarque générique. Permet au Coder d'agir
        directement sur le feedback.

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

def _configure_dspy(settings: Settings, model_id: str, think: bool = False,
                    api_base: Optional[str] = None, api_key: Optional[str] = None):
    """Configure dynamiquement DSPy pour pointer vers une instance llama-server (F-58).

    Provider litellm ``openai/`` contre l'endpoint OpenAI-compatible ``/v1`` de llama-server
    (ou n'importe quel endpoint OpenAI-compat : Ollama, OpenAI, OpenRouter — backend-agnostique).

    Thinking piloté CÔTÉ SERVEUR : le flag ``--reasoning on/off`` est passé au spawn de
    llama-server par ``model_lifecycle`` (config ModelSpec). Le paramètre ``think`` est INERT
    (conservé pour ne pas casser les appelants). Le thinking va dans ``reasoning_content``
    (séparé), DSPy lit ``content`` (réponse finale propre) — comportement voulu, validé F-58.

    Args :
        api_base/api_key/model_id : overrides depuis le serveur spawné (model_lifecycle.srv).
            Si fournis, on les utilise (port dynamique du process spawné). Sinon, fallback
            sur les settings (rétro-compatibilité tests mockés / endpoint externe fixe).
    """
    if api_base is None:
        api_base = settings.ollama_reasoning_api_base if model_id == settings.reasoning_model_id else settings.ollama_api_base
    if api_key is None:
        api_key = settings.ollama_api_key
    lm = dspy.LM(
        f"openai/{model_id}",
        api_base=api_base,
        api_key=api_key,
        max_tokens=8192,
        temperature=0.3,
        timeout=settings.llm_timeout_s,
    )
    return lm


# ==========================================
# Exécuteurs de Nœuds (Wrappers Asynchrones)
# ==========================================

def _no_think_model_id(settings: Settings) -> str:
    """Résout le model_id pour les nœuds think=False (Judge/Security/Escalation).

    F-58 : avec llama-server, le thinking se pilote côté serveur via models.ini
    (reasoning=on/off), donc les nœuds think=False doivent pointer sur la section
    `reasoning = off` (ex: "gemma-4-12b-nothink"). Si reasoning_no_think_model_id est
    vide (défaut, rétro-compatibilité Ollama/tests), on retombe sur reasoning_model_id.
    """
    return settings.reasoning_no_think_model_id or settings.reasoning_model_id


async def _run_dspy_node(signature, predictor_kwargs: dict, settings: Settings, spec, think: bool = False, model_override: Optional[str] = None) -> Any:
    """Helper pour exécuter un nœud DSPy avec le cycle de vie du modèle."""
    with model_lifecycle(spec) as srv:
        _mid = model_override or srv.model_id or spec.model
        _base = srv.api_base
        _key = srv.api_key
        lm = _configure_dspy(settings, _mid, think=think, api_base=_base, api_key=_key)
        with dspy.context(lm=lm):
            predictor = dspy.ChainOfThought(signature)
            return await asyncio.to_thread(predictor, **predictor_kwargs)


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
    start_time = time.time()
    try:
        result = await _run_dspy_node(
            signature=RouterSignature,
            predictor_kwargs={"task_content": task_content},
            settings=settings,
            spec=settings.fast_spec,
            think=False,
        )
        
        metrics = NodeMetrics(
            node="router_dspy", 
            model=settings.fast_spec.model, 
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
    capabilities = _build_capabilities_summary(settings)
    start_time = time.time()
    try:
        result = await _run_dspy_node(
            signature=PromptRefinerSignature,
            predictor_kwargs={
                "raw_prompt": raw_prompt,
                "available_capabilities": capabilities,
            },
            settings=settings,
            spec=settings.reasoning_spec,
            think=True,
            model_override=settings.prompt_refiner_model_id,
        )
        refined = result.output
        n_amb = len(refined.ambiguities_detected) if refined.ambiguities_detected else 0
        print(f"[+] PromptRefiner : spec produite ({len(refined.refined_prompt)} caractères"
              f"{f', {n_amb} ambiguïté(s) détectée(s)' if n_amb else ''}).")

        metrics = NodeMetrics(
            node="prompt_refiner_dspy",
            model=settings.prompt_refiner_model_id or settings.reasoning_spec.model,
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
        result = await _run_dspy_node(
            signature=ArchitectSignature,
            predictor_kwargs={"task_content": architect_input},
            settings=settings,
            spec=settings.reasoning_spec,
            think=True,
        )

        metrics = NodeMetrics(
            node="architect_dspy",
            model=settings.reasoning_spec.model,
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
    code_content = ""
    for file_path in subtask.get("target_files", []):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code_content += f"--- {file_path} ---\n{f.read()}\n\n"
        except Exception:
            pass

    start_time = time.time()
    try:
        result = await _run_dspy_node(
            signature=SecuritySignature,
            predictor_kwargs={
                "task_id": subtask.get("id", "unknown"),
                "code": code_content or "Code manquant"
            },
            settings=settings,
            spec=settings.reasoning_spec,
            think=True,
        )
        
        metrics = NodeMetrics(
            node="security_dspy",
            model=settings.reasoning_spec.model,
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
    code_content = ""
    for file_path in subtask.get("target_files", []):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code_content += f"--- {file_path} ---\n{f.read()}\n\n"
        except Exception:
            pass

    vulns = security_res.vulnerabilities if security_res and security_res.vulnerabilities else ["Aucune vulnérabilité critique détectée."]
    
    tests = "Résultats non disponibles"
    if test_res:
        if isinstance(test_res, dict):
            tests = str(test_res.get("details", test_res))
        else:
            tests = getattr(test_res, "details", str(test_res))
    tests = truncate_output(tests, head_lines=settings.stderr_head_lines, tail_lines=settings.stderr_tail_lines, max_chars=settings.feedback_max_chars)

    start_time = time.time()
    try:
        task_requirements = truncate_output(
            subtask.get("original_content", "") or "Cahier des charges non disponible.",
            head_lines=30,
            tail_lines=10,
            max_chars=1500,
        )
        result = await _run_dspy_node(
            signature=CodeJudgeSignature,
            predictor_kwargs={
                "task_id": subtask.get("id", "unknown"),
                "code": code_content or "Code manquant",
                "security_vulnerabilities": vulns,
                "test_results": tests,
                "task_requirements": task_requirements,
            },
            settings=settings,
            spec=settings.reasoning_spec,
            think=True,
        )
        
        metrics = NodeMetrics(
            node="code_judge_dspy",
            model=settings.reasoning_spec.model,
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
        result = await _run_dspy_node(
            signature=EscalationSignature,
            predictor_kwargs={
                "task_id": subtask.get("id", "unknown"),
                "task_description": subtask.get("description") or subtask.get("content") or "Description non disponible.",
                "failure_history": failure_history or "Aucun historique de réfutation enregistré.",
                "current_code": current_code,
            },
            settings=settings,
            spec=settings.reasoning_spec,
            think=True,
        )

        metrics = NodeMetrics(
            node="escalation_dspy",
            model=settings.reasoning_spec.model,
            duration_s=time.time() - start_time,
            input_tokens=0,
            output_tokens=0
        )
        return result.output, metrics
    except Exception as e:
        print(f"[-] Erreur critique DSPy (Escalation) : {e}")
        return None, None
