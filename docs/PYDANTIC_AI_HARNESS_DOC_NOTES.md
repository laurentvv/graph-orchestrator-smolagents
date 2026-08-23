# Notes de lecture — Doc Pydantic AI / Harness (migration F-157)

> **Règle (AGENTS.md §5)** : la doc officielle COMPLÈTE est en local —
> `references/pydantic-ai-docs/llms-full.txt` (262 pages, markdown propre) avec
> `INDEX.md` (titre → n° de ligne ; lecture ciblée `sed -n '<début>,<fin>p' …`).
> **SI UNE PAGE DE DOC EXISTE POUR CE QUE TU CODES, LIS-LA AVANT.** Chaque page est
> aussi fetchable à jour via `https://pydantic.dev/docs/ai/<chemin>/index.md`.
> Ce document = synthèse des points importants AVEC LIENS, issue de la lecture
> F-157 (2026-08-23). Version lue : pydantic-ai-slim 2.33.0 / pydantic-ai-harness 0.24.0.

---

## 1. Provider & llama.cpp (nos modèles locaux)

- **OpenAI-compatible** : [models/openai](https://pydantic.dev/docs/ai/models/openai/) —
  `OpenAIChatModel` + `OpenAIProvider(base_url=…, api_key=…)`. Remèdes aux endpoints
  exotiques via `OpenAIModelProfile` : `openai_supports_strict_tool_definition=False`,
  `openai_chat_supports_multiple_system_messages=False` (chat template côté serveur),
  `openai_chat_supports_max_completion_tokens=False`. **Preuve spike : les 4 tests
  passent MÊME avec le profil par défaut** (llama.cpp récent accepte tout) — flags
  conservés par prudence.
- [Ollama](https://pydantic.dev/docs/ai/models/ollama/) : `OllamaModel` dédié (autre
  runtime) — pas notre cas, llama-server reste sur le chemin OpenAI-compat.
- **Fallback de modèle** : [retries](https://pydantic.dev/docs/ai/core-concepts/retries/)
  documente `FallbackModel` (même requête vers un modèle différent) — candidat pour
  l'escalade Ultra F-111 sans boucle maison.

## 2. Boucle, contrôle, retries — la carte des 5 couches

Page map : [Retries](https://pydantic.dev/docs/ai/core-concepts/retries/) — 5 couches aux
budgets INDÉPENDANTS : **Transport** (HTTP tenacity, invisible pour l'agent) → **Model
fallback** (`FallbackModel`) → **Tool** (le modèle corrige son call) → **Output validation**
→ **Run** (usage limits). Ne pas les confondre. Config : `Agent(retries=…)` accepte un int
ou `{'tools': 3, 'output': 1}` ; par run : `agent.run(retries=…)`.
[Timeouts](https://pydantic.dev/docs/ai/core-concepts/timeouts/) séparés.
- **Hooks** : [core-concepts/hooks](https://pydantic.dev/docs/ai/core-concepts/hooks/) —
  `before/after/wrap/error` × run / node (par step graph) / model_request / tool_validate /
  tool_execute / output_validate / output_process + `run_event_stream`. Les node hooks
  tirent quel que soit le mode de pilotage (`run`, `iter`, `next`). `before_model_request`
  peut MUTER `request_context.messages` (nos injections) ; `SkipModelRequest(response)`
  court-circuite l'appel ; `ModelRetry` renvoie un message de correction au modèle.
- **Pilotage pas-à-pas** : `agent.iter()` (itération de nœuds, `run.new_messages()` à
  chaque step) — utilisé tel quel dans `debug/run_coder_pydantic.py` pour le dump live.
- **Capabilities custom** : [capabilities/custom](https://pydantic.dev/docs/ai/capabilities/custom/)
  — sous-classer `AbstractCapability` (dataclass ok, hooks typés, `for_run` = isolation
  d'état par run, `defer_loading` + `id` stable = chargement à la demande). **C'est le
  pattern de portage de nos gardes** (LoopGuard, purge d'images → capabilities).
- **On-demand** : [capabilities/on-demand](https://pydantic.dev/docs/ai/capabilities/on-demand/) —
  capability réduite à une ligne de catalogue, tools cachés jusqu'à `load_capability`.

## 3. Tools & MCP

- **Function tools** : [tools](https://pydantic.dev/docs/ai/tools-toolsets/tools/) —
  `@agent.tool` (avec `RunContext`) / `@agent.tool_plain` / `tools=[…]` / `toolsets=[…]`.
  Advanced : [tools-advanced](https://pydantic.dev/docs/ai/tools-toolsets/tools-advanced/)
  (ToolSettings, retries par tool, `prepare`, exécution parallèle).
- **Toolsets** : [toolsets](https://pydantic.dev/docs/ai/tools-toolsets/toolsets/) —
  collections combinables (nos familles d'outils : fichiers / devtools / skills).
- **Deferred tools** : [deferred-tools](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/) —
  tools non envoyés au modèle jusqu'à demande (+ HITL approval).
- **MCP** : [capabilities/mcp](https://pydantic.dev/docs/ai/capabilities/mcp/) +
  [mcp/client](https://pydantic.dev/docs/ai/mcp/client/) — `MCP(url)` ou
  `MCPToolset(script_stdio)` : **accepte un script Python OU Node.js en stdio** →
  chrome-devtools-mcp se branche directement (fini `ToolCollection.from_mcp` + le patch
  mcpadapt des images). Lifecycle par `async with agent` / `async with toolset`.
  Transformation per-tool via client fastmcp (équivalent de nos wrappers vision).
  ⚠️ **Leçon F-160 (mesurée, 2026-08-23)** : sur les runs à output outil,
  pydantic-ai envoie `tool_choice='required'` par défaut — llama-server encode
  ce forçage en GRAMMAIRE GBNF d'union des tools, qui **casse au-delà de
  ~45-60 outils** (45 OK / 62 → 400 « failed to parse grammar », body capturé
  puis rejoué). Fix : `ModelSettings(tool_choice='auto')` dès que des toolsets
  MCP sont attachés (coder_pydantic.build_coder_agent) — plus de grammaire
  contrainte, le forçage comportemental reste porté par le protocole prompt +
  IdleBreaker. Les noms d'outils MCP arrivent avec leurs TIRETS d'origine
  (ex `resolve-library-id`) — mcpadapt les convertissait en underscores :
  utiliser `RenamedToolset` pour préserver les noms cités par les prompts/skills.
  ✅ **Leçon F-161 (prouvée in-process, 2026-08-23 — vision multimodale)** : les
  retours d'outils MCP `ImageContent` sont mappés NATIVEMENT en `BinaryImage`
  (`_map_mcp_tool_result`, pydantic_ai/mcp.py) — mais un `process_tool_call`
  custom qui réduit le résultat en texte écrase l'image (et un fallback naïf
  produit `str(bytes)` = bruit hexadécimal). Le retour d'un processor peut être
  la liste mixte `[str, BinaryImage]` (ToolResult valide) : le framework la
  stocke comme `ToolReturnPart` multimodal et `OpenAIChatModel` la sérialise en
  message `role=tool` (texte + « See file <id>. ») PUIS message `user` séparé
  (« This is file <id>: » + data-URI base64) — exactement le format que
  llama-server+mmproj décode. Purge des anciennes images : seam officiel
  `ProcessHistory` (reconstruire les parts en objets NEUFS — ce sont des
  dataclasses, `dataclasses.replace`, jamais de mutation in-place), cf.
  coder_pydantic_vision.py.
- **Common/Native tools** : [common-tools](https://pydantic.dev/docs/ai/tools-toolsets/common-tools/),
  [native-tools](https://pydantic.dev/docs/ai/tools-toolsets/native-tools/) (exécutés côté
  provider — inutiles en local llama.cpp).

## 4. Sortie structurée (CoderOutput)

[Output](https://pydantic.dev/docs/ai/core-concepts/output/) — par défaut via tool-calling
(validé par smoke test D) ; plusieurs output types = un output tool chacun (schémas plus
simples) ; output modes (native/instructions) configurables ; output functions = action
finale SANS renvoyer le résultat au modèle. **CoderOutput Pydantic se mappe sur
`output_type=` directement** — remplace `extract_and_validate` + sauvetage DSPy.

## 5. Mémoire, historique, contexte

- [message-history](https://pydantic.dev/docs/ai/core-concepts/message-history/) —
  `result.all_messages()/new_messages()`, `message_history=` pour continuer/forker un run ;
  patterns de history processors (trimming/summarization/rédaction).
- [ProcessHistory](https://pydantic.dev/docs/ai/capabilities/process-history/) — capability
  wrapper d'un processeur d'historique (sync/async, `RunContext` optionnel, ordre
  d'enregistrement). **Seam officiel de notre purge d'images perte-zéro** (remplacer
  les parts par des objets neufs, pas muter in place — OTel caveat documenté).
- Compaction : [harness/compaction](https://pydantic.dev/docs/ai/harness/compaction/) —
  menu zéro-LLM (sliding window, `ClearToolResults`, **`DeduplicateFileReads`** ≡ notre
  nudge F-130 mais structurel et quasi sans perte, `ClampOversizedMessages` par part) +
  `SummarizingCompaction` + **`TieredCompaction`** (escalade cheap→cher, recommandé).
  Ancrage des compteurs sur l'usage provider réel ; pairing tool_call/result garanti.
  Provider-native : [capabilities/compaction](https://pydantic.dev/docs/ai/capabilities/compaction/)
  (OpenAI/Anthropic seulement — pas nous ; le model-agnostic marche partout).
- Contexte : [tool-output-limits](https://pydantic.dev/docs/ai/harness/tool-output-limits/)
  (truncate/spill-to-file/summarize), [warn-on-cache-busts](https://pydantic.dev/docs/ai/harness/warn-on-cache-busts/)
  (observe `usage.cache_read_tokens` normalisé — sentinelle pour notre `--cache-reuse`
  llama-server), [media stores](https://pydantic.dev/docs/ai/harness/media/) (contenus
  binaires gros → stockage content-addressed hors historique), [conversation-search](https://pydantic.dev/docs/ai/harness/conversation-search/)
  (BM25 sur les tours compactés), [step-persistence](https://pydantic.dev/docs/ai/harness/step-persistence/)
  (snapshots continuable/forkable par boundary — intéressant pour nos retries F-104).

## 6. Nudges & garde-fous (l'équivalent officiel de vision_callback)

- **[SystemReminders](https://pydantic.dev/docs/ai/harness/system-reminders/)** — LE
  remplacement des ~10 nudges (F-114/125/129/130/131/138) : `Reminder(content,
  interval, first_after, trigger, max_fires, tag)` statique + **dynamic
  `(RunContext) -> str | None`** évalué à CHAQUE requête (conditions sur `ctx.run_step`,
  usage, etc.) ; `GoalReanchor` intégré (ré-ancre le 1er user prompt ≡ GoalEnforcer) ;
  injection en queue derrière **CachePoint** → jamais dans `message_history`, préfixe
  cache byte-stable. Tag `<system-reminder>` convention Claude Code.
- **[Guardrails](https://pydantic.dev/docs/ai/harness/guardrails/)** — validation du
  prompt entrant, des tool calls, de l'output sortant avec verdicts
  allow/block/replace/retry/approve, chaînes de guards, détecteurs secrets/PII.
- **[Spend limits](https://pydantic.dev/docs/ai/harness/spend/)** — budgets cross-runs
  (inutile en local GPU mais utile si endpoints distants).

## 7. Écosystème Coder (le stack officiel)

- [Coder](https://pydantic.dev/docs/ai/harness/coder/) = FileSystem + Shell + RepoContext
  + Planning + SubAgents + ClearToolResults + WarnNearLimits + ToolOutputLimits —
  démontable bloc par bloc (pas de boîte noire).
- **[FileSystem](https://pydantic.dev/docs/ai/harness/filesystem/)** — 8 tools
  path-scopés ; `read_file` rend **numéros de ligne + hash** ; `write_file`/`edit_file`
  acceptent **`expected_hash`** (concurrence optimiste ≡ ReadGate F-67 structurel) ;
  `edit_file` = remplacement exact **unique** (contrat anti-corruption) ; erreurs
  corrigibles par le modèle → `ModelRetry`, erreurs fatales → abort ; patterns
  allowed/denied/protected (`.env`, clés protégées par défaut) ≡ io_guard en structurel ;
  walkers vs accès direct documentés.
- [Shell](https://pydantic.dev/docs/ai/harness/shell/) — allowlist, env scrubbing,
  processus background gérés (garde-butoir, pas frontière de sécurité).
- [RepoContext](https://pydantic.dev/docs/ai/harness/repo-context/) — AGENTS.md/CLAUDE.md
  + structure + skills + hooks du repo.
- [Planning](https://pydantic.dev/docs/ai/harness/planning/) — plan structuré auto-entretenu,
  rappel live cache-safe (intérêt à évaluer vs notre Drafter).
- [Subagents](https://pydantic.dev/docs/ai/harness/subagents/) — `delegate_task`, historique
  isolé, catalogue dans le préfixe caché.
- [Memory](https://pydantic.dev/docs/ai/harness/memory/) — notebooks persistants nommés.
- **[Skills](https://pydantic.dev/docs/ai/harness/skills/)** — consomme le standard
  agentskills.io (`SKILL.md` + frontmatter) **= notre format existant** ; extra `skills`
  pour le YAML ; lazy via `load_capability` ≡ F-57.
- [CodeMode](https://pydantic.dev/docs/ai/harness/code-mode/) — sandbox Monty, budgets
  (30 s/256 Mo, max_tool_calls=100, max_retries=3), catalogue dynamique cache-friendly.
  **NO-GO prouvé avec Qwen 4B** (spike F-157 : le modèle écrit `open()` au lieu d'appeler
  les tools pliés, régénère à l'identique) — à retester avec un gros modèle seulement.

## 8. Web / vision (pour le Web Tester & visual_check)

- **[PlaywrightBrowser](https://pydantic.dev/docs/ai/harness/playwright/)** — Chromium
  stateful complet via async Playwright : navigate/click/type/scroll/JS/**screenshot**.
  Extra `playwright` + binaire chromium (`auto_install_chromium=True` possible).
  **Candidat n°1 pour remplacer chrome-devtools-mcp** côté Tester (in-process Python,
  pas de MCP) — à comparer en phase 3 (le MCP DevTools garde la console enrichie F-126).
- [Browser Use](https://pydantic.dev/docs/ai/harness/browser-use/) — délègue un objectif
  web ouvert à un agent browser autonome (trop ouvert pour nos tests déterministes).
- WebSearch/WebFetch/X : [capabilities](https://pydantic.dev/docs/ai/capabilities/mcp/)
  (fallback DuckDuckGo local pour la recherche).

## 9. Tests (notre culture pytest)

[Unit testing](https://pydantic.dev/docs/ai/guides/testing/) — **`TestModel`** appelle
tous les tools et génère des données valides par schéma (0 LLM, 0 réseau) ;
**`FunctionModel`** pour des réponses scriptées ; `agent.override(model=…,
toolsets=…)` ; **`ALLOW_MODEL_REQUESTS=False`** global anti-fuite réseau. Permet des
tests déterministes du Coder pydantic sans GPU — inestimable pour la non-régression F-157.

## 10. Divers à connaître

- [Agent Specs](https://pydantic.dev/docs/ai/core-concepts/agent-spec/) — agents en
  YAML/JSON (capabilities customs enregistrables) — piste de config déclarative.
- [Pydantic Graph](https://pydantic.dev/docs/ai/graph/overview/) (+ [builder](https://pydantic.dev/docs/ai/graph/builder/),
  [steps](https://pydantic.dev/docs/ai/graph/builder/steps/), [joins](https://pydantic.dev/docs/ai/graph/builder/joins/),
  [parallel](https://pydantic.dev/docs/ai/graph/builder/parallel/)) — moteur de graphe typé
  embarqué : NE PAS migrer notre orchestrateur maintenant (il marche), mais à garder en
  tête si un jour on remplace workflows.py.
- Durable execution ([overview](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/) —
  Temporal/DBOS/Prefect/Restate) : runs survivant aux restarts — futur E2E longs.
- Interfaces : `agent.to_cli_sync()` / `to_web()` / [ACP](https://pydantic.dev/docs/ai/harness/acp/)
  (servir l'agent aux éditeurs) — pas notre besoin.

## 11. Pièges d'API déjà payés (v2.33 / harness 0.24.0, Python 3.14)

| Piège | Fix |
|---|---|
| `result.usage()` planté | `result.usage` est une **propriété** |
| `UsageLimits(requests=…)` | champ = `request_limit` (+ `tool_calls_limit`, `total_tokens_limit`…) |
| `ClearToolResults()` sans args | exige `max_messages=` / `max_tokens=` / `max_fraction=` |
| `CodeMode` ImportError | extra : `uv add "pydantic-ai-harness[code-mode]"` (Monty) |
| CodeMode × petit modèle | NO-GO 4B (cf. §7) — tools natifs par défaut |
| Skills frontmatter YAML | extra : `pydantic-ai-harness[skills]` |
| TestModel + native tools | `agent.override(model=TestModel(), native_tools=[])` |

## 12. Reste à lire (priorisé, offsets dans INDEX.md local)

Phase 3 concernée : Guardrails (détail des verdicts), Media Stores (purge d'images avec
remise à la demande), Step Persistence (reprise post-crash), Advanced Tool Features
(préparation d'args = nos sanitizeurs), Shell (allowlist fine), Deferred Tools (HITL),
Memory/Conversation Search (mémoire inter-runs), Multi-Agent Patterns, Extensibility.
Pages couvertes en survol/1-ligne : Realtime voix, Evals détaillées, AG-UI/Vercel UI,
ACP, Durable exec détaillé, providers cloud spécifiques — reprendre SI le besoin émerge.
