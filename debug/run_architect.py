"""Lance le nœud Architect (production) en isolation — découpage + stratégie.

Usage :
    uv run python debug/run_architect.py                       # spec Bubble Sort par défaut
    uv run python debug/run_architect.py "ma spec"              # spec perso
    uv run python debug/run_architect.py @prompts/spec.md       # spec depuis un fichier

L'Architect (F-01/F-15/F-29/F-57) découpe le cahier des charges en sous-tâches, chacune
avec une stratégie (simple/incremental/multifile), des target_files et des skills
sélectionnés (F-57 v3). Pense en raisonnement (think=True). Fait aussi un ReAct
préalable (SkillResearchSignature) qui peut rechercher/installer des skills dynamiques
(F-82) — dégradation gracieuse si pas de token GitHub.

Appelle DIRECTEMENT execute_architect_node de dspy_nodes.py (0 duplication) →
comportement réel : Context7 prefetch + skills statiques + ReAct skill research +
ArchitectSignature, model_lifecycle (spawn llama-server REASONING spec).

But : valider le découpage (1 fichier = 1 sous-tâche, stratégie techno-driven correcte)
sans lancer le Coder ni le workflow complet de 30-40 min.
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


DEFAULT_SPEC = (
    "Crée un visualiseur d'algorithme Bubble Sort interactif en HTML/CSS/JS vanilla, "
    "réparti sur TROIS fichiers séparés : index.html (structure + lien vers le CSS et "
    "le JS), styles.css (tout le style), script.js (toute la logique). Pas de framework "
    "ni de CDN externe.\n\n"
    "L'interface doit montrer un tableau de barres verticales (hauteurs proportionnelles "
    "aux valeurs) qui s'animent pendant le tri. Fonctionnalités attendues :\n"
    "- un bouton « Démarrer le tri » qui lance l'animation pas-à-pas ;\n"
    "- un bouton « Réinitialiser » qui génère un nouveau tableau aléatoire ;\n"
    "- un curseur/slidebar pour régler la vitesse d'animation ;\n"
    "- un compteur affichant le nombre de comparaisons effectuées.\n\n"
    "Contraintes : index.html référence styles.css via <link> et script.js via "
    "<script src>. Le JS accède au DOM via les ids du HTML. Design soigné, thème sombre."
)


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


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Architect isolation (découpage + stratégie)")
    parser.add_argument("spec", nargs="?", default=None,
                        help="Cahier des charges (ou @fichier). Sinon : Bubble Sort par défaut.")
    args = parser.parse_args()

    from graph_orchestrator.config import settings
    from graph_orchestrator.dspy_nodes import execute_architect_node

    spec = _resolve_arg(args.spec) if args.spec else DEFAULT_SPEC

    print("[*] Architect isolation — PRODUCTION (execute_architect_node)")
    print(f"    Modèle REASONING : {settings.reasoning_spec.model}")
    print(f"    Backend           : {settings.reasoning_spec.backend}")
    print(f"    Endpoint          : {settings.local_reasoning_api_base}")
    print(f"    Timeout           : {settings.llm_timeout_s}s")
    print(f"    Spec (extrait)    : {spec[:80]}...")
    print(f"{'=' * 70}")

    # task minimal : l'Architect lit task.get("content"). reasoning_model ignoré (logging).
    task = {"id": "architect_isolation", "content": spec}

    result, metrics = await execute_architect_node(task, None, settings)

    print(f"\n{'=' * 70}")
    print("RÉSULTAT DE L'ARCHITECT — isolation (production)")
    print(f"{'=' * 70}")
    if result is None:
        print("[!] L'Architect n'a pas retourné de résultat (crash ou timeout).")
        return

    print(f"Plan ID            : {result.plan_id}")
    print(f"Architecture globale :")
    for line in (result.global_architecture or "(vide)").splitlines():
        print(f"  {line}")
    print(f"\nSous-tâches ({len(result.subtasks)}) :")
    for i, st in enumerate(result.subtasks, 1):
        print(f"  [{i}] {st.task_id}")
        print(f"      description   : {st.description[:100]}{'...' if len(st.description) > 100 else ''}")
        print(f"      target_files  : {st.target_files}")
        print(f"      stratégie     : {st.strategy}")
        if st.sections:
            print(f"      sections      : {st.sections}")
        if st.skills:
            print(f"      skills        : {st.skills}")
    if metrics:
        print(f"\nMODÈLE : {metrics.model} ({metrics.duration_s:.1f}s)")
    print(f"{'=' * 70}")
    print("[*] Fin — vérifiez : 1 fichier = 1 sous-tâche, stratégie techno-driven")
    print("    (HTML/CSS/JS = multifile par défaut, gros monolithe = incremental).")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())
