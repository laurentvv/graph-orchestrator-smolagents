"""Chronométrage NU des outils Chrome DevTools MCP (0 LLM) — vérification goulot n°1.

Question : « Chrome DevTools ne devrait pas être lent, il doit y avoir un blocage
quelque part. » Ce script mesure les appels MCP réels du graphe (même fabrique
que chrome_devtools_tools(), spawn npx chrome-devtools-mcp --isolated) sur le
livrable d'un run réel, SANS aucun LLM :

  1. connexion MCP (open_mcp_with_timeout, production F-104)
  2. navigate_page (file:// absolu)
  3. navigate_page reload (le reset d'isolation recommandé pour les sondes)
  4. discover_ui / take_snapshot (via evaluate_script natif)
  5. evaluate_script lecture d'état (hauteurs des barres, compteur)

Usage :
    uv run python debug/bench_devtools_naked.py [chemin index.html]
"""
import asyncio
import os
import sys
import time

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graph_orchestrator.chrome_devtools_tool import chrome_devtools_tools  # noqa: E402


async def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else \
        "runs/2026-08-22_1732_bubble_sort_multifile_v6/index.html"
    url = "file:///" + os.path.abspath(target).replace("\\", "/")
    print(f"[*] Cible : {url}")

    t0 = time.perf_counter()
    with chrome_devtools_tools() as cdt:
        t_conn = time.perf_counter() - t0
        if not cdt:
            print("[!] MCP chrome-devtools indisponible (yield []) — vérifier npx/CHROME_DEVTOOLS_ENABLED.")
            return 2
        names = sorted(t.name for t in cdt)
        print(f"[+] Connexion MCP : {t_conn:.1f}s — {len(names)} outils.")

        def find(name):
            return next((t for t in cdt if t.name == name), None)

        nav = find("navigate_page")
        ev = find("evaluate_script")

        # 1. Navigation initiale (froid : première page du navigateur spawné)
        t0 = time.perf_counter()
        r = await nav.coroutine(url=url) if hasattr(nav, "coroutine") else nav(url=url)
        print(f"[+] navigate_page (initial) : {time.perf_counter()-t0:.2f}s — {str(r)[:80]}")

        # 2. Reload (le reset d'isolation proposé entre sondes)
        for i in range(2):
            t0 = time.perf_counter()
            r = await nav.coroutine(type="reload") if hasattr(nav, "coroutine") else nav(type="reload")
            print(f"[+] navigate_page (reload #{i+1}) : {time.perf_counter()-t0:.2f}s — {str(r)[:60]}")

        # 3. evaluate_script — lecture d'état type sonde (aucune mutation)
        probe = (
            "() => { const bars = [...document.querySelectorAll('[class*=bar], .bar, [id*=bar]')];"
            " const nums = [...document.querySelectorAll('h1,h2,h3,p,span,div')]"
            "   .map(e => (e.id||'')+':'+(e.textContent||'').trim().slice(0,30));"
            " return JSON.stringify({ n_bars: bars.length, sample: nums.slice(0, 6) }); }"
        )
        for i in range(3):
            t0 = time.perf_counter()
            r = await ev.coroutine(function=probe) if hasattr(ev, "coroutine") else ev(function=probe)
            dt = time.perf_counter() - t0
            print(f"[+] evaluate_script (lecture #{i+1}) : {dt:.2f}s — {str(r)[:100]}")

        # 4. Attente in-page de 5 s DANS UN SEUL appel (pattern anti-artefact #3)
        waiter = (
            "async () => { const t0 = performance.now();"
            " await new Promise(r => setTimeout(r, 5000));"
            " return JSON.stringify({ waited_ms: Math.round(performance.now()-t0) }); }"
        )
        t0 = time.perf_counter()
        r = await ev.coroutine(function=waiter) if hasattr(ev, "coroutine") else ev(function=waiter)
        print(f"[+] evaluate_script (attente in-page 5s) : {time.perf_counter()-t0:.2f}s — {str(r)[:60]}")

    print("[i] Connexion MCP fermée proprement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
