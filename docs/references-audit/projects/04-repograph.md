# 04 — RepoGraph

## En-tête
- **Nom** : RepoGraph
- **Chemin** : `references/RepoGraph/`
- **Type** : implémentation de papier de recherche / graphe de code repository-level (plug-in multi-méthodes SWE-bench)
- **Langage principal** : Python
- **Statistiques** : 17 fichiers pertinents hors sous-clone (`repograph/` 3, `agentless/` 12, + README/requirements), ~210 KB de code audité ; arbre total ~7,3 MB (dominé par `SWE-agent/` non audité)

## Synthèse
RepoGraph est un **module plug-in repository-level** qui construit un graphe de code (networkx `MultiDiGraph`) à partir d'un repo Python puis l'expose pour enrichir le contexte d'un LLM. Pipeline : (1) `create_structure` parse le repo en dict hiérarchique (classes/fonctions avec lignes + texte), (2) `CodeGraph` utilise **tree-sitter** (queries SCM inline pour `def`/`ref` de classes et fonctions + fallback pygments) pour extraire des `Tag` nommés, filtre builtins/libs std via `exec` des imports, (3) `tag_to_graph` relie classes→méthodes et refs→defs dans un `MultiDiGraph`, (4) `RepoSearcher` fournit traversées (1-hop, 2-hop, DFS, BFS), (5) côté Agentless, `retrieve_graph` + `construct_code_graph_context` ré-injectent les dépendances dans le prompt de fault-localization.

Le projet est adapté d'**aider (RepoMap)** + **Agentless** + **grep-ast**. Intégrations fournies : Agentless (pipeline procédural, flag `--repo_graph`) et SWE-agent (action `search_repo`).

