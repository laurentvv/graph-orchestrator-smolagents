"""Met à jour docs/references-audit/inventory.json pour refléter l'audit approfondi
des projets 14-23.

Initial (historique) : qm = 1 entrée (README), claude-code = 2 entrées (README + AGENTS_LIST).
Après audit 14-18 : qm = 24 entrées, claude-code = 13 entrées, learn-claude-code = 18,
system-prompts = 17, awesome-claude-skills = 11.
Audit 19-23 (2026-08-03, procédure PROCEDURE-AUDIT-REFERENCE.md) :
  - 19 loopx              = 10 entrées (P3 anti-loop + P9 compaction + P11 event stream)
  - 20 code-review-graph  = 10 entrées (P6 risk score + blast radius)
  - 21 davidondrej-skills =  6 entrées (P8 denylist 27 regex + P10 doctrine)
  - 22 llm-council        =  4 entrées (P6 council anonymisé)
  - 23 mattpocock-skills  =  9 entrées (P10 doctrine fusion + P6/P0 engineering skills)
Audit 24 (2026-08-05) :
  - 24 pi                 =  7 entrées (P9 compaction, P6 Judge)

Corrige aussi les reuse_rating globaux inversés par l'ancienne fiche bâclée :
  - qm : medium -> high   (algorithmes portables : compaction, mémoire, idempotency, queues)
  - claude-code : high -> medium  (53 prompts, majorité de code TS non portable)

Usage :  python update_inventory.py
"""
import json
from pathlib import Path

INVENTORY = Path(__file__).parent / "docs" / "references-audit" / "inventory.json"

# ---------------------------------------------------------------------------
# 14 — qm : 24 entrées (code algorithmique portable + prompts + schémas SQL)
# ---------------------------------------------------------------------------
QM_FILES = [
    # --- Compaction de contexte (Priorité 9 du plan) ---
    {"path": "references/qm/src/harness/context-compaction.ts", "type": "code", "reuse": "high",
     "key_symbols": ["planCompaction", "CompactionPlan", "forModelContext", "estimateEntryTokens", "estimateHistoryTokens", "recentEntryCountWithinBudget", "compactTranscript", "COMPACT_SOFT_FRACTION", "COMPACT_HARD_FRACTION", "INTERRUPTED_TOOL_RESULT"],
     "description": "Coeur de la compaction : planCompaction décide quoi résumer vs garder (fractions soft 0.7 / hard 0.9), préserve les paires tool_call/tool_result, résumé incrémental via throughSeq, reconstruction des calls interrompus. Cache tokens LRU 50k."},
    {"path": "references/qm/src/core/orchestrator/compaction.ts", "type": "code", "reuse": "high",
     "key_symbols": ["createCompaction", "compactContextIfNeeded", "scheduleBackgroundCompaction", "summarizeForCompaction", "applyCompaction", "MAX_CONTEXT_ENTRIES", "MAX_CONTEXT_TOKENS", "KEEP_RECENT_TOKEN_FRACTION"],
     "description": "Orchestration duale : compaction synchrone au-dessus de hard-limit, async en tâche de fond au-dessus de soft-limit (keyed queue + lease compaction 60s). Bornes 400 entries / 120k tokens."},
    {"path": "references/qm/src/harness/tape-fold.ts", "type": "code", "reuse": "medium",
     "key_symbols": ["foldTape", "lintFold", "healDanglingCalls", "healFoldInterrupt", "planTapeSeed", "filterTapeForAudience", "FoldLint"],
     "description": "Rejoue un tape (log events) en messages LLM. healDanglingCalls reconstruit des toolResult pour les tool_calls orphelins ; lintFold valide la structure. Pattern event-sourcing + garde-fous robustesse."},
    # --- Mémoire durable / knowledge graph (Priorité 6 Judge + Priorité 9) ---
    {"path": "references/qm/src/memory/strategies/consolidation.ts", "type": "code", "reuse": "high",
     "key_symbols": ["MEMORY_CONSOLIDATION_PROMPT", "parseConsolidationActions", "applyConsolidationActions", "createConsolidator", "ConsolidationAction"],
     "description": "LLM-juge qui maintient un notebook de mémoire : reçoit des facts numérotés, émet UPDATE <n> / DELETE <n> / ADD:. Déclenche après N bullets. Pattern exact du rôle Judge pour la consolidation claims/refutations DuckDB."},
    {"path": "references/qm/src/memory/strategies/scratch-promote.ts", "type": "code", "reuse": "high",
     "key_symbols": ["createScratchPromote", "PROMOTION_PROMPT", "logPath", "bumpMarker", "resetMarker", "readLogWindow"],
     "description": "Mémoire deux tiers : notebook long-terme curaté + logs scratch datés (expirent 14j). Marker captures-since-promote, à seuil atteint un LLM gradue le scratch vers le notebook."},
    {"path": "references/qm/src/memory/strategies/per-turn.ts", "type": "code", "reuse": "high",
     "key_symbols": ["createBurstBuffer", "extractFacts", "MEMORY_EXTRACTION_PROMPT", "AUTONOMOUS_EXTRACTION_ADDENDUM", "parseFacts", "isAutonomousBurst"],
     "description": "Burst buffer : regroupe les turns consécutifs (fenêtre quiet 180s ou maxTurns 10) puis flush un one-shot d'extraction. Distingue turns humains (préférences) vs autonomes (addendum anti-auto-attribution)."},
    {"path": "references/qm/src/memory/memory-service.ts", "type": "code", "reuse": "high",
     "key_symbols": ["MemoryService", "createMemoryService", "foldCapture", "queryBullets", "normalizeReplace", "replaceIfRevision", "revisionToken", "MAX_FACTS"],
     "description": "Interface recall/capture/query/replace/replaceIfRevision/history/restore. foldCapture dédup normalisée + cap 300 + provenance. replaceIfRevision = contrôle concurrence optimiste pour DuckDB."},
    {"path": "references/qm/src/memory/notebook.ts", "type": "code", "reuse": "high",
     "key_symbols": ["isBullet", "bulletText", "captureDate", "normalize", "capTail", "RECALL_MAX_CHARS"],
     "description": "Utilitaires purs de parsing de notebook markdown. capTail garde la fin (mémoire récente prioritaire), contre-intuitif et judicieux. Trivial à porter."},
    {"path": "references/qm/src/memory/postgres-memory-service.ts", "type": "code", "reuse": "medium",
     "key_symbols": ["createPostgresMemoryService", "conditionalReplace", "append"],
     "description": "Persistance append-only avec versioning (scope_id, seq). conditionalReplace = advisory lock + comparaison seq attendue. Schéma memory_revisions = blueprint pour DuckDB."},
    {"path": "references/qm/src/memory/strategies/agent-only.ts", "type": "code", "reuse": "medium",
     "key_symbols": ["createAgentOnlyStrategy", "AGENT_ONLY_PROMPT_LINES"],
     "description": "Stratégie sans capture auto : l'agent est le seul curateur via un tool memory. Mode dégradé/fallback utile."},
    {"path": "references/qm/src/memory/strategy.ts", "type": "code", "reuse": "medium",
     "key_symbols": ["MemoryStrategy", "MemoryStrategyKind", "createMemoryStrategy", "parseMemoryStrategyKind"],
     "description": "Factory qui compose strategy + memory wrapper. Dispatcher trivial à recoder en Python pour sélection declarative (per-turn / scratch-promote / agent-only)."},
    # --- Harness / cycle de vie ---
    {"path": "references/qm/src/harness/harness.ts", "type": "code", "reuse": "high",
     "key_symbols": ["Harness", "HarnessTurnController", "HarnessModelUtilities", "defineHarness", "HarnessCapability", "HarnessAdapterProfile"],
     "description": "Interface harnais abstrait : turns.runTurn + models (shouldRespond, compactHistory, contextTokenBudget, oneShot, judge, screenSecurity). Mappe 1:1 à l'architecture DSPy-Brains + smolagents-Hands."},
    {"path": "references/qm/src/core/orchestrator.ts", "type": "code", "reuse": "high",
     "key_symbols": ["createOrchestrator", "Orchestrator.handleTurn", "ProjectRosterChanged"],
     "description": "Spine complète d'un turn dans l'ordre exact : rate-limit -> budget -> resolution -> lease -> filter history -> security screen -> compaction -> run harness turn -> append -> background compaction -> memory capture. Blueprint du cycle de vie cible."},
    # --- Budgets / Rate-limit (Priorité 8) ---
    {"path": "references/qm/src/ratelimit/budget.ts", "type": "code", "reuse": "high",
     "key_symbols": ["createBudgetTracker", "BudgetTracker", "estimateCostUsd", "DEFAULT_BUDGET_WINDOW_MS"],
     "description": "Budget USD par principal sur fenêtre glissante 24h + limite org globale. check (allowed/spent/limit) + record. Estimation inputTokens × usdPerMTok portable tel quel."},
    {"path": "references/qm/src/ratelimit/rate-limiter.ts", "type": "code", "reuse": "high",
     "key_symbols": ["createRateLimiter", "RateLimiter", "RateLimiterOptions"],
     "description": "Rate limiter simple par fenêtre fixe : max maxPerWindow requêtes par windowMs par principal, retourne retryAfterMs. Trivial, pur, portable."},
    # --- Idempotency (Priorité 8 robustesse) ---
    {"path": "references/qm/src/idempotency/idempotency-store.ts", "type": "code", "reuse": "high",
     "key_symbols": ["IdempotencyStore", "createIdempotencyStore", "IdempotencyRecord", "once"],
     "description": "once(key, fn) : exécute fn exactement une fois (inflight set + done map + DurableMap), rétention 14j, prune périodique. Critique pour les turns rejoués (webhooks, cron, retries). À wrapper au-dessus de DuckDB."},
    # --- Queue de runs / sessions / persistance (Priorité 12 scopes) ---
    {"path": "references/qm/src/runs/run-store.ts", "type": "code", "reuse": "high",
     "key_symbols": ["RunStore", "Run", "RunStatus", "EnqueueInput", "EnqueueResult", "errorParks", "leaseLapsed", "isTerminal"],
     "description": "Contrat de queue de runs : enqueue(dedupKey), claim(workerId,ttl), heartbeat, releaseLease, complete, fail(retry?), reapExpired. errorParks = politique retry vs park définitif après N erreurs."},
    {"path": "references/qm/src/runs/postgres-run-store.ts", "type": "code", "reuse": "high",
     "key_symbols": ["createPostgresRunStore"],
     "description": "Impl SQL du RunStore : claim via ORDER BY created_at ASC FOR UPDATE SKIP LOCKED LIMIT 1, enqueue dedup via idempotency_key, lease par lease_token+lease_expires_at. Blueprint direct pour DuckDB."},
    {"path": "references/qm/src/sessions/session-store.ts", "type": "code", "reuse": "high",
     "key_symbols": ["SessionStore", "Lease", "LeaseHolder", "TapeRecord", "TapeKind", "LlmCallUsage"],
     "description": "Contrat session avec leases typés (turn/compaction/fork/backfill) : un turn ne peut pas compacter pendant qu'un autre tient le lease turn. LlmCallUsage = shape de télémétrie (input/output/cacheRead/cacheWrite/totalTokens/costUsd)."},
    {"path": "references/qm/src/persistence/durable-map.ts", "type": "code", "reuse": "high",
     "key_symbols": ["DurableMap", "createMemoryMap", "createPostgresMap", "createPostgresMapFactory", "applyPatch"],
     "description": "Map KV générique (get/put/putIfAbsent/merge/update/deleteIf/take) avec deux impls. Pattern version globale + cache snapshot invalidé (15s). Primitive de persistance universelle au-dessus de DuckDB."},
    {"path": "references/qm/src/persistence/leader-lease.ts", "type": "code", "reuse": "medium",
     "key_symbols": ["LeaderLease", "createPostgresLeaderLease", "createNoopLeaderLease", "hold"],
     "description": "Leader election via pg_try_advisory_lock ; hold(key, fn) exécute fn tant que le lock est tenu. Pour tâches singleton (reaper, compaction background). Contrat portable (émuler via table lease+timestamp en DuckDB)."},
    {"path": "references/qm/src/runs/worker.ts", "type": "code", "reuse": "medium",
     "key_symbols": ["createWorker", "processRun", "LEASE_LOST_CONSECUTIVE", "CLAIM_FAIL_CRASH_CONSECUTIVE"],
     "description": "Boucle worker : claim -> processRun (heartbeat, annulation après 3 beats perdus via AbortController) -> complete/fail. Backoff exponentiel sur échec de claim."},
    {"path": "references/qm/src/runs/tool-ledger.ts", "type": "code", "reuse": "medium",
     "key_symbols": ["ToolLedger", "createNullLedger", "LedgerBegin", "begin", "record"],
     "description": "Cache de résultats d'outils par (runId, attempt, callIndex) : begin retourne {cached, output?}, record persiste. Évite de ré-exécuter un tool idempotent au retry."},
    # --- Protocoles / prompts (Priorité 9 doctrine mémoire) ---
    {"path": "references/qm/src/resolution/protocols/shared-core.md", "type": "doc", "reuse": "high",
     "key_symbols": [],
     "description": "Prompt socle : doctrine mémoire (memory is an index of pointers, never the data itself ; working state va dans un fichier, pas un fact), sandbox persistant, skills comme procédures."},
    {"path": "references/qm/src/resolution/protocols/mode-autonomous.md", "type": "doc", "reuse": "medium",
     "key_symbols": [],
     "description": "Prompt mode autonome : personne ne lit ce transcript, worklog privé, silence par défaut, une ligne de log en fin de turn. Transposable au Judge/Tester."},
    {"path": "references/qm/src/resolution/protocols/mode-conversation.md", "type": "doc", "reuse": "medium",
     "key_symbols": [],
     "description": "Prompt DM 1:1 : ack en une ligne puis travail silencieux, dernier message auto-suffisant, jamais pointer le tool output brut. Hygiène applicable aux Coders."},
    {"path": "references/qm/src/resolution/protocols/mode-fallback.md", "type": "doc", "reuse": "medium",
     "key_symbols": [],
     "description": "Prompt turns sans surface (cron/replay) : réponse finale = ce que la personne lira, human terms. Pertinent pour les turns automatisés de l'orchestrateur."},
    {"path": "references/qm/README.md", "type": "doc", "reuse": "low",
     "key_symbols": [],
     "description": "Présentation produit, surfaces Slack/Web, multi-harness. Peu de valeur technique transposable."},
]

