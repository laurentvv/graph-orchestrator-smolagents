# 06 — graphify

## En-tête
- **Nom** : graphify (package PyPI `graphifyy`, v0.9.30)
- **Chemin** : `references/graphify/`
- **Type** : knowledge graph de code — skill pour assistants coding (Claude Code, Codex, Cursor, Gemini CLI, 20+ plateformes)
- **Langage principal** : Python 3.10+ (NetworkX + tree-sitter)
- **Origine** : Graphify-Labs, Y Combinator S26
- **Statistiques** : 658 fichiers pertinents (274 `.py`, 361 `.md`, 14 `.json`, 9 `yaml/yml/toml`) ; 27 MB total (22 MB hors traductions/corpus). 36 grammaires tree-sitter + extracteurs regex (Apex) + configs.

## Synthèse
graphify transforme un dossier (code, docs, PDFs, images, vidéo/audio) en un **knowledge graph navigable** (`graph.json` au format node-link NetworkX). Le pipeline est `detect() → extract() → build() → cluster() → analyze() → report() → export()`, chaque étape étant une fonction sans état partagé.

Trois idées clés, directement réutilisables pour `graph-orchestrator-smolagents` :
1. **Tags de confiance sur les edges** (`EXTRACTED` = explicite dans la source, `INFERRED` = résolu par inférence avec `confidence_score` 0.55–0.95, `AMBIGUOUS` = incertain). C'est exactement le modèle de provenance applicable au KG DuckDB de claims/refutations — chaque edge porterait son origine et son score.
2. **Analyse d'impact multi-relation** (`affected.py`) : BFS inverse sur 13 types de relations (calls, imports, inherits, extends, implements, uses, mixes_in, references, requires...) avec provenance par edge (`via_file`, `via_location` = site exact du call/import, pas la ligne de définition).
3. **Architecture d'extracteurs par langage** découplée via un `LanguageConfig` dataclass et un registry `LANGUAGE_EXTRACTORS`. Ajouter un langage = un fichier `extract_<lang>.py` + une entrée dans le registry.

