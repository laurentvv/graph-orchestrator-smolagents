"""Registry des outils smolagents outillés.

Pattern repris de my-claw : une liste plate TOOLS d'instances d'outils,
et une fonction get_tools(names) qui filtre par nom pour construire le set
d'outils d'un agent spécifique.

Les outils sont instanciés paresseusement (à l'import du module) avec graceful
degradation : si une dépendance manque, l'outil est simplement absent de la liste.
"""

from typing import List, Optional

from smolagents import Tool


def _safe_instantiate(tool_cls, *args, **kwargs) -> Optional[Tool]:
    """Instancie un outil, retourne None si la dépendance manque (graceful degradation)."""
    try:
        return tool_cls(*args, **kwargs)
    except Exception:
        return None


def _build_registry() -> List[Tool]:
    """Construit la liste plate de tous les outils disponibles."""
    tools: List[Tool] = []

    # --- Outils filesystem (toujours dispo, stdlib) ---
    from .filesystem import ReadFileTool, WriteFileTool, ListDirTool
    tools += [ReadFileTool(), WriteFileTool(), ListDirTool()]

    # --- Outil Node.js (subprocess sur `node`) ---
    from .node_exec import NodeExecTool
    node_tool = _safe_instantiate(NodeExecTool)
    if node_tool:
        tools.append(node_tool)

    # --- Recherche web (DuckDuckGo, dépendance ddgs) ---
    from .web_search import WebSearchTool
    web_tool = _safe_instantiate(WebSearchTool)
    if web_tool:
        tools.append(web_tool)

    # --- Python interpreter (built-in smolagents) ---
    from smolagents import PythonInterpreterTool
    py_tool = _safe_instantiate(
        PythonInterpreterTool,
        authorized_imports=[
            "math", "json", "re", "datetime", "pathlib", "os",
            "requests", "urllib", "csv", "statistics", "collections",
        ],
        timeout_seconds=60,
    )
    if py_tool:
        tools.append(py_tool)

    return tools


# Registry singleton (construit à l'import)
TOOLS: List[Tool] = _build_registry()

# Index par nom pour lookup rapide
TOOLS_BY_NAME: dict[str, Tool] = {t.name: t for t in TOOLS}


def get_tools(names: Optional[List[str]] = None) -> List[Tool]:
    """Retourne les outils par nom. Si names est None, retourne tous les outils.

    Usage :
        get_tools(["node_exec", "web_search"])  # un sous-set
        get_tools()                              # tout
    """
    if names is None:
        return list(TOOLS)
    return [TOOLS_BY_NAME[n] for n in names if n in TOOLS_BY_NAME]


def list_tool_names() -> List[str]:
    """Retourne la liste des noms d'outils disponibles (pour l'UI / health check)."""
    return list(TOOLS_BY_NAME.keys())
