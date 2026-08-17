"""Test de compatibilité du décodage spéculatif MTP (--spec-type draft-mtp) — 0 LLM côté graphe.

Contexte (2026-08-17) : les GGUF du projet (Qwen3.5-4B-MTP, Ornith-1.0-9B-MTP) contiennent
des couches MTP (tenseurs blk.N.nextn.*) que llama-server IGNORE au chargement tant que
--spec-type draft-mtp n'est pas passé. Preuve dans logs/llama-server/*.log :
    W model has unused tensor blk.32.nextn.eh_proj.weight ... -- ignoring

Ce script fait un A/B par rôle du graphe (modèle + flags EXACTS du spawn production,
graph_orchestrator/llama_server.py::_spawn) :

    A. baseline : flags production (--parallel 1, --flash-attn, --reasoning, --mmproj, -ngl)
    B. spec-mtp : idem + --spec-default --spec-type draft-mtp --spec-draft-type-k q8_0
                  --spec-draft-type-v q8_0
    C. spec+kvq8 (si B passe) : idem B + --cache-type-k q8_0 --cache-type-v q8_0

Vérifications par run :
    - serveur sain (/health ok) — sinon OOM/crash → incompatible ;
    - le log NE contient PLUS les warnings "unused tensor ... nextn" (le draft a consommé
      les couches MTP) — s'ils persistent, le serveur a silencieusement ignoré le draft ;
    - génération /completion OK et tokens/s (comparaison baseline vs spec) ;
    - métriques d'acceptation spec via /metrics (prometheus) si exposées.

Usage :
    uv run python debug/test_mtp_spec.py                # 3 rôles × A/B (+C si OK)
    uv run python debug/test_mtp_spec.py --only fast    # un seul rôle : fast|reasoning|no_think
    uv run python debug/test_mtp_spec.py --ctx 8192 --n-predict 128

Contexte de test réduit par défaut (8192) : le but est la compatibilité et le delta de
vitesse, pas la réplique exacte de la pression VRAM production (FAST_CONTEXT=49152).
"""
import argparse
import json
import os
import re
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
    _LLAMA_BACKEND,
    _LLAMA_SERVER_BIN,
)

HOST = "127.0.0.1"
LOAD_TIMEOUT = 300.0     # aligné production (llama_server._wait_for_health)
GEN_TIMEOUT = 180.0
COOLDOWN_S = 3.0         # laisse l'OS libérer la VRAM entre deux spawns

PROMPT = (
    "Écris une fonction JavaScript bubbleSort(arr) qui trie un tableau d'entiers "
    "en place et le retourne, avec un commentaire par ligne."
)

SPEC_FLAGS = [
    # Aligné sur les flags production (llama_server._build_cmd) : PAS de --spec-default
    # (ngram-mod empilé dégrade : 24,1 vs 25,6 t/s bench 2026-08-17) ; n-max 2 optimal.
    "--spec-type", "draft-mtp",
    "--spec-draft-n-max", "2",
    "--spec-draft-type-k", "q8_0",
    "--spec-draft-type-v", "q8_0",
]
KV_Q8_FLAGS = ["--cache-type-k", "q8_0", "--cache-type-v", "q8_0"]


