"""Nœud Tester (runner web) sur pydantic-ai-harness — phase 3.7 (F-162).

Migration plan docs/PLAN_MIGRATION_PYDANTIC_HARNESS.md §3.7 : le runner web du
Tester passe sur le MÊME socle que le Coder pydantic (phases 3.1→3.6), par
configuration fine — pas une seconde migration. Axes de différenciation (plan
§Principe d'architecture) :

  - **Modèle**  : ``no_think_spec`` (Ornith 9B no-think, multimodal mmproj) au
    lieu du 4B fast du Coder ;
  - **Tools**   : DevTools MCP + **Puppeteer MCP** (en plus, repli documenté) +
    12 helpers DOM + sondes + lecture seule (read_file/list_directory) +
    ``fix_known_error`` F-133 — PAS de FileSystem en écriture (parité
    smolagents : le Tester teste, il ne réécrit pas les livrables) ;
  - **Skills**  : web-tester (toujours) + devtools-preview PRÉ-COLLÉ (garantie
    déterministe goulot 2026-08-21) + sélection Architect budgetée F-103,
    resources inlinées (F-97) ;
  - **Prompt**  : prompt compacté F-152 porté en instructions système
    (découpage system/user cache-friendly) + checklist F-46/F-82 + re-test
    ciblé F-47/F-52 en itération > 1 ;
  - **Sortie**  : ``CoderOutput`` (contrat de sortie HISTORIQUE du nœud Tester
    — le « TesterOutput » du plan ; le graphe consomme ce type tel quel) ;
  - **Bornes**  : ``tester_max_steps`` (ou TARGETED_MAX_STEPS en mode ciblé) en
    UsageLimits + ``tester_timeout_s`` en wall-clock (``asyncio.wait_for``,
    parité run_with_retry timeout_s).

Socle hérité tel quel : gardes F-159 (LoopGuard v2 + gels navigateur + churn,
IdleBreaker hint Tester, ReviveRetry + revive llama-server), compaction
TieredCompaction ciblée max_steps Tester, vision F-161 (screenshots → contexte
image + purge perte-zéro), tool_choice='auto' avec toolsets (leçon grammaire
F-160 — le Tester porte ~50 outils avec Puppeteer).

Écarts documentés vs profil Coder (volontaires) : PAS de GoalGate (le Tester
ne produit pas de livrable — ses preuves de complétion n'existent pas) ; PAS
de reminders checklist/wind-down F-114/F-131 (portés par visual_check, outil
Coder) ; nudges loop/stall/idle/browser conservés via
``build_tester_reminders``.

Activation : ``TESTER_ENGINE=pydantic`` (défaut ``smolagents`` — zéro
changement de comportement tant que le flag n'est pas posé).
"""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from .logging_utils import NodeMetrics
from .models import CoderOutput

from pydantic_ai.capabilities import AbstractCapability

# Le « TesterOutput » du plan = le contrat de sortie historique du nœud Tester
# (web_tester smolagents valide déjà CoderOutput) — alias documentaire.
TesterOutput = CoderOutput

# Imports pydantic-ai différés dans les fonctions (convention coder_pydantic).


# ============================================================
# Custom tools (lecture seule + auto-fixer — parité smolagents)
# ============================================================


def read_file(path: str, offset: int = 0, limit: int = -1) -> str:
    """Reads a file and returns its content with line numbers.

    Use this to inspect the generated HTML/JS code BEFORE testing it (identify
    the real ids/classes to target in your assertions). NEVER guess a DOM id.

    Args:
        path: The file path (relative, e.g. "script.js").
        offset: The starting line number (0-indexed).
        limit: Max number of lines to return (-1 = all).
    """
    from . import tools as _tools

    return _tools.read_file(path=path, offset=offset, limit=limit)


def list_directory(path: str = ".") -> str:
    """Lists the contents of a directory.

    Args:
        path: The directory path to list. Defaults to current directory.
    """
    from . import tools as _tools

    return _tools.list_directory(path=path)


def fix_known_error(path: str, error_message: str) -> str:
    """Applies a DETERMINISTIC fix for a mechanically-known error class (F-133).

    Use ONLY for proven mechanical fixes: "Assignment to constant variable"
    (const → let) or a literal \\n separator causing a SyntaxError. After a
    successful fix, RELOAD the page and CONTINUE testing. Anything else →
    normal verdict.

    Args:
        path: The file to fix (relative).
        error_message: The exact console error message.
    """
    from . import tools as _tools

    return _tools.fix_known_error(path=path, error_message=error_message)


