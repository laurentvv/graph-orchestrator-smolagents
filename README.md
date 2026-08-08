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
- **The Stall Detector** complements the circuit breaker by hashing the *output content* (what the agent actually wrote), not just the input — it catches the case where the agent rewrites the same file with a cosmetically different call, and detects runs with no new material delivered.
- **The Read-Before-Write Gate** strictly forbids an agent from editing a file it hasn't read first.
- **Context Compaction & Branch Summarization**: Dynamically compresses Python code via AST (Abstract Syntax Trees). But we go further: if an agent fails 10 times in a row, the engine summarizes the failed branch into a single learning insight. If it reads a file and then modifies it later, the obsolete reads are purged (File-State Compaction). This guarantees the agent never suffers from "Context Overflow".

---

## 🗄️ Ironclad Memory: The Knowledge Graph
These AIs (the Architect, the Coder, the Tester) don't share a fragile history prompt that fades over time. They communicate and persist their knowledge inside a **local relational database (DuckDB)**.

When a Coder fails and the Judge rejects the code, the reason for the rejection is etched into the Knowledge Graph. On the next iteration, the Coder queries this database to "learn from its mistakes", guaranteeing the system **never produces a regression**.

> 🧹 **Consolidation + oubli (F-68 Phase 1)** : sans maintenance, le KG grossit indéfiniment avec des réfutations rabâchées. En fin de run, un nœud DSPy (LLM-juge, format qm `UPDATE/DELETE/ADD`) déduplique et fusionne les claims redondants par entité. Un oubli par rétention temporelle (`MEMORY_RETENTION_DAYS=30`) prune les claims obsolètes tout en préservant les leçons durables (`escalation` + `insight`). Opt-out `MEMORY_CONSOLIDATION_ENABLED=false`.

> 🔁 **Recall cross-run (F-68 Phase 2)** : la mémoire survive d'un run à l'autre. En DÉBUT de run, les N leçons durables les plus récentes (`insight` + `escalation` — les kinds que l'oubli préserve) sont rappelées et injectées dans le prompt du Coder. Un run qui a appris qu'« une itération par `requestAnimationFrame` évite l'animation instantanée » transmet cette leçon aux runs suivants. Déterministe (0 LLM, 1 query SQL globale), top-N par récence, note « ignore si non pertinent ». Opt-out `MEMORY_RECALL_ENABLED=false`.

> 📦 **Contextualisation par package (F-76)** : un fichier `AGENTS.md` au niveau du dossier cible des `target_files` est lu et injecté dans le prompt du Coder comme directives spécifiques au composant (règles i18n, design system, conventions d'un sous-projet). Défense path traversal (containment realpath, fail-open).

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

**Workflow**: copy an entry from the catalogue into `tasks.json` (`coding` section), run the factory, then inject the verdict into the tracker:
```bash
uv run python scripts/parse_run_result.py --test-id bubble-sort-multifile   # latest run
uv run python scripts/parse_run_result.py --dry-run                         # preview only
```
The script parses the "RÉSULTAT FINAL DU GRAPHE" block, derives the status (✅/❌/⚠️/⏹️), and appends a row (duplicate-guarded). The recommended first validation is `bubble-sort-monofile` (bounded, single file).

## 🔬 Node Isolation Scripts (F-55 + F-89)

Debugging a single node (prompt, skill, logic) used to require relaunching the full 30-40 min graph. The `debug/` folder ships **isolation scripts** that call the **real production function** for each node (0 mock, 0 duplication) with fixed fixtures — so you iterate in **seconds/minutes**, not tens of minutes.

| Script | Node | Fixed inputs | What it validates |
| :--- | :--- | :--- | :--- |
| `debug/run_router.py` | Router | 5 prompts (Python/React/HTML/Rust/ambiguous) | No JS-overflow (F-56a bug) |
| `debug/run_prompt_refiner.py` | PromptRefiner | 3 prompts (vague/structured/minimal) | Vague-term detection without scope invention |
| `debug/run_architect.py` | Architect | Bubble Sort spec | 1 file = 1 subtask, techno-driven strategy |
| `debug/run_drafter.py` | Drafter | Bubble Sort JS subtask | Draft logic quality (reinjectable into Coder) |
| `debug/run_security.py` | Security | 4 codes (clean/XSS/eval/pickle) | OWASP detection without false positives |
| `debug/run_judge.py` | Judge | 4 scenarios (correct/bug/nit/fail-closed) | Verdict + fail-closed without LLM |
| `debug/run_coder.py` | Coder | Bubble Sort 3 files (+ optional draft) | Full code output (F-88) |
| `debug/run_web_tester_standalone.py` | Web Tester | HTML correct/bugged | Functional assertions (F-45) |
| `debug/isolation/run_linter.py` | Linter | 7 buggy/correct files | Syntax gatekeeper (deterministic, F-55) |
| `debug/validate_static_tester_live.py` | Static Tester | HTML corrupted/correct | DOM + wiring gatekeeper (deterministic, F-54) |
| `debug/run_consolidation.py` | Consolidation | 3 scenarios (duplicates/mixed/clean) | KG claim dedup/merge + forgetting (F-68 Ph1) |
| `debug/run_lesson_recall.py` | Lesson Recall | 3 scenarios (default/empty/scratch) | Cross-run durable lesson recall (F-68 Ph2) |

```bash
uv run python debug/run_router.py                   # default fixture set
uv run python debug/run_judge.py fail-closed        # single named scenario
uv run python debug/run_architect.py @prompts/spec.md  # custom input from file
```

See [`debug/isolation/README.md`](debug/isolation/README.md) for the full convention (manual methodologies F-55 + LLM isolation scripts F-89 + golden files).

---

> 📖 **For Systems Engineers & Architects:**
> Want to dive into the belly of the beast? Interested in asynchronous routing, abstract syntax trees, and DSPy specifications?
> 👉 [Check out our deep technical documentation (Architecture Details)](docs/ARCHITECTURE_DETAILS.md)
