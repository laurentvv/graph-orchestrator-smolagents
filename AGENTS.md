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
Prompts de test classés par difficulté dans `references/Prompt-Vault/` (clone externe de `laurentvv/Prompt-Vault`, gitignoré — tout ajout : commité dans le clone ET reporté en copie trackée dans `prompts/`, sinon perdu au re-clone) : `Easy/` (Bubble_Sort_Visualizer, Color_Palette_Generator, ToDo_List), `Medium/` (Sorting_Visualization, Pixel_Art_Editor), `Hard/` (Kanban_Board, Markdown_Editor_Desktop, Local_OCR, Tetris_Modern_Game), `Advanced/` (LLM_Speedometer, Feed_Aggregator, Hantavirus_Simulation, File_Listing). Chaque `.md` = un cahier des charges structuré (souvent « 1 fichier `index.html`, HTML+CSS+JS vanilla »). Tableau récapitulatif : `references/Prompt-Vault/README.md`.

## 5. Projets de Référence
* **Code et audits** : `docs/references-audit/` (lié au code GitHub stocké dans `references/`) — implémentations production-éprouvées à réutiliser plutôt que de réinventer.
* **Flags llama-server** : `docs/LLAMA_SERVER_FLAGS.md` — guide de décision pour intégrer un nouveau modèle GGUF (MTP spéculatif, KV quant, cache-reuse, flags écartés avec preuves, méthodologie de bench). À consulter AVANT de changer `<PREFIX>_*` dans le `.env`.
* **Cartographie Nœuds & Skills** : `docs/NODES_AND_SKILLS.md` — system prompts forcés par nœud, 11 skills, modes eager/lazy (F-57). À consulter pour savoir ce que voit chaque agent LLM à l'exécution.
* **Refactoring automatique des skills (F-92)** : `scripts/refactor_skills.py` découpe les `SKILL.md` > 80 lignes (sections secondaires → `resources/`, chargement lazy via `view_file`). À exécuter dès qu'un skill devient volumineux.

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
Boucle de feedback hybride Humain + IA (pas d'agent local autonome) :
1. **Exécution autonome** : c'est TOI (l'assistant) qui lances `uv run python scripts/run_analyzer.py` après un run E2E ou à la demande (chaque run est journalisé dans `logs/run-<timestamp>-<mode>.log`).
2. **Analyse** : lire la sortie, repérer les problèmes récurrents (ex. parsing Pydantic, top-level `await`, crashes d'outils MCP).
3. **Validation humaine** : JAMAIS modifier les règles à l'aveugle — résumé clair + solution proposée (ex. « durcir cette règle dans `nodes.py` »), attendre le feu vert.
4. **Application** : intervenir dans le code source pour durcir prompts ou skills.
*Exemples réels* : interdiction du top-level `await` Puppeteer + déclarations de fonction pour `evaluate_script` ; triples quotes `r"""…"""` + Monkey Testing pour stabiliser le 4B.

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
| `debug/run_turn_checkpoint.py` | Checkpoint git par itération F-102 (snapshot sans contamination, 0 LLM) | `uv run python debug/run_turn_checkpoint.py` |
| `debug/run_fs_safety.py` | Robustesse FS F-95 (transaction+crash-recovery, verrou cross-process, cloisonnement IO, 0 LLM) | `uv run python debug/run_fs_safety.py` |
| `debug/test_mtp_spec.py` | Compatibilité/bench MTP spéculatif llama-server (A/B baseline vs `--spec-type draft-mtp`, 0 LLM) | `uv run python debug/test_mtp_spec.py [--only fast\|reasoning\|no_think] [--ctx N]` |
| `debug/bench_prefill_flags.py` | Bench préfill flags FAST (`--cache-reuse`, `-ub`), charge agent multi-tours simulée (0 LLM) | `uv run python debug/bench_prefill_flags.py [--ctx N] [--turns N]` |

Boucle : identifier le nœud impacté → lancer son script → observer le verdict → couper si erreur, corriger, relancer. Input ad hoc : scénario nommé (`debug/run_judge.py bug`), prompt en CLI (`debug/run_router.py "ma description"`), ou `@fichier`. Une fois le nœud validé isolément, relancer l'E2E complet (§7). Détail technique : les nœuds DSPy ignorent le paramètre `*_model` — le vrai modèle vient de `_run_dspy_node → model_lifecycle(spec)` qui spawn son propre llama-server ; les scripts reproduisent fidèlement ce comportement.

## 10. Run de Référence (Golden Run)
Run E2E parfait sauvegardé définitivement : `debug/reference_run_qwen4b_bubble_sort/` — fichiers générés complets, draft de l'Architecte, journal d'exécution (`run_full.log`) avec tableau d'observabilité. Métriques clés : 1768 s (~29,5 min) GPU local ; 648 748 tokens ; Coder 2 itérations (la 1ère corrigée par les gardes, la 2e validée par la boucle F-45) ; Qwen-4B (Coder) + Ornith-9B (Architect/Judge). Étalon-or prouvant que petits modèles + Monkey Testing + guardrails syntaxiques produisent des apps Vanilla JS complexes de manière fiable.

**Validation moderne (2026-08-17, runs #10-#11, post-mortems `debug/POSTMORTEM_RUN10/11.md`)** : la PREMIÈRE APPROBATION E2E complète avec la pile de gardes actuelle (run #11, `STATIC_TESTER_ENABLED=0`) — Tester LLM trouve un vrai bug → fail-closed F-108 → le 4B corrige chirurgicalement (feedback qualitatif précis) → re-test ciblé F-52 → Security → Judge APPROUVE (~23 min, 14,3 M tokens). **Run préservé : `debug/reference_run_2026-08-17_first_e2e_approval/`** (livrables approuvés + draft + log complet + historique git du run — la correction = « Iteration 2, script.js +2 insertions » — + archives de compaction ; README local détaille tout). Le run #10 (gardes actives) valide F-114/F-115 et prouve le refus déterministe (3× Static Tester, escalade propre, 0 faux positif d'approbation). Leçons clés : (1) le rituel screenshot → 6× `visual_check` → final_answer est la clé de convergence du 4B (0 appel → 60 appels entre run #9 et #10) ; (2) cap `fullPage` indispensable (images 9 315 px = timeouts 600 s) ; (3) le 4B sait CORRIGER avec un feedback qualitatif précis — qualité du feedback > escalade de modèle.

**Livrable PARFAIT (2026-08-18 22:09, run #19, épilogue `debug/POSTMORTEM_RUN13.md`)** : après **7 runs E2E le même jour** en boucle méta-analyste à chaud (chaque défaut → garde déterministe ou consigne amont : sonde gradient, 3 étages géométrie barres, snapshot PRE-clic chargement, compteur statique (a-bis) v1/v2), le run #19 produit un livrable **100 % conforme en UNE itération** (~14 min, 21 steps) : chargement 29/30 barres visibles (4→250px proportionnelles), compteur VIVANT 0→249, tri 30/30 croissant, validé jusqu'à l'œil humain. **Run préservé : `debug/reference_run_2026-08-18_run19_perfect_deliverable/`** (livrables + PREMIÈRE préservation des artefacts F-120 plan.md/task.md + draft dont la géométrie flex-end prescrite prouve le Fix B + log + git history à commit unique + 8 logs llama ; README local détaille le tableau des 7 runs). Leçon clé : le 4B suit le PLAN à la lettre — un prompt Architect sain (règles génériques, pas la solution) vaut mieux que 10 corrections aval ; les échecs documentés d'une journée deviennent les leçons cross-run du lendemain (F-68). Mur restant identifié : F-116 (compaction contexte Coder — thrashs #13/#16).

## 11. Maintenance Régulière des Dépendances et de Python (F-98)
1. **Exécution** : à la demande de l'utilisateur ou lors des cycles de maintenance, monter les dépendances via `uv lock --upgrade` + `uv sync` (ou `scripts/upgrade_stack.py`).
2. **Validation immédiate (non-régression)** : lancer `pytest` après toute mise à niveau, diagnostiquer conflits d'API/ruptures de signatures, adapter tests/middlewares.
3. **Validation E2E + rapport** : confirmer la stabilité via un run d'isolation ou de graphe, présenter la synthèse des montées majeures/mineures, préparer la PR dédiée.
4. **llama.cpp vendé (F-123, veille hebdo)** : `uv run python scripts/update_llamacpp.py` (check seul ; `--apply` = télécharge, vérifie les flags, swap avec backup `.bak`). Jamais d'`--apply` sans validation post-swap (`debug/test_mtp_spec.py --only reasoning` + tests). Guide : `docs/LLAMA_SERVER_FLAGS.md`.
