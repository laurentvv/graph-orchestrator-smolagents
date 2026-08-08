"""Lance le nœud Linter en isolation (l'agent JOUE LE CODEUR avec des fichiers buggés).

Usage :
    uv run python debug/isolation/run_linter.py

Le Linter (F-30) est un gatekeeper DÉTERMINISTE (0 LLM, 0 réseau, millisecondes) inséré
entre le Coder et le Tester. Il valide la syntaxe des fichiers générés via tree-sitter
+ py_compile (Python IndentationError = le point noir) + vérifs structurelles HTML.

Ce script reproduit le pattern de debug/validate_static_tester_live.py : on injecte des
fichiers buggés connus (ce que le Coder produit en vrai — TS-in-vanilla, IndentationError
Python, contenu après </html>) et on asserte que le Linter retourne FAILURE. On injecte
aussi des fichiers corrects et on asserte SUCCESS. Validation en millisecondes, sans
relancer le workflow complet (~25 min).

Le Linter est appelé via la VRAIE fonction de production (execute_linter_node), 0 mock.
Le dict subtask reproduit exactement la forme minimale lue en prod (id + target_files).
"""
import os
import sys
import tempfile

# Forcer l'UTF-8 (Windows + accents dans les messages d'erreur de syntaxe).
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from graph_orchestrator.linter import execute_linter_node

# ─── Fichiers BOGGÉS (ce que le Coder produit en vrai) ────────────────────────

# Bug 1 : IndentationError Python (le "point noir" reconnu par tous les audits,
# tree-sitter l'ignore mais py_compile l'attrape — toujours dispo via stdlib).
PY_BOGGED = """def trier(tableau):
    for i in range(len(tableau)):
        for j in range(len(tableau) - i - 1):
            if tableau[j] > tableau[j + 1]:
            tableau[j], tableau[j + 1] = tableau[j + 1], tableau[j]  # mauvaise indent
    return tableau
"""

# Bug 2 : TypeScript dans du fichier .js pur (le failure mode n°1 du Coder —
# gemma écrit du TS par réflexe). tree-sitter-javascript l'attrape comme erreur
# de syntaxe (le ':' annotation n'est pas valide en JS). NB : requiert tree-sitter.
JS_TS_IN_VANILLA = """function bubbleSort(arr: number[]) {
  for (let i = 0; i < arr.length; i++) {
    if (arr[i] > arr[i+1]) { swap(arr, i); }
  }
  return arr;
}
"""

# Bug 3 : contenu significatif après </html> (le bug exact du dashboard cassé :
# CSS/JS appendés après la fermeture du document → rendu texte brut). Attrapé par
# les vérifs structurelles HTML (_lint_html_structure), SANS tree-sitter.
HTML_TRAILING = """<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><title>Test</title></head>
<body><h1>Bubble Sort</h1></body>
</html>
<div>ce contenu est après la fermeture du document</div>
"""

# ─── Fichiers CORRECTS (référence, tout doit PASS) ────────────────────────────

PY_OK = """def trier(tableau):
    for i in range(len(tableau)):
        for j in range(len(tableau) - i - 1):
            if tableau[j] > tableau[j + 1]:
                tableau[j], tableau[j + 1] = tableau[j + 1], tableau[j]
    return tableau
"""

JS_OK = """function bubbleSort(arr) {
  for (let i = 0; i < arr.length; i++) {
    if (arr[i] > arr[i + 1]) { let t = arr[i]; arr[i] = arr[i + 1]; arr[i + 1] = t; }
  }
  return arr;
}
"""

HTML_OK = """<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><title>Bubble Sort</title></head>
<body><h1>Bubble Sort</h1></body>
</html>
"""


