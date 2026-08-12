import subprocess
import time
import re
import sys

# Forcer l'UTF-8 pour l'affichage console Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

MODEL_BLOB = r"D:\OLLAMA_MODELS\blobs\sha256-0a270ec9fe6b34f4a0d33992b6135117b484ebc4766ab76b51d4ae8c457e4c42"

# Dernier -ngl validé (global, mis à jour par la boucle principale). Utilisé par le
# handler KeyboardInterrupt de test_ngl pour afficher la config optimale en cas de Ctrl+C.
_CURRENT = None

def test_ngl(ngl):
    print(f"\n{'='*50}")
    print(f"🧪 Test de charge GPU avec -ngl {ngl}...")
    
    # On utilise llama-cli pour un test "one-shot" rapide
    # -n 50 limite la génération à 50 tokens (assez pour avoir le benchmark de vitesse)
    cmd = [
        "llama-cli",
        "-m", MODEL_BLOB,
        "-c", "8192",
        "-ngl", str(ngl),
        "-p", "Explique très brièvement ce qu'est le tri à bulles.",
        "-n", "50",
    ]
    
    # Popen explicite (au lieu de subprocess.run) pour pouvoir tuer l'enfant
    # proprement si l'utilisateur appuie sur Ctrl+C. Avec subprocess.run + capture_output,
    # un KeyboardInterrupt laisse l'enfant vivant et les threads de lecture bloqués.
    proc = None
    try:
        t0 = time.time()
        # stdin=DEVNULL empêche le cli de rester bloqué en mode interactif
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
        )
        stdout_data, stderr_data = proc.communicate(timeout=120)
        output = (stderr_data or "") + "\n" + (stdout_data or "")
        
        # Détection du Out Of Memory
        if "ErrorOutOfDeviceMemory" in output or "failed to allocate" in output or "out of memory" in output.lower():
            print(f"❌ OOM (Out Of Memory) atteint avec -ngl {ngl}. Trop de VRAM demandée.")
            return False
            
        # Extraction de la vitesse depuis les statistiques finales de llama.cpp
        # Exemple: llama_print_timings:        eval time =    1234.56 ms /    50 runs   (   24.69 ms per token,    40.50 tokens per second)
        match = re.search(r"eval time = .*? runs\s+\(.*?, \s*([0-9.]+) tokens per second\)", output)
        
        if match:
            tps = float(match.group(1))
            duration = time.time() - t0
            print(f"✅ Succès ! Vitesse d'inférence : {tps:.2f} tokens/seconde (Temps total: {duration:.1f}s)")
            return True
        else:
            print("✅ Succès (mais format de log non reconnu).")
            # En cas de doute, on affiche la fin du log
            lines = output.split('\n')
            for line in lines[-10:]:
                if "eval time" in line:
                    print(line.strip())
            return True
            
    except subprocess.TimeoutExpired:
        print("❌ Timeout : la commande a pris trop de temps (inhabituel pour 50 tokens).")
        _kill_proc(proc)
        return False
    except KeyboardInterrupt:
        # Ctrl+C : on tue l'enfant et on ferme les pipes pour éviter
        # que les threads de lecture restent bloqués, puis on sort proprement.
        print(f"\n⏹️  Interrompu par l'utilisateur pendant le test -ngl {ngl}.")
        _kill_proc(proc)
        print("🏆 Le dernier -ngl valide était : {} couches.".format(_CURRENT))
        print("Ta configuration optimale reste donc : -ngl", _CURRENT)
        sys.exit(0)
    except Exception as e:
        print(f"❌ Erreur inattendue : {e}")
        _kill_proc(proc)
        return False


def _kill_proc(proc):
    """Tue proprement le processus enfant et ferme ses pipes."""
    if proc and proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass
    if proc:
        try:
            proc.stdout.close()
        except Exception:
            pass
        try:
            proc.stderr.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=10)
        except Exception:
            pass

if __name__ == "__main__":
    print("Recherche du paramètre '-ngl' optimal pour ta carte graphique...")
    print("Le script va augmenter progressivement les couches GPU jusqu'au crash OOM.")
    print("Astuce : appuie sur Ctrl+C à tout moment pour arrêter proprement.")
    
    # On teste progressivement pour trouver le sweet spot
    layers_to_test = [15, 20, 25, 28, 30, 32, 35, 38]
    
    optimal_ngl = 15
    max_tps = 0
    _CURRENT = 15  # dernier -ngl validé (utilisé par le handler KeyboardInterrupt)
    
    for layer in layers_to_test:
        success = test_ngl(layer)
        if not success:
            print(f"\n⚠️ Limite de VRAM atteinte à {layer} couches.")
            print(f"🏆 Le paramètre optimal recommandé pour ta configuration est : -ngl {optimal_ngl}")
            break
        
        optimal_ngl = layer
        _CURRENT = layer
        time.sleep(2) # Laisse quelques secondes au GPU pour vider son cache entre deux runs

    if optimal_ngl == layers_to_test[-1]:
        print(f"\n🏆 Tout est passé ! Le paramètre optimal recommandé est : -ngl {optimal_ngl}")
