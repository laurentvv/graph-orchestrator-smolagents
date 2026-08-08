"""Lance le nœud Drafter (production) en isolation — logique pure avant le Coder.

Usage :
    uv run python debug/run_drafter.py                          # sous-tâche Bubble Sort par défaut
    uv run python debug/run_drafter.py --strategy incremental   # forcer une stratégie
    uv run python debug/run_drafter.py "ma sous-tâche"          # description perso

Le Drafter génère un brouillon de logique (draft_markdown) à partir de la description
d'une sous-tâche, indépendamment des outils. Ce draft est ensuite consommé par le Coder
(debug/run_coder.py --draft <fichier>) pour injecter la logique dans les fichiers cibles.

Appelle DIRECTEMENT execute_drafter_node de dspy_nodes.py (0 duplication) → comportement
réel : DrafterSignature, model_lifecycle (spawn llama-server REASONING spec, think=True).

But : valider la qualité du brouillon de logique (sans lancer le Coder) puis le réinjecter
dans run_coder.py --draft pour valider le Coder en isolation — la boucle de debug à 2
niveaux (Drafter → Coder) sans le workflow complet de 30-40 min.
"""
import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


OUT_DIR = "debug/drafter_isolation_out"

DEFAULT_SUBTASK = (
    "Crée la logique JavaScript d'un visualiseur Bubble Sort : fonction performStep() "
    "qui fait UNE itération de comparaison/échange par frame (requestAnimationFrame), "
    "variables i/j persistées hors fonction, compteur de comparaisons, boutons "
    "Démarrer/Réinitialiser, curseur de vitesse."
)

DEFAULT_TARGET_FILES = ["script.js"]


async def main():
    parser = argparse.ArgumentParser(description="Drafter isolation (logique pure)")
    parser.add_argument("subtask", nargs="?", default=None,
                        help="Description de la sous-tâche. Sinon : Bubble Sort JS par défaut.")
    parser.add_argument("--strategy", default="simple",
                        choices=["simple", "incremental", "multifile"],
                        help="Stratégie de construction (défaut: simple)")
    parser.add_argument("--files", default=None,
                        help="Fichiers cibles séparés par virgule (défaut: script.js)")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    from graph_orchestrator.config import settings
    from graph_orchestrator.dspy_nodes import execute_drafter_node

    subtask_desc = args.subtask or DEFAULT_SUBTASK
    target_files = args.files.split(",") if args.files else DEFAULT_TARGET_FILES

    print("[*] Drafter isolation — PRODUCTION (execute_drafter_node)")
    print(f"    Modèle REASONING : {settings.reasoning_spec.model}")
    print(f"    Backend           : {settings.reasoning_spec.backend}")
    print(f"    Endpoint          : {settings.local_reasoning_api_base}")
    print(f"    Timeout           : {settings.llm_timeout_s}s")
    print(f"    Stratégie         : {args.strategy}")
    print(f"    Target files      : {target_files}")
    print(f"    Sous-tâche        : {subtask_desc[:80]}...")
    print(f"{'=' * 70}")

    # subtask_dict minimal — reproduit sub_dict du workflow (clés lues par le Drafter).
    subtask_dict = {
        "id": "drafter_isolation",
        "content": subtask_desc,
        "strategy": args.strategy,
        "target_files": target_files,
    }

    result, metrics = await execute_drafter_node(subtask_dict, None, settings)

    print(f"\n{'=' * 70}")
    print("RÉSULTAT DU DRAFTER — isolation (production)")
    print(f"{'=' * 70}")
    if result is None:
        print("[!] Le Drafter n'a pas retourné de résultat (crash ou timeout).")
        return

    # Sauvegarde du draft dans un fichier (pour réinjection dans run_coder.py --draft).
    draft_path = os.path.join(OUT_DIR, "draft_isolation.md")
    with open(draft_path, "w", encoding="utf-8") as f:
        f.write(result.draft_markdown or "")

    draft_lines = len((result.draft_markdown or "").splitlines())
    draft_size = len(result.draft_markdown or "")
    print(f"Draft {draft_size} octets / {draft_lines} lignes")
    print(f"Sauvegardé : {os.path.abspath(draft_path)}")
    print(f"\n--- APERÇU (20 premières lignes) ---")
    for line in (result.draft_markdown or "(vide)").splitlines()[:20]:
        print(f"  {line}")
    if draft_lines > 20:
        print(f"  ... ({draft_lines - 20} lignes supplémentaires)")
    if metrics:
        print(f"\nMODÈLE : {metrics.model} ({metrics.duration_s:.1f}s)")
    print(f"{'=' * 70}")
    print(f"[*] Pour réinjecter ce draft dans le Coder :")
    print(f"    uv run python debug/run_coder.py --draft {draft_path}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())
