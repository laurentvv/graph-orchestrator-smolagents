"""step_callback smolagents : faire remonter les screenshots dans observations_images. F-45.

PROBLÈME : smolagents (v1.26.0) ne pousse PAS automatiquement les images retournées
par les outils MCP dans le contexte multimodal du LLM. Les screenshots de
`take_screenshot` (Chrome DevTools) sont décodés en PIL.Image par l'adaptateur MCP
mais :
  - ToolCallingAgent : test de type exact `type(result) in [AgentImage]` (agents.py:1392),
    les outils MCP viennent en output_type="object" → fallback isinstance → AgentImage
    normalement, MAIS l'observation texte reste "Stored 'image.png' in memory." et
    observations_images n'est JAMAIS peuplé (c'est le gap).
  - CodeAgent : l'outil est appelé via python_interpreter, le retour passe par
    `str(code_output.output)` (agents.py:1752) → l'image est perdue dans la conversion.

SOLUTION : un step_callback (pattern officiel smolagents/vision_web_browser.py:66-84)
qui capture l'image via un wrapper installé autour des outils MCP, puis la pousse
dans memory_step.observations_images à la fin de chaque step. C'est le SEUL mécanisme
intégré qui produit une vraie content-part image vue par le modèle (memory.py:112-124).

Le wrapper capture l'image au passage (au moment où l'outil forward() retourne),
sans casser le comportement original (l'image est quand même retournée à l'agent).
"""

import logging
import re
from typing import Any, List, Optional

from smolagents import Tool

from .config import settings

logger = logging.getLogger(__name__)

# Clé sous laquelle l'image capturée est stockée sur l'objet partagé passé au
# callback. On utilise une liste mutable (append) plutôt qu'une valeur simple pour
# pouvoir cumuler si plusieurs screenshots dans un même step, et reset entre steps.
_CAPTURE_ATTR = "_last_screenshot"

# F-114 (post-mortem run #9) : nudge contextuel vers la checklist visual_check.
# Le 4B prenait 48 screenshots en concluant en prose SANS JAMAIS appeler
# visual_check (0 appel en 3 tentatives) → la gate F-109 refusait final_answer
# → boucle déterministe 3 × max_steps, 43,9 M tokens pour 0 livrable. Le nudge
# rappelle l'exigence AU MOMENT du comportement fautif (dans les observations du
# step), pas seulement au boundary de retry (F-109-bis). Pattern repeat-tool-reminder
# (fiche 46-deepseek-harness) : rappel gradué injecté via le contexte, sans veto.
_NUDGE_THRESHOLD = 3
_SCREENSHOT_NUDGE_STATE = {"count": 0}

# F-125 (post-mortem run 2026-08-19 12:02, Tetris) : détection onglet gelé.
# L'onglet audité ne répondait plus au renderer — timeout CDP ~190 s sur
# Page.captureScreenshot / Runtime.evaluate / Input.dispatchKeyEvent — tandis que
# list_pages / list_console_messages répondaient (commandes browser-process).
# Le Coder a brûlé ~15 steps / ~45 min à retenter les MÊMES outils au lieu de
# récupérer, jusqu'à l'échec définitif (« Coder crash », run perdu). Même pattern
# que F-114 : compteur d'observations d'erreur protocole CONSECUTIVES, directive
# de récupération injectée à partir du seuil. Fail-open total (jamais d'exception).
_BROWSER_STALL_THRESHOLD = 3
_BROWSER_STALL_STATE = {"count": 0}
# Signatures d'erreur observées dans le run : "Runtime.evaluate timed out.",
# "Page.captureScreenshot timed out.", "Input.dispatchKeyEvent timed out.",
# "Protocol error (Page.captureScreenshot): Not attached to an active page".
# F-129 : « Navigation timeout » (gel AU CHARGEMENT, run 2026-08-20_0901) —
# avant, ce message ne matchait AUCUN marqueur → le compteur ne voyait pas
# les timeouts de navigate_page.
_BROWSER_STALL_MARKERS = ("timed out", "Not attached to an active page", "Navigation timeout")


def reset_browser_stall() -> None:
    """Réinitialise le compteur anti-gel (même lifecycle que reset_screenshot_nudge)."""
    _BROWSER_STALL_STATE["count"] = 0


