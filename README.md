# 🧠 Graph Orchestrator: The Autonomous Software Factory

![Graph Orchestrator Architecture](docs/orchestrator_banner.jpg)

[![Status](https://img.shields.io/badge/Status-Production_Ready-success.svg)](#)
[![Tests](https://img.shields.io/badge/Tests-1460+_Passed-brightgreen.svg)](#)
[![Stack](https://img.shields.io/badge/Stack-DSPy_3.0_%7C_smolagents_%7C_DuckDB_%7C_Chrome_MCP-blue.svg)](#)
[![Code Quality](https://img.shields.io/badge/Code_Quality-Grade_A-brightgreen.svg)](#)

Welcome to the **Graph Orchestrator** — an enterprise-grade **autonomous software engineering factory**. This is not a fragile chatbot that spits out snippets and breaks at the first runtime error. It is a orchestrated multi-agent factory that turns natural language specifications into **audited, tested, and visually validated applications** with **zero human intervention**.

> 💡 **Fire-and-Forget Engineering**: Define your goal, start the factory, and get turnkey deliverables with proven timing, live HTTP readiness, and automated code review.

---

## 🚀 Why This Software Factory Changes Everything

Most coding agents try to do everything in a single prompt: plan, code, test, and self-evaluate. This inevitably causes context collapse, blind edits, and infinite loops. 

The Graph Orchestrator eliminates these failure modes through **strict separation of concerns** and **deterministic industrial guardrails**:

```
[ Your Prompt in tasks.json ]
              │
              ▼
   🧠 PromptRefiner & Architect (DSPy Reasoning)
              │  (Strict JSON Specs & Drafts — 0 lines of code written)
              ▼
   🛠️ Coder Agent (smolagents + CodeAgent)
              │  (Multi-file implementation, isolated FS sandbox)
              ▼
   ⚡ Deterministic Guardrails (0 LLM overhead)
              ├── AST Syntax & DOM Wiring Linters
              ├── Multi-Signal Temporal Animation Probes (F-112)
              └── Live HTTP Server Readiness Verification (F-100)
              │
              ▼
   👀 Multimodal Validation & Security
              ├── Chrome DevTools MCP: Screenshots & Visual Audits (F-45, F-109)
              ├── OWASP Vulnerability Scanner & Secret Redaction (F-105)
              └── Fail-Closed Judge Node with Git Turn Diffing (F-102, F-108)
              │
         [ Approved? ]
          ├── NO  ──► Auto-Correction Iteration (Memory & Checkpoint preserved)
          └── YES ──► 📦 Production-Ready Deliverable in runs/
```

### The 6 Pillars of Autonomous Reliability

1. 🧠 **Brains vs. Hands Architecture**  
   Deep reasoning models (**Architect**, **Judge**, **Security**) plan and evaluate without ever touching file writes. Fast, focused coding models (**Coder**) execute clear subtasks with strict file toolkits.
2. 👀 **Multimodal Visual Self-Correction**  
   The Coder drives real headless Chrome instances via the **Model Context Protocol (MCP)**. It captures screenshots of its own UI, inspects canvas pixels and DOM elements, and self-corrects visual bugs before you ever see them.
3. 📚 **Zero API Hallucinations (Context7 Network)**  
   When modern frameworks or libraries are detected, the orchestrator pre-fetches the latest official documentation in real time through Context7.
4. 🛡️ **Fail-Closed Industrial Guardrails**  
   Bugs are caught before expensive LLM calls: arithmetic delay resolution, canvas rendering integrity checks, strict prompt guidance budget gates (`check_agent_guidance.py`), and automated secret redaction (`<REDACTED>`).
5. 💾 **Transactional Filesystem & Self-Healing Runtime**  
   Every code generation runs inside an atomic filesystem transaction with journaled rollbacks (ported from OpenKB), cross-process run locks, verified non-destructive pruning (with a 6-hour grace period), and automatic LLM server revival on transient disconnects.
6. 🗄️ **Relational Event Stream Memory (DuckDB)**  
   No fragile chat histories that get truncated. All agent steps, verdicts, and learnings are etched into a persistent local DuckDB Knowledge Graph, preventing regressions across iterations.

---

## ⚡ Quickstart: Launching the Factory in 30 Seconds

### 1. Define your task in `tasks.json`
Write your requirements in plain text and specify the target output files:

```json
{
  "coding": [
    {
      "id": "bubble-sort-multifile-v6",
      "content": "Create an interactive Bubble Sort visualizer in vanilla HTML/CSS/JS across THREE files: index.html, styles.css, script.js. Include dark theme, step-by-step animation, speed controls, and comparative statistics.",
      "target_files": [
        "index.html",
        "styles.css",
        "script.js"
      ]
    }
  ]
}
```

### 2. Start the factory
```powershell
$env:WORKFLOW_MODE="coding"
$env:PYTHONIOENCODING="utf-8"
uv run python -m graph_orchestrator.workflows
```

### 3. Sit back and grab a coffee ☕
The orchestrator refines the prompt, drafts the architecture, generates clean modular code, runs automated browser tests, self-heals any flaws, and outputs verified deliverables into `runs/`.

---

## 🏆 Proven Industrial Reliability: The Golden Run

We maintain a permanent reference run (**Golden Run**) in `debug/reference_run_qwen4b_bubble_sort/`, proving that lightweight local models (Qwen-4B for coding + Ornith-9B for reasoning) reliably produce complex, multi-file web applications:

| Metric | Result |
|---|---|
| **Total Duration** | ~29.5 minutes (100% local consumer GPU) |
| **Tokens Processed** | 648,748 tokens |
| **Iterations** | 2 passes (Auto-corrected on pass 1, approved on pass 2) |
| **Deliverable** | 3 clean files (`index.html`, `styles.css`, `script.js`) with responsive dark UI and smooth canvas rendering |
| **Full Trace** | Inspectable in `debug/reference_run_qwen4b_bubble_sort/run_full.log` |

---

## 🔬 Under the Hood: The Reliability & Quality Stack

For developers, architects, and system engineers looking at the technical foundations:

- **Multi-Signal Temporal Animation Probe (F-112)**: Tracks all numeric DOM IDs, canvas djb2 pixel hash deltas, and terminal CSS classes. Resolves delay formulas arithmetically (`sleep(320 - speed * 2)` with `$speed=320` → detects negative/clamped delay). Catches instant/frozen animations deterministically in < 5 seconds without LLM cost.
- **Live HTTP Readiness Probing (F-100)**: Serves deliverables on dynamic local ports (Python `http.server` or detected project recipes) and validates HTTP 200 responses and clean socket teardown.
- **Non-Contaminating Git Turn Checkpoints (F-102)**: Snapshots the run worktree into dedicated git refs (`refs/graph-orchestrator/turns/<key>`) per iteration without touching HEAD, enabling structured per-file turn diffs for the Judge.
- **Multi-Tier LLM Retry & Server Revive (F-104 & F-113)**: Transparent call-level retries with exponential backoff and jitter. Dead dynamic local servers are automatically re-spawned and dynamic `api_base` properties ensure crash-proof Pydantic rescues.
- **Lossless Context Compaction v2 (F-101)**: 5-layer deterministic context management with lossless JSONL disk archives (`.transcripts/`) and single-use overflow guard latches.
- **Filesystem Isolation & Non-Destructive Prune (F-95 & F-113)**: Advisory cross-process directory locks (`.fs_tx/dir.lock`), hardlink/copy mutation snapshots, path allowlist sandboxing, and verified pruning with a 6-hour safety grace window.
- **Automated Secret Redaction & Security Hardening (F-105)**: Command guard blocking OS keychain / password manager access, plus unified feedback output sanitization replacing sensitive tokens and credentials with `<REDACTED>`.

---

## 📚 Documentation & Technical References

- 📖 [Technical Architecture & Node Graph](docs/TECHNICAL_DOCS.md)
- 🧭 [Node & Skill Directory](docs/NODES_AND_SKILLS.md)
- 📋 [Agent Specifications & Disk State Contracts](AGENTS.md)
- 🧪 [Isolated Node Debugging Suite](debug/isolation/README.md)
