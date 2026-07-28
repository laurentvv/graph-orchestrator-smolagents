"""Outil d'exécution Node.js pour les agents.

smolagents n'a pas d'outil Node.js built-in. On crée un Tool qui exécute du
JavaScript/TypeScript via le runtime `node` (subprocess), avec timeout.

⚠️ NON SANDBOXÉ : exécution directe sur la machine (usage local/dev contrôlé).
"""

import subprocess
import os
import tempfile
from typing import Optional

from smolagents import Tool


class NodeExecTool(Tool):
    name = "node_exec"
    description = (
        "Exécute du code JavaScript/Node.js et retourne la sortie standard. "
        "Utile pour : tester du JS, parser du JSON, utiliser les APIs Node, "
        "vérifier la syntaxe d'un fichier .js/.ts, ou faire du prototypage rapide. "
        "Le code est écrit dans un fichier temporaire et exécuté via `node`."
    )
    inputs = {
        "code": {
            "type": "string",
            "description": "Le code JavaScript à exécuter (CommonJS, `require` disponible).",
        },
        "timeout": {
            "type": "integer",
            "nullable": True,
            "description": "Délai max en secondes (défaut 30).",
        },
    }
    output_type = "string"

    def forward(self, code: str, timeout: Optional[int] = 30) -> str:
        # On écrit le code dans un fichier temporaire pour gérer proprement
        # le multi-lignes et les modules ES (extension .mjs => ESM, .cjs => CommonJS).
        suffix = ".mjs"  # ESM par défaut (import/export modernes)
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, encoding="utf-8"
        )
        try:
            tmp.write(code)
            tmp.flush()
            tmp.close()

            result = subprocess.run(
                ["node", tmp.name],
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )

            output = result.stdout
            if result.returncode != 0:
                output += f"\n[stderr]\n{result.stderr}" if result.stderr else ""
                output += f"\n[exit code {result.returncode}]"
            # Tronque les sorties énormes (évite de saturer le contexte LLM)
            if len(output) > 20000:
                output = output[:20000] + "\n... [sortie tronquée]"
            return output or "(aucune sortie)"
        except subprocess.TimeoutExpired:
            return f"[TIMEOUT] L'exécution Node a dépassé {timeout}s."
        except FileNotFoundError:
            return "[ERREUR] `node` n'est pas installé ou absent du PATH."
        finally:
            try:
                os.unlink(tmp.name)
            except (OSError, UnboundLocalError):
                pass
