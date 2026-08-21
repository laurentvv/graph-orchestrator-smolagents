"""Runner de tests WEB (MCP Puppeteer / Chrome DevTools).

Refactorisation du bloc Puppeteer qui vivait dans `execute_tester_node`
(nodes.py:438-503). Comportement strictement identique, simplement extrait dans
une classe `WebTestRunner` implémentant l'interface `TestRunner` commune, afin
que le nœud Tester puisse dispatcher selon la techno sans dupliquer de logique.

C'est le runner historique (seul comportement du Tester avant le cycle
polyvalent) et le fallback par défaut quand aucune techno n'est détectée.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

# clean_dom_for_llm est importé côté tests (tests/test_dom_filter.py) et utilisé
# à terme pour post-traiter tout HTML rapatrié côté Python. Dans web_tester, le
# nettoyage s'opère côté navigateur (JS injecté dans le prompt, plus efficace :
# pas de round-trip du HTML brut). On garde l'import symbolique pour documenter
# la dépendance et faciliter son utilisation future (ex: analyse post-capture).
from ..dom_filter import clean_dom_for_llm  # noqa: F401
from ..llama_server import model_lifecycle
from ..logging_utils import NodeMetrics
from ..models import CoderOutput
from ..prompts import build_role_header


class WebTestRunner:
    """Teste une application web (HTML/CSS/JS) via Chrome DevTools (MCP Puppeteer)."""

    async def run(self, task: dict, model, settings) -> Tuple[Optional[CoderOutput], Optional[NodeMetrics]]:
        # Imports locaux : MCP/smolagents sont lourds et le module doit rester
        # importable même si l'environnement web (Chrome/npx) n'est pas dispo
        # (ex: le runner Python n'en a pas besoin).
        from mcp import StdioServerParameters
        from graph_orchestrator.compaction import CompactingCodeAgent

        from ..nodes import run_with_retry, resolve_verbosity, LoggedOpenAIServerModel
        from ..skills_loader import load_skill_body, load_skill_body_resolved
        from ..loop_guard import LoopGuard

        env = os.environ.copy()
        env["PUPPETEER_EXECUTABLE_PATH"] = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

        server_parameters = StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-puppeteer"],
            env=env,
        )

        # F-104 (crush, P8) : init MCP Puppeteer BORNÉE par serveur — un npx
        # pendu (téléchargement à froid) ne fige plus le nœud 30 s ni l'event
        # loop. Timeout → DÉGRADATION : le tester tourne avec Chrome DevTools
        # (pilote primaire de fait, cf. F-72) + outils de lecture ; warning
        # loggué. Le CM est déjà ouvert par le helper : fermeture par callback
        # direct __exit__ (pas de `with` — déjà consommé).
        from ..mcp_connect import open_mcp_with_timeout
        from contextlib import ExitStack

        puppeteer_cm, puppeteer_tools = open_mcp_with_timeout(
            server_parameters, settings.puppeteer_connect_timeout_s, "puppeteer"
        )
        if puppeteer_cm is None:
            puppeteer_tools = []
        with ExitStack() as _mcp_stack:
            if puppeteer_cm is not None:
                _mcp_stack.callback(puppeteer_cm.__exit__, None, None, None)
            # Outils Chrome DevTools (navigation, clics, console...) + Context7
            # (doc de libs à jour). context7_tools() → [] si pas de clé
            # (backward-compat : le tester tourne sans Context7). Imbriqué dans un
            # `with` car la connexion MCP doit rester ouverte pendant le run du tester.
            from ..context7_tool import context7_tools
            from ..chrome_devtools_tool import chrome_devtools_tools
            from ..vision_callback import wrap_screenshot_tools, make_screenshot_callback
            from ..tools import read_file, list_directory, fix_known_error
            with context7_tools() as c7_tools, chrome_devtools_tools() as cdt_tools:
                # F-45 : on cumule Puppeteer (skill dédié, assertions puppeteer_evaluate)
                # ET Chrome DevTools (console structurée avec source maps, Lighthouse,
                # take_snapshot a11y). Les deux pilotes cohabitent (profils isolés).
                tester_tools = [*puppeteer_tools]
                tester_tools.extend(c7_tools)
                tester_tools.extend(cdt_tools)
                # read_file + list_directory : le Tester (CodeAgent) a légitimement
                # besoin de lire le code HTML/JS généré avant de le tester (identifier
                # les IDs/classes à cibler, comprendre la structure). Sans ces outils,
                # le modèle tente open() (interdit par la sandbox CodeAgent →
                # InterpreterError) puis read_file() (non fourni → InterpreterError),
                # et s'enfonce dans [Branch Summarization] jusqu'au timeout 600s.
                # Diagnostiqué sur run 2026-08-05_1507_bubble_sort (bs-001, 6 steps
                # gaspillés en "Forbidden function evaluation: 'open'/'read_file'").
                tester_tools.extend([read_file, list_directory])
                # F-133 (proposition utilisateur, session 2026-08-20) : le Tester
                # trouve une erreur mécanique → l'outil applique le fix prouvé →
                # il recharge et CONTINUE son test au lieu d'échouer l'itération
                # entière (cycle Coder ~30 min économisé). Classes couvertes :
                # const réassignée, \n littéral — tout le reste reste au verdict.
                tester_tools.append(fix_known_error)
                # F-45 : wrap les outils de screenshot (puppeteer_screenshot ET
                # take_screenshot DevTools) pour faire remonter l'image au LLM via
                # observations_images. Sinon le Tester "rend" le screenshot sans le
                # voir — or le modèle reasoning (gemma-4) est multimodal et peut
                # détecter des bugs visuels (layout cassé, superpositions).
                screenshot_capture: list = []
                tester_tools = wrap_screenshot_tools(tester_tools, screenshot_capture)
                # F-127 : enrichissement console pour le Tester AUSSI — sanitise
                # l'enum `types` (le 9B invente "exception" → MCP -32602 → step
                # perdu, run 2026-08-19_2104) et ajoute les stack traces des
                # erreurs (guide le verdict). Fail-open sans get_console_message.
                from ..vision_callback import wrap_console_enrichment
                tester_tools = wrap_console_enrichment(tester_tools)

                # F-72 (Prompt Offloading) : outils helper DevTools (clean_dom,
                # add_visual_tags, fuzz_click_all_buttons) — encapsulent des snippets JS
                # récurrents pour décharger le prompt du LLM. Wrappent evaluate_script
                # (DevTools, pilote primaire) — contrairement aux anciens
                # puppeteer_clean_dom/add_visual_tags qui wrappaient puppeteer_evaluate
                # (navigateur Puppeteer ne chargeant pas les file:// locaux = morts).
                # Fail-open : si DevTools indispo, factory retourne [] (rien ajouté).
                from ..devtools_dom_tools import build_devtools_helper_tools
                tester_tools.extend(build_devtools_helper_tools(cdt_tools))

                # F-47 : mode re-test ciblé si itération >1 ET réfutations disponibles.
                # Le Tester ne re-valide QUE les bugs signalés par le Judge + smoke-test,
                # en 6 steps (vs 12). Économie ~60% temps/tokens (façon git diff).
                from ..targeted_retest import (
                    should_use_targeted_retest, extract_bug_points,
                    build_targeted_retest_block, TARGETED_MAX_STEPS,
                )
                refutations = task.get("refutations", [])
                iteration = task.get("iteration", 1)
                use_targeted = should_use_targeted_retest(iteration, refutations)
                # max_steps adaptatif : 6 en mode ciblé (re-test), settings.tester_max_steps
                # (défaut 12, configurable) en mode complet.
                tester_max_steps = TARGETED_MAX_STEPS if use_targeted else settings.tester_max_steps
                mode_label = "CIBLÉ (re-test bugs)" if use_targeted else "complet"
                print(f"    [>] Tester mode: {mode_label} (max_steps={tester_max_steps})")

                # L'instanciation de local_tester a été déplacée plus bas, à l'intérieur du bloc `with model_lifecycle`.

                # F-57 v3: Skills dynamiques choisis par l'Architecte pour le Tester
                from ..skills_loader import enforce_skill_budget
                tester_skills = task.get("tester_skills", [])
                if not tester_skills:
                    tester_skills = ["web-tester"] # Repli statique par défaut
                
                # Budgétisation pour le Tester (socle "web-tester" toujours conservé)
                tester_skills = enforce_skill_budget(
                    tester_skills, 
                    budget_tokens=settings.skill_budget_tokens, 
                    always_skills={"web-tester"}
                )
                
                blocks = []
                # F-97 / MA-5 : résout la progressive disclosure F-92 côté serveur.
                # Le Tester (one-shot, 8 steps) a besoin de TOUT le contenu de la skill ;
                # lire les resources/*.md dynamiquement épuise son budget (5 steps perdus).
                # On inline donc les resources quand le flag est actif (défaut ON).
                loader = load_skill_body_resolved if settings.tester_inline_skill_resources else load_skill_body
                for s in tester_skills:
                    body = loader(s)
                    if body:
                        blocks.append(f"### SKILL: {s}\n{body}")
                skill_content = "\n\n".join(blocks)

                workspace_url = "file:///" + os.path.abspath(os.getcwd()).replace("\\", "/")

                target_files_urls = ""
                if "target_files" in task and task["target_files"]:
                    target_files_urls = "Les fichiers cibles de cette tâche se trouvent aux adresses suivantes :\n"
                    for fpath in task["target_files"]:
                        file_url = f"{workspace_url}/{fpath.replace('\\', '/')}"
                        target_files_urls += f"- {file_url}\n"

                # Premier fichier cible (typiquement le HTML principal à ouvrir dans le navigateur).
                # On l'utilise comme EXEMPLE concret dans le prompt : un petit LLM suit littéralement
                # l'exemple, donc il DOIT pointer sur le vrai fichier (ex: landing_page/index.html)
                # et non sur la racine du projet (bug : navigateur s'ouvrait à la racine).
                primary_target = (task.get("target_files") or ["index.html"])[0]
                primary_url = f"{workspace_url}/{primary_target.replace(chr(92), '/')}"

                # Cahier des charges COMPLET (spec racine), distinct de la sous-tâche.
                # Indispensable pour les tests fonctionnels : le tester doit connaître
                # le comportement attendu global pour écrire des assertions pertinentes
                # (ex: "le tri doit produire un tableau ordonné"), pas juste vérifier
                # que la page s'affiche. Fallback sur content si non propagé.
                full_requirements = task.get("original_content") or task.get("content", "")

                # F-45 : hint DevTools si Chrome DevTools est disponible (en complément
                # de Puppeteer). Vide si cdt_tools vide (backward-compat, Puppeteer seul).
                # Note 2026-08 : DevTools est désormais le pilote PRIMAIRE (navigation +
                # snapshot + console + assertions). Puppeteer navigate ne charge pas les
                # fichiers file:// locaux (bug du serveur @modelcontextprotocol/server-puppeteer
                # déprécié) → orientation DevTools-first pour fiabiliser le Tester.
                # F-72 : doc DevTools factorisée. DEVTOOLS_BASE_DOC (signatures communes
                # navigate_page/list_console_messages/evaluate_script + anti-IIFE critique)
                # est partagée avec le Coder (nodes.py::_DEVTOOLS_TOOLS_DOC). Le Tester
                # ajoute take_snapshot/click/fill/take_screenshot + ses avertissements
                # spécifiques (filePath, visual bug, python builtins).
                from ..chrome_devtools_tool import DEVTOOLS_BASE_DOC
                if cdt_tools:
                    devtools_hint = (
                        "\n## OUTILS Chrome DevTools (pilote PRIMAIRE — navigation + assertions)\n"
                        "Tu as accès à des outils DevTools (SANS préfixe puppeteer_). Ce sont désormais tes outils PRINCIPAUX (la navigation Puppeteer ne charge pas les fichiers locaux). ATTENTION :\n"
                        "  [DANGER FATAL] : N'utilise JAMAIS l'argument optionnel `filePath` dans AUCUN de ces outils (laisse-le omis/non défini). Si tu essaies de l'utiliser (même avec une chaîne vide), tu auras une erreur critique 'Access denied' MCP.\n"
                        + DEVTOOLS_BASE_DOC
                        + "\n- `take_snapshot(verbose: true)` : arbre a11y complet (structure, IDs, visibilité). Avec `verbose: true`, tu obtiendras tout le DOM ultra-détaillé.\n"
                        "- `click(uid=...)` / `fill(uid=..., value=...)` : interactions (uids vus dans take_snapshot).\n"
                        "- `take_screenshot(fullPage: true)` : capture visuelle. Avec `fullPage: true`, capture toute la hauteur. L'image TE REVIENT.\n"
                        "  [VISUAL BUG ALERT CRITIQUE] : Tu dois impérativement t'assurer qu'AUCUN élément clé ne disparaît ou ne devient invisible pendant l'interaction (ex: des barres qui s'effacent car elles perdent leur classe couleur sur un fond sombre). Si tu vois des éléments s'évaporer, c'est un FAILURE immédiat ! Tu peux utiliser `evaluate_script` pour inspecter les styles calculés (ex: getComputedStyle) et vérifier que les éléments ont bien une couleur.\n"
                        "  [PYTHON BUILT-INS] : Si tu utilises `time.sleep()` en Python, n'oublie pas de faire `import time` au début de ton code.\n"
                        "Priorité : DevTools pour TOUT (navigation, assertions, console, visuel). N'utilise les outils `puppeteer_*` QUE si DevTools est indisponible.\n"
                    )
                else:
                    devtools_hint = ""

                # F-46 : checklist PARSÉE depuis la spec (déterministe, 0 LLM). Force le
                # Tester à tester CHACUNE des fonctionnalités du cahier des charges, pas
                # seulement 2-3 au hasard (failure mode observé : compteur de comparaisons
                # manquant non détecté). Vide si la section est absente (fallback historique).
                from ..requirements_checklist import extract_functionalities, build_checklist_block
                functionalities = extract_functionalities(full_requirements)
                checklist_block = build_checklist_block(functionalities)

                # F-82 : critères fonctionnels générés par l'Architecte (pilote unique).
                # Priorité sur F-46 (regex spec) car plus précis — produits par compréhension
                # du cahier des charges, pas par pattern matching. Ne s'applique PAS en mode
                # ciblé F-47 (itération >1) qui reste orthogonal (re-test des bugs signalés).
                from ..validation_criteria import build_functional_criteria_block
                architect_criteria = task.get("functional_test_criteria") or []
                if architect_criteria:
                    checklist_block = build_functional_criteria_block(architect_criteria)

                # F-47 : en mode ciblé (itération >1 + réfutations), on REMPLACE la
                # checklist générique F-46/F-82 par un prompt ciblé sur les bugs signalés.
                # Le Tester ne teste QUE ces bugs + un smoke-test (console + screenshot).
                # Rationnel : en itération >1, 90% de la checklist re-vérifie des
                # choses qui marchaient déjà — gaspillage. Le re-test ciblé se concentre
                # sur ce que le Coder est censé avoir corrigé.
                if use_targeted:
                    bugs_feedback = extract_bug_points(refutations) or ""
                    # F-48 : diff git (lignes EXACTES modifiées) — source de vérité plus
                    # précise que les bugs texte. Vide si git indispo ou iter 1.
                    git_diff = task.get("git_diff", "")
                    targeted_block = build_targeted_retest_block(
                        bugs_feedback, iteration, git_diff
                    )
                    # En mode ciblé, la checklist F-46/F-82 est remplacée (sinon on double le
                    # travail : checklist complète + re-test ciblé = trop de steps pour 6).
                    checklist_block = targeted_block

                prompt = f"""{build_role_header("web_tester")}

