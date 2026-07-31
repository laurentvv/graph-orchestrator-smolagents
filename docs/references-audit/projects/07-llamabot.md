# 07 — LlamaBot

## En-tête
- **Nom** : LlamaBot
- **Chemin** : `references/LlamaBot/`
- **Type** : framework d'agent de coding multi-agent (LangGraph 1.0 + LangChain `create_agent` + supervisor)
- **Langage principal** : Python 3.11 (backend FastAPI/WebSocket) + JavaScript vanilla (frontend)
- **Statistiques** : 168 fichiers pertinents (.md/.py/.json/.yaml/.toml), 8.6 MB total, 12 753 LOC Python, 10 agents déclarés dans `langgraph.json`
- **Réutilisabilité globale** : **Moyenne** (patterns test/web/circuit-breaker transférables, mais stack LangGraph diffère de DSPy/smolagents)

## Synthèse
LlamaBot est un framework d'agent de coding orienté Rails (Ruby on Rails) et édition HTML/clone de sites. Architecture LangChain 1.0+ `create_agent` avec middleware (NOT `StateGraph` manuel) — point critique documenté dans `docs/research/injected-state-create-agent-memo.md` : `InjectedState` de `langgraph.prebuilt` **ne fonctionne pas** avec `langchain.agents.create_agent`, le projet utilise donc `ToolRuntime` pour accéder à l'état dans les outils.

Points forts pour le projet cible (DSPy/smolagents) :
- **Agent de test TDD 6-stages** (`rails_testing_agent`) avec circuit-breaker (3 échecs) — modèle direct pour le nœud Tester.
- **Capture Playwright** (`capture_page_and_img_src`, `trim_html_for_llm`) — modèle pour le web tester.
- **Catalogue d'outils** 20+ (git status/commit/command, bash avec truncation `BASH_OUTPUT_MAX_CHARS=12000` et détection d'erreurs, Tavily search, grep/glob ripgrep, TODO tracking, GitHub CLI) — adaptables en `Tool` smolagents.
- **Sub-agents délégation** (`delegate_task`, `delegate_research`) pour isolation de contexte.
- **DynamicModelMiddleware** + `llm_factory.get_llm()` (Claude/GPT-5/Gemini/DeepSeek).

