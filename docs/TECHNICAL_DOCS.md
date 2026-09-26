# Graph Orchestrator — Technical Documentation

Deep dive into every guard, compaction layer, recovery mechanism, memory subsystem and performance flag of the factory. The user-facing overview lives in the [README](../README.md); this document is for systems engineers who want to know *exactly* how the machine works.

Feature IDs (`F-xxx`) refer to `feature_list.json` — the complete, status-tagged cartography of the project.

---

## 1. The Guardrail Stack (Zero-LLM Gates)

We don't waste expensive AI cycles verifying simple typos. Before any file reaches an LLM judge, several deterministic gates ensure stability:

- **The Linter** (F-30) instantly scans syntax (tree-sitter / `py_compile` / `node --check`) right after the Coder, before any LLM tester.
- **The Static Tester** (F-54) checks web mechanics in tiers: JS syntax (`node --check` — catches TypeScript-in-vanilla, the #1 small-model failure), event wiring (are the buttons actually clickable?), DOM visibility via real Chrome geometry (catches the `height: X%` with no parent height bug), plus **CSS-variable cross-file checks** (F-164: `var(--*)` consumed but `:root` never written).
- **Temporal tier** (F-112): after clicking the primary action, the Static Tester tracks every numeric DOM element, the first canvas' pixel hash and terminal classes — if a signal progressed but is already stable within 400 ms, the animation ran *instantly* (negative/clamped delay, whole algorithm in one tick) and the artifact is refuted deterministically. Delay formulas are also resolved arithmetically (`sleep(320 - speed*2)` with `speed=320` → −320 ms → flagged).
- **Anti-Loop Circuit Breaker** (F-36): SHA-256 fingerprint of every tool call — the exact same call repeated 3× triggers an abort; a **Stall Detector** complements it by hashing the *output content*, catching cosmetic rewrites that deliver nothing new.
- **Prompt-size budget gate** (F-103, port of deer-flow's CI check): `uv run python scripts/check_agent_guidance.py` bounds the size of every guidance file injected into the small local models (root/module/skill tiers + the cumulative Coder chain) — prompt bloat fails fast in CI instead of killing a 40-minute GPU run with a context overflow.
- **Secret redaction**: a command denylist blocks password managers and keychain access outright, and every feedback line heading to an LLM passes automatic redaction (`<REDACTED>` for API keys, tokens and literal passwords) — without ever mangling actual code.
- **HTTP readiness proof** (F-100): the deliverable is served on a free local port (`http.server` for vanilla apps, or the project's own start command when detected) and probed — "the page is served and answers" becomes an executable proof instead of `file://` only. Recipe: `uv run python debug/run_verify.py [folder]`.

## 2. Coder Robustness & Continuity

### Mechanical auto-fix before LLM cycles (F-166)
When a small model emits literal `\n` escapes in its edit arguments, the write tools **decode them automatically instead of rejecting the call** (a 4-hour run was once burned on 15 consecutive rejections of that exact trap). A tolerant aider-style matching cascade (relative indentation, line-diff fallback) applies edits that would otherwise bounce; every write returns instant syntax diagnostics; and proven-mechanical error classes (`const` reassignment, literal `\n` in files) are fixed by a deterministic `fix_known_error` tool available to the Coder itself. Pure code first, LLM cycles last.

### Anti-total-rewrite & console stack traces (F-126)
Post-mortem of a 93-minute Tetris run: the 4B "fixed" a one-line bug by rewriting the whole 600-line `index.html` — three times — until the context overflowed. Three deterministic fixes: `write_file` **refuses to overwrite an existing file larger than 100 lines** (`CODER_WRITEFILE_MAX_LINES`; creating new files stays free — fixes go through `search_replace`/`multi_replace`); console errors are automatically **enriched with their full stack traces** plus a targeted `read_file(offset=line-8)` directive, so the model lands *on* the faulty line; and the Coder's llama-server context was raised to 65 536 with a q8_0 KV cache (less VRAM than the previous 49 152 in f16 on a 6 GB card).

### Graph continuity over Coder death (F-170)
The Coder has no authority to stop a run — even crashed. Post-mortem of the first 100%-pydantic run: a `UsageLimitExceeded` inside a non-converging visual-verification loop killed the whole graph *before* Linter/Static/Tester/Judge ever ran — while the deliverable was actually written on disk. Two guards now hold:
- **Budget-salvaged verdict**: on request-budget exhaustion, the full message history is captured (`capture_run_messages`, partial state included) and replayed in one bounded tool-less call with its own 3-request budget, forcing an *honest* `CoderOutput` (unperformed checks reported as such). GuardAbort/transport failures remain clean failures without salvage.
- **Never return early on a dead Coder**: the workflow synthesizes an honest failure output, journals a `coder/error` DuckDB event, and lets the deterministic gates referee the on-disk state — a deterministic refutation relaunches the Coder on the next iteration in correction mode; exhaustion escalates as always. `CODER_MAX_STEPS` raised 40→60 (on the pydantic engine, one tool call = one request).

### Older, always-on guards
Argument coercion by real tool schema (F-42 sanitizer), orphan tool-result repair for checkpoint replays (F-41), idempotent side-effects via a DuckDB-backed `once()` store (F-43), cross-process FS transactions with rollback journal and a path allowlist confining the Coder to its run directory (F-95), bash denylist blocking destructive commands across Unix/Windows (F-38).

## 3. Context Management — Compaction v2 → v3

**Compaction v2 (F-101)**: a deterministic 5-layer context compaction with loss-less disk archive — snipped steps go to `.transcripts/*.jsonl` (chained markers, nothing escapes successive compactions) and oversized tool outputs persist to `.task_outputs/` behind re-readable `<persisted-output>` previews. A context overflow triggers exactly ONE recovery per node run; a second drains the node cleanly. A `context_frame` scratchpad survives every compaction.

**Payload-resilient v3 (F-116)**: the 772k–990k tokens/step thrash wall had a root cause the image purge couldn't see — for a code-executor agent, `model_output` carries the thought **plus the full code block** and is resent at every step. v3 adds (all deterministic, default-on, kilocode ports): a **model_output clip** for old steps (head+tail, full version archived), a **loss-less image purge** (screenshots archived behind text placeholders), a bounded transcript of the snipped middle, **dead-end tombstones** ("CULS-DE-SAC: do not repeat"), a **hierarchical soft retry reset** replacing the total memory wipe (the visual ritual is no longer replayed from scratch ×3), and a **preflight** estimate that escalates compaction *before* sending a doomed request. The opt-in LLM semantic compaction wires the dormant summary prompts through `agent.model`, guarded by a verified-usage `CompactionBudget`. On top, the **ponytail doctrine** (7-rung YAGNI ladder, −54% LOC / −22% tokens) is injected into the Coder role header as *source* reduction — with an explicit "minimal describes the CODE, not the SCOPE" clause so the 4B never under-delivers requested features.

## 4. Validation Pipeline Proofs

- **Per-iteration git checkpoints** (F-102): at the start of every Coder iteration the run worktree is snapshotted into a git ref (`refs/graph-orchestrator/turns/<key>`) without touching HEAD, the index or the worktree — the Judge then reads *what git says* changed (per-file status + adds/dels), available from iteration 1. A run-local git repo (F-53) tracks every Coder change, feeding exact diffs to the Tester and Judge.
- **Evidence-required visual audit** (F-109/F-114): the Coder's "all criteria verified" self-declaration is not accepted — every visual criterion must be *materialized* through a `visual_check(criterion_number, verdict, observation)` tool call after the screenshot, otherwise `final_answer` is refused (run #10 after the fix: 60 audit calls, convergence in 12 steps). Screenshots are capped to the viewport (giant 9 000-pixel captures caused 600 s vision timeouts). Since F-126 the gate relies on a *durable* execution-time proof instead of scanning agent memory (which compaction/retries can purge).
- **Targeted re-test, git-diff style** (F-52): in iteration N+1 the Tester re-validates *only* the reported bugs + a console smoke test (max_steps 12→6) instead of re-testing everything from scratch (~90% of the work was re-verification).
- **Multimodal testing**: headless Chrome via MCP (DevTools + Puppeteer), screenshots analyzed by the vision models, DOM pre-filtered anti-noise (F-37: size divided by ≥3).

## 5. Planning & Plans-as-Files

- **Plan materialization** (F-120, planning-with-files): the Architect's plan is mirrored into the run directory as `plan.md` (global architecture, subtasks with strategy/sections/file checklists, visual & functional criteria, judge rubric) and `task.md` (live checklist + dated verdict journal) — deterministically regenerated at every run transition, 0 LLM. A short **stable anchor** (goal + current subtask + checklist + `plan.md` pointer) is injected into the Coder prompt at *every* iteration, so the small model keeps a fixed reference instead of a growing context.
- **Prescriptive-density Drafter** (F-167): A/B testing proved both Ornith-1.0 and 1.5 cloned a *hollow* draft — the root cause of the invalidated golden run was the Drafter's output FORMAT, not the GGUF. The Drafter now emits exact values (colors, sizes, formulas) enforced by a `draft_gate` density check, with retry-with-feedback.
- **Spec preservation** (F-62): the original full requirements are injected directly into the Coder prompt — the Architect synthesizes for strategy, never at the expense of the exact colors/numbers/constraints.

## 6. Infrastructure & Performance

- **LLM transport retry** (F-104): transient `Connection error` is retried at the *call* level — same request replayed with backoff + 25% jitter + 30 s cap, server-advised `retry-after` honored, fully transparent to the agent (nothing enters its history). A dead spawned server is re-spawned mid-run and the OpenAI client re-created on the new port; DSPy nodes get the same budget via litellm `num_retries`; MCP servers connect with per-server timeouts so a hung `npx` never blocks the run.
- **MTP speculative decoding** (F-123): the 9B GGUFs carry Multi-Token-Prediction layers llama-server was silently ignoring. `REASONING_SPEC_MTP=true` + `REASONING_KV_QUANT=q8_0` activate the embedded draft (`--spec-type draft-mtp --spec-draft-n-max 2`): measured **~+50% tokens/s** at 32k context (18.2 → 27.2 tok/s on RTX 3060 6 GB). Deliberately OFF on the 4B Coder (−42% measured — low draft acceptance). A/B harness: `debug/test_mtp_spec.py`. Vendored llama.cpp upgraded to build b10472 (CUDA 13.3).
- **Run-scoped browser pool** (F-163): all browser consumers (Coder, Static Tester, web Tester) share **one pool-owned Chrome per run** — MCP servers connect via `--browserUrl` instead of each spawning its own; the pool health-checks `/json/version`, respawns on death, and kills the whole process tree at run end (ending Windows orphan-Chrome leaks and ×4 cold-starts). Opt-out `BROWSER_POOL_ENABLED=0`; validate with `debug/run_browser_pool.py`.
- **Checkpoints & crash recovery** (F-24): GraphState persisted at every transition; a stable `run_id` derived from task content means a crashed run *resumes* — skipping the Architect, completed subtasks, and picking up at the exact iteration.
- **Crash-safe runs** (F-95): cross-process exclusive lock per run directory (two parallel resumes can never mutate the same run), FS transactions around every Coder call, journal rollback on next start. Harness: `debug/run_fs_safety.py`.
- llama.cpp flag guide (KV quant, cache-reuse, MTP, rejected flags, benchmark method): [`docs/LLAMA_SERVER_FLAGS.md`](LLAMA_SERVER_FLAGS.md).

## 7. Self-Installing & Lazy-Loaded Skills

- **Skills on demand** (F-57): the Coder gets a lightweight catalog (~100 tokens/skill) in its system prompt and a `load_skill` tool for full bodies — measured −36.8% system-prompt size per step, ~24k tokens/run saved. Critical skills (file-creation, coding, context7-research) stay eager by design.
- **Skill Finder** (F-82): when a task needs expertise the local catalog lacks (e.g. the **Vercel AI SDK**), the Architect notices the gap *before* planning and reaches out to the open [skills.sh](https://www.skills.sh/) registry (`npx skills`): trust-gated (author allowlist **+** safety markers), installed into `skills/`, registered with a dedicated keyword regex — flowing through the same lazy/budget pipeline as built-in skills. Persistence is a versioned manifest, never a source-file mutation. Opt-out `SKILL_FINDER_ENABLED=false`. Validation prompts: [`prompts/validation/`](../prompts/validation/README.md).

## 8. Knowledge Graph & Deep Memory

> 🧹 **Consolidation + forgetting (F-68 Phase 1)**: at run end, an LLM-judge node deduplicates and merges redundant claims per entity (qm `UPDATE/DELETE/ADD` format); temporal retention (`MEMORY_RETENTION_DAYS=30`) prunes stale claims while preserving durable lessons (`escalation` + `insight`). Opt-out `MEMORY_CONSOLIDATION_ENABLED=false`.

> 🔁 **Cross-run recall (F-68 Phase 2)**: at run *start*, the N most recent durable lessons are injected into the Coder prompt — a run that learned "one iteration per `requestAnimationFrame` avoids instant animation" transmits the lesson forward. Deterministic (0 LLM), top-N by recency. Opt-out `MEMORY_RECALL_ENABLED=false`.

> 📦 **Package contextualization (F-76)**: an `AGENTS.md` at the `target_files` folder is injected into the Coder prompt as component-specific directives (path-traversal-safe, fail-open).

> 💾 **Persistence**: the KG lives in `data/graph_orchestrator.db` (package-anchored path, cwd-independent); the event stream in `data/event_stream.duckdb` (`run_event` table — every run, verdict, fix and merge is queryable post-mortem); run history in `data/runs_history.duckdb`. Override via `KG_PATH`.

## 9. Engine Migration — smolagents → pydantic-ai-harness (complete)

The Coder and web Tester originally ran on smolagents `CodeAgent`. They now run **exclusively** on [pydantic-ai-harness] (F-151→F-169): native `CoderOutput` structured output, behavioral guards (loop/stall/idle/goal), transport revive, tiered context compaction, MCP toolsets with per-tool transforms (screenshot `filePath` stripping, console stack enrichment), and native multimodal vision (screenshots returned in-context, losslessly purged when stale). Measured **−82% input tokens** vs the smolagent baseline. F-169 removed the engine switch entirely — there is a single code path — and added DSPy structure-rescue guardians (a parse-failed draft is salvaged deterministically before burning a retry). Migration journal: [`docs/PLAN_MIGRATION_PYDANTIC_HARNESS.md`](PLAN_MIGRATION_PYDANTIC_HARNESS.md); official-doc reading notes: [`docs/PYDANTIC_AI_HARNESS_DOC_NOTES.md`](PYDANTIC_AI_HARNESS_DOC_NOTES.md).

## 10. Test Suite & Regression Prompts

The repo ships a **curated catalogue of test prompts** to validate the graph on bounded, reproducible tasks:

- **Catalogue** → [`prompts/test_prompts.py`](../prompts/test_prompts.py) — typed entries (`id`, `content`, `target_files`, `notes`) with helpers `by_id()` / `to_coding_task()`. List them: `uv run python -m prompts.test_prompts`.
- **Results tracker** → [`prompts/test_results.md`](../prompts/test_results.md) — manual dashboard updated after each run.

| id | strategy | what it validates |
| :--- | :--- | :--- |
| `bubble-sort-monofile` | single `index.html` | baseline: step-by-step animation, speed slider, counter, color states |
| `bubble-sort-multifile` | 3 files | Architect picks multifile strategy (F-29), Coder wires files together, per-file linting |

**Workflow**: copy an entry into `tasks.json`, run the factory, then inject the verdict:
```bash
uv run python scripts/parse_run_result.py --test-id bubble-sort-multifile   # latest run
uv run python scripts/parse_run_result.py --dry-run                         # preview only
```

Full CI suite: **2 131 tests / 0 failed** (`uv run pytest`), covering every deterministic guard and workflow E2E with mocked LLMs.

## 11. Node Isolation Scripts (F-55 + F-89)

Debugging one node used to require the full 30–40 min graph. The `debug/` folder ships isolation scripts calling the **real production function** (0 mock) with fixed fixtures — iterate in seconds/minutes:

| Script | Node | Fixed inputs | What it validates |
| :--- | :--- | :--- | :--- |
| `debug/run_router.py` | Router | 5 prompts (Python/React/HTML/Rust/ambiguous) | No JS-overflow |
| `debug/run_prompt_refiner.py` | PromptRefiner | 3 prompts (vague/structured/minimal) | Vague-term detection without scope invention |
| `debug/run_architect.py` | Architect | Bubble Sort spec | 1 file = 1 subtask, techno-driven strategy |
| `debug/run_drafter.py` | Drafter | Bubble Sort JS subtask | Draft density (F-167 gate) |
| `debug/run_security.py` | Security | 4 codes (clean/XSS/eval/pickle) | OWASP detection without false positives |
| `debug/run_judge.py` | Judge | 4 scenarios (correct/bug/nit/fail-closed) | Verdict + fail-closed |
| `debug/run_coder.py` | Coder | Bubble Sort 3 files (+ optional draft) | Full code output |
| `debug/run_web_tester_standalone.py` | Web Tester | HTML correct/bugged | Functional assertions |
| `debug/isolation/run_linter.py` | Linter | 7 buggy/correct files | Syntax gatekeeper (deterministic) |
| `debug/validate_static_tester_live.py` | Static Tester | HTML corrupted/correct | DOM + wiring + temporal gatekeeper |
| `debug/run_verify.py` | Executable proof | any folder | HTTP readiness (F-100) |
| `debug/run_fs_safety.py` | FS robustness | crash scenarios | transactions + lock + recovery (F-95) |
| `debug/run_browser_pool.py` | Browser pool | — | single Chrome per run (F-163) |
| `debug/test_mtp_spec.py` | llama-server | A/B bench | MTP compat + perf (F-123) |
| `debug/run_consolidation.py` | Consolidation | 3 scenarios | KG dedup/merge + forgetting (F-68 Ph1) |
| `debug/run_lesson_recall.py` | Lesson Recall | 3 scenarios | cross-run recall (F-68 Ph2) |

Full convention (manual methodologies + golden files): [`debug/isolation/README.md`](../debug/isolation/README.md). The complete table also lives in [`docs/DEBUG_SCRIPTS.md`](DEBUG_SCRIPTS.md).

## 12. Reference Runs & Post-Mortems

Preserved, retention-proof runs under `debug/reference_run_*` (deliverables + drafts + full logs + run git history):

| Folder | What it captures |
|---|---|
| `reference_run_qwen4b_bubble_sort/` | The original Golden Run (~30 min, 2 Coder iterations). |
| `reference_run_2026-08-17_first_e2e_approval/` | First full E2E approval: real bug found → surgical fix → approved (~23 min). |
| `reference_run_2026-08-18_run19_perfect_deliverable/` | Perfect deliverable in one iteration (~14 min, 21 steps) — plus its later invalidation analysis (swap-vs-comparison counter, fixed upstream by F-167). |

Post-mortems live in `debug/POSTMORTEM_*.md`. Meta-lessons that shaped the architecture: *the 4B can correct anything if the feedback is precise and qualitative*; *a healthy upstream prompt is worth ten downstream corrections*; *the base is more important than the log* (a lying or lossy DB record once sent a correction loop after a phantom bug — F164-6).

## 13. Architecture Details

See [`docs/ARCHITECTURE_DETAILS.md`](ARCHITECTURE_DETAILS.md) for additional system-design specifications, and [`docs/NODES_AND_SKILLS.md`](NODES_AND_SKILLS.md) for the forced system prompts and skill routing per node.
