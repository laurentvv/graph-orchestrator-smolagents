# Analyse : migration du nœud Coder vers un harness de codage dédié (et avenir de smolagents)

> Date : 2026-08-22 · Statut : analyse / décision en attente de feu vert
> Question posée : remplacer le moteur smolagents du nœud Coder par un harness de codage dédié
> (réf. [pydantic.dev/docs/ai/harness](https://pydantic.dev/docs/ai/harness/)) et évaluer si smolagents
> reste la bonne solution pour l'usine.

---

## 1. Verdict exécutif

1. **L'intuition est correcte : smolagents est un framework d'agents minimaliste, pas un harness de codage.**
   La comparaison Credal sur le benchmark CORE donne ~78 % pour un même modèle puissant dans le
   harness Claude Code contre ~42 % dans smolagents : ce n'est pas le modèle, c'est le harness qui
   plafonne. Le dépôt en apporte la preuve interne : ~3 500-4 000 LOC de glue (compaction, gardes,
   vision, prefill, retry) ont été construites **pour compenser** ce que smolagents n'offre pas.
2. **Un seul candidat bibliothèque répond à toutes les contraintes : `pydantic-ai-harness`** (MIT,
   org pydantic, Python 3.10+, embarquable dans un nœud). Son modèle de « capabilities » couvre
   nativement presque chaque pièce maison (compaction tierée, limites d'outputs outils, hooks par
   step, MCP, system reminders ≈ nudges) **et** il propose un `CodeMode` (script Python dans un
   sandbox Monty) qui prolonge la philosophie CodeAct déjà validée avec le Qwen 4B.
3. **Mais le candidat est jeune (0.x, ~802 ★, 184 commits) et le chemin llama.cpp a des angles
   connus** (issue pydantic/pydantic-ai#4878). La migration ne doit donc **pas** être un big-bang :
   spike A/B derrière `debug/run_coder.py` (méthodologie F-89), critères GO/NO-GO chiffrés, plan B
   = boucle maison sur squelette **waku-agent** (vérifié dans `references/` : boucle 114 lignes
   MIT avec Observer par step + client OpenAI-compat natif, §5.1). Les harness des référents ont
   été comparés en détail (§5) : aucun n'est un meilleur moteur in-process, mais plusieurs sont
   d'excellentes sources de patterns (§5.4).
4. **smolagents reste acceptable transitoirement** comme substrate loop+MCP pour le Coder/Web
   Tester le temps de la validation ; les nœuds de raisonnement (DSPy : Router, Refiner, Architect,
   Drafter, Security, Judge, Escalation) ne sont **pas concernés** par cette question.

---

## 2. État des lieux : ce que smolagents fait réellement dans l'usine

Cartographie issue du code (cf. §annexe A pour les file:line) :

| Rôle smolagents | Où | Réalité |
|---|---|---|
| Boucle agent Coder | `CompactingCodeAgent(CodeAgent)` — compaction.py:621, nodes.py:1656 | **CodeAct** : le modèle écrit un bloc ```python exécuté par un interpréteur local (`code_block_tags="markdown"`, `additional_authorized_imports=[os, subprocess]`, executor timeout) |
| Boucle Web Tester | testers/web_tester.py:367 | Même stack + Puppeteer MCP en plus de chrome-devtools |
| Modèle | `LoggedOpenAIServerModel(OpenAIServerModel)` — nodes.py:98 | llama-server local (API OpenAI-compatible), retry transport F-104, contournement `api_base`, prefill assistant F-103 (`ChatMessage(role="assistant")` = "```python\n") |
| Outils | `@tool` / `Tool` / `BaseTool` dans tools.py, devtools_dom_tools.py, vision_callback.py, skill_loader_tool.py… | ~30 outils : fichiers (read/write/edit/search_replace/multi_replace), DevTools helpers JS (12), skills lazy, log_event, visual_check |
| MCP | `ToolCollection.from_mcp` — mcp_connect.py:54, chrome_devtools_tool.py | chrome-devtools-mcp (screenshots, console, DOM) + Context7 ; patch mcpadapt pour les images |
| Mémoire | `AgentMemory`/`ActionStep` + override `write_memory_to_messages` — compaction.py:646 | Compaction maison : purge images perte-zéro, snip hiérarchique, clip outputs, budgets, preflight |
| Gardes | `step_callbacks` unique point d'accroche — nodes.py:1668 | screenshot callback (images → `observations_images` + ~10 nudges F-114/125/129/130/131/138), LoopGuard, StallDetector, GoalEnforcer lisent `agent.memory.steps` |

**Chiffres** : package `graph_orchestrator` ≈ 25 800 LOC ; modules important smolagents ≈ 7 220 LOC,
dont ≈ **3 500-4 000 LOC durément couplées à l'API smolagents** (≈ 30 % de glue pour 70 % de métier
dans les modules touchés). À cela : ~5 000 LOC de tests/mock smolagents et le mini-harness
`agent_server` (2ᵉ harness du dépôt, ToolCollection également).

**Lecture stratégique** : l'usine a déjà reconstruit autour de smolagents tout ce qu'un harness de
codage apporte normalement (gestion de contexte, gardes, injection de rappels, vision). smolagents
n'apporte plus que : la boucle CodeAgent (~1 000 lignes core), l'exécuteur Python, le plumbing
Tool/@tool, `ToolCollection` (MCP) et une structure mémoire. Le coût actuel de smolagents =
dépendance structurante + plafond qualitatif ; le coût d'une migration = réécrire la glue (~4 k LOC)
et **révalidation comportementale** de tout l'arsenal durci (F-50, F-90, F-103/104, F-114,
F-125–F-131, F-138…).

---

## 3. Contraintes discriminantes (issues de l'usine)

1. **Bibliothèque Python embarquable** dans `execute_coder_node` — pas un CLI ni un service distant.
   Élimine d'office : opencode (TS, serveur embarqué mais IPC), crush (Go), pi / prime-agent /
   room (TS), kilocode (TS, API REST+SSE), deepseek-harness (SDK Python = simple driver JSON-RPC
   d'un runtime TS).
2. **Modèles locaux via llama-server** (llama.cpp, API OpenAI-compatible, `--jinja` requis pour les
   tools). Pas de cloud, pas d'API Responses.
3. **Petit modèle fast (Qwen3.5-4B)** → le **protocole d'action** est le facteur n°1 de fiabilité :
   - CodeAct markdown + prefill (actuel) : validé, durci (DRY, prefills, gardes).
   - Native tool-calling JSON : entraînable (templates Hermes) mais fragile sur un 4B, surtout pour
     de longues charges (code JSON-échappé dans un argument d'outil).
   - Edit-formats texte (aider SEARCH/REPLACE, udiff, whole) : réputés les plus robustes petits
     modèles ; pas de JSON du tout.
4. **Hooks par step** : injection de nudges, remontée d'images dans les observations, gardes
   anti-boucle avec introspection de l'historique.
5. **Vision** : screenshots PIL → observations multimodales (le Judge/Tester raisonnent dessus).
6. **Prefill assistant / samplers / grammaires** : arsenal F-103 branché sur llama-server
   (`llama_server.py` reste propriété de l'usine quel que soit le choix).
7. **Sortie structurée** `CoderOutput` Pydantic + sauvetage DSPy (models.py:251) — le nœud doit
   continuer à produire un objet validé.

---

## 4. Le candidat : pydantic-ai-harness

### 4.1 Fiche

- **Origine** : « Harness Week » (pydantic.dev), officiel, adossé à Pydantic AI v2. Dépôt
  `pydantic/pydantic-ai-harness` : MIT, ~802 ★, 184 commits, Python 3.10+, versionnement 0.x
  (ruptures possibles entre minors, migrations documentées).
- **Modèle** : tout provider Pydantic AI ; chemin local = `OpenAIChatModel` +
  `OpenAIProvider(base_url="http://localhost:PORT/v1")` (le pattern Rapid-MLX de la doc est
  exactement notre cas). Remèdes documentés pour les endpoints exotiques via `OpenAIModelProfile` :
  `openai_supports_strict_tool_definition=False`, `openai_chat_supports_multiple_system_messages=False`
  (llama.cpp applique le chat template côté serveur), `openai_chat_supports_max_completion_tokens=False`.
  ⚠️ Issue ouverte pydantic/pydantic-ai#4878 (« Need for llama.cpp providers ») : le provider OpenAI
  a des comportements surprenants avec llama.cpp — à traiter en tête du spike.
- **Embedding** : `Agent(model, capabilities=[...])` — c'est une bibliothèque, pas un CLI (le CLI
  `clai` n'est qu'un habillage). S'insère dans un nœud asyncio avec `asyncio.to_thread` comme
  aujourd'hui.

### 4.2 Mapping pièce maison ↔ capability (le cœur de l'analyse)

| Machinerie maison (smolagents) | Équivalent pydantic-ai-harness | Qualité du match |
|---|---|---|
| `CompactingCodeAgent.write_memory_to_messages` (purge images, snip, clip, budgets, preflight) | `TieredCompaction` (stratégies zéro-LLM puis summarization LLM en fallback) + `ClearToolResults(0.7)` + `WarnNearLimits(0.9)` + `ToolOutputLimits` | **Bon** ; purge d'images non documentée → à porter via `ProcessHistory` (capability custom) |
| `step_callbacks` + ~10 nudges (F-114/125/129/130/131/138) | Hooks `after_node_run` / `before_model_request` (mutation de `messages`) + capability `SystemReminders` | **Très bon** — hooks plus riches que smolagents (before/after/wrap/error × run/node/model/tool) |
| `vision_callback` : wrappers d'outils (strip `filePath`, patch mcpadapt, images → observations) | Hook `tool_execute` (wrap : transformer le résultat, `SkipToolExecution`, recover d'erreur) ; retours multimodaux natifs (« multimodal final expressions return natively ») | **Bon** — le wrapping d'outil devient un hook au lieu d'une sous-classe `Tool` |
| `run_with_retry` + LoopGuard / StallDetector / GoalEnforcer (introspection `memory.steps`) | Hooks `run`/`node_run` (wrap) + `run_event_stream` ; agents pilotables par itération (`agent.iter`) | **Bon** — même niveau de contrôle, portage direct des gardes |
| `io_guard` (allowlist de chemins pur Python) | `FileSystem(root)` : path-traversal et symlink safe par construction | **Bon** — la garde devient structurelle |
| `ToolCollection.from_mcp` (chrome-devtools, Context7, Puppeteer) | `MCPServerStdio` natif Pydantic AI (+ capabilities `browser-use`, `playwright` si un jour utiles) | **Bon** — supprime le patch mcpadapt |
| `LoggedOpenAIServerModel` (retry, `api_base`) | Provider standard + `model_request` hooks (retry/logging) | **Moyen** — à revalider contre llama.cpp (issue #4878) |
| Prefill assistant F-103 | **Pas d'équivalent documenté.** Avec `CodeMode`, le besoin change de nature (voir 4.3) | **Point de vigilance** |
| Prompt géant utilisateur (ROLE_BLOCKS + invariants + stratégie + fichiers + skills) | `instructions=` + `reinject_system_prompt` + `RepoContext` + capability `Skills` | **Bon** — le prompt devient un vrai system prompt géré |
| `CoderOutput` Pydantic + `extract_and_validate` + sauvetage DSPy | `output_type=CoderOutput` natif (validation + retries intégrés) | **Très bon** — simplifie models.py |
| `additional_authorized_imports=[os, subprocess]` + exécuteur Python timeoutné | `CodeMode` : sandbox Monty, `resource_limits` (30 s / 256 MiB par défaut), imports limités (pas de subprocess) ; I/O via `MountDir`/`os_access` | **Différent** — plus sûr mais plus restreint ; les usages os/subprocess du Coder sont à recaser en tools |

### 4.3 Le point critique : protocole d'action et Qwen 4B

- **Aujourd'hui** : CodeAgent = bloc ```python en markdown dans la réponse → préfillable
  ("```python\n"), pas de JSON, DRY côté serveur. C'est ce qui a été durci et qui tient.
- **CodeMode** : le programme Python est passé **dans l'argument d'un tool call `run_code`** (JSON
  échappé) puis exécuté dans Monty (sous-ensemble Python : `sys, typing, asyncio, math, json, re,
  unicodedata, datetime, os, pathlib` ; pas d'imports tiers ; REPL persistant ; `max_retries=3`,
  `max_tool_calls=100`, budget CPU/RAM par session). Avantages massifs : 1 aller-retour au lieu de N,
  calcul local (filtrage/agrégation), historique compact — exactement la promesse CodeAct poussée au
  bout. Risque : l'échappement JSON de programmes longs par un 4B via llama-server est **le** risque
  n°1 du spike (les échecs de tool-call JSON sont déjà une famille de bugs connue des petits
  modèles). Mitigations possibles : tool-calling Hermes de Qwen 3.5, `openai_supports_strict_tool_definition=False`,
  et à défaut retour au mode tools natifs du Coder harness (read/write/edit) avec edit full-file ou
  diff — à qualifier au spike.
- **Sans CodeMode**, le `Coder` standard (FileSystem+Shell+Planning+SubAgents) suppose un modèle
  « moderne » (doc : « modern models don't need procedural coaching ») — hypothèse non acquise
  avec un 4B local. Les instructions procedurales de l'usine (invariants, rituel visual_check)
  restent nécessaires → `instructions=` custom obligatoire (prévu par l'API).

### 4.4 Risques spécifiques

1. **Maturité 0.x** : churn d'API possible entre minors ; pin précis + lock requis.
2. **llama.cpp secondaire** chez Pydantic (Ollama a sa page dédiée, llama.cpp non) ; issue #4878
   ouverte → le spike commence par un smoke test provider.
3. **Images dans la compaction** : non documentées ; la purge perte-zéro F-120/F-121 devra être
   une capability `ProcessHistory` maison (le mécanisme existe, c'est le point d'extension prévu).
4. **Coût de révalidation** : tout le comportement durci (F-50 boucle screenshots, F-90/F-109
   visual_check, F-114 nudges, F-125–131 anti-gels, F-138) doit repasser la stack d'isolation F-89
   puis un E2E Bubble Sort + un Hard (Kanban).

---

## 5. Comparaison détaillée contre les harness des référents (vérifiés dans le code)

Cette section remplace la première passe (basée sur les seuls audits) par une comparaison **vérifiée
dans les dépôts `references/`** (file:line cités). Rappel des critères discriminants (§3) :
in-process Python, llama-server, protocole compatible 4B, hooks par step, sortie structurée.

### 5.1 Panorama par famille

**Famille A — In-process Python (embarquables dans `execute_coder_node`)** :

- **aider** (Apache 2.0) — moteur d'**édition**, pas un agent autonome. `Coder.create()`
  (base_coder.py:124-201) + `run(with_message=…)` = **une itération par appel**, retourne une
  `str` brute (base_coder.py:881) — c'est notre graphe qui fournit la boucle (comme aujourd'hui).
  llama-server OK : litellm + préfixe `openai/` + `OPENAI_API_BASE` (main.py:620-621). Edit-formats :
  `whole` par défaut pour modèle inconnu (models.py:131), `diff` SEARCH/REPLACE, `udiff`, `patch`.
  ⚠️ Le matching fuzzy « vrai » (`replace_closest_edit_distance`, editblock.py:296) est **du code
  mort** dans cette version (bare `return` ligne 183) — les fallbacks réels sont
  whitespace/ligne-vide/`...` seulement. Hooks par step : aucun natif — le hook de facto est de
  sous-classer `InputOutput` (io.py:230), et l'autonomie exige `yes=True` pour neutraliser les
  `confirm_ask` des réflexions lint/test (max_reflections=3, base_coder.py:101). RepoMap 1024
  tokens (×8 sans fichiers au chat, repomap.py:124-132). Pas de sortie structurée, pas de vision.
- **waku-agent** (MIT, PyPI `waku-agent`) — ⭐ découverte de la vérification code : **le meilleur
  squelette « posséder la boucle »**. `run_loop` = 114 lignes (waku/loop/agent.py:41-51) avec
  `Observer = Callable[[str, LoopEvent], None]` émettant `text`/`llm`/`tool` **par step**
  (lignes 75-106) — exactement le hook cherché ; un tool peut recevoir `_notify` (registry.py:54-55)
  → remontée de screenshots triviale. **Client OpenAI-compat natif** (`OpenAICompatClient`,
  models.py:296-410, streaming inclus) → llama-server direct. Mini moteur de graphe avec
  `max_visits` par nœud + `max_steps` global (graph/engine.py:133-157). Ce n'est pas un coder
  (aucun tool d'édition, `LoopResult` dataclass, pas de Pydantic) — mais pour le plan B, c'est
  ~700 lignes MIT qui remplacent l'écriture from-scratch de la boucle.
- **nanocode** (MIT) — boucle nue 272 lignes mono-fichier, couplée Anthropic en 3 blocs
  (call_api, parsing tool_use, make_schema) ; portage OpenAI-compat ≈ 1-2 h. Utile comme plancher
  de comparaison et pour son contrat d'edit « old unique sinon erreur » (nanocode.py:44-45).

**Famille A-bis — Python mais NON embarquables** :

- **open-swe** (MIT) — plateforme complète LangChain (dashboard, Slack/Linear, sandbox cloud,
  `langgraph_sdk` partout). Sa factory `make_model` **force `use_responses_api=True`** pour
  `openai:` (utils/model.py:142) → casse llama-server par défaut (contournement : `model_kwargs`
  ligne 101-108). Valeur : patterns de middlewares (`@before_model` injection de contexte,
  `@after_agent` coupure, `awrap_model_call`) — au prix de la dépendance langchain+deepagents.
- **hermes-agent** (MIT) — assistant personnel monolithique (run_agent.py 9 051 lignes, gateway
  multi-plateformes). Meilleur support llama.cpp du panel (provider `custom` avec alias
  `llamacpp`, plugins/model-providers/custom/__init__.py:84-101, gestion `think=False`) mais
  prisonnier de l'app. Patterns : contrat middleware 4 kinds, sécurité (≈260 patterns dangereux).
- **LlamaBot, deer-flow** — multi-agents LangGraph orientés cloud/Rails (LlamaBot) ou monolithe
  multi-tenant (deer-flow, pourtant MIT). Middlewares intéressants (circuit-breaker, gate
  read-before-write) mais pas des moteurs embarquables.

**Famille B — Out-of-process mais pilotables depuis Python** (évalués sérieusement, cf. 5.3) :

- **deepseek-harness** (MIT) — ⭐ **seul SDK Python officiel du panel** : JSON-RPC 2.0 sur stdio
  (`python/sdk/`), `Session.run() → RunResult` avec événements par step y compris sous-agents.
  Limite : l'adaptateur openai-custom exige de composer un `cordis.yml` (adaptateur `llm-pi-ai`) ;
  runtime TS en sous-processus ; « developer preview » à ruptures annoncées.
- **opencode** — serveur REST+SSE (`opencode serve`), OpenAPI publié (`packages/sdk/openapi.json`)
  → client Python générationnable ; provider `openai-compatible` natif (baseURL → /chat/completions)
  = llama-server direct ; **prompt avec `delivery: "steer" | "queue"`** = injection mid-run possible
  (schema/session-delivery.ts:5) ; SSE avec replay par n° de séquence. Pas de SDK Python officiel.
- **pi** — mode RPC headless JSON stdin/stdout (`modes/rpc/rpc-mode.ts`) pilotable en JSONL depuis
  Python ; extensions avec `tool_call` **mutable** + `{block, reason, terminate}` ; compaction à
  cut-points sûrs. Protocole serveur binaire custom (pas HTTP).
- **crush** — daemon HTTP sur named pipe Windows (server.go:158-197) : sessions, SSE, permission
  grant, cancel. API non documentée/instable. Provider local exemplaire (`base_url` + `extra_body`
  verbatim + auto-discovery `/v1/models`, config.go:126-142).

**Famille C — Non moteurs** : kilocode (fork d'opencode — son CodeMode est un interpréteur
tree-walking TS de ~3 465 lignes, `packages/codemode/src/interpreter/runtime.ts`, qui n'orchestre
que les tools MCP ; à piller, pas à embarquer), openfox (vrai harness local-LLM-first mais TS ;
ses docs `ENGINE-LOOP.md`/`SESSION-DEBUGGING.md` = blueprint direct pour un bespoke), qm et loopx
(control planes : compaction duale 0.7/0.9 + mémoire deux tiers pour l'un, anti-loop déterministe
+ transactions de turn pour l'autre), hunk (review), axon/RepoGraph/graphify (knowledge graphs),
obscura (navigateur headless Rust via MCP), ponytail/framework (skills).

### 5.2 Matrice décisionnelle (moteur Coder)

| Critère | pydantic-ai-harness | aider | waku-agent | open-swe | deepseek-harness | opencode | pi | crush | nanocode |
|---|---|---|---|---|---|---|---|---|---|
| In-process Python | ✓ biblio | ✓ biblio | ✓ boucle 114 L | ✗ plateforme | ✗ runtime TS | ✗ serveur TS | ✗ RPC stdio | ✗ named pipe | ✓ 272 L |
| llama-server | ~ OpenAI-compat + flags (issue #4878) | ✓ litellm `openai/` | ✓ client natif | ✗ force Responses API | ~ via `cordis.yml` à écrire | ✓ provider dédié | ✓ pi-ai | ✓ base_url+extra_body | ✗ (portage 1-2 h) |
| Protocole 4B-friendly | CodeMode (code dans arg JSON) ou tools natifs | ✓✓ edit-formats texte | au choix (tools à fournir) | tools natifs | run_code bilingue TS/Python | tools natifs | tools natifs | tools natifs | tools natifs |
| Hooks par step | ✓✓ before/after/wrap × run/node/model/tool | ~ sous-classe `InputOutput` | ✓✓ Observer + `_notify` tools | ✓ middlewares | ✓ events SDK | ~ SSE + steer/queue | ✓ extensions | ~ PreToolUse shell | ✗ |
| Édition de code | FileSystem (read/write/edit/search) | ✓✓ edit-formats + repomap + lint/test réflexifs | ✗ à écrire | backends deepagents | ✓ | ✓ | ✓ | ✓ | ✓ minimal |
| Sortie structurée Pydantic | ✓✓ `output_type` natif | ✗ str brute | ✗ dataclass | ~ via LangChain | ~ events SDK | ✗ | ✗ | ✗ | ✗ |
| Compaction/contexte | ✓✓ TieredCompaction + 3 caps | ✗ (repomap seulement) | ✗ à porter | Summarization (bug `reasoning_content` cité) | ✓✓ checkpoint 8 sections KV-warm | endpoint compact | ✓✓ cut-points sûrs + file-tracker | ✗ | ✗ |
| Vision mid-loop | ✓ retours multimodaux + hooks | ✗ | ✓ `_notify` | ~ | ~ | ~ | ~ | ~ | ✗ |
| Prefill / samplers fins | ✗ non documenté | ~ (via litellm, non First-class) | ✓✓ contrôle total (on possède la boucle) | ✗ | ✗ | ✗ | ✗ | ✗ | ✓✓ contrôle total |
| Licence | MIT | Apache 2.0 | MIT | MIT | MIT | à vérifier | à vérifier | à vérifier | MIT |
| Maturité | 0.x jeune (org pydantic) | ✓✓ très mature | v0.1.4 jeune | interne LangChain | developer preview | ✓✓ très répandu | ✓ actif | ✓ actif | pédagogique |
| **Verdict moteur** | **Candidat n°1 (spike)** | Couche édition / complément | **Squelette du plan B** | Écarté | Plan C (SDK Python) | Plan C (REST steer) | Patterns | Patterns | Plancher |

Benchmark de contexte (pour situer le plafond harness) : CORE, même modèle fort ≈ 78 % (harness
Claude Code) vs ≈ 42 % (smolagents) — [Credal](https://credal.ai/blog/best-agent-harness-platforms) ;
panoramas 2026 : [Firecrawl](https://www.firecrawl.dev/blog/best-ai-coding-agents),
[Raschka — Using Local Coding Agents](https://magazine.sebastianraschka.com/p/using-local-coding-agents).

### 5.3 Les duels clés

**pydantic-ai-harness vs aider** — deux philosophies opposées qui sont en fait complémentaires :
pydantic est un harness **avec boucle** (capabilities, hooks, compaction, sortie structurée) ;
aider est un moteur d'**édition sans boucle** (une itération par `run()`, notre graphe pilote).
aider gagne sur la maturité et les edit-formats texte éprouvés petits modèles (zéro JSON) ;
pydantic gagne sur tout le reste (hooks par step, vision, sortie Pydantic, compaction).
Hybride réaliste : garder les modules d'édition d'aider (`editblock`, `repomap`) comme **tools**
dans le moteur retenu — notre tools.py a déjà `search_replace`/`multi_replace`, proches cousins.

**pydantic-ai-harness vs waku-agent (plan B)** — bibliothèque de capabilities vs possession de la
boucle. La vérification code change la donne du plan B : ce n'est plus « écrire ~2 k LOC from
scratch » mais **« monter nos tools/gardes existants sur la boucle waku (MIT, ~700 L utiles,
déps anthropic+openai) »** — l'Observer waku couvre le besoin nudges/screenshots, l'
`OpenAICompatClient` couvre llama-server, et le contrôle total préserve prefill/DRY/futurs GBNF.
Ce que waku n'a pas : tout le métier codage (éditeurs, compaction tierée, skills) — c'est-à-dire
précisément ce que l'usine possède déjà en version smolagents-dégrevable.

**pydantic-ai-harness vs deepseek-harness / opencode (plan C)** — les deux seuls out-of-process
pilotables proprement (SDK JSON-RPC officiel pour l'un, REST+SSE+steer pour l'autre) rendent
l'injection mid-run **possible** (steer/queue, événements par step). Mais ils abandonnent ce qui
fait la valeur de l'usine : prefill assistant, samplers DRY côté serveur, ROLE_BLOCKS/invariants
forcés, nudges conditionnels par step, remontée d'images pilotée. À conserver en plan C de
dernier recours, pas en cible.

### 5.4 Ce que le moteur retenu doit voler aux référents (mapping précis)

| Pattern source | Référence file:line | Destination dans l'usine |
|---|---|---|
| Anti-loop doux `[3,5,8]` : canonisation des args (tri récursif clés), reminder escaladé injecté comme contexte, reset sur interjection user | deepseek-harness `repeat-tool-reminder/src/index.ts:89-105,189-232` | Complément de LoopGuard : nudge AVANT le hard-stop (LoopGuard v2) |
| Signature SHA-256 (tool+args+**result**), fenêtre 10, seuil 5 | crush `loop_detection.go:19-71` | LoopGuard v2 (détecte les appels identiques aux résultats identiques) |
| Compaction checkpoint **8 sections fixes** + replay du préfixe exact pour warm KV-cache | deepseek-harness `summarizer.ts:24-66` | Capability `ProcessHistory` (ou compaction waku) — réutilise le cache-reuse llama-server |
| Cut-points sûrs (jamais entre tool_call et tool_result) + **file-tracker cumulatif** inter-compactions | pi `compaction.ts:307-420,34-70` | Purge images / compaction maison portée |
| Hook `tool_call` avec input **mutable** + `{block, reason, terminate}` (terminate si tout le batch le demande) | pi `extensions/types.ts:917-918,1086-1096` | Sémantique exacte des hooks `before_tool_execute` (pydantic) |
| Frontière plain-data `copyIn`/`copyOut` + diagnostics typés + budget triple (temps/appels/octets) | kilocode `tool-runtime.ts:152-171`, `codemode.ts:62-110` | Si CodeAct/CodeMode conservé : durcissement de l'exécuteur |
| `extra_body` verbatim + auto-discovery `/v1/models` | crush `config.go:126-142` | Glue provider llama_server.py |
| Contrat d'edit « old unique sinon erreur explicite » | nanocode `nanocode.py:44-45` | `edit_file`/`search_replace` de tools.py |
| Blueprint boucle + event-sourcing session | openfox `ENGINE-LOOP.md`, `SESSION-DEBUGGING.md` | Plan B (docs transposables à DuckDB) |
| Compaction duale (soft 0.7 async / hard 0.9 synchrone) + mémoire deux tiers | qm (audit 14) | Évolution F-116 `_f116_compact_memory` |

---

## 6. smolagents est-il encore la bonne solution ?

- **Comme harness de codage : non.** Ce n'est pas son positionnement (« barebones library for
  agents that think in code », cœur ~1 000 lignes) et l'usine a dû écrire le harness elle-même
  autour. Le plafond est démontré (benchmark + 4 k LOC de rattrapage).
- **Comme substrate loop + MCP + Tool : acceptable en transition.** Rien n'est cassé ; les runs de
  référence (#11, #19) prouvent que le couple CodeAct+gardes produit des livrables conformes. Le
  paradoxe à assumer : plus on durcit, plus smolagents devient une coquille — la valeur est dans
  les gardes maison, pas dans la boucle.
- **Les nœuds DSPy ne sont pas concernés** (doctrine dspy_nodes.py:12 : raisonnement = DSPy,
  exécution = smolagents). La migration ne déplace que la moitié « exécution ».
- **Conséquence logique** : la question n'est pas « quel framework ? » mais « qui possède la
  boucle ? ». Deux trajectoires cohérentes : (a) externaliser la plomberie standard vers
  pydantic-ai-harness et reloger les gardes maison en hooks/capabilities ; (b) assumer le bespoke
  et supprimer la dépendance. Rester sur smolagents à long terme n'est ni l'un ni l'autre : c'est
  payer une dépendance pour un plafond.

---

## 7. Scénarios de migration

### S0 — Statu quo durci
Continuer à patcher smolagents (comme F-156 en cours). Coût : 0 migration, mais chaque feature
compense le harness au lieu de construire. À réserver si le spike S1 échoue et que S2 est refusé.

### S1 — pydantic-ai-harness pour le Coder (recommandé, conditionnel au spike)
Phasage proposé :
1. **Spike provider** (0 LLM risque) : `OpenAIChatModel` + llama-server spawné par
   `model_lifecycle` ; tool-calling Hermes ; vérifier les flags `OpenAIModelProfile`. Bloquant si
   la pyd. d'appels tools ne passe pas.
2. **Spike `debug/run_coder_pydantic.py`** (nouveau script d'isolation F-89, à côté de
   `debug/run_coder.py`) : Coder minimal `capabilities=[FileSystem(runs/…), CodeMode(tools=[…]),
   ToolOutputLimits, ClearToolResults]` + `instructions=` reprenant ROLE_BLOCKS/invariants.
   Entrée figée = prompt Bubble_Sort_Visualizer. Mesures GO/NO-GO :
   - taux de tool-calls `run_code` bien formés (JSON) ≥ 90 % sur ≥ 10 exécutions ;
   - zéro boucle de screenshots (F-50) et rituel visual_check présent ;
   - livrable conforme au contrat Bubble Sort (assertions du Tester) ;
   - tokens totaux ≤ status quo (CodeMode doit compacter les allers-retours) ;
   - pas de régression F-125–F-131 (gels navigation/édition).
3. **Portage des gardes** si GO : LoopGuard/StallDetector/GoalEnforcer en hooks `node_run` ;
   purge d'images en `ProcessHistory` ; prompt complet + skills ; `output_type=CoderOutput`.
4. **Web Tester en second** (il partage le stack), puis retrait de smolagents du pyproject
   (dernier step, seulement quand Coder+Tester tiennent).
Chaque phase = feature F-xxx + PR dédiée (règle d'or Git), validée isolation puis E2E.

### S2 — Mini-harness maison sur squelette waku-agent (plan B, renforcé par la comparaison)
La vérification code des référents change le coût de ce scénario : partir de la boucle
**waku-agent** (MIT, PyPI `waku-agent`, ~700 lignes utiles, deps `anthropic`+`openai` seulement) :
`run_loop` 114 lignes avec Observer par step (nudges/screenshots natifs), `OpenAICompatClient`
llama-server prêt, moteur de graphe `max_visits` anti-boucle. On y monte : les tools existants
dégrevés de l'interface smolagents (tools.py/devtools_dom_tools.py = métier portable), la
compaction actuelle dégrevée (ou le pattern checkpoint 8 sections de deepseek-harness), les gardes
existantes + les vols de §5.4. Protocole au choix — conserver le CodeAct markdown+prefill actuel
(zéro réapprentissage du 4B, contrôle total DRY/GBNF). Coût : bien en-deçà du « 1-2 k LOC from
scratch » estimé initialement ; bénéfice : contrôle total, zéro churn amont.

### S3 — Hybride transitoire
Coder migré S1/S2, Web Tester et `agent_server` restés smolagents. Utile si le Tester s'avère plus
délicat (double MCP DevTools+Puppeteer). Éviter de le figer : deux harness en parallèle = double
maintenance.

### S4 — Moteur out-of-process piloté (plan C, dernier recours)
Si les voies in-process échouent : **deepseek-harness** (seul SDK Python officiel du panel,
JSON-RPC stdio, événements par step) ou **opencode** (REST+SSE, prompt `delivery: steer|queue`
= injection mid-run, OpenAPI pour client Python généré, provider openai-compatible natif).
On abandonne alors prefill assistant, samplers DRY, ROLE_BLOCKS forcés et nudges conditionnels —
c'est-à-dire le cœur de la valeur comportementale de l'usine. À n'envisager que si l'on accepte
de déléguer le comportement du Coder au harness tiers.

---

## 8. Recommandation

1. **Valider S1 par le spike** (phases 1-2 de §7-S1) : c'est le seul chemin qui donne à l'usine un
   harness de codage maintenu par un tiers **sans perdre le contrôle** (hooks ≈ gardes maison,
   capabilities ≈ comportements maison). Pin strict de version + veille issue #4878.
2. **GO/NO-GO mesuré** sur les critères chiffrés ci-dessus ; en cas d'échec du protocole d'action
   (JSON 4B), tester la variante « tools natifs FileSystem + edit-formats aider » avant d'abandonner.
3. **NO-GO définitif → S2** (bespoke sur squelette waku-agent), en conservant le protocole CodeAct
   actuel : la boucle vient de waku, le métier (tools, gardes, compaction) est déjà à l'usine —
   c'est le plan B le moins cher des trois scénarios. Ajouter les vols de §5.4 quel que soit le
   moteur retenu (ils améliorent LoopGuard et la compaction dès maintenant, indépendamment de la
   migration).
4. **Plan C (S4) seulement en dernier recours** : deepseek-harness (SDK Python officiel) ou
   opencode (REST steer/queue) restent pilotables proprement, mais déléguer le comportement du
   Coder à un runtime tiers abandonne prefill/samplers/nudges — le cœur de la valeur de l'usine.
5. smolagents n'est retiré du `pyproject.toml` qu'à la fin (Coder **et** Tester migrés) ;
   les nœuds DSPy ne bougent pas.

---

## 9. Résultats du spike F-157 (2026-08-23) — VERDICT : GO (variante tools natifs)

### 9.1 Phase 1 — smoke test provider : 100 % PASS

`debug/pydantic_smoke_provider.py` — 4 tests contre llama-server spawné (`model_lifecycle`,
fast spec Qwen3.5-4B-Q4_K_M) :

| Test | Résultat | Détail |
|---|---|---|
| A. Chat, profil OpenAI **par défaut** | PASS | l'issue #4878 ne nous mord pas (llama.cpp récent accepte `max_completion_tokens`, tool defs strictes) |
| B. Chat, profil conservateur | PASS | flags `OpenAIModelProfile` inutiles en pratique — conservés par prudence |
| C. Tool-calling natif (JSON Hermes) | PASS | tool appelé puis résultat exploité (2 requêtes) |
| D. Sortie structurée `output_type` Pydantic | PASS | `Verdict(city='Lyon', temperature_c=21)` validé au premier essai |

### 9.2 Phase 2 — spike Coder : CodeMode NO-GO, tools natifs GO

**Round 1-2 (`--codemode`) : NO-GO documenté.** Le Qwen 4B ne suit pas la convention
CodeMode : au lieu d'appeler les tools pliés dans le sandbox Monty, il écrit du Python
idiomatique `with open('index.html','w') as f: f.write(...)` — rejeté par Monty
(`error[unresolved-reference]: Name 'open' used when not defined`, diagnostics précis
avec ligne). Malgré des messages d'erreur excellents, le modèle **régénère le même
programme à l'identique** (6 retries, ~5 k tokens chacun, ~7 min/tentative) jusqu'au
crash `UnexpectedModelBehavior`. Logs : `logs/spike_pydantic_round2.log`. Conclusion :
CodeMode suppose un modèle qui « voit » les tools comme fonctions — hors de portée du 4B
actuel ; à retester si passage à un gros modèle (escalade Ultra).

**Round 3 (tools natifs, défaut) : GO.** `debug/run_coder_pydantic.py` — Agent
FileSystem('.') + ToolOutputLimits + ClearToolResults(0.7), instructions = ROLE_BLOCKS
coder/coder_frontend + UNIVERSAL_INVARIANTS + protocole natif, sans CodeMode :

- Livrable Bubble Sort 3 fichiers : **8/8 contrôles** (existence, câblage styles.css/
  script.js, init robuste readyState/DOMContentLoaded, 'use strict', zéro placeholder) ;
- **14 tool calls / 14 retours / 0 retry prompt** (100 % bien formés — critère ≥ 90 %) ;
- 11 requêtes LLM, **131 589 / 7 414 tokens in/out**, 593,6 s (~10 min) ;
- comportement : écriture fichier par fichier (`write_file` ~3-10 Ko par appel), puis
  phase de **vérification** (read_file de chaque fichier + list_directory) avant le
  résumé final — l'invariant « verify after write » émergé spontanément ;
- `script.js` commence par `'use strict'` : invariants coder_frontend suivis.

### 9.3 A/B vs baseline smolagents

Baseline : `debug/run_coder.py` (même tâche, même Qwen 3.5 4B spawné, arsenal production
complet : skills, visual_check, MCP DevTools). Premier passage bloqué par un bug
préexistant sur main (`select_skills` inexistant — repli skills de `execute_coder_node`,
invisible en E2E car l'Architect fournit toujours subtask.skills ; corrigé sur la
branche : `build_skills_block(task_content)` + import). Second passage OK
(`logs/spike_smolagents_baseline2.log`) :

| Métrique | smolagents (production) | pydantic-ai-harness (spike minimal) | Delta |
|---|---|---|---|
| Livrable | 3 fichiers, 9,9 Ko, critères visuels vérifiés | 3 fichiers, 22,8 Ko, 8/8 contrôles | livrable pydantic plus riche |
| Durée | 533,5 s | 593,6 s | ~équivalent |
| Steps / requêtes LLM | 15 | 11 | -27 % |
| **Tokens IN cumulés** | **384 322** (20 k → 384 k,historique renvoyée en entier à chaque step) | **131 589** | **-66 %** |
| Tokens OUT | 4 287 | 7 414 | +73 % (plus de contenu réel écrit) |

Lecture : chaque step smolagents renvoie tout l'historique (les inputs par step montent
de 20 k à 384 k) ; le stack pydantic (instructions cache-stables + ToolOutputLimits +
ClearToolResults + pas de méga-prompt utilisateur réinjecté) maintient l'historique
compact. Nuance d'honnêteté : le baseline avait la vision MCP + visual_check (coût
inclus), le spike n'avait aucune capacité vision — la phase 3 réévaluera avec
PlaywrightBrowser/DevTools branchés.

### 9.4 Décision

La variante **tools natifs** du scénario S1 est GO : le protocole d'action le plus sûr
pour le 4B n'est ni le CodeAct markdown de smolagents ni le CodeMode Monty, mais le
tool-calling JSON natif avec outils à granularité fichier — ce que pydantic-ai-harness
offre avec en prime les équivalents structuraux de nos gardes maison (cf. §5.2 : hooks
≡ gardes, SystemReminders ≡ nudges, expected_hash ≡ ReadGate, DeduplicateFileReads ≡
F-130). Phase 3 (portage gardes + MCP vision + CoderOutput + Web Tester) débloquée.

---

## Annexe A — Références code clés

- Coder : nodes.py:1656 (`CompactingCodeAgent`), nodes.py:1468-1530 (prompt), nodes.py:592
  (`run_with_retry`), config.py:272 (`coder_max_steps=40`), config.py:286 (`CODER_PREFILL_CODE`).
- Modèle : nodes.py:98 (`LoggedOpenAIServerModel`), llama_server.py:362 (`model_lifecycle`),
  nodes.py:130-151 (`_maybe_prefill`).
- Outils : tools.py (16 `@tool`), devtools_dom_tools.py:725 (12 helpers JS), skill_loader_tool.py:21,
  chrome_devtools_tool.py:59, mcp_connect.py:40.
- Vision/gardes : vision_callback.py:1017 (callback+nudges), vision_callback.py:782 (wrappers
  screenshots), loop_guard.py, stall_detector.py, goal_enforcer.py.
- Mémoire : compaction.py:621-821 (`CompactingCodeAgent`, `write_memory_to_messages`).
- Sortie : models.py:251 (`extract_and_validate`), models.py:125 (`CoderOutput`).
- Isolation : `debug/run_coder.py`, `debug/run_coder_matrix.py` (F-89).

## Annexe B — Sources web

- **Doc Pydantic AI complète en local** (2026-08-22, gitignorée) :
  `references/pydantic-ai-docs/llms-full.txt` (5 Mo, 262 pages — source officielle, markdown propre),
  `references/pydantic-ai-docs/crawl_2026-08-22_overview_depth1.md` (7,1 Mo, 276 pages — crawl
  complet incl. navigation), `references/pydantic-ai-docs/llms.txt` (index). À consulter en premier
  pour le spike S1 (pages clés : harness/coder, harness/code-mode, capabilities/compaction,
  core-concepts/hooks, models/openai). Chaque page existe aussi en `.md` direct :
  `https://pydantic.dev/docs/ai/<chemin>/index.md`.
- Harness : [docs](https://pydantic.dev/docs/ai/harness/) · [Coder](https://pydantic.dev/docs/ai/harness/coder/) ·
  [CodeMode](https://pydantic.dev/docs/ai/harness/code-mode/) · [Hooks](https://pydantic.dev/docs/ai/core-concepts/hooks/) ·
  [Compaction](https://pydantic.dev/docs/ai/capabilities/compaction/) · [Modèles OpenAI-compat](https://pydantic.dev/docs/ai/models/openai/) ·
  [dépôt GitHub](https://github.com/pydantic/pydantic-ai-harness) · [annonce Harness Week](https://pydantic.dev/articles/harness-week) ·
  [Pydantic AI v2](https://pydantic.dev/articles/pydantic-ai-v2)
- llama.cpp : [issue #4878](https://github.com/pydantic/pydantic-ai/issues/4878) ·
  [issue harness #114](https://github.com/pydantic/pydantic-ai-harness/issues/114)
- Benchmarks/panoramas : [Credal CORE 78 % vs 42 %](https://credal.ai/blog/best-agent-harness-platforms) ·
  [Firecrawl 2026](https://www.firecrawl.dev/blog/best-ai-coding-agents) ·
  [Raschka local coding agents](https://magazine.sebastianraschka.com/p/using-local-coding-agents) ·
  [r/LocalLLM](https://www.reddit.com/r/LocalLLM/comments/1ug3xu4/whats_the_best_harness_for_a_local_model_is_it/)
- smolagents : [dépôt](https://github.com/huggingface/smolagents) · [docs](https://huggingface.co/docs/smolagents/en/index)
