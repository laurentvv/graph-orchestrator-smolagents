"""Nœud Coder sur pydantic-ai-harness — socle commun × profil Coder (F-158).

Migration plan phase 3.1-3.2 (docs/PLAN_MIGRATION_PYDANTIC_HARNESS.md) : ce module
construit le PROFIL CODER sur le socle pydantic-ai. Le profil Tester (runner web,
phase 3.7) réutilisera ces mêmes briques par configuration (tools/skills/prompt/
modèle/output), pas par une seconde migration.

Périmètre CE module (parité 3.1 + 3.2) :
  - FileSystem (8 tools path-scopés, ``expected_hash`` concurrence optimiste,
    protected patterns ≡ io_guard structurel) ;
  - custom tools déléguant aux implémentations canoniques de ``tools.py``
    (search_replace / multi_replace / append_file / check_js_syntax /
    read_python_skeleton / log_event / visual_check / check_run_state) ;
  - ``output_type=CoderOutput`` : sortie validée nativement par tool-calling
    (smoke test D du spike F-157) — remplace ``extract_and_validate`` + le
    sauvetage DSPy ;
  - instructions ROLE_BLOCKS coder + invariants + protocole tool-calls natifs
    (adapté du spike round 3 GO : -66 % tokens IN vs smolagents) ;
  - skills eager (sélection Architect + budget F-103) + tool load_skill ;
  - UsageLimits ≡ coder_max_steps ; escalade Ultra F-111 conservée via
    ``_select_coder_spec`` (itération ≥ 3) ; ClearToolResults + ToolOutputLimits
    du spike conservés (prouvés en isolation).

Phases 3.3-3.4 (F-159, coder_pydantic_guards.py) : gardes comportementales
(LoopGuard v2, StallDetector, IdleBreaker, GoalGate, ReviveRetry) + nudges
SystemReminders dynamiques + compaction TieredCompaction — assemblées par
``guards=True`` dans build_coder_agent (bascule ``CODER_PYDANTIC_GUARDS``).

Phase 3.5 (F-160, coder_pydantic_mcp.py) : MCP navigateur & doc —
chrome-devtools (navigate/console/evaluate + 12 helpers DOM + enrichissement
console F-126 via process_tool_call) et Context7, ouverts par open_coder_mcp
(dégradation gracieuse par serveur). ``browser_tools_available`` devient
dynamique : le skill devtools-preview est re-pré-collé sur tâche web et le
bloc VISUAL VALIDATION (console-centrique) revient. Écart restant : la vision
multimodale (screenshots → contexte image) est la phase 3.6 — take_screenshot
ne retourne ici qu'une confirmation texte.

Activation : ``CODER_ENGINE=pydantic`` (défaut ``smolagents`` — zéro changement
de comportement tant que le flag n'est pas posé).
"""

from __future__ import annotations

import os
import time
from typing import Optional, Tuple

from .logging_utils import NodeMetrics
from .models import CoderOutput

# Imports pydantic-ai différés dans les fonctions : le module reste importable
# (tests 0-LLM, CI sans réseau) même si un extra harness manque un jour.


# ============================================================
# Custom tools (wrappers minces vers les implémentations canoniques)
# ============================================================
# Les fonctions de tools.py sont décorées @tool (smolagents → objet SimpleTool
# sans __name__) : elles ne peuvent PAS être passées telles quelles à
# Agent(tools=[...]). Ces wrappers exposent une signature/docstring propres au
# tool-calling pydantic-ai et délèguent à l'implémentation unique (gardes
# F-132 anti-no-op/anti-\n littéral, io_guard F-95, diagnostics P2 — tout est
# conservé par délégation).


def search_replace(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Surgically edits a file by replacing the 'old_string' block with the 'new_string' block.

    PREFER this tool over write_file when modifying an EXISTING file: you only need to
    provide the exact code to find and its replacement, NOT the whole file. The matching
    is TOLERANT (minor whitespace differences, '...' ellipses). If 'old_string' appears
    multiple times the edit fails (add surrounding lines) unless replace_all=True.

    Args:
        path: The file path to edit (relative). Must exist.
        old_string: The exact block of text to find (copy it verbatim from the file).
        new_string: The replacement block — real code, never a placeholder.
        replace_all: True to replace EVERY exact occurrence instead of failing on ambiguity.
    """
    from . import tools as _tools

    return _tools.search_replace(
        path=path, old_string=old_string, new_string=new_string, replace_all=replace_all
    )


def multi_replace(path: str, replacements: list) -> str:
    """Applies multiple search/replace operations to a file in ONE call, without rewriting it.

    Args:
        path: The file path to edit (relative). Must exist.
        replacements: A list of dicts, each with 'old_string' and 'new_string'.
            Example: [{"old_string": "foo()", "new_string": "bar()"}]
    """
    from . import tools as _tools

    return _tools.multi_replace(path=path, replacements=replacements)


def append_file(path: str, content: str) -> str:
    """Appends content to the END of an existing file (incremental strategy only).

    Args:
        path: The file path to append to (relative).
        content: The block to append — real code, never a placeholder.
    """
    from . import tools as _tools

    return _tools.append_file(path=path, content=content)


def check_js_syntax(path: str) -> str:
    """Checks JavaScript syntax (node --check) and CSS variable definitions of a file.

    ALWAYS call this on every .js file (and the <script> content of .html files)
    BEFORE finishing: it detects SyntaxError, TypeScript-in-vanilla and undefined
    CSS variables (var(--x) without a :root definition).

    Args:
        path: The file to check (relative), e.g. "script.js" or "index.html".
    """
    from . import tools as _tools

    return _tools.check_js_syntax(path=path)


def read_python_skeleton(path: str) -> str:
    """Reads the skeleton of a Python file (signatures + docstrings, body elided).

    Cheap overview of a large .py file without loading its full content.

    Args:
        path: The Python file path (relative).
    """
    from . import tools as _tools

    return _tools.read_python_skeleton(path=path)


def log_event(event_type: str, details: str) -> str:
    """Logs a major event in the execution history (DuckDB, current run).

    Use this to keep a trace of the execution instead of writing to a text file.

    Args:
        event_type: The type of event (e.g. 'init', 'gen', 'eval', 'fix', 'error').
        details: A description of the event.
    """
    from . import tools as _tools

    return _tools.log_event(event_type=event_type, details=details)


def visual_check(criterion_number: int, verdict: bool, observation: str) -> str:
    """Records your verdict for ONE visual success criterion of this task.

    Call this once per criterion (numbered from 1) when visual criteria are
    listed in the task. verdict must be an HONEST boolean based on what you
    actually verified.

    Args:
        criterion_number: The 1-based criterion number from the task.
        verdict: True only if the criterion is verified as met.
        observation: One sentence: what you checked and what you saw.
    """
    from . import tools as _tools

    return _tools.visual_check(
        criterion_number=criterion_number, verdict=verdict, observation=observation
    )


def check_run_state() -> str:
    """Returns the current execution state summary (iterations, status)."""
    from . import tools as _tools

    return _tools.check_run_state()


def load_skill(skill_name: str) -> str:
    """Loads the FULL content of a skill listed in the skills catalog.

    Use for skills marked (lazy) in the catalog. EAGER skills are already in
    your instructions — do NOT reload them.

    Args:
        skill_name: Exact skill name from the catalog (e.g. "frontend-design").
    """
    from .skill_loader_tool import load_skill as _load_skill

    return _load_skill(skill_name=skill_name)


def build_coder_custom_tools() -> list:
    """Liste des custom tools du profil Coder (wrappers ci-dessus)."""
    return [
        search_replace,
        multi_replace,
        append_file,
        check_js_syntax,
        read_python_skeleton,
        log_event,
        visual_check,
        check_run_state,
        load_skill,
    ]


# ============================================================
# Instructions (profil Coder — protocole tool-calls natifs)
# ============================================================

_PROTOCOL_BLOCK = """### PROTOCOL (native tool calls — MANDATORY)
1. ACT, do not narrate: every turn MUST call at least one tool. A turn without any tool call is a failed idle turn.
2. Call your tools DIRECTLY as tool calls with NAMED arguments (e.g. write_file(path="index.html", content="...")). Never write Python code to manipulate files (no open(), no os.) — only the tools.
3. COMPLETE CONTENT: each write_file carries the COMPLETE final content of the file (never elide, never placeholders like "TODO", "...", "// code here").
4. EDITING: to modify an existing file, PREFER search_replace / multi_replace (surgical) over rewriting the whole file. append_file is ONLY for the incremental strategy.
5. STALE-WRITE PROTECTION: read_file returns a content hash — after a recent read, you may pass expected_hash to write_file/edit_file to reject writes based on outdated content.
6. VERIFY BEFORE FINISHING: for any JavaScript deliverable, call check_js_syntax(path=...) and fix what it reports (a syntax error in one <script> block silently kills the whole page).
7. STEP-BY-STEP ANIMATION (visualizers/algorithms): ALWAYS use async/await with a sleep helper (const sleep = ms => new Promise(r => setTimeout(r, ms));). NEVER a synchronous while/for loop with un-awaited setTimeout.
8. STOP CONDITION: as soon as the target files are written and verified (at most 1 syntax/linter check without error), call the final_result tool IMMEDIATELY. Do not loop, do not re-read finished files."""

_FINAL_RESULT_BLOCK = """### FINAL ANSWER (structured output)
When done, call the `final_result` tool with ALL fields:
- task_id: "{task_id}"
- status: "success" or "failure" (failure = you could not complete the deliverable — be honest)
- details: short summary of files written and verifications performed
- linter_ok: true ONLY after a real syntax check (check_js_syntax / python skeleton) reported no error
- vision_ok: true ONLY if you visually verified the rendered UI through a tool (screenshot); otherwise false"""


def _strategy_block(strategy: str, sections: list, iteration: int) -> str:
    """Bloc workflow par stratégie — parité nodes.py, adapté au moteur pydantic.

    La vérification navigateur (navigate/console) vit dans le bloc LIVE
    VERIFICATION (F-160, injecté quand DevTools est connecté) ; ce bloc porte
    la vérification statique check_js_syntax commune aux deux moteurs.
    """
    if iteration > 1:
        return f"""### WORKFLOW — CORRECTION MODE (Iteration {iteration}, files ALREADY EXIST)
DO NOT RESTART FROM SCRATCH. Target files already exist from the previous iteration.
The current code of your files is injected in the task message — you do NOT need read_file to get it.
Bugs to fix are described in the Task Content ([LINTER] / [TESTER] / [JUDGE] tickets).

Proceed as follows:
1. Review the current code and the bug report.
2. Apply your fixes:
   - Isolated single-line change: use `search_replace(path=..., old_string=..., new_string=...)`.
   - Multiple scattered changes: use `multi_replace(path=..., replacements=[...])`.
   - Short file (< 150 lines) or major overhaul: rewrite the complete corrected file with `write_file`.
3. Verify every modified JS/HTML file with `check_js_syntax`.
4. Call final_result when all fixes are applied and verified."""
    if strategy == "incremental":
        sections_str = ", ".join(sections) if sections else "(sections to define)"
        return f"""### WORKFLOW (INCREMENTAL strategy)
Build this file in modular stages:
1. write_file(skeleton) ONCE: basic HTML structure with insertion markers (<!-- INSERT_CSS -->, <!-- INSERT_JS -->).
2. For EACH section ({sections_str}): append_file(content=section) at the proper spot.
3. Once all sections are injected, close cleanly (</body></html>).
4. check_js_syntax, then final_result."""
    if strategy == "multifile":
        return """### WORKFLOW (MULTIFILE strategy)
Build each target file modularly (1 logical module = 1 file).
⚠️ CRITICAL & MANDATORY: Each file is written with its COMPLETE content using write_file.
If a Drafter draft is provided, use it as your starting foundation and refine it.
1. Write each target file (`write_file(path=..., content=...)`) with complete, working code.
2. Ensure all UI components and event listeners are wired (buttons, sliders, stats display, async animation loop).
3. Verify with `check_js_syntax` on every JS-bearing file.
4. final_result when everything is complete and verified.
🚫 NEVER call append_file on a file created with write_file."""
    return """### WORKFLOW (SIMPLE strategy)
1. `write_file(path=..., content=...)` with the COMPLETE file content.
2. If a Drafter draft is provided: use its structure and enhance it with complete styles and wired event listeners.
3. Verify with `check_js_syntax`, then call final_result."""


def _skills_block_for(task: dict, browser_tools_available: bool) -> str:
    """Sélection des skills — miroir de nodes.py (F-57 : l'Architect décide,
    budget F-103, repli contextuel si rien de sélectionné).

    ``browser_tools_available`` (F-160) : le skill ``devtools-preview`` est
    pré-collé sur tâche web quand le MCP DevTools est connecté — parité
    smolagents exacte (le rituel navigate/console est alors réellement
    exécutable).
    """
    from .skills_loader import (
        ALWAYS_SKILLS_CODER,
        build_skills_block,
        enforce_skill_budget,
        load_skill_body,
    )

    architect_skills = list(task.get("skills", []) or [])
    if (
        browser_tools_available
        and architect_skills
        and _is_web_task(task)
        and "devtools-preview" not in architect_skills
    ):
        architect_skills = ["devtools-preview"] + architect_skills
    if architect_skills:
        architect_skills = enforce_skill_budget(
            selected_skills=architect_skills,
            budget_tokens=16000,
            always_skills=ALWAYS_SKILLS_CODER,
        )
        blocks: list = []
        for name in architect_skills:
            body = load_skill_body(name)
            if body:
                blocks.append(f"### SKILL: {name}\n{body}")
        if blocks:
            return (
                "Here are your SPECIALIZED SKILLS — follow their directives directly:\n\n"
                + "\n\n".join(blocks)
            )
    return build_skills_block(task.get("content", ""))


def _is_web_task(task: dict) -> bool:
    """Miroir de nodes.py._is_web_task (import direct impossible : circularité
    nodes → coder_pydantic → nodes)."""
    target_files = task.get("target_files") or []
    web_exts = (".html", ".htm", ".css", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte")
    if any(str(f).lower().endswith(web_exts) for f in target_files):
        return True
    content = (task.get("content") or "").lower()
    return any(
        kw in content
        for kw in ("html", "css", "javascript", " web ", "landing page", "frontend", "front-end")
    )


def _build_devtools_block(task: dict) -> str:
    """Bloc VISUAL VALIDATION du profil Coder pydantic (phase 3.5, F-160).

    Miroir de nodes.py._build_devtools_blocks, ADAPTÉ à la phase 3.5 : tant que
    la vision multimodale n'est pas migrée (3.6), take_screenshot ne retourne
    qu'une confirmation TEXTE — la vérification s'appuie donc sur la CONSOLE et
    les sondes DOM (discover_ui/fuzz/probe_*), pas sur l'inspection visuelle.
    Appelé uniquement quand les outils navigateur sont connectés
    (open_coder_mcp → browser_tools_available).
    """
    import os

    target_files = task.get("target_files") or ["index.html"]
    primary_target = target_files[0]
    primary_url = "file:///" + os.path.abspath(primary_target).replace("\\", "/")

    if not _is_web_task(task):
        return ""

    from .validation_criteria import build_visual_criteria_block

    visual_block = build_visual_criteria_block(task.get("visual_success_criteria") or [])
    if visual_block:
        criteria_note = (
            "\n7. VISUAL CRITERIA VALIDATION: confirm each criterion below through DOM probes "
            "(discover_ui / evaluate_script / probe_*), and record honest verdicts with "
            "visual_check(criterion_number=..., verdict=..., observation=...). A single NO = failure -> fix."
        )
    else:
        criteria_note = (
            "\n7. final_result only when: 1) the page loads with 0 console errors, "
            "2) interactive controls are wired (fuzz proves it)."
        )

    return f"""### 🖥️ LIVE VERIFICATION (Chrome DevTools — verify BEFORE final_result)
You have a controllable Chrome browser to VERIFY your page through REAL execution.

⚠️ CRITICAL TRAP: a page with good-looking CSS may have BROKEN JavaScript silently
(dead buttons, unhandled events). Only the console and live interactions reveal this.
NOTE: take_screenshot returns a text confirmation only (image input arrives phase 3.6) —
base your verdicts on console + DOM probes, not on visual inspection.

Verification Workflow (perform AFTER creating files, BEFORE final_result):
1. `navigate_page(url="{primary_url}")` — opens your page in Chrome (exact URL below).
2. `list_console_messages()` — MANDATORY: 0 JS errors required (SyntaxError, undefined, Uncaught).
3. `discover_ui()` — learn the REAL DOM ids/dimensions; never guess a selector.
4. UI FUZZING: `fuzz_click_all_buttons()` then `fuzz_keyboard_controls()`, then re-check `list_console_messages()`.
5. If errors occur: FIX via `search_replace` (never rewrite the whole file), then re-test (navigate, console, fuzz).
6. ANIMATED/ALGORITHM PAGE: a static snapshot proves nothing — for sorting bars call
   `probe_sort_state()` (waits for the REAL completed-sort verdict); for canvas games call
   `probe_canvas_activity()` and require ANIMATING status; `instrument_calls()` / `dump_function_source()`
   diagnose a live-but-frozen engine.
⚠️ If `navigate_page` TIMEOUTS on your LOCAL page: the JS thread is frozen (infinite loop). Check your while loops.
{criteria_note}

Exact page URL (primary target): {primary_url}
{visual_block}"""


def build_coder_instructions(task: dict, browser_tools_available: bool = True,
                             context7_available: bool = False) -> str:
    """Instructions système du profil Coder (partie STABLE du prompt).

    Rôle + invariants + protocole + stratégie + fichiers cibles + skills +
    directives AGENTS.md locales. Le contenu de la tâche (variable) part dans
    le user prompt (build_coder_user_prompt) — découpage system/user
    cache-friendly pour --cache-reuse llama-server.

    ``browser_tools_available`` (F-160) : True quand le MCP DevTools est
    connecté (open_coder_mcp) → bloc LIVE VERIFICATION + skill devtools-preview
    pré-collé sur tâche web. ``context7_available`` : True quand le MCP Context7
    est connecté → ligne d'orientation anti-hallucination d'API.
    """
    from .prompts import ROLE_BLOCKS, build_role_header

    parts = [build_role_header("coder"), _PROTOCOL_BLOCK]

    strategy = task.get("strategy", "simple")
    sections = task.get("sections", []) or []
    iteration = int(task.get("iteration", 1) or 1)
    parts.append(_strategy_block(strategy, sections, iteration))

    if task.get("target_files"):
        files_list = "\n".join([f"- {f}" for f in task["target_files"]])
        parts.append(
            "### ⚠️ TARGET FILES — YOU MUST CREATE THESE FILES (highest priority)\n"
            f"{files_list}\n\n"
            "- 📍 YOUR CURRENT WORKING DIRECTORY IS THE RUN DIRECTORY: use relative paths "
            "(`index.html`, NOT `runs/...`, NOT absolute).\n"
            "- write_file automatically creates parent directories if needed.\n"
            "- 🚀 QUICK JS VALIDATION: verify every generated/modified JavaScript file with "
            "`check_js_syntax(path=...)` before final_result."
        )

    if browser_tools_available:
        devtools_block = _build_devtools_block(task)
        if devtools_block:
            parts.append(devtools_block)

    parts.append(_FINAL_RESULT_BLOCK.format(task_id=task.get("id", "")))

    tools_lines = [
        "### AVAILABLE TOOLS\n"
        "- File tools: `read_file` (line numbers + hash), `write_file` (complete file, "
        "expected_hash), `edit_file` (exact unique replacement), `append_file` (end of file), "
        "`list_directory`, `search_files` (regex), `find_files` (glob), `create_directory`, `file_info`.\n"
        "- Surgical edits: `search_replace` / `multi_replace` (tolerant matching) — PREFERRED over "
        "full rewrite for existing files.\n"
        "- Verification: `check_js_syntax` (node --check + CSS vars), `read_python_skeleton`.\n"
        "- Trace: `log_event` (DuckDB), `check_run_state`.\n"
        "- Task-specific: `visual_check` (per visual criterion), `load_skill` (lazy skills)."
    ]
    if browser_tools_available:
        tools_lines.append(
            "- Browser (Chrome DevTools MCP): `navigate_page`, `list_console_messages`, "
            "`evaluate_script`, `take_screenshot`, `click`, `fill`, plus DOM probes "
            "(`discover_ui`, `fuzz_click_all_buttons`, `fuzz_keyboard_controls`, "
            "`probe_canvas_activity`, `probe_sort_state`, `expose_game_state`, "
            "`instrument_calls`, `dump_function_source`, `force_advance`, `heal_selector`, "
            "`clean_dom`)."
        )
    if context7_available:
        tools_lines.append(
            "- Library docs (Context7 MCP): `resolve_library_id` / `query_docs` — ONLY for "
            "external libraries (React, Chart.js...). NEVER for vanilla HTML/JS/CSS."
        )
    parts.append("\n".join(tools_lines))

    skills = _skills_block_for(task, browser_tools_available)
    if skills:
        parts.append(skills)

    local_agents_md_block = _local_agents_md_block(task)
    if local_agents_md_block:
        parts.append(local_agents_md_block)

    return "\n\n".join(p for p in parts if p)


def _local_agents_md_block(task: dict) -> str:
    """AGENTS.md local au composant (F-59) — miroir de nodes.py."""
    target_dir = os.path.dirname((task.get("target_files") or ["."])[0]) or "."
    agents_md_path = os.path.join(target_dir, "AGENTS.md")
    if not os.path.exists(agents_md_path):
        return ""
    try:
        workspace_root = os.path.realpath(os.getcwd())
        resolved = os.path.realpath(agents_md_path)
        if os.path.exists(resolved) and (
            resolved == workspace_root or resolved.startswith(workspace_root + os.sep)
        ):
            with open(resolved, "r", encoding="utf-8") as f:
                return (
                    "\n### COMPONENT-SPECIFIC DIRECTIVES (AGENTS.md)\n"
                    + f.read()
                    + "\n"
                )
    except Exception:
        pass
    return ""


def build_coder_user_prompt(task: dict) -> str:
    """User prompt (partie VARIABLE) : fichiers courants + contenu tâche + draft
    + contexte global + leçons. Miroir de la moitié basse du prompt nodes.py."""
    iteration = int(task.get("iteration", 1) or 1)

    current_files_block = ""
    if iteration > 1 and task.get("target_files"):
        snippets = []
        for tf in task["target_files"]:
            if os.path.isfile(tf):
                try:
                    with open(tf, "r", encoding="utf-8") as f:
                        snippets.append(f"--- File `{tf}` ---\n```\n{f.read()}\n```")
                except Exception:
                    pass
        if snippets:
            current_files_block = (
                "### 📂 CURRENT CODE OF TARGET FILES (ALREADY IN CONTEXT — NO read_file NEEDED)\n"
                "The code below is the exact state on disk from the previous iteration. "
                "Proceed DIRECTLY to modifications:\n\n"
                + "\n\n".join(snippets)
                + "\n\n"
            )

    parts = [
        current_files_block,
        f"{task.get('plan_anchor', '')}### Contenu de la tâche\n{task['content']}",
    ]
    if task.get("draft_instruction"):
        parts.append(task["draft_instruction"])
    if task.get("original_content"):
        parts.append(
            f"### Contexte global (Rappel du cahier des charges initial)\n{task['original_content']}"
        )
    if task.get("lessons"):
        parts.append(task["lessons"])
    parts.append(
        "### RAPPEL (récence)\n"
        "- AGIS via des tool calls, ne raconte pas.\n"
        "- AUCUN placeholder : contenu COMPLET à chaque write_file.\n"
        "- Un livrable JS non vérifié par check_js_syntax n'est pas terminé.\n"
        "- Dès que les fichiers cibles sont écrits et vérifiés : final_result IMMÉDIAT."
    )
    return "\n\n".join(p for p in parts if p)


# ============================================================
# Assemblage de l'Agent (testable 0-LLM : construire ≠ exécuter)
# ============================================================

def build_coder_capabilities(task: dict, settings, guards: bool = True,
                              extra_capabilities: Optional[list] = None,
                              on_reminder_fired=None) -> list:
    """Liste ordonnée des capabilities du profil Coder (testable sans exécution).

    Ordre : ``extra_capabilities`` EN TÊTE (wrap hooks : premier enregistré =
    plus externe — ReviveRetry enveloppe les requêtes modèle au-delà des
    reminders), puis FileSystem/ToolOutputLimits (production 3.1), puis selon
    ``guards`` : soit l'arsenal F-159 (compaction + gardes + reminders), soit
    le comportement F-158 exact (ClearToolResults standalone, A/B 3.1-3.2).
    """
    from pydantic_ai_harness import ClearToolResults, FileSystem, ToolOutputLimits

    capabilities: list = list(extra_capabilities or [])
    capabilities.append(FileSystem(root_dir="."))
    capabilities.append(ToolOutputLimits())
    if guards:
        from .coder_pydantic_guards import (
            CoderGuardState,
            as_capabilities,
            build_compaction_capabilities,
            build_guard_reminders,
        )

        state = CoderGuardState()
        capabilities.extend(build_compaction_capabilities(settings))
        capabilities.extend(as_capabilities(state, task, settings))
        capabilities.append(
            build_guard_reminders(state, task, settings, on_fire=on_reminder_fired)
        )
    else:
        capabilities.append(ClearToolResults(max_fraction=0.7))
    return capabilities


def build_coder_agent(model, task: dict, settings, coder_max_tokens: int,
                      browser_tools_available: bool = True, guards: bool = True,
                      extra_capabilities: Optional[list] = None,
                      on_reminder_fired=None, toolsets: Optional[list] = None,
                      context7_available: bool = False):
    """Assemble l'Agent pydantic du profil Coder autour du modèle fourni.

    Séparé de run_coder_pydantic pour être testable sans GPU (construction
    seule, aucun appel réseau) et réutilisable par le profil Tester (3.7) —
    c'est le « socle commun » du plan : seule la liste tools/instructions/
    output_type change d'un profil à l'autre. Voir build_coder_capabilities
    pour la sémantique de ``guards`` / ``extra_capabilities``. ``toolsets``
    (F-160) : toolsets MCP ouverts (chrome-devtools + helpers + context7) —
    leur lifecycle est porté par l'appelant (open_coder_mcp).
    """
    from pydantic_ai import Agent, ModelSettings

    capabilities = build_coder_capabilities(
        task,
        settings,
        guards=guards,
        extra_capabilities=extra_capabilities,
        on_reminder_fired=on_reminder_fired,
    )

    model_settings = ModelSettings(
        temperature=settings.coder_temperature,
        max_tokens=coder_max_tokens,
        timeout=settings.llm_timeout_s,
    )
    if toolsets:
        # F-160 : pydantic-ai force tool_choice='required' par défaut sur les
        # runs à output outil — llama-server encode ce forçage en GRAMMAIRE
        # GBNF d'union des tools, qui casse au-delà de ~45-60 outils (mesuré :
        # 45 outils OK, 62 → 400 « failed to parse grammar » ; les MCP portent
        # le Coder à 62). 'auto' supprime la grammaire contrainte sans changer
        # le protocole tool-calls ; le forçage comportemental reste porté par
        # le PROTOCOL block + IdleBreaker (F-159).
        model_settings["tool_choice"] = "auto"

    return Agent(
        model,
        instructions=build_coder_instructions(
            task, browser_tools_available, context7_available=context7_available
        ),
        capabilities=capabilities,
        tools=build_coder_custom_tools(),
        toolsets=list(toolsets) if toolsets else [],
        output_type=CoderOutput,
        # Retries niveau output-validation (pydantic-ai couche 4) ≡
        # worker_max_retries du chemin smolagents.
        retries=settings.worker_max_retries,
        model_settings=model_settings,
    )


# ============================================================
# Exécution du nœud (contrat identique à execute_coder_node smolagents)
# ============================================================

async def run_coder_pydantic(
    task: dict, settings
) -> Tuple[Optional[CoderOutput], Optional[NodeMetrics]]:
    """Exécute le Coder sur pydantic-ai-harness. Retour (CoderOutput|None, NodeMetrics|None).

    Contrat identique au chemin smolagents (run_with_retry) : sortie validée ou
    None (échec propre — le graphe continue vers Linter/Static Tester).
    Les retries de sortie (validation CoderOutput) sont natifs pydantic-ai
    (Agent.retries) ; les gardes 3.3-3.4 (F-159) : ReviveRetry enveloppe chaque
    requête (revive llama-server au passage), GuardAbort (boucle stérile, idle)
    → échec propre distinct d'un crash.
    """
    from pydantic_ai.models.openai import OpenAIChatModel, OpenAIModelProfile
    from pydantic_ai.providers.openai import OpenAIProvider
    from pydantic_ai.usage import UsageLimits

    from .llama_server import model_lifecycle
    from .nodes import _select_coder_spec  # import tardif : anti-circularité

    # Resets d'état des outils partagés (même lifecycle que le chemin smolagents —
    # les fonctions tools.py portent leurs propres registres : plafond de lectures
    # identiques F-141, preuve d'écriture durable, audit visuel).
    from .tools import reset_read_supply, reset_visual_audit, reset_write_proof

    reset_read_supply()
    reset_write_proof()
    reset_visual_audit()

    from .coder_pydantic_guards import GuardAbort

    coder_spec, coder_max_tokens, is_ultra = _select_coder_spec(task, settings)
    if is_ultra:
        print(
            f"[⚡] CODER ULTRA (pydantic, itération {task.get('iteration', 1)}) : "
            f"{os.path.basename(coder_spec.model or '?')} (gros modèle no-think)."
        )

    user_prompt = build_coder_user_prompt(task)
    node_label = f"coder[{task.get('id', '?')}]"

    t0 = time.time()
    with model_lifecycle(coder_spec) as srv:
        if not srv.api_base:
            print("[-] Coder (pydantic) : échec du spawn llama-server — échec propre.")
            return None, None

        # Profil OpenAI-compat llama-server (spike F-157 : les flags sont
        # conservés par prudence bien que le défaut passe les 4 smoke tests).
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
            """Reconstruit le modèle après un revive sur un NOUVEAU port."""
            return OpenAIChatModel(
                srv.model_id,
                provider=OpenAIProvider(base_url=api_base, api_key=srv.api_key),
                profile=profile,
            )

        # F-159 ReviveRetry (F-104) : policy maison + revive llama-server.
        revive_cap = None
        if settings.llm_retry_enabled:
            from .coder_pydantic_guards import ReviveRetryCapability
            from .llm_retry import RetryPolicy

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

        # F-160 (phase 3.5) : MCP navigateur (chrome-devtools + helpers DOM) et
        # doc (Context7) — dégradation gracieuse par serveur ; les toolsets
        # restent ouverts pendant TOUT le run (open_coder_mcp = miroir des
        # context managers smolagents F-45/F-17).
        from .coder_pydantic_mcp import open_coder_mcp

        async with open_coder_mcp(settings) as mcp:
            agent = build_coder_agent(
                model,
                task,
                settings,
                coder_max_tokens,
                browser_tools_available=mcp.browser_tools_available,
                guards=settings.coder_pydantic_guards,
                extra_capabilities=[revive_cap] if revive_cap is not None else None,
                toolsets=mcp.toolsets,
                context7_available=mcp.context7_available,
            )
            print(f"[*] Coder (pydantic) — llama-server prêt : {srv.api_base}")
            try:
                result = await agent.run(
                    user_prompt,
                    usage_limits=UsageLimits(
                        request_limit=settings.coder_max_steps,
                        tool_calls_limit=settings.coder_max_steps * 3,
                    ),
                )
            except GuardAbort as exc:
                duration = time.time() - t0
                print(f"[-] Coder (pydantic) GARDÉ-ABORT propre ({exc})")
                return None, NodeMetrics(
                    node=node_label,
                    model=str(coder_spec.model or ""),
                    duration_s=duration,
                    input_tokens=None,
                    output_tokens=None,
                )
            except Exception as exc:  # noqa: BLE001 — échec propre, le graphe continue
                duration = time.time() - t0
                print(f"[-] Coder (pydantic) ÉCHEC ({type(exc).__name__}: {exc})")
                return None, NodeMetrics(
                    node=node_label,
                    model=str(coder_spec.model or ""),
                    duration_s=duration,
                    input_tokens=None,
                    output_tokens=None,
                )

        usage = result.usage  # propriété (piège v2.33 : pas une méthode)
        duration = time.time() - t0
        metrics = NodeMetrics(
            node=node_label,
            model=str(coder_spec.model or ""),
            duration_s=duration,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
        )
        output = result.output
        if isinstance(output, CoderOutput):
            print(
                f"[+] Coder (pydantic) : status={output.status} "
                f"({metrics.input_tokens or 0} in / {metrics.output_tokens or 0} out, "
                f"{duration:.1f}s)"
            )
        return output, metrics
