"""Tests unitaires de ``devtools_dom_tools`` (F-72 — Prompt Offloading).

Vérifie la factory fail-open et la délégation correcte : chaque helper appelle
``evaluate_script`` avec le bon snippet JS (passé via ``function=``, pas ``script=``),
sur le navigateur DevTools actif (et non Puppeteer, qui ne charge pas les file://).

0 LLM, 0 réseau, 0 navigateur — on mocke ``evaluate_script`` avec un fake qui capture
l'argument ``function``.
"""
from __future__ import annotations

import os

from smolagents import Tool

from graph_orchestrator import devtools_dom_tools
from graph_orchestrator.devtools_dom_tools import (
    _ADD_VISUAL_TAGS_JS,
    _CLEAN_DOM_JS,
    _FUZZ_CLICK_JS,
    DevToolsAddVisualTagsTool,
    DevToolsCleanDomTool,
    DevToolsFuzzClickTool,
    build_devtools_helper_tools,
)


class _FakeEval(Tool):
    """Fake de l'outil MCP evaluate_script : capture l'arg `function`."""

    name = "evaluate_script"
    description = "fake evaluate_script pour test"
    inputs = {}
    output_type = "string"
    # smolagents valide que les params de forward() matchent les inputs déclarés.
    # Les outils MCP réels skip cette validation (schéma vient du serveur) ; on l'imite.
    skip_forward_signature_validation = True

    def __init__(self):
        super().__init__()
        self.captured_function = None

    def forward(self, function=None, **kwargs):
        self.captured_function = function
        return "FAKE_EVAL_RESULT"


class _OtherTool(Tool):
    name = "navigate_page"
    description = "autre outil DevTools"
    inputs = {}
    output_type = "string"
    skip_forward_signature_validation = True

    def forward(self, **kwargs):
        return "ok"


# ==========================================
# Factory fail-open
# ==========================================
def test_factory_empty_cdt_returns_empty():
    """DevTools indispo (cdt_tools=[]) → factory retourne []."""
    assert build_devtools_helper_tools([]) == []


def test_factory_no_evaluate_script_returns_empty():
    """evaluate_script absent de la liste → factory retourne [] (les autres outils inchangés)."""
    tools = [_OtherTool()]
    assert build_devtools_helper_tools(tools) == []


def test_factory_with_evaluate_script_returns_twelve_helpers():
    """evaluate_script présent → factory retourne les 12 helpers (bons noms).

    F-127 : discover_ui en TÊTE. F-145 : +4 sondes de preuve de mouvement.
    F-155 : +probe_sort_state (tri en cours vs tri cassé)."""
    eval_tool = _FakeEval()
    helpers = build_devtools_helper_tools([_OtherTool(), eval_tool])
    names = [getattr(h, "name", "") for h in helpers]
    assert names == [
        "discover_ui",
        "clean_dom",
        "add_visual_tags",
        "fuzz_click_all_buttons",
        "probe_canvas_activity",
        "fuzz_keyboard_controls",
        "heal_selector",
        "expose_game_state",
        "instrument_calls",
        "dump_function_source",
        "force_advance",
        "probe_sort_state",
    ]
    # F-155 : 12 helpers au total (7 + 4 sondes mouvement + 1 sonde tri).
    assert len(helpers) == 12


# ==========================================
# Attributs d'identité (transparence vis-à-vis du CodeAgent)
# ==========================================
def test_helper_tools_metadata():
    """Chaque helper expose les 4 attributs d'identité smolagents attendus."""
    eval_tool = _FakeEval()
    for cls, expected_name in [
        (DevToolsCleanDomTool, "clean_dom"),
        (DevToolsAddVisualTagsTool, "add_visual_tags"),
        (DevToolsFuzzClickTool, "fuzz_click_all_buttons"),
        (devtools_dom_tools.DevToolsFuzzKeyboardTool, "fuzz_keyboard_controls"),
    ]:
        t = cls(eval_tool)
        assert t.name == expected_name
        assert t.output_type == "string"
        assert t.inputs == {}
        assert isinstance(t.description, str) and len(t.description) > 20
    # F-145 : outils à arguments optionnels — inputs déclarés nullable (exigence smolagents).
    for cls, expected_name, expected_inputs in [
        (devtools_dom_tools.DevToolsProbeCanvasTool, "probe_canvas_activity", {"window_ms"}),
        (devtools_dom_tools.DevToolsExposeGameStateTool, "expose_game_state", {"names"}),
        (devtools_dom_tools.DevToolsInstrumentCallsTool, "instrument_calls", {"names", "window_s"}),
        (devtools_dom_tools.DevToolsDumpFunctionSourceTool, "dump_function_source", {"names"}),
        (devtools_dom_tools.DevToolsForceAdvanceTool, "force_advance", {"fn", "times"}),
        (devtools_dom_tools.DevToolsProbeSortStateTool, "probe_sort_state", {"max_wait_ms"}),
    ]:
        t = cls(eval_tool)
        assert t.name == expected_name
        assert t.output_type == "string"
        assert set(t.inputs.keys()) == expected_inputs
        assert all(spec.get("nullable") for spec in t.inputs.values())
        assert isinstance(t.description, str) and len(t.description) > 20


