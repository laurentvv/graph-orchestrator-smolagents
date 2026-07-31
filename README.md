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
- **The Brains (DSPy 3.0)**: Cognitive nodes (Router, Architect, Security Reviewer, Code Judge) use DSPy `Signatures` and `ChainOfThought` to strictly map open-ended reasoning into guaranteed `Pydantic` JSON schemas. No more fragile manual prompting or regex hacking.
- **The Hands (smolagents)**: Execution nodes (Fan-out Coders, Testers) take the deterministic JSON orders from the Brains and execute them in reality using local tool collections (Chrome DevTools MCP, bash commands, file system access).

### 2. The Coding Playbook (Autonomous Engineering Team)
Instead of letting a single agent write and evaluate its own code, this system simulates an entire engineering team:
- **DSPy Architect Node**: A heavy reasoning model that takes a complex prompt, designs the global architecture, and breaks it down into granular JSON subtasks using strict Pydantic constraints. It also emits a **build strategy per subtask** (`simple` | `incremental` | `multifile`) telling the Coder *how* to construct the files — not just *what* to build.
- **Fan-out Coder Nodes (smolagents `CodeAgent`)**: For each subtask, a Coder agent is spawned asynchronously to write code by generating **Python that calls tools** (`write_file(path=..., content=...)`). CodeAgent was chosen over ToolCallingAgent after empirical comparison: small local models (gemma) reliably generate Python but fail to emit valid JSON tool-calls. A **guard software** detects idle steps (model reasons without acting) and broken code blocks (unclosed strings), re-injecting targeted correction messages.
- **Linter Node (Shift Left, deterministic)**: Right after the Coder, a **0-LLM gatekeeper** validates syntax (`tree-sitter` for Python/HTML/CSS/JS/TS/TSX + `py_compile` for Python indentation + HTML structural checks like *content after `</html>`*). On invalid syntax it **short-circuits the expensive Tester** and loops back to the Coder with the error — a syntax typo should never waste a full LLM cycle.
- **Parallel Validation**: 
  - *Tester Node (smolagents, **polyvalent**)*: Detects the target technology (web → **Puppeteer MCP** for browser testing; Python → **`pytest` subprocess** with deterministic pass/fail + captured stderr) and routes to the matching runner. Captured output is **truncated** (head + tail) before feedback to protect the LLM context window from "Context Overflow".
    - **Auto-dependency resolution**: the Python tester detects `ModuleNotFoundError` in the captured stderr and **installs the missing package itself** (`pip install`, non-persistent — does *not* touch `pyproject.toml`/`uv.lock`) before re-running the tests, rather than wasting an LLM cycle on what is merely an absent dependency. Capped at 1 retry (anti-loop), module name validated against an identifier regex (defense-in-depth against command injection). Opt-out via `AUTO_INSTALL_DEPS=false`.
    - **Functional logic testing (not just crash detection)**: the web tester writes **assertion scripts** via `puppeteer_evaluate` to verify the *behavior* the app claims to deliver (e.g. "is the array sorted after clicking Start?"), not only that the page renders without JS errors. The full requirements (cahier des charges) are propagated to the tester so it knows what to verify. Iterate on the tester in isolation with `uv run python run_tester.py [file.html] [task description]`.
  - *Security Reviewer (DSPy)*: Audits the code against vulnerabilities (XSS, injections, etc.) and returns a typed list of flaws.
- **DSPy Judge Node**: Acts as the ultimate PR reviewer. Analyzes tester/security reports, outputting a deterministic `approved: bool` verdict to either merge the code or trigger a feedback loop.
- **Escalation Node (automatic post-mortem)**: When a subtask exhausts the circuit breaker (3 rejected iterations), an `EscalationSignature` DSPy node synthesizes the accumulated refutations from the Knowledge Graph into a **structured post-mortem** (root cause + lesson + severity). The diagnosis is persisted in the KG (`kind="escalation"`) and linked to the refutations it summarizes via `ESCALATES` edges — queryable by future runs to avoid repeating the same dead-ends. Controlled by `ESCALATION_ENABLED` (default on; degrades gracefully to the legacy `max_iterations_reached` status if disabled or if the reasoning endpoint is down).
- **Context7 (up-to-date library docs)**: The Coder, Architect, and web-Tester are wired to **Context7** (`@upstash/context7-mcp`) to fetch **current library/framework documentation** — the antidote to API hallucination. Rather than relying on stale memorized APIs, agents consult official docs on demand. Controlled by the `context7-research` skill: it triggers **only for external libs** (React, Chart.js, pandas…) and **stays dormant on vanilla JS/CSS or algorithmic tasks** to avoid wasting steps. Requires `CONTEXT7_API_KEY` (degrades gracefully without it — all nodes run unchanged).

