# 27 — browser-use

## En-tête
- **Nom** : browser-use
- **Chemin** : `references/browser-use/`
- **Type** : Framework d'automatisation de navigateur par IA
- **Langage principal** : Python
- **Statistiques** : 476 fichiers, ~385 `.py`

## Synthèse
`browser-use` est une bibliothèque Python permettant à un agent LLM d'utiliser un navigateur web (remplir des formulaires, extraire des données, QA automation). Il supporte de multiples LLMs et interagit avec le navigateur.
Pour `graph-orchestrator-smolagents`, cette référence est extrêmement précieuse (Note globale 🟢) pour sa capacité à gérer l'état du navigateur, la compaction du DOM (HTML vers Markdown), et son système d'évaluation (`judge`) pour évaluer les traces d'exécution de manière autonome.
Aucune réserve majeure, le code est propre, bien typé, et hautement portable.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/browser-use/AGENTS.md` | Directives et règles de développement pour l'agent. | 🟢 Haute |
| `references/browser-use/CLAUDE.md` | Commandes de build, test, lint, et bonnes pratiques d'architecture. | 🟢 Haute |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/browser-use/browser_use/agent/judge.py` | `construct_judge_messages` | Construit les prompts pour qu'un Judge LLM évalue la trace d'un agent. | 🟢 Haute | Implémentation directe pour P6 Judge avec support vision. |
| `references/browser-use/browser_use/dom/markdown_extractor.py` | `extract_clean_markdown` | Réduit un arbre DOM (HTML) en markdown épuré. | 🟢 Haute | Parfait pour P9 Compaction et l'extraction de contexte allégé. |
| `references/browser-use/browser_use/agent/prompts.py` | `SystemPrompt`, `cache=True` | Gestion dynamique des prompts système selon le modèle avec caching. | 🟢 Haute | Pattern robuste pour P0 Cadre système. |
| `references/browser-use/browser_use/agent/message_manager/service.py` | `MessageManagerState` | Historique des messages et formatage. | 🟡 Moyenne | Offre une base pour le flux P11. |

## Correspondance avec `plan_usine_logicielle.md`
- **P0** : Gestion dynamique et caching des prompts système (`prompts.py`).
- **P6** : Mécanisme d'évaluation LLM via Judge (`judge.py`).
- **P9** : Extraction et réduction du DOM en Markdown (`markdown_extractor.py`).
- **P11** : Gestion de l'état des messages (`message_manager/service.py`).
