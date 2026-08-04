"""Lance le nœud Coder en mode ToolCallingAgent (production) en isolation.

Usage :
    uv run python run_coder_tca.py [description_tache]

Défaut :
    description_tache = Bubble Sort Visualizer (vanilla JS, borné, 1 fichier)

Comparatif CodeAgent : ce script est le RÉFÉRENCE (mode actuel de production). Il
appelle DIRECTEMENT execute_coder_node de nodes.py (0 duplication) — donc il
reproduit fidèlement le comportement réel : run_with_retry, prompt, sauvetage DSPy.
À comparer avec run_coder_codeagent.py (même cahier des charges, mode CodeAgent).

Isolation stricte : écrit EXCLUSIVEMENT dans codeagent_compare/tca/. Le dossier est
nettoyé puis recréé à chaque lancement (write_file from scratch garanti — sinon un
search_replace sur le fichier résiduel fausserait la mesure de durée/tokens/steps).
"""
import asyncio
import os
import shutil
import sys

from dotenv import load_dotenv

load_dotenv()


# 🔒 DOSSIER DE SORTIE HARDCODÉ — disjoint du mode CodeAgent par construction.
# Ne pas rendre configurable : garantit l'isolation stricte entre les 2 modes.
OUT_DIR = "codeagent_compare/tca"
TARGET_FILE = f"{OUT_DIR}/index.html"

DEFAULT_TASK = (
    "Bubble Sort Visualizer — single index.html file. "
    "Visuals: array as vertical bars (divs, height = value), three colors "
    "(default, comparing, sorted), dark mode theme. "
    "Controls: Start Sort button, Reset button, Speed slider. "
    "Live stats: counter for number of comparisons. "
    "Vanilla JavaScript, no external libraries."
)


def _resolve_task_desc(arg: str) -> str:
    """Résout l'argument CLI en description de tâche.

    Si arg commence par '@', on lit le contenu du fichier pointé (permet de
    charger un cahier des charges depuis un fichier sans réécrire le script).
    Sinon, on utilise arg directement comme texte de la tâche.
    """
    if arg.startswith("@"):
        path = arg[1:]
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return arg


def _reset_out_dir() -> None:
    """Nettoie et recrée le dossier de sortie (write_file from scratch garanti).

    ignore_errors=True : ne sort jamais en erreur, même au 1er run (dossier absent)
    ou si des handles de fichiers sont encore ouverts (best-effort).
    """
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.makedirs(OUT_DIR, exist_ok=True)


async def main():
    # Args CLI : description de tâche optionnelle (dossier de sortie TOUJOURS hardcodé).
    # Support @fichier : charge le cahier des charges depuis un fichier (ex: prompts/xxx.md).
    raw_arg = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TASK
    task_desc = _resolve_task_desc(raw_arg)

    # Forcer l'UTF-8 (Windows + accents dans les prompts).
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # 🔒 Isolation stricte : repartir d'un dossier vierge à chaque run.
    _reset_out_dir()

    # Imports paresseux (après load_dotenv pour que .env soit bien chargé).
    from graph_orchestrator.config import settings
    from graph_orchestrator.nodes import build_fast_model, execute_coder_node

    print(f"[*] Coder standalone — MODE ToolCallingAgent (PRODUCTION)")
    print(f"    Dossier sortie  : {os.path.abspath(OUT_DIR)} (isolé, nettoyé)")
    print(f"    Fichier cible   : {TARGET_FILE}")
    print(f"    Modèle FAST     : {settings.fast_model_id}")
    print(f"    Endpoint        : {settings.local_api_base}")
    print(f"    max_steps       : 12 | tempér. : {settings.coder_temperature}")
    print(f"    CAHIER CHARGES  : {task_desc[:80]}...")
    print()

    # Le dictionnaire de tâche reproduit exactement sub_dict du workflow (workflows.py).
    # target_files pointe dans NOTRE dossier dédié → execute_coder_node construit le
    # target_files_instruction qui dit au Coder de créer CE fichier précis.
    task = {
        "id": "tca_standalone",
        "content": task_desc,
        "target_files": [TARGET_FILE],
    }

    fast_model = build_fast_model(settings)
    result, metrics = await execute_coder_node(task, fast_model, settings)

    # Affichage du résultat + métriques comparatives.
    print("\n" + "=" * 60)
    print("RÉSULTAT DU CODER — ToolCallingAgent (production)")
    print("=" * 60)
    if result is None:
        print("[!] Le Coder n'a pas retourné de résultat (crash ou timeout).")
    else:
        print(f"Statut  : {result.status}")
        print(f"Détails :")
        print(result.details or "(vide)")
    print("-" * 60)

    # 🔒 Vérification post-run : le fichier est-il dans le BON dossier ?
    file_exists = os.path.exists(TARGET_FILE)
    file_size = os.path.getsize(TARGET_FILE) if file_exists else 0
    print(f"Fichier créé     : {os.path.abspath(TARGET_FILE)}")
    print(f"  Existe         : {'OUI' if file_exists else 'NON'}")
    print(f"  Taille         : {file_size} octets")
    if metrics:
        print(f"Durée            : {metrics.duration_s:.1f}s")
        print(f"Modèle           : {metrics.model}")
        print(f"Tokens (in/out)  : {metrics.input_tokens} / {metrics.output_tokens}")
    print("=" * 60)
    print("\n→ Comparer avec : uv run python run_coder_codeagent.py")


if __name__ == "__main__":
    asyncio.run(main())
