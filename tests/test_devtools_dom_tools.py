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


def test_factory_with_evaluate_script_returns_six_helpers():
    """evaluate_script présent → factory retourne les 6 helpers (bons noms).

    F-127 : discover_ui ajouté EN TÊTE (inventaire UI à appeler en premier)."""
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
    ]
    assert len(helpers) == 6


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
        (devtools_dom_tools.DevToolsProbeCanvasTool, "probe_canvas_activity"),
        (devtools_dom_tools.DevToolsFuzzKeyboardTool, "fuzz_keyboard_controls"),
    ]:
        t = cls(eval_tool)
        assert t.name == expected_name
        assert t.output_type == "string"
        assert t.inputs == {}
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
