"""Bataille de modèles reasoning — bench isolé sur les nœuds DSPy.

Compare 2 modèles de raisonnement (ex: Ornith-1.0-9B vs Unsloth Gemma-12B) sur les MÊMES
tâches, en appelant les VRAIES fonctions de production (execute_*_node de dspy_nodes.py).
Le terrain = Bubble Sort (cahier des charges borné, vanilla JS) — identique pour les 2.

Usage :
    uv run python debug/bench_models_reasoning.py <model_A> <model_B>

Exemple :
    uv run python debug/bench_models_reasoning.py \
        hf.co/protoLabsAI/Ornith-1.0-9B-MTP-GGUF:Q4_K_M \
        hf.co/unsloth/gemma-4-12b-it-GGUF:Q4_K_M

Métriques mesurées par modèle et par nœud :
  - Router (think=False) : classification language + durée
  - Architect (think=True) : nombre de sous-tâches + stratégie + durée (le nœud discriminant)
  - Judge (think=False) : verdict + nombre de findings + durée
  - Security (think=False) : is_secure + nombre de findings + durée

Le verdict de la bataille = tableau comparatif + interprétation. Aucun fichier modifié
(le script surcharge settings.reasoning_model_id en RAM, ne touche pas au .env).

NB : le Judge et le Security ont besoin de code sur disque (target_files). On leur fournit
un HTML Bubble Sort embarqué (tempfile) + un rapport Tester simulé, identiques pour les 2.
"""
import asyncio
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# Forcer l'UTF-8 (Windows + accents).
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ─── Terrain neutre : Bubble Sort (cahier des charges + code + inputs simulés) ──
SPEC = """Crée un visualiseur d'algorithme Bubble Sort (tri à bulles) interactif en
HTML/CSS/JS vanilla (un seul fichier index.html). L'interface doit montrer un tableau de
barres verticales qui s'animent pendant le tri. Fonctionnalités : bouton « Démarrer le tri »
(animé pas-à-pas), bouton « Réinitialiser » (nouveau tableau aléatoire), curseur vitesse,
compteur de comparaisons, code couleur (comparaison/trié/non traité). Dark mode, responsive.
"""

# HTML Bubble Sort (correct) pour le Judge/Security — tempfile, identique pour les 2 modèles.
HTML_OK = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><title>Bubble Sort</title></head>
<body>
  <button id="startBtn">Démarrer</button>
  <input id="speedSlider" type="range" min="1" max="100" value="50">
  <span id="counter">0</span>
  <div id="bars"></div>
