import asyncio
import os
import sys

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from graph_orchestrator.config import load_settings
from graph_orchestrator.nodes import build_fast_model, execute_tester_node

async def main():
    print("[*] Lancement du Web Tester Standalone (Isolation)...")
    
    settings = load_settings()
    
    target_file = sys.argv[1] if len(sys.argv) > 1 else "runs/2026-08-19_0029_tetris_modern_onefile/index.html"
    abs_target = os.path.abspath(target_file)
    target_url = f"file:///{abs_target.replace(os.sep, '/')}"
    
    print(f"[*] Cible : {target_file} ({target_url})")
    
    task = {
        "id": "standalone-tetris-test",
        "tech": "web",
        "target_files": [target_file],
        "content": (
            f"Teste rigoureusement l'application web à l'adresse {target_url} :\n"
            "1. navigate_page pour ouvrir l'application.\n"
            "2. list_console_messages pour vérifier l'absence d'erreurs JS (TypeError, ReferenceError).\n"
            "3. TEST DYNAMIQUE & STATE-DIFFING :\n"
            "   - Capture l'état initial (take_snapshot, position/score).\n"
            "   - Envoie des touches d'action (press_key avec ArrowLeft, ArrowRight, ArrowDown, ArrowUp, Space).\n"
            "   - Évalue par script (evaluate_script) si la pièce bouge, si les collisions fonctionnent, "
            "     et si la fonction lock() empile les 4 blocs au bon endroit sur le plateau (et pas seulement en 0,0).\n"
            "   - Vérifie que la rotation fonctionne et ne crash pas.\n"
            "4. Vérifie les boutons (Pause, Restart/Rejouer) par clics.\n"
            "5. take_screenshot pour le rendu final.\n"
            "6. Conclus par un rapport complet avec statut PASS ou FAIL et la liste exacte des anomalies constatées."
        ),
        "skills": []
    }
    
    print("[*] Initialisation du modèle Fast (Qwen3.5-4B Multimodal)...")
    fast_model = build_fast_model(settings)
    
    print("[*] Lancement du Web Tester...")
    test_output, metrics = await execute_tester_node(task, fast_model, settings)
    
    print("\n" + "="*50)
    print("RÉSULTAT DU WEB TESTER :")
    print("="*50)
    if test_output:
        print(f"Statut : {test_output.status}")
        print("Détails :")
        print(test_output.details or "(aucun détail)")
    else:
        print("Timeout ou erreur : le Tester a renvoyé None.")
        
    if metrics:
        print("\n" + "-"*50)
        print(f"Durée           : {metrics.duration_s:.1f}s")
        print(f"Tokens (in/out) : {metrics.input_tokens} / {metrics.output_tokens}")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
