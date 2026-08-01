# 17 — system-prompts-and-models-of-ai-tools

## En-tête
- **Nom** : system-prompts-and-models-of-ai-tools
- **Chemin** : `references/system-prompts-and-models-of-ai-tools/`
- **Type** : Collection de system prompts extraits/leakés d'outils IA commerciaux et open-source. Matière première textuelle (prompts), pas du code à porter.
- **Langage principal** : Texte (prompts `.txt`/`.yaml`) + JSON (schémas de tools).
- **Statistiques** : 32 dossiers d'outils, 83 fichiers `.txt`, 17 `.json` (schémas de function-calling, **pas** des configs de modèles), 4 PNG (logos). ~15 prompts d'agents de coding exploitables ; les autres sont frontend-only, search/writing, ou padding narratif.

## Synthèse
C'est une **bibliothèque de patterns** pour écrire ou durcir les `system_prompts` des agents du projet cible. La valeur n'est pas dans un fichier unique mais dans : (1) les **~15 prompts d'agents de coding** complets (Codex CLI, Manus, Augment, Claude Code 2.0, Gemini CLI, Devin, Cursor, Cline, Windsurf…), et (2) les **10 invariants universels** qui reviennent dans tous les bons prompts (read-before-write, pas de whole-file rewrite, format d'édition formel, test-first, approval gating, anti-boucle…). Ces invariants sont la **vraie valeur transversale** : ils doivent devenir une section partagée par tous nos agents.

La topologie multi-agent est aussi modélisée chez **Manus** (Planner + Knowledge + Datasource séparés + agent loop formel Analyze→Select→Wait→Iterate→Submit→Standby), ce qui est un *blueprint* direct pour Router → Architect → Coders fan-out.

**Réserves importantes** :
- ⚠️ **Biais stack** : ~80 % des prompts sont orientés JS/TS/React/frontend (v0, Lovable, Same.dev, Leap, Cursor…). Pour Python/DSPy/smolagents, il faut **adapter**.
- ⚠️ **Licence/éthique** : prompts **leakés/extraits** d'outils commerciaux. On s'inspire des *patterns* ; pour citer verbatim, préférer les **open-source** (Cline, RooCode, Codex CLI, Gemini CLI) qui sont sûrs.
- ⚠️ **Padding** : la densité directive n'est pas corrélée à la taille. Les gros fichiers (Google vibe-coder 1644 L, Claude Fable 5 1580 L, Leap 1237 L, Sonnet 4.6 1191 L, Comet 1060 L) sont souvent narratifs. **Privilégier les 100-400 lignes.**
- ⚠️ **Anti-pattern à éviter** : `Z.ai Code` dit « do not write test code » — l'inverse de notre Priorité 6 (TDD).

