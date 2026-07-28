"""Outils filesystem ciblés codage : lire/écrire/lister des fichiers.

⚠️ NON SANDBOXÉ : accès direct au filesystem (usage local/dev contrôlé).
On restreint aux opérations utiles pour un agent de codage (pas de delete récursif
sauvage pour limiter les dégâts accidentels).
"""

import os
from typing import Optional

from smolagents import Tool


class ReadFileTool(Tool):
    name = "read_file"
    description = (
        "Lit le contenu d'un fichier texte et le retourne. "
        "Utile pour inspecter du code source, des configs, des logs."
    )
    inputs = {
        "path": {"type": "string", "description": "Chemin du fichier à lire."},
        "max_lines": {
            "type": "integer",
            "nullable": True,
            "description": "Nombre max de lignes à lire (défaut 1000).",
        },
    }
    output_type = "string"

    def forward(self, path: str, max_lines: int = 1000) -> str:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            if len(lines) > max_lines:
                content = "".join(lines[:max_lines]) + f"\n... [{len(lines) - max_lines} lignes tronquées]"
            else:
                content = "".join(lines)
            return content
        except FileNotFoundError:
            return f"[ERREUR] Fichier introuvable : {path}"
        except Exception as e:
            return f"[ERREUR] Lecture impossible : {e}"


class WriteFileTool(Tool):
    name = "write_file"
    description = (
        "Écrit du contenu dans un fichier (écrase s'il existe, crée sinon). "
        "Crée les répertoires parents si nécessaire. "
        "À utiliser pour créer/modifier du code source ou des fichiers de config."
    )
    inputs = {
        "path": {"type": "string", "description": "Chemin du fichier à écrire."},
        "content": {"type": "string", "description": "Le contenu à écrire."},
    }
    output_type = "string"

    def forward(self, path: str, content: str) -> str:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"[OK] {len(content)} caractères écrits dans {path}"
        except Exception as e:
            return f"[ERREUR] Écriture impossible : {e}"


class ListDirTool(Tool):
    name = "list_dir"
    description = (
        "Liste le contenu d'un répertoire. "
        "Utile pour explorer la structure d'un projet."
    )
    inputs = {
        "path": {"type": "string", "description": "Chemin du répertoire à lister."},
    }
    output_type = "string"

    def forward(self, path: str) -> str:
        try:
            entries = sorted(os.listdir(path))
            lines = []
            for e in entries:
                full = os.path.join(path, e)
                tag = "[D]" if os.path.isdir(full) else "   "
                lines.append(f"{tag} {e}")
            return f"{path}\n{'-' * 40}\n" + "\n".join(lines) if lines else f"{path} (vide)"
        except FileNotFoundError:
            return f"[ERREUR] Répertoire introuvable : {path}"
        except Exception as e:
            return f"[ERREUR] Listage impossible : {e}"
