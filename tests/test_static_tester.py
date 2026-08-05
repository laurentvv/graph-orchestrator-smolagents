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
    extract_inline_js,
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
def test_extract_inline_js_basic():
    assert extract_inline_js("<script>let x = 1;</script>") == "let x = 1;"


def test_extract_inline_js_skips_external_src():
    """Un <script src='app.js'> ne doit PAS être extrait (code externe indispo)."""
    html = '<script src="app.js"></script><script>let y = 2;</script>'
    js = extract_inline_js(html)
    assert "let y = 2;" in js
    assert "app.js" not in js


def test_extract_inline_js_multiple_blocks():
    html = "<script>a()</script><script>b()</script>"
    assert "a()" in extract_inline_js(html)
    assert "b()" in extract_inline_js(html)


def test_extract_inline_js_empty_when_no_script():
    assert extract_inline_js("<html><body><h1>Hi</h1></body></html>") == ""


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
    errs = _check_js_syntax(html)
    assert len(errs) >= 1
    assert "SyntaxError" in errs[0]


def test_valid_js_syntax_passes():
    """JS vanilla valide → 0 erreur."""
    html = "<script>function foo() { return 1; } foo();</script>"
    assert _check_js_syntax(html) == []


def test_no_script_no_error():
    """HTML sans JS → rien à valider."""
    assert _check_js_syntax("<html><body><h1>Hello</h1></body></html>") == []


# ==========================================
# Tier 1b — Wiring addEventListener (le piège n°1)
# ==========================================
def test_slider_not_wired():
    """Le piège n°1 : <input id='speedSlider'> existe mais AUCUN handler.
    Slider visible mais inactif — indétectable par screenshot."""
    html = """<html><body>
<input id="speedSlider" type="range" min="1" max="100">
<script>function init() { console.log("ready"); } init();</script>
</body></html>"""
    errs = _check_event_wiring(html)
    assert any("speedSlider" in e and "wiring" in e for e in errs), \
        f"Devrait détecter speedSlider non-wiré, got: {errs}"


def test_button_not_wired():
    """Bouton avec id mais aucun handler → flagged."""
    html = """<html><body>
<button id="startBtn">Start</button>
<script>console.log("page loaded");</script>
</body></html>"""
    errs = _check_event_wiring(html)
    assert any("startBtn" in e for e in errs)


def test_slider_wired_via_getElementById():
    """Slider branché via getElementById + addEventListener → 0 erreur."""
    html = """<html><body>
<input id="speedSlider" type="range">
<script>
const s = document.getElementById("speedSlider");
s.addEventListener("input", () => {});
</script></body></html>"""
    assert _check_event_wiring(html) == []


def test_button_wired_inline_onclick():
    """onclick inline = branchement légitime → toléré."""
    html = '<html><body><button id="b" onclick="doThing()">Go</button></body></html>'
    assert _check_event_wiring(html) == []


def test_submit_button_in_form_not_flagged():
    """<button type='submit'> dans un form = submit natif → pas besoin de JS."""
    html = """<html><body>
<form action="/save">
  <input name="q" type="text">
  <button type="submit">Envoyer</button>
</form></body></html>"""
    assert _check_event_wiring(html) == []


def test_link_with_href_not_flagged():
    """<a href='...'> = navigation native → pas besoin de JS."""
    html = '<html><body><a href="https://example.com">Lien</a></body></html>'
    assert _check_event_wiring(html) == []


def test_hidden_input_not_flagged():
    """<input type='hidden'> = pas interactif → ignoré."""
    html = '<html><body><input id="csrf" type="hidden" value="x"></body></html>'
    assert _check_event_wiring(html) == []


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