def _build_browser_stall_nudge(observations: str) -> Optional[str]:
    """Directive de récupération si l'onglet semble gelé (erreurs protocole consécutives).

    Retourne None tant que le seuil n'est pas atteint ou que le step courant n'est
    pas en erreur protocole (le compteur repart de zéro au premier step sain).
    Best-effort total : jamais d'exception (fail-open).
    """
    try:
        text = observations or ""
        if not any(m in text for m in _BROWSER_STALL_MARKERS):
            _BROWSER_STALL_STATE["count"] = 0
            return None
        _BROWSER_STALL_STATE["count"] += 1
        if _BROWSER_STALL_STATE["count"] < _BROWSER_STALL_THRESHOLD:
            return None
        n = _BROWSER_STALL_STATE["count"]
        return (
            f"[NAVIGATEUR GELÉ] {n} erreurs de protocole consécutives (timeout / page "
            f"détachée) : l'onglet ne répond plus au renderer. NE RETENTE PAS tel quel "
            f"take_screenshot / evaluate_script / press_key — chaque essai coûte ~3 min. "
            f"Récupération dans l'ordre : (1) list_pages() puis "
            f'navigate_page(type="reload") ; si plusieurs onglets pointent sur le même '
            f"fichier, ferme les doublons via close_page ; (2) si la page re-gèle "
            f"aussitôt, c'est TON code qui bloque le renderer (boucle while infinie "
            f"sans rendu) : corrige le fichier AVANT de re-tester ; (3) après 2 "
            f'récupérations échouées, final_answer avec status="failure" et '
            f'details="renderer gelé" — un échec propre vaut mieux que brûler le budget.'
        )
    except Exception as e:  # pragma: no cover - fail-open garanti
        logger.debug("nudge anti-gel échec (%s) — ignoré.", e)
        return None


def reset_screenshot_nudge() -> None:
    """Réinitialise le compteur de screenshots du nudge (une exécution de nœud Coder = un cycle).

    À appeler au même endroit que ``tools.reset_visual_audit()`` (même lifecycle).
    Le compteur traverse volontairement les retries de run_with_retry : 30
    screenshots pris à la tentative 1 doivent déclencher le nudge immédiatement
    à la tentative 2, pas après 3 nouveaux screenshots.
    """
    _SCREENSHOT_NUDGE_STATE["count"] = 0


# F-129 (post-mortem run 2026-08-20_0901, Tetris) : gel AU CHARGEMENT.
# navigate_page vers index.html répondait « Navigation timeout of 10000 ms
# exceeded » dès la PREMIÈRE navigation : le JS bloquait le thread principal
# avant l'événement load (do...while de rejet contre un sac contenant TOUS les
# types de pièces — condition jamais fausse, jamais terminant). Le nudge F-125
# ne détectait pas ce cas : (a) son marqueur "timed out" ne matche pas
# « Navigation timeout » ; (b) les commandes saines du browser-process
# (list_console_messages vide — un gel est SILENCIEUX) remettaient son compteur
# à zéro → jamais 3 erreurs protocole « consécutives ». Un timeout de
# navigation sur un fichier LOCAL est TOUJOURS pathologique (chargement <1s)
# → directive immédiate, sans seuil, dès la 1re occurrence. Fail-open total.
_NAV_TIMEOUT_MARKER = "Navigation timeout"
_NAV_FREEZE_STATE = {"count": 0}


def reset_nav_freeze_nudge() -> None:
    """Réinitialise le compteur de gels au chargement (même lifecycle que les autres)."""
    _NAV_FREEZE_STATE["count"] = 0


