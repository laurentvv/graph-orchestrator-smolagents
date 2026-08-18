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
from .judge_diff import build_judge_code_block
from .llama_server import model_lifecycle
from .logging_utils import NodeMetrics
from .models import (
    ArchitectOutput,
    CodeJudgeOutput,
    ConsolidationOutput,
    EscalationOutput,
    Finding,
    PromptRefinerOutput,
    RouterOutput,
    SecurityOutput,
    DrafterOutput,
)
from .prompts import with_invariants
from .knowledge_graph import apply_consolidation_actions


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
        """Mandatory pipeline:
        1. CLARITY & DISAMBIGUATION: detect VAGUE terms in the raw prompt (e.g. 'fast',
           'user-friendly', 'flexible', 'modern', 'optimized', 'nice-looking', and their
           French equivalents such as 'rapide', 'beau') and list them in
           `ambiguities_detected`. Rewrite them as measurable requirements (e.g. 'fast' →
           'response time < 200ms' IF quantifiable, otherwise drop/soften).
        2. CONTEXT: use `available_capabilities` to STEER the spec toward what is feasible
           (web-tester → browser-testable criteria; python-tester → pytest criteria;
           context7 → note 'consult the library docs'). Only CITE them, do not consume
           these capabilities yourself.
        3. FORMATTING: structure the spec into these EXACT fixed sections:
             ## Objective (1-3 sentences: the expected visible outcome)
             ## Expected Features (bullet points, each testable)
             ## Technical Constraints (stack, imposed format, max size if specified)
             ## Acceptance Criteria (Given/When/Then when relevant, otherwise concrete bullets)
        4. LIGHT COMPLETION: add ONLY obvious basic gaps (typical edge cases: empty field,
           invalid data, boundary values). NEVER add a feature the user did not ask for
           (anti scope-hallucination).

        CRITICAL RULES:
        - LANGUAGE: always write the refined spec in ENGLISH, whatever the input language
          (pattern Kilo Code / Cline 'Enhance Prompt' — downstream small models are
          significantly stronger on structured English).
        - If a requirement is missing from the raw prompt, do not invent it — just flag it
          as missing in a 'To clarify' section.
        - CONCISENESS: ~30 lines max. A spec is a brief, not a novel.
        - PRESERVE every EXPLICIT requirement of the raw prompt (imposed stack, format,
          element counts...).
        - If the raw prompt is ALREADY clear and structured, return a near-identical spec
          (do not degrade a good input).
        """,
    )
    raw_prompt: str = dspy.InputField(desc="The raw user prompt, often vague or incomplete (any language)")
    available_capabilities: str = dspy.InputField(desc="Catalogue of available capabilities (skills, Context7 status, testers) to steer the spec toward what is feasible")
    output: PromptRefinerOutput = dspy.OutputField(desc="Structured spec in ENGLISH (refined_prompt) + detected vague terms (ambiguities_detected)")


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
          fichier cible) dans le même run. Convient pour TOUT fichier < ~500 lignes. Un
          visualiseur d'algorithme (Bubble Sort, ToDo, palette de couleurs...) = 'simple'.
        - 'incremental' : RÉSERVÉ aux GROS fichiers monolithiques (> ~500 lignes, ex: un
          dashboard admin complet dans un seul index.html imposé par la spec). Le Coder
          construira le squelette PUIS remplira section par section via append_file. Dans ce
          cas, fournis 'sections' = liste des sections (ex: ['css', 'sidebar', 'kpi', 'js']).
          ⚠️ N'utilise JAMAIS incremental sur un fichier < ~500 lignes — un visualiseur
          interactif (~200-300 lignes) DOIT être 'simple'. Incremental sur un petit fichier
          laisse les marqueurs INSERT_* non remplacés (bug observé en prod) et casse la page.
        - 'multifile' : quand une sous-tâche porte PLUSIEURS fichiers liés (index.html +
          styles.css + script.js). Le Coder crée chaque fichier via write_file autonome.
          Même logique que 'simple' (contenu complet par fichier), juste pour signaler
          qu'il y a plusieurs fichiers dans la sous-tâche.

        QUAND UTILISER QUOI (règle stricte) :
        - 1 seul fichier < 500 lignes (Bubble Sort, ToDo, visualizer, palette...) → 'simple'.
        - Plusieurs fichiers liés (site HTML+CSS+JS) → 'multifile' (1 sous-tâche, tous fichiers).
        - 1 SEUL fichier > 500 lignes (dashboard monolithe imposé par la spec) → 'incremental'.
        Si tu hésites entre 'simple' et 'incremental', c'est 'simple'. Le doute profite à 'simple'.

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
        est exclusif aux fichiers MONOLITHIQUES IMPOSÉS par la spec (> ~500 lignes).

        RÈGLE DE SÉLECTION DES SKILLS (F-57, Priorité 10) :
        Pour CHAQUE sous-tâche, remplis 'skills' avec les skills pertinents parmi ce catalogue.
        Un budget de tokens (défaut ~8000) plafonne automatiquement la sélection côté Coder
        (rogne les plus gros si dépassement) — donc sélectionne généreusement ce qui est utile,
        le système garde les plus pertinents sous le budget :
        - 'frontend-design' : OBLIGATOIRE pour toute tâche web (HTML/CSS/JS, landing page,
          dashboard, visualizer). Design pro concret : palettes, typo, layout APP vs LANDING.
        - 'devtools-preview' : pour les tâches web avec interface interactive (boutons,
          animations) — le Coder auto-validera sa page via Chrome DevTools (screenshot+console).
        - 'web-animation' : OBLIGATOIRE pour tout visualiseur d'algorithme (tri, pathfinding,
          simulation) ou toute animation JS. Documente le pattern async/await avec sleep()
          (JAMAIS setTimeout dans une boucle = animation instantanée invisible) + sync DOM
          après swap + init au chargement. Sans ce skill, le Coder produit des animations cassées.
        - 'python-testing-patterns' : pour les projets Python où le Coder doit produire des
          tests pytest (fixtures, mocking, TDD). Donne la doctrine du code testable.
        - 'code-review' : pour les sous-tâches complexes où le Coder doit s'auto-réviser
          (revue structurée Standards + Spec, rubric critical/major/minor).
        - 'systematic-debugging' : pour les itérations de correction (itération 2+) où le
          Coder doit diagnostiquer un bug de façon structurée (hypothèses falsifiables, bisection).
        Ne mets JAMAIS un skill non listé ci-dessus. Si la tâche est du vanilla simple sans
        enjeu design (ex: script CLI pur), 'skills' peut rester vide (le socle file-creation +
        coding + context7-research est toujours injecté automatiquement par défaut).

        RÈGLE DE CRITÈRES DE VALIDATION (F-90 — l'Architecte est le PILOTE des validations) :
        Tu produis les ordres de validation que les autres nœuds (Coder, Tester, Judge) vont
        exécuter. Ils doivent être SPÉCIFIQUES au cahier des charges, pas génériques. Sans
        critères explicites, le Coder valide à l'aveugle (biais observé en prod : canvas vide
        excusé comme "normal avant interaction" alors que generateArray() est appelé à l'init).

        Pour CHAQUE sous-tâche, remplis 3 champs :

        1. 'visual_success_criteria' (LISTE d'assertions visuelles concrètes, pour le Coder) :
           Ce que le Coder DOIT voir sur son screenshot avant de valider. Sois précis et
           anti-biais — un visuel VIDE est un BUG, pas "normal avant interaction" :
           - ✅ "Au chargement de la page, ≥1 barre colorée VISIBLE dans le canvas (un canvas
             vide au chargement = BUG critique, pas 'normal')"
           - ✅ "Le compteur affiche '0' au chargement"
           - ✅ "Les boutons Démarrer/Réinitialiser sont visibles et cliquables"
           - ❌ VAGUE : "le rendu est correct" (le modèle excusera un canvas vide)
           - ❌ ABSENT : si tu ne mets rien, le Coder validera à l'aveugle.
           Ne mets RIEN ici si la tâche n'est PAS visuelle (script CLI, API backend pur).

        2. 'functional_test_criteria' (LISTE d'assertions de comportement, pour le Tester) :
           Ce que le Tester DOIT vérifier via evaluate_script (pas seulement absence de crash) :
           - ✅ "Après clic sur Démarrer puis await sleep(400ms), le compteur > 0"
           - ✅ "Après fin du tri, le tableau est trié par ordre croissant (vérifier heights)"
           - ✅ "Déplacer le slider de vitesse change la valeur affichée à l'écran"
           Ces critères REMPLACENT la checklist générique quand non vide — plus précis car
           produits par ta compréhension du cahier des charges.

        3. 'acceptance_rubric' (TEXTE court, pour le Judge) :
           Les critères d'acceptation PONDÉRÉS spécifiques à cette sous-tâche :
           - ✅ "CRITICAL: barres visibles au chargement + tri correct. HIGH: code couleur
                3 états distincts. MEDIUM: responsive mobile. LOW: animations fluides."
           Ce champ est concaténé au cahier des charges global du Judge. Laisse vide si la
           spec suffit (tâche triviale).

        Le Coder suivra ta stratégie à la lettre. Chaque sous-tâche DOIT inclure dans sa
        `description` la liste explicite des tests et critères d'acceptation (comportements
        attendus testables). N'oublie pas de copier-coller les tests depuis le prompt d'origine.

        RÈGLE DE PRÉSERVATION DES DONNÉES (CRITIQUE) :
        Ne résume JAMAIS le cahier des charges de manière abstraite. Tu dois IMPÉRATIVEMENT copier-coller dans la `description` de la sous-tâche toutes les valeurs techniques explicites du prompt d'origine :
        - Les valeurs chiffrées (ex: 30 éléments, 15ms).
        - Les codes couleurs (ex: #4fc3f7).
        - Les contraintes technologiques strictes.
        Si tu les résumes, le Coder n'y aura pas accès et la tâche échouera.
        """,
    )
    task_content: str = dspy.InputField(desc="Le cahier des charges global de la fonctionnalité ou du projet à développer")
    output: ArchitectOutput = dspy.OutputField(desc="Plan : liste de sous-tâches (2-4 max). Chaque ArchitectTask a target_files + strategy + sections (si incremental). Définis aussi 'skills' (pour le Coder, ex: ['tdd']), 'tester_skills' (pour le Tester, ex: ['webapp-testing']), 'judge_skills' (ex: ['code-review']), et les critères de validation F-82 : 'visual_success_criteria' (assertions visuelles pour le Coder, ex: ['barres visibles au chargement']), 'functional_test_criteria' (assertions comportementales pour le Tester), 'acceptance_rubric' (critères pondérés pour le Judge).")


class DrafterSignature(dspy.Signature):
    __doc__ = with_invariants(
        "drafter",
        """Agit comme l'Architecte Logiciel : conçoit un PLAN D'IMPLÉMENTATION précis
        (intention + structure + logique), PAS du code brut. Le Coder implémentera ce plan.

        RÔLE : Tu produis un plan d'implémentation que le Coder suivra. Ce plan décrit
        COMMENT construire la solution (structure, logique, edge cases), pas le code exact.
        Le Coder code from-scratch en suivant ton plan → pas de copier-coller → pas de doublon.

        RÈGLES CRITIQUES :
        1. Produis un PLAN D'IMPLÉMENTATION en Markdown, structuré par fichier cible.
        2. Pour chaque fichier, décris : sa structure (IDs/classes DOM), sa logique
           (fonctions, algorithmes), et les edge cases à gérer.
        3. Sois PRÉCIS sur la logique algorithmique : étapes exactes, variables clés,
           conditions, boucles. Le Coder doit pouvoir implémenter sans ambiguïté.
        4. Pour les visualiseurs/animations : précise le mécanisme de timing (await sleep,
           requestAnimationFrame avec 1 itération/frame), la sync DOM après chaque opération
           (mettre à jour les hauteurs/couleurs des éléments après swap).
        5. N'écris PAS de code complet — décris l'intention et la logique. Des snippets
           courts (signature de fonction, structure HTML) sont OK, mais pas de fichiers entiers.

        ANTI-PIÈGES (leçons de prod — PRÉCISES dans ton plan) :
        - Canvas : fillRect(x, y, w, h) dessine depuis le coin HAUT-GAUCHE. y = canvas.height
          dessine hors champ. Le Coder doit utiliser y = canvas.height - barHeight.
        - Animation : JAMAIS de boucle for complète dans un setTimeout (instantané).
          Utiliser await sleep(ms) avec UNE itération par appel asynchrone.
        - Sync DOM : après un swap de valeurs, TOUJOURS mettre à jour l'affichage
          (bar.style.height = newValue) avant de continuer.
        - Init : le tableau doit être généré ET affiché au chargement (pas de barres vides).

        FORMAT DE SORTIE :
        ## Fichier : index.html
        - Structure : container, h1, div#chart (ou canvas), boutons (ids), slider, compteur
        - IDs DOM exacts : startBtn, resetBtn, speedRange, counter, chart
        - <link> vers styles.css, <script src="script.js">

        ## Fichier : styles.css
        - Thème sombre, layout flex, .bar avec transition height
        - 3 classes d'état : .comparing, .sorted, .default

        ## Fichier : script.js
        - Variables : arr[], isSorting, speed, comparisons
        - generateArray() : crée N valeurs aléatoires, appelle draw()
        - draw() : pour chaque valeur, crée/met à jour un div.bar avec height proportionnelle
        - bubbleSort() : async, boucle while(swapped) avec await sleep(speed) à chaque comparaison,
          swap = échange valeurs + MAJ height du DOM (bar.style.height)
        - Event listeners : startBtn → bubbleSort, resetBtn → generateArray, speedRange → speed
        - Init : generateArray() au chargement (barres visibles immédiatement)
        """,
    )
    subtask_description: str = dspy.InputField(desc="Description de la sous-tâche")
    strategy: str = dspy.InputField(desc="Stratégie choisie par l'architecte")
    target_files: str = dspy.InputField(desc="Liste stricte des fichiers à implémenter")
    draft_markdown: str = dspy.OutputField(desc="Plan d'implémentation structuré par fichier (intention + logique, PAS de code brut complet).")


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
        4. SANCTIONNE LES ÉCHECS DE TEST : Si ``test_results`` contient "Timeout", "Error", 
           "Fail" ou indique que l'exécution n'a pas pu se terminer, tu DOIS IMPÉRATIVEMENT
           déclarer un finding 'critical' et mettre ``is_approved=False``. Le code ne doit JAMAIS 
           être approuvé si le test n'est pas 100% vert.
        5. APPLIQUE ``security_vulnerabilities`` : toute vuln critical/high = ``is_approved=False``.
        6. DÉCIDE : ``is_approved`` ssi 0 critical/high.

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


class ConsolidationSignature(dspy.Signature):
    __doc__ = with_invariants(
        "judge",
        """Memory Consolidation Architect (F-68, P6-ter) — consolidation de claims du Knowledge Graph.

        Tu reçois N claims numérotés (1..N) pour une entité (fichier/sous-tâche). Ces claims sont
        des observations et réfutations accumulées pendant le run. Ton rôle est de DÉDUPLIQUER et
        FUSIONNER les claims redondants ou évolutifs pour éviter que le KG ne grossisse indéfiniment
        avec du rabâchage.

        PROCÉDURE OBLIGATOIRE :
        1. Lis les N claims numérotés. Identifie les DOUBLONS SÉMANTIQUES (même idée, wording
           différent — ex: "SyntaxError ligne 5" et "Erreur de syntaxe à la ligne 5").
        2. Pour chaque groupe de doublons : émets UPDATE <index_du_meilleur>: <texte fusionné>
           puis DELETE <index_des_autres>. Préfère UPDATE sur DELETE+ADD quand un fait a évolué.
        3. DELETE le bruit : mécanique pure lookupable (chemins de fichiers, détails d'API triviaux,
           timestamps) qui n'apporte rien à un run futur. MAIS NE JAMAIS supprimer un fait exploitant.
        4. Si tu découvres un PATRON transversal (leçon qui émerge de plusieurs claims), émets
           ADD: <insight consolidé> pour le capturer comme une nouvelle claim durable.
        5. Si rien à consolider (peu de claims, peu de chevauchement), retourne actions=[].

        ANTI-NITS : ne delete pas un claim juste pour un wording imparfait. Delete = redondance
        RÉELLE ou bruit trivial. Update = fusion de 2+ claims sur le même sujet.

        Les index sont 1-based (premier claim = index 1). Index invalide = action ignorée.
        """,
    )
    entity_id: str = dspy.InputField(desc="L'entité (fichier/sous-tâche) consolidée")
    numbered_claims: str = dspy.InputField(desc="Claims numérotés 1..N (format: 'N°1: <content>\\nN°2: <content>...'). Matière première de la consolidation.")
    output: ConsolidationOutput = dspy.OutputField(desc="Actions de consolidation UPDATE/DELETE/ADD (index 1-based) + résumé")


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
        api_base = settings.local_reasoning_api_base if model_id == settings.reasoning_model_id else settings.local_api_base
    if api_key is None:
        api_key = settings.local_api_key
    lm = dspy.LM(
        f"openai/{model_id}",
        api_base=api_base,
        api_key=api_key,
        max_tokens=8192,
        temperature=0.3,
        timeout=settings.llm_timeout_s,
        # F-104 (P8) : retry transport litellm natif (backoff+jitter internes,
        # honorant retry-after). Un blip transitoire ne tuait plus le nœud DSPy
        # (avant : except Exception → None, None → dégradation immédiate).
        # Autorité unique côté smolagents = RetryPolicy (llm_retry.py) ; côté
        # DSPy/litellm on réutilise le même budget de tentatives.
        num_retries=settings.llm_transport_retries if settings.llm_retry_enabled else 0,
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


async def _run_dspy_node(signature, predictor_kwargs: dict, settings: Settings, spec, think: bool = False, model_override: Optional[str] = None, module_class=None, tools: list = None, module_kwargs: dict = None) -> Any:
    """Helper pour exécuter un nœud DSPy avec le cycle de vie du modèle."""
    with model_lifecycle(spec) as srv:
        _mid = model_override or srv.model_id or spec.model
        _base = srv.api_base
        _key = srv.api_key
        lm = _configure_dspy(settings, _mid, think=think, api_base=_base, api_key=_key)
        with dspy.context(lm=lm):
            mkwargs = module_kwargs or {}
            if module_class is not None:
                if tools:
                    predictor = module_class(signature, tools=tools, **mkwargs)
                else:
                    predictor = module_class(signature, **mkwargs)
            else:
                predictor = dspy.ChainOfThought(signature, **mkwargs)
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
            from .skills_loader import SKILLS_DIR
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
    """Exécute le nœud PromptRefiner (modèle rapide, comme le Coder/Router).

    Reformule le prompt brut en spec structurée AVANT l'Architect. Tâche légère de
    reformatage/classification (pas de raisonnement profond) → utilise le FAST spec
    (Qwen3.5-4B, même modèle que le Coder et le Router). Clone exact du pattern
    execute_router_node (dspy.ChainOfThought + asyncio.to_thread + dégradation gracieuse),
    avec 2 inputs (raw_prompt + available_capabilities).

    Historique : ce nœud a d'abord tourné sur reasoning_spec + override gemma-4-E4B
    (PROMPT_REFINER_MODEL_ID), puis a été migré vers fast_spec (2026-08-10) — la
    reformulation d'un prompt n'a pas besoin d'un 9B raisonneur, et le fast_spec évite
    de spawner un serveur lourd supplémentaire. Le champ ``prompt_refiner_model_id``
    reste lu par config.py (rétro-compat .env) mais est désormais DORMANT (ignoré ici).

    Args:
        raw_prompt: Le prompt utilisateur brut (souvent vague).
        reasoning_model: Paramètre conservé pour rétro-compat de signature (non utilisé
            — le vrai modèle vient de ``settings.fast_spec`` via ``_run_dspy_node``,
            comme pour les autres nœuds DSPy).
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
            spec=settings.fast_spec,
            think=False,
        )
        refined = result.output
        n_amb = len(refined.ambiguities_detected) if refined.ambiguities_detected else 0
        print(f"[+] PromptRefiner : spec produite ({len(refined.refined_prompt)} caractères"
              f"{f', {n_amb} ambiguïté(s) détectée(s)' if n_amb else ''}).")

        metrics = NodeMetrics(
            node="prompt_refiner_dspy",
            model=settings.fast_spec.model,
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
    # pas appeler Context7 lui-même.
    task_content_raw = task.get("content", "")
    
    # F-57 v3 : Injection des skills statiques pour l'Architecte (ex: to-spec)
    from .skills_loader import BASE_SKILLS_BY_NODE, load_skill_body
    architect_skills_text = ""
    architect_skills_list = BASE_SKILLS_BY_NODE.get("architect", [])
    if architect_skills_list:
        blocks = []
        for s in architect_skills_list:
            body = load_skill_body(s)
            if body:
                blocks.append(f"### SKILL: {s}\n{body}")
        if blocks:
            architect_skills_text = "COMPÉTENCES POUR LA CONCEPTION (Applique ces guidelines pour structurer ton plan) :\n\n" + "\n\n".join(blocks) + "\n\n---\n\n"

    architect_input = architect_skills_text + task_content_raw
    if _mentions_external_lib(task_content_raw):
        from .context7_tool import fetch_context7_brief
        brief = await asyncio.to_thread(fetch_context7_brief, task_content_raw)
        if brief:
            architect_input = f"{brief}\n\n---\n\n{task_content_raw}"
            print(f"[+] Architect : brief Context7 injecté ({len(brief)} caractères).")
        else:
            print("[*] Architect : Context7 indisponible/non pertinent — planification sans brief.")
    try:
        # F-82 — Skill Finder : recherche dynamique de skills via ReAct avant le plan.
        # Gate par settings.skill_finder_enabled (défaut True → toujours ON, opt-out uniquement).
        # Permet de découvrir des compétences spécialisées : design, animation, son/audio,
        # canvas, moteurs de jeu, typographie, comme des frameworks (F-82 élargi).
        # Fail-open (F-82-bis) : si le ReAct échoue ou dérive (parse JSON, timeout), on
        # continue vers la planification normale avec les skills locaux.
        if settings.skill_finder_enabled:
            print("[*] Architect : Vérification des besoins en skills dynamiques (design, animation, son, canvas, libs)...")
            try:
                from .tools import search_and_install_skill

                # Signature ReAct. F-85 : wrap avec with_invariants (cohérence + anti-injection
                # — ce ReAct consomme du tool output externe non fiable : le résultat de
                # search_and_install_skill peut contenir du contenu distant).
                class SkillResearchSignature(dspy.Signature):
                    __doc__ = with_invariants(
                        "router",
                        """RÔLE STRICT : Tu es un ANALYSTE DE COMPÉTENCES (Skill Finder).
                        Tu ne rédiges JAMAIS de code applicatif (aucun HTML, CSS, JS ou Python).

                        MISSION :
                        Analyser le cahier des charges et déterminer si des compétences spécialisées
                        (design, animation, son/audio, moteur de jeu, canvas graphique, framework spécifique)
                        doivent être recherchées et installées via l'outil search_and_install_skill.

                        DÉCISION (agis, ne raconte pas) :
                        - Si le projet nécessite du son / audio / musique : appelle search_and_install_skill(query='sound') ou 'audio'.
                        - Si le projet implique du canvas / jeu / physique / game-feel : appelle search_and_install_skill(query='canvas') ou 'game'.
                        - Si le projet nécessite des animations / motion avancées : appelle search_and_install_skill(query='animation').
                        - Si le projet nomme une techno / lib (ex: React, Tailwind, GSAP, Three.js) : appelle search_and_install_skill(query='react' / 'tailwind' / etc.).
                        - Si les compétences locales suffisent déjà ou si rien de pertinent n'est trouvé : réponds 'Aucun skill ajouté'.

                        RÈGLES CRITIQUES :
                        - NE JAMAIS ÉCRIRE DE CODE dans ta réponse (pas de balises HTML, pas de styles CSS, pas de scripts JS).
                        - 1 seul appel d'outil (le plus pertinent pour le besoin central).
                        """,
                    )
                    task_content: str = dspy.InputField(desc="Le cahier des charges global")
                    research_summary: str = dspy.OutputField(desc="Résumé des skills installés ou 'Aucun skill ajouté'")

                def _search_skill_wrapper(query: str, author: str = None, triggers: str = None) -> str:
                    """Outil de recherche. 'query' cherche le skill (ex: 'sound', 'canvas', 'game', 'react').
                    triggers (optionnel) : mots-clés déclencheurs séparés par virgule
                    (ex: 'audio,sound,synth') proposés pour la ligne regex dédiée."""
                    return search_and_install_skill.forward(query, author, triggers)

                react_result = await _run_dspy_node(
                    signature=SkillResearchSignature,
                    predictor_kwargs={"task_content": task_content_raw},
                    settings=settings,
                    spec=settings.reasoning_spec,
                    think=False,
                    module_class=dspy.ReAct,
                    tools=[_search_skill_wrapper],
                    module_kwargs={"max_iters": 2},
                )

                research_summary = getattr(react_result, "research_summary", None)
                if research_summary and "Aucun" not in research_summary:
                    print(f"[+] Architect : Résultat de la recherche de skills : {research_summary}")
                    architect_input = f"RÉSULTAT DE L'INSTALLATION DYNAMIQUE DE SKILLS :\n{research_summary}\n\n---\n\n{architect_input}"
            except Exception as e:
                print(f"[!] Architect : Recherche de skills dynamiques échouée/ignorée ({e}) — continuation avec les skills locaux.")
        
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


async def execute_drafter_node(
    subtask_dict: dict, reasoning_model, settings: Settings
) -> Tuple[Optional[DrafterOutput], Optional[NodeMetrics]]:
    """Nœud Algorithm Drafter : génère la logique pure (sans outil)."""
    task_id = subtask_dict["id"]
    print(f"[*] DSPy Algorithm Drafter sur la sous-tâche {task_id}...")
    
    t0 = time.time()
    try:
        result = await _run_dspy_node(
            signature=DrafterSignature,
            predictor_kwargs={
                "subtask_description": subtask_dict["content"],
                "strategy": subtask_dict.get("strategy", "simple"),
                "target_files": ", ".join(subtask_dict.get("target_files", []))
            },
            settings=settings,
            spec=settings.reasoning_spec,
            think=True,
        )
        dur = time.time() - t0
        metrics = NodeMetrics(
            node="drafter_dspy",
            model=settings.reasoning_spec.model,
            duration_s=dur,
            input_tokens=0,
            output_tokens=0
        )
        from .models import DrafterOutput
        draft_out = DrafterOutput(task_id=task_id, draft_markdown=result.draft_markdown)
        return draft_out, metrics
    except Exception as e:
        print(f"[-] Erreur Drafter_DSPy : {str(e)[:200]}")
    
    dur = time.time() - t0
    metrics = NodeMetrics("drafter_dspy", settings.reasoning_spec.model, dur, 0, 0)
    return None, metrics


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
            spec=settings.no_think_spec,
            think=False,
        )
        
        metrics = NodeMetrics(
            node="security_dspy",
            model=settings.no_think_spec.model,
            duration_s=time.time() - start_time, 
            input_tokens=0, 
            output_tokens=0
        )
        return result.output, metrics
    except Exception as e:
        print(f"[-] Erreur critique DSPy (Security) : {e}")
        return None, None


def _judge_deliverable_files(subtask: dict) -> list:
    """Calcule la liste de fichiers à montrer au Judge = le DELIVERABLE COMPLET.

    Fix run 2026-08-11 : quand l'Architect split un app cohésive multi-fichiers en
    N sous-tâches (1 fichier chacune), ``subtask.target_files`` ne contient qu'1
    fichier. Le Judge ne voyait QUE index.html → « styles.css et script.js manquants »
    → rejet systématique ×3 itérations → escalade, bien que le Coder ait écrit les 3
    fichiers.

    Solution : UNION de ``target_files`` (la sous-tâche) avec TOUS les fichiers source
    présents dans le run dir (cwd). Le Judge évalue ainsi le deliverable complet, pas
    un sous-ensemble. Fail-open : si listdir échoue, on garde target_files seul.
    """
    import os as _os
    files = list(subtask.get("target_files", []))
    try:
        _src_exts = (
            ".html", ".htm", ".css", ".js", ".mjs", ".py",
            ".ts", ".tsx", ".jsx", ".vue", ".svelte",
        )
        cwd_files = sorted(
            f for f in _os.listdir(".")
            if _os.path.isfile(f) and f.lower().endswith(_src_exts)
        )
        merged = sorted(set(files) | set(cwd_files))
        if len(merged) > len(files):
            print(
                f"[i] Judge : vue deliverable complet ({len(merged)} fichiers source "
                f"au lieu de {len(files)} pour la sous-tâche)."
            )
        return merged
    except Exception:
        return files


async def execute_code_judge_node(subtask: dict, test_res: Any, security_res: Optional[SecurityOutput], reasoning_model, settings: Settings) -> Tuple[Optional[CodeJudgeOutput], Optional[NodeMetrics]]:
    """Exécute le Juge final qui décide si la boucle de développement s'arrête.

    Fail-closed (post-mortem run 123955) : si ``security_res is None`` (nœud Security
    en échec LLM/infra), on RETOURNE IMMÉDIATEMENT un verdict ``is_approved=False`` SANS
    appeler le LLM Judge. Avant ce fix, ``None`` était silencieusement transformé en
    "Aucune vulnérabilité critique détectée." → le Juge approuvait à l'aveugle un code
    non audité (run 123955 : ``bs-001`` APPROUVÉ juste après ``Error in generating
    model output`` côté Security). Désormais impossible : pas d'audit = pas d'approbation.

    Args:
        subtask (dict): La sous-tâche évaluée.
        test_res (Any): La sortie de l'agent Testeur QA (smolagents).
        security_res (SecurityOutput | None): Les vulnérabilités identifiées, ou ``None``
            si le nœud Security a échoué (auquel cas la sous-tâche est bloquée ici).
        reasoning_model: Modèle lourd.
        settings: Configuration.

    Returns:
        CodeJudgeOutput dictant si le code est 'approved' ou s'il nécessite un feedback.
    """
    print(f"[*] DSPy Code Judge sur la tâche {subtask.get('id')}...")
    # F-70 : ancrage IN-DIFF ONLY. Le Judge reçoit le diff multi-fichiers (F-53,
    # déjà propagé dans subtask["git_diff"]) en priorité + le code complet tronqué
    # pour la vérification des exigences. En iter 1 (diff vide) = full-file pur,
    # rétrocompat strict. F-102 : + le résumé structuré « ce que git dit » (ref
    # du tour, disponible dès l'iter 1). Voir judge_diff.build_judge_code_block.
    code_content = build_judge_code_block(
        _judge_deliverable_files(subtask),
        subtask.get("git_diff", ""),
        turn_diff_files=subtask.get("turn_diff_summary"),
    )

    # Fail-closed : pas d'audit sécurité = pas d'approbation. On court-circuite le
    # LLM Judge (économise le budget + rend l'approbation sans audit impossible).
    if security_res is None:
        print(f"[!] Security indisponible pour {subtask.get('id')} — Judge SKIPPÉ (fail-closed), approbation bloquée.")
        blocked = CodeJudgeOutput(
            task_id=subtask.get("id", "unknown"),
            is_approved=False,
            final_feedback=(
                "Audit de sécurité INDISPONIBLE (le nœud Security n'a pas produit de "
                "verdict — échec LLM/infra). Approbation BLOQUÉE par sécurité (fail-closed). "
                "Relancer le run ou auditer manuellement le code avant validation."
            ),
            findings=[Finding(
                severity="critical",
                category="security",
                location="(audit indisponible)",
                description="Le nœud Security Reviewer n'a pas délivré de verdict — code non audité.",
                suggestion="Relancer le run (cause souvent transitoire : VRAM, connexion llama-server) ou auditer manuellement.",
            )],
        )
        metrics = NodeMetrics(
            node="code_judge_dspy",
            model=settings.no_think_spec.model,
            duration_s=0.0,
            input_tokens=0,
            output_tokens=0,
        )
        return blocked, metrics

    # Fail-closed TEST (post-mortem run #3, 2026-08-14 — rejet utilisateur) : un
    # verdict de test FAILURE ne peut PLUS être approuvé par le LLM Judge. Le run #3
    # a montré le 9B approuver une app dont le Tester avait (correctement) dérivé
    # failure (animation instantanée sleep 5ms + compteur jamais incrémenté) — alors
    # que le prompt Judge disait DÉJÀ « SANCTIONNE LES ÉCHECS DE TEST ». Doctrine
    # F-33 : un prompt seul ne suffit jamais → gate LOGICIELLE, mirror du fail-closed
    # Security. failure/timeout/absence de verdict → is_approved=False SANS appel
    # LLM (le feedback va au Coder pour l'itération suivante ; à max_iterations,
    # l'escalation prend le relais). Opt-out : JUDGE_RESPECT_TEST_FAILURE=false.
    if getattr(settings, "judge_respect_test_failure", True):
        test_status = None
        test_details = ""
        if test_res is None:
            test_status = "missing"
        elif isinstance(test_res, str):
            if "TIMEOUT" in test_res.upper():
                test_status = "timeout"
                test_details = test_res
        elif hasattr(test_res, "status"):
            test_status = str(getattr(test_res, "status") or "").lower() or None
            test_details = str(getattr(test_res, "details") or "")
        if test_status in ("failure", "timeout", "missing"):
            reason = {
                "failure": "le nœud Tester a rapporté un ÉCHEC fonctionnel",
                "timeout": "le nœud Tester a subi un TIMEOUT",
                "missing": "le nœud Tester n'a produit AUCUN verdict",
            }[test_status]
            print(f"[!] Test {test_status} pour {subtask.get('id')} — Judge SKIPPÉ (fail-closed), approbation bloquée.")
            blocked = CodeJudgeOutput(
                task_id=subtask.get("id", "unknown"),
                is_approved=False,
                final_feedback=(
                    f"APPROBATION BLOQUÉE (fail-closed test) : {reason}. "
                    f"Détails du Tester : {test_details[:500] or '(aucun)'} "
                    "Corrige les échecs listés — l'approbation est impossible tant que "
                    "les tests fonctionnels échouent."
                ),
                findings=[Finding(
                    severity="critical",
                    category="testing",
                    location="(verdict Tester)",
                    description=f"Verdict Tester = {test_status} : {test_details[:300] or 'aucun détail'}",
                    suggestion="Corriger les échecs fonctionnels signalés par le Tester, puis relancer l'itération.",
                )],
            )
            metrics = NodeMetrics(
                node="code_judge_dspy",
                model=settings.no_think_spec.model,
                duration_s=0.0,
                input_tokens=0,
                output_tokens=0,
            )
            return blocked, metrics

    vulns = security_res.vulnerabilities if security_res.vulnerabilities else ["Aucune vulnérabilité critique détectée."]
    
    tests = "Résultats non disponibles"
    if test_res:
        if isinstance(test_res, dict):
            tests = f"status={test_res.get('status', '?')} | {test_res.get('details', test_res)}"
        else:
            _st = getattr(test_res, "status", None)
            # Post-mortem run #3 : le STATUS doit être explicite dans test_results
            # (avant, seuls les details passaient — le Judge LLM ne voyait jamais
            # le mot failure).
            tests = (f"status={_st} | " if _st else "") + str(getattr(test_res, "details", str(test_res)))
    tests = truncate_output(tests, head_lines=settings.stderr_head_lines, tail_lines=settings.stderr_tail_lines, max_chars=settings.feedback_max_chars)

    start_time = time.time()
    try:
        task_requirements = truncate_output(
            subtask.get("original_content", "") or "Cahier des charges non disponible.",
            head_lines=30,
            tail_lines=10,
            max_chars=1500,
        )
        # F-82 : rubric d'acceptation pondérée générée par l'Architecte (spécifique à la
        # sous-tâche, contrairement à la spec globale tronquée ci-dessus). Concaténée AVANT
        # la spec pour que le Judge voie d'abord les critères pondérés (CRITICAL/HIGH/...)
        # puis le détail du cahier des charges. Vide = comportement historique.
        from .validation_criteria import build_judge_rubric_block
        rubric_block = build_judge_rubric_block(subtask.get("acceptance_rubric", ""))
        if rubric_block:
            task_requirements = truncate_output(
                f"{rubric_block}\n### Cahier des charges global\n{subtask.get('original_content', '') or ''}",
                head_lines=45,
                tail_lines=10,
                max_chars=2000,
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
            spec=settings.no_think_spec,
            think=False,
        )
        
        metrics = NodeMetrics(
            node="code_judge_dspy",
            model=settings.no_think_spec.model,
            duration_s=time.time() - start_time,
            input_tokens=0,
            output_tokens=0
        )
        # F-93 : grounding post-hoc des findings (anti-hallucination de localisation).
        # Politique non-destructive (Option 1) : rétrograde + flague les findings dont la
        # localisation/fragment ne s'ancre dans AUCUN fichier source ; is_approved
        # inchangé. Fail-open total : un bug grounding ne peut JAMAIS casser le verdict.
        verdict = result.output
        if settings.judge_grounding_enabled and verdict is not None and getattr(verdict, "findings", None):
            try:
                from .judge_grounding import apply_grounding, ground_findings, read_source_files
                _src = read_source_files(_judge_deliverable_files(subtask))
                _report = ground_findings(verdict.findings, _src)
                if _report.ungrounded_count:
                    verdict = apply_grounding(verdict, _report)
                    print(
                        f"[i] Judge grounding (F-93) : {_report.ungrounded_count}/"
                        f"{_report.total} finding(s) non ancré(s) → rétrogradé(s)+flagué(s) "
                        f"(is_approved inchangé)."
                    )
            except Exception as _ge:
                print(f"[!] Judge grounding (F-93) échec (fail-open, verdict intact) : {_ge}")
        return verdict, metrics
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
            spec=settings.no_think_spec,
            think=False,
        )

        metrics = NodeMetrics(
            node="escalation_dspy",
            model=settings.no_think_spec.model,
            duration_s=time.time() - start_time,
            input_tokens=0,
            output_tokens=0
        )
        return result.output, metrics
    except Exception as e:
        print(f"[-] Erreur critique DSPy (Escalation) : {e}")
        return None, None


