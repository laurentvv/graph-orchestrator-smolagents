# 02 — aider

## En-tête
- **Nom** : aider (package PyPI `aider-chat`)
- **Chemin** : `references/aider/`
- **Type** : AI pair-programming CLI mature (le projet cible `graph-orchestrator-smolagents` en dérive explicitement : `RepoGraph` descend de `RepoMap`)
- **Langage principal** : Python (100%)
- **Statistiques** : 336 fichiers pertinents (.md/.py/.json/.yaml/.toml/.txt) hors `.git/` ; 80 fichiers `.py` dans `aider/aider/` (dont 38 dans `coders/`) ; repo total ~215 MB dont ~56 MB de mp4 dans `website/`

## Synthèse
Aider est l'AI coding agent CLI de référence, mature et très largement adopté (top 20 OpenRouter, 6.8M installs PyPI). Sa valeur pour le projet cible est triple :

1. **Formats d'édition robustes** — aider propose 12 edit-formats (`whole`, `diff`=SEARCH/REPLACE, `udiff`, `patch`=V4A/apply_patch, `diff-fenced`, `editor-*`, `architect`, `ask`, `context`, `help`) avec parsing + application tolérants aux erreurs (fuzzy match, réindentation relative, diff-match-patch, cherry-pick git). C'est l'alternative directe au "whole-file rewrite" actuel des Coders de `graph-orchestrator-smolagents`.
2. **RepoMap (PageRank + tree-sitter)** — source originale dont `RepoGraph` dérive : extraction de tags `def`/`ref` via tree-sitter (`grep_ast`), construction d'un `nx.MultiDiGraph`, ranking par `nx.pagerank(personalization=chat_files)`, cache `diskcache`, budget `map_tokens`.
3. **Pattern Architect → Editor** — `ArchitectCoder` (Brains) propose une description de changement, puis délègue l'application à un `EditorCoder` (Hands) avec `editor_model` + `editor_edit_format`, `map_tokens=0`. Exactement le pattern Routeur → Architect → Coders du projet cible.

