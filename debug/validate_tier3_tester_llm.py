"""V3 — Le Tester LLM valide le fichier (corrigé ou bugué).

Adapté de debug/run_web_tester_standalone.py, CORRIGÉ : ne lit pas FAST_BACKEND_URL
(variable inexistante — le WebTester reconstruit son modèle depuis REASONING_NO_THINK_*
via settings.no_think_spec, le modèle passé en arg est ignoré).

Usage :
    uv run python debug/validate_tier3_tester_llm.py [path/to/index.html]

Sans argument : valide le fichier corrigé par V2 (debug/tier3_validation/index.html).
Avec --buggy : valide le fichier bugué original (doit FAIL grâce à la règle 4 + recette).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

DEFAULT_CORRECTED = "debug/tier3_validation/index.html"
BUGGY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "runs", "2026-08-05_1602_bubble_sort", "index.html",
)

BUBBLE_SORT_SPEC = (
    "Crée un visualiseur de tri à bulles (Bubble Sort) en HTML/CSS/JS vanilla dans un "
    "seul fichier index.html. L'utilisateur doit VOIR l'animation du tri étape par étape : "
    "les barres se comparent puis s'échangent progressivement, avec un délai visible "
    "réglable par un slider de vitesse. Affiche un compteur de comparaisons. Boutons "
    "Démarrer et Réinitialiser. Code couleur : barre en cours de comparaison, barre triée.\n\n"
    "## Fonctionnalités attendues\n"
    "- Animation pas-à-pas visible du tri (délai entre chaque comparaison/échange)\n"
    "- Curseur/slidebar pour régler la vitesse d'animation\n"
    "- Compteur de comparaisons mis à jour en temps réel\n"
    "- Bouton Démarrer le tri\n"
    "- Bouton Réinitialiser\n"
    "- Code couleur (barre comparée, barre triée)\n"
)


async def run_tester(target_file: str, label: str):
    from graph_orchestrator.config import settings
    from graph_orchestrator.testers.web_tester import WebTestRunner

    print(f"\n{'='*70}")
    print(f"  V3 : TESTER LLM — {label}")
    print(f"{'='*70}")
    print(f"  Cible      : {target_file}")
    print(f"  Modèle     : {settings.no_think_spec.model or settings.reasoning_no_think_model_id}")
    print(f"  Backend    : {settings.no_think_spec.backend}")
    print(f"  Max steps  : {settings.tester_max_steps}")
    print(f"  Timeout    : {settings.tester_timeout_s}s")

    if not os.path.exists(target_file):
        print(f"[!] Fichier introuvable : {target_file}")
        return None

    # IMPORTANT : chdir dans le dossier du fichier pour que primary_url file:/// soit juste.
    file_dir = os.path.dirname(os.path.abspath(target_file))
    file_name = os.path.basename(target_file)
    old_cwd = os.getcwd()
    os.chdir(file_dir)
    try:
        # id DOIT être un identifiant Python valide (smolagents l'utilise comme nom d'agent).
        slug = "corrected" if "CORRIGÉ" in label else ("buggy" if "BUGGÉ" in label else "explicit")
        task = {
            "id": f"tier3_test_{slug}",
            "content": (
                f"Teste le fichier {file_name}. Clique sur Démarrer, puis vérifie que "
                f"l'animation progresse VISIBLEMENT dans le temps (pas instantanée). "
                f"Utilise puppeteer_add_visual_tags puis take_screenshot. Écris une "
                f"assertion temporelle (snapshot compteur avant clic, re-snapshot après "
                f"~400ms, vérifie progression partielle)."
            ),
            "target_files": [file_name],
            "original_content": BUBBLE_SORT_SPEC,
            "iteration": 1,
            "router_lang": "javascript",
            "tech": "web",
        }
        runner = WebTestRunner()
        test_output, metrics = await runner.run(task, model=None, settings=settings)
    finally:
        os.chdir(old_cwd)

    print("\n--- Résultat Tester LLM ---")
    if test_output is None:
        print("[!] Tester n'a pas retourné de résultat (timeout/crash).")
        return None
    if isinstance(test_output, str):
        print(f"[!] Timeout/erreur : {test_output[:400]}")
        return None
    print(f"Statut  : {test_output.status}")
    print(f"Détails :\n{(test_output.details or '(vide)')[:1500]}")
    if metrics:
        print(f"\nDurée/tokens : {metrics.duration_s:.1f}s | "
              f"in={metrics.input_tokens} out={metrics.output_tokens}")
    return test_output.status


async def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # Argument : fichier explicite, ou --buggy, ou défaut = fichier corrigé V2.
    if len(sys.argv) > 1 and sys.argv[1] == "--buggy":
        target, label = BUGGY, "BUGGÉ (doit FAIL maintenant)"
    elif len(sys.argv) > 1:
        target, label = sys.argv[1], "EXPLICITE"
    else:
        target, label = DEFAULT_CORRECTED, "CORRIGÉ (doit PASS)"

    status = await run_tester(target, label)

    print(f"\n{'='*70}")
    if status is None:
        print("  BILAN V3 : ⚠️  Tester n'a pas conclu (timeout/crash).")
    elif "BUGGÉ" in label:
        verdict = "✅ OK" if status == "failure" else "❌ Le Tester devrait FAIL"
        print(f"  BILAN V3 (buggé → FAIL attendu) : {verdict} (status={status})")
    else:
        verdict = "✅ OK" if status == "success" else "❌ Le Tester devrait PASS"
        print(f"  BILAN V3 (corrigé → SUCCESS attendu) : {verdict} (status={status})")
    print(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())
