"""Tests unitaires du Static Tester (F-49) — gatekeeper déterministe web.

Déterministes, 0 LLM, 0 réseau. Stratégie = test_linter.py : vrais fichiers
via tmp_path, zéro mock (sauf cas node/Chrome absents).

L'AGENT JOUE LE CODEUR : chaque test écrit un HTML « comme le Coder le ferait »,
avec un bug injecté connu, et asserte que le Static Tester l'attrape. Les checks
sont GÉNÉRIQUES (marchent sur n'importe quel HTML, pas seulement Bubble Sort) —
on utilise Bubble Sort comme cas concret car c'est le bug observé en vrai.

Couverture :
- Tier 1a : node --check (TS-in-vanilla = bug n°1, accolade non fermée).
- Tier 1b : wiring addEventListener (slider non branché = piège n°1).
- Tier 1b : tolérances légitimes (onclick inline, submit natif, a[href]).
- Tier 2 : visibilité DOM (barres invisibles = bug CSS height:%) — skip si Chrome absent.
- Dégradation : node absent, Chrome absent, non-HTML pass-through, opt-out flag.
- Extraction JS : skip des <script src> externes.
"""

import pytest

from graph_orchestrator.static_tester import (
    execute_static_tester_node,
    static_check_html,
    extract_all_js,
    _check_js_syntax,
    _check_event_wiring,
    _detect_html,
)


def _write(tmp_path, name, content):
    """Helper : écrit un fichier de test et retourne son chemin absolu."""
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return str(f)


# HTML Bubble Sort valide complet (référence = tout doit PASS).
# Sert de base qu'on corrompt ensuite pour chaque test de bug.
VALID_BUBBLE_SORT = """<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><title>Bubble Sort</title>
<style>
  #bars { height: 400px; display: flex; align-items: flex-end; }
  .bar { background: #4a90d9; margin: 0 2px; }
</style></head>
<body>
  <button id="startBtn">Démarrer</button>
  <button id="resetBtn">Réinitialiser</button>
  <input id="speedSlider" type="range" min="1" max="100" value="50">
  <div id="counter">Comparaisons : 0</div>
  <div id="bars"></div>
<script>
const startBtn = document.getElementById("startBtn");
const resetBtn = document.getElementById("resetBtn");
const slider = document.getElementById("speedSlider");
const bars = document.getElementById("bars");
let comparisons = 0;

function renderArray(arr) {
  bars.innerHTML = "";
  arr.forEach(v => {
    const bar = document.createElement("div");
    bar.className = "bar";
    bar.style.height = (v * 3) + "px";
    bars.appendChild(bar);
  });
}
function bubbleSort(arr) {
  for (let i = 0; i < arr.length; i++) {
    for (let j = 0; j < arr.length - i - 1; j++) {
      comparisons++;
      if (arr[j] > arr[j+1]) { let t = arr[j]; arr[j] = arr[j+1]; arr[j+1] = t; }
    }
  }
  return arr;
}
startBtn.addEventListener("click", () => { bubbleSort([3,1,2]); });
resetBtn.addEventListener("click", () => { renderArray([3,1,2]); });
slider.addEventListener("input", () => { console.log(slider.value); });
renderArray([3,1,2]);
</script>
</body></html>"""


# ==========================================
# Détection HTML (extension)
# ==========================================
def test_detect_html_extensions():
    assert _detect_html("page.html") is True
    assert _detect_html("page.htm") is True
    assert _detect_html("script.js") is False
    assert _detect_html("app.py") is False


# ==========================================
# Extraction JS inline
# ==========================================
def test_extract_all_js_basic():
    assert extract_all_js("<script>let x = 1;</script>") == "let x = 1;"


def test_extract_all_js_skips_external_src():
    """Un <script src='app.js'> ne doit PAS être extrait (code externe indispo)."""
    html = '<script src="app.js"></script><script>let y = 2;</script>'
    js = extract_all_js(html)
    assert "let y = 2;" in js
    assert "app.js" not in js


def test_extract_all_js_multiple_blocks():
    html = "<script>a()</script><script>b()</script>"
    assert "a()" in extract_all_js(html)
    assert "b()" in extract_all_js(html)


def test_extract_all_js_empty_when_no_script():
    assert extract_all_js("<html><body><h1>Hi</h1></body></html>") == ""


# ==========================================
# Tier 1a — node --check (le bug n°1 : TS-in-vanilla)
# ==========================================
def test_ts_annotation_in_script(tmp_path):
    """Le bug n°1 du Coder : annotation TypeScript dans du JS vanilla.
    `function sort(arr: number[])` → SyntaxError → page blanche."""
    html = """<html><body><script>
function bubbleSort(arr: number[]) {
  return arr;
}
</script></body></html>"""
    errs = _check_js_syntax(html)
    assert len(errs) == 1
    assert "node --check" in errs[0]
    assert "SyntaxError" in errs[0]


def test_ts_as_cast_in_script(tmp_path):
    """Autre TS-in-vanilla : `as Cast`."""
    html = "<script>const el = document.getElementById('x') as HTMLDivElement;</script>"
    errs = _check_js_syntax(html)
    assert len(errs) == 1
    assert "SyntaxError" in errs[0]


def test_unclosed_brace_in_script():
    """Accolade non fermée → SyntaxError (le Coder coupe parfois la génération)."""
    html = "<script>function foo() { return 1; </script>"
    js = extract_all_js(html)
    errs = _check_js_syntax(js)
    assert len(errs) >= 1
    assert "SyntaxError" in errs[0]


def test_valid_js_syntax_passes():
    """JS vanilla valide → 0 erreur."""
    html = "<script>function foo() { return 1; } foo();</script>"
    js = extract_all_js(html)
    assert _check_js_syntax(js) == []


def test_no_script_no_error():
    """HTML sans JS → rien à valider."""
    js = extract_all_js("<html><body><h1>Hello</h1></body></html>")
    assert _check_js_syntax(js) == []


# ==========================================
# Tier 1b — Wiring addEventListener (le piège n°1)
# ==========================================
def test_slider_not_wired():
    """Le piège n°1 : <input id='speedSlider'> existe mais AUCUN handler.
    Slider visible mais inactif = indétectable par screenshot."""
    html = """<html><body>
<input id="speedSlider" type="range" min="1" max="100">
<script>function init() { console.log("ready"); } init();</script>
</body></html>"""
    js = extract_all_js(html)
    errs = _check_event_wiring(html, js)
    assert len(errs) == 1
    assert "input" in errs[0].lower() and "speedSlider" in errs[0]


