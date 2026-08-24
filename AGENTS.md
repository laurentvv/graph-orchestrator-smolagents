# AGENTS.md - Spécifications de l'Agent : Gestion de l'État sur Disque

# PARTIE 1 : DIRECTIVES POUR L'AGENT (PROMPT)

## 1. Principe Fondamental
Ne te fie jamais uniquement à ta fenêtre de contexte pour suivre l'avancement : elle s'altère, se compresse et s'efface. L'unique source de vérité = les trois fichiers de suivi à la racine + la base d'historisation DuckDB. À chaque initialisation, plantage ou redémarrage, lis-les et interroge l'historique pour reconstruire ton état de manière déterministe.

## 1-bis. Périmètre : l'Usine (ce dépôt) ≠ les Produits de l'Usine (`runs/`)
> ⚠️ **Avertissement anti-confusion pour les agents de codage** (assistants type ZCode) : ce projet
> contient DEUX niveaux de « code » qui ne doivent JAMAIS être confondus :
> 1. **LE GRAPHE — l'usine elle-même**, le programme que TU maintiens : `graph_orchestrator/` (nœuds,
>    prompts, gardes), `testers/`, `tests/`, `scripts/`, `skills/`, `debug/`, `prompts/`, fichiers
>    d'état (`feature_list.json`, `progress.md`, `contract.md`), `data/event_stream.duckdb`. Tout
>    cycle de développement (branche → tests → PR) s'applique À CE NIVEAU uniquement.
> 2. **LES LIVRABLES DU GRAPHE — les programmes que l'usine fabrique** lors de ses runs :
>    `runs/<dated>_<slug>/` (ex. visualiseur Bubble Sort : `index.html`, `styles.css`, `script.js`).
>    Ces artefacts sont la SORTIE de l'usine (gitignorés) — ce ne sont PAS les fichiers du projet.
>
> Conséquences opérationnelles :
> * Un bug constaté dans un livrable `runs/` est un **symptôme du comportement d'un nœud du graphe**
>   (prompt, skill, garde, modèle) : on diagnostique et on corrige L'USINE. On ne « répare » jamais un
>   livrable en place, sauf phase de validation/debug explicite (ex. boucle Coder isolée F-109).
> * Les commits/branches/PR ne concernent JAMAIS le contenu de `runs/` (gitignoré) — uniquement
>   l'usine et sa documentation.
> * **Distinction de contexte** : ce fichier `AGENTS.md` guide l'assistant de développement qui
>   travaille SUR l'usine ; il n'est PAS injecté aux nœuds LLM pendant les runs. La guidance runtime
>   des nœuds vit dans `graph_orchestrator/prompts.py` + `skills/` (budgétée par le gate F-103
>   `scripts/check_agent_guidance.py`). Ne justifie jamais d'une règle AGENTS.md un effet supposé sur
>   les runs du graphe, ni l'inverse.

## 2. Architecture des Fichiers à Initialiser

### A. `feature_list.json`
* **Rôle** : cartographie complète des fonctionnalités. **Cycle de vie** : générée à la planification initiale, mise à jour dès qu'une fonctionnalité change de statut.
* **Format strict** : `{"features": [{"id": "F-01", "name": "…", "description": "périmètre technique", "status": "pending | in_progress | completed", "dependencies": []}]}`

### B. `contract.md`
* **Rôle** : contrat de validation technique négocié entre planification et évaluation — assertions strictes et testables (viser 15-30 critères). **Cycle de vie** : figé juste avant la première ligne de code, plus modifiable par le générateur.
* **Format** : « Critères d'Acceptation Automatisés » (cases `- [ ]` numérotées) + « Protocole d'Évaluation » (commande `pytest`, zéro avertissement, zéro échec).

### C. `progress.md`
* **Rôle** : tableau de bord macroscopique du sprint — savoir instantanément ce qui est en cours après un redémarrage. **Cycle de vie** : mis à jour à la fin de chaque itération.
* **Format** : « Objectif Actuel » (cases à cocher) + « Jalons de l'Itération » (étapes cochées).

