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

F-163 (pool navigateur run-scoped) : ce context manager est une FAÇADE du pool —
quand le pool est engagé, le serveur se connecte au Chrome partagé du run
(--browserUrl) au lieu de lancer le sien ; le lease garantit un Chrome sain
(health-check + respawn) pendant toute la durée du consommateur.
"""

import logging
from contextlib import contextmanager
from typing import Any, Optional

logger = logging.getLogger(__name__)


# Doc de base des outils Chrome DevTools, partagée entre le Coder
# (nodes.py::_DEVTOOLS_TOOLS_DOC) et le WebTester (web_tester.py::devtools_hint).
# F-72 (Prompt Offloading) : single source of truth pour les signatures communes
# + l'avertissement anti-IIFE CRITIQUE (le point de sécurité d'exécution le plus
# important — une IIFE fait crasher le CDP). Chaque rôle ajoute ses spécificités
# via concatenation (Coder : note syntax check / pas Lighthouse ; Tester :
# take_snapshot/click/fill/take_screenshot + filePath/visual bug/python builtins).
DEVTOOLS_BASE_DOC = """\
- `navigate_page(url=...)` : ouvre la page dans Chrome (OBLIGATOIRE pour la navigation initiale ; utilise un file:/// absolu pour un fichier local).
- `list_console_messages()` : erreurs JS de la console (avec source maps). ⚠️ Renvoie une chaîne Markdown directement affichable — ne fais NI boucle `for` NI `.get()` : utilise simplement `print(list_console_messages())`.
- `evaluate_script(function="...")` : exécute du JS dans la page (lecture DOM, assertions fonctionnelles).
  ⚠️ ATTENTION : Les arguments nommés sont OBLIGATOIRES pour tous ces outils (ex: `evaluate_script(function="...")`).
  ⚠️ CRITIQUE (anti-IIFE) : N'utilise JAMAIS 'await' au premier niveau (top-level await). Le MCP chrome-devtools attend une DÉCLARATION de fonction (et l'invoque lui-même). Tu dois fournir une fonction asynchrone NON invoquée. Correct : `async () => { await ... }`. Ne JAMAIS utiliser une IIFE comme `(() => { await ... })()`, sinon le CDP crashera avec l'erreur 'await is only valid in async functions'."""


def _build_params(browser_url: Optional[str] = None) -> Optional[Any]:
    """Construit les params MCP Chrome DevTools, ou None si désactivé/indisponible.

    Délègue à agent_server.mcp.build_chrome_devtools_params (source unique de
    vérité pour la commande npx/options). On ne duplique pas la config ici.
    ``browser_url`` (F-163) : URL du Chrome partagé du pool navigateur, None en
    mode historique (le serveur lance son propre Chrome --isolated).
    """
    from agent_server.mcp import build_chrome_devtools_params

    return build_chrome_devtools_params(browser_url=browser_url)


@contextmanager
def chrome_devtools_tools():
    """Context manager : ouvre une connexion Chrome DevTools MCP et yield ses outils.

    Pattern OBLIGATOIRE : ToolCollection.from_mcp est un @contextmanager et la
    connexion MCP (thread + event loop) doit rester ouverte PENDANT que l'agent
    utilise les outils (cf. context7_tool.py pour le même pattern).

    F-163 (pool navigateur run-scoped) : quand le pool est engagé (config +
    hors pytest), un LEASE garantit un Chrome partagé sain pendant le
    consommateur et le serveur s'y connecte (--browserUrl) au lieu de lancer
    le sien — Chrome chaud, aucun arbre à fuir. Pool indisponible/désactivé →
    comportement historique exact.

    Tolérance aux pannes :
      - params None (CHROME_DEVTOOLS_ENABLED=0 ou mcp absent) → yield [] silencieusement
      - connexion réseau/lancement Chrome échouée → yield [] + warning

    Usage typique :
        with chrome_devtools_tools() as cdt:
            agent = CodeAgent(tools=[write_file, read_file, *cdt], ...)
            agent.run(prompt)
    """
    from contextlib import ExitStack

    from . import browser_pool as _bp
    from .config import settings as _settings
    from .mcp_connect import open_mcp_with_timeout

    with ExitStack() as _stack:
        browser_url = None
        if _bp.pool_should_engage(_settings):
            # Lease refcounté : spawn/health-check Chrome, URL ou None (repli).
            browser_url = _stack.enter_context(
                _bp.get_browser_pool().lease("chrome_devtools_tools")
            )
        if browser_url:
            params = _build_params(browser_url=browser_url)
        else:
            # Appel SANS kwargs : compat avec les lambdas de test existantes.
            params = _build_params()
        if params is None:
            # Désactivé (opt-out ou mcp non installé). Mode silencieux comme Context7.
            yield []
            return

        # F-104 (crush) : attente de connexion BORNÉE par serveur — un npx pendu
        # (téléchargement à froid de chrome-devtools-mcp@latest) ne fige plus le
        # nœud 30 s : timeout → dégradation (yield []), le run continue.
        try:
            cm, tools = open_mcp_with_timeout(
                params, _settings.chrome_devtools_connect_timeout_s, "chrome-devtools"
            )
        except Exception as e:
            # Connexion échouée (npx absent, Chrome non trouvé, port occupé...). On
            # prévient mais on ne fait pas planter le nœud : le Coder/tester tourne
            # sans preview visuel, comme avant la feature F-45.
            logger.warning("Chrome DevTools indisponible (%s) — poursuite sans preview.", e)
            yield []
            return
        if cm is None:
            yield []
            return
        try:
            yield tools
        except BaseException as be:
            cm.__exit__(type(be), be, be.__traceback__)
            raise
        else:
            cm.__exit__(None, None, None)
