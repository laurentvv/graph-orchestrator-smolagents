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

        from ..nodes import run_with_retry, resolve_verbosity
        from ..skills_loader import load_skill_body

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
            with context7_tools() as c7_tools:
                tester_tools = [*tool_collection.tools]
                tester_tools.extend(c7_tools)
                local_tester = ToolCallingAgent(
                    tools=tester_tools,
                    model=model,
                    name=f"tester_{task['id'].replace('-', '_')}",
                    description="Agent QA chargé de tester les interfaces web avec le MCP Puppeteer.",
                    verbosity_level=resolve_verbosity("HIGH"),
                    # 24 steps (vs défaut 20) : les tests fonctionnels assertionnels
                    # (puppeteer_evaluate × 2-4 comportements) consomment des steps en
                    # plus du smoke-test (navigate/screenshot/console). Sans marge, le
                    # tester épuise son budget avant d'arriver aux assertions clés.
                    max_steps=24,
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

                prompt = f"""{build_role_header("web_tester")}

Voici tes instructions obligatoires (Skill) :
{skill_content}

### CAHIER DES CHARGES COMPLET (comportements attendus à vérifier)
{full_requirements}

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
                return await run_with_retry(local_tester, prompt, CoderOutput, settings.worker_max_retries)
