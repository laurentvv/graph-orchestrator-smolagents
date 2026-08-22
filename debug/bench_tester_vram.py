"""Bench A/B prefill du serveur no-think (Tester/ULTRA) — reproduction goulot run 2026-08-22_1732.

Contexte (2026-08-22, goulot n°1 « hang Chrome/DevTools du Tester ») :
le Web Tester perd 20-25 min en steps de 25-300 s. Le log llama-server du run
(2026-08-22_1732, port 60931) montre que le temps est LLM, pas DevTools :
prefill 45-66 t/s + gen 10-11 t/s, contre 1342 t/s / 41 t/s au bench sain
F-116-9d (logs/llama-server/prefill-final-p63813.log, ornith-1.0 @ ctx 32768).

Deux choses ont changé depuis ce bench sain :
  1. Modèle ornith-1.0 → ornith-1.5 (téléchargé 2026-08-21 23:02) :
     poids 5.24 GiB + mmproj BF16 0.86 GiB = 6.10 GiB avant KV, sur RTX 3060
     Laptop 6144 MiB (~5.7 GiB libres de base).
  2. REASONING_NO_THINK_CONTEXT=49152 (au lieu de 32768 au bench) et
     REASONING_NO_THINK_NGL=99 forcé → warning au chargement :
     « common_fit_params: failed to fit params to free device memory:
       n_gpu_layers already set by user to 99, abort » (auto-fit ANNULÉ).

Ce script reproduit le spawn EXACT de production (graph_orchestrator/
llama_server.py::_build_cmd sur settings.no_think_spec) puis varie UN paramètre
à la fois pour isoler la cause :

  A prod    : -c 49152 -ngl 99   (config .env actuelle = lente constatée)
  B ctx32k  : -c 32768 -ngl 99   (isole l'effet taille de contexte)
  C autofit : -c 49152 -ngl auto (isole l'effet ngl forcé / auto-fit)
  D 32k+fit : -c 32768 -ngl auto

Mesure : POST /completion, timings serveur (prompt_n/prompt_ms/predicted_*),
plus un contrôle « failed to fit » dans le log du serveur. 0 LLM côté graphe.

Usage :
    uv run python debug/bench_tester_vram.py                # 4 configs, prompt ~8k
    uv run python debug/bench_tester_vram.py --tokens 18000 # prompt ~18k (réplique step 1 Tester)
    uv run python debug/bench_tester_vram.py --only A --tokens 18000
"""
import argparse
import dataclasses
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graph_orchestrator.config import settings  # noqa: E402
from graph_orchestrator.llama_server import (  # noqa: E402
    _build_cmd,
    _free_port,
    _wait_for_health,
)

LOAD_TIMEOUT = 420.0
GEN_TIMEOUT = 900.0     # A @18k ≈ 270 s de prefill + marge
COOLDOWN_S = 5.0

# ~52 tokens par répétition de cette phrase (calibré sur le prompt_n renvoyé par
# le serveur : 99039 tokens pour 1904 phrases ; le but est la VITESSE, pas le sens).
_SENTENCE = (
    "Probe report {i}: the deterministic audit inspected element index {i} and "
    "found layout stable, counters consistent, and animation frames advancing "
    "normally across samples {a} through {b}; no regression was detected."
)


def _build_prompt(n_tokens: int) -> str:
    """Construit un prompt synthétique d'environ n_tokens (texte varié, non dégénéré)."""
    parts = []
    i = 0
    # ~52 tokens par phrase (cf. constante ci-dessus) → nombre de phrases = cible/52,
    # visé un peu large : le serveur tronque au contexte de toute façon.
    while len(parts) < int(n_tokens / 52 * 1.02):
        parts.append(_SENTENCE.format(i=i, a=i * 3, b=i * 3 + 2))
        i += 1
    return " ".join(parts)


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True, timeout=30,
        )
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _vram_free_mib() -> int:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        return int(r.stdout.strip().splitlines()[0])
    except Exception:
        return -1