def _build_nav_freeze_nudge(observations: str) -> Optional[str]:
    """Directive immédiate si la navigation vers la page LOCALE timeout (gel du thread JS).

    Un fichier statique local se charge en <1s : un Navigation timeout signifie
    que le script bloque le renderer AVANT l'événement load (boucle synchrone
    infinie). La console reste vide (gel silencieux) et screenshot/evaluate
    timeout aussi — aucun retry navigateur n'aide. Best-effort total.
    """
    try:
        text = observations or ""
        if _NAV_TIMEOUT_MARKER not in text:
            return None
        _NAV_FREEZE_STATE["count"] += 1
        n = _NAV_FREEZE_STATE["count"]
        return (
            f"[GEL AU CHARGEMENT #{n}] Navigation timeout sur ta page LOCALE = ton JS "
            f"bloque le thread principal (boucle while/do-while infinie) — ce n'est NI "
            f"un problème de navigateur NI un délai : un fichier local se charge en <1s. "
            f"La console restera vide (gel silencieux) et take_screenshot/evaluate_script "
            f"timeout aussi : NE RETENTE PAS la navigation telle quelle. Diagnostic : "
            f"(1) read_file du JS ; (2) cherche les boucles while(...)/do...while dont "
            f"la condition ne peut JAMAIS devenir fausse (ex : rejet contre une liste "
            f"contenant TOUS les cas possibles, while(true) sans break atteignable) ; "
            f"(3) corrige par search_replace ; (4) navigate_page à nouveau pour "
            f"CONFIRMER le dégel (console + screenshot)."
        )
    except Exception as e:  # pragma: no cover - fail-open garanti
        logger.debug("nudge gel chargement échec (%s) — ignoré.", e)
        return None


def _build_checklist_nudge(criteria_count: int) -> Optional[str]:
    """Construit le rappel checklist si le pattern « screenshots sans audit » est détecté.

    Retourne None tant que le seuil n'est pas atteint ou que tous les critères
    sont audités. Best-effort total : jamais d'exception (fail-open).
    """
    try:
        from .tools import get_visual_audit  # import local (outils = état module-level)

        _SCREENSHOT_NUDGE_STATE["count"] += 1
        audited = {a.get("criterion_number") for a in get_visual_audit()}
        missing = sorted(set(range(1, criteria_count + 1)) - audited)
        if not missing or _SCREENSHOT_NUDGE_STATE["count"] < _NUDGE_THRESHOLD:
            return None
        n = _SCREENSHOT_NUDGE_STATE["count"]
        return (
            f"[CHECKLIST VISUELLE] Screenshot #{n} pris, mais {len(missing)}/{criteria_count} "
            f"critère(s) restent NON audités : {missing}. NE prends PAS un autre screenshot : "
            f"appelle MAINTENANT visual_check(criterion_number=i, verdict=True|False, "
            f'observation="ce que tu vois sur la capture ci-dessus") pour CHAQUE critère '
            f"manquant, puis final_answer. Sans checklist complète, final_answer sera REFUSÉ."
        )
    except Exception as e:  # pragma: no cover - fail-open garanti
        logger.debug("nudge checklist échec (%s) — ignoré.", e)
        return None


def _mark_screenshot_proof(name: str, result: Any) -> None:
    """Marque la preuve de screenshot pour la gate F-109 durable — fail-open total.

    Seuls les vrais outils de capture comptent (take_snapshot = arbre a11y texte,
    evaluate_script = JS arbitraire : ni l'un ni l'autre ne prouvent un audit
    visuel). Succès = image PIL retournée, ou texte sans signature d'échec
    (access denied, timeout, page détachée).
    """
    if name not in ("take_screenshot", "puppeteer_screenshot"):
        return
    try:
        from .tools import mark_screenshot_taken

        import PIL.Image as _PILImage
        if isinstance(result, _PILImage.Image):
            mark_screenshot_taken()
            return
        text = str(result or "")
        if text and not any(
            m in text.lower()
            for m in ("error", "timed out", "access denied", "not attached")
        ):
            mark_screenshot_taken()
    except Exception as e:  # pragma: no cover - fail-open garanti
        logger.debug("mark_screenshot_proof échec (%s) — ignoré.", e)