Voici tes instructions obligatoires (Skill) :
{skill_content}

### CAHIER DES CHARGES COMPLET (comportements attendus à vérifier)
{full_requirements}
{checklist_block}
### Description de la sous-tâche testée
{task['content']}

ATTENTION - Le dossier de travail absolu est : {workspace_url}
{target_files_urls}

[FORMAT DES CHEMINS — OUTILS DIFFÉRENTS] Tes outils n'acceptent PAS le même format de chemin :
- `navigate_page(url=...)` (DevTools) : utilise le format URL `file:///D:/...` (cf. primary_url ci-dessous). C'est le SEUL outil qui attend `file:///`.
- `read_file(path=...)` / `list_directory(path=...)` : utilise un chemin simple SANS `file:///` — soit relatif (`index.html`, `landing_page/styles.css`) soit absolu `D:/GIT/...`. Passer un `file:///` ici → [Errno 22] ; passer `/d/GIT/` (MSYS) → [WinError 123].
(Sécurité : read_file/list_directory normalisent automatiquement un `file:///` ou un préfixe MSYS `/d/...` si tu glisses, mais UTILISE LE BON FORMAT pour ne pas gaspiller de steps.) Ne traduis JAMAIS en MSYS `/d/GIT/...`.

### ⚠️ NAVIGATION OBLIGATOIRE avec DevTools `navigate_page` (PAS puppeteer_navigate)
[BUG CONNU CRITIQUE] Le serveur `puppeteer_navigate` répond "Navigated to ..." mais ne
charge PAS réellement le fichier local file:// — la page reste `about:blank` et tous tes
`puppeteer_evaluate`/`take_snapshot` verront une page VIDE. Tu perdrais alors 16 steps en
boucle puis le nœud timeout (600s) → FAILURE systématique.
SOLUTION : utilise UNIQUEMENT `navigate_page(url="{primary_url}")` (outil Chrome DevTools,
SANS préfixe puppeteer_) pour ouvrir la page. C'est le seul pilote qui charge réellement
les fichiers file:// dans cet environnement.
URL EXACTE à passer : {primary_url}
(N'utilise PAS {workspace_url}/index.html à la racine — le fichier est dans un sous-répertoire.)
[2 NAVIGATEURS SÉPARÉS] Puppeteer et DevTools MCP pilotent chacun leur propre instance de
Chrome. Ne mélange JAMAIS : si tu navigues avec `navigate_page` (DevTools), fais TOUT le
reste (snapshot, console, evaluate, click, screenshot) avec les outils DevTools SANS préfixe
`puppeteer_`. Les assertions via `puppeteer_evaluate` verraient l'AUTRE navigateur (vide).

### 🛠️ INSPECTION DU DOM (préfère DevTools)
Pour inspecter la structure sans surcharger ton contexte :
1. `take_snapshot()` (DevTools) : arbre a11y complet — structure, IDs, visibilité. C'est ta vue
   principale du DOM. Utilise `verbose=True` pour le détail complet.
2. `evaluate_script(function="async () => document.body.innerHTML.length")` (DevTools) : pour
   des checks ponctuels (nombre d'éléments, valeurs, styles calculés).
Les outils `clean_dom()`, `add_visual_tags()`, `fuzz_click_all_buttons()`, `probe_canvas_activity()`, `fuzz_keyboard_controls()`, `expose_game_state()`, `instrument_calls()`, `dump_function_source()`, `force_advance()` instrumentent le navigateur DevTools actif :
- `probe_canvas_activity(window_ms=2400)` : hash RGB du canvas en 4 échantillons sur ~2,4 s + liveness rAF. Verdicts : ANIMATING / STATIC_PAINTED (+`suspect_animation_broken` si la boucle tourne mais que le rendu ne change JAMAIS) / INERT_EMPTY. Fenêtre min 800 ms — une chute à 800ms/row est invisible en dessous.
- `expose_game_state(names=None)` : lit l'état interne top-level (score, lines, currentPiece, board...) ×2 à 1,5 s d'intervalle → `changed_over_1500ms` prouve que l'état VIT.
- `instrument_calls(names=None, window_s=3)` : compte les appels RÉELS de draw/gameLoop/moveDown — discrimine moteur mort vs moteur vivant au rendu figé.
- `dump_function_source(names=None)` : source (toString) des fonctions du jeu — les bugs de rendu s'y lisent (ex réel : pièce peinte à `(ghostY+r)` au lieu de `(currentPiece.y+r)`).
- `force_advance(fn='moveDown', times=40)` : accélère l'horloge du jeu (N appels d'update en 1 s) → state_changed prouve la logique.
- `fuzz_keyboard_controls()` : simule les touches clavier de jeu (Flèches, Espace, Z, X) et capture immédiatement toute exception JS non gérée.
- `clean_dom()` : renvoie le DOM allégé (analyse sans polluer ton contexte).
- `add_visual_tags()` : ajoute des badges rouges numérotés sur les éléments cliquables avant un screenshot.
- `fuzz_click_all_buttons()` : clique tous les `<button>` pour réveiller les bugs JS cachés.

Vérifie l'application web générée. N'oublie PAS l'étape 4 du skill (Functional Logic Testing) :
identifie les comportements clés du cahier des charges ci-dessus et écris des assertions via
`evaluate_script` (DevTools) pour vérifier qu'ils fonctionnent — pas seulement que la page ne crash pas.
{devtools_hint}
Tu DOIS produire du code en appelant tes outils via du PYTHON (CodeAgent). NE JAMAIS expliquer sans agir.

### RÈGLES CRITIQUES (numérotées)
1. AGIS, ne raconte pas : quand tu dis "je vais faire X", tu DOIS faire X dans la foulée.
2. ARGUMENTS NOMMÉS OBLIGATOIRES : Pour TOUS tes appels d'outils, tu DOIS utiliser des arguments nommés (ex: evaluate_script(function="...")). Les arguments positionnels feront crasher l'exécution.
3. PYTHON BUILT-INS : Si tu utilises `time.sleep()` ou d'autres modules standards dans ton code Python, n'oublie pas de les importer (ex: `import time` au début du bloc).
4. NAVIGATION D'ABORD (STEP 1) : Démarre OBLIGATOIREMENT à l'étape 1 par `navigate_page(url="{primary_url}")` pour ouvrir l'application dans le navigateur. Ne perds JAMAIS d'étapes à lire le code source (`read_file`) au début : tu es un testeur E2E dynamique en boîte noire, ton rôle est d'interagir directement avec l'application vivante. Si tu as besoin de lire un fichier ponctuel, utilise l'outil `read_file` (jamais `open()`).
   ⚠️ Si `navigate_page` TIMEOUT sur cette page locale : l'UI est GELÉE par une boucle JS infinie (fichier local = chargement <1s). C'est un ÉCHEC FONCTIONNEL MAJEUR : conclus immédiatement `status="failure"` avec details="page gelée au chargement (navigation timeout : boucle JS infinie)". Ne brûle PAS tes steps à retenter navigate/screenshot (ils timeouteront aussi, et la console restera vide : un gel est silencieux).
5. ANIMATION = TEST TEMPOREL, PAS ÉTAT FINAL : pour un visualiseur/animation, NE JAMAIS
   te contenter d'attendre un délai fixe (ex: `setTimeout(r, 2000)`) puis vérifier l'état
   final — une animation **instantanée** (exécutée en 1 frame au lieu de progresser) passe
   ce test alors que c'est un bug grave. Tu DOIS mesurer la progression dans le temps :
   identifie un signal de progression dans le DOM (compteur, éléments marqués, attribut
   changeant), snapshot AVANT de déclencher l'action, re-snapshot après un court délai
   (~400ms), et vérifier que la progression est PARTIELLE (ni 0 ni terminale, si
   l'animation doit durer > 400ms). Une animation qui termine en < 50ms est un BUG
   (instantanée), pas un succès. Voir la recette temporelle dans le skill.
5-bis. JEU/CANVAS = PREUVE DE MOUVEMENT OBLIGATOIRE (F-145) : avant tout verdict PASS
   sur un critère de jeu/animation, tu DOIS prouver le MOUVEMENT avec un outil :
   `probe_canvas_activity()` (statut ANIMATING) OU `expose_game_state()` (changed_over_1500ms
   non vide) OU `force_advance()` (state_changed=true). Un screenshot statique ne prouve RIEN
   (ex réel : livrable Tetris au plateau superbe où la pièce n'a JAMAIS été dessinée à sa
   position réelle — invisible sur screenshot, flaggé par STATIC_PAINTED+suspect). Si
   STATIC_PAINTED alors que raf_per_s > 0 → défaut MAJEUR ; diagnostique en 2 appels :
   `instrument_calls()` puis `dump_function_source(names="draw")`, cite la ligne fautive
   dans ton rapport.
6. 🛑 BUDGET STEPS — CONVERGE RAPIDEMENT (anti over-exploration) : tu as un budget limité
   de steps. Suite type : 1 `navigate_page` + 1 `list_console_messages` + 1 assertion par
   critère fonctionnel + 1 `final_answer`. Soit ~{settings.tester_max_steps} steps pour TOUT. RÈGLES :
   - UNE SEULE assertion par `evaluate_script` (regroupe plusieurs checks dans le même
     script async plutôt que d'émettre 5 appels séparés sur la même page).
   - Ne JAMAIS re-vérifier un critère déjà PASS. PASS = acquis, on passe au suivant.
   - Si un critère FAIL après 2 tentatives → note FAIL et passe au suivant (ne boucle pas).
   - `final_answer` OBLIGATOIRE dès que tous les critères ont un verdict (PASS/FAIL/N-A).
   - Atteindre max_steps sans `final_answer` = ÉCHEC automatique du nœud (timeout).

### FORMAT DE SORTIE (obligatoire)
Tu écris du code Python dans un bloc ````python ... ```` qui appelle tes outils.
Une fois terminé, retourne ton résultat final STRICTEMENT en appelant l'outil `final_answer`.
Le dictionnaire passé à `final_answer` DOIT absolument respecter ce format exact :
```python
# Thought courte (1 phrase) PUIS appel immédiat — pas de longue réflexion
add_visual_tags()
# ... autres appels ...
final_answer({{"task_id": "{task['id']}", "status": "success", "details": "Un résumé détaillé de tes tests visuels, console ET assertions fonctionnelles."}})
```
"""
                # Guard anti-loop (fix TIMINGS_ANALYSE) : le Tester peut aussi boucler sur
                # le même appel puppeteer_evaluate (ex: même script JS échouant répétitivement
                # à cause d'une assignation `=` au lieu d'un appel `()` sur querySelector).
                # Le guard détecte la répétition exacte et injecte un message de rupture.
                # node_kind="tester" : le message idle cite les outils Puppeteer, pas write_file.
                guard = LoopGuard(
                    threshold=settings.loop_guard_threshold,
                    enabled=settings.loop_guard_enabled,
                )
                with model_lifecycle(settings.no_think_spec) as srv:
                    _mid = srv.model_id or settings.reasoning_no_think_model_id or settings.reasoning_model_id
                    # F-104 : LoggedOpenAIServerModel (retry transport pré-contenu,
                    # openfox+opencode) + revive=srv.revive (serveur spawné mort
                    # mid-run → respawn entre 2 tentatives, mémoire agent préservée).
                    # max_retries=0 : retry SDK openai désactivé, autorité = F-104.
                    dynamic_tester_model = LoggedOpenAIServerModel(
                        model_id=_mid,
                        api_base=srv.api_base or settings.local_reasoning_api_base,
                        api_key=srv.api_key or settings.local_api_key,
                        max_tokens=settings.reasoning_max_tokens,
                        client_kwargs={"timeout": settings.llm_timeout_s, "max_retries": 0},
                        revive=srv.revive,
                    )
                    local_tester = CompactingCodeAgent(
                        tools=tester_tools,
                        model=dynamic_tester_model,
                        name=f"tester_{task['id'].replace('-', '_')}",
                        description="Agent QA chargé de tester les interfaces web avec le MCP Puppeteer.",
                        verbosity_level=resolve_verbosity("HIGH"),
                        max_steps=tester_max_steps,
                        step_callbacks=[make_screenshot_callback(screenshot_capture)],
                        # Safety net anti `InterpreterError: Import of os is not allowed`
                        # (run9 F-90). PRINCIPE : TESTER = CODER pour les droits d'exécution
                        # Python — le Tester écrit des scripts de test et doit pouvoir coder
                        # comme le Coder. On reprend DONC le même set d'imports autorisés que
                        # le Coder (nodes.py:1071 additional_authorized_imports). La règle n°4
                        # steer vers read_file/list_directory pour LIRE, mais os/subprocess
                        # restent dispos (ex: subprocess pour lancer un binaire, os.path).
                        # Doctrine F-33 « un prompt seul ne suffit jamais » : si le modèle
                        # glisse à `import os`/`import subprocess`, on ne crash plus.
                        additional_authorized_imports=["os", "subprocess"],
                    )
                    return await run_with_retry(
                        local_tester, prompt, CoderOutput, settings.worker_max_retries,
                        loop_guard=guard, node_kind="tester",
                        timeout_s=settings.tester_timeout_s,
                    )
