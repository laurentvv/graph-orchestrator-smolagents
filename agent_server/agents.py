"""Builder d'agents outillés (Phase B).

Assemble un CodeAgent smolagents avec :
  - les outils demandés (depuis le registry TOOLS)
  - les outils MCP (passés en paramètre depuis le lifespan)
  - les instructions d'un skill (injectées comme `instructions`)
  - un modèle (depuis la config graph_orchestrator)

Le CodeAgent est préféré au ToolCallingAgent pour le codage : il génère et exécute
du Python nativement (moteur d'exécution intégré), en plus des tools.
"""

from typing import List, Optional

from smolagents import CodeAgent, OpenAIServerModel, Tool

from graph_orchestrator.config import Settings

from .tools import get_tools, list_tool_names
from .skills import get_skill_instructions, list_skills


def build_model(settings: Settings, model_id: Optional[str] = None) -> OpenAIServerModel:
    """Construit le modèle LLM depuis la config (serveur local par défaut)."""
    return OpenAIServerModel(
        model_id=model_id or settings.reasoning_model_id,
        api_base=settings.local_api_base,
        api_key=settings.local_api_key,
        max_tokens=settings.reasoning_max_tokens,
    )


def build_coding_agent(
    settings: Settings,
    tool_names: Optional[List[str]] = None,
    mcp_tools: Optional[List[Tool]] = None,
    skill_name: str = "coding",
    model_id: Optional[str] = None,
    max_steps: int = 20,
) -> CodeAgent:
    """Construit un CodeAgent outillé pour le codage.

    Args:
        tool_names: noms des outils natifs à inclure (None = tous)
        mcp_tools: outils MCP additionnels (depuis le lifespan)
        skill_name: nom du skill dont charger les instructions
        model_id: override du modèle (sinon settings.reasoning_model_id)
        max_steps: nombre max d'étapes de l'agent
    """
    model = build_model(settings, model_id)

    # Outils natifs (registry) + outils MCP
    tools = get_tools(tool_names)
    if mcp_tools:
        tools = tools + list(mcp_tools)

    # Instructions du skill (si demandé)
    instructions = get_skill_instructions(skill_name) or ""

    agent = CodeAgent(
        tools=tools,
        model=model,
        instructions=instructions,
        max_steps=max_steps,
        add_base_tools=False,  # on gère nous-mêmes le set d'outils
        name="coding_agent",
        description="Agent développeur outillé (Python/Node/Web/MCP) pour le codage.",
    )
    return agent


def list_available_tools() -> List[str]:
    """Liste les outils natifs disponibles (pour l'UI)."""
    return list_tool_names()


def list_available_skills() -> List[dict]:
    """Liste les skills disponibles (pour l'UI)."""
    return list_skills()