# ==========================================
# Délégation forward → evaluate_script(function=<bon JS>)
# ==========================================
def test_clean_dom_delegates_with_function_kwarg():
    """clean_dom appelle evaluate_script avec function=_CLEAN_DOM_JS (pas script=)."""
    eval_tool = _FakeEval()
    res = DevToolsCleanDomTool(eval_tool).forward()
    assert res == "FAKE_EVAL_RESULT"
    assert eval_tool.captured_function == _CLEAN_DOM_JS


def test_add_visual_tags_delegates_with_function_kwarg():
    """add_visual_tags appelle evaluate_script avec function=_ADD_VISUAL_TAGS_JS."""
    eval_tool = _FakeEval()
    DevToolsAddVisualTagsTool(eval_tool).forward()
    assert eval_tool.captured_function == _ADD_VISUAL_TAGS_JS


def test_fuzz_click_delegates_with_function_kwarg():
    """fuzz_click_all_buttons appelle evaluate_script avec function=_FUZZ_CLICK_JS."""
    eval_tool = _FakeEval()
    DevToolsFuzzClickTool(eval_tool).forward()
    assert eval_tool.captured_function == _FUZZ_CLICK_JS


# ==========================================
# Contrat JS — non-IIFE (DevTools invoque lui-même)
# ==========================================
def test_js_snippets_are_not_iife():
    """Les snippets JS NE doivent PAS être des IIFE (DevTools evaluate_script lève une
    erreur si on lui passe une fonction auto-invoquée). Forme attendue : `() => { ... }`
    SANS les parenthèses d'invocation finales."""
    for snippet in [_CLEAN_DOM_JS, _ADD_VISUAL_TAGS_JS, _FUZZ_CLICK_JS]:
        assert snippet.startswith("() => "), (
            f"Le snippet doit commencer par '() => ' (fonction non invoquée). Got: {snippet[:40]!r}"
        )
        assert not snippet.endswith(")()"), (
            f"Le snippet NE doit PAS être une IIFE (pas de ')()' final). Got: {snippet[-10:]!r}"
        )


def test_clean_dom_js_preserves_strip_targets():
    """Le JS de clean_dom strippe bien les balises bruyantes attendues (corps préservé
    depuis l'ancien PuppeteerCleanDomTool)."""
    for tag in ["script", "style", "svg", "canvas", "iframe", "noscript", "template"]:
        assert tag in _CLEAN_DOM_JS, f"La balise <{tag}> devrait être strippée par clean_dom."


def test_module_exports_factory():
    """Le module expose bien la factory et les 3 classes (sanity check import)."""
    assert callable(devtools_dom_tools.build_devtools_helper_tools)


# ==========================================
# F-145 — Sondes de preuve de mouvement (post-mortem run #8 Tetris)
# ==========================================
class _FakeEvalCapturing(_FakeEval):
    """Fake qui capture TOUS les kwargs (function + args de sondes F-145)."""

    def __init__(self):
        super().__init__()
        self.captured_kwargs = None

    def forward(self, function=None, **kwargs):
        self.captured_function = function
        self.captured_kwargs = kwargs
        return "FAKE_EVAL_RESULT"


def test_probe_canvas_v2_default_window():
    """probe_canvas_activity sans argument → défaut 2400 interpolé dans le JS.
    F-155 : le MCP REJETTE les kwargs (Unknown argument "window_ms", prouvé run
    2026-08-22_1732) — le paramètre voyage DANS la fonction, jamais à côté."""
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsProbeCanvasTool(ev)
    out = t.forward()
    assert out == "FAKE_EVAL_RESULT"
    assert ev.captured_kwargs == {}, "aucun kwarg ne doit partir vers le MCP"
    assert "Number('2400')" in ev.captured_function


def test_probe_canvas_v2_custom_window():
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsProbeCanvasTool(ev)
    t.forward(window_ms=4000)
    assert ev.captured_kwargs == {}
    assert "Number('4000')" in ev.captured_function


def test_probe_canvas_v2_window_clamped_python_side():
    """Bornage AVANT interpolation (défense en profondeur : le JS borne aussi)."""
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsProbeCanvasTool(ev)
    t.forward(window_ms=999999)
    assert "Number('10000')" in ev.captured_function
    t.forward(window_ms=1)
    assert "Number('800')" in ev.captured_function


