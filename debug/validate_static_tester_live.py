"""Validation live du Static Tester (F-49) — l'agent JOUE LE CODEUR.

Scénario 1 (HTML corrompu) : le Coder a injecté les 3 bugs connus de la
méthodologie (TS-in-vanilla + slider non branché + barres invisibles).
Le Static Tester DOIT retourner FAILURE avec les 3 bugs nommés.

Scénario 2 (HTML correct) : un bubble sort propre et complet.
Le Static Tester DOIT retourner SUCCESS.

Ce script valide le comportement end-to-end sans lancer tout le workflow.
"""
import os
import tempfile

from graph_orchestrator.static_tester import execute_static_tester_node

# ─── Scénario 1 : HTML corrompu (les 3 bugs de la méthodologie) ─────────────
# Bug 1 : TypeScript dans du vanilla (`: number[]`) → SyntaxError → page blanche.
# Bug 2 : slider non branché (id présent, aucun addEventListener).
# Bug 3 : barres invisibles (.bar height:% sur conteneur sans height).
CORRUPTED_HTML = """<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><title>Bubble Sort</title>
<style>
  #bars { min-height: 400px; display: flex; align-items: flex-end; }
  .bar { height: 80%; margin: 0 2px; background: #4a90d9; }
</style></head>
<body>
  <button id="startBtn">Démarrer</button>
  <input id="speedSlider" type="range" min="1" max="100" value="50">
  <div id="bars"></div>
<script>
function bubbleSort(arr: number[]) {
  for (let i = 0; i < arr.length; i++) {
    for (let j = 0; j < arr.length - i - 1; j++) {
      if (arr[j] > arr[j+1]) { let t = arr[j]; arr[j] = arr[j+1]; arr[j+1] = t; }
    }
  }
  return arr;
}
const startBtn = document.getElementById("startBtn");
const bars = document.getElementById("bars");
startBtn.addEventListener("click", () => {
  for (let i = 0; i < 5; i++) {
    const b = document.createElement("div");
    b.className = "bar";
    bars.appendChild(b);
  }
  bubbleSort([3, 1, 2]);
});
</script>
</body></html>"""

# ─── Scénario 2 : HTML correct (référence, tout doit PASS) ──────────────────
CORRECT_HTML = """<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><title>Bubble Sort</title>
<style>
  #bars { height: 400px; display: flex; align-items: flex-end; }
  .bar { width: 30px; margin: 0 2px; background: #4a90d9; }
</style></head>
<body>
  <button id="startBtn">Démarrer</button>
  <input id="speedSlider" type="range" min="1" max="100" value="50">
  <div id="bars"></div>
<script>
function bubbleSort(arr) {
  for (let i = 0; i < arr.length; i++) {
    for (let j = 0; j < arr.length - i - 1; j++) {
      if (arr[j] > arr[j+1]) { let t = arr[j]; arr[j] = arr[j+1]; arr[j+1] = t; }
    }
  }
  return arr;
}
const startBtn = document.getElementById("startBtn");
const slider = document.getElementById("speedSlider");
const bars = document.getElementById("bars");
slider.addEventListener("input", () => { console.log(slider.value); });
startBtn.addEventListener("click", () => {
  const arr = [5, 2, 8, 1, 4];
  for (let i = 0; i < arr.length; i++) {
    const b = document.createElement("div");
    b.className = "bar";
    b.style.height = (arr[i] * 30) + "px";
    bars.appendChild(b);
  }
  bubbleSort(arr);
});
</script>
</body></html>"""


def run(label, html):
    print(f"\n{'='*70}")
    print(f"SCÉNARIO : {label}")
    print(f"{'='*70}")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        path = f.name
    try:
        res, metrics = execute_static_tester_node({"id": "st1", "target_files": [path]}, settings=None)
        print(f"VERDICT   : {res.status}")
        print(f"TIER      : {metrics.node} (durée {metrics.duration_s:.2f}s, 0 LLM)")
        print(f"DÉTAILS   :\n{res.details}")
        return res.status
    finally:
        os.unlink(path)


if __name__ == "__main__":
    s1 = run("HTML corrompu (3 bugs : TS + slider non-wired + barres invisibles)", CORRUPTED_HTML)
    s2 = run("HTML correct (bubble sort propre et complet)", CORRECT_HTML)

    print(f"\n{'='*70}")
    print("BILAN DE LA VALIDATION")
    print(f"{'='*70}")
    ok1 = s1 == "failure"
    ok2 = s2 == "success"
    print(f"  Scénario 1 (corrompu → FAILURE attendu) : {'✅ OK' if ok1 else '❌ ÉCHEC'} (obtenu: {s1})")
    print(f"  Scénario 2 (correct   → SUCCESS attendu) : {'✅ OK' if ok2 else '❌ ÉCHEC'} (obtenu: {s2})")
    if ok1 and ok2:
        print("\n🎉 VALIDATION RÉUSSIE : le Static Tester discrimine correctement les bugs.")
    else:
        print("\n⚠️  Validation à revoir.")