### D. Historisation Événementielle (DuckDB)
* **Rôle** : toute la mémoire événementielle de l'usine vit dans `data/event_stream.duckdb` (table `run_event`), JAMAIS dans un fichier texte plat (contexte préservé, requêtes post-mortem avancées).
* **Deux canaux d'écriture** : runtime (agents du graphe) = outil `log_event(event_type, details)` du Coder (`tools.py`, run_id courant) ; assistant IA (ZCode) = CLI `uv run python scripts/log_event.py <event_type> "<message>"` (options `--run-id`, `--date`). C'est LE geste de fin de cycle.
* **RÈGLE CRITIQUE — AUCUN JOURNAL PLAT** : l'ancien journal a été supprimé le 2026-08-14 (F-106), historique intégralement récupéré en base (199 événements datés, `run_id='legacy_md'`). Ne recrée JAMAIS ce fichier, n'append JAMAIS d'événement dans un `.md`. Historique git consultable (`git log -p --follow -- log.md`), ré-importable via `scripts/recover_log_history.py`.
* **Lecture post-mortem** : requêtes DuckDB directes sur `run_event` (colonnes `run_id`, `node`, `event_type`, `message`, `created_at`).

## 3. Directives Opérationnelles pour la Boucle d'Exécution
1. **Bootstrap** : vérifie les trois fichiers de suivi ; absents → crée-les selon les formats ci-dessus ; présents → lis-les pour reconstruire ta mémoire immédiate.
2. **Action** : avant d'exécuter une tâche, enregistre l'événement dans DuckDB (outil `log_event` côté graphe, CLI `scripts/log_event.py` côté assistant).
3. **Synchronisation** : après chaque écriture de fichier ou test, mets à jour le fichier de statut associé (`progress.md` ou `feature_list.json`).
4. **Gestion des erreurs** : si exception ou interruption, l'état valide = dernier événement enregistré dans DuckDB + assertions de `progress.md`.
5. **README** : mets à jour `README.md` à chaque nouvelle fonctionnalité importante terminée, avant de clore la tâche.
6. **INTERDICTION DE SUPPRESSION (RÈGLE CRITIQUE)** : ne **JAMAIS** supprimer ou vider `progress.md`, `feature_list.json`, `contract.md`, ni altérer/supprimer les bases du dossier `data/` (DuckDB, SQLite). Même si l'utilisateur demande un « full run de 0 » : ces fichiers/bases constituent ta mémoire d'agent et l'historique d'exécution ; ils n'ont aucun rapport avec les fichiers générés par l'orchestrateur.

# PARTIE 2 : GUIDE D'UTILISATION POUR LE DÉVELOPPEUR

## 4. Banque de Prompts de Test (Prompt-Vault)
Prompts classés par difficulté dans `references/Prompt-Vault/` (clone externe gitignoré — tout ajout : commité dans le clone ET reporté en copie trackée dans `prompts/`) : `Easy/`, `Medium/`, `Hard/`, `Advanced/` (un `.md` = un cahier des charges, souvent « 1 fichier `index.html`, HTML+CSS+JS vanilla »). Sommaire : `references/Prompt-Vault/README.md`.

