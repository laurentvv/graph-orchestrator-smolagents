<div align="center">
  <img src="docs/orchestrator_banner.jpg" alt="Autonomous AI Agent Team Graph Orchestrator" width="100%" />
  
  <h1>Graph Orchestrator with DSPy & smolagents</h1>
  <p><strong>A production-ready Hybrid Multi-Agent Architecture for Software Engineering and Data Processing</strong></p>
  
  [![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
  [![DSPy](https://img.shields.io/badge/DSPy-3.0_enabled-purple.svg)](https://dspy.ai/)
  [![Smolagents](https://img.shields.io/badge/smolagents-enabled-orange.svg)](https://github.com/huggingface/smolagents)
  [![DuckDB](https://img.shields.io/badge/DuckDB-enabled-yellow.svg)](https://duckdb.org/)
</div>

---

This repository implements a highly advanced **Hybrid Graph Engineering** architecture for AI agents. It leverages the mathematical rigor of **DSPy 3.0** (for declarative reasoning and structural JSON generation) and the pragmatic execution engine of **smolagents** (for tool-calling and sandboxed environment interaction).

Moving away from fragile, linear AI execution loops, this orchestrator embraces a **distributed, parallel, and verifiable** model with distinct roles: **The Brains** (DSPy) and **The Hands** (smolagents).

> 📖 **Architecture Manifesto:** See [DOC_DSPY_ARCHITECTURE.md](DOC_DSPY_ARCHITECTURE.md) for a deep dive into the DSPy migration, Signatures, and ChainOfThought implementations.

## 🌟 Key Features & Hybrid Architecture

### 1. "Brains vs Hands" Topology
- **The Brains (DSPy 3.0)**: Cognitive nodes (Router, Architect, Security Reviewer, Code Judge) use DSPy `Signatures` and `ChainOfThought` to strictly map open-ended reasoning into guaranteed `Pydantic` JSON schemas. No more fragile manual prompting or regex hacking. All nodes share a **universal invariants** foundation (`prompts.py`): 10 cross-cutting patterns distilled from an audit of ~12 production coding-agent prompts (read-before-write, no whole-file rewrite, verify-after, never-assume-library, approval gating, anti-loop, concision, parallel tool calls, professional objectivity, defensive security) — injected into every DSPy Signature (`__doc__`) and every smolagents prompt (`build_role_header`). Each node also carries a **specialized role** (Coder→type-hints/verify-after, Architect→read-only/5-axes, Judge→in-diff-only/anti-nits, Security→OWASP/CVSS, Tester→pyramid-70/20/10/AAA) inspired by the open-source prompts catalogued in the references audit.
- **The Hands (smolagents)**: Execution nodes (Fan-out Coders, Testers) take the deterministic JSON orders from the Brains and execute them in reality using local tool collections (Chrome DevTools MCP, bash commands, file system access). The `bash_command` tool runs behind a **destructive-command guard** (`bash_guard.py`) that blocks system-wiping commands (`rm -rf /`, `format`, `mkfs`, `dd of=/dev/sd*`, `shutdown`, `git push --force`, `curl | sh`…) before `shell=True` execution, returning a pedagogical message instead — a first layer of runtime robustness (the full Docker sandbox remains a separate workstream). Opt-out via `BASH_GUARD_ENABLED=false`.

### 2. The Coding Playbook (Autonomous Engineering Team)
Instead of letting a single agent write and evaluate its own code, this system simulates an entire engineering team:
- **PromptRefiner Node (meta-prompt, before the Architect)**: a DSPy reasoning node (gemma, `ChainOfThought`) that rewrites the raw user prompt into a **structured spec** (Goal / Expected features / Technical constraints / Validation criteria in Given/When/When when relevant) *before* it reaches the Router and Architect. Inspired by the "Enhance Prompt" pattern of Kilo Code / Cline / Roo Code. It knows the catalog of available capabilities (skills + Context7 status + testers) to orient the spec toward what's actually buildable, detects vague terms (`fast`, `user-friendly`...), and structures without inventing scope. The refined prompt is persisted in the checkpoint (LLM skipped on resume). Opt-out via `PROMPT_REFINER_ENABLED`; degrades gracefully to the raw prompt if the LLM is down.
- **DSPy Architect Node**: A heavy reasoning model that takes a complex prompt, designs the global architecture, and breaks it down into granular JSON subtasks using strict Pydantic constraints. It also emits a **build strategy per subtask** (`simple` | `incremental` | `multifile`) telling the Coder *how* to construct the files — not just *what* to build.
- **Fan-out Coder Nodes (smolagents `CodeAgent`)**: For each subtask, a Coder agent is spawned asynchronously to write code by generating **Python that calls tools** (`write_file(path=..., content=...)`). CodeAgent was chosen over ToolCallingAgent after empirical comparison: small local models (gemma) reliably generate Python but fail to emit valid JSON tool-calls. A **guard software** detects idle steps (model reasons without acting), broken code blocks (unclosed strings), and **empty HTML skeletons** (preventing small models from failing at incremental generation), re-injecting targeted correction messages. A **cryptographic anti-loop** (SHA-256 fingerprint of `tool + arguments`) trips a circuit-breaker when the Coder repeats the *exact same* tool call N times in a row — stopping token hemorrhage from "spinning in circles" failures. Configurable via `LOOP_GUARD_ENABLED` / `LOOP_GUARD_THRESHOLD`. An **Orphan Repair** layer (`orphan_repair.py`) additionally guards the conversation history: if a `tool_use` call has no matching `tool_result` (e.g. the agent was interrupted mid-tool-call and the memory was restored from a checkpoint), it injects a fake `{"status": "error", "error": "Interrompu"}` response **before** the agent runs, so the asymmetric tool-call pair never crashes the LLM API on replay. Both the generic "messages" form and the smolagents `memory.steps` form are handled; the integration is defensive (never blocks the main flow). A **Sanitizer** layer (`sanitizer.py`) automatically **auto-types** tool arguments: small models often emit malformed values (`offset="1, 80"` → coerced to `80`, `replace_all="true"` → `True`, JSON strings for `array`/`object` fields), which otherwise trigger wasted retries on Pydantic type-validation errors. It coerces *best-effort* against the real `tool.inputs` schema (never LLM inference) and leaves non-coercible values untouched so smolagents validation remains the final arbiter. Deterministic, 0-LLM. Configurable via `SANITIZER_ENABLED` (default on). An **Idempotence** layer (`idempotency.py`) guarantees that non-idempotent side effects (`append_file`, `pip install`) are applied **exactly once per run** — even after a checkpoint replay (crash recovery). Backed by DuckDB (survives a new process), with a 14-day retention and lazy pruning; a failed operation is not marked done (retryable). `write_file` is intentionally NOT wrapped (idempotent by overwrite by design); `bash_command` is covered by the guard + anti-loop instead. Opt-out via `IDEMPOTENCE_ENABLED`.
- **Linter Node (Shift Left, deterministic)**: Right after the Coder, a **0-LLM gatekeeper** validates syntax (`tree-sitter` for Python/HTML/CSS/JS/TS/TSX + `py_compile` for Python indentation + HTML structural checks like *content after `</html>`*). On invalid syntax it **short-circuits the expensive Tester** and loops back to the Coder with the error — a syntax typo should never waste a full LLM cycle.
- **Static Tester Node (deterministic web gatekeeper)**: A second 0-LLM gatekeeper (web-only) that validates **web semantics** the Linter cannot reach (it skips inline `<script>` JS — `tree-sitter-html` parses it as text). Three tiers in fail-fast order: **Tier 1** (`node --check` on the extracted JS catches TypeScript-in-vanilla = the #1 Coder bug = blank page; `addEventListener` wiring check catches an interactive control present but not connected — the slider-not-wired trap that a screenshot *cannot* detect); **Tier 2** (Chrome DevTools `getBoundingClientRect().height` after clicking the primary action — catches elements created in JS but rendered invisible by a CSS `height:%` on a heightless parent, the exact bug the LLM missed by confirmation bias). Implements the proven 7-step methodology from `debug/MANUAL_TESTER_METHODOLOGY.md`. Catches ~80% of web bugs in <6s vs the LLM Tester's 25 min. Graceful degradation: if `node` or Chrome is absent the affected tier skips silently (the LLM Tester takes over); opt-out via `STATIC_TESTER_ENABLED=0` / `STATIC_TESTER_DEVTOOLS=0`.
- **Parallel Validation**: 
  - *Tester Node (smolagents, **polyvalent**)*: Detects the target technology (web → **Puppeteer MCP** for browser testing; Python → **`pytest` subprocess** with deterministic pass/fail + captured stderr) and routes to the matching runner. Captured output is **truncated** (head + tail) before feedback to protect the LLM context window from "Context Overflow".
    - **Auto-dependency resolution**: the Python tester detects `ModuleNotFoundError` in the captured stderr and **installs the missing package itself** (`pip install`, non-persistent — does *not* touch `pyproject.toml`/`uv.lock`) before re-running the tests, rather than wasting an LLM cycle on what is merely an absent dependency. Capped at 1 retry (anti-loop), module name validated against an identifier regex (defense-in-depth against command injection). Opt-out via `AUTO_INSTALL_DEPS=false`.
    - **Functional logic testing (not just crash detection)**: the web tester writes **assertion scripts** via `puppeteer_evaluate` to verify the *behavior* the app claims to deliver (e.g. "is the array sorted after clicking Start?"), not only that the page renders without JS errors. The full requirements (cahier des charges) are propagated to the tester so it knows what to verify. Iterate on the tester in isolation with `uv run python run_tester.py [file.html] [task description]`.
    - **Anti-loop hardening (F-45)**: the web tester is protected against its two observed failure modes. (1) A **capped step budget** (`TESTER_MAX_STEPS`, default 12 — the verdict is clear by step 10-12; the old hard-coded 24 let the model burn ~30 min looping). (2) A **contextual idle guard** (`node_kind="tester"`): if a turn emits reasoning without a tool call (the `does not contain any JSON blob` failure mode), a Puppeteer-specific remediation is re-injected (`puppeteer_*`/`final_answer`, not `write_file`), plus a `LoopGuard` catches the exact repetition of the same `puppeteer_evaluate` script.
    - **querySelector hygiene (F-45)**: the web-tester skill carries an explicit directive against the #1 observed friction — writing `document.querySelector='...'` (assignment, which **overwrites the native function** in the page context) instead of `document.querySelector('...')` (call). The directive teaches "store the *result* in a `const`, never reassign a native method" and offers `getElementById`/`getElementsByTagName` fallbacks, plus a `DOMContentLoaded` guard before the first assertion (avoids false failures on pages that populate their DOM in a load handler).
    - **DOM cleanup before LLM feedback**: before analyzing or quoting the captured HTML, the tester strips noisy tags (`<script>`, `<style>`, `<svg>`, `<canvas>`, `<iframe>`, `<head>`, comments) — reducing page size by ~3× on realistic markup without losing the semantic content (text, `id`, `class`, `aria-*`) needed for functional assertions. The cleanup runs browser-side via an injected JS snippet (no Python round-trip), backed by the `dom_filter.clean_dom_for_llm` utility.
  - *Security Reviewer (DSPy)*: Audits the code against vulnerabilities (OWASP Top 10: XSS, injections, broken auth, data exposure…) and returns a typed list of flaws, now with **CVSS-anchored severity** (`findings`: critical/high/medium/low + location + suggestion). Defensive-only posture (refuses malicious code, never logs secrets).
- **DSPy Judge Node**: Acts as the ultimate PR reviewer. Analyzes tester/security reports, outputting a deterministic `approved: bool` verdict to either merge the code or trigger a feedback loop. Enforces a **severity rubric** (`findings`: critical/high/medium/low), **in-diff-only** anchoring (judges the changed code, not the whole file) and **anti-nits** (no rejection for pure style) — "professional objectivity" (truth over validation). A single `low` finding never justifies a rejection.
- **Thinking mode, selective (F-47)**: Gemma 4's built-in *thinking* (step-by-step reasoning) is **forced on Ollama's `/v1` endpoint** and not disable there (Ollama 0.32.5, latest). All DSPy nodes therefore talk Ollama's **native `/api/chat`** via the litellm `ollama/` provider (instead of `openai/` → `/v1`), which honors the `think` parameter. Thinking is **disabled by default** (`think=False`) for Router/PromptRefiner/Security/Judge/Escalation — these are classification/verdict tasks where the rubric is in the prompt and the thinking only burns the generation budget without emitting the verdict (caused Judge hangs of ~23 min before the fix). The **Architect alone keeps thinking on** (`think=True`) — step-by-step reasoning genuinely helps the decomposition/strategy (simple/incremental/multifile). Validated: `think=False` answers in ~6 s vs ~23 min. See `debug/GAPS_TESTER_JUDGE.md`.
- **Escalation Node (automatic post-mortem)**: When a subtask exhausts the circuit breaker (3 rejected iterations), an `EscalationSignature` DSPy node synthesizes the accumulated refutations from the Knowledge Graph into a **structured post-mortem** (root cause + lesson + severity). The diagnosis is persisted in the KG (`kind="escalation"`) and linked to the refutations it summarizes via `ESCALATES` edges — queryable by future runs to avoid repeating the same dead-ends. Controlled by `ESCALATION_ENABLED` (default on; degrades gracefully to the legacy `max_iterations_reached` status if disabled or if the reasoning endpoint is down).
- **Context7 (up-to-date library docs)**: The Coder, Architect, and web-Tester are wired to **Context7** (`@upstash/context7-mcp`) to fetch **current library/framework documentation** — the antidote to API hallucination. Rather than relying on stale memorized APIs, agents consult official docs on demand. Controlled by the `context7-research` skill: it triggers **only for external libs** (React, Chart.js, pandas…) and **stays dormant on vanilla JS/CSS or algorithmic tasks** to avoid wasting steps. Requires `CONTEXT7_API_KEY` (degrades gracefully without it — all nodes run unchanged).
- **Chrome DevTools MCP (visual self-validation)**: The Coder and web-Tester are wired to **`chrome-devtools-mcp`** (`npx chrome-devtools-mcp@latest`, stdio) to pilot a live Chrome instance — navigate the generated HTML page, take a screenshot, read the JS console, click/fill to test interactions. The screenshot is **returned as an image to the model** (the fast model `gemma-4-E4B` is multimodal — verified at runtime), so the Coder can **spot visual bugs (broken layout, blank page, overlapping elements) and fix them *before* `final_answer`**, instead of sending a visually broken page to the Tester. A dedicated **`vision_callback`** (`step_callback` smolagents) pushes the captured screenshot into `observations_images` — necessary because smolagents v1.26.0 does not automatically expose MCP tool images to the LLM otherwise. On the web-Tester, Chrome DevTools **complements Puppeteer** (kept for its dedicated assertion skill) by adding structured console messages (`list_console_messages` with source maps), accessibility-tree snapshots (`take_snapshot`), and Lighthouse audits. Controlled by `CHROME_DEVTOOLS_ENABLED` (degrades gracefully — all nodes run without visual preview if disabled, exactly as before F-45); `CHROME_PATH` and `CHROME_DEVTOOLS_HEADLESS` tune the Chrome binary and headless mode.

### 3. Persistent Knowledge Graph (DuckDB)
Context windows are limited. Instead of passing massive conversation histories between the agents, **all agents read and write to a shared, persistent DuckDB Knowledge Graph**.
- Tracks entities, observations, refutations, and typed edges (`REFUTES`, `SUPPORTS`).
- Absolute provenance: every claim knows which agent, model, and run produced it.
- **Agentic SQL Querying**: Agents are equipped with a `query_duckdb_knowledge_graph` tool to actively query historical bugs across past projects to avoid repeating mistakes.

### 4. Smart Model Tiering
Save costs and boost speed by dynamically routing tasks to the right brain:
- **Fast Model** (`FAST_MODEL_ID`, default `gemma-4-E4B`): Frequent, lower-cost operations — Coder, Router. Multimodal (vision validated at runtime, used by the Coder's visual self-validation F-45).
- **Reasoning Model** (`REASONING_MODEL_ID`, default `gemma-4-12B`): Deep reasoning and ChainOfThought — Architect, Judge, Tester, Security Reviewer, PromptRefiner, Escalation, Adversaries, Synthesis.

### 5. Node Graph & Data Flow (Coding Workflow)
The end-to-end sequence of nodes, their LLM tier, and how data flows between them:

```
tasks.json (user prompt)
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│  1. PromptRefiner    [reasoning]  DSPy                   │
│     Rewrites raw prompt → structured spec               │
│     (## Objectif / Fonctionnalités / Critères)          │
│     Skipped on resume (persisted in checkpoint)         │
└─────────────────────────────────────────────────────────┘
   │ refined_prompt
   ▼
┌─────────────────────────────────────────────────────────┐
│  2. Router           [fast]  DSPy                        │
│     Classifies the technology (web/python/js/...)       │
└─────────────────────────────────────────────────────────┘
   │ router_lang
   ▼
┌─────────────────────────────────────────────────────────┐
│  3. Architect        [reasoning]  DSPy                   │
│     Splits task into subtasks (Pydantic)                │
│     + strategy per subtask (simple/incremental/multifile)│
└─────────────────────────────────────────────────────────┘
   │ subtasks[]
   ▼  (Fan-out: 1 loop per subtask, in parallel)
┌─────────────────────────────────────────────────────────┐
│  ┌─ AUTO-CORRECTION LOOP (max 3 iterations) ──────────┐ │
│  │                                                     │ │
│  │  4. Coder        [fast]  smolagents CodeAgent       │ │
│  │     Generates code (write_file/search_replace)      │ │
│  │     + DevTools MCP: navigate/screenshot/console     │ │
│  │       (visual self-validation, F-45)                │ │
│  │     Skills: coding, file-creation, frontend-design, │ │
│  │       context7-research, devtools-preview           │ │
│  └───────────────┬─────────────────────────────────────┘ │
│                  │                                         │
│                  ▼                                         │
│  5. Linter        [NO LLM]  deterministic (tree-sitter)  │
│     Validates syntax. If KO → back to Coder (Shift Left) │
│                  │ (if syntax OK)                          │
│                  ▼                                         │
│  5b. Static Tester [NO LLM] deterministic web gatekeeper  │
│      node --check (TS-in-vanilla) + wiring addEventListener│
│      + DOM visibility via DevTools (invisible bars).      │
│      If KO → back to Coder (court-circuite le Tester LLM) │
│                  │ (if checks OK or non-HTML)              │
│                  ▼                                         │
│  ┌─ AUDITS (sequential if AUDIT_PARALLEL=false) ───────┐ │
│  │  6a. Tester     [reasoning]  smolagents TCA          │ │
│  │      Drives Chrome (Puppeteer + DevTools MCP)        │ │
│  │      + requirements checklist (F-46)                 │ │
│  │      Skill: web-tester (puppeteer_* assertions)      │ │
│  │      OR PythonTestRunner (pytest subprocess, 0 LLM)  │ │
│  │                                                       │ │
│  │  6b. Security   [reasoning]  DSPy                    │ │
│  │      OWASP Top 10, CVSS, defensive-only              │ │
│  └───────────────┬─────────────────────────────────────┘ │
│                  │ test_res + sec_res                     │
│                  ▼                                         │
│  7. Judge         [fast]  DSPy                             │
│     Arbitrates: approved (merge) or feedback (re-loop)    │
│     Rubric: severity, in-diff-only, anti-nits             │
│  └─────────┬───────────────────────────────────────────┘ │
│            │                                               │
│     ┌──────┴───────┐                                      │
│     ▼              ▼                                      │
│  approved      rejected                                   │
│  (subtask      → refutations written to DuckDB            │
│   validated)   → Coder reads them next iteration          │
│     │              (read_file + search_replace)           │
│     │              (max 3 iterations)                     │
│     │                    │                                │
│     │              if 3 failures → 8. Escalation          │
│     │              [reasoning] DSPy                        │
│     │              post-mortem (root cause + lesson)       │
│     │              persisted in DuckDB                     │
│     ▼                                                      │
└──┤ subtask done                                            │
   ▼                                                         │
(all subtasks validated) → DONE, global verdict              │
```

**Key data flows:**
- **`original_content`**: the full spec (PromptRefiner output) is propagated to the Tester so it knows what to verify — and its `## Fonctionnalités attendues` section is parsed into a deterministic checklist (F-46) the Tester must tick item by item.
- **Refutations in DuckDB**: when the Judge rejects, bugs are written to the Knowledge Graph (`kind="refutation"`); the Coder reads them back next iteration via `query_duckdb_knowledge_graph`.
- **Checkpointing**: `coding_state` is persisted in DuckDB → crash recovery at any point.

<details>
<summary><b>Exploration mode (alternative workflow)</b></summary>

When `WORKFLOW_MODE=exploration` (divergent research), a different set of nodes is used:

| Node | LLM | Framework | Role |
|---|---|---|---|
| **Worker** | fast | smolagents ToolCallingAgent | Generates divergent leads |
| **Reduce** | — (none) | Python | Aggregates Worker outputs |
| **Adversary** | reasoning | DSPy | 3 skeptics refute in parallel |
| **Synth** | reasoning | DSPy | Final synthesis of accumulated findings |

These nodes are not used in coding mode.
</details>

---

## 🛠 Prerequisites

- Python 3.12+
- [Ollama](https://ollama.com/) installed and running locally.
- [uv](https://github.com/astral-sh/uv) installed for blazing fast dependency management.
- DuckDB (`uv pip install duckdb`)
- DSPy (`uv add dspy-ai`)

## 🚀 Installation

This project uses `uv` for seamless dependency and virtual environment management.

```bash
# 1. Download the required GGUF blobs for llama-server (models are launched dynamically)
#    - Fast model (Fan-out / Workers / Router) :
#    Download a small model (e.g. gemma-4-E4B.gguf)
#    - Heavy reasoning model (Architect / Coder / Judge) :
#    Download a larger model (e.g. gemma-4-12B.gguf)
#    Set their absolute paths in the .env file.
# 2. Sync Python dependencies via uv (including DSPy, smolagents, etc.)
uv sync

# 3. Copy the configuration template
cp .env.example .env
```

## 🎮 Usage

Ensure `llama-server` is in your PATH. The orchestrator will spawn and kill the models automatically during the workflow based on your `.env` configuration.

### Managing Prompts and Tasks (`tasks.json`)
You don't need to touch Python code to give orders to the orchestrator. Simply modify the `tasks.json` file in the root directory. This file dictates what tasks are run depending on the active `WORKFLOW_MODE`.

```json
{
  "coding": [
    {
      "id": "T004",
      "content": "Crée un jeu de Tetris simple...",
      "target_files": ["index.html", "style.css", "tetris.js"]
    }
  ]
}
```

### Software Engineering Mode (Coding Workflow)
Unleash the full multi-agent hybrid team (DSPy Architect ➔ smolagents Coders ➔ Testers ➔ DSPy Judge) using the tasks defined in your `tasks.json`:
```bash
$env:WORKFLOW_MODE="coding"
$env:PYTHONIOENCODING="utf-8"
uv run python -m graph_orchestrator.workflows
```
Each run is journaled automatically into `logs/run-<timestamp>-<mode>.log` (colors stripped for a clean plain-text log) — no manual redirection needed.

### Data Processing: One-shot Mode (Default)
Executes the standard Fan-out → Reduce → Adversary → Synth flow (mode par défaut de `WORKFLOW_MODE`, aucun réglage requis):
```bash
uv run agent_graph.py
```
`agent_graph.py` délègue à `graph_orchestrator.workflows.main()`, qui lit `WORKFLOW_MODE` pour choisir le mode (`one_shot` par défaut, `exploration` ou `coding`).

### Data Processing: Exploration Mode (Loop-until-dry)
```bash
WORKFLOW_MODE=exploration uv run python -m graph_orchestrator.workflows
```

### Run Analysis & Continuous Improvement
After a run (especially End-to-End coding workflows), you can analyze the execution logs and DuckDB database to extract metrics (tokens, duration per node, errors, crashes).
```bash
uv run python scripts/run_analyzer.py
```
Every run is auto-journaled to `logs/run-<timestamp>-<mode>.log` (via a Tee on stdout+stderr in `workflows.main()`). This script auto-detects the latest log there (cross-platform — honors `$LOGS_DIR`, or pass `--log <path>` / `--logs-dir <dir>` to override) and produces an `analysis_report.md`. This is critical for post-mortem debugging and continuous improvement of the agents (F-60 & F-61).

## 🧪 Testing

### Unit tests (no LLM, < 1 second)

The unit tests (Pydantic schemas, JSON extraction, adversarial voting logic, loop termination, MCP mocks, checklist parser) execute **without LLM calls**:

```bash
uv run pytest tests/ -v          # 535 tests, ~25s
```

### Node isolation scripts (iterate on ONE node without the full workflow)

To iterate quickly on a node (skill, prompt, logic) without relaunching the ~25-min full workflow (Architect → Coder → Tester → Judge), use these standalone runners. They call the **same production functions** (`execute_*_node`) — zero mock, zero behavior drift. Known-buggy inputs → assertion on the verdict (pattern proven by `debug/validate_static_tester_live.py` for the Static Tester).

**Root scripts** (Coder / Tester / Static Tester — predate F-55):

| Script | Node | Example |
|---|---|---|
| `run_tester.py` | Tester (LLM, Puppeteer/DevTools) | `uv run python run_tester.py` (auto-detects latest `runs/*/index.html`) |
| `run_tester.py` | Tester, specific file + custom spec | `uv run python run_tester.py runs/.../index.html "$(cat spec.md)"` |
| `run_coder_tca.py` | Coder (production CodeAgent, F-45 DevTools) | `uv run python run_coder_tca.py "Bubble sort visualizer"` |
| `run_coder_codeagent.py` | Coder (experimental CodeAgent mode) | `uv run python run_coder_codeagent.py "..."` |
| `debug/validate_static_tester_live.py` | Static Tester (F-54, deterministic) | `uv run python debug/validate_static_tester_live.py` |

**`debug/isolation/`** (F-55 — play a node by hand, no LLM call):

Per-node **methodologies** (`MANUAL_<NODE>_METHODOLOGY.md`) describing exactly what *the agent* does when playing that node by hand — fail-fast steps, tools used (`Read`/`grep`/`node`/DevTools/judgment), failure modes caught, and confirmation biases. Calqued on `debug/MANUAL_TESTER_METHODOLOGY.md` (the original Tester pattern).

| File | Node played | Output |
|---|---|---|
| `debug/isolation/MANUAL_ROUTER_METHODOLOGY.md` | Router (F-01) | `RouterOutput(language)` |
| `debug/isolation/MANUAL_ARCHITECT_METHODOLOGY.md` | Architect (F-15/F-29) | `ArchitectOutput(subtasks[strategy])` |
| `debug/isolation/MANUAL_LINTER_METHODOLOGY.md` | Linter (F-30) | `CoderOutput(status)` |
| `debug/isolation/MANUAL_SECURITY_METHODOLOGY.md` | Security (F-44 OWASP) | `SecurityOutput(is_secure, findings)` |
| `debug/isolation/MANUAL_JUDGE_METHODOLOGY.md` | Judge (F-44 rubric) | `CodeJudgeOutput(is_approved, findings)` |
| `debug/isolation/run_linter.py` | Linter (automated validation) | `CoderOutput(status)` — validates the Linter methodology in execution (7/7 scenarios ✅) |

See `debug/isolation/README.md` for the full input/output contract of each node and how to play a node by hand.

**`run_tester.py` details** — auto-detects the most recent `runs/*/index.html`, displays the extracted checklist (so you see exactly which features the Tester must verify), and runs the Tester in isolation:
```bash
uv run python run_tester.py
# [*] Tester standalone
#     Fichier testé     : runs/2026-08-02_1237_bubble_sort/index.html (7973 octets)
#     Checklist F-46 extraite : 5 fonctionnalité(s) à tester
#       1. Bouton « Démarrer le tri »...
#       2. Bouton « Réinitialiser »...
#       3. Curseur/slidebar pour régler la vitesse...
#       4. Compteur affichant le nombre de comparaisons...
#       5. Code couleur clair...
```

The default spec is the Bubble Sort requirements in **PromptRefiner format** (`## Fonctionnalités attendues` section) — this is what triggers the F-46 checklist. If you pass a plain-text spec (no structured section), the Tester falls back to the legacy free-text mode.

## ⚙️ Configuration

All parameters can be customized via environment variables or the `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_API_BASE` | `http://localhost:11434/v1` | OpenAI-compatible endpoint (Target for FAST_MODEL_ID, can be remote e.g., AlmaLinux) |
| `OLLAMA_REASONING_API_BASE` | `http://localhost:11434/v1` | Endpoint specifically for the heavy reasoning model |
| `FAST_MODEL_ID` | `qwen3.5:2b` | Light model for fan-out workers and routers |
| `REASONING_MODEL_ID` | `hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL` | Heavy model for ChainOfThought |
| `ADVERSARY_COUNT` | `3` | Number of independent skeptics for validation |
| `MAX_ITERATIONS` | `3` | Feedback loop limit for Coders and Exploration |
| `KG_PATH` | `graph_orchestrator.db` | DuckDB database path |
| `WORKFLOW_MODE` | `one_shot` | `one_shot`, `exploration`, or `coding` |

## 📁 Project Structure

```text
agent_graph.py                 ← Entry point (dispatche selon WORKFLOW_MODE)
DOC_DSPY_ARCHITECTURE.md       ← 📖 DSPy v3 Hybrid Architecture Manifesto
graph_orchestrator/
  ├── config.py                ← Env variables & defaults
  ├── models.py                ← Pydantic schemas (ArchitectOutput, SecurityOutput, etc.)
  ├── dspy_nodes.py            ← 🧠 The Brains: DSPy 3.0 Signatures & Predictors (Router, Architect, Judge)
  ├── nodes.py                 ← 🖐️ The Hands: smolagents CodeAgents (Coders) + Tester dispatcher
  ├── chrome_devtools_tool.py  ← 🖥️ Chrome DevTools MCP (visual self-validation, F-45)
  ├── vision_callback.py       ← 📸 step_callback: screenshots → observations_images (multimodal)
  ├── testers/                 ← 🧪 Polyvalent test runners (web: Puppeteer + DevTools, python: pytest, ...)
  ├── feedback_utils.py        ← Output truncation (head+tail) to prevent Context Overflow in the feedback loop
  ├── workflows.py             ← Complex orchestrations integrating DSPy and smolagents
  ├── knowledge_graph.py       ← DuckDB integration (claims, checkpoints)
  └── hitl.py                  ← Human-In-The-Loop logic
tasks.json                     ← 📝 User task definitions and prompts (auto-loaded)
docs/
  ├── orchestrator_banner.jpg  ← README Banner
  └── guide-graphes.md         ← Reference legacy manifest
```
