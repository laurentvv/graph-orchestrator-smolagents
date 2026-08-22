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


# F-155 : les paramètres sont INTERPOLÉS dans le JS (placeholders __TOKEN__),
# jamais passés en kwargs — le MCP chrome-devtools REJETTE tout argument hors
# function/args/filePath/dialogAction (« Unknown argument "window_ms" », prouvé
# run 2026-08-22_1732 : les helpers F-145 paramétrés échouaient en prod depuis
# leur création, seuls leurs défauts JS fonctionnaient). Le wrapper clampe et
# valide côté Python AVANT interpolation (ints bornés, identifiants nus).
_PROBE_CANVAS_V2_JS = (
    "async () => {"
    " const wm = Math.max(800, Math.min(10000, Number('__WINDOW_MS__')));"
    " const canvases = Array.from(document.querySelectorAll('canvas'));"
    " if (canvases.length === 0) return JSON.stringify({ has_canvas: false, message: 'Aucun canvas dans la page.' });"
    # liveness rAF : 1 s dédiée (un onglet caché gèle rAF → contexte pour écarter un faux positif)
    " let raf = 0; let rafStop = false;"
    " const rafTick = () => { if (rafStop) return; raf++; requestAnimationFrame(rafTick); };"
    " requestAnimationFrame(rafTick);"
    " await new Promise(r => setTimeout(r, 1000));"
    " rafStop = true;"
    " const raf_per_s = raf;"
    " const hashRGB = (d) => { let h = 5381; for (let p = 0; p < d.length; p += 12) { h = (((h * 33) ^ d[p]) ^ d[p+1]) ^ d[p+2]; } return h >>> 0; };"
    " const grab = (ctx, w, h) => { try { return ctx.getImageData(0, 0, Math.min(w, 400), Math.min(h, 400)).data; } catch (e) { return null; } };"
    " const results = [];"
    " for (let i = 0; i < canvases.length; i++) {"
    "   const c = canvases[i];"
    "   const rect = c.getBoundingClientRect();"
    "   const w = c.width || rect.width;"
    "   const h = c.height || rect.height;"
    "   let ctx = null;"
    "   try { ctx = c.getContext('2d'); } catch(e){}"
    "   if (!ctx) {"
    "     results.push({ index: i, width: w, height: h, status: 'NON_2D', note: 'WebGL/non-2D' });"
    "     continue;"
    "   }"
    "   const d0 = grab(ctx, w, h);"
    "   let painted = -1;"
    "   if (d0) { painted = 0; for (let p = 0; p < d0.length; p += 12) { if (d0[p] || d0[p+1] || d0[p+2]) painted++; } }"
    # hash RGB (F-145) : une pièce qui tombe garde le MÊME nombre de pixels peints —
    # seul un hash de position change. 4 échantillons espacés de window/3.
    "   const hashes = [];"
    "   if (d0) hashes.push(hashRGB(d0));"
    "   const nSamples = 3; const step = wm / nSamples;"
    "   for (let k = 1; k <= nSamples; k++) { await new Promise(r => setTimeout(r, step)); const d = grab(ctx, w, h); if (d) hashes.push(hashRGB(d)); }"
    "   let changed = false;"
    "   for (let k = 1; k < hashes.length; k++) { if (hashes[k] !== hashes[k-1]) { changed = true; break; } }"
    "   let status; let suspect = false;"
    "   if (painted === 0) status = 'INERT_EMPTY';"
    "   else if (w < 50 || h < 50) status = 'TOO_SMALL';"
    "   else if (changed) status = 'ANIMATING';"
    "   else { status = 'STATIC_PAINTED'; if (raf_per_s > 0) suspect = true; }"
    "   results.push({"
    "     index: i,"
    "     width: w,"
    "     height: h,"
    "     painted_sampled: painted,"
    "     samples: hashes.length,"
    "     changed: changed,"
    "     status: status,"
    "     suspect_animation_broken: suspect"
    "   });"
    " }"
    " const anySuspect = results.some(r => r.suspect_animation_broken);"
    " return JSON.stringify({"
    "   has_canvas: true,"
    "   visibility: document.visibilityState,"
    "   raf_per_s: raf_per_s,"
    "   window_ms: wm,"
    "   canvases: results,"
    "   hint: anySuspect ? 'BOUCLE rAF ACTIVE MAIS RENDU FIGÉ — animation probablement cassée (ex: pièce dessinée via la mauvaise variable). Diagnostique avec dump_function_source() sur la fonction draw().' : null"
    " });"
    "}"
)


