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
    output_dir = os.path.join(os.path.dirname(__file__), "out_test_3")
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
        name=f"coder_skills_{task['id']}",
        description="Agent développeur capable d'explorer le projet, d'écrire, lire, modifier du code.",
        verbosity_level=resolve_verbosity("HIGH"),
        max_steps=12,
        add_base_tools=False,
    )
    
    from graph_orchestrator.prompts import build_role_header
    from graph_orchestrator.skills_loader import build_skills_block

    target_files_instruction = ""
    if "target_files" in task and task["target_files"]:
        files_list = "\n".join([f"- {f}" for f in task["target_files"]])
        target_files_instruction = f"""
### ⚠️ FICHIERS CIBLES — TU DOIS CRÉER CES FICHIERS (priorité absolue)
{files_list}

- 'write_file' crée automatiquement les sous-répertoires manquants.
- Chaque fichier cible DOIT être créé. Ne passe pas au reste avant."""

    strategy_block = """### WORKFLOW (stratégie SIMPLE)
1. write_file(path=..., content=...) pour créer le fichier cible (contenu complet).
2. final_answer quand c'est terminé."""

    skills_block = build_skills_block(task.get("content", ""))

    prompt = f"""{build_role_header("coder")}
Tu DOIS produire du code en appelant tes outils via du PYTHON (CodeAgent). NE JAMAIS expliquer sans agir.

### RÈGLES CRITIQUES (numérotées)
1. AGIS, ne raconte pas : quand tu dis "je vais faire X", tu DOIS faire X dans la foulée.
   Une réponse sans appel d'outil est considérée comme une TÂCHE TERMINÉE (échec).
2. BLOCS COMPLETS : chaque appel write_file/append_file doit contenir un bloc SYNTAXIQUEMENT
   COMPLET (quotes/braces/parenthèses équilibrées). NE JAMAIS laisser une string/brace
   ouverte entre 2 appels. Si le contenu dépasse ~60 lignes, DÉCOUPE en plusieurs append_file.
3. PAS DE PLACEHOLDER : interdiction absolue de "TODO", "...", "Logique ici", fonctions vides
   ou mocks. Implémentation COMPLÈTE, RÉELLE et FONCTIONNELLE.
4. ANTI-BOUCLE : NE RE-ÉCRIS JAMAIS avec write_file un fichier déjà créé (ça l'écrase).
   Pour AJOUTER du contenu → append_file. Pour MODIFIER un fragment → search_replace.

### FORMAT DE SORTIE (obligatoire)
Tu écris du code Python dans un bloc ```python``` qui appelle tes outils. Exemple one-shot :
```python
# Thought courte (1 phrase) PUIS appel immédiat — pas de longue réflexion
resultat = write_file(path="index.html", content="<!DOCTYPE html>\\n<html>...</html>")
print(resultat)
# ... autres appels ...
final_answer({{"task_id": "{task['id']}", "status": "success", "details": "Fichiers créés."}})
```

{strategy_block}
{target_files_instruction}

### OUTILS DISPONIBLES
- `write_file(path, content)` : CRÉE/ÉCRASE un fichier complet. Sous-dossiers créés auto.
- `append_file(path, content)` : AJOUTE un bloc à la FIN d'un fichier existant (garde anti-doublon).
- `search_replace(path, old_string, new_string)` : MODIFIE un fragment (matching tolérant). À utiliser après read_file.
- `read_file(path)` / `list_directory(path)` : lecture/exploration.

### EXIGENCE DE QUALITÉ
Code prêt pour la production, respectant les conventions du langage.
{skills_block}

### Contenu de la tâche
{task['content']}

### RAPPEL (récence)
- AGIS via des appels d'outils Python, ne raconte pas.
- Chaque bloc syntaxiquement complet, ≤ 60 lignes ou découpe via append_file.
- AUCUN placeholder. final_answer quand les fichiers cibles sont créés.
"""

    print(f"[*] Démarrage de l'agent improved prompt pour la tâche: {task['id']}")
    try:
        result = local_coder.run(prompt)
        print("\n[RESULTAT FINAL]")
        print(result)
    except Exception as e:
        print(f"\n[ERREUR] {e}")

if __name__ == "__main__":
    main()
