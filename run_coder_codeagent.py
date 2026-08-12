"""Lance le nœud Coder en mode CodeAgent (expérimental) en isolation.

Usage :
    uv run python run_coder_codeagent.py [description_tache]

Défaut :
    description_tache = Bubble Sort Visualizer (vanilla JS, borné, 1 fichier)

Comparatif ToolCallingAgent : ce script instancie un CodeAgent smolagents (génération
de Python au lieu de JSON) sur le MÊME cahier des charges que run_coder_tca.py
(qui utilise la fonction de production execute_coder_node). Objectif : mesurer si
CodeAgent est plus robuste que ToolCallingAgent pour le node Coder (la corruption
JSON des gros contenus était la douleur n°1 historique du Coder).

Différences techniques vs ToolCallingAgent :
- Le modèle génère du code Python dans un code block (pas un tool_call JSON).
- Les outils sont appelés comme des fonctions : write_file(path="...", content="...").
- final_answer s'appelle en syntaxe Python : final_answer("texte") ou final_answer({...}).
- Un step = un code block complet (peut enchaîner plusieurs write_file).
- executor_type="local" par défaut : interpréteur AST maison. NON sandboxé OS, mais
  bash_command existe déjà dans les tools → pas de régression sécurité vs la prod.

Isolation stricte : écrit EXCLUSIVEMENT dans codeagent_compare/codeagent/. Le dossier
est nettoyé puis recréé à chaque lancement (write_file from scratch garanti — sinon
un search_replace sur le fichier résiduel fausserait la mesure).
"""
import asyncio
import os
import shutil
import sys

from dotenv import load_dotenv

load_dotenv()


# 🔒 DOSSIER DE SORTIE HARDCODÉ — disjoint du mode TCA par construction.
# Ne pas rendre configurable : garantit l'isolation stricte entre les 2 modes.
OUT_DIR = "codeagent_compare/codeagent"
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


def _extract_coder_output(raw_output):
    """Convertit la valeur retournée par final_answer(...) en CoderOutput.

    CodeAgent permet à final_answer de prendre n'importe quel objet Python. On
    normalise ici (pas de sauvetage DSPy : comparaison honnête, on veut voir l'échec
    brut si échec il y a).

    Cas :
    - dict avec status/details → CoderOutput(**dict).
    - string → tente extract_and_validate (fallback JSON, pour le cas où le modèle
      aurait quand même généré du JSON dans final_answer).
    - autre (None, nombre, objet) → wrap en CoderOutput(success, str(raw_output)).
    """
    from graph_orchestrator.models import CoderOutput, extract_and_validate

    if raw_output is None:
        return CoderOutput(task_id="codeagent_standalone", status="failure",
                           details="final_answer a retourné None (aucun résultat).")

    # dict → validation directe (le modèle a passé un dict structuré à final_answer)
    if isinstance(raw_output, dict):
        try:
            if "task_id" not in raw_output:
                raw_output = {"task_id": "codeagent_standalone", **raw_output}
            return CoderOutput(**raw_output)
        except Exception as e:
            return CoderOutput(task_id="codeagent_standalone", status="failure",
                               details=f"final_answer(dict) invalide : {e} — {raw_output}")

    # string → tente le fallback JSON (extract_and_validate cherche un blob {...})
    if isinstance(raw_output, str):
        validated = extract_and_validate(raw_output, CoderOutput)
        if validated:
            return validated
        # Pas du JSON valide : on wrap pour ne pas perdre l'info
        return CoderOutput(task_id="codeagent_standalone", status="success",
                           details=f"(final_answer non-JSON) {raw_output[:500]}")

    # Autre type (nombre, objet) → wrap
    return CoderOutput(task_id="codeagent_standalone", status="success",
                       details=f"(final_answer {type(raw_output).__name__}) {str(raw_output)[:500]}")


