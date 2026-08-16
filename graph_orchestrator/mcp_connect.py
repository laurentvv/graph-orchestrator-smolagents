"""Init MCP bornée — un serveur pendu ne bloque jamais le run (F-104, P8).

Portage du pattern **crush** (internal/agent/coordinator.go) : l'init MCP
n'est JAMAIS bloquante en interactif — la palette d'outils est construite sur
l'état courant, et un serveur lent/pendu ne stoppe pas le run. Écho Claude
Code v2.1.232 ``WaitForMcpServers`` (attendre la connexion au lieu
d'échouer... mais borné).

Problème initial : ``ToolCollection.from_mcp`` délègue à mcpadapt dont le
``connect_timeout`` par défaut est de 30 s — 30 s pendant lesquelles le thread
appelant ET l'event loop async (``execute_coder_node`` entre directement dans
le context manager) restent figés, pour FINIR par une exception. Un npx qui
télécharge son paquet à froid (chrome-devtools-mcp@latest, puppeteer) peut
facilement dépasser.

``open_mcp_with_timeout`` borne l'attente :
- connexion dans le délai → ``(cm, tools)`` — le CM est DÉJÀ ouvert, l'appelant
  doit le fermer via ``cm.__exit__(...)`` (pas de re-``with`` : un
  @contextmanager ne se consomme qu'une fois) ;
- timeout → ``(None, [])`` — dégradation gracieuse du nœud (le run continue
  sans ces outils), le thread de connexion est ABANDONNÉ en daemon (même
  compromis zombie-thread que le timeout de ``run_with_retry``, nodes.py) ;
- erreur d'init → l'exception est relancée (l'appelant gère sa dégradation).

100 % Python natif, 0 LLM. Timeout PAR SERVEUR (crush) : chaque module passe
son propre setting (chrome-devtools / context7 / puppeteer).
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional, Tuple

from smolagents import ToolCollection

logger = logging.getLogger(__name__)


def open_mcp_with_timeout(
    params: Any,
    timeout_s: float,
    server_name: str = "mcp",
) -> Tuple[Optional[Any], list]:
    """Ouvre une connexion MCP ``ToolCollection.from_mcp`` avec attente bornée.

    Retourne ``(cm, tools)`` si la connexion est établie dans le délai,
    ``(None, [])`` au timeout (serveur lent/pendu — dégradation), et RELÈVE
    l'exception d'initialisation sinon (npx absent, Chrome introuvable...).

    Le context manager retourné est déjà entré : le fermer par un appel
    direct ``cm.__exit__(...)`` (un ``with cm`` échouerait — déjà consommé).
    """
    cm = ToolCollection.from_mcp(params, trust_remote_code=True)

    box: dict = {}
    done = threading.Event()

    def _connect() -> None:
        try:
            entered = cm.__enter__()
            box["tools"] = list(entered.tools)
        except BaseException as e:  # noqa: BLE001 — retransmis au caller
            box["error"] = e
        finally:
            done.set()

    # Thread daemon : un thread bloqué dans la connexion ne doit JAMAIS
    # empêcher l'interpréteur de s'arrêter (fin de run / fin de pytest).
    worker = threading.Thread(
        target=_connect, daemon=True, name=f"mcp-connect-{server_name}"
    )
    worker.start()

    if not done.wait(max(float(timeout_s), 0.1)):
        logger.warning(
            "[%s] init MCP > %.1fs (F-104, crush : non bloquant) — run sans ces outils",
            server_name, float(timeout_s),
        )
        return None, []

    if "error" in box:
        raise box["error"]
    return cm, box.get("tools") or []
