# 50 — hunk

## En-tête
- **Nom** : Hunk (`hunk`)
- **Chemin** : `references/hunk/`
- **Type** : Visualiseur et réviseur de diffs en terminal (TUI) conçu spécifiquement pour les changesets générés par des agents IA — basé sur OpenTUI et Pierre diffs, avec support d'annotations inline par des agents IA, broker de sessions daemon, garde-fous d'écriture sur le workspace et détection multi-VCS (Git, Jujutsu, Sapling).
- **Langage principal** : TypeScript / React TUI (OpenTUI) / Bun / Node.js (1 031 fichiers : 712 `.ts`, 117 `.tsx`, 61 `.md`, 59 `.json`, 30 `.mjs`, 14 `.html`, 10 `.css`, 8 `.sh`) ; monorepo avec packages `session-broker`, `session-broker-core`, `session-broker-node`, `session-broker-bun`, `term-video`.
- **Licence** : MIT

## Synthèse
Hunk est un visualiseur de diffs et un outil de revue de code en mode terminal (TUI) pensé dès le départ pour la collaboration entre développeurs et agents autonomes. Contrairement aux outils de diff traditionnels axés uniquement sur le texte brut, Hunk structure la revue de code sous forme de flux multi-fichiers interactif avec navigation latérale, affichage côte-à-côte (*split*) ou empilé (*stacked*), et surtout **intégration d'annotations inline produites par des agents IA directement positionnées à côté du code**.

