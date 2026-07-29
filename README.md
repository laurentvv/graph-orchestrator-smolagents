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
- **DSPy Architect Node**: A heavy reasoning model that takes a complex prompt, designs the global architecture, and breaks it down into granular JSON subtasks using strict Pydantic constraints.
- **Fan-out Coder Nodes (smolagents)**: For each subtask, a Coder agent is spawned asynchronously to write code using precise tools.
- **Parallel Validation**: 
  - *Tester Node (smolagents)*: Uses **Chrome DevTools MCP** to visually and functionally test web code.
  - *Security Reviewer (DSPy)*: Audits the code against vulnerabilities (XSS, injections, etc.) and returns a typed list of flaws.
- **DSPy Judge Node**: Acts as the ultimate PR reviewer. Analyzes tester/security reports, outputting a deterministic `approved: bool` verdict to either merge the code or trigger a feedback loop.

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
Executes the standard Fan-out → Reduce → Adversary → Synth flow:
```bash
uv run agent_graph.py
```

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
agent_graph.py                 ← Entry point for one-shot data processing
DOC_DSPY_ARCHITECTURE.md       ← 📖 DSPy v3 Hybrid Architecture Manifesto
graph_orchestrator/
  ├── config.py                ← Env variables & defaults
  ├── models.py                ← Pydantic schemas (ArchitectOutput, SecurityOutput, etc.)
  ├── dspy_nodes.py            ← 🧠 The Brains: DSPy 3.0 Signatures & Predictors (Router, Architect, Judge)
  ├── nodes.py                 ← 🖐️ The Hands: smolagents CodeAgents (Coders, Testers)
  ├── workflows.py             ← Complex orchestrations integrating DSPy and smolagents
  ├── knowledge_graph.py       ← DuckDB integration
  └── hitl.py                  ← Human-In-The-Loop logic
tasks.json                     ← 📝 User task definitions and prompts (auto-loaded)
docs/
  ├── orchestrator_banner.jpg  ← README Banner
  └── guide-graphes.md         ← Reference legacy manifest
```
