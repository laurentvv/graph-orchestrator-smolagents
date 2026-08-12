# 35 — Understand-Anything

## En-tête
- **Nom** : Understand-Anything
- **Chemin** : `references/Understand-Anything/`
- **Type** : Plugin / Framework d'analyse de code (Multi-Agent)
- **Langage principal** : TypeScript (Core) / Python (Scripts de merge graph)
- **Statistiques** : ~500 fichiers, principalement `.ts`, `.md`, `.py`.

## Synthèse
Understand-Anything est un outil d'analyse structurelle et sémantique de code (plugin pour Claude Code/Copilot) qui utilise une approche hybride : Tree-sitter pour l'extraction déterministe (imports, exports) et LLMs pour la sémantique (résumés, intentions, domaines métiers). Le projet génère un graphe de connaissances (Knowledge Graph) complet d'un dépôt.

Pour le projet cible (`graph-orchestrator-smolagents`), ce dépôt est une mine d'or (note globale 🟢 Haute). Les scripts de fusion de graphes en Python (merge-batch-graphs, merge-subdomain-graphs) sont directement réutilisables pour le P9 (Reducers / Compaction). Les prompts d'agents (File Analyzer, Domain Analyzer, Tour Builder) constituent des exemples très pertinents pour orchestrer l'analyse structurelle (P4 / P0) et extraire des domaines métiers (P0). De plus, le schéma de données (schema.ts) apporte des invariants (P0-bis) solides pour modéliser des graphes métiers.

Les réserves concernent principalement la complexité inhérente au framework TypeScript (packages/core) et l'intégration étroite avec les CLI (Claude Code), qui nécessite de n'extraire que les composants algorithmiques ou les prompts.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `understand-anything-plugin/skills/understand/SKILL.md` | Point d'entrée du skill Claude, illustre le lancement de l'analyse (batching). | 🟡 Moyenne |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `understand-anything-plugin/skills/understand/merge-batch-graphs.py` | `merge_graphs`, `normalize_direction` | Fusion de graphes (batch) en Python, résolution des IDs et du sens des arêtes. | 🟢 Haute | Parfait pour le P9 (reducers) ; permet de fusionner des sous-graphes générés par différents sous-agents. |
| `understand-anything-plugin/skills/understand/merge-subdomain-graphs.py` | `STRUCTURAL_EDGE_TYPES`, `merge_graphs` | Fusion de graphes de domaines. Gère la déduplication et l'alerte sur la perte d'arêtes structurelles. | 🟢 Haute | Utile pour consolider la vue métier globale (P9). |
| `understand-anything-plugin/agents/file-analyzer.md` | *Prompting* | Prompt d'agent pour extraire les nœuds et arêtes d'un fichier en combinant vue Tree-sitter et source. | 🟢 Haute | Exemple brillant d'agent spécialisé dans l'extraction KG (P4 / P0). |
| `understand-anything-plugin/agents/domain-analyzer.md` | *Prompting*, `domainMeta` | Agent spécialisé dans l'extraction de domaines, flux et étapes métier. | 🟢 Haute | Aide pour le P0 (Cadre système) à structurer la compréhension du domaine. |
| `understand-anything-plugin/agents/tour-builder.md` | *Fan-In/Fan-Out*, `BFS traversal` | Combinaison script d'analyse de graphe (PageRank/BFS) et prompt pour créer un tour guidé. | 🟢 Haute | Excellent pattern algorithmique pour naviguer dans un graphe (P4 / P0). |
| `understand-anything-plugin/packages/core/src/schema.ts` | `EdgeTypeSchema`, `NODE_TYPE_ALIASES` | Invariants et schéma exhaustif des types de nœuds et d'arêtes. | 🟢 Haute | Modèle de données solide pour le P0-bis (Invariants universels). |
| `understand-anything-plugin/packages/core/src/staleness.ts` | `GraphFreshnessResult` | Détection des fichiers modifiés via Git pour l'analyse incrémentale. | 🟡 Moyenne | Utile pour optimiser les cycles (P9) en ne traitant que ce qui a changé. |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `understand-anything-plugin/packages/core/src/schema.ts` | Code/Schema | Schéma Zod des types autorisés dans le Knowledge Graph. |

## Exclusions conscientes
- Tout le dashboard (UI web, `packages/dashboard` et `packages/viewer`) qui est en React/Vite et n'est pas utile pour l'orchestrateur.
- L'intégration Tree-sitter Wasm (spécifique à l'écosystème Node.js/navigateur).

## Correspondance avec `plan_usine_logicielle.md`
- **P0** : `domain-analyzer.md`, `file-analyzer.md` (prompts de spécialisation).
- **P0-bis** : `schema.ts` (invariants de modélisation KG).
- **P4** : `tour-builder.md`, `file-analyzer.md` (bien que P4 soit hors-scope, ces concepts peuvent influencer le contexte de confiance).
- **P9** : `merge-batch-graphs.py`, `merge-subdomain-graphs.py`, `staleness.ts` (mécanismes de réduction et de mise à jour incrémentale).