Le code est mature (numérotation de bugs jusqu'à #2297). Un serveur MCP (`serve.py`) expose 10 outils (`query_graph`, `shortest_path`, `get_pr_impact`, `triage_prs`...). Limites : densément commenté, très lié au format `graph.json` NetworkX, persistance JSON plat (pas DuckDB). Note de réutilisabilité globale : **Haute**.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/graphify/README.md` | README racine (869 lignes) : pitch, install 20+ plateformes, commandes, variables d'env, privacy, benchmarks LOCOMO/LongMemEval | Haute |
| `references/graphify/ARCHITECTURE.md` | Pipeline en 7 étapes, schéma d'extraction (nodes/edges/confidence), tableau des modules, procédure "ajouter un langage" | Haute |
| `references/graphify/docs/how-it-works.md` | Les 3 passes (AST local / Whisper local / LLM sémantique), Leiden, rubrique de scoring de confiance (0.55–0.95), format `graph.json` | Haute |
| `references/graphify/docs/node-summaries-rfc.md` | RFC : summaries déterministes au niveau fichier (Option A attribut `summary` vs Option B sidecar) avec champs `generated_by`, `summary_version` | Moyenne |
| `references/graphify/docs/superpowers/specs/2026-05-04-incremental-updates-dedup-design.md` | Spec : dedup incrémental, mise à jour par hash de fichier | Moyenne |
| `references/graphify/SECURITY.md` | Modèle de menace (SSRF, path traversal, memory bomb) | Moyenne |
| `references/graphify/BENCHMARKS.md` | Benchmarks LOCOMO (recall@10 = 0.497), LongMemEval, coût token = 0 pour le code | Faible |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/graphify/graphify/affected.py` | `AffectedHit` (dataclass : `node_id, depth, via_relation, via_file, via_location`), `affected_nodes()`, `resolve_seed()`, `format_affected()`, `DEFAULT_AFFECTED_RELATIONS` (13 relations), `load_graph()` | Analyse d'impact par BFS inverse multi-relation. `via_file`/`via_location` pointent vers le SITE du call/import (pas la définition). Resolve-seed tolérant | **Haute** | Modèle d'impact analysis avec provenance par edge directement transposable au KG DuckDB pour tracer quelles claims/refutations sont affectées par un changement |
| `references/graphify/graphify/extractors/models.py` | `LanguageConfig` (dataclass), `_SymbolResolutionFacts` + 7 dataclasses de faits (`_SymbolDeclarationFact`, `_SymbolImportFact`, `_SymbolAliasFact`, `_SymbolExportFact`, `_StarExportFact`, `_NamespaceExportFact`, `_SymbolUseFact`) | Configuration déclarative d'un langage tree-sitter + modèle de faits de résolution de symboles | **Haute** | Architecture découplée : séparer la config d'un langage de la logique de traversal |
| `references/graphify/graphify/extractors/__init__.py` | `LANGUAGE_EXTRACTORS` (registry dict `{lang: extract_fn}`), 25+ extracteurs importés | Registry d'extracteurs par langage | **Haute** | Pattern simple et éprouvé pour étendre les sources d'extraction |
| `references/graphify/graphify/build.py` | `build_from_json()`, `build()`, `build_merge()`, `merge_raw_extraction()`, `prefix_graph_for_global()`, `prune_repo_from_graph()`, `deduplicate_by_label()`, `edge_data()`/`edge_datas()` | Assemblage NetworkX : ghost-dedup AST vs sémantique, re-key sémantique depuis `source_file`, cross-language phantom-edge guard, merge incrémental replace-per-source | **Moyenne** | Logique de merge/dedup robuste ; l'idée "replace-per-source" (un fichier ré-extrait remplace sa contribution précédente) est transposable au DuckDB |
| `references/graphify/graphify/cluster.py` | `cluster()`, `_partition()` (Leiden→Louvain fallback), `label_communities_by_hub()`, `cohesion_score()`, `remap_communities_to_previous()` | Détection de communautés Leiden avec split des communautés >25%, exclusion de hubs par percentile, stabilité des IDs par matching greedy | **Moyenne** | Algorithmes matures ; pas de besoin de clustering de code identifié côté cible, mais `remap_communities_to_previous` est un bon pattern de stabilité |
| `references/graphify/graphify/security.py` | `validate_url()`, `safe_fetch()`/`safe_fetch_text()`, `_SSRFGuardedHTTPConnection`/`_SSRFGuardedHTTPSConnection`, `validate_graph_path()`, `check_graph_file_size_cap()`, `sanitize_label()`, `sanitize_metadata()` | Guards de sécurité : SSRF (résolution DNS unique + validation IP, anti-DNS-rebind), memory bomb (cap 512 MiB), path traversal, injection HTML | **Moyenne** | Bonnes pratiques si le projet cible fetch des URLs ou charge des graphs externes |
| `references/graphify/graphify/global_graph.py` | `global_add()`, `global_remove()`, `global_list()`, `global_path()` | Graph global multi-projets à `~/.graphify/`. Préfixe les IDs (`repo_tag::node_id`), déduplique les nœuds externes par label | **Moyenne** | Pattern de fédération de graphs par namespace |
| `references/graphify/graphify/serve.py` | 10 outils MCP : `query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path`, `list_prs`, `get_pr_impact`, `triage_prs` + 6 ressources ; transports stdio + HTTP | Serveur MCP exposant le graph avec auth (`--api-key`), stateless mode, multi-contexte | **Moyenne** | Squelette MCP complet si le projet cible veut exposer son KG via MCP |
| `references/graphify/graphify/extractors/engine.py` | `_extract_with_config()` (dispatch central, 4748 lignes) | Moteur d'extraction AST universel : walk tree-sitter selon `LanguageConfig`, collecte `calls`/`imports`/`references`/`inherits`/`implements`, second pass pour `indirect_call` | Faible | Trop volumineux et spécifique tree-sitter ; fonctions helpers par langage = références si on parse du Python/JS |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/graphify/graphify/skill.md` + `skill-*.md` (16 fichiers) | spec | Déclarations de skill pour 20+ assistants. `skill.md` = skill racine (pipeline 9 étapes en bash). Les 15 `skill-<platform>.md` sont des variantes |
| `references/graphify/graphify/skills/<platform>/references/extraction-spec.md` (×13 plateformes) | spec | Prompt exact d'extraction sémantique (schéma JSON, règles EXTRACTED/INFERRED/AMBIGUOUS, rubrique de confiance, hyperedges, règles vision). Contenu identique dupliqué par plateforme |
| `references/graphify/graphify/skills/<platform>/references/{query,update,hooks,exports,add-watch,github-and-merge,transcribe}.md` | spec | Runbooks détaillés pour chaque sous-commande (dupliqués ×13) |
| `references/graphify/graphify/always_on/*.md` (6 fichiers) | config | Fichiers always-on écrits par `graphify install` : `agents-md.md`, `claude-md.md`, `gemini-md.md`, `kiro-steering.md`, `vscode-instructions.md`, `antigravity-rules.md` |
| `references/graphify/pyproject.toml` | config | Package `graphifyy` v0.9.30 ; 31 deps tree-sitter ; extras `[mcp, neo4j, falkordb, leiden, openai, anthropic, gemini, bedrock, ollama, pdf, office, video, sql, postgres, terraform, pascal, dm, chinese]` |

## Exclusions conscientes
- **~31 traductions README** (`docs/translations/README.<locale>.md` : ar-SA, zh-CN, ja-JP, ko-KR, de-DE, fr-FR, es-ES, hi-IN, pt-BR, ru-RU, etc.) : 1 conservée (README racine anglais), 30 autres ignorées — contenu identique traduit, sans valeur technique.
- **Corpus `worked/`** (5 corpus, 36 fichiers, 4.3 MB) : `worked/example/`, `worked/httpx/`, `worked/karpathy-repos/`, `worked/mixed-corpus/`, `worked/rsl-siege-manager/`. Corpus d'exemple avec `graph.json` + `GRAPH_REPORT.md` générés — signalés, non détaillés.
- **Doublons de skills par plateforme** (`graphify/skills/{agents,amp,claude,claw,codex,copilot,droid,kilo,kiro,opencode,pi,trae,vscode,windows}/references/*.md`, ~104 fichiers) : contenu identique d'une plateforme à l'autre — 1 exemplaire (sous `agents/`) suffit.
- **CHANGELOG.md** : historique de versions, non détaillé.
