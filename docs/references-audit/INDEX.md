# INDEX — Audit des références

> **Document maître** de l'audit radical du dossier `references/`. Objectif : retrouver instantanément n'importe quelle information / feature / code utile, avec son **emplacement complet** et une **évaluation de réutilisabilité** pour `graph-orchestrator-smolagents`.

---

## Vue d'ensemble

| Métrique | Valeur |
|---|---|
| **Date de l'audit** | 2026-07-31 |
| **Projets/dossiers audités** | 13 |
| **Entrées de fichiers inventoriées** | 315 (inventaire machine : [`inventory.json`](./inventory.json)) |
| **Fichiers pertinents scannés** (base) | ~10 000 (hors `.git/`, `node_modules/`, médias, fixtures) |
| **Périmètre** | docs (`.md`/`.mdx`) + code source (`.py/.ts/.go/.js/.html/.css`) + JSON/YAML de spec/contrat |
| **Exclusions** | `.git/` (~730 MB), `node_modules/`, médias (1 293 SVG, 16 mp4…), fixtures de tests, traductions de README (1 conservée/projet) |

**Projet cible** : `graph-orchestrator-smolagents` — orchestrateur multi-agent (Routeur → Architect → Coders fan-out → Tester → Judge), persistance DuckDB (knowledge graph de claims/refutations), test polyvalent (web Puppeteer + Python pytest), Context7. Stack Python (DSPy "Brains" + smolagents "Hands").

---

## 🧭 Navigation — les 13 fiches

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

---

## 🗂️ Synthèse thématique — 3 familles

### 1. 🤖 Coding agents CLI (code lourd, peu portable)
`aider` (Python, mature), `crush` (Go), `nanocode` (Python, 1 fichier), `opencode` (TS, gigantesque), `openfox` (TS, local-LLM-first). → Valeur : edit-formats robustes (aider), anti-loop (crush), patterns d'outils minimaux (nanocode), specs de protocole (opencode), persistance event-sourcing (openfox).

### 2. 🔧 Frameworks d'orchestration d'agents (mixte code + docs)
`axon` + `RepoGraph` + `graphify` (knowledge graph de code, tree-sitter — **le trio le plus réutilisable**), `deer-flow` (super-agent ByteDance), `open-swe` (LangChain), `LlamaBot` (LangGraph Rails). → Valeur : patterns d'orchestration, contrats de protocole, middlewares, plans/review cycles, agents de test.

### 3. 📚 Ressources & outils
`Prompt-Vault` (12 prompts de test), `RepoGraph` (recherche académique SWE-bench), `deer_flow_analysis.md` (synthèse orientante).

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

---

## 📊 Matrice réutilisabilité croisée

| Projet | 🟢 Haute | 🟡 Moyenne | 🔴 Faible |
|---|---|---|---|
| Prompt-Vault | 13 | 0 | 0 |
| aider | 17 | 11 | 10 |
| nanocode | 1 | 8 | 2 |
| RepoGraph | 8 | 6 | 2 |
| axon | 23 | 7 | 0 |
| graphify | 11 | 6 | 4 |
| LlamaBot | 5 | 7 | 16 |
| deer-flow | 21 | 18 | 7 |
| open-swe | 11 | 7 | 12 |
| crush | 1 | 7 | 17 |
| opencode | 0 | 5 | 22 |
| openfox | 3 | 3 | 20 |
| deer-flow-analysis | 5 | 0 | 0 |

**Constats** :
- **axon** (23 Haute) et **aider** (17 Haute) sont les mines d'or.
- **deer-flow** (21 Haute) malgré une note globale Moyenne — la valeur est dans les contracts/plans/middlewares.
- **opencode/openfox** (TS) : peu de Haute, mais leurs **specs/docs** restent des références conceptuelles.

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

---

## 📁 Structure du dossier audit

```
docs/references-audit/
├── README.md              ← Mode d'emploi (start ici)
├── INDEX.md               ← CE DOCUMENT (navigation + synthèse + Hall of Fame)
├── inventory.json         ← Inventaire machine-lisible (315 entrées, filtrable)
└── projects/              ← 13 fiches détaillées (1 par projet)
    ├── 01-prompt-vault.md
    ├── 02-aider.md
    ├── ...
    └── 13-deer-flow-analysis.md
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