def test_button_not_wired():
    """Bouton avec id mais aucun handler → flagged."""
    html = """<html><body>
<button id="startBtn">Start</button>
<script>console.log("page loaded");</script>
</body></html>"""
    js = extract_all_js(html)
    errs = _check_event_wiring(html, js)
    assert len(errs) == 1
    assert "button" in errs[0].lower() and "startBtn" in errs[0]


def test_slider_wired_via_getElementById():
    """Slider branché via getElementById + addEventListener → 0 erreur."""
    html = """<html><body>
<input id="speedSlider" type="range">
<script>
const s = document.getElementById("speedSlider");
s.addEventListener("input", () => {});
</script></body></html>"""
    js = extract_all_js(html)
    assert _check_event_wiring(html, js) == []


def test_button_wired_inline_onclick():
    """onclick inline = branchement légitime → toléré."""
    html = '<html><body><button id="b" onclick="doThing()">Go</button></body></html>'
    js = extract_all_js(html)
    assert _check_event_wiring(html, js) == []


def test_submit_button_in_form_not_flagged():
    """<button type='submit'> dans un form = submit natif → pas besoin de JS."""
    html = """<html><body>
<form action="/save">
  <input name="q" type="text">
  <button type="submit">Envoyer</button>
</form></body></html>"""
    js = extract_all_js(html)
    assert _check_event_wiring(html, js) == []


def test_link_with_href_not_flagged():
    """<a href='...'> = navigation native → pas besoin de JS."""
    html = '<html><body><a href="https://example.com">Lien</a></body></html>'
    js = extract_all_js(html)
    assert _check_event_wiring(html, js) == []


def test_hidden_input_not_flagged():
    """<input type='hidden'> = pas interactif → ignoré."""
    html = '<html><body><input id="csrf" type="hidden" value="x"></body></html>'
    js = extract_all_js(html)
    assert _check_event_wiring(html, js) == []


# ==========================================
# Nœud complet execute_static_tester_node (intégration)
# ==========================================
def test_valid_bubble_sort_passes_all(tmp_path):
    """HTML Bubble Sort complet et correct → tous checks PASS, is_valid=True.
    C'est la référence : tout ce qui n'est pas corrompu doit passer."""
    p = _write(tmp_path, "index.html", VALID_BUBBLE_SORT)
    subtask = {"id": "st1", "target_files": [p]}
    res, metrics = execute_static_tester_node(subtask, settings=None)
    assert res.status == "success", f"HTML valide ne devrait pas échouer: {res.details}"
    assert metrics.node == "static_tester"
    assert metrics.model == "static-tester"
    assert metrics.input_tokens == 0  # 0 LLM


def test_ts_in_html_fails_node(tmp_path):
    """Le bug n°1 au niveau nœud : TS dans <script> → failure."""
    html = """<!DOCTYPE html><html><body>
<script>function sort(arr: number[]) { return arr; }</script>
</body></html>"""
    p = _write(tmp_path, "index.html", html)
    subtask = {"id": "st1", "target_files": [p]}
    res, _ = execute_static_tester_node(subtask, settings=None)
    assert res.status == "failure"
    assert "node --check" in res.details or "SyntaxError" in res.details


def test_slider_not_wired_fails_node(tmp_path):
    """Le piège n°1 au niveau nœud : slider non branché → failure."""
    html = """<!DOCTYPE html><html><body>
<input id="speedSlider" type="range" min="1" max="100">
<button id="startBtn">Start</button>
<script>console.log("no handlers here");</script>
</body></html>"""
    p = _write(tmp_path, "index.html", html)
    subtask = {"id": "st1", "target_files": [p]}
    res, _ = execute_static_tester_node(subtask, settings=None)
    assert res.status == "failure"
    assert "wiring" in res.details


def test_non_html_passthrough(tmp_path):
    """Target Python → le Static Tester est web-only, pass-through success."""
    p = _write(tmp_path, "app.py", "def foo():\n    return 1\n")
    subtask = {"id": "st1", "target_files": [p]}
    res, _ = execute_static_tester_node(subtask, settings=None)
    assert res.status == "success"
    assert "HTML" in res.details or "web-only" in res.details


def test_opt_out_flag_disables(monkeypatch, tmp_path):
    """STATIC_TESTER_ENABLED=0 → le nœud est désactivé (pass-through)."""
    monkeypatch.setenv("STATIC_TESTER_ENABLED", "0")
    # HTML avec un bug TS flagrant → ne devrait PAS être détecté (nœud off).
    p = _write(tmp_path, "index.html",
               "<script>function f(x: number) { return x; }</script>")
    subtask = {"id": "st1", "target_files": [p]}
    res, _ = execute_static_tester_node(subtask, settings=None)
    assert res.status == "success"  # désactivé = ne voit pas le bug
    assert "désactivé" in res.details


def test_devtools_disabled_still_runs_tier1(monkeypatch, tmp_path):
    """STATIC_TESTER_DEVTOOLS=0 → Tier 2 skip mais Tier 1 reste actif.
    Un bug TS doit TOUJOURS être attrapé (Tier 1 = 0 dépendance Chrome)."""
    monkeypatch.setenv("STATIC_TESTER_DEVTOOLS", "0")
    p = _write(tmp_path, "index.html",
               "<script>function f(x: number) { return x; }</script>")
    subtask = {"id": "st1", "target_files": [p]}
    res, _ = execute_static_tester_node(subtask, settings=None)
    assert res.status == "failure"
    assert "node --check" in res.details


def test_multiple_targets_aggregates_errors(tmp_path):
    """Plusieurs fichiers HTML : agrège les erreurs de chacun."""
    bad1 = _write(tmp_path, "a.html", "<script>let x: number = 1;</script>")
    bad2 = _write(tmp_path, "b.html", '<button id="dead">X</button>')  # wiring
    subtask = {"id": "st1", "target_files": [bad1, bad2]}
    res, _ = execute_static_tester_node(subtask, settings=None)
    assert res.status == "failure"
    assert "a.html" in res.details
    assert "b.html" in res.details


def test_missing_file_skipped(tmp_path):
    """Fichier absent → skip (pas un échec faux), comme le Linter."""
    subtask = {"id": "st1", "target_files": [str(tmp_path / "missing.html")]}
    res, _ = execute_static_tester_node(subtask, settings=None)
    assert res.status == "success"