def test_probe_canvas_v2_js_uses_rgb_hash_not_pixel_count():
    """Leçon ghostY : une pièce qui tombe garde le MÊME nombre de pixels peints —
    la v2 doit hasher les CANAUX RGB (position), pas compter les pixels."""
    js = devtools_dom_tools._PROBE_CANVAS_V2_JS
    assert "hashRGB" in js
    assert "raf_per_s" in js, "la liveness rAF doit être mesurée (boucle vivante ?)"
    assert "suspect_animation_broken" in js, "verdict STATIC_PAINTED + rAF actif = flag suspect"
    assert "visibility" in js, "onglet caché = rAF gelé → contexte anti-faux-positif"
    assert "d[p]" in js and "d[p+1]" in js, "hash sur les canaux RGB, pas l'alpha seul"
    assert js.startswith("async () => "), "le snippet doit être une fonction non invoquée"


def test_expose_game_state_delegates_with_names_csv():
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsExposeGameStateTool(ev)
    out = t.forward(names="score,lines,board")
    assert out == "FAKE_EVAL_RESULT"
    assert ev.captured_kwargs == {}
    assert "score,lines,board" in ev.captured_function
    assert "changed_over_1500ms" in devtools_dom_tools._EXPOSE_STATE_JS


def test_expose_game_state_default_no_names_kwarg():
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsExposeGameStateTool(ev)
    t.forward()
    assert ev.captured_kwargs == {}
    assert "__NAMES__" not in ev.captured_function, "placeholder remplacé (vide → DEFAULT JS)"


def test_expose_game_state_rejects_non_identifiers():
    """Les noms finissent dans un eval() page-side : seuls les identifiants JS nus passent."""
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsExposeGameStateTool(ev)
    out = t.forward(names="score); fetch('http://evil")
    assert out.startswith("ERROR")
    assert ev.captured_function is None, "evaluate_script ne doit PAS être appelé sur nom invalide"


def test_instrument_calls_delegates_and_defaults():
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsInstrumentCallsTool(ev)
    t.forward()
    assert ev.captured_kwargs == {}
    assert "Number('3')" in ev.captured_function
    t.forward(names="draw,gameLoop", window_s=5)
    assert ev.captured_kwargs == {}
    assert "draw,gameLoop" in ev.captured_function and "Number('5')" in ev.captured_function
    js = devtools_dom_tools._INSTRUMENT_CALLS_JS
    assert "counts[n]++" in js and "eval(n + ' = w')" in js


def test_instrument_calls_rejects_non_identifiers():
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsInstrumentCallsTool(ev)
    out = t.forward(names="draw,alert(1)")
    assert out.startswith("ERROR")
    assert ev.captured_function is None


def test_dump_function_source_delegates_and_caps():
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsDumpFunctionSourceTool(ev)
    t.forward(names="draw")
    assert ev.captured_kwargs == {}
    assert "draw" in ev.captured_function
    js = devtools_dom_tools._DUMP_SOURCE_JS
    assert "v.toString().slice(0, 1200)" in js, "source capée par fonction (contexte)"


def test_dump_function_source_rejects_non_identifiers():
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsDumpFunctionSourceTool(ev)
    out = t.forward(names="draw")
    assert out == "FAKE_EVAL_RESULT"
    out = t.forward(names="draw,x()")
    assert out.startswith("ERROR")


def test_force_advance_defaults_move_down_40():
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsForceAdvanceTool(ev)
    t.forward()
    assert ev.captured_kwargs == {}
    assert "'moveDown'" in ev.captured_function and "Number('40')" in ev.captured_function
    t.forward(fn="update", times=200)
    assert ev.captured_kwargs == {}
    assert "'update'" in ev.captured_function and "Number('200')" in ev.captured_function
    js = devtools_dom_tools._FORCE_ADVANCE_JS
    assert "state_before" in js and "state_after" in js and "last_error" in js


def test_force_advance_rejects_non_identifier_fn():
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsForceAdvanceTool(ev)
    out = t.forward(fn="moveDown();fetch('http://x')")
    assert out.startswith("ERROR")
    assert ev.captured_function is None


def test_split_identifiers_helper():
    names, bad = devtools_dom_tools._split_identifiers("score, lines ,board")
    assert names == ["score", "lines", "board"]
    assert bad == []
    names, bad = devtools_dom_tools._split_identifiers("ok,alert(1),x-y")
    assert names == ["ok", "alert(1)", "x-y"]
    assert bad == ["alert(1)", "x-y"]
    names, bad = devtools_dom_tools._split_identifiers("")
    assert names == [] and bad == []