Bonus : `scrape.py` (Playwright + httpx + pypandoc pour mode research/web testing), `linter.py` (lint post-édit avec tree_context), `commands.py` (~40 commandes slash), `diffs.py` (live-diff streaming avec progress bar). Note de réutilisabilité globale : **Haute**.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/aider/aider/website/docs/more/edit-formats.md` | Tableau comparatif des edit-formats supportés | Haute |
| `references/aider/aider/website/_posts/2024-09-26-architect.md` | Article blog sur le mode architect (Brains/Hands) | Haute |
| `references/aider/aider/website/_posts/2023-10-22-repomap.md` | Article fondateur sur le RepoMap | Haute |
| `references/aider/aider/website/examples/semantic-search-replace.md` | Exemple annoté SEARCH/REPLACE | Haute |
| `references/aider/aider/website/docs/repomap.md` | Doc conceptuelle du RepoMap (ctags, ranking, map_tokens) | Moyenne |
| `references/aider/aider/website/docs/unified-diffs.md` | Rationale du format udiff | Moyenne |
| `references/aider/aider/website/docs/usage/lint-test.md` | Usage du lint/test auto post-édit | Moyenne |
| `references/aider/aider/website/docs/usage/browser.md` | Doc scraping web (Playwright/pandoc) | Moyenne |
| `references/aider/aider/website/_posts/2024-05-22-linting.md` | Rationale du linter intégré | Moyenne |
| `references/aider/README.md` | Présentation produit, features, exemples CLI, badges | Faible |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/aider/aider/coders/editblock_coder.py` | `EditBlockCoder` (edit_format=`"diff"`), `find_original_update_blocks`, `do_replace`, `replace_most_similar_chunk`, `perfect_or_whitespace`, `try_dotdotdots`, `replace_part_with_missing_leading_whitespace`, `find_similar_lines` | Format SEARCH/REPLACE (`<<<<<<< SEARCH` / `=======` / `>>>>>>> REPLACE`). Parsing du stream LLM, application tolérante : match exact → match sans whitespace de tête → ellipsis `...` → fuzzy `SequenceMatcher`. Génère messages d'erreur "Did you mean" pour re-prompting | **Haute** | Alternative robuste au whole-file rewrite pour fiabiliser les Coders ; stratégies de fallback à réutiliser telles quelles |
| `references/aider/aider/coders/editblock_prompts.py` | `EditBlockPrompts` (`main_system`, `system_reminder`, `example_messages`, `rename_with_shell`, `go_ahead_tip`) | Prompt canonique du format SEARCH/REPLACE : règles explicites, 2 exemples few-shot (modify + new file), rappels système | **Haute** | Prompt éprouvé à copier/adapter pour DSPy/smolagents |
| `references/aider/aider/coders/search_replace.py` | `RelativeIndenter` (`make_relative`/`make_absolute`), `dmp_apply`, `dmp_lines_apply`, `map_patches`, `flexible_search_and_replace`, `search_and_replace`, `git_cherry_pick_osr_onto_o`, `diff_lines`, `all_preprocs`, `editblock_strategies`, `udiff_strategies` | Moteur d'application d'edits multi-stratégies : (a) réindentation relative pour normaliser whitespace, (b) `diff_match_patch` char/line-level, (c) cherry-pick git comme méthode de fallback, (d) pré-processeurs | **Haute** | Cœur de la robustesse d'application ; rare et précieux |
| `references/aider/aider/repomap.py` | `RepoMap` (`get_repo_map`, `get_ranked_tags`, `get_ranked_tags_map`, `get_tags_raw`, `render_tree`, `to_tree`, `token_count`), `Tag` namedtuple, `load_tags_cache`, `nx.pagerank(personalization=...)` | Source originale de `RepoGraph`. Pipeline : tree-sitter SCM queries → tags `def`/`ref` → `nx.MultiDiGraph` pondéré (snakes/camel/kebab boost, `_` penalty, `sqrt(num_refs)`) → PageRank personnalisé par fichiers en chat → ranking des définitions → rendu `TreeContext` sous budget `map_tokens`. Cache `diskcache` v3/v4 + fallback dict sur erreur SQLite | **Haute** | Étudier pour aligner/calibrer `RepoGraph` (pondérations, personalization, fallback cache) |
| `references/aider/aider/coders/architect_coder.py` + `references/aider/aider/coders/architect_prompts.py` | `ArchitectCoder.reply_completed` (edit_format=`"architect"`), `ArchitectPrompts` (`main_system` "expert architect engineer… provide direction to your editor engineer") | Pattern Brains/Hands : après réponse de l'architect, crée un `Coder.create(main_model=editor_model, edit_format=editor_edit_format, map_tokens=0, suggest_shell_commands=False, cache_prompts=False)` et lance `editor_coder.run(with_message=content)` | **Haute** | Modèle direct pour l'étape Architect → Coders du workflow cible |
| `references/aider/aider/coders/patch_coder.py` + `references/aider/aider/coders/patch_prompts.py` | `PatchCoder` (edit_format=`"patch"`), `Patch`, `PatchAction`, `Chunk`, `ActionType`, `find_context_core`, `find_context`, `peek_next_section`, `_parse_patch_text`, `_apply_update`, `identify_files_needed` ; `PatchPrompts` | Format V4A / apply_patch (`*** Begin Patch`, `*** Update File:`, `*** Add File:`, `*** Delete File:`, `*** Move to:`, `*** End of File`, `@@scope@@`). Parser complet + applicateur avec niveaux de fuzz (exact → rstrip → strip). Support move/rename | **Haute** | Format moderne (GPT-5 era), le plus structuré ; bon candidat pour des éditions fiables multi-fichiers |
| `references/aider/aider/scrape.py` | `Scraper` (`scrape`, `scrape_with_playwright`, `scrape_with_httpx`, `html_to_markdown`, `looks_like_html`, `try_pandoc`), `slimdown_html`, `install_playwright`, `has_playwright`, `aider_user_agent` | Extraction web : Playwright (Chromium headless, masque "Headless" du UA, `wait_until="networkidle"`) en prioritaire, fallback `httpx`, conversion HTML→Markdown via `pypandoc` + `BeautifulSoup` | **Haute** | Réutilisable pour le mode "research/web testing" du projet cible |
| `references/aider/aider/coders/editor_editblock_coder.py` + `references/aider/aider/coders/editor_editblock_prompts.py` | `EditorEditBlockCoder` (edit_format=`"editor-diff"`), `EditorEditBlockPrompts` | Variante "Hands pure" du SEARCH/REPLACE : sous-classe `EditBlockCoder` avec prompt épuré (pas de shell, pas de go_ahead_tip). C'est le coder réellement instancié par `ArchitectCoder` | **Haute** | C'est le "Hands" concret du pattern Architect |
| `references/aider/aider/coders/udiff_coder.py` + `references/aider/aider/coders/udiff_prompts.py` | `UnifiedDiffCoder` (edit_format=`"udiff"`), `find_diffs`, `process_fenced_block`, `hunk_to_before_after`, `apply_hunk`, `apply_partial_hunk`, `make_new_lines_explicit`, `normalize_hunk` ; `UnifiedDiffPrompts` | Format unified-diff `diff -U0` (hunks `@@ ... @@`, lignes `+`/`-`/` `). Application par recherche de contexte + reconstruction de hunks | Moyenne | Alternative valide au SEARCH/REPLACE, mais udiff est plus fragile sur l'indentation |
| `references/aider/aider/linter.py` | `Linter` (`lint`, `py_lint`, `run_cmd`, `set_linter`), `LintResult`, `basic_lint`, `lint_python_compile`, `tree_context`, `find_filenames_and_linenums` | Lint post-édit multi-langage : cmd configurable par langage, fallback `basic_lint` (regex) + `compile()` pour Python, rendu `TreeContext` montrant la zone d'erreur | Moyenne | Utile pour boucle Tester/Judge auto-fix |
| `references/aider/aider/commands.py` | `Commands` (~40 méthodes `cmd_*` : `cmd_add`, `cmd_drop`, `cmd_commit`, `cmd_lint`, `cmd_test`, `cmd_run`, `cmd_diff`, `cmd_undo`, `cmd_clear`, `cmd_web`, `cmd_architect`, `cmd_ask`, `cmd_code`, `cmd_context`, `cmd_map`, ...), `do_run` | Système de commandes slash complet | Moyenne | Patron pour le routeur de commandes |
| `references/aider/aider/diffs.py` | `diff_partial_update`, `find_last_non_deleted`, `create_progress_bar`, `assert_newlines` | Diff unifié partiel pendant le streaming LLM, avec barre de progression lignes traitées | Moyenne | Pour UX de streaming des Coders |
| `references/aider/aider/coders/base_coder.py` + `references/aider/aider/coders/base_prompts.py` | `Coder` (classe abstraite, `edit_format`, `gpt_prompts`, `partial_response_content`, `abs_fnames`, `abs_root_path`, `get_inchat_relative_files`), `CoderPrompts` (`files_content_prefix`, `lazy_prompt`, `overeager_prompt`, `repo_content_prefix`) | Socle commun : cycle get_edits → apply_edits, gestion fichiers en chat, prompts partagés | Moyenne | Architecture de référence pour un Coder abstrait |
| `references/aider/aider/coders/wholefile_coder.py` + `references/aider/aider/coders/wholefile_prompts.py` | `WholeFileCoder` (edit_format=`"whole"`, `get_edits`, `apply_edits`, `do_live_diff`, `render_incremental_response`) ; `WholeFilePrompts` | Format whole-file (réécrit fichier entier dans fence). Live-diff streaming via `diffs.diff_partial_update`. C'est l'approche actuelle du projet cible | Moyenne | À comparer pour mesurer le gain des formats search/replace |
| `references/aider/aider/coders/editor_whole_coder.py` + `references/aider/aider/coders/editor_whole_prompts.py` | `EditorWholeFileCoder` (edit_format=`"editor-whole"`), `EditorWholeFilePrompts` | Variante "Hands" du whole-file | Moyenne | |
| `references/aider/aider/coders/editblock_fenced_coder.py` + `references/aider/aider/coders/editblock_fenced_prompts.py` | `EditBlockFencedCoder` (edit_format=`"diff-fenced"`) | SEARCH/REPLACE avec fence quadruple-backtick (pour modèles qui interprètent mal le triple) | Moyenne | |
| `references/aider/aider/coders/__init__.py` | `__all__` | Registre des 12 coders exportés (HelpCoder, AskCoder, Coder, EditBlockCoder, EditBlockFencedCoder, WholeFileCoder, PatchCoder, UnifiedDiffCoder, UnifiedDiffSimpleCoder, ArchitectCoder, EditorEditBlockCoder, EditorWholeFileCoder, EditorDiffFencedCoder, ContextCoder) | Moyenne | Cartographie des edit-formats |
| `references/aider/aider/models.py` | `Model` (`edit_format` default `"whole"`, `editor_model_name`, `editor_edit_format`, `get_editor_model`) | Mapping modèles→edit_format (GPT-5 family → `"diff"`, certains → `"udiff"`) | Moyenne | Guide de calibration modèle→format |
| `references/aider/aider/coders/udiff_simple.py` + `udiff_simple_prompts.py` | `UnifiedDiffSimpleCoder` (edit_format=`"udiff-simple"`) | Variante simplifiée d'udiff | Faible | |
| `references/aider/aider/coders/ask_coder.py` + `ask_prompts.py` | `AskCoder` (edit_format=`"ask"`) | Mode question sans édition | Faible | |
| `references/aider/aider/coders/context_coder.py` + `context_prompts.py` | `ContextCoder` (edit_format=`"context"`) | Chargeur de contexte read-only | Faible | |
| `references/aider/aider/coders/help_coder.py` + `help_prompts.py` | `HelpCoder` (edit_format=`"help"`) | Réponses aux questions d'aide | Faible | |
| `references/aider/aider/coders/editblock_func_coder.py` + `editblock_func_prompts.py` ; `wholefile_func_coder.py` + `wholefile_func_prompts.py` ; `single_wholefile_func_coder.py` + `single_wholefile_func_prompts.py` | `EditBlockFunctionCoder`, `WholeFileFunctionCoder`, `SingleWholeFileFunctionCoder` | Variantes "function-calling" (édits passés via tool calls plutôt que texte) | Faible | |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/aider/aider/resources/model-settings.yml` | config | Mapping modèle → `edit_format`, `editor_model`, `editor_edit_format`, weak_model, params. Référence pour calibrer le projet cible |
| `references/aider/aider/resources/model-metadata.json` | config | Métadonnées de modèles (context window, pricing, etc.) |
| `references/aider/aider/queries/tree-sitter-language-pack/` + `tree-sitter-languages/` | spec (SCM) | Requêtes tree-sitter (fichiers `*.scm`) pour extraire `def`/`ref` par langage — cœur du RepoMap |
| `references/aider/pyproject.toml` | config | Définition du package `aider-chat`, dépendances, entry points |
| `references/aider/requirements.txt` + `requirements/*.txt` | config | Dépendances (dont `tree-sitter`, `grep_ast`, `networkx`, `diskcache`, `diff_match_patch`, `playwright`, `pypandoc`, `litellm`) |

## Exclusions conscientes
- `references/aider/aider/website/` (~142 `.md`, ~56 MB de `.mp4`, assets audio/json, `_posts/`, `_data/` leaderboards, `_includes/`) : docs du site Jekyll + médias, hors périmètre code. Seuls quelques `.md` conceptuels sont remontés en section doc.
- `references/aider/benchmark/` (10 `.py` + `swe-bench*.txt` fixtures) : harnais swe-bench, non détaillé.
- `references/aider/tests/` (~5.7 MB, ~80 fichiers `test_*.py`) : non audité en détail, mais riche en cas de test pour les edit-formats (`test_editblock.py`, `test_coder.py`, `test_udiff.py`).
- `references/aider/scripts/` (16 `.py`) : scripts de maintenance du repo (blame, history, versionbump), non pertinents.
- Modules périphériques `voice.py`, `watch.py`, `copypaste.py`, `gui.py`, `onboarding.py`, `analytics.py`, `editor.py`, `mdstream.py`, `waiting.py`, `watch_prompts.py` : fonctionnalités non pertinentes pour le projet cible.
