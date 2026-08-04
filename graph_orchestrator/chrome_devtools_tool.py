"""Intégration Chrome DevTools MCP pour le Coder et le WebTester (F-45).

Chrome DevTools MCP (https://github.com/ChromeDevTools/chrome-devtools-mcp) pilote
un Chrome live via Puppeteer, exposant des outils de navigation, screenshots, clics,
console JS structurée, Lighthouse et performance traces.

Deux usages dans le coding workflow :
  1. CODER (auto-validation visuelle) : après write_file d'une page HTML, le Coder
     ouvre la page (navigate_page), prend un screenshot (take_screenshot) et le
     modèle vision (gemma-4-E4B — validé, il voit les images) vérifie le rendu AVANT
     final_answer. Évite d'envoyer une page visuellement ratée au Tester.
  2. WEBTESTER (complément d'outils) : Chrome DevTools s'ajoute à Puppeteer (gardé
     pour son skill dédié). Apporte list_console_messages (erreurs JS avec source
     maps), take_snapshot (a11y tree), lighthouse_audit, performance traces.

⚠️ Capture d'image vs modèle : smolagents ne pousse PAS automatiquement les
screenshots des outils MCP dans le contexte multimodal du LLM (observations_images).
Il faut un step_callback dédié — cf. vision_callback.make_screenshot_callback.

Robustesse : si le serveur est indisponible (npx absent, Chrome non trouvé,
CHROME_DEVTOOLS_ENABLED=0), chrome_devtools_tools() yield []. Aucun nœud ne
dépend de Chrome DevTools pour fonctionner (backward-compatible, comme Context7).
"""

import logging
from contextlib import contextmanager
from typing import Any, Optional

from smolagents import ToolCollection

logger = logging.getLogger(__name__)


def _build_params() -> Optional[Any]:
    """Construit les params MCP Chrome DevTools, ou None si désactivé/indisponible.

    Délègue à agent_server.mcp.build_chrome_devtools_params (source unique de
    vérité pour la commande npx/options). On ne duplique pas la config ici.
    """
    from agent_server.mcp import build_chrome_devtools_params

    return build_chrome_devtools_params()


@contextmanager
def chrome_devtools_tools():
    """Context manager : ouvre une connexion Chrome DevTools MCP et yield ses outils.

    Pattern OBLIGATOIRE : ToolCollection.from_mcp est un @contextmanager et la
    connexion MCP (thread + event loop) doit rester ouverte PENDANT que l'agent
    utilise les outils (cf. context7_tool.py pour le même pattern).

    Tolérance aux pannes :
      - params None (CHROME_DEVTOOLS_ENABLED=0 ou mcp absent) → yield [] silencieusement
      - connexion réseau/lancement Chrome échouée → yield [] + warning

    Usage typique :
        with chrome_devtools_tools() as cdt:
            agent = CodeAgent(tools=[write_file, read_file, *cdt], ...)
            agent.run(prompt)
    """
    params = _build_params()
    if params is None:
        # Désactivé (opt-out ou mcp non installé). Mode silencieux comme Context7.
        yield []
        return

    try:
        with ToolCollection.from_mcp(params, trust_remote_code=True) as tool_collection:
            # Filtrage strict (anti context-overflow) : on ne garde que l'essentiel
            allowed = {"navigate_page", "take_screenshot", "take_snapshot", "list_console_messages", "evaluate_script"}
            tools = [t for t in tool_collection.tools if t.name in allowed]
            logger.debug("Chrome DevTools connecté : %d outil(s) (filtrés sur %d).", len(tools), len(list(tool_collection.tools)))
            yield tools
    except Exception as e:
        # Connexion échouée (npx absent, Chrome non trouvé, port occupé...). On
        # prévient mais on ne fait pas planter le nœud : le Coder/tester tourne
        # sans preview visuel, comme avant la feature F-45.
        logger.warning("Chrome DevTools indisponible (%s) — poursuite sans preview.", e)
        yield []