async def execute_consolidation_node(
    kg,
    run_id: str,
    settings: Settings,
) -> Tuple[Optional[dict], Optional[List[NodeMetrics]]]:
    """Exécute la consolidation mémoire du Knowledge Graph (F-68 Phase 1, P6-ter).

    Parcourt les claims de chaque entité du run, et pour celles qui dépassent le
    seuil ``memory_consolidation_after``, demande à un LLM-juge d'émettre des actions
    UPDATE/DELETE/ADD (format qm consolidation.ts) pour dédupliquer/fusionner les
    claims rabâchés. L'applier déterministe (apply_consolidation_actions, 0 LLM)
    applique ensuite ces actions.

    Déclenché en fin de run (workflows.py), APRÈS la boucle des sous-tâches, AVANT
    clear_checkpoint. Dégradation gracieuse : si le LLM est down, le KG reste intact
    (aucune mutation), on retourne (None, None) et l'appelant replie silencieusement.

    Args:
        kg: Le KnowledgeGraph (instance de graph_orchestrator.knowledge_graph.KnowledgeGraph).
            Typé ``Any`` ici pour éviter un import circulaire (knowledge_graph n'importe
            rien de ce module, mais on évite le couplage type statique).
        run_id (str): L'identifiant stable du run (pour filtrer les claims).
        settings (Settings): Configuration globale (memory_consolidation_after, specs).

    Returns:
        Tuple (summary_dict | None, metrics_list | None). summary_dict =
        {entity_id: {updated, deleted, added, skipped}} par entité consolidée.
        (None, None) si rien à consolider ou erreur LLM.
    """
    if not settings.memory_consolidation_enabled:
        return None, None

    print("[*] DSPy Nœud de Consolidation mémoire (F-68) — parcours des entités du run...")
    entities = kg.get_entities_by_run(run_id)
    if not entities:
        print("[*] Aucune entité à consolider pour ce run.")
        return None, None

    all_metrics: List[NodeMetrics] = []
    summary: dict = {}

    for entity_id in entities:
        # On consolide uniquement les observations + réfutations (rabâchage).
        # escalation + insight sont des leçons durables, préservées.
        claims = [
            c for c in kg.get_claims(entity_id)
            if c.get("kind") in ("observation", "refutation")
        ]
        if len(claims) < settings.memory_consolidation_after:
            continue  # qm maybeMaintain : pas assez de matière pour consolider

        # Numérotation 1-based (convention qm).
        numbered_text = "\n".join(
            f"N°{i}: {c.get('content', '')}"
            for i, c in enumerate(claims, start=1)
        )
        # Troncature pour protéger le contexte LLM.
        numbered_text = truncate_output(
            numbered_text,
            head_lines=settings.stderr_head_lines,
            tail_lines=settings.stderr_tail_lines,
            max_chars=settings.feedback_max_chars,
        )

        print(f"[*] Consolidation de {entity_id} ({len(claims)} claims)...")
        start_time = time.time()
        try:
            result = await _run_dspy_node(
                signature=ConsolidationSignature,
                predictor_kwargs={
                    "entity_id": entity_id,
                    "numbered_claims": numbered_text,
                },
                settings=settings,
                spec=settings.no_think_spec,
                think=False,
            )
            cons_output: ConsolidationOutput = result.output

            # Applier déterministe (0 LLM) — le LLM décide, le code applique.
            apply_result = apply_consolidation_actions(
                kg=kg,
                numbered_claims=claims,
                actions=cons_output.actions,
                entity_id=entity_id,
                run_id=run_id,
            )
            summary[entity_id] = apply_result

            all_metrics.append(NodeMetrics(
                node="consolidation_dspy",
                model=settings.no_think_spec.model,
                duration_s=time.time() - start_time,
                input_tokens=0,
                output_tokens=0,
            ))
            print(
                f"[*] {entity_id}: {apply_result['updated']} maj, "
                f"{apply_result['deleted']} suppr, {apply_result['added']} ajouts, "
                f"{apply_result['skipped']} skip."
            )
        except Exception as e:
            print(f"[-] Erreur consolidation {entity_id} ({e}) — KG intact, skip.")
            continue

    if not summary:
        print("[*] Aucune entité n'a dépassé le seuil de consolidation.")
        return None, None

    print(f"[*] Consolidation terminée : {len(summary)} entité(s) traitée(s).")
    return summary, all_metrics if all_metrics else None
