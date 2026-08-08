import subprocess
import time
import sys
import json
import re
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
N_TOKENS = 50
LOAD_TIMEOUT = 120     # temps max d'attente du chargement du modèle (health ok)
COMPLETION_TIMEOUT = 180

# Dernier -ngl validé (mis à jour par la boucle principale).
_CURRENT = None


def get_free_port():
    """Retourne un port TCP libre sur 127.0.0.1."""
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _http_get_json(path, port, timeout=5):
    url = "http://{}:{}{}".format(HOST, port, path)
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _http_post_json(path, port, payload, timeout=COMPLETION_TIMEOUT):
    url = "http://{}:{}{}".format(HOST, port, path)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _start_server(ngl, port):
    """Lance llama-server en arrière-plan pour le -ngl donné. Retourne (proc, log_f, log_path)."""
    log_path = "server_ngl_{}.log".format(ngl)
    log_f = open(log_path, "w", encoding="utf-8")
    cmd = [
        "llama-server",
        "-m", MODEL_BLOB,
        "-c", str(CTX),
        "-ngl", str(ngl),
        "--host", HOST,
        "--port", str(port),
        "--no-webui",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )
    return proc, log_f, log_path


def _wait_ready(proc, port):
    """Attend que /health renvoie 'ok'. Retourne (True, statut) ou (False, raison)."""
    t0 = time.time()
    while time.time() - t0 < LOAD_TIMEOUT:
        # Le process est déjà mort pendant le chargement -> probablement OOM.
        if proc.poll() is not None:
            return False, "process-exited ({})".format(proc.returncode)
        try:
            health = _http_get_json("/health", port, timeout=5)
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(1)
            continue
        status = health.get("status", "")
        if status == "ok":
            return True, "ok"
        if status == "error":
            return False, "error"
        time.sleep(1)
    return False, "timeout"

def _read_server_log(log_path):
    """Lit la fin du log serveur pour afficher des indices (OOM éventuel)."""
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
        return lines[-15:]
    except Exception:
        return []


def _kill_server(proc, log_f):
    """Tue llama-server et ferme son log."""
    if proc and proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass
    if log_f:
        try:
            log_f.close()
        except Exception:
            pass
    if proc:
        try:
            proc.wait(timeout=10)
        except Exception:
            pass


def test_ngl(ngl, port):
    print("\n" + "=" * 50)
    print(f"🧪 Test de charge GPU avec -ngl {ngl}...")

    proc, log_f, log_path = _start_server(ngl, port)

    try:
        ready, reason = _wait_ready(proc, port)
        if not ready:
            print(f"❌ Échec du chargement avec -ngl {ngl} (état : {reason}).")
            _print_tail(log_path)
            return False

        print(f"   Modèle chargé avec -ngl {ngl}, lancement de l'inférence...")

        try:
            resp = _http_post_json("/completion", port,
                                   {"prompt": PROMPT, "n_predict": N_TOKENS})
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"❌ -ngl {ngl} : erreur HTTP {e.code} pendant l'inférence.")
            print("   " + body[:300])
            return False

        timings = resp.get("timings", {})
        tps = timings.get("predicted_per_second")
        if tps is None:
            print(f"✅ Succès avec -ngl {ngl} (benchmark non fourni).")
        else:
            print(f"✅ Succès ! Vitesse d'inférence : {tps:.2f} tokens/seconde")
        return True

    except KeyboardInterrupt:
        print(f"\n⏹️  Interrompu par l'utilisateur pendant le test -ngl {ngl}.")
        print("🏆 La configuration optimale restait : -ngl", _CURRENT)
        return "interrupt"

    except Exception as e:
        print(f"❌ Erreur inattendue avec -ngl {ngl} : {e}")
        return False

    finally:
        _kill_server(proc, log_f)
        time.sleep(2)  # laisse le GPU libérer sa mémoire entre deux tests


def _print_tail(log_path):
    print("   --- fin du log serveur ---")
    for line in _read_server_log(log_path):
        print("   | " + line)


def run_auto_fit():
    """Mode 'Ollama' : on ne passe PAS -ngl. llama.cpp auto-ajuste le nombre de
    couches GPU à la VRAM libre (mécanisme common_fit_params), exactement comme
    Ollama. On relit ensuite le log serveur pour le nombre de couches offloadées."""
    print("\n" + "=" * 60)
    print("🤖 Mode auto-fit (comportement Ollama) : -ngl NON fixé → llama.cpp s'adapte")
    port = get_free_port()
    log_path = "server_auto_fit.log"
    log_f = open(log_path, "w", encoding="utf-8")

    cmd = [
        "llama-server",
        "-m", MODEL_BLOB,
        "-c", str(CTX),
        "--host", HOST,
        "--port", str(port),
        "--no-webui",
        "--no-mmap",          # comme Ollama (windows_cuda)
        "--flash-attn", "auto",
    ]
    print("   Commande lancée (sans -ngl) :\n   " + " ".join(cmd) + "\n")
    proc = subprocess.Popen(cmd, stdout=log_f, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL)

    try:
        ready, reason = _wait_ready(proc, port)
        if not ready:
            print(f"❌ Le chargement auto-fit a échoué (état : {reason}).")
            _print_tail(log_path)
            return
        resp = _http_post_json("/completion", port,
                               {"prompt": PROMPT, "n_predict": N_TOKENS})
        tps = resp.get("timings", {}).get("predicted_per_second")

        # Nombre de couches offloadées, relu dans le log serveur
        offloaded = None
        for line in _read_server_log_for(log_path, "offloaded"):
            m = re.search(r"offloaded (\d+)/(\d+) layers", line)
            if m:
                offloaded = (int(m.group(1)), int(m.group(2)))
                break

        print("\n🏁 Résultat auto-fit (équivalent Ollama) :")
        if offloaded:
            print(f"   → couches offloadées sur GPU : {offloaded[0]}/{offloaded[1]}")
        if tps is not None:
            print(f"   → vitesse d'inférence        : {tps:.2f} tokens/seconde")
        else:
            print("   → benchmark non fourni par le serveur.")
        print("\n   💡 C'est la config 'sûre' qu'utilise Ollama : s'adapte à la VRAM,")
        print("      idéale si tu utilises un grand contexte ou un modèle multimodale.")
    finally:
        _kill_server(proc, log_f)


def _read_server_log_for(log_path, keyword):
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().splitlines()
    except Exception:
        return []


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "auto":
        run_auto_fit()
        sys.exit(0)

    print("Recherche du paramètre '-ngl' optimal via llama-server (HTTP)...")
    print("Le serveur est relancé sur un port libre pour chaque valeur testée.")
    print("Astuce : appuie sur Ctrl+C à tout moment pour arrêter proprement.")

    layers_to_test = [15, 20, 25, 28, 30, 32, 35, 38]
    optimal_ngl = 15
    _CURRENT = 15

    for l in layers_to_test:
        port = get_free_port()
        result = test_ngl(l, port)
        if result == "interrupt":
            sys.exit(0)
        if not result:
            print(f"\n⚠️ Limite de VRAM atteinte à {l} couches.")
            print(f"🏆 Le paramètre optimal recommandé est : -ngl {optimal_ngl}")
            break
        optimal_ngl = l
        _CURRENT = l

    if optimal_ngl == layers_to_test[-1]:
        print(f"\n🏆 Tout est passé ! Le paramètre optimal recommandé est : -ngl {optimal_ngl}")

