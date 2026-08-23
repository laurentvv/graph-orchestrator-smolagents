"""Diagnostic F-160 : tool_choice vs grammaire llama-server (autonome).

Construit l'ensemble d'outils EXACT du Coder pydantic (chrome-devtools MCP réel
+ 12 helpers + customs + FileSystem + final_result), puis rejoue des requêtes
minimales contre un llama-server spawné en variant `tool_choice` et la taille
de l'ensemble. Matrice mesurée le 2026-08-23 : 62 outils + `required` → 400
« Failed to initialize samplers: failed to parse grammar » ; 62 + auto/absent
→ OK ; 45 + required → OK (seuil de taille entre 46 et 62 — d'où le
tool_choice='auto' conditionnel de build_coder_agent quand des toolsets MCP
sont attachés).

Usage : uv run python debug/replay_request_f160.py
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv

load_dotenv()


async def _collect_tools() -> list:
    """Assemble les paramètres d'outils comme la requête production."""
    from agent_server.mcp import build_chrome_devtools_params
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    p = build_chrome_devtools_params()
    out = []
    if p is not None:
        tr = StdioTransport(command=p.command, args=list(p.args), env=dict(p.env))
        async with Client(tr) as c:
            tools = await c.list_tools()
            out += [
                {"type": "function", "function": {"name": t.name, "description": t.description or "d", "parameters": dict(t.inputSchema)}}
                for t in tools
            ]
    return out


async def main():
    import httpx

    from graph_orchestrator.config import load_settings
    from graph_orchestrator.llama_server import model_lifecycle

    settings = load_settings()
    devtools = await _collect_tools()
    n_dev = len(devtools)
    print(f"[*] {n_dev} outils DevTools collectés (chrome-devtools-mcp réel).")

    from graph_orchestrator.coder_pydantic import build_coder_custom_tools
    from graph_orchestrator.coder_pydantic_mcp import build_dom_helper_toolset
    from graph_orchestrator.models import CoderOutput
    from pydantic_ai.toolsets import FunctionToolset

    class _Noop:
        async def call_tool(self, name, args):
            return ""

    helpers = [
        {"type": "function", "function": {"name": n, "description": t.description or "d", "parameters": t.tool_def.parameters_json_schema}}
        for n, t in build_dom_helper_toolset(_Noop()).tools.items()
    ]
    customs = []
    cts = FunctionToolset(list(build_coder_custom_tools()))
    for n, t in cts.tools.items():
        customs.append({"type": "function", "function": {"name": n, "description": t.description or "d", "parameters": t.tool_def.parameters_json_schema}})
    final = {"type": "function", "function": {"name": "final_result", "description": "final output", "parameters": CoderOutput.model_json_schema()}}

    base_tools = customs + devtools + helpers + [final]

    with model_lifecycle(settings.fast_spec) as srv:
        base = srv.api_base

        async def probe(label, tools, tool_choice="__omit__"):
            body = {
                "model": "default",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
                "tools": tools,
            }
            if tool_choice != "__omit__":
                body["tool_choice"] = tool_choice
            async with httpx.AsyncClient(timeout=120) as hc:
                r = await hc.post(f"{base}/chat/completions", json=body)
            print(("OK  " if r.status_code == 200 else f"{r.status_code} "), label)
            return r.status_code == 200

        await probe(f"tout ({len(base_tools)} outils) + required", base_tools, "required")
        await probe(f"tout ({len(base_tools)} outils) + auto", base_tools, "auto")
        await probe(f"tout ({len(base_tools)} outils) sans tool_choice", base_tools)
        for n in (30, 45, 55):
            if n < len(base_tools):
                await probe(f"{n} outils + required", base_tools[:n], "required")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