class _ScreenshotCapturingTool(Tool):
    """Wrapper non-intrusif autour d'un outil MCP : capture les retours PIL.Image.

    smolagents ne proposant pas de hook "après forward()", on sous-classe Tool et
    on délègue au tool original. Le __call__ est hérité de Tool (gère déjà
    sanitize_inputs_outputs + handle_agent_output_types), on intercepte juste forward().

    On ne wrap QUE les outils qui peuvent retourner une image (take_screenshot,
    screencast_*). Les autres (navigate_page, click...) sont laissés intacts.

    ⚠️ PIÈGE chrome-devtools-mcp : take_screenshot retourne un CallToolResult avec
    PLUSIEURS content items (1 TextContent "Took a screenshot..." + 1 ImageContent).
    L'adaptateur mcpadapt ne prend que content[0] (le texte) → l'image est PERDUE.
    On contourne en patchant le tool wrappé pour qu'il retourne l'ImageContent si
    présent (voir _patch_forward_for_image). Sans ça, le modèle ne verrait jamais
    le screenshot (juste le texte "Took a screenshot...").
    """

    # Noms d'outils MCP Chrome DevTools / Puppeteer pouvant produire une image.
    SCREENSHOT_TOOL_NAMES = {
        "take_screenshot",        # Chrome DevTools MCP
        "take_snapshot",          # Chrome DevTools MCP (F-50/F-90 fix filePath)
        "take_heapsnapshot",      # Chrome DevTools MCP
        "evaluate_script",        # Chrome DevTools MCP (F-50/F-90 fix filePath="")
        "puppeteer_screenshot",   # Puppeteer MCP (Tester)
        "performance_stop_trace", # peut retourner une image dans certains cas
    }

    def __init__(self, wrapped: Tool, capture_holder: Any):
        # Copie l'identité du tool wrappé (l'agent voit le même nom/description/inputs).
        self.name = wrapped.name
        self.description = wrapped.description
        self.inputs = wrapped.inputs
        self.output_type = wrapped.output_type
        self.wrapped = wrapped
        self.capture_holder = capture_holder
        self.is_initialized = True
        # CRITIQUE : bypass la validation de signature de forward. Les outils MCP ont
        # des inputs variés (take_screenshot: filePath?, format?...) et notre wrapper
        # délègue via *args/**kwargs. On skip comme le fait l'adaptateur MCP natif
        # (smolagents_adapter.py:151) — sinon smolagents rejette le wrapper car la
        # signature générique ne matche pas exactement les inputs déclarés.
        self.skip_forward_signature_validation = True
        # Hérite des attributs optionnels du tool MCP wrappé (ex: output_schema).
        for attr in ("output_schema", "structured_output"):
            if hasattr(wrapped, attr):
                setattr(self, attr, getattr(wrapped, attr))
        # Patch le forward du tool wrappé pour qu'il retourne l'ImageContent si
        # l'outil renvoie du multi-content (texte + image). Cf. docstring classe.
        _patch_forward_for_image(wrapped)

    def forward(self, *args, **kwargs):
        # F-50/F-90 fix : strip filePath des outils DevTools. chrome-devtools-mcp --isolated
        # rejette toute écriture disque (pas de workspace root configuré) → l'outil
        # échoue avec Access denied.
        for _fp in ("filePath", "file_path"):
            if _fp in kwargs:
                kwargs.pop(_fp, None)
                logger.debug(
                    "vision_callback: %s strippé pour %s (fix isolated DevTools MCP).",
                    _fp,
                    self.name,
                )
        # F-114 (post-mortem run #9) : cap fullPage. Le Coder appelle
        # take_screenshot(fullPage=True) → images de plusieurs milliers de pixels
        # de haut (jusqu'à 1265×9315 observés) → prompt processing vision de
        # plusieurs minutes → Request timed out (600 s) qui a tué la tentative 2
        # du run #9. La capture viewport suffit à l'audit visuel. On ne mute QUE
        # les clés déjà présentes (jamais d'injection d'argument inconnu vers le
        # serveur MCP). Opt-out VISION_FULLPAGE_CAP=false.
        if settings.vision_fullpage_cap:
            for _key in ("fullPage", "full_page"):
                if kwargs.get(_key):
                    kwargs[_key] = False
                    logger.debug(
                        "vision_callback: %s forcé à False (cap F-114 — "
                        "images fullPage géantes = timeouts LLM).",
                        _key,
                    )
        result = self.wrapped.forward(*args, **kwargs)
        # F-126 : preuve durable pour la gate F-109 (tools._SCREENSHOT_PROOF).
        # Marquée à l'EXÉCUTION réelle de l'outil — insensible à la compaction
        # F-101 / purge de mémoire qui rendait le scan mémoire faux-négatif
        # (run 2026-08-19_1552 : screenshot étape 7, gate « PAS utilisé » à la 41).
        _mark_screenshot_proof(self.name, result)
        # Capture si c'est une image (PIL.Image.Image). On importe PIL ici (pas au
        # niveau module) car PIL est une dépendance optionnelle via smolagents.
        try:
            import PIL.Image as _PILImage
            if isinstance(result, _PILImage.Image):
                # On stocke une copie : l'instance d'origine peut être fermée par
                # le context manager MCP à la fin du run (le buffer sous-jacent
                # disparaîtrait). copy() garantit la persistance.
                self.capture_holder.append(result.copy())
        except Exception as e:
            logger.debug("capture screenshot échec (%s) — ignoré.", e)
        return result


