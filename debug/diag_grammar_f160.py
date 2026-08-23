"""Diagnostic F-160 : identifier le schéma d'outil qui casse le convertisseur
GBNF de llama-server (« Failed to initialize samplers: failed to parse grammar »).

Spawn le serveur FAST de production, envoie des /v1/chat/completions minimaux
avec UN outil à la fois (schémas MCP DevTools réels + helpers + variants
synthétiques $schema/exclusiveMinimum), affiche OK/400 par outil.
0 LLM generateur (max_tokens=1) — échec grammar = 400 immédiat.
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv

load_dotenv()


async def main() -> int:
    import httpx

    from agent_server.mcp import build_chrome_devtools_params
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport
    from graph_orchestrator.config import settings
    from graph_orchestrator.llama_server import model_lifecycle

    # 1. Schémas réels DevTools
    p = build_chrome_devtools_params()
    tr = StdioTransport(command=p.command, args=list(p.args), env=dict(p.env))
    async with Client(tr) as c:
        tools = await c.list_tools()
        devtools = [(t.name, dict(t.inputSchema)) for t in tools]

    # 2. Variants synthétiques pour isoler les mots-clés suspects
    synthetic = [
        ("syn_plain", {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}),
        ("syn_with_dollar_schema", {"$schema": "http://json-schema.org/draft-07/schema#",
                                    "type": "object", "properties": {"a": {"type": "string"}}}),
        ("syn_excl_min", {"type": "object", "properties": {
            "q": {"type": "number", "exclusiveMinimum": 0}}}),
        ("syn_null_default", {"type": "object", "properties": {
            "n": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": None}}}),
    ]

    candidates = synthetic + devtools

    spec = settings.fast_spec
    with model_lifecycle(spec) as srv:
        base = srv.api_base
        print(f"[*] serveur prêt : {base}")
        failures = []
        for name, schema in candidates:
            body = {
                "model": "default",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
                "tools": [{"type": "function", "function": {
                    "name": name, "description": "d", "parameters": schema}}],
            }
            try:
                async with httpx.AsyncClient(timeout=30) as hc:
                    r = await hc.post(f"{base}/chat/completions", json=body)
                ok = r.status_code == 200
                if not ok:
                    msg = r.json().get("error", {}).get("message", "")[:80]
                    failures.append(name)
                    print(f"[400] {name} : {msg}")
                else:
                    print(f"[OK ] {name}")
            except Exception as exc:  # noqa: BLE001
                failures.append(name)
                print(f"[ERR] {name} : {exc}")

        print("\n===", len(failures), "échecs :", failures)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
