"""Bench préfill des flags candidats FAST (Qwen-4B) : --cache-reuse et -ub. 0 LLM graphe.

Contexte (2026-08-17, recherche flags llama.cpp b10472) : deux flags candidats pour le
 rôle FAST (Coder multi-tours, goulot = PRÉFILL : post-mortem run #4 = marathon 35
 steps × ~135 s de préfill) :

  A. --cache-reuse 256 : réutilise des chunks de KV via shifting quand le MILIEU du
     prompt change (l'agent réécrit/compacte d'anciens messages — F-101). Sans lui,
     le cache de préfixe du slot est invalidé à partir du premier token modifié.
     Valeur 256 = presets officiels llama.cpp Qwen Coder + particula.tech (juil. 2026).
  B. -ub (ubatch) : batch physique du préfill. Défaut 512 ; 1024/2048 = préfill plus
     rapide si VRAM compute buffer suffisante (4B ~2,5 Go → marge sur 6 Go).

Charge A (multi-tours agent) : système ~1,5k tokens + 8 tours ; à CHAQUE tour un bloc
tool-result ancien est modifié (milieu d'historique) + un tour appended → discrimine
le shifting (cache-reuse) du simple cache de préfixe (baseline). max_tokens 24/tour.
Métrique : somme des prompt_ms par tour (timings de /v1/chat/completions).

Charge B (préfill one-shot) : /completion avec prompt ~12k tokens, serveur FRAIS à
chaque variante (zéro cache). Métrique : prompt_per_second.

Usage : uv run python debug/bench_prefill_flags.py [--ctx 16384] [--turns 8]
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graph_orchestrator.config import settings  # noqa: E402
from graph_orchestrator.llama_server import _LLAMA_SERVER_BIN  # noqa: E402

HOST = "127.0.0.1"
LOAD_TIMEOUT = 300.0
COOLDOWN_S = 3.0

SYSTEM_BASE = (
    "Tu es un agent codeur expert en JavaScript vanilla. Voici tes règles de "
    "production : chaque livrable doit être un fichier HTML autonome ; interdiction "
    "des frameworks ; les gestionnaires d'événements doivent référencer des IDs DOM "
    "existants ; les animations doivent être bornées ; les captures d'écran se font "
    "au viewport uniquement. Règles de syntaxe : pas de top-level await ; les "
    "fonctions doivent être déclarées avant usage ; triples quotes interdites en "
    "JS. Historique des leçons de runs précédents : le compteur de comparaisons "
    "doit être propagé au DOM ; les timers doivent être nettoyés ; le thème sombre "
    "doit couvrir tous les panneaux. "
)
USER_TMPL = (
    "Tool result step {i}:\n```js\nfunction step{i}() {{ /* logique de tri étape {i} "
    "— compare arr[j] et arr[j+1], swap si nécessaire, incrémente le compter, "
    "met à jour les barres DOM, programme la frame suivante */ }}\n```\n"
    "Continue : analyse ce résultat et planifie la suite."
)


def get_free_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _post(path: str, port: int, payload: dict, timeout: float = 300.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"http://{HOST}:{port}{path}", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def start_server(spec, ctx: int, extra: list[str]):
    port = get_free_port()
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    logs_dir = os.path.join(project_root, "logs", "llama-server")
    os.makedirs(logs_dir, exist_ok=True)
    tag = re.sub(r"[^a-z0-9]+", "-", " ".join(extra).lower())[:40] or "baseline"
    log_path = os.path.join(logs_dir, f"prefill-bench-{time.strftime('%Y%m%d-%H%M%S')}-p{port}-{tag}.log")
    log_f = open(log_path, "w", encoding="utf-8", buffering=1)
    cmd = [_LLAMA_SERVER_BIN, "-m", spec.model, "--host", HOST, "--port", str(port),
           "-c", str(ctx), "--reasoning", spec.reasoning or "off", "--alias", "default",
           "--flash-attn", spec.flash_attn or "auto", "--parallel", "1"]
    if spec.mmproj and os.path.exists(spec.mmproj):
        cmd += ["--mmproj", spec.mmproj]
    cmd += extra
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log_f, stdin=subprocess.DEVNULL)
    t0 = time.time()
    while time.time() - t0 < LOAD_TIMEOUT:
        if proc.poll() is not None:
            raise RuntimeError(f"serveur mort au chargement ({proc.returncode}) — voir {log_path}")
        try:
            with urllib.request.urlopen(f"http://{HOST}:{port}/health", timeout=3) as r:
                if json.loads(r.read()).get("status") == "ok":
                    return proc, port, log_f, log_path
        except Exception:
            time.sleep(1.0)
    raise RuntimeError("timeout chargement")


def stop_server(proc, log_f):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    log_f.close()
    time.sleep(COOLDOWN_S)


def bench_cache_reuse(spec, ctx: int, turns: int, extra: list[str], label: str):
    """Charge multi-tours agent : historique croissant + bloc médian réécrit/tour."""
    proc = port = log_f = None
    try:
        proc, port, log_f, _ = start_server(spec, ctx, extra)
        system = {"role": "system", "content": SYSTEM_BASE * 12}  # ~1,5-2k tokens
        messages = [system]
        prompt_ms_total, prompt_tokens_total = 0, 0
        per_turn = []
        for i in range(1, turns + 1):
            messages.append({"role": "user", "content": USER_TMPL.format(i=i)})
            # Réécrit le PREMIER tool-result (milieu d'historique) : simule la
            # compaction/résumé d'anciens steps (F-101) → invalide le cache de
            # préfixe baseline à partir de ce point ; seul cache-reuse peut
            # réutiliser la queue via shifting.
            if len(messages) > 3:
                first_user = messages[1]["content"]
                messages[1]["content"] = first_user + f"\n[synthèse mise à jour v{i}]"
            resp = _post("/v1/chat/completions", port, {
                "model": "default", "messages": messages, "max_tokens": 24,
            }, timeout=300.0)
            t = resp.get("timings", {})
            prompt_ms = t.get("prompt_ms", 0.0)
            n_prompt = t.get("prompt_n", resp.get("usage", {}).get("prompt_tokens", 0))
            prompt_ms_total += prompt_ms
            prompt_tokens_total += n_prompt
            per_turn.append((i, n_prompt, prompt_ms))
            messages.append({"role": "assistant",
                             "content": resp["choices"][0]["message"]["content"] or "ok"})
        print(f"\n[{label}] tours={turns} tokens_préfill_total={prompt_tokens_total} "
              f"temps_préfill_total={prompt_ms_total/1000.0:.2f}s")
        for i, n, ms in per_turn:
            print(f"    tour {i}: prompt_n={n:5d}  prompt_ms={ms:8.0f}")
        return {"label": label, "prompt_s": prompt_ms_total / 1000.0,
                "tokens": prompt_tokens_total}
    finally:
        if proc:
            stop_server(proc, log_f)


def bench_ubatch(spec, ctx: int, extra: list[str], label: str):
    """Préfill one-shot ~12k tokens sur serveur frais : mesure prompt_per_second."""
    proc = port = log_f = None
    try:
        proc, port, log_f, _ = start_server(spec, ctx, extra)
        prompt = SYSTEM_BASE * 60 + "\nRésume en une phrase.\n"  # ~12k tokens
        resp = _post("/completion", port, {"prompt": prompt, "n_predict": 16}, timeout=300.0)
        t = resp.get("timings", {})
        tps = t.get("prompt_per_second", 0.0)
        n = t.get("prompt_n", 0)
        print(f"[{label}] prompt_n={n}  prompt_per_second={tps:.1f} tok/s")
        return {"label": label, "prefill_tps": tps}
    finally:
        if proc:
            stop_server(proc, log_f)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ctx", type=int, default=16384)
    ap.add_argument("--turns", type=int, default=8)
    args = ap.parse_args()
    spec = settings.fast_spec
    print(f"Modèle FAST : {os.path.basename(spec.model)} | ctx {args.ctx} | binaire {os.path.basename(_LLAMA_SERVER_BIN)}")

    print("\n=== A. cache-reuse (charge agent multi-tours, bloc médian réécrit) ===")
    ra = []
    ra.append(bench_cache_reuse(spec, args.ctx, args.turns, [], "baseline"))
    ra.append(bench_cache_reuse(spec, args.ctx, args.turns,
                                ["--cache-reuse", "256"], "cache-reuse-256"))

    print("\n=== B. ubatch préfill (one-shot ~12k tokens, serveur frais) ===")
    rb = []
    for ub in (512, 1024, 2048):
        rb.append(bench_ubatch(spec, args.ctx, ["-ub", str(ub)], f"ub-{ub}"))

    print("\n=== SYNTHÈSE ===")
    b = ra[0]["prompt_s"]
    for r in ra:
        d = (r["prompt_s"] / b - 1.0) * 100.0 if b else 0
        print(f"  {r['label']:<18} préfill total {r['prompt_s']:.2f}s ({d:+.0f}% vs baseline)")
    bb = rb[0]["prefill_tps"]
    for r in rb:
        d = (r["prefill_tps"] / bb - 1.0) * 100.0 if bb else 0
        print(f"  {r['label']:<18} préfill {r['prefill_tps']:.1f} tok/s ({d:+.0f}% vs ub-512)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
