"""Lance le nœud Code Judge (production) en isolation — verdict final + findings.

Usage :
    uv run python debug/run_judge.py                # jeu de 4 scénarios par défaut
    uv run python debug/run_judge.py correct        # un seul scénario nommé
    uv run python debug/run_judge.py --fail-closed  # scénario fail-closed (security=None)

Le Code Judge (F-44) décide si la boucle Coder↔Tester s'arrête (is_approved). Rubric
severity F-44 (critical/high/medium/low), IN-DIFF ONLY (F-70), anti-nits, procédure
obligatoire 5 étapes (F-56c), fail-closed si security_res=None (post-mortem run 123955 :
pas d'audit = pas d'approbation, sans appeler le LLM).

Appelle DIRECTEMENT execute_code_judge_node de dspy_nodes.py (0 duplication) →
comportement réel : build_judge_code_block (F-70 IN-DIFF), CodeJudgeSignature (rôles +
invariants F-44 + rubric F-56c), model_lifecycle (spawn REASONING_NO_THINK spec).

But : valider que le Judge approuve le code correct, rejette les bugs subtils (critical),
ne surrélève pas les nits (low), et bloque sans audit sécurité — sans relancer le
workflow complet de 30-40 min.
"""
import argparse
import asyncio
import os
import sys
import tempfile

from dotenv import load_dotenv

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from graph_orchestrator.models import SecurityOutput


# ─── FIXTURES FIGÉES — code (ce que le Coder produit) + test_res + security_res ─
# Le Judge croise 4 sources : code, test_results, security_res, task_requirements.

CODE_CORRECT = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><title>Bubble Sort</title></head>
<body>
  <button id="startBtn">Démarrer</button>
  <button id="resetBtn">Réinitialiser</button>
  <input id="speedSlider" type="range" min="1" max="100" value="50">
  <div id="counter">0</div>
  <div id="bars"></div>
<script>
let arr = [], i = 0, j = 0, comparisons = 0, isSorting = false;
function init() { arr = []; i = 0; j = 0; comparisons = 0; isSorting = false;
  for (let k = 0; k < 10; k++) arr.push(Math.floor(Math.random() * 100) + 10); render(); }
