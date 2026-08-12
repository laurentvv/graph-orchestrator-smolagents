"""Test final live du Read-Before-Write Gate (F-67) sur le vrai prompt Bubble Sort.

Récupère le dernier prompt Architect→Coder pour Bubble Sort (extrait du log du
dernier run réussi) et le rejoue via execute_coder_node (fonction de production
qui contient maintenant le gate).

Scénario : 1 passe sur la stratégie incremental (write_file squelette + N
append_file sections). Valide que le gate ne casse pas le workflow incremental
(append_file est exempté du gate depuis la correction du 2026-08-04 — sinon
chaque append était bloqué → explosion du contexte → crash overflow).

Usage :
    uv run python debug/test_gate_live_bubble.py
"""
import asyncio
import os
import sys

# Pour exécuter depuis la racine du projet.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

OUT_DIR = "debug/gate_test_bubble"
TARGET_FILE = f"{OUT_DIR}/index.html"
PROMPT_FILE = "debug/last_task_content_bubble.txt"


async def _run_coder_pass(task: dict, label: str) -> None:
    """Lance execute_coder_node (gate actif) sur une passe, affiche le résultat."""
    from graph_orchestrator.config import settings
    from graph_orchestrator.nodes import build_fast_model, execute_coder_node

    print(f"\n{'='*70}")
    print(f"  PASSE : {label}")
    print(f"{'='*70}")
    print(f"  Fichier cible : {os.path.abspath(TARGET_FILE)}")
    print(f"  Existe avant  : {os.path.exists(TARGET_FILE)}")
    if os.path.exists(TARGET_FILE):
        print(f"  Taille avant  : {os.path.getsize(TARGET_FILE)} octets")
    print(f"  Modèle FAST   : {settings.fast_model_id}")
    print(f"  Endpoint      : {settings.ollama_api_base}")
    print(f"  Gate actif    : {settings.read_before_write_enabled}")
    print()

    fast_model = build_fast_model(settings)
    result, metrics = await execute_coder_node(task, fast_model, settings)

    print(f"\n--- Résultat {label} ---")
    if result is None:
        print("[!] Coder n'a pas retourné de résultat (crash/timeout).")
    else:
        print(f"Statut  : {result.status}")
        details = (result.details or "(vide)")
        # Détecter un blocage du gate dans les détails/observations.
        gate_blocked = "read_file" in details.lower() and "gate" in details.lower()
        if gate_blocked:
            print("🛑 GATE A BLOQUÉ (détecté dans les détails)")
        print(f"Détails : {details[:800]}")
    print(f"Fichier après : {'OUI' if os.path.exists(TARGET_FILE) else 'NON'}"
          f" ({os.path.getsize(TARGET_FILE) if os.path.exists(TARGET_FILE) else 0} octets)")
    if metrics:
        print(f"Durée/tokens   : {metrics.duration_s:.1f}s | "
              f"in={metrics.input_tokens} out={metrics.output_tokens}")


async def main() -> None:
    # UTF-8 sur Windows.
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # Charger le vrai contenu de sous-tâche (extrait du log du dernier run Bubble Sort).
    if not os.path.exists(PROMPT_FILE):
        print(f"[!] {PROMPT_FILE} introuvable. Lancez d'abord l'extraction.")
        sys.exit(1)
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        task_content = f.read().strip()

    # Le task dict reproduit exactement sub_dict du workflow (workflows.py).
    # strategy=incremental, sections=celles de l'Architect (du checkpoint).
    task = {
        "id": "gate_test_bubble",
        "content": task_content.split("### Contexte global")[0].strip(),
        "original_content": task_content,  # cahier des charges complet
        "target_files": [TARGET_FILE],
        "strategy": "incremental",
        "sections": ["css_styles", "layout_structure", "state_management_and_init",
                     "bubble_sort_algorithm", "animation_engine", "event_listeners"],
        "iteration": 1,
    }

    # 1 PASSE sur la stratégie incremental : write_file(squelette) + N append_file.
    # Valide que le gate ne casse pas le workflow (append_file exempté du gate).
    import shutil
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    task["iteration"] = 1
    task["id"] = "gate_test_bubble"
    await _run_coder_pass(task, "STRATÉGIE INCREMENTAL (write_file + append_file)")

    print("\n" + "=" * 70)
    print("  FIN DU TEST LIVE")
    print("=" * 70)
    if os.path.exists(TARGET_FILE):
        size = os.path.getsize(TARGET_FILE)
        print(f"  ✓ Fichier créé : {TARGET_FILE} ({size} octets)")
        if size > 3000:
            print("  ✓ Taille saine (>3 Ko) — le workflow incremental a complété.")
        else:
            print("  ⚠ Taille faible — vérifier le contenu.")
    else:
        print("  ✗ Fichier NON créé — le workflow a échoué.")


if __name__ == "__main__":
    asyncio.run(main())
