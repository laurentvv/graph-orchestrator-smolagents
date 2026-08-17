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


def reset_screenshot_nudge() -> None:
    """Réinitialise le compteur de screenshots du nudge (une exécution de nœud Coder = un cycle).

    À appeler au même endroit que ``tools.reset_visual_audit()`` (même lifecycle).
    Le compteur traverse volontairement les retries de run_with_retry : 30
    screenshots pris à la tentative 1 doivent déclencher le nudge immédiatement
    à la tentative 2, pas après 3 nouveaux screenshots.
    """
    _SCREENSHOT_NUDGE_STATE["count"] = 0


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
        # F-50/F-90 fix : strip filePath des screenshots. chrome-devtools-mcp --isolated
        # rejette toute écriture disque (pas de workspace root configuré) → l'outil
        # échoue AVANT de retourner l'image → la callback vision ne capture rien → le
        # Coder boucle sur l'erreur (run 2026-08-11 : 36 erreurs, 25 steps / 510k tokens).
        # Or l'image revient DE TOUTE FAÇON via observations_images
        # (make_screenshot_callback) : le filePath est donc à la fois inutile ET cassant.
        # On le retire silencieusement (best-effort, jamais d'exception). Le wrapper voit
        # kwargs déjà typés car le sanitizer (F-42) tourne avant/après ce proxy.
        if "filePath" in kwargs:
            kwargs.pop("filePath", None)
            logger.debug(
                "vision_callback: filePath strippé (fix screenshot loop) — "
                "capture via observations_images, pas d'écriture disque."
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