# ==========================================
# F-155 — Sonde déterministe de tri animé (goulot n°3, run 2026-08-22_1732)
# ==========================================
def test_probe_sort_state_default_wait():
    """probe_sort_state sans argument → défaut 180000 ms interpolé (un tri animé
    peut prendre >120 s — mesuré 144 s sur le livrable du run 1732 avec Chrome
    qui bride les timers ; le verdict revient AVANT dès que c'est trié)."""
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsProbeSortStateTool(ev)
    out = t.forward()
    assert out == "FAKE_EVAL_RESULT"
    assert ev.captured_kwargs == {}, "aucun kwarg ne doit partir vers le MCP"
    assert "Number('180000')" in ev.captured_function


def test_probe_sort_state_custom_wait():
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsProbeSortStateTool(ev)
    t.forward(max_wait_ms=180000)
    assert ev.captured_kwargs == {}
    assert "Number('180000')" in ev.captured_function


def test_probe_sort_state_wait_clamped_python_side():
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsProbeSortStateTool(ev)
    t.forward(max_wait_ms=999999999)
    assert "Number('300000')" in ev.captured_function


def test_probe_sort_state_js_contract():
    """Le JS doit : être une fonction async NON invoquée (anti-IIFE), poller
    in-page jusqu'au verdict (pas de snapshot prématuré), distinguer tri en
    cours (movement) de tri cassé (static), et borner l'attente."""
    js = devtools_dom_tools._PROBE_SORT_STATE_JS
    assert js.startswith("async () => "), "fonction non invoquée attendue"
    assert not js.endswith(")()"), "une IIFE crasherait le CDP"
    for verdict in [
        "SORTED_ALREADY",
        "SORTED_AFTER_WAIT",
        "IN_PROGRESS_STILL_MOVING",
        "STATIC_UNSORTED",
        "NO_TARGETS",
    ]:
        assert verdict in js, f"verdict {verdict} absent de la sonde"
    assert "setTimeout" in js and "POLL_MS" in js, "polling in-page obligatoire"
    assert "Math.max(1000, Math.min(300000" in js, "attente bornée 1s-300s"
    assert "moving_after_timeout" in js, "la distinction en-cours/cassé passe par le mouvement post-timeout"
    assert "performance.now" in js, "waited_ms mesuré côté page"


# ==========================================
# F-155 — Garde syntaxe JS : node --check sur TOUS les snippets interpolés
# (le bug des apostrophes fermantes manquantes dans probe_sort_state n'aurait
# jamais été vu par les tests de délégation — le MCP seul le révélait à l'exécution)
# ==========================================
def test_all_js_snippets_pass_node_check():
    """Chaque snippet, une fois ses placeholders remplacés, doit être du JS
    syntaxiquement valide (const f = <fonction non invoquée>;)."""
    import shutil
    import subprocess
    import tempfile

    if shutil.which("node") is None:
        import pytest
        pytest.skip("node absent — garde syntaxe JS indisponible")

    m = devtools_dom_tools
    snippets = {
        "clean_dom": m._CLEAN_DOM_JS,
        "add_visual_tags": m._ADD_VISUAL_TAGS_JS,
        "fuzz_click": m._FUZZ_CLICK_JS,
        "discover_ui": m._DISCOVER_UI_JS,
        "fuzz_keyboard": m._FUZZ_KEYBOARD_JS,
        "probe_canvas": m._PROBE_CANVAS_V2_JS.replace("__WINDOW_MS__", "2400"),
        "expose_state": m._EXPOSE_STATE_JS.replace("__NAMES__", "score"),
        "instrument_calls": m._INSTRUMENT_CALLS_JS.replace("__NAMES__", "draw").replace("__WINDOW_S__", "3"),
        "dump_source": m._DUMP_SOURCE_JS.replace("__NAMES__", "draw"),
        "force_advance": m._FORCE_ADVANCE_JS.replace("__FN__", "moveDown").replace("__TIMES__", "40"),
        "probe_sort_state": m._PROBE_SORT_STATE_JS.replace("__MAX_WAIT_MS__", "120000"),
    }
    failures = []
    with tempfile.TemporaryDirectory() as td:
        for name, js in snippets.items():
            path = os.path.join(td, f"{name}.js")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("const f = " + js + ";\n")
            r = subprocess.run(["node", "--check", path], capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                failures.append((name, r.stderr[:200]))
    assert not failures, f"Snippets JS syntaxiquement invalides : {failures}"


def test_no_placeholder_left_after_interpolation():
    """Un placeholder oublié (ex __MAX_WAIT_MS__) devient NaN côté JS — le
    wrapper doit TOUJOURS remplacer avant l'appel MCP."""
    ev = _FakeEvalCapturing()
    devtools_dom_tools.DevToolsProbeSortStateTool(ev).forward()
    assert "__MAX_WAIT_MS__" not in ev.captured_function
    devtools_dom_tools.DevToolsProbeCanvasTool(ev).forward(window_ms=1000)
    assert "__WINDOW_MS__" not in ev.captured_function
