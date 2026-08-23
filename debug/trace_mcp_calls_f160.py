"""Diagnostic F-160 : trace des appels MCP pendant un mini-run Coder pydantic.

Wrap fastmcp Client.call_tool (record global) puis exécute run_coder_pydantic
sur une petite tâche web — prouve que le 4B exerce les outils navigateur
(navigate_page, list_console_messages, helpers…) à travers le toolset pydantic.
"""

import asyncio
import os
import shutil
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv

load_dotenv()

OUT_DIR = "debug/coder_pydantic_out"
TASK = {
    "id": "ts-trace",
    "content": (
        "Crée une mini-page counter.html : un bouton +1 et un compteur affiché, "
        "HTML/CSS/JS inline vanilla, dark theme. Vérifie ensuite la page dans le "
        "navigateur (console) avant de conclure."
    ),
    "target_files": ["counter.html"],
    "strategy": "simple",
    "sections": [],
    "skills": [],
    "iteration": 1,
}

CALLS = Counter()


async def main() -> int:
    from fastmcp.client.client import Client as FastMCPClient

    orig = FastMCPClient.call_tool

    async def rec(self, *a, **kw):
        name = a[0] if a else kw.get("name", "?")
        CALLS[name] += 1
        return await orig(self, *a, **kw)

    FastMCPClient.call_tool = rec

    from graph_orchestrator.config import settings
    from graph_orchestrator.coder_pydantic import run_coder_pydantic

    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    orig_cwd = os.getcwd()
    os.chdir(OUT_DIR)
    try:
        t0 = time.time()
        out, metrics = await asyncio.wait_for(run_coder_pydantic(TASK, settings), timeout=900)
        print(f"\nrun {time.time()-t0:.0f}s | output={'OK' if out else 'None'} | status={getattr(out, 'status', '-')}")
        if metrics:
            print(f"tokens {metrics.input_tokens} in / {metrics.output_tokens} out")
    except Exception as exc:  # noqa: BLE001
        print(f"run exception: {type(exc).__name__}: {exc}")
    finally:
        os.chdir(orig_cwd)

    print("\n=== APPELS MCP ENREGISTRÉS (Client.call_tool) ===")
    for name, n in CALLS.most_common():
        print(f"  {n:3d}× {name}")
    if not CALLS:
        print("  (aucun — le modèle n'a pas utilisé les outils MCP)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
