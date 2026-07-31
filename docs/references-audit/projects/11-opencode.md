# 11 — opencode

## En-tête
- **Nom** : opencode (OpenCode AI)
- **Chemin** : `references/opencode/`
- **Type** : Agent de coding open source (CLI+TUI+serveur embarqué), monorepo 32 packages
- **Langage principal** : TypeScript (Bun + Effect-TS + Solid/OpenTUI)
- **Statistiques** : 3606 fichiers pertinents (.md/.ts/.tsx/.json hors node_modules/.git/package-lock) — le plus volumineux des 13 ; specs/v2 = 9 cahiers des charges

## Synthèse
Agent de coding mature entièrement TypeScript/Effect-TS — écosystème incompatible avec Python (DSPy/smolagents). La valeur pour le projet cible réside UNIQUEMENT dans `specs/v2/` (cahiers des charges de protocole agent : session event-sourcing, tools, config, provider/model, permission/provider policy) et l'organisation monorepo. Le code TS n'est pas portable, mais les spécifications décrivent des contrats de haut niveau (event-sourcing, context epochs/compaction, permission/provider policy) transposables conceptuellement à un orchestrateur Python. Note de réutilisabilité globale : **Faible**.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/opencode/specs/v2/session.md` | Session V2 : prompt admission/promotion (inbox durable steer/queue), Context Epochs (baseline immutable + updates chronologiques), compaction auto/overflow, event-sourcing, tableau parité V1→V2 | Moyenne (concepts) |
| `references/opencode/specs/v2/tools.md` | Outils V2 : `Tool.make` opaque, Tool.Context (sessionID/agent/assistantMessageID/toolCallID), registration scopée, output bounding, échecs (ToolFailure vs interruption) | Moyenne |
| `references/opencode/specs/v2/config.md` | Revue config V2 en 11 groupes (providers, agents, permissions, mcp, compaction), décisions keep/remove/redesign par champ | Moyenne |
| `references/opencode/specs/v2/provider-policy.md` | Policy allow/deny (wildcard, last-match-wins), precedence inversée (user-global > repo), migration legacy enabled/disabled_providers | Moyenne |
| `references/opencode/specs/v2/provider-model.md` | Schémas Provider/Model catalog Effect, endpoints (openai/anthropic/aisdk), variants, cost/limit, plugins built-in | Faible (TS) |
| `references/opencode/specs/v2/instructions.md` | Directives port core V2 : services conteneurs typés, plugin hooks (Immer drafts + cancel), boot composition | Faible (Effect) |
| `references/opencode/specs/v2/todo.md` | Roadmap V2 : agent loop Effect-native, prompt inbox durable, continuation recovery différée, hot-reload | Faible |
| `references/opencode/specs/v2/schema-changelog.md` | Historique changements schema durable V2 (compaction, context epochs, tool registry, apply_patch, permissions) | Faible (référence) |
| `references/opencode/specs/v2/catalog-config-plugin-lifecycle.md` | Options lifecycle catalog/config/plugin (replayable transforms, reload) | Faible |
| `references/opencode/specs/project.md` | API HTTP project/session (REST multi-project/worktree) | Faible |
| `references/opencode/specs/tui-package.md` | Plan extraction package TUI (10 sections, ownership boundaries CLI/SDK) | Faible |
| `references/opencode/README.md`, `AGENTS.md`, `CONTEXT.md`, `CONTRIBUTING.md`, `packages/docs/README.md` | Docs produit/orientation | Faible |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/opencode/packages/core/src/session/` (18 fichiers) | `execution.ts`, `run-coordinator.ts`, `context-epoch.ts`, `compaction.ts`, `projector.ts`, `input.ts`, `prompt.ts`, `store.ts`, `history.ts` | Cœur session V2 Effect-native : coordinateur, epochs contexte, compaction, projection event-sourcing, inbox | Faible | Concepts transposables (event-sourcing, compaction) mais Effect-TS pur |
| `references/opencode/packages/core/src/tool/` | `Definition`, `Tool.make`, `Tool.Context`, `ToolFailure` | Registry outils typé, output bounding, permission-checked built-ins | Faible | Contrat élégant mais indissociable d'Effect |
| `references/opencode/packages/core/src/permission/` | `PermissionV2.Ruleset`, `assert` | Ruleset ordonné `{action, resource, effect: allow/deny/ask}` | Faible | Modèle policy transposable |
| `references/opencode/packages/core/src/skill/` | skill registry, skill tool | Skills à chargement différé permission-filtered | Faible | Concept proche DeerFlow/Prompt-Vault |
| `references/opencode/packages/core/src/` (485 fichiers) | account, config, credential, database, event, filesystem, oauth, permission, plugin, project, pty, reference, ripgrep, session, share, skill, system-context, tool | Core V2 domaines typés | Faible | TS/Effect |
| `references/opencode/packages/llm/src/` (151 fichiers) | `llm.ts`, `provider.ts`, `tool.ts`, `cache-policy`, `route`, `protocols`, `providers/` (anthropic, openai, openai-compatible, google, amazon-bedrock, azure, github-copilot, openrouter, xai, cloudflare) | SDK LLM multi-provider | Faible | Multi-provider mais TS ; cible utilise DSPy/smolagents |
| `references/opencode/packages/opencode/src/session/` (20 fichiers) | `prompt.ts`, `compaction.ts`, `retry.ts`, `reminders.ts`, `overflow.ts`, `llm.ts`, `system.ts`, `message.ts`, `processor.ts` | Application legacy session | Faible | Legacy TS |
| `references/opencode/packages/opencode/src/tool/` (25 fichiers) | `task.ts`, `apply_patch.ts`, `read.ts`, `edit.ts`, `write.ts`, `grep.ts`, `glob.ts`, `shell.ts`, `webfetch.ts`, `websearch.ts`, `skill.ts`, `todo.ts`, `plan.ts`, `question.ts`, `lsp.ts` | Outils built-in legacy | Faible | Concepts d'outils transposables |
| `references/opencode/packages/opencode/src/` (707 fichiers) | `session/`, `tool/`, `provider/`, `agent/`, `mcp/`, `plugin/`, `config/`, `server/`, `cli/` | Application legacy complète | Faible | Riche mais legacy TS |
| `references/opencode/packages/tui/` (239), `ui/` (240), `web/`, `desktop/`, `console/`, `storybook/`, `session-ui/` | composants/routes/thèmes/renderers | Frontends TUI/web React/Solid | Nulle | Interface TS pure |
| `references/opencode/packages/{schema,plugin,protocol,server,client,cli,sdk,...}` | schemas, plugins, SDKs, intégrations | Infra/SDK | Faible/Nulle | TS |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/opencode/specs/v2/*.md` (9 fichiers) | Specs protocole V2 | config, session, tools, provider-model, provider-policy, instructions, todo, schema-changelog, catalog-config-plugin-lifecycle |
| `references/opencode/specs/project.md`, `specs/tui-package.md` | Specs HTTP/archi | API project/session, extraction TUI |
| `references/opencode/.opencode/` | Config dogfooding | agents (triage.md, duplicate-pr.md), commands (commit.md, changelog.md, issues.md, learn.md, translate.md), skills (effect/SKILL.md), tools (github-triage.ts, github-pr-search.ts), glossary (16 langues i18n), themes, tui.json |
| `references/opencode/package.json` | Config monorepo | Workspace Bun |

## Exclusions conscientes
- Tout code TypeScript (Effect-TS) : non portable vers Python (DSPy/smolagents).
- `packages/app/` (e2e/performance/storybook) : tests frontend non pertinents.
- Frontends (`tui/`, `ui/`, `web/`, `desktop/`, `console/`, `storybook/`, `session-ui/`) : UI TS.
- `infra/`, `nix/`, `.github/`, `.vscode/`, `.zed/`, `artifacts/` : infra/tooling.
- Glossaires i18n (`.opencode/glossary/*.md`, 16 langues) : localisation produit.