**Pertinence pour le projet cible** : le KG DuckDB actuel stocke des claims/refutations mais **pas la structure de code**. RepoGraph comble exactement ce vide — construction de graphe de code, recherche de dépendances, compression de fichiers pour le contexte LLM. Les briques `CodeGraph`, `RepoSearcher`, `get_skeleton` (libcst) et les fonctions `retrieve_graph`/`construct_code_graph_context` sont directement adaptables. Les prompts FL (`obtain_relevant_code_graph_prompt`) sont réutilisables pour le rôle Architect/Coders. Note de réutilisabilité globale : **Haute**.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/RepoGraph/README.md` | Overview papier, setup, CLI `python repograph/construct_graph.py <dir>`, intégrations SWE-bench, dataset HF/Drive des graphs pré-calculés | Moyenne |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/RepoGraph/repograph/construct_graph.py` | `CodeGraph`, `Tag`, `get_code_graph`, `get_tag_files`, `tag_to_graph`, `get_ranked_tags`, `get_tags_raw`, `std_proj_funcs`, `find_files` | Construction du graphe de code : tree-sitter (queries SCM inline) + structure AST pour extraire def/ref, filtrage builtins via `exec` d'imports, construction `nx.MultiDiGraph` (classes→méthodes, refs→defs). `__main__` pickle `graph.pkl` + `tags.json` | **Haute** | Cœur du value-proposition : le KG DuckDB cible ne modélise pas la structure de code. `CodeGraph` est autonome (deps: tree-sitter, grep-ast, networkx) |
| `references/RepoGraph/repograph/graph_searcher.py` | `RepoSearcher`, `one_hop_neighbors`, `two_hop_neighbors`, `dfs`, `bfs` | Traversées de graphe minces (DFS/BFS bornés en profondeur) sur networkx | **Haute** | Wrapper clair pour exposer le graphe à un agent ; adaptable tel quel pour outil `search_dependencies` |
| `references/RepoGraph/repograph/utils.py` | `create_structure`, `parse_python_file` | Parse un repo Python en dict hiérarchique {classes, functions, text, start_line, end_line} via `ast` | **Haute** | Pré-requis de `CodeGraph` ; pur stdlib `ast`, réutilisable pour indexer le code dans DuckDB |
| `references/RepoGraph/agentless/fl/localize.py` | `retrieve_graph`, `construct_code_graph_context`, `localize`, `merge` | Récupère les callers/callees d'un symbole et fabrique un bloc de contexte texte (`### Dependencies for {func}`) injecté dans le prompt FL | **Haute** | Pont graphe→prompt directement transposable au workflow coding (Architect/Coders) |
| `references/RepoGraph/agentless/fl/FL.py` | `FL` (ABC), `LLMFL(FL)`, `obtain_relevant_code_graph_prompt`, `localize_line_from_coarse_function_locs` | Fault-localization multi-niveaux (fichier → fonction compressée → ligne) avec injection optionnelle du contexte graphe | **Haute** | Prompts et structure de pipeline (coarse→fine) réutilisables pour la phase de localisation avant fan-out Coders |
| `references/RepoGraph/agentless/util/compress_file.py` | `CompressTransformer` (libcst `CSTTransformer`), `get_skeleton` | Compression de code : remplace corps de fonctions par `...`, supprime docstrings, garde `ClassDef`/`FunctionDef`/constantes | **Haute** | Indépendant, pur libcst, idéal pour réduire le contexte envoyé au LLM. Usage : `get_skeleton(code, keep_constant=True)` |
| `references/RepoGraph/agentless/util/preprocess_data.py` | `line_wrap_content`, `get_repo_files`, `show_project_structure`, `get_full_file_paths_and_classes_and_functions`, `transfer_arb_locs_to_locs` | Utilitaires de mise en forme du contexte (numérotation de lignes, sticky-scroll, extraction de fichiers) | **Moyenne** | `line_wrap_content` utile pour afficher code numéroté ; reste couplé à la structure dict Agentless |
| `references/RepoGraph/agentless/util/postprocess_data.py` | `check_syntax`, `extract_code_blocks`, `extract_locs_for_files`, `lint_code`, `parse_edit_commands` | Post-processing des sorties LLM (extraction de blocs ```python, validation syntaxique) | **Moyenne** | Réutilisable pour parser les réponses des Coders ; `lint_code` invoque un subprocess git temporaire |
| `references/RepoGraph/agentless/repair/repair.py` | `construct_topn_file_context` | Construction du contexte Top-N + génération de patch | **Moyenne** | `construct_topn_file_context` est appelé par le pipeline FL ; réutilisable pour assembleur de contexte |
| `references/RepoGraph/agentless/get_repo_structure/get_repo_structure.py` | `clone_repo`, `checkout_commit`, `get_project_structure_from_scratch`, `get_code_graph_from_scratch`, `filter_out_test_files`, `repo_to_top_folder` | Clonage git + checkout commit + construction structure/graphe pour SWE-bench | **Moyenne** | Orchestration SWE-bench spécifique (dict `repo_to_top_folder` hardcodé), mais pattern clone→checkout→parse montré |
| `references/RepoGraph/agentless/util/utils.py` | `load_jsonl`, `write_jsonl`, `load_json`, `combine_by_instance_id` | IO JSON/JSONL triviaux | Faible | Généraliste, déjà couvert |
| `references/RepoGraph/agentless/util/parse_global_var.py` | `parse_global_var_from_code` | Extraction de variables globales (AST) | Faible | Spécifique au prompt FL incluant les vars globales |
| `references/RepoGraph/agentless/util/api_requests.py` | `create_chatgpt_config`, `num_tokens_from_messages`, `request_chatgpt_engine` | Wrapper API OpenAI (gpt-4o hardcodé) + comptage tokens | Faible | Remplaçable par DSPy/smolagents du projet cible |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/RepoGraph/requirements.txt` | config | Dépendances pinées : `tree-sitter==0.21.3`, `tree-sitter-languages==1.10.2`, `grep-ast==0.3.2`, `networkx==3.2.1`, `pygments==2.18.0`, `libcst==1.4.0`, `openai==1.42.0`, `tiktoken==0.7.0` — base pour réutiliser `CodeGraph` |
| `references/RepoGraph/README.md` | spec | Spécifie le contrat d'usage : CLI `construct_graph.py <dir>` → `tags_{id}.jsonl` + `{id}.pkl` (networkx) ; datasets pré-calculés sur HF (`MrZilinXiao/RepoGraph`) et Drive |

## Exclusions conscientes
- `references/RepoGraph/SWE-agent/` : sous-clone externe (~37 fichiers `.py`, ~7 MB, contient son propre `pyproject.toml`, `tests/`, `evaluation/`, frontend). **Non audité en détail.** Signalement : intègre RepoGraph via `sweagent/environment/code_graph.py` (variante `RepoMap` avec `diskcache.Cache`), `sweagent/environment/retrieve_graph.py` (script CLI `main(func_name)` lisant `/graph.pkl`+`/tags.json`, retourne successors/predecessors filtrés des tests), et `config/commands/_code_graph.py`. Ces 3 fichiers sont l'équivalent "agent framework" de `repograph/` — potentiellement utiles mais redondants avec le code `repograph/` plus propre.
