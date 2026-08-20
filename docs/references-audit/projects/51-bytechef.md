# 51 — bytechef

## En-tête
- **Nom** : ByteChef (`bytechef`)
- **Chemin** : `references/bytechef/`
- **Type** : Plateforme d'intégration et d'automatisation open-source unifiant l'orchestration d'agents IA, l'exécution de workflows complexes et 180+ connecteurs — architecture distribuée basée sur un coordinateur d'état de tâches, des workers résilients, un composant Agent IA avec 12 guardrails modulaires (PII, secrets, jailbreak, NSFW, topical alignment), une mémoire multi-backend et une passerelle MCP bidirectionnelle (in & out).
- **Langage principal** : Java 21 / Spring Boot 3 / TypeScript (React / Tailwind / Vite) ; 13 222 fichiers : 10 137 `.java`, 1 129 `.ts`, 619 `.tsx`, 336 `.json`, 308 `.gradle.kts`, 212 `.md`, 128 `.yaml`, 89 `.html`, 54 `.css`.
- **Licence** : Apache-2.0 (Core Engine) + Fair-code (EE features)

## Synthèse
ByteChef est une plateforme d'intégration (iPaaS) et d'automatisation d'entreprise de grande envergure, conçue pour combler le fossé entre les workflows déterministes d'APIs et les agents IA autonomes. Là où la plupart des frameworks séparent l'automatisation classique et les agents LLM, ByteChef intègre un composant natif **AI Agent** qui s'insère directement comme un nœud dans un graphe de tâches complexe.