class DevToolsProbeCanvasTool(Tool):
    name = "probe_canvas_activity"
    description = (
        "Sonde d'activité Canvas (F-145) : hash RGB de chaque <canvas> 2D en 4 échantillons "
        "sur une fenêtre paramétrable window_ms (défaut 2400, min 800 — une chute de pièce à "
        "800ms/row est INVISIBLE sous 800ms de fenêtre). Mesure aussi raf_per_s (boucle vivante ?) "
        "et visibility (onglet caché = rAF gelé, écarter le faux positif). Verdicts : ANIMATING / "
        "STATIC_PAINTED / INERT_EMPTY / NON_2D + flag suspect_animation_broken quand la boucle "
        "tourne mais que le rendu ne change JAMAIS (bug du genre pièce dessinée à ghostY au lieu de y). "
        "À appeler SANS ARGUMENT (fenêtre défaut) ou avec window_ms=4000 pour un jeu lent."
    )
    inputs = {
        "window_ms": {
            "type": "integer",
            "description": "durée totale d'observation en ms (défaut 2400, bornes 800-10000)",
            "nullable": True,
        },
    }
    output_type = "string"

    def __init__(self, evaluate_script_tool: Tool):
        super().__init__()
        self._eval = evaluate_script_tool

    def forward(self, window_ms=None) -> str:
        wm = 2400 if window_ms is None else max(800, min(10000, int(window_ms)))
        return self._eval(function=_PROBE_CANVAS_V2_JS.replace("__WINDOW_MS__", str(wm)))


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


# --- F-145 : sondes de preuve de mouvement (post-mortem run #8 Tetris) --------
# La sonde canvas v1 (400 ms fixes) était disponible au Tester du run #8 et n'a
# pas pu voir le bug ghostY : une chute à 800 ms/row ne change rien sous 800 ms
# de fenêtre, et un compte de pixels peints ne bouge pas quand une pièce tombe
# (même nombre de cellules). Ces 4 outils portent la méthode de debug qui a
# trouvé le bug manuellement : lire l'ÉTAT interne, compter les APPELS réels,
# lire le SOURCE des fonctions, accélérer l'HORLOGE du jeu.

import re as _re

_IDENT_RE = _re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def _split_identifiers(names_csv: str, limit: int = 30):
    """Splitte une liste CSV de noms JS et rejette les non-identifiants.

    Les noms finissent dans un eval() page-side : on n'accepte que des
    identifiants JS nus (robustesse — evaluate_script reste du JS complet
    pour l'agent, il n'y a pas d'escalade de privilège ici).
    """
    names = [n.strip() for n in (names_csv or "").split(",") if n.strip()]
    bad = [n for n in names if not _IDENT_RE.match(n)]
    return names[:limit], bad


# F-155 : __NAMES__ interpolé côté Python (voir note _PROBE_CANVAS_V2_JS).
_EXPOSE_STATE_JS = (
    "async () => {"
    " const DEFAULT = 'score,lines,level,best,paused,gameOver,isGameOver,running,isPlaying,playing,started,currentPiece,board,grid,lives,time,frame,frameCount,coins';"
    " const names = ('__NAMES__' || DEFAULT).split(',').map(s => s.trim()).filter(Boolean).slice(0, 30);"
    " const read = (n) => {"
    "   try {"
    "     const v = eval(n);"
    "     if (v === undefined) return { missing: true };"
    "     if (v === null || typeof v === 'boolean' || typeof v === 'number') return { value: v };"
    "     if (typeof v === 'string') return { value: v.slice(0, 80) };"
    "     if (typeof v === 'function') return { kind: 'function' };"
    "     if (Array.isArray(v)) return { kind: 'array', length: v.length };"
    "     if (typeof v === 'object') {"
    "       if (n === 'board' || n === 'grid') { let nz = 0; for (const row of v) { if (Array.isArray(row)) for (const cell of row) { if (cell) nz++; } } return { kind: 'grid', rows: v.length, non_empty_cells: nz }; }"
    "       try { return { kind: 'object', json: JSON.stringify(v).slice(0, 200) }; } catch (e) { return { kind: 'object' }; }"
    "     }"
    "     return { kind: typeof v };"
    "   } catch (e) { return { missing: true }; }"
    " };"
    " const snap = () => { const o = {}; for (const n of names) o[n] = read(n); return o; };"
    " const t0 = snap();"
    " await new Promise(r => setTimeout(r, 1500));"
    " const t1 = snap();"
    " const changed = [];"
    " for (const n of names) { if (JSON.stringify(t0[n]) !== JSON.stringify(t1[n])) changed.push(n); }"
    " return JSON.stringify({ names: names, values: t1, changed_over_1500ms: changed, note: 'changed vide = etat fige (normal sans action ; ANORMAL pour un jeu anime en cours)' });"
    "}"
)


