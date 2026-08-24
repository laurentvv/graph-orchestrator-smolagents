# INDEX — Audit des références

> **Document maître** de l'audit radical du dossier `references/`. Objectif : retrouver instantanément n'importe quelle information / feature / code utile, avec son **emplacement complet** et une **évaluation de réutilisabilité** pour `graph-orchestrator-smolagents`.

---

## Vue d'ensemble

| Métrique | Valeur |
|---|---|
| **Date de l'audit** | 2026-08-24 |
| **Projets/dossiers audités** | 52 |
| **Entrées de fichiers inventoriées** | 687 (inventaire machine : [`inventory.json`](./inventory.json)) |
| **Fichiers pertinents scannés** (base) | ~14 000 (hors `.git/`, `node_modules/`, médias, fixtures) |
| **Périmètre** | docs (`.md`/`.mdx`) + code source (`.py/.ts/.go/.js/.html/.css/.rs/.java`) + JSON/YAML de spec/contrat |
| **Exclusions** | `.git/` (~730 MB), `node_modules/`, médias (1 293 SVG, 16 mp4…), fixtures de tests, traductions de README (1 conservée/projet) |

**Projet cible** : `graph-orchestrator-smolagents` — orchestrateur multi-agent (Routeur → Architect → Coders fan-out → Tester → Judge), persistance DuckDB (knowledge graph de claims/refutations), test polyvalent (web Puppeteer + Python pytest), Context7. Stack Python (DSPy "Brains" + smolagents "Hands").

---

## 🧭 Navigation — les 52 fiches

