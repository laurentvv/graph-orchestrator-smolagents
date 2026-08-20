"""Bench A/B Q4_K_M vs Q6_K pour le rôle FAST (Coder) aux flags EXACTS de production. 0 LLM graphe.

Question (décision utilisateur 2026-08-19, post-F-126) : le blob
`models/qwen35-4b-mtp/Qwen3.5-4B-Q6_K.gguf` (3,64 Go vs 2,83 Go en Q4_K_M)
« passe-t-il » sur la RTX 3060 Laptop 6 Go avec la nouvelle config Coder
(ctx 65536 + KV q8_0 + cache-reuse 256 + mmproj + --parallel 1) ? Et à quel
prix en performance (préfill = goulot du rôle Coder multi-tours) ?

Méthode : spawn via llama_server._build_cmd (la VRAIE commande production,
F-123), attente /health, puis :
  - lecture du log serveur : layers offloadées, buffers ;
  - VRAM nvidia-smi serveur chaud ;
  - préfill one-shot ~12k tokens (prompt_per_second) ;
  - génération 128 tokens (predicted_per_second).

Usage : uv run python debug/bench_q6_coder.py [--skip-q4]   # --skip-q4 = Q6 seul
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
from dataclasses import replace

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graph_orchestrator.config import settings  # noqa: E402
from graph_orchestrator.llama_server import _LLAMA_SERVER_BIN, _build_cmd  # noqa: E402

HOST = "127.0.0.1"
LOAD_TIMEOUT = 300.0
COOLDOWN_S = 5.0

MODELS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "qwen35-4b-mtp"
)
Q4 = os.path.join(MODELS_DIR, "Qwen3.5-4B-Q4_K_M.gguf")
Q6 = os.path.join(MODELS_DIR, "Qwen3.5-4B-Q6_K.gguf")

# ~12k tokens (même calibration que debug/bench_prefill_flags.py charge B).
PROMPT_12K = (
    "Règle de production du codeur expert : chaque livrable est un fichier HTML "
    "autonome en JavaScript vanilla, sans framework ; les gestionnaires "
    "d'événements référencent des IDs DOM existants ; les animations sont bornées ; "
    "le thème sombre couvre tous les panneaux ; les timers sont nettoyés. "
) * 60 + "\nRésume en une phrase.\n"


def get_free_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _post(path: str, port: int, payload: dict, timeout: float = 300.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://{HOST}:{port}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def vram_used_mib() -> str:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip().splitlines()
        return out[0].strip() + " MiB"
    except Exception as e:  # pragma: no cover
        return f"n/a ({e})"


def run_variant(label: str, spec) -> dict:
    port = get_free_port()
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "logs", "llama-server")
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(
        logs_dir, f"q6-bench-{time.strftime('%Y%m%d-%H%M%S')}-p{port}-{label}.log"
    )
    cmd = _build_cmd(spec, port)
    print(f"\n=== {label} : {os.path.basename(spec.model)} ===")
    print(f"cmd : {' '.join(cmd[1:])}")
    print(f"log : {log_path}")
    log_f = open(log_path, "w", encoding="utf-8", buffering=1)
    t0 = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log_f,
                            stdin=subprocess.DEVNULL)
    result = {"label": label, "model": os.path.basename(spec.model)}
    try:
        while time.time() - t0 < LOAD_TIMEOUT:
            if proc.poll() is not None:
                result["load"] = f"ÉCHEC (exit {proc.returncode})"
                _dump_log_tail(log_path)
                return result
            try:
                with urllib.request.urlopen(f"http://{HOST}:{port}/health", timeout=3) as r:
                    if json.loads(r.read().decode()).get("status") == "ok":
                        break
            except Exception:
                time.sleep(1.0)
        else:
            result["load"] = "ÉCHEC (timeout 300 s)"
            _dump_log_tail(log_path)
            return result
        result["load_s"] = round(time.time() - t0, 1)
        result["load"] = "OK"
        print(f"[{label}] chargé en {result['load_s']}s — VRAM {vram_used_mib()}")

        # Layers offloadées + buffers depuis le log serveur (ANSI strippé :
        # les codes couleur s'intercalent dans les lignes et cassent les regex).
        log_f.flush()
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            log_txt = re.sub(r"\x1b\[[0-9;]*m", "", f.read())
        m = re.search(r"offloaded (\d+)/(\d+) layers", log_txt)
        result["layers_gpu"] = f"{m.group(1)}/{m.group(2)}" if m else "?"
        m = re.search(r"KV self size[^=]*=\s*([0-9.]+\s*\w+)", log_txt)
        if m:
            result["kv_size"] = m.group(1).strip()
        print(f"[{label}] layers GPU : {result['layers_gpu']}"
              + (f" | KV : {result['kv_size']}" if "kv_size" in result else ""))

        # Préfill one-shot ~12k tokens.
        resp = _post("/completion", port, {"prompt": PROMPT_12K, "n_predict": 16})
        t = resp.get("timings", {})
        result["prompt_n"] = t.get("prompt_n", 0)
        result["prefill_tps"] = round(t.get("prompt_per_second", 0.0), 1)
        print(f"[{label}] préfill {result['prompt_n']} tokens : {result['prefill_tps']} tok/s")

        # Génération 128 tokens (conversationne charge réaliste courte).
        resp = _post("/completion", port,
                     {"prompt": "Écris une fonction JavaScript de tri à bulles commentée :\n",
                      "n_predict": 128})
        t = resp.get("timings", {})
        result["gen_tps"] = round(t.get("predicted_per_second", 0.0), 1)
        print(f"[{label}] génération : {result['gen_tps']} tok/s")

        result["vram_hot"] = vram_used_mib()
        return result
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        log_f.close()
        time.sleep(COOLDOWN_S)


def _dump_log_tail(log_path: str) -> None:
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        print("---- tail log serveur (échec) ----")
        for line in lines[-15:]:
            print("   ", line.rstrip())
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-q4", action="store_true", help="ne tester que le Q6_K")
    args = ap.parse_args()

    base = settings.fast_spec  # .env : ctx 65536, kv q8_0, cache_reuse 256 (F-126)
    print(f"Config production FAST : ctx={base.context} kv={base.kv_quant or 'f16'} "
          f"cache_reuse={base.cache_reuse} mmproj={'oui' if base.mmproj else 'non'} "
          f"| binaire {os.path.basename(_LLAMA_SERVER_BIN)}")
    print(f"VRAM avant bench : {vram_used_mib()}")

    results = []
    if not args.skip_q4:
        assert os.path.exists(base.model), f"blob Q4 introuvable : {base.model}"
        results.append(run_variant("q4_k_m-baseline", base))
    q6_spec = replace(base, model=Q6)
    assert os.path.exists(Q6), f"blob Q6 introuvable : {Q6}"
    results.append(run_variant("q6_k-candidat", q6_spec))

    print("\n================ SYNTHÈSE ================")
    print(f"{'variante':<18}{'load':<7}{'layers':<8}{'vram':<14}{'préfill':<16}{'gen':<10}")
    for r in results:
        print(f"{r['label']:<18}{str(r.get('load')):<7}"
              f"{str(r.get('layers_gpu', '?')):<8}{str(r.get('vram_hot', '?')):<14}"
              f"{str(r.get('prefill_tps', '?')) + ' t/s':<16}{str(r.get('gen_tps', '?')) + ' t/s':<10}")
    if len(results) == 2 and results[0].get("prefill_tps") and results[1].get("prefill_tps"):
        delta = 100.0 * (results[1]["prefill_tps"] - results[0]["prefill_tps"]) / results[0]["prefill_tps"]
        print(f"\nΔ préfill Q6 vs Q4 : {delta:+.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
