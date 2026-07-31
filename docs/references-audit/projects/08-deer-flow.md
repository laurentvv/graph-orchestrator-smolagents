# 08 — deer-flow

## En-tête
- **Nom** : deer-flow (ByteDance, "DeerFlow 2.0 — Deep Exploration and Efficient Research Flow")
- **Chemin** : `references/deer-flow/`
- **Type** : orchestrateur de "super agent" (sub-agents + mémoire long-terme + sandboxes + skills + multi-channel IM)
- **Langage principal** : Python 3.12 (backend, LangGraph + LangChain) + TypeScript (frontend Next.js/React)
- **Statistiques** : ~2092 fichiers (~99 MB total) — rewrite complet v2 (aucun code partagé avec v1)

## Synthèse
DeerFlow 2.0 est un **"super agent harness"** open-source (MIT) qui orchestre des sub-agents, gère une mémoire long-terme persistante (DeerMem), exécute du code dans des sandboxes isolées (E2B / AIO containers / Local), expose l'agent via des canaux IM (Slack, Discord, Telegram, GitHub, Lark/Feishu, WeCom, WeChat, DingTalk) et un frontend web, et extensible via des "Skills" (packages Markdown `SKILL.md` à chargement progressif). Architecture multi-tenant avec authentification OIDC/JWT/local et authorization pluggable (RBAC).