def test_empty_target_list(tmp_path):
    """Aucun target → pass-through success."""
    subtask = {"id": "st1", "target_files": []}
    res, _ = execute_static_tester_node(subtask, settings=None)
    assert res.status == "success"


# ==========================================
# Tier 1c — Smels comportementaux (post-mortem run #3)
# ==========================================
from graph_orchestrator.static_tester import _check_behavioral_smells  # noqa: E402

# Le script EXACT du bug run #3 (généré par le Coder, rejeté par l'utilisateur) :
# compteur affiché jamais incrémenté + await sleep(speed) avec let speed = 5 (5 ms/étape).
RUN3_BUGGY_JS = """
const counterEl = document.getElementById('counter');
let comparisons = 0;
let speed = 5;
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
async function bubbleSort() {
    for (let i = 0; i < data.length - 1; i++) {
        await sleep(speed);
        if (data[i] > data[i + 1]) { [data[i], data[i+1]] = [data[i+1], data[i]]; }
    }
}
counterEl.textContent = comparisons;
"""


def test_behavioral_run3_both_bugs_caught():
    """LE test du post-mortem : les 2 bugs du run #3 (compteur mort + animation
    instantanée 5ms) sont attrapés par le Tier 1c — là où Tier 2/3 étaient aveugles."""
    errors = _check_behavioral_smells(RUN3_BUGGY_JS)
    assert any("comparisons" in e and "JAMAIS incrémenté" in e for e in errors)
    assert any("5 ms par étape" in e for e in errors)


def test_behavioral_counter_incremented_clean():
    js = RUN3_BUGGY_JS.replace(
        "await sleep(speed);", "await sleep(320 - speed * 28); comparisons++;"
    )
    assert _check_behavioral_smells(js) == [], "compteur incrémenté + délai 50-300ms = propre"


def test_behavioral_compteur_calcule_non_flagge():
    """Anti-FP : un compteur recalculé (pas initialisé à 0) n'est pas flaggé."""
    js = "let total = 0;\ntotal = a + b;\nel.textContent = total;"
    assert _check_behavioral_smells(js) == []


RUN17_STATIC_COUNTER_JS = """let comparisonCount = 0;
let isSorting = false;
const counter = document.getElementById('counter');
const startBtn = document.getElementById('startBtn');
async function bubbleSort() {
    comparisonCount = 0;
    counter.textContent = '0';
    for (let i = 0; i < arr.length - 1; i++) {
        await sleep(speed);
        if (arr[i] > arr[i + 1]) { swapped = true; }
    }
    markSorted();
}
function reset() {
    comparisonCount = 0;
    counter.textContent = '0';
}
"""


def test_behavioral_compteur_statique_run17():
    """Run #17 : l'élément #counter est ciblé par JS mais écrit UNIQUEMENT avec
    des littéraux constants — la variable comparisonCount n'est jamais affichée
    (le check (a) ne voit rien : aucun identifiant dans les écritures). La
    variante (a-bis) raisonne sur l'ÉLÉMENT et doit réfuter."""
    errors = _check_behavioral_smells(RUN17_STATIC_COUNTER_JS)
    assert any(
        "littéraux constants" in e and "counter" in e for e in errors
    ), f"compteur statique run #17 non détecté : {errors}"


def test_behavioral_compteur_dynamique_element_non_flagge():
    """Anti-FP du (a-bis) : même code mais l'élément reçoit une valeur dynamique
    (template) → jamais flaggué."""
    js = RUN17_STATIC_COUNTER_JS.replace(
        "counter.textContent = '0';",
        "counter.textContent = `${comparisonCount}`;",
    )
    assert not any("littéraux constants" in e for e in _check_behavioral_smells(js))


def test_behavioral_template_literal_counter():
    js = "let swaps = 0;\nel.innerHTML = `Swaps: ${swaps}`;\nloop();"
    errors = _check_behavioral_smells(js)
    assert any("swaps" in e for e in errors)


def test_behavioral_delays_legitimes():
    assert _check_behavioral_smells("await sleep(300);") == []
    assert _check_behavioral_smells("await sleep(50);") == []
    assert _check_behavioral_smells("setTimeout(fn, 0);") == [], "deferral hors contexte animation = légitime"
    assert _check_behavioral_smells("await sleep(8);") != [], "sleep littéral < 20ms = instantané"


def test_behavioral_settimeout_avec_contexte_animation():
    js = "function animateStep() { setTimeout(draw, 10); }"
    assert _check_behavioral_smells(js) != [], "setTimeout 10ms en contexte animation = instantané"


def test_behavioral_var_non_numerique_ignoree():
    assert _check_behavioral_smells("el.textContent = title;") == []


def test_static_tester_node_attrape_run3(tmp_path, monkeypatch):
    """Intégration : le nœud Static Tester rejette le livrable run #3 en Tier 1
    (0 Chrome) avec les erreurs [behavior] — court-circuite le Tester LLM."""
    import shutil
    if shutil.which("node") is None:
        import pytest
        pytest.skip("node absent")
    monkeypatch.setenv("STATIC_TESTER_DEVTOOLS", "0")
    p = _write(tmp_path, "index.html", "<script>" + RUN3_BUGGY_JS + "</script>")
    subtask = {"id": "st1c", "target_files": [p]}
    res, _ = execute_static_tester_node(subtask, settings=None)
    assert res.status == "failure"
    assert "[behavior]" in res.details
    assert "JAMAIS incrémenté" in res.details
    assert "5 ms par étape" in res.details


# ==========================================
# Tier 2 — Visibilité DOM (skip si Chrome absent)
# ==========================================
def test_invisible_bars_height_percent(tmp_path, monkeypatch):
    """LE bug qui a trompé le LLM : .bar{height:50%} sur conteneur SANS height
    → résolu à 0 → barres invisibles. Le Static Tester Tier 2 DOIT l'attraper.

    On force le Tier 2. Si Chrome n'est pas dispo dans l'env de test, on skip
    (le test live validera ce cas — cf. validation finale du plan).
    """
    html = """<!DOCTYPE html><html><body>
<style>#bars { min-height: 400px; } .bar { height: 50%; }</style>
<div id="bars"></div>
<button id="go">Go</button>
<script>
const bars = document.getElementById("bars");
const go = document.getElementById("go");
go.addEventListener("click", () => {
  for (let i = 0; i < 5; i++) {
    const b = document.createElement("div");
    b.className = "bar";
    bars.appendChild(b);
  }
});
</script></body></html>"""
    p = _write(tmp_path, "index.html", html)
    res = static_check_html(p, run_devtools=True)
    # Si Chrome dispo → doit FAIL (barres invisibles). Sinon → Tier 1 seul (PASS,
    # pas de bug statique), tier_reached="tier1" → on skip le test.
    if res.tier_reached != "tier2":
        pytest.skip("Chrome DevTools indispo dans l'env de test — Tier 2 testé en live.")
    assert not res.is_valid, f"Devrait détecter barres invisibles: {res.errors}"
    assert any("INVISIBLE" in e or "height" in e for e in res.errors)


