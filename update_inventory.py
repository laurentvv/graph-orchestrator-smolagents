"""Met à jour docs/references-audit/inventory.json pour refléter l'audit approfondi
des projets 14 (qm) et 15 (claude-code-unified-agents).

Avant : qm = 1 entrée (README), claude-code = 2 entrées (README + AGENTS_LIST).
Après  : qm = 24 entrées de code/doc, claude-code = 13 entrées de prompts.

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


def main() -> None:
    data = json.loads(INVENTORY.read_text(encoding="utf-8"))

    data["projects_audited"] = 15
    data["audit_date"] = "2026-07-31"

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
        updated.append(project)
        seen_ids.add(pid)

    # Sécurité : si qm/claude-code n'étaient pas déjà présents, on les ajoute.
    if "qm" not in seen_ids:
        updated.append({"id": "qm", "name": "qm", "path": "references/qm",
                        "category": "agent-harness", "reuse_rating": "high",
                        "summary": "(ajouté par update_inventory.py)", "files": QM_FILES})
    if "claude-code-unified-agents" not in seen_ids:
        updated.append({"id": "claude-code-unified-agents", "name": "claude-code-unified-agents",
                        "path": "references/claude-code-unified-agents", "category": "agent-prompts",
                        "reuse_rating": "medium", "summary": "(ajouté par update_inventory.py)",
                        "files": CC_FILES})

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
    qm = next(p for p in data["projects"] if p["id"] == "qm")
    cc = next(p for p in data["projects"] if p["id"] == "claude-code-unified-agents")
    print(f"  qm : {len(qm['files'])} entrées (reuse_rating={qm['reuse_rating']})")
    print(f"  claude-code-unified-agents : {len(cc['files'])} entrées (reuse_rating={cc['reuse_rating']})")


if __name__ == "__main__":
    main()
