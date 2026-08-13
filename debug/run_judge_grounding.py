"""Lance le grounding des findings Judge (F-93) en isolation DÉTERMINISTE — 0 LLM.

Usage :
    uv run python debug/run_judge_grounding.py

Contrairement à ``run_judge.py`` (qui appelle le vrai nœud Judge + LLM), ce script
teste UNIQUEMENT le module ``judge_grounding.py`` (port langextract + politique
Option 1) sur des fixtures figées. Itération sub-seconde : couper si erreur,
corriger ``judge_grounding.py``, relancer. Aucun spawn llama-server, aucun GPU.

3 scénarios sur un HTML Bubble Sort réaliste (le genre de fichier qu'un Architect
produit via ``debug/run_architect.py``) :
  1. **ancré**       : finding cite un vrai fragment (``bubbleSort``)     → grounded, conservé.
  2. **inventé**     : finding cite un fragment inventé + ligne 9999      → ungrounded, rétrogradé + flagué.
  3. **prose-only**  : finding en langage naturel (aucun fragment code)   → fail-open grounded, conservé.

Vérifie les invariants de la politique Option 1 : is_approved JAMAIS changé,
finding ancré inchangé, finding inventé rétrogradé d'un cran + flagué ``[ungrounded]``.
"""
import os
import sys
import tempfile

# Ensure UTF-8 output on Windows consoles.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from graph_orchestrator.judge_grounding import (
    apply_grounding,
    extract_code_fragments,
    fragment_is_grounded,
    ground_findings,
    read_source_files,
)
from graph_orchestrator.models import CodeJudgeOutput, Finding


# HTML Bubble Sort réaliste (miroir de ce que le Coder produit sur la spec par défaut
# de run_architect.py). Sert de source contre laquelle ancrer les findings.
BUBBLE_HTML = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><title>Bubble Sort</title></head>
<body>
  <button id="startBtn">Démarrer</button>
  <button id="resetBtn">Réinitialiser</button>
  <input id="speedSlider" type="range" min="1" max="100" value="50">
  <div id="counter">0</div>
  <div id="bars"></div>
