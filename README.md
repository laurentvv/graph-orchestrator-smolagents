# 🧠 Graph Orchestrator: The Autonomous Software Factory

![Graph Orchestrator Architecture](docs/orchestrator_banner.jpg)

[![Status](https://img.shields.io/badge/Status-Production_Ready-success.svg)](#)
[![Stack](https://img.shields.io/badge/Stack-DSPy_3.0_%7C_smolagents_%7C_MCP-blue.svg)](#)

Welcome to the **Graph Orchestrator**. This isn't just another AI chatbot that generates lines of code and crashes at the first error. It is a **fully autonomous engineering team**, orchestrated via graphs, equipped with persistent memory, and designed to solve complex end-to-end tasks without any human intervention.

If you've ever been frustrated by agents stuck in infinite loops, editing code blindly, or forgetting the initial requirements halfway through the project, this architecture was built *exactly* for you.

---

## 🚀 Why is this software factory unique?

The vast majority of existing coding agents (Roo Code, Cline, Devin) rely on a single omnipotent AI model that must do everything: plan, code, test, and self-evaluate. This inevitably leads to context collapse and cognitive blindness.

The Graph Orchestrator breaks this ceiling by introducing the **"Brains vs Hands"** paradigm:

### 1. 🧠 The Brains (DSPy) Handle the Architecture
We delegate the heavy thinking to deep reasoning models (Chain of Thought, 32k tokens). 
The **Architect**, the **Judge**, and the **Security Expert** never write a single line of code. They mathematically break down the requirements, generate ultra-strict Pydantic JSON schemas (preventing hallucinations), and ruthlessly evaluate the deliverables.

### 2. 🛠️ The Hands (smolagents) Execute in the Field
For each subtask, a **Coder** node (fast model) wakes up. It receives a clear order and a powerful toolkit. It writes files, navigates the terminal, uses Git, and even has... eyes!

### 3. 👀 Multimodal Visual Self-Correction
Say goodbye to web interfaces with invisible buttons or overlapping divs. Our agents use the **MCP (Model Context Protocol)** to drive Chrome in the background. The agent takes a screenshot of its own code, analyzes it using its vision models, and fixes visual bugs on its own *before* you even see them.

### 4. 📚 The End of API Hallucinations (Context7)
An LLM cannot code using a library that was released yesterday. Instead of letting it invent imaginary methods, our factory is hooked up in real-time to the **Context7** documentation network. As soon as the agent detects it needs *React*, *Prisma*, or *Tailwind*, it automatically pre-fetches the latest official documentation.

### 5. 🛡️ Bulletproof Guardrails (Zero-LLM Gates)
We don't waste expensive AI cycles verifying simple typos. Before any file is validated:
- **The Linter** instantly scans the syntax.
- **The Static Tester** checks the web mechanics in three tiers: JS syntax (`node --check`), event wiring (are the buttons actually clickable?), DOM visibility (elements rendered, not just created), and **temporal behavior** — it detects "instant animations" where an algorithm (e.g. a sort) runs entirely in one frame instead of animating step-by-step.
- **The Anti-Loop Circuit Breaker** mathematically detects if the agent makes the exact same mistake 3 times in a row, triggering an Escalation (auto-post-mortem).
- **The Read-Before-Write Gate** strictly forbids an agent from editing a file it hasn't read first.
- **Context Compaction & Branch Summarization**: Dynamically compresses Python code via AST (Abstract Syntax Trees). But we go further: if an agent fails 10 times in a row, the engine summarizes the failed branch into a single learning insight. If it reads a file and then modifies it later, the obsolete reads are purged (File-State Compaction). This guarantees the agent never suffers from "Context Overflow".

---

## 🗄️ Ironclad Memory: The Knowledge Graph
These AIs (the Architect, the Coder, the Tester) don't share a fragile history prompt that fades over time. They communicate and persist their knowledge inside a **local relational database (DuckDB)**.

When a Coder fails and the Judge rejects the code, the reason for the rejection is etched into the Knowledge Graph. On the next iteration, the Coder queries this database to "learn from its mistakes", guaranteeing the system **never produces a regression**.

> 💾 **Persistance** : la base du KG vit dans `data/graph_orchestrator.db` (chemin ancré au paquet, indépendant du cwd). Les autres bases DuckDB (`event_stream.duckdb`, `runs_history.duckdb`) sont regroupées au même endroit. Override possible via `KG_PATH` dans `.env`.

---

## 🛠️ Ready to Start the Factory?

Want to see the team at work? The entry point is incredibly simple:

1. Open `tasks.json` and write your business requirements in natural language.
2. Boot the factory with a single command line:
   ```powershell
   $env:WORKFLOW_MODE="coding"
   $env:PYTHONIOENCODING="utf-8"
   uv run python -m graph_orchestrator.workflows
   ```
3. Grab a coffee ☕ and watch the orchestrator branch, plan, code, visually self-correct, and deliver a turnkey, stable, and audited project.

---

## 🧪 Test Suite & Regression Prompts

The repo ships a **curated catalogue of test prompts** to validate the graph on bounded, reproducible tasks (per `AGENTS.md §7`):

- **Catalogue** → [`prompts/test_prompts.py`](prompts/test_prompts.py) — typed Python entries (`id`, `content`, `target_files`, `notes`) with helpers `by_id()` and `to_coding_task()`. List them with `uv run python -m prompts.test_prompts`.
- **Results tracker** → [`prompts/test_results.md`](prompts/test_results.md) — manual dashboard (status + post-run notes) to update after each run.

| id | strategy | what it validates |
| :--- | :--- | :--- |
| `bubble-sort-monofile` | single `index.html` | baseline: step-by-step animation, speed slider, counter, color states |
| `bubble-sort-multifile` | `index.html` + `styles.css` + `script.js` | the Architect picks multifile (F-29), the Coder wires files together (link/script src + DOM ids), and linting runs per file |

**Workflow**: copy an entry from the catalogue into `tasks.json` (`coding` section), run the factory, then append a row to `test_results.md`. The recommended first validation is `bubble-sort-monofile` (bounded, single file).

---

> 📖 **For Systems Engineers & Architects:**
> Want to dive into the belly of the beast? Interested in asynchronous routing, abstract syntax trees, and DSPy specifications?
> 👉 [Check out our deep technical documentation (Architecture Details)](docs/ARCHITECTURE_DETAILS.md)
