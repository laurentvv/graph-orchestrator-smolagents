import subprocess
import time
import sys
import json
import os
import socket
import urllib.request
import urllib.error

# Forcer l'UTF-8 pour l'affichage console Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

MODEL_BLOB = r"D:\OLLAMA_MODELS\blobs\sha256-0a270ec9fe6b34f4a0d33992b6135117b484ebc4766ab76b51d4ae8c457e4c42"
HOST = "127.0.0.1"
CTX = 8192
PROMPT = "Explique très brièvement ce qu'est le tri à bulles."


def free_port():
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


port = free_port()


def http_post(path, payload, timeout=300):
    url = "http://{}:{}{}".format(HOST, port, path)
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    print("=" * 60)
    print("🧠 Validation Thinking Gemma 4 — llama.cpp direct")
    print("   --reasoning on | auto-fit (sans -ngl) | contexte 8192")

    env = os.environ.copy()
    # (approche retenue : le flag --reasoning on, plus direct que les chat_template_kwargs)

    cmd = [
        "llama-server",
        "-m", MODEL_BLOB,
        "-c", "8192",
        # PAS de -ngl → auto-fit (comportement Ollama, évite l'OOM)
        "--port", str(port),
        "--reasoning", "on",
        "--no-webui",
    ]
    print("\nCommande lancée :")
    print("   " + " ".join(cmd) + "\n")

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env=env, stdin=subprocess.DEVNULL)
    try:
        # Attente du serveur
        ready = False
        t0 = time.time()
        while time.time() - t0 < 180:
            if proc.poll() is not None:
                print("❌ Le serveur est sorti pendant le chargement (probablement OOM).")
                return
            try:
                h = json.loads(urllib.request.urlopen(
                    "http://{}:{}/health".format(HOST, port), timeout=3).read().decode())
                if h.get("status") == "ok":
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(1)
        if not ready:
            print("❌ Le serveur n'a pas démarré à temps.")
            return
        print("✅ Serveur prêt (auto-fit OK). Envoi de la requête...")

        t_start = time.time()
        resp = http_post("/v1/chat/completions", {
            "model": "gemma",
            "messages": [{"role": "user", "content": PROMPT}],
            "temperature": 0.3,
            # kwargs du template envoyés PAR-REQUÊTE (mécanisme documenté par llama.cpp)
            "chat_template_kwargs": {"enable_thinking": True},
        })
        duration = time.time() - t_start

        msg = resp["choices"][0]["message"]
        content = msg.get("content", "")
        reasoning_content = msg.get("reasoning_content") or msg.get("reasoning") or ""

        usage = resp.get("usage", {})
        comp_tokens = usage.get("completion_tokens") or 0
        tps = comp_tokens / duration if duration > 0 else 0

        print(f"\n⏱️  Durée : {duration:.1f}s | tokens générés : {comp_tokens} | débit : {tps:.2f} tok/s")
        print("   Clés du message :", sorted(msg.keys()))

        # Détection (insensible à la casse) de toute balise de canal
        low = content.lower()
        hits = []
        for tag in ["<|channel>thought", "<channel|>", "thought", "</channel>", "reasoning", "<start_of_thinking>", "<thinking>"]:
            if tag.lower() in low:
                hits.append(tag)
        print("   Balises trouvées dans content :", hits if hits else "aucune")

        thought_ok = bool(reasoning_content) or ("<|channel>thought" in content) or ("<thinking" in low)

        if thought_ok:
            print("✅ THINKING ACTIVÉ.")
        else:
            print("❌ THINKING non détecté (ni reasoning_content, ni balise dans content).")

        if reasoning_content:
            print("\n--- reasoning_content (pensée) ---")
            print(reasoning_content[:2000])

        print("\n--- content (réponse finale) ---")
        print(content)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        time.sleep(2)


if __name__ == "__main__":
    main()
