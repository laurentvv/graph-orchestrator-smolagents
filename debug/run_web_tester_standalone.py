import asyncio
import os
import sys

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graph_orchestrator.config import load_settings
from smolagents import OpenAIServerModel
from graph_orchestrator.testers.web_tester import WebTestRunner

async def main():
    print("[*] Lancement du Web Tester Standalone...")
    
    settings = load_settings()
    
    # On instancie le modèle (on prend les paramètres de l'env .env comme le fait l'orchestrateur)
    # fast_model est utilisé par le tester
    api_base = os.getenv("FAST_BACKEND_URL", "http://localhost:8080/v1")
    model_id = os.getenv("FAST_MODEL", "default")
    
    fast_model = OpenAIServerModel(
        api_base=api_base,
        model_id=model_id,
        api_key="local-no-key"
    )
    
    # On mock une tache pour l'agent
    task = {
        "id": "standalone-test",
        "tech": "web",
        "target_files": ["runs/2026-08-05_0112_bubble_sort/index.html"],
        "content": "Clique sur Démarrer, attends 500ms. Utilise l'outil `puppeteer_add_visual_tags` puis fais un `take_screenshot` pour vérifier visuellement si les barres disparaissent.",
        "skills": []
    }
    
    print(f"[*] Cible : {task['target_files'][0]}")
    print("[*] Lancement du runner (cela peut prendre jusqu'à 5 minutes)...")
    
    runner = WebTestRunner()
    test_output, metrics = await runner.run(task, fast_model, settings)
    
    print("\n" + "="*50)
    print("RÉSULTAT DU TEST :")
    print("="*50)
    if test_output:
        if isinstance(test_output, str):
            print(test_output)
        else:
            print(test_output.details)
    else:
        print("Timeout ou erreur : le Tester a renvoyé None (TIMEOUT ERROR géré par l'orchestrateur au niveau superieur).")

if __name__ == "__main__":
    asyncio.run(main())
