"""Schémas Pydantic pour l'API web (requêtes/réponses + événements de streaming)."""

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    """Requête pour lancer un run d'agent."""
    prompt: str = Field(..., description="Le prompt/question pour l'agent")
    mode: Literal["chat", "graph", "exploration"] = Field(
        "chat", description="Mode d'exécution : chat (agent outillé), graph (Fan-out/Adversaire), exploration (loop-until-dry)"
    )
    model_id: Optional[str] = Field(None, description="Modèle à utiliser (défaut: settings.reasoning_model_id)")
    tool_names: Optional[List[str]] = Field(
        None, description="Noms des outils à inclure (défaut: tous). Ignoré en mode graph."
    )
    skill_name: str = Field("coding", description="Skill dont charger les instructions (mode chat)")
    max_steps: int = Field(20, description="Nombre max d'étapes de l'agent (mode chat)")


class RunResponse(BaseModel):
    """Réponse immédiate au lancement d'un run (le résultat vient via WebSocket)."""
    run_id: str
    status: Literal["started"] = "started"


# ==========================================
# Événements de streaming (WebSocket)
# ==========================================

class RunEvent(BaseModel):
    """Un événement du flux d'exécution (pushé via WebSocket à l'UI)."""
    type: Literal["step", "tool_call", "observation", "token_usage", "final", "error", "status"]
    run_id: str
    data: dict = Field(default_factory=dict)


class StepData(BaseModel):
    """Données d'un événement 'step' (une étape de l'agent)."""
    step_number: int
    tool_calls: Optional[List[dict]] = None  # [{name, arguments}]
    observations: Optional[str] = None  # sortie de l'outil
    duration_s: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Diagnostic du serveur (endpoint /health)."""
    status: Literal["ok", "degraded"]
    local_llm_reachable: bool
    models_configured: dict
    tools_available: List[str]
    skills_available: List[dict]
    mcp_servers: List[dict]


class KgSnapshot(BaseModel):
    """Snapshot du Knowledge Graph (endpoint /api/kg)."""
    entities: List[dict]
    claims: List[dict]
    provenance: List[dict]
    edges: List[dict]
