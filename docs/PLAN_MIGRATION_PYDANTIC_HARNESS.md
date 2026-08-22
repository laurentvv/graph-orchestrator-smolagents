# Plan d'intégration pydantic-ai-harness — inventaire complet (F-157, phases 3 → 6)

> Découlé de `docs/PYDANTIC_AI_HARNESS_DOC_NOTES.md` (lecture obligatoire de la doc
> officielle, 262 pages locales) et de `docs/ANALYSE_MIGRATION_HARNESS_CODAGE.md`
> (analyse + spike GO, PR #106). Ce plan couvre **tout ce que le harness rend
> possible** : remplacements de l'existant, améliorations, et **features que l'usine
> n'a pas encore**. Prérequis : merge de la PR #106 (spike + dépendance pinée).
>
> Légende statut : **R** = remplacement d'un équivalent smolagents existant ·
> **A** = amélioration d'un mécanisme maison (le harness le fait mieux/structurellement) ·
> **N** = NOUVEAU (l'usine ne l'a pas). Effort : S (<0,5 j) · M (0,5-2 j) · L (>2 j).

---

## Phase 3 — Nœuds qui codent : Coder + Web Tester (P0, directement après merge #106)

> **Périmètre = TOUS les nœuds qui codent** : `execute_coder_node` (Coder) ET
> `execute_tester_node` → `testers/web_tester.py` (Web Tester) — les deux seuls nœuds
> à boucle agentique smolagents. Hors périmètre (rien à migrer) : Static Tester et
> Linter (déterministes, zéro LLM), nœuds de raisonnement (DSPy : Router, Refiner,
> Architect, Drafter, Security, Judge, Escalation), `agent_server` (nettoyage final
> phase 6). Séquence interne : parité Coder (3.1→3.5) → vision/multimodal, prérequis
> Tester (3.6) → migration Web Tester (3.7), qui hérite de tout le travail précédent
> (stack partagé : modèle loggé, callback screenshots, MCP DevTools + Puppeteer).

Objectif : un `execute_coder_node` pydantic **paritaire ou supérieur** au smolagents
d'aujourd'hui, puis un `execute_tester_node` migré sur le même socle, validés par
`debug/run_coder_pydantic.py` A/B, `debug/run_tester.py` puis E2E Bubble Sort.

### 3.1 Outils fichiers

| Item | Statut | Contenu | Doc | Effort |
|---|---|---|---|---|
| FileSystem 8 tools | R | `read_file`/`write_file`/`edit_file`/`list_directory`/`search_files`/`find_files`/`create_directory`/`file_info` remplacent les `@tool` de tools.py | [FileSystem](https://pydantic.dev/docs/ai/harness/filesystem/) | S (déjà spike) |
| `multi_replace`/`search_replace`/`append_file` | R | Pas d'équivalent natif → custom `@agent.tool` (logique tools.py portable) | [Function tools](https://pydantic.dev/docs/ai/tools-toolsets/tools/) | S |
| `check_js_syntax`/`read_python_skeleton` | R | Custom tools (corps inchangés) | idem | S |
| `log_event` (DuckDB) | R | Custom tool (run_id courant via `RunContext.deps` — mieux qu'aujourd'hui : deps typées) | [Dependencies](https://pydantic.dev/docs/ai/core-concepts/dependencies/) | S |
| `expected_hash` concurrence optimiste | A | Le hash rendu par `read_file` protège write/edit des écritures périmées — renforce le ReadGate F-67 (jamais branché) SANS garde dédiée ; instruire le modèle via PROTOCOL | [FileSystem](https://pydantic.dev/docs/ai/harness/filesystem/) | S |
| io_guard (allowlist chemins) | A | `allowed/denied/protected_patterns` structurels (`.env`, clés protégés par défaut) | idem | S |
| Erreurs corrigibles → ModelRetry | A | Taxonomie officielle missing-file/stale-edit/denied-path → auto-correction au lieu d'abort | idem | — |

### 3.2 Prompt, sortie, skills

| Item | Statut | Contenu | Doc | Effort |
|---|---|---|---|---|
| `output_type=CoderOutput` | R | Sortie validée nativement (retries inclus) — **supprime `extract_and_validate` + sauvetage DSPy** (models.py:251-339) | [Output](https://pydantic.dev/docs/ai/core-concepts/output/) | M |
| instructions ROLE_BLOCKS + invariants | R | `instructions=` + capability [Reinject System Prompt](https://pydantic.dev/docs/ai/capabilities/reinject-system-prompt/) (survit aux compactions) | [Agent](https://pydantic.dev/docs/ai/core-concepts/agent/) | S |
| Skills (F-57 eager/lazy) | R | Capability `Skills(skills/)` : notre format SKILL.md agentskills.io est déjà conforme ; lazy via `load_capability` ≡ `load_skill` ; extra `[skills]` pour le frontmatter YAML | [Skills](https://pydantic.dev/docs/ai/harness/skills/) | M |
| AGENTS.md composant (F-59) | R | Capability `RepoContext` (fichiers d'instructions + structure + skills + hooks du repo) | [Repo Context](https://pydantic.dev/docs/ai/harness/repo-context/) | S |
| Mode CORRECTION (it.>1, F-82 cap critères) | R | Notre logique workflow inchangée ; `PrepareTools` permet en plus d'ajuster les tools PAR requête (ex. retirer write en relecture) | [PrepareTools](https://pydantic.dev/docs/ai/capabilities/prepare-tools/) | M |

### 3.3 Gardes & contrôle (portage + vols référents §5.4 analyse)

| Item | Statut | Contenu | Doc | Effort |
|---|---|---|---|---|
| LoopGuard v2 | A | Hook `after_node_run` + signature SHA-256 (tool+args+**résultat**, fenêtre 10/seuil 5 — vol crush) + **nudge `[3,5,8]` à canonisation d'args** (vol deepseek) AVANT hard-stop via SystemReminders dynamique | [Hooks](https://pydantic.dev/docs/ai/core-concepts/hooks/) | M |
| StallDetector | R | Hook node (hash du livrable matériel — logique maison portable) | idem | S |
| GoalEnforcer | A | `GoalReanchor` intégré (ré-ancre le 1er user prompt à chaque requête, zéro LLM) + notre verify-after-proof en hook `before_node_run`/wrap | [System Reminders](https://pydantic.dev/docs/ai/harness/system-reminders/) | M |
| ~10 nudges (F-114/125/129/130/131/138) | A | **SystemReminders dynamiques** `(RunContext) -> str|None` — injection en queue derrière CachePoint : ne pollue PLUS l'historique (aujourd'hui `memory_step.observations` s'accumule), préserve le cache llama-server | idem | M |
| Idle breaker / retry loop F-104 | A | Carte officielle des 5 couches de retry (transport→fallback→tool→output→run) ; `AsyncHTTPX2TenacityTransport` pour le transport ; `revive()` llama-server → hook `on_model_request_error` | [Retries](https://pydantic.dev/docs/ai/core-concepts/retries/) | M |
| UsageLimits | R | `request_limit`/`tool_calls_limit`/`total_tokens_limit` ≡ max_steps 40 + bornes | [API](https://pydantic.dev/docs/ai/api/pydantic-ai/usage/) | S |

### 3.4 Contexte & mémoire

| Item | Statut | Contenu | Doc | Effort |
|---|---|---|---|---|
| CompactingCodeAgent (F-116) | R | **TieredCompaction** (escalade zéro-LLM→summarization) + ClearToolResults + ToolOutputLimits + WarnNearLimits | [Compaction](https://pydantic.dev/docs/ai/harness/compaction/) | M |
| Purge images perte-zéro | R | Custom `ProcessHistory` (remplacer les parts par objets neufs — jamais muter in place) | [Process History](https://pydantic.dev/docs/ai/capabilities/process-history/) | M |
| Relectures stériles (F-130) | A | **`DeduplicateFileReads`** structurel (quasi sans perte, chaque requête) — remplace le nudge par une élimination | idem | — |
| Gros outputs (budget F-138) | A | ClampOversizedMessages par part + ToolOutputLimits (truncate/spill-to-file/summarize) | [Tool Output Limits](https://pydantic.dev/docs/ai/harness/tool-output-limits/) | S |
| llm_compact_history | R | SummarizingCompaction (le même modèle ou un modèle moins cher) | idem | S |
| Checkpoint 8 sections KV-warm (vol deepseek) | N | Prompt de summarization structuré + replay du préfixe exact → **réutilise `--cache-reuse`** llama-server | [Compaction](https://pydantic.dev/docs/ai/harness/compaction/) | M |

### 3.5 MCP & web

| Item | Statut | Contenu | Doc | Effort |
|---|---|---|---|---|
| chrome-devtools-mcp (F-50/90) | R | `MCP` capability / `MCPToolset` (script stdio Node) — **supprime ToolCollection + le patch mcpadapt** | [MCP](https://pydantic.dev/docs/ai/capabilities/mcp/) | M |
| 12 helpers DOM JS (F-72) | R | Custom toolset (corps JS portables), préfixés via `PrefixTools` | [Toolsets](https://pydantic.dev/docs/ai/tools-toolsets/toolsets/) | M |
| Console enrichie (F-126) | R | Transformation per-tool (client fastmcp) ou wrapper toolset | [MCP client](https://pydantic.dev/docs/ai/mcp/client/) | M |
| Context7 | R | `MCP` capability | idem | S |
| DuckDuckGoSearchTool | R | Capability `WebSearch` (fallback DDG local documenté) | [Web Search](https://pydantic.dev/docs/ai/capabilities/web-search/) | S |

### 3.6 Vision & multimodal (prérequis Web Tester)

| Item | Statut | Contenu | Doc | Effort |
|---|---|---|---|---|
| Vision Coder (screenshots → contexte) | R | Screenshots MCP DevTools comme retours multimodaux d'outils (prouvé CodeMode « multimodal final expressions » ; à valider sur tools natifs) | [Multimodal Input](https://pydantic.dev/docs/ai/core-concepts/input/) | M |
| Boucle screenshots (F-50) | R | Strippage `filePath` etc. → transformation per-tool fastmcp ou wrapper toolset (plus de sous-classage `Tool`) | [MCP client](https://pydantic.dev/docs/ai/mcp/client/) | M |

### 3.7 Web Tester (`testers/web_tester.py`)

| Item | Statut | Contenu | Doc | Effort |
|---|---|---|---|---|
| Migration du nœud | R | Même socle que le Coder (FileSystem + custom tools + gardes + compaction) + **Puppeteer MCP** via `MCP` capability (en plus de DevTools) ; prompt compacté F-152 en instructions ; `TesterOutput` en `output_type` | [Harness](https://pydantic.dev/docs/ai/harness/) | L |
| Validation | R | `debug/run_tester.py` en isolation puis E2E Bubble Sort complet (Tester+Security+Judge enchaînés) | §9 analyse | — |

---

## Phase 4 — Robustesse & outillage transverse (P1)

> Items déplacés/ex-migrateurs : tout ce qui n'est pas bloquant pour la parité des
> deux nœuds qui codent, mais qui fiabilise l'ensemble.

| Item | Statut | Contenu | Doc | Effort |
|---|---|---|---|---|
| **PlaywrightBrowser** | N | **Alternative in-process à chrome-devtools-mcp** (Chromium stateful, JS, screenshot, `auto_install_chromium`) — A/B à lancer en phase 4 pour les DEUX nœuds : moins d'IO MCP, un seul process ; DevTools garde la console enrichie | [Playwright](https://pydantic.dev/docs/ai/harness/playwright/) | M |
| Escalade Ultra (F-111) | A | **FallbackModel** (bascule automatique) ou **Select Model** (hook par requête) — remplace `_select_coder_spec` ad hoc | [Select Model](https://pydantic.dev/docs/ai/capabilities/select-model/) | M |
| WarnOnCacheBusts | N | Sentinelle d'effondrement du cache prompt (lit `usage.cache_read_tokens` normalisé) — protège l'investissement `--cache-reuse` ; ajuster `cache_ttl_seconds` | [Warn On Cache Busts](https://pydantic.dev/docs/ai/harness/warn-on-cache-busts/) | S |
| **TestModel/FunctionModel en CI** | N | Tests déterministes du câblage Coder **sans GPU ni LLM** (TestModel génère des données valides par schéma et appelle tous les tools) + `agent.override` + `ALLOW_MODEL_REQUESTS=False` anti-fuite — remplace une partie des ~5 k LOC de mocks smolagents | [Unit testing](https://pydantic.dev/docs/ai/guides/testing/) | M |
| Media Stores | N | Contenus binaires lourds (screenshots) hors historique, content-addressed, remis à la demande — généralise `.transcripts/` | [Media Stores](https://pydantic.dev/docs/ai/harness/media/) | M |

---

## Phase 5 — Nouveautés produit (P2, features qu'on n'a pas)

| Item | Contenu & valeur pour l'usine | Doc | Effort |
|---|---|---|---|
| **Planning** (N) | Plan structuré auto-entretenu avec rappel live cache-safe — le Coder suit un todo pendant les tâches longues (aujourd'hui seul le Drafter planifie, en amont) | [Planning](https://pydantic.dev/docs/ai/harness/planning/) | S |
| **Subagents** (N) | `delegate_task` à des sous-agents à historique isolé — ex. un explorer read-only pour fouiller le dossier avant écriture (réduit le contexte du Coder principal) ; épouse la philosophie fan-out du graphe | [Subagents](https://pydantic.dev/docs/ai/harness/subagents/) | M |
| **Advisor** (N) | Consultation d'un second modèle quand bloqué — **le 4B peut interroger l'Ornith-9B in-run** (outil natif provider ou fallback local pydantic) : tiering intra-nœud, nouveau | [Advisor](https://pydantic.dev/docs/ai/harness/advisor/) | M |
| **Tool Search** (N) | Catalogue différé quand >20 tools (le Coder en expose ~30) — économie de tokens de définitions | [Tool Search](https://pydantic.dev/docs/ai/capabilities/tool-search/) | S |
| **Memory** (N) | Notebooks persistants inter-runs — le Coder pourrait mémoriser les leçons par type de tâche (généralisation des post-mortem F-61) | [Memory](https://pydantic.dev/docs/ai/harness/memory/) | M |
| **Conversation Search** (N) | BM25 sur les tours compactés + runs passés — post-mortem LLM « pourquoi le run X a échoué » | [Conversation Search](https://pydantic.dev/docs/ai/harness/conversation-search/) | S |
| **Step Persistence** (N) | Snapshots continuable/forkable par boundary + suivi des side-effects outils — **reprendre un run Coder après crash** (va plus loin que revive F-104) | [Step Persistence](https://pydantic.dev/docs/ai/harness/step-persistence/) | M |
| **Guardrails** (N) | Verdicts allow/block/replace/retry/approve sur prompt entrant, tool calls, output sortant + détecteurs secrets/PII — complète le nœud Security en amont | [Guardrails](https://pydantic.dev/docs/ai/harness/guardrails/) | M |
| **Deferred Tools + HITL** (N) | Approval gating outillé (notre invariant #5 est aujourd'hui purement textuel) | [Deferred Tools](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/) | S |
| **Agent Specs YAML** (N) | Agents déclaratifs (capabilities customs enregistrables) — variantes de nœuds sans code | [Agent Specs](https://pydantic.dev/docs/ai/core-concepts/agent-spec/) | S |
| **OTel/Logfire instrumentation** (N) | Traces standard de chaque appel modèle/outil — export OTLP → pourrait nourrir DuckDB ou Logfire ; remplace une partie des métriques maison | [Instrumentation](https://pydantic.dev/docs/ai/capabilities/instrumentation/) | M |
| **ACP + to_web/to_cli** (N) | Servir le Coder à un éditeur (ACP) ou UI web/CLI — **debug manuel du nœud** sans réécrire de harnais | [ACP](https://pydantic.dev/docs/ai/harness/acp/) | S |
| Anti-loop `[3,5,8]` + hash crush (N, vols §5.4) | Intégrés au LoopGuard v2 (phase 3.3) même si migration s'arrêtait | refs/ analyse §5.4 | M |

---

## Phase 6 — Horizon (P3, à garder en vue, ne pas engager maintenant)

| Item | Pourquoi attendre | Doc |
|---|---|---|
| Durable execution (Temporal/DBOS/Prefect) | Runs E2E survivant aux restarts — pertinent quand les runs dépasseront l'heure | [Durable](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/) |
| Pydantic Evals | Formaliser la validation E2E en datasets/évals (LLM-judge intégré) — après stabilisation phase 3-4 | [Evals](https://pydantic.dev/docs/ai/evals/evals/) |
| Pydantic Graph | Moteur de graphe typé — candidat futur de workflows.py, MAIS l'orchestrateur actuel fonctionne : ne pas migrer | [Graph](https://pydantic.dev/docs/ai/graph/overview/) |
| Dynamic Workflow | Orchestrateur écrivant un script sandboxé pour coordonner des sous-agents — à réévaluer avec un gros modèle (leçon CodeMode) | [Dynamic Workflow](https://pydantic.dev/docs/ai/harness/dynamic-workflow/) |
| Runtime Capability Creation | L'agent crée des capabilities mid-run — puissant mais risqué (gated par review) | [Capability Creation](https://pydantic.dev/docs/ai/harness/capability-creation/) |
| Retrait final de smolagents | Une fois Coder + Web Tester + agent_server migrés : `uv remove smolagents` + purge des ~4 k LOC de glue (annexe A analyse) | analyse §7-S1 ph.4 |

## Non-cibles assumées

CodeMode (NO-GO 4B prouvé — réservé aux gros modèles), Browser Use (trop ouvert pour des
tests déterministes), outils natifs provider (inutiles en local), WebSearch cloud
(Exa/You.com), StackOne/LocalStack/Modal Sandbox (cloud), spend limits (GPU local =
coût fixe — revoir si endpoints distants), native provider compaction (OpenAI/Anthropic only).

## Séquence recommandée

1. **P3.1-3.2** (parité tools + output_type + skills) → A/B isolation, critères = spike
   round 3 + CoderOutput validé. 2. **P3.3-3.4** (gardes + compaction) → rejouer les
   scénarios de gel F-125/129/131 en isolation. 3. **P3.5** (MCP + helpers) → E2E Bubble
   Sort complet. 4. **P3.6-3.7** (vision + Web Tester) → `debug/run_tester.py` puis E2E.
   5. Phase 4 (PlaywrightBrowser A/B, FallbackModel, TestModel CI, Media Stores,
   WarnOnCacheBusts). 6. Phase 5 au fil de l'eau (une feature = un F-xxx + PR).
   Chaque étape : branche → isolation → E2E → PR (règle d'or Git + Kilo Review).
   smolagents n'est retiré du `pyproject.toml` qu'une fois Coder **et** Tester migrés
   (leur stack partagé fait que le second hérite du premier — d'où l'ordre).
