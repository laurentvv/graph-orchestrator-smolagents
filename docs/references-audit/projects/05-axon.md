# 05 — axon

## En-tête
- **Nom** : axon (package PyPI `axoniq`)
- **Chemin** : `references/axon/`
- **Type** : framework d'orchestration / knowledge graph de code (code intelligence engine)
- **Langage principal** : Python (package `axon`, backend) + TypeScript/React (frontend dashboard)
- **Statistiques** : ~90 fichiers pertinents, ~3.3 MB (1.2 MB src Python, 433K tests, 60K docs)
- **Stack** : tree-sitter, KuzuDB (graphe + FTS + vecteurs), igraph/leidenalg, fastembed (ONNX 384-dim), FastAPI, mcp SDK (FastMCP), Typer, watchfiles, React+Vite+Sigma.js

## Synthèse
Axon indexe n'importe quelle codebase (Python/JS/TS) en un **knowledge graph structurel** via un pipeline d'ingestion 12 phases (walk → structure → parse tree-sitter → imports → calls → heritage → types → communautés Leiden → processes/flows → dead code → coupling git → embeddings). Le graphe est persisté dans KuzuDB (embedded, Cypher, FTS BM25, vecteurs HNSW) et exposé via trois surfaces : CLI Typer, serveur MCP (15 tools + 3 resources) pour agents IA, et dashboard web React (FastAPI + Sigma.js WebGL). La valeur pour `graph-orchestrator-smolagents` est **très élevée** : les patterns de pipeline d'ingestion multi-phases, d'analyse d'impact par BFS avec groupement par profondeur, de détection de dead code multi-passes (override/protocol/conformité framework), de Reciprocal Rank Fusion (BM25+vecteur+fuzzy), de guard Cypher read-only, et l'architecture MCP server sont directement adaptables. Le projet cible (persistance DuckDB de claims/refutations, workflow Routeur→Architect→Coders→Tester→Judge) peut réutiliser le modèle de graphe orienté code (NodeLabel/RelType/GraphNode), le pipeline orchestré avec `PipelineResult`, les outils MCP `axon_impact`/`axon_context`/`axon_call_path`, et la stratégie de Cypher guard. Note de réutilisabilité globale : **Haute**.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/axon/README.md` | Doc racine : pitch, pipeline 12 phases, modèle de graphe (nodes/relationships + ID format), 7 outils MCP, endpoints API, comparatifs, stack technique | Haute |
| `references/axon/docs/frontend-spec.md` | Spec UI web complète (1320 lignes) : design system "terminal power tool", 3 vues (Explorer/Analysis/Cypher), schéma API REST, Zustand stores, animations impact/flow, keyboard shortcuts | Moyenne |
| `references/axon/CONTRIBUTING.md` | Guide contribution | Faible |
| `references/axon/pyproject.toml` | Dépendances clés (kuzu, tree-sitter, igraph, leidenalg, fastembed, mcp, fastapi, watchfiles, pathspec, typer), build hatchling | Moyenne |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/axon/src/axon/core/ingestion/pipeline.py` | `PipelineResult`, `run_pipeline()`, `reindex_files()`, `build_graph()` | Orchestrateur des 12 phases d'ingestion (walk→structure→parse→imports→calls/heritage/types parallélisés→communities→processes→dead_code→coupling→bulk_load+embeddings). `_timed` context manager pour timing par phase. Reindex incrémental. | Haute | Modèle d'orchestrateur multi-phases directement transposable au pipeline coding ; `PipelineResult` + `progress_callback` adaptables pour Routeur→Architect→Coders→Tester→Judge |
| `references/axon/src/axon/core/ingestion/dead_code.py` | `process_dead_code()` | Détection dead code multi-passes avec exemptions (entry points, exports, constructors, tests, dunder, `__init__.py`, décorateurs framework) + 3 passes de correction false-positives (override, conformance Protocol, stubs) | Haute | Logique "unreachable symbol detection" réutilisable pour identifier claims/refutations orphelins dans le KG DuckDB |
| `references/axon/src/axon/core/search/hybrid.py` | `hybrid_search()`, `_accumulate_ranks()` | Reciprocal Rank Fusion (RRF) : fusion BM25 + vecteur + fuzzy via `score = Σ weight/(k+rank)`. Candidate limit, poids configurables, fallback fuzzy si FTS vide | Haute | Algorithme RRF directement réutilisable pour ranking hybride de claims/refutations (texte + embeddings) dans DuckDB |
| `references/axon/src/axon/core/cypher_guard.py` | `WRITE_KEYWORDS`, `sanitize_cypher()` | Regex compilée détectant mots-clés d'écriture Cypher (DELETE/DROP/CREATE/SET/MERGE/...) après strip des commentaires | Haute | Guard read-only directement adaptable ; pattern applicable à toute garde SQL/Cypher |
| `references/axon/src/axon/mcp/tools.py` | `handle_impact()`, `handle_context()`, `handle_call_path()`, `handle_query()`, `handle_cypher()`, `handle_dead_code()`, `handle_review_risk()`, `handle_test_impact()`, ... | 14 handlers MCP : impact analysis (BFS `traverse_with_depth`, groupé par profondeur will-break/may-break/review), context 360° (callers/callees/type refs/heritage), call path BFS, review risk (score 0-10), test impact | Haute | Architecture tools MCP complète et patterns d'analyse de graphe adaptables pour exposer le KG de claims aux agents smolagents |
| `references/axon/src/axon/mcp/server.py` | `server` (Server), `TOOLS` (15 Tool), `_dispatch_tool()`, `_with_storage()`, `create_streamable_http_app()` | Serveur MCP complet : registration tools/resources, dispatch, injection storage partagé + lock async, mode read-only fallback, transport stdio + streamable HTTP (ASGI) | Haute | Squelette serveur MCP FastMCP réutilisable pour exposer tools du projet cible |
| `references/axon/src/axon/core/storage/base.py` | `StorageBackend` (Protocol), `SearchResult`, `NodeEmbedding`, `EMBEDDING_DIMENSIONS` | Protocol `@runtime_checkable` : contrat complet d'un backend graphe (CRUD nodes/rels, callers/callees, traverse BFS + `traverse_with_depth`, fts/fuzzy/vector search, bulk_load, embeddings). 384-dim | Haute | Protocol abstrait transposable pour abstraction de la persistance DuckDB |
| `references/axon/src/axon/core/storage/kuzu_backend.py` | `KuzuBackend`, `escape_cypher()` | Implémentation backend KuzuDB (1250 lignes) : schema creation, bulk load CSV COPY FROM, FTS indexes, vector_search via `array_cosine_similarity`, BFS, retry sur lock | Moyenne | Backend KuzuDB spécifique (non DuckDB) ; patterns bulk load CSV, FTS indexes, escape_cypher adaptables mais projection vers DuckDB nécessite réécriture |
| `references/axon/src/axon/core/graph/model.py` | `NodeLabel` (Enum), `RelType` (Enum), `GraphNode`, `GraphRelationship`, `generate_id()` | Modèle de données : 10 NodeLabels, 11 RelTypes, ID format `{label}:{file_path}:{symbol_name}` | Haute | Schéma graphe adaptable pour workflow multi-agent (Coder/Test/Judge comme nodes) ; `generate_id` déterministe |
| `references/axon/src/axon/core/graph/graph.py` | `KnowledgeGraph` | Graphe en mémoire dict-backed avec indexes secondaires O(1) par label/type/adjacence. Cascade delete | Haute | Implémentation graphe staging réutilisable avant persistance DuckDB |
| `references/axon/src/axon/core/ingestion/calls.py` | `resolve_call()`, `process_calls()`, `_CALL_BLOCKLIST` | Résolution d'appels avec scores de confiance (même fichier 1.0, import 1.0, fuzzy global 0.5). Blocklist 138 builtins | Haute | Logique de résolution/confiance adaptable pour tracer les dépendances entre claims et entre agents |
| `references/axon/src/axon/core/ingestion/coupling.py` | `resolve_coupling()`, `parse_git_log()`, `build_cochange_matrix()` | Analyse change coupling via git log (6 mois) : force = `co_changes/max(changes)`, filtres strength≥0.3 | Haute | Pattern de couplage temporel pour découvrir quelles parties du graphe de claims évoluent ensemble |
| `references/axon/src/axon/core/ingestion/processes.py` | `process_processes()`, `find_entry_points()`, `trace_flow()` | Détection flows : entry points framework-aware, BFS trace (max_depth 6), classification cross/intra-community | Haute | Logique de tracing flows adaptable pour tracer chemins Routeur→Architect→Coders→Tester→Judge |
| `references/axon/src/axon/core/ingestion/walker.py` | `walk_repo()`, `discover_files()`, `FileEntry` | Walker filesystem : `git ls-files` puis fallback os.walk, respecte gitignore (pathspec), prune dirs, lecture parallèle | Haute | Utilitaire robuste réutilisable pour scanner le codebase lors du workflow coding |
| `references/axon/src/axon/core/embeddings/embedder.py` | `embed_graph()`, `embed_query()`, `EMBEDDABLE_LABELS` | Pipeline embeddings fastembed (nomic-embed-text-v1.5, 384-dim Matryoshka), cache modèle thread-safe | Haute | Pipeline embeddings réutilisable pour vectoriser claims/refutations + recherche sémantique |
| `references/axon/src/axon/mcp/resources.py` | `get_overview()`, `get_dead_code_list()`, `get_schema()` | Handlers resources MCP (overview counts, dead code, schema statique) | Haute | Pattern de resources MCP réutilisable |
| `references/axon/src/axon/runtime.py` | `AxonRuntime` | Dataclass `@slots` conteneur état partagé (storage, repo_path, watch, lock, urls, event_listeners) | Haute | Pattern de conteneur runtime partagé réutilisable |
| `references/axon/src/axon/config/ignore.py` | `load_gitignore()`, `should_ignore()`, `DEFAULT_IGNORE_PATTERNS` | Matching gitignore via pathspec | Haute | Réutilisable pour exclure fichiers du scan codebase |
| `references/axon/src/axon/core/parsers/base.py` | `LanguageParser` (ABC), `SymbolInfo`, `ImportInfo`, `CallInfo`, `ParseResult` | Interface parser + dataclasses IR (symboles, imports, calls, type refs, heritage, exports) | Moyenne | IR propre extensible comme modèle de représentation intermédiaire |
| `references/axon/src/axon/cli/main.py` | `app` (Typer), commandes CLI | CLI Typer complet (analyze/query/context/impact/dead-code/cypher/watch/diff/host/ui/setup/mcp/serve) | Moyenne | Patterns CLI Typer + gestion storage read-only réutilisables |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/axon/docs/frontend-spec.md` | spec | Spec UI web : design system, 3 vues, schéma API REST, Zustand stores, 10 phases d'implémentation |
| `references/axon/pyproject.toml` | config | Dépendances (versions min), optionnel `[neo4j]`, build hatchling, ruff/pytest config |
| `references/axon/src/axon/core/graph/model.py` | contrat | Contrat de modèle de données : enums NodeLabel/RelType, dataclasses GraphNode/GraphRelationship, format ID `generate_id()` |
| `references/axon/src/axon/core/storage/base.py` | contrat | Contrat Protocol `StorageBackend` (runtime_checkable) : signature complète du backend de persistance graphe |
| `references/axon/src/axon/core/parsers/base.py` | contrat | Contrat parser `LanguageParser` ABC + IR dataclasses |

## Exclusions conscientes
- **Frontend TypeScript/React** (`src/axon/web/frontend/src/**/*.ts`, `*.tsx`, configs `tsconfig*.json`, `vite.config.ts`, `package.json`) : UI dashboard non portable vers un projet backend Python ; seuls les patterns conceptuels (stores Zustand, hooks SSE) ont une valeur documentaire via `docs/frontend-spec.md`.
- **Parsers tree-sitter** (`python_lang.py`, `typescript.py`) : 1300+ lignes spécifiques à l'AST tree-sitter du code source, non transposables au knowledge graph de claims/refutations.
- **Heritage/Types/Structure ingestion** : phases trop spécifiques à l'analyse de code OO.
- **Tests** (`tests/**`) : spécifiques à axon, conservés seulement comme exemples de contrats d'API.
- **Configs GitHub** (`.github/**`) : CI/CD générique.
- **Médias** (logo svg/png) : exclus par filtrage initial.
