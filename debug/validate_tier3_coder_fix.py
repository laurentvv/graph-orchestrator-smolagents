"""V2 — Le Coder corrige le fichier bugué, guidé par le feedback du Tier 3.

Adapté de debug/test_gate_live_bubble.py. On travaille dans debug/tier3_validation/
(nettoyé puis recréé), en chdir pour que target_files court = index.html.

Le Coder reçoit :
  - Le cahier des charges Bubble Sort (original_content).
  - Le feedback du Tier 3 (refutation) : "performStep contient tout l'algorithme →
    avance d'une seule itération par frame".
  - iteration=2 → mode CORRECTION (read_file + multi_replace, pas rewrite).

La règle 9 (nodes.py) + le paragraphe granularité (skills/coding) doivent pousser le
modèle à corriger performStep en "une itération par frame".

Usage :
    uv run python debug/validate_tier3_coder_fix.py
"""
import asyncio
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

OUT_DIR = "debug/tier3_validation"
TARGET_FILE = f"{OUT_DIR}/index.html"
BUGGY_SOURCE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "runs", "2026-08-05_1602_bubble_sort", "index.html",
)

# Feedback du Tier 3 = réfutation telle que le Coder la recevrait en iter 2 dans le graphe.
TIER3_FEEDBACK = (
    "[STATIC TESTER] BUGS WEB DÉTECTÉS (Static Tester déterministe, 0 LLM) :\n"
    "Fichier index.html :\n"
    "  - [temporal] Animation instantanée détectée : l'action 'startBtn' amène l'état à "
    "son terme (signal 0→435, terminal) en moins de 400 ms, au lieu de progresser sur "
    "plusieurs secondes/frame. Cause typique : la fonction appelée par `requestAnimationFrame` "
    "(ou nommée step/tick/performStep) contient les boucles `for`/`while` complètes de "
    "l'algorithme → tout s'exécute en 1 tick JS. Corrige en n'avançant que d'UNE seule "
    "itération par frame (indices i/j persistés hors de la fonction). Le `delay`/slider "
    "de vitesse doit réellement contrôler le rythme."
)

# Cahier des charges Bubble Sort (version courte = content de la sous-tâche).
BUBBLE_SORT_SPEC = (
    "Crée un visualiseur de tri à bulles (Bubble Sort) en HTML/CSS/JS vanilla dans un "
    "seul fichier index.html. L'utilisateur doit VOIR l'animation du tri étape par étape : "
    "les barres se comparent puis s'échangent progressivement, avec un délai visible "
    "réglable par un slider de vitesse. Affiche un compteur de comparaisons. Boutons "
    "Démarrer et Réinitialiser. Code couleur : barre en cours de comparaison, barre triée."
)


async def run_coder_fix():
    from graph_orchestrator.config import settings
    from graph_orchestrator.nodes import build_fast_model, execute_coder_node

    print(f"\n{'='*70}")
    print("  V2 : CODEUR EN MODE CORRECTION (iteration=2)")
    print(f"{'='*70}")
    print(f"  Cible      : {os.path.abspath(TARGET_FILE)}")
    print(f"  Modèle     : {settings.fast_model_id}")
    print(f"  Backend    : {settings.fast_spec.backend}")
    print(f"  Gate       : {settings.read_before_write_enabled}")
    print()

    # Prépare le dossier : nettoie, recrée, copie le fichier bugué.
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    shutil.copy(BUGGY_SOURCE, TARGET_FILE)
    print(f"  Fichier bugué copié ({os.path.getsize(TARGET_FILE)} octets).")

    # task dict = sub_dict du workflow. iteration=2 → mode correction.
    task = {
        "id": "tier3_fix",
        "content": (
            f"{BUBBLE_SORT_SPEC}\n\n"
            f"### FEEDBACK DU STATIC TESTER (itération précédente)\n"
            f"Corrige le bug suivant sans tout réécrire (utilise read_file puis "
            f"search_replace/multi_replace) :\n{TIER3_FEEDBACK}"
        ),
        "original_content": BUBBLE_SORT_SPEC,
        "target_files": [TARGET_FILE],
        "strategy": "simple",
        "iteration": 2,
        "router_lang": "javascript",
    }

    fast_model = build_fast_model(settings)
    result, metrics = await execute_coder_node(task, fast_model, settings)

    print("\n--- Résultat Coder ---")
    if result is None:
        print("[!] Coder n'a pas retourné de résultat (crash/timeout).")
        return False
    if isinstance(result, str):
        print(f"[!] Timeout/erreur : {result[:300]}")
        return False
    print(f"Statut  : {result.status}")
    print(f"Détails : {(result.details or '(vide)')[:600]}")
    if metrics:
        print(f"Durée/tokens : {metrics.duration_s:.1f}s | "
              f"in={metrics.input_tokens} out={metrics.output_tokens}")
    print(f"Fichier : {os.path.getsize(TARGET_FILE)} octets après correction.")
    return result.status == "success"


async def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    ok = await run_coder_fix()

    # Vérification structurelle : performStep ne doit plus contenir de double boucle.
    print("\n--- Vérification structurelle du fichier corrigé ---")
    if os.path.exists(TARGET_FILE):
        with open(TARGET_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        # Heuristique : la fonction performStep/step ne doit pas contenir 2 boucles for imbriquées.
        import re
        # Cherche le corps de performStep/step/tick/animate.
        m = re.search(r"function\s+(?:performStep|step|tick|animate)\s*\([^)]*\)\s*\{",
                      content, re.IGNORECASE)
        if m:
            start = m.end()
            depth = 1
            j = start
            while j < len(content) and depth > 0:
                if content[j] == "{":
                    depth += 1
                elif content[j] == "}":
                    depth -= 1
                j += 1
            body = content[start:j - 1]
            nb_for = len(re.findall(r"\bfor\s*\(", body))
            nb_while = len(re.findall(r"\bwhile\s*\(", body))
            print(f"Fonction trouvée : {m.group(0)}")
            print(f"Boucles dans le corps : {nb_for} for + {nb_while} while = {nb_for + nb_while}")
            if nb_for + nb_while >= 2:
                print("❌ ÉCHEC : la fonction de step contient encore plusieurs boucles "
                      "(l'algorithme complet). Le Coder n'a pas corrigé.")
            elif nb_for + nb_while == 1:
                print("⚠️  Une boucle — acceptable si elle break/return après une itération, "
                      "mais le pattern idéal est un if/else sans boucle.")
            else:
                print("✅ OK : la fonction de step n'a plus de boucle (pattern if/else = "
                      "une itération par frame).")
        else:
            print("Fonction performStep/step introuvable — vérifier manuellement.")
    else:
        print("Fichier corrigé introuvable.")

    print(f"\n{'='*70}")
    print(f"  BILAN V2 : {'✅ SUCCÈS' if ok else '❌ À EXAMINER'}")
    print(f"{'='*70}")
    print("Prochaine étape : re-run V1 (Static Tester) sur le fichier corrigé pour confirmer.")
    print("Commande : uv run python -c \"")
    print("  from graph_orchestrator.static_tester import execute_static_tester_node")
    print(f"  r,_ = execute_static_tester_node({{'id':'t','target_files':['{TARGET_FILE}']}}, None)")
    print("  print(r.status, r.details[:200])")


if __name__ == "__main__":
    asyncio.run(main())
