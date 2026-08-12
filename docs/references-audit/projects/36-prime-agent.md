# XX — prime-agent

## En-tête
- **Nom** : prime-agent
- **Chemin** : `references/prime-agent/`
- **Type** : Agent de coding RLM (Reinforcement Learning Models)
- **Langage principal** : TypeScript
- **Statistiques** : ~1145 fichiers, 919 `.ts`, 96 `.md`.

## Synthèse
Prime Agent est un agent de codage open-source en TypeScript par Prime Intellect. Il s'agit d'un agent "self-improving" (RLM) conçu avec une architecture robuste incluant des capacités d'autonomie (gates, limites), de compaction de contexte via le résumé des opérations sur les fichiers, et une communication en streaming via le Agent Client Protocol (ACP).

Pour `graph-orchestrator-smolagents`, bien que le projet cible soit en Python, Prime Agent offre de très bons patterns architecturaux. Les algorithmes d'anti-loop (gates de validation), la compaction intelligente du contexte, et le streaming NDJSON (ACP) sont directement transposables. La note est 🟡 (Moyenne) uniquement car le portage TS vers Python nécessite un effort d'adaptation.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/prime-agent/AGENTS.md` | Règles de comportement de l'agent, instructions sur la gestion des erreurs et du formatage. | 🟡 Moyenne |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/prime-agent/packages/coding-agent/src/core/compaction/compaction.ts` | `createCompactionSummaryMessage`, `serializeConversation` | Compaction de contexte basée sur un suivi des opérations fichiers (`FileOperations`). | 🟡 Moyenne | L'approche "file ops summary" est très pertinente pour la priorité P9 (Reducers). |
| `references/prime-agent/packages/coding-agent/src/core/autonomous.ts` | `AgentAutonomousConfig`, `AgentAutonomousGateConfig` | Garde-fous d'autonomie (limites de tours, tokens) et "gates" de validation avant de poursuivre. | 🟡 Moyenne | Blueprint algorithmique pour la priorité P3 (Anti-loop). |
| `references/prime-agent/packages/coding-agent/src/core/tools/output-accumulator.ts` | `OutputAccumulator`, `DEFAULT_MAX_BYTES` | Accumulateur stream-safe de stdout/stderr avec troncature et sauvegarde sur disque temporaire. | 🟡 Moyenne | Très utile pour éviter les crashs de contexte (P8 Middlewares) lors de l'exécution de bash. |
| `references/prime-agent/packages/coding-agent/src/modes/acp/acp-mode.ts` | `acpUpdatesForSessionEvent` | Implémentation du Agent Client Protocol (ACP) sur NDJSON pour streamer les événements. | 🟡 Moyenne | Preuve de concept pour P11 (Event stream) avec un protocole normalisé. |
| `references/prime-agent/packages/agent/src/agent-loop.ts` | `AgentMessage`, `ToolExecutionMode` | Boucle d'agent séparant rigoureusement les messages internes de ceux envoyés au LLM (exécution parallèle supportée). | 🟡 Moyenne | Design pattern intéressant pour la robustesse de l'orchestrateur. |

## Exclusions conscientes
- L'interface utilisateur TUI (`packages/coding-agent/src/modes/interactive/`) et la couche d'intégration CLI.
- La bibliothèque IA sous-jacente (`@earendil-works/pi-ai`) qui est un wrapper TypeScript spécifique.

## Correspondance avec `plan_usine_logicielle.md`
- **P3** : `autonomous.ts` (Gates et limites d'autonomie pour contrer les boucles infinies).
- **P8** : `output-accumulator.ts` (Troncature dynamique de la sortie stdout pour les middlewares).
- **P9** : `compaction.ts` (Réduction de contexte basée sur le résumé des actions fichiers accomplies).
- **P11** : `acp-mode.ts` (Streaming NDJSON normalisé via ACP).