def test_tier2_skipped_when_devtools_off(tmp_path, monkeypatch):
    """STATIC_TESTER_DEVTOOLS=0 → tier_reached='tier1' (pas tier2)."""
    monkeypatch.setenv("STATIC_TESTER_DEVTOOLS", "0")
    p = _write(tmp_path, "index.html", VALID_BUBBLE_SORT)
    res = static_check_html(p, run_devtools=False)
    assert res.is_valid
    assert res.tier_reached == "tier1"


def test_gradient_bars_visible_run13(tmp_path):
    """Run #13 (F-124) : `.comparing { background: linear-gradient(…) }` sans
    texte — backgroundColor reste TRANSPARENT (le gradient vit dans
    background-image) mais la barre est PARFAITEMENT visible (hauteur réelle).
    La sonde Tier 2 ne doit PLUS la flagguer « INVISIBLE » (faux positif qui a
    coûté 2 itérations complètes au run #13). Skip si Chrome indispo (live)."""
    html = """<!DOCTYPE html><html><body>
<style>
#bars { display: flex; align-items: flex-end; gap: 4px; min-height: 400px; }
.bar { width: 24px; height: 60px; background: linear-gradient(180deg, #42a5f5, #1e88e5); }
.bar.comparing { background: linear-gradient(180deg, #ff6f00, #f57c00); }
</style>
<div id="bars"></div>
<button id="go">Go</button>
<script>
const bars = document.getElementById("bars");
const go = document.getElementById("go");
go.addEventListener("click", () => {
  for (let i = 0; i < 5; i++) {
    const b = document.createElement("div");
    b.className = "bar" + (i < 2 ? " comparing" : "");
    bars.appendChild(b);
  }
});
</script></body></html>"""
    p = _write(tmp_path, "index.html", html)
    res = static_check_html(p, run_devtools=True)
    if res.tier_reached != "tier2":
        pytest.skip("Chrome DevTools indispo dans l'env de test — Tier 2 testé en live.")
    assert res.is_valid, f"Faux positif run #13 : barres à gradient flagguées : {res.errors}"
    assert not any("INVISIBLE" in e for e in res.errors)


def test_truly_transparent_bars_still_flagged(tmp_path):
    """Contre-faux-négatif du fix run #13 : un div avec hauteur réelle mais
    AUCUN fond (ni couleur ni image) et sans texte reste réellement invisible à
    l'écran (bug historique « perte de classe de couleur ») → DOIT rester
    flaggué. Skip si Chrome indispo (live)."""
    html = """<!DOCTYPE html><html><body>
<style>
#bars { display: flex; align-items: flex-end; gap: 4px; min-height: 400px; }
.bar { width: 24px; height: 60px; } /* AUCUN background → invisible à l'écran */
</style>
<div id="bars"></div>
<button id="go">Go</button>
<script>
const bars = document.getElementById("bars");
const go = document.getElementById("go");
go.addEventListener("click", () => {
  for (let i = 0; i < 5; i++) {
    const b = document.createElement("div");
    b.className = "bar";
    bars.appendChild(b);
  }
});
</script></body></html>"""
    p = _write(tmp_path, "index.html", html)
    res = static_check_html(p, run_devtools=True)
    if res.tier_reached != "tier2":
        pytest.skip("Chrome DevTools indispo dans l'env de test — Tier 2 testé en live.")
    assert not res.is_valid, "Barres réellement transparentes (aucun fond) : devraient être flagguées."
    assert any("INVISIBLE" in e for e in res.errors)


def test_sonde_tier2_couvre_background_image():
    """Garde anti-régression (déterministe, 0 Chrome) : la sonde JS du Tier 2
    doit tester cs.backgroundImage — sinon tout fond en gradient (F-124)
    redevient un faux « INVISIBLE » (run #13)."""
    import inspect

    import graph_orchestrator.static_tester as st

    assert "cs.backgroundImage === 'none'" in inspect.getsource(st)


def _bars_page(css_container: str, css_bar: str, js_height: str) -> str:
    """Page de visualiseur paramétrable : 20 barres créées au clic."""
    return f"""<!DOCTYPE html><html><body>
<style>
#bars {{ {css_container} }}
.bar {{ {css_bar} }}
</style>
<div id="bars"></div>
<button id="go">Go</button>
<script>
const bars = document.getElementById("bars");
const go = document.getElementById("go");
go.addEventListener("click", () => {{
  const vals = [12, 45, 78, 23, 90, 56, 34, 67, 89, 15, 42, 71, 28, 95, 63, 38, 82, 50, 19, 74];
  for (let i = 0; i < 20; i++) {{
    const b = document.createElement("div");
    b.className = "bar";
    {js_height}
    bars.appendChild(b);
  }}
}});
</script></body></html>"""


def test_flat_bars_run14_flagged(tmp_path):
    """Run #14 (barres plates) : 20 barres quasi IDENTIQUES + pleine largeur
    (flex-basis écrase style.height) → le Tier 2 DOIT réfuter même si chaque
    barre est individuellement « visible ». Géométrie EXACTE du bug : conteneur
    column + flex:1. Skip si Chrome indispo (live)."""
    html = _bars_page(
        "display: flex; flex-direction: column; height: 300px;",
        "flex: 1; background: #ef5350;",
        "",
    )
    p = _write(tmp_path, "index.html", html)
    res = static_check_html(p, run_devtools=True)
    if res.tier_reached != "tier2":
        pytest.skip("Chrome DevTools indispo dans l'env de test — Tier 2 testé en live.")
    assert not res.is_valid, f"Barres plates (run #14) devraient être flagguées : {res.errors}"
    assert any("IDENTIQUES" in e for e in res.errors)


