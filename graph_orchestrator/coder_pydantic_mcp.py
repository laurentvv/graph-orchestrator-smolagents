"""MCP navigateur & doc pour le Coder pydantic — phase 3.5 (F-160).

Plan docs/PLAN_MIGRATION_PYDANTIC_HARNESS.md §3.5 : les serveurs MCP du Coder
smolagents (chrome-devtools F-50/90 + Context7 F-17) migrent sur les seams
officiels du harness — ``MCPToolset`` (fastmcp) remplace ``ToolCollection.from_mcp``
+ le patch mcpadapt ; la transformation per-tool (``process_tool_call``) remplace
le sous-classage smolagents ``Tool``.

Contenu :
  - chrome-devtools-mcp (stdio npx, même commande que agent_server.mcp — source
    unique de vérité) : navigate/console/screenshot/evaluate_script… ;
  - transformations per-tool via ``process_tool_call`` (doc pydantic.dev
    capabilities/mcp + mcp/client) :
      * F-50/F-90 : strippage ``filePath``/``file_path`` de take_screenshot /
        take_snapshot (chrome-devtools-mcp ``--isolated`` n'a pas de workspace
        root → Access denied → boucle de screenshots) ;
      * F-127 : sanitisation de l'enum ``types`` de list_console_messages
        (valeurs inventées → MCP -32602 → step perdu) ;
      * F-126 : enrichissement console — les stacks complètes de
        ``get_console_message(msgid)`` sont appendues au retour de
        list_console_messages + directive read_file ciblée (le 4B soupçonne les
        mauvaises fonctions sans localisation : 3 réécritures complètes, run
        2026-08-19_1552) ;
  - 12 helpers DOM (F-72/F-145/F-155) : FunctionToolset de fonctions asynchrones
    déléguant à ``evaluate_script`` via le client fastmcp — corps JS réutilisés
    À L'IDENTIQUE depuis devtools_dom_tools (0 changement comportemental) ;
  - Context7 (HTTP streamable + header CONTEXT7_API_KEY) : resolve_library_id /
    query_docs.

Dégradation gracieuse (miroir F-104 smolagents) : serveur désactivé/absent →
toolset None ; échec/timeout d'init (``init_timeout`` = réglages
``*_connect_timeout_s``) → warning + skip, le nœud tourne sans cet apport —
aucun nœud ne dépend d'un MCP pour fonctionner.

Vision multimodale (screenshots → contexte image) = phase 3.6 (F-161) :
``take_screenshot`` retourne désormais une liste mixte ``[note_texte,
BinaryImage]`` — le framework l'éclate en message tool texte + message user
image (data-URI décodée par le mmproj llama-server). Le strippage filePath
(F-50/F-90) est inchangé ; la purge des anciennes images vit dans
``coder_pydantic_vision`` (ProcessHistory, parité F-101/F-116).

Activation : ``CODER_ENGINE=pydantic`` (l'aiguillage F-158) ; rien de nouveau
à configurer — CHROME_DEVTOOLS_ENABLED / CONTEXT7_API_KEY / CHROME_PATH /
CHROME_DEVTOOLS_HEADLESS restent les réglages existants.
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Outils DevTools dont le paramètre filePath est strippé (F-50/F-90 — cf.
# vision_callback._FILEPATH_TOOLS : même liste).
_FILEPATH_STRIPPED_TOOLS = frozenset({"take_screenshot", "take_snapshot"})


# ============================================================
# Transformation per-tool (process_tool_call)
# ============================================================


def _prepare_tool_args(name: str, args: dict) -> dict:
    """Nettoie les arguments AVANT délégation au serveur MCP. Pur, testable.

    - F-50/F-90 : retire ``filePath``/``file_path`` des outils screenshot
      (rejetés par chrome-devtools-mcp ``--isolated`` → boucle de screenshots).
    - F-127 : sanitise l'enum ``types`` de list_console_messages (valeurs
      inventées par le modèle → MCP -32602).
    """
    from .vision_callback import _sanitize_console_kwargs

    args = dict(args or {})
    if name in _FILEPATH_STRIPPED_TOOLS:
        for fp in ("filePath", "file_path"):
            if args.pop(fp, None) is not None:
                logger.debug("coder_pydantic_mcp: %s strippé pour %s (fix isolated).", fp, name)
    if name == "list_console_messages":
        args = _sanitize_console_kwargs(args)
    return args


def _enrich_console(text: str, details: list) -> str:
    """Port pydantic de vision_callback._enrich_console_output (F-126).

    ``details`` : résultats (str) de get_console_message(msgid=N) pour les
    msgids [error], déjà bornés par l'appelant. Réutilise l'extraction de
    frames et le wording exact du chemin smolagents (parité comportementale).
    """
    from .vision_callback import (
        _CONSOLE_ERROR_RE,
        _CONSOLE_MAX_ERRORS,
        _extract_stack_frames,
        _update_console_pending,
    )

    if not text:
        return text
    msgids = [int(m) for m in _CONSOLE_ERROR_RE.findall(text)]
    # F-128 : chaque check console rafraîchit l'état « erreurs en attente de
    # re-vérification » (consommé par les reminders/nudges maison).
    try:
        _update_console_pending(bool(msgids))
    except Exception:  # noqa: BLE001 — fail-open
        pass
    if not msgids:
        return text

    from .vision_callback import _CONSOLE_FRAME_RE, _CONSOLE_MAX_FRAMES

    blocks: list = []
    first_frame: Optional[str] = None
    for msgid, detail in zip(msgids[:_CONSOLE_MAX_ERRORS], details):
        frames = _extract_stack_frames(str(detail or ""))
        if not frames:
            continue
        blocks.append(f"[msgid={msgid}]\n" + "\n".join(f"  {f}" for f in frames[:_CONSOLE_MAX_FRAMES]))
        if first_frame is None:
            first_frame = frames[0]
    if not blocks:
        return text

    guidance = ""
    if first_frame:
        m = _CONSOLE_FRAME_RE.search(first_frame)
        if m:
            fname, line = m.group(1), int(m.group(2))
            guidance = (
                f'\n→ Bug LOCAL dans "{fname}" autour de la ligne {line} : '
                f'read_file(path="{fname}", offset={max(0, line - 8)}, limit=20), '
                "puis search_replace CHIRURGICAL (vérifie la fonction fautive ET "
                "ses appelants)."
            )
    extra = len(msgids) - _CONSOLE_MAX_ERRORS
    extra_note = (
        f"\n(+{extra} erreur(s) non détaillée(s) — get_console_message(msgid=N) pour les voir)"
        if extra > 0
        else ""
    )
    return (
        f"{text}\n\n### 📍 STACK TRACES COMPLÈTES (get_console_message)\n"
        + "\n".join(blocks)
        + extra_note
        + guidance
        + "\n⚠️ Une erreur console = un bug LOCAL : NE réécris PAS tout le fichier "
        "(write_file sur un gros fichier existant est REFUSÉ)."
    )


def make_process_tool_call(vision: bool = True):
    """Construit le callback ``process_tool_call`` du toolset DevTools.

    Signature officielle (doc mcp/client « Tool call customization ») :
    ``async (ctx, call_tool, name, tool_args) -> ToolResult``. Pour les outils
    texte, retourne un str (partie texte du résultat MCP) ; le détail console
    (get_console_message) est récupéré par le MÊME canal (call_tool) —
    équivalent du wrapper _ConsoleEnrichingTool smolagents, sans sous-classage.

    Phase 3.6 (F-161) — ``vision=True`` (défaut) : un résultat contenant des
    images (``take_screenshot`` → ``BinaryImage`` mappé par le toolset)
    retourne ``[note_texte, *images]`` (ToolResult multimodal valide — le
    modèle VOIT l'image). ``vision=False`` reproduit un monde sans vision.
    """
    from .coder_pydantic_vision import make_image_tool_return, split_tool_result

    async def process_tool_call(ctx, call_tool, name: str, tool_args: dict) -> Any:  # noqa: ANN001
        args = _prepare_tool_args(name, tool_args)
        result = await call_tool(name, args)
        text, images = split_tool_result(result)
        if images:
            return make_image_tool_return(text, images, vision=vision)
        if name != "list_console_messages":
            return text
        # F-126 : va chercher les stacks des erreurs (borné : max 4).
        from .vision_callback import _CONSOLE_ERROR_RE, _CONSOLE_MAX_ERRORS

        msgids = [int(m) for m in _CONSOLE_ERROR_RE.findall(text)][:_CONSOLE_MAX_ERRORS]
        details: list = []
        for msgid in msgids:
            try:
                detail = await call_tool("get_console_message", {"msgid": msgid})
                details.append(render_mcp_result(detail))
            except Exception as exc:  # noqa: BLE001 — fail-open total
                logger.debug("coder_pydantic_mcp: get_console_message(%s) KO (%s)", msgid, exc)
                details.append("")
        try:
            return _enrich_console(text, details)
        except Exception as exc:  # noqa: BLE001 — fail-open total
            logger.warning("coder_pydantic_mcp: enrich console KO (%s) — retour brut.", exc)
            return text

    return process_tool_call


def render_mcp_result(result: Any) -> str:
    """Aplatit un résultat d'appel MCP en texte modèle-friendly. Défensif.

    fastmcp retourne un ``CallToolResult`` (.content liste de blocs, .data
    structuré) ; le chemin str des tests fournit du texte brut. F-161 : les
    items binaires (``BinaryImage`` des screenshots) sont IGNORÉS proprement
    (l'ancien fallback produisait ``str(bytes)`` — du bruit hexadécimal dans
    le contexte) ; le parcours image complet vit dans ``process_tool_call``.
    """
    from .coder_pydantic_vision import split_tool_result

    return split_tool_result(result)[0]


# ============================================================
# Toolsets MCP (chrome-devtools stdio / Context7 HTTP)
# ============================================================


def build_devtools_mcp_toolset(settings) -> Optional[Any]:
    """MCPToolset chrome-devtools (stdio npx), ou None si désactivé/indisponible.

    La commande npx/options vient de ``agent_server.mcp.build_chrome_devtools_params``
    (source unique de vérité, déjà testée) : ``--isolated --viewport 1280x800
    --screenshot-format jpeg`` (+ CHROME_PATH / CHROME_DEVTOOLS_HEADLESS).
    """
    from agent_server.mcp import build_chrome_devtools_params

    params = build_chrome_devtools_params()
    if params is None:
        return None
    from fastmcp.client.transports import StdioTransport
    from pydantic_ai.mcp import MCPToolset

    # Transport direct (MCPToolset construit son propre client fastmcp : cache
    # d'outils + invalidation par notifications gérés nativement).
    transport = StdioTransport(command=params.command, args=list(params.args or []), env=dict(params.env or {}))
    return MCPToolset(
        transport,
        id="chrome-devtools",
        init_timeout=settings.chrome_devtools_connect_timeout_s,
        # F-161 : vision multimodale (screenshots → contexte image) quand
        # CODER_PYDANTIC_VISION=true (défaut).
        process_tool_call=make_process_tool_call(
            vision=getattr(settings, "coder_pydantic_vision", True)
        ),
        # 'retry' (défaut) : une erreur serveur devient ModelRetry → le modèle
        # corrige son appel (sémantique du tool-retry maison smolagents).
        tool_error_behavior="retry",
    )


def build_context7_mcp_toolset(settings) -> Optional[Any]:
    """MCPToolset Context7 (HTTP streamable + header API), ou None sans clé.

    URL/header délégués à ``agent_server.mcp.build_context7_params`` (source
    unique de vérité). Les 2 outils (resolve_library_id, query_docs) sont
    RENOMMÉS en underscores (RenamedToolset) : le serveur expose des tirets
    (``resolve-library-id``) que mcpadapt convertissait côté smolagents — les
    prompts/skills citent les noms underscores, on préserve la parité.
    """
    from agent_server.mcp import build_context7_params

    params = build_context7_params()
    if params is None:
        return None
    from pydantic_ai.mcp import MCPToolset
    from pydantic_ai.toolsets.renamed import RenamedToolset

    toolset = MCPToolset(
        params["url"],
        headers=dict(params.get("headers") or {}),
        id="context7",
        init_timeout=settings.context7_connect_timeout_s,
        tool_error_behavior="retry",
    )
    return RenamedToolset(toolset, {"resolve_library_id": "resolve-library-id", "query_docs": "query-docs"})


# ============================================================
# 12 helpers DOM (F-72/F-145/F-155) — FunctionToolset
# ============================================================
# Miroir pydantic de devtools_dom_tools : les corps JS sont importés À
# L'IDENTIQUE (constantes privées du module) ; seule l'enveloppe change —
# fonction asynchrone du toolset déléguant à evaluate_script via le client
# fastmcp, au lieu de sous-classe smolagents.Tool wrappant l'outil MCP.


def build_dom_helper_toolset(devtools_client) -> Optional[Any]:
    """FunctionToolset des helpers DOM, ou None sans client DevTools (fail-open).

    Chaque helper expose l'INTENTION en description (le JS vit dans l'outil,
    pas dans le prompt — F-72) et interpole ses paramètres côté Python
    (placeholders __TOKEN__ : le MCP chrome-devtools rejette tout argument
    hors function/args/filePath — prouvé F-155).
    """
    if devtools_client is None:
        return None
    from pydantic_ai.toolsets import FunctionToolset

    from .devtools_dom_tools import (
        _ADD_VISUAL_TAGS_JS,
        _CLEAN_DOM_JS,
        _DISCOVER_UI_JS,
        _DUMP_SOURCE_JS,
        _EXPOSE_STATE_JS,
        _FORCE_ADVANCE_JS,
        _FUZZ_CLICK_JS,
        _FUZZ_KEYBOARD_JS,
        _HEAL_SELECTOR_JS,
        _IDENT_RE,
        _INSTRUMENT_CALLS_JS,
        _PROBE_CANVAS_V2_JS,
        _PROBE_SORT_STATE_JS,
        _split_identifiers,
    )

    async def _eval(function: str, args: Optional[list] = None) -> str:
        call_args = {"function": function}
        if args is not None:
            call_args["args"] = args
        result = await devtools_client.call_tool("evaluate_script", call_args)
        return render_mcp_result(result)

    async def clean_dom() -> str:
        """Cleans the DOM of the active Chrome page (removes script, style, svg, canvas, iframe, noscript, template) and returns the lightweight HTML (max 8000 chars). Call with NO ARGUMENT to inspect the page structure without polluting your context."""
        return await _eval(_CLEAN_DOM_JS)

    async def add_visual_tags() -> str:
        """Adds numbered red badges (e1, e2...) on every VISIBLE clickable element of the active page. Call with NO ARGUMENT BEFORE take_screenshot to ease element spotting/clicking."""
        return await _eval(_ADD_VISUAL_TAGS_JS)

    async def fuzz_click_all_buttons() -> str:
        """Monkey testing: clicks ALL <button> elements of the active page to wake up hidden JS bugs (missing handlers, click exceptions). Call with NO ARGUMENT, then chain list_console_messages to catch errors."""
        return await _eval(_FUZZ_CLICK_JS)

    async def probe_canvas_activity(window_ms: Optional[int] = None) -> str:
        """Canvas activity probe: RGB hash of each 2D <canvas> over 4 samples in a parametrizable window (default 2400 ms, min 800 — a 800ms/row fall is INVISIBLE under 800ms). Also measures raf_per_s (live loop?) and visibility (hidden tab = rAF frozen). Verdicts: ANIMATING / STATIC_PAINTED / INERT_EMPTY / NON_2D + flag suspect_animation_broken when the loop runs but the render NEVER changes.

        Args:
            window_ms: total observation duration in ms (default 2400, bounds 800-10000).
        """
        wm = 2400 if window_ms is None else max(800, min(10000, int(window_ms)))
        return await _eval(_PROBE_CANVAS_V2_JS.replace("__WINDOW_MS__", str(wm)))

    async def fuzz_keyboard_controls() -> str:
        """Keyboard exception interception: simulates game keys (Arrows, Space, Z, X) while catching any unhandled JS crash. Call with NO ARGUMENT."""
        return await _eval(_FUZZ_KEYBOARD_JS)

    async def discover_ui() -> str:
        """Complete UI inventory in ONE call: canvas IDs and dimensions, buttons (id+text), inputs (id+type), key elements and visible text sample. Call FIRST right after navigate_page to learn the REAL IDs before any evaluate_script — NEVER guess a DOM id."""
        return await _eval(_DISCOVER_UI_JS)

    async def heal_selector(tag: str, text_hint: str = "", attr_hint: str = "") -> str:
        """Self-healing selector: when your selector (e.g. '#startBtn') no longer finds the element (renamed/regenerated by a fix), re-locate it by similarity. Returns the best candidate (score >= 0.4) with its selector — avoids a test FAIL on a simple rename.

        Args:
            tag: HTML tag of the searched element, e.g. 'button'.
            text_hint: expected visible text of the element, e.g. 'Start'.
            attr_hint: expected attributes 'class=btn primary|data-action=start' (optional).
        """
        return await _eval(_HEAL_SELECTOR_JS, args=[str(tag), str(text_hint or ""), str(attr_hint or "")])

    async def expose_game_state(names: Optional[str] = None) -> str:
        """Reads the INTERNAL game/page state: top-level <script> variables (score, lines, level, paused, gameOver, currentPiece, board...) by bare identifier. Two snapshots 1.5s apart → changed_over_1500ms proves the state LIVES. A game whose state changes while the canvas is frozen (see probe_canvas_activity) = render bug.

        Args:
            names: CSV list of JS identifiers (default provided: score,lines,level,best,paused,gameOver,...).
        """
        if names:
            _, bad = _split_identifiers(names)
            if bad:
                return f"ERROR (expose_game_state) : noms invalides {bad} — identifiants JS nus uniquement, séparés par des virgules."
        return await _eval(_EXPOSE_STATE_JS.replace("__NAMES__", (names or "").strip()))

    async def instrument_calls(names: Optional[str] = None, window_s: Optional[int] = None) -> str:
        """Liveness counter: wraps global game functions (draw, gameLoop, moveDown...) and counts their REAL calls during window_s seconds (default 3). Proves the loop runs and gravity pulls — discriminates 'dead engine' vs 'live engine but frozen render'.

        Args:
            names: CSV list of functions to wrap (default: draw,update,gameLoop,loop,tick,render,...).
            window_s: observation duration in seconds (default 3, bounds 1-30).
        """
        if names:
            _, bad = _split_identifiers(names, limit=20)
            if bad:
                return f"ERROR (instrument_calls) : noms invalides {bad} — identifiants JS nus uniquement."
        ws = 3 if window_s is None else max(1, min(30, int(window_s)))
        js = _INSTRUMENT_CALLS_JS.replace("__NAMES__", (names or "").strip()).replace("__WINDOW_S__", str(ws))
        return await _eval(js)

    async def dump_function_source(names: Optional[str] = None) -> str:
        """In-page source read: returns the source code (Function.prototype.toString) of global game functions — draw, gameLoop, moveDown... This is how the ghostY bug was found (piece drawn with the wrong variable, invisible on a screenshot).

        Args:
            names: CSV list of functions to dump (default list provided, max 10).
        """
        if names:
            _, bad = _split_identifiers(names, limit=10)
            if bad:
                return f"ERROR (dump_function_source) : noms invalides {bad} — identifiants JS nus uniquement."
        return await _eval(_DUMP_SOURCE_JS.replace("__NAMES__", (names or "").strip()))

    async def force_advance(fn: Optional[str] = None, times: Optional[int] = None) -> str:
        """Accelerated clock: calls a global game update function N times (default 40) to test the logic in 1 second instead of waiting the real clock; returns before/after state (state_changed) + first exception. state_changed=false while the function runs = broken logic; state changes but canvas doesn't = render bug (cross-check probe_canvas_activity).

        Args:
            fn: name of the function to call (default: moveDown).
            times: number of calls (default 40, max 500).
        """
        fname = fn or "moveDown"
        if not _IDENT_RE.match(fname or ""):
            return "ERROR (force_advance) : nom de fonction invalide — identifiant JS nu uniquement."
        n = 40 if times is None else max(1, min(500, int(times)))
        js = _FORCE_ADVANCE_JS.replace("__FN__", fname.strip()).replace("__TIMES__", str(n))
        return await _eval(js)

    async def probe_sort_state(max_wait_ms: Optional[int] = None) -> str:
        """Sort-state probe: waits in-page for the REAL completion signal of an animated sort (polls every 500 ms), then measures post-timeout movement. Verdicts: SORTED_ALREADY / SORTED_AFTER_WAIT / IN_PROGRESS_STILL_MOVING / STATIC_UNSORTED / NO_TARGETS — 'still sorting' is distinguished from 'broken sort'. NEVER conclude 'not sorted' before this verdict.

        Args:
            max_wait_ms: max total wait in ms (default 180000, bounds 1000-300000).
        """
        mw = 180000 if max_wait_ms is None else max(1000, min(300000, int(max_wait_ms)))
        return await _eval(_PROBE_SORT_STATE_JS.replace("__MAX_WAIT_MS__", str(mw)))

    return FunctionToolset(
        [
            clean_dom,
            add_visual_tags,
            fuzz_click_all_buttons,
            probe_canvas_activity,
            fuzz_keyboard_controls,
            discover_ui,
            heal_selector,
            expose_game_state,
            instrument_calls,
            dump_function_source,
            force_advance,
            probe_sort_state,
        ],
        id="devtools-helpers",
    )


# ============================================================
# Ouverture groupée (lifecycle + dégradation gracieuse)
# ============================================================


@dataclass
class CoderMCP:
    """État MCP du nœud : toolsets ouverts + flags pour le prompt/instructions."""

    toolsets: list = field(default_factory=list)
    browser_tools_available: bool = False
    context7_available: bool = False
    devtools_client: Any = None  # fastmcp Client (helpers evaluate_script)


@asynccontextmanager
async def open_coder_mcp(settings):
    """Ouvre les toolsets MCP du Coder, avec dégradation individuelle.

    Miroir des context managers smolagents (chrome_devtools_tools /
    context7_tools) : chaque serveur indisponible (désactivé, timeout
    init_timeout, npx absent…) est SKIPPÉ avec un warning — le nœud tourne
    avec ce qui a pu s'ouvrir, jamais bloqué par un MCP (F-104).
    """
    state = CoderMCP()
    async with AsyncExitStack() as stack:
        devtools = build_devtools_mcp_toolset(settings)
        if devtools is not None:
            try:
                await stack.enter_async_context(devtools)
                state.toolsets.append(devtools)
                state.browser_tools_available = True
                state.devtools_client = devtools.client
                print("[MCP] chrome-devtools (pydantic) : connecté.")
            except Exception as exc:  # noqa: BLE001 — dégradation, pas d'échec nœud
                logger.warning("chrome-devtools indisponible (%s) — poursuite sans preview.", exc)
                print(f"[MCP] chrome-devtools (pydantic) : indisponible ({exc}) — sans preview.")

        helpers = build_dom_helper_toolset(state.devtools_client)
        if helpers is not None:
            state.toolsets.append(helpers)

        context7 = build_context7_mcp_toolset(settings)
        if context7 is not None:
            try:
                await stack.enter_async_context(context7)
                state.toolsets.append(context7)
                state.context7_available = True
                print("[MCP] context7 (pydantic) : connecté.")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Context7 indisponible (%s) — poursuite sans doc.", exc)
                print(f"[MCP] context7 (pydantic) : indisponible ({exc}) — sans doc.")

        yield state