def _patch_forward_for_image(tool: Tool) -> None:
    """Patch un outil MCP pour qu'il retourne l'ImageContent si multi-content. F-45.

    Problème : l'adaptateur mcpadapt (smolagents_adapter.py:189) ne prend que
    `mcp_output.content[0]`. Or chrome-devtools-mcp `take_screenshot` renvoie :
      content[0] = TextContent("Took a screenshot of the current page's viewport.")
      content[1] = ImageContent(data=<base64 png/jpeg>, mimeType="image/jpeg")
    → l'agent reçoit le texte, l'image est perdue.

    Solution : on wrap le `func` sous-jacent (closure de l'adaptateur) via une
    re-définition de forward qui parcourt TOUS les content items et retourne le
    premier ImageContent (décodé en PIL.Image) s'il existe, sinon le texte.

    Comme `func` n'est pas exposé comme attribut, on le récupère en inspectant la
    closure du forward existant (cell.cell_contents). C'est fragile mais c'est le
    seul moyen sans fork de mcpadapt. Si l'inspection échoue (structure inattendue),
    on no-op silencieusement (le wrapper de capture classique prend le relais).
    """
    import types

    original_forward = tool.forward
    try:
        # Le forward de MCPAdaptTool référence `func` via closure. On le récupère.
        # __closure__ est un tuple de cells ; on cherche celle qui est callable et
        # accepte un dict (signature de func: (dict) -> CallToolResult).
        func = None
        closure = getattr(original_forward, "__closure__", None) or ()
        for cell in closure:
            try:
                val = cell.cell_contents
            except ValueError:
                continue
            if callable(val) and val is not tool:
                # Heuristique : func est la closure qui produit le CallToolResult.
                # On vérifie qu'elle retourne qqchose avec .content (CallToolResult).
                func = val
                break
        if func is None:
            logger.debug("patch_forward: func non trouvé dans la closure — skip.")
            return

        def new_forward(self, *args, **kwargs):
            # Reproduit la logique d'appel de func de l'adaptateur (dict ou kwargs).
            if len(args) == 1 and isinstance(args[0], dict) and not kwargs:
                mcp_output = func(args[0])
            elif not args:
                mcp_output = func(kwargs)
            else:
                # Fallback : delegate au forward original (cas non gérés).
                return original_forward(*args, **kwargs)

            if not getattr(mcp_output, "content", None):
                return original_forward(*args, **kwargs)

            # Parcourt les content items : cherche un ImageContent (prioritaire).
            import base64
            import mcp as _mcp
            from io import BytesIO
            import PIL.Image as _PILImage

            text_fallback = None
            for item in mcp_output.content:
                if isinstance(item, _mcp.types.ImageContent):
                    image_data = base64.b64decode(item.data)
                    return _PILImage.open(BytesIO(image_data))
                if text_fallback is None and isinstance(item, _mcp.types.TextContent):
                    text_fallback = item.text
            # Pas d'image : retourne le texte (comportement adaptateur standard).
            return text_fallback if text_fallback is not None else str(mcp_output)

        # Remplace le forward lié du tool par notre version patched.
        tool.forward = types.MethodType(new_forward, tool)
        logger.debug("patch_forward: take_screenshot patché pour extraire l'ImageContent.")
    except Exception as e:
        # Échec du patch (structure mcpadapt inattendue, version différente...).
        # On ne casse rien : le wrapper de capture classique reste actif (marche si
        # l'outil retourne nativement une PIL.Image, ex: Puppeteer le fait).
        logger.debug("patch_forward échec (%s) — fallback capture classique.", e)


def wrap_screenshot_tools(tools: List[Tool], capture_holder: List[Any]) -> List[Tool]:
    """Remplace les outils de screenshot par leur wrapper capturant (in-place sémantique).

    Args:
        tools: Liste d'outils (MCP ou natifs) de l'agent.
        capture_holder: Liste mutable partagée avec le step_callback (les images
            capturées y sont append).

    Returns:
        Nouvelle liste où les outils de screenshot sont wrappés, les autres intacts.
        Si capture_holder est None, retourne tools inchangé (capture désactivée).
    """
    if capture_holder is None:
        return tools
    wrapped_list: List[Tool] = []
    for t in tools:
        if getattr(t, "name", "") in _ScreenshotCapturingTool.SCREENSHOT_TOOL_NAMES:
            wrapped_list.append(_ScreenshotCapturingTool(t, capture_holder))
        else:
            wrapped_list.append(t)
    return wrapped_list


