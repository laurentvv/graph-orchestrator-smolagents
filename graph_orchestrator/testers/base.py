"""Fondations du dispatch multi-techno du nœud Tester (Priorité 2).

Le Tester était historiquement 100% dédié au web (MCP Puppeteer). On le rend
polyvalent : chaque techno a son propre runner (web, python, rust, ts...), tous
derrière une interface commune (`TestRunner`).

La techno est détectée de façon REDONDANTE (deux signaux indépendants) :
1. `RouterOutput.language` — le routeur LLM a déjà classifié la techno principale.
2. Les extensions de `subtask.target_files` — déterministe, sans hallucination
   (.py→python, .html/.css/.js→web, .rs→rust, .ts/.tsx→typescript...).

Si les deux signaux se contredisent, les extensions l'emportent (déterministe > LLM).
En dernier recours, on retombe sur "web" (compatibilité arrière : c'était le
seul comportement avant ce cycle).
"""

from __future__ import annotations

import os
from typing import Optional, Protocol, Tuple, runtime_checkable

from ..config import Settings
from ..logging_utils import NodeMetrics
from ..models import CoderOutput


# =====================================================================
# Détection de techno (redondante : Router + extensions)
# =====================================================================

# Extension → techno. Le second caractère est ignoré dans le lower pour tolérer
# les casses (.PY, .Rs). Les frameworks web (.jsx/.tsx/.vue) ramènent au web.
_EXT_TO_TECH: dict[str, str] = {
    ".py": "python",
    ".html": "web",
    ".htm": "web",
    ".css": "web",
    ".js": "web",
    ".mjs": "web",
    ".jsx": "web",
    ".ts": "typescript",
    ".tsx": "web",
    ".vue": "web",
    ".svelte": "web",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".cs": "csharp",
}

# Language détecté par le routeur (string libre) → techno canonique.
# Tolérant aux casses et variantes ("JavaScript", "js", "node").
_ROUTER_LANG_TO_TECH: dict[str, str] = {
    "python": "python",
    "py": "python",
    "javascript": "web",
    "js": "web",
    "node": "web",
    "html": "web",
    "html5": "web",
    "css": "web",
    "web": "web",
    "frontend": "web",
    "typescript": "typescript",
    "ts": "typescript",
    "rust": "rust",
    "rs": "rust",
    "go": "go",
    "golang": "go",
    "java": "java",
    "ruby": "ruby",
    "php": "php",
    "c": "c",
    "cpp": "cpp",
    "c++": "cpp",
    "csharp": "csharp",
    "c#": "csharp",
}

# Techno par défaut si rien n'est détectable. "web" assure la compatibilité
# arrière (l'unique comportement du Tester avant ce cycle était Puppeteer).
DEFAULT_TECH = "web"


def _tech_from_extensions(target_files: list) -> str:
    """Infère la techno depuis les extensions des fichiers cibles.

    Si plusieurs technos sont présentes (ex: .py + .html), on prend la première
    détectée (l'Architect produit 1 sous-tâche = 1 fichier, donc en pratique il
    n'y a qu'une techno par sous-tâche). Retourne "" si rien de connu.
    """
    if not target_files:
        return ""
    for fpath in target_files:
        if not isinstance(fpath, str):
            continue
        _, ext = os.path.splitext(fpath)
        ext = ext.lower()
        if ext in _EXT_TO_TECH:
            return _EXT_TO_TECH[ext]
    return ""


def _tech_from_router(router_lang: Optional[str]) -> str:
    """Normalise la techno détectée par le routeur LLM (string libre)."""
    if not router_lang:
        return ""
    key = router_lang.strip().lower()
    return _ROUTER_LANG_TO_TECH.get(key, "")


def detect_tech(task: dict, router_lang: Optional[str] = None) -> str:
    """Détecte la techno de test d'une sous-tâche (détection redondante).

    Priorité :
      1. Extensions de `task["target_files"]` (déterministe — gagne en cas de conflit).
      2. `router_lang` (le LLM routeur a déjà classifié).
      3. `DEFAULT_TECH` ("web") — compat arrière.

    Args:
        task: La sous-tâche (doit contenir `target_files`, optionnellement).
        router_lang: La techno détectée par le routeur (`RouterOutput.language`),
            si connue.

    Returns:
        Une techno canonique ("python", "web", "typescript", "rust", ...) ou
        `DEFAULT_TECH` si rien n'est détectable.
    """
    ext_tech = _tech_from_extensions(task.get("target_files") or [])
    if ext_tech:
        return ext_tech

    router_tech = _tech_from_router(router_lang)
    if router_tech:
        return router_tech

    return DEFAULT_TECH


# =====================================================================
# Interface commune des runners
# =====================================================================

@runtime_checkable
class TestRunner(Protocol):
    """Interface commune à tous les runners de tests (web, python, rust...).

    Chaque runner encapsule la logique de test d'UNE techno et retourne le
    même contrat que l'ancien nœud Tester unique : un `CoderOutput` (status +
    details) + des métriques. Le workflow et le Judge le consomment ainsi sans
    se soucier de la techno sous-jacente.
    """

    async def run(
        self,
        task: dict,
        model,
        settings: Settings,
    ) -> Tuple[Optional[CoderOutput], Optional[NodeMetrics]]:
        """Exécute les tests pour la techno du runner.

        Args:
            task: La sous-tâche (content, target_files, tech...).
            model: Le modèle de raisonnement (OpenAIServerModel) pour les runners
                pilotés par LLM (web). Les runners subprocess (python) l'ignorent.
            settings: La configuration (timeouts, troncature...).

        Returns:
            (CoderOutput|None, NodeMetrics|None) — même contrat que les autres nœuds.
        """
        ...
