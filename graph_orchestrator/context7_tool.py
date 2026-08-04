"""Intégration Context7 (doc de libs à jour) pour les nœuds du coding workflow.

Context7 expose 2 outils via le transport MCP streamable-http :
  - resolve_library_id(query, libraryName) → Context7-compatible library ID
  - query_docs(libraryId, query)           → documentation + exemples à jour

Antidote à l'hallucination d'API : plutôt que de se fier à la mémoire du modèle
(souvent obsolète), on consulte la doc officielle à la demande.

Deux modes d'usage dans le coding workflow :
  1. AGENT (Coder / web-tester, smolagents) : on leur injecte les @tool MCP via
     le context manager context7_tools(). L'agent décide QUAND chercher (cf. skill
     context7-research). Le `with` maintient la connexion MCP ouverte pendant tout
     le run de l'agent (sinon les outils deviendraient inertes).
  2. PRÉ-FETCH (Architect, DSPy sans boucle d'outils) : fetch_context7_brief()
     consulte Context7 en amont et renvoie un résumé compact injecté dans le prompt.

Robustesse : si CONTEXT7_API_KEY est absente ou la connexion échoue, TOUT se
dégrade gracieusement — context7_tools() yield [], fetch_context7_brief() → "".
Aucun nœud ne dépend de Context7 pour fonctionner (backward-compatible).
"""

import logging
import re
from contextlib import contextmanager
from typing import List, Optional

from smolagents import Tool, ToolCollection

# Réutilise la config MCP existante (URL, transport, header d'auth).
# Import local pour éviter un cycle d'import au chargement du package.
logger = logging.getLogger(__name__)


def _build_params() -> Optional[dict]:
    """Construit les params MCP Context7, ou None si pas de CONTEXT7_API_KEY.

    Délègue à agent_server.mcp.build_context7_params (source unique de vérité
    pour l'URL/transport/header). On ne duplique pas la config ici.
    """
    from agent_server.mcp import build_context7_params
    return build_context7_params()


@contextmanager
def context7_tools():
    """Context manager : ouvre une connexion Context7 et yield ses outils MCP.

    Pattern OBLIGATOIRE : ToolCollection.from_mcp est un @contextmanager et la
    connexion MCP (thread + event loop) doit rester ouverte PENDANT que l'agent
    utilise les outils. Si on ferme trop tôt, les tools deviennent inertes. Si on
    ne ferme pas proprement, on obtient "Cannot close a running event loop".

    Tolérance aux pannes (pattern repris de agent_server/mcp.connect_mcp_server) :
      - params None (pas de clé) → yield [] silencieusement
      - connexion réseau échouée → yield [] + warning (l'agent tourne sans doc)

    Usage typique :
        with context7_tools() as c7:
            agent = ToolCallingAgent(tools=[read_file, write_file, *c7], ...)
            agent.run(prompt)
    """
    params = _build_params()
    if params is None:
        # Pas de clé API : Context7 désactivé. Ce n'est pas une erreur — c'est le
        # mode par défaut en l'absence de configuration. On reste silencieux.
        yield []
        return

    try:
        with ToolCollection.from_mcp(params, trust_remote_code=True) as tool_collection:
            tools = list(tool_collection.tools)
            logger.debug("Context7 connecté : %d outil(s).", len(tools))
            yield tools
    except Exception as e:
        # Connexion échouée (réseau, serveur down, timeout). On prévient mais on
        # ne fait pas planter le nœud : le Coder/tester tourne sans doc.
        logger.warning("Context7 indisponible (%s) — poursuite sans doc.", e)
        yield []


def fetch_context7_brief(query: str, top_k: int = 3) -> str:
    """Pré-fetch un résumé doc contextuel pour l'Architect (nœud DSPy sans outils).

    Resolve la lib la plus pertinente pour `query`, puis récupère sa doc et la
    condense en un bref injectable dans le prompt de planification. Utilisé en
    amont du ChainOfThought de l'Architect qui ne peut pas appeler d'outils.

    Args:
        query: Question ou description de tâche (ex: contenu de tasks.json).
        top_k: Nombre de points de doc à garder dans le résumé.

    Returns:
        Un résumé doc compact préfixé d'un titre, OU "" si Context7 indisponible,
        non configuré, ou si aucune lib pertinente n'a été trouvée. Jamais d'exception.
    """
    params = _build_params()
    if params is None:
        return ""

    try:
        with ToolCollection.from_mcp(params, trust_remote_code=True) as tool_collection:
            tools_by_name = {t.name: t for t in tool_collection.tools}
            resolver = tools_by_name.get("resolve_library_id")
            doc_tool = tools_by_name.get("query_docs")
            if resolver is None or doc_tool is None:
                # Noms d'outils inattendus (API Context7 a changé ?). On ne devine pas.
                logger.warning("Context7 : outils attendus (resolve_library_id/query_docs) absents.")
                return ""

            # 1) Resolve : trouve la lib la plus pertinente pour cette tâche.
            # On ne passe que `query` (le ranking se fait sur la pertinence vs la
            # question). `libraryName` est omis : une chaîne vide pouvait être
            # interprétée différemment d'un paramètre absent par le serveur MCP
            # (Kilo review). On ne devine pas un nom de lib — on laisse Context7
            # proposer les candidats les plus pertinents.
            resolved = resolver(query=query, libraryName="")
            if not resolved:
                return ""

            # La réponse de resolve_library_id est un texte (JSON ou formatté).
            # On en extrait le premier libraryId candidat (format /org/project).
            match = re.search(r"(/\S+?/\S+?)(?:\s|$|,|\"|\n|`)", str(resolved))
            if not match:
                # Rien qui ressemble à un libraryId : on abandonne proprement.
                return ""
            library_id = match.group(1)

            # 2) Query-docs : récupère la doc de la lib pour cette tâche.
            docs = doc_tool(libraryId=library_id, query=query[:300])
            if not docs:
                return ""

            # 3) Condense : on garde le début (head), borné en caractères pour ne
            # pas saturer le contexte de l'Architect. On retire le superflu.
            brief = str(docs).strip()
            max_chars = 1500
            if len(brief) > max_chars:
                brief = brief[:max_chars].rsplit("\n", 1)[0] + "\n[...]"

            return (
                f"## 📚 Documentation à jour (Context7) — lib {library_id}\n"
                f"{brief}\n"
            )
    except Exception as e:
        # Timeout réseau, API down, parsing inattendu : on ne plante jamais
        # l'Architect. Le brief vide = l'Architect planifie sans doc, comme avant.
        logger.warning("fetch_context7_brief : échec (%s) — brief vide.", e)
        return ""