# ===========================================================================
# F-126 (post-mortem run 2026-08-19_1552) : enrichment des erreurs console.
# ===========================================================================
# `list_console_messages` formate les erreurs SANS localisation ("msgid=1
# [error] Uncaught TypeError ... (0 args)") → le 4B soupçonnait les mauvaises
# fonctions (isCollision/rotation) pendant que le vrai bug (merge()) était à
# 60 lignes de ses lectures → 3 réécritures complètes, run perdu.
# `get_console_message(msgid)` expose la stack complète ("at isCollision
# (index.html:352:58)") : on l'append automatiquement au retour de
# list_console_messages avec la directive read_file ciblée. Fail-open total.
# ===========================================================================
_CONSOLE_LIST_TOOL = "list_console_messages"
_CONSOLE_DETAIL_TOOL = "get_console_message"
_CONSOLE_ERROR_RE = re.compile(r"msgid=(\d+) \[error\]")
_CONSOLE_FRAME_RE = re.compile(r"\(([^()]+?):(\d+):\d+\)")
_CONSOLE_MAX_ERRORS = 4
_CONSOLE_MAX_FRAMES = 8
# F-127 (post-mortem run 2026-08-19_2104) : enum `types` valide de chrome-devtools
# MCP. Le modèle passe des valeurs inventées (ex "exception") → MCP -32602 → step
# perdu. Le wrapper filtre avant délégation (et retire l'arg si tout est invalide).
_CONSOLE_VALID_TYPES = frozenset({
    "log", "debug", "info", "error", "warn", "dir", "dirxml", "table", "trace",
    "clear", "startgroup", "startgroupcollapsed", "endgroup", "assert", "profile",
    "profileend", "count", "timeend", "verbose", "issue",
})


def _sanitize_console_kwargs(kwargs: dict) -> dict:
    """Filtre l'enum `types` de list_console_messages sur les valeurs valides (F-127).

    Retire l'argument si aucune valeur ne survit (l'absence de filtre = tous les
    types, comportement MCP par défaut). Ne touche à rien d'autre.
    """
    types = kwargs.get("types")
    if not isinstance(types, (list, tuple)):
        return kwargs
    valid = [str(t) for t in types if str(t).lower() in _CONSOLE_VALID_TYPES]
    out = dict(kwargs)
    if valid:
        out["types"] = valid
    else:
        out.pop("types", None)
    return out


# F-128 (post-mortem run 2026-08-19_2250) : « boucle de vérification sans
# terminaison ». Le 4B corrigeait le bug (4 search_replace chirurgicaux, guidés
# par les stacks R4) mais NE RE-TESTAIT PAS la page : il relisait le fichier à
# la place → jamais la preuve que l'erreur avait disparu → 17 turns de stall,
# 2×40 steps épuisés, run perdu alors que le livrable était sain. Ce module
# maintient « des erreurs console ont été vues et pas encore re-vérifiées » ;
# les outils d'édition (search_replace/multi_replace/edit_file) collent alors
# une directive post-fix au retour, au moment EXACT du comportement fautif
# (même pattern que les nudges F-114/F-125).
_CONSOLE_PENDING = {"pending": False, "hint": ""}


def reset_console_pending() -> None:
    """Réinitialise l'état post-fix (une exécution de nœud = un cycle)."""
    _CONSOLE_PENDING["pending"] = False
    _CONSOLE_PENDING["hint"] = ""


def _update_console_pending(errors_found: bool, hint: str = "") -> None:
    """Met à jour l'état après CHAQUE list_console_messages : erreurs vues →
    attente d'un fix puis re-vérification ; console propre → attente levée."""
    _CONSOLE_PENDING["pending"] = bool(errors_found)
    _CONSOLE_PENDING["hint"] = hint if errors_found else ""