def _run_config(name: str, spec, n_tokens: int, log_dir: str) -> dict | None:
    port = _free_port()
    cmd = _build_cmd(spec, port)
    print(f"\n=== {name} : ctx={spec.context} ngl={spec.gpu_layers or 'auto'} "
          f"(port {port}) ===")
    print("    $ " + " ".join(cmd[:2] + ["..."] + cmd[-8:]))
    log_path = os.path.join(log_dir, f"bench_{name}_p{port}.log")
    lf = open(log_path, "w", encoding="utf-8", errors="replace")
    t0 = time.time()
    try:
        proc = subprocess.Popen(
            cmd, stdout=lf, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as e:
        print(f"    [!] spawn échoué : {e}")
        return None
    finally:
        pass

    try:
        ok = _wait_for_health(port, timeout=LOAD_TIMEOUT)
        if not ok:
            print(f"    [!] serveur PAS sain après {LOAD_TIMEOUT}s (OOM/crash ?) — voir {log_path}")
            return {"config": name, "error": "unhealthy"}
        load_s = time.time() - t0
        print(f"    chargé en {load_s:.0f}s ; VRAM libre restante : {_vram_free_mib()} MiB")

        prompt = _build_prompt(n_tokens)
        payload = json.dumps({
            "prompt": prompt, "n_predict": 32, "temperature": 0, "cache_prompt": True,
        }).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/completion", data=payload,
            headers={"Content-Type": "application/json"},
        )
        tg0 = time.time()
        with urllib.request.urlopen(req, timeout=GEN_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        wall_s = time.time() - tg0
        t = data.get("timings", {})
        pn, pms = t.get("prompt_n", 0), t.get("prompt_ms", 0.0)
        gn, gms = t.get("predicted_n", 0), t.get("predicted_ms", 0.0)
        ptps = pn / pms * 1000 if pms else 0.0
        gtps = gn / gms * 1000 if gms else 0.0
        print(f"    prefill : {pn} tokens en {pms/1000:.1f}s = {ptps:.0f} t/s")
        print(f"    gen     : {gn} tokens en {gms/1000:.1f}s = {gtps:.1f} t/s")
        print(f"    wall /completion : {wall_s:.1f}s")
        return {
            "config": name, "ctx": spec.context, "ngl": spec.gpu_layers,
            "load_s": round(load_s), "prompt_n": pn, "prompt_ms": round(pms),
            "prefill_tps": round(ptps), "gen_tps": round(gtps, 1),
            "wall_s": round(wall_s, 1),
        }
    except urllib.error.URLError as e:
        print(f"    [!] requête échouée : {e}")
        return {"config": name, "error": str(e)}
    finally:
        _kill_tree(proc)
        lf.close()
        # Laisse le driver libérer la VRAM avant le spawn suivant.
        deadline = time.time() + 40
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            time.sleep(1.0)
        time.sleep(COOLDOWN_S)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokens", type=int, default=8000,
                    help="cible de tokens du prompt (défaut 8000 ; 18000 = réplique step 1 Tester)")
    ap.add_argument("--only", type=str, default="",
                    help="limiter à certaines configs, ex 'A,D' ou 'A'")
    ap.add_argument("--model", type=str, default="",
                    help="gguf alternatif (ex ornith-1.0) → une seule config E_custom")
    ap.add_argument("--mmproj", type=str, default="",
                    help="mmproj pour --model ; 'none' = SANS mmproj (isole son coût VRAM)")
    ap.add_argument("--ctx", type=int, default=0, help="ctx pour --model (défaut = prod)")
    ap.add_argument("--ngl", type=int, default=-1,
                    help="ngl pour --model (défaut = prod ; 0 = auto-fit)")
    args = ap.parse_args()

    base = settings.no_think_spec
    if base.backend != "spawn" or not base.model:
        print("[!] REASONING_NO_THINK_BACKEND != spawn — ce bench exige un spawn local.")
        return 2
    print(f"[i] spec production : {os.path.basename(base.model)}")
    print(f"    poids {os.path.getsize(base.model)/2**30:.2f} GiB"
          + (f" + mmproj {os.path.getsize(base.mmproj)/2**30:.2f} GiB"
             if base.mmproj and os.path.exists(base.mmproj) else " (mmproj absent)"))
    print(f"[i] VRAM libre au départ : {_vram_free_mib()} MiB")

    if args.model:
        overrides = {"model": args.model}
        if args.mmproj == "none":
            overrides["mmproj"] = ""
        elif args.mmproj:
            overrides["mmproj"] = args.mmproj
        if args.ctx:
            overrides["context"] = args.ctx
        if args.ngl >= 0:
            overrides["gpu_layers"] = args.ngl
        configs = {"E_custom": dataclasses.replace(base, **overrides)}
        print(f"[i] config custom unique : {configs['E_custom'].model} "
              f"ctx={configs['E_custom'].context} ngl={configs['E_custom'].gpu_layers or 'auto'} "
              f"mmproj={'oui' if configs['E_custom'].mmproj else 'NON'}")
    else:
        configs = {
            "A_prod_49k_ngl99": base,
            "B_ctx32k_ngl99": dataclasses.replace(base, context=32768),
            "C_ctx49k_autofit": dataclasses.replace(base, gpu_layers=0),
            "D_ctx32k_autofit": dataclasses.replace(base, context=32768, gpu_layers=0),
        }
        if args.only:
            keep = {x.strip().split("_")[0].upper() for x in args.only.split(",") if x.strip()}
            configs = {k: v for k, v in configs.items() if k[0].upper() in keep}
            print(f"[i] configs retenues : {list(configs)}")

    log_dir = os.path.join("logs", "llama-server")
    os.makedirs(log_dir, exist_ok=True)
    results = []
    for name, spec in configs.items():
        r = _run_config(name, spec, args.tokens, log_dir)
        if r:
            results.append(r)

    print("\n===== SYNTHÈSE (prompt ~%d tokens) =====" % args.tokens)
    print(f"{'config':<18}{'ctx':>7}{'ngl':>6}{'load':>6}{'p_ms':>9}{'p t/s':>8}{'gen t/s':>9}{'wall':>7}")
    for r in results:
        if "error" in r:
            print(f"{r['config']:<18}  ERREUR: {r['error']}")
            continue
        print(f"{r['config']:<18}{r['ctx']:>7}{r['ngl'] or 'auto':>6}"
              f"{r['load_s']:>5}s{r['prompt_ms']:>8}ms{r['prefill_tps']:>8}"
              f"{r['gen_tps']:>9}{r['wall_s']:>6}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