## 5. Projets de Référence
* **Code et audits** : `docs/references-audit/` (lié au code GitHub dans `references/`) — implémentations production-éprouvées à réutiliser plutôt que réinventer.
* **Flags llama-server** : `docs/LLAMA_SERVER_FLAGS.md` — guide AVANT de changer `<PREFIX>_*` dans le `.env` (MTP, KV quant, cache-reuse, flags écartés, méthodo bench).
* **Cartographie Nœuds & Skills** : `docs/NODES_AND_SKILLS.md` — system prompts forcés par nœud, 11 skills, modes eager/lazy (F-57). À consulter pour savoir ce que voit chaque agent LLM à l'exécution.
* **Refactoring automatique des skills (F-92)** : `scripts/refactor_skills.py` découpe les `SKILL.md` > 80 lignes (sections secondaires → `resources/`, chargement lazy via `view_file`). À exécuter dès qu'un skill devient volumineux.
* **Doc Pydantic AI Harness en local (F-157, RÈGLE : SI UNE DOC EXISTE, LA LIRE AVANT DE CODER)** : `references/pydantic-ai-docs/` (gitignoré) contient la doc OFFICIELLE COMPLÈTE (262 pages) — `llms-full.txt` (5 Mo, markdown propre) + `INDEX.md` (titre → n° de ligne ; lecture ciblée : `sed -n '<début>,<fin>p' references/pydantic-ai-docs/llms-full.txt`) + crawl rendu. **Synthèse de lecture avec LIENS par page : `docs/PYDANTIC_AI_HARNESS_DOC_NOTES.md` (tracké) — à lire EN PREMIER** avant toute modif du Coder pydantic. Toute modif part de la page de doc concernée, pas d'hypothèses ; le site expose chaque page en `.md` direct (`https://pydantic.dev/docs/ai/<chemin>/index.md`) pour un re-fetch unitaire à jour.

## 6. Git & GitHub
* **Règle d'or Git** : ne JAMAIS travailler ou pousser directement sur `main`. Crée une branche (`feat/...` ou `fix/...`) avant toute modification.
* **Kilo Code Review** : l'agent GitHub doit approuver la PR avant le merge. Une fois la PR soumise, ARRÊTE-TOI (pas de boucle d'attente) — tu seras réveillé après validation pour supprimer la branche et revenir sur `main`.

