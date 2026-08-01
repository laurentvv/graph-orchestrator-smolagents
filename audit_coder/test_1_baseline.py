import os
import sys
import json

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smolagents import CodeAgent
from graph_orchestrator.tools import list_directory, read_file, write_file, append_file, edit_file, search_replace
from graph_orchestrator.config import load_settings
from graph_orchestrator.workflows import build_fast_model
from graph_orchestrator.nodes import resolve_verbosity

def main():
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

    # Force GPU model for fast model (coder)
    os.environ["FAST_MODEL_ID"] = "hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL"
    os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"
    
    # Setup output directory
    output_dir = os.path.join(os.path.dirname(__file__), "out_test_1")
    os.makedirs(output_dir, exist_ok=True)
    os.chdir(output_dir)
    print(f"[*] Workspace: {output_dir}")

    # Load settings and model
    settings = load_settings()
    fast_model = build_fast_model(settings)

    # Load task from tasks.json
    tasks_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tasks.json")
    with open(tasks_path, "r", encoding="utf-8") as f:
        tasks_data = json.load(f)
    
    task = tasks_data.get("coding", [])[0]
    
    # Baseline tools
    coder_tools = [list_directory, read_file, write_file, append_file, edit_file, search_replace]
    
    # Instantiate CodeAgent
    local_coder = CodeAgent(
        tools=coder_tools,
        model=fast_model,
        name=f"coder_baseline_{task['id']}",
        description="Agent développeur capable d'explorer le projet, d'écrire, lire, modifier du code.",
        verbosity_level=resolve_verbosity("HIGH"),
        max_steps=12,
        add_base_tools=False,
    )
    
    # Baseline prompt (minimal, without F-32 improvements)
    target_files_instruction = ""
    if "target_files" in task and task["target_files"]:
        files_list = "\n".join([f"- {f}" for f in task["target_files"]])
        target_files_instruction = f"""
Tu dois créer ces fichiers:
{files_list}
"""

    prompt = f"""Tu es un agent développeur. Tu écris du code Python pour utiliser tes outils.

{target_files_instruction}

Contenu de la tâche :
{task['content']}

Utilise les outils pour créer le projet. Quand c'est fini, utilise final_answer().
"""

    print(f"[*] Démarrage de l'agent baseline pour la tâche: {task['id']}")
    try:
        result = local_coder.run(prompt)
        print("\n[RESULTAT FINAL]")
        print(result)
    except Exception as e:
        print(f"\n[ERREUR] {e}")

if __name__ == "__main__":
    main()
