import os
import sys
import json
import asyncio

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph_orchestrator.config import load_settings
from graph_orchestrator.dspy_nodes import execute_architect_node

async def main():
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

    # Configure environment
    os.environ["FAST_MODEL_ID"] = "hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL"
    os.environ["REASONING_MODEL_ID"] = "hf.co/google/gemma-4-12B-it-qat-q4_0-gguf:latest"
    os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"
    
    settings = load_settings()
    import dataclasses
    settings = dataclasses.replace(settings, reasoning_model_id="hf.co/google/gemma-4-12B-it-qat-q4_0-gguf:latest")

    # Setup output directory
    output_dir = os.path.join(os.path.dirname(__file__), "out_test_7")
    os.makedirs(output_dir, exist_ok=True)
    os.chdir(output_dir)
    print(f"[*] Workspace: {output_dir}")

    # Load task from tasks.json
    tasks_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tasks.json")
    with open(tasks_path, "r", encoding="utf-8") as f:
        tasks_data = json.load(f)
    
    task = tasks_data.get("coding", [])[0]
    
    print(f"[*] Exécution de l'Architecte pour la tâche: {task['id']}")
    try:
        # None pour reasoning_model (le noeud configure dspy lui-même via _configure_dspy)
        result, metrics = await execute_architect_node(task, None, settings)
        print("\n" + "="*50)
        print("[RESULTAT FINAL ARCHITECTE]")
        print("="*50)
        if result and result.subtasks:
            for i, st in enumerate(result.subtasks):
                print(f"\n--- SOUS-TÂCHE {i+1} ---")
                print(f"Task ID      : {st.task_id}")
                print(f"Strategy     : {st.strategy}")
                print(f"Target files : {st.target_files}")
                print(f"Sections     : {st.sections}")
                print(f"Description  :\n{st.description}")
        else:
            print("Aucun résultat ou subtasks vides.")
    except Exception as e:
        print(f"\n[ERREUR] {e}")

if __name__ == "__main__":
    asyncio.run(main())
