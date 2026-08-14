# 45 — OpenSandbox

## En-tête
- **Nom** : OpenSandbox (ex-Alibaba, CNCF Landscape, OpenSSF Best Practices)
- **Chemin** : `references/OpenSandbox/`
- **Type** : Plateforme de sandbox généraliste pour applications IA (lifecycle serveur + runtimes Docker/K8s + SDKs + CLI + MCP)
- **Langage principal** : Python (serveur FastAPI + SDK) / Go (runtime execd, operator K8s) ; SDKs secondaires Kotlin/C#/TS
- **Statistiques** : 2143 fichiers hors `.git/` : 661 `.py`, 598 `.go`, 193 `.md`, 112 `.yaml`, 106 `.kt`, 72 `.cs`, 63 `.ts` ; dépôt très actif (commits quotidiens)
- **Licence** : Apache-2.0 (headers « Copyright 2026 Alibaba Group Holding Ltd »)

## Synthèse
OpenSandbox résout le problème *orthogonal et complémentaire* du nôtre : là où `graph-orchestrator-smolagents` orchestre des agents LLM qui **génèrent** du code web, OpenSandbox fournit l'infrastructure pour **exécuter ce code de façon isolée, timeoutée, snapshotable et rejouable** (conteneur → commande → filesystem → snapshot → restore). Ce n'est pas un orchestrateur d'agents : pas de Judge, pas de TDD, pas d'anti-loop agent.

