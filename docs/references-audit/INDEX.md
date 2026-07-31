# INDEX — Audit des références

> **Document maître** de l'audit radical du dossier `references/`. Objectif : retrouver instantanément n'importe quelle information / feature / code utile, avec son **emplacement complet** et une **évaluation de réutilisabilité** pour `graph-orchestrator-smolagents`.

---

## Vue d'ensemble

| Métrique | Valeur |
|---|---|
| **Date de l'audit** | 2026-07-31 |
| **Projets/dossiers audités** | 15 |
| **Entrées de fichiers inventoriées** | 356 (inventaire machine : [`inventory.json`](./inventory.json)) |
| **Fichiers pertinents scannés** (base) | ~10 000 (hors `.git/`, `node_modules/`, médias, fixtures) |
| **Périmètre** | docs (`.md`/`.mdx`) + code source (`.py/.ts/.go/.js/.html/.css`) + JSON/YAML de spec/contrat |
| **Exclusions** | `.git/` (~730 MB), `node_modules/`, médias (1 293 SVG, 16 mp4…), fixtures de tests, traductions de README (1 conservée/projet) |

**Projet cible** : `graph-orchestrator-smolagents` — orchestrateur multi-agent (Routeur → Architect → Coders fan-out → Tester → Judge), persistance DuckDB (knowledge graph de claims/refutations), test polyvalent (web Puppeteer + Python pytest), Context7. Stack Python (DSPy "Brains" + smolagents "Hands").

---

## 🧭 Navigation — les 15 fiches

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

---

## 🗂️ Synthèse thématique — 3 familles

### 1. 🤖 Coding agents CLI (code lourd, peu portable)
`aider` (Python, mature), `crush` (Go), `nanocode` (Python, 1 fichier), `opencode` (TS, gigantesque), `openfox` (TS, local-LLM-first). → Valeur : edit-formats robustes (aider), anti-loop (crush), patterns d'outils minimaux (nanocode), specs de protocole (opencode), persistance event-sourcing (openfox).

### 2. 🔧 Frameworks d'orchestration d'agents (mixte code + docs)
`axon` + `RepoGraph` + `graphify` (knowledge graph de code, tree-sitter — **le trio le plus réutilisable**), `deer-flow` (super-agent ByteDance), `open-swe` (LangChain), `LlamaBot` (LangGraph Rails), `qm` (harnais TS — compaction/mémoire/queues portables). → Valeur : patterns d'orchestration, contrats de protocole, middlewares, plans/review cycles, agents de test, **compaction de contexte (qm)**.

### 3. 📚 Ressources & outils
`Prompt-Vault` (12 prompts de test), `RepoGraph` (recherche académique SWE-bench), `deer_flow_analysis.md` (synthèse orientante), `claude-code-unified-agents` (prompts de spécialisation).

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
| **Total** | **143** | **131** | **80** | — |

**Constats** :
- **axon** (23 Haute) et **aider** (17 Haute) restent les mines d'or côté Python.
- **qm** (17 Haute) rejoint le peloton de tête : malgré le TypeScript, ses algorithmes de **compaction de contexte, mémoire durable, idempotency et queues à leases** sont portables. (L'ancienne fiche la notait Moyenne à tort.)
- **deer-flow** (21 Haute) malgré une note globale Moyenne — la valeur est dans les contracts/plans/middlewares.
- **claude-code-unified-agents** : 7 prompts purs 🟢 (alignés avec les rôles du graphe), mais la majorité des 53 fichiers est du code TS non portable → note Moyenne. (L'ancienne fiche la notait Haute à tort.)
- **opencode/openfox** (TS) : peu de Haute, leurs **specs/docs** restent des références conceptuelles au mieux.

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
| **Compacter l'historique de contexte** (LLM context overflow) | Fiche **14-qm** → `harness/context-compaction.ts` (`planCompaction`) + `core/orchestrator/compaction.ts` (duale sync+async) |
| **Consolider le knowledge graph** (LLM-juge de claims) | Fiche **14-qm** → `memory/strategies/consolidation.ts` (`UPDATE`/`DELETE`/`ADD`) |
| **Garantir un effet de bord unique** (idempotence des retries) | Fiche **14-qm** → `idempotency/idempotency-store.ts` (`once(key, fn)`) |
| **Contrôler le coût LLM** (budget USD, fenêtre glissante) | Fiche **14-qm** → `ratelimit/budget.ts` (`createBudgetTracker`, `estimateCostUsd`) |
| Un **system prompt** pour le Judge / Reviewer | Fiche **15-claude-code** → `quality/code-reviewer.md` (Critical/Major/Minor, lecture seule) |
| Un **system prompt** pour le Security Reviewer | Fiche **15-claude-code** → `quality/security-auditor.md` (OWASP, CVSS) |
| Un **system prompt** pour le Coder Python | Fiche **15-claude-code** → `development/python-pro.md` (type hints, PEP 8) |
| Un schéma pour **déclarer formellement un agent** | Fiche **15-claude-code** → `specialized/agent-generator.md` (`AgentCapabilitySchema`) |

---

## 📁 Structure du dossier audit

```
docs/references-audit/
├── README.md              ← Mode d'emploi (start ici)
├── INDEX.md               ← CE DOCUMENT (navigation + synthèse + Hall of Fame)
├── inventory.json         ← Inventaire machine-lisible (356 entrées, filtrable)
└── projects/              ← 15 fiches détaillées (1 par projet)
    ├── 01-prompt-vault.md
    ├── 02-aider.md
    ├── ...
    ├── 13-deer-flow-analysis.md
    ├── 14-qm.md
    └── 15-claude-code-unified-agents.md
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
