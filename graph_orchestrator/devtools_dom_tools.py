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


_PROBE_CANVAS_JS = (
    "async () => {"
    " const canvases = Array.from(document.querySelectorAll('canvas'));"
    " if (canvases.length === 0) return JSON.stringify({ has_canvas: false, message: 'Aucun canvas dans la page.' });"
    " const results = [];"
    " for (let i = 0; i < canvases.length; i++) {"
    "   const c = canvases[i];"
    "   const rect = c.getBoundingClientRect();"
    "   const w = c.width || rect.width;"
    "   const h = c.height || rect.height;"
    "   let ctx = null;"
    "   try { ctx = c.getContext('2d'); } catch(e){}"
    "   if (!ctx) {"
    "     results.push({ index: i, width: w, height: h, is_inert: false, note: 'WebGL/non-2D' });"
    "     continue;"
    "   }"
    "   let img1 = null;"
    "   try { img1 = ctx.getImageData(0, 0, Math.min(w, 200), Math.min(h, 200)).data; } catch(e){}"
    "   let painted = 0;"
    "   if (img1) {"
    "     for (let p = 3; p < img1.length; p += 4) { if (img1[p] > 0) painted++; }"
    "   }"
    "   await new Promise(r => setTimeout(r, 400));"
    "   let img2 = null;"
    "   try { img2 = ctx.getImageData(0, 0, Math.min(w, 200), Math.min(h, 200)).data; } catch(e){}"
    "   let changed = 0;"
    "   if (img1 && img2) {"
    "     for (let p = 0; p < Math.min(img1.length, img2.length); p += 4) {"
    "       if (img1[p] !== img2[p] || img1[p+1] !== img2[p+1] || img1[p+2] !== img2[p+2]) changed++;"
    "     }"
    "   }"
    "   const is_inert = (painted === 0);"
    "   const is_animating = (changed > 0);"
    "   results.push({"
    "     index: i,"
    "     width: w,"
    "     height: h,"
    "     rect_width: rect.width,"
    "     rect_height: rect.height,"
    "     painted_pixels: painted,"
    "     changed_pixels_400ms: changed,"
    "     is_inert: is_inert,"
    "     is_animating: is_animating,"
    "     status: (is_inert ? 'INERT/EMPTY' : (w < 50 || h < 50 ? 'TOO_SMALL' : 'ACTIVE'))"
    "   });"
    " }"
    " return JSON.stringify({ has_canvas: true, canvases: results });"
    "}"
)


class DevToolsProbeCanvasTool(Tool):
    name = "probe_canvas_activity"
    description = (
        "Sonde d'activité Canvas (Browser-Use / Stagehand) : analyse les balises <canvas>. "
        "Vérifie la surface peinte (> 0 pixels non vides) et compare 2 captures à 400ms d'intervalle "
        "pour prouver que la boucle 60 FPS est active et que la toile n'est pas inerte ou écrasée. "
        "À appeler SANS ARGUMENT."
    )
    inputs = {}
    output_type = "string"

    def __init__(self, evaluate_script_tool: Tool):
        super().__init__()
        self._eval = evaluate_script_tool

    def forward(self) -> str:
        return self._eval(function=_PROBE_CANVAS_JS)


_FUZZ_KEYBOARD_JS = (
    "() => {"
    " const keys = ['ArrowLeft', 'ArrowRight', 'ArrowDown', 'ArrowUp', 'Space', 'KeyZ', 'KeyX', 'Enter'];"
    " const errors = [];"
    " const handler = (e) => { errors.push(e.message || String(e)); };"
    " window.addEventListener('error', handler);"
    " try {"
    "   for (const key of keys) {"
    "     const code = key.startsWith('Key') ? key : (key === 'Space' ? 'Space' : key);"
    "     const k = key === 'Space' ? ' ' : key;"
    "     window.dispatchEvent(new KeyboardEvent('keydown', { key: k, code: code, bubbles: true, cancelable: true }));"
    "     window.dispatchEvent(new KeyboardEvent('keyup', { key: k, code: code, bubbles: true, cancelable: true }));"
    "   }"
    " } catch (err) {"
    "   errors.push(err.message || String(err));"
    " } finally {"
    "   window.removeEventListener('error', handler);"
    " }"
    " return JSON.stringify({ keys_tested: keys, unhandled_errors: errors });"
    "}"
)


class DevToolsFuzzKeyboardTool(Tool):
    name = "fuzz_keyboard_controls"
    description = (
        "Interception des exceptions clavier (Browser-Use) : simule les touches de jeu (Flèches, Espace, Z, X) "
        "en capturant immédiatement tout crash ou exception JS non gérée. À appeler SANS ARGUMENT."
    )
    inputs = {}
    output_type = "string"

    def __init__(self, evaluate_script_tool: Tool):
        super().__init__()
        self._eval = evaluate_script_tool

    def forward(self) -> str:
        return self._eval(function=_FUZZ_KEYBOARD_JS)


# F-127 (post-mortem run 2026-08-19_2104) : le Web Tester brûlait 3-4 steps à
# DÉCOUVRIR la page (ID du canvas deviné 'canvas' vs réel 'gameCanvas', boutons,
# champs) avant de pouvoir tester. Un seul appel renvoie l'inventaire UI complet.
_DISCOVER_UI_JS = (
    "() => { const q = s => [...document.querySelectorAll(s)];"
    " const txt = el => (el.textContent || '').trim().slice(0, 40);"
    " return JSON.stringify({"
    " url: location.href, title: document.title,"
    " canvases: q('canvas').map(c => ({ id: c.id || null, width: c.width, height: c.height })),"
    " buttons: q('button').map(b => ({ id: b.id || null, text: txt(b) })),"
    " inputs: q('input, select').map(i => ({ id: i.id || null, type: i.type || null })),"
    " keyElements: q('h1, h2, [class*=score], [class*=level]').map(txt).filter(Boolean).slice(0, 8),"
    " visibleTextSample: (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 300)"
    " }); }"
)