La bonne surprise est que les parties les plus pertinentes pour nous sont en **Python pur copiable presque tel quel** : le module `transport/` du SDK Python (retry/backoff/jitter/deadline sur httpx, design documenté par l'OSEP-0017) est un travail de niveau production qui couvre exactement notre P8 ; le serveur MCP FastMCP est un modèle de design d'outils avec docstrings-contrats et registre de sessions ; le middleware `request_id` (ContextVar + logging Filter) est un pattern d'observabilité transplantable en ~30 lignes.

Le protocole de lifecycle (`specs/sandbox-lifecycle.yml`, spec-first) est la vraie matière intellectuelle pour **P8-bis** : machine à états explicite (Running→Pausing→Paused→Resuming), création asynchrone 202+polling, TTL absolu avec `renew-expiration`, snapshot asynchrone avec `Location`, restore par `snapshotId` avec entrypoint neutre, endpoints signés avec expiration, télémétrie fire-and-forget. Le concept d'isolation session (OSEP-0013 : bubblewrap, `run_once` idempotent) est exactement le modèle d'« exécution isolée et rejouable » visé, même si l'implémentation Go/Linux ne se transpose pas.

Réserves : (1) biais stack — le runtime (execd, ingress, operator K8s) est Go et Docker/K8s-locked ; ce qui est transposable, c'est le *contrat* (specs) et le *client* (SDK Python). (2) Complexité ops — on n'adopte pas la plateforme, on pique des patterns. (3) Le MCP server garde son état en mémoire sans persistance. (4) Rien pour le Judge/TDD (P6 non couvert). Note globale : **🟢 Haute** — pour tout ce qui est Python/specs/patterns (~70 % de la valeur), 🔴 pour le runtime Go/K8s.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/OpenSandbox/oseps/0017-resilient-sdk-transport.md` | Design complet du transport résilient : taxonomie d'exceptions, retry, jitter décorrélé, deadline | Haute (P8) |
| `references/OpenSandbox/docs/guides/pause-resume.md` | Sémantique pause/resume/snapshot (table des états, `sandboxId` stable, commit rootfs) | Haute (P8-bis) |
| `references/OpenSandbox/docs/guides/multi-tenancy.md` + `references/OpenSandbox/oseps/0014-multi-tenancy.md` | API key → namespace, startup guards — modèle minimal de cloisonnement | Haute (P12) |
| `references/OpenSandbox/docs/guides/isolation-sessions.md` | Sessions bubblewrap mutuellement isolées, `run_once`/`with_session`, tableau comparatif des frontières | Moyenne (P8-bis, concept) |
| `references/OpenSandbox/docs/guides/client-pool.md` | Pool de clients/sandboxes pré-chauffés (pool d'IDs) — pattern pool de processus llama.cpp | Moyenne (P9) |
| `references/OpenSandbox/oseps/0008-pause-resume-rootfs-snapshot.md` | Snapshot rootfs en image OCI (statut implemented) | Moyenne (P8-bis) |
| `references/OpenSandbox/oseps/0013-isolated-execution-api.md` | API d'exécution isolée par sessions (idempotence `run_once`) | Moyenne (P8-bis) |
| `references/OpenSandbox/oseps/README.md` + `references/OpenSandbox/oseps/osep-template.md.template` | Format standardisé de proposals (frontmatter + toc + Test Plan) — gouvernance spec-first | Moyenne |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/OpenSandbox/sdks/sandbox/python/src/opensandbox/transport/retry.py` (+ `_classify.py`, `_decision.py`, `_async_retry.py`, `_sync_retry.py`) | `RetryPolicy` (frozen dataclass : `max_retries=3`, `initial_backoff=500ms`, `backoff_multiplier=2.0`, `jitter=DECORRELATED`, `per_attempt_timeout`, `overall_deadline`, hook `on_retry`), `RetryCause` (enum `PRE_SEND`/`READ_TIMEOUT`/`STATUS_429`…), `RetryEvent`, `classify_transport_exception()`, `is_body_replayable()` | Middleware de retry résilient sur httpx : classification pré-send (safe sur toute méthode) vs post-send (idempotents seulement), deadline mur-mur, clamp des timeouts par phase, `Retry-After` honoré et plafonné, sleep clampé au budget restant, réponse rejetée `aclose()`d | **Haute** | **LE middleware P8** pour nos appels llama.cpp/HTTP et MCP. Python pur, dépendance httpx seulement, copiable tel quel |
| `references/OpenSandbox/sdks/mcp/sandbox/python/src/opensandbox_mcp/server.py` | `ServerState` (registre `dict[str, Sandbox]` + `asyncio.Lock`), `register_tools(mcp, prefix, state, …)` avec `@tool()`, `_get_or_connect_sandbox()`, `create_server(instructions=…)`, `ctx.report_progress()` | Serveur MCP FastMCP complet : 20+ outils (sandbox_create/kill/renew, command_run/interrupt, file_read/write/search/move), docstrings-contrats, reconnexion, registre par id, progression | **Haute** | Modèle direct pour exposer nos outils (chrome-devtools, linter, exécution) via MCP + industrialiser notre client MCP (P0 docstrings-contrats, P11 progression) |
| `references/OpenSandbox/specs/sandbox-lifecycle.yml` | endpoints `/sandboxes` (POST **202** + polling), `/pause|resume` (202 + états intermédiaires), `/renew-expiration` (TTL absolu), `/snapshots` (202 + `Location`), `/metadata` (PATCH **JSON Merge Patch RFC 7396**), `/endpoints/{port}?expires=` (token signé), `/metrics/events` (télémétrie fire-and-forget « MUST NOT affect usability ») | Spec OpenAPI de 1712 lignes : le contrat complet du lifecycle d'un sandbox | **Haute** | Contrat à imiter pour P8-bis : chaque exécution de code généré = sandbox horodaté, snapshot avant mutation, restore depuis snapshot, TTL/renew anti-fuite. Le format spec-first (contrat = source de vérité) est aussi un pattern de gouvernance |
| `references/OpenSandbox/server/opensandbox_server/services/snapshot_restore.py` | `resolve_sandbox_image_from_request()`, `DEFAULT_SNAPSHOT_RESTORE_ENTRYPOINT = ["tail", "-f", "/dev/null"]` | Création **depuis `snapshotId`** : résout l'image du snapshot, rejette 409 si `SnapshotState != READY`, vérifie l'isolation tenant, injecte un entrypoint neutre | Moyenne | Sémantique « rejouer depuis un point de restauration » = cœur de P8-bis (pour nous : workspace versionné par itération Coder, reset avant retry). Implémentation OCI/K8s non portable, la sémantique si |
| `references/OpenSandbox/skills/troubleshoot-sandbox/SKILL.md` + `references/OpenSandbox/cli/src/opensandbox_cli/skill_registry.py` | frontmatter `name/description/user-invocable/argument-hint` ; `SkillSpec(slug, package_file, title, summary, trigger_hint, marker_id)`, `BUILTIN_SKILLS`, `split_frontmatter()`, `extract_section(body, heading)`, `render_skill_for_target()` | Skills markdown : tableau symptôme→vérification→cause probable (exit codes 137/126/127, OOMKilled…), registre avec corps détaillé lazy et sections extractibles | **Haute** | Exactement la discipline P10 (description courte eager, corps lazy, sections extractibles) + le tableau diagnostic est un gabarit de **grounding des findings** Judge (P6) |
| `references/OpenSandbox/AGENTS.md` (+ `server/AGENTS.md`, `specs/AGENTS.md`, `CLAUDE.md` pointeur) | racine = **routeur** (« Prefer the nearest `AGENTS.md` in the directory tree »), Repository Map, Routing par tâche, Guardrails 3 niveaux **Always / Ask first / Never** ; `server/` = Key Paths + « Never: business logic in route handlers » ; `specs/` = Contract Map | AGENTS.md hiérarchiques : invariant universel à la racine + spécialisation locale par dossier, résolution « le plus proche gagne » | **Haute** | Implémentation réelle de P0 (spécialisation par nœud) + P0-bis (invariants) : transposable trivialement à nos nœuds PromptRefiner/Router/Coder/Judge et skills |
| `references/OpenSandbox/server/opensandbox_server/middleware/request_id.py` | `request_id_ctx: ContextVar[str \| None]`, `RequestIdMiddleware` (lit/génère `X-Request-ID`, reset du token en `finally`), `RequestIdFilter` (injecte `request_id` dans chaque `LogRecord`), `get_request_id()` | Corrélation des logs par requête sans plumbing — ~30 lignes | **Haute** | P11 : même pattern pour corréler tous les logs par run/nœud (ContextVar), base de l'event stream structuré |
| `references/OpenSandbox/server/opensandbox_server/tenants/models.py` | `TenantEntry(name, namespace, api_keys)` | Mapping API key → namespace (OSEP-0014), startup guards | **Haute** | P12 : le modèle minimal de cloisonnement multi-utilisateurs, applicable à nos scopes DuckDB |
| `references/OpenSandbox/server/opensandbox_server/integrations/otel/metrics.py` | `setup_otel_metrics()`, `record_sandbox_create_duration()` | Métriques OTEL par durée d'opération | Moyenne | P11 : complément télémétrie (spec `/metrics/events` fire-and-forget côté SDK) |
| `references/OpenSandbox/tests/python/tests/base_e2e_test.py` + `test_sandbox_e2e.py` | `create_connection_config()`, `is_kubernetes_runtime()`, env vars `OPENSANDBOX_TEST_*` ; 22 tests **ordonnés et numérotés** (`test_01_sandbox_lifecycle_and_health`, `test_04_interrupt_command`, `test_07_x_request_id_passthrough_on_server_error`) | Harnais E2E piloté par env vars, scénarios lifecycle/command/interrupt/pause/resume numérotés | Moyenne | P6/P11 : discipline de tests E2E ordonnés pour nos suites Tester/Judge + passthrough du request-id |
| `references/OpenSandbox/examples/langgraph/main.py` | `WorkflowState(TypedDict)` avec `attempt/max_attempts/last_error/fallback_command/cleaned`, nœud `run_job` (substitue une commande de **fallback**), `decide_next()` (arête conditionnelle, self-loop bornée `max_attempts=2`), `cleanup_sandbox` + `finally` | Anti-loop illustrée en LangGraph : compteur d'attempts dans l'état, fallback **différent** à chaque retry, cleanup garanti | **Haute** | P3 : le pattern exact de notre boucle Coder→Tester (self-loop bornée + fallback différencié + cleanup en finally) |
| `references/OpenSandbox/examples/playwright/main.py` | Playwright headless **dans** le sandbox, screenshot téléchargé via `files.read_bytes` | Exemple de validation visuelle navigateur exécutée en environnement isolé | Moyenne | Rapprochement direct avec notre validation visuelle chrome-devtools (un jour sandboxée, P8-bis) |
| `references/OpenSandbox/components/execd/pkg/isolation/` (`bwrap.go`, `isolator.go`, `seccomp_gen.go`, `probe.go`) | isolateur bubblewrap, génération de filtres seccomp, probe de capacités | Isolation de sessions Linux (namespaces via bwrap + seccomp) | Faible | Concept P8-bis only — Go/Linux non portable, à relire pour comprendre les frontières d'isolation |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/OpenSandbox/specs/sandbox-lifecycle.yml` | spec OpenAPI | Contrat du lifecycle (création 202, pause/resume, TTL, snapshots, endpoints signés, télémétrie) — cf. ligne dédiée dans Code réutilisable |
| `references/OpenSandbox/oseps/` | proposals (17 OSEPs) | Design decisions numérotées avec template standardisé + Test Plan — gouvernance spec-first (`specs/AGENTS.md` : le contrat est la source de vérité) |

## Exclusions conscientes
- `references/OpenSandbox/components/` (Go : execd, ingress, egress, nodeagent) et `references/OpenSandbox/kubernetes/` (operator, CRDs, Helm) : 🔴 runtime non portable — lecture ponctuelle de `execd/pkg/isolation/` pour le concept uniquement.
- SDKs Kotlin/TS/C#/Go (`sdks/sandbox/{kotlin,javascript,csharp,go}`) : doublons du SDK Python, ignorer.
- Ingress/egress/credential-vault (OSEP-0001/0011/0012) : pertinents seulement si on expose un jour les apps générées sur le réseau — hors périmètre.
- `docs/` (site VitePress volumineux) : ne lire que les 4 guides cités ci-dessus.
- Pas de brique Judge/verdict/TDD : le `test_plan` des OSEPs est le plus proche, sans test automatique de code généré.

## Correspondance avec `plan_usine_logicielle.md`
- **P0 / P0-bis** : AGENTS.md hiérarchiques (routeur racine + Guardrails Always/Ask-first/Never + « le plus proche gagne ») ; docstrings-contrats des tools MCP.
- **P3** : exemple LangGraph (`attempt/max_attempts/fallback_command` + arête conditionnelle bornée + cleanup `finally`).
- **P6** : tableau symptôme→cause du skill troubleshooting (grounding des findings) ; tests E2E ordonnés/numérotés.
- **P8** : `RetryPolicy`/`RetryAsyncTransport` (classification pré/post-send, jitter décorrélé, deadline, `Retry-After`) — le middleware anti-crash de référence, en Python.
- **P8-bis** : spec lifecycle (202+polling, TTL/renew, snapshot/restore, `sandboxId` stable, entrypoint neutre) ; isolation sessions `run_once` (OSEP-0013).
- **P9** : (indirect) pattern du pool de clients pré-chauffés → pool de processus llama.cpp.
- **P10** : format SKILL.md (frontmatter + trigger lazy + sections extractibles) via `SkillSpec`/`extract_section`.
- **P11** : `RequestIdMiddleware`/`RequestIdFilter` (ContextVar), `/metrics/events` fire-and-forget, OTEL metrics.
- **P12** : `TenantEntry` (API key → namespace) + OSEP-0014 multi-tenancy.
