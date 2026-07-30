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

from ..logging_utils import NodeMetrics
from ..models import CoderOutput


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
            local_tester = ToolCallingAgent(
                tools=[*tool_collection.tools],
                model=model,
                name=f"tester_{task['id'].replace('-', '_')}",
                description="Agent QA chargé de tester les interfaces web avec le MCP Chrome DevTools.",
                verbosity_level=resolve_verbosity("HIGH"),
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

            prompt = f"""Tu es un agent QA autonome (Web Tester Node).

Voici tes instructions obligatoires (Skill) :
{skill_content}

Contenu de la tâche d'origine : {task['content']}

ATTENTION - Le dossier de travail absolu est : {workspace_url}
{target_files_urls}
Pour utiliser 'puppeteer_navigate', tu dois ouvrir le fichier HTML principal à cette URL EXACTE : {primary_url}
(N'utilise PAS {workspace_url}/index.html à la racine — le fichier est dans un sous-répertoire.)

Vérifie l'application web générée. Utilise tes outils MCP pour naviguer, inspecter et interagir.
Une fois terminé, retourne ton résultat final STRICTEMENT en utilisant l'outil 'final_answer'.
Ton JSON DOIT absolument respecter ce format exact pour appeler l'outil final_answer :
{{
  "name": "final_answer",
  "arguments": {{
    "answer": {{
      "task_id": "{task['id']}",
      "status": "success ou failure",
      "details": "Un résumé détaillé de tes tests visuels et interactifs."
    }}
  }}
}}
"""
            return await run_with_retry(local_tester, prompt, CoderOutput, settings.worker_max_retries)