class DevToolsDiscoverUiTool(Tool):
    name = "discover_ui"
    description = (
        "Inventaire UI complet en 1 appel : IDs et dimensions des <canvas>, boutons (id+texte), "
        "champs (id+type), éléments clés et échantillon de texte visible. À appeler EN PREMIER "
        "juste après navigate_page pour connaître les VRAIS IDs avant tout evaluate_script — "
        "ne devine JAMAIS un ID DOM."
    )
    inputs = {}
    output_type = "string"

    def __init__(self, evaluate_script_tool: Tool):
        super().__init__()
        self._eval = evaluate_script_tool

    def forward(self) -> str:
        return self._eval(function=_DISCOVER_UI_JS)


# P6/F-139 (port Scrapling retrieve_similar, parser.py:530) : JS de scoring
# de similarité pour re-localiser un élément disparu. Score = tag exact
# (+0.35) + similarité texte (rapport longueur commune, jusqu'à +0.4) +
# recouvrement d'attributs clés (id/class/data-*, jusqu'à +0.25). Seuil
# d'acceptation 0.4 (miroir Scrapling AUTO_MATCH). Cap 2000 éléments.
_HEAL_SELECTOR_JS = """
(tag, textHint, attrHint) => {
  const MAX = 2000;
  const els = Array.from(document.querySelectorAll('*')).slice(0, MAX);
  const norm = (s) => (s || '').toLowerCase().trim();
  const textHintN = norm(textHint);
  const attrHintN = norm(attrHint);
  let best = null;
  for (const el of els) {
    if (el.tagName.toLowerCase() !== String(tag).toLowerCase()) continue;
    let score = 0.35;
    const t = norm(el.textContent).slice(0, 200);
    if (textHintN) {
      const a = textHintN.slice(0, 200);
      let common = 0;
      for (let i = 0; i < Math.min(a.length, t.length); i++) {
        if (a[i] === t[i]) common++;
      }
      const denom = Math.max(a.length, t.length) || 1;
      if (Math.max(a.length, t.length) < 8) score += (a === t) ? 0.4 : 0;
      else score += 0.4 * (common / denom);
    }
    if (attrHintN) {
      const attrs = Array.from(el.attributes).map(
        (at) => at.name + '=' + norm(at.value)
      ).join('|');
      let hits = 0;
      for (const part of attrHintN.split('|')) {
        if (part && attrs.includes(part)) hits++;
      }
      const total = attrHintN.split('|').filter(Boolean).length || 1;
      score += 0.25 * (hits / total);
    }
    if (!best || score > best.score) {
      best = {
        score: Math.round(score * 100) / 100,
        tag: el.tagName.toLowerCase(),
        id: el.id || null,
        text: (el.textContent || '').trim().slice(0, 80),
        selector: el.id ? ('#' + el.id) : (
          el.className && typeof el.className === 'string'
            ? (el.tagName.toLowerCase() + '.' + el.className.trim().split(/\\s+/).join('.'))
            : el.tagName.toLowerCase()
        )
      };
    }
  }
  if (!best || best.score < 0.4) {
    return JSON.stringify({ found: false, message: 'Aucun candidat >= 0.4' });
  }
  return JSON.stringify({ found: true, ...best });
}
"""


class DevToolsHealSelectorTool(Tool):
    name = "heal_selector"
    description = (
        "Self-healing de sélecteur (port Scrapling) : quand ton sélecteur (ex: '#startBtn') "
        "ne trouve PLUS l'élément (régénéré/renommé par un fix), re-localise-le par similarité. "
        "Args : tag (ex: 'button'), text_hint (texte visible de l'élément, ex: 'Start'), "
        "attr_hint (attributs attendus 'class=btn primary|data-action=start', optionnel). "
        "Retourne le meilleur candidat (score >= 0.4) avec son sélecteur — évite un FAIL de test "
        "sur un simple renommage."
    )
    inputs = {
        "tag": {"type": "string", "description": "tag HTML de l'élément cherché"},
        "text_hint": {"type": "string", "description": "texte visible attendu", "nullable": True},
        "attr_hint": {"type": "string", "description": "attributs attendus, 'k=v|k2=v2'", "nullable": True},
    }
    output_type = "string"

    def __init__(self, evaluate_script_tool: Tool):
        super().__init__()
        self._eval = evaluate_script_tool

    def forward(self, tag: str, text_hint: str = "", attr_hint: str = "") -> str:
        return self._eval(function=_HEAL_SELECTOR_JS, args=[tag, text_hint, attr_hint])


def build_devtools_helper_tools(cdt_tools: List[Tool]) -> List[Tool]:
    """Factory fail-open : instancie les helpers DevTools si ``evaluate_script`` est dispo.

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
        DevToolsDiscoverUiTool(eval_tool),
        DevToolsCleanDomTool(eval_tool),
        DevToolsAddVisualTagsTool(eval_tool),
        DevToolsFuzzClickTool(eval_tool),
        DevToolsProbeCanvasTool(eval_tool),
        DevToolsFuzzKeyboardTool(eval_tool),
        DevToolsHealSelectorTool(eval_tool),
    ]
