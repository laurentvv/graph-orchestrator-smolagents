# 19 — room

## En-tête
- **Nom** : room (Quoroom)
- **Chemin** : `references/room/`
- **Type** : Framework d'orchestration multi-agents
- **Langage principal** : TypeScript
- **Statistiques** : 360 fichiers, ~250 `.ts`/`.tsx`, 1 appli UI (React) + 1 backend (Node)

## Synthèse
Quoroom ("room") est un projet open-source expérimental de framework "swarm" (intelligence en essaim) fonctionnant en local. Il orchestre un ensemble d'agents répartis en rôles (Queen, Workers, Quorum) avec des mécanismes de décision asynchrones, des accès mémoire, et l'utilisation d'outils web. 

Bien que le projet soit écrit en TypeScript (et donc non directement copiable dans `graph-orchestrator-smolagents` qui est en Python), il regorge de **patterns d'architecture exceptionnels** pour la résilience et la performance. 

On y trouve notamment un excellent contournement des limites de caractères Windows, une approche "singleton" pour les navigateurs headless (OpenClaw) qui divise par 10 la latence des appels web, et un modèle pub/sub extrêmement élégant pour le fan-out d'événements. Note globale 🟡 Moyenne car adaptation linguistique nécessaire, mais valeur algorithmique 🟢 Haute.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `README.md` | Présentation des concepts Queen/Workers/Quorum. | 🟡 Moyenne |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `src/shared/claude-code.ts` | `resolveNodeScript`, `executeClaudeCode` | Workaround pour extraire le script JS des wrappers `.cmd` Windows, évitant la limite de 8191 caractères de `cmd.exe`. | 🟢 Haute | Stratégique pour P8-bis (Sandbox), transposable en Python via `subprocess`. |
| `src/shared/web-tools.ts` | `_browser`, `getBrowser`, `webFetch` | Pattern "OpenClaw" : navigateur Playwright instancié une seule fois (singleton) et réutilisé par contextes. | 🟢 Haute | Réduit le TTI des requêtes web (P10 Skills) de ~2s à quelques ms. |
| `src/server/event-bus.ts` | `EventBus`, `wildcardHandlers` | Implémentation minimaliste pub/sub via Map/Set pour router les événements vers les WebSockets. | 🟢 Haute | Pattern canonique pour P11 (Event stream) très facile à écrire en Python natif. |
| `src/shared/rate-limit.ts` | `RATE_LIMIT_PATTERNS`, `detectRateLimit` | Parsing par expressions régulières (429, quotas) sur la sortie brute du LLM. | 🟡 Moyenne | Rustique mais robuste pour P8 (Middlewares anti-crash). |
| `src/shared/agent-executor.ts` | `compressSession` | Pré-troncature naïve (2000 caractères par tour) de l'historique avant de demander un résumé au modèle. | 🟡 Moyenne | Inspirant pour P9 (Compaction), évite le dépassement de contexte lors de la compression elle-même. |
| `src/shared/quorum.ts` | `announce`, `QuorumDecision` | Mécanisme de vote asynchrone ("Reine" annonce, "Worker" peut objecter pendant X minutes). | 🟡 Moyenne | Intéressant pour des scopes multi-utilisateurs ou P12. |

## Exclusions conscientes
- `src/ui/` : Application React / Tailwind complète (Dashboard, composants), totalement hors scope pour le backend orchestrateur Python.
- `src/mcp/` : Serveur MCP implémenté avec le SDK TS. L'orchestrateur Python utilisera d'autres implémentations.
- `e2e/` : Tests Playwright applicatifs.

## Correspondance avec `plan_usine_logicielle.md`
- **P8-bis** : `src/shared/claude-code.ts` (contournement cmd Windows pour exécution robuste).
- **P8** : `src/shared/rate-limit.ts` (mécanisme de regex pour détecter le rate-limit).
- **P9** : `src/shared/agent-executor.ts` (troncature avant compression session).
- **P10** : `src/shared/web-tools.ts` (pattern OpenClaw pour les outils navigateurs rapides).
- **P11** : `src/server/event-bus.ts` (architecture pub/sub Map/Set).