def test_varied_bars_run14_ok(tmp_path):
    """Contre-faux-positif : 20 barres ROW avec hauteurs PROPORTIONNELLES
    variées → jamais flagguées « IDENTIQUES ». Skip si Chrome indispo (live)."""
    html = _bars_page(
        "display: flex; flex-direction: row; align-items: flex-end; height: 300px;",
        "width: 12px; background: #ef5350;",
        "b.style.height = vals[i] + 'px';",
    )
    p = _write(tmp_path, "index.html", html)
    res = static_check_html(p, run_devtools=True)
    if res.tier_reached != "tier2":
        pytest.skip("Chrome DevTools indispo dans l'env de test — Tier 2 testé en live.")
    assert res.is_valid, f"Barres proportionnelles ne doivent pas être flagguées : {res.errors}"
    assert not any("IDENTIQUES" in e for e in res.errors)


def test_empty_at_load_run15_flagged(tmp_path):
    """Run #15 : barres CRÉÉES au chargement mais height:0 (les vraies hauteurs
    ne viennent qu'au clic Start) → page visuellement VIDE à l'ouverture.
    Le snapshot PRE-clic du Tier 2 DOIT réfuter (critère F-82 n°1). Skip si
    Chrome indispo (live)."""
    html = _bars_page(
        "display: flex; flex-direction: row; align-items: flex-end; height: 300px;",
        "width: 12px; background: #ef5350;",
        "b.style.height = '0px';",  # bug run #15 : hauteur nulle à la création
    )
    p = _write(tmp_path, "index.html", html)
    res = static_check_html(p, run_devtools=True)
    if res.tier_reached != "tier2":
        pytest.skip("Chrome DevTools indispo dans l'env de test — Tier 2 testé en live.")
    assert not res.is_valid, f"Conteneur vide au chargement (run #15) : devrait être réfuté : {res.errors}"
    assert any("[CHARGEMENT]" in e for e in res.errors)


def test_bars_visible_at_load_ok(tmp_path):
    """Contre-faux-positif du check chargement : barres avec hauteur réelle
    DÈS la création (géométrie correcte) → aucun flag [CHARGEMENT]. Skip si
    Chrome indispo (live)."""
    html = _bars_page(
        "display: flex; flex-direction: row; align-items: flex-end; height: 300px;",
        "width: 12px; background: #ef5350;",
        "b.style.height = vals[i] + 'px';",
    )
    p = _write(tmp_path, "index.html", html)
    res = static_check_html(p, run_devtools=True)
    if res.tier_reached != "tier2":
        pytest.skip("Chrome DevTools indispo dans l'env de test — Tier 2 testé en live.")
    assert res.is_valid, f"Barres visibles au chargement ne doivent pas être flagguées : {res.errors}"
    assert not any("[CHARGEMENT]" in e for e in res.errors)


# ==========================================
# Dégradation node absent
# ==========================================
def test_node_absent_degrades(monkeypatch):
    """node absent du PATH → Tier 1a skip gracieusement (pas d'échec faux).
    On simule en faisant échouer le subprocess."""
    import graph_orchestrator.static_tester as st

    def fake_run(js):
        # Simule node absent.
        return 0, ""  # le code retourne (0, "") quand node absent (skip silencieux)

    monkeypatch.setattr(st, "_run_node_check", fake_run)
    html = "<script>let x: number = 1;</script>"  # TS (aurait dû FAIL)
    errs = _check_js_syntax(html)
    assert errs == [], "node absent → pas d'échec faux (le LLM Tester prend le relais)"


# ==========================================
# Tier 3 — Animation temporelle (skip si Chrome absent)
# ==========================================
# HTML du bug réel diagnostiqué (run 2026-08-05_1602_bubble_sort) : performStep()
# contient les deux boucles imbriquées complètes → tout le tri en 1 tick JS.
INSTANT_ANIMATION_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>.visualization{height:300px;display:flex;align-items:flex-end;background:#eee;padding:4px}
.bar{flex:1;min-width:6px;background:#4a90d9}.bar.sorted{background:#39e6c4}</style>
</head><body>
<div class="visualization" id="visualization"></div>
<button id="startBtn">Démarrer</button>
<div>Comparaisons: <span id="counter">0</span></div>
<script>
let array=[],comparisons=0,delay=50;
function init(){
  const c=document.getElementById('visualization');c.innerHTML='';array=[];comparisons=0;
  document.getElementById('counter').textContent=0;
  for(let i=0;i<30;i++){const v=Math.floor(Math.random()*100)+1;array.push(v);
    const b=document.createElement('div');b.className='bar';b.style.height=(v*2)+'px';c.appendChild(b);}
}
function performStep(){
  const bars=document.querySelectorAll('.bar');const n=array.length;
  for(let i=0;i<n-1;i++){for(let j=0;j<n-i-1;j++){
    comparisons++;document.getElementById('counter').textContent=comparisons;
    if(array[j]>array[j+1]){[array[j],array[j+1]]=[array[j+1],array[j]];
      [bars[j].style.height,bars[j+1].style.height]=[bars[j+1].style.height,bars[j].style.height];}
  }bars[n-i-1].classList.add('sorted');}
}
document.getElementById('startBtn').addEventListener('click',()=>{performStep();});
init();
</script></body></html>"""

# HTML correct : progression sur ~2s (await sleep entre swaps), non terminal à 400ms.
PROGRESSIVE_ANIMATION_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8">
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


def test_instant_animation_perform_step_loop(tmp_path):
    """Le bug du run 2026-08-05_1602 : performStep() contient tout l'algorithme
    → animation instantanée. Le Tier 3 DOIT la détecter.

    On isole le verdict Tier 3 : peu importe les autres bugs (Tier 1/2), on vérifie
    qu'une erreur "[temporal]"/"instantanée" est présente. Si Chrome indispo → skip.
    """
    p = _write(tmp_path, "index.html", INSTANT_ANIMATION_HTML)
    res = static_check_html(p, run_devtools=True, run_temporal=True)
    if res.tier_reached != "tier3":
        pytest.skip("Chrome DevTools indispo dans l'env de test — Tier 3 testé en live.")
    temporal_errors = [e for e in res.errors if "instantanée" in e or "[temporal]" in e]
    assert temporal_errors, f"Le Tier 3 doit détecter l'animation instantanée: {res.errors}"


def test_progressive_animation_passes(tmp_path):
    """Une animation légitime (await sleep entre swaps, ~2s) ne doit PAS être
    flagguée par le Tier 3 (pas de faux positif). À 400ms l'animation n'est pas
    terminale → pas de flag [temporal].

    On isole le verdict Tier 3 : aucune erreur "[temporal]"/"instantanée".
    """
    p = _write(tmp_path, "index.html", PROGRESSIVE_ANIMATION_HTML)
    res = static_check_html(p, run_devtools=True, run_temporal=True)
    if res.tier_reached != "tier3":
        pytest.skip("Chrome DevTools indispo dans l'env de test — Tier 3 testé en live.")
    temporal_errors = [e for e in res.errors if "instantanée" in e or "[temporal]" in e]
    assert not temporal_errors, f"Animation légitime ne doit pas être flagguée par le Tier 3: {temporal_errors}"


def test_temporal_disabled_env(tmp_path):
    """run_temporal=False → le Tier 3 ne s'exécute pas, donc le bug d'animation
    instantanée n'est PAS détecté (même avec Chrome dispo).

    On isole la désactivation du Tier 3 : peu importe les autres bugs (Tier 1/2),
    on vérifie juste qu'aucune erreur "[temporal]"/"instantanée" n'est rapportée
    ET que tier_reached n'atteint pas "tier3".
    """
    p = _write(tmp_path, "index.html", INSTANT_ANIMATION_HTML)
    res = static_check_html(p, run_devtools=True, run_temporal=False)
    # Le Tier 3 n'a pas tourné → pas de message d'animation instantanée.
    assert all("instantanée" not in e for e in res.errors), res.errors
    assert all("[temporal]" not in e for e in res.errors), res.errors
    assert res.tier_reached != "tier3", f"Tier 3 ne doit pas s'exécuter: {res.tier_reached}"


def test_temporal_env_var_optout(tmp_path, monkeypatch):
    """STATIC_TESTER_TEMPORAL=0 → l'env-var désactive le Tier 3 au niveau du nœud."""
    monkeypatch.setenv("STATIC_TESTER_TEMPORAL", "0")
    p = _write(tmp_path, "index.html", INSTANT_ANIMATION_HTML)
    res, _ = execute_static_tester_node(
        {"id": "st3", "target_files": [p]}, settings=None
    )
    # Le bug d'animation instantanée est spécifique au Tier 3. Sans lui, ce message
    # n'apparaît jamais dans les détails (les autres bugs Tier 1/2 peuvent être là).
    assert "instantanée" not in res.details, "Tier 3 désactivé ne doit pas flaguer l'animation"


def test_temporal_no_progress_signal_skip():
    """Une page sans compteur ni .sorted → signal indétectable → le Tier 3 ne
    flag PAS (jamais de faux positif). On appelle _evaluate_temporal directement
    avec une sonde qui ne trouve rien à mesurer."""
    import graph_orchestrator.static_tester as st

    # _evaluate_temporal sans DevTools → retourne [] (skip), pas de flag.
    errs = st._evaluate_temporal([], "file:///dummy", "startBtn")
    assert errs == [], "Sans DevTools ou signal, le Tier 3 doit skip sans flaguer."



# ==========================================
# F-110 — compteur rafraîchi + canvas-child (post-mortem run #6)
# ==========================================
RUN6_BUGGY_REFRESH = """
let comparisons = 0;
counterDisplay.textContent = comparisons;   // init UNE fois AVANT la boucle
async function bubbleSort() {
    for (let i = 0; i < data.length - 1; i++) {
        comparisons++;
        if (data[i] > data[i + 1]) { swap(i, i + 1); }
    }
}
"""

RUN6_CANVAS_HTML = '<canvas id="chart" width="800" height="400"></canvas>'
RUN6_CANVAS_JS = """
for (let i = 0; i < 30; i++) {
    const bar = document.createElement('div');
    document.getElementById('chart').appendChild(bar);
}
"""


def test_behavioral_run6_counter_never_refreshed():
    """Post-mortem run #6 : l'incrément existe (Tier 1c historique passe) mais
    l'affichage n'est JAMAIS rafraîchi dans la boucle → compteur figé à 0."""
    errors = _check_behavioral_smells(RUN6_BUGGY_REFRESH)
    assert any("comparisons" in e and "JAMAIS rafraîchi" in e for e in errors)


def test_behavioral_counter_refreshed_in_loop_clean():
    js = RUN6_BUGGY_REFRESH.replace(
        "comparisons++;",
        "comparisons++; counterEl.textContent = comparisons;",
    )
    assert _check_behavioral_smells(js) == []


def test_canvas_children_anti_pattern():
    """Post-mortem run #6 : appendChild DANS un <canvas> — jamais rendu."""
    from graph_orchestrator.static_tester import _check_canvas_children
    errors = _check_canvas_children(RUN6_CANVAS_HTML, RUN6_CANVAS_JS)
    assert len(errors) == 1 and "chart" in errors[0] and "JAMAIS" in errors[0]


def test_canvas_children_clean_when_div_container():
    from graph_orchestrator.static_tester import _check_canvas_children
    html = '<div id="viz"></div>'
    js = RUN6_CANVAS_JS.replace("'chart'", "'viz'")
    assert _check_canvas_children(html, js) == []


def test_canvas_children_clean_when_ctx_drawing():
    from graph_orchestrator.static_tester import _check_canvas_children
    js = "const ctx = canvas.getContext('2d'); ctx.fillRect(0, 0, 10, 10);"
    assert _check_canvas_children(RUN6_CANVAS_HTML, js) == []


# ==========================================
# F-112 (post-mortem run #8, 2026-08-16) — le livrable avait un tri instantané
# invisible du Tier 3 : le découvreur de signal prenait le PREMIER élément
# numérique du DOM = le libellé du slider (constante) placé AVANT le compteur.
# + le délai était une FORMULE négative (`sleep(320 - speed*2)`, speed=320ms)
# que la résolution littérale ne voyait pas.
# ==========================================

# Réplique exacte du run #8 : canvas (pas de .sorted), speedLabel numérique
# AVANT le counter dans le DOM, tri complet instantané (sleep négatif clampé
# à 0, draw() unique en fin).
RUN8_INSTANT_CANVAS_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Bubble Sort Visualizer</title></head><body>
<div id="container"><h1>Bubble Sort Visualizer</h1>
<canvas id="chart" width="400" height="200"></canvas>
<div id="controls"><button id="startBtn">Start</button><button id="resetBtn">Reset</button></div>
<div id="speed"><label>Speed: <span id="speedLabel">5</span></label>
<input type="range" id="speedRange" min="1" max="10" value="5"></div>
<div id="counter">0</div></div>
<script>
const canvas=document.getElementById('chart'),ctx=canvas.getContext('2d');
const counter=document.getElementById('counter');
let arr=[],comparisons=0,speed=320;
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}
function draw(){ctx.clearRect(0,0,400,200);arr.forEach((v,i)=>{ctx.fillStyle='#454545';
ctx.fillRect(i*13,200-v*2,12,v*2);});}
function init(){arr=[];for(let i=0;i<30;i++)arr.push(Math.floor(Math.random()*100)+1);draw();}
async function bubbleSort(){
  comparisons=0;let swapped=true;
  while(swapped){swapped=false;
    for(let i=0;i<arr.length-1;i++){
      comparisons++;counter.textContent=comparisons;
      if(arr[i]>arr[i+1]){[arr[i],arr[i+1]]=[arr[i+1],arr[i]];swapped=true;}}}
    await sleep(320 - speed * 2); // NÉGATIF (-320) → clampé à 0 par setTimeout
  draw();}
document.getElementById('startBtn').addEventListener('click',()=>{if(!window._s){window._s=1;bubbleSort();}});
init();
</script></body></html>"""

# Même page mais avec UNE étape par await (délai positif 80ms, draw() dans la
# boucle) : l'animation progressive ne doit JAMAIS être flagguée.
RUN8_PROGRESSIVE_CANVAS_HTML = RUN8_INSTANT_CANVAS_HTML.replace(
    """while(swapped){swapped=false;
    for(let i=0;i<arr.length-1;i++){
      comparisons++;counter.textContent=comparisons;
      if(arr[i]>arr[i+1]){[arr[i],arr[i+1]]=[arr[i+1],arr[i]];swapped=true;}}}
    await sleep(320 - speed * 2); // NÉGATIF (-320) → clampé à 0 par setTimeout
  draw();}""",
    """for(let p=0;p<arr.length-1;p++){
    for(let i=0;i<arr.length-1-p;i++){
      comparisons++;counter.textContent=comparisons;
      if(arr[i]>arr[i+1]){[arr[i],arr[i+1]]=[arr[i+1],arr[i]];}
      await sleep(80);draw();}} // UNE étape par await + rendu DANS la boucle
  draw();}""",
).replace("const speed=320;", "const speed=4;")


class TestResolveDelayMs:
    """F-112 — résolution arithmétique des délais (le bug formule du run #8)."""

    def test_formule_negative_run8(self):
        from graph_orchestrator.static_tester import _resolve_delay_ms
        js = "let speed = 320;\nawait sleep(320 - speed * 2);"
        assert _resolve_delay_ms("320 - speed * 2", js) == -320

    def test_formule_positive_legitime(self):
        from graph_orchestrator.static_tester import _resolve_delay_ms
        js = "let speedValue = 10;\nawait sleep(320 - speedValue * 28);"
        assert _resolve_delay_ms("320 - speedValue * 28", js) == 40

    def test_variable_non_liee_fail_open(self):
        from graph_orchestrator.static_tester import _resolve_delay_ms
        assert _resolve_delay_ms("320 - speed * 28", "const other = 1;") is None
        assert _resolve_delay_ms("speed", "") is None

    def test_litteral_et_variable_simple(self):
        from graph_orchestrator.static_tester import _resolve_delay_ms
        assert _resolve_delay_ms("5", "x") == 5
        assert _resolve_delay_ms("speed", "let speed = 5;") == 5

    def test_division_par_zero_fail_open(self):
        from graph_orchestrator.static_tester import _resolve_delay_ms
        assert _resolve_delay_ms("speed / 0", "let speed = 100;") is None

    def test_nom_de_fonction_rejete(self):
        """Un appel (ex: `sleep(getDelay())`) n'est jamais évalué — whitelist
        arithmétique stricte : pas d'eval arbitraire."""
        from graph_orchestrator.static_tester import _resolve_delay_ms
        assert _resolve_delay_ms("getDelay() + 1", "let getDelay = 3;") is None


class TestBehavioralRun8Formula:
    """Le Tier 1c attrape désormais la FORMULE négative (invisible avant F-112)."""

    def test_run8_delai_negatif_flagge(self):
        from graph_orchestrator.static_tester import _check_behavioral_smells
        js = (
            "let speed = 320;\n"
            "async function s(){for(;;){comparisons++;"
            "counter.textContent=comparisons;await sleep(320 - speed * 2);}}"
        )
        errors = _check_behavioral_smells(js)
        assert any("-320 ms" in e and "NÉGATIVE" in e for e in errors), errors

    def test_message_sans_formule_litterale_suggeree(self):
        """Post-mortem run #8 : le message AVANT F-112 suggérait `320 - speed*28`
        littéralement — le Coder l'a greffée à l'aveugle. Le nouveau message
        porte l'INVARIANT (unité de la variable) et aucune formule à copier."""
        from graph_orchestrator.static_tester import _check_behavioral_smells
        errors = _check_behavioral_smells("await sleep(5); draw();")
        assert errors
        assert "320 - speed" not in errors[0]
        assert "UNITÉ" in errors[0] or "unité" in errors[0]

    def test_formule_positive_propre(self):
        from graph_orchestrator.static_tester import _check_behavioral_smells
        js = (
            "let speedValue = 10;\n"
            "async function s(){for(;;){comparisons++;"
            "counter.textContent=comparisons;await sleep(320 - speedValue * 28);}}"
        )
        # 40 ms par étape = animation visible → pas de flag délai.
        assert not any("Délai d'animation" in e for e in _check_behavioral_smells(js))


class TestTemporalVerdict:
    """F-112 — verdict pur multi-signal (sans Chrome), sur des snapshots réels."""

    def _snap(self, **over):
        base = {
            "nums0": {"speedLabel": 5, "counter": 0},
            "nums1": {"speedLabel": 5, "counter": 0},
            "nums2": {"speedLabel": 5, "counter": 0},
            "term0": 0, "term1": 0, "term2": 0,
            "c0": 111, "c1": 111, "c2": 111,
        }
        base.update(over)
        return base

    def test_run8_compteur_progressif_puis_stable_flag(self):
        """LA régression du run #8 : le compteur avance (0→217) et le canvas
        change — mais TOUT est déjà stable à la fenêtre de stabilisation."""
        from graph_orchestrator.static_tester import _temporal_verdict
        snap = self._snap(nums1={"speedLabel": 5, "counter": 217},
                          nums2={"speedLabel": 5, "counter": 217}, c1=222, c2=222)
        verdict = _temporal_verdict(snap, "startBtn")
        assert verdict and "[temporal]" in verdict[0]
        assert "counter" in verdict[0] and "canvas" in verdict[0]

    def test_run8_canvas_seul_flag(self):
        """App canvas SANS compteur : le hash pixels reste le seul signal."""
        from graph_orchestrator.static_tester import _temporal_verdict
        snap = self._snap(c1=222, c2=222)
        verdict = _temporal_verdict(snap, "startBtn")
        assert verdict and "canvas" in verdict[0]

    def test_progressive_pas_de_flag(self):
        from graph_orchestrator.static_tester import _temporal_verdict
        snap = self._snap(nums1={"speedLabel": 5, "counter": 13},
                          nums2={"speedLabel": 5, "counter": 15})
        assert _temporal_verdict(snap, "startBtn") == []

 

    def test_canvas_progressif_pas_de_flag(self):
        from graph_orchestrator.static_tester import _temporal_verdict
        snap = self._snap(c1=222, c2=333)
        assert _temporal_verdict(snap, "startBtn") == []

    def test_signal_constant_seul_skip(self):
        """L'exacte cécité du run #8 AVANT F-112 : seul le speedLabel (constante)
        existe, rien ne bouge → skip (jamais de FP)."""
        from graph_orchestrator.static_tester import _temporal_verdict
        assert _temporal_verdict(self._snap(), "startBtn") == []

    def test_classes_terminales_stables_flag(self):
        from graph_orchestrator.static_tester import _temporal_verdict
        snap = self._snap(term1=12, term2=12)
        verdict = _temporal_verdict(snap, "startBtn")
        assert verdict and "terminaux" in verdict[0]

    def test_canvas_absent_ignore(self):
        from graph_orchestrator.static_tester import _temporal_verdict
        snap = self._snap(c0=None, c1=None, c2=None,
                          nums1={"speedLabel": 5, "counter": 90},
                          nums2={"speedLabel": 5, "counter": 90})
        assert _temporal_verdict(snap, "startBtn")

    def test_no_btn_skip(self):
        from graph_orchestrator.static_tester import _temporal_verdict
        assert _temporal_verdict({"reason": "no-btn"}, "startBtn") == []


# Réplique exacte du run #8 : canvas (pas de .sorted), speedLabel numérique
# AVANT le counter dans le DOM, tri complet instantané (sleep négatif clampé
# à 0, draw() unique en fin).
RUN8_INSTANT_CANVAS_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Bubble Sort Visualizer</title></head><body>
<div id="container"><h1>Bubble Sort Visualizer</h1>
<canvas id="chart" width="400" height="200"></canvas>
<div id="controls"><button id="startBtn">Start</button><button id="resetBtn">Reset</button></div>
<div id="speed"><label>Speed: <span id="speedLabel">5</span></label>
<input type="range" id="speedRange" min="1" max="10" value="5"></div>
<div id="counter">0</div></div>
<script>
const canvas=document.getElementById('chart'),ctx=canvas.getContext('2d');
const counter=document.getElementById('counter');
let arr=[],comparisons=0,speed=320;
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}
function draw(){ctx.clearRect(0,0,400,200);arr.forEach((v,i)=>{ctx.fillStyle='#454545';
ctx.fillRect(i*13,200-v*2,12,v*2);});}
function init(){arr=[];for(let i=0;i<30;i++)arr.push(Math.floor(Math.random()*100)+1);draw();}
async function bubbleSort(){
  comparisons=0;let swapped=true;
  while(swapped){swapped=false;
    for(let i=0;i<arr.length-1;i++){
      comparisons++;counter.textContent=comparisons;
      if(arr[i]>arr[i+1]){[arr[i],arr[i+1]]=[arr[i+1],arr[i]];swapped=true;}}}
    await sleep(320 - speed * 2); // NEGATIF (-320) -> clampe a 0 par setTimeout
  draw();}
