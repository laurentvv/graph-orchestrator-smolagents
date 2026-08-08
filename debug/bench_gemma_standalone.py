import sys
import time
import json
import urllib.request

# Forcer l'UTF-8 (Windows + accents/emojis).
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Cahier des charges pour tester l'Architecte
SPEC = """Crée un visualiseur d'algorithme Bubble Sort (tri à bulles) interactif en
HTML/CSS/JS vanilla (un seul fichier index.html). L'interface doit montrer un tableau de
barres verticales qui s'animent pendant le tri. Fonctionnalités : bouton « Démarrer le tri »
(animé pas-à-pas), bouton « Réinitialiser » (nouveau tableau aléatoire), curseur vitesse,
compteur de comparaisons, code couleur (comparaison/trié/non traité). Dark mode, responsive.
"""

def test_architect_standalone(model_id: str, use_think_token: bool):
    # Appel direct natif à Ollama (pas de DSPy, pas de LiteLLM, pas de /v1)
    api_url = "http://localhost:11434/api/chat"
    
    # Reproduction du prompt système de l'Architecte
    system_prompt = """Tu es un architecte logiciel expert.
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
    
    if use_think_token:
        # INJECTION DU TOKEN MAGIQUE DE GEMMA 4 (sans activer le paramètre API 'think=True')
        system_prompt = "<|think|>\n" + system_prompt
        
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": SPEC}
    ]
    
    payload = {
        "model": model_id,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.3
        }
    }
    
    print(f"\n{'='*80}")
    print(f"🚀 Modèle : {model_id}")
    print(f"🧠 Injection du token <|think|> : {'OUI' if use_think_token else 'NON'}")
    print(f"{'='*80}")
    
    t0 = time.time()
    req = urllib.request.Request(
        api_url, 
        data=json.dumps(payload).encode("utf-8"), 
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("message", {}).get("content", "")
            duration = time.time() - t0
            
            print(f"⏱️ Durée d'exécution : {duration:.1f}s")
            print(f"📊 Longueur de la réponse : {len(content)} caractères")
            
            # Vérification des balises de pensée
            if "<|channel>thought" in content:
                thought_start = content.find("<|channel>thought")
                thought_end = content.find("<channel|>")
                if thought_end > thought_start:
                    thought_content = content[thought_start+19:thought_end].strip()
                    if thought_content:
                        print(f"✅ THINKING ACTIVÉ ! Contenu du 'thought' : {len(thought_content)} caractères.")
                    else:
                        print("❌ BALISES PRÉSENTES MAIS VIDES (Thinking désactivé/ignoré).")
            else:
                print("❌ AUCUNE balise de réflexion détectée.")
                
            print("\n--- RÉPONSE BRUTE (Début) ---")
            print(content[:800])
            if len(content) > 800:
                print("... [TRONQUÉ]")
                
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode('utf-8')
        print(f"❌ Erreur API ({e.code}) : {error_msg}")
    except Exception as e:
        print(f"❌ Erreur lors de l'appel : {e}")

if __name__ == "__main__":
    # Test des deux modèles Gemma que tu possèdes
    models = [
        "hf.co/unsloth/gemma-4-12b-it-GGUF:Q4_K_M",
        "hf.co/google/gemma-4-12B-it-qat-q4_0-gguf:latest"
    ]
    
    print("Démarrage du benchmark standalone (sans DSPy ni graph_orchestrator)...")
    
    for m in models:
        # Test 1 : Sans le token
        test_architect_standalone(m, use_think_token=False)
        # Test 2 : Avec le token injecté dans le prompt système
        test_architect_standalone(m, use_think_token=True)
