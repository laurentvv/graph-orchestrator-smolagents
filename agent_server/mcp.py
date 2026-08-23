"""Connexion aux serveurs MCP (Model Context Protocol) au lifespan FastAPI.

Trois serveurs câblés (configurables via env) :
  - Context7 (HTTP) : documentation de libs à jour (anti-hallucination d'API)
  - crawl4ai-mcp-llm (stdio via uvx) : crawling web de pages dynamiques
  - chrome-devtools-mcp (stdio via npx) : pilotage Chrome live (screenshots, console,
    clics, Lighthouse) — auto-validation visuelle du Coder + Tester web. F-45.

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


def build_chrome_devtools_params(browser_url: Optional[str] = None) -> Optional[Any]:
    """Construit la config MCP pour chrome-devtools-mcp (stdio via npx). F-45.

    Chrome DevTools MCP : pilotage d'un Chrome live (Puppeteer sous le capot) pour
    navigate/screenshot/click/fill/console/Lighthouse. Sert à l'auto-validation
    visuelle du Coder (le modèle vision vérifie sa page avant final_answer) et au
    complément d'outils du WebTester (console structurée + Lighthouse).

    Args:
        browser_url: F-163 — URL du Chrome PARTAGÉ du pool navigateur
            (ex: http://127.0.0.1:39217). Si fournie, le serveur S'Y CONNECTE
            (--browserUrl) au lieu de lancer son PROPRE Chrome : pas de
            --isolated (l'isolation vient du user-data-dir temporaire du pool),
            pas de cold-start, pas d'arbre cmd→npx→node→Chrome à fuir.

    Options notables :
      - `--isolated` (mode historique seulement) : profil temporaire (cleanup
        auto, pas de pollution entre runs).
      - `--viewport 1280x800` : résolution réaliste (le défaut 800x600 tronque les
        layouts responsives — même correction que pour Puppeteer web_tester.py).
      - `--screenshot-format jpeg` : JPEG ~3-5x plus petit que PNG → économise le
        contexte du petit LLM vision (gemma-4-E4B). Crucial pour ne pas saturer.
      - `--executable-path` : chemin Chrome (si non set, le serveur cherche lui-même).

    Transport : stdio via `npx -y chrome-devtools-mcp@latest`. Si la connexion
    échoue, le context manager chrome_devtools_tools() yield [] (dégradation gracieuse).

    Config env :
      - CHROME_DEVTOOLS_ENABLED=0 : désactive totalement (opt-out global).
      - CHROME_PATH : chemin Chrome (remplace le hardcode web_tester.py:42).
      - CHROME_DEVTOOLS_HEADLESS=1 : mode headless (CI/sans UI).
    """
    if StdioServerParameters is None:
        return None
    if os.getenv("CHROME_DEVTOOLS_ENABLED", "1").strip().lower() in {"0", "false", "no", "off"}:
        return None

    args = ["-y", "chrome-devtools-mcp@latest", "--viewport", "1280x800",
            "--screenshot-format", "jpeg"]
    if browser_url:
        # F-163 : connexion au Chrome du pool (option officielle du serveur).
        args += ["--browserUrl", browser_url]
    else:
        args.append("--isolated")
    # Headless optionnel (défaut : visible, utile pour débugger en dev).
    if os.getenv("CHROME_DEVTOOLS_HEADLESS", "0").strip().lower() in {"1", "true", "yes", "on"}:
        args.append("--headless")
    # Chemin Chrome optionnel (sinon le serveur détecte l'installation système).
    # Ignoré en mode --browserUrl (le serveur ne lance rien).
    chrome_path = os.getenv("CHROME_PATH")
    if chrome_path and not browser_url:
        args += ["--executable-path", chrome_path]

    return StdioServerParameters(
        command="npx",
        args=args,
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
        ("chrome-devtools", build_chrome_devtools_params()),
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
    cdt = build_chrome_devtools_params()
    return [
        {"name": "context7", "configured": c7 is not None, "transport": "http"},
        {"name": "crawl4ai", "configured": crawl is not None, "transport": "stdio"},
        {"name": "chrome-devtools", "configured": cdt is not None, "transport": "stdio"},
    ]