def get_free_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _http_get(path: str, port: int, timeout: float = 5.0) -> str:
    with urllib.request.urlopen(f"http://{HOST}:{port}{path}", timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _http_post_json(path: str, port: int, payload: dict, timeout: float = GEN_TIMEOUT) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://{HOST}:{port}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def build_cmd(spec, ctx: int, extra_flags: list[str], force_auto_ngl: bool = False) -> list[str]:
    """Reproduit la construction de llama_server._spawn (flags production) + extra_flags."""
    cmd = [
        _LLAMA_SERVER_BIN,
        "-m", spec.model,
        "--host", HOST,
        "--port", "__PORT__",  # remplacé par le caller
        "-c", str(ctx),
        "--reasoning", spec.reasoning or "off",
        "--alias", "default",
        "--flash-attn", spec.flash_attn or "auto",
        "--parallel", "1",
    ]
    if spec.gpu_layers and spec.gpu_layers > 0 and not force_auto_ngl:
        cmd += ["-ngl", str(spec.gpu_layers)]
    if spec.mmproj and os.path.exists(spec.mmproj):
        cmd += ["--mmproj", spec.mmproj]
    return cmd + extra_flags


def wait_ready(proc, port: int):
    """Attend /health. Retourne (ok, raison). Détecte crash process et /health error."""
    t0 = time.time()
    while time.time() - t0 < LOAD_TIMEOUT:
        if proc.poll() is not None:
            return False, f"process-exited (code {proc.returncode})"
        try:
            health = json.loads(_http_get("/health", port))
            status = health.get("status", "")
            if status == "ok":
                return True, "ok"
            if status == "error":
                return False, "health-error"
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(1.0)
    return False, "timeout"


def read_log_lines(log_path: str) -> list[str]:
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().splitlines()
    except Exception:
        return []


def strip_ansi(line: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", line)


def run_variant(role: str, spec, ctx: int, n_predict: int,
                extra_flags: list[str], label: str, force_auto_ngl: bool = False) -> dict:
    """Spawn + santé + détection draft + bench. Retourne un dict-résultat."""
    port = get_free_port()
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    logs_dir = os.path.join(project_root, "logs", "llama-server")
    os.makedirs(logs_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_path = os.path.join(logs_dir, f"mtp-test-{stamp}-p{port}-{role}-{label}.log")
    log_f = open(log_path, "w", encoding="utf-8", buffering=1)

    cmd = build_cmd(spec, ctx, extra_flags, force_auto_ngl)
    cmd = [str(port) if a == "__PORT__" else a for a in cmd]
    print(f"\n[{role}/{label}] spawn : {' '.join(os.path.basename(str(c)) if i == 0 else str(c) for i, c in enumerate(cmd))}")
    print(f"[{role}/{label}] log    : {log_path}")

    result = {"role": role, "label": label, "log": log_path, "ok": False,
              "reason": "", "tps": None, "nextn_ignored": None, "spec_lines": [],
              "forced_auto_ngl": force_auto_ngl}
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log_f,
                                stdin=subprocess.DEVNULL)
    except Exception as e:
        result["reason"] = f"spawn-failed: {str(e)[:120]}"
        log_f.close()
        return result

    try:
        ready, reason = wait_ready(proc, port)
        if not ready:
            result["reason"] = reason
            print(f"[{role}/{label}] ❌ chargement échoué : {reason}")
            for line in read_log_lines(log_path)[-8:]:
                print("    | " + strip_ansi(line)[:140])
            return result

        lines = [strip_ansi(l) for l in read_log_lines(log_path)]
        nextn_warns = [l for l in lines if "unused tensor" in l and "nextn" in l]
        result["nextn_ignored"] = len(nextn_warns)
        result["spec_lines"] = [l.strip()[:120] for l in lines
                                if re.search(r"\b(draft|spec)", l, re.IGNORECASE)
                                and "unused tensor" not in l][:6]

        print(f"[{role}/{label}] serveur ok — nextn ignored: {len(nextn_warns)}")
        for s in result["spec_lines"]:
            print(f"    spec| {s}")

        try:
            resp = _http_post_json("/completion", port,
                                   {"prompt": PROMPT, "n_predict": n_predict})
            result["tps"] = resp.get("timings", {}).get("predicted_per_second")
            result["n_gen"] = len(resp.get("content", "")) > 0
            result["ok"] = True
            print(f"[{role}/{label}] ✅ génération OK — {result['tps']:.2f} tok/s")
        except Exception as e:
            result["reason"] = f"completion-failed: {str(e)[:120]}"
            print(f"[{role}/{label}] ❌ génération échouée : {str(e)[:120]}")
            return result

        # Métriques d'acceptation spec (prometheus), si exposées.
        try:
            metrics = _http_get("/metrics", port, timeout=5)
            spec_metrics = [l for l in metrics.splitlines()
                            if "speculative" in l.lower() or "draft" in l.lower()]
            for m in spec_metrics[:6]:
                print(f"    metric| {m[:120]}")
        except Exception:
            pass
        return result
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        log_f.close()
        time.sleep(COOLDOWN_S)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", choices=["fast", "reasoning", "no_think"], default=None)
    ap.add_argument("--ctx", type=int, default=8192)
    ap.add_argument("--n-predict", type=int, default=128)
    args = ap.parse_args()

    roles = [
        ("fast", settings.fast_spec),
        ("reasoning", settings.reasoning_spec),
        ("no_think", settings.no_think_spec),
    ]
    if args.only:
        roles = [(r, s) for r, s in roles if r == args.only]

    print(f"Binaire    : {_LLAMA_SERVER_BIN} (backend={_LLAMA_BACKEND})")
    print(f"CTX test   : {args.ctx} | n_predict : {args.n_predict}")

    results = []
    for role, spec in roles:
        if not (spec.backend == "spawn" and spec.model and os.path.exists(spec.model)):
            print(f"\n[{role}] ignoré (backend={spec.backend} ou modèle absent)")
            continue
        print(f"\n{'=' * 70}")
        print(f"Rôle {role} : {os.path.basename(spec.model)} "
              f"(reasoning={spec.reasoning}, ngl={spec.gpu_layers or 'auto-fit'}, "
              f"mmproj={'oui' if spec.mmproj and os.path.exists(spec.mmproj) else 'non'})")

        base = run_variant(role, spec, args.ctx, args.n_predict, [], "baseline")
        results.append(base)

        specr = run_variant(role, spec, args.ctx, args.n_predict, SPEC_FLAGS, "spec-mtp")
        # Retry auto-fit si le -ngl fixe (ex: REASONING_NGL=99) fait OOM avec le draft.
        if not specr["ok"] and spec.gpu_layers and spec.gpu_layers > 0:
            print(f"[{role}] retry spec-mtp SANS -ngl fixe (auto-fit)...")
            specr2 = run_variant(role, spec, args.ctx, args.n_predict, SPEC_FLAGS,
                                 "spec-mtp-autofit", force_auto_ngl=True)
            if specr2["ok"]:
                specr = specr2
        results.append(specr)

        if specr["ok"] and specr["nextn_ignored"] == 0:
            kv = run_variant(role, spec, args.ctx, args.n_predict,
                             SPEC_FLAGS + KV_Q8_FLAGS, "spec-kvq8")
            results.append(kv)

    print(f"\n{'=' * 70}\nSYNTHÈSE")
    print(f"{'rôle/variante':<28}{'ok':<5}{'nextn ignorés':<15}{'tok/s':<10}remarque")
    for r in results:
        tps = f"{r['tps']:.2f}" if r["tps"] else "—"
        nextn = str(r["nextn_ignored"]) if r["nextn_ignored"] is not None else "?"
        note = r["reason"] or ("" if r["nextn_ignored"] == 0 else "⚠ draft ignoré !")
        if r["forced_auto_ngl"]:
            note = (note + " (auto-fit)").strip()
        print(f"{r['role'] + '/' + r['label']:<28}{'✅' if r['ok'] else '❌':<5}{nextn:<15}{tps:<10}{note}")

    verdicts = []
    for r in results:
        if r["label"] == "baseline":
            continue
        if not r["ok"]:
            verdicts.append(f"{r['role']}: spec ÉCHOUE ({r['reason']})")
        elif r["nextn_ignored"] and r["nextn_ignored"] > 0:
            verdicts.append(f"{r['role']}: spec charge mais IGNORE le draft MTP")
        else:
            b = next((x for x in results if x["role"] == r["role"] and x["label"] == "baseline"), None)
            delta = ""
            if b and b["tps"] and r["tps"]:
                d = (r["tps"] / b["tps"] - 1.0) * 100.0
                delta = f" ({d:+.0f}% vs baseline)"
            verdicts.append(f"{r['role']}: COMPATIBLE ✅{delta}")
    print("\nVERDICT :")
    for v in verdicts:
        print("  - " + v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