class DevToolsExposeGameStateTool(Tool):
    name = "expose_game_state"
    description = (
        "Lit l'ÉTAT INTERNE du jeu/page (F-145) : les variables top-level des <script> classiques "
        "(score, lines, level, paused, gameOver, currentPiece, board...) sont accessibles par "
        "identifiant nu. Deux snapshots espacés de 1,5 s → changed_over_1500ms prouve si l'état VIT. "
        "Args : names='score,lines,board' (optionnel, liste par défaut fournie). Un jeu dont l'état "
        "change mais dont le canvas est figé (voir probe_canvas_activity) = bug de rendu."
    )
    inputs = {
        "names": {
            "type": "string",
            "description": "liste CSV d'identifiants JS (défaut: score,lines,level,best,paused,gameOver,currentPiece,board,...)",
            "nullable": True,
        },
    }
    output_type = "string"

    def __init__(self, evaluate_script_tool: Tool):
        super().__init__()
        self._eval = evaluate_script_tool

    def forward(self, names=None) -> str:
        if names:
            _, bad = _split_identifiers(names)
            if bad:
                return f"ERROR (expose_game_state) : noms invalides {bad} — identifiants JS nuds uniquement, séparés par des virgules."
        return self._eval(function=_EXPOSE_STATE_JS.replace("__NAMES__", (names or "").strip()))


# F-155 : __NAMES__/__WINDOW_S__ interpolés côté Python (voir note _PROBE_CANVAS_V2_JS).
_INSTRUMENT_CALLS_JS = (
    "async () => {"
    " const DEFAULT = 'draw,update,gameLoop,loop,tick,render,animate,moveDown,updateHUD,updateScore,spawnPiece';"
    " const names = ('__NAMES__' || DEFAULT).split(',').map(s => s.trim()).filter(Boolean).slice(0, 20);"
    " const ws = Math.max(1, Math.min(30, Number('__WINDOW_S__')));"
    " const counts = {}; const wrapped = [];"
    " for (const n of names) {"
    "   try {"
    "     const v = eval(n);"
    "     if (typeof v !== 'function') { counts[n] = 'not_a_function'; continue; }"
    "     counts[n] = 0;"
    "     const w = function (...a) { counts[n]++; return v.apply(this, a); };"
    "     eval(n + ' = w');"
    "     wrapped.push(n);"
    "   } catch (e) { counts[n] = 'error'; }"
    " }"
    " await new Promise(r => setTimeout(r, ws * 1000));"
    " return JSON.stringify({ wrapped: wrapped, window_s: ws, calls: counts, note: '0 appels = fonction morte/jamais appelée ; n>0 = boucle vivante (si le canvas reste figé → bug de rendu)' });"
    "}"
)


