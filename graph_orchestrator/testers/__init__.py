"""Package des runners de tests multi-techno (Priorité 2 — Tester polyvalent).

Chaque techno de test est encapsulée dans un runner implémentant l'interface
commune `TestRunner` (voir base.py). Le nœud Tester (`execute_tester_node`)
détecte la techno via `detect_tech` puis route vers le bon runner via
`get_runner`.

AJOUTER UNE TECHNO (rust, ts, go...) = 3 étapes, SANS toucher au dispatcher :
  1. Créer `graph_orchestrator/testers/<tech>_tester.py` (classe implémentant TestRunner).
  2. Créer le skill `skills/<tech>-tester/SKILL.md`.
  3. Ajouter une ligne au registre RUNNERS ci-dessous + mapper l'extension dans base.py.
"""

from __future__ import annotations

from .base import DEFAULT_TECH, TestRunner, detect_tech

__all__ = ["get_runner", "detect_tech", "DEFAULT_TECH", "TestRunner"]


# Registre techno → classe de runner. On instancie à la demande (lazy) : les
# runners LLM (web) importent MCP/smolagents, on évite donc de les charger si
# seule la techno python est demandée (et vice-versa pour le web sans pytest).
#
# NOTE : on mappe volontairement plusieurs alias de techno vers "web" — .tsx est
# du web (React), .jsx aussi. TypeScript pur (.ts) a son propre runner
# (placeholder : redirige vers web pour l'instant, runner dédié = cycle futur).
_RUNNER_CLASSES = {
    "web": ("web_tester", "WebTestRunner"),
    "python": ("python_tester", "PythonTestRunner"),
    # Technos connues mais sans runner dédié ce cycle : fallback web (compat).
    # Un runner dédié sera ajouté dans un cycle futur sans casser le dispatcher.
    "typescript": ("web_tester", "WebTestRunner"),
    "rust": ("web_tester", "WebTestRunner"),
    "go": ("web_tester", "WebTestRunner"),
    "java": ("web_tester", "WebTestRunner"),
    "ruby": ("web_tester", "WebTestRunner"),
    "php": ("web_tester", "WebTestRunner"),
    "c": ("web_tester", "WebTestRunner"),
    "cpp": ("web_tester", "WebTestRunner"),
    "csharp": ("web_tester", "WebTestRunner"),
}


def get_runner(tech: str) -> TestRunner:
    """Retourne le runner de tests adapté à la techno.

    Fallback sur `DEFAULT_TECH` ("web") si la techno est inconnue — c'était le
    seul comportement du Tester avant ce cycle, on garantit la compatibilité arrière.

    Args:
        tech: Techno canonique détectée par `detect_tech` ("python", "web", ...).

    Returns:
        Une instance de runner implémentant `TestRunner`.
    """
    module_name, class_name = _RUNNER_CLASSES.get(tech, _RUNNER_CLASSES[DEFAULT_TECH])

    # Import paresseux (lazy) : on n'importe que le module du runner demandé.
    # Cela évite de charger MCP/smolagents quand on fait du Python pur, etc.
    import importlib
    module = importlib.import_module(f".{module_name}", package=__package__)
    runner_cls = getattr(module, class_name)
    return runner_cls()
