import json
import asyncio
from graph_orchestrator.context7_tool import fetch_context7_brief
from graph_orchestrator.dspy_nodes import _mentions_external_lib

def main():
    # 1. Lire le prompt dans tasks.json
    try:
        with open("tasks.json", "r", encoding="utf-8") as f:
            tasks_data = json.load(f)
            # On prend la première tâche de coding
            task_content = tasks_data.get("coding", [])[0].get("content", "")
    except Exception as e:
        print(f"Erreur de lecture de tasks.json: {e}")
        return

    print("=== PROMPT EXTRAIT DE tasks.json ===")
    print(task_content[:200] + "...\n")
    
    # 1.5. On ajoute volontairement un mot clé pour forcer le déclenchement
    task_content += " On utilisera Tailwind CSS pour le style."

    # 2. Vérifier si ça trigger le pre-fetch
    if _mentions_external_lib(task_content):
        print("[+] Déclenchement de Context7 détecté ! Simulation du pré-fetch...\n")
        
        # Le fetch est synchrone (bloquant dans context7_tool, ou asynchrone dans asyncio.to_thread)
        # Ici fetch_context7_brief est synchrone
        brief = fetch_context7_brief(task_content)
        
        if brief:
            print("=== BRIEF GÉNÉRÉ PAR CONTEXT7 (Injecté à l'Architecte) ===")
            print(brief)
        else:
            print("[-] fetch_context7_brief a renvoyé une chaîne vide (pas de lib trouvée ou erreur réseau).")
    else:
        print("[-] Le prompt ne mentionne pas de librairie externe reconnue (framework). Context7 ignoré.")

if __name__ == "__main__":
    main()
