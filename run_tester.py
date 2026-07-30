"""Lance le nœud Tester en isolation (sans tout le workflow).

Usage :
    uv run python run_tester.py [fichier_html] [description_tache]

Défauts :
    fichier_html      = bubble_sort/index.html
    description_tache = "Bubble Sort visualizer (vanilla JS, dark mode, barres + 3 couleurs, Start/Reset/Speed, compteur comparaisons)"

Permet d'itérer sur le tester (skill, prompt) sans relancer les ~15 min du workflow
complet (Architect → Coder → Tester → Judge). Le tester reçoit le cahier des charges
complet + le fichier à tester, exactement comme en production.
"""
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()


DEFAULT_HTML = "bubble_sort/index.html"
DEFAULT_TASK = (
    "Bubble Sort Visualizer — single index.html file. "
    "Visuals: array as vertical bars (divs, height = value), three colors "
    "(default, comparing, sorted), dark mode theme. "
    "Controls: Start Sort button, Reset button, Speed slider. "
    "Live stats: counter for number of comparisons. "
    "Vanilla JavaScript, no external libraries."
)


async def main():
    # Args CLI optionnels : fichier HTML + description de la tâche.
    html_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HTML
    task_desc = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_TASK

    if not os.path.exists(html_file):
        print(f"[!] Fichier introuvable : {html_file}")
        sys.exit(1)

    # Forcer l'UTF-8 (Puppeteer/Windows + accents dans les prompts).
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # Construire les settings + le modèle reasoning (comme le workflow).
    from graph_orchestrator.config import settings
    from graph_orchestrator.nodes import build_reasoning_model, execute_tester_node

    print(f"[*] Tester standalone")
    print(f"    Fichier testé     : {html_file} ({os.path.getsize(html_file)} octets)")
    print(f"    Modèle reasoning  : {settings.reasoning_model_id}")
    print(f"    Endpoint          : {settings.ollama_reasoning_api_base}")
    print(f"    CAHIER DES CHARGES : {task_desc[:80]}...")
    print()

    # Le dictionnaire de tâche reproduit exactement sub_dict du workflow.
    # original_content = cahier des charges complet (propagé au tester en prod).
    task = {
        "id": "standalone_test",
        "content": f"Teste le fichier {html_file} généré pour cette sous-tâche.",
        "target_files": [html_file],
        "original_content": task_desc,
        "router_lang": "javascript",
    }

    reasoning_model = build_reasoning_model(settings)
    result, metrics = await execute_tester_node(task, reasoning_model, settings)

    # Affichage du résultat.
    print("\n" + "=" * 60)
    print("RÉSULTAT DU TESTER")
    print("=" * 60)
    if result is None:
        print("[!] Le tester n'a pas retourné de résultat (crash ou timeout).")
    else:
        print(f"Statut  : {result.status}")
        print(f"Détails :")
        print(result.details or "(vide)")
    print("=" * 60)

    if metrics:
        print(f"\nDurée : {metrics.duration_s:.1f}s | Modèle : {metrics.model}")


if __name__ == "__main__":
    asyncio.run(main())
