"""Validation live du Tier 3 (temporal) du Static Tester — sur le VRAI fichier bugué.

Scénario 1 (buggé) : runs/2026-08-05_1602_bubble_sort/index.html, dont performStep()
    contient les deux boucles imbriquées complètes du bubble sort → tout le tri en 1
    tick JS → animation instantanée. Les Tier 1 (syntaxe valide, wiring OK) et Tier 2
    (barres visibles) PASS ce fichier. Le Tier 3 DOIT le détecter (FAIL).

Scénario 2 (correct) : un bubble sort avec `await sleep` entre swaps (~2 s). Le Tier 3
    ne DOIT PAS le flagguer (pas de faux positif sur une animation légitime).

Ce script valide le comportement end-to-end sans lancer tout le workflow.
Prérequis : Chrome DevTools dispo (sinon le Tier 3 skippe — scénario 1 le signale).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph_orchestrator.static_tester import execute_static_tester_node

# Le vrai fichier bugué diagnostiqué (run 2026-08-05_1602_bubble_sort).
BUGGY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "runs", "2026-08-05_1602_bubble_sort", "index.html",
)

# HTML correct : progression sur ~2 s (await sleep entre swaps), non terminal à 400 ms.
CORRECT_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>.visualization{height:300px;display:flex;align-items:flex-end;background:#eee;padding:4px}
.bar{flex:1;min-width:6px;background:#4a90d9}.bar.sorted{background:#39e6c4}</style>
</head><body>
<div class="visualization" id="visualization"></div>
<button id="startBtn">Démarrer</button>
<div>Comparaisons: <span id="counter">0</span></div>
<script>
let array=[],comparisons=0,sleep=ms=>new Promise(r=>setTimeout(r,ms));
function init(){
  const c=document.getElementById('visualization');c.innerHTML='';array=[];comparisons=0;
  document.getElementById('counter').textContent=0;
  for(let i=0;i<12;i++){const v=Math.floor(Math.random()*100)+1;array.push(v);
    const b=document.createElement('div');b.className='bar';b.style.height=(v*2)+'px';c.appendChild(b);}
}
async function sort(){
  const n=array.length,bars=document.querySelectorAll('.bar');
  for(let i=0;i<n-1;i++){for(let j=0;j<n-i-1;j++){
    comparisons++;document.getElementById('counter').textContent=comparisons;
    if(array[j]>array[j+1]){[array[j],array[j+1]]=[array[j+1],array[j]];
      [bars[j].style.height,bars[j+1].style.height]=[bars[j+1].style.height,bars[j].style.height];}
    await sleep(30);}bars[n-i-1].classList.add('sorted');}
}
document.getElementById('startBtn').addEventListener('click',()=>{sort();});
init();
</script></body></html>"""


def run_buggy():
    """Scénario 1 : le vrai fichier bugué. Tier 3 DOIT retourner failure.

    Retourne (status, details) pour permettre au bilan de vérifier le mot-clé.
    """
    print(f"\n{'='*70}")
    print("SCÉNARIO 1 : fichier bugué du run (performStep = double boucle)")
    print(f"{'='*70}")
    if not os.path.exists(BUGGY_FILE):
        print(f"[!] Fichier introuvable : {BUGGY_FILE}")
        return None, ""
    print(f"Cible : {BUGGY_FILE}")
    res, metrics = execute_static_tester_node(
        {"id": "tier3-buggy", "target_files": [BUGGY_FILE]}, settings=None
    )
    print(f"VERDICT   : {res.status}")
    print(f"DURÉE     : {metrics.duration_s:.2f}s (0 LLM)")
    print(f"DÉTAILS   :\n{res.details}")
    return res.status, res.details


def run_correct(tmp_dir):
    """Scénario 2 : HTML correct (animation ~2s). Tier 3 DOIT retourner success."""
    print(f"\n{'='*70}")
    print("SCÉNARIO 2 : bubble sort correct (await sleep entre swaps, ~2s)")
    print(f"{'='*70}")
    path = os.path.join(tmp_dir, "correct.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(CORRECT_HTML)
    res, metrics = execute_static_tester_node(
        {"id": "tier3-correct", "target_files": [path]}, settings=None
    )
    print(f"VERDICT   : {res.status}")
    print(f"DURÉE     : {metrics.duration_s:.2f}s (0 LLM)")
    print(f"DÉTAILS   :\n{res.details}")
    return res.status, res.details


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        s1, d1 = run_buggy()
        s2, d2 = run_correct(tmp_dir)

    print(f"\n{'='*70}")
    print("BILAN DE LA VALIDATION TIER 3")
    print(f"{'='*70}")
    if s1 is None:
        print("  Scénario 1 : NON EXÉCUTÉ (fichier bugué introuvable).")
        return

    detected = "instantanée" in d1
    ok1 = (s1 == "failure") and detected
    # Scénario 2 OK si success, OU si failure mais SANS le mot-clé instantanée
    # (un autre bug Tier 1/2 peut exister, l'important est l'absence de faux positif Tier 3).
    ok2 = ("instantanée" not in d2)

    print(f"  Scénario 1 (buggé   → FAILURE + 'instantanée' attendu) : "
          f"{'✅ OK' if ok1 else '❌ ÉCHEC'} (status={s1}, mot-clé détecté={detected})")
    print(f"  Scénario 2 (correct  → pas de faux positif Tier 3)      : "
          f"{'✅ OK' if ok2 else '❌ ÉCHEC'} (status={s2})")
    if ok1 and ok2:
        print("\n🎉 VALIDATION RÉUSSIE : le Tier 3 détecte l'animation instantanée sur le "
              "vrai fichier bugué, sans faux positif sur une animation légitime.")
    else:
        print("\n⚠️  Validation à revoir.")


if __name__ == "__main__":
    main()
