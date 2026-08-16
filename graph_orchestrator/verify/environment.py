"""Manifeste d'environnement pour la vérification projet (F-100).

Port de ``references/hermes-agent/agent/verify/environment.py`` (lui-même
porté de grok-cli ``src/verify/environment.ts``). Le manifeste vit à
``<projet>/.verify/environment.json`` (écart de chemin vs hermes ``.hermes/``
/ grok ``.grok/`` : namespace neutre de l'usine) et constitue la source de
vérité éditable : présent et valide, il PRIME sur la détection statique.

Dans le hot path de l'usine, aucun manifeste n'est écrit automatiquement —
il sert de surcharge explicite (un Coder ou un humain peut fournir une
recette exacte) ; la détection fraîche reste le chemin par défaut.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from graph_orchestrator.verify.recipes import Recipe, detect_recipe

MANIFEST_VERSION = 1
_MANIFEST_RELPATH = Path(".verify") / "environment.json"


def manifest_path(root: Path) -> Path:
    """Chemin du manifeste de vérification pour le projet à ``root``."""
    return Path(root) / _MANIFEST_RELPATH


def load_manifest(root: Path) -> Recipe | None:
    """Charge la recette sauvegardée, en tolérant les fichiers malformés.

    Miroir du ``loadVerifyEnvironment`` grok : tout problème de lecture /
    parse / forme retourne ``None`` plutôt que de lever — un manifeste
    corrompu dégrade vers la détection fraîche au lieu de casser la vérif.
    """
    path = manifest_path(root)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        manifest = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(manifest, dict):
        return None
    # Accepte la forme enveloppée {version, recipe} et la recette nue.
    recipe_raw = manifest.get("recipe", manifest)
    return Recipe.from_dict(recipe_raw)


def save_manifest(root: Path, recipe: Recipe) -> Path:
    """Persiste ``recipe`` comme manifeste de vérification du projet.

    Écrit la forme enveloppée versionnée (équivalent ``saveVerifyEnvironment``
    grok) et retourne le chemin du manifeste.
    """
    path = manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": MANIFEST_VERSION,
        "recipe": recipe.to_dict(),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def load_or_detect(root: Path) -> tuple[Recipe | None, str]:
    """Retourne (recipe, source) où source vaut 'manifest' ou 'detected'.

    Un manifeste sauvegardé PRIME sur la détection fraîche (comportement
    grok-cli : ``.grok/environment.json`` est la source de vérité).
    """
    saved = load_manifest(root)
    if saved is not None:
        return saved, "manifest"
    return detect_recipe(root), "detected"