Pour `graph-orchestrator-smolagents`, Hunk constitue une référence majeure sur plusieurs axes clés :
1. **P6 (Judge & Revue de Code Enrichie)** : Les modules `src/ui/lib/agentAnnotations.ts` et `agentNoteGeometry.ts` formalisent un modèle de données rigoureux pour les annotations d'agents (positionnement de notes inline par ligne/hunk, statuts, niveaux de sévérité, bulles contextuelles popover), apportant le standard idéal pour formater les verdicts de notre nœud Judge.
2. **P0-bis & P8-bis (Garde-Fous d'Écriture Workspace)** : Le module `src/ui/lib/workspaceWriteGuard.ts` implémente une barrière de protection stricte interdisant toute mutation accidentelle ou non autorisée de l'espace de travail lors des phases d'inspection et de revue de code.
3. **P8 & P12 (Broker de Sessions & Multiplexage Daemon)** : Le package `packages/session-broker` implémente un démon léger (`daemon.ts`, `broker.ts`, `brokerState.ts`) gérant des baux de sessions (`lease`), le multiplexage de flux de revue et des limites d'exécution (`limits.ts`), permettant à plusieurs agents ou terminaux de communiquer et de réviser des diffs en parallèle sans conflit.
4. **P1 (Algorithmique de Réconciliation de Diff)** : `src/ui/highlights/reconcile.ts` et `useHighlightedDiff.ts` fournissent un algorithme robuste pour recalculer et synchroniser les surlignages et les curseurs lors de l'application incrémentale de patchs.
5. **P10 (Skills de Revue de Diff)** : Le skill `skills/hunk-review/SKILL.md` formalise la façon dont un LLM doit analyser un ensemble de diffs et émettre des commentaires de revue ciblés et structurés.

Note globale : **🟢 Haute** — architecture remarquable pour le modèle de données des annotations d'agents, la protection du workspace en lecture/revue et le broker de sessions d'agent.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/hunk/AGENTS.md` | Charte opérationnelle d'ingénierie du dépôt Hunk : standards TUI, invariants de typage, gestion des états réactifs | **Haute** (P0-bis — source d'invariants de code et bonnes pratiques) |
| `references/hunk/CLAUDE.md` | Directives de développement pour Claude Code au sein du repo Hunk | Moyenne (P0 — directives d'outillage) |
| `references/hunk/README.md` | Présentation complète de Hunk, capture d'écrans, support multi-VCS et intégrations | Moyenne (P6 — vue d'ensemble du réviseur de diffs) |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/hunk/src/ui/lib/agentAnnotations.ts` | `AgentAnnotation`, `AgentNote`, `AgentAnnotationSeverity`, `createAgentAnnotation`, `filterAnnotationsByFile` | Modèle de données pour les annotations de code émises par des agents IA (positions de lignes, sévérité, contenu, ancrage de hunk) | **Haute** | P6 : Standard idéal pour structurer les findings et retours de revue du nœud Judge |
| `references/hunk/src/ui/lib/agentNoteGeometry.ts` | `computeAgentNoteGeometry`, `calculatePopoverBounds`, `fitInViewport` | Calcul géométrique du positionnement des notes d'agents à côté des lignes modifiées sans débordement | **Haute** | P6 : Logique d'affichage et de disposition des retours de test/review |
| `references/hunk/src/ui/lib/workspaceWriteGuard.ts` | `WorkspaceWriteGuard`, `assertWritable`, `acquireWriteLock`, `releaseWriteLock`, `ReadOnlyViolationError` | Garde-fou d'intégrité interdisant toute écriture sur le système de fichiers lors des opérations de consultation ou de review | **Haute** | P0-bis+P8-bis : Sécurité essentielle pour verrouiller le workspace pendant les passes du Judge, Tester ou Linter |
| `references/hunk/src/ui/highlights/reconcile.ts` | `reconcileHighlights`, `mapLinePositions`, `shiftHighlights` | Algorithme de réconciliation des positions de lignes et des highlights après application ou modification de hunks | **Haute** | P1+P6 : Maintien de la cohérence des numéros de lignes lors de l'application de patchs |
| `references/hunk/src/ui/diff/useHighlightedDiff.ts` | `useHighlightedDiff`, `parseDiffHunks`, `computeDiffMetrics` | Moteur d'analyse et de décomposition de diffs unifiés en structures hiérarchiques exploitables | **Haute** | P1+P6 : Analyse fine des diffs pour l'évaluation de modifications de code |
| `references/hunk/src/ui/fileViews/renderPlan.ts` | `RenderPlan`, `createRenderPlan`, `optimizeViewportLines` | Planification du rendu de fenêtres de fichiers larges avec fenêtrage adaptatif et calcul d'overscan | Moyenne | P9 : Gestion de la compaction et du fenêtrage de données volumineuses |
| `references/hunk/packages/session-broker/src/broker.ts` | `SessionBroker`, `registerSession`, `routeMessage`, `closeSession` | Démon broker gérant le routage de messages et la coordination entre sessions de revue concurrentes | **Haute** | P8+P12 : Architecture de coordination de sessions concurrentes |
| `references/hunk/packages/session-broker-core/src/brokerState.ts` | `BrokerState`, `SessionEntry`, `LeaseStatus`, `pruneExpiredLeases` | Gestionnaire d'état du broker avec baux temporisés (`lease`) et purge automatique des sessions expirées | **Haute** | P8+P12 : Gestion de baux d'exécution et de cycle de vie de sessions |
| `references/hunk/skills/hunk-review/SKILL.md` | `hunk-review`, `ReviewStrategy`, `InlineNoteFormat` | Skill d'agent spécialisée pour la revue de code et la génération d'annotations sur des changements git | **Haute** | P10+P6 : Prompt et canevas d'évaluation de diffs pour agents autonomes |
| `references/hunk/skills/hunk-extensions/SKILL.md` | `hunk-extensions`, `ExtensionManifest`, `CapabilityLease` | Modèle de conception d'extensions et d'outils modulaires pour l'analyse de code | Moyenne | P10 : Spécification de modularité de skills/extensions |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/hunk/packages/session-broker-core/src/types.ts` | Session Broker Schemas | Définitions de types pour les messages, connexions et baux du broker de sessions |
| `references/hunk/src/ui/fileViews/types.ts` | File View Schemas | Structures de données pour les vues de fichiers, layouts (split/stacked) et curseurs |

## Exclusions conscientes
| Chemin | Motif d'exclusion |
|---|---|
| `references/hunk/website/` | Site web statique de documentation (Astro/Starlight). Ignorer. |
| `references/hunk/packages/term-video/` | Outil interne de génération de vidéos promotionnelles dans le terminal. Ignorer. |
| `references/hunk/nix/`, `flake.nix` | Fichiers de packaging pour la distribution Nix/NixOS. Ignorer. |

## Correspondance avec `plan_usine_logicielle.md`
- **P0-bis** : `workspaceWriteGuard.ts` (verrouillage strict en écriture lors des phases d'analyse/revue).
- **P1** : `useHighlightedDiff.ts` & `reconcile.ts` (recalibrage des positions de lignes et analyse de hunks).
- **P6** : `agentAnnotations.ts`, `agentNoteGeometry.ts` & `hunk-review` (standard de données pour les annotations de revue du Judge).
- **P8 / P8-bis** : `workspaceWriteGuard.ts` (confinement de l'autorité d'écriture) + `session-broker` (gestion de baux et timeouts de sessions).
- **P10** : `skills/hunk-review/SKILL.md` (doctrine de revue de code assistée par agent).
- **P11** : `session-broker-core` (flux d'événements de sessions et télémétrie de review).
- **P12** : `SessionBroker` & `BrokerState` (gestion et isolation multi-sessions concurrentes).