def build_tester_custom_tools() -> list:
    """Liste des custom tools du profil Tester (wrappers ci-dessus)."""
    return [read_file, list_directory, fix_known_error]


# ============================================================
# Puppeteer MCP (repli documenté — DevTools reste le pilote primaire)
# ============================================================


def make_tester_process_tool_call(vision: bool = True):
    """``process_tool_call`` du toolset Puppeteer — délègue au processor
    commun (strippage filePath DevTools, sanitisation console F-127,
    enrichissement F-126, retours image F-161) après strippage additionnel de
    ``filePath`` sur ``puppeteer_screenshot`` (parité ``vision_callback.
    _FILEPATH_TOOLS`` qui couvrait les DEUX pilotes côté smolagents).
    """
    from .coder_pydantic_mcp import make_process_tool_call

    base = make_process_tool_call(vision=vision)

    async def process_tool_call(ctx, call_tool, name: str, tool_args: dict) -> Any:  # noqa: ANN001
        args = dict(tool_args or {})
        if name == "puppeteer_screenshot":
            for fp in ("filePath", "file_path"):
                if args.pop(fp, None) is not None:
                    pass  # strippé : le serveur Puppeteer ne connaît pas filePath
        return await base(ctx, call_tool, name, args)

    return process_tool_call


def build_puppeteer_mcp_toolset(settings) -> Optional[Any]:
    """MCPToolset Puppeteer (stdio npx), ou None si indisponible.

    Parité smolagents web_tester : même commande (``npx -y
    @modelcontextprotocol/server-puppeteer``), même PUPPETEER_EXECUTABLE_PATH,
    ``init_timeout`` = ``puppeteer_connect_timeout_s`` (borne F-104 : un npx
    pendu ne fige plus le nœud). DÉGRADATION assumée : Puppeteer ne charge pas
    les fichiers file:// locaux (bug du serveur déprécié) — DevTools est le
    pilote primaire, Puppeteer reste exposé comme repli outillage.
    """
    from fastmcp.client.transports import StdioTransport
    from pydantic_ai.mcp import MCPToolset

    env = os.environ.copy()
    env["PUPPETEER_EXECUTABLE_PATH"] = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    transport = StdioTransport(command="npx", args=["-y", "@modelcontextprotocol/server-puppeteer"], env=env)
    return MCPToolset(
        transport,
        id="puppeteer",
        init_timeout=settings.puppeteer_connect_timeout_s,
        process_tool_call=make_tester_process_tool_call(
            vision=getattr(settings, "coder_pydantic_vision", True)
        ),
        tool_error_behavior="retry",
    )


# ============================================================
# Ouverture groupée (lifecycle + dégradation gracieuse par serveur)
# ============================================================


@dataclass
class TesterMCP:
    """État MCP du nœud Tester : toolsets ouverts + flags pour le prompt."""

    toolsets: list = field(default_factory=list)
    browser_tools_available: bool = False
    puppeteer_available: bool = False
    context7_available: bool = False


@asynccontextmanager
async def open_tester_mcp(settings):
    """Ouvre les toolsets MCP du Tester : DevTools + helpers DOM + Puppeteer +
    Context7, avec dégradation INDIVIDUELLE par serveur (miroir F-104 / F-160).

    Puppeteer dispose d'un statut à part : son échec (timeout npx, Chrome
    absent) n'entame PAS le run — DevTools est le pilote primaire, on loggue
    simplement le repli.
    """
    from .coder_pydantic_mcp import (
        build_context7_mcp_toolset,
        build_devtools_mcp_toolset,
        build_dom_helper_toolset,
    )

    state = TesterMCP()
    async with AsyncExitStack() as stack:
        devtools = build_devtools_mcp_toolset(settings)
        if devtools is not None:
            try:
                await stack.enter_async_context(devtools)
                state.toolsets.append(devtools)
                state.browser_tools_available = True
                print("[MCP] chrome-devtools (pydantic tester) : connecté.")
            except Exception as exc:  # noqa: BLE001 — dégradation, pas d'échec nœud
                print(f"[MCP] chrome-devtools (pydantic tester) : indisponible ({exc}) — pilote primaire ABSENT.")

        helpers = build_dom_helper_toolset(getattr(devtools, "client", None) if devtools is not None else None)
        if helpers is not None:
            state.toolsets.append(helpers)

        puppeteer = build_puppeteer_mcp_toolset(settings)
        if puppeteer is not None:
            try:
                await stack.enter_async_context(puppeteer)
                state.toolsets.append(puppeteer)
                state.puppeteer_available = True
                print("[MCP] puppeteer (pydantic tester) : connecté (repli).")
            except Exception as exc:  # noqa: BLE001
                print(f"[MCP] puppeteer (pydantic tester) : indisponible ({exc}) — repli DevTools seul.")

        context7 = build_context7_mcp_toolset(settings)
        if context7 is not None:
            try:
                await stack.enter_async_context(context7)
                state.toolsets.append(context7)
                state.context7_available = True
                print("[MCP] context7 (pydantic tester) : connecté.")
            except Exception as exc:  # noqa: BLE001
                print(f"[MCP] context7 (pydantic tester) : indisponible ({exc}) — sans doc.")

        yield state


# ============================================================
# Instructions (profil Tester — prompt compacté F-152 en natif tool-calls)
# ============================================================

_TESTER_PROTOCOL_BLOCK = """### PROTOCOL (native tool calls — MANDATORY)
1. ACT, do not narrate: every turn MUST call at least one tool. A turn without any tool call is a failed idle turn.
2. Call your tools DIRECTLY as tool calls with NAMED arguments (e.g. evaluate_script(function="...")). Never write Python code — only the tools.
3. NAVIGATION FIRST (STEP 1): begin with navigate_page(url=...) on the exact URL given in the task. Do NOT read source files upfront; you are a dynamic black-box tester.
   The browser starts on about:blank — ANY interaction before navigate_page is void (wasted turns).
   ⚠️ If navigate_page TIMEOUTS on this local page: the UI is frozen by an infinite JS loop. Return status="failure" with details="page frozen on load (infinite loop)".
4. ANIMATION = TEMPORAL TEST, NOT STATIC STATE: for algorithm visualizers and animations, measure progression over time (verify partial state during execution, not merely initial or post-completion state).
5. GAME/CANVAS = MOTION PROOF REQUIRED: for interactive games, prove motion with probe_canvas_activity (ANIMATING) or expose_game_state.
6. PROBE ISOLATION & ANIMATED SORTS: successive evaluate_script calls MUTATE the page (clicks, resets, corrupted state). Before each INDEPENDENT assertion sequence, reset the page with navigate_page(type="reload") (~0.2s, cheap). For sorting tasks, NEVER conclude "not sorted" from a snapshot taken before the animation completes: call probe_sort_state(max_wait_ms=...) ONCE and trust its verdict — SORTED_AFTER_WAIT = pass, IN_PROGRESS_STILL_MOVING = pass (slow animation, NOT a defect), STATIC_UNSORTED = fail.
7. STEP BUDGET — CONVERGE RAPIDLY: batch assertions per page state into a single evaluate_script; never re-verify already-PASS criteria; call final_result immediately once every criterion has a verdict.
8. MECHANICAL FIXES ONLY: if the console shows a proven mechanical error (const reassignment, literal \\n), apply fix_known_error, reload, and CONTINUE testing — anything else goes to your verdict, never rewrite files yourself."""

_FINAL_RESULT_BLOCK = """### FINAL VERDICT (structured output)
When every criterion has a verdict, call the `final_result` tool with ALL fields:
- task_id: "{task_id}"
- status: "success" ONLY if: the page loads, 0 console errors after interactions, AND every checklist criterion passes. Otherwise "failure" with the exact bugs in details.
- details: test summary — console state, each criterion PASS/FAIL (quote the observed values), screenshots inspected.
- linter_ok: true if the console was checked clean. vision_ok: true if you inspected a screenshot."""


def _tester_skills_block(task: dict, settings) -> str:
    """Sélection des skills du Tester — miroir web_tester.py smolagents.

    Garantie déterministe (goulot 2026-08-21) : devtools-preview PRÉ-COLLÉ
    avant le budget (le mode d'emploi des outils ne peut pas dépendre de la
    sélection LLM de l'Architect) ; web-tester toujours conservé ; resources
    inlinées si ``tester_inline_skill_resources`` (F-97/MA-5 — le Tester
    one-shot a besoin de TOUT le contenu, pas de la progressive disclosure).
    Copie défensive de task["tester_skills"] (persisté au checkpoint — review
    Kilo PR #102 : jamais de mutation du dict de tâche).
    """
    from .skills_loader import enforce_skill_budget, load_skill_body, load_skill_body_resolved

    tester_skills = list(task.get("tester_skills", []) or [])
    if not tester_skills:
        tester_skills = ["web-tester"]
    if "devtools-preview" not in tester_skills:
        tester_skills.insert(0, "devtools-preview")
    tester_skills = enforce_skill_budget(
        tester_skills,
        budget_tokens=settings.skill_budget_tokens,
        always_skills={"web-tester"},
    )

    loader = load_skill_body_resolved if settings.tester_inline_skill_resources else load_skill_body
    blocks = []
    for name in tester_skills:
        body = loader(name)
        if body:
            blocks.append(f"### SKILL: {name}\n{body}")
    return "Here are your mandatory skill instructions:\n\n" + "\n\n".join(blocks)


def _devtools_hint(browser_tools_available: bool, vision_available: bool) -> str:
    """Bloc outils navigateur du profil Tester (conditionné aux connexions).

    Port du devtools_hint smolagents : DevTools pilote PRIMAIRE, avertissement
    filePath F-50/F-90 (déjà strippé côté serveur d'outils — consigne
    conservée car le modèle tente spontanément de l'utiliser), take_snapshot/
    click/fill, VISUAL BUG ALERT, vision F-161 (le screenshot revient COMME
    IMAGE dans le contexte).
    """
    if not browser_tools_available:
        return ""
    from .chrome_devtools_tool import DEVTOOLS_BASE_DOC

    if vision_available:
        vision_line = (
            "- `take_screenshot()`: the screenshot comes back AS AN IMAGE attached to your "
            "context — LOOK at it (layout breaks, invisible elements, overlapping UI). "
            "[VISUAL BUG ALERT CRITICAL]: if key elements disappear or become invisible "
            "during interaction, it is an immediate FAILURE. Use evaluate_script + "
            "getComputedStyle to prove color/visibility issues.\n"
        )
    else:
        vision_line = (
            "- `take_screenshot()`: text confirmation only (vision disabled) — base visual "
            "verdicts on DOM probes (evaluate_script, discover_ui), not on image inspection.\n"
        )
    return (
        "### 🖥️ BROWSER TOOLS (Chrome DevTools MCP — PRIMARY pilot)\n"
        "Navigation, assertions, console, screenshots — ALL through the DevTools tools.\n"
        "  [DANGER FATAL] : NEVER pass the optional `filePath` argument in ANY of these tools "
        "(leave it undefined — the server rejects it: 'Access denied').\n"
        f"{DEVTOOLS_BASE_DOC}\n"
        "- `take_snapshot(verbose: true)` : full a11y/DOM tree (structure, IDs, visibility).\n"
        "- `click(uid=...)` / `fill(uid=..., value=...)` : interactions (uids from take_snapshot).\n"
        f"{vision_line}"
        "Priority: DevTools for EVERYTHING. The legacy `puppeteer_*` tools (if present) are a "
        "FALLBACK only when DevTools is unavailable.\n"
    )


def build_tester_instructions(
    task: dict,
    settings,
    browser_tools_available: bool = True,
    puppeteer_available: bool = False,
    context7_available: bool = False,
    vision_available: bool = True,
) -> str:
    """Instructions système du profil Tester (partie STABLE, cache-friendly).

    Rôle web_tester + skills + protocole natif + doc outils + format de
    verdict. Le contenu variable (spec, checklist, URLs) part dans le user
    prompt (build_tester_user_prompt).
    """
    from .prompts import build_role_header

    parts = [
        build_role_header("web_tester"),
        _TESTER_PROTOCOL_BLOCK,
        _devtools_hint(browser_tools_available, vision_available),
    ]

    if browser_tools_available:
        parts.append(
            "### 🛠️ DOM PROBES & HELPERS (high-level tools — prefer these over raw evaluate_script)\n"
            "- `discover_ui()`: complete UI inventory (canvas ids/dimensions, buttons, inputs) — call FIRST after navigate_page, NEVER guess a DOM id.\n"
            "- `probe_canvas_activity(window_ms=...)`: canvas liveness (ANIMATING / STATIC_PAINTED + suspect_animation_broken).\n"
            "- `probe_sort_state(max_wait_ms=...)`: animated-sort verdict (waits IN-PAGE until sorted). NEVER conclude 'not sorted' without it.\n"
            "- `expose_game_state(names=...)`: internal runtime variables across 1.5s (changed_over_1500ms proves the state LIVES).\n"
            "- `instrument_calls(names=..., window_s=...)`: counts REAL function calls (draw/update/gameLoop).\n"
            "- `dump_function_source(names=...)`: in-page source of global functions (how logic bugs are READ).\n"
            "- `force_advance(fn=..., times=...)`: accelerated clock for logic testing.\n"
            "- `fuzz_click_all_buttons()` / `fuzz_keyboard_controls()`: monkey testing, then re-check list_console_messages.\n"
            "- `heal_selector(tag=..., text_hint=...)`: re-locate a renamed element (self-healing selector).\n"
            "- `clean_dom()` / `add_visual_tags()`: lightweight DOM / numbered badges before screenshots.\n"
        )
    if puppeteer_available:
        parts.append(
            "### LEGACY Puppeteer tools (FALLBACK)\n"
            "The `puppeteer_*` tools drive a SEPARATE Chrome instance that does NOT load local "
            "file:// pages properly. Use them ONLY if DevTools is unavailable."
        )
    if context7_available:
        parts.append(
            "### Library docs (Context7)\n"
            "`resolve_library_id` / `query_docs` — ONLY to check an external library's real API. "
            "NEVER for vanilla HTML/JS/CSS."
        )

    parts.append(_FINAL_RESULT_BLOCK.format(task_id=task.get("id", "")))
    parts.append(_tester_skills_block(task, settings))
    return "\n\n".join(p for p in parts if p)


def build_tester_user_prompt(task: dict, settings, use_targeted: bool) -> str:
    """User prompt (partie VARIABLE) : spec complète OU re-test ciblé +
    checklist + sous-tâche + URLs exactes. Port direct du prompt smolagents
    (les blocs canoniques F-46/F-82/F-47/F-52 sont réutilisés tels quels).
    """
    from .targeted_retest import extract_bug_points, build_targeted_retest_block
    from .requirements_checklist import extract_functionalities, build_checklist_block
    from .validation_criteria import build_functional_criteria_block

    workspace_url = "file:///" + os.path.abspath(os.getcwd()).replace("\\", "/")

    target_files_urls = ""
    if task.get("target_files"):
        target_files_urls = "The target files of this task are located at:\n"
        for fpath in task["target_files"]:
            target_files_urls += f"- {workspace_url}/{fpath.replace(chr(92), '/')}\n"

    # Premier fichier cible = exemple concret de navigation (un petit LLM suit
    # littéralement l'exemple : il DOIT pointer sur le vrai fichier, pas la
    # racine du run — bug historique du navigateur s'ouvrant à la racine).
    primary_target = (task.get("target_files") or ["index.html"])[0]
    primary_url = f"{workspace_url}/{primary_target.replace(chr(92), '/')}"

    full_requirements = task.get("original_content") or task.get("content", "")

    if use_targeted:
        refutations = task.get("refutations", [])
        iteration = task.get("iteration", 1)
        bugs_feedback = extract_bug_points(refutations) or ""
        git_diff = task.get("git_diff", "")
        checklist_block = build_targeted_retest_block(bugs_feedback, iteration, git_diff)
        reqs_block = ""
    else:
        functionalities = extract_functionalities(full_requirements)
        checklist_block = build_checklist_block(functionalities)
        architect_criteria = task.get("functional_test_criteria") or []
        if architect_criteria:
            checklist_block = build_functional_criteria_block(architect_criteria)
        reqs_block = f"### COMPREHENSIVE SPECIFICATION (expected behaviors to verify)\n{full_requirements}\n"

    return f"""{reqs_block}{checklist_block}
### Description of the subtask under test
{task['content']}

ATTENTION - The absolute working directory is: {workspace_url}
{target_files_urls}
[PATH FORMAT FOR DIFFERENT TOOLS] Your tools expect specific path formats:
- `navigate_page(url=...)` (DevTools): uses the URL format `file:///D:/...` (see the exact URL below). This is the ONLY tool expecting `file:///`.
- `read_file(path=...)` / `list_directory(path=...)`: uses a relative path (`index.html`, `styles.css`) or a standard absolute path `D:/GIT/...` (Do NOT pass MSYS `/d/GIT/...` or `file:///`).

### ⚠️ MANDATORY NAVIGATION via DevTools `navigate_page` (NOT puppeteer_navigate)
Always use `navigate_page(url="{primary_url}")` to open the application in Chrome.
EXACT URL to pass: {primary_url}
Verify the generated web application. Execute functional assertions via `evaluate_script` (DevTools) to prove key behaviors work dynamically.
"""


# ============================================================
# Assemblage de l'Agent (testable 0-LLM : construire ≠ exécuter)
# ============================================================


class _ProgressPrintCapability(AbstractCapability):
    """Impression de progression par tour (observabilité du nœud, miroir du
    verbosity HIGH smolagents : un nœud de 10-20 min ne peut pas être muet).

    Après CHAQUE requête modèle : tour + noms des tool calls émis (ou « tour
    sans tool call »). Fail-open total ; sans effet sur le comportement.

    Sous-classe AbstractCapability (leçon run 2 F-162 : le harness APPELLE
    l'instance à l'enregistrement — un duck-typing sans héritage lève
    ``'object' is not callable`` dès le 1er run, invisible à la construction).
    """

    def __init__(self):
        self.id = None
        self.description = None
        self.defer_loading = False

    async def before_run(self, ctx) -> None:  # noqa: ANN001
        print("[T] Tester (pydantic) : démarrage des tours de test.")

    async def after_model_request(self, ctx, *, request_context, response):  # noqa: ANN001
        try:
            from pydantic_ai.messages import ToolCallPart

            calls = [p.tool_name for p in response.parts if isinstance(p, ToolCallPart)]
            if calls:
                print(f"[T] tour {ctx.run_step}: {', '.join(calls)}")
            else:
                print(f"[T] tour {ctx.run_step}: sans tool call")
        except Exception:  # noqa: BLE001 — impression best-effort
            pass
        return response


def build_tester_capabilities(task: dict, settings, max_steps: int,
                              extra_capabilities: Optional[list] = None,
                              on_reminder_fired=None) -> list:
    """Liste ordonnée des capabilities du profil Tester.

    Différences vs build_coder_capabilities : PAS de FileSystem (lecture via
    custom tools read-only), PAS de GoalGate (aucun livrable à prouver),
    IdleBreaker avec hint Tester, compaction/reminders calibrés sur
    ``max_steps`` (tester_max_steps ou TARGETED_MAX_STEPS).
    """
    from pydantic_ai_harness import ToolOutputLimits

    from .coder_pydantic_guards import (
        CoderGuardState,
        IdleBreakerCapability,
        ToolGuardsCapability,
        build_compaction_capabilities,
        build_tester_reminders,
    )
    from .coder_pydantic_vision import build_vision_capabilities

    capabilities: list = list(extra_capabilities or [])  # ReviveRetry EN TÊTE
    capabilities.append(_ProgressPrintCapability())
    capabilities.append(ToolOutputLimits())
    capabilities.extend(build_vision_capabilities(settings))
    if getattr(settings, "coder_pydantic_guards", True):
        state = CoderGuardState()
        # WarnNearLimits ancré sur le budget de REQUÊTES réel (×2, cf. run
        # run_tester_pydantic) — pas sur tester_max_steps brut.
        capabilities.extend(build_compaction_capabilities(settings, max_steps=max_steps * 2))
        capabilities.append(
            ToolGuardsCapability(
                state,
                stall_threshold=int(settings.stall_detector_threshold),
                churn_threshold=5,
                browser_stall_threshold=3,
            )
        )
        capabilities.append(
            IdleBreakerCapability(
                state,
                threshold=int(settings.idle_breaker_threshold),
                action_hint=(
                    "navigate_page / list_console_messages / evaluate_script / probe_* , or "
                    "finish with final_result"
                ),
            )
        )
        capabilities.append(
            build_tester_reminders(
                state, on_fire=on_reminder_fired, max_requests=max_steps * 2
            )
        )
    else:
        from pydantic_ai_harness import ClearToolResults

        capabilities.append(ClearToolResults(max_fraction=0.7))
    return capabilities