class DevToolsInstrumentCallsTool(Tool):
    name = "instrument_calls"
    description = (
        "Compteur de vie (F-145) : wrappe les fonctions globales du jeu (draw, gameLoop, moveDown...) "
        "et compte leurs APPELS RÉELS pendant window_s secondes (défaut 3). Prouve que la boucle "
        "tourne et que la gravité tire — discrimine « moteur mort » vs « moteur vivant mais rendu figé ». "
        "Args : names='draw,gameLoop' (optionnel), window_s=3 (optionnel)."
    )
    inputs = {
        "names": {"type": "string", "description": "liste CSV de fonctions à wrapper", "nullable": True},
        "window_s": {"type": "integer", "description": "durée d'observation en secondes (défaut 3)", "nullable": True},
    }
    output_type = "string"

    def __init__(self, evaluate_script_tool: Tool):
        super().__init__()
        self._eval = evaluate_script_tool

    def forward(self, names=None, window_s=None) -> str:
        if names:
            _, bad = _split_identifiers(names, limit=20)
            if bad:
                return f"ERROR (instrument_calls) : noms invalides {bad} — identifiants JS nuds uniquement."
        ws = 3 if window_s is None else max(1, min(30, int(window_s)))
        js = _INSTRUMENT_CALLS_JS.replace("__NAMES__", (names or "").strip()).replace("__WINDOW_S__", str(ws))
        return self._eval(function=js)


# F-155 : __NAMES__ interpolé côté Python (voir note _PROBE_CANVAS_V2_JS).
_DUMP_SOURCE_JS = (
    "() => {"
    " const DEFAULT = 'draw,update,gameLoop,loop,tick,render,moveDown,spawnPiece,collide,moveLeft,moveRight,rotate,merge,clearLines';"
    " const names = ('__NAMES__' || DEFAULT).split(',').map(s => s.trim()).filter(Boolean).slice(0, 10);"
    " const out = {};"
    " for (const n of names) {"
    "   try {"
    "     const v = eval(n);"
    "     out[n] = typeof v === 'function' ? v.toString().slice(0, 1200) : '[' + typeof v + ']';"
    "   } catch (e) { out[n] = '[absent]'; }"
    " }"
    " return JSON.stringify({ sources: out, note: 'Cherche les inversions de variables (ex: dessiner (ghostY+r) au lieu de (currentPiece.y+r)) et les conditions jamais vraies.' });"
    "}"
)


class DevToolsDumpFunctionSourceTool(Tool):
    name = "dump_function_source"
    description = (
        "Lecture de source in-page (F-145) : renvoie le code source (Function.prototype.toString) "
        "des fonctions globales du jeu — draw, gameLoop, moveDown... C'est ainsi qu'a été trouvé le "
        "bug ghostY (pièce dessinée à la mauvaise variable, invisible sur un screenshot). "
        "Args : names='draw,gameLoop' (optionnel, max 10 fonctions)."
    )
    inputs = {
        "names": {"type": "string", "description": "liste CSV de fonctions à dumper", "nullable": True},
    }
    output_type = "string"

    def __init__(self, evaluate_script_tool: Tool):
        super().__init__()
        self._eval = evaluate_script_tool

    def forward(self, names=None) -> str:
        if names:
            _, bad = _split_identifiers(names, limit=10)
            if bad:
                return f"ERROR (dump_function_source) : noms invalides {bad} — identifiants JS nuds uniquement."
        return self._eval(function=_DUMP_SOURCE_JS.replace("__NAMES__", (names or "").strip()))


# F-155 : __FN__/__TIMES__ interpolés côté Python (voir note _PROBE_CANVAS_V2_JS).
_FORCE_ADVANCE_JS = (
    "() => {"
    " const fname = '__FN__';"
    " const n = Math.max(1, Math.min(500, Number('__TIMES__')));"
    " const readCompact = () => {"
    "   const names = ['score', 'lines', 'level', 'best', 'paused', 'gameOver', 'currentPiece', 'board'];"
    "   const o = {};"
    "   for (const nm of names) {"
    "     try {"
    "       const v = eval(nm);"
    "       if (v === undefined) continue;"
    "       if (nm === 'board' || nm === 'grid' || Array.isArray(v)) { o[nm] = '[array]'; }"
    "       else if (v && typeof v === 'object') { o[nm] = { x: v.x, y: v.y, type: v.type }; }"
    "       else { o[nm] = typeof v === 'string' ? v.slice(0, 40) : v; }"
    "     } catch (e) {}"
    "   }"
    "   return o;"
    " };"
    " const before = readCompact();"
    " let done = 0; let lastError = null;"
    " try {"
    "   const f = eval(fname);"
    "   if (typeof f !== 'function') return JSON.stringify({ error: fname + \" n'est pas une fonction globale accessible\" });"
    "   for (let i = 0; i < n; i++) { f(); done++; }"
    " } catch (e) { lastError = String(e).slice(0, 200); }"
    " const after = readCompact();"
    " let stateChanged = false;"
    " try { stateChanged = JSON.stringify(before) !== JSON.stringify(after); } catch (e) {}"
    " return JSON.stringify({ fn: fname, calls_done: done, last_error: lastError, state_before: before, state_after: after, state_changed: stateChanged });"
    "}"
)