document.getElementById('startBtn').addEventListener('click',()=>{if(!window._s){window._s=1;bubbleSort();}});
init();
</script></body></html>"""

# Même page mais UNE étape par await (delai positif 80ms, draw() DANS la
# boucle) : l'animation progressive ne doit JAMAIS etre flagguee.
RUN8_PROGRESSIVE_CANVAS_HTML = RUN8_INSTANT_CANVAS_HTML.replace(
    """while(swapped){swapped=false;
    for(let i=0;i<arr.length-1;i++){
      comparisons++;counter.textContent=comparisons;
      if(arr[i]>arr[i+1]){[arr[i],arr[i+1]]=[arr[i+1],arr[i]];swapped=true;}}}
    await sleep(320 - speed * 2); // NEGATIF (-320) -> clampe a 0 par setTimeout
  draw();}""",
    """for(let p=0;p<arr.length-1;p++){
    for(let i=0;i<arr.length-1-p;i++){
      comparisons++;counter.textContent=comparisons;
      if(arr[i]>arr[i+1]){[arr[i],arr[i+1]]=[arr[i+1],arr[i]];}
      await sleep(80);draw();}} // UNE etape par await + rendu DANS la boucle
  draw();}""",
).replace("speed=320;", "speed=4;")


class TestTemporalLiveRun8Regression:
    """LIVE (Chrome requis, sinon skip) : la réplique exacte du run #8 DOIT être
    réfutée par le Tier 3 multi-signal — là où l'ancienne sonde était aveugle
    (speedLabel constant découvert avant le compteur)."""

    def test_run8_replicat_refute(self, tmp_path):
        p = _write(tmp_path, "index.html", RUN8_INSTANT_CANVAS_HTML)
        res = static_check_html(p, run_devtools=True, run_temporal=True)
        if res.tier_reached != "tier3":
            pytest.skip("Chrome DevTools indispo dans l'env de test — Tier 3 testé en live.")
        temporal_errors = [e for e in res.errors if "instantanée" in e or "[temporal]" in e]
        assert temporal_errors, (
            f"Le Tier 3 multi-signal doit détecter le tri instantané du run #8: {res.errors}"
        )

    def test_run8_progressive_replicat_passe(self, tmp_path):
        p = _write(tmp_path, "index.html", RUN8_PROGRESSIVE_CANVAS_HTML)
        res = static_check_html(p, run_devtools=True, run_temporal=True)
        if res.tier_reached != "tier3":
            pytest.skip("Chrome DevTools indispo dans l'env de test — Tier 3 testé en live.")
        temporal_errors = [e for e in res.errors if "instantanée" in e or "[temporal]" in e]
        assert not temporal_errors, (
            f"Animation progressive canvas ne doit pas être flagguée: {temporal_errors}"
        )