# ---------------------------------------------------------------------------
# 15 — claude-code-unified-agents : 13 entrées (prompts purs + en-têtes)
# ---------------------------------------------------------------------------
CC_BASE = "references/claude-code-unified-agents/claude-code-unified-agents/.claude/agents"
CC_FILES = [
    # --- Méta / orchestration ---
    {"path": f"{CC_BASE}/orchestrator.md", "type": "prompt", "reuse": "high",
     "key_symbols": ["Conditional Routing", "delegate_to", "Decision Framework"],
     "description": "Prompt pur (185 lignes). Routeur déclaratif : Sequential/Parallel/Conditional Routing, syntaxe delegate_to(agent, task=...), output Task Analysis & Delegation Plan. Correspond au nœud Routeur du graphe."},
    {"path": f"{CC_BASE}/specialized/error-detective.md", "type": "prompt", "reuse": "medium",
     "key_symbols": ["enhanceStackTrace", "identifyPattern", "findRootCause", "generateHypothesis", "findSolutions", "generateReport"],
     "description": "En-tête prompt RCA (pipeline investigate en 7 étapes), suivi de ~990 lignes de code TS non portable. Canevas de raisonnement pour un Debugger/diagnostic agent ou la boucle de réparation du Tester."},
    {"path": f"{CC_BASE}/specialized/context-manager.md", "type": "prompt", "reuse": "medium",
     "key_symbols": ["State Isolation", "Checkpointing", "Event Sourcing", "last-write-wins", "deep-merge"],
     "description": "En-tête : session continuity, checkpoints, stratégies de merge. 90% du fichier est une implémentation TS ContextManager non portable. Concepts utiles pour l'état partagé entre nœuds du graphe."},
    {"path": f"{CC_BASE}/specialized/agent-generator.md", "type": "prompt", "reuse": "medium",
     "key_symbols": ["AgentCapabilitySchema", "analyzeRequirements", "selectPattern", "composeCapabilities", "generateSystemPrompt"],
     "description": "En-tête : dynamic agent creation. AgentCapabilitySchema (zod : name/description/category/expertise/tools/constraints) + pipeline de génération de system_prompt. Aligné avec le plan spécialisation des agents."},
    # --- Development (Coders) ---
    {"path": f"{CC_BASE}/development/backend-architect.md", "type": "prompt", "reuse": "high",
     "key_symbols": ["Scalability", "Data consistency", "Security implications", "Monitoring", "Deployment and rollback"],
     "description": "Prompt pur (46 lignes). API REST/GraphQL, microservices. 5 axes obligatoires de conception = cadre de raisonnement pour le nœud Architect et le contract.md."},
    {"path": f"{CC_BASE}/development/python-pro.md", "type": "prompt", "reuse": "high",
     "key_symbols": ["comprehensive type hints", "PEP 8", "docstrings", "pytest", "mypy"],
     "description": "Prompt pur (55 lignes). Expert Python : type hints systématiques, PEP 8, docstrings avec exemples. L'un des seuls avec garde-fous concrets. Coder Python direct, champ tools = canevas smolagents."},
    {"path": f"{CC_BASE}/development/frontend-specialist.md", "type": "prompt", "reuse": "high",
     "key_symbols": ["semantic HTML", "ARIA", "keyboard navigation", "lazy loading", "code splitting"],
     "description": "Prompt pur (49 lignes). React/Vue/Angular/Svelte, a11y. Coder Web/Frontend, directives a11y utiles pour le Tester web."},
    # --- Quality (Tester / Judge / Security) ---
    {"path": f"{CC_BASE}/quality/test-engineer.md", "type": "prompt", "reuse": "high",
     "key_symbols": ["Test Pyramid 70/20/10", "BDD", "TDD", "Arrange-Act-Assert", "independent and isolated tests"],
     "description": "Prompt pur (148 lignes). Stratégies de test, pyramide 70/20/10, pattern AAA, tests indépendants. Garde-fous actionnables pour le prompt du Tester Python."},
    {"path": f"{CC_BASE}/quality/code-reviewer.md", "type": "prompt", "reuse": "high",
     "key_symbols": ["Critical", "Major", "Minor", "Read", "Grep", "Glob", "Bash"],
     "description": "Prompt pur (103 lignes). Review qualité/sécurité/perf. Tools lecture seule (PAS de Write = conforme à un Judge). Output structuré Code Review Summary Critical/Major/Minor + Acknowledge good practices. Inspiration directe du format du Judge (Priorité 6)."},
    {"path": f"{CC_BASE}/quality/security-auditor.md", "type": "prompt", "reuse": "high",
     "key_symbols": ["OWASP Top 10", "SOC2", "HIPAA", "PCI-DSS", "GDPR", "ISO27001", "CVSS"],
     "description": "Prompt pur (125 lignes). SAST/DAST/SCA, frameworks compliance, tools lecture seule. Output Security Audit Report avec scores CVSS. Security Reviewer direct, taxonomie vulns transposable."},
    {"path": f"{CC_BASE}/quality/e2e-test-specialist.md", "type": "prompt", "reuse": "medium",
     "key_symbols": ["Page Object Pattern", "Test Independence", "explicit waits"],
     "description": "En-tête prompt Playwright/Cypress/POM puis ~970 lignes de code TS non portable. Seules les Best Practices (~30 lignes) sont portables. Tester web."},
    # --- Infrastructure (secondaire) ---
    {"path": f"{CC_BASE}/infrastructure/devops-engineer.md", "type": "prompt", "reuse": "medium",
     "key_symbols": ["principle of least privilege", "automate everything", "immutable infrastructure", "blue-green deployments"],
     "description": "Prompt pur (62 lignes). CI/CD, IaC. Cadre secondaire, utile seulement si un agent DevOps/release est ajouté."},
    {"path": "references/claude-code-unified-agents/README.md", "type": "doc", "reuse": "low",
     "key_symbols": [],
     "description": "Présentation produit. Annonce 54 agents mais le dépôt en contient 53 (4 promis absents : ui-designer, content-strategist, performance-optimizer, iot-engineer)."},
]


