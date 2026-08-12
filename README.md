# 🧠 Graph Orchestrator: The Autonomous Software Factory

![Graph Orchestrator Architecture](docs/orchestrator_banner.jpg)

[![Status](https://img.shields.io/badge/Status-Production_Ready-success.svg)](#)
[![Stack](https://img.shields.io/badge/Stack-DSPy_3.0_%7C_smolagents_%7C_MCP-blue.svg)](#)
[![Code Quality](https://img.shields.io/badge/Code_Quality-Grade_A-brightgreen.svg)](#)

Welcome to the **Graph Orchestrator**. This isn't just another AI chatbot that generates lines of code and crashes at the first error. It is a **fully autonomous engineering team**, orchestrated via graphs, equipped with persistent memory, and designed to solve complex end-to-end tasks without any human intervention.

If you've ever been frustrated by agents stuck in infinite loops, editing code blindly, or forgetting the initial requirements halfway through the project, this architecture was built *exactly* for you.

Proudly maintaining a **Grade A Code Quality**, ensuring zero dead code, zero formatting errors, and pristine modularity.

---

## 🚀 Why is this software factory unique?

The vast majority of existing coding agents rely on a single omnipotent AI model that must do everything: plan, code, test, and self-evaluate. This inevitably leads to context collapse and cognitive blindness.

The Graph Orchestrator breaks this ceiling by introducing the **"Brains vs Hands"** paradigm:

### 1. 🧠 The Brains (DSPy) Handle the Architecture
We delegate the heavy thinking to deep reasoning models. The **Architect**, the **Judge**, and the **Security Expert** never write a single line of code. They mathematically break down the requirements, generate ultra-strict JSON schemas, and ruthlessly evaluate the deliverables.

### 2. 🛠️ The Hands (smolagents) Execute in the Field
For each subtask, a **Coder** node wakes up. It receives a clear order and a powerful toolkit. It writes files, navigates the terminal, uses Git, and even has eyes to check UI elements visually before pushing code.

### 3. 👀 Multimodal Visual Self-Correction
Say goodbye to web interfaces with invisible buttons or overlapping divs. Our agents use the **MCP (Model Context Protocol)** to drive Chrome in the background. The agent takes a screenshot of its own code, analyzes it using its vision models, and fixes visual bugs on its own *before* you even see them.

### 4. 📚 The End of API Hallucinations (Context7)
Instead of letting the AI invent imaginary methods, our factory is hooked up in real-time to the **Context7** documentation network. As soon as the agent detects it needs a specific framework, it automatically pre-fetches the latest official documentation.

### 5. 🛡️ Bulletproof Guardrails
We don't waste expensive AI cycles verifying simple typos. Before any file is validated, strict guardrails instantly scan syntax, test web mechanics, detect infinite loops, and guarantee no file is written before it has been read.

### 6. 🗄️ Ironclad Memory: The Knowledge Graph
These AIs don't share a fragile history prompt that fades over time. They communicate and persist their knowledge inside a **local relational database (DuckDB)**. When a Coder fails, the reason is etched into the Knowledge Graph, guaranteeing the system **never produces a regression**.

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

> 📖 **For Systems Engineers & Architects:**
> Want to dive into the belly of the beast? Interested in asynchronous routing, abstract syntax trees, and DSPy specifications?
> 👉 [Check out our deep technical documentation](docs/TECHNICAL_DOCS.md)