async def _run_codeagent(agent, prompt):
    """Exécute le CodeAgent une fois (pas de retry) et retourne (CoderOutput, métriques).

    Pas de sauvetage DSPy : on veut le comportement brut du modèle pour comparer
    honnêtement avec le TCA (qui, lui, a run_with_retry + sauvetage en prod).
    Si CodeAgent réussit du 1er coup là où le TCA a besoin de retries, c'est un
    argument empirique en faveur de CodeAgent.
    """
    from graph_orchestrator.logging_utils import NodeMetrics

    run_result = await asyncio.to_thread(
        agent.run, prompt, stream=False, return_full_result=True
    )

    # raw_output = valeur passée à final_answer(...) (peut être str, dict, nombre...)
    raw_output = run_result.output if hasattr(run_result, "output") else run_result
    coder_output = _extract_coder_output(raw_output)

    # Métriques (même logique que _metrics_from_run de nodes.py)
    model_id = getattr(getattr(agent, "model", None), "model_id", "?")
    node_name = getattr(agent, "name", "agent")
    duration = in_tok = out_tok = None
    timing = getattr(run_result, "timing", None)
    if timing is not None:
        duration = getattr(timing, "duration", None)
    token_usage = getattr(run_result, "token_usage", None)
    if token_usage is not None:
        in_tok = getattr(token_usage, "input_tokens", None)
        out_tok = getattr(token_usage, "output_tokens", None)

    metrics = NodeMetrics(node=node_name, model=model_id, duration_s=duration,
                          input_tokens=in_tok, output_tokens=out_tok)
    return coder_output, metrics


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

    # Imports paresseux (après load_dotenv).
    from smolagents import CodeAgent, DuckDuckGoSearchTool

    from graph_orchestrator.config import settings
    from graph_orchestrator.nodes import build_fast_model, resolve_verbosity
    from graph_orchestrator.tools import (
        list_directory, read_file, write_file, append_file, edit_file, search_replace,
    )
    from graph_orchestrator.context7_tool import context7_tools
    from graph_orchestrator.skills_loader import build_skills_block

    print("[*] Coder standalone — MODE CodeAgent (EXPÉRIMENTAL)")
    print(f"    Dossier sortie  : {os.path.abspath(OUT_DIR)} (isolé, nettoyé)")
    print(f"    Fichier cible   : {TARGET_FILE}")
    print(f"    Modèle FAST     : {settings.fast_model_id}")
    print(f"    Endpoint        : {settings.local_api_base}")
    print(f"    max_steps       : 12 | tempér. : {settings.coder_temperature}")
    print(f"    CAHIER CHARGES  : {task_desc[:80]}...")
    print()

    # La connexion Context7 doit rester ouverte PENDANT tout le run (comme la prod).
    # Tolérance aux pannes : c7=[] si pas de clé (Bubble Sort = vanilla, dormant de toute façon).
    with context7_tools() as c7_tools:
        # Mêmes outils que le Coder de production (nodes.py:354-355), append_file inclus.
        coder_tools = [list_directory, read_file, write_file, append_file, edit_file,
                       search_replace, DuckDuckGoSearchTool()]
        coder_tools.extend(c7_tools)

        agent = CodeAgent(
            tools=coder_tools,
            model=build_fast_model(settings),  # même modèle FAST (comparaison à conditions égales)
            name="coder_codeagent_standalone",
            description="Agent développeur capable d'explorer le projet, d'écrire, lire, modifier du code.",
            verbosity_level=resolve_verbosity("HIGH"),  # = LogLevel.DEBUG (logs comparables au TCA)
            max_steps=12,  # même borne anti-boucle que la prod
            add_base_tools=False,  # on gère nous-mêmes le set d'outils
        )

        skills_block = build_skills_block(task_desc)

        # Prompt adapté pour CodeAgent : final_answer en SYNTAXE PYTHON (pas JSON).
        # Le modèle génère un code block qui appelle write_file(...) comme une fonction.
        prompt = f"""Tu es un Agent Développeur Senior autonome. Ta mission est d'accomplir la tâche ci-dessous en écrivant du CODE PYTHON qui appelle tes outils.

### PLAN D'ACTION
Suis SCRUPULEUSEMENT le WORKFLOW décrit dans le cahier des charges ci-dessous (s'il impose un
découpage incrémental squelette + append_file section par section, respecte-le à la lettre —
c'est ce qui rend la génération viable). Sinon, crée le fichier via `write_file` puis termine.
Une fois le fichier cible assemblé, appelle `final_answer(...)`.

### ⚠️ FICHIER CIBLE — TU DOIS CRÉER CE FICHIER (priorité absolue)
- {TARGET_FILE}
- `write_file` crée automatiquement les sous-répertoires manquants : appelle `write_file` avec le chemin complet MÊME SI le dossier n'existe pas encore.

### ⚠️ RÈGLE ANTI-BOUCLE (très important)
- NE RE-ÉCRIS JAMAIS avec `write_file` un fichier que tu as déjà créé (ça l'écrase). Pour
  ajouter du contenu, utilise `append_file`.
- Si un outil répond "Successfully wrote" / "Appended ...", l'opération est FAITE — passe à la suivante.
- NE RELIS PAS les fichiers après écriture (ça gaspille des étapes).

### COMMENT APPELER LES OUTILS (syntaxe Python)
Les outils sont des fonctions Python. Appelle-les avec les arguments NOMMÉS directement.
Tu peux enchaîner PLUSIEURS appels d'outils dans UN MÊME bloc de code (c'est l'avantage
du mode CodeAgent) :
```python
# 1. squelette de base (write_file une seule fois)
r = write_file(path="{TARGET_FILE}", content="<!DOCTYPE html>\\n<html>\\n<head>...</head>\\n<body><div id=\\"app\\"></div></body>\\n</html>")
print(r)
# 2. remplir section par section (append_file)
r = append_file(path="{TARGET_FILE}", content="<style>...CSS complet...</style>")
print(r)
r = append_file(path="{TARGET_FILE}", content="<script>...JS partie 1...</script>")
print(r)
# 3. TERMINER — passe un dict à final_answer
final_answer({{"task_id": "codeagent_standalone", "status": "success", "details": "index.html assemblé."}})
```
- `write_file(path, content)` : CRÉE/ÉCRASE un fichier complet (squelette initial, < ~150 lignes).
- `append_file(path, content)` : AJOUTE un bloc à la FIN d'un fichier existant. POUR CONSTRUIRE UN
  GROS FICHIER section par section (write_file squelette puis N append_file). Garde anti-doublon
  intégré (ré-appender le même contenu est détecté et signalé).
- `search_replace(path, old_string, new_string)` : MODIFIE un fichier EXISTANT (matching tolérant). À éviter pour une création from scratch.
- `read_file(path)` : lis le contenu d'un fichier.
- `list_directory(path)` : liste un dossier EXISTANT.
- N'utilise PAS DuckDuckGoSearchTool (trop lent). Bubble Sort = vanilla, aucune lib externe.

### EXIGENCE DE QUALITÉ
AUCUN MOCK OU PLACEHOLDER : implémentation COMPLÈTE, RÉELLE et FONCTIONNELLE. Code prêt pour la production.

{skills_block}

### Contenu de la tâche
{task_desc}
"""

        result, metrics = await _run_codeagent(agent, prompt)

    # Affichage du résultat + métriques comparatives.
    print("\n" + "=" * 60)
    print("RÉSULTAT DU CODER — CodeAgent (expérimental)")
    print("=" * 60)
    print(f"Statut  : {result.status}")
    print("Détails :")
    print(result.details or "(vide)")
    print("-" * 60)

    # 🔒 Vérification post-run : le fichier est-il dans le BON dossier ?
    file_exists = os.path.exists(TARGET_FILE)
    file_size = os.path.getsize(TARGET_FILE) if file_exists else 0
    # Compteur de steps (best-effort : smolagents stocke l'historique dans agent.memory)
    steps_consumed = len(getattr(getattr(agent, "memory", None), "steps", []))
    print(f"Fichier créé     : {os.path.abspath(TARGET_FILE)}")
    print(f"  Existe         : {'OUI' if file_exists else 'NON'}")
    print(f"  Taille         : {file_size} octets")
    if metrics:
        print(f"Durée            : {metrics.duration_s:.1f}s")
        print(f"Modèle           : {metrics.model}")
        print(f"Tokens (in/out)  : {metrics.input_tokens} / {metrics.output_tokens}")
    print(f"Steps consommés  : {steps_consumed} / 12")
    print("=" * 60)
    print("\n→ Comparer avec : uv run python run_coder_tca.py")


if __name__ == "__main__":
    asyncio.run(main())