# ---------------------------------------------------------------------------
# 16 — learn-claude-code : 18 entrées (patterns Python natifs, testés)
# ---------------------------------------------------------------------------
LCC_FILES = [
    # --- Intégration / vue d'ensemble ---
    {"path": "references/learn-claude-code/s20_comprehensive/code.py", "type": "code", "reuse": "high",
     "key_symbols": ["terminal_print", "agent loop agrégée"],
     "description": "Capstone 2119 lignes : hooks + compaction + task graph + error recovery + memory + subagent + background dans une seule boucle sans collision. Référence d'intégration montrant que les patterns se combinent. Point d'entrée recommandé."},
    {"path": "references/learn-claude-code/agents/s_full.py", "type": "code", "reuse": "high",
     "key_symbols": ["microcompact", "drain background", "check inbox", "dispatch 23 outils"],
     "description": "Capstone s01-s11 (740 lignes) : microcompact + drain background + check inbox avant chaque appel LLM. Version consolidée SANS le bruit s14-s19. Souvent le meilleur point d'entrée unique."},
    # --- P8 : Hooks + Error Recovery + Compaction (préservation paires) ---
    {"path": "references/learn-claude-code/s04_hooks/code.py", "type": "code", "reuse": "high",
     "key_symbols": ["HOOKS", "trigger_hooks", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"],
     "description": "Architecture middleware en ~30 lignes : registre HOOKS[event] + trigger_hooks (court-circuite si callback retourne non-None). Squelette de TOUS les middlewares (Sanitizer, Orphan Repair, LoopDetection) ET de l'event stream. P8 + P11."},
    {"path": "references/learn-claude-code/s11_error_recovery/code.py", "type": "code", "reuse": "high",
     "key_symbols": ["RecoveryState", "with_retry", "is_prompt_too_long_error", "backoff", "fallback model"],
     "description": "3 chemins de récupération : escalation max_tokens 8K→64K, compaction, backoff exponentiel+jitter (max 10) + fallback model après 529 consécutifs. Squelette du middleware anti-crash. P8."},
    {"path": "references/learn-claude-code/s08_context_compact/code.py", "type": "code", "reuse": "high",
     "key_symbols": ["snip_compact", "micro_compact", "tool_result_budget", "reactive_compact", "budget → snip → micro → auto"],
     "description": "4 couches en cascade : snip (trim middle si >50 msg), micro (remplace vieux tool_results par placeholders), budget (persiste gros résultats sur disque), reactive (urgence prompt_too_long). Préserve les paires tool_use/tool_result = Orphan Repair. Équivalent Python de context-compaction.ts (qm). P9."},
    {"path": "references/learn-claude-code/tests/test_compaction_tool_pairs.py", "type": "test", "reuse": "high",
     "key_symbols": ["assert_no_orphan_tool_results", "snip_compact", "reactive_compact"],
     "description": "Test du middleware Orphan Repair : valide la préservation des paires tool_use/tool_result (5 scénarios). Test exact de la préoccupation P8 Orphan Repair. Pattern de test réutilisable."},
    # --- P10 : Skill loading ---
    {"path": "references/learn-claude-code/s07_skill_loading/code.py", "type": "code", "reuse": "high",
     "key_symbols": ["_parse_frontmatter", "_scan_skills", "load_skill"],
     "description": "Lazy loading : scan skills/*/SKILL.md au démarrage (parse YAML frontmatter), injecte nom+description (~100 tokens/skill) dans SYSTEM, load_skill(name) charge le contenu complet via tool_result à la demande. Blueprint quasi direct de P10, Python natif."},
    {"path": "references/learn-claude-code/skills/code-review/SKILL.md", "type": "skill", "reuse": "high",
     "key_symbols": ["Security", "Correctness", "Performance", "Maintainability", "Testing"],
     "description": "Checklist structurée de revue + format de sortie (158 lignes). Réutilisable tel quel comme prompt de Judge. P6."},
    # --- P6 : Task system + TodoWrite ---
    {"path": "references/learn-claude-code/s12_task_system/code.py", "type": "code", "reuse": "high",
     "key_symbols": ["Task", "blockedBy", "can_start", "claim_task", "complete_task"],
     "description": "Mini-orchestrateur DAG file-backed : Task dataclass (id, subject, status, owner, blockedBy), can_start (deps manquantes=bloqué), claim_task, complete_task (reporte débloquage aval). P6 cycle de vie plan + base P3."},
    {"path": "references/learn-claude-code/s05_todo_write/code.py", "type": "code", "reuse": "high",
     "key_symbols": ["TodoWrite", "nag reminder", "_normalize_todos"],
     "description": "Persistence d'un plan/todo à travers la conversation + nag reminder (réinjecte si stale) + validation défensive (_normalize_todos fallback JSON→ast.literal_eval car LLM envoie souvent string au lieu de list). P6."},
    # --- P0 : Subagent ---
    {"path": "references/learn-claude-code/s06_subagent/code.py", "type": "code", "reuse": "high",
     "key_symbols": ["spawn_subagent", "max 30 turns", "pas de récursion"],
     "description": "spawn_subagent(description) : messages frais, hard cap 30 tours, pas de récursion (subagent sans l'outil task), retourne summary only. Patron d'isolation des subagents pour Coder/Tester spécialisés. P0."},
    # --- P0 : fondamentaux agent loop + tools + system prompt ---
    {"path": "references/learn-claude-code/s01_agent_loop/code.py", "type": "code", "reuse": "medium",
     "key_symbols": ["while stop_reason == tool_use"],
     "description": "Boucle agent nue (137 lignes) : perception → LLM → action. Socle minimal, clair et dépouillé. P0 fondamentaux (smolagents fournit déjà cette boucle)."},
    {"path": "references/learn-claude-code/s02_tool_use/code.py", "type": "code", "reuse": "medium",
     "key_symbols": ["TOOL_HANDLERS", "dispatch map"],
     "description": "Multi-outils + dispatch map TOOL_HANDLERS (190 lignes). Pattern de registre d'outils déjà utilisé dans tools.py du projet cible. P0."},
    {"path": "references/learn-claude-code/s10_system_prompt/code.py", "type": "code", "reuse": "medium",
     "key_symbols": ["assemblage system prompt", "cache déterministe"],
     "description": "Construction reproductible du system prompt (skills + mémoire + cache déterministe, 219 lignes). P0/P11."},
    # --- P8-bis partiel : Permission (deny-list, pas isolation) ---
    {"path": "references/learn-claude-code/s03_permission/code.py", "type": "code", "reuse": "medium",
     "key_symbols": ["deny", "rule", "approval", "3 gates"],
     "description": "3 gates : deny (règles permanentes), rule (auto-approve par pattern), approval (humain). Limité à un deny-list, pas une vraie isolation Docker. P8-bis partiel (à combiner avec qm pour sandbox complète)."},
    # --- Mémoire (partiel, pas un KG) ---
    {"path": "references/learn-claude-code/s09_memory/code.py", "type": "code", "reuse": "medium",
     "key_symbols": ["select_relevant_memories", ".memory/", "frontmatter"],
     "description": "Mémoire persistante file-backed : index léger + fichiers Markdown frontmatter, select_relevant_memories (LLM ou fallback keyword). Pas un KG (pas de claims/refutations). Pattern index+contenu à la demande transposable. P6 partiel."},
    # --- Hors scope (exclusions conscientes, gardés pour traçabilité) ---
    {"path": "references/learn-claude-code/s18_worktree_isolation/code.py", "type": "code", "reuse": "low",
     "key_symbols": ["git worktree add", "validate_worktree_name", "_count_worktree_changes", "events.jsonl"],
     "description": "Isolation par worktree git soignée (anti path traversal). Hors scope : orienté git worktree, pas multi-tenant utilisateurs. qm reste la réf P12."},
    {"path": "references/learn-claude-code/s19_mcp_plugin/code.py", "type": "code", "reuse": "low",
     "key_symbols": ["MCPClient (mock)", "assemble_tool_pool", "mcp__{server}__{tool}"],
     "description": "MCPClient est un MOCK (handler factice, pas de vraie connexion stdio/HTTP). Seul le naming convention est utile. Le projet cible a déjà Context7 MCP branché."},
]


# ---------------------------------------------------------------------------
# 17 — system-prompts-and-models-of-ai-tools : 17 entrées (prompts + invariants)
# ---------------------------------------------------------------------------
SP_BASE = "references/system-prompts-and-models-of-ai-tools"
SP_FILES = [
    # --- Top 6 prompts d'agents de coding (🟢 Haute) ---
    {"path": f"{SP_BASE}/Open Source prompts/Codex CLI/openai-codex-cli-system-prompt-20250820.txt", "type": "prompt", "reuse": "high",
     "key_symbols": ["Testing your work", "3 modes sandbox", "4 modes approval", "apply_patch", "fix root cause not surface"],
     "description": "Le plus aligned avec notre stack CLI (342 L, open-source). Philosophie de test start specific → broaden, 3 modes sandbox (read-only/workspace-write/danger), 4 modes approval (untrusted/on-failure/on-request/never), format apply_patch. Sections Testing + Sandbox exploitables telles quelles pour Coder + Tester."},
    {"path": f"{SP_BASE}/Manus Agent Tools & Prompt/Prompt.txt", "type": "prompt", "reuse": "high",
     "key_symbols": ["Planner", "Knowledge", "Datasource", "agent loop", "todo.md"],
     "description": "Architecture multi-module (Planner/Knowledge/Datasource séparés dans l'event stream) + agent loop formel Analyze→Select→Wait→Iterate→Submit→Standby. Blueprint direct pour Router→Architect→Coders fan-out. Notre topologie."},
    {"path": f"{SP_BASE}/Manus Agent Tools & Prompt/Modules.txt", "type": "prompt", "reuse": "high",
     "key_symbols": ["Planner", "Knowledge", "Datasource", "event stream"],
     "description": "Détaille l'architecture multi-module (Planner/Knowledge/Datasource séparés). Modèle pour la séparation des rôles et le fan-out."},
    {"path": f"{SP_BASE}/Manus Agent Tools & Prompt/Agent loop.txt", "type": "prompt", "reuse": "high",
     "key_symbols": ["Analyze", "Select", "Wait", "Iterate", "Submit", "Standby"],
     "description": "Agent loop formel en 6 phases (33 L). Skeleton de boucle agent réutilisable."},
    {"path": f"{SP_BASE}/Augment Code/gpt-5-agent-prompts.txt", "type": "prompt", "reuse": "high",
     "key_symbols": ["Tasklist Triggers", "Information-gathering tools", "Package Management", "view", "grep-search", "codebase-retrieval"],
     "description": "Très structuré (241 L). Catégorisation des outils par purpose (view/grep-search/codebase-retrieval), Tasklist Triggers (multi-file, >2 itérations), Package Management par langage (pip/poetry pour Python), escalade si rabbit hole. Parfait pour Router + Coder Python."},
    {"path": f"{SP_BASE}/Anthropic/Claude Code 2.0.txt", "type": "prompt", "reuse": "high",
     "key_symbols": ["Git Safety Protocol", "professional objectivity", "read-before-edit", "anti-syscall", "no preamble/postamble"],
     "description": "Référence Coder + Judge + Security (1150 L). Git Safety Protocol (jamais --force/--no-verify/amend sans check), professional objectivity (truth > validation = base du Reviewer), read-before-edit (Edit échoue si non lu), concision radicale. Verbeux — voir la version courte Claude Code/Prompt.txt (191 L)."},
    {"path": f"{SP_BASE}/Anthropic/Claude Code/Prompt.txt", "type": "prompt", "reuse": "high",
     "key_symbols": ["concision", "tool usage policy", "Git Safety"],
     "description": "Condensé du Claude Code (191 L). Bonne densité directive sans le padding de la version 2.0."},
    {"path": f"{SP_BASE}/Open Source prompts/Gemini CLI/google-gemini-cli-system-prompt.txt", "type": "prompt", "reuse": "high",
     "key_symbols": ["Understand", "Plan", "Implement", "Verify Tests", "Verify Standards", "NEVER assume standard test commands"],
     "description": "Ultra-dense (188 L, open-source). Workflow 5 étapes explicite, NEVER assume standard test commands (check README/package.json), auto-vérification post-edit (lint+typecheck OBLIGATOIRE). Squelette du cycle Coder→Tester→Judge."},
    {"path": f"{SP_BASE}/Devin AI/Prompt.txt", "type": "prompt", "reuse": "high",
     "key_symbols": ["<think> tool", "10 cas d'usage", "ne jamais modifier les tests", "report environment issues"],
     "description": "(402 L) <think> tool avec 10 cas d'usage obligatoires (avant git critique, avant code changes, avant completion) = base du reasoning Architect/Judge. Règle ne jamais modifier les tests = critique pour le Tester. Data Security section."},
    {"path": f"{SP_BASE}/Cursor Prompts/Agent Prompt 2025-09-03.txt", "type": "prompt", "reuse": "high",
     "key_symbols": ["status_update_spec", "maximize_parallel_tool_calls", "gate avant edit", "anti-boucle linter max 3", "Clean Code"],
     "description": "Récent et dense (229 L). status_update cadencé (avant batch, après todo = tracing inter-agent), gate avant edit (reconcile TODO), anti-boucle linter (max 3 puis ask user), code_style Clean Code. Implémente concrètement notre P3/P8 anti-boucle."},
    {"path": f"{SP_BASE}/Open Source prompts/Cline/Prompt.txt", "type": "prompt", "reuse": "high",
     "key_symbols": ["SEARCH/REPLACE blocks", "requires_approval", "règles 1-4", "move/delete"],
     "description": "Spec de référence du format SEARCH/REPLACE (607 L, open-source). Règles 1-4 documentées exhaustivement + opérations move/delete. requires_approval booléen par commande. Déjà porté en P1 côté édition."},
    {"path": f"{SP_BASE}/Traycer AI/phase_mode_prompts.txt", "type": "prompt", "reuse": "high",
     "key_symbols": ["You DO NOT write code", "read-only tech lead", "phases high-level", "decision tree"],
     "description": "Architect PUR (46 L). Read-only tech lead (ne écrit pas de code), breakdown en phases, decision tree clarification. Modèle du Read-Only déjà appliqué dans notre Architect DSPy."},
    # --- Prompts Moyenne (utilses mais alignement partiel) ---
    {"path": f"{SP_BASE}/Windsurf/Prompt Wave 11.txt", "type": "prompt", "reuse": "medium",
     "key_symbols": ["create_memory", "update_plan", "gate unsafe commands", "browser_preview"],
     "description": "Concis (125 L). Memory system persistant + plan mastermind + gate unsafe commands. Utile si on ajoute persistence inter-turns."},
    {"path": f"{SP_BASE}/Replit/Prompt.txt", "type": "prompt", "reuse": "medium",
     "key_symbols": ["proposed_file_replace_substring", "is_dangerous", "protocole XML"],
     "description": "Format XML intéressant (137 L) : proposed_file_replace_substring, proposed_shell_command is_dangerous=true. Alternative à SEARCH/REPLACE + approval gating."},
    {"path": f"{SP_BASE}/Kiro/Spec_Prompt.txt", "type": "prompt", "reuse": "medium",
     "key_symbols": ["spec/design documents", "ABSOLUTE MINIMAL code", "PII substitution"],
     "description": "Architect (spec) + Security (PII substitution). 514 L."},
    {"path": f"{SP_BASE}/Open Source prompts/RooCode/Prompt.txt", "type": "prompt", "reuse": "medium",
     "key_symbols": ["multi-mode", "Code/Architect/Ask/Debug", ".roo/rules-*"],
     "description": "Variante de Cline (665 L, open-source) + multi-mode (Code/Architect/Ask/Debug) + custom instructions par mode. Patron de spécialisation (P0)."},
    {"path": f"{SP_BASE}/Cursor Prompts/Agent Tools v1.0.json", "type": "spec", "reuse": "medium",
     "key_symbols": ["codebase_search", "read_file", "function-calling"],
     "description": "Schéma de function-calling (JSON). Référence pour concevoir les signatures d'outils DSPy/smolagents."},
]


# ---------------------------------------------------------------------------
# 18 — awesome-claude-skills : 10 entrées (format SKILL.md + outillage)
# ---------------------------------------------------------------------------
ACS_BASE = "references/awesome-claude-skills"
ACS_FILES = [
    # --- skill-creator : méta-skill pivot (P10) ---
    {"path": f"{ACS_BASE}/skill-creator/SKILL.md", "type": "skill", "reuse": "high",
     "key_symbols": ["Anatomy", "Progressive Disclosure", "three-level loading", "Metadata", "SKILL.md body", "Bundled resources"],
     "description": "Méta-skill pivot (209 L). Définit l'anatomie d'une skill ET le modèle 3-niveaux (Progressive Disclosure) : Metadata ~100 mots toujours en contexte → corps SKILL.md <5k mots au déclenchement → resources illimitées (scripts exécutés sans être lus). Caution externe du modèle P10."},
    {"path": f"{ACS_BASE}/skill-creator/scripts/init_skill.py", "type": "code", "reuse": "high",
     "key_symbols": ["init_skill", "scaffolding", "SKILL.md + scripts/ + references/ + assets/"],
     "description": "Génère le squelette canonique d'une skill (303 L) : SKILL.md + 3 dossiers. Réutilisable en l'état comme scripts/new_skill.py pour normaliser la création de nos skills."},
    {"path": f"{ACS_BASE}/skill-creator/scripts/quick_validate.py", "type": "code", "reuse": "high",
     "key_symbols": ["validate_frontmatter", "regex ^[a-z0-9-]+$", "check chevrons <>"],
     "description": "Valide (64 L) : name en hyphen-case strict, pas de --, pas de chevrons dans description, description explicite. À adopter comme gate CI/pre-commit sur notre dossier skills/."},
    {"path": f"{ACS_BASE}/skill-creator/scripts/package_skill.py", "type": "code", "reuse": "medium",
     "key_symbols": ["package_skill", "zip bundling"],
     "description": "Packaging zip d'une skill pour distribution marketplace. Mécanisme utile à comprendre ; moins pertinent pour nous."},
    # --- mcp-builder ---
    {"path": f"{ACS_BASE}/mcp-builder/SKILL.md", "type": "skill", "reuse": "high",
     "key_symbols": ["Research", "Implementation", "Review", "Evaluation", "Build for Workflows", "Optimize for Limited Context"],
     "description": "Guide 4 phases (328 L) pour bâtir des serveurs MCP. Principes de design d'outils pour agents transposables à nos Hands smolagents : Build for Workflows Not Just API, Optimize for Limited Context, Actionable Error Messages, Evaluation-Driven Development."},
    {"path": f"{ACS_BASE}/mcp-builder/reference/mcp_best_practices.md", "type": "doc", "reuse": "high",
     "key_symbols": ["Build for Workflows", "Optimize for Limited Context", "Actionable Error Messages"],
     "description": "Bonnes pratiques MCP. Principes de design d'outils transposables aux tools smolagents."},
    {"path": f"{ACS_BASE}/mcp-builder/reference/evaluation.md", "type": "doc", "reuse": "medium",
     "key_symbols": ["10 questions XML", "vérification"],
     "description": "Pattern créer 10 questions d'évaluation XML + vérifier les réponses. Transposable au nœud Judge (création de cas de vérification)."},
    # --- webapp-testing ---
    {"path": f"{ACS_BASE}/webapp-testing/SKILL.md", "type": "skill", "reuse": "medium",
     "key_symbols": ["Playwright", "reconnaissance-then-action", "screenshot → sélecteurs"],
     "description": "Test de webapps locales via Playwright (95 L) avec gestion cycle de vie serveur. Complément Playwright-native à notre web_tester (Puppeteer MCP)."},
    {"path": f"{ACS_BASE}/webapp-testing/scripts/with_server.py", "type": "code", "reuse": "medium",
     "key_symbols": ["wait_for_port", "multi-serveur", "cycle de vie serveur"],
     "description": "Démarre/arrête un serveur local proprement pendant les tests Playwright, attend que le port soit prêt. Pattern réutilisable pour le nœud Tester."},
    # --- document-skills (exemple scripts-heavy) ---
    {"path": f"{ACS_BASE}/document-skills/docx/ooxml/scripts/pack.py", "type": "code", "reuse": "medium",
     "key_symbols": ["pack", "unpack", "validate", "manipulation zip OOXML"],
     "description": "Manipulation OOXML complète (~30 .py dans document-skills). Exemple le plus abouti de skill scripts-heavy : modèle de découplage SKILL.md (instructions) / scripts/ (déterministe) / references/ (doc). Illustre exécuter sans lire la source."},
    # --- changelog-generator (exemple pure-instructions) ---
    {"path": f"{ACS_BASE}/changelog-generator/SKILL.md", "type": "skill", "reuse": "medium",
     "key_symbols": ["pure-instructions", "catégorisation commits → changelog"],
     "description": "Transforme commits git en changelog user-friendly catégorisé (104 L, 0 script). Branchable sur post-hook Coder. Contre-point : skill pure-instructions (vs docx tout-script)."},
]


# ---------------------------------------------------------------------------
# 19 — loopx : control plane pour agents longue durée (P3 anti-loop + P9 compaction + P11 event stream)
# ---------------------------------------------------------------------------
LOOPX_BASE = "references/loopx"
LOOPX_FILES = [
    # --- P3 Anti-loop (Priorité 3) ---
    {"path": f"{LOOPX_BASE}/loopx/control_plane/quota/recent_runs.py", "type": "code", "reuse": "high",
     "key_symbols": ["consecutive_unchanged_monitor_observations", "build_monitor_debt_arbitration", "_run_is_unchanged_monitor_observation", "_run_is_controller_bookkeeping", "MONITOR_DEBT_UNCHANGED_TURN_THRESHOLD"],
     "description": "Détecteur de stall déterministe (~160 L). Compte les turns consécutifs sans transition matérielle ; ignore le bookkeeping (accounting/state_refreshed) ; au-delà du seuil=2, l'arbitration change la priorité (backoff). Complément déterministe à crush (10) qui ne fait que du hash d'output."},
    {"path": f"{LOOPX_BASE}/loopx/capabilities/issue_fix/pr_monitor_materialization.py", "type": "code", "reuse": "high",
     "key_symbols": ["_group_fingerprint", "result_hash", "material_change", "consecutive_no_change"],
     "description": "Pattern de détection de boucle par hash d'output. Calcule un hash canonique de la sortie, le compare au précédent ; si inchangé, incrémente un compteur de stall. Pattern exact pour hasher la sortie du Coder à chaque itération (complète notre F-36 qui ne fingerprint que les tool_calls)."},
    {"path": f"{LOOPX_BASE}/loopx/control_plane/work_items/delivery_outcome.py", "type": "code", "reuse": "high",
     "key_symbols": ["DeliveryOutcome", "DeliveryTurnKind", "ACCOUNTABLE_DELIVERY_OUTCOMES", "PROGRESS_DELIVERY_OUTCOMES", "normalize_delivery_outcome", "delivery_turn_kind_for_run"],
     "description": "Vocabulaire normalisé du résultat d'un turn (accountable/progress/followthrough). Un turn sans outcome matérielle = pas de progression = graine de stall. La métrique qui alimente tout l'anti-loop loopx."},
    {"path": f"{LOOPX_BASE}/loopx/control_plane/turn_driver/transaction.py", "type": "code", "reuse": "high",
     "key_symbols": ["LoopXTurnResultKind", "build_loopx_turn_transaction_plan", "validate_loopx_turn_receipt", "NO_SPEND_RESULT_KINDS", "STOP_RESULT_KINDS"],
     "description": "Modèle de transaction pour un turn d'agent. Enum (VALIDATED_PROGRESS/REPAIR_REQUIRED/REPLAN_REQUIRED/QUOTA_SPEND_FAILED...), phases ordonnées result<validate<writeback<spend, gating du spend selon le résultat. Distingue turns qui coûtent vs turns gratuits. Transposable au workflow Coder→Linter→Tester."},
    {"path": f"{LOOPX_BASE}/loopx/control_plane/quota/slot_accounting.py", "type": "code", "reuse": "medium",
     "key_symbols": ["build_quota_slot_spend_event", "record_quota_slot_spend_from_preview", "_latest_unspent_accountable_delivery_run", "build_quota_slot_void_event"],
     "description": "Comptabilité des slots de quota : chaque delivery accountable consomme un slot, détection du dernier run accountable non dépensé, void/annulation. Budget anti-boucle (au-delà du quota → escalade). Lié au modèle goal/run loopx."},
    {"path": f"{LOOPX_BASE}/loopx/control_plane/quota/stall_repair.py", "type": "code", "reuse": "medium",
     "key_symbols": ["build_quota_stall_self_repair_hint", "apply_stall_repair_delivery_guard", "RUNTIME_RECOVERY_ACTION_TOKENS", "control_plane_self_repair_allows"],
     "description": "Au lieu de bloquer ou spinner, déclenche un self-repair turn borné : un seul spend autorisé après réparation+validation+writeback. Décide si l'action recommandée est une réparation runtime (retry/repair/restore)."},
    # --- P9 Compaction (Priorité 9) ---
    {"path": f"{LOOPX_BASE}/loopx/control_plane/runtime/run_compaction.py", "type": "code", "reuse": "high",
     "key_symbols": ["compact_run_base", "compact_human_reward", "compact_operator_gate", "compact_vision_checkpoint", "RUN_BASE_COMPACT_FIELDS"],
     "description": "Compaction par whitelist de champs par type de payload (un tuple de champs à garder). Évite le trim bête : garde l'essentiel structurel, jette le verbose. Compaction structurelle (pas sémantique) — à compléter par un résumé LLM pour petits modèles. Transposable quasi-direct."},
    {"path": f"{LOOPX_BASE}/loopx/control_plane/runtime/run_context_retention.py", "type": "code", "reuse": "high",
     "key_symbols": ["latest_runs_with_agent_context", "PER_AGENT_CONTEXT_RUN_FIELDS"],
     "description": "Rétention du contexte durable le plus récent par agent (vision/checkpoint). Complément à run_compaction : préserve le dernier état vision/checkpoint par agent lors de la compaction."},
    # --- P11 Event stream (Priorité 11) ---
    {"path": f"{LOOPX_BASE}/loopx/event_sourced_state.py", "type": "code", "reuse": "high",
     "key_symbols": ["AppendOnlyStateEventStore", "normalize_state_event", "event_fingerprint", "event_stream_checksum", "_dedupe_events", "build_state_projection", "StateEventConflictError"],
     "description": "Event sourcing append-only JSONL : idempotence par event_id+fingerprint, détection de conflit, séquence auto, rebuild d'état par projection, checksum SHA256 du flux. Lock fichier exclusif sur append. Logique d'idempotence/reprise directement adaptable (à reloger sur DuckDB au lieu de JSONL)."},
    {"path": f"{LOOPX_BASE}/loopx/control_plane/runtime/event_ledger.py", "type": "code", "reuse": "high",
     "key_symbols": ["EVENT_LEDGER_CLASSES", "event_ledger_event_class", "build_event_ledger_summary", "blank_event_ledger_goal"],
     "description": "Journal d'événements classifiés en 5 classes (accounting/decision/evidence/state/work), agrégés sur fenêtres 24h/7d par goal, avec dernier event/benchmark. Projection depuis l'historique de runs. Blueprint pour l'event stream (P11) au-delà du contrat deer-flow (08/13)."},
]


# ---------------------------------------------------------------------------
# 20 — code-review-graph : risk score + blast radius pour le Judge (P6)
# ---------------------------------------------------------------------------
CRG_BASE = "references/code-review-graph"
CRG_FILES = [
    # --- Risk score composite (P6 Judge) ---
    {"path": f"{CRG_BASE}/code_review_graph/changes.py", "type": "code", "reuse": "high",
     "key_symbols": ["compute_risk_score", "analyze_changes", "review_priorities", "test_gaps"],
     "description": "Score de risque 0.0-1.0 multi-facteurs : flow participation (cap 0.25), cross-community callers (cap 0.15), test coverage transitive (0.30→0.05 si >=5 tests), security keywords (+0.20), caller count (cap 0.10), churn (cap 0.15). review_priorities = top-10 par score desc. Transposable en signaux quantitatifs d'entrée du Judge."},
    {"path": f"{CRG_BASE}/code_review_graph/constants.py", "type": "code", "reuse": "high",
     "key_symbols": ["SECURITY_KEYWORDS", "IMPACT_EDGE_WEIGHTS", "IMPACT_EDGE_DIRECTIONS", "IMPACT_DEPTH_DECAY", "IMPACT_SCORE_FLOOR"],
     "description": "Tables de poids par type de relation (CALLS 1.0, INHERITS 0.9, TESTED_BY 0.7, REFERENCES 0.6, IMPORTS_FROM 0.5, CONTAINS 0.3) + decay géométrique par hop (0.6) + plancher (0.05) + SECURITY_KEYWORDS (26 termes). Réutilisables telles quelles."},
    {"path": f"{CRG_BASE}/code_review_graph/tools/context.py", "type": "code", "reuse": "high",
     "key_symbols": ["get_minimal_context", "risk bucketing", "_extract_warnings"],
     "description": "Seuils de bucketing risk→label (>0.7 high, >0.4 medium, sinon low) + extraction de warnings (test gaps, high risk, coupling). Couplage minimal→standard→verbose. Seuils 0.7/0.4 à calibrer pour la rubric critical/high/medium/low du Judge."},
    {"path": f"{CRG_BASE}/code_review_graph/flows.py", "type": "code", "reuse": "medium",
     "key_symbols": ["compute_criticality", "detect_entry_points", "trace_flows"],
     "description": "Score de criticalité d'un flux d'exécution : file_spread 0.30 + external_calls 0.20 + security 0.25 + test_gap 0.15 + depth 0.10. Un finding sur un flow critique est plus prioritaire."},
    {"path": f"{CRG_BASE}/code_review_graph/graph.py", "type": "code", "reuse": "medium",
     "key_symbols": ["get_impact_radius", "get_impact_radius_sql", "get_impact_radius_networkx", "MAX_IMPACT_NODES"],
     "description": "Blast radius par relaxation best-score bornée : frontière itérative, score * edge_weight * IMPACT_DEPTH_DECAY, plancher, MAX_IMPACT_NODES=500. Deux moteurs (SQL SQLite vs networkx). Algorithme de propagation d'impact d'un changement."},
    {"path": f"{CRG_BASE}/code_review_graph/analysis.py", "type": "code", "reuse": "medium",
     "key_symbols": ["find_surprising_connections", "find_hub_nodes", "find_bridge_nodes"],
     "description": "Détection de couplage architectural surprenant : scoring d'edges anormaux (cross-community +0.3, cross-language +0.2, peripheral-to-hub +0.2). Utile pour générer des findings dépendance suspecte."},
    {"path": f"{CRG_BASE}/code_review_graph/eval/scorer.py", "type": "code", "reuse": "medium",
     "key_symbols": ["compute_precision_recall", "compute_mrr", "compute_token_efficiency"],
     "description": "Métriques d'évaluation d'un Judge/retrieval (P/R/F1, MRR, token efficiency) + méthodo de benchmark (différencier upper-bound circulaire et métrique honnête). Pour mesurer la qualité du nœud Judge sur un corpus."},
    # --- Patterns de structuration de review (P6) ---
    {"path": f"{CRG_BASE}/skills/review-pr/SKILL.md", "type": "skill", "reuse": "high",
     "key_symbols": ["Risk Assessment", "File-by-File Review", "Missing Tests", "Recommendations", "findings grouped by risk level"],
     "description": "Skill workflow de review PR. Squelette de format de sortie du Judge (findings structurés par risk level + recommendation finale). Pattern GO/NO-GO dans prompts.py::pre_merge_check_prompt."},
    {"path": f"{CRG_BASE}/skills/review-changes/SKILL.md", "type": "skill", "reuse": "high",
     "key_symbols": ["findings grouped by risk level", "high/medium/low"],
     "description": "Skill workflow de review de changes. Pattern de regroupement des findings par niveau de risque."},
    {"path": f"{CRG_BASE}/docs/LEGAL.md", "type": "doc", "reuse": "high",
     "key_symbols": ["MIT", "zero telemetry", "all local"],
     "description": "Confirmation : MIT, zero telemetry, tout local. Autorise citation/adaptation libre des prompts et algorithmes."},
]


# ---------------------------------------------------------------------------
# 21 — davidondrej-skills : hooks denylist anti-crash (P8) + doctrine authoring (P10)
# ---------------------------------------------------------------------------
DD_BASE = "references/davidondrej-skills"
DD_FILES = [
    # --- P8 Middlewares anti-crash (denylist) ---
    {"path": f"{DD_BASE}/hooks/dangerous-patterns.txt", "type": "spec", "reuse": "high",
     "key_symbols": ["27 regex POSIX-ERE", "9 categories", "rm -rf /", "fork bomb", "curl|sh", "git push --force", "gh repo delete", "gh auth token", "git reflog expire"],
     "description": "Denylist de 27 regex POSIX-ERE (une par ligne ; commentaires # et lignes vides ignorés ; 52 lignes au total dont 15 commentaires + 10 vides). Commandes bash destructrices : rm -rf //~, --no-preserve-root, dd of=/dev/, mkfs, sudo rm, fork bomb, curl|sh, git push --force, chmod 777 /, gh repo/release/secret/ssh-key delete, gh auth token. Réutilisable tel quel (transpiler [:space:]→\\s pour Python re)."},
    {"path": f"{DD_BASE}/hooks/deny-dangerous.sh", "type": "code", "reuse": "high",
     "key_symbols": ["jq extract command", "grep -qE", "fail-open", "exitcode mode", "cursor JSON mode"],
     "description": "Moteur de garde PreToolUse. jq extrait la commande (.tool_input.command / .toolInput.command / .command), boucle while read + grep -qE. Fail-open si jq absent ou patterns manquants. Modes exitcode (exit 2 + stderr) ou cursor (JSON permission:deny stdout). Message explicite citant le pattern matché."},
    {"path": f"{DD_BASE}/hooks/test-guard.sh", "type": "test", "reuse": "high",
     "key_symbols": ["~115 cas (block + allow)", "deux shapes payload", "rm -rf node_modules allow", "git push --force-with-lease allow"],
     "description": "Suite de tests (~115 cas au total : ~75 block + ~40 allow) sur les deux shapes de payload (Claude/Codex exit-code + Cursor JSON). Couvre tous les patterns + faux positifs (rm -rf node_modules doit passer). À porter en tests pytest paramétrés."},
    {"path": f"{DD_BASE}/skills/ops-and-setup/global-agent-guardrails/SKILL.md", "type": "skill", "reuse": "medium",
     "key_symbols": ["block catastrophic-only", "allow recoverable", "wiring par agent (9)", "Codex hash-pinning", "Cursor failClosed=false"],
     "description": "Doctrine companion de la denylist : block only irreversible/catastrophic commands, allow local-destructive-but-recoverable. Table de wiring par agent (9 agents). Recette E2E de vérification. Contient les gotchas (classes de faux positifs)."},
    # --- P10 Doctrine authoring ---
    {"path": f"{DD_BASE}/skills/skill-authoring/effective-agent-skills/SKILL.md", "type": "skill", "reuse": "medium",
     "key_symbols": ["progressive disclosure", "anatomy SKILL.md", "Pattern A capability primitives", "Pattern B process primitives", "anti-patterns", "ship/security checklist"],
     "description": "Doctrine d'authoring de skills (13 sections). Pattern A (capability primitives / wrappers CLI) vs Pattern B (process primitives / disciplines). Référence P10 (cf. fiche 23 fusion doctrine avec awesome-claude-skills + mattpocock)."},
    # --- P3 connexe (stop condition) ---
    {"path": f"{DD_BASE}/skills/agent-orchestration/goal-loop/SKILL.md", "type": "skill", "reuse": "medium",
     "key_symbols": ["5-part contract", "pursuing/paused/achieved/unmet/budget-limited", "anti-reward-hacking"],
     "description": "Doctrine de boucle auto-contrôlée avec stop condition vérifiable. 5-part contract : Objective / Constraints / Validation command / Stop condition / Documentation. Interdiction explicite du reward-hacking (Do not delete, skip, weaken tests)."},
]


# ---------------------------------------------------------------------------
# 22 — llm-council : pattern council anonymisé pour le Judge (P6)
# ---------------------------------------------------------------------------
LC_BASE = "references/llm-council"
LC_FILES = [
    # --- Pattern council anonymisé (P6 Judge) ---
    {"path": f"{LC_BASE}/backend/council.py", "type": "code", "reuse": "medium",
     "key_symbols": ["stage1_collect_responses", "stage2_collect_rankings", "stage3_synthesize_final", "run_full_council", "label_to_model", "parse_ranking_from_text", "calculate_aggregate_rankings"],
     "description": "Cœur du pattern council anonymisé (~250 L). Pipeline 3 stages : first opinions en parallèle → review/rank avec anonymisation A/B/C (labels neutres chr(65+i) + mapping réversible label_to_model jamais envoyé aux juges) + prompt strict FINAL RANKING: → Chairman compile. Agrégation Borda par position moyenne. Réutiliser le pattern d'anonymisation comme option d'enrichissement du Judge (coût 2N+1 appels)."},
    {"path": f"{LC_BASE}/backend/openrouter.py", "type": "code", "reuse": "high",
     "key_symbols": ["query_model", "query_models_parallel", "asyncio.gather", "degrade gracieuse"],
     "description": "Parallélisation multi-LLM via asyncio.gather + httpx.AsyncClient. Dégénérescence gracieuse (None si échec, on continue). ~80 L. Réutiliser comme patron mais branché sur le client LLM local (DSPy/smolagents), pas OpenRouter."},
    {"path": f"{LC_BASE}/backend/config.py", "type": "code", "reuse": "low",
     "key_symbols": ["COUNCIL_MODELS", "CHAIRMAN_MODEL", "OPENROUTER_API_URL"],
     "description": "Config minimale hardcoded (4 modèles council + 1 chairman Gemini). Patron à remplacer par une config dynamique de nos modèles locaux."},
    {"path": f"{LC_BASE}/backend/main.py", "type": "code", "reuse": "low",
     "key_symbols": ["send_message", "send_message_stream", "streaming SSE stage-par-stage"],
     "description": "Endpoints FastAPI + streaming SSE stage-par-stage (stage1_start→stage1_complete...). Patron de progression utile pour un Judge long."},
]


# ---------------------------------------------------------------------------
# 23 — mattpocock-skills : doctrine authoring P10 (fusion) + engineering skills (P6/P0)
# ---------------------------------------------------------------------------
MP_BASE = "references/mattpocock-skills"
MP_FILES = [
    # --- P10 Doctrine authoring (pivot de la fusion) ---
    {"path": f"{MP_BASE}/skills/productivity/writing-great-skills/SKILL.md", "type": "skill", "reuse": "high",
     "key_symbols": ["Predictability", "context load vs cognitive load", "model-invoked vs user-invoked", "router skill", "information hierarchy 3 rungs", "progressive disclosure", "context pointer", "leading word", "completion criterion", "post-completion steps", "single source of truth", "negation elephant"],
     "description": "LE FICHIER P10. Doctrine d'authoring la plus aboutie des 3 refs (awesome-claude-skills + davidondrej + mattpocock). Racine = Predictability ; deux charges (cognitive/context) ; hiérarchie 3 rungs (in-skill step / in-skill reference / external reference) ; 5 failure modes (premature completion, duplication, sediment, sprawl, no-op, negation). Concepts agnostiques du runtime, applicables à nos skills smolagents."},
    {"path": f"{MP_BASE}/docs/productivity/writing-great-skills.md", "type": "doc", "reuse": "high",
     "key_symbols": ["GLOSSARY", "Predictability", "leading word", "completion criterion"],
     "description": "Doc longue miroir de writing-great-skills + GLOSSARY.md (202 L). Armature conceptuelle de la fiche doctrine P10 fusionnée."},
    {"path": f"{MP_BASE}/scripts/list-skills.sh", "type": "code", "reuse": "high",
     "key_symbols": ["find -name SKILL.md", "filtre node_modules"],
     "description": "Discovery des skills par convention SKILL.md (7 L). Mécanique de registry implicite. Patron simple de discovery (complémentaire de init_skill.py/quick_validate.py de awesome-claude-skills)."},
    {"path": f"{MP_BASE}/scripts/link-skills.sh", "type": "code", "reuse": "medium",
     "key_symbols": ["symlink ~/.claude/skills", "exclusion deprecated/", "détection symlink circulaire"],
     "description": "Installe chaque skill comme symlink dans 2 harness dirs (57 L), git pull suffit pour MAJ. Détection de symlink circulaire. Spécifique Unix/Claude — concept utile à adapter."},
    {"path": f"{MP_BASE}/.agents/adr/0001-explicit-setup-pointer-only-for-hard-dependencies.md", "type": "doc", "reuse": "high",
     "key_symbols": ["hard-dependency vs soft-dependency", "setup pointer", "fail-loud vs degrade-gracefully"],
     "description": "Décision : seuls les skills à dépendance dure pointent vers setup ; les skills à dépendance molle dégradent gracieusement. Pattern architectural fail-loud vs degrade-gracefully (notre Context7/devtools font déjà du degrade-gracefully)."},
    {"path": f"{MP_BASE}/.agents/adr/0002-ship-as-a-claude-code-plugin.md", "type": "doc", "reuse": "medium",
     "key_symbols": ["plugin manifest array vs path string", "marketplace mono-plugin", "Codex cache symlinks"],
     "description": "Décision packaging multi-harness. Leçon de distribution (plugin Claude array explicite vs path string Codex unique)."},
    # --- P6 Judge / review ---
    {"path": f"{MP_BASE}/skills/engineering/code-review/SKILL.md", "type": "skill", "reuse": "high",
     "key_symbols": ["two axes Standards/Spec", "parallel sub-agents", "Fowler smell baseline 12", "git diff fixed-point...HEAD", "merge-base three-dot", "hard violation vs judgement call"],
     "description": "Review du diff depuis un point fixe sur 2 axes en sub-agents parallèles (jamais fusionnés ni re-rankés). Standards = conventions repo + base Fowler ; Spec = conformité issue/PRD. Pattern de judge agent à deux axes (Standards → lint/coding-standards, Spec → conformité PRD)."},
    {"path": f"{MP_BASE}/skills/engineering/tdd/SKILL.md", "type": "skill", "reuse": "high",
     "key_symbols": ["red → green", "seam (Michael Feathers)", "pre-agreed seams", "tracer bullet", "vertical slices vs horizontal slicing", "tautological test", "implementation-coupled"],
     "description": "Boucle red-green en vertical slices (1 test → 1 impl → repeat), tests seulement aux seams pré-agréés, refactoring hors-boucle (délégué à code-review). 3 anti-patterns nommés. Doctrine TDD pour le nœud Tester."},
    # --- P0 Spécialisation (debug) ---
    {"path": f"{MP_BASE}/skills/engineering/diagnosing-bugs/SKILL.md", "type": "skill", "reuse": "medium",
     "key_symbols": ["tight feedback loop", "red-capable", "minimise", "falsifiable hypothesis (3-5 ranked)", "DEBUG tagging", "bisection harness"],
     "description": "6 phases : loop tight qui passe au rouge → reproduire/minimiser → 3-5 hypothèses falsifiables → instrumenter (1 var/time) → fix + regression test → cleanup. Doctrine de diagnostic pour le nœud Tester/Escalation."},
]


# ---------------------------------------------------------------------------
# 24 — pi : compaction, branch summarization, vitest-evals (P9/P6)
# ---------------------------------------------------------------------------
PI_BASE = "references/pi"
PI_FILES = [
    {"path": f"{PI_BASE}/packages/coding-agent/src/core/compaction/compaction.ts", "type": "code", "reuse": "high",
     "key_symbols": ["compact", "extractFileOperations"],
     "description": "Compaction du contexte basée sur les fichiers lus/écrits au lieu de la troncature brute. Blueprint parfait pour P9 (compaction DuckDB)."},
    {"path": f"{PI_BASE}/packages/coding-agent/src/core/compaction/branch-summarization.ts", "type": "code", "reuse": "high",
     "key_symbols": ["BranchSummaryResult", "collectEntriesForBranchSummary"],
     "description": "Algorithme résumant une branche abandonnée lors d'un 'undo', préservant l'apprentissage (P9)."},
    {"path": f"{PI_BASE}/packages/evals/src/vitest-evals/harness-table.ts", "type": "code", "reuse": "high",
     "key_symbols": ["createJudge", "TargetTaskJudge"],
     "description": "Implémentation de LLM-as-a-judge dans vitest (P6 Judge / TDD)."},
    {"path": f"{PI_BASE}/packages/coding-agent/src/core/bash-executor.ts", "type": "code", "reuse": "medium",
     "key_symbols": ["executeBashWithOperations"],
     "description": "Abstraction de l'exécution Bash pour sandbox LLM (P8)."},
    {"path": f"{PI_BASE}/packages/coding-agent/src/core/extensions/types.ts", "type": "spec", "reuse": "medium",
     "key_symbols": ["ExtensionRunner", "ToolExecutionStartEvent"],
     "description": "Système d'intercepteurs événementiels (middlewares) avant/après appel d'outil (P8 anti-crash)."},
    {"path": f"{PI_BASE}/packages/coding-agent/src/core/skills.ts", "type": "code", "reuse": "medium",
     "key_symbols": ["formatSkillsForPrompt", "Skill"],
     "description": "Chargement des skills YAML+Markdown pour injection dans le System Prompt (P10)."},
    {"path": f"{PI_BASE}/packages/agent/src/proxy.ts", "type": "code", "reuse": "medium",
     "key_symbols": ["ProxyMessageEventStream"],
     "description": "API pour streamer raisonnement et toolcalls, base pour event bus JSON (P11)."},
]

def main() -> None:
    data = json.loads(INVENTORY.read_text(encoding="utf-8"))

    data["projects_audited"] = 24
    data["audit_date"] = "2026-08-05"

    updated = []
    seen_ids = set()
    for project in data["projects"]:
        pid = project.get("id")
        if pid == "qm":
            project = {
                "id": "qm", "name": "qm", "path": "references/qm",
                "category": "agent-harness",
                "reuse_rating": "high",
                "summary": "Plateforme d'agent multi-joueur (Slack/Web) headless, multi-harness, persistance Postgres. TS/Node mais logique algorithmique largement portable : compaction de contexte duale (synchrone+async), mémoire durable deux-tiers avec LLM-juge de consolidation (UPDATE/DELETE/ADD), idempotency store, queue de runs avec leases typés, budgets USD. Probablement la référence la plus riche en algorithmes portables du dossier.",
                "files": QM_FILES,
            }
        elif pid == "claude-code-unified-agents":
            project = {
                "id": "claude-code-unified-agents", "name": "claude-code-unified-agents",
                "path": "references/claude-code-unified-agents",
                "category": "agent-prompts",
                "reuse_rating": "medium",
                "summary": "Collection de 53 (et non 54) agents Claude Code spécialisés. Valeur concentrée dans ~8 prompts purs (49-185 lignes) alignés avec les rôles Router/Architect/Coder/Tester/Judge/Security : python-pro, code-reviewer, security-auditor, test-engineer, frontend-specialist, backend-architect, orchestrator. Les autres fichiers sont du code TS non portable (code trophy). 4 agents promis absents du dépôt.",
                "files": CC_FILES,
            }
        elif pid == "learn-claude-code":
            project = {
                "id": "learn-claude-code", "name": "learn-claude-code",
                "path": "references/learn-claude-code",
                "category": "harness-engineering",
                "reuse_rating": "high",
                "summary": "Cours didactique en 20 leçons qui déconstruit Claude Code en harness engineering. PYTHON NATIF (contrairement à qm) : patterns portables quasi littéralement. Couvre P8 (hooks s04 + error recovery s11), P9 (compaction s08), P10 (skill loading s07), P11 (event stream via hooks), P6 (task DAG s12 + todo s05), P0 (subagent s06). Lacunes assumées : P3 anti-loop (crush), P6 Judge/DuckDB (open-swe), P8-bis sandbox stricte (qm).",
                "files": LCC_FILES,
            }
        elif pid == "system-prompts-and-models-of-ai-tools":
            project = {
                "id": "system-prompts-and-models-of-ai-tools",
                "name": "system-prompts-and-models-of-ai-tools",
                "path": "references/system-prompts-and-models-of-ai-tools",
                "category": "system-prompts",
                "reuse_rating": "high",
                "summary": "Collection de system prompts extraits/leakés d'outils IA commerciaux + open-source (32 dossiers, 83 txt + 17 json). Bibliothèque de patterns pour les system_prompts du projet. ~15 prompts d'agents de coding exploitables (Codex CLI, Manus, Augment, Claude Code 2.0, Gemini CLI, Devin, Cursor, Cline). 10 invariants universels identifiés (read-before-write, pas whole-file rewrite, test-first, approval gating, anti-boucle...). Réserves : biais JS/TS/React (80%), prompts leakés (préférer open-source pour citation verbatim), padding dans les gros fichiers.",
                "files": SP_FILES,
            }
        elif pid == "awesome-claude-skills":
            project = {
                "id": "awesome-claude-skills", "name": "awesome-claude-skills",
                "path": "references/awesome-claude-skills",
                "category": "skills",
                "reuse_rating": "medium",
                "summary": "Marketplace officielle Claude de skills (ComposioHQ). 30 skills top-level + 832 composio-skills SaaS. Valeur = patrimoine méthodologique, pas le contenu métier (25/30 skills sont business/marketing). Pivot : skill-creator (modèle 3-niveaux Progressive Disclosure = caution externe de P10) + init_skill.py/quick_validate.py (outillage) + mcp-builder (manuel MCP). Gap identifié : nos skills sont mono-fichiers (pas de scripts/references/assets) et chargées eager — P10 corrige ça.",
                "files": ACS_FILES,
            }
        elif pid == "loopx":
            project = {
                "id": "loopx", "name": "loopx",
                "path": "references/loopx",
                "category": "agent-control-plane",
                "reuse_rating": "high",
                "summary": "Local control plane pour agents longue durée (github.com/huangruiteng/loopx, MIT, ~2757 PRs). Python stdlib pure, zéro dépendance runtime. Couvre 3 priorités indépendantes : P3 anti-loop (quota comptable + stall detector déterministe + hash d'output matériel + delivery_outcome), P9 compaction (whitelist de champs par type de payload), P11 event stream (event sourcing append-only idempotent + ledger classifié 5 classes + turn transaction). Persistance JSONL+filelock (à reloger sur DuckDB). Code verbeux : extraire les algorithmes, pas copier.",
                "files": LOOPX_FILES,
            }
        elif pid == "code-review-graph":
            project = {
                "id": "code-review-graph", "name": "code-review-graph",
                "path": "references/code-review-graph",
                "category": "code-analysis-tool",
                "reuse_rating": "medium",
                "summary": "Orchestrateur local-first de graphe de connaissance structurel pour code review (Tree-sitter + networkx + SQLite + MCP). Pas un Judge LLM, mais un moteur d'analyse d'impact (blast radius) et de scoring de risque pré-review. Valeur P6 : risk score composite multi-facteurs (compute_risk_score ∈ [0,1] + buckets 0.7/0.4), tables de poids par type de relation (IMPACT_EDGE_WEIGHTS), patterns de structuration de feedback de review (skills review-pr/review-changes). MIT, zero telemetry. On transpose des modèles de scoring, pas le runtime (MCP+SQLite+Tree-sitter).",
                "files": CRG_FILES,
            }
        elif pid == "davidondrej-skills":
            project = {
                "id": "davidondrej-skills", "name": "davidondrej-skills",
                "path": "references/davidondrej-skills",
                "category": "skills",
                "reuse_rating": "medium",
                "summary": "Collection de ~49 Agent Skills (standard agentskills.io) + sous-système de hooks de sécurité cross-agent. Valeur concentrée sur P8 : denylist de 27 regex POSIX-ERE (fichier .txt portable, 9 catégories, ~115 tests block+allow) + doctrine fail-open (block catastrophic-only, allow recoverable). Enrichit notre F-38 (bash_guard.py) de patterns manquants. ⚠️ Correction : la procédure Annexe D cite '52 regex' mais c'est 52 lignes dont 27 regex effectives. Secondaire P10 : effective-agent-skills (doctrine authoring, fusion fiche 23). Aucun Python — réimplémenter le moteur en re.",
                "files": DD_FILES,
            }
        elif pid == "llm-council":
            project = {
                "id": "llm-council", "name": "llm-council",
                "path": "references/llm-council",
                "category": "llm-voting-app",
                "reuse_rating": "medium",
                "summary": "Web app locale de council LLM (ChatGPT-like multi-modèles via OpenRouter). Pattern council anonymisé pour P6 : N LLM répondent, se jugent mutuellement à l'aveugle (labels A/B/C + mapping réversible jamais envoyé aux juges), un Chairman compile (3 stages + agrégation Borda). ⚠️ Réserves majeures : 99% vibe-coded, non testé, coût 2N+1 appels LLM (incompatible GPU local systématique), couplage OpenRouter payant, persistance JSON plat. À traiter comme inspiration/pseudocode, pas comme dépendance. Réutiliser le pattern d'anonymisation uniquement pour valider des findings à enjeu.",
                "files": LC_FILES,
            }
        elif pid == "mattpocock-skills":
            project = {
                "id": "mattpocock-skills", "name": "mattpocock-skills",
                "path": "references/mattpocock-skills",
                "category": "skills",
                "reuse_rating": "high",
                "summary": "Collection de ~41 skills agent (Matt Pocock, 'Skills For Real Engineers') + doctrine d'authoring formelle. Pivot de la fusion doctrine P10 (avec awesome-claude-skills 18 + davidondrej 21) : writing-great-skills/SKILL.md formalise une théorie (Predictability racine, deux charges cognitive/context, hiérarchie 3 rungs, 5 failure modes, leading words). Secondaire P6 : code-review (two axes en sub-agents parallèles) + tdd (vertical slices). Tout est Markdown+YAML+bash (zéro Python) ; philosophie small/composable/any-model à nuancer vs notre orchestrateur stateful. Exemples TS-biaisés.",
                "files": MP_FILES,
            }
        elif pid == "pi":
            project = {
                "id": "pi", "name": "pi",
                "path": "references/pi",
                "category": "agent-framework",
                "reuse_rating": "high",
                "summary": "Agent stateful interactif (monorepo TS). Brillante implémentation de compaction de contexte basée sur l'état des fichiers (P9) et de branch summarization pour l'undo. Système LLM-as-a-judge (vitest-evals) validant P6. Modèles clairs d'intercepteurs événementiels (P8) et de stream (P11). Fort couplage TS/Node à ignorer pour s'inspirer de l'architecture.",
                "files": PI_FILES,
            }
        updated.append(project)
        seen_ids.add(pid)

    # Sécurité : si qm/claude-code/learn-claude-code/system-prompts/awesome-claude-skills n'étaient pas déjà présents, on les ajoute.
    if "qm" not in seen_ids:
        updated.append({"id": "qm", "name": "qm", "path": "references/qm",
                        "category": "agent-harness", "reuse_rating": "high",
                        "summary": "(ajouté par update_inventory.py)", "files": QM_FILES})
    if "claude-code-unified-agents" not in seen_ids:
        updated.append({"id": "claude-code-unified-agents", "name": "claude-code-unified-agents",
                        "path": "references/claude-code-unified-agents", "category": "agent-prompts",
                        "reuse_rating": "medium", "summary": "(ajouté par update_inventory.py)",
                        "files": CC_FILES})
    if "learn-claude-code" not in seen_ids:
        updated.append({"id": "learn-claude-code", "name": "learn-claude-code",
                        "path": "references/learn-claude-code",
                        "category": "harness-engineering", "reuse_rating": "high",
                        "summary": "(ajouté par update_inventory.py)", "files": LCC_FILES})
    if "system-prompts-and-models-of-ai-tools" not in seen_ids:
        updated.append({"id": "system-prompts-and-models-of-ai-tools",
                        "name": "system-prompts-and-models-of-ai-tools",
                        "path": "references/system-prompts-and-models-of-ai-tools",
                        "category": "system-prompts", "reuse_rating": "high",
                        "summary": "(ajouté par update_inventory.py)", "files": SP_FILES})
    if "awesome-claude-skills" not in seen_ids:
        updated.append({"id": "awesome-claude-skills", "name": "awesome-claude-skills",
                        "path": "references/awesome-claude-skills",
                        "category": "skills", "reuse_rating": "medium",
                        "summary": "(ajouté par update_inventory.py)", "files": ACS_FILES})
    if "loopx" not in seen_ids:
        updated.append({"id": "loopx", "name": "loopx",
                        "path": "references/loopx",
                        "category": "agent-control-plane", "reuse_rating": "high",
                        "summary": "(ajouté par update_inventory.py)", "files": LOOPX_FILES})
    if "code-review-graph" not in seen_ids:
        updated.append({"id": "code-review-graph", "name": "code-review-graph",
                        "path": "references/code-review-graph",
                        "category": "code-analysis-tool", "reuse_rating": "medium",
                        "summary": "(ajouté par update_inventory.py)", "files": CRG_FILES})
    if "davidondrej-skills" not in seen_ids:
        updated.append({"id": "davidondrej-skills", "name": "davidondrej-skills",
                        "path": "references/davidondrej-skills",
                        "category": "skills", "reuse_rating": "medium",
                        "summary": "(ajouté par update_inventory.py)", "files": DD_FILES})
    if "llm-council" not in seen_ids:
        updated.append({"id": "llm-council", "name": "llm-council",
                        "path": "references/llm-council",
                        "category": "llm-voting-app", "reuse_rating": "medium",
                        "summary": "(ajouté par update_inventory.py)", "files": LC_FILES})
    if "mattpocock-skills" not in seen_ids:
        updated.append({"id": "mattpocock-skills", "name": "mattpocock-skills",
                        "path": "references/mattpocock-skills",
                        "category": "skills", "reuse_rating": "high",
                        "summary": "(ajouté par update_inventory.py)", "files": MP_FILES})
    if "pi" not in seen_ids:
        updated.append({"id": "pi", "name": "pi",
                        "path": "references/pi",
                        "category": "agent-framework", "reuse_rating": "high",
                        "summary": "(ajouté par update_inventory.py)", "files": PI_FILES})

    data["projects"] = updated

    INVENTORY.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    total = sum(len(p["files"]) for p in data["projects"])
    by_reuse = {}
    for p in data["projects"]:
        for f in p["files"]:
            r = f.get("reuse", "?")
            by_reuse[r] = by_reuse.get(r, 0) + 1
    print(f"OK — {len(data['projects'])} projets, {total} entrées au total.")
    print(f"Répartition : {by_reuse}")
    for new_id in ("loopx", "code-review-graph", "davidondrej-skills", "llm-council", "mattpocock-skills", "pi"):
        proj = next(p for p in data["projects"] if p["id"] == new_id)
        print(f"  {new_id} : {len(proj['files'])} entrées (reuse_rating={proj['reuse_rating']})")


if __name__ == "__main__":
    main()