def pending_post_fix_directive() -> Optional[str]:
    """Directive à coller au retour d'un outil d'édition si des erreurs console
    attendent une re-vérification. None si rien en attente (fail-open total)."""
    if not _CONSOLE_PENDING.get("pending"):
        return None
    hint = f" (dernière localisation : {_CONSOLE_PENDING['hint']})" if _CONSOLE_PENDING.get("hint") else ""
    return (
        f"\n\n➡️ FIX APPLIQUÉ sur un fichier qui avait des erreurs console{hint}. "
        "PROCHAINE ACTION OBLIGATOIRE : re-teste la PAGE — navigate_page puis "
        "list_console_messages — pour CONFIRMER que l'erreur a disparu. NE relis "
        "PAS le fichier : le code source ne prouve rien, seule la console le peut. "
        "Console propre → visual_check restants + final_answer immédiatement."
    )


def _extract_stack_frames(detail: str) -> List[str]:
    """Extrait les frames `at fn (file:line:col)` du retour de get_console_message."""
    frames: List[str] = []
    in_stack = False
    for raw in (detail or "").splitlines():
        line = raw.strip()
        if line.startswith("### Stack trace"):
            in_stack = True
            continue
        if not in_stack:
            continue
        if line.startswith("Note:") or line.startswith("###"):
            break
        if line.startswith("at "):
            frames.append(line)
    return frames


def _enrich_console_output(text: str, detail_tool) -> str:
    """Append les stack traces des erreurs console + directive de correction ciblée.

    Retourne `text` inchangé si aucune erreur / pas d'outil détail / aucune stack
    (fail-open). Budget borné : max 4 erreurs, 8 frames chacune.
    """
    if not text or detail_tool is None:
        return text
    msgids = [int(m) for m in _CONSOLE_ERROR_RE.findall(text)]
    # F-128 : chaque check console rafraîchit l'état « erreurs en attente de
    # re-vérification » (consommé par les outils d'édition via directive).
    _update_console_pending(bool(msgids))
    if not msgids:
        return text
    blocks: List[str] = []
    first_frame: Optional[str] = None
    for msgid in msgids[:_CONSOLE_MAX_ERRORS]:
        detail = str(detail_tool(msgid=msgid) or "")
        frames = _extract_stack_frames(detail)
        if not frames:
            continue
        blocks.append(
            f"[msgid={msgid}]\n" + "\n".join(f"  {f}" for f in frames[:_CONSOLE_MAX_FRAMES])
        )
        if first_frame is None:
            first_frame = frames[0]
    # F-128 : mémorise la localisation fraîche pour la directive post-fix.
    if first_frame:
        _CONSOLE_PENDING["hint"] = first_frame
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


class _ConsoleEnrichingTool(Tool):
    """Wrapper autour de list_console_messages : enrichit les [error] de leur stack trace.

    Même pattern que _ScreenshotCapturingTool : copie l'identité de l'outil wrappé
    (l'agent voit le même nom/description/inputs) et délègue via forward().
    """

    def __init__(self, wrapped: Tool, detail_tool: Optional[Tool]):
        self.name = wrapped.name
        self.description = wrapped.description
        self.inputs = wrapped.inputs
        self.output_type = wrapped.output_type
        self.wrapped = wrapped
        self.detail_tool = detail_tool
        self.is_initialized = True
        self.skip_forward_signature_validation = True
        for attr in ("output_schema", "structured_output"):
            if hasattr(wrapped, attr):
                setattr(self, attr, getattr(wrapped, attr))

    def forward(self, *args, **kwargs):
        # F-127 : sanitise l'enum types AVANT délégation (évite le MCP -32602).
        kwargs = _sanitize_console_kwargs(kwargs)
        result = self.wrapped.forward(*args, **kwargs)
        try:
            return _enrich_console_output(str(result or ""), self.detail_tool)
        except Exception as e:  # pragma: no cover - fail-open garanti
            logger.debug("enrich_console_output échec (%s) — retour brut.", e)
            return result


def wrap_console_enrichment(tools: List[Tool]) -> List[Tool]:
    """Wrappe list_console_messages pour enrichir les erreurs console (F-126).

    Ne fait rien si list_console_messages OU get_console_message est absent de la
    liste (fail-open, ex. serveur DevTools partiel).
    """
    detail = next(
        (t for t in tools if getattr(t, "name", "") == _CONSOLE_DETAIL_TOOL), None
    )
    if detail is None:
        return tools
    out: List[Tool] = []
    for t in tools:
        if getattr(t, "name", "") == _CONSOLE_LIST_TOOL:
            out.append(_ConsoleEnrichingTool(t, detail))
        else:
            out.append(t)
    return out


