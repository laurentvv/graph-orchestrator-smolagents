"""Isolation F-162 : nœud Tester (runner web) pydantic-ai-harness de PRODUCTION.

Appelle la VRAIE fonction ``graph_orchestrator.tester_pydantic.run_tester_pydantic``
(convention F-89 : 0 mock) sur le LIVRABLE PARFAIT du run #19
(``debug/reference_run_2026-08-18_run19_perfect_deliverable/`` — 3 fichiers,
validé visuellement + fonctionnellement par l'user, AGENTS.md §10). Le flag
TESTER_ENGINE n'est pas nécessaire : l'isolation appelle le module directement ;
en E2E, c'est ``TESTER_ENGINE=pydantic`` qui aiguille WebTestRunner.

Deux scénarios (miroir ``debug/run_judge.py`` scénario nommé) :

  ok   (défaut) : livrable parfait copié tel quel → verdict attendu SUCCESS
                 (prouve l'absence de faux rejet).
  bug           : même livrable MUTÉ — la mise à jour du compteur de
                 comparaisons est retirée (counterEl figé à 0, le bug
                 historique F-110) → verdict attendu FAILURE (prouve la
                 DÉTECTION ; bug purement fonctionnel : 0 erreur console,
                 invisible des gates déterministes, seul le LLM peut le voir).

Contrôles :
  - sortie CoderOutput VALIDÉE nativement (output_type, pas de sauvetage) ;
  - task_id exact ; verdict conforme au scénario (status + details non vides) ;
  - MCP DevTools (+ Puppeteer/Context7 si dispo) réellement exercés —
    observer les logs [MCP] et le récit details (console, critères, visuel) ;
  - tokens & durée (baseline smolagents F-155 : steps 5-20 s, navigate 51 s).

Usage :
    uv run python debug/run_tester.py            # scénario ok (défaut)
    uv run python debug/run_tester.py bug        # scénario bug (compteur figé)
"""

import argparse
import asyncio
import os
import re
import shutil
import sys
import time

from dotenv import load_dotenv

load_dotenv()

# 🔒 DOSSIER DE SORTIE HARDCODÉ — isolation stricte (recréé à chaque run).
OUT_DIR = "debug/tester_pydantic_out"
REF_DIR = "debug/reference_run_2026-08-18_run19_perfect_deliverable"

TARGET_FILES = ["index.html", "styles.css", "script.js"]

# Le bug F-110 : la ligne qui rafraîchit le compteur de comparaisons. Retirée,
# le compteur reste figé à '0' pendant tout le tri (0 erreur console).
_COUNTER_LINE_RE = re.compile(r"^\s*counterEl\.textContent\s*=\s*comparisonCount\.toString\(\);.*$", re.M)

# Même cahier des charges que debug/run_coder_pydantic.py (A/B honnête) —
# servi en original_content (spec racine) pour la checklist F-46/F-82.
SPEC = (
    "Crée un visualiseur d'algorithme Bubble Sort (tri à bulles) interactif en "
    "HTML/CSS/JS vanilla, réparti sur TROIS fichiers séparés : index.html (structure "
    "+ lien vers le CSS et le JS), styles.css (tout le style), script.js (toute la "
    "logique). Pas de framework ni de CDN externe.\n\n"
    "L'interface doit montrer un tableau de barres verticales (hauteurs proportionnelles "
    "aux valeurs) qui s'animent pendant le tri. Fonctionnalités attendues :\n"
    "- un bouton « Démarrer le tri » qui lance l'animation pas-à-pas de Bubble Sort "
    "avec un délai visible entre chaque comparaison/échange ;\n"
    "- un bouton « Réinitialiser » qui génère un nouveau tableau aléatoire ;\n"
    "- un curseur/slidebar pour régler la vitesse d'animation ;\n"
    "- un compteur affichant le nombre de comparaisons effectuées ;\n"
    "- un code couleur clair : barre en cours de comparaison = une couleur, barre déjà "
    "triée = une autre couleur, barres non encore traitées = couleur par défaut.\n\n"
    "Contraintes techniques : index.html doit référencer styles.css via <link> et "
    "script.js via <script src>. Le JS accède au DOM via les ids définis dans le HTML. "
    "Design soigné, responsive, avec un thème sombre (dark mode)."
)

# Critères fonctionnels F-82 façon Architecte (pilotent la checklist du Tester).
FUNCTIONAL_CRITERIA = [
    "Bouton « Démarrer le tri » : lancer le tri pas-à-pas avec délai visible entre chaque comparaison/échange",
    "Bouton « Réinitialiser » : générer un nouveau tableau aléatoire",
    "Curseur de vitesse : modifier la vitesse d'animation en cours de tri",
    "Compteur de comparaisons : incrémenter et AFFICHER le nombre réel de comparaisons pendant le tri",
    "Code couleur : barre en cours de comparaison ≠ barre triée ≠ barre non traitée",
    "Tri correct : après exécution complète, les barres sont ordonnées croissant",
]


