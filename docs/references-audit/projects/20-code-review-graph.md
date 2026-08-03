# 20 — code-review-graph

## En-tête
- **Nom** : code-review-graph
- **Chemin** : `references/code-review-graph/`
- **Type** : Orchestrateur local-first de **graphe de connaissance structurel** pour code review (parse un repo avec Tree-sitter → graphe nodes/edges → exposé via MCP/CLI pour nourrir un LLM externe avec un sous-graphe token-optimisé). Aussi une GitHub Action + extension VSCode.
- **Langage principal** : Python 3.10+ (`code_review_graph/`, 156 `.py`) + TypeScript (extension VSCode, 27 `.ts`)
- **Statistiques** : 362 fichiers hors `.git/` (156 `.py`, 47 `.md`, 27 `.ts`, 24 `.csv` de benchmarks, 15 `.yml`+7 `.yaml`). Version 2.3.7, licence MIT.
- **Stack** : Python (`fastmcp` MCP, `tree-sitter`+`tree-sitter-language-pack`, `networkx`, **SQLite** `graph.db`, `igraph` optionnel, embeddings optionnels) + GitHub Action + VSCode ext.
- **Persistance** : **SQLite** (`graph.db`) — schéma conceptuel inspirant mais migrations/requêtes non portables vers DuckDB.

## Synthèse
Ce n'est **pas** un Judge LLM avec rubric critical/high/medium/low au sens du P6 cible — c'est un **moteur d'analyse d'impact (blast radius) et de scoring de risque pré-review**. Le « review » se fait ensuite par un LLM externe (via MCP) nourri avec un sous-graphe token-optimisé. La valeur pour le projet cible est donc concentrée sur trois axes concrets :

1. Un **modèle de risk score composite multi-facteurs** (`compute_risk_score` ∈ [0,1] : flow participation cap 0.25, cross-community callers cap 0.15, test coverage transitive 0.30→0.05, security keywords +0.20, caller count cap 0.10, churn cap 0.15) directement transposable au nœud Judge pour prioriser ses findings.
2. Un **système de scoring d'impact par relaxation BFS** (edge weights par type de relation + decay géométrique par profondeur `IMPACT_DEPTH_DECAY=0.6`, plancher `0.05`) pour le blast radius.
3. Des **patterns de structuration de feedback de review** (skills + prompts MCP) : minimal→standard→verbose, regroupement par niveau de risque, GO/NO-GO.

**Réserves** :
- Persistance **SQLite** alors que le projet cible est **DuckDB** : les requêtes SQL de scoring sont en partie réutilisables mais le schéma/migrations ne l'est pas directement (la table `risk_index(node_id, risk_score, caller_count, test_coverage, security_relevant)` est un bon **modèle de schéma** à réimplémenter en DuckDB).
- Couplage fort à `fastmcp`/MCP et Tree-sitter : les briques « algorithme » se détachent, les briques « tool MCP / CLI / parsers multi-langages » moins.
- Code dense (`graph.py` ~1700 L, `flows.py` 718, `refactor.py` 613) — l'extraction demande du découpage.
- **Aucun prompt propriétaire leaké** : les prompts (`prompts.py`, `skills/`) sont des workflows MCP originaux (enchaînements d'appels d'outils), citables/adaptables librement sous MIT. `docs/LEGAL.md` confirme zero telemetry, MIT, tout local.

