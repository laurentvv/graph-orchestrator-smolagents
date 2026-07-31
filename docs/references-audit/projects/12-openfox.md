# 12 — openfox

## En-tête
- **Nom** : OpenFox
- **Chemin** : `references/openfox/`
- **Type** : Assistant de coding "Local-LLM-first" (CLI + serveur + web)
- **Langage principal** : TypeScript (Node.js 24+, Hono/Express, WebSocket, SQLite better-sqlite3)
- **Statistiques** : 597 fichiers pertinents (.md/.ts/.json hors node_modules/.git) ; stack OpenAI-compatible (vLLM, sglang, ollama, llamacpp)

## Synthèse
Assistant de coding local-LLM-first (point commun avec le projet cible via Ollama). La valeur réside dans la **documentation d'architecture de l'engine-loop multi-tour** (event-sourcing + EventStore SSOT + compaction par mode). Le code TS n'est pas portable, mais les diagrammes ASCII détaillés (`runChatTurn`, `runTopLevelAgentLoop`, compaction auto/manuelle, lifecycle context window) sont directement orientants pour concevoir une boucle d'orchestrateur Python avec persistance DuckDB. Note de réutilisabilité globale : **Faible**.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/openfox/docs/ENGINE-LOOP.md` (25 Ko) | Diagramme ASCII exhaustif du tour de chat : `runChatTurn` → `runTopLevelAgentLoop` (for;;), branches post-response (pattern retry, abort, compaction check, truncation, tool calls, compaction mode, normal complete), event types, data flow, reminder reinjection après compaction | Haute (architecture) |
| `references/openfox/docs/MTAE-ARCHITECTURE.md` | Vision engine multi-tour : orchestrator mince + agent loop pur (jamais EventStore direct), 7 sous-fonctions typées (`buildContext`, `streamLLM`, `shouldCompact`, `matchAutoPatterns`, `executeTools`, `drainQueue`, `compactionLoop`), stratégie de test, migration en 4 phases | Haute (architecture) |
| `references/openfox/docs/SESSION-DEBUGGING.md` | Schéma BDD SQLite (projects/sessions/events/settings), event-sourcing + snapshots (`turn.snapshot` = état complet fin de tour), types d'événements, requêtes SQL de debug. Transposable à DuckDB | Haute (persistance) |
| `references/openfox/docs/DESIGN-AUTO-RETRY-PATTERNS.md` | Pattern matching auto-retry configurable (regex sur thinking/content/both, action retry, détection mid-stream, cap retries). Remplace toggle XML hardcoded | Moyenne (concept) |
| `references/openfox/docs/PROVIDER-PLUGINS.md` | Système plugins provider (AuthAdapter, TransportAdapter, Preset), manifest package.json, lifecycle, exemple minimal | Faible (TS) |
| `references/openfox/docs/PR-REVIEW.md` | Workflow PR review agent-assisté (5 phases : setup/review/fix/test/merge), squash-merge via API REST, cherry-pick fixes | Faible (process) |
| `references/openfox/docs/DESIGN-UNIFIED-IMAGE-HANDLING.md` | Fallback vision model | Faible |
| `references/openfox/docs/RELEASE.md`, `REVERSE-PROXY.md` | Release, reverse-proxy | Faible |
| `references/openfox/README.md` | Présentation 2.0 : multi-turn engine, provider dialog, auto-retry, unified image handling, workflows contract-driven | Moyenne (overview) |
| `references/openfox/AGENTS.md` | Guide codebase : stack (Node 24+/Hono/Express/WebSocket/SQLite), structure, build/lint/test commands | Moyenne (orientation) |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/openfox/src/server/chat/` | `orchestrator.ts` (`runChatTurn`, `runGenericAgentTurn`, `runBuilderTurn`, `injectModeReminderIfNeeded`), `agent-loop.ts` (`runTopLevelAgentLoop`, `executeToolBatch`), `conversation-history.ts` (`getConversationMessages`, `buildContextMessagesFromEventHistory`), `stream-pure.ts` (`streamLLMPure`, `consumeStreamGenerator`), `execute-tools.ts`, `auto-patterns.ts` (`matchAutoPatterns`), `retry-limiter.ts`, `request-context.ts` (`assembleAgentRequest`, `buildTopLevelSystemPrompt`), `drain-queue.ts`, `truncation.ts` | Cœur du moteur agent décrit par les docs. La boucle for(;;) avec branches post-response est l'implémentation des diagrammes ASCII | Faible | Code TS ; mais la structure de contrôle (loop + branches) est le modèle à transposer |
| `references/openfox/src/server/context/` | `compactor.ts` (`shouldCompact`, `compactContext`), `image-processor.ts`, `instructions.ts`, `tokenizer.ts`, `nudge-helpers.ts` | Compaction, instructions, tokenizing | Faible | TS ; `shouldCompact(threshold)` transposable |
| `references/openfox/src/server/events/` | `EventStore` (`store.ts`), event types | EventStore SSOT event-sourcing | Faible | TS ; modèle transposable à DuckDB |
| `references/openfox/src/server/session/` | `SessionManager` (`setCurrentContextSize`, `drainAsapMessages`) | Gestion session, queue ASAP | Faible | TS |
| `references/openfox/src/server/db/` | `index.ts`, `sessions.ts`, `projects.ts`, `settings.ts`, `migrations.ts` | Persistance SQLite (better-sqlite3), migrations | Faible | TS ; schéma transposable à DuckDB (cf. SESSION-DEBUGGING.md) |
| `references/openfox/src/server/workflows/` | `executor.ts`, `registry.ts`, `types.ts`, `shell.ts` | Exécuteur workflows contract-driven (steps, transitions, phases plan/build/verification) | Moyenne (concept workflow) | Modèle step/transition transposable |
| `references/openfox/src/server/tools/` (40+ fichiers) | `edit.ts`, `read.ts`, `shell.streaming.ts`, `edit-context.ts`, `file-tracker.ts`, `path-security.ts`, `load-skill.ts`, `session-metadata.ts`, `background-process/`, `ask.ts`, `dev-server.ts`, `diagnostics.ts`, `pdf-utils.ts` | Outils built-in avec tests (edit race, path denial, encoding, shell streaming) | Faible | TS ; concepts de sécurité (path-security, edit mutex) transposables |
| `references/openfox/src/server/agents/` | `registry.ts`, `types.ts` | Registry agents (planner/builder/verifier/sub-agents) | Faible | TS |
| `references/openfox/src/server/sub-agents/` | `SubAgentExecutor` | Exécution sous-agents isolés | Faible | TS ; concept proche DeerFlow |
| `references/openfox/src/server/skills/` | skill loading | Skills (cf. load-skill tool) | Faible | TS |
| `references/openfox/src/server/providers/`, `src/provider/` | providers OpenAI-compatible (vLLM, sglang, ollama, llamacpp) | Intégration LLMs locaux | Faible | TS ; pertinent car même cible Ollama, mais projet cible utilise LiteLLM/DSPy |
| `references/openfox/src/server/` (routes/, ws/, runner/, queue/, commands/, llm/, mcp/, lsp/, git/, terminal/, dev-server/, shared/, utils/, public/), `src/cli/`, `src/shared/`, `web/` | routes HTTP, WS, runner, queue, commands, MCP, LSP | Reste du serveur et frontend | Nulle/Faible | TS/infra |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/openfox/.openfox/workflows/review.workflow.json` | Workflow JSON | Workflow PR review contract-driven (8 steps, transitions, phases build/verification, maxIterations=20). Format JSON déclaratif transposable |
| `references/openfox/.openfox/dev.json`, `workspace.json` | Config runtime | Config dev/workspace OpenFox |
| `references/openfox/.openfox/commands/test-cmd.command.md` | Commande | Exemple commande |
| `references/openfox/.jscpd-web.json`, `package.json`, `tsconfig*.json` | Config lint/build | Config déduplication code, Node/TS |

## Exclusions conscientes
- Tout code TypeScript (Node.js/Hono/Express) : non portable vers Python.
- `web/` (frontend React 19/Tailwind/Zustand/Vite) : UI.
- `e2e/`, `e2e-playwright/`, `dist/`, `docs/screenshots/` : tests e2e, artefacts build, images.
- `docs/RELEASE.md`, `REVERSE-PROXY.md` : opérations produit.
