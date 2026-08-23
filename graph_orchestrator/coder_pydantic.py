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

Hors périmètre (phases suivantes du plan) : MCP DevTools/Context7 + vision
multimodale (3.5/3.6 → le protocole n'annonce PAS navigate_page/screenshot),
gardes LoopGuard/Stall/Goal + SystemReminders (3.3), TieredCompaction (3.4).
Le graphe continue de fonctionner : la validation aval (Static Tester → Tester
LLM → Judge) reste l'arbitre de la qualité du livrable.

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

    Différence assumée vs smolagents : pas encore d'outils navigateur (phase
    3.5/3.6) → l'étape de vérification s'appuie sur check_js_syntax au lieu
    de navigate_page + list_console_messages.
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

    Écart moteur pydantic 3.1-3.2 : ``devtools-preview`` (rituel visuel
    navigate_page/screenshot) n'est PAS garanti sur tâche web tant que le MCP
    DevTools n'est pas migré (phase 3.5/3.6) — un skill qui documente des
    outils absents induit le modèle en erreur. Le skill reste honoré s'il a
    été EXPLICITEMENT sélectionné par l'Architect (contenu utile pour la
    phase d'après), seul le pré-scotchage automatique est suspendu.
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


def build_coder_instructions(task: dict, browser_tools_available: bool = True) -> str:
    """Instructions système du profil Coder (partie STABLE du prompt).

    Rôle + invariants + protocole + stratégie + fichiers cibles + skills +
    directives AGENTS.md locales. Le contenu de la tâche (variable) part dans
    le user prompt (build_coder_user_prompt) — découpage system/user
    cache-friendly pour --cache-reuse llama-server.

    ``browser_tools_available`` : False tant que le MCP DevTools n'est pas
    migré (phase 3.5/3.6) — suspend le pré-scotchage du skill devtools-preview
    et adapte les étapes de vérification (check_js_syntax au lieu de la
    console navigateur).
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

    parts.append(_FINAL_RESULT_BLOCK.format(task_id=task.get("id", "")))

    parts.append(
        "### AVAILABLE TOOLS\n"
        "- File tools: `read_file` (line numbers + hash), `write_file` (complete file, "
        "expected_hash), `edit_file` (exact unique replacement), `append_file` (end of file), "
        "`list_directory`, `search_files` (regex), `find_files` (glob), `create_directory`, `file_info`.\n"
        "- Surgical edits: `search_replace` / `multi_replace` (tolerant matching) — PREFERRED over "
        "full rewrite for existing files.\n"
        "- Verification: `check_js_syntax` (node --check + CSS vars), `read_python_skeleton`.\n"
        "- Trace: `log_event` (DuckDB), `check_run_state`.\n"
        "- Task-specific: `visual_check` (per visual criterion), `load_skill` (lazy skills)."
    )

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

def build_coder_agent(model, task: dict, settings, coder_max_tokens: int,
                      browser_tools_available: bool = True):
    """Assemble l'Agent pydantic du profil Coder autour du modèle fourni.

    Séparé de run_coder_pydantic pour être testable sans GPU (construction
    seule, aucun appel réseau) et réutilisable par le profil Tester (3.7) —
    c'est le « socle commun » du plan : seule la liste tools/instructions/
    output_type change d'un profil à l'autre.
    """
    from pydantic_ai import Agent, ModelSettings
    from pydantic_ai_harness import ClearToolResults, FileSystem, ToolOutputLimits

    return Agent(
        model,
        instructions=build_coder_instructions(task, browser_tools_available),
        capabilities=[
            FileSystem(root_dir="."),
            ToolOutputLimits(),
            ClearToolResults(max_fraction=0.7),
        ],
        tools=build_coder_custom_tools(),
        output_type=CoderOutput,
        # Retries niveau output-validation (pydantic-ai couche 4) ≡
        # worker_max_retries du chemin smolagents.
        retries=settings.worker_max_retries,
        model_settings=ModelSettings(
            temperature=settings.coder_temperature,
            max_tokens=coder_max_tokens,
            timeout=settings.llm_timeout_s,
        ),
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
    (Agent.retries) ; les gardes comportementales (LoopGuard/Goal…) arrivent en
    phase 3.3 — la validation aval du graphe reste l'arbitre.
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
        # Phase 3.1-3.2 : pas de MCP navigateur → devtools-preview non collé,
        # vérification par check_js_syntax (flip à True en phase 3.5/3.6).
        agent = build_coder_agent(
            model, task, settings, coder_max_tokens, browser_tools_available=False
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