Note globale : **🟡 Moyenne**. Le code est propre, testé (tests unitaires sur `compute_risk_score`), licence claire. Mais l'architecture MCP+Tree-sitter+SQLite ne colle pas à la cible DSPy+smolagents+DuckDB : on transpose des **modèles de scoring** et des **patterns de structuration**, pas le runtime. La valeur réelle est de fournir des **signaux quantitatifs** au Judge (qui aujourd'hui ne s'appuie que sur du qualitatif LLM) — c'est un enrichissement, pas un drop-in.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/code-review-graph/docs/LEGAL.md` | Confirmation : MIT, zero telemetry, tout local — autorise citation/adaptation | Haute |
| `references/code-review-graph/skills/review-pr/SKILL.md` | Skill workflow de review PR avec sections Risk Assessment / File-by-File / Missing Tests / Recommendations | Haute |
| `references/code-review-graph/skills/review-changes/SKILL.md` | Skill workflow de review de changes (findings grouped by risk level high/medium/low) | Haute |
| `references/code-review-graph/evaluate/` (24 `.csv`) | Benchmarks impact_accuracy / multi_hop / token_efficiency sur flask/fastapi/express/gin/httpx — méthodo d'évaluation d'un Judge | Moyenne |
| `references/code-review-graph/README.md` (+ 5 traductions) | Marketing produit, très volumineux — ignorer pour l'audit technique | Faible |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/code-review-graph/code_review_graph/changes.py` | `compute_risk_score(store, node, churn_counts) -> float` (l. 313-374), `analyze_changes(...)` (l. 382-531) → `risk_score`, `changed_functions`, `review_priorities` (top 10 triés), `test_gaps` | **Score de risque 0.0-1.0 multi-facteurs** : flow participation (cap 0.25, pondérée par criticalité), cross-community callers (cap 0.15), test coverage transitive (0.30→0.05 si ≥5 tests), security keywords (+0.20), caller count (cap 0.10), churn optionnel (cap 0.15). `review_priorities` = top-10 par score desc. | **Haute** | Transposer les poids/plafonds en signaux d'entrée du Judge ; `review_priorities` inspire l'ordonnancement des findings. Tests dans `tests/test_changes.py` (l. 220-345) donnent un cahier de recette |
| `references/code-review-graph/code_review_graph/constants.py` | `SECURITY_KEYWORDS` (frozenset de 26 termes, l. 33-99), `IMPACT_EDGE_WEIGHTS` (CALLS 1.0, INHERITS/OVERRIDES/IMPLEMENTS 0.9, TESTED_BY 0.7, REFERENCES/DEPENDS_ON 0.6, IMPORTS_FROM 0.5, CONTAINS 0.3), `IMPACT_EDGE_DIRECTIONS`, `IMPACT_DEPTH_DECAY=0.6`, `IMPACT_SCORE_FLOOR=0.05` | **Tables de poids par type de relation** + decay géométrique par hop. Séparation explicite review-risk weights vs community-affinity weights. | **Haute** | Réutiliser `IMPACT_EDGE_WEIGHTS` telle quelle pour pondérer l'impact d'un finding sur le graphe de dépendances ; `SECURITY_KEYWORDS` pour auto-tag de findings security |
| `references/code-review-graph/code_review_graph/graph.py` | `get_impact_radius(...)` (l. 1317-1640), `get_impact_radius_sql(...)` (relaxation SQLite best-score), `get_impact_radius_networkx(...)` | **Blast radius par relaxation best-score bornée** : frontière itérative, `score * edge_weight * IMPACT_DEPTH_DECAY`, plancher `IMPACT_SCORE_FLOOR`, `MAX_IMPACT_NODES=500`, deux moteurs (SQL vs networkx). Retourne `impact_scores` (qn→score) ordonné DESC. | Moyenne | Algorithme de propagation d'impact d'un changement ; pour P6, permet de scorer « ce finding touche N nœuds à score élevé ». Voir P4 repo map (hors-scope) |
| `references/code-review-graph/code_review_graph/flows.py` | `compute_criticality(flow, adj) -> float` (l. 325-394), `detect_entry_points`, `trace_flows` | **Score de criticalité d'un flux d'exécution** : file_spread 0.30 + external_calls 0.20 + security 0.25 + test_gap 0.15 + depth 0.10. Détection d'entry points via décorateurs framework + name patterns. | Moyenne | Un finding sur un flow critique (score élevé) est plus prioritaire ; la rubric weights est directement adaptable |
| `references/code-review-graph/code_review_graph/tools/context.py` + `tools/hints.py` | `get_minimal_context(...)` (l. 99-176) bucketing `risk = "high" if >0.7 elif >0.4 "medium" else "low"`, `_extract_warnings(result)` (hints l. 318-344) | **Seuils de bucketing risk→label** (>0.7 high, >0.4 medium) + extraction de warnings (test gaps, high risk, coupling). Couplage minimal→standard→verbose. | **Haute** | Seuils 0.7/0.4 à calibrer pour la rubric critical/high/medium/low du Judge ; pattern de warnings à injecter dans le prompt Judge |
| `references/code-review-graph/code_review_graph/analysis.py` | `find_surprising_connections(store, top_n=15)` (l. 213-315), `find_hub_nodes`, `find_bridge_nodes` | **Détection de couplage architectural surprenant** : scoring d'edges anormaux (cross-community +0.3, cross-language +0.2, peripheral-to-hub +0.2, cross-file-type), utile pour générer des findings « dépendance suspecte ». | Moyenne | P6 connexe (findings de couplage) + signaux pour l'Architect |
| `references/code-review-graph/code_review_graph/eval/scorer.py` + `eval/benchmarks/impact_accuracy.py` | `compute_precision_recall(predicted, actual)`, `compute_mrr(correct, results)`, `compute_token_efficiency(raw, graph)` ; benchmark 2 modes ground-truth (graph-derived circulaire vs co-change « honnête ») | **Métriques d'évaluation d'un Judge/retrieval** (P/R/F1, MRR, token efficiency) + méthodo de benchmark (différencier upper-bound circulaire et métrique honnête). | Moyenne | Transversal : pour mesurer la qualité du nœud Judge sur un corpus |
| `references/code-review-graph/code_review_graph/refactor.py` | `find_dead_code` (l. 244-613), anti-faux-positifs via entry points/mock patterns | Détection de code mort multi-passes avec gardes contre les faux positifs. | Faible | Utile seulement si le Judge doit signaler du code mort (hors P6 cœur) |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/code-review-graph/action.yml` | config | GitHub Action glue — non portable, juste pour comprendre l'interface CI |
| `references/code-review-graph/code_review_graph/constants.py` | spec (constantes) | Tables de poids canoniques (`IMPACT_EDGE_WEIGHTS`, `SECURITY_KEYWORDS`, `IMPACT_DEPTH_DECAY`) — les valeurs de calibration à réutiliser |
| `references/code-review-graph/docs/schema` (éventuel) | spec | Schéma SQLite `nodes/edges/communities/flows/risk_index` — bon modèle de schéma à réimplémenter en DuckDB |

## Exclusions conscientes
- `references/code-review-graph/code-review-graph-vscode/` (27 `.ts`) — UI VSCode, non portable.
- `references/code-review-graph/action.yml`, `.github/`, `scripts/render_pr_comment.py` — intégration CI GitHub propriétaire au workflow.
- `references/code-review-graph/code_review_graph/migrations.py` + persistance SQLite — le projet cible est DuckDB ; le **schéma conceptuel** est inspirant mais les migrations/requêtes ne se portent pas. La table `risk_index` est un bon **modèle de schéma**.
- `references/code-review-graph/code_review_graph/` runtime MCP (`fastmcp`, prompts MCP, daemon) — le projet cible est DSPy+smolagents ; on garde les algorithmes, pas le runtime MCP.
- Parsers multi-langages (`jedi_resolver`, `spring_resolver`, `tsconfig_resolver`, `hcl_resolver`, `rescript_resolver`, `custom_languages`) — non pertinents pour un orchestrateur de coding Python.
- Embeddings/cloud providers (`embeddings.py`, options openai/google/minimax/voyage) — hors-scope, et le projet cible est LLM locaux.
- `references/code-review-graph/diagrams/` (assets, d3.v7.min.js embarqué) — assets de démo.
- README marketing (44 Ko) + 5 traductions — ignorer pour l'audit technique.

## Correspondance avec `plan_usine_logicielle.md`
- **P6 (Judge / Findings / TDD)** : `changes.py::compute_risk_score` (brique 1) et `constants.py::IMPACT_EDGE_WEIGHTS` (brique 2) sont presque utilisables tels quels comme **signaux quantitatifs d'entrée du Judge** (aujourd'hui le Judge ne s'appuie que sur du qualitatif LLM). `tools/context.py` (brique 5) fournit les **seuils 0.7/0.4** à calibrer pour la rubric critical/high/medium/low. `skills/review-pr` (brique 6) inspire le **format de sortie structuré** (findings groupés par risk level + recommendations). `eval/scorer.py` (brique 8) fournit les **métriques** pour benchmarker le Judge (P/R/F1, MRR). **Action concrète suggérée** : extraire un module `judge_signals.py` (scoring composite test coverage + sécurité + criticalité → `risk_score ∈ [0,1]` + bucket) injecté comme contexte structuré au prompt du Judge. Complémentaire d'open-swe (09, findings de revue) et system-prompts (17, professional objectivity) — pas en concurrence.
