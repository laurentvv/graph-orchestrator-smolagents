"""Outils DevTools helper — encapsulent des snippets JS récurrents en outils dédiés.

F-72 (Prompt Offloading) : ces snippets vivaient auparavant soit en texte brut dans
les prompts du Coder/Tester (ex: fuzzing UI ``nodes.py``), soit dans des sous-classes
imbriquées **mortes** (``PuppeteerCleanDomTool``/``PuppeteerAddVisualTagsTool`` de
``web_tester.py``) qui wrappaient ``puppeteer_evaluate``. Or le navigateur Puppeteer
ne charge pas les fichiers ``file://`` locaux (bug du serveur MCP déprécié) → DevTools
(``evaluate_script``) est devenu le pilote PRIMAIRE. Les outils helper ont donc été
recréés ici pour wrapper ``evaluate_script``.

Bénéfice : le JS vit dans l'outil (description 1 ligne expose l'INTENTION), pas dans
le prompt (gain de contexte + charge cognitive réduite pour les petits LLM locaux).

Adaptation des snippets Puppeteer → DevTools : le corps JS est préservé **exact**,
mais l'enveloppe IIFE ``(() => { ... })()`` est retirée. DevTools ``evaluate_script``
exige une fonction **non invoquée** ``() => { ... }`` (il l'invoque lui-même) — passer
une IIFE crasherait (cf. avertissement anti-IIFE des prompts).

Patron : sous-classes ``smolagents.Tool`` qui délèguent à l'outil MCP ``evaluate_script``
via ``function=``. Factory fail-open : si ``evaluate_script`` est absent (DevTools
indisponible), retourne ``[]`` (l'agent tourne sans ces helpers).
"""
from __future__ import annotations

import logging
from typing import List

from smolagents import Tool

logger = logging.getLogger(__name__)


# Snippets JS — corps préservés exacts des prompts/anciennes classes (0 changement
# comportemental), enveloppe IIFE retirée pour la compatibilité DevTools evaluate_script.
_CLEAN_DOM_JS = (
    "() => { const clone = document.documentElement.cloneNode(true);"
    " clone.querySelectorAll('script,style,svg,canvas,iframe,noscript,template')"
    ".forEach(el => el.remove());"
    " return clone.outerHTML.replace(/<!--[\\s\\S]*?-->/g,'')"
    ".replace(/\\s{2,}/g,' ').slice(0, 8000); }"
)

_ADD_VISUAL_TAGS_JS = (
    "() => { let c = 1;"
    " document.querySelectorAll('button, input, select, a').forEach(el => {"
    " const r = el.getBoundingClientRect();"
    " if (r.width === 0 || r.height === 0) return;"
    " const b = document.createElement('div');"
    " b.innerText = 'e' + c++;"
    " b.style.cssText = `position:absolute; left:${r.left+window.scrollX}px;"
    " top:${r.top+window.scrollY-10}px; background:red; color:white;"
    " font-size:12px; padding:2px; z-index:9999; pointer-events:none;`;"
    " document.body.appendChild(b); });"
    " return 'Tags OpenFox injectés avec succès. Prends un screenshot maintenant !'; }"
)

_FUZZ_CLICK_JS = (
    "() => { document.querySelectorAll('button').forEach(b => b.click());"
    " return 'Fuzzing: tous les <button> cliqués.'; }"
)


class DevToolsCleanDomTool(Tool):
    name = "clean_dom"
    description = (
        "Nettoie le DOM de la page Chrome DevTools active (supprime script, style, svg, "
        "canvas, iframe, noscript, template) et renvoie le HTML allégé (max 8000 chars). "
        "À appeler SANS ARGUMENT pour analyser la structure de la page sans polluer ton "
        "contexte."
    )
    inputs = {}
    output_type = "string"

    def __init__(self, evaluate_script_tool: Tool):
        super().__init__()
        self._eval = evaluate_script_tool

    def forward(self) -> str:
        return self._eval(function=_CLEAN_DOM_JS)


class DevToolsAddVisualTagsTool(Tool):
    name = "add_visual_tags"
    description = (
        "Ajoute des badges rouges numérotés (e1, e2...) sur tous les éléments cliquables "
        "VISIBLES de la page Chrome DevTools active. À appeler SANS ARGUMENT AVANT "
        "take_screenshot pour faciliter le repérage/clic (méthode OpenFox)."
    )
    inputs = {}
    output_type = "string"

    def __init__(self, evaluate_script_tool: Tool):
        super().__init__()
        self._eval = evaluate_script_tool

    def forward(self) -> str:
        return self._eval(function=_ADD_VISUAL_TAGS_JS)


class DevToolsFuzzClickTool(Tool):
    name = "fuzz_click_all_buttons"
    description = (
        "Monkey testing : clique TOUS les <button> de la page Chrome DevTools active pour "
        "réveiller les bugs JS cachés (handlers manquants, exceptions au clic). À appeler "
        "SANS ARGUMENT, puis enchaîne avec list_console_messages pour capter les erreurs."
    )
    inputs = {}
    output_type = "string"

    def __init__(self, evaluate_script_tool: Tool):
        super().__init__()
        self._eval = evaluate_script_tool

    def forward(self) -> str:
        return self._eval(function=_FUZZ_CLICK_JS)


def build_devtools_helper_tools(cdt_tools: List[Tool]) -> List[Tool]:
    """Factory fail-open : instancie les 3 helpers DevTools si ``evaluate_script`` est dispo.

    Retourne ``[]`` si DevTools est indisponible (``cdt_tools`` vide) ou si
    ``evaluate_script`` n'y figure pas — l'agent tourne alors sans ces helpers
    (dégradation gracieuse).
    """
    eval_tool = next(
        (t for t in cdt_tools if getattr(t, "name", "") == "evaluate_script"), None
    )
    if eval_tool is None:
        logger.debug(
            "devtools_dom_tools : evaluate_script absent — helpers DOM skip (fail-open)."
        )
        return []
    return [
        DevToolsCleanDomTool(eval_tool),
        DevToolsAddVisualTagsTool(eval_tool),
        DevToolsFuzzClickTool(eval_tool),
    ]
