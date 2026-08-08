import sys
import time
import json
import urllib.request
import urllib.error
import subprocess

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

MODEL_BLOB = r"D:\OLLAMA_MODELS\blobs\sha256-0a270ec9fe6b34f4a0d33992b6135117b484ebc4766ab76b51d4ae8c457e4c42"
API_URL = "http://127.0.0.1:8080/v1/chat/completions"

SYSTEM_PROMPT = """Tu es un architecte logiciel expert.
Analyse la tâche et génère un plan en sous-tâches unitaires.
Règles :
1. Une sous-tâche = un ensemble cohérent de fichiers.
2. Pour chaque sous-tâche, choisis une stratégie ('simple', 'incremental', 'multifile').

Réponds UNIQUEMENT au format JSON avec cette structure (pas de markdown autour) :
{
  "subtasks": [
    {
      "id": "identifiant",
      "target_files": ["fichier1.ext"],
      "strategy": "simple"
    }
  ]
}
"""

SPEC = """Crée un visualiseur d'algorithme Bubble Sort (tri à bulles) interactif en HTML/CSS/JS vanilla."""

def test_llama_server(enable_thinking: bool):
    print(f"\n{'='*80}")
    print(f"🚀 Lancement de llama-server (enable_thinking={enable_thinking})...")
    print(f"{'='*80}")
    
    # Utilisation d'une variable d'environnement pour éviter le cauchemar de l'échappement JSON sous Windows
    kwargs_str = '{"enable_thinking": true}' if enable_thinking else '{"enable_thinking": false}'
    
    import os
    env = os.environ.copy()
    env["LLAMA_ARG_CHAT_TEMPLATE_KWARGS"] = kwargs_str
    
    cmd = [
        "llama-server", 
        "-m", MODEL_BLOB, 
        "-c", "8192", 
        "-ngl", "999",
        "--port", "8080"
    ]
    
    # Démarrage du processus
    process = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    try:
        # Attente que le serveur soit prêt
        server_ready = False
        for _ in range(30):
            try:
                urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=1)
                server_ready = True
                break
            except Exception:
                time.sleep(1)
                
        if not server_ready:
            print("❌ Le serveur n'a pas démarré à temps.")
            return

        print("✅ Serveur prêt. Envoi de la requête...")
        
        payload = {
            "model": "gemma",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": SPEC}
            ],
            "temperature": 0.3
        }
        
        t0 = time.time()
        req = urllib.request.Request(
            API_URL, 
            data=json.dumps(payload).encode("utf-8"), 
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"].get("content", "")
            duration = time.time() - t0
            
            print(f"⏱️ Durée : {duration:.1f}s")
            
            if "<|channel>thought" in content:
                thought_start = content.find("<|channel>thought")
                thought_end = content.find("<channel|>")
                if thought_end > thought_start:
                    thought_content = content[thought_start+19:thought_end].strip()
                    if thought_content:
                        print(f"✅ THINKING ACTIVÉ ! Contenu du 'thought' : {len(thought_content)} caractères.")
                    else:
                        print("❌ BALISES PRÉSENTES MAIS VIDES (Thinking désactivé).")
            else:
                print("❌ AUCUNE balise de réflexion détectée dans la sortie.")
                
            print("\n--- RÉPONSE BRUTE (Début) ---")
            print(content[:800])
            
    finally:
        print("\nArrêt du serveur...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        time.sleep(2) # Laisse le temps au port de se libérer

if __name__ == "__main__":
    # Test 1 : Sans thinking
    test_llama_server(enable_thinking=False)
    # Test 2 : Avec thinking
    test_llama_server(enable_thinking=True)