### 3. Persistent Knowledge Graph (DuckDB)
Context windows are limited. Instead of passing massive conversation histories between the agents, **all agents read and write to a shared, persistent DuckDB Knowledge Graph**.
- Tracks entities, observations, refutations, and typed edges (`REFUTES`, `SUPPORTS`).
- Absolute provenance: every claim knows which agent, model, and run produced it.
- **Agentic SQL Querying**: Agents are equipped with a `query_duckdb_knowledge_graph` tool to actively query historical bugs across past projects to avoid repeating mistakes.

### 4. Smart Model Tiering
Save costs and boost speed by dynamically routing tasks to the right brain:
- **Light Models** (`qwen3.5:2b`): Used for fan-out execution workers and rapid localized routing.
- **Heavy Models** (`gemma-4-E4B`): Reserved for the Architect, Code Judge, and Synthesis where deep reasoning and ChainOfThought is required.

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
# 1. Pull the required local models via Ollama
#    - Fast model (Fan-out / Workers / Router) :
ollama pull qwen3.5:2b
#    - Heavy reasoning model (Architect / Coder / Judge) :
ollama pull hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL

# 2. Sync Python dependencies via uv (including DSPy, smolagents, etc.)
uv sync

# 3. Copy the configuration template
cp .env.example .env
```

## 🎮 Usage

Ensure your Ollama server is running in the background (`ollama serve`).

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

### Data Processing: One-shot Mode (Default)
Executes the standard Fan-out → Reduce → Adversary → Synth flow (mode par défaut de `WORKFLOW_MODE`, aucun réglage requis):
```bash
uv run agent_graph.py
```
`agent_graph.py` délègue à `graph_orchestrator.workflows.main()`, qui lit `WORKFLOW_MODE` pour choisir le mode (`one_shot` par défaut, `exploration` ou `coding`).

### Data Processing: Exploration Mode (Loop-until-dry)
```bash
$env:WORKFLOW_MODE="exploration"
uv run python -m graph_orchestrator.workflows
```

## 🧪 Testing

The unit tests (Pydantic schemas, JSON extraction, adversarial voting logic, loop termination) execute **without LLM calls** and run in < 1 second:

```bash
uv run pytest tests/ -v
```

## ⚙️ Configuration

All parameters can be customized via environment variables or the `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_API_BASE` | `http://localhost:11434/v1` | OpenAI-compatible endpoint (Target for FAST_MODEL_ID, can be remote e.g., AlmaLinux) |
| `OLLAMA_REASONING_API_BASE` | `http://localhost:11434/v1` | Endpoint specifically for the heavy reasoning model |
| `FAST_MODEL_ID` | `qwen2.5-coder:3b` | Light model for fan-out workers and routers |
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
  ├── testers/                 ← 🧪 Polyvalent test runners (web: Puppeteer, python: pytest subprocess, ...)
  ├── feedback_utils.py        ← Output truncation (head+tail) to prevent Context Overflow in the feedback loop
  ├── workflows.py             ← Complex orchestrations integrating DSPy and smolagents
  ├── knowledge_graph.py       ← DuckDB integration (claims, checkpoints)
  └── hitl.py                  ← Human-In-The-Loop logic
tasks.json                     ← 📝 User task definitions and prompts (auto-loaded)
docs/
  ├── orchestrator_banner.jpg  ← README Banner
  └── guide-graphes.md         ← Reference legacy manifest
```
