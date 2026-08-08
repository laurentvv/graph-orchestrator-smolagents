"""Lance le nœud Router (production) en isolation — classification prompt → langage.

Usage :
    uv run python debug/run_router.py                  # jeu de 5 prompts par défaut
    uv run python debug/run_router.py "ma description de tâche"  # prompt perso
    uv run python debug/run_router.py @prompts/spec.md           # prompt depuis un fichier

Le Router (F-01) est le 1er nœud du workflow : il classifie le prompt utilisateur brut
en langage techno (python / javascript / react / rust / go / etc.). Bug historique
documenté (F-56a) : déborde vers javascript quand le prompt mentionne des mots-clés web
alors que les extensions/contraintes pointent vers python.

Appelle DIRECTEMENT execute_router_node de dspy_nodes.py (0 duplication) → comportement
réel : _configure_dspy, RouterSignature (rôles + invariants F-44 + procédure F-56a),
model_lifecycle (spawn llama-server FAST spec).

But : itérer en secondes/min sur le Router (tester qu'un prompt Python ne déborde plus
vers javascript) sans relancer le workflow complet de 30-40 min.
"""
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Forcer l'UTF-8 (Windows + accents dans les prompts).
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ─── JEU DE TESTS FIGÉ (prompts variés, bug F-56a = déborde vers javascript) ─
# Chaque entrée = (label, prompt, langage attendu). Le verdict n'est pas asserté
# (non-déterministe LLM) mais affiché pour inspection visuelle.
DEFAULT_PROMPTS = [
    (
        "Python (mots-clés web piège)",
        "Crée une API web REST en Python avec Flask qui expose des endpoints JSON pour "
        "gérer une liste de tâches. Le frontend HTML n'est pas demandé.",
        "python",
    ),
    (
        "React (JSX explicite)",
        "Build a dashboard component in React with TypeScript showing real-time stock "
        "prices. Use hooks (useState, useEffect) and styled-components.",
        "javascript",
    ),
    (
        "HTML/CSS/JS vanilla",
        "Crée un visualiseur d'algorithme Bubble Sort en HTML/CSS/JS vanilla sur un seul "
        "fichier index.html. Pas de framework ni de CDN externe.",
        "javascript",
    ),
    (
        "Rust",
        "Écris un programme Rust qui lit un fichier CSV ligne par ligne et calcule la "
        "moyenne de la colonne numérique. Utilise la crate csv et serde.",
        "rust",
    ),
    (
        "Ambigu (aucun mot-clé fort)",
        "Fais un petit outil qui affiche l'heure actuelle avec une interface graphique.",
        "(indéterminé)",
    ),
]


def _resolve_arg(arg: str) -> str:
    """Résout un arg CLI : @fichier → contenu, chemin existant → contenu, sinon texte brut."""
    if not arg:
        return arg
    if arg.startswith("@"):
        with open(arg[1:], "r", encoding="utf-8") as f:
            return f.read().strip()
    if os.path.isfile(arg):
        with open(arg, "r", encoding="utf-8") as f:
            return f.read().strip()
    return arg


async def run_one(label: str, prompt: str, expected: str, settings) -> None:
    """Affiche le contrat + exécute le Router sur UN prompt."""
    from graph_orchestrator.dspy_nodes import execute_router_node

    print(f"\n{'=' * 70}")
    print(f"SCÉNARIO : {label}")
    print(f"  attendu : {expected}")
    print(f"  prompt  : {prompt[:90]}{'...' if len(prompt) > 90 else ''}")
    print(f"{'=' * 70}")

    # fast_model=None : le Router l'ignore (utilisé pour logging uniquement, le vrai
    # modèle vient de _run_dspy_node → model_lifecycle(settings.fast_spec)).
    result, metrics = await execute_router_node(prompt, None, settings)

    if result is None:
        print("  ❌ Le Router n'a pas retourné de résultat (crash ou timeout).")
        return
    detected = result.language
    icon = "✅" if detected.strip().lower() == expected.strip().lower() else "⚠️"
    print(f"  VERDICT : {icon} language={detected!r} (attendu {expected!r})")
    if metrics:
        print(f"  MODÈLE  : {metrics.model} ({metrics.duration_s:.1f}s)")


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Router isolation (classification prompt→langage)")
    parser.add_argument("prompt", nargs="?", default=None,
                        help="Prompt unique (ou @fichier). Sinon : jeu de 5 prompts par défaut.")
    args = parser.parse_args()

    from graph_orchestrator.config import settings

    print("[*] Router isolation — PRODUCTION (execute_router_node)")
    print(f"    Modèle FAST     : {settings.fast_spec.model}")
    print(f"    Backend         : {settings.fast_spec.backend}")
    print(f"    Endpoint        : {settings.local_api_base}")
    print(f"    Timeout         : {settings.llm_timeout_s}s")

    if args.prompt:
        # Mode prompt unique.
        prompt = _resolve_arg(args.prompt)
        await run_one("Prompt unique", prompt, "(vérification visuelle)", settings)
    else:
        # Mode jeu de tests figé.
        for label, prompt, expected in DEFAULT_PROMPTS:
            await run_one(label, prompt, expected, settings)

    print(f"\n{'=' * 70}")
    print("[*] Fin — vérifiez les verdicts ✅/⚠️ ci-dessus.")
    print("    Les nœuds LLM sont non-déterministes : le verdict exact peut varier,")
    print("    mais un prompt Python qui retourne 'javascript' = bug F-56a confirmé.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())