def _prepare_out_dir(scenario: str) -> bool:
    """Recrée OUT_DIR avec le livrable de référence (muté si scénario bug)."""
    if not all(os.path.isfile(os.path.join(REF_DIR, f)) for f in TARGET_FILES):
        print(f"[-] Livrable de référence incomplet dans {REF_DIR} — isolation impossible.")
        return False
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    for fname in TARGET_FILES:
        shutil.copy2(os.path.join(REF_DIR, fname), os.path.join(OUT_DIR, fname))
    if scenario == "bug":
        path = os.path.join(OUT_DIR, "script.js")
        with open(path, "r", encoding="utf-8") as f:
            js = f.read()
        mutated, n = _COUNTER_LINE_RE.subn("// (ligne retirée — scénario bug)", js)
        if n == 0:
            print("[-] Mutation bug introuvable (ligne compteur) — scénario impossible.")
            return False
        with open(path, "w", encoding="utf-8") as f:
            f.write(mutated)
        print(f"[*] Scénario bug : {n} ligne(s) compteur retirée(s) — compteur figé à 0 (F-110).")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Isolation Tester pydantic-ai-harness (F-162, phase 3.7)")
    parser.add_argument("scenario", nargs="?", default="ok", choices=["ok", "bug"],
                        help="ok = livrable parfait (attendu SUCCESS) ; bug = compteur figé (attendu FAILURE)")
    args = parser.parse_args()

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if not _prepare_out_dir(args.scenario):
        return 1

    from graph_orchestrator.config import settings

    print("[*] Isolation Tester (runner web) pydantic-ai-harness — F-162 phase 3.7 (PRODUCTION)")
    print(f"    Sortie isolée : {os.path.abspath(OUT_DIR)}")
    print(f"    Scénario     : {args.scenario} (verdict attendu : "
          f"{'SUCCESS' if args.scenario == 'ok' else 'FAILURE'})")
    print(f"    Modèle       : {settings.no_think_spec.model} (no-think 9B)")
    print(f"    gardes socle : {settings.coder_pydantic_guards} | vision : "
          f"{getattr(settings, 'coder_pydantic_vision', True)}")
    print(f"    max steps    : {settings.tester_max_steps} | timeout : {settings.tester_timeout_s}s")
    print()

    # Tâche dict au format production (workflows.py sub_dict → WebTestRunner).
    task = {
        "id": "bs-001",
        "content": "Implémente le visualiseur Bubble Sort complet (3 fichiers : index.html, styles.css, script.js) selon la spec.",
        "target_files": list(TARGET_FILES),
        "original_content": SPEC,
        "functional_test_criteria": list(FUNCTIONAL_CRITERIA),
        "tester_skills": ["web-tester"],
        "iteration": 1,
    }

    from graph_orchestrator.tester_pydantic import run_tester_pydantic

    original_cwd = os.getcwd()
    os.chdir(OUT_DIR)  # miroir du chdir F-40 (le tester navigue/relit en relatif)
    t0 = time.time()
    try:
        tester_output, metrics = asyncio.run(run_tester_pydantic(task, settings))
    finally:
        os.chdir(original_cwd)
    duration = time.time() - t0

    expected = "success" if args.scenario == "ok" else "failure"
    print("\n" + "=" * 60)
    print(f"RÉSULTAT DE L'ISOLATION — Tester pydantic (scénario {args.scenario})")
    print("=" * 60)
    checks: list[tuple[str, bool, str]] = []
    if tester_output is not None:
        print(f"CoderOutput VALIDÉ nativement : task_id={tester_output.task_id}")
        print(f"  status={tester_output.status} (attendu {expected})")
        print(f"  linter_ok={tester_output.linter_ok} vision_ok={tester_output.vision_ok}")
        print(f"  details: {tester_output.details[:400]}")
        checks.append(("sortie CoderOutput validée (native)", True, ""))
        checks.append(("task_id exact", tester_output.task_id == task["id"], tester_output.task_id))
        checks.append((f"verdict == {expected}", tester_output.status == expected, f"obtenu {tester_output.status}"))
        checks.append(("details substantiels (>80 chars)", len(tester_output.details) > 80,
                       f"{len(tester_output.details)} chars"))
    else:
        print("CoderOutput : None (échec du run)")
        checks.append(("sortie CoderOutput validée (native)", False, "None"))
    if metrics is not None:
        print(f"  tokens in/out : {metrics.input_tokens} / {metrics.output_tokens}")
        print(f"  durée noeud   : {metrics.duration_s:.1f}s")
    print(f"  durée totale  : {duration:.1f}s")
    print("-" * 60)
    ok_count = sum(1 for _, ok, _ in checks if ok)
    for name, ok, detail in checks:
        print(f"  [{'✓' if ok else '✗'}] {name} {detail}")
    verdict = "GO" if ok_count == len(checks) else "NO-GO"
    print(f"VERDICT : {verdict} ({ok_count}/{len(checks)} contrôles)")
    print("=" * 60)
    return 0 if verdict == "GO" else 1


if __name__ == "__main__":
    sys.exit(main())
