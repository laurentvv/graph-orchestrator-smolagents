"""Serveur FastAPI : expose les agents outillés avec streaming WebSocket live.

Architecture :
  - lifespan : connecte MCP (Context7 + crawl4ai), init KG. Cleanup au shutdown.
  - POST /api/run : lance un run en arrière-plan, retourne un run_id.
  - WS /ws/run/{run_id} : streame les événements en live (step_callbacks → queue → WS).
  - GET /api/kg : snapshot du Knowledge Graph.
  - GET /api/health : diagnostics.
  - GET /api/tools, /api/skills : listes pour l'UI.

Le streaming : on attache un step_callback à l'agent qui pousse chaque ActionStep
dans une asyncio.Queue. Le handler WebSocket lit la queue et envoie les événements.
"""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from typing import Dict, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from rich.console import Console

from graph_orchestrator.config import Settings, settings as default_settings
from graph_orchestrator.knowledge_graph import KnowledgeGraph

from .agents import build_coding_agent, list_available_tools, list_available_skills
from .events import action_step_to_event
from .mcp import connect_all_mcp, list_mcp_servers_status
from .schemas import (
    HealthResponse,
    KgSnapshot,
    RunEvent,
    RunRequest,
    RunResponse,
    StepData,
)

console = Console()

# État global de l'app (rempli dans le lifespan)
_app_state: dict = {
    "mcp_tools": [],
    "mcp_context": None,
    "kg": None,
    "settings": default_settings,
    "ollama_reachable": False,
}

# Runs en cours : {run_id: {"queue": asyncio.Queue, "task": asyncio.Task}}
_runs: Dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise MCP + KG au démarrage, cleanup au shutdown."""
    settings: Settings = _app_state["settings"]

    # --- Knowledge Graph ---
    _app_state["kg"] = KnowledgeGraph(settings.kg_path)
    console.print(f"[green][app] Knowledge Graph : {settings.kg_path}[/green]")

    # --- MCP (tolérance aux pannes) ---
    try:
        with connect_all_mcp() as mcp_tools:
            _app_state["mcp_tools"] = mcp_tools
            console.print(f"[green][app] {len(mcp_tools)} outil(s) MCP chargé(s)[/green]")
            _app_state["ollama_reachable"] = _check_ollama(settings)
            yield
    finally:
        if _app_state["kg"]:
            _app_state["kg"].close()
        console.print("[yellow][app] Shutdown complete[/yellow]")


def _check_ollama(settings: Settings) -> bool:
    """Vérifie si Ollama répond (non bloquant, timeout court)."""
    import urllib.request
    base = settings.ollama_api_base.rstrip("/").removesuffix("/v1")
    try:
        req = urllib.request.urlopen(f"{base}/api/tags", timeout=2)
        return req.status == 200
    except Exception:
        return False


app = FastAPI(
    title="Graph Orchestrator — Agent Server",
    description="Agents outillés (Python/Node/Web/MCP) avec streaming live",
    version="0.5.0",
    lifespan=lifespan,
)

# CORS pour le frontend React (dev server sur autre port)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev local ; restreindre en prod
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# Routes utilitaires (UI)
# ==========================================

@app.get("/api/health")
async def health() -> HealthResponse:
    settings: Settings = _app_state["settings"]
    return HealthResponse(
        status="ok" if _app_state["ollama_reachable"] else "degraded",
        ollama_reachable=_app_state["ollama_reachable"],
        models_configured={
            "fast": settings.fast_model_id,
            "reasoning": settings.reasoning_model_id,
        },
        tools_available=list_available_tools(),
        skills_available=list_available_skills(),
        mcp_servers=list_mcp_servers_status(),
    )


@app.get("/api/tools")
async def get_tools_list():
    return {"tools": list_available_tools()}


@app.get("/api/skills")
async def get_skills_list():
    return {"skills": list_available_skills()}


@app.get("/api/kg", response_model=KgSnapshot)
async def get_kg():
    kg: KnowledgeGraph = _app_state["kg"]
    if kg is None:
        return KgSnapshot(entities=[], claims=[], provenance=[], edges=[])
    return KgSnapshot(**kg.dump())


# ==========================================
# Lancement d'un run + streaming WebSocket
# ==========================================

@app.post("/api/run", response_model=RunResponse)
async def start_run(req: RunRequest) -> RunResponse:
    """Lance un run d'agent en arrière-plan. Le résultat vient via /ws/run/{run_id}."""
    run_id = str(uuid.uuid4())[:8]
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(_execute_run(run_id, req, queue))
    _runs[run_id] = {"queue": queue, "task": task}

    return RunResponse(run_id=run_id)


@app.post("/api/cancel/{run_id}")
async def cancel_run(run_id: str):
    """Annule un run en cours (tue la tâche backend + notifie le WS)."""
    entry = _runs.get(run_id)
    if entry is None:
        return {"cancelled": False, "reason": "Run inconnu ou déjà terminé"}
    task: asyncio.Task = entry["task"]
    queue: asyncio.Queue = entry["queue"]
    # Notifie le WS que c'est annulé
    await queue.put(RunEvent(type="status", run_id=run_id, data={"message": "Annulé par l'utilisateur.", "done": True}))
    # Tue la tâche backend
    task.cancel()
    return {"cancelled": True}