Limites : stack LangGraph ≠ DSPy/smolagents ; outils spécifiques Rails (Docker socket exec, `rails_api_sh`, ActiveRecord) ; frontend JS et app web Rails non transférables.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/LlamaBot/docs/research/injected-state-create-agent-memo.md` | Memo technique : `InjectedState` cassé avec `create_agent`, pattern `ToolRuntime` alternatif | **Haute** (piège LangChain 1.0 à éviter) |
| `references/LlamaBot/README.md` | Vue d'ensemble : 6 agents, 20+ outils, stack LangGraph+FastAPI+Postgres, variables d'env | Moyenne |
| `references/LlamaBot/SUMMARIZATION_BUG.md` | Bug de compaction SummarizationMiddleware (DeepSeek reasoning_content ignoré) | Moyenne (token counting) |
| `references/LlamaBot/docs/VISION.md` | Vision produit (open-source, self-hostable) | Faible |
| `references/LlamaBot/docs/DEPLOY.md` | Déploiement Ubuntu/Nginx/Certbot/Postgres checkpointer | Faible |
| `references/LlamaBot/IMPLEMENTATION_PLAN.md` | Plan d'implémentation détaillé (36 KB) | Faible |
| `references/LlamaBot/LLAMABOT_JAVASCRIPT_REUSABILITY.md` | Réutilisabilité du frontend JS | Faible |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/LlamaBot/app/agents/leonardo/rails_testing_agent/nodes.py` | `build_workflow()`, `get_cached_system_prompt()`, `SUMMARIZATION_PROMPT`, `default_tools` | Agent TDD 6-stages (Bug Intake → Test Design → Failing Test → Verify → Hand-off → Regression) avec `SummarizationMiddleware` + circuit-breaker | **Haute** | Modèle direct pour nœud Tester ; workflow RED→GREEN applicable à pytest |
| `references/LlamaBot/app/agents/leonardo/rails_testing_agent/prompts.py` | `TDD_BUG_REPRODUCTION_PROMPT`, `RAILS_QA_SOFTWARE_ENGINEER_PROMPT`, `RAILS_TESTING_AGENT_PROMPT` | Prompts TDD structurés (stages, non-négociables, sécurité) | **Haute** | Squelette de prompt réutilisable (remplacer RSpec→pytest) |
| `references/LlamaBot/app/agents/leonardo/rails_agent/middleware.py` | `FailureCircuitBreakerMiddleware` (3 failures), `check_failure_limit`, `DynamicModelMiddleware`, `ViewPathContextMiddleware`, `inject_view_context`, `DeepSeekReasoningMiddleware` | Middleware LangChain : circuit-breaker (stop après 3 `failed_tool_calls_count` via reducer `operator.add`), sélection modèle runtime, injection contexte, fix DeepSeek reasoning_content | **Haute** | Circuit-breaker = pattern directement transposable au projet cible |
| `references/LlamaBot/app/agents/utils/playwright_screenshot.py` | `capture_page_and_img_src(url, image_path)`, `trim_html_for_llm(html)`, `PLAYWRIGHT_AVAILABLE` | Capture async Playwright (screenshot full_page + HTML + img src list) + nettoyage HTML pour LLM (supprime script/meta/svg/canvas, garde attrs src/href/alt/title) | **Haute** | Modèle direct pour web tester (Puppeteer équivalent) |
| `references/LlamaBot/app/agents/leonardo/rails_agent/tools.py` | `BASH_OUTPUT_MAX_CHARS`, `BASH_ERROR_PATTERNS`, `BASH_CRITICAL_ERROR_PATTERNS`, `detect_bash_errors()`, `truncate_output()`, `read_file`, `write_file`, `edit_file` (fuzzy match via `difflib`), `glob_files`, `grep_files` (ripgrep), `git_status`, `git_commit`, `bash_command`, `internet_search` (Tavily), `write_todos`, `normalize_whitespace()`, `guard_against_beginning_slash_argument()` | Catalogue 20+ outils + utilitaires (truncation, détection erreurs, path normalization, fuzzy edit) | Moyenne | Adaptables en `Tool` smolagents ; `edit_file` fuzzy match et `truncate_output` directement utiles |
| `references/LlamaBot/app/agents/leonardo/rails_agent/state.py` | `Todo` (TypedDict: content/status pending-in_progress-completed), `RailsAgentState` (todos, debug_info, agent_mode, llm_model, `failed_tool_calls_count` avec `operator.add`) | Schéma d'état agent + compteur échecs (reducer) | Moyenne | Pattern de state + reducer réutilisable |
| `references/LlamaBot/app/agents/leonardo/rails_agent/sub_agents.py` | `delegate_task`, `delegate_research`, `create_sub_agent()`, `create_research_sub_agent()`, `RESEARCH_ONLY_PROMPT` | Délégation à sub-agents isolés (read-only vs full) | Moyenne | Pattern fan-out/isolation de contexte applicable au fan-out Coders |
| `references/LlamaBot/app/agents/leonardo/llm_factory.py` | `get_llm(model_name)`, `ChatDeepSeekWithReasoning`, `FakeTestChatModel`, `DEFAULT_LLM_MODEL` | Factory LLM multi-provider (Claude/GPT-5/Gemini/DeepSeek) avec thinking activé | Moyenne | Modèle d'abstraction provider (utile si DSPy multi-provider) |
| `references/LlamaBot/app/agents/utils/token_counter.py` | `gemini_multimodal_token_counter(messages)`, `SUMMARIZATION_TOKEN_THRESHOLD=100000` | Compteur tokens universel (tiktoken + Gemini API pour multimodal, gère reasoning_content DeepSeek) | Moyenne | Logique de token counting pour seuil de summarization |
| `references/LlamaBot/app/agents/leonardo/rails_agent/nodes.py` | `build_workflow()`, `get_cached_system_prompt()`, `SUMMARIZATION_PROMPT`, `default_tools` | Assembly agent principal avec stack middleware (Summarization→DynamicModel→DeepSeek→ViewContext→CircuitBreaker) + prompt caching Anthropic | Moyenne | Patron d'assemblage middleware (traduire en DSPy/smolagents) |
| `references/LlamaBot/app/agents/leonardo/rails_testing_agent/middleware.py` | `TestingModeContextMiddleware`, `inject_testing_mode_context` | Injection contexte TDD mode | Moyenne | Pattern d'injection de mode réutilisable |
| `references/LlamaBot/app/agents/llamapress/clone_agent.py` | `LlamaPressState`, `url_clone_agent`, `image_clone_agent`, `router_node`, `write_html_page`, `get_screenshot_and_html_content_using_playwright`, `build_workflow()` | Graphe supervisor clone de sites (router→url/image clone→tools) avec `InjectedState` (ancien pattern StateGraph) | Faible | Pattern supervisor intéressant mais très lié à Rails/LlamaPress API |
| `references/LlamaBot/app/services/headless_agent_executor.py` | `execute_agent_headless()` | Exécution agent sans WebSocket (jobs planifiés) | Faible | Spécifique infra FastAPI/SQLModel |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/LlamaBot/app/langgraph.json` | config | Registre 10 agents (llamabot, llamapress, rails_agent, rails_testing_agent, rails_ai_builder, rails_ticket_mode, rails_user_mode, rails_beginner, rails_plan_mode, pyxl_agent) avec points d'entrée `build_workflow` |
| `references/LlamaBot/langgraph.json` | config | Config racine LangGraph |
| `references/LlamaBot/pyproject.toml` | config | Métadonnées paquet Python |
| `references/LlamaBot/requirements.txt` | config | Dépendances (langchain, langgraph, playwright, tavily, anthropic, openai, google-genai, deepseek) |
| `references/LlamaBot/.env.example` | config | Variables d'env (OPENAI/ANTHROPIC/GOOGLE/TAVILY/LANGSMITH_API_KEY, DB_URI, LLAMAPRESS_API_URL) |
| `references/LlamaBot/docker-compose.yml` | config | Stack Docker (LlamaBot + Rails LlamaPress) |
| `references/LlamaBot/docs/CLA.md` | spec | Contributor License Agreement |
| `references/LlamaBot/app/rails/requirements/REQUIREMENTS.md` | spec | Specs Rails (shape-up style) |

## Exclusions conscientes
- `references/LlamaBot/docs/dev_logs/` : **41 fichiers** journaux de versions (0.1.14 → 0.5.1) + release notes HTML GitHub — signalés non détaillés (journaux de versions chronologiques)
- App web Rails (LlamaPress) : `references/LlamaBot/app/agents/llamapress/` (clone HTML), outils Docker socket exec, ActiveRecord, `rails_api_sh()` — spécifiques écosystème Rails
- Frontend JavaScript : `references/LlamaBot/app/frontend/` — non pertinent (projet cible = backend Python)
- Migrations Alembic : `references/LlamaBot/app/alembic/versions/` — schémas DB spécifiques
- Routers/services FastAPI : `references/LlamaBot/app/routers/`, `app/websocket/`, `app/services/` (sauf `headless_agent_executor`) — couche transport HTTP/WS non transférée