<script>
function bubbleSort(arr) {
  let n = arr.length, cmp = 0;
  for (let i = 0; i < n; i++)
    for (let j = 0; j < n - i - 1; j++) {
      cmp++;
      if (arr[j] > arr[j+1]) { let t = arr[j]; arr[j] = arr[j+1]; arr[j+1] = t; }
    }
  document.getElementById("counter").textContent = cmp;
  return arr;
}
document.getElementById("startBtn").addEventListener("click", () => {
  bubbleSort([5,2,8,1,4]);
});
document.getElementById("speedSlider").addEventListener("input", (e) => {
  console.log("speed", e.target.value);
});
</script>
</body></html>
"""

# Rapport Tester simulé (pass) — identique pour les 2 modèles.
TEST_PASS = (
    "Statut: SUCCESS. ASSERTIONS: Tri croissant: PASS. Slider vitesse: PASS. "
    "Compteur comparaisons: PASS. ERREURS CONSOLE: aucune."
)


@dataclass
class NodeResult:
    node: str
    ok: bool
    duration_s: Optional[float] = None
    raw_output: str = ""  # résumé lisible du verdict
    error: str = ""


@dataclass
class ModelBench:
    model_id: str
    results: list = field(default_factory=list)

    @property
    def label(self) -> str:
        # Raccourci lisible pour les tableaux.
        m = self.model_id
        return "Ornith-9B" if "ornith" in m.lower() else (
            "Unsloth-12B" if "unsloth" in m.lower() and "12b" in m.lower() else m[:30]
        )


async def _bench_router(model_bench: ModelBench, settings) -> None:
    """Router : classifie SPEC en language. Attendu 'javascript'."""
    from graph_orchestrator.dspy_nodes import execute_router_node
    t0 = time.time()
    try:
        res, metrics = await execute_router_node(SPEC, None, settings)
        dur = time.time() - t0
        if res is None:
            model_bench.results.append(NodeResult("router", False, dur, "", "None (crash/timeout)"))
        else:
            ok = res.language and res.language.lower() in ("javascript", "html")
            model_bench.results.append(NodeResult("router", ok, dur, f"language={res.language!r}"))
    except Exception as e:
        model_bench.results.append(NodeResult("router", False, time.time() - t0, "", str(e)[:200]))


async def _bench_architect(model_bench: ModelBench, settings) -> None:
    """Architect (think=True) : découpe SPEC en sous-tâches. LE nœud discriminant."""
    from graph_orchestrator.dspy_nodes import execute_architect_node
    task = {"id": "bench_arch", "content": SPEC}
    t0 = time.time()
    try:
        res, metrics = await execute_architect_node(task, None, settings)
        dur = time.time() - t0
        if res is None:
            model_bench.results.append(NodeResult("architect", False, dur, "", "None (crash/timeout)"))
        else:
            n = len(res.subtasks)
            strategies = [getattr(st, "strategy", "?") for st in res.subtasks]
            ok = 1 <= n <= 4
            model_bench.results.append(
                NodeResult("architect", ok, dur, f"{n} sous-tâche(s), stratégies={strategies}")
            )
    except Exception as e:
        model_bench.results.append(NodeResult("architect", False, time.time() - t0, "", str(e)[:200]))


async def _bench_judge(model_bench: ModelBench, settings, html_path: str) -> None:
    """Judge : verdict sur HTML_OK + TEST_PASS. Attendu is_approved=True."""
    from graph_orchestrator.dspy_nodes import execute_code_judge_node
    subtask = {"id": "bench_judge", "target_files": [html_path], "original_content": SPEC}
    t0 = time.time()
    try:
        res, metrics = await execute_code_judge_node(subtask, TEST_PASS, None, None, settings)
        dur = time.time() - t0
        if res is None:
            model_bench.results.append(NodeResult("judge", False, dur, "", "None (crash/timeout)"))
        else:
            # HTML_OK est correct + tests pass → attendu approved. Un rejet = trop sévère.
            ok = res.is_approved is True
            model_bench.results.append(
                NodeResult("judge", ok, dur, f"is_approved={res.is_approved}, {len(res.findings)} finding(s)")
            )
    except Exception as e:
        model_bench.results.append(NodeResult("judge", False, time.time() - t0, "", str(e)[:200]))


async def _warmup_model(model_id: str, api_base: str) -> float:
    """Précharge le modèle en VRAM via une inférence triviale (hors timing du bench).

    Ollama charge les modèles à la demande (lazy) : le 1er appel est lent (chargement
    GGUF → VRAM), les suivants sont rapides. Sans warmup, le 1er modèle testé serait
    pénalisé par le chargement, et si les 2 tiennent en VRAM simultanément le 2e serait
    avantagé (déjà chargé par le 1er). On neutralise ça en préchargeant CHAQUE modèle
    juste avant de le bench, et en chronométrant ce chargement séparément (informatif,
    non compté dans le score).

    Retourne la durée du chargement (secondes)."""
    import urllib.request
    import json as _json
    # api_base peut contenir /v1 (config OpenAI-compat) → /api/chat pour Ollama natif.
    base = api_base.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = base + "/api/chat"
    payload = _json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": "ok"}],
        "stream": False,
        "think": False,
        "options": {"num_predict": 1},  # 1 token suffit à charger le modèle
    }).encode("utf-8")
    t0 = time.time()
    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            resp.read()  # consommer la réponse
    except Exception as e:
        # Le warmup peut échouer (modèle non pullé, VRAM insuffisante) — on ne bloque
        # pas le bench pour autant, le nœud concerné échouera de toute façon.
        print(f"  ⚠️  Warmup échoué : {str(e)[:120]}")
    return time.time() - t0


async def _bench_security(model_bench: ModelBench, settings, html_path: str) -> None:
    """Security : audit HTML sain. Attendu is_secure=True."""
    from graph_orchestrator.dspy_nodes import execute_security_reviewer_node
    subtask = {"id": "bench_sec", "target_files": [html_path]}
    t0 = time.time()
    try:
        res, metrics = await execute_security_reviewer_node(subtask, None, settings)
        dur = time.time() - t0
        if res is None:
            model_bench.results.append(NodeResult("security", False, dur, "", "None (crash/timeout)"))
        else:
            # HTML_OK est sain → attendu secure. Un is_secure=False = faux positif.
            ok = res.is_secure is True
            model_bench.results.append(
                NodeResult("security", ok, dur, f"is_secure={res.is_secure}, {len(res.findings)} finding(s)")
            )
    except Exception as e:
        model_bench.results.append(NodeResult("security", False, time.time() - t0, "", str(e)[:200]))


async def run_model(model_id: str, html_path: str) -> ModelBench:
    """Surcharge settings.reasoning_model_id en RAM et fait passer les 4 nœuds."""
    from dataclasses import replace
    from graph_orchestrator.config import settings

    # Surcharge : on crée une copie des settings avec le model_id qu'on veut tester.
    # settings est une frozen dataclass → replace() pour faire une copie modifiée.
    # NB : Router utilise fast_model_id (inchangé) — on teste surtout Architect/Judge/Security
    # qui utilisent reasoning_model_id. Le Router est inclus comme sanity check (même fast model).
    bench = ModelBench(model_id=model_id)

    # Monkey-patch : les nœuds DSPy lisent settings.reasoning_model_id globalement. On patche
    # l'attribut sur l'objet settings (même si frozen, on passe par object.__setattr__).
    original_id = settings.reasoning_model_id
    try:
        object.__setattr__(settings, "reasoning_model_id", model_id)
        print(f"\n{'='*70}\n🤖 MODÈLE : {bench.label} ({model_id})\n{'='*70}")

        print(f"  [0/4] Warmup (chargement VRAM)...")
        w_dur = await _warmup_model(model_id, settings.ollama_reasoning_api_base)
        print(f"        → {w_dur:.1f}s (non compté)")

        print(f"  [1/4] Router (fast, sanity)...")
        await _bench_router(bench, settings)
        print(f"        → {bench.results[-1].raw_output} ({bench.results[-1].duration_s:.1f}s)")

        print(f"  [2/4] Architect (think=True, le discriminant)...")
        await _bench_architect(bench, settings)
        r = bench.results[-1]
        print(f"        → {r.raw_output} ({r.duration_s:.1f}s) {'✅' if r.ok else '❌'}")

        print(f"  [3/4] Judge (verdict sur HTML correct)...")
        await _bench_judge(bench, settings, html_path)
        r = bench.results[-1]
        print(f"        → {r.raw_output} ({r.duration_s:.1f}s) {'✅' if r.ok else '❌'}")

        print(f"  [4/4] Security (audit HTML sain)...")
        await _bench_security(bench, settings, html_path)
        r = bench.results[-1]
        print(f"        → {r.raw_output} ({r.duration_s:.1f}s) {'✅' if r.ok else '❌'}")
    finally:
        object.__setattr__(settings, "reasoning_model_id", original_id)

    return bench


def _print_verdict(a: ModelBench, b: ModelBench) -> None:
    """Tableau comparatif + interprétation de la bataille."""
    nodes = ["router", "architect", "judge", "security"]
    print(f"\n\n{'='*78}")
    print("🏆 TABLEAU DE LA BATAILLE")
    print(f"{'='*78}")
    print(f"{'Nœud':<12} | {'A: ' + a.label:<28} | {'B: ' + b.label:<28}")
    print(f"{'-'*12}-+-{'-'*28}-+-{'-'*28}")
    for node in nodes:
        ra = next((r for r in a.results if r.node == node), None)
        rb = next((r for r in b.results if r.node == node), None)
        def cell(r):
            if r is None:
                return "—"
            dur = f"{r.duration_s:.1f}s" if r.duration_s else "?"
            icon = "✅" if r.ok else "❌"
            return f"{icon} {r.raw_output[:22]} ({dur})"
        print(f"{node:<12} | {cell(ra):<28} | {cell(rb):<28}")

    # Score : 1 point par nœud réussi (+1 bonus si Architect réussi, le + discriminant).
    score_a = sum(1 for r in a.results if r.ok) + (1 if any(r.node == "architect" and r.ok for r in a.results) else 0)
    score_b = sum(1 for r in b.results if r.ok) + (1 if any(r.node == "architect" and r.ok for r in b.results) else 0)
    dur_a = sum(r.duration_s for r in a.results if r.duration_s)
    dur_b = sum(r.duration_s for r in b.results if r.duration_s)

    print(f"\n📊 SCORE (1 pt/nœud réussi + 1 bonus Architect) :")
    print(f"   {a.label}: {score_a}/5 | durée totale {dur_a:.1f}s")
    print(f"   {b.label}: {score_b}/5 | durée totale {dur_b:.1f}s")

    print(f"\n🎯 VERDICT :")
    if score_a > score_b:
        winner = a.label
    elif score_b > score_a:
        winner = b.label
    else:
        # Égalité au score → le + rapide gagne.
        winner = a.label if dur_a <= dur_b else b.label
        print(f"   Égalité au score ({score_a}-{score_b}) → départage à la durée.")
    print(f"   🥇 Vainqueur : {winner}")
    print(f"\n   Interprétation :")
    print(f"   - Architect (think=True) est le test clé : c'est lui qui crashe sur le QAT,")
    print(f"     donc le modèle qui réussit l'Architect SUPPORT le thinking (critère n°1).")
    print(f"   - Judge/Security : un échec = verdict incohérent (trop sévère ou faux positif).")
    print(f"   - La durée importe moins que la justesse (tu as dit 'durée n'a pas d'importance').")


async def main():
    if len(sys.argv) < 3:
        print("Usage: uv run python debug/bench_models_reasoning.py <model_A> <model_B>")
        print("Exemple:")
        print("  uv run python debug/bench_models_reasoning.py \\")
        print("      hf.co/protoLabsAI/Ornith-1.0-9B-MTP-GGUF:Q4_K_M \\")
        print("      hf.co/unsloth/gemma-4-12b-it-GGUF:Q4_K_M")
        sys.exit(1)

    model_a = sys.argv[1]
    model_b = sys.argv[2]

    # HTML tempfile (identique pour les 2 modèles — terrain neutre).
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8")
    f.write(HTML_OK)
    f.close()
    html_path = f.name

    print(f"⚔️  BATAILLE DE MODÈLES REASONING")
    print(f"   A : {model_a}")
    print(f"   B : {model_b}")
    print(f"   Terrain : Bubble Sort (cahier des charges + HTML correct identiques)")
    print(f"   Nœuds testés : Router (sanity) → Architect (think=True, clé) → Judge → Security")

    try:
        bench_a = await run_model(model_a, html_path)
        bench_b = await run_model(model_b, html_path)
        _print_verdict(bench_a, bench_b)
    finally:
        os.unlink(html_path)


if __name__ == "__main__":
    asyncio.run(main())