**Pour `graph-orchestrator-smolagents` (workflow coding Routeur→Architect→Coders fan-out→Tester→Judge, persistance DuckDB), la valeur est essentiellement documentaire** :
- Stack différente (LangGraph/LangChain, pas DSPy/smolagents) → le code n'est pas directement portable.
- Mais les **cahiers des charges** (RFC authorization pluggable, plans TDD superpowers, contracts JSON de protocole d'événements) et les **patterns architecturaux** (chaîne de middlewares, ThreadState avec reducers typés, sub-agents isolés, dedupe store, event-store append-only) sont directement inspirants pour concevoir un orchestrateur robuste.
- Le `run_event_stream_contract.json` (17 Ko) est un modèle de **spec de protocole d'événements versionné** avec règles frozen/additive/breaking — réutilisable tel quel pour le design du stream d'événements d'un orchestrateur.

Note : le fichier d'analyse existant `references/deer_flow_analysis.md` (fiche 13) couvre déjà 5 patterns clés — cette fiche ne le duplique pas et se concentre sur l'inventaire complet et la catégorisation. Note de réutilisabilité globale : **Moyenne**.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/deer-flow/README.md` | README racine (90 Ko) : présentation super-agent harness, config modèles/sandbox/channels/memory, architecture, sécurité | Haute (vue d'ensemble) |
| `references/deer-flow/docs/plans/2026-07-10-pluggable-authorization-rfc.md` | **RFC Authorization pluggable** : `AuthorizationProvider` Protocol à 2 couches (capability filtering assembly-time + execution authorization runtime via GuardrailMiddleware). Built-in `RbacAuthorizationProvider` | **Haute** (modèle de RFC authz) |
| `references/deer-flow/docs/plans/2026-07-10-pluggable-authorization-implementation-notes.md` | Notes de continuité d'implémentation authz (PR par PR, décisions review, contrats mergés) | Haute |
| `references/deer-flow/docs/plans/2026-07-15-authz-phase1a-implementation-plan.md` + `...phase1a1-trusted-principal...` | Plans d'implémentation TDD phase 1a/1a1 (principal de confiance) | Haute |
| `references/deer-flow/docs/plans/STORAGE_REWRITE_PLAN.md` | **Plan rewrite stockage DeerMem** : layout `users/{user}/memory.json` + `agents/{agent}/facts/{sha-prefix}/{fact_id}.md`, writes incrémentaux, journalé, révisions optimistes. PR #4279 | **Haute** (modèle persistance mémoire) |
| `references/deer-flow/docs/plans/STORAGE_REWRITE_CHANGES.md` | Détail des changements du storage rewrite | Moyenne |
| `references/deer-flow/docs/plans/OPENVIKING_HTTP_MEMORY_INTEGRATION.md` | Plan intégration backend mémoire HTTP (OpenViking) via interface `MemoryManager` pluggable | Moyenne |
| `references/deer-flow/docs/plans/2026-04-01-langfuse-tracing.md` | Plan TDD tracing multi-provider (Langfuse + LangSmith simultanés), factory de callbacks | Moyenne (pattern observabilité) |
| `references/deer-flow/docs/plans/2026-07-17-remember-login.md` | Plan "remember me" (session cookie persistant) | Faible |
| `references/deer-flow/docs/superpowers/plans/2026-04-10-event-store-history.md` | **Plan couche de compatibilité event-store** : remplacer checkpoint par event-store append-only comme source de messages (fix perte après summarization) | **Haute** (design event-sourcing) |
| `references/deer-flow/docs/superpowers/specs/2026-04-11-runjournal-history-evaluation.md` | Spéc/évidence d'évaluation du runjournal (chaîne de preuves alignement) | Moyenne |
| `references/deer-flow/docs/superpowers/specs/2026-04-11-summarize-marker-design.md` | Design marker de summarization | Moyenne |
| `references/deer-flow/docs/superpowers/plans/2026-07-01-scheduled-tasks-mvp.md` | **Plan MVP scheduled tasks** durable (cron + once), persistence models/repos, scheduler service, REST API. Contraintes: réutiliser lifecycle run, owner isolation | **Haute** (cahier des charges scheduler) |
| `references/deer-flow/docs/superpowers/specs/2026-07-01-scheduled-tasks-mvp-design.md` | Design associé au scheduled tasks MVP | Haute |
| `references/deer-flow/docs/superpowers/plans/2026-07-02-read-before-write-gate.md` | **Plan middleware Read-Before-Write** : bloquer `write_file`/`str_replace` sauf si agent a lu la version courante (hash sha256 stampé sur `ToolMessage.additional_kwargs["deerflow_read_mark"]`). State dérivé des messages. Fix #3857 | **Haute** (pattern gate middleware) |
| `references/deer-flow/docs/superpowers/specs/2026-07-02-read-before-write-gate-design.md` | Design du read-before-write gate | Haute |
| `references/deer-flow/docs/superpowers/plans/2026-06-19-guardrail-request-attribution.md` | Plan attribution contexte utilisateur runtime → `GuardrailRequest` via `runtime.context` | Moyenne (sécurité/guardrails) |
| `references/deer-flow/docs/agents/maintainer-orchestrator-design.md` | **Design notes maintainer-orchestrator** : skill "comment-only" pour triage issues/PR. Trust boundary (comment plane = action la plus réversible). Barre de posting (confiance × sévérité P0/P1/P2) | **Haute** (design orchestrateur agent de maintenance) |
| `references/deer-flow/plans/subagent-card-runtime-metadata.md` | **Plan metadata runtime carte subagent** : usage tokens cumulatif, identité modèle effectif. Décisions arch (keyed par `task_id`, additif/optionnel, pas de migration DB) | **Haute** (design UI/runtime sub-agents) |
| `references/deer-flow/backend/docs/ARCHITECTURE.md` | Doc architecture backend | Moyenne |
| `references/deer-flow/backend/docs/AUTH_DESIGN.md` (+ `AUTH_UPGRADE.md`, `SSO.md`, `AUTH_TEST_PLAN.md`) | Docs design auth (OIDC/JWT/local, SSO, plans de test) | Moyenne |
| `references/deer-flow/backend/docs/RUN_EVENT_STREAM.md` | Doc companion du run event stream (contrepoint du contract JSON) | **Haute** |
| `references/deer-flow/backend/docs/middleware-execution-flow.md` | Doc ordre d'exécution de la chaîne de middlewares | **Haute** (comprendre la chaîne) |
| `references/deer-flow/backend/docs/CONFIGURATION.md` | Référence config complète (sandbox, channels, etc.) | Moyenne |
| `references/deer-flow/backend/docs/GUARDRAILS.md` | Doc guardrails (custom provider) | Moyenne |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/deer-flow/contracts/run_event_stream_contract.json` | `record_schema`, `categories`, `events[]`, `compatibility.{frozen, additive, breaking}` | **Spec de protocole d'événements versionné** : freeze des noms/catégories, règles d'évolution (additif autorisé, breaking listé), schéma producteur par event, catégories (`trace/message/outputs/error/middleware/context/subagent/workspace`), sémantique de séquence | **Haute** | Modèle directement applicable pour designer un stream d'événements d'orchestrateur versionné et stable |
| `references/deer-flow/contracts/subagent_status_contract.json` | `valid_status_values`, `valid_stop_reason_values` | Contrat wire cross-language du statut structuré sub-agent (v2). status (completed/failed/cancelled/timed_out/polling_timed_out), stop_reason (token_capped/turn_capped/loop_capped) | **Haute** | Modèle d'énum de statuts de sub-agents + raisons d'arrêt (utile pour fan-out Coder→Tester→Judge) |
| `references/deer-flow/contracts/slash_skill_contract.json` | `reserved_slash_skill_names`, `skill_name_pattern` | Contrat cross-language parser slash-skill (backend Python ↔ frontend TS) | Moyenne |
| `references/deer-flow/contracts/skill_review/*.schema.json` (3 schémas) | `readiness`, `assurance`, `dimensions[].status`, `issues[].severity/confidence` | Schémas JSON Schema v1 du système de review de skills (snapshot package → facts → report) | **Haute** | Modèle de pipeline de revue qualité déterministe + LLM (utile pour un Judge/Reviewer agent) |
| `references/deer-flow/backend/app/channels/base.py` | `Channel(ABC)` (`start`, `stop`, `send`, `send_file`, `receive_file`, `supports_streaming`) | **Abstraction de canal de messagerie** : classe de base abstraite pour connecter l'agent à un canal IM | Moyenne | Pattern d'abstraction multi-canal réutilisable (Invoker abstraction) |
| `references/deer-flow/backend/app/channels/message_bus.py` | `MessageBus`, `InboundMessage`, `OutboundMessage`, `ResolvedAttachment`, `InboundMessageType(StrEnum)` | Bus de messages inbound/outbound avec pièces jointes résolues | Moyenne | Modèle de messages normalisés cross-canal |
| `references/deer-flow/backend/app/channels/dedupe_store.py` | `InboundDedupeStore(Protocol)`, `MemoryInboundDedupeStore`, `PostgresInboundDedupeStore`, `make_inbound_dedupe_store()` | **Store de déduplication inbound** : Protocol + 2 implémentations (memory, Postgres) + factory selon config multi-worker | Moyenne | Pattern dedupe/idempotence réutilisable pour la persistance/polling |
| `references/deer-flow/backend/app/channels/{slack,github,discord,telegram}.py` | `SlackChannel`, `GitHubChannel`, `DiscordChannel`, `TelegramChannel` | Implémentations concrètes de canaux | Faible | Spécifiques API tierces ; l'abstraction `base.py` est la vraie valeur |
| `references/deer-flow/backend/app/gateway/auth/providers.py` | `AuthProvider(ABC)` (abstract) | **Abstraction provider d'authentification** | Moyenne | Point d'extension auth pluggable |
| `references/deer-flow/backend/app/gateway/auth/oidc.py` | `OIDCService`, `OIDCMetadata`, `OIDCIdentity`, hiérarchie `OIDCError*`, `_constant_time_compare()` | Service OIDC complet (métadonnées, identité, hiérarchie d'erreurs, comparaison temps constant) | Moyenne | Implémentation OIDC robuste réutilisable |
| `references/deer-flow/backend/app/gateway/auth/jwt.py` | `TokenPayload(BaseModel)`, `create_access_token()`, `decode_token()` | Émission/vérification JWT avec `token_version` | Moyenne | Modèle JWT avec versionnage de token |
| `references/deer-flow/backend/packages/harness/deerflow/authz/` | `AuthorizationProvider` (Protocol), `RbacAuthorizationProvider`, enforcement 2-couches | **Implémentation authorization pluggable** (la RFC ci-dessus réalisée) | Moyenne | Modèle authz 2-couches (filter assembly + deny runtime) |
| `references/deer-flow/backend/packages/harness/deerflow/agents/middlewares/*.py` (30 middlewares) | `InputSanitization`, `ToolResultSanitization`, `ToolProgress`, `LoopDetection`, `ToolOutputBudget`, `TokenBudget`, `SubagentLimit`, `SkillActivation`, `SkillToolPolicy`, `ReadBeforeWrite`, `DanglingToolCall`, `DeferredToolFilter`, `LLMErrorHandling`, `Summarization`, `TerminalResponse`, ... | **Chaîne de middlewares** autour de l'appel LLM (sanitization, détection de boucle, budget tokens, limites sub-agents, gates d'outils) | **Haute** (patterns) | Les concepts (loop detection, token budget, tool output budget, read-before-write gate) sont directement transposables à un orchestrateur smolagents |
| `references/deer-flow/backend/packages/harness/deerflow/agents/thread_state.py` | `ThreadState` (extends AgentState), `merge_delegations`, `merge_skill_context` | État du graphe avec reducers typés (cap delegations à N, skill_context = références uniquement) | **Haute** (pattern) | Modèle de state d'orchestrateur avec compaction |
| `references/deer-flow/backend/packages/harness/deerflow/subagents/executor.py` | `SubagentExecutor`, `_isolated_subagent_loop`, `_extract_final_result`, `_extract_llm_error_fallback` | **Exécuteur de sub-agents** : event loop isolé, extraction résultat pur (pas de pollution parent), gestion erreurs LLM | **Haute** (pattern fan-out) | Pattern d'isolation et de collecte de résultats de sub-agents directement utile pour fan-out Coders |
| `references/deer-flow/backend/packages/harness/deerflow/guardrails/{provider,middleware,builtin}.py` | `GuardrailProvider`, `GuardrailMiddleware`, `GuardrailRequest` | Middleware guardrail (point d'application de l'authz runtime) | Moyenne |
| `references/deer-flow/skills/public/*/SKILL.md` (23 skills) | frontmatter `name`/`description` + corps Markdown | **Pattern "Skill"** : package de capacité à chargement progressif (un `SKILL.md` par dossier). Ex: `data-analysis` (DuckDB), `deep-research`, `code-documentation`, `skill-reviewer` | **Haute** (pattern) | Modèle de capabilities modulaires lazy-loaded |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/deer-flow/contracts/run_event_stream_contract.json` | spec (JSON Schema 2020-12) | Contrat protocole d'événements run (17 Ko) : noms frozen, règles additive/breaking, schémas producteurs, catégories, sémantique séquence, alias legacy |
| `references/deer-flow/contracts/subagent_status_contract.json` | spec (JSON) | Contrat wire statut sub-agent v2 (status + stop_reason) |
| `references/deer-flow/contracts/slash_skill_contract.json` | spec (JSON) | Contrat cross-language parser slash-skill |
| `references/deer-flow/contracts/skill_review/package_snapshot.v1.schema.json` | spec (JSON Schema) | Snapshot de package de skill (fichiers, limites, erreurs reader) |
| `references/deer-flow/contracts/skill_review/review_facts.v1.schema.json` | spec (JSON Schema) | Facts de review (subject, findings, completeness, analyzer_errors) |
| `references/deer-flow/contracts/skill_review/review_report.v1.schema.json` | spec (JSON Schema) | Rapport de review (readiness, assurance, dimensions, issues, evidence, recommended_actions) |
| `references/deer-flow/config.example.yaml` (118 Ko) | config | Référence config complète (modèles, sandbox E2B/AIO/Local, channels, memory, authz, tracing, extensions middlewares, scheduled tasks) |
| `references/deer-flow/docs/plans/2026-07-10-pluggable-authorization-rfc.md` | spec (RFC) | RFC authorization pluggable |
| `references/deer-flow/docs/superpowers/specs/*.md` (8 specs) | spec | Specs design superpowers |
| `references/deer-flow/docs/superpowers/plans/*.md` (9 plans) | spec (plans TDD) | Plans d'implémentation TDD superpowers |

## Exclusions conscientes
- **Frontend TypeScript** : `frontend/src/**` (Next.js/React, ~30 Mo, TUI web, composer, settings UI) — non pertinent pour un orchestrateur backend Python
- **Déploiement/infra** : `docker/` (lark-cli-broker/init, nginx, provisioner), `deploy/helm/`, `pr-build/`, scripts build
- **Traductions README** : `README_fr.md`, `README_zh.md`, `README_ja.md`, `README_ru.md` (duplicates du README racine)
- **CHANGELOG** : `CHANGELOG.md` (77 Ko), `CHANGELOG_zh.md` (77 Ko) — historique
- **Skills/public détaillés individuellement** : 23 skills regroupés en une entrée pattern
- **.agent/skills/** : `blocking-io-guard`, `engineer-system-change`, `smoke-test` (outils internes dev)
- **Tests/backend samples** : `backend/tests/**`, `backend/samples/**`
- **Workflows GitHub** : `.github/workflows/**`, `ISSUE_TEMPLATE/**`