**Note de réutilisabilité globale : Haute** (comme matière première prompts ; différent du code à porter).

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/system-prompts-and-models-of-ai-tools/README.md` | Présentation de la collection (32 outils, nature des prompts) | Faible |
| `references/system-prompts-and-models-of-ai-tools/Manus Agent Tools & Prompt/Agent loop.txt` | Agent loop formel (33 L) : Analyze→Select→Wait→Iterate→Submit→Standby. Skeleton de boucle agent | Haute |
| `references/system-prompts-and-models-of-ai-tools/Manus Agent Tools & Prompt/Modules.txt` | Architecture multi-module (Planner/Knowledge/Datasource séparés dans l'event stream) | Haute |

## Code réutilisable
> Ici le « code » = le **texte des prompts**. Les `.json` sont des **schémas de function-calling** (utiles comme référence pour concevoir les signatures d'outils DSPy/smolagents, pas comme matière prompt). Privilégier les prompts **concis et denses** (100-400 L).

| Chemin | Rôle(s) couvert(s) | Patterns phares | Réutilisabilité | Justification |
|---|---|---|---|---|
| `…/Open Source prompts/Codex CLI/openai-codex-cli-system-prompt-20250820.txt` (342 L) | **Coder + Tester + Architect** | Philosophie de test « start specific → broaden », **3 modes sandbox** (read-only/workspace-write/danger), **4 modes approval** (untrusted/on-failure/on-request/never), « fix root cause not surface », max 3 itérations formatage, format `apply_patch` | **Haute** | **Le plus aligned avec notre stack CLI.** Sections Testing + Sandbox/Approvals exploitables telles quelles pour le Tester et le contrôle d'exécution smolagents. Open-source (sûr à citer) |
| `…/Manus Agent Tools & Prompt/Prompt.txt` + `Modules.txt` (250+206 L) | **Router + Architect (fan-out)** | Architecture multi-module (Planner/Knowledge/Datasource séparés), **agent loop formel**, `todo.md` persistant, info priority (API > search > mémoire) | **Haute** | **Topologie multi-agent** = blueprint direct pour Router→Architect→Coders fan-out. Notre architecture |
| `…/Augment Code/gpt-5-agent-prompts.txt` (241 L) | **Router + Coder + Tester** | **Catégorisation des outils par purpose** (`view`/`grep-search`/`codebase-retrieval`), **Tasklist Triggers** (multi-file, >2 itérations), **Package Management** (table par langage dont pip/poetry), safe-by-default verification, escalade si rabbit hole | **Haute** | Parfait pour le **Router** (décider qui fait quoi) et le Coder Python. Très structuré |
| `…/Anthropic/Claude Code 2.0.txt` (1150 L) | **Coder + Judge + Security** | **Git Safety Protocol** (jamais `--force`/`--no-verify`/amend sans check), **professional objectivity** (truth > validation = base du Reviewer), **read-before-edit** (Edit échoue si non lu), anti-syscall (préférer outils dédiés à bash), concision radicale (no preamble/postamble) | **Haute** | Référence pour Coder + **Judge** (professional objectivity) + Security (defensive-only). Verbeux — la version courte `…/Claude Code/Prompt.txt` (191 L) est un bon condensé |
| `…/Open Source prompts/Gemini CLI/google-gemini-cli-system-prompt.txt` (188 L) | **Coder + Tester + Judge** | Workflow **5 étapes explicite** (Understand→Plan→Implement→Verify Tests→Verify Standards), « NEVER assume standard test commands » (check README/package.json), auto-vérification post-edit (lint+typecheck OBLIGATOIRE) | **Haute** | Ultra-dense (188 L). Squelette idéal du cycle Coder→Tester→Judge. Open-source (sûr à citer) |
| `…/Devin AI/Prompt.txt` (402 L) | **Architect + Tester + Security** | **`<think>` tool avec 10 cas d'usage obligatoires** (avant git critique, avant code changes, avant completion), « ne jamais modifier les tests sauf demande », « report environment issues sans fixer », Data Security | **Haute** | `<think>` tool = base du reasoning Architect et Judge. Règle « ne pas modifier tests » = critique pour notre Tester |
| `…/Cursor Prompts/Agent Prompt 2025-09-03.txt` (229 L) | **Coder + Router** | **status_update cadencé** (avant chaque batch, après chaque todo), **gate avant edit** (reconcile TODO list), **anti-boucle linter** (max 3 puis ask user), code_style Clean Code (Martin), **maximize_parallel_tool_calls** | **Haute** | Récent et dense. status_update = tracing inter-agent. Anti-boucle linter = notre P3/P8 |
| `…/Open Source prompts/Cline/Prompt.txt` (607 L) | **Coder + Security** | **SEARCH/REPLACE blocks documentés exhaustivement** (règles 1-4 + opérations move/delete), `requires_approval` booléen par commande, MCP tool-use | **Haute** | Spec de référence pour le format d'édition SEARCH/REPLACE (déjà porté en P1). Open-source (sûr à citer) |
| `…/Traycer AI/phase_mode_prompts.txt` (46 L) | **Architect pur** | **Read-only tech lead** (« You DO NOT write code »), breakdown en phases high-level, decision tree clarification | **Haute** | **Architect pur**, sans contamination Coder. 46 lignes, le plus dépouillé. Modèle du Read-Only déjà appliqué dans notre Architect DSPy |
| `…/Windsurf/Prompt Wave 11.txt` (125 L) | **Router + Architect** | **memory system persistant** (`create_memory`), plan mastermind (`update_plan`), gate unsafe commands (« NEVER run if could be unsafe »), browser_preview auto après server | Moyenne | Concis. Memory + plan = utiles si on ajoute persistence inter-turns |
| `…/Replit/Prompt.txt` (137 L) | **Coder + Security** | **Protocole de réponse XML structuré** (`<proposed_file_replace_substring>`, `<proposed_shell_command is_dangerous="true">`), nudges vers outils workspace (Secrets/Deployments) | Moyenne | Format XML intéressant (alternative à SEARCH/REPLACE). `is_dangerous` flag = approval gating |
| `…/Kiro/Spec_Prompt.txt` (514 L) | **Architect + Security** | Spec/design documents, « ABSOLUTE MINIMAL code », **PII substitution**, tone « solutions-oriented » | Moyenne | Architect (spec). PII substitution utile pour Security |
| `…/Open Source prompts/RooCode/Prompt.txt` (665 L) | **Architect + Coder** | Variante de Cline + **multi-mode** (Code/Architect/Ask/Debug), custom instructions par mode (`.roo/rules-*/`) | Moyenne | Le multi-mode est un patron de spécialisation (P0). Open-source |
| `…/Cursor Prompts/Agent Prompt 2.0.txt` (772 L) | Coder | Version plus longue du Cursor agent (sections tool-use détaillées) | Moyenne | Version courte 2025-09-03 préférable (plus dense) |
| `…/Qoder/prompt.txt` (376 L) | **Architect + Tester** | Task planning détaillé (break down, verification après chaque étape, « NEVER mark complete until executed »), proactiveness graduée | Moyenne | Verification tasks = gate completion utile pour P6 |

### Schémas de tools (JSON) — référence pour les signatures d'outils
| Chemin | Apport |
|---|---|
| `…/Cursor Prompts/Agent Tools v1.0.json` | Schémas de function-calling (`codebase_search`, `read_file`…) — référence pour concevoir les tools DSPy/smolagents |
| `…/Replit/Tools.json` | Schémas (`restart_workflow`, `search_filesystem`…) — idem |
| `…/Augment Code/*.json` (2 fichiers) | Schémas d'outils catégorisés par purpose |

## ⚡ Les 10 invariants universels (la vraie valeur transversale)
> Vérifiés par grep croisé sur ~12 prompts d'agents de coding. Ces patterns reviennent partout — ils doivent devenir une **section partagée** par tous nos system_prompts (cf. plan P0-bis).

1. **Read-before-write / read-before-edit** — l'outil Edit doit échouer si le fichier n'a pas été lu récemment (Claude Code 2.0, Cline, Cursor, Same.dev). Re-lire si >5 messages.
2. **Pas de whole-file rewrite** — privilégier SEARCH/REPLACE / `apply_patch` / substring replace. Toujours des edits ciblés (Cline, RooCode, Codex CLI, Replit, Manus).
3. **Format d'édition formel** — un format canonique (SEARCH/REPLACE blocks, `apply_patch` Begin/End, `<proposed_file_replace_substring>`, `str_replace_editor`) réduit les erreurs.
4. **NEVER assume library available** — vérifier `package.json`/`requirements.txt`/imports voisins avant d'utiliser une lib (Claude Code, Devin, Gemini CLI, Traycer, Trae — le plus récurrent, 9+ prompts).
5. **Test-first / verify-after** — exécuter tests + lint + typecheck après chaque edit, jamais supposer le framework de test (Codex CLI, Gemini CLI, Claude Code, Augment). Philosophie « specific→broad ».
6. **Approval gating sur actions destructives** — `requires_approval`, `is_dangerous`, sandbox modes (Cline, Replit, Codex CLI, Windsurf, Devin). Jamais commit/push/install sans permission.
7. **Anti-boucle / rabbit-hole** — max 3 itérations linter (Cursor), « stop après effort raisonnable » (Augment), « going in circles → ask user » (Augment, Devin think tool).
8. **No comments / no preamble / concision** — « DO NOT ADD ANY COMMENTS unless asked » (Claude Code, Codex CLI, Devin), réponses <4 lignes (Claude Code, Gemini CLI).
9. **Todo/Task tracking obligatoire** — TodoWrite/update_plan/todo.md (Claude Code, Codex CLI, Cursor, Augment, Qoder, Manus). Marquer completed immédiatement, pas de batch.
10. **Parallel tool calls par défaut** — batch les reads/recherches indépendantes (Cursor, Windsurf, Same.dev, Traycer, Qoder). « 3-5x faster, expected behavior ».
11. *(bonus)* **Professional objectivity** — désaccorder l'utilisateur si nécessaire, truth > validation (Claude Code 2.0). Base du **Judge**.
12. *(bonus)* **Defensive security only** — refuser code malveillant, ne jamais logger/exposer secrets (Claude Code, Devin, Gemini CLI, Trae). Base du **Security Reviewer**.

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `…/*/*.json` (17 fichiers) | spec (schémas de tools) | Schémas de function-calling — référence pour concevoir les signatures d'outils DSPy/smolagents (ex: voir comment Cursor définit `codebase_search`, Replit `search_filesystem`) |
| `…/Amp/*.yaml` (2 fichiers) | config (prompts YAML) | Format YAML de prompts codés (claude-4-sonnet 68KB, gpt-5 64KB) — alternative de formatage |

## Exclusions conscientes
- **Hors-scope coding agent** (8 dossiers 🔴) : `Perplexity` (search/RAG), `NotionAi` (writing/workspace), `Warp.dev` (terminal uniquement), `dia` (browser chat), `Cluely` (assistant overlay), `Junie` (read-only explorer JetBrains), `Xcode` (actions Apple trop scopées), `Comet Assistant` (browser-agent Perplexity malgré 1060 lignes).
- **Frontend verrouillé** (🟡, utile seulement pour un Coder web) : `v0` (Vercel React/Next), `Lovable` (React/Vite/Tailwind/Supabase), `Same.dev` (clone UI), `Leap.new` (frontend-heavy), `Z.ai Code` (Next.js from scratch + anti-pattern « do not write test code »).
- **Padding narratif** : gros fichiers peu denses — `Google/Gemini/AI Studio vibe-coder.txt` (1644 L), `Anthropic/Claude Fable 5.txt` (1580 L), `Leap.new/Prompts.txt` (1237 L), `Anthropic/Claude Sonnet 4.6.txt` (1191 L), `Comet Assistant/System Prompt.txt` (1060 L), `Orchids.app` (1014 L), `Emergent` (946 L). Privilégier les 100-400 lignes.
- `assets/` (4 PNG logos), `README.md`, `LICENSE.md` : non pertinents.

## Correspondance avec `plan_usine_logicielle.md`
- **P0 (Spécialisation des Agents)** : cette référence est la **bibliothèque de patterns** pour les system_prompts spécialisés. Top 6 = bases concrètes par rôle (Codex CLI→Coder/Tester, Manus→architecture multi-agent, Augment→Router, Claude Code 2.0→Coder/Judge, Gemini CLI→workflow, Devin→`<think>` reasoning).
- **P0-bis (Invariants universels — NOUVEAU)** : les 10 invariants ci-dessus doivent devenir une section partagée par tous nos agents.
- **P6 (Judge / Findings / TDD)** : « professional objectivity » de Claude Code 2.0 = base du Reviewer ; « ne jamais modifier les tests » de Devin = règle Tester ; workflow verify-after (Gemini CLI) ; « fix root cause not surface » (Codex CLI).
- **P8 (Anti-boucle linter)** : Cursor « max 3 itérations puis ask user » = implémentation concrète de notre P3/P8.
- **Lacune assumée** : biais JS/TS/React — adapter pour Python/DSPy/smolagents.