async def _execute_run(run_id: str, req: RunRequest, queue: asyncio.Queue) -> None:
    """Exécute le run et pousse les événements dans la queue."""
    settings: Settings = _app_state["settings"]
    mcp_tools: List = _app_state["mcp_tools"]

    async def push(event_type: str, data: dict):
        await queue.put(RunEvent(type=event_type, run_id=run_id, data=data))

    try:
        await push("status", {"message": "Initialisation..."})

        # Capture la loop AVANT l'exécution (le callback tourne dans un thread smolagents
        # où asyncio.get_event_loop() ne retourne PAS la loop principale).
        main_loop = asyncio.get_running_loop()

        # Callback qui pousse chaque step dans la queue
        def on_step(memory_step, agent):
            data = action_step_to_event(memory_step)
            # push synchrone → schedule sur la loop principale capturée
            try:
                asyncio.run_coroutine_threadsafe(push("step", data), main_loop)
            except RuntimeError:
                pass

        # Construction de l'agent selon le mode
        if req.mode == "chat":
            agent = build_coding_agent(
                settings=settings,
                tool_names=req.tool_names,
                mcp_tools=mcp_tools,
                skill_name=req.skill_name,
                model_id=req.model_id,
                max_steps=req.max_steps,
            )
            # smolagents CallbackRegistry.register(step_cls, callback) pour ActionStep
            from smolagents.memory import ActionStep
            try:
                agent.step_callbacks.register(ActionStep, on_step)
            except (TypeError, AttributeError):
                # Fallback : ancienne API (list)
                try:
                    agent.step_callbacks.callbacks.append(on_step)
                except Exception:
                    pass

            await push("status", {"message": f"Agent prêt : {len(agent.tools)} outil(s). Exécution..."})

            # Exécution (synchrone smolagents → déporté dans un thread)
            result = await asyncio.to_thread(
                agent.run, req.prompt, False  # stream=False (on stream via step_callback)
            )

            await push("final", {"output": str(result)[:10000]})

        elif req.mode in ("graph", "exploration"):
            await push("status", {"message": f"Mode {req.mode} : via graph_orchestrator..."})
            from graph_orchestrator.runner import run_graph_workflow
            from graph_orchestrator.workflows import run_exploration_workflow, ONE_SHOT_TASKS, EXPLORATION_SEED_TASKS

            # Construit les tâches à partir du prompt
            tasks = [{"id": "u1", "content": req.prompt}]

            if req.mode == "graph":
                final, metrics = await run_graph_workflow(tasks, settings)
            else:
                final, metrics = await run_exploration_workflow(
                    tasks or EXPLORATION_SEED_TASKS, settings
                )

            # Pousse les métriques et le résultat
            for m in metrics:
                await push("step", {
                    "step_number": 0,
                    "tool_calls": [{"name": m.node, "arguments": ""}],
                    "observations": f"{m.node} via {m.model}: {m.duration_s}s, {m.total_tokens} tokens",
                    "duration_s": m.duration_s,
                    "input_tokens": m.input_tokens,
                    "output_tokens": m.output_tokens,
                })

            if final:
                # Sérialise en JSON string (final est un objet Pydantic FinalSynthesis)
                import json as _json
                await push("final", {"output": _json.dumps(final.model_dump(), ensure_ascii=False, indent=2)})
            else:
                await push("final", {"output": "(aucun résultat)"})

    except Exception as e:
        await push("error", {"message": str(e)[:500]})
    finally:
        await push("status", {"message": "Run terminé.", "done": True})
        # La queue reste accessible jusqu'à ce que le WS la lise ou timeout


# ==========================================
# WebSocket : streame les événements d'un run
# ==========================================

@app.websocket("/ws/run/{run_id}")
async def ws_run(websocket: WebSocket, run_id: str):
    """Streame en live les événements d'un run via WebSocket."""
    await websocket.accept()

    entry = _runs.get(run_id)
    if entry is None:
        await websocket.send_text(json.dumps({"type": "error", "run_id": run_id, "data": {"message": "Run inconnu"}}))
        await websocket.close()
        return

    queue: asyncio.Queue = entry["queue"]

    try:
        while True:
            try:
                # Attend le prochain événement (timeout pour permettre le heartbeat)
                event: RunEvent = await asyncio.wait_for(queue.get(), timeout=120)
                await websocket.send_text(event.model_dump_json())

                # Si c'est l'événement final (done), on ferme
                if event.type == "status" and event.data.get("done"):
                    break
            except asyncio.TimeoutError:
                # Heartbeat : garde la connexion vivante
                await websocket.send_text(json.dumps({"type": "status", "run_id": run_id, "data": {"heartbeat": True}}))
    except WebSocketDisconnect:
        pass  # client déconnecté
    finally:
        _runs.pop(run_id, None)


# ==========================================
# Point d'entrée
# ==========================================

def main():
    """Lance le serveur avec uvicorn."""
    import uvicorn
    uvicorn.run("agent_server.app:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
