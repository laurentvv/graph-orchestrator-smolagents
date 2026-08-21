"""Tests unitaires de ``devtools_dom_tools`` (F-72 — Prompt Offloading).

Vérifie la factory fail-open et la délégation correcte : chaque helper appelle
``evaluate_script`` avec le bon snippet JS (passé via ``function=``, pas ``script=``),
sur le navigateur DevTools actif (et non Puppeteer, qui ne charge pas les file://).

0 LLM, 0 réseau, 0 navigateur — on mocke ``evaluate_script`` avec un fake qui capture
l'argument ``function``.
"""
from __future__ import annotations

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


def test_factory_with_evaluate_script_returns_eleven_helpers():
    """evaluate_script présent → factory retourne les 11 helpers (bons noms).

    F-127 : discover_ui en TÊTE. F-145 : +4 sondes de preuve de mouvement."""
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
    ]
    # F-145 : 11 helpers au total (7 + 4 sondes preuve de mouvement).
    assert len(helpers) == 11


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
    """probe_canvas_activity sans argument → window_ms=2400 par défaut (une chute
    à 800ms/row était INVISIBLE avec les 400 ms fixes de la v1)."""
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsProbeCanvasTool(ev)
    out = t.forward()
    assert out == "FAKE_EVAL_RESULT"
    assert ev.captured_kwargs == {"window_ms": 2400}


def test_probe_canvas_v2_custom_window():
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsProbeCanvasTool(ev)
    t.forward(window_ms=4000)
    assert ev.captured_kwargs == {"window_ms": 4000}


def test_probe_canvas_v2_js_uses_rgb_hash_not_pixel_count():
    """Leçon ghostY : une pièce qui tombe garde le MÊME nombre de pixels peints —
    la v2 doit hasher les CANAUX RGB (position), pas compter les pixels."""
    js = devtools_dom_tools._PROBE_CANVAS_V2_JS
    assert "hashRGB" in js
    assert "raf_per_s" in js, "la liveness rAF doit être mesurée (boucle vivante ?)"
    assert "suspect_animation_broken" in js, "verdict STATIC_PAINTED + rAF actif = flag suspect"
    assert "visibility" in js, "onglet caché = rAF gelé → contexte anti-faux-positif"
    assert "d[p]" in js and "d[p+1]" in js, "hash sur les canaux RGB, pas l'alpha seul"
    assert js.startswith("async (window_ms) => "), "le snippet doit être une fonction non invoquée"


def test_expose_game_state_delegates_with_names_csv():
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsExposeGameStateTool(ev)
    out = t.forward(names="score,lines,board")
    assert out == "FAKE_EVAL_RESULT"
    assert ev.captured_kwargs == {"names_csv": "score,lines,board"}
    assert "changed_over_1500ms" in devtools_dom_tools._EXPOSE_STATE_JS


def test_expose_game_state_default_no_names_kwarg():
    ev = _FakeEvalCapturing()
    t = devtools_dom_tools.DevToolsExposeGameStateTool(ev)
    t.forward()
    assert ev.captured_kwargs == {"names_csv": None}


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
    assert ev.captured_kwargs == {"names_csv": None, "window_s": 3}
    t.forward(names="draw,gameLoop", window_s=5)
    assert ev.captured_kwargs == {"names_csv": "draw,gameLoop", "window_s": 5}
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
    assert ev.captured_kwargs == {"names_csv": "draw"}
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
    assert ev.captured_kwargs == {"fn": "moveDown", "times": 40}
    t.forward(fn="update", times=200)
    assert ev.captured_kwargs == {"fn": "update", "times": 200}
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
