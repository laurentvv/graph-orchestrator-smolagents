"""Lance le nœud PromptRefiner (production) en isolation — meta-prompt avant l'Architect.

Usage :
    uv run python debug/run_prompt_refiner.py              # jeu de prompts vagues par défaut
    uv run python debug/run_prompt_refiner.py "ma demande"  # prompt perso
    uv run python debug/run_prompt_refiner.py @prompts/spec.md  # prompt depuis un fichier

Le PromptRefiner (F-39) reformule le prompt utilisateur brut en spec structurée AVANT
le Router et l'Architect. Pipeline : (1) détection termes vagues (fast/easy/user-friendly)
→ ambiguities_detected ; (2) orientation selon capacités dispo ; (3) structuration
sections fixes (Objectif/Fonctionnalités/Contraintes/Critères) ; (4) complétion légère
SANS inventer de scope.

Appelle DIRECTEMENT execute_prompt_refiner_node de dspy_nodes.py (0 duplication) →
comportement réel : _configure_dspy, PromptRefinerSignature, model_lifecycle (spawn
llama-server REASONING_NO_THINK spec + model_override PROMPT_REFINER_MODEL_ID).

But : itérer en secondes/min sur le PromptRefiner (vérifier qu'il détecte les termes
vagues sans inventer du scope) sans relancer le workflow complet de 30-40 min.
"""
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


# ─── JEU DE TESTS FIGÉ (prompts avec termes vagues, le créneau du PromptRefiner) ─
DEFAULT_PROMPTS = [
    (
        "Termes vagues explicites (fast/user-friendly)",
        "Crée une application web rapide et user-friendly pour gérer mes contacts. "
        "Ça doit être joli et moderne.",
    ),
    (
        "Spec déjà structurée (ne doit PAS déformer)",
        "Crée un visualiseur Bubble Sort en HTML/CSS/JS vanilla (index.html + styles.css "
        "+ script.js). Boutons Démarrer/Réinitialiser, curseur vitesse, compteur "
        "comparaisons. Thème sombre, responsive.",
    ),
    (
        "Demande minimaliste (le PromptRefiner doit structurer sans inventer)",
        "Fais un todo list.",
    ),
]


def _resolve_arg(arg: str) -> str:
    if not arg:
        return arg
    if arg.startswith("@"):
        with open(arg[1:], "r", encoding="utf-8") as f:
            return f.read().strip()
    if os.path.isfile(arg):
        with open(arg, "r", encoding="utf-8") as f:
            return f.read().strip()
    return arg


async def run_one(label: str, prompt: str, settings) -> None:
    from graph_orchestrator.dspy_nodes import execute_prompt_refiner_node

    print(f"\n{'=' * 70}")
    print(f"SCÉNARIO : {label}")
    print(f"  prompt brut : {prompt[:90]}{'...' if len(prompt) > 90 else ''}")
    print(f"{'=' * 70}")

    # reasoning_model=None : ignoré (logging uniquement). Le vrai modèle vient de
    # _run_dspy_node → model_lifecycle(settings.no_think_spec) + model_override.
    result, metrics = await execute_prompt_refiner_node(prompt, None, settings)

    if result is None:
        # Dégradation gracieuse : repli sur prompt brut si LLM down.
        print("  ⚠️  Le PromptRefiner n'a pas retourné de résultat (LLM down → repli brut en prod).")
        return
    print(f"  AMBIGUITÉS : {result.ambiguities_detected or '(aucune)'}")
    print(f"  SPEC REFINÉE :")
    # Indentation pour la lisibilité.
    for line in (result.refined_prompt or "(vide)").splitlines():
        print(f"    {line}")
    if metrics:
        print(f"  MODÈLE  : {metrics.model} ({metrics.duration_s:.1f}s)")


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="PromptRefiner isolation (meta-prompt)")
    parser.add_argument("prompt", nargs="?", default=None,
                        help="Prompt unique (ou @fichier). Sinon : jeu de prompts vagues par défaut.")
    args = parser.parse_args()

    from graph_orchestrator.config import settings

    print("[*] PromptRefiner isolation — PRODUCTION (execute_prompt_refiner_node)")
    print(f"    Modèle (override) : {settings.prompt_refiner_model_id or '(défaut reasoning)'}")
    print(f"    Backend            : {settings.no_think_spec.backend}")
    print(f"    Timeout            : {settings.llm_timeout_s}s")
    print(f"    Refiner enabled    : {settings.prompt_refiner_enabled}")

    if args.prompt:
        prompt = _resolve_arg(args.prompt)
        await run_one("Prompt unique", prompt, settings)
    else:
        for label, prompt in DEFAULT_PROMPTS:
            await run_one(label, prompt, settings)

    print(f"\n{'=' * 70}")
    print("[*] Fin — vérifiez visuellement : ambiguïtés détectées + spec structurée")
    print("    SANS invention de scope (les specs déjà claires ne doivent pas être déformées).")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())