class DevToolsForceAdvanceTool(Tool):
    name = "force_advance"
    description = (
        "Horloge accélérée (F-145) : appelle N fois (défaut 40) une fonction d'update globale du jeu "
        "(défaut moveDown) pour tester la logique en 1 seconde au lieu d'attendre l'horloge réelle, et "
        "renvoie l'état avant/après (state_changed) + la 1re exception rencontrée. Si state_changed=false "
        "alors que la fonction tourne → la logique est cassée ; si l'état change mais pas le canvas → "
        "bug de rendu (croise probe_canvas_activity)."
    )
    inputs = {
        "fn": {"type": "string", "description": "nom de la fonction à appeler (défaut: moveDown)", "nullable": True},
        "times": {"type": "integer", "description": "nombre d'appels (défaut 40, max 500)", "nullable": True},
    }
    output_type = "string"

    def __init__(self, evaluate_script_tool: Tool):
        super().__init__()
        self._eval = evaluate_script_tool

    def forward(self, fn=None, times=None) -> str:
        fname = fn or "moveDown"
        if not _IDENT_RE.match(fname or ""):
            return "ERROR (force_advance) : nom de fonction invalide — identifiant JS nu uniquement."
        n = 40 if times is None else max(1, min(500, int(times)))
        js = _FORCE_ADVANCE_JS.replace("__FN__", fname.strip()).replace("__TIMES__", str(n))
        return self._eval(function=js)


# F-155 (goulot n°3, run 2026-08-22_1732) : le Tester a conclu « non trié » en
# attendant 60 s IN-PAGE un tri animé qui dure ~95 s. La sonde doit attendre
# le VRAI signal de complétion (ou prouver l'inertie), dans UN SEUL appel —
# pas de snapshot prématuré, pas d'attente fixe plus courte que l'animation.
# Verdicts : SORTED_ALREADY / SORTED_AFTER_WAIT / IN_PROGRESS_STILL_MOVING /
# STATIC_UNSORTED / NO_TARGETS — « tri en cours » est désormais distingué de
# « tri cassé » par la mesure de mouvement post-timeout.
# __MAX_WAIT_MS__ interpolé côté Python (voir note _PROBE_CANVAS_V2_JS).
_PROBE_SORT_STATE_JS = (
    "async () => {"
    " const mw = Math.max(1000, Math.min(300000, Number('__MAX_WAIT_MS__')));"
    " const POLL_MS = 500;"
    " const cap = (a) => a.slice(0, 400);"
    " const valueOf = (el) => {"
    "   const dv = el.getAttribute && el.getAttribute('data-value');"
    "   if (dv !== null && dv !== '' && !isNaN(Number(dv))) return Number(dv);"
    "   const h = parseFloat(el.style && el.style.height);"
    "   if (!isNaN(h) && h > 0) return h;"
    "   const t = parseFloat((el.textContent || '').trim());"
    "   if (!isNaN(t)) return t;"
    "   return null;"
    " };"
    " const collect = () => {"
    "   let els = cap(Array.from(document.querySelectorAll('[class*=\"bar\"],[id*=\"bar\"]')));"
    "   let withVal = els.filter(e => valueOf(e) !== null);"
    "   if (withVal.length < 4) {"
    "     let best = null;"
    "     for (const c of document.querySelectorAll('div,section,main')) {"
    "       const kids = c.children ? Array.from(c.children) : [];"
    "       if (kids.length >= 4 && (!best || kids.length > best.length)) best = kids;"
    "     }"
    "     if (best) withVal = cap(best).filter(e => valueOf(e) !== null);"
    "   }"
    "   return cap(withVal.map(valueOf));"
    " };"
    " const isSorted = (vs) => {"
    "   if (vs.length < 2) return null;"
    "   for (let i = 0; i < vs.length - 1; i++) { if (vs[i] > vs[i + 1]) return false; }"
    "   return true;"
    " };"
    " const counter = (() => {"
    "   const el = document.querySelector('[id*=\"counter\"],[id*=\"comparison\"],[class*=\"counter\"]');"
    "   return el ? (el.textContent || '').trim().slice(0, 40) : null;"
    " })();"
    " const v0 = collect();"
    " if (v0.length < 4) return JSON.stringify({ verdict: 'NO_TARGETS', n: v0.length,"
    "   hint: 'Moins de 4 elements a valeur numerique (data-value, height inline, texte)."
    " Tri sur canvas ? Utilise probe_canvas_activity(). Sinon inspecte avec discover_ui().' });"
    " const s0 = isSorted(v0);"
    " if (s0 === true) return JSON.stringify({ verdict: 'SORTED_ALREADY', n: v0.length,"
    "   values_head: v0.slice(0, 8), counter: counter, waited_ms: 0 });"
    " const t0 = performance.now();"
    " let v = v0;"
    " while (performance.now() - t0 < mw) {"
    "   await new Promise(r => setTimeout(r, POLL_MS));"
    "   v = collect();"
    "   if (isSorted(v) === true) return JSON.stringify({ verdict: 'SORTED_AFTER_WAIT',"
    "     n: v.length, values_head: v.slice(0, 8), counter: counter,"
    "     waited_ms: Math.round(performance.now() - t0),"
    "     note: 'Tri anime complet : ne conclus jamais non-trie avant ce verdict.' });"
    " }"
    " const sigA = v.join(',');"
    " await new Promise(r => setTimeout(r, 800));"
    " const vEnd = collect();"
    " const moving = vEnd.join(',') !== sigA;"
    " return JSON.stringify({"
    "   verdict: moving ? 'IN_PROGRESS_STILL_MOVING' : 'STATIC_UNSORTED',"
    "   n: vEnd.length, values_head: vEnd.slice(0, 8), counter: counter,"
    "   waited_ms: Math.round(performance.now() - t0), moving_after_timeout: moving,"
    "   hint: moving ? 'Le tri AVANCE encore (animation lente) : rallonge max_wait_ms, PAS un defaut.'"
    "     : 'Fige ET non trie : tri casse ou avorte. Diagnostique avec instrument_calls() puis dump_function_source().' });"
    "}"
)


