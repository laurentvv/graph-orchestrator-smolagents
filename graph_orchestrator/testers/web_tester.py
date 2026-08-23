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
        # F-162 (plan migration pydantic-ai-harness, phase 3.7) : moteur
        # alternatif pydantic-ai-harness activé par TESTER_ENGINE=pydantic.
        # L'aiguillage est le SEUL point de divergence — smolagents reste le
        # défaut inchangé (miroir CODER_ENGINE dans execute_coder_node).
        _engine = str(getattr(settings, "tester_engine", "smolagents") or "smolagents").lower()
        if _engine == "pydantic":
            from ..tester_pydantic import run_tester_pydantic

            return await run_tester_pydantic(task, settings)
        if _engine != "smolagents":
            print(f"[!] TESTER_ENGINE inconnu '{_engine}' — repli smolagents.")
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

                # Goulot 2026-08-21 (décision user : skill forcé OBLIGATOIRE pour
                # Coder ET Tester) : le mode d'emploi des outils DevTools
                # (devtools-preview — navigate→console→screenshot, anti-IIFE,
                # pièges) ne peut pas dépendre de la sélection LLM de
                # l'Architect (le golden #19 l'avait, les runs ratés l'ont
                # perdu). Le WebTester pilote les MÊMES outils DevTools MCP —
                # garantie déterministe, avant le budget (priorité mode d'emploi).
                # Copie d'abord : task["tester_skills"] est persisté au checkpoint
                # (review Kilo PR #102 — jamais de mutation du dict de tâche).
                tester_skills = list(tester_skills)
                if "devtools-preview" not in tester_skills:
                    tester_skills.insert(0, "devtools-preview")

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
                    reqs_block = ""
                else:
                    reqs_block = f"### COMPREHENSIVE SPECIFICATION (expected behaviors to verify)\n{full_requirements}\n"

                prompt = f"""{build_role_header("web_tester")}

Here are your mandatory skill instructions:
{skill_content}

{reqs_block}{checklist_block}
### Description of the subtask under test
{task['content']}

ATTENTION - The absolute working directory is: {workspace_url}
{target_files_urls}

[PATH FORMAT FOR DIFFERENT TOOLS] Your tools expect specific path formats:
- `navigate_page(url=...)` (DevTools): uses the URL format `file:///D:/...` (see primary_url below). This is the ONLY tool expecting `file:///`.
- `read_file(path=...)` / `list_directory(path=...)`: uses a relative path (`index.html`, `landing_page/styles.css`) or standard absolute path `D:/GIT/...`. (Do NOT pass MSYS `/d/GIT/...` or `file:///`).

### ⚠️ MANDATORY NAVIGATION via DevTools `navigate_page` (NOT puppeteer_navigate)
Always use `navigate_page(url="{primary_url}")` to open the application in Chrome.
EXACT URL to pass: {primary_url}
Puppeteer and DevTools MCP run separate Chrome instances. Always use DevTools tools (`navigate_page`, `take_snapshot`, `list_console_messages`, `evaluate_script`, `click`, `take_screenshot`).

### 🛠️ DOM INSPECTION (DevTools tools)
1. `take_snapshot(verbose=True)`: Full accessibility/DOM tree — structure, IDs, visibility.
2. `evaluate_script(function="async () => ...")`: For executing runtime assertions.
3. Interactive testing tools:
- `probe_canvas_activity(window_ms=2400)`: Tests canvas animation liveliness (ANIMATING / STATIC_PAINTED).
- `probe_sort_state(max_wait_ms=180000)`: Animated-sort verdict — waits IN-PAGE until sorted (SORTED / IN_PROGRESS / STATIC_UNSORTED). NEVER conclude "not sorted" without it.
- `expose_game_state(names=None)`: Inspects internal runtime game variables across a 1.5s interval.
- `instrument_calls(names=None, window_s=3)`: Counts actual function calls (e.g. draw/update).
- `fuzz_keyboard_controls()`: Simulates keyboard inputs (Arrows, Space, Z, X).
- `fuzz_click_all_buttons()`: Fuzz-clicks all buttons to uncover hidden JS runtime exceptions.
- `clean_dom()`: Returns lightweight DOM.
- `add_visual_tags()`: Adds numbered visual tags for screenshots.

Verify the generated web application. Execute functional assertions via `evaluate_script` (DevTools) to prove key behaviors work dynamically.
{devtools_hint}
You MUST produce code by executing tools via PYTHON (CodeAgent). NEVER explain without acting.

### CRITICAL RULES (numbered)
1. ACT, do not just narrate: When you state an intention, execute it immediately in the code block.
2. MANDATORY NAMED ARGUMENTS: For ALL tool calls, you MUST use named arguments (e.g. `evaluate_script(function="...")`).
3. PYTHON BUILT-INS: If you use `time.sleep()`, import it (`import time`).
4. NAVIGATION FIRST (STEP 1): Always begin at Step 1 with `navigate_page(url="{primary_url}")`. Do NOT waste steps reading source files upfront; you are a dynamic black-box tester.
   ⚠️ If `navigate_page` TIMEOUTS on this local page: the UI is frozen by an infinite JS loop. Return `status="failure"` immediately with details="page frozen on load (infinite loop)".
5. ANIMATION = TEMPORAL TEST, NOT STATIC STATE: For algorithm visualizers and animations, measure progression over time (verify partial state during execution, not merely checking initial or post-completion state).
5-bis. GAME/CANVAS = MOTION PROOF REQUIRED: For interactive games, prove motion with `probe_canvas_activity()` (ANIMATING) or `expose_game_state()`.
5-ter. PROBE ISOLATION & ANIMATED SORTS: successive evaluate_script MUTATE the page (clicks, resets, corrupted state). Before each INDEPENDENT assertion sequence, reset the page with `navigate_page(type="reload")` (~0.2s, cheap). For sorting tasks, NEVER conclude "not sorted" from a snapshot taken before the animation completes: call `probe_sort_state(max_wait_ms=...)` ONCE and trust its verdict — SORTED_AFTER_WAIT = pass, IN_PROGRESS_STILL_MOVING = pass (slow animation, NOT a defect), STATIC_UNSORTED = fail.
6. STEP BUDGET — CONVERGE RAPIDLY: You have a limited step budget (~{settings.tester_max_steps} steps).
   - Batch assertions per page state into a single `evaluate_script`.
   - Never re-verify already PASS criteria.
   - Call `final_answer` immediately once all criteria have verdicts.

### OUTPUT FORMAT (mandatory)
You write Python code inside a ````python ... ```` block that calls your tools.
When complete, return your final verdict by calling `final_answer`:
```python
# Short Thought (1 sentence) THEN immediate execution:
add_visual_tags()
# ... other test calls ...
final_answer({{"task_id": "{task['id']}", "status": "success", "details": "Detailed summary of console, visual, and functional assertion test results."}})
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
                    # Goulot 2026-08-21 (review Kilo PR #102) : le Tester utilise
                    # make_screenshot_callback, qui embarque les nudges churn
                    # d'édition / budget vision / lectures stériles — sans reset
                    # ici, il hériterait des compteurs du Coder. Même lifecycle
                    # que nodes.py : reset à chaque montage du nœud.
                    from ..vision_callback import (
                        reset_edit_churn,
                        reset_read_stall,
                        reset_vision_budget,
                    )

                    reset_read_stall()
                    reset_edit_churn()
                    reset_vision_budget()
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