## 7. Tests du Graphe (Workflow Coding)
0. **Modèles** : `powershell .\scripts\download_models.ps1` télécharge les `.gguf` requis (Qwen, Ornith) vers `models/`.
1. **Prompt** : copier un prompt de `references/Prompt-Vault/` dans `tasks.json` (`coding.content`) et adapter `target_files`.
2. **Config** : `WORKFLOW_MODE=coding` dans `.env` ; chemins GGUF (`FAST_MODEL`, `REASONING_MODEL`) pointant vers `models/` ; `FAST_BACKEND=spawn` et `REASONING_BACKEND=spawn`.
3. **Exécution** : `uv run agent_graph.py` (ajouter `PYTHONUNBUFFERED=1` si pipe).
4. **Déroulement** (diagramme complet : `README.md` § « Node Graph & Data Flow ») : PromptRefiner → Router → Architect → (Coder → Linter → Static Tester → Tester+Security → Judge, max 3 itérations par sous-tâche) → Escalation si circuit breaker.
* **Tiering modèles** (tous multimodaux) : `fast_model` (Qwen3.5-4B) → Coder, Router ; `reasoning_model` (Ornith-1.0-9B) → PromptRefiner, Architect, Drafter, Tester, Security, Judge, Escalation.
* **Audits séquentiels GPU-local** : `AUDIT_PARALLEL=false` (défaut) — Tester PUIS Security, sinon saturation VRAM.
* **Piège `filePath` screenshots (F-50/F-90)** : le Coder tend à appeler `take_screenshot(filePath=…)` → rejeté par chrome-devtools-mcp `--isolated` (aucun workspace root) → boucle de screenshots. FIX applicatif : `vision_callback.py` strippe `filePath` avant de déléguer (l'image revient via `observations_images`). Si une boucle de screenshots réapparaît : grep `Access denied` dans le log.
* Notes : valider le graphe avec **Bubble_Sort_Visualizer** (Easy, 1 fichier, borné). Toute modif de `.env.example` → reporter les ajouts dans `.env` local (sans toucher au contenu secret).

## 8. Amélioration Continue (Le Rôle du Meta-Analyste, F-61)
Boucle de feedback hybride Humain + IA :
1. **Exécution autonome** : lancer `uv run python scripts/run_analyzer.py` après un run E2E ou à la demande (`logs/run-<timestamp>-<mode>.log`).
2. **Analyse** : repérer les problèmes récurrents (parsing Pydantic, top-level `await`, crashes MCP). **RÈGLE — VÉRIFIER LA BASE EN MÊME TEMPS QUE LE LOG, ET AVANT ELLE** : à chaque diagnostic, interroger ce qui a été RÉELLEMENT enregistré en base (`run_event` de `data/event_stream.duckdb` + claims/refutations/verdicts du KG `data/graph_orchestrator.db`) en parallèle du log — c'est PLUS important que le log : la base contient ce que le graphe RELIT pour piloter la suite (tickets de correction, escalade), et l'enregistrement peut être lossy (snippet tronqué, résumé dérivé d'un fallback, doublons, erreur d'outil classée « assertion en échec ») alors que le log paraît sain. Leçon F164-6 (2026-08-24) : run entier faussé par une réfutation KG dupliquée + tronquée + mensongère → itération de correction aveugle sur un bug fantôme.
3. **Code pur d'abord** : se demander systématiquement « ce problème peut-il être résolu par du code PUR ? » — garde déterministe, sonde, auto-fixer. Fix mécanique prouvé par l'erreur → code pur ; diagnostic/jugement qualitatif → LLM.
4. **Recherche web en cas de blocage** : quand N itérations d'isolation n'avancent plus, chercher l'état de l'art (WebSearch : flags llama-server, samplers, formats). Tester sur un serveur spawned à la main avant d'intégrer (`docs/LLAMA_SERVER_FLAGS.md`).
5. **Arsenal pour forcer un format** : (a) **Prefill assistant** `CODER_PREFILL_CODE=true` (démarre physiquement dans ```python), (b) **Sampler DRY** `<PREFIX>_DRY_MULTIPLIER=0.8` (pénalise la répétition de séquences), (c) **Grammaires GBNF** (contrainte token-level), (d) **Gardes observationnelles** (filet applicatif).
6. **Validation humaine** : résumé clair + solution proposée, attendre le feu vert avant modification des règles.
7. **Application** : durcir code, prompts ou skills selon validation.

## 9. Tests Rapides par Nœud (Isolation LLM — F-89)
Un run E2E complet dure 30-40 min GPU-local ; valider la modif d'UN seul nœud (prompt, skill, config, logique) se fait en **secondes/minutes** via le script d'isolation du dossier `debug/` : chacun appelle la VRAIE fonction de production (0 mock) avec des entrées figées. C'est la boucle de debug itérative recommandée, AVANT tout run E2E. Convention complète : `debug/isolation/README.md`.

| Script | Nœud testé | Commande |
|---|---|---|
| `debug/run_router.py` | Router (classification langage) | `uv run python debug/run_router.py` |
| `debug/run_prompt_refiner.py` | PromptRefiner (meta-prompt) | `uv run python debug/run_prompt_refiner.py` |
| `debug/run_architect.py` | Architect (découpage + stratégie) | `uv run python debug/run_architect.py` |
| `debug/run_drafter.py` | Drafter (logique pure) | `uv run python debug/run_drafter.py` |
| `debug/run_security.py` | Security (audit OWASP) | `uv run python debug/run_security.py` |
| `debug/run_judge.py` | Judge (verdict final) | `uv run python debug/run_judge.py` |
| `debug/run_coder.py` | Coder (génération code) | `uv run python debug/run_coder.py` |
| `debug/run_web_tester_standalone.py` | Web Tester (assertions) | `uv run python debug/run_web_tester_standalone.py` |
| `debug/isolation/run_linter.py` | Linter (déterministe, 0 LLM) | `uv run python debug/isolation/run_linter.py` |
| `debug/validate_static_tester_live.py` | Static Tester (déterministe) | `uv run python debug/validate_static_tester_live.py` |
| `debug/run_verify.py` | Vérif exécutable F-100 (recette + readiness HTTP, 0 LLM) | `uv run python debug/run_verify.py [dossier]` |
| `debug/run_turn_checkpoint.py` | Checkpoint git par itération F-102 (0 LLM) | `uv run python debug/run_turn_checkpoint.py` |
| `debug/run_fs_safety.py` | Robustesse FS F-95 (transaction+crash-recovery, verrou cross-process, 0 LLM) | `uv run python debug/run_fs_safety.py` |
| `debug/test_mtp_spec.py` | Compat/bench MTP spéculatif llama-server (A/B `--spec-type draft-mtp`, 0 LLM) | `uv run python debug/test_mtp_spec.py [--only fast\|reasoning\|no_think] [--ctx N]` |
| `debug/bench_prefill_flags.py` | Bench préfill flags FAST (`--cache-reuse`, `-ub`), multi-tours simulé (0 LLM) | `uv run python debug/bench_prefill_flags.py [--ctx N] [--turns N]` |
| `debug/diag_grammar_f160.py` / `replay_request_f160.py` / `trace_mcp_calls_f160.py` | F-160 : grammaire llama-server vs `tool_choice`, rejeu variants, trace appels MCP | `uv run python debug/<script>.py` |
| `debug/run_browser_pool.py` | Pool navigateur F-163 (Chrome unique/run, 0 LLM) | `uv run python debug/run_browser_pool.py` |

Boucle : identifier le nœud impacté → lancer son script → observer le verdict → couper si erreur, corriger, relancer. Input ad hoc : scénario nommé (`debug/run_judge.py bug`), prompt en CLI (`debug/run_router.py "ma description"`), ou `@fichier`. Une fois le nœud validé isolément, relancer l'E2E complet (§7). Détail technique : les nœuds DSPy ignorent le paramètre `*_model` — le vrai modèle vient de `_run_dspy_node → model_lifecycle(spec)` qui spawn son propre llama-server ; les scripts reproduisent fidèlement ce comportement.

## 10. Runs de Référence (Golden Runs)
- **Run historique Bubble Sort** : `debug/reference_run_qwen4b_bubble_sort/` — 1768 s GPU local, Coder 2 itérations, Qwen-4B + Ornith-9B.
- **Première approbation E2E (2026-08-17, run #11)** : `debug/reference_run_2026-08-17_first_e2e_approval/` — Tester LLM détecte un bug, correction chirurgicale du 4B, Judge approuve (~23 min, 14,3 M tokens).
- **Livrable parfait en une itération (2026-08-18, run #19)** : `debug/reference_run_2026-08-18_run19_perfect_deliverable/` — 100 % conforme en une itération (~14 min, 21 steps), préservation artefacts F-120 (`plan.md`, `task.md`, `draft.md`). Leçon : le 4B suit le plan à la lettre, un prompt/draft sain vaut mieux que des corrections aval.

## 11. Maintenance Régulière des Dépendances et de Python (F-98)
1. **Exécution** : à la demande de l'utilisateur ou lors des cycles de maintenance, monter les dépendances via `uv lock --upgrade` + `uv sync` (ou `scripts/upgrade_stack.py`).
2. **Validation immédiate (non-régression)** : lancer `pytest` après toute mise à niveau, diagnostiquer conflits d'API/ruptures de signatures, adapter tests/middlewares.
3. **Validation E2E + rapport** : confirmer la stabilité via un run d'isolation ou de graphe, présenter la synthèse des montées majeures/mineures, préparer la PR dédiée.
4. **llama.cpp vendé (F-123, veille hebdo)** : `uv run python scripts/update_llamacpp.py` (check seul ; `--apply` = télécharge, vérifie les flags, swap avec backup `.bak`). Jamais d'`--apply` sans validation post-swap (`debug/test_mtp_spec.py --only reasoning` + tests). Guide : `docs/LLAMA_SERVER_FLAGS.md`.
