# 19 — waku-agent

## En-tête
- **Nom** : waku-agent
- **Chemin** : `references/waku-agent/`
- **Type** : agent personnel local
- **Langage principal** : Python
- **Statistiques** : ~150 fichiers (majoritairement `.py`)

## Synthèse
Waku-agent est un assistant personnel local axé sur la transparence et la lisibilité de l'architecture. Son point fort réside dans son code modulaire avec peu ou pas de frameworks abstraits (ex. LangGraph), ce qui permet une compréhension directe de la boucle d'exécution (loop), de la mémoire et des évaluations. 

La valeur pour `graph-orchestrator-smolagents` est remarquable. Les motifs logiciels de Waku-agent (séparation des modèles pour le routage de mémoire, batching de l'historique, moteur de graphe déterministe par vagues avec détection des collisions, et traçage exhaustif) sont en parfaite résonance avec les objectifs P0, P6, P9 et P11 de notre plan d'usine logicielle.

La note globale est 🟢 Haute. Ce dépôt offre un grand nombre de composants Python élégants et robustes, applicables de façon quasi-directe à un orchestrateur multi-agent.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/waku-agent/README.md` | Explication complète de l'architecture (loop, graph, gate) avec diagrammes | 🟢 Haute |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/waku-agent/waku/loop/agent.py` | `run_loop`, `LoopResult` | Boucle agentique pure sans framework (~95 lignes) | 🟢 Haute | Motif fondamental de boucle d'exécution intégrant guardrails et un système d'observateurs (P0). |
| `references/waku-agent/waku/memory/retrieval_gate.py` | `should_retrieve`, `GATE_PROMPT` | Porte de décision (petit LLM) pour la récupération mémoire | 🟢 Haute | Mécanisme très intelligent pour protéger la fenêtre de contexte et éviter l'over-retrieval (P9). |
| `references/waku-agent/waku/graph/engine.py` | `run_graph`, `GraphStateCollision` | Moteur de graphe asynchrone fonctionnant par vagues | 🟢 Haute | Structure déterministe limitant les cycles (`max_visits`) et empêchant l'écrasement silencieux d'états concurrents (P0/P11). |
| `references/waku-agent/waku/memory/consolidation.py` | `consolidate_if_due`, `SUMMARIZER_PROMPT` | Résumé périodique et distillation des faits en mémoire | 🟢 Haute | Modèle concret pour la compaction de contexte différée, extrayant les faits importants sans solliciter l'API à chaque tour (P9). |
| `references/waku-agent/evals/judge/test_response_quality.py` | `geval_metrics`, `test_scheduling_reply_is_helpful` | Évaluation as-judge basée sur DeepEval | 🟢 Haute | Démonstration claire de la bonne pratique séparant les tests de qualité as-judge des tests unitaires déterministes (P6). |
| `references/waku-agent/waku/ops/tracing.py` | `Tracer`, `compose`, `_record_usage` | Export OpenTelemetry, JSONL, et facturation tokens | 🟢 Haute | Tracer universel robuste avec ledger permanent, totalement adapté au stream d'évènements (P11). |

## Exclusions conscientes
- Outils d'intégration (Apple Calendar, Telegram) hors scope pour notre orchestateur Python.
- Interface UI (`static/`, dashboard JS) non nécessaire à un orchestrateur CLI/machine-to-machine.

## Correspondance avec `plan_usine_logicielle.md`
- **P0** : Le moteur central (boucle et événements).
- **P6** : Structure de tests as-judge.
- **P9** : Filtrage du rappel via gate, et batch de consolidation asynchrone.
- **P11** : Traceur d'évènements OTel/JSONL.