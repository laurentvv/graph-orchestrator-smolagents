# 10 — crush

## En-tête
- **Nom** : crush
- **Chemin** : `references/crush/`
- **Type** : agent de coding terminal multi-modèle (écosystème Charm)
- **Langage principal** : Go (module `github.com/charmbracelet/crush`, `go 1.26.5`)
- **Statistiques** : 618 fichiers pertinents (.go/.md/.json/.yaml/.toml/.mod), 546 fichiers Go, ~41 MB total. Racine : `README.md`, `AGENTS.md`, `schema.json` (schéma config), `go.mod`, `main.go`.
- **Dépendances clés** : `charm.land/fantasy` (abstraction LLM multi-provider), `charm.land/bubbletea/v2` (TUI), `charm.land/catwalk` (catalogue modèles), SQLite via sqlc.

## Synthèse
Crush est un assistant de coding CLI/TUI de Charm, écrit en Go, qui orchestre des conversations LLM tool-use par session. L'architecture centrale tourne autour d'un **`Coordinator`** qui gère des agents nommés (`coder` = agent principal, `task` = sub-agent polyvalent invoqué comme un tool `agent`) et d'un **`sessionAgent`** qui exécute la boucle de streaming, gère la queue de prompts, l'annulation, l'auto-summarize et la persistance. Les providers (Anthropic, OpenAI, Gemini, Bedrock, Copilot, Hyper, etc.) sont abstraits par `charm.land/fantasy`. Le système est extensible via LSP, MCP (stdio/http/sse) et **Agent Skills** (standard `agentskills.io`). Un moteur de **hooks** (compatible Claude Code) permet de bloquer/réécrire/auto-approuver les appels d'outils via scripts shell avant la vérification de permissions.

Pour `graph-orchestrator-smolagents`, l'intérêt principal réside dans :
1. **`loop_detection.go`** (`hasRepeatedToolCalls`) — anti-loop par hash SHA256 des interactions tool, isolé et trivialement portable en Python pour durcir le circuit-breaker des Coders.
2. Le **pattern sub-agent** (`runSubAgent` + tool `agent` + accumulation de coût parent→enfant) — modèle d'orchestration fan-out pertinent.
3. Le **filetracker** (suivi fichiers lus par session), le concept de **hooks** PreToolUse (deny/allow/halt + rewrite d'input), et le **permission service** (allowlist + approbation interactive).

Note de réutilisabilité globale : **Moyenne** (l'anti-loop est le seul élément à valeur d'export directe Haute ; le reste est conceptuel ou non portable).

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/crush/docs/hooks/README.md` | **Guide hooks complet** (humain+agent) : exécution via shell POSIX embarqué, events, input (env vars + stdin JSON), output envelope (`decision`/`halt`/`reason`/`context`/`updated_input`), exit codes (0/2/49), aggregation multi-hooks, compat Claude Code | Moyenne (spéc de hooks adaptable) |
| `references/crush/README.md` | Doc produit : installation, config (providers/MCP/LSP/skills/hooks), providers custom OpenAI/Anthropic-compat, modèles locaux | Faible (contexte produit) |
| `references/crush/AGENTS.md` | Guide dev interne : architecture (`internal/`), patterns (config-as-service, tools auto-documentés, prompts Go-template, pub/sub), commandes build/test/lint | Faible (carte d'orientation) |
| `references/crush/docs/hooks/FUTURE.md` | Hooks planned : `context_files` (lazy injection de chemins vs contenu) | Faible |
| `references/crush/docs/hooks/examples/rtk-rewrite.sh` | Exemple hook de réécriture de commande bash (RTK token-saving) | Faible (exemple) |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/crush/internal/agent/loop_detection.go` | `hasRepeatedToolCalls(steps, windowSize, maxRepeats) bool` ; `getToolInteractionSignature(content)` ; `toolResultOutputString(result)` ; const `loopDetectionWindowSize=10`, `loopDetectionMaxRepeats=5` | Anti-loop : examine les `windowSize` dernières steps, hash SHA256 de (ToolName + Input + Output appariés par ToolCallID), déclenche si un count > maxRepeats. Steps sans tool-call ignorées. Branché via `StopWhen` dans `agent.go` | **Haute** | ~90 lignes, aucune dépendance métier (juste `fantasy.StepResult`/`crypto/sha256`). Trivialement reproductible en Python (~30 lignes) pour renforcer le circuit-breaker/anti-loop des Coders. Le seuil strict `>` et la fenêtre=10/repeats=5 sont des valeurs calibrées éprouvées |
| `references/crush/internal/agent/coordinator.go` | `Coordinator` interface ; `coordinator` struct ; `NewCoordinator` ; `runSubAgent(ctx, subAgentParams)` ; `agentTool()` ; `buildAgent` ; `buildTools` ; `updateParentSessionCost` ; `AgentToolName="agent"` | Orchestrateur multi-agent : build agents nommés, gère queue/cancel/auth-retry (401 → refresh → retry), et surtout **fan-out sub-agent** via `fantasy.NewParallelAgentTool`. `runSubAgent` crée une sous-session, exécute le sub-agent, propage le coût enfant→parent | Moyenne | Pattern sub-agent directement pertinent pour le fan-out Routeur→Coders. L'accumulation de coût et la gestion de sous-session sont transposables conceptuellement. NB : crush n'a que 2 agents (`coder`+`task`), pas d'architect/judge |
| `references/crush/internal/agent/agent.go` | `SessionAgent` interface ; `sessionAgent` struct ; `NewSessionAgent` ; `SessionAgentCall` ; `SessionAgentOptions` ; `AcceptedRun` ; `ValidateCall` ; `StopWhen` (intègre loop detection) | Boucle de streaming principale : queue de prompts par session, annulation concurrente (cancelMark + acceptSeq monotone), **auto-summarize** (seuils `largeContextWindowThreshold=200_000`, ratio `smallContextWindowRatio=0.2`), persistence messages même sur cancel | Moyenne | La logique d'auto-summarize et la gestion robuste d'annulation sont instructives ; le mécanisme de seuil de summarization est réutilisable comme heuristique |
| `references/crush/internal/agent/agent_tool.go` | `AgentParams{Prompt}` ; `agentTool()` | Définition du tool `agent` (sub-agent task) : `fantasy.NewParallelAgentTool`, délègue à `runSubAgent` | Moyenne | Montre le pattern "tool qui lance un agent" — utile pour concevoir le fan-out Coders comme tool du Routeur |
| `references/crush/internal/hooks/hooks.go` | `Decision` (None/Allow/Deny) ; `HookResult` ; `AggregateResult` ; `aggregate()` ; `shallowMerge()` ; `EventPreToolUse` ; `HaltExitCode=49` | Sémantique d'agrégation multi-hooks : deny>allow>none, halt sticky, `updated_input` shallow-merge en ordre config, reasons/contexts concaténés | Faible-Moyenne | Logique d'agrégation (precedence deny>allow, shallow-merge) portable comme spec de policy-engine |
| `references/crush/internal/hooks/runner.go` | `Runner` ; `NewRunner(hooks, cwd, projectDir)` ; `Run()` ; `matchingHooks()` | Exécution parallèle des hooks via shell embarqué, dédup par commande, timeout + abandon-grace, parsing exit codes (2=block, 49=halt) | Faible | Implémentation Go non portable ; intéressant pour le design de timeouts/abandon |
| `references/crush/internal/agent/hooked_tool.go` | `hookedTool` ; `newHookedTool` ; `wrapToolsWithHooks(tools, runner, isSubAgent)` | Décorateur : wrap chaque tool pour lancer PreToolUse hooks avant exécution. Sub-agents non wrappés | Faible | Pattern décorateur d'outil propre ; concept de hooks applicable |
| `references/crush/internal/permission/permission.go` | `Service` interface ; `permissionService` ; `NewPermissionService` ; `Request` ; `Grant` ; `GrantPersistent` ; `Deny` ; `WithHookApproval` ; `PermissionKey` | Service de permission : allowlist (`toolName` ou `toolName:action`), approbation persistante par session, prompt interactif via pubsub, pré-approval par hook | Faible | Concept d'allowlist + approbation réutilisable ; l'impl concurrency/pubsub est spécifique |
| `references/crush/internal/filetracker/service.go` | `Service` interface ; `service` ; `NewService` ; `RecordRead` ; `LastReadTime` ; `ListReadFiles` | Suit les fichiers lus par session (SQLite). Permet de savoir quels fichiers ont été lus et quand | Faible-Moyenne | Idée de tracking de fichiers touchés par session utile pour le contexte/audit d'un orchestrateur |
| `references/crush/internal/skills/skills.go` | `Skill` ; `Parse` ; `Discover` ; `ToPromptXML` ; `Validate` ; `Deduplicate` ; `Filter` ; `ApproxTokenCount` | Découverte/parse de `SKILL.md` (frontmatter YAML), validation, injection XML dans le system prompt, dédup (dernier gagne = user>builtin) | Faible | Standard agentskills.io ; peu pertinent hors TUI agent. `ApproxTokenCount` (~4 chars/token) trivialement reproductible |
| `references/crush/internal/agent/usage_fallback.go` | `fallbackStepUsage(messages, step)` ; `estimateMessageTokens` ; `approxTokenCount` ; `usageIsZero` | Estimation de tokens quand le provider ne renvoie pas l'usage (~4 chars/token). Robustesse | Faible | Heuristique simple réutilisable en Python en 1 ligne |
| `references/crush/internal/diff/diff.go` | `GenerateDiff(before, after, fileName) (unified, additions, removals)` | Diff unifié via `go-udiff` + comptage +/- | Faible | Trivial en Python (difflib) |
| `references/crush/internal/agent/loop_detection_test.go` | `TestHasRepeatedToolCalls`, `TestGetToolInteractionSignature`, helpers `makeStep`/`makeToolStep`/`makeEmptyStep` | Tests documentant le comportement exact (seuil strict `>`, steps vides ignorées, signatures ToolCallID-indépendantes) | Moyenne | Spec exécutable idéale pour réimplémenter la même logique en Python (pytest) |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/crush/schema.json` | spec (JSON Schema) | Schéma de `crush.json` : `Config` (providers, mcp, lsp, options, permissions, tools, hooks), `HookConfig` (name/matcher regex/command/timeout), `ProviderConfig`, `Options`. Référence de tous les knobs de config |
| `references/crush/crush.json` | config (exemple) | Config par défaut embarquée (providers/models) |
| `references/crush/internal/agent/testdata/TestCoderAgent/glm-5.1/*.yaml` | spec (golden tests) | Cas de test d'agent (bash/edit/read/grep/multiedit/parallel_tool_calls) pour GLM-5.1 — montrent les patterns d'appels d'outils attendus |
| `references/crush/internal/config/config.go` | spec (constantes) | `AgentCoder="coder"`, `AgentTask="task"`, `SelectedModelTypeLarge/Small`. Définit la structure d'agents (2 agents nommés) |
| `references/crush/internal/agent/templates/*.md` | spec (prompts) | Templates de system prompts (coder, task, agent_tool, summary, title, agentic_fetch) |
| `references/crush/docs/hooks/README.md` (section Reference) | spec (contrat hooks) | Spéc formelle : stdin payload, output envelope, exit codes (0/2/49), règles d'agrégation, variables d'env |
| `references/crush/.golangci.yml`, `.goreleaser.yml`, `Taskfile.yaml`, `sqlc.yaml` | config (build) | Configuration toolchain Go (lint, release, tasks, sqlc). Non pertinent pour la cible Python |

## Exclusions conscientes
- **Code Go non portable** : TUI Bubble Tea (`internal/ui/`, ~moitié du repo), client LSP (`internal/lsp/`), client MCP (`internal/agent/tools/mcp/`), OAuth providers (`internal/oauth/`), couche client/serveur HTTP (`internal/client/`, `internal/server/`, `internal/proto/`), persistance SQLite/sqlc (`internal/db/`), shell embarqué (`internal/shell/`), telemetry (`internal/event/`). Totalement liés à l'écosystème Charm/Go.
- **Abstraction provider `charm.land/fantasy`** : non portable, et la cible utilise déjà DSPy+smolagents. Le code provider-specific dans `coordinator.go` (`buildAnthropicProvider`, etc.) est exclu.
- **Config/tooling Go** (`.golangci.yml`, `.goreleaser.yml`, `flake.nix`, workflows GitHub Actions) — non pertinent.
- **L'anti-loop est le seul élément à valeur d'export directe** (réutilisabilité haute) ; le reste est conceptuel (moyenne) ou non portable (faible).
