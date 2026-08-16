"""Vérification exécutable des livrables (F-100) — port hermes-agent verify/.

Recettes de vérification statiques (détection de stack → commandes
bootstrap/build/test/start + port + chemin de readiness) et runner
subprocess (boucle de readiness HTTP + teardown de l'arbre de process).

« La page est servie et répond » devient une preuve exécutable au lieu de
``file://`` + console seule (les scripts ES-module et fetch sont bloqués
par CORS en file://). Consommé par le Static Tester (Tier HTTP) ; utilisable
en isolation via ``debug/run_verify.py``.
"""

from graph_orchestrator.verify.environment import (
    load_manifest,
    load_or_detect,
    manifest_path,
    save_manifest,
)
from graph_orchestrator.verify.recipes import Recipe, detect_recipe
from graph_orchestrator.verify.runner import (
    ReadinessResult,
    VerifyResult,
    run_verify,
)

__all__ = [
    "Recipe",
    "detect_recipe",
    "load_manifest",
    "load_or_detect",
    "manifest_path",
    "save_manifest",
    "ReadinessResult",
    "VerifyResult",
    "run_verify",
]