class DevToolsProbeSortStateTool(Tool):
    name = "probe_sort_state"
    description = (
        "Sonde déterministe de tri animé (F-155) : lit les valeurs des barres (data-value, height inline, "
        "ou texte), et si ce n'est pas trié ATTEND IN-PAGE (poll 500 ms) jusqu'à tri complété ou "
        "max_wait_ms (défaut 180000, max 300000) — UN SEUL appel, zéro step supplémentaire. Verdicts : "
        "SORTED_ALREADY / SORTED_AFTER_WAIT (tri animé complet) / IN_PROGRESS_STILL_MOVING (animation "
        "lente, PAS un défaut — rallonge max_wait_ms) / STATIC_UNSORTED (figé et non trié = tri cassé) / "
        "NO_TARGETS. Règle : ne JAMAIS conclure « non trié » sur un snapshot pris avant la fin de "
        "l'animation — attends ce verdict."
    )
    inputs = {
        "max_wait_ms": {
            "type": "integer",
            "description": "attente max avant verdict IN_PROGRESS/STATIC (défaut 180000, bornes 1000-300000)",
            "nullable": True,
        },
    }
    output_type = "string"

    def __init__(self, evaluate_script_tool: Tool):
        super().__init__()
        self._eval = evaluate_script_tool

    def forward(self, max_wait_ms=None) -> str:
        mw = 180000 if max_wait_ms is None else max(1000, min(300000, int(max_wait_ms)))
        return self._eval(function=_PROBE_SORT_STATE_JS.replace("__MAX_WAIT_MS__", str(mw)))


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
        # F-145 : sondes de preuve de mouvement
        DevToolsExposeGameStateTool(eval_tool),
        DevToolsInstrumentCallsTool(eval_tool),
        DevToolsDumpFunctionSourceTool(eval_tool),
        DevToolsForceAdvanceTool(eval_tool),
        # F-155 : sonde déterministe de tri animé (tri en cours vs tri cassé)
        DevToolsProbeSortStateTool(eval_tool),
    ]