def make_screenshot_callback(capture_holder: List[Any], visual_criteria_count: int = 0):
    """Fabrique un step_callback smolagents qui peuple observations_images.

    À enregistrer via `step_callbacks=[cb]` sur le CodeAgent (Coder) ou
    ToolCallingAgent (Tester). À chaque fin de step, si un screenshot a été capturé
    ce step (via wrap_screenshot_tools), il est poussé dans
    memory_step.observations_images → devient une content-part image vue par le LLM.

    Le capture_holder est RESET à chaque step (on ne veut garder que le dernier
    screenshot, pas empiler — un screenshot = ~1-2k tokens vision).

    F-114 : si ``visual_criteria_count`` > 0 (Coder avec critères F-90 uniquement —
    le Tester passe 0 par défaut, visual_check n'existe pas chez lui), le callback
    vérifie après chaque screenshot si la checklist visual_check stagne
    (pattern run #9 : 48 screenshots, 0 appel). Au seuil ``_NUDGE_THRESHOLD``, le
    rappel est APPENDU à ``memory_step.observations`` — canal fiable car
    ``_finalize_step`` (qui exécute les step_callbacks) tourne APRÈS l'assignation
    des observations par l'agent (smolagents agents.py) : le texte survit dans la
    mémoire et est vu au step suivant, indépendamment du type de retour de l'outil
    (image PIL pour take_screenshot).

    Args:
        capture_holder: La même liste mutable passée à wrap_screenshot_tools.
        visual_criteria_count: Nombre de critères visuels attendus (gate F-109).
            0 = nudge inactif.

    Returns:
        Une fonction callback(memory_step, agent) -> None.
    """
    def _callback(memory_step, agent) -> None:
        # F-129 : nudge gel au chargement — détection IMMÉDIATE (un timeout de
        # navigation sur fichier local est toujours pathologique), AVANT le
        # nudge anti-gel F-125 qui requiert 3 erreurs protocole consécutives
        # (compteur remis à zéro par les commandes browser-process saines).
        nav_freeze = _build_nav_freeze_nudge(
            getattr(memory_step, "observations", "") or ""
        )
        if nav_freeze:
            try:
                current = getattr(memory_step, "observations", None) or ""
                memory_step.observations = (
                    f"{current}\n\n{nav_freeze}" if current else nav_freeze
                )
            except Exception as e:
                logger.debug("nudge gel chargement : append observations échec (%s).", e)
        # F-125 : nudge anti-gel — AVANT l'early-return capture : un step en erreur
        # protocole ne produit AUCUNE image (holder vide), c'est précisément le
        # signal. Le checklist-nudge F-114 reste, lui, conditionné aux screenshots.
        stall_nudge = _build_browser_stall_nudge(
            getattr(memory_step, "observations", "") or ""
        )
        if stall_nudge:
            try:
                current = getattr(memory_step, "observations", None) or ""
                memory_step.observations = (
                    f"{current}\n\n{stall_nudge}" if current else stall_nudge
                )
            except Exception as e:
                logger.debug("nudge anti-gel : append observations échec (%s).", e)
        if not capture_holder:
            return
        # On ne prend que le dernier screenshot du step (le plus pertinent : état
        # final de la page après les actions). Empiler tous les screenshots
        # coûterait cher en contexte vision pour peu de valeur ajoutée.
        latest = capture_holder[-1]
        try:
            memory_step.observations_images = [latest.copy()]
        except Exception as e:
            logger.debug("step_callback vision : push image échec (%s).", e)
        # Reset pour le step suivant (la liste est partagée, on ne veut pas que le
        # screenshot d'un step précédent ressurgisse si le step courant n'en prend pas).
        capture_holder.clear()
        # F-114 : nudge checklist (Coder uniquement, fail-open).
        if visual_criteria_count > 0:
            nudge = _build_checklist_nudge(visual_criteria_count)
            if nudge:
                try:
                    current = getattr(memory_step, "observations", None) or ""
                    memory_step.observations = f"{current}\n\n{nudge}" if current else nudge
                except Exception as e:
                    logger.debug("nudge checklist : append observations échec (%s).", e)

    return _callback
