"""Lance le nœud Security Reviewer (production) en isolation — audit OWASP.

Usage :
    uv run python debug/run_security.py          # jeu de 4 codes (propre/XSS/eval/pickle)
    uv run python debug/run_security.py propre   # un seul scénario nommé

Le Security Reviewer (F-44) audite le code produit pour les vulnérabilités OWASP Top 10.
Sort un verdict is_secure + une liste de vulnérabilités + des Finding (severity, category,
CVSS implicite). Patterns dangereux concrets (F-56d / F-65) : innerHTML/document.write/
eval/os.system/subprocess shell=True/pickle.loads/md5/verify=False/CORS*/debug=True.
Discrimination input externe vs contrôlé (F-56d) pour éviter les faux positifs.

Appelle DIRECTEMENT execute_security_reviewer_node de dspy_nodes.py (0 duplication) →
comportement réel : SecuritySignature (rôles + invariants F-44 + OWASP F-56d),
model_lifecycle (spawn llama-server REASONING_NO_THINK spec, think=False).

But : valider que le Security détecte XSS/eval/pickle sans faux positifs sur du code
propre — sans relancer le workflow complet de 30-40 min.
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


# ─── FIXTURES FIGÉES (codes représentatifs, ce que le Coder produit en vrai) ──

# Code propre : opérations sûres, pas de source externe non contrôlée. Le Security
# DOIT retourner is_secure=True.
CODE_CLEAN = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>App</title></head>
<body>
  <div id="app"></div>
  <button id="btn">Clique</button>
<script>
const app = document.getElementById("app");
document.getElementById("btn").addEventListener("click", () => {
  const total = 1 + 2;  // calcul pur, pas de input externe
  app.textContent = "Résultat : " + total;  // textContent = sûr (pas de parsing HTML)
});
</script>
</body></html>
"""

# XSS via innerHTML sur input externe : le failure mode n°1 du web. Le Security DOIT
# retourner is_secure=False avec une finding category XSS.
CODE_XSS = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>App</title></head>
<body>
  <input id="userInput" type="text" placeholder="Votre nom">
  <div id="output"></div>
<script>
const input = document.getElementById("userInput");
const output = document.getElementById("output");
input.addEventListener("input", () => {
  output.innerHTML = "<b>" + input.value + "</b>";  // innerHTML = XSS (input non échappé)
});
</script>
</body></html>
"""

# eval sur donnée externe : injection de code arbitraire. Le Security DOIT flagguer.
CODE_EVAL = """<script>
// RCE via eval sur paramètre URL — critical.
const params = new URLSearchParams(window.location.search);
const expr = params.get("calc");
const result = eval(expr);  // eval = OWASP A03
console.log("Résultat :", result);
</script>
"""

# pickle.loads sur donnée non contrôlée : désérialisation arbitraire = RCE Python.
CODE_PICKLE = """import pickle
import socket

def load_data(payload: bytes):
    # pickle.loads sur donnée réseau = RCE (__reduce__).
    return pickle.loads(payload)  # OWASP A08/A03

s = socket.socket()
s.bind(("0.0.0.0", 9999))
conn, _ = s.accept()
data = conn.recv(4096)
obj = load_data(data)
"""

SCENARIOS = [
    ("propre", "Code propre (textContent, calcul pur)", CODE_CLEAN, ".html", True),
    ("xss", "XSS via innerHTML sur input externe", CODE_XSS, ".html", False),
    ("eval", "eval() sur paramètre URL (RCE)", CODE_EVAL, ".html", False),
    ("pickle", "pickle.loads sur donnée réseau (RCE Python)", CODE_PICKLE, ".py", False),
]


def _write_fixture(content: str, suffix: str) -> str:
    """Écrit la fixture dans un tempfile et retourne le chemin (nettoyage par l'appelant)."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


async def run_one(label: str, code: str, suffix: str, expect_secure: bool, settings) -> bool:
    from graph_orchestrator.dspy_nodes import execute_security_reviewer_node

    print(f"\n{'=' * 70}")
    print(f"SCÉNARIO : {label}")
    print(f"  attendu : is_secure={'True' if expect_secure else 'False'}")
    print(f"{'=' * 70}")

    path = _write_fixture(code, suffix)
    try:
        subtask = {"id": "security_isolation", "target_files": [path]}
        result, metrics = await execute_security_reviewer_node(subtask, None, settings)

        if result is None:
            print("  ❌ Le Security n'a pas retourné de résultat (crash ou timeout).")
            return False
        verdict_secure = result.is_secure
        icon = "✅" if verdict_secure == expect_secure else "⚠️"
        print(f"  VERDICT : {icon} is_secure={verdict_secure} (attendu {expect_secure})")
        print(f"  VULNÉRABILITÉS : {result.vulnerabilities or '(aucune)'}")
        if result.findings:
            print(f"  FINDINGS ({len(result.findings)}) :")
            for fd in result.findings:
                print(f"    [{fd.severity}] {fd.category} @ {fd.location or '(n/a)'}")
                print(f"      {fd.description[:100]}")
        if metrics:
            print(f"  MODÈLE  : {metrics.model} ({metrics.duration_s:.1f}s)")
        return verdict_secure == expect_secure
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


async def main():
    parser = argparse.ArgumentParser(description="Security Reviewer isolation (OWASP)")
    parser.add_argument("scenario", nargs="?", default=None,
                        help="Scénario unique : propre | xss | eval | pickle. Sinon : tous.")
    args = parser.parse_args()

    from graph_orchestrator.config import settings

    print("[*] Security Reviewer isolation — PRODUCTION (execute_security_reviewer_node)")
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
    for name, label, code, suffix, expect in selected:
        ok = await run_one(label, code, suffix, expect, settings)
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
    else:
        print("\n⚠️  Certains scénarios divergent — les nœuds LLM sont non-déterministes,")
        print("    mais un code propre qui retourne is_secure=False = faux positif à corriger.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())
