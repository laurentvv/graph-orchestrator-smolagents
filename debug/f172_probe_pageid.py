"""Validation live F-172 — défaut pageId sur le bridge (chrome-devtools-mcp 1.8.0).

Deux phases :
  1. SONDAGE : schémas requis, erreur exacte sans pageId, format list_pages,
     piège pageId=0 (diagnostic initial, conservé pour post-mortem).
  2. VALIDATION DU FIX : les MÊMES appels à travers le fallback de production
     ``coder_pydantic_mcp.call_tool_with_page_id_fallback`` + le spawn ÉPINGLÉ
     ``chrome-devtools-mcp@1.8.0`` (args construits par agent_server.mcp comme
     en prod) — evaluate_script et navigate_page sans pageId doivent RÉUSSIR
     avec injection transparente.

Spawn jetable (headless + isolated → ne touche PAS le Chrome de l'utilisateur).
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from graph_orchestrator.coder_pydantic_mcp import call_tool_with_page_id_fallback

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s : %(message)s")


async def probe_raw(client: Client) -> None:
    print("\n========== PHASE 1 : SONDAGE (comportement serveur brut) ==========")
    tools = await client.list_tools()
    requiring = sorted(
        t.name for t in tools if "pageId" in ((t.inputSchema or {}).get("required") or [])
    )
    print(f"Outils exigeant pageId : {len(requiring)} → {requiring}")

    print("\n-- list_pages (format brut) --")
    res = await client.call_tool("list_pages", {})
    for block in res.content:
        print(repr(getattr(block, "text", block))[:400])

    print("\n-- navigate_page SANS pageId --")
    try:
        await client.call_tool("navigate_page", {"url": "data:text/html,<h1>F172</h1>"})
        print("OK inattendu (pas d'erreur)")
    except Exception as exc:  # noqa: BLE001
        print(f"ERREUR {type(exc).__name__}: {exc}")

    print("\n-- navigate_page AVEC pageId=0 (hallucination typique) --")
    try:
        await client.call_tool(
            "navigate_page", {"url": "data:text/html,<h1>F172</h1>", "pageId": 0}
        )
        print("OK inattendu (pas d'erreur)")
    except Exception as exc:  # noqa: BLE001
        print(f"ERREUR {type(exc).__name__}: {exc}")


async def probe_fix(client: Client) -> int:
    print("\n========== PHASE 2 : VALIDATION DU FIX (fallback production) ==========")
    call = client.call_tool

    url = "data:text/html,<h1 id='x'>F172</h1><script>document.title='f172-ok'</script>"

    print("\n-- navigate_page SANS pageId via fallback --")
    res = await call_tool_with_page_id_fallback(call, "navigate_page", {"url": url})
    print("OK :", repr(getattr(res.content[0], "text", res))[:120])

    print("\n-- evaluate_script SANS pageId via fallback --")
    res = await call_tool_with_page_id_fallback(
        call, "evaluate_script", {"function": "() => document.title"}
    )
    text = getattr(res.content[0], "text", res)
    print("OK :", repr(text)[:200])
    assert "f172-ok" in str(text), "le script n'a pas tourné sur la bonne page"

    print("\n-- evaluate_script AVEC pageId=0 via fallback (remplacement) --")
    res = await call_tool_with_page_id_fallback(
        call, "evaluate_script", {"function": "() => 6 * 7", "pageId": 0}
    )
    text = getattr(res.content[0], "text", res)
    print("OK :", repr(text)[:200])
    assert "42" in str(text), "pageId=0 n'a pas été remplacé par la page sélectionnée"

    print("\n[F-172] VALIDATION LIVE : les 3 appels sauvés, page ciblée correcte.")
    return 0


async def main() -> int:
    # Spawn exact de la prod : args construits par agent_server.mcp (version
    # épinglée 1.8.0), headless + isolated pour un probe jetable.
    os.environ["CHROME_DEVTOOLS_ENABLED"] = "1"
    os.environ["CHROME_DEVTOOLS_HEADLESS"] = "1"
    from agent_server.mcp import build_chrome_devtools_params

    params = build_chrome_devtools_params()
    assert params is not None, "CHROME_DEVTOOLS_ENABLED doit être à 1"
    print(f"Commande spawn : {params.command} {' '.join(params.args)}")

    transport = StdioTransport(command=params.command, args=list(params.args), env=dict(params.env or {}))
    async with Client(transport) as client:
        await probe_raw(client)
        return await probe_fix(client)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
