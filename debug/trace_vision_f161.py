"""Diagnostic F-161 : preuve vision multimodale pendant un mini-run Coder pydantic.

Wrap (record global, délégation intacte) :
  - fastmcp Client.call_tool — compte les appels MCP (dont take_screenshot) ;
  - coder_pydantic_vision.split_tool_result — loggue chaque image extraite
    d'un retour d'outil (outil, media_type, taille octets) ;
  - coder_pydantic_vision.purge_history_images — loggue purges/archives ;
puis exécute run_coder_pydantic sur une mini-tâche exigeant un screenshot ET sa
description visuelle — la description du rendu par le 4B est la preuve ultime
que l'image est bien partie au mmproj (croiser avec le log llama-server : saut
de prompt eval ≈ +1,5-2,5k tokens).
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
    "id": "ts-vision",
    "content": (
        "Crée une mini-page counter.html : un bouton +1 et un compteur affiché, "
        "HTML/CSS/JS inline vanilla, dark theme. Vérifie ensuite la page dans le "
        "navigateur : console PUIS take_screenshot — DÉCRIS précisément ce que tu "
        "VOIS sur l'image (couleurs, disposition, texte) avant de conclure."
    ),
    "target_files": ["counter.html"],
    "strategy": "simple",
    "sections": [],
    "skills": [],
    "iteration": 1,
}

CALLS = Counter()
IMAGES = []
PURGES = []


async def main() -> int:
    from fastmcp.client.client import Client as FastMCPClient

    orig = FastMCPClient.call_tool

    async def rec(self, *a, **kw):
        name = a[0] if a else kw.get("name", "?")
        CALLS[name] += 1
        return await orig(self, *a, **kw)

    FastMCPClient.call_tool = rec

    from graph_orchestrator import coder_pydantic_vision as vis

    orig_split = vis.split_tool_result

    def rec_split(result):
        text, images = orig_split(result)
        if images:
            for img in images:
                IMAGES.append(
                    (getattr(img, "media_type", "?"), len(getattr(img, "data", b"")), text[:40])
                )
                print(f"  [VISION] image extraite du retour outil : {IMAGES[-1]}")
        return text, images

    vis.split_tool_result = rec_split

    orig_purge = vis.purge_history_images

    def rec_purge(messages, keep=1, archive_dir=None):
        before = sum(len(getattr(p, "files", []) or []) for m in messages for p in getattr(m, "parts", []))
        out = orig_purge(messages, keep=keep, archive_dir=archive_dir)
        after = sum(len(getattr(p, "files", []) or []) for m in out for p in getattr(m, "parts", []))
        if before != after:
            PURGES.append((before, after))
            print(f"  [PURGE] images vivantes {before} -> {after} (keep={keep})")
        return out

    vis.purge_history_images = rec_purge

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
        print(f"vision_ok={getattr(out, 'vision_ok', '-')}")
        details = getattr(out, "details", "") or ""
        print(f"details: {details[:400]}")
        if metrics:
            print(f"tokens {metrics.input_tokens} in / {metrics.output_tokens} out")
    except Exception as exc:  # noqa: BLE001
        print(f"run exception: {type(exc).__name__}: {exc}")
    finally:
        os.chdir(orig_cwd)

    print("\n=== APPELS MCP (Client.call_tool) ===")
    for name, n in CALLS.most_common():
        print(f"  {n:3d}× {name}")
    print(f"=== IMAGES INJECTÉES DANS LE CONTEXTE : {len(IMAGES)} ===")
    for media, size, text in IMAGES:
        print(f"  {media} {size} octets | texte retour: {text!r}")
    print(f"=== PURGES : {PURGES or 'aucune (≤ keep images)'} ===")
    transcripts = os.path.join(OUT_DIR, ".transcripts", "images")
    if os.path.isdir(transcripts):
        print(f"  archives : {os.listdir(transcripts)}")
    else:
        print("  (pas d'archives .transcripts/images)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
