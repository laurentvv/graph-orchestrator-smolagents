"""Connexion aux serveurs MCP (Model Context Protocol) au lifespan FastAPI.

Deux serveurs câblés (configurables via env) :
  - Context7 (HTTP) : documentation de libs à jour (anti-hallucination d'API)
  - crawl4ai-mcp-llm (stdio via uvx) : crawling web de pages dynamiques

Pattern repris de my-claw : ToolCollection.from_mcp() dans le lifespan, avec
tolérance aux pannes (fallback liste vide + warning) si un serveur est indisponible.

Les serveurs sont connectés au démarrage (lifespan) et fermés proprement au shutdown.
"""

import os
from contextlib import contextmanager
from typing import Any, List, Optional

from smolagents import Tool, ToolCollection

# Rend les types mcp disponibles même si l'extra n'est pas installé
try:
    from mcp import StdioServerParameters
except ImportError:
    StdioServerParameters = None  # type: ignore


def build_context7_params() -> Optional[dict]:
    """Construit la config MCP pour Context7 (HTTP), ou None si pas de clé API.

    Context7 : https://mcp.context7.com/mcp, requiert CONTEXT7_API_KEY.
    """
    api_key = os.getenv("CONTEXT7_API_KEY")
    if not api_key:
        return None
    return {
        "url": "https://mcp.context7.com/mcp",
        "transport": "streamable-http",
        "headers": {"CONTEXT7_API_KEY": api_key},
    }


def build_crawl4ai_params() -> Optional[Any]:
    """Construit la config MCP pour crawl4ai-mcp-llm (stdio via uvx).

    crawl4ai : crawling web pour LLM. Lancé via `uvx --python 3.13 crawl4ai-mcp-llm`.
    Note : Python 3.13 spécifié pour éviter les soucis de compilation sur Windows.
    """
    if StdioServerParameters is None:
        return None
    return StdioServerParameters(
        command="uvx",
        args=["--python", "3.13", "crawl4ai-mcp-llm"],
        env={**os.environ},
    )


@contextmanager
def connect_mcp_server(name: str, params) -> List[Tool]:
    """Context manager qui connecte un serveur MCP et yield ses outils.

    Tolérance aux pannes : si la connexion échoue (réseau, dépendance, serveur down),
    on yield une liste vide + warning au lieu de crasher.
    """
    if params is None:
        print(f"[MCP] {name}: configuration manquante, ignoré.")
        yield []
        return

    try:
        with ToolCollection.from_mcp(params, trust_remote_code=True) as tool_collection:
            tools = list(tool_collection.tools)
            print(f"[MCP] {name}: {len(tools)} outil(s) chargé(s).")
            yield tools
    except Exception as e:
        print(f"[MCP] {name}: connexion échouée ({e}), ignoré.")
        yield []


@contextmanager
def connect_all_mcp():
    """Connecte TOUS les serveurs MCP configurés et yield l'ensemble des outils.

    À utiliser dans le lifespan FastAPI (avec `with`). Les serveurs sont fermés au exit.
    Imbrique proprement les context managers via ExitStack pour garantir le cleanup.
    """
    import contextlib

    servers = [
        ("context7", build_context7_params()),
        ("crawl4ai", build_crawl4ai_params()),
    ]

    all_tools: List[Tool] = []
    with contextlib.ExitStack() as stack:
        for name, params in servers:
            tools = stack.enter_context(connect_mcp_server(name, params))
            all_tools.extend(tools)
        print(f"[MCP] Total : {len(all_tools)} outil(s) MCP chargé(s).")
        yield all_tools


def list_mcp_servers_status() -> List[dict]:
    """Diagnostic pour /health : quels serveurs MCP sont configurés/dispos ?"""
    c7 = build_context7_params()
    crawl = build_crawl4ai_params()
    return [
        {"name": "context7", "configured": c7 is not None, "transport": "http"},
        {"name": "crawl4ai", "configured": crawl is not None, "transport": "stdio"},
    ]
