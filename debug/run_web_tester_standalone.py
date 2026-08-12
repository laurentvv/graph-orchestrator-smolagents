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
    
    # On mock une tache pour l'agent. Cible = bubble sort valide (bouton #start-btn,
    # compteur #counter, barres). La skill web-tester (chargée par défaut) référence des
    # fichiers resources/ via view_file — c'est le chemin qui faisait crashed le Tester
    # en run9 F-90 (modèle confondait view_file avec import os Python). Tâche alignée
    # avec le prompt DevTools-first actuel (navigate_page, pas puppeteer_navigate).
    task = {
        "id": "standalone-test",
        "tech": "web",
        "target_files": ["runs/2026-08-11_2109_bubble_sort_multifile_v6/index.html"],
        "content": (
            "Teste le visualiseur de tri à bulles : (1) navigate_page pour ouvrir la page ; "
            "(2) list_console_messages pour vérifier l'absence d'erreurs JS ; (3) clique sur "
            "le bouton 'Démarrer le tri' ; (4) TEST TEMPOREL : snapshot du compteur de "
            "comparaisons avant clic, attends ~500ms, re-snapshot après — vérifie une "
            "progression PARTIELLE (animation non instantanée) ; (5) take_screenshot. "
            "Verdict PASS/FAIL couvrant : démarrage, animation progressive, compteur."
        ),
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
