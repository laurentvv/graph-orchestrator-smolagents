# Graph Orchestrator Technical Documentation

This document contains the deep technical details, architectures, node isolations, and testing paradigms of the Graph Orchestrator.

## 1. Deep Dive: Zero-LLM Gates & Guardrails

We don't waste expensive AI cycles verifying simple typos. Before any file is validated, several gates ensure stability:
- **The Linter** instantly scans the syntax.
- **The Static Tester** checks the web mechanics in three tiers: JS syntax (`node --check`), event wiring (are the buttons actually clickable?), DOM visibility (elements rendered, not just created), and **temporal behavior** — it detects "instant animations" where an algorithm (e.g. a sort) runs entirely in one frame instead of animating step-by-step.
- **The Anti-Loop Circuit Breaker** mathematically detects if the agent makes the exact same mistake 3 times in a row, triggering an Escalation (auto-post-mortem).
- **The Stall Detector** complements the circuit breaker by hashing the *output content* (what the agent actually wrote), not just the input — it catches the case where the agent rewrites the same file with a cosmetically different call, and detects runs with no new material delivered.
- **Direct Context Pre-Injection & Safe Edits**: In multi-turn correction, existing code is pre-injected directly into context, removing artificial read barriers and enabling instant, surgical edits.
- **Context Compaction & Branch Summarization**: Dynamically compresses Python code via AST (Abstract Syntax Trees). If an agent fails 10 times in a row, the engine summarizes the failed branch into a single learning insight. If it reads a file and then modifies it later, the obsolete reads are purged (File-State Compaction). This guarantees the agent never suffers from "Context Overflow".

## 2. Self-Installing Skills (F-82 — Skill Finder)

When a task needs expertise the local catalog lacks (e.g. the **Vercel AI SDK**, **React best-practices**), the Architect notices the gap *before* planning and reaches out to the open **[skills.sh](https://www.skills.sh/)** registry (`npx skills`). It searches, **trust-gates** the result (configurable author allowlist **+** skills.sh safety markers — unsafe/malicious is blocked even for a trusted author), installs the skill into `skills/`, then registers a **dedicated keyword regex** for it — so the Coder picks it up exactly like the built-in skills, flowing through the same lazy/budget pipeline (catalog metadata, token budget, on-demand `load_skill`). Persistence is a versioned manifest (`skills/installed-skills.json`), never a source-file mutation. Opt-out: `SKILL_FINDER_ENABLED=false`. **Validation prompts** for this feature live in [`prompts/validation/`](./prompts/validation/README.md) (loaded into `tasks.json` via `scripts/load_prompt.py`).

## 3. Knowledge Graph & Deep Memory Details

> 🧹 **Consolidation + oubli (F-68 Phase 1)** : sans maintenance, le KG grossit indéfiniment avec des réfutations rabâchées. En fin de run, un nœud DSPy (LLM-juge, format qm `UPDATE/DELETE/ADD`) déduplique et fusionne les claims redondants par entité. Un oubli par rétention temporelle (`MEMORY_RETENTION_DAYS=30`) prune les claims obsolètes tout en préservant les leçons durables (`escalation` + `insight`). Opt-out `MEMORY_CONSOLIDATION_ENABLED=false`.

> 🔁 **Recall cross-run (F-68 Phase 2)** : la mémoire survive d'un run à l'autre. En DÉBUT de run, les N leçons durables les plus récentes (`insight` + `escalation` — les kinds que l'oubli préserve) sont rappelées et injectées dans le prompt du Coder. Un run qui a appris qu'« une itération par `requestAnimationFrame` évite l'animation instantanée » transmet cette leçon aux runs suivants. Déterministe (0 LLM, 1 query SQL globale), top-N par récence, note « ignore si non pertinent ». Opt-out `MEMORY_RECALL_ENABLED=false`.

> 📦 **Contextualisation par package (F-76)** : un fichier `AGENTS.md` au niveau du dossier cible des `target_files` est lu et injecté dans le prompt du Coder comme directives spécifiques au composant (règles i18n, design system, conventions d'un sous-projet). Défense path traversal (containment realpath, fail-open).

> 💾 **Persistance** : la base du KG vit dans `data/graph_orchestrator.db` (chemin ancré au paquet, indépendant du cwd). Les autres bases DuckDB (`event_stream.duckdb`, `runs_history.duckdb`) sont regroupées au même endroit. Override possible via `KG_PATH` dans `.env`.

## 4. Test Suite & Regression Prompts

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

## 5. Node Isolation Scripts (F-55 + F-89)

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

## 6. Architecture Details

Also see [docs/ARCHITECTURE_DETAILS.md](ARCHITECTURE_DETAILS.md) if available for additional system design specifications.
