"""Validation live du pool navigateur run-scoped (F-163) — convention F-89.

Appelle les VRAIES fonctions de production (0 mock, 0 LLM) :
  - browser_pool.configure_run / lease / shutdown_run ;
  - façade smolagents chrome_devtools_tools() (ToolCollection.from_mcp) ;
  - façade pydantic build_devtools_mcp_toolset(browser_url=...) (MCPToolset).

Contrôles :
  1. configure_run + lease → Chrome spawn UNE fois (health /json/version OK).
  2. Façade smolagents : navigate_page + evaluate_script sur une page témoin
     (le serveur npx se CONNECTE au Chrome du pool via --browserUrl).
  3. Re-lease après release → AUCUN respawn (Chrome chaud, spawn_count=1).
  4. Façade pydantic : le MÊME Chrome répond (evaluate via MCPToolset).
  5. shutdown_run → arbre tué (PID racine mort), user-data-dir purgé, zéro
     chrome.exe automation résiduel (baseline vs post-shutdown).

Usage : uv run python debug/run_browser_pool.py
Durée : ~20-40 s (spawn Chrome + 2 serveurs npx).
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph_orchestrator import browser_pool as bp  # noqa: E402
from graph_orchestrator.chrome_devtools_tool import chrome_devtools_tools  # noqa: E402
from graph_orchestrator.config import load_settings  # noqa: E402

RESULTS: list = []


def _check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def _chrome_pids() -> set:
    return bp._pids_by_name("chrome.exe")


def main() -> int:
    settings = load_settings()
    pool = bp.get_browser_pool()

    marker = f"F163-POOL-{random.randint(1000, 9999)}"
    tmpdir = tempfile.mkdtemp(prefix="f163-pool-check-")
    page = os.path.join(tmpdir, "page.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(f"<!DOCTYPE html><html><head><title>{marker}</title></head>"
                f"<body><h1 id='mark'>{marker}</h1></body></html>")
    page_url = "file:///" + page.replace("\\", "/")

    baseline = _chrome_pids()

    print(f"== F-163 : pool navigateur run-scoped (témoin {marker}) ==")

    # --- 1. Spawn unique -----------------------------------------------------
    print("[1] configure_run + lease → spawn Chrome")
    pool.configure_run("debug_f163")
    root_pid = None
    port1 = None
    with pool.lease("check-1", spawn_timeout_s=settings.browser_pool_spawn_timeout_s) as url:
        st = pool.stats()
        _check("lease retourne une URL --browserUrl", url is not None, str(url))
        _check("Chrome sain (health /json/version)", st["healthy"])
        _check("spawn_count == 1", st["spawn_count"] == 1, f"spawn_count={st['spawn_count']}")
        root_pid, port1 = st["root_pid"], st["port"]

        # --- 2. Façade smolagents -------------------------------------------
        print("[2] façade smolagents chrome_devtools_tools()")
        with chrome_devtools_tools() as tools:
            _check("façade yield des outils", len(tools) > 0, f"{len(tools)} outils")
            by_name = {getattr(t, "name", str(t)): t for t in tools}
            navigate = by_name.get("navigate_page")
            evaluate = by_name.get("evaluate_script")
            if navigate is None or evaluate is None:
                _check("navigate_page + evaluate_script présents", False,
                       f"navigate={navigate is not None} evaluate={evaluate is not None}")
            else:
                navigate(url=page_url)
                # Signature adaptative (miroir static_tester._eval).
                inputs = getattr(evaluate, "inputs", {}) or {}
                js = "() => document.title"
                if "function" in inputs:
                    got = evaluate(function=js)
                elif "script" in inputs:
                    got = evaluate(script=js)
                else:
                    got = evaluate(js)
                _check("smolagents lit la page témoin (même Chrome)", marker in str(got),
                       f"title={str(got)[:60]!r}")

    # --- 3. Chrome chaud ------------------------------------------------------
    print("[3] release puis re-lease → aucun cold-start")
    with pool.lease("check-2") as url2:
        st2 = pool.stats()
        _check("pas de respawn (spawn_count == 1)", st2["spawn_count"] == 1,
               f"spawn_count={st2['spawn_count']}")
        _check("port stable", st2["port"] == port1, f"port={st2['port']}")

        # --- 4. Façade pydantic ----------------------------------------------
        print("[4] façade pydantic build_devtools_mcp_toolset(browser_url=...)")
        asyncio.run(_pydantic_check(url2, page_url, marker))

    # --- 5. Shutdown + zéro résidu --------------------------------------------
    print("[5] shutdown_run → arbre tué, zéro chrome automation résiduel")
    pool.shutdown_run(reason="fin de validation F-163")
    st3 = pool.stats()
    _check("PID racine mort", root_pid is None or root_pid not in _chrome_pids(),
           f"root={root_pid}")
    _check("pool reset (root_pid None)", st3["root_pid"] is None)
    time.sleep(1.0)
    after = _chrome_pids()
    # Tolérance : l'utilisateur peut avoir ouvert SON Chrome pendant le test —
    # on ne vérifie que NOTRE arbre + les automation (marqueur pipe).
    leftovers = after - baseline
    auto_leftovers = []
    if leftovers:
        cmdlines = bp._cmdlines_by_pid("chrome.exe")
        auto_leftovers = [p for p in leftovers
                          if p in cmdlines and bp._AUTOMATION_CHROME_MARKER in cmdlines[p]]
    _check("zéro chrome automation résiduel", not auto_leftovers,
           f"leftovers={sorted(auto_leftovers)}")

    ok_count = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n== F-163 : {ok_count}/{len(RESULTS)} contrôles PASS ==")
    try:
        os.remove(page)
        os.rmdir(tmpdir)
    except OSError:
        pass
    return 0 if ok_count == len(RESULTS) else 1


async def _pydantic_check(browser_url: str, page_url: str, marker: str) -> None:
    """Façade pydantic : MCPToolset connecté au Chrome du pool (F-160 seam)."""
    from graph_orchestrator.coder_pydantic_mcp import build_devtools_mcp_toolset
    from graph_orchestrator.config import load_settings

    ts = build_devtools_mcp_toolset(load_settings(), browser_url=browser_url)
    if ts is None:
        _check("toolset pydantic construit", False, "build → None (désactivé ?)")
        return
    try:
        async with ts:
            args_ok = "--browserUrl" in ts.client.transport.args
            _check("transport porte --browserUrl", args_ok)
            await ts.client.call_tool("navigate_page", {"url": page_url})
            res = await ts.client.call_tool(
                "evaluate_script", {"function": "() => document.title"}
            )
            text = str(getattr(res, "content", res))
            _check("pydantic lit la page témoin (même Chrome)", marker in text,
                   f"title={text[:60]!r}")
    except Exception as exc:  # noqa: BLE001 — le contrôle échoue proprement
        _check("façade pydantic connectée au pool", False, f"{exc}")


if __name__ == "__main__":
    raise SystemExit(main())