def build_tester_agent(model, task: dict, settings, tester_max_steps: int,
                       browser_tools_available: bool = True,
                       puppeteer_available: bool = False,
                       context7_available: bool = False,
                       vision_available: bool = True,
                       extra_capabilities: Optional[list] = None,
                       on_reminder_fired=None, toolsets: Optional[list] = None):
    """Assemble l'Agent pydantic du profil Tester — socle commun, profil par
    configuration (tools/skills/prompt/modèle/output). Testable sans GPU
    (construction seule). Miroir de build_coder_agent."""
    from pydantic_ai import Agent, ModelSettings

    capabilities = build_tester_capabilities(
        task, settings, max_steps=tester_max_steps,
        extra_capabilities=extra_capabilities, on_reminder_fired=on_reminder_fired,
    )

    model_settings = ModelSettings(
        max_tokens=settings.reasoning_max_tokens,
        timeout=settings.llm_timeout_s,
    )
    if toolsets:
        # Leçon F-160 : tool_choice='required' (défaut pydantic-ai sur les runs
        # à output outil) → grammaire GBNF d'union qui casse llama-server au
        # delà de ~45-60 outils ; le Tester en porte ~50 avec Puppeteer.
        model_settings["tool_choice"] = "auto"

    return Agent(
        model,
        instructions=build_tester_instructions(
            task, settings,
            browser_tools_available=browser_tools_available,
            puppeteer_available=puppeteer_available,
            context7_available=context7_available,
            vision_available=vision_available,
        ),
        capabilities=capabilities,
        tools=build_tester_custom_tools(),
        toolsets=list(toolsets) if toolsets else [],
        output_type=CoderOutput,
        retries=settings.worker_max_retries,
        model_settings=model_settings,
    )


# ============================================================
# Exécution du nœud (contrat identique à WebTestRunner smolagents)
# ============================================================


