# INDEX — Audit des références

> **Document maître** de l'audit radical du dossier `references/`. Objectif : retrouver instantanément n'importe quelle information / feature / code utile, avec son **emplacement complet** et une **évaluation de réutilisabilité** pour `graph-orchestrator-smolagents`.

---

## Vue d'ensemble

| Métrique | Valeur |
|---|---|
| **Date de l'audit** | 2026-08-05 |
| **Projets/dossiers audités** | 24 |
| **Entrées de fichiers inventoriées** | 448 (inventaire machine : [`inventory.json`](./inventory.json)) |
| **Fichiers pertinents scannés** (base) | ~11 300 (hors `.git/`, `node_modules/`, médias, fixtures) |
| **Périmètre** | docs (`.md`/`.mdx`) + code source (`.py/.ts/.go/.js/.html/.css`) + JSON/YAML de spec/contrat |
| **Exclusions** | `.git/` (~730 MB), `node_modules/`, médias (1 293 SVG, 16 mp4…), fixtures de tests, traductions de README (1 conservée/projet) |

**Projet cible** : `graph-orchestrator-smolagents` — orchestrateur multi-agent (Routeur → Architect → Coders fan-out → Tester → Judge), persistance DuckDB (knowledge graph de claims/refutations), test polyvalent (web Puppeteer + Python pytest), Context7. Stack Python (DSPy "Brains" + smolagents "Hands").

---

## 🧭 Navigation — les 24 fiches

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

---

## 🗂️ Synthèse thématique — 3 familles

### 1. 🤖 Coding agents CLI (code lourd, peu portable)
`aider` (Python, mature), `crush` (Go), `nanocode` (Python, 1 fichier), `opencode` (TS, gigantesque), `openfox` (TS, local-LLM-first). → Valeur : edit-formats robustes (aider), anti-loop (crush), patterns d'outils minimaux (nanocode), specs de protocole (opencode), persistance event-sourcing (openfox).

### 2. 🔧 Frameworks d'orchestration d'agents (mixte code + docs)
`axon` + `RepoGraph` + `graphify` (knowledge graph de code, tree-sitter — **le trio le plus réutilisable**), `deer-flow` (super-agent ByteDance), `open-swe` (LangChain), `LlamaBot` (LangGraph Rails), `qm` (harnais TS — compaction/mémoire/queues portables), `learn-claude-code` (déconstruction Python pédagogique de Claude Code), `loopx` (control plane — anti-loop déterministe + event sourcing + compaction, stdlib pure), `code-review-graph` (analyse d'impact + risk score composite), `pi` (agent stateful TS). → Valeur : patterns d'orchestration, contrats de protocole, middlewares, plans/review cycles, agents de test, **compaction de contexte (qm, pi)**, **patterns harness Python natifs (learn-claude-code)**, **anti-loop déterministe + event ledger (loopx)**, **branch summarization (pi)**.

### 3. 📚 Ressources & outils
`Prompt-Vault` (12 prompts de test), `RepoGraph` (recherche académique SWE-bench), `deer_flow_analysis.md` (synthèse orientante), `claude-code-unified-agents` (prompts de spécialisation), `system-prompts-and-models-of-ai-tools` (**bibliothèque de system prompts** d'outils commerciaux/open-source), `awesome-claude-skills` (**doctrine du format SKILL.md** + outillage), `davidondrej-skills` (denylist 27 regex + hooks anti-crash), `mattpocock-skills` (**doctrine d'authoring formelle** + engineering skills), `llm-council` (pattern council anonymisé).

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
| **Total** | **198** | **164** | **84** | — |

> ℹ️ Le total de la matrice (446 = 198+164+84) couvre les entrées classées H/M/L. L'inventaire machine compte 448 entrées au total (2 entrées pré-existantes non classées dans d'anciens projets).

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

---

## 📁 Structure du dossier audit

```
docs/references-audit/
├── README.md              ← Mode d'emploi (start ici)
├── INDEX.md               ← CE DOCUMENT (navigation + synthèse + Hall of Fame)
├── inventory.json         ← Inventaire machine-lisible (441 entrées, filtrable)
└── projects/              ← 23 fiches détaillées (1 par projet)
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
    └── 24-pi.md
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