<script>
function bubbleSort(arr) {
  for (let i = 0; i < arr.length; i++)
    for (let j = 0; j < arr.length - i - 1; j++)
      if (arr[j] > arr[j+1]) { let t = arr[j]; arr[j] = arr[j+1]; arr[j+1] = t; }
  return arr;
}
let counter = 0;
document.getElementById("startBtn").addEventListener("click", () => { bubbleSort([3,1,2]); });
</script>
</body></html>
"""

# Trois findings : ancré / inventé / prose-only.
FINDING_GROUNDED = Finding(
    severity="high", category="correctness", location="index.html",
    description="La fonction `bubbleSort` ne met pas à jour le compteur de comparaisons.",
)
FINDING_INVENTED = Finding(
    severity="critical", category="security", location="index.html:9999",
    description="Appel à `eval(userInput)` qui permet une injection XSS critique.",
)
FINDING_PROSE = Finding(
    severity="low", category="maintainability", location="index.html",
    description="Le code est peu clair et les noms de variables sont trop courts.",
)


def _print_finding(label: str, f: Finding) -> None:
    flag = "  [ungrounded]" if "[ungrounded" in f.description else ""
    desc = f.description if len(f.description) <= 90 else f.description[:87] + "..."
    print(f"    {label}: severity={f.severity:<8} location={f.location or '(n/a)':<16}{flag}")
    print(f"           {desc}")


def main() -> int:
    print("[*] Judge grounding (F-93) — isolation DÉTERMINISTE (0 LLM, 0 GPU).")
    print(f"    threshold coverage = 0.75 | window cap = 2·len(needle) (densité ≥ ~0.5)")
    print(f"    politique = Option 1 (rétrograde + flag, is_approved INVARIANT)\n")

    # Écrit le HTML source dans un tmp file (simule le run dir).
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8")
    tmp.write(BUBBLE_HTML)
    tmp.close()
    src_path = tmp.name

    try:
        sources = read_source_files([src_path])
        print(f"[+] Source lue : {os.path.basename(src_path)} "
              f"({len(BUBBLE_HTML)} chars, {BUBBLE_HTML.count(chr(10))+1} lignes)\n")

        # Smoke : vérifie qu'un vrai fragment s'ancre et qu'un inventé non.
        print("=== Smoke fragment_is_grounded ===")
        for frag, expect in [("bubbleSort", True), ("eval(userInput)", False), ("speedSlider", True)]:
            got = fragment_is_grounded(BUBBLE_HTML, frag)
            icon = "✅" if got == expect else "❌"
            print(f"  {icon} fragment_is_grounded({frag!r}) = {got} (attendu {expect})")
            if "_FRAG_DEBUG" in os.environ:
                print(f"       fragments extraits de 'bug `bar.sort` ici': "
                      f"{extract_code_fragments('bug `bar.sort` ici')}")
        print()

        findings = [FINDING_GROUNDED, FINDING_INVENTED, FINDING_PROSE]
        verdict_before = CodeJudgeOutput(
            task_id="grounding_iso", is_approved=False,
            final_feedback="3 findings : 1 ancré, 1 inventé, 1 prose-only.",
            findings=findings,
        )

        print("=== Verdict AVANT grounding ===")
        print(f"  is_approved = {verdict_before.is_approved}")
        for f in verdict_before.findings:
            _print_finding("finding", f)
        print()

        report = ground_findings(verdict_before.findings, sources)
        verdict_after = apply_grounding(verdict_before, report)

        print("=== Rapport grounding ===")
        print(f"  total={report.total}  grounded={report.grounded_count}  "
              f"ungrounded={report.ungrounded_count}")
        for item in report.items:
            icon = "✅ grounded  " if item.grounded else "⚠️  ungrounded"
            print(f"  {icon} | {os.path.basename(item.matched_file) if item.matched_file else '(n/a)':<14} | {item.reason}")
        print()

        print("=== Verdict APRÈS grounding (politique Option 1) ===")
        print(f"  is_approved = {verdict_after.is_approved}  "
              f"({'INVARIANT ✅' if verdict_after.is_approved == verdict_before.is_approved else 'CHANGÉ ❌❌'})")
        for f in verdict_after.findings:
            _print_finding("finding", f)
        print()

        # Assertions (non-destructive policy invariants).
        ok = True
        checks = []
        checks.append(("is_approved invariant",
                       verdict_after.is_approved == verdict_before.is_approved))
        # ancré : severity inchangée, pas de flag.
        g = verdict_after.findings[0]
        checks.append(("finding ancré conservé (severity high, pas de flag)",
                       g.severity == "high" and "[ungrounded" not in g.description))
        # inventé : critical→high + flag.
        inv = verdict_after.findings[1]
        checks.append(("finding inventé rétrogradé critical→high + flagué",
                       inv.severity == "high" and "[ungrounded" in inv.description))
        # prose-only : low inchangé, pas de flag (fail-open grounded).
        pro = verdict_after.findings[2]
        checks.append(("finding prose-only conservé (fail-open grounded, pas de flag)",
                       pro.severity == "low" and "[ungrounded" not in pro.description))

        print("=== Invariants politique Option 1 ===")
        for label, passed in checks:
            print(f"  {'✅' if passed else '❌'} {label}")
            ok = ok and passed

        print(f"\n{'='*60}")
        if ok:
            print("🎉 Grounding F-93 valide : politique non-destructive tenue.")
            print("    Le finding inventé est rétrogradé+flagué SANS toucher au verdict.")
        else:
            print("⚠️  Un invariant est violé — corriger judge_grounding.py puis relancer.")
        print(f"{'='*60}")
        return 0 if ok else 1
    finally:
        try:
            os.unlink(src_path)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