| # | Projet | Réutilisabilité | Fiche | Résumé en 1 ligne |
|---|---|---|---|---|
| 01 | **Prompt-Vault** | 🟢 Haute | [01-prompt-vault](./projects/01-prompt-vault.md) | 12 cahiers des charges de coding (Easy→Advanced) pour tester le workflow — matériel d'éval clé-en-main |
| 02 | **aider** | 🟢 Haute | [02-aider](./projects/02-aider.md) | 12 edit-formats robustes (SEARCH/REPLACE, V4A) + RepoMap original + pattern Architect→Editor |
| 03 | **nanocode** | 🟡 Moyenne | [03-nanocode](./projects/03-nanocode.md) | Agent à outils minimal (1 fichier, zéro dépendance) — `edit` avec unicité anti-ambiguïté |
| 04 | **RepoGraph** | 🟢 Haute | [04-repograph](./projects/04-repograph.md) | Graphe de code repository-level (tree-sitter + networkx) + compression libcst pour le contexte LLM |
| 05 | **axon** | 🟢 Haute | [05-axon](./projects/05-axon.md) | Knowledge graph de code 12-phases + MCP server (15 tools) + RRF + dead code + impact analysis |
| 06 | **graphify** | 🟢 Haute | [06-graphify](./projects/06-graphify.md) | KG de code multi-langage + tags de confiance EXTRACTED/INFERRED + impact analysis avec provenance |
| 07 | **LlamaBot** | 🟡 Moyenne | [07-llamabot](./projects/07-llamabot.md) | Agent de test TDD 6-stages + circuit-breaker + capture Playwright (patterns, stack LangGraph) |
| 08 | **deer-flow** | 🟡 Moyenne | [08-deer-flow](./projects/08-deer-flow.md) | Super-agent harness (30 middlewares, contracts JSON de protocole, RFC authz, plans TDD) |
| 09 | **open-swe** | 🟡 Moyenne | [09-open-swe](./projects/09-open-swe.md) | Module plan-review + findings de review + diff PR + approval gates (style Stripe Minions) |
| 10 | **crush** | 🟡 Moyenne | [10-crush](./projects/10-crush.md) | Agent Go Charm — `loop_detection.go` anti-loop (hash SHA256) + pattern sub-agent fan-out |
| 11 | **opencode** | 🔴 Faible | [11-opencode](./projects/11-opencode.md) | Agent TS/Effect-TS — uniquement les `specs/v2/` (cahiers des charges protocole) ont de la valeur |
| 12 | **openfox** | 🔴 Faible | [12-openfox](./projects/12-openfox.md) | Agent TS local-LLM-first — docs d'architecture engine-loop + persistance SQLite (→ DuckDB) |
| 13 | **deer_flow_analysis.md** | 🟢 Haute | [13-deer-flow-analysis](./projects/13-deer-flow-analysis.md) | Note d'analyse : 3 idées actionnables (middlewares, reducers typés, contexte à la demande) |
| 14 | **qm** | 🟢 Haute | [14-qm](./projects/14-qm.md) | Plateforme agent multi-joueur (TS) — **algorithmes portables** : compaction de contexte duale, mémoire durable deux-tiers (LLM-juge de consolidation), idempotency, queues à leases typés |
| 15 | **claude-code-unified-agents** | 🟡 Moyenne | [15-claude-code-unified-agents](./projects/15-claude-code-unified-agents.md) | 53 (et non 54) agents Claude Code — ~8 prompts purs alignés avec les rôles Router/Coder/Tester/Judge/Security ; reste = code TS non portable |
| 16 | **learn-claude-code** | 🟢 Haute | [16-learn-claude-code](./projects/16-learn-claude-code.md) | Cours 20 leçons déconstruisant Claude Code en harness engineering — **Python natif** : hooks, compaction, error recovery, skill loading, task DAG (patterns directement portables) |
| 17 | **system-prompts-and-models-of-ai-tools** | 🟢 Haute | [17-system-prompts-and-models-of-ai-tools](./projects/17-system-prompts-and-models-of-ai-tools.md) | Collection de system prompts extraits d'outils IA (32 dossiers) — **bibliothèque de patterns** pour nos prompts : Codex CLI, Manus, Claude Code 2.0, Gemini CLI, Cursor + 10 invariants universels |
| 18 | **awesome-claude-skills** | 🟡 Moyenne | [18-awesome-claude-skills](./projects/18-awesome-claude-skills.md) | Marketplace officielle Claude de skills — **doctrine du format SKILL.md** (modèle 3-niveaux Progressive Disclosure) + outillage (`init_skill.py`/`quick_validate.py`) + `mcp-builder`. Caution externe de P10 |
| 19 | **loopx** | 🟢 Haute | [19-loopx](./projects/19-loopx.md) | Control plane pour agents longue durée — **3 priorités** : anti-loop déterministe (stall detector + hash d'output + delivery_outcome), compaction par whitelist de champs, event sourcing idempotent |
| 20 | **code-review-graph** | 🟡 Moyenne | [20-code-review-graph](./projects/20-code-review-graph.md) | Moteur d'analyse d'impact + **risk score composite** (`compute_risk_score` ∈ [0,1], buckets 0.7/0.4) + `IMPACT_EDGE_WEIGHTS` — signaux quantitatifs pour le Judge (P6) |
| 21 | **davidondrej-skills** | 🟡 Moyenne | [21-davidondrej-skills](./projects/21-davidondrej-skills.md) | **Denylist 27 regex POSIX-ERE** (bash destructeur) + moteur fail-open + ~115 tests — enrichit notre `bash_guard.py` (P8) |
| 22 | **llm-council** | 🟡 Moyenne | [22-llm-council](./projects/22-llm-council.md) | Pattern **council anonymisé** (labels A/B/C + mapping réversible + agrégation Borda) — option d'enrichissement du Judge (⚠️ coût 2N+1 appels) |
| 23 | **mattpocock-skills** | 🟢 Haute | [23-mattpocock-skills](./projects/23-mattpocock-skills.md) | **Doctrine d'authoring formelle** (Predictability, deux charges, hiérarchie 3 rungs, 5 failure modes) — pivot de la fusion P10 + `code-review`/`tdd` engineering skills |
| 24 | **pi** | 🟢 Haute | [24-pi](./projects/24-pi.md) | Agent stateful TS — **compaction contextuelle**, résumé de branche pour P9, et juge empirique vitest (P6) |
| 25 | **hermes-agent** | 🟢 Haute | [25-hermes-agent](./projects/25-hermes-agent.md) | Agent auto-amélioré Python (Nous Research) — **5 axes en Python pur** : compaction offline+live (P9), SQLite FTS5 event-sourcing (P11), skills agentskills.io + guard + AST audit (P10), sécurité multi-couches (P3/P8), contrat middleware 4 kinds (P8) |
| 26 | **cloudflare-os** | 🟡 Moyenne | [26-cloudflare-os](./projects/26-cloudflare-os.md) | Environnement agentique TS — Gatekeepers et sécurité basée sur les capacités, asynchrone |
| 27 | **browser-use** | 🟢 Haute | [27-browser-use](./projects/27-browser-use.md) | Framework Python d'automatisation de navigateur par IA. Gère l'état du navigateur, la compaction du DOM et le système Judge |
| 28 | **TencentDB-Agent-Memory** | 🟢 Haute | [28-TencentDB-Agent-Memory](./projects/28-TencentDB-Agent-Memory.md) | Framework de mémoire avancée (pipeline L0→L3 complet, dédup `store/skip/update/merge` supérieure, oubli par chaleur, Skill Review gate 5-critères/4-dim, context-offload Mermaid scoré) — prompts TypeScript transposables quasi-directement |
| 29 | **system-prompts-leaks** | 🟢 Haute | [29-system-prompts-leaks](./projects/29-system-prompts-leaks.md) | Collection de prompts système de production (Claude Code, Gemini CLI, Cursor, etc.). Références incontournables |
| 30 | **Ix** | 🟡 Moyenne | [30-Ix](./projects/30-Ix.md) | Framework de mémoire persistante (graphe relationnel ArangoDB) — requêtes tree-sitter réutilisables + skills de navigation sémantique |
| 31 | **Scrapling** | 🟡 Moyenne | [31-Scrapling](./projects/31-Scrapling.md) | Framework Python de web scraping adaptatif (parseur lxml, fetchers anti-bot, spiders async) + serveur MCP pour agents |
| 32 | **OpenKB** | 🟢 Haute | [32-OpenKB](./projects/32-OpenKB.md) | Knowledge Base compiler Python — robustesse FS (transactions hardlinks, verrous coopératifs, IO allowlist) + Skill Factory |
| 33 | **room** | 🟡 Moyenne | [33-room](./projects/33-room.md) | Framework multi-agents TS (swarm Queen/Workers) — patterns résilience (rate-limit 429, singleton navigateur, event-bus, Windows 8191 chars) |
| 34 | **brooklyn-skills** | 🟢 Haute | [34-brooklyn-skills](./projects/34-brooklyn-skills.md) | Skills portables — doctrine (`defaults.md` UI-first/clean-PR) + `no-tropes` (anti-tics d'écriture LLM) |
| 35 | **Understand-Anything** | 🟢 Haute | [35-Understand-Anything](./projects/35-Understand-Anything.md) | Analyse de code multi-agent (tree-sitter + LLM) — scripts Python `merge_graphs` + prompts Tour Builder (Fan-In/Fan-Out) |
| 36 | **prime-agent** | 🟡 Moyenne | [36-prime-agent](./projects/36-prime-agent.md) | Agent de coding RLM TS — gates anti-emballement (`AgentAutonomousConfig`) + compaction file-ops + `OutputAccumulator` stream-safe |
| 37 | **obsidian-skills** | 🟢 Haute | [37-obsidian-skills](./projects/37-obsidian-skills.md) | Skills agentiques Obsidian — architecture modulaire déclarative (`SKILL.md`/`references/`), valide la Progressive Disclosure (P10) |
| 38 | **skills** | 🟢 Haute | [38-skills](./projects/38-skills.md) | Skills officielles Anthropic — harnais d'évaluation (`skill-creator` split train/test, `mcp-builder` eval) + doctrine de création |
| 39 | **langextract** | 🟢 Haute | [39-langextract](./projects/39-langextract.md) | Lib d'extraction structurée Google — grounding par alignement (`WordAligner` difflib/LCS) anti-hallucination des findings Judge |
| 40 | **waku-agent** | 🟢 Haute | [40-waku-agent](./projects/40-waku-agent.md) | Agent perso local Python pur — boucle guardrails, DAG déterministe par vagues (`GraphStateCollision`), tracing JSONL/OTel |
| 41 | **stagehand** | 🟡 Moyenne | [41-stagehand](./projects/41-stagehand.md) | SDK browser-agent LLM — primitives `act`/`observe`/`extract` self-healing + DOM tronqué optimisé tokens |
| 42 | **anydoc** | 🟢 Haute | [42-anydoc](./projects/42-anydoc.md) | Conversion documentaire Rust/Python — LLM Judge pairwise anti-biais (inversion A/B) + skill déclaratif canonique |
| 43 | **framework** | 🟡 Moyenne | [43-framework](./projects/43-framework.md) | Framework AI-Driven Dev — SDLC orchestré (`01-sdlc`) + revue 3-axes (code/functional/relevancy) + debug 11 étapes par hypothèses |
| 44 | **sentrux** | 🟡 Moyenne | [44-sentrux](./projects/44-sentrux.md) | Capteur de santé structurelle (5 métriques racines, score 0-10000) + pipeline tree-sitter multi-langage (Rust, à porter) |
| 45 | **OpenSandbox** | 🟢 Haute | [45-OpenSandbox](./projects/45-OpenSandbox.md) | Plateforme de sandbox pour agents IA (ex-Alibaba) — transport retry Python pur (P8), spec lifecycle snapshot/restore (P8-bis), AGENTS.md hiérarchiques (P0), request-id ContextVar (P11) |
| 46 | **deepseek-harness** | 🟢 Haute | [46-deepseek-harness](./projects/46-deepseek-harness.md) | Harness d'agent « everything is a plugin » (TS/Cordis, DeepSeek) — anti-loop + boucle ralph (P3), retry durable (P8), compaction checkpoint 8 sections (P9), event stream typé (P11) |
| 47 | **kilocode** | 🟢 Haute | [47-kilocode](./projects/47-kilocode.md) | Agent de coding multi-surface (CLI/VS Code/JetBrains) — Agent Manager multi-worktrees (P12/P3), compaction payload recovery & chunks (P9), CodeMode confiné (P8-bis/P8), kilo-memory (P6/P11) |
| 48 | **ponytail** | 🟢 Haute | [48-ponytail](./projects/48-ponytail.md) | Doctrine & framework anti-over-engineering (The lazy senior dev mode, MIT) — échelle YAGNI 7 rungs (-54% LOC, -22% tokens, 100% safe) + format 1 ligne/finding pour le Judge |
| 49 | **obscura** | 🟢 Haute | [49-obscura](./projects/49-obscura.md) | Navigateur headless Rust ultra-léger (~30 Mo RAM, 85 ms load) — serveur MCP avec identifiants stables `interactive_refs`, limite de tokens `DEFAULT_TEXT_LIMIT = 4000`, serveur CDP |
| 50 | **hunk** | 🟢 Haute | [50-hunk](./projects/50-hunk.md) | Visualiseur/réviseur de diffs TUI pour agents IA (OpenTUI) — annotations inline IA pour le Judge (`agentAnnotations.ts`), `workspaceWriteGuard` et daemon `session-broker` |
| 51 | **bytechef** | 🟡 Moyenne | [51-bytechef](./projects/51-bytechef.md) | Plateforme d'intégration & orchestration d'agents IA (Java/Spring Boot) — batterie de 12 guardrails modulaires (secrets, PII, sanitization, topical alignment), MCP et coordinateur de tâches |
| 52 | **AutoDesign** | 🟢 Haute | [52-AutoDesign](./projects/52-AutoDesign.md) | Framework méta-harnais et usine multi-agents pour génération d'artefacts éditables (Posters, Slides, Web, Vidéos) depuis PDF — critic forké autonome (P6), claim graph strict (P0), process supervision Job Objects (P8) et skills v2 (P10) |

---

## 🗂️ Synthèse thématique — 3 familles

### 1. 🤖 Coding agents CLI (code lourd, peu portable)
`aider` (Python, mature), `crush` (Go), `nanocode` (Python, 1 fichier), `opencode` (TS, gigantesque), `openfox` (TS, local-LLM-first), `kilocode` (TS/SolidJS, multi-worktrees). → Valeur : edit-formats robustes (aider), anti-loop (crush), patterns d'outils minimaux (nanocode), specs de protocole (opencode), persistance event-sourcing (openfox), Agent Manager & worktrees isolés (kilocode).

### 2. 🔧 Frameworks d'orchestration d'agents (mixte code + docs)
`axon` + `RepoGraph` + `graphify` (knowledge graph de code, tree-sitter — **le trio le plus réutilisable**), `deer-flow` (super-agent ByteDance), `open-swe` (LangChain), `LlamaBot` (LangGraph Rails), `qm` (harnais TS — compaction/mémoire/queues portables), `learn-claude-code` (déconstruction Python pédagogique de Claude Code), `loopx` (control plane — anti-loop déterministe + event sourcing + compaction, stdlib pure), `code-review-graph` (analyse d'impact + risk score composite), `pi` (agent stateful TS), `hermes-agent` (agent auto-amélioré Python Nous Research — compaction + SQLite FTS5 + skills + sécurité + middleware), `cloudflare-os` (architecture Gatekeepers, human in the loop asynchrone), `browser-use` (automatisation web Python), `deepseek-harness` (harness TS/Cordis « everything is a plugin » — anti-loop ralph + retry durable + compaction checkpoint + event log typé), `OpenSandbox` (plateforme de sandbox ex-Alibaba — transport retry Python + spec lifecycle snapshot/restore), `obscura` (navigateur headless Rust ultra-léger ~30 Mo + serveur MCP + CDP), `hunk` (diff viewer TUI agent-first + inline AI annotations + session broker), `bytechef` (plateforme d'orchestration & intégration d'entreprise + 12 guardrails modulaires), `AutoDesign` (framework de méta-harnais double-boucle + vision critic forké + extraction stricte de claim graph + process supervision durable Win32/POSIX + skills v2 Progressive Disclosure). → Valeur : patterns d'orchestration, contrats de protocole, middlewares, plans/review cycles, agents de test, **compaction de contexte (qm, pi, hermes-agent, browser-use, deepseek-harness, kilocode)**, **patterns harness Python natifs (learn-claude-code, hermes-agent, AutoDesign)**, **anti-loop déterministe + event ledger (loopx, deepseek-harness, AutoDesign)**, **isolation d'itérations par worktrees (kilocode)**, **annotations inline d'agents IA pour le Judge (hunk)**, **serveur MCP web ultra-léger avec identifiants stables (obscura)**, **batterie de 12 guardrails modulaires d'entrée/sortie (bytechef)**, **supervision de sous-processus cross-platform et vision critic forké autonome (AutoDesign)**.

### 3. 📚 Ressources & outils
`Prompt-Vault` (12 prompts de test), `RepoGraph` (recherche académique SWE-bench), `deer_flow_analysis.md` (synthèse orientante), `claude-code-unified-agents` (prompts de spécialisation), `system-prompts-and-models-of-ai-tools` (**bibliothèque de system prompts** d'outils commerciaux/open-source), `awesome-claude-skills` (**doctrine du format SKILL.md** + outillage), `davidondrej-skills` (denylist 27 regex + hooks anti-crash), `mattpocock-skills` (**doctrine d'authoring formelle** + engineering skills), `llm-council` (pattern council anonymisé), `ponytail` (**doctrine de concision anti-over-engineering** + échelle YAGNI 7 rungs + format 1 ligne/finding).

---

## 🏆 Hall of Fame — Top 25 fichiers les plus réutilisables

Sélection des briques à plus forte valeur d'export directe pour le projet cible. Triés par thématique d'application.

### Knowledge graph de code (la brique manquante du KG DuckDB actuel)
| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/axon/src/axon/core/ingestion/pipeline.py` | `PipelineResult`, `run_pipeline` | Modèle d'orchestrateur 12-phases transposable au workflow coding |
| `references/axon/src/axon/core/search/hybrid.py` | `hybrid_search`, `_accumulate_ranks` | Reciprocal Rank Fusion (BM25+vecteur+fuzzy) pour ranking claims DuckDB |
| `references/axon/src/axon/core/ingestion/dead_code.py` | `process_dead_code` | Détection multi-passes → claims/refutations orphelins |
| `references/axon/src/axon/mcp/tools.py` | `handle_impact`, `handle_context`, `handle_call_path` | Impact analysis BFS groupé par profondeur — exposer le KG aux agents |
| `references/axon/src/axon/core/graph/model.py` | `NodeLabel`, `RelType`, `GraphNode`, `generate_id` | Schéma de graphe adaptable (Coder/Test/Judge comme nodes) |
| `references/RepoGraph/repograph/construct_graph.py` | `CodeGraph`, `tag_to_graph` | Construction graphe de code (tree-sitter, autonome) |
| `references/RepoGraph/repograph/graph_searcher.py` | `RepoSearcher`, `dfs`, `bfs` | Traversées de graphe minces pour outil `search_dependencies` |
| `references/RepoGraph/agentless/util/compress_file.py` | `get_skeleton` | Compression libcst (corps → `...`) pour réduire le contexte LLM |
| `references/graphify/graphify/affected.py` | `AffectedHit`, `affected_nodes` | Impact analysis avec provenance par edge (`via_file`/`via_location`) |
| `references/aider/aider/repomap.py` | `RepoMap`, `nx.pagerank(personalization=...)` | Source originale du RepoMap (ranking PageRank, cache diskcache) |

### Fiabilisation des Coders (edit-formats)
| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/aider/aider/coders/editblock_coder.py` | `EditBlockCoder`, `find_original_update_blocks` | Format SEARCH/REPLACE avec fallbacks (exact → whitespace → ellipsis → fuzzy) |
| `references/aider/aider/coders/search_replace.py` | `RelativeIndenter`, `dmp_apply`, `git_cherry_pick_osr_onto_o` | Moteur d'application multi-stratégies (rareté) |
| `references/aider/aider/coders/patch_coder.py` | `PatchCoder`, `Patch`, `PatchAction` | Format V4A/apply_patch moderne (GPT-5 era), multi-fichiers + move |
| `references/aider/aider/coders/architect_coder.py` | `ArchitectCoder.reply_completed` | Pattern Brains/Hands (Architect → EditorCoder) |
| `references/nanocode/nanocode.py` | `edit` (l.38-51) | `edit` avec unicité du `old_string` (anti-ambiguïté, ~10 lignes) |

### Anti-loop / circuit-breaker / robustesse
| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/crush/internal/agent/loop_detection.go` | `hasRepeatedToolCalls` | Anti-loop par hash SHA256 (~90 lignes Go → ~30 Python) |
| `references/LlamaBot/app/agents/leonardo/rails_agent/middleware.py` | `FailureCircuitBreakerMiddleware` | Circuit-breaker (stop après 3 échecs, reducer `operator.add`) |
| `references/deer-flow/backend/packages/harness/deerflow/agents/middlewares/` | `LoopDetection`, `TokenBudget`, `ToolOutputBudget` | Chaîne de 30 middlewares (loop, budget, sanitization) |

### Compaction de contexte / mémoire durable / robustesse runtime (qm)
> ⚠️ **La plus grande valeur de `qm` — ignorée par l'ancienne fiche.** Pour un orchestrateur long-running à contexte limité (DSPy brains sur petits modèles locaux), ces briques sont des blueprints quasi-directs.

| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/qm/src/harness/context-compaction.ts` | `planCompaction`, `forModelContext`, `estimateEntryTokens`, `COMPACT_SOFT_FRACTION=0.7`, `COMPACT_HARD_FRACTION=0.9`, `INTERRUPTED_TOOL_RESULT` | **Le fichier le plus précieux de tout le dossier.** Planning de compaction token-aware, préservation des paires tool_call/result, résumé incrémental, reconstruction des calls interrompus |
| `references/qm/src/core/orchestrator/compaction.ts` | `createCompaction`, `compactContextIfNeeded`, `scheduleBackgroundCompaction`, `MAX_CONTEXT_TOKENS=120_000` | Compaction **duale** : synchrone hard-limit + async soft-limit en tâche de fond avec lease |
| `references/qm/src/memory/strategies/consolidation.ts` | `MEMORY_CONSOLIDATION_PROMPT`, `applyConsolidationActions`, `ConsolidationAction` | LLM-juge `UPDATE <n>`/`DELETE <n>`/`ADD:` = consolidation de claims pour le Judge (Priorité 6) |
| `references/qm/src/memory/strategies/scratch-promote.ts` | `createScratchPromote`, `PROMOTION_PROMPT` | Mémoire deux tiers : scratch volatile + notebook consolidé durable |
| `references/qm/src/memory/memory-service.ts` | `MemoryService`, `foldCapture`, `replaceIfRevision`, `MAX_FACTS=300` | Contrat mémoire (recall/capture/replace) + dédup normalisée + concurrence optimiste |
| `references/qm/src/idempotency/idempotency-store.ts` | `once(key, fn)`, `IdempotencyStore` | Effet de bord appliqué exactement une fois (turns rejoués / retries) |
| `references/qm/src/ratelimit/budget.ts` | `createBudgetTracker`, `estimateCostUsd`, `DEFAULT_BUDGET_WINDOW_MS` | Budget USD par fenêtre glissante 24h — contrôle de coût LLM |
| `references/qm/src/runs/run-store.ts` | `RunStore`, `errorParks`, `claim`, `heartbeat`, `reapExpired` | Queue distribuée (dedup/lease/heartbeat/retry/reaper) — modèle pour DuckDB |
| `references/qm/src/sessions/session-store.ts` | `LeaseHolder` (`turn`/`compaction`/`fork`), `LlmCallUsage` | **Leases typés par rôle** : empêcher une compaction d'écraser un turn en cours |

### Tester / Judge / Review
| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/LlamaBot/app/agents/leonardo/rails_testing_agent/nodes.py` | `build_workflow`, 6 stages TDD | Agent de test RED→GREEN avec circuit-breaker (modèle nœud Tester) |
| `references/LlamaBot/app/agents/utils/playwright_screenshot.py` | `capture_page_and_img_src`, `trim_html_for_llm` | Capture web + nettoyage HTML (modèle web tester) |
| `references/open-swe/agent/review/findings.py` | `Finding`, `_finding_fingerprint`, `filter_findings_for_publish` | Schéma de findings de revue (severity, dédup SHA-256, cap) — pour le Judge |
| `references/open-swe/agent/dashboard/pr_diff.py` | `build_pr_diff_files` | Diff full-content multi-fichiers d'une PR GitHub (utile pour le Judge) |
| `references/open-swe/agent/dashboard/plan_store.py` | `PLAN_STATUS_*`, `save_plan_content` | Cycle de vie d'un plan (6 statuts, approve/reject) — pour l'Architect |

### Contrats / specs / protocoles
| Fichier | Apport |
|---|---|
| `references/deer-flow/contracts/run_event_stream_contract.json` | Spec de protocole d'événements versionné (frozen/additive/breaking) — 17 Ko |
| `references/deer-flow/contracts/skill_review/*.schema.json` (3 schémas) | Pipeline de revue qualité (snapshot → facts → report) |
| `references/deer-flow/docs/superpowers/plans/2026-07-02-read-before-write-gate.md` | Pattern gate middleware stateless (write sauf si lu) |

### Note de synthèse
| Fichier | Apport |
|---|---|
| `references/deer_flow_analysis.md` | Les 3 idées actionnables : middlewares autour du nœud Agent, reducers typés, contexte à la demande (Prompt-Vault) |

### Anti-loop déterministe + event sourcing idempotent (loopx)
> ⚙️ **La matière déterministe qui manquait pour P3 et P11.** crush (10) ne faisait que du hash d'output ; loopx apporte un véritable modèle comptable du turn (productif vs gratuit) + un stall detector + un event sourcing idempotent. Python stdlib pure → portable direct.

| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/loopx/loopx/control_plane/quota/recent_runs.py` | `consecutive_unchanged_monitor_observations`, `MONITOR_DEBT_UNCHANGED_TURN_THRESHOLD=2` | **Stall detector déterministe** (~160 L). Compte les turns sans transition matérielle, ignore le bookkeeping, au-delà du seuil=2 → backoff. Complément direct à notre LoopGuard (F-36) qui ne fingerprint que les tool_calls |
| `references/loopx/loopx/capabilities/issue_fix/pr_monitor_materialization.py` | `_group_fingerprint`, `result_hash`, `material_change` | **Pattern de hash d'output matériel** (le précédent hash ≠ nouveau hash → `material_change`, sinon `consecutive_no_change++`). Exactement ce qu'il faut pour hasher la sortie du Coder à chaque itération |
| `references/loopx/loopx/control_plane/work_items/delivery_outcome.py` | `DeliveryOutcome`, `ACCOUNTABLE_DELIVERY_OUTCOMES` | **Vocabulaire du résultat de turn** (accountable/progress/idle). La métrique qui alimente tout l'anti-loop |
| `references/loopx/loopx/event_sourced_state.py` | `AppendOnlyStateEventStore`, `event_fingerprint`, `event_stream_checksum`, `StateEventConflictError` | **Event sourcing append-only idempotent** (fingerprint + checksum SHA256 + détection de conflit + rebuild d'état). À reloger sur DuckDB (le projet cible l'utilise déjà) |
| `references/loopx/loopx/control_plane/runtime/event_ledger.py` | `EVENT_LEDGER_CLASSES` (5 classes), `build_event_ledger_summary` | **Journal d'événements classifié** (accounting/decision/evidence/state/work) agrégé sur fenêtres 24h/7d. Blueprint pour l'event stream (P11) au-delà du contrat deer-flow |
| `references/loopx/loopx/control_plane/runtime/run_compaction.py` | `compact_run_base`, `RUN_BASE_COMPACT_FIELDS` | **Compaction par whitelist de champs par type de payload** (complément structurel à qm sémantique) |

### Risk score quantitatif pour le Judge (code-review-graph)
> 📊 **Signaux quantitatifs d'entrée du Judge.** Le Judge actuel ne s'appuie que sur du qualitatif LLM ; code-review-graph apporte un scoring composite multi-facteurs ∈ [0,1] + buckets + tables de poids par type de relation.

| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/code-review-graph/code_review_graph/changes.py` | `compute_risk_score(store, node, churn_counts) -> float`, `review_priorities` | **Score de risque 0.0-1.0 multi-facteurs** (flow participation 0.25, callers 0.15, test coverage 0.30→0.05, security +0.20, churn 0.15). `review_priorities` = top-10 par score desc — inspire l'ordonnancement des findings |
| `references/code-review-graph/code_review_graph/constants.py` | `IMPACT_EDGE_WEIGHTS`, `IMPACT_DEPTH_DECAY=0.6`, `SECURITY_KEYWORDS` | **Tables de poids par type de relation** (CALLS 1.0, INHERITS 0.9, TESTED_BY 0.7…) + decay géométrique + 26 security keywords. Réutilisables telles quelles |
| `references/code-review-graph/code_review_graph/tools/context.py` | `get_minimal_context`, bucketing `>0.7 high, >0.4 medium` | **Seuils de bucketing** à calibrer pour la rubric critical/high/medium/low du Judge |

### Doctrine d'authoring de skills (mattpocock — pivot de la fusion P10)
> 🎓 **La théorie de l'authoring qui manquait.** awesome-claude-skills (18) + davidondrej (21) sont des collections ; mattpocock formalise un modèle conceptuel cohérent applicable à nos skills smolagents.

| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/mattpocock-skills/skills/productivity/writing-great-skills/SKILL.md` (+ `GLOSSARY.md`) | **Predictability**, **context load vs cognitive load**, **model-invoked vs user-invoked**, **router skill**, **3 rungs**, **5 failure modes**, **leading word** | **Doctrine P10 la plus aboutie**. Racine = Predictability ; deux charges (cognitive/context) ; hiérarchie 3 rungs ; failure modes nommés (premature completion, duplication, sediment, sprawl, no-op, negation). Concepts agnostiques du runtime |
| `references/mattpocock-skills/.agents/adr/0001-*.md` | **hard-dependency vs soft-dependency** | Pattern **fail-loud vs degrade-gracefully** (notre Context7/devtools font déjà du degrade-gracefully) |
| `references/mattpocock-skills/skills/engineering/code-review/SKILL.md` | **two axes** (Standards/Spec), **parallel sub-agents** | Pattern de judge à deux axes (Standards → lint, Spec → conformité PRD) en sub-agents parallèles jamais fusionnés |

### System prompts spécialisés (claude-code-unified-agents)
> Valeur concentrée dans ~8 prompts purs (49–185 lignes) alignés avec les rôles du graphe. Les autres fichiers sont du code TS non portable. 4 agents promis par le README sont absents (`ui-designer`, `content-strategist`, `performance-optimizer`, `iot-engineer`).

| Fichier | Rôle cible | Apport |
|---|---|---|
| `…/.claude/agents/quality/code-reviewer.md` | **Judge** | Output structuré Critical/Major/Minor, tools lecture seule (pas de Write) — format du Judge (Priorité 6) |
| `…/.claude/agents/quality/security-auditor.md` | **Security Reviewer** | Taxonomie vulns OWASP + scores CVSS + compliance frameworks |
| `…/.claude/agents/quality/test-engineer.md` | **Tester (Python)** | Pyramide 70/20/10, pattern AAA (Arrange-Act-Assert), tests indépendants |
| `…/.claude/agents/development/python-pro.md` | **Coder (Python)** | Type hints systématiques, PEP 8, docstrings (garde-fous concrets) |
| `…/.claude/agents/development/frontend-specialist.md` | **Coder (Web)** | a11y (ARIA, clavier), lazy loading, code splitting |
| `…/.claude/agents/development/backend-architect.md` | **Architect** | 5 axes obligatoires : scalabilité, cohérence, sécurité, monitoring, rollback |
| `…/.claude/agents/orchestrator.md` | **Router** | Conditional Routing, Decision Framework, `delegate_to(agent, task=…)` |
| `…/.claude/agents/specialized/agent-generator.md` | Spécialisation agents | `AgentCapabilitySchema` (name/description/category/expertise/tools/constraints) — déclarer formellement un rôle |

### Harness patterns Python natifs (learn-claude-code)
> ⚡ **La référence la plus directement exploitable** pour les briques transversales : contrairement à qm (TypeScript), tout est en **Python natif**, portage quasi littéral. Code pédagogique mais **fonctionnel et testé**. Couvre P8 (hooks + error recovery), P9 (compaction), P10 (skill loading), P11 (event stream), P6 (task DAG), P0 (subagent).

| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/learn-claude-code/s04_hooks/code.py` | `HOOKS[event]`, `trigger_hooks` | **Architecture middleware en ~30 lignes.** Squelette de TOUS les middlewares (Sanitizer, Orphan Repair, LoopDetection) ET de l'event stream (P8 + P11) |
| `references/learn-claude-code/s11_error_recovery/code.py` | `RecoveryState`, `with_retry`, fallback model | 3 chemins de récupération : escalation max_tokens, compaction, backoff+jitter+fallback model (P8 anti-crash) |
| `references/learn-claude-code/s08_context_compact/code.py` | `snip_compact`, `micro_compact`, `reactive_compact` | 4 couches budget→snip→micro→auto. **Préserve les paires tool_use/tool_result** = Orphan Repair. Équivalent Python de `context-compaction.ts` (qm), testé |
| `references/learn-claude-code/tests/test_compaction_tool_pairs.py` | `assert_no_orphan_tool_results` | **Test exact du middleware Orphan Repair** (P8) — 5 scénarios de paires préservées |
| `references/learn-claude-code/s07_skill_loading/code.py` | `_scan_skills`, `load_skill`, `_parse_frontmatter` | **Blueprint quasi direct de P10** : catalogue cheap en SYSTEM + chargement on-demand (Python natif) |
| `references/learn-claude-code/s12_task_system/code.py` | `Task`, `blockedBy`, `can_start`, `claim_task`, `complete_task` | Mini-orchestrateur DAG file-backed — cycle de vie plan (P6) + base escalade (P3) |
| `references/learn-claude-code/s06_subagent/code.py` | `spawn_subagent`, cap 30 tours, pas de récursion | Patron d'isolation des subagents pour Coder/Tester spécialisés (P0) |
| `references/learn-claude-code/s05_todo_write/code.py` | `nag reminder`, `_normalize_todos` | Persistence plan/todo + validation défensive (LLM envoie string au lieu de list) (P6) |
| `references/learn-claude-code/s20_comprehensive/code.py` (ou `agents/s_full.py`) | boucle agrégée | **Référence d'intégration** : compose hooks + compaction + task graph + error recovery dans une seule boucle. Point d'entrée recommandé |
| `references/learn-claude-code/skills/code-review/SKILL.md` | checklist Security/Correctness/… | Skill de revue réutilisable tel quel comme prompt de Judge (P6) |

### Bibliothèque de system prompts (system-prompts-and-models-of-ai-tools)
> 📚 **Matière première textuelle** (prompts extraits d'outils IA commerciaux + open-source). La valeur : (1) ~15 prompts d'agents de coding exploitables, (2) **10 invariants universels** identifiés (read-before-write, pas whole-file rewrite, test-first, approval gating, anti-boucle…). ⚠️ Biais JS/TS/React (80%) ; prompts leakés (préférer open-source pour citation verbatim). Pour P0 (spécialisation) et P6 (Judge/TDD).

| Fichier | Rôle(s) | Apport |
|---|---|---|
| `…/Open Source prompts/Codex CLI/openai-codex-cli-system-prompt-20250820.txt` | **Coder + Tester + Architect** | **Le plus aligned CLI** (342 L, open-source). 3 modes sandbox, 4 modes approval, philosophie test « specific→broad », format `apply_patch` |
| `…/Manus Agent Tools & Prompt/Prompt.txt` + `Modules.txt` + `Agent loop.txt` | **Router + Architect** | **Topologie multi-agent** (Planner/Knowledge/Datasource) + agent loop formel Analyze→Select→Wait→Iterate→Submit→Standby = blueprint Router→Architect→Coders |
| `…/Augment Code/gpt-5-agent-prompts.txt` | **Router + Coder** | Catégorisation des outils par purpose + Tasklist Triggers + Package Management (pip/poetry pour Python) |
| `…/Anthropic/Claude Code 2.0.txt` | **Coder + Judge + Security** | Git Safety Protocol, **professional objectivity** (truth > validation = base du Reviewer), read-before-edit, anti-syscall |
| `…/Open Source prompts/Gemini CLI/google-gemini-cli-system-prompt.txt` | **Coder + Tester + Judge** | Workflow **5 étapes** Understand→Plan→Implement→Verify Tests→Verify Standards. Ultra-dense (188 L, open-source) |
| `…/Devin AI/Prompt.txt` | **Architect + Tester** | **`<think>` tool 10 cas d'usage obligatoires** = base reasoning Architect/Judge ; « ne jamais modifier les tests » = règle Tester |
| `…/Cursor Prompts/Agent Prompt 2025-09-03.txt` | **Coder + Router** | status_update cadencé (tracing inter-agent), **anti-boucle linter max 3** puis ask user, maximize_parallel_tool_calls |
| `…/Open Source prompts/Cline/Prompt.txt` | **Coder + Security** | **Spec de référence SEARCH/REPLACE** (règles 1-4), `requires_approval` booléen par commande |
| `…/Traycer AI/phase_mode_prompts.txt` | **Architect pur** | **Read-only tech lead** (« You DO NOT write code »), 46 lignes. Modèle du Read-Only |
| **10 invariants universels** (section fiche 17) | **Tous les rôles** | read-before-write, pas whole-file rewrite, format d'édition formel, NEVER assume lib, test-first, approval gating, anti-boucle, concision, todo tracking, parallel tool calls |

### Doctrine du format SKILL.md (awesome-claude-skills)
> 🎓 **Patrimoine méthodologique** (pas du contenu métier — 25/30 skills sont business). La valeur : le **modèle 3-niveaux** (Progressive Disclosure) qui formalise exactement notre P10 (lazy loading), l'**outillage** de création/validation des skills, et `mcp-builder`. Gap identifié : nos skills sont mono-fichiers + chargées eager ; P10 corrige ça.

| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `…/skill-creator/SKILL.md` | `Progressive Disclosure`, `three-level loading`, `Metadata`, `SKILL.md body`, `Bundled resources` | **Doctrine du modèle 3-niveaux** : Metadata ~100 mots (toujours en contexte) → corps <5k mots (au déclenchement) → resources illimitées (scripts exécutés sans être lus). **Caution externe de P10** |
| `…/skill-creator/scripts/init_skill.py` | `init_skill`, scaffolding `SKILL.md` + 3 dossiers | Génère le squelette canonique d'une skill. À adapter en `scripts/new_skill.py` |
| `…/skill-creator/scripts/quick_validate.py` | `validate_frontmatter`, regex `^[a-z0-9-]+$`, check `<>` | Valide name/description/hyphen-case. **À adopter comme gate CI** sur `skills/` |
| `…/mcp-builder/SKILL.md` + `reference/mcp_best_practices.md` | `Build for Workflows`, `Optimize for Limited Context`, `Actionable Error Messages` | Manuel MCP + principes de design d'outils transposables aux « Hands » smolagents |
| `…/mcp-builder/reference/evaluation.md` | pattern « 10 QA XML + vérification » | Input pour le **nœud Judge** (cas de vérification) |
| `…/document-skills/docx/ooxml/scripts/pack.py` (+ `unpack.py`, `validate.py`) | manipulation zip OOXML | **Exemple le plus abouti de skill « scripts-heavy »** : découplage SKILL.md / scripts / references. « Exécuter sans lire la source » |
| `…/webapp-testing/scripts/with_server.py` | `wait_for_port`, cycle de vie serveur | Complément Playwright au **nœud Tester** (notre `web_tester` est Puppeteer) |
| **Format SKILL.md canonique** (section fiche 18) | frontmatter `name`+`description`, `When to Use`, `scripts/`+`references/`+`assets/` | Structure récurrente adoptée par la marketplace officielle Claude. Nos SKILL.md sont déjà compatibles (même frontmatter) |

### Compaction + Persistence + Skills + Sécurité (hermes-agent — 5 axes orthogonaux Python pur)
> 🏆 **Le dépôt le plus dense et portable du dossier.** Agent auto-amélioré de Nous Research (MIT, 8487 fichiers mais cœur utile dans ~15 fichiers Python). 5 axes orthogonaux couvrent P3/P8/P9/P10/P11 — souvent en **Python pur copiable quasi tel quel**, contrairement à qm (TypeScript) ou pi (TypeScript).

| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/hermes-agent/trajectory_compressor.py` | `TrajectoryCompressor`, `CompressionConfig`, `_find_protected_indices`, `_is_boundary_clean`, `_snap_boundary`, `_generate_summary` | **Compaction OFFLINE** : protège head+tail, "snappe" les boundaries pour ne pas couper une paire gpt→tool, summarise le milieu, budget cible. Python pur portable (P9) |
| `references/hermes-agent/agent/context_compressor.py` | `ContextCompressor`, `should_compress`, `record_completed_compaction`, `record_timeout_failure`, `get_active_compression_failure_cooldown`, `_persist_ineffective_compression_count` | **Compaction LIVE** avec **garde-fous persistés** : cooldown/streak/ineffective counter en DB = anti-loop de compaction qui manque au projet. Chevauchement P3+P9 |
| `references/hermes-agent/hermes_state_common.py` | `SCHEMA_SQL`, `FTS_SQL`, `FTS_TRIGRAM_SQL`, `_FTS_TRIGGERS`, `MAX_FTS5_QUERY_CHARS`, `SCHEMA_VERSION = 25` | **Schéma SQLite event-sourcing** : tables `sessions` (parent_session_id → lineage compaction), `messages`, `compression_locks` (verrou cross-process), `async_delegations` (subagents), FTS5 + trigram + sanitizer anti-injection. P11 |
| `references/hermes-agent/tools/skills_tool.py` (+ `skills_sync.py`, `skill_provenance.py`, `skills_guard.py`, `skills_ast_audit.py`) | `_find_all_skills`, `_parse_frontmatter`, `skill_matches_platform`, `sync_skills`, `_content_hash`, `set_current_write_origin` (contextvars), `ScanResult` (verdict safe/caution/dangerous), `ast_scan_path` | **Système skills agentskills.io complet** : format SKILL.md + sync/diff (hash) + **provenance contextvars** (qui a créé/modifié) + **guard regex** (verdict 3 niveaux + trust_level) + **AST audit** (imports dynamiques). P10 + P8 |
| `references/hermes-agent/tools/threat_patterns.py` (+ `approval.py`, `path_security.py`, `url_safety.py`) | `scan_for_threats(content, scope)`, `first_threat_message`, scopes `all`/`context`/`strict` ; `DANGEROUS_PATTERNS` (~260 regex), `detect_dangerous_command` ; `validate_within_dir`, `has_traversal_component` ; `is_safe_url`, `_is_blocked_ip`, `create_ssrf_safe_client`, `_SSRFGuardedNetworkBackend` | **Bibliothèque sécurité multi-couches Python pur** : threat patterns (injection/C2/frameworks offensifs/exfiltration) scope-aware + ~260 dangerous commands + path traversal blocker + **SSRF guards** (bloque IPs privées/métadonnées cloud). Copiable quasi tel quel pour le nœud Coder/Security. P3 + P0-bis + P8 |
| `references/hermes-agent/docs/middleware/README.md` | `llm_request`, `tool_request`, `llm_execution`, `tool_execution`, `hermes.middleware.v1`, `middleware_trace` | **Contrat middleware modèle** à 4 points d'extension avec `next_call` chain of responsibility + **fail-open** + traçabilité. Runtime context complet (session/task/turn/provider/model/tool). Blueprint P8 |
| `references/hermes-agent/tools/environments/base.py` | `BaseEnvironment` (ABC), `execute`, `_BoundedOutputCollector` (head+tail bounded, spill disk), `touch_activity_if_due` (heartbeat), `_pipe_stdin` (Windows-safe) | **ABC de sandbox** au contrat propre + output collector borné + heartbeat + stdin Windows-safe. Python pur (P1 + P8-bis) |
| `references/hermes-agent/agent/error_classifier.py` | `FailoverReason`, `ClassifiedError`, `classify_api_error`, `_classify_400`/`_classify_402`/`_classify_by_status`/`_classify_by_message` | **Taxonomie fine d'erreurs API LLM** (400/402/by status/message/error_code) pour diagnostics failover. Python pur portable direct (P8 + P6) |

### Résilience transport & lifecycle sandbox (OpenSandbox)
> 🛡️ **L'infrastructure d'exécution qui manquait** (ex-Alibaba, Apache-2.0, CNCF Landscape). Python pur copiable pour le transport/MCP/middlewares ; spec OpenAPI pour le contrat du rejouable (P8-bis). Runtime Go/K8s hors scope — on prend le contrat et le client.

| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/OpenSandbox/sdks/sandbox/python/src/opensandbox/transport/retry.py` | `RetryPolicy`, `RetryCause`, `JitterMode.DECORRELATED` | **LE middleware P8 en Python pur** : backoff x2 plafonné + jitter décorrélé, codes retryables idempotent vs non-idempotent, `per_attempt_timeout` + `overall_deadline`, hook `on_retry`. Design documenté dans `oseps/0017` |
| `references/OpenSandbox/sdks/sandbox/python/src/opensandbox/transport/_async_retry.py` | `RetryAsyncTransport.handle_async_request` | Deadline mur-mur, clamp des timeouts par phase, `Retry-After` honoré et plafonné, sleep clampé au budget restant, `CancelledError` jamais avalé |
| `references/OpenSandbox/sdks/sandbox/python/src/opensandbox/transport/_classify.py` | `classify_transport_exception`, `is_body_replayable` | Classification pré-send (safe sur toute méthode) vs post-send (idempotents seulement) — le cœur sémantique du retry correct |
| `references/OpenSandbox/specs/sandbox-lifecycle.yml` | `/sandboxes 202+polling`, `renew-expiration`, `/snapshots`, endpoints signés | **Contrat du lifecycle rejouable** (P8-bis) : machine à états, TTL absolu renouvelable, snapshot/restore asynchrones, télémétrie fire-and-forget |
| `references/OpenSandbox/server/opensandbox_server/middleware/request_id.py` | `request_id_ctx`, `RequestIdMiddleware`, `RequestIdFilter` | Corrélation des logs par ContextVar en ~30 lignes (P11) |
| `references/OpenSandbox/examples/langgraph/main.py` | `WorkflowState`, `fallback_command`, `decide_next` | Anti-loop illustrée : self-loop bornée + fallback différencié à chaque retry + cleanup en `finally` (P3) |

### Mécanismes de harness : anti-loop, retry durable, compaction, event log (deepseek-harness)
> 🔁 **La meilleure référence de design sur P3 et P11** (DeepSeek AI, MIT, TS/Cordis « everything is a plugin », invariant-driven). On porte l'intention, pas la syntaxe. P6 explicitement absent (self-declaration documentée).

| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/deepseek-harness/packages/guard/repeat-tool-reminder/src/index.ts` | `Config.thresholds [3,5,8]`, `canonicalize`, `Chain`, `observe()`, `prependContext()` | **Détecteur de répétitions consécutives** d'appels d'outils (clé = nom + arguments canonisés) avec escalade douce sans veto — portage Python ~150 lignes, complément doux au LoopGuard F-36 (P3) |
| `references/deepseek-harness/packages/workflow/tool-ralph/README.md` | `ralph(objective, maxRounds)`, handoff `status/evidence/nextSteps`, `maxHandoffChars` | **Boucle à agents frais** : objectif immuable, contexte remis à zéro chaque round, handoff borné = seul transfert (P3 radical). Documente la limite « no independent evaluator » (P6) |
| `references/deepseek-harness/packages/llm/llm-retry/src/index.ts` | `localDelay`, `recover()`, `providerRetryAfterMs` | **Retry durable** : compteur persisté dans le log de session → survit à un crash/restart (P8) |
| `references/deepseek-harness/packages/compaction/compaction-basic/src/summarizer.ts` | `COMPACTION_INSTRUCTION` (8 sections), `summarizeWithLlm`, `finishError` | **Prompt de checkpoint 8 sections** + réutilisation du KV cache (préfixe identique) + fail-closed si tronqué (P9) |
| `references/deepseek-harness/packages/core/session/src/types.ts` | `SessionEventMap`, `SessionEvent.ignorable?`, `SurfaceOp`, `sourceEventSeqs` | **Event log typé extensible avec provenance** — le plus abouti du dossier ; convention « Model-visible ⟺ logged » (P11) |
| `references/deepseek-harness/AGENTS.md` | « Registrations are effects », « Model-visible ⟺ logged », « Misconfiguration fails loud » | **Charte d'invariants** exigés de tout plugin — source directe pour enrichir `UNIVERSAL_INVARIANTS` (P0-bis) |

### Orchestration multi-worktrees & Compaction résiliente aux gros payloads (kilocode)
> 🌳 **Isolation complète des itérations et résilience aux context overflows multimédia.** Kilo Code apporte le gestionnaire de git worktrees (`WorktreeManager`) permettant d'exécuter des runs dans des branches dédiées sans collision, et résout les plantages de compaction sur les historiques riches en screenshots via `KiloCompactionPayloadRecovery`.

| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/kilocode/packages/kilo-vscode/src/agent-manager/WorktreeManager.ts` | `WorktreeManager`, `createWorktree`, `cleanupWorktree`, `RM_OPTS` | **Gestionnaire de cycle de vie des git worktrees** (`.kilo/worktrees/`) avec suppression récursive résiliente et multi-versioning (P12+P3) |
| `references/kilocode/packages/opencode/src/kilocode/session/compaction-payload-recovery.ts` | `KiloCompactionPayloadRecovery`, `matches`, `strip` | **Sauvetage des erreurs 4MB/payload overflow** : stripping rétroactif des tool outputs et conversion des screenshots/médias en placeholders texte (P9) |
| `references/kilocode/packages/opencode/src/kilocode/session/compaction-chunks.ts` | `KiloCompactionChunks`, `replay`, `summarize` | **Compaction récursive par chunks** (profondeur max 3, ratio 0.6) avec requêtes synthétiques de rejeu pour très longs historiques (P9) |
| `references/kilocode/packages/codemode/src/codemode.ts` (+ `runtime.ts`) | `CodeMode`, `ExecutionLimits`, `DiagnosticKind` | **Interpréteur JS confiné par AST walk** avec quotas stricts (timeout, max tool calls) et diagnostics normalisés (P8-bis+P8) |
| `references/kilocode/packages/kilo-memory/src/memory.ts` (+ `schema.ts`, `decisions.ts`) | `Memory`, `MemorySchema`, `MemoryDecisions` | **Mémoire structurée multi-fichiers** avec journal append-only des décisions (accepted/skipped/fallback) et digest 4KB (P6+P11) |
| `references/kilocode/packages/opencode/src/kilocode/snapshot/diff-full.ts` | `DiffFull.batch`, `MAX_DETAIL_SIZE` | **Calcul de diff git natif par tranches de 500 fichiers** (contournement limite Windows 8191 chars) avec repli doux (P1+P6) |
| `references/kilocode/packages/opencode/src/kilocode/permission/config-paths.ts` | `ConfigProtection`, `CONFIG_ROOT_FILES` | **Garde-fou interdisant au LLM d'auto-modifier ses fichiers de règles** (`kilo.json`, `AGENTS.md`) sans validation humaine (P0-bis+P8) |

### Concision & Anti-Over-Engineering (ponytail)
> ✂️ **La doctrine universelle de sobriété pour agents de coding.** Benchmarks prouvés (-54% LOC, -22% tokens, 100% safe) et format 1 ligne/finding pour le Judge.

| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/ponytail/.agents/rules/ponytail.md` | `The Ponytail Ladder` (Rungs 1-7), `Bug fix = root cause` | **Échelle de décision YAGNI en 7 rungs** : directives de parcimonie à injecter dans les prompts Coder/Drafter |
| `references/ponytail/.openclaw/skills/ponytail-review/SKILL.md` | `ponytail-review`, `delete:`, `stdlib:`, `native:`, `yagni:`, `shrink:`, `net: -<N> lines` | **Format de revue de diff concis** (1 ligne par finding) pour le Judge |
| `references/ponytail/.openclaw/skills/ponytail-audit/SKILL.md` | `ponytail-audit`, `Hunt`, `Output` | **Audit statique de complexité** pour traquer le code mort et les wrappers inutiles |

### Navigateur Headless Léger & Serveur MCP (obscura)
> 🌐 **L'alternative légère à Chromium (~30 Mo RAM, 85 ms load) avec serveur MCP stable.**

| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/obscura/crates/obscura-mcp/src/lib.rs` | `BrowserState`, `DEFAULT_TEXT_LIMIT = 4000`, `interactive_refs` (`e3`, `e4`), `page_mut` | **Serveur MCP pour agent** : identifiants stables par snapshot au lieu de sélecteurs CSS fragiles + plafond strict 4000 chars |
| `references/obscura/crates/obscura-browser/src/lifecycle.rs` | `PageLifecycle`, `NavigationState`, `waitFor` | **Machine à états de cycle de vie de page** (DOM ready, network idle) pour éliminer les flaky tests |
| `references/obscura/crates/obscura-render/src/paint.rs` | `Renderer`, `paint_tree`, `capture_frame` | **Rendu graphique 2D pur (tiny-skia)** sans GPU lourd pour capture de screenshots |

### TUI Diff Review & Annotations IA (hunk)
> 📝 **Standard d'annotations inline pour agents IA et protection du workspace.**

| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/hunk/src/ui/lib/agentAnnotations.ts` | `AgentAnnotation`, `AgentNote`, `AgentAnnotationSeverity` | **Modèle de données d'annotations inline IA** (ligne/hunk, sévérité, ancrage) pour le Judge |
| `references/hunk/src/ui/lib/workspaceWriteGuard.ts` | `WorkspaceWriteGuard`, `assertWritable`, `acquireWriteLock` | **Garde-fou d'écriture** : verrouillage du workspace pendant les passes de review et de test |
| `references/hunk/src/ui/highlights/reconcile.ts` | `reconcileHighlights`, `mapLinePositions` | **Réconciliation de positions de lignes** lors de modifications de patchs |
| `references/hunk/packages/session-broker/src/broker.ts` | `SessionBroker`, `registerSession`, `routeMessage` | **Démon broker de sessions** avec baux temporisés pour revue concurrente |

### Guardrails Modulaires & Sécurité Entrée/Sortie (bytechef)
> 🛡️ **Batterie complète de 12 guardrails pour sécuriser les flux agents.**

| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/bytechef/server/libs/core/guardrails/guardrails-impl/src/main/java/com/bytechef/guardrails/util/SecretKeyDetectorUtils.java` | `SecretKeyDetectorUtils`, `detectSecrets`, `isLikelySecret` | **Détection haute précision de clés d'API et tokens** dans les invites et sorties LLM |
| `references/bytechef/server/libs/core/guardrails/guardrails-impl/src/main/java/com/bytechef/guardrails/util/PiiDetectorUtils.java` | `PiiDetectorUtils`, `detectPii`, `maskPii` | **Détection et masquage PII** (emails, téléphones, identifiants) |
| `references/bytechef/server/libs/core/guardrails/guardrails-impl/src/main/java/com/bytechef/guardrails/advisor/CheckForViolationsAdvisor.java` | `CheckForViolationsAdvisor`, `validateInputOutput`, `collectViolations` | **Advisor d'interception d'invites/sorties** compilant l'ensemble des violations de sécurité |
| `references/bytechef/server/ee/libs/platform/platform-mcp/platform-mcp-impl/src/main/java/com/bytechef/platform/mcp/McpServerFacade.java` | `McpServerFacade`, `listTools`, `executeTool` | **Façade MCP bidirectionnelle** pour consommation et exposition d'outils |

### Méta-harnais, vision critic forké & process supervision (AutoDesign)
> 🎨 **Architecture double-boucle d'optimisation de harnais, critique visuelle autonome et supervision de sous-processus robuste.**

| Fichier | Symbole(s) clé(s) | Apport |
|---|---|---|
| `references/AutoDesign/autodesign/agents/critic_agent.py` | `CriticAgent`, `CritiqueReport`, `report_verdict` | **Sous-agent de critique visuelle forké autonome** avec propre boucle LLM, budget de tours indépendant et outils de vérification ciblés (`read_slide_render`, `read_paper_section`) (P6) |
| `references/AutoDesign/autodesign/agents/claim_graph_extractor.py` | `ClaimGraphExtractor`, `EXTRACT_FAIL_THESIS`, `report_claim_graph` | **Extraction structurée de graphes de claims** avec citation textuelle obligatoire et dégradation gracieuse (P0/P6) |
| `references/AutoDesign/autodesign/process_supervision.py` | `ProcessIdentity`, `ProcessRecord`, `SpawnIntent`, `_configure_windows_api` | **Supervision durable et terminaison d'arbre de processus** via Windows Job Objects (Win32 ctypes) et groupes POSIX sans orphelins (P8) |
| `references/AutoDesign/autodesign/agents/atomic_artifact_promotion.py` | `publish_artifact_directory`, `recover_artifact_promotion` | **Promotion atomique crash-safe** de répertoires avec journal réversible et rollback (`prepared` -> `backup_created` -> `final_installed` -> `committed`) (P8-bis) |
| `references/AutoDesign/autodesign/candidate_assessment.py` | `DeliveryAssessment`, `_QUALITY_ONLY_ISSUES`, `assess_candidate_delivery` | **Séparation formelle hard blockers vs diagnostics qualitatifs** anti-boucle de rejet infini (P3) |
| `references/AutoDesign/autodesign/skills/registry.py` | `SkillManifest`, `SkillResource`, `SkillPack`, `select_skills` | **Registre de skills v2** avec chargement à la demande (`SkillResource`, `when_to_read`, `stages`) et budget description <= 160 car. (P10) |
| `references/AutoDesign/autodesign/util/claim_graph_validator.py` | `validate_claim_graph`, `_norm_ws` | **Validateur déterministe d'inclusion textuelle stricte** anti-hallucination (`raw_quote` dans `paper_raw_text`) (P0-bis/P6) |
| `references/AutoDesign/autodesign/util/provenance.py` | `validate_provenance`, `ProvenanceReport`, `_NUMERIC_RE` | **Audit déterministe anti-hallucination numérique** forçant l'ancrage sur citations de sources (P0-bis/P6) |

---

## 📊 Matrice réutilisabilité croisée

| Projet | 🟢 Haute | 🟡 Moyenne | 🔴 Faible | Note globale |
|---|---|---|---|---|
| Prompt-Vault | 13 | 0 | 0 | 🟢 Haute |
| aider | 17 | 15 | 6 | 🟢 Haute |
| nanocode | 1 | 7 | 3 | 🟡 Moyenne |
| RepoGraph | 8 | 5 | 3 | 🟢 Haute |
| axon | 23 | 5 | 1 | 🟢 Haute |
| graphify | 11 | 8 | 2 | 🟢 Haute |
| LlamaBot | 5 | 17 | 6 | 🟡 Moyenne |
| deer-flow | 21 | 23 | 2 | 🟡 Moyenne |
| open-swe | 11 | 14 | 5 | 🟡 Moyenne |
| crush | 1 | 14 | 10 | 🟡 Moyenne |
| opencode | 0 | 4 | 22 | 🔴 Faible |
| openfox | 3 | 4 | 18 | 🔴 Faible |
| deer-flow-analysis | 5 | 0 | 0 | 🟢 Haute |
| **qm** | **17** | **10** | **1** | 🟢 **Haute** |
| **claude-code-unified-agents** | **7** | **5** | **1** | 🟡 **Moyenne** |
| **learn-claude-code** | **11** | **5** | **2** | 🟢 **Haute** |
| **system-prompts-and-models-of-ai-tools** | **12** | **5** | **0** | 🟢 **Haute** |
| **awesome-claude-skills** | **5** | **6** | **0** | 🟡 **Moyenne** |
| **loopx** | **8** | **2** | **0** | 🟢 **Haute** |
| **code-review-graph** | **6** | **4** | **0** | 🟡 **Moyenne** |
| **davidondrej-skills** | **3** | **3** | **0** | 🟡 **Moyenne** |
| **llm-council** | **1** | **1** | **2** | 🟡 **Moyenne** |
| **mattpocock-skills** | **6** | **3** | **0** | 🟢 **Haute** |
| **pi** | **3** | **4** | **0** | 🟢 **Haute** |
| **hermes-agent** | **15** | **13** | **0** | 🟢 **Haute** |
| **cloudflare-os** | **0** | **3** | **0** | 🟡 **Moyenne** |
| **browser-use** | **3** | **3** | **0** | 🟢 **Haute** |
| **TencentDB-Agent-Memory** | **8** | **5** | **0** | 🟢 **Haute** |
| **OpenSandbox** | **14** | **7** | **1** | 🟢 **Haute** |
| **deepseek-harness** | **13** | **9** | **2** | 🟢 **Haute** |
| **kilocode** | **14** | **5** | **0** | 🟢 **Haute** |
| **ponytail** | **4** | **4** | **0** | 🟢 **Haute** |
| **obscura** | **6** | **3** | **0** | 🟢 **Haute** |
| **hunk** | **9** | **0** | **0** | 🟢 **Haute** |
| **bytechef** | **6** | **2** | **0** | 🟡 **Moyenne** |
| **AutoDesign** | **18** | **1** | **0** | 🟢 **Haute** |
| **Total** | **308** | **219** | **87** | — |

> ℹ️ Le total de la matrice (614 = 308+219+87) couvre les fiches 01-28 et 45-52. Les fiches 29-44 (ajout en masse du 2026-08-12) n'ont pas été intégrées à la matrice — leurs comptes par projet sont consultables programmatiquement dans [`inventory.json`](./inventory.json), qui fait foi : **687 entrées machine au total (356 H / 242 M / 87 L / 2 non classées)**.

**Constats** :
- **axon** (23 Haute) et **aider** (17 Haute) restent les mines d'or côté Python.
- **qm** (17 Haute) rejoint le peloton de tête : malgré le TypeScript, ses algorithmes de **compaction de contexte, mémoire durable, idempotency et queues à leases** sont portables. (L'ancienne fiche la notait Moyenne à tort.)
- **learn-claude-code** (11 Haute, 🟢 Haute) : la référence la plus **directement exploitable** pour les briques transversales (hooks, compaction, error recovery, skill loading, task DAG) car **Python natif** — portage quasi littéral, contrairement à qm (TS).
- **system-prompts-and-models-of-ai-tools** (12 Haute, 🟢 Haute) : **bibliothèque de patterns** pour les system_prompts. 10 invariants universels identifiés (read-before-write, test-first, approval gating…). À utiliser comme matière première pour P0 (spécialisation) et P6 (Judge/TDD).
- **awesome-claude-skills** (5 Haute, 🟡 Moyenne) : valeur = **patrimoine méthodologique** (format SKILL.md, modèle 3-niveaux, outillage) pas le contenu métier (25/30 skills business). Pivot pour P10.
- **deer-flow** (21 Haute) malgré une note globale Moyenne — la valeur est dans les contracts/plans/middlewares.
- **claude-code-unified-agents** : 7 prompts purs 🟢 (alignés avec les rôles du graphe), mais la majorité des 53 fichiers est du code TS non portable → note Moyenne. (L'ancienne fiche la notait Haute à tort.)
- **opencode/openfox** (TS) : peu de Haute, leurs **specs/docs** restent des références conceptuelles au mieux.
- **loopx** (8 Haute, 🟢 Haute) : le **complément déterministe manquant à crush (10)** pour P3 — au lieu d'un simple hash d'output, loopx apporte un stall detector (seuil=2, ignore le bookkeeping), un vocabulaire de delivery_outcome (accountable/progress/idle) et un modèle de turn transaction (turns productifs vs gratuits). Couvre aussi P9 (compaction par whitelist de champs) et P11 (event sourcing idempotent + ledger 5 classes). Stdlib pure, zéro dépendance → portable direct, mais code verbeux (extraire les algorithmes, pas copier).
- **code-review-graph** (6 Haute, 🟡 Moyenne) : apporte des **signaux quantitatifs** au Judge (aujourd'hui uniquement qualitatif LLM) — `compute_risk_score` ∈ [0,1] multi-facteurs + buckets 0.7/0.4 + `IMPACT_EDGE_WEIGHTS`. Le runtime (MCP+SQLite+Tree-sitter) ne se porte pas, on transpose les modèles de scoring.
- **mattpocock-skills** (6 Haute, 🟢 Haute) : **pivot de la fusion doctrine P10** (avec awesome-claude-skills 18 + davidondrej 21) — le seul des 3 qui formalise une *théorie* de l'authoring (Predictability, deux charges, hiérarchie 3 rungs) plutôt qu'une collection.
- **davidondrej-skills** (3 Haute, 🟡 Moyenne) : **enrichit directement notre `bash_guard.py` (F-38)** de patterns manquants (gh delete, fork bomb, `curl|sh`, reflog expire) + doctrine fail-open + ~115 tests prêts à porter. ⚠️ Correction procédure : « 52 regex » = en réalité **27 regex** (fichier de 52 lignes).
- **llm-council** (🟡 Moyenne) : un seul pattern utile (council anonymisé A/B/C + Borda) pour valider des findings à enjeu, mais **réserves majeures** (vibe-coded, coût 2N+1 appels, OpenRouter payant) → à traiter comme inspiration, pas dépendance.
- **pi** (3 Haute, 🟢 Haute) : très forte valeur sur **P9 (compaction basée sur l'état fichier)** et **branch summarization**, approche complémentaire et mature à qm/loopx. Son TDD harness valide statistiquement nos choix P6.
- **hermes-agent** (15 Haute, 🟢 Haute) : **le dépôt le plus dense et portable du dossier sur 5 axes orthogonaux**. Compaction offline (`trajectory_compressor`) + live avec garde-fous persistés (`context_compressor` cooldown/streak/ineffective), persistence SQLite FTS5 + lineage + event-sourcing subagents, skills agentskills.io avec provenance contextvars + guard + AST audit, **bibliothèque sécurité Python pur copiable quasi telle quelle** (threat patterns + ~260 dangerous commands + SSRF guards + path traversal), contrat middleware 4 kinds avec `next_call` chain + fail-open. Cœur utile concentré dans ~15 fichiers Python (malgré 8487 fichiers au total). Rejoint le peloton de tête avec axon (23 Haute) et aider (17 Haute). Réserves : pas DuckDB (transposer le pattern), adapters LLM cloud massifs non portables, god-files à découper.
- **cloudflare-os** (3 Moyenne, 🟡 Moyenne) : apporte un excellent pattern architectural de sécurité (**Gatekeepers**, Capability-based access control) et d'approbation asynchrone (human in the loop par simulation). Même si TS, la doctrine inspire fortement la gestion MCP.
- **TencentDB-Agent-Memory** (8 Haute, 🟢 **Haute** — renotée 2026-08-07) : la fiche initiale était superficielle (4 briques, notée Moyenne). L'audit approfondi des **prompts** révèle un gisement complémentaire à qm pour **P6-ter (F-68)** : là où qm fournit le contrat de persistance scratch/notebook (`recall`/`capture`/`replaceIfRevision`), TencentDB couvre les **3 maillons que qm ne couvre pas** — (a) **extraction L1** d'atomes (3 principes : qualité>quantité, valide hors-contexte, fusion causale ; dualité chat/code), (b) **dédup L1** par `store/skip/update/merge` **supérieure** au `UPDATE/DELETE/ADD` de qm (merge cross-type + many-to-many + bump priorité), (c) **oubli par chaleur** (heat : new=1/update=old+1/merge=sum+1 + `[DELETED]`) qui manque totalement à notre KG. Bonus : **Skill Review gate** 5-critères + 4-dim/100pts (P10/F-87), **context-offload Mermaid scoré** + cognitive tombstones (P9/F-86). Ce sont des **prompts** TypeScript, transposables quasi-directement (pas du code runtime). Les 2 références qm+TencentDB sont **nécessaires ensemble** pour F-68.
- **OpenSandbox** (14 Haute, 🟢 **Haute** — 2026-08-14) : le **complément d'infrastructure d'exécution** qui manquait au dossier. Ce n'est pas un orchestrateur (pas de Judge/TDD) mais la plateforme qui **exécute** le code généré de façon isolée/timeoutée/snapshotable/rejouable — exactement P8-bis. La pépite : le module `transport/` du SDK Python est **LE middleware P8 en Python pur copiable** (classification pré/post-send, jitter décorrélé, deadline mur-mur, `Retry-After` plafonné — design documenté OSEP-0017). La spec OpenAPI `sandbox-lifecycle.yml` fournit le **contrat** du rejouable (202 Biss+polling, TTL renew, snapshot/restore, endpoints signés) quand qm (14) fournissait l'idempotence applicative. Bonus P0 : AGENTS.md hiérarchiques (« le plus proche gagne » + Guardrails Always/Ask-first/Never). Runtime Go/K8s ignoré — on prend le contrat et le client.
- **deepseek-harness** (13 Haute, 🟢 **Haute** — 2026-08-14) : **la meilleure référence de design sur P3 et P11**. Anti-loop en deux couches complémentaires : `repeat-tool-reminder` (détection douce de répétitions consécutives, escalade sans veto — le complément humain à notre LoopGuard F-36 et au stall detector loopx 19) et la **boucle ralph à agents frais** (contexte remis à zéro chaque round + handoff borné — la contre-mesure radicale). P11 : l'event log de session est **le plus abouti du dossier** (types extensibles par declaration merging, provenance `sourceEventSeqs`, flag `ignorable` = fail-closed sur type inconnu, convention « Model-visible ⟺ logged »). P9 : le prompt de checkpoint **8 sections** avec réutilisation du KV cache. P8 : retry durable **dont le compteur survit à un crash** (persisté dans le log) + spec des 5 waterfalls d'exécution d'outil. TypeScript/Cordis : on porte l'intention, pas la syntaxe ; P6 explicitement absent (self-declaration documentée comme limite — argument de plus pour notre Judge indépendant).
- **kilocode** (14 Haute, 🟢 **Haute** — 2026-08-17) : **mine d'or architecturale pour l'isolation multi-worktrees, la compaction résiliente aux médias et le confinement d'outils**. (1) L'**Agent Manager** (`WorktreeManager`) fournit le blueprint complet pour exécuter des sessions de génération/test parallèles dans des git worktrees indépendants (`.kilo/worktrees/`) sans collision (P12/P3). (2) `KiloCompactionPayloadRecovery` résout les context overflows de 4MB dus à l'accumulation de screenshots/médias par stripping des tool outputs achevés et substitution en placeholders texte (P9). (3) `KiloCompactionChunks` apporte la compaction hiérarchique récursive par chunks (arbre profondeur 3, ratio 0.6) avec requêtes synthétiques de rejeu (P9). (4) `codemode` fournit un interpréteur JS confiné par AST walk avec quotas stricts (timeout, max tool calls) et diagnostics normalisés (P8-bis/P8). (5) `ConfigProtection` interdit au LLM de modifier ses propres fichiers de règles (`kilo.json`, `AGENTS.md`) sans validation humaine explicite (P0-bis/P8).
- **ponytail** (4 Haute, 🟢 **Haute** — 2026-08-20) : **doctrine de sobriété et de concision anti-over-engineering**. Apporte l'échelle YAGNI en 7 rungs (YAGNI -> codebase -> stdlib -> platform -> installed deps -> one-line -> minimal code) prouvée scientifiquement par benchmarks agentiques (-54% LOC, -22% tokens, 100% safe), et le format 1 ligne/finding (`delete:`, `stdlib:`, `native:`, `yagni:`, `shrink:`) pour le Judge.
- **obscura** (6 Haute, 🟢 **Haute** — 2026-08-20) : **moteur de navigateur headless ultra-léger (~30 Mo RAM vs 200+ Mo Chromium)** écrit en Rust avec V8. Apporte la table d'identifiants stables `interactive_refs` (`e3`, `e4`) évitant les sélecteurs CSS fragiles, le plafond strict `DEFAULT_TEXT_LIMIT = 4000` anti-saturation de contexte LLM, et le rendu 2D pur (tiny-skia) sans GPU.
- **hunk** (9 Haute, 🟢 **Haute** — 2026-08-20) : **visualiseur et réviseur de diffs en terminal (TUI) conçu pour agents IA**. Apporte le standard de données d'annotations inline pour le Judge (`agentAnnotations.ts`), le verrouillage strict du workspace en lecture (`workspaceWriteGuard.ts`), et le daemon `session-broker` pour le multiplexage de flux de revue.
- **bytechef** (6 Haute, 🟡 **Moyenne** — 2026-08-20) : **plateforme d'orchestration d'entreprise et 12 guardrails modulaires**. Apporte des détecteurs de pointe pour les clés d'API / secrets (`SecretKeyDetectorUtils`), les données PII (`PiiDetectorUtils`), l'alignement thématique (`TopicalAlignment`) et l'assainissement de texte (`SanitizeTextAdvisor`).
- **AutoDesign** (18 Haute, 🟢 **Haute** — 2026-08-24) : **méta-harnais multi-agents, vision-critic forké autonome et supervision de processus robuste**. Apporte (1) le patron de **sous-agent forké CriticAgent** avec vision multi-modalité et budget de tours autonome (P6), (2) l'extraction et la **validation stricte d'inclusion textuelle des faits (ClaimGraphExtractor + validate_claim_graph + validate_provenance)** bannissant les hallucinations chiffrées (P0-bis/P6), (3) la **supervision durable de processus et terminaison d'arbre (process_supervision.py)** via Windows Job Objects Win32 ctypes et groupes POSIX anti-processus zombies (P8), (4) la **séparation formelle hard blockers vs diagnostics qualitatifs (candidate_assessment.py)** pour éviter les boucles de rejet infini (P3), (5) la **promotion atomique crash-safe de livrables (atomic_artifact_promotion.py)** avec journal réversible (P8-bis), et (6) le **registre de skills v2 (skills/registry.py)** avec Progressive Disclosure des ressources et contrainte budgétaire sur descriptions (P10). Cœur Python pur et Playwright directement exploitable.


---

## 🔍 Guide de recherche — « comment retrouver X »

| Je cherche… | Où aller |
|---|---|
| Un format d'édition fiable pour les Coders (vs whole-file) | Fiche **02-aider** → `editblock_coder.py`, `patch_coder.py`, `search_replace.py` |
| Comment représenter la structure du code dans le KG | Fiches **05-axon**, **04-repograph**, **06-graphify** (le trio knowledge graph) |
| Un anti-loop / circuit-breaker pour les Coders | Fiche **10-crush** → `loop_detection.go` ; **07-llamabot** → `FailureCircuitBreakerMiddleware` |
| Un modèle de nœud Tester (TDD, RED→GREEN) | Fiche **07-llamabot** → `rails_testing_agent/nodes.py` (6 stages) |
| Un modèle de nœud Judge (findings de revue) | Fiche **09-open-swe** → `review/findings.py`, `review/style_guidance.py` |
| Comment exposer le KG aux agents via MCP | Fiche **05-axon** → `mcp/server.py`, `mcp/tools.py` |
| Un cas de test pour benchmarker le workflow | Fiche **01-prompt-vault** → `Easy/Bubble_Sort_Visualizer.md` (entrée recommandée) |
| Un modèle de persistance event-sourcing | Fiche **12-openfox** → `docs/SESSION-DEBUGGING.md` ; **08-deer-flow** → `event-store-history.md` |
| Une spec de protocole d'événements versionné | Fiche **08-deer-flow** → `contracts/run_event_stream_contract.json` |
| Un pattern Architect → Editor (Brains/Hands) | Fiche **02-aider** → `architect_coder.py` |
| Compresser le code pour le contexte LLM | Fiche **04-repograph** → `compress_file.py` (`get_skeleton`) |
| Un web scraper (Playwright) | Fiche **02-aider** → `scrape.py` |
| Les 3 idées actionnables clés | Fiche **13-deer-flow-analysis** (note de synthèse) |
| **Compacter l'historique de contexte** (LLM context overflow) | Fiche **24-pi** → `compaction.ts` (basé sur file state) ; Fiche **14-qm** → `harness/context-compaction.ts` (`planCompaction`) + `core/orchestrator/compaction.ts` (duale sync+async) |
| **Résumé de branche (branch summarization)** | Fiche **24-pi** → `branch-summarization.ts` (pour undo et préservation apprentissage) |
| **Consolider le knowledge graph** (LLM-juge de claims) | Fiche **14-qm** → `memory/strategies/consolidation.ts` (`UPDATE`/`DELETE`/`ADD`) |
| **Garantir un effet de bord unique** (idempotence des retries) | Fiche **14-qm** → `idempotency/idempotency-store.ts` (`once(key, fn)`) |
| **Contrôler le coût LLM** (budget USD, fenêtre glissante) | Fiche **14-qm** → `ratelimit/budget.ts` (`createBudgetTracker`, `estimateCostUsd`) |
| Un **system prompt** pour le Judge / Reviewer | Fiche **15-claude-code** → `quality/code-reviewer.md` (Critical/Major/Minor, lecture seule) |
| Un **system prompt** pour le Security Reviewer | Fiche **15-claude-code** → `quality/security-auditor.md` (OWASP, CVSS) |
| Un **system prompt** pour le Coder Python | Fiche **15-claude-code** → `development/python-pro.md` (type hints, PEP 8) |
| Un schéma pour **déclarer formellement un agent** | Fiche **15-claude-code** → `specialized/agent-generator.md` (`AgentCapabilitySchema`) |
| **Une architecture de middlewares** (hooks/events, Python natif) | Fiche **16-learn-claude-code** → `s04_hooks/code.py` (`HOOKS[event]`, `trigger_hooks`) |
| **Un middleware anti-crash** (retry, backoff, fallback model) | Fiche **16-learn-claude-code** → `s11_error_recovery/code.py` (`with_retry`, `RecoveryState`) |
| **Compacter le contexte** (version Python, avec tests) | Fiche **16-learn-claude-code** → `s08_context_compact/code.py` (4 couches) ; version TS plus mature en fiche **14-qm** |
| **Charger les skills à la demande** (lazy, Python natif) | Fiche **16-learn-claude-code** → `s07_skill_loading/code.py` (`load_skill`, `_scan_skills`) |
| **Un système de tâches avec dépendances** (DAG) | Fiche **16-learn-claude-code** → `s12_task_system/code.py` (`blockedBy`, `can_start`) |
| **Instancier un subagent isolé** (contexte frais, cap tours) | Fiche **16-learn-claude-code** → `s06_subagent/code.py` (`spawn_subagent`) |
| Un **system prompt** de référence pour agent de coding | Fiche **17-system-prompts** → `Codex CLI` (342 L, le plus aligned CLI), `Gemini CLI` (188 L), `Claude Code 2.0` |
| Une **topologie multi-agent** (Planner/modules/agent loop) | Fiche **17-system-prompts** → `Manus/Prompt.txt` + `Modules.txt` + `Agent loop.txt` |
| Une base pour le **reasoning** de l'Architect (`<think>` tool) | Fiche **17-system-prompts** → `Devin AI/Prompt.txt` (10 cas d'usage obligatoires) |
| Les **invariants universels** des prompts d'agents de coding | Fiche **17-system-prompts** → section « 10 invariants universels » (read-before-write, test-first, approval gating, anti-boucle…) |
| Un **patron d'approval gating** pour actions destructives | Fiche **17-system-prompts** → `Cline` (`requires_approval`), `Replit` (`is_dangerous`), `Codex CLI` (4 modes approval) |
| Une **spec du format SEARCH/REPLACE** (règles exhaustives) | Fiche **17-system-prompts** → `Cline/Prompt.txt` (règles 1-4 + move/delete) |
| Des **schémas de function-calling** pour concevoir nos tools | Fiche **17-system-prompts** → `Cursor Prompts/Agent Tools v1.0.json`, `Replit/Tools.json` |
| La **doctrine du format SKILL.md** (modèle 3-niveaux, progressive disclosure) | Fiche **18-awesome-claude-skills** → `skill-creator/SKILL.md` (§Progressive Disclosure) |
| Un **outil de scaffolding/validation** pour nos skills | Fiche **18-awesome-claude-skills** → `skill-creator/scripts/init_skill.py` + `quick_validate.py` |
| Un **manuel pour construire un serveur MCP** | Fiche **18-awesome-claude-skills** → `mcp-builder/SKILL.md` + `reference/python_mcp_server.md` |
| Un **pattern de cycle de vie serveur** pour le Tester (Playwright) | Fiche **18-awesome-claude-skills** → `webapp-testing/scripts/with_server.py` |
| Un **anti-loop déterministe** (au-delà du hash d'output) | Fiche **19-loopx** → `control_plane/quota/recent_runs.py` (stall detector seuil=2, ignore bookkeeping) + `capabilities/issue_fix/pr_monitor_materialization.py` (`result_hash`/`material_change`) |
| Classifier chaque itération Coder→Tester (productif vs gratuit) | Fiche **19-loopx** → `control_plane/work_items/delivery_outcome.py` (`DeliveryOutcome` accountable/progress) + `turn_driver/transaction.py` (`NO_SPEND`/`STOP_RESULT_KINDS`) |
| Un **event sourcing idempotent** (reprise/checkpoint) | Fiche **19-loopx** → `event_sourced_state.py` (`AppendOnlyStateEventStore`, fingerprint, checksum, conflict detection) — à reloger sur DuckDB |
| Un **journal d'événements classifié** pour l'observabilité | Fiche **19-loopx** → `control_plane/runtime/event_ledger.py` (`EVENT_LEDGER_CLASSES` 5 classes, fenêtres 24h/7d) |
| Une **compaction structurelle** (par whitelist de champs, avant le résumé LLM coûteux) | Fiche **19-loopx** → `control_plane/runtime/run_compaction.py` (`RUN_BASE_COMPACT_FIELDS`) — complément à qm (14, sémantique) |
| Un **risk score quantitatif** pour prioriser les findings du Judge | Fiche **20-code-review-graph** → `changes.py` (`compute_risk_score` ∈ [0,1] multi-facteurs) + `tools/context.py` (buckets 0.7/0.4) |
| Des **poids par type de relation** pour un graphe de dépendances | Fiche **20-code-review-graph** → `constants.py` (`IMPACT_EDGE_WEIGHTS` : CALLS 1.0, INHERITS 0.9…) + `IMPACT_DEPTH_DECAY=0.6` |
| Un **format de sortie structuré** pour le Judge (findings par risk level) | Fiche **20-code-review-graph** → `skills/review-pr/SKILL.md` (Risk Assessment / File-by-File / Recommendations) |
| Des **métriques** pour benchmarker le Judge (P/R/F1, MRR) | Fiche **20-code-review-graph** → `eval/scorer.py` (`compute_precision_recall`, `compute_mrr`) |
| Une **denylist de commandes bash destructrices** (regex) | Fiche **21-davidondrej-skills** → `hooks/dangerous-patterns.txt` (27 regex POSIX-ERE) + `test-guard.sh` (~115 cas block+allow) |
| Le **moteur fail-open** d'un garde anti-crash | Fiche **21-davidondrej-skills** → `hooks/deny-dangerous.sh` (rejet explicite citant le pattern, fail-open sur erreur) |
| Un **pattern de council LLM** (jugement mutuel à l'aveugle) | Fiche **22-llm-council** → `backend/council.py` (anonymisation A/B/C + mapping réversible + agrégation Borda) — ⚠️ coût 2N+1 appels |
| Une **doctrine d'authoring de skills** (théorie formelle) | Fiche **23-mattpocock-skills** → `writing-great-skills/SKILL.md` (Predictability, deux charges, 3 rungs, 5 failure modes) — pivot de la fusion P10 |
| Un **judge à deux axes** (Standards + Spec) en sub-agents parallèles | Fiche **23-mattpocock-skills** → `engineering/code-review/SKILL.md` (jamais fusionnés ni re-rankés) |
| Un **pattern hard-dependency vs soft-dependency** (fail-loud vs degrade) | Fiche **23-mattpocock-skills** → `.agents/adr/0001-*.md` |
| **Compacter une trajectoire offline** (post-exécution, pour training/eval) | Fiche **25-hermes-agent** → `trajectory_compressor.py` (`TrajectoryCompressor`, head/tail protégé + milieu compressible + boundary snapping) |
| Un **anti-loop de compaction** (cooldown/streak/ineffective persistés) | Fiche **25-hermes-agent** → `agent/context_compressor.py` (`record_timeout_failure`, `get_active_compression_failure_cooldown`, `_persist_ineffective_compression_count`) |
| Un **schéma SQLite event-sourcing** (messages + lineage compaction + locks cross-process) | Fiche **25-hermes-agent** → `hermes_state_common.py` (`SCHEMA_SQL`, `FTS_SQL`, tables `sessions`/`messages`/`compression_locks`/`async_delegations`) |
| Une **recherche full-text** sur l'historique (FTS5 + trigram + sanitizer) | Fiche **25-hermes-agent** → `hermes_state_search.py` (`search_messages`, `_sanitize_fts5_query`, `_run_trigram_search`) |
| Un **système de skills complet** (loading + sync + provenance + guard + AST audit) | Fiche **25-hermes-agent** → `tools/skills_tool.py` + `skills_sync.py` + `skill_provenance.py` + `skills_guard.py` + `skills_ast_audit.py` |
| Une **bibliothèque de threat patterns** (injection, C2, frameworks offensifs, exfiltration) | Fiche **25-hermes-agent** → `tools/threat_patterns.py` (`scan_for_threats`, scope-aware all/context/strict) |
| Une **denylist de commandes dangereuses** (~260 patterns Python) | Fiche **25-hermes-agent** → `tools/approval.py` (`DANGEROUS_PATTERNS`, `detect_dangerous_command`) — enrichit davidondrej (21, 27 regex) et notre bash_guard.py |
| Des **guards SSRF** (bloque IPs privées/métadonnées cloud) | Fiche **25-hermes-agent** → `tools/url_safety.py` (`is_safe_url`, `_is_blocked_ip`, `create_ssrf_safe_client`, `_SSRFGuardedNetworkBackend`) |
| Un **path traversal blocker** (validate_within_dir) | Fiche **25-hermes-agent** → `tools/path_security.py` (`validate_within_dir`, `has_traversal_component`) |
| Un **contrat de middleware** à 4 points d'extension (request/execution LLM+tool, next_call chain, fail-open) | Fiche **25-hermes-agent** → `docs/middleware/README.md` (`llm_request`/`tool_request`/`llm_execution`/`tool_execution`, `hermes.middleware.v1`) |
| Une **taxonomie d'erreurs API LLM** (pour error recovery/escalation) | Fiche **25-hermes-agent** → `agent/error_classifier.py` (`classify_api_error`, `FailoverReason`, `_classify_400`/`_classify_402`) |
| Une **ABC de sandbox** (contrat execute + output collector borné + heartbeat + stdin Windows-safe) | Fiche **25-hermes-agent** → `tools/environments/base.py` (`BaseEnvironment`, `_BoundedOutputCollector`, `touch_activity_if_due`, `_pipe_stdin`) |
| Un **pattern de background review** (fork thread + digest + whitelist outils, Judge auto-apprenant) | Fiche **25-hermes-agent** → `agent/background_review.py` (`spawn_background_review_thread`, `_digest_history`, `_bg_review_auto_deny`) |
| Une **politique de retry résiliente** pour les appels LLM/HTTP/MCP (classification pré/post-send, jitter, deadline) | Fiche **45-OpenSandbox** → `sdks/sandbox/python/src/opensandbox/transport/retry.py` (`RetryPolicy`) + `_classify.py` (`classify_transport_exception`) — Python pur copiable |
| Un **contrat de lifecycle sandbox rejouable** (TTL renew, snapshot/restore, 202+polling, endpoints signés) | Fiche **45-OpenSandbox** → `specs/sandbox-lifecycle.yml` (spec OpenAPI 1712 L) + `server/.../services/snapshot_restore.py` |
| Un **modèle de serveur MCP** (docstrings-contrats, registre de sessions, progression) | Fiche **45-OpenSandbox** → `sdks/mcp/sandbox/python/src/opensandbox_mcp/server.py` (`ServerState`, `register_tools`, `create_server`) |
| Un pattern de **corrélation de logs par ContextVar** (request_id sans plumbing) | Fiche **45-OpenSandbox** → `server/opensandbox_server/middleware/request_id.py` (`request_id_ctx`, `RequestIdFilter`) |
| Une **anti-loop illustrée en graphe** (self-loop bornée + fallback différencié + cleanup) | Fiche **45-OpenSandbox** → `examples/langgraph/main.py` (`WorkflowState`, `fallback_command`, `decide_next`) |
| Un modèle minimal de **cloisonnement multi-utilisateurs** (clé → namespace) | Fiche **45-OpenSandbox** → `server/.../tenants/models.py` (`TenantEntry`) + `docs/guides/multi-tenancy.md` |
| Un **détecteur de répétitions d'appels d'outils** (escalade douce, sans veto) | Fiche **46-deepseek-harness** → `packages/guard/repeat-tool-reminder/src/index.ts` (`thresholds [3,5,8]`, `canonicalize`) — portage Python ~150 lignes |
| Une **reprise par agents frais** (contexte remis à zéro, handoff borné, objectif immuable) | Fiche **46-deepseek-harness** → `packages/workflow/tool-ralph/README.md` (`ralph`, `maxHandoffChars` 16384) |
| Un **retry LLM durable** (compteur persisté qui survit à un crash) | Fiche **46-deepseek-harness** → `packages/llm/llm-retry/src/index.ts` (`recover()`, `localDelay`) |
| Un **prompt de compaction structuré** (checkpoint 8 sections + KV-cache reuse + fail-closed) | Fiche **46-deepseek-harness** → `packages/compaction/compaction-basic/src/summarizer.ts` (`COMPACTION_INSTRUCTION`) |
| Un **event log typé extensible** (provenance, fail-closed sur type inconnu) | Fiche **46-deepseek-harness** → `packages/core/session/src/types.ts` (`SessionEventMap`, `ignorable?`, `sourceEventSeqs`) |
| La **spec des middlewares d'exécution d'outil** (5 waterfalls documentés) | Fiche **46-deepseek-harness** → `docs/tool-execution-pipeline.md` + `docs/architecture.md` (turn flow) |
| Une **charte d'invariants** de développement agentique (fail-loud, « Model-visible ⟺ logged ») | Fiche **46-deepseek-harness** → `AGENTS.md` (racine) — source directe pour `UNIVERSAL_INVARIANTS` (P0-bis) |
| **Isoler les sessions d'agents dans des git worktrees dédiés** | Fiche **47-kilocode** → `packages/kilo-vscode/src/agent-manager/WorktreeManager.ts` (`WorktreeManager`, `createWorktree`) |
| **Sauver un context overflow 4MB** (screenshots/médias) en compaction | Fiche **47-kilocode** → `packages/opencode/src/kilocode/session/compaction-payload-recovery.ts` (`KiloCompactionPayloadRecovery`) |
| Une **compaction hiérarchique par chunks** pour longs historiques | Fiche **47-kilocode** → `packages/opencode/src/kilocode/session/compaction-chunks.ts` (`KiloCompactionChunks`) |
| Un **interpréteur de code confiné (CodeMode)** avec quotas et diagnostics | Fiche **47-kilocode** → `packages/codemode/src/codemode.ts` + `src/interpreter/runtime.ts` (`CodeMode`, `DiagnosticKind`) |
| Une **mémoire persistante structurée avec journal des décisions** | Fiche **47-kilocode** → `packages/kilo-memory/src/memory.ts` (`Memory`, `MemoryDecisions`) |
| **Protéger les fichiers de configuration** contre l'auto-altération LLM | Fiche **47-kilocode** → `packages/opencode/src/kilocode/permission/config-paths.ts` (`ConfigProtection`) |
| Un **calcul de diff git natif par tranches de 500 fichiers** (guard Windows) | Fiche **47-kilocode** → `packages/opencode/src/kilocode/snapshot/diff-full.ts` (`DiffFull.batch`) |
| Une **doctrine anti-over-engineering (échelle YAGNI 7 rungs)** | Fiche **48-ponytail** → `.agents/rules/ponytail.md` (`The Ponytail Ladder`, `Bug fix = root cause`) |
| Un **format de revue de diff concis 1 ligne/finding** | Fiche **48-ponytail** → `.openclaw/skills/ponytail-review/SKILL.md` (`delete:`, `stdlib:`, `native:`, `yagni:`) |
| Un **audit de complexité et traque de code mort** | Fiche **48-ponytail** → `.openclaw/skills/ponytail-audit/SKILL.md` (`ponytail-audit`, `Hunt`) |
| Un **serveur MCP de navigation web ultra-léger avec identifiants stables** | Fiche **49-obscura** → `crates/obscura-mcp/src/lib.rs` (`interactive_refs`, `DEFAULT_TEXT_LIMIT = 4000`) |
| Un **moteur de rendu 2D pur (tiny-skia) sans GPU** pour captures web | Fiche **49-obscura** → `crates/obscura-render/src/paint.rs` (`paint_tree`, `capture_frame`) |
| Un **modèle d'annotations inline IA pour le Judge** | Fiche **50-hunk** → `src/ui/lib/agentAnnotations.ts` (`AgentAnnotation`, `AgentNote`, `AgentAnnotationSeverity`) |
| Un **garde-fou de verrouillage en écriture du workspace** | Fiche **50-hunk** → `src/ui/lib/workspaceWriteGuard.ts` (`WorkspaceWriteGuard`, `assertWritable`) |
| Un **démon broker de sessions avec baux de revue** | Fiche **50-hunk** → `packages/session-broker/src/broker.ts` (`SessionBroker`, `registerSession`) |
| Des **détecteurs de secrets/API keys et masquage PII** | Fiche **51-bytechef** → `SecretKeyDetectorUtils.java`, `PiiDetectorUtils.java` |
| Un **advisor de vérification d'invites/sorties multi-violations** | Fiche **51-bytechef** → `CheckForViolationsAdvisor.java` (`validateInputOutput`, `collectViolations`) |
| Une **façade MCP bidirectionnelle** (tools discovery + execution) | Fiche **51-bytechef** → `McpServerFacade.java` (`listTools`, `executeTool`) |
| Un **sous-agent forké de critique visuelle** avec budget dédié | Fiche **52-AutoDesign** → `autodesign/agents/critic_agent.py` (`CriticAgent`, `CritiqueReport`) |
| Une **extraction et validation stricte de faits/citations (anti-hallucination)** | Fiche **52-AutoDesign** → `autodesign/agents/claim_graph_extractor.py` + `util/claim_graph_validator.py` (`ClaimGraphExtractor`, `validate_claim_graph`, `validate_provenance`) |
| Une **supervision durable de processus et terminaison d'arbre (Windows Job Objects + POSIX)** | Fiche **52-AutoDesign** → `autodesign/process_supervision.py` (`ProcessIdentity`, `ProcessRecord`, `SpawnIntent`) |
| Une **publication atomique de répertoires avec journal réversible et rollback** | Fiche **52-AutoDesign** → `autodesign/agents/atomic_artifact_promotion.py` (`publish_artifact_directory`, `recover_artifact_promotion`) |
| Un **registre de skills v2 avec Progressive Disclosure et budget description** | Fiche **52-AutoDesign** → `autodesign/skills/registry.py` (`SkillManifest`, `SkillResource`, `select_skills`) |
| Une **séparation formelle hard blockers vs diagnostics qualitatifs** anti-boucle | Fiche **52-AutoDesign** → `autodesign/candidate_assessment.py` (`DeliveryAssessment`, `_QUALITY_ONLY_ISSUES`) |

---

## 📁 Structure du dossier audit

```
docs/references-audit/
├── README.md              ← Mode d'emploi (start ici)
├── INDEX.md               ← CE DOCUMENT (navigation + synthèse + Hall of Fame)
├── inventory.json         ← Inventaire machine-lisible (687 entrées, filtrable)
└── projects/              ← 52 fiches détaillées (1 par projet)
    ├── 01-prompt-vault.md
    ├── 02-aider.md
    ├── ...
    ├── 13-deer-flow-analysis.md
    ├── 14-qm.md
    ├── 15-claude-code-unified-agents.md
    ├── 16-learn-claude-code.md
    ├── 17-system-prompts-and-models-of-ai-tools.md
    ├── 18-awesome-claude-skills.md
    ├── 19-loopx.md
    ├── 20-code-review-graph.md
    ├── 21-davidondrej-skills.md
    ├── 22-llm-council.md
    ├── 23-mattpocock-skills.md
    ├── 24-pi.md
    ├── 25-hermes-agent.md
    ├── 26-cloudflare-os.md
    ├── 27-browser-use.md
    ├── 28-TencentDB-Agent-Memory.md
    ├── 29-system-prompts-leaks.md
    ├── 30-Ix.md
    ├── 31-Scrapling.md
    ├── 32-OpenKB.md
    ├── 33-room.md
    ├── 34-brooklyn-skills.md
    ├── 35-Understand-Anything.md
    ├── 36-prime-agent.md
    ├── 37-obsidian-skills.md
    ├── 38-skills.md
    ├── 39-langextract.md
    ├── 40-waku-agent.md
    ├── 41-stagehand.md
    ├── 42-anydoc.md
    ├── 43-framework.md
    ├── 44-sentrux.md
    ├── 45-OpenSandbox.md
    ├── 46-deepseek-harness.md
    ├── 47-kilocode.md
    ├── 48-ponytail.md
    ├── 49-obscura.md
    ├── 50-hunk.md
    ├── 51-bytechef.md
    └── 52-AutoDesign.md
```

**Pour recherche programmatique** : `inventory.json` est consommable directement :
```python
import json
inv = json.load(open('docs/references-audit/inventory.json', encoding='utf-8'))
# Tous les fichiers à réutilisabilité Haute
high = [f for p in inv['projects'] for f in p['files'] if f['reuse'] == 'high']
# Fichiers d'un projet précis
axon = next(p for p in inv['projects'] if p['id'] == 'axon')
```