Pour `graph-orchestrator-smolagents`, ByteChef apporte des architectures et des briques de référence majeures :
1. **P8 & P0-bis (Garde-Fous de Sécurité & 12 Guardrails Modulaires)** : Le module `server/libs/modules/components/ai/agent/guardrails` implémente un ensemble exhaustif de 12 garde-fous pour sécuriser les entrées et sorties des agents :
   - Détection PII (`PiiDetectorUtils`, masquage de données personnelles sensibles par regex et classification).
   - Détection de clés secrètes / tokens (`SecretKeyDetectorUtils`, détection de tokens d'API, clés privées, headers Authorization).
   - Alignement thématique (`TopicalAlignment`, contrôle du respect du périmètre du prompt).
   - Assainissement textuel (`SanitizeTextAdvisor`, réécriture et suppression d'injections).
   - Agrégateur d'erreurs de violations (`CheckForViolationsAdvisor`, compilation unifiée des entorses aux règles).
2. **P8 & P12 (Architecture Coordinateur / Workers / Multi-Tenant)** : L'architecture distribuée de ByteChef (`platform-coordinator` et `platform-worker`) gère les transitions d'états de tâches, les politiques de retry exponentiel, les queues de messages asynchrones et l'isolation multi-tenant stricte (`TenantContext`, `TenantThreadPoolTaskExecutor`), fournissant un modèle robuste pour la scalabilité de notre orchestrateur.
3. **P10 & P8 (Passerelle MCP Bidirectionnelle)** : `platform-mcp` implémente à la fois un client MCP pour consommer des serveurs d'outils externes et un serveur MCP pour exposer des workflows d'agents comme des outils pour d'autres agents.
4. **P6 & P11 (Mémoire d'Agent Multi-Backend & Télémétrie)** : Abstraction de la mémoire de conversation (`ChatMemoryAddMessagesAction`, `ChatMemoryGetMessagesAction`) supportant 8 backends (JDBC, Redis, Cassandra, Cosmos DB, Vector Stores).

Réserves : Le projet est un volumineux monorepo d'entreprise en Java / Spring Boot 3 (>13 000 fichiers), ce qui exclut l'importation brute de code dans notre stack Python. Cependant, les algorithmes de guardrails (regex, détecteurs de secrets, advisors de violations), les modèles de coordination de tâches et les contrats MCP sont directement exploitables. Note globale : **🟡 Moyenne** (pour l'adaptation de code) / **🟢 Haute** (pour la richesse conceptuelle des guardrails et de l'orchestration de tâches).

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/bytechef/AGENTS.md` | Guide d'architecture globale et invariants de contribution pour ByteChef | **Haute** (P0-bis — principes de gouvernance de graphe) |
| `references/bytechef/CLAUDE.md` | Directives et commandes de développement pour Claude Code sur le dépôt ByteChef | Moyenne (P0 — directives de workflow) |
| `references/bytechef/README.md` | Vue d'ensemble de la plateforme, architecture de l'agent IA, guardrails et MCP | **Haute** (P0 / P8 — vue d'ensemble des capacités d'agent) |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/bytechef/server/libs/modules/components/ai/agent/guardrails/src/main/java/com/bytechef/component/ai/agent/guardrails/util/SecretKeyDetectorUtils.java` | `SecretKeyDetectorUtils`, `detectSecrets`, `isLikelySecret`, `sanitizeSecretTokens` | Détecteur haute précision de clés d'API, tokens d'authentification et secrets dans les invites et sorties LLM | **Haute** | P8+P0-bis : Indispensable pour notre Security Reviewer et nos middlewares de protection des outputs |
| `references/bytechef/server/libs/modules/components/ai/agent/guardrails/src/main/java/com/bytechef/component/ai/agent/guardrails/util/PiiDetectorUtils.java` | `PiiDetectorUtils`, `detectPii`, `maskPii`, `PiiEntity` | Détecteur et masqueur d'informations personnelles identifiables (adresses emails, numéros de téléphone, numéros de sécurité sociale) | **Haute** | P8 : Module de protection de la confidentialité transposable en Python |
| `references/bytechef/server/libs/modules/components/ai/agent/guardrails/src/main/java/com/bytechef/component/ai/agent/guardrails/advisor/CheckForViolationsAdvisor.java` | `CheckForViolationsAdvisor`, `validateInputOutput`, `collectViolations`, `onViolation` | Advisor d'interception d'invites et de complétions vérifiant l'ensemble des règles de sécurité avant transmission | **Haute** | P8 : Pattern d'interception de requêtes/réponses pour notre pipeline d'agents DSPy |
| `references/bytechef/server/libs/modules/components/ai/agent/guardrails/src/main/java/com/bytechef/component/ai/agent/guardrails/advisor/SanitizeTextAdvisor.java` | `SanitizeTextAdvisor`, `sanitize`, `stripDisallowedPatterns` | Assainisseur de texte éliminant les motifs d'injection, balises dangereuses et sorties malformées | **Haute** | P8 : Filtre de nettoyage pour le Coder et les sorties de test |
| `references/bytechef/server/libs/modules/components/ai/agent/guardrails/src/main/java/com/bytechef/component/ai/agent/guardrails/util/KeywordMatcherUtils.java` | `KeywordMatcherUtils`, `containsDisallowedKeywords`, `fuzzyMatchKeyword` | Algorithme de correspondance de mots-clés interdits et détection de contournements textuels | Moyenne | P8 : Barrière déterministe anti-dérive |
| `references/bytechef/server/libs/modules/components/ai/agent/guardrails/topical-alignment/src/main/java/com/bytechef/component/ai/agent/guardrails/topicalalignment/cluster/TopicalAlignment.java` | `TopicalAlignment`, `isAlignedWithTopic`, `evaluateRelevance` | Évaluateur de conformité thématique vérifiant si la réponse de l'agent reste dans le cadre strict de sa mission | Moyenne | P6+P8 : Nudge déterministe ou prompt d'alignement pour le Coder |
| `references/bytechef/server/libs/platform/platform-coordinator/src/main/java/com/bytechef/platform/coordinator/config/PlatformCoordinatorConfiguration.java` | `PlatformCoordinatorConfiguration`, `taskExecutionCoordinator`, `workflowStateDispatcher` | Moteur de coordination d'état de tâches et dispatching d'événements de workflow | Moyenne | P11+P12 : Blueprint de coordinateur centralisé pour l'orchestrateur |
| `references/bytechef/server/libs/platform/platform-worker/src/main/java/com/bytechef/platform/worker/config/PlatformWorkerConfiguration.java` | `PlatformWorkerConfiguration`, `taskWorker`, `retryPolicy`, `concurrencyLimiter` | Configuration des workers d'exécution de tâches avec limitations de concurrence et politiques de reprise | Moyenne | P8+P8-bis : Modèle de résilience et de confinement des exécutions |
| `references/bytechef/server/libs/core/tenant/tenant-api/src/main/java/com/bytechef/tenant/TenantContext.java` | `TenantContext`, `getTenantId`, `withTenant`, `clear` | Gestionnaire de contexte d'isolation multi-tenant via stockage thread-local / asynchrone | Moyenne | P12 : Modèle d'isolation de session multi-projets |
| `references/bytechef/server/libs/platform/platform-mcp/platform-mcp-api/src/main/java/com/bytechef/platform/mcp/facade/McpServerFacade.java` | `McpServerFacade`, `listTools`, `executeTool`, `registerServer` | Façade de gestion et de proxying pour les serveurs et outils du Model Context Protocol (MCP) | **Haute** | P10+P8 : Abstraction de passerelle MCP client/serveur |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/bytechef/server/libs/platform/platform-mcp/platform-mcp-api/src/main/java/com/bytechef/platform/mcp/domain/McpTool.java` | MCP Tool Schemas | Modèle de données d'un outil MCP avec paramètres JSON Schema et types de retour |
| `references/bytechef/server/libs/modules/components/ai/agent/guardrails/src/main/java/com/bytechef/component/ai/agent/guardrails/GuardrailExceptionKind.java` | Guardrail Schemas | Taxonomie des types d'erreurs et de violations de guardrails |

## Exclusions conscientes
| Chemin | Motif d'exclusion |
|---|---|
| `references/bytechef/client/` | Interface utilisateur web SaaS en React / Vite / Tailwind. Ignorer. |
| `references/bytechef/server/libs/modules/components/` (hors `ai/`) | 180+ connecteurs tiers SaaS commerciaux (Asana, Salesforce, Hubspot, Stripe...). Ignorer. |
| `references/bytechef/buildSrc/`, `gradlew` | Scripts et plugins de compilation Gradle / Kotlin DSL. Ignorer. |
| `references/bytechef/server/ee/` | Fonctionnalités spécifiques à la licence commerciale Enterprise Edition (SAML, audit logs cloud). Ignorer. |

## Correspondance avec `plan_usine_logicielle.md`
- **P0 / P0-bis** : `SecretKeyDetectorUtils` & `CheckForViolationsAdvisor` (protection universelle contre les fuites de secrets et violation de charte).
- **P6** : `TopicalAlignment` (contrôle d'alignement thématique des livrables par le Judge).
- **P8** : `PiiDetectorUtils`, `SecretKeyDetectorUtils`, `SanitizeTextAdvisor` (batterie de 12 guardrails modulaires d'entrée/sortie).
- **P8-bis** : `PlatformWorkerConfiguration` (politique de retry, concurrence et confinement de tâches).
- **P10** : `McpServerFacade` & `McpTool` (consommation et exposition dynamique d'outils MCP).
- **P11** : `PlatformCoordinatorConfiguration` (suivi d'état et journalisation événementielle des transitions de tâches).
- **P12** : `TenantContext` & `TenantThreadPoolTaskExecutor` (isolation multi-locataires et contextuelle).
