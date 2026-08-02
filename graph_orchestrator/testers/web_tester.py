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
        from smolagents import ToolCollection, ToolCallingAgent

        from ..nodes import run_with_retry, resolve_verbosity, _detect_idle_step
        from ..skills_loader import load_skill_body
        from ..loop_guard import LoopGuard

        env = os.environ.copy()
        env["PUPPETEER_EXECUTABLE_PATH"] = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

        server_parameters = StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-puppeteer"],
            env=env,
        )

        # Le context manager assure la fermeture propre du serveur MCP après le run.
        with ToolCollection.from_mcp(server_parameters, trust_remote_code=True) as tool_collection:
            # Outils Chrome DevTools (navigation, clics, console...) + Context7
            # (doc de libs à jour). context7_tools() → [] si pas de clé
            # (backward-compat : le tester tourne sans Context7). Imbriqué dans un
            # `with` car la connexion MCP doit rester ouverte pendant le run du tester.
            from ..context7_tool import context7_tools
            from ..chrome_devtools_tool import chrome_devtools_tools
            from ..vision_callback import wrap_screenshot_tools, make_screenshot_callback
            with context7_tools() as c7_tools, chrome_devtools_tools() as cdt_tools:
                # F-45 : on cumule Puppeteer (skill dédié, assertions puppeteer_evaluate)
                # ET Chrome DevTools (console structurée avec source maps, Lighthouse,
                # take_snapshot a11y). Les deux pilotes cohabitent (profils isolés).
                tester_tools = [*tool_collection.tools]
                tester_tools.extend(c7_tools)
                tester_tools.extend(cdt_tools)
                # F-45 : wrap les outils de screenshot (puppeteer_screenshot ET
                # take_screenshot DevTools) pour faire remonter l'image au LLM via
                # observations_images. Sinon le Tester "rend" le screenshot sans le
                # voir — or le modèle reasoning (gemma-4) est multimodal et peut
                # détecter des bugs visuels (layout cassé, superpositions).
                screenshot_capture: list = []
                tester_tools = wrap_screenshot_tools(tester_tools, screenshot_capture)

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

                local_tester = ToolCallingAgent(
                    tools=tester_tools,
                    model=model,
                    name=f"tester_{task['id'].replace('-', '_')}",
                    description="Agent QA chargé de tester les interfaces web avec le MCP Puppeteer.",
                    verbosity_level=resolve_verbosity("HIGH"),
                    # max_steps adaptatif (F-47) : 6 en mode ciblé, settings.tester_max_steps
                    # (défaut 12, configurable via TESTER_MAX_STEPS) en complet.
                    # Rationnel complet : au-delà de 12, le contexte du ToolCallingAgent
                    # explose (observations DOM accumulées : +18k tokens/step observé
                    # sur run F-45, 405k tokens au step 21). Or gemma-4-12B perd en
                    # qualité au-delà de ~100k tokens.
                    max_steps=tester_max_steps,
                    # F-45 : step_callback vision — pousse le screenshot dans
                    # observations_images pour que le modèle le voie et détecte les
                    # bugs visuels (pas seulement console/assertions).
                    step_callbacks=[make_screenshot_callback(screenshot_capture)],
                )

                # Skill chargé via le loader centralisé (cohérent avec les autres nœuds) ;
                # le frontmatter est nettoyé pour économiser le contexte du LLM.
                skill_content = load_skill_body("web-tester")

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
                devtools_hint = (
                    "\n## OUTILS COMPLÉMENTAIRES Chrome DevTools (en plus de Puppeteer)\n"
                    "Tu as AUSSI accès à des outils DevTools (SANS préfixe puppeteer_) :\n"
                    "- `list_console_messages()` : erreurs JS avec source maps (plus précis que puppeteer_evaluate pour la console).\n"
                    "- `take_snapshot()` : arbre a11y complet (structure de la page, IDs/textes).\n"
                    "- `evaluate_script(function)` : JS dans la page (alternative à puppeteer_evaluate).\n"
                    "- `take_screenshot()` : capture visuelle — l'image TE REVIENT, analyse le rendu (bugs CSS, superpositions).\n"
                    "Priorité : garde Puppeteer pour les assertions (skill maîtrisé). Utilise DevTools pour la console et le visuel.\n"
                    if cdt_tools else ""
                )

                # F-46 : checklist PARSÉE depuis la spec (déterministe, 0 LLM). Force le
                # Tester à tester CHACUNE des fonctionnalités du cahier des charges, pas
                # seulement 2-3 au hasard (failure mode observé : compteur de comparaisons
                # manquant non détecté). Vide si la section est absente (fallback historique).
                from ..requirements_checklist import extract_functionalities, build_checklist_block
                functionalities = extract_functionalities(full_requirements)
                checklist_block = build_checklist_block(functionalities)

                # F-47 : en mode ciblé (itération >1 + réfutations), on REMPLACE la
                # checklist générique F-46 par un prompt ciblé sur les bugs signalés.
                # Le Tester ne teste QUE ces bugs + un smoke-test (console + screenshot).
                # Rationnel : en itération >1, 90% de la checklist F-46 re-vérifie des
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
                    # En mode ciblé, la checklist F-46 est remplacée (sinon on double le
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
Pour utiliser 'puppeteer_navigate', tu dois ouvrir le fichier HTML principal à cette URL EXACTE : {primary_url}
(N'utilise PAS {workspace_url}/index.html à la racine — le fichier est dans un sous-répertoire.)

### 🧹 NETTOYAGE DOM (économise le contexte — Priorité 6)
Quand tu inspectes le HTML de la page (via `puppeteer_evaluate("document.documentElement.outerHTML")`),
NE renvoie JAMAIS le HTML brut dans ton raisonnement : les `<script>`, `<style>`, `<svg>`,
`<canvas>` sont massifs et inutiles pour valider la logique. Applique TOUJOURS ce nettoyage
avant d'analyser ou de citer le DOM dans ton rapport :
```js
// Récupère un DOM NETTOYÉ (script/style/svg/canvas/comments supprimés, whitespace compacté)
(() => {{
  const clone = document.documentElement.cloneNode(true);
  clone.querySelectorAll('script,style,svg,canvas,iframe,noscript,template').forEach(el => el.remove());
  return clone.outerHTML.replace(/<!--[\\s\\S]*?-->/g,'').replace(/\\s{{2,}}/g,' ').slice(0, 8000);
}})()
```
Cela divise par ~10 la taille du HTML que tu manipules, sans perdre le texte/structure pertinents
pour tes assertions fonctionnelles (IDs, classes, contenu textuel, attributs aria-*).

Vérifie l'application web générée. N'oublie PAS l'étape 4 du skill (Functional Logic Testing) :
identifie les comportements clés du cahier des charges ci-dessus et écris des assertions via
'puppeteer_evaluate' pour vérifier qu'ils fonctionnent — pas seulement que la page ne crash pas.
{devtools_hint}
Une fois terminé, retourne ton résultat final STRICTEMENT en utilisant l'outil 'final_answer'.
Ton JSON DOIT absolument respecter ce format exact pour appeler l'outil final_answer :
{{
  "name": "final_answer",
  "arguments": {{
    "answer": {{
      "task_id": "{task['id']}",
      "status": "success ou failure",
      "details": "Un résumé détaillé de tes tests visuels, console ET assertions fonctionnelles."
    }}
  }}
}}
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
                return await run_with_retry(
                    local_tester, prompt, CoderOutput, settings.worker_max_retries,
                    loop_guard=guard, node_kind="tester",
                )