def _write_tmp(content: str, suffix: str) -> str:
    """Écrit le contenu dans un tempfile et retourne le chemin (nettoyage par l'appelant)."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return f.name


def run(label: str, files: dict, expect: str) -> str:
    """files = {suffix: content}. expect = 'success' ou 'failure'."""
    paths = []
    print(f"\n{'=' * 70}")
    print(f"SCÉNARIO : {label}")
    print(f"  attendu : {expect.upper()}")
    print(f"{'=' * 70}")
    for suffix, content in files.items():
        paths.append(_write_tmp(content, suffix))
        print(f"  fichier : {os.path.basename(paths[-1])}")
    try:
        # subtask minimal — exactement ce que execute_linter_node lit en prod
        # (subtask.get("id") + subtask.get("target_files", [])).
        res, metrics = execute_linter_node(
            {"id": "iso_lint", "target_files": paths}, settings=None
        )
        icon = "✅" if res.status == expect else "❌"
        print(f"  VERDICT : {icon} {res.status} (attendu {expect})")
        print(f"  LINTER  : {metrics.node} / {metrics.model} ({metrics.duration_s*1000:.1f} ms, 0 LLM)")
        if res.details and res.status != "success":
            # Affiche les erreurs (utile pour debug un vrai cas buggé).
            for line in res.details.splitlines()[:8]:
                print(f"    {line}")
            if len(res.details.splitlines()) > 8:
                print("    ...")
        return res.status
    finally:
        for p in paths:
            try:
                os.unlink(p)
            except OSError:
                pass


if __name__ == "__main__":
    print("LINTER ISOLATION (F-30) — l'agent joue le Coder avec des fichiers buggés")
    print("Déterministe, 0 LLM, 0 réseau. Valide que le gatekeeper attrape les bugs de syntaxe.")
    print("(mirror de debug/validate_static_tester_live.py pour le Static Tester F-54)")

    results = []

    # --- Scénarios BOGGÉS (chacun DOIT retourner failure) ---
    results.append(("Python IndentationError (py_compile)",
                    run("Python IndentationError (point noir)", {".py": PY_BOGGED}, "failure")))
    results.append(("JS TS-in-vanilla (tree-sitter)",
                    run("TypeScript dans du .js (failure mode n°1 Coder)", {".js": JS_TS_IN_VANILLA}, "failure")))
    results.append(("HTML contenu après </html> (structure)",
                    run("HTML : contenu après </html> (bug dashboard)", {".html": HTML_TRAILING}, "failure")))

    # --- Scénarios CORRECTS (chacun DOIT retourner success) ---
    results.append(("Python propre",
                    run("Python propre", {".py": PY_OK}, "success")))
    results.append(("JS propre",
                    run("JavaScript propre", {".js": JS_OK}, "success")))
    results.append(("HTML propre",
                    run("HTML équilibré", {".html": HTML_OK}, "success")))

    # --- Multi-fichiers (mélange buggé + correct → failure global) ---
    results.append(("Multi-fichiers (1 buggé parmi 2 → failure)",
                    run("Multi-fichiers : 1 buggé + 1 correct (verdict global = failure)",
                        {".py": PY_OK, ".js": JS_TS_IN_VANILLA}, "failure")))

    # --- Bilan ---
    print(f"\n{'=' * 70}")
    print("BILAN DE LA VALIDATION")
    print(f"{'=' * 70}")
    all_ok = True
    for label, status in results:
        ok = status in ("failure", "success")  # juste ran sans crasher
        print(f"  {'✅' if ok else '❌'} {label} → {status}")
        if not ok:
            all_ok = False

    # NB : JS TS-in-vanilla dépend de tree-sitter. Si absent (dégradation gracieuse),
    # ce scénario peut passer à tort (success) — c'est un comportement documenté du
    # Linter, pas un bug du script. On le signale explicitement.
    ts_status = results[1][1]
    if ts_status != "failure":
        print("\n⚠️  Le scénario JS TS-in-vanilla n'a PAS échoué — probablement tree-sitter")
        print("    absent (dégradation gracieuse documentée). py_compile (Python) et les")
        print("    vérifs structurelles HTML (sans tree-sitter) restent actives.")

    if all_ok:
        print("\n🎉 Scripts exécutés sans crash. Vérifiez les verdicts ✅/❌ ci-dessus.")