function performStep() {
  if (i < arr.length) {
    if (j < arr.length - i - 1) {
      if (arr[j] > arr[j+1]) { let t = arr[j]; arr[j] = arr[j+1]; arr[j+1] = t; }
      j++; comparisons++; document.getElementById("counter").textContent = comparisons;
    } else { i++; j = 0; }
  } else { isSorting = false; }
  render();
}
document.getElementById("startBtn").addEventListener("click", () => {
  if (!isSorting) { isSorting = true; function loop() { if (isSorting) { performStep(); setTimeout(loop, 110 - speedSlider.value); } } loop(); }
});
document.getElementById("resetBtn").addEventListener("click", init);
init();
</script>
</body></html>
"""

# Code avec bug de logique subtil : le tri ne fonctionne pas (compare au lieu d'échanger).
CODE_BUG = """<script>
function bubbleSort(arr) {
  for (let i = 0; i < arr.length; i++) {
    for (let j = 0; j < arr.length - i - 1; j++) {
      if (arr[j] > arr[j+1]) {
        // BUG : compare au lieu d'échanger — le tableau n'est jamais trié.
        console.log("should swap but don't");
      }
    }
  }
  return arr;
}
</script>
"""

# Code correct mais avec un nit de style (var au lieu de let/const) — ne doit PAS être critical.
CODE_NIT = """<script>
var x = 10;  // nit : var est déprécié, let/const préféré. Mais le code fonctionne.
var y = 20;
console.log(x + y);
</script>
"""

# Task requirements commun à tous les scénarios Bubble Sort.
TASK_REQUIREMENTS = (
    "Bubble Sort visualizer : boutons Démarrer/Réinitialiser, curseur vitesse, "
    "compteur de comparaisons, code couleur des barres, animation pas-à-pas."
)

# test_res simulés : en prod, c'est la sortie du WebTester (dict avec "details").
TEST_PASS = {"status": "success", "details": "All functional assertions passed. 0 console errors."}
TEST_FAIL = {"status": "failure", "details": "Assertion failed: array not sorted after sort. [3,1,2] stayed [3,1,2]."}

# security_res simulés : SecurityOutput (Pydantic). [] = aucune vulnérabilité.
SEC_CLEAN = SecurityOutput(task_id="iso", is_secure=True, vulnerabilities=[], findings=[])
SEC_UNAUDITED = None  # fail-closed path


SCENARIOS = [
    # (name, label, code, test_res, security_res, expect_approved)
    ("correct", "Code correct + tests PASS + security clean", CODE_CORRECT, TEST_PASS, SEC_CLEAN, True),
    ("bug", "Code avec bug logique + tests FAIL", CODE_BUG, TEST_FAIL, SEC_CLEAN, False),
    ("nit", "Code correct mais nit de style + tests PASS", CODE_NIT, TEST_PASS, SEC_CLEAN, True),
    ("fail-closed", "security_res=None → bloqué sans LLM", CODE_CORRECT, TEST_PASS, SEC_UNAUDITED, False),
]


def _write_fixture(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


async def run_one(name: str, label: str, code: str, test_res, security_res, expect_approved: bool, settings) -> bool:
    from graph_orchestrator.dspy_nodes import execute_code_judge_node

    print(f"\n{'=' * 70}")
    print(f"SCÉNARIO : {label}")
    print(f"  attendu : is_approved={'True' if expect_approved else 'False'}")
    print(f"{'=' * 70}")

    path = _write_fixture(code)
    try:
        subtask = {
            "id": "judge_isolation",
            "target_files": [path],
            "original_content": TASK_REQUIREMENTS,
            "git_diff": "",  # iter 1 = full-file rétrocompat
        }
        result, metrics = await execute_code_judge_node(subtask, test_res, security_res, None, settings)

        if result is None:
            print("  ❌ Le Judge n'a pas retourné de résultat (crash ou timeout).")
            return False
        verdict = result.is_approved
        icon = "✅" if verdict == expect_approved else "⚠️"
        print(f"  VERDICT : {icon} is_approved={verdict} (attendu {expect_approved})")
        print(f"  FEEDBACK : {(result.final_feedback or '(vide)')[:150]}")
        if result.findings:
            print(f"  FINDINGS ({len(result.findings)}) :")
            for fd in result.findings:
                print(f"    [{fd.severity}] {fd.category} @ {fd.location or '(n/a)'}")
        if metrics:
            print(f"  MODÈLE  : {metrics.model} ({metrics.duration_s:.1f}s)")
        return verdict == expect_approved
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


async def main():
    parser = argparse.ArgumentParser(description="Code Judge isolation (verdict final)")
    parser.add_argument("scenario", nargs="?", default=None,
                        help="Scénario unique : correct | bug | nit | fail-closed. Sinon : tous.")
    args = parser.parse_args()

    from graph_orchestrator.config import settings

    print("[*] Code Judge isolation — PRODUCTION (execute_code_judge_node)")
    print(f"    Modèle NO_THINK : {settings.no_think_spec.model}")
    print(f"    Backend          : {settings.no_think_spec.backend}")
    print(f"    Endpoint         : {settings.local_api_base}")
    print(f"    Timeout          : {settings.llm_timeout_s}s")

    selected = SCENARIOS
    if args.scenario:
        selected = [s for s in SCENARIOS if s[0] == args.scenario]
        if not selected:
            print(f"[!] Scénario inconnu : {args.scenario}. Choix : {[s[0] for s in SCENARIOS]}")
            return

    results = []
    for name, label, code, test_res, security_res, expect in selected:
        ok = await run_one(name, label, code, test_res, security_res, expect, settings)
        results.append((name, ok))

    print(f"\n{'=' * 70}")
    print("BILAN DE LA VALIDATION")
    print(f"{'=' * 70}")
    all_ok = True
    for name, ok in results:
        print(f"  {'✅' if ok else '⚠️'} {name}")
        if not ok:
            all_ok = False
    if all_ok:
        print("\n🎉 Tous les scénarios concordent avec les verdicts attendus.")
        print("    Le fail-closed (security=None) bloque SANS appeler le LLM (0s).")
    else:
        print("\n⚠️  Certains scénarios divergent — les nœuds LLM sont non-déterministes,")
        print("    mais un code correct+tests PASS qui retourne is_approved=False = faux négatif.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())
