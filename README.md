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
We don't waste expensive AI cycles verifying simple typos. Before any file is validated, strict guardrails instantly scan syntax, test web mechanics, detect infinite loops, and guarantee no file is written before it has been read. Context is treated as a scarce resource too: a deterministic budget gate (`uv run python scripts/check_agent_guidance.py`, port of deer-flow's CI check) bounds the size of every guidance file injected into the small local models — root/module/skill tiers plus the cumulative Coder chain — so prompt bloat fails fast in CI instead of killing a 40-minute GPU run with a context overflow. Secrets get the same treatment: a command denylist blocks password managers and keychain access outright, and every feedback line heading to an LLM passes through automatic redaction (`<REDACTED>` for API keys, tokens and literal passwords) — while never mangling actual code.

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

## 📝 Defining Tasks with `tasks.json`

The orchestrator reads your instructions from `tasks.json`. This file acts as the backlog for your autonomous team. You can define tasks in different workflows (`exploration`, `coding`, `one_shot`).

Here is a concrete example of a `coding` task for a Bubble Sort visualizer:

```json
{
  "coding": [
    {
      "id": "bubble-sort-multifile-v6",
      "content": "Crée un visualiseur d'algorithme Bubble Sort (tri à bulles) interactif en HTML/CSS/JS vanilla, réparti sur TROIS fichiers séparés : index.html (structure + lien vers le CSS et le JS), styles.css (tout le style), script.js (toute la logique). Pas de framework ni de CDN externe.\n\nL'interface doit montrer un tableau de barres verticales (hauteurs proportionnelles aux valeurs) qui s'animent pendant le tri. Fonctionnalités attendues :\n- un bouton « Démarrer le tri » qui lance l'animation pas-à-pas...\n\nContraintes techniques : index.html doit référencer styles.css via <link> et script.js via <script src>. Design soigné, responsive, avec un thème sombre.",
      "target_files": [
        "index.html",
        "styles.css",
        "script.js"
      ]
    }
  ]
}
```

You describe what you want in plain text in `content`, and you list the files you want the system to output in `target_files`.

---

## 🏆 What does a complete run look like? (The Golden Run)

When you run the command above with the Bubble Sort task, the system doesn't just blindly output code. It follows a rigorous industrial process. 

We have saved a perfect reference run, or **"Golden Run"**, located in `debug/reference_run_qwen4b_bubble_sort/`. Here is exactly what happens during those ~30 minutes:

### 1. Planning & Architecture (The Brains)
The **Architect** model (Ornith-9B) reads your `tasks.json` and creates a detailed technical specification.
* **Output generated:** `draft_bubble_sort_viz_001.md` containing the step-by-step logic, state management, and file structure.

### 2. Implementation (The Hands)
The **Coder** model (Qwen-4B) wakes up, reads the Architect's draft, and writes the code.
* **Output generated:** `index.html`, `styles.css`, and `script.js`.

### 3. Automated Guardrails & Multimodal Testing
Before the code is finalized, it passes through our CI/CD-like pipeline:
- **Static Tester:** Instantly checks for Syntax errors (e.g., TS in Vanilla JS) and checks DOM wiring (e.g., `addEventListener` attached to existing IDs).
- **HTTP readiness proof (F-100):** the deliverable is served on a free local port (`http.server` for vanilla apps, or the project's own start command when detected) and probed — "the page is served and answers" becomes an executable proof instead of `file://` only.
- **Per-iteration git checkpoint (F-102):** at the start of every Coder iteration the run worktree is snapshotted into a git ref (`refs/graph-orchestrator/turns/<key>`) without touching HEAD, the index or the worktree — the Judge then reads *what git says* changed (per-file status + adds/dels), available from iteration 1 onward.
- **Multimodal Testing:** The Coder spins up a headless Chrome via MCP, takes a screenshot of `index.html`, and uses its vision capabilities to verify the dark theme and UI rendering.
- **Judge & Security:** A deep reasoning model audits the code for vulnerabilities (XSS, `eval()`) and functional completeness. 

### 4. Self-Correction
If a test fails, the **Judge** rejects the commit, provides feedback, and the **Coder** starts a new iteration automatically. In our Golden Run, the Coder auto-corrected an issue in the first pass and succeeded perfectly on the second pass.

### 📊 Golden Run Metrics
- **Total Duration:** 29.5 minutes (on local GPU).
- **Tokens Processed:** 648,748 tokens.
- **Result:** A fully functional, responsive, and visually appealing Bubble Sort visualization, correctly split across 3 files, without a single human intervention.
- **Full logs:** You can inspect the complete execution trace in `debug/reference_run_qwen4b_bubble_sort/run_full.log`.

---

> 📖 **For Systems Engineers & Architects:**
> Want to dive into the belly of the beast? Interested in asynchronous routing, abstract syntax trees, and DSPy specifications?
> 👉 [Check out our deep technical documentation](docs/TECHNICAL_DOCS.md)
> 👉 [Read the Agent System Prompts & Guidelines](AGENTS.md)