async def run_tester_pydantic(
    task: dict, settings
) -> Tuple[Optional[CoderOutput], Optional[NodeMetrics]]:
    """Exécute le runner web du Tester sur pydantic-ai-harness.

    Retour (CoderOutput|None, NodeMetrics|None) — contrat identique au chemin
    smolagents. Timeout wall-clock ``tester_timeout_s`` (asyncio.wait_for,
    parité run_with_retry : une fois le budget épuisé, échec propre — le
    Static Tester/Judge arbitrent sur ce qui a déjà été observé).
    """
    from pydantic_ai.exceptions import UsageLimitExceeded
    from pydantic_ai.models.openai import OpenAIChatModel, OpenAIModelProfile
    from pydantic_ai.providers.openai import OpenAIProvider
    from pydantic_ai.usage import UsageLimits

    from .coder_pydantic_guards import GuardAbort, ReviveRetryCapability
    from .llama_server import model_lifecycle
    from .llm_retry import RetryPolicy
    from .targeted_retest import TARGETED_MAX_STEPS, should_use_targeted_retest

    refutations = task.get("refutations", [])
    iteration = task.get("iteration", 1)
    use_targeted = should_use_targeted_retest(iteration, refutations)
    tester_max_steps = TARGETED_MAX_STEPS if use_targeted else settings.tester_max_steps
    mode_label = "CIBLÉ (re-test bugs)" if use_targeted else "complet"
    print(f"    [>] Tester mode: {mode_label} (max_steps={tester_max_steps})")

    user_prompt = build_tester_user_prompt(task, settings, use_targeted)
    node_label = f"tester[{task.get('id', '?')}]"
    model_name = str(settings.no_think_spec.model or "")

    t0 = time.time()
    with model_lifecycle(settings.no_think_spec) as srv:
        if not srv.api_base:
            print("[-] Tester (pydantic) : échec du spawn llama-server — échec propre.")
            return None, None

        profile = OpenAIModelProfile(
            openai_supports_strict_tool_definition=False,
            openai_chat_supports_multiple_system_messages=False,
            openai_chat_supports_max_completion_tokens=False,
        )
        model = OpenAIChatModel(
            srv.model_id,
            provider=OpenAIProvider(base_url=srv.api_base, api_key=srv.api_key),
            profile=profile,
        )

        def _model_factory(api_base: str):
            return OpenAIChatModel(
                srv.model_id,
                provider=OpenAIProvider(base_url=api_base, api_key=srv.api_key),
                profile=profile,
            )

        revive_cap = None
        if settings.llm_retry_enabled:
            revive_cap = ReviveRetryCapability(
                policy=RetryPolicy(
                    max_retries=settings.llm_transport_retries,
                    base_delay_s=settings.llm_retry_base_delay_s,
                    max_delay_s=settings.llm_retry_max_delay_s,
                    jitter_factor=settings.llm_retry_jitter,
                ),
                revive=srv.revive,
                model_factory=_model_factory,
                current_base=srv.api_base,
            )

        async with open_tester_mcp(settings) as mcp:
            agent = build_tester_agent(
                model,
                task,
                settings,
                tester_max_steps,
                browser_tools_available=mcp.browser_tools_available,
                puppeteer_available=mcp.puppeteer_available,
                context7_available=mcp.context7_available,
                vision_available=getattr(settings, "coder_pydantic_vision", True),
                extra_capabilities=[revive_cap] if revive_cap is not None else None,
                toolsets=mcp.toolsets,
            )
            print(f"[*] Tester (pydantic) — llama-server prêt : {srv.api_base}")
            try:
                # Budget requêtes = tester_max_steps × 2 (leçon run 1 F-162 : en
                # smolagents, 1 step CodeAgent enchaîne PLUSIEURS tool calls dans
                # un seul bloc Python ; en pydantic 1 requête ≈ 1 tool call — le
                # budget 1:1 épuisait les 16 requêtes avant tout verdict, run tué
                # à 768 s / 25,8k tokens. La vraie garde anti-boucle reste
                # ToolGuardsCapability, pas le décompte de requêtes).
                result = await asyncio.wait_for(
                    agent.run(
                        user_prompt,
                        usage_limits=UsageLimits(
                            request_limit=tester_max_steps * 2,
                            tool_calls_limit=tester_max_steps * 6,
                        ),
                    ),
                    timeout=settings.tester_timeout_s,
                )
            except GuardAbort as exc:
                duration = time.time() - t0
                print(f"[-] Tester (pydantic) GARDE-ABORT propre ({exc})")
                return None, NodeMetrics(
                    node=node_label, model=model_name, duration_s=duration,
                    input_tokens=None, output_tokens=None,
                )
            except UsageLimitExceeded as exc:
                duration = time.time() - t0
                print(
                    f"[-] Tester (pydantic) : budget de requêtes épuisé ({exc}) — "
                    "échec propre (le Static Tester/Judge arbitrent)."
                )
                return None, NodeMetrics(
                    node=node_label, model=model_name, duration_s=duration,
                    input_tokens=None, output_tokens=None,
                )
            except asyncio.TimeoutError:
                duration = time.time() - t0
                print(
                    f"[-] Timeout du nœud tester après {settings.tester_timeout_s}s "
                    "(boucle/interaction sans fin) — échec propre."
                )
                return None, NodeMetrics(
                    node=node_label, model=model_name, duration_s=duration,
                    input_tokens=None, output_tokens=None,
                )
            except Exception as exc:  # noqa: BLE001 — échec propre, le graphe continue
                duration = time.time() - t0
                print(f"[-] Tester (pydantic) ÉCHEC ({type(exc).__name__}: {exc})")
                return None, NodeMetrics(
                    node=node_label, model=model_name, duration_s=duration,
                    input_tokens=None, output_tokens=None,
                )

        usage = result.usage  # propriété (piège v2.33 : pas une méthode)
        duration = time.time() - t0
        metrics = NodeMetrics(
            node=node_label,
            model=model_name,
            duration_s=duration,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
        )
        output = result.output
        if isinstance(output, CoderOutput):
            print(
                f"[+] Tester (pydantic) : status={output.status} "
                f"({metrics.input_tokens or 0} in / {metrics.output_tokens or 0} out, "
                f"{duration:.1f}s)"
            )
        return output, metrics
