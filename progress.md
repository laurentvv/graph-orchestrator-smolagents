# État d'Avancement du Sprint

## Objectif Actuel
- [x] Valider le coding workflow de bout en bout sur un prompt "landing page premium"
      (Architect → Coder → Tester → Judge → verdict). ATTEINT (run #12 HTML propre,
      run #13 cycle complet + reprise après crash multi-crash).
- [x] Ajouter `browser-use` aux références et exécuter le workflow d'audit. TERMINÉ.
- [x] Cycle CHROME DEVTOOLS MCP + VALIDATION VISUELLE (F-45) : auto-validation visuelle
      du Coder (screenshot vu par gemma-4-E4B multimodal avant final_answer) + complément
      d'outils DevTools au WebTester (cumul avec Puppeteer, pas de suppression).
      Implémentation TERMINÉE (28 tests, 521 passed / 0 failed). Validation run à venir.
- [x] Cycle CHECKLIST FONCTIONNALITÉS + FIXES ROBUSTESSE GPU-LOCAL (F-46) : 3 runs de
      validation Bubble Sort ont révélé Security silencieux (VRAM saturée par parallélisme),
      Coder générant du TypeScript en vanilla, et Tester oubliant des fonctionnalités.
      Fixes (AUDIT_PARALLEL=false, max_steps 24→12, anti-TS, console obligatoire, règle 2
      essais) + checklist parsée forcée (1 assertion/fonctionnalité). Implémentation
      TERMINÉE (14 tests, 535 passed / 0 failed).
- [ ] Cycle TESTER POLYVALENT + AUTO-CORRECTION stderr (Priorité 2) : dispatch
      multi-techno (web+python) + troncature anti Context-Overflow. En cours.
- [ ] Cycle CONTEXT7 (doc libs à jour, anti-hallucination d'API) : intégration sur
      3 nœuds + skill stratégique. Implémentation TERMINÉE, validation runs à venir.
- [x] Cycle TESTER FONCTIONNEL (assertions comportementales, F-20) : le tester ne
      testait que l'absence de crash → bugs de logique validés à tort. Implémentation
      TERMINÉE (skill puppeteer_* + assertions, propagation spec, Judge équipé).
- [x] POST-MORTEM RUN 123955 (F-61 amélioration continue) : 3 bugs récurrents détectés
      par `run_analyzer.py` et corrigés sur la branche `fix/postmortem-run-123955` :
      (1) **Security fail-open CRITIQUE** — `security_res=None` (audit KO) était
      silencieusement transformé en "Aucune vulnérabilité" → le Judge approuvait à
      l'aveugle un code non audité (bs-001 APPROUVÉ juste après Error LLM). Fix :
      hard block fail-closed dans `execute_code_judge_node` (retour `is_approved=False`
      SANS appel LLM) + traçage KG de l'échec Security.
      (2) **Tester `click` forbidden (6×)** — l'allowlist DevTools filtrait `click`/`fill`
      alors que la doc les recommandait → smolagents rejetait l'appel. Fix : `click`/`fill`
      ajoutés à l'allowlist `chrome_devtools_tool.py`.
      (3) **Coder `}` au lieu de `)` (6×)** — quand `search_replace(new_string="<JS>")`
      contient des accolades, le modèle fermait l'appel Python par `}`. Fix : règle n°8
      dans le prompt Coder + section dédiée dans le skill coding (miroir du bloc IIFE
      web-tester). Implémentation TERMINÉE (42 tests sur les 3 zones, 692 passed / 7
      pré-existants non liés).

## Jalons de l'Itération (cycle F-72 — Prompt Offloading)
> Priorité 10 du plan usine logicielle (volet Prompt Offloading). Encapsuler la complexité
> (snippets JS, algorithmes) dans des OUTILS Python dédiés au lieu de l'injecter en texte
> brut dans les prompts système. Modèle cité en réf : Web Tester (`puppeteer_clean_dom` /
> `puppeteer_add_visual_tags`). **Découverte clé : ce « modèle » était CASSÉ** — il wrappait
> `puppeteer_evaluate` (navigateur Puppeteer qui ne charge PAS les `file://` locaux → DevTools
> est devenu le pilote primaire). Le prompt du Tester disait même de NE PAS les utiliser. F-72
> recrée ces helpers en version DevTools, plus `check_js_syntax` et la centralisation de la doc.

- [x] F72-1 : Module `js_utils.py` — extraction DRY de `run_node_check` + `MAX_JS_CHARS` depuis
  `static_tester.py` (alias privés `_run_node_check`/`_MAX_JS_CHARS` préservent l'appelant, imports
  morts `subprocess`/`tempfile` retirés, 0 changement comportemental). Partagé Static Tester
  Tier 1a + futur outil Coder.
- [x] F72-2 : Outil `@tool check_js_syntax(path)` (tools.py, Coder) — auto-validation verify-after
  de la syntaxe JS via `node --check` ; détection `node` absent upfront (`shutil.which` → message
  informatif, n'affirme jamais 'valide' à tort) ; retrait de l'exemple subprocess `node --check`
  du prompt Coder (→ mention de l'outil).
- [x] F72-3 : Module `devtools_dom_tools.py` — 3 sous-classes `Tool` (`clean_dom`, `add_visual_tags`,
  `fuzz_click_all_buttons`) wrappent `evaluate_script` (DevTools) via `function=<JS>` ; snippets JS
  corps préservés EXACTS, adaptation `script=`→`function=` + retrait enveloppe IIFE (DevTools exige
  une fonction NON invoquée, une IIFE crasherait le CDP). Factory `build_devtools_helper_tools`
  fail-open. **Répare le modèle cassé.**
- [x] F72-4 : WebTester — retrait du bloc Puppeteer mort (`PuppeteerAddVisualTagsTool`/
  `PuppeteerCleanDomTool`) + branchement `build_devtools_helper_tools(cdt_tools)` ; prompt màj
  (les 3 outils désormais DevTools-based et OK à utiliser) ; 2 skills `web-tester/resources/` màj
  cohérence (`puppeteer_clean_dom`→`clean_dom` ; note « À ÉVITER » → « OK sur le navigateur actif »).
- [x] F72-5 : Coder — branchement `build_devtools_helper_tools(cdt_tools)` + retrait du snippet
  fuzzing inline du `preview_block` (étape 3 → `fuzz_click_all_buttons()`).
- [x] F72-6 : Centralisation doc DevTools — `DEVTOOLS_BASE_DOC` (chrome_devtools_tool.py, signatures
  communes `navigate_page`/`list_console_messages`/`evaluate_script` + anti-IIFE CRITIQUE, single
  source of truth) partagée Coder (`_DEVTOOLS_TOOLS_DOC`) + Tester (`devtools_hint`, ajoute
  `take_snapshot`/`click`/`fill`/`take_screenshot` + filePath/visual bug/python builtins). Couverture
  point-par-point vérifiée (0 marqueur perdu vs 6 points doc Coder + 13 points hint Tester).
- [x] F72-7 : Validation — py_compile OK (7 fichiers). **19 nouveaux tests PASS** (js_utils 5 +
  devtools_dom_tools 10 + tools +4). Suite complète **940 passed / 8 failed** (les 8 STRICTEMENT
  pré-existants `test_read_gate`×4 + `test_skill_lazy_loading`×3 + `test_guard`×1, documentés
  F-97/F-82, AUCUN lié à F-72). **0 régression.** État disque synchronisé (feature_list F-72
  completed, contract C337-C344, plan_usine case P10 cochée, progress).

## Jalons de l'Itération (cycle F-93 — Grounding des findings Judge, P6)
> Anti-hallucination de localisation. Le Judge exige « LOCALISATION OBLIGATOIRE » mais aucun garde
> logiciel ne vérifiait qu'elle existe dans le source → un critical inventé pouvait faire rejeter
> le code à tort. Décision utilisateur : **politique Option 1 non-destructive** (rétrograde+flag,
> is_approved inchangé) — calibrage d'abord, automation du verdict en cycle futur après mesure du
> taux de faux-positifs par le Meta-Analyste (P15).

- [x] Étape F93-1 : Exploration (2 subagents parallèles) — map précise : `Finding` schema
  (models.py:23, Pydantic mutable, `findings` JAMAIS persisté en DuckDB → liberté de mutation),
  point d'insertion `execute_code_judge_node` dspy_nodes.py (retournait `result.output` brut,
  aucun post-traitement ; fail-closed security=None retourne avant LLM = naturellement exclu),
  miroir F-70 (judge_metrics + judge_diff style), algorithme langextract (legacy sliding-window
  + LCS DP, pure stdlib). Décision design : porter le LEGACY `_fuzzy_align_extraction` (plus
  simple, bornage fenêtre implique densité) plutôt que le DP LCS.
- [x] Étape F93-2 : Module `graph_orchestrator/judge_grounding.py` (~330 lignes, 0 LLM) — port
  `_normalize_token` (lowercase+plural stem), `fragment_is_grounded` (sliding-window difflib,
  coverage 0.75, max_window 2·needle), `read_source_files`/`_resolve_file`/`extract_code_fragments`
  (spans backtick + chains a.b.c ONLY, PAS de prose ni filenames via `_looks_like_filename`),
  `_extract_file_line_refs`, `ground_finding` (line-range check + fragments), `ground_findings`,
  `apply_grounding` (Option 1 : rétrograde 1 cran + flag `[ungrounded]`, `model_copy` is_approved
  inchangé, no-op si 0 ungrounded). Data models locaux.
- [x] Étape F93-3 : Intégration `execute_code_judge_node` — post-LLM, gardé par
  `settings.judge_grounding_enabled`, `try/except` fail-open total, log observabilité.
- [x] Étape F93-4 : Config `judge_grounding_enabled` (défaut True) + `.env.example` + `.env`.
- [x] Étape F93-5 : Tests — `test_judge_grounding.py` (34 : normalize 4, fragment_grounded 8,
  extract 6 dont filename-exclu, read/resolve 7, ground_finding 6, ground_findings 2, apply 4) +
  2 intégration `test_dspy_nodes.py` (downgrade critical→high+flag / opt-out). **36 nouveaux PASS.**
- [x] Étape F93-6 : Bug trouvé + corrigé pendant les tests — `extract_code_fragments` extrayait
  les filenames (`index.html`) comme chains → false ungrounded (prose-only) OU faux grounded si
  un fichier du repo contenait `index`/`html`. Fix : `_looks_like_filename` + `_FILE_EXTS` exclut
  les filenames (gérés par line-range + _resolve_file). Test `test_filename_exclu_des_fragments`.
- [x] Étape F93-7 (Stade A) : py_compile OK + suite Judge ciblée **75/75 PASS**. Suite complète
  **979 passed / 9 failed** dont **8 STRICTEMENT pré-existants** confirmés identiques via `git stash`
  (read_gate×4 + skill_lazy×3 + guard×1, AUCUN lié au grounding) + 1 flaky non reproduit en
  isolation. **0 régression F-93.**
- [x] Étape F93-8 (Stade B) : `debug/run_judge_grounding.py` (déterministe 0 LLM) — valide les 4
  invariants politique Option 1 (ancré conservé, inventé rétrogradé critical→high+flagué,
  prose-only fail-open, is_approved invariant). `debug/run_judge.py` étendu (flag ungrounded).
- [ ] Étape F93-9 (Stade B live) : `debug/run_architect.py` (nœud Architect isolé GPU) produit un
  ArchitectOutput réaliste (vrais target_files + critères F-90) pour ancrer le test grounding.
- [x] Étape F93-10 (Stade C) : run E2E `FRESH_START=1 JUDGE_GROUNDING_ENABLED=1` Bubble Sort
  lancé (~57 min, **tué par décision utilisateur** — trajectoire estimée 1,5-2 h, F-93 étant
  par ailleurs validé). **Intégration tenue** : boot sain (Router=HTML, Architect plan 3-fichiers,
  Recall 8 leçons), 23 Coder steps, Judge iter 1 a rejeté normalement (`ts-html-structure REJETÉ`
  → DuckDB), **grounding silencieux = 0 ligne « ungrounded »/« grounding » dans le log → 0 faux
  flooding, 0 crash, fail-open confirmé en prod**. Les 2 exceptions sont des `Connection error`
  llama-server transitoires (infra, pas F-93). Le déclenchement positif (downgrade d'un finding
  halluciné) est probabiliste et n'a pas été observé sur la portion de run ; l'objectif d'intégration
  (« F-93 marche dans la vraie chaîne sans casser le Judge ») est atteint. Log : `logs/e2e_f93_run.log`.

> **Décision clé (politique)** : Option 1 (non-destructive)而非 Option 2/3 (recompute verdict).
> Le grounding ne peut JAMAIS approuver à tort (is_approved inchangé). La phase de calibrage
> collecte les flags `[ungrounded]` pour que le Meta-Analyste (P15) mesure le taux de faux-positifs
> avant toute automation. Complément orthogonal à F-70 (métriques quantitatives) : vérification
> d'intégrité qualitative en ligne.

## Jalons de l'Itération (cycle fix F-53 — isolation git du run dir anti-pollution repo principal)
> Bug signalé en bonus de la PR #61 : `git_snapshot` (F-53) avait créé un commit vide « Iteration 1 »
> dans le **repo principal** pendant un run E2E (reflog `9e860af`, droppé ensuite). Le `.git` du run
> est censé vivre dans `runs/<dated>/` (gitignoré), pas polluer le repo parent.

- [x] F53-1 : **Diagnostic**. Le code reposait sur `_run_git(cwd=None)` (hérite du cwd process) +
  garde Python `os.path.isdir(".git")` qui ne vérifie que le `.git` direct. Or **git remonte
  l'arborescence** pour découvrir un repo : si pour quelque raison que ce soit (cwd erroné, `.git`
  non créé, env `GIT_DIR`, etc.) le repo découvert n'est pas le run dir, le commit atterrit dans le
  parent. Preuve : `git show 9e860af` = commit vide (`--allow-empty`, signature exacte de
  `commit_iteration`) sur parent `81773e3` (état détaché droppé). Les run dirs ont bien un `.git`
  imbriqué → l'isolation marche *en principe*, mais aucun garde logiciel ne garantit l'isolation
  en cas de divergence cwd/decouverte.
- [x] F53-2 : **Fix de robustesse** (TDD). `git_snapshot.py` : (a) param `repo_path` optionnel sur
  les 4 fonctions publiques (`init_run_git`/`commit_iteration`/`get_last_diff`/`has_git_history`),
  rétrocompatible (défaut `None` = cwd process, les 12 tests existants inchangés) ; (b) toutes les
  commandes git passent `cwd=repo_path` (cwd-indépendant) ; (c) **garde défensive `_is_isolated`**
  qui compare `git rev-parse --show-toplevel` au run dir attendu (Windows-safe : `normcase`+`normpath`)
  et **REFUSE** toute opération si le repo découvert n'est pas le run dir. `workflows.py` passe
  `run_output_dir` explicitement aux 3 call sites (init/commit/get_diff).
- [x] F53-3 : **Tests** : 6 nouveaux tests `TestIsolationRobustesse` (init/commit/diff/history avec
  `repo_path` depuis un cwd ailleurs + **garde anti-pollution** : un run dir sans `.git` propre
  découvrant un parent ne crée AUCUN commit dans le parent + vérif toplevel après init). RED → GREEN.
  Fichier `test_git_snapshot.py` : 12 → 18 passed.
- [x] F53-4 : **Validation** : suite complète **908 passed / 8 failed** — les 8 échecs sont
  **pré-existants** (test_read_gate ×4 + test_skill_lazy_loading ×3 + test_guard ×1), confirmés sur
  main via `git stash` (test_guard échoue aussi sur main, non lié à F-53). **0 régression**.
  Note : `test_output_dir::test_e2e_resume_reuses_same_run_dir` est **flaky minute-boundary** par
  construction (run 1 clear le checkpoint ligne 966 + run_id diffère entre les 2 runs → run 2 ne
  reprend jamais via checkpoint, passe uniquement si les 2 runs tombent dans la même minute). À
  durcir dans un cycle dédié (hors scope F-53).

## Jalons de l'Itération (cycle F-61 Meta-Analyste — post-mortem run partiel 1h30)
> Rôle Meta-Analyste (AGENTS.md §8). Run E2E `bubble-sort-multifile-v6` lancé puis interrompu
> après 1h30 (trop long). `run_analyzer.py` sur le log partiel → diagnostic confirmé par lecture code.

- [x] F61-1 : Run E2E + `run_analyzer.py` → métriques brutes : **17,4M tokens input** (vs 7,5M
  pour run9 *complet*), 111 steps, 4 restarts Tester, 6 crashes « Pydantic→sauvetage DSPy→Connection error ».
- [x] F61-2 : **Diagnostic corrigé** (1ère hypothèse partiellement fausse). (a) P2 « compaction
  screenshots » était **DÉJÀ implémenté** (`apply_image_purge` compaction.py:22, appelé inconditionnellement
  dans `write_memory_to_messages`) — mon grep initial l'avait manqué. (b) Vraie cause des 5 retries :
  `_tester_max_steps_fallback` (nodes.py:189) **retournait `None` en l'absence de signal PASS/FAIL** →
  retry complet du Tester → qui re-thrash (`import os`, navigation sans assertion) → pas de signal →
  `None` → retry ×5. Le sauvetage DSPy crash en Connection error est un symptôme secondaire (payload
  énorme renvoyé au serveur surchargé), il rend `None` proprement et passe la main au fallback.
- [x] F61-3 : **Correctif P1 appliqué** (scope approuvé : « robustesse extraction verdict Tester ») :
  (1) `_tester_max_steps_fallback` ne retourne **PLUS None** — verdict `failure` « Tester n'a pas convergé »
  par défaut (tue la boucle de retries : un run max_steps sans conclusion est lui-même un signal).
  (2) `extract_and_validate` (models.py) tronque le `broken_text` du sauvetage à 6000 chars (défensif,
  anti Connection error sur payload énorme). P2 : rien (déjà fait). P3 droppé (snip threshold irrelevant
  à max_steps=8).
- [x] F61-4 : **Validation** : 5 tests `TestTesterMaxStepsFallback` PASS (dont 1 mis à jour
  `test_fallback_failure_si_aucun_signal`). Suite complète **902 passed / 8 failed** — les 8 échecs
  (test_read_gate ×4 + test_skill_lazy_loading ×3-4) sont **pré-existants**, confirmés strictement
  identiques via `git stash` (documentés F-82). **0 régression**. py_compile OK.

## Jalons de l'Itération (cycle Intégration formelle des fiches 30-44 — doc/cohérence)
> Fait suite au commit `dfcea24` (ajout brut des 15 dépôts fiches 30-44). Périmètre = travail
> documentaire uniquement (AUCUN code de production modifié, AUCUN test impacté). Miroir de F-66
> (qui avait intégré les fiches 19-23).

- [x] Étape IF30-1 : Lecture des 15 fiches 30-44 (en-têtes, notes globales, composants) + diagnostic
  — les bullets « Nouvelles Références d'Audit (Batch Août 2026) » en bas du plan étaient un DUMP
  BROUILLON avec numérotation incohérente (`fiche **19-Understand-Anything**`, `**XX-prime-agent**`,
  `**40-skills**`...) non distribué dans les priorités.
- [x] Étape IF30-2 : Distribution des bullets dans les sections de priorité cibles (P0-bis, P2, P3,
  P4, P6, P6-bis, P6-ter, P8, P8-bis, P9, P10, P11) en cases `[ ]` propres — numérotation corrigée
  (30-44 canonique), références `file:symbol` préservées, 12 nouvelles cases datées 2026-08-12.
- [x] Étape IF30-3 : Suppression du dump brut (120 lignes, anciennes lignes 427-548). Plan passé de
  549 à 468 lignes (vérifié : 0 marqueur `Nouvelles Références`, 0 numéro de fiche stale).
- [x] Étape IF30-4 : Création de 4 features formelles F-93..F-96 dans `feature_list.json` pour les
  workstreams les plus substantiels — F-93 grounding findings Judge (langextract, P6), F-94 capteur
  santé structurelle (sentrux, P6/P15), F-95 robustesse FS transactions/locks/IO allowlist (OpenKB,
  P8-bis), F-96 harnais évaluation skills (Anthropic skills, P10). **95 features total, JSON valide.**
- [x] Étape IF30-5 : Correction des en-têtes internes de 12 fiches sur 15 (mauvais numéros 19/XX/40/21
  → 30-44 canonique ; 3 fiches déjà correctes 30-Ix/31-Scrapling/34-brooklyn laissées intactes).
- [x] Étape IF30-6 : `INDEX.md` rendu cohérent — compteurs (29→44 projets, 494→569 entrées, date
  2026-08-12), tableau de navigation complété (15 lignes, 44 fiches), arbre du dossier complété
  (29-44). `references-audit/README.md` : 494→569.
- [x] Étape IF30-7 : Branche `docs/integration-fiches-30-44` + commit.

## Jalons de l'Itération (cycle Tester fonctionnel — F-20)
- [x] Étape TF-1 : Diagnostic (4 causes racines : skill aveugle logique, noms MCP faux, spec non propagée, Judge sans requirements).
- [x] Étape TF-2 : Skill web-tester réécrit (noms puppeteer_* + étape "Functional Logic Testing" via puppeteer_evaluate).
- [x] Étape TF-3 : Propagation spec complète (workflows seed_content → sub_dict original_content → tester prompt "CAHIER DES CHARGES").
- [x] Étape TF-4 : Judge équipé (CodeJudgeSignature + task_requirements).
- [x] Étape TF-5 : max_steps tester 20→24 (marge assertions).
- [x] Étape TF-6 : tests/test_web_tester_functional.py (11 tests). Suite 212 passed / 0 failed.
- [x] Étape TF-7 : Validation standalone (run_tester.py) — VALIDÉ ✅
  Le tester écrit de vraies assertions (puppeteer_evaluate + IIFE), détecte que le
  tableau n'est pas trié → FAIL documenté. Avant : "success" à tort. Itération skill
  via script standalone (~3 min) au lieu du workflow complet (~30 min).
- [x] Étape TF-8 : Corrections skill (syntaxe IIFE anti "Illegal return statement",
  résolution 1280×800, champ ASSERTIONS FONCTIONNELLES au rapport).
- [x] Étape TF-9 : Outil run_tester.py (tester isolé, itération rapide).

## Jalons de l'Itération (cycle Context7 — doc libs à jour)
- [x] Étape C7-1 : Exploration (API Context7, 3 nœuds, patterns de test) + plan approuvé.
- [x] Étape C7-2 : Module context7_tool.py (get_context7_tools + fetch_context7_brief, dégradation gracieuse).
- [x] Étape C7-3 : Skill context7-research (workflow stratégique : QUAND chercher = libs externes uniquement).
- [x] Étape C7-4 : Branchement skills_loader (socle Coder + règle dynamique libs).
- [x] Étape C7-5 : Coder (outils + prompt nuancé) + Architect (pré-fetch brief + garde-fou vanilla) + web-tester (outils).
- [x] Étape C7-6 : tests/test_context7_tool.py (13 tests, mock réseau, 0 dépendance réseau).
- [x] Étape C7-7 : Suite pytest → 201 passed / 0 failed (188 avant + 13 nouveaux).
- [ ] Étape C7-8 : Validation run Bubble Sort (Context7 dormant sur vanilla).
- [ ] Étape C7-9 : Validation run avec lib externe (Context7 en action).

## Jalons de l'Itération (cycle Tester polyvalent + stderr)
- [x] Étape A : Planification + exploration (détection techno, skills_loader, config).
- [x] Étape B : feedback_utils.py (troncature head+tail + truncate_history) + tests (15 PASS).
- [x] Étape C : config.py (settings test_timeout_s, stderr_head/tail_lines, feedback_max_chars).
- [x] Étape D : Package testers/ (base+detect_tech, web_tester refactor, python_tester subprocess).
- [x] Étape E : Nœud execute_tester_node refondu en dispatcher (nodes.py).
- [x] Étape F : skills_loader couche dynamique techno→skill pour le tester (select_skills_for_tester).
- [x] Étape G : Skills web-tester (enrichi) + python-tester (nouveau).
- [x] Étape H : Brancher troncature aux 3 points (dspy_nodes, workflows, tools/bash_command).
- [x] Étape I : Tests (tech_detection, python_runner, tester_dispatch, intégration troncature).
- [x] Étape J : uv run pytest tests/ → 185 passed, 2 failed (les 2 échecs sont PRÉ-EXISTANTS
  sur main dans test_extract.py, hors périmètre ce cycle). +45 tests vs base.
- [ ] Étape K : contract.md + feature_list + plan cochés + log/progress fin + PR.

## Jalons de l'Itération (test process complet)
- [x] Étape 1 : Prompt de test (tasks.json → landing page Nimbus) + reset KG.
- [x] Étape 2 : Corrections préventives (Context7, duplication router/judge, flushing).
- [x] Étape 3 : Réécriture du Coder (garde anti-vide, prompt anti-boucle, skills ciblés).
- [x] Étape 4 : Création skills file-creation + frontend-design + skills_loader (2 couches).
- [x] Étape 5 : Robustesse matérielle (FAST_MAX_TOKENS, LLM_TIMEOUT_S=600, Modelfile bigctx).
- [x] Étape 6 : Optimisations vitesse (Architect 3 sous-tâches, skills allégés, num_predict 4000).
- [x] Étape 7 : Étude références (crush/openfox/nanocode) + évaluation Nanbeige (abandonné).
- [x] Étape 7bis : Audit détaillé des projets (crush, nanocode, openfox) extrait dans references_audit.md.
- [x] Étape 8 : Run #11 → process multi-agent VALIDÉ de bout en bout (boucle Coder→Judge→feedback).
- [x] Étape 9 : PR #2 mergée (Kilo review SUCCESS). Stratégie modèles définie (Gemma4 GPU / distant CPU).
- [x] Étape 10 (cycle SEARCH/REPLACE) : outil search_replace tolérant (portage Aider) + Mutex par fichier.
  search_replace_utils.py + tools.py + Coder équipé + 11 tests unitaires PASS.
- [x] Étape 11 : Run validation (Coder utilise search_replace → HTML non corrompu) — Run #12 VALIDÉ.
- [x] Étape 11.5 : Mise à jour de l'architecture avec les principes de juillet 2026 (Ng, Anthropic, Google).
- [x] Étape 12 (cycle CHECKPOINTS) : Persistance d'État (Priorité 3). Table `checkpoint`
  dans DuckDB + run_id stable (hash du contenu de tâche) + branchement save/load dans
  run_coding_workflow (skip Architect + skip sous-tâches completed + reprise à l'itération).
  Granularité "début d'itération" (sûre/idempotente). Config FRESH_START. 12 tests PASS.
- [x] Étape 13 : Run validation reprise (interrompre un run CPU-only, relancer → reprise).
  Run #13 VALIDÉ en conditions réelles : cycle complet bout-en-bout avec crashs répétés,
  reprise automatique (skip Architect + skip sous-tâches validées), 3 fichiers générés
  (index.html 12 533 o, styles.css 14 033 o, script.js 7 285 o). Checkpoint effacé en fin.
- [ ] Étape 14 : Cycle suivant (Priorité 2 stderr / Nœud d'Escalade / Repo Map / CodeAgent).

## Jalons de l'Itération (cycle Nœud d'Escalade — F-23)
- [x] Étape ESC-1 : Planification approuvée (stratégie Diagnostic seul + persistance KG).
- [x] Étape ESC-2 : Modèle EscalationOutput (models.py).
- [x] Étape ESC-3 : Signature DSPy + execute_escalation_node (dspy_nodes.py).
- [x] Étape ESC-4 : Config escalation_enabled (config.py + .env.example).
- [x] Étape ESC-5 : Branchement workflows.py (remplacer max_iterations_reached).
- [x] Étape ESC-6 : Tests tests/test_escalation.py (8 tests, 0 LLM).
- [x] Étape ESC-7 : Suite pytest complète (220 passed / 0 failed).
- [x] Étape ESC-8 : Docs (contract.md, plan, README) + finalisation état disque.

## Jalons de l'Itération (cycle Auto-Dépendances — F-26)
- [x] Étape AD-1 : Planification approuvée (pip install non-persistant + validation regex + cap 1 retry).
- [x] Étape AD-2 : config.py + .env.example (auto_install_deps opt-out, valeur par défaut pour pas casser les helpers de test).
- [x] Étape AD-3 : python_tester.py (extract_missing_module + _install_module + branchement dans run()).
- [x] Étape AD-4 : tests/test_python_runner.py (extract unitaire + comportement auto-install + contrat _install_module).
- [x] Étape AD-5 : Suite pytest → 232 passed / 0 failed (220 avant + 12 nouveaux). 0 régression.
- [x] Étape AD-6 : Docs (contract.md +7 critères, plan, README) + finalisation état disque.

## Jalons de l'Itération (cycle Découpage incrémental — F-28, CodeAgent P0)
- [x] Étape DI-1 : 2e comparatif gros fichier inline INTERROMPU (1h, step 1 non fini) → gros
  write_file monolithique INEXPLOITABLE sur CPU-only. Le problème = le PATTERN, pas le type d'agent.
- [x] Étape DI-2 : 2 audits (references + web) — gap append_file confirmé (aucun projet ne l'a).
  Pattern n°1 recommandé pour petits modèles CPU = accumulateur incrémental.
- [x] Étape DI-3 : Plan approuvé (outil append_file + tests + prompt incrémental + branchement).
- [x] Étape DI-4 : append_file dans tools.py (mutex + gardes + feedback + anti-doublon léger).
- [x] Étape DI-5 : tests/test_append_file.py (8 tests, 0 LLM) — 8/8 PASS.
- [x] Étape DI-6 : Branchement append_file au Coder prod (nodes.py coder_tools) — additif non-cassant.
  Suite pytest 240 passed / 0 failed (232 avant + 8 nouveaux).
- [x] Étape DI-7 : prompts/dashboard_admin_incremental.md (workflow squelette + append section par section).
- [x] Étape DI-8 : Scripts comparatifs équipés (append_file dans tools des 2 scripts + prompt CodeAgent adapté).
- [x] Étape DI-9 : Runs comparatifs TCA vs CodeAgent sur le dashboard incrémental.
  RÉSULTAT : Le modèle (gemma-4-e4b) écrivait un squelette vide mais échouait à faire les `append_file` suivants.
  SOLUTION : Ajout d'une garde anti-squelette HTML dans `write_file` pour interdire la stratégie incrémentale sur ces fichiers et forcer l'écriture monolithique. Test validé : le CodeAgent a généré les 280 lignes d'un coup avec succès.
- [x] Étape DI-10 : Décision : Le garde-fou a été corrigé (regex DOTALL) et poussé en PR. L'utilisation du CodeAgent est confirmée car il génère correctement le fichier d'un bloc.

## 🗺️ Feuille de route Finalisation (P1-P3, décidée 2026-07-31)
Ce cycle (CodeAgent + append_file) a révélé 4 gaps qui s'emboîtent. Le workflow actuel
marche sur du simple (Bubble Sort) mais SOUFFRE sur le gros/multi-étapes (dashboard).
P1-P3 = finaliser (P4 = optimisations secondaires, hors périmètre immédiat).

### P1 — Migrer le Coder vers CodeAgent (IMMÉDIAT, ce cycle)
- [x] Preuves empiriques réunies (3 comparatifs convergent).
- [x] Migration execute_coder_node : ToolCallingAgent → CodeAgent + prompt Python (F-32).
- [x] Guard logiciel anti-déraillement (F-33 : idle step + parsing cassé).
- [ ] Validation run réel final (étape suivante).

### P2 — Architect évolué : stratégie de découpage adaptative (F-29, cycle suivant)
- [x] Enrichir ArchitectSignature : stratégie par sous-tâche (simple | incrémental | multi-fichier).
- [x] Décision techno-driven (HTML/CSS/JS=multifile par défaut, Python/TS=multifile, monolithe imposé=incremental).
- [x] L'Architect dicte au Coder COMMENT construire, pas juste QUOI (propagation sub_dict).
- [x] Tests (6 PASS).

### P3 — Linter Shift Left (F-30 = P7 plan usine logicielle, cycle d'après)
- [x] Nœud linter léger (tree-sitter multi-langue + py_compile) entre Coder et Tester.
- [x] Boucle fermée : syntaxe invalide → court-circuite le Tester coûteux → feedback Coder.
- [x] Couverture multi-langue : Python, HTML, CSS, JS, TS, TSX (17 tests PASS).
- [x] Branchement workflow (DuckDB réfutation source='linter' + continue).

### État validation
- [x] Suite pytest 271 passed / 0 failed (240 avant + 31 nouveaux). 0 régression.
- [x] Import workflow complet OK (pas de circularité).
- [ ] Run réel de validation (uv run python -m graph_orchestrator.workflows) — étape suivante.

### Hors finalisation (P4, à évaluer plus tard)
- F-31 : Tester en mode CodeAgent (2e candidat, optimisation potentielle, non urgent).
- F-34 : Nœud d'Audit Dette Technique (python-health-audit via uvx) en fin de workflow.
- File viewer fenêtré SWE-agent ACI (lourd, optionnel).
- 5 nœuds sans tools (Worker/Judge/Synth/Adversary) : CodeAgent inutile, ne pas migrer.
- **F-50 : Scripts d'isolation « l'agent joue le rôle du nœud » pour dépannage/validation rapide.**
  Idée : systématiser le pattern qui a si bien marché sur F-49 (l'agent injecte des
  entrées buggées et valide la sortie en <6s, au lieu de lancer le workflow complet de
  ~25 min). Un script d'isolation par nœud, qui fournit le contexte minimal et appelle
  la VRAIE fonction de production (zéro dérive de comportement). Bénéfices :
  - **Dépannage rapide** : itérer sur un nœud (prompt, skill, logique) sans relancer tout
    le graphe. Retour en secondes, pas en dizaines de minutes.
  - **Détection de régressions** : inputs buggés connus → assertion sur le verdict.
  - **Onboarding/debug** : comprendre le contrat entrée/sortie d'un nœud en l'exécutant
    isolément avec des données contrôlées.
  Nœuds candidats (par ordre de valeur) :
  1. **Tester** (`run_tester.py` existe déjà F-46) — étendre aux autres runners.
  2. **Coder** (`run_coder.py` / `prompts/bubble_sort_spec.md` existe déjà isolation) —
     formaliser en script réutilisable avec spec en entrée.
  3. **Static Tester** (`debug/validate_static_tester_live.py` existe déjà F-49) — garder.
  4. **Linter** — injecter fichiers buggés (TS, Python IndentationError, contenu après
     </html>) et valider le court-circuit.
  5. **Architect / Router / Judge** — injecter specs/prompt et valider le JSON de sortie
     (DSPy, moins évident à isoler mais faisable via signature directe).
  6. **Security Reviewer** — injecter code vulnérable (XSS, eval) et valider le verdict.
  Convention : un dossier `debug/isolation/` avec un script par nœud, documentation du
  contrat d'entrée (quoi fournir) et d'attentes (quoi vérifier). Réutilise les fixtures
  déjà écrites dans les tests unitaires.

## Jalons bootstrap (faits)
- [x] Création agent.md (specs gestion d'état).
- [x] Initialisation feature_list.json, contract.md, progress.md.

## Jalons de l'Itération (cycle CodeAgent — Priorité 0, transition ToolCallingAgent→CodeAgent)
- [x] Étape CA-1 : Analyse codebase (7 ToolCallingAgent + 1 CodeAgent mort). Seul le
  Coder est un vrai candidat (5 agents sans tools = pas de bénéfice, Security en DSPy).
- [x] Étape CA-2 : Plan approuvé (2 scripts séparés, mode TCA import direct prod,
  mode CodeAgent expérimental, isolation stricte des répertoires).
- [x] Étape CA-3 : run_coder_tca.py (import execute_coder_node, OUT_DIR=tca/ isolé+nettoyé).
- [x] Étape CA-4 : run_coder_codeagent.py (CodeAgent, prompt final_answer Python,
  extraction maison, OUT_DIR=codeagent/ isolé+nettoyé).
- [x] Étape CA-5 : .gitignore + codeagent_compare/ (artefacts jetables).
- [ ] Étape CA-6 : Vérification imports + syntaxe (py_compile).
- [x] Étape CA-7 : Runs comparatifs (TCA puis CodeAgent) — TERMINÉ. Les 2 réussissent
  sur Bubble Sort (borné). CodeAgent gagne sur tokens IN (-63%) et durée (-19%).
  Résultats consignés dans le journal d'événements (migré DuckDB).
- [ ] Étape CA-8 : Décision : migrer execute_coder_node vers CodeAgent (si gain prouvé)
  OU garder TCA (si CodeAgent n'apporte rien). Création feature F-XX le cas échéant.
  → EN ATTENTE : un 2e test sur contenu plus lourd (multi-fichiers / HTML 3000+
  lignes) confirmerait le gain sur le scénario-douleur (corruption JSON du TCA).


## Jalons de l'Itération (Amélioration Plan Usine Logicielle)
- [x] Étape 1 : Analyse des audits LlamaBot, Deer Flow, Crush, OpenCode, Aider.
- [x] Étape 2 : Création de l'artefact Implementation Plan soumis pour validation.
- [x] Étape 3 : Application des modifications au plan_usine_logicielle.md.
- [x] Étape 4 : Mise à jour de progress.md et feature_list.json.

## Jalons de l'Itération (Output daté par run — F-40, Priorité 13)
- [x] Étape OD-1 : Exploration points d'insertion (KG instantiation, checkpoint, run_id critique,
  load_tasks_from_json relatif) + décision design (date + persistance checkpoint pour préserver
  la reprise — le timestamp seul l'aurait cassée).
- [x] Étape OD-2 : config.py + .env.example — output_dir (défaut runs).
- [x] Étape OD-3 : workflows.py — _slugify + _resolve_run_output_dir + _scoped_chdir (context
  manager finally) + branchement (KG avant chdir, corps wrappé dans with) + persistance checkpoint.
- [x] Étape OD-4 : Refactor indentation corps 350 lignes (script Python + py_compile + suite
  381 passed = 0 cassé).
- [x] Étape OD-5 : tests/test_output_dir.py (13 PASS) — slugify, resolve, scoped_chdir, E2E
  (Coder écrit dans run dir + reprise même dossier + kg_path stable). Correctif mock linter
  (module source, pas workflows).
- [x] Étape OD-6 : Suite pytest complète → 394 passed / 0 failed (381 + 13). 0 régression.
- [x] Étape OD-7 : État disque synchronisé (contract.md +9 critères 105-113, feature_list.json
  +F-40, progress.md, plan_usine_logicielle.md case P13 cochée, .gitignore runs/).

## Jalons de l'Itération (nœud PromptRefiner — F-39, meta-prompt avant l'Architect)
- [x] Étape PR-1 : Exploration (Router/Architect DSPy, checkpoint, test patterns) + recherche web
  Kilo Code/Cline "Enhance Prompt" (sources consignées). Plan approuvé (Phase 1 seule ;
  Phase 2 MIPROv2 écartée — signal biaisé mono-modèle 6 Go VRAM).
- [x] Étape PR-2 : models.py PromptRefinerOutput (refined_prompt + ambiguities_detected).
- [x] Étape PR-3 : dspy_nodes.py — PromptRefinerSignature (2 inputs, docstring pipeline aligné
  Kilo/Cline/open-swe) + _build_capabilities_summary (catalogue complet via list_skills, repli
  défensif dossier skills/, statut Context7, testers statiques) + execute_prompt_refiner_node
  (clone execute_router_node, gemma REASONING, dégradation None,None).
- [x] Étape PR-4 : config.py + .env.example — prompt_refiner_enabled (défaut True).
- [x] Étape PR-5 : workflows.py — branchement APRÈS run_id (critique : hash stable) AVANT Router +
  checkpoint refined_prompt (skip LLM à la reprise).
- [x] Étape PR-6 : tests/test_prompt_refiner.py (8 tests). BUG DÉCOUVERT + CORRIGÉ : les 3 helpers
  E2E existants (test_escalation/test_checkpoint/test_feedback_integration) ne mockaient pas
  execute_prompt_refiner_node → le workflow appelait le VRAI LLM en test → hang. Correctif :
  ajout d'un mock passe-through (None → repli prompt brut) dans les 3 helpers.
- [x] Étape PR-7 : Suite pytest complète → 379 passed / 0 failed (371 avant + 8 nouveaux). 0 régression.
- [x] Étape PR-8 : État disque synchronisé (contract.md +9 critères 96-104, feature_list.json
  +F-39, progress.md, plan_usine_logicielle.md +Priorité 12 +Phase 2 chantier futur, README.md,
  .env.example). Commit + push + PR.

## Jalons de l'Itération (cycle 3 tâches rapides : Anti-Loop P3 + Nettoyage DOM P6 + Guard bash P8-bis)
- [x] Étape TR-1 : Sélection des 2 tâches les plus rapides et isolées du plan (P3 ligne 73
  + P6 ligne 108). Écart de l'Anti-Loop SHA256 (nodes.py) et du Nettoyage DOM (web_tester.py).
  Note archi : dépôt sans LangGraph (pas de GraphState), checkpoints ne rechargent pas la
  mémoire smolagents → "Orphan Repair" (P8) écarté (N/A).
- [x] Étape TR-2 (Tâche 1 — Anti-Loop, F-36) : loop_guard.py (compute_tool_call_fingerprint
  SHA256 + LoopGuard.record/repeated_action/reset + extract_tool_calls_from_step pour
  ToolCallingAgent ET CodeAgent). Config LOOP_GUARD_ENABLED/THRESHOLD. Branché dans
  run_with_retry (param optionnel non-cassant) via execute_coder_node.
- [x] Étape TR-3 (Tâche 2 — Nettoyage DOM, F-37) : dom_filter.py (clean_dom_for_llm,
  regex précompilées, sans dépendance). Branché dans web_tester.py (directive prompt +
  snippet JS côté navigateur).
- [x] Étape TR-4 : Tests (test_loop_guard.py 16 tests + test_dom_filter.py 18 tests).
  Correction marqueur async (@pytest.mark.anyio, pas asyncio — projet utilise anyio).
- [x] Étape TR-5 : Suite pytest complète → 305 passed / 0 failed (271 avant + 34 nouveaux).
  0 régression. Seuls warnings = DeprecationWarning DSPy (préexistants, hors périmètre).
- [x] Étape TR-6 : État disque synchronisé (contract.md +16 critères 72-87, feature_list.json
  +F-36/F-37, progress.md, plan_usine_logicielle.md, .env.example).
- [x] Étape TR-7 (Tâche 3 — Guard bash denylist, F-38, P8-bis) : bash_guard.py
  (check_bash_command, denylist regex case-insensitive Unix+Windows+cross, message
  pédagogique jamais d'exception). Branché dans tools.py bash_command AVANT subprocess.run.
  Config BASH_GUARD_ENABLED. Patterns debuggés via fichier temp (lookbehind/lookahead pour
  flags /s /q /f, `-[rRfF]{1,3}` pour rm). 66 tests PASS.
- [x] Étape TR-8 : Suite pytest complète → 371 passed / 0 failed (305 avant + 66 nouveaux).
  0 régression.
- [x] Étape TR-9 : État disque synchronisé (contract.md +8 critères 88-95, feature_list.json
  +F-38, progress.md, plan_usine_logicielle.md P8-bis ❌→🟡 + sous-case guard, README.md,
  .env.example). Commit + push + PR.

## Jalons de l'Itération (cycle 2 tâches rapides : Anti-Loop P3 + Nettoyage DOM P6)
- [x] Étape TR-1 : Sélection des 2 tâches les plus rapides et isolées du plan (P3 ligne 73
  + P6 ligne 108). Écart de l'Anti-Loop SHA256 (nodes.py) et du Nettoyage DOM (web_tester.py).
  Note archi : dépôt sans LangGraph (pas de GraphState), checkpoints ne rechargent pas la
  mémoire smolagents → "Orphan Repair" (P8) écarté (N/A).
- [x] Étape TR-2 (Tâche 1 — Anti-Loop, F-36) : loop_guard.py (compute_tool_call_fingerprint
  SHA256 + LoopGuard.record/repeated_action/reset + extract_tool_calls_from_step pour
  ToolCallingAgent ET CodeAgent). Config LOOP_GUARD_ENABLED/THRESHOLD. Branché dans
  run_with_retry (param optionnel non-cassant) via execute_coder_node.
- [x] Étape TR-3 (Tâche 2 — Nettoyage DOM, F-37) : dom_filter.py (clean_dom_for_llm,
  regex précompilées, sans dépendance). Branché dans web_tester.py (directive prompt +
  snippet JS côté navigateur).
- [x] Étape TR-4 : Tests (test_loop_guard.py 16 tests + test_dom_filter.py 18 tests).
  Correction marqueur async (@pytest.mark.anyio, pas asyncio — projet utilise anyio).
- [x] Étape TR-5 : Suite pytest complète → 305 passed / 0 failed (271 avant + 34 nouveaux).
  0 régression. Seuls warnings = DeprecationWarning DSPy (préexistants, hors périmètre).
- [x] Étape TR-6 : État disque synchronisé (contract.md +16 critères 72-87, feature_list.json
  +F-36/F-37, progress.md, plan_usine_logicielle.md, .env.example).

## Jalons de l'Itération (P8 — Orphan Repair, anti-corruption d'historique, F-41)
- [x] Étape OP-1 : Contexte — P8 du plan (ligne 129), blueprint s08_context_compact, structure smolagents memory.steps/ActionStep lue.
- [x] Étape OP-2 : `orphan_repair.py` — niveau messages (`repair_orphan_tool_results`, FAKE_INTERRUPTED={{status:error,error:Interrompu}}) gérant tool_use + forme sérialisée type=function/function.name, réponse via tool_use_id/tool_call_id/id.
- [x] Étape OP-3 : `orphan_repair.py` — niveau steps (`repair_orphan_steps` : ActionStep avec tool_calls sans observations/error/is_final_answer → observations=FAKE_INTERRUPTED).
- [x] Étape OP-4 : Intégration défensive (`try/except Exception: pass`) dans `nodes.run_with_retry` (bloc P8, ~lignes 174-189) AVANT chaque `agent.run`.
- [x] Étape OP-5 : Tests — `tests/test_orphan_repair.py` 11 tests ; vérif `orphan+guard+loop_guard` = 35 passed ; suite complète = 405 passed / 0 failed (0 régression).
- [x] Étape OP-6 : État disque synchronisé — feature_list.json +F-41, contract.md +critères 114-121, plan_usine_logicielle.md P8 [x], progress.md, README.md.

## Jalons de l'Itération (P8 — Sanitizer, Auto-typage des arguments d'outil, F-42)
- [x] Étape SZ-1 : Contexte — petit LLM émet des args malformés (offset="1, 80", replace_all="true") → TypeError validation smolagents → retries gaspillés. Flux de validation tracé (agents.py:1476 validate_tool_arguments). Chemin CodeAgent confirmé : executor local expose les outils et les appelle via `__call__` directement (PAS execute_tool_call/validate_tool_arguments) → proxy `__call__` intercepte avant `forward`.
- [x] Étape SZ-2 : `sanitizer.py` niveau coercition — `_parse_string_to_structure` (json.loads→ast.literal_eval fallback), `_coerce_integer` (dernier entier d'une chaîne), `_coerce_number`, `_coerce_boolean` (true/1/yes/on→True), `coerce_value` (array/object/string/None respecté, best-effort), `sanitize_tool_arguments` (clés connues seulement, non-dict intact).
- [x] Étape SZ-3 : `sanitizer.py` niveau proxy — `SanitizedTool(BaseTool)` copie name/description/inputs/output_type, intercepte `__call__` pour coerçer kwargs avant de déléguer à l'outil réel ; `wrap_tool` + `sanitize_tools(enabled)` no-op quand disabled.
- [x] Étape SZ-4 : Config `sanitizer_enabled` (env `SANITIZER_ENABLED`, défaut True) dans `config.py` (champ dataclass + load_settings).
- [x] Étape SZ-5 : Branchement `nodes.execute_coder_node` + `execute_architect_node` via `sanitize_tools(..., enabled=settings.sanitizer_enabled)`.
- [x] Étape SZ-6 : Tests — `tests/test_sanitizer.py` 23 tests (coercion 13 + sanitize 4 + proxy 3 + wrap 3) ; 23/23 PASS.
- [x] Étape SZ-7 : Suite pytest complète → 417 passed / 0 failed (394 baseline + 23 nouveaux), 0 régression. web_tester_functional désélectionné (nécessite Chrome/npx).
- [x] Étape SZ-8 : État disque synchronisé — feature_list.json +F-42, contract.md +critères 122-129, progress.md, README.md.

## Jalons de l'Itération (P8-bis — Idempotence des effets de bord, F-43)
- [x] Étape ID-1 : Contexte — replays de checkpoint réappliquent les effets de bord non-idempotents (append_file, pip install). Référence qm idempotency-store.ts (once(key, fn), inflight + done + backing + rétention 14j). Mécanisme de replay tracé (save_coding_state granularité début d'itération → Coder rejoue).
- [x] Étape ID-2 : `idempotency.py` — `IdempotencyStore` (once/committed/reset/_prune_if_due, threading.Lock, backing DuckDB) + `make_op_key` + contexte module-level (`_scoped_idempotency`/`get_current_store`/`set_current_store`/`clear_current_store`). Port Python fidèle de qm.
- [x] Étape ID-3 : `knowledge_graph.py` — table `idempotency_record(run_id, op_key, created_at, PK)` + `save_idempotency` (INSERT OR IGNORE) / `is_idempotency_committed` / `prune_idempotency` / `clear_idempotency`. Import `datetime`/`timedelta` ajouté.
- [x] Étape ID-4 : `config.py` + `.env.example` — `idempotence_enabled` (défaut True) + `idempotency_retention_days` (défaut 14).
- [x] Étape ID-5 : Branchement `workflows.py` — store créé après kg+run_id+checkpoint, corps wrappé `with _scoped_chdir(...), _scoped_idempotency(_idem_store):` (composition sans réindentation). `clear_idempotency(run_id)` aux 2 sites `clear_checkpoint` (FRESH_START + fin de run).
- [x] Étape ID-6 : Branchement `tools.py` (`append_file` via `once` + `_do_append` closure, write_file NON wrappé) + `python_tester.py` (`_install_module` via `_install_module_or_raise`/`_InstallFailed`, échec non marqué done).
- [x] Étape ID-7 : Tests — `tests/test_idempotency.py` 25 tests (store 10 + KG 4 + scoped 3 + make_op_key 4 + intégration append 2 + intégration pip 2) ; 25/25 PASS.
- [x] Étape ID-8 : Suite pytest complète → 442 passed / 0 failed (417 baseline + 25 nouveaux), 0 régression. web_tester_functional désélectionné (nécessite Chrome/npx). État disque synchronisé (feature_list.json +F-43, contract.md +critères 130-140, plan_usine_logicielle.md P8-bis [x], progress.md, README.md).

## Jalons de l'Itération (cycle Refonte Prompts — P0 + P0-bis + P6, F-44)
- [x] Étape RP-1 : Cartographie prompts actuels (6 nœuds DSPy docstring + 2 smolagents f-string + 1 déterministe sans prompt ; aucun préfixe commun). Lecture fiches audit 15/16/17 (invariants universels, prompts purs par rôle, prompts open-source citables).
- [x] Étape RP-2 : Création `graph_orchestrator/prompts.py` — fondation partagée (UNIVERSAL_INVARIANTS 10 patterns + ROLE_BLOCKS 9 rôles + build_role_header/with_invariants helpers + build_invariants_header standalone).
- [x] Étape RP-3 : Injection des invariants dans les 6 Signatures DSPy (`dspy_nodes.py`) via `__doc__ = with_invariants(role, doc_métier)`. Mécanisme validé empiriquement (DSPy lit `__doc__` via metaclass — test probe `SigB.instructions` contient rôle+invariants+métier).
- [x] Étape RP-4 : Durcissement Judge (CodeJudgeSignature + docstring enrichi : rubric critical/high/medium/low, in-diff only, anti-nits, professional objectivity, vérification comportementale via task_requirements) + extension additive `CodeJudgeOutput.findings: List[Finding] = []`.
- [x] Étape RP-5 : Durcissement Security (SecuritySignature + docstring enrichi : OWASP Top 10, scores CVSS, defensive-only) + extension additive `SecurityOutput.findings: List[Finding] = []`. Schéma `Finding` (`severity/category/location/description/suggestion`) + `Severity` Literal définis dans models.py.
- [x] Étape RP-6 : Spécialisation prompts smolagents — Coder (`nodes.py`) préfixé par `build_role_header("coder")` (rôle + 10 invariants dont verify-after, type hints, anti-laziness) ; WebTester (`testers/web_tester.py`) préfixé par `build_role_header("web_tester")` (pyramide 70/20/10, pattern AAA, indépendance des tests).
- [x] Étape RP-7 : Suppression ~180 lignes de nœuds smolagents DÉPRÉCIÉS dans `nodes.py` (versions mortes execute_router_node/execute_architect_node/execute_security_reviewer_node/execute_code_judge_node — jamais appelées par run_coding_workflow qui importe les versions DSPy) + imports morts nettoyés (RouterOutput/ArchitectOutput/SecurityOutput/CodeJudgeOutput retirés de l'import nodes.py). Préalable requis par le plan (ligne 42).
- [x] Étape RP-8 : Tests — `tests/test_prompts.py` 40 tests (invariants 2 + rôles paramétrés 17 + build_role_header 3 + with_invariants 2 + signatures DSPy paramétrées 6 + rubric markers 3 + Finding/models 7) ; 40/40 PASS.
- [x] Étape RP-9 : Suite pytest complète → 482 passed / 0 failed (442 baseline + 40 nouveaux), 0 régression. web_tester_functional désélectionné (nécessite Chrome/npx).
- [x] Étape RP-10 : État disque synchronisé (feature_list.json +F-44, contract.md +critères 141-149, plan_usine_logicielle.md P0+P0-bis+P6 cochés, progress.md, README.md).

## Jalons de l'Itération (requête utilisateur)
- [x] Clonage du dépôt awesome-claude-skills dans references/.

## Jalons de l'Itération (cycle Validation Coder — 6 fixes + Architect + timings)
- [x] Étape VC-1 : Fix SanitizedTool.__getattr__ (to_code_prompt délégation — bug CodeAgent crash).
- [x] Étape VC-2 : Fix search_replace arg names (search→old_string, replace→new_string, convention canonique aider/Cline).
- [x] Étape VC-3 : Fix Coder mode CORRECTION (iteration>1 = read_file+search_replace, pas rewrite).
- [x] Étape VC-4 : Fix auto-réparation HTML append_file (déplace </body></html> à la fin, 0 LLM).
- [x] Étape VC-5 : Fix Linter HTML (ignore faux positifs tree-sitter sur CSS/JS inline).
- [x] Étape VC-6 : Fix Architect découpage (règle "1 livrable testable = 1 sous-tâche" + simple par défaut).
- [x] Étape VC-7 : Run GPU validation — Coder one-shot (2 steps/77s, 9726 octets, HTML+BubbleSort complets).
- [x] Étape VC-8 : Analyse timings (debug/TIMINGS_ANALYSE.md) — Tester identifié comme goulot (querySelector, ~30 min).
- [x] Étape VC-9 : Audit utilisateur intégré (audit_coder/ — 7 tests + screenshots, confirme Coder one-shot).
- [x] Étape VC-10 : Suite pytest 482 passed / 0 failed après tous les fixes. Commit.
- [x] Étape VC-11 (cycle suivant) : Fix Tester querySelector (ACTION IMMÉDIATE documentée).

## Jalons de l'Itération (cycle Fix Tester querySelector — F-45)
- [x] Étape F45-1 : Diagnostic empirique (lecture log GPU) — racine corrigée vs hypothèse
  initiale du doc : le modèle écrit `document.querySelector='...'` (assignation `=`) au lieu
  de `document.querySelector('...')` (appel `()`) → écrase la fonction native → boucle fatale.
  Ce n'est PAS "Puppeteer n'expose pas querySelector". Le HTML généré utilise getElementById.
- [x] Étape F45-2 (Axe 1 — Skill web-tester) : directive ciblée anti "querySelector assigné
  vs appelé" (= fatal vs ()) + garde anti-pollution du contexte (jamais réassigner une méthode
  native) + replis robustes getElementById/getElementsByTagName + pattern DOMContentLoaded.
- [x] Étape F45-3 (Axe 2 — Cap steps) : config.py `tester_max_steps` (défaut 12, avant 24
  hardcoded) + .env.example + web_tester.py (max_steps=settings.tester_max_steps).
- [x] Étape F45-4 (Axe 3 — Guard contextuel) : LoopGuard instancié et passé au WebTestRunner
  via run_with_retry + _detect_idle_step contextuel (node_kind='tester' → message puppeteer_*
  /final_answer, pas write_file) ; run_with_retry accepte node_kind (défaut 'coder').
- [x] Étape F45-5 (Tests) : test_guard.py +3 (message contextuel tester/coder, productif
  no-message, run_with_retry node_kind='tester' émet le log idle) + test_config.py +1
  (tester_max_steps défaut+override).
- [x] Étape F45-6 (Suite) : pytest 487 passed / 0 failed (482 baseline + 5 nouveaux).
- [x] Étape F45-7 (État disque) : debug/TIMINGS_ANALYSE.md (ACTION CORRIGÉE + recommandations
  statutées), feature_list.json +F-45, contract.md +critères 150-155, progress.md.

## Jalons de l'Itération (cycle Fix bug visuel Coder + Judge hang — F-46/F-47)
- [x] Étape F46-1 : Diagnostic bug visuel — lecture log F-45 prouve que le Coder applique
  LITTÉRALEMENT 'hero 3.5rem' du skill frontend-design (log lignes 403-405 + 482). Le skill
  était conçu pour landing pages, inadapté à un visualiseur (app/tool).
- [x] Étape F46-2 : Skill frontend-design réécrit — ÉTAPE 0 (APP/TOOL vs LANDING/PAGE),
  fourchettes conditionnelles (remplacent 'hero 3.5rem'), garde anti-titre-géant, directive
  layout APP (pas de row à 1024px, une colonne).
- [x] Étape F46-3 : Bug FRESH_START corrigé — load_dotenv(override=True) écrasait l'env shell
  → FRESH_START=1 au shell inopérant. Passé à override=False (défaut). Validé.
- [x] Étape F47-1 : Diagnostic Gap 2 (Judge hang) — analyse log + tests exhaustifs. Prompt
  Judge PETIT (~4k tokens, déjà tronqué). Température 0.3 CORRECTE (ne pas changer). VRAIE
  cause : thinking Gemma 4 FORCÉ sur /v1 (Ollama 0.32.5 = dernière version). Non désactivable
  via /v1 (think/chat_template_kwargs/Modelfile testés, tous ignorés).
- [x] Étape F47-2 : Percée technique — provider litellm 'ollama/' parle /api/chat natif +
  paramètre think. Testé : think=false → 3.8s, réponse directe (vs 23min thinking).
- [x] Étape F47-3 : _configure_dspy migre vers ollama/ + retrait /v1 + paramètre think.
  Décision utilisateur : think=True uniquement Architect, think=False pour les 5 autres
  nœuds DSPy (Router/PromptRefiner/Security/Judge/Escalation).
- [x] Étape F47-4 : Tests — 2 tests test_prompt_refiner.py mis à jour (assertions think=False).
  Suite pytest 487 passed / 0 failed.
- [x] Étape F4647-5 : debug/GAPS_TESTER_JUDGE.md — 2 gaps consignés avec DONNÉES RÉELLES
  (Gap 1 screenshot jetté par smolagents, Gap 2 thinking résolu par F-47).

## [ARCHIVE — F-48 fermée sans cycle dédié (2026-08-11)]
> F-48 « Vision Coder » était planifiée quand le backend était Ollama /v1 et avant que
> F-50/F-58/F-90 n'existent. Les 4 étapes ci-dessous sont devenues OBSOLÈTES ou furent
> livrées autrement. La description de F-48 décrivait comme « à faire » ce qui était déjà
> en prod. Feature marquée `completed` (livrée par étapes) lors du nettoyage de cohérence.
> - F48-1 (think=false Coder) → résolu par **F-58** (migration llama-server spawn +
>   `FAST_REASONING=off` au spawn via ModelSpec, `llama_server.py:198`). Le contournement
>   litellm `/api/chat` de F-47 (spécifique Ollama /v1) n'a plus de raison d'être.
> - F48-2 (screenshot tool) + F48-3 (verify-after skill) → livrés par **F-50** (ex-F-45) :
>   `vision_callback.py` + `chrome_devtools_tool.py` + skill `devtools-preview` + bloc
>   VALIDATION VISUELLE dans le prompt Coder + enforcement programmatique. **F-90** a
>   ajouté `visual_success_criteria` générés par l'Architect (checklist OUI/NON vs screenshot).
> - F48-4 (comparatif A/B) → non essentiel, non fait.
>
> Le Coder a DONC déjà la vision en prod. Cette section est conservée pour la traçabilité
> historique mais ne décrit plus un « prochain cycle ».

## Jalons de l'Itération (cycle Chrome DevTools MCP + validation visuelle — F-45)
- [x] Étape CD-0 : Vérification runtime fast_model (gemma-4-E4B) multimodal — VALIDÉ
      (image rouge 4x4 envoyée via /v1/chat/completions → réponse "Roux... rouge").
- [x] Étape CD-1 : Config MCP build_chrome_devtools_params() (agent_server/mcp.py) —
      source unique stdio (npx chrome-devtools-mcp@latest --isolated --viewport 1280x800
      --screenshot-format jpeg), opt-out CHROME_DEVTOOLS_ENABLED, CHROME_PATH, HEADLESS.
- [x] Étape CD-2 : Context manager chrome_devtools_tool.py (yield [] si KO, dégradation
      gracieuse pattern Context7).
- [x] Étape CD-3 : Module vision_callback.py — wrapper _ScreenshotCapturingTool (capture
      PIL image) + make_screenshot_callback (step_callback peuple observations_images).
      Nécessaire car smolagents v1.26.0 ne pousse pas auto les images MCP en multimodal.
- [x] Étape CD-4 : Branchement Coder (CodeAgent) — outils DevTools + step_callback +
      prompt section VALIDATION VISUELLE (conditionnelle web), max_steps 12→14.
- [x] Étape CD-5 : Branchement WebTester — cumul Puppeteer + Chrome DevTools,
      step_callback vision actif, doc outils complémentaires dans le prompt.
- [x] Étape CD-6 : Skill devtools-preview/SKILL.md + skills_loader (routage dynamique web).
- [x] Étape CD-7 : Config .env + .env.example (CHROME_DEVTOOLS_ENABLED, CHROME_PATH,
      CHROME_DEVTOOLS_HEADLESS). Reporté dans .env local (AGENTS.md §7).
- [x] Étape CD-8 : tests/test_chrome_devtools_tool.py (28 tests : params, dégradation,
      callback, helpers Coder, skills). Suite pytest 521 passed / 0 failed (+28 vs baseline).
- [x] Étape CD-9 : Fichiers état (feature_list F-45, contract C150-C160, progress, log).
- [ ] Étape CD-10 : Validation run Bubble_Sort_Visualizer (borné, WORKFLOW_MODE=coding).

## Jalons de l'Itération (cycle Checklist fonctionnalités + fixes robustesse — F-46)
- [x] Étape CD-11 : 3 runs de validation Bubble Sort (diagnostic des failure modes).
- [x] Étape CD-12 : Fix AUDIT_PARALLEL=false (séquentialise Tester PUIS Security, GPU-local).
- [x] Étape CD-13 : Fix max_steps Tester 24→12 (anti-explosion contexte 405k→233k tokens).
- [x] Étape CD-14 : Skill coding anti-TypeScript (tableau syntaxes interdites en vanilla).
- [x] Étape CD-15 : Skill devtools-preview — list_console_messages OBLIGATOIRE avant screenshot.
- [x] Étape CD-16 : Skill web-tester — règle des 2 essais (conclure FAILURE vite).
- [x] Étape CD-17 : requirements_checklist.py (parser regex + build_checklist_block).
- [x] Étape CD-18 : Injection checklist dans web_tester.py (checklist_block après cahier charges).
- [x] Étape CD-19 : tests/test_requirements_checklist.py (14 tests). Suite 535 passed / 0 failed.
- [x] Étape CD-20 : Doc — README.md §"Node Graph & Data Flow" (diagramme ASCII complet
      avec tiering modèles + flux données) + AGENTS.md (séquence + référence).
- [x] Étape CD-21 : Fichiers état (feature_list F-46, contract C161-C170, log, progress).
- [ ] Étape CD-22 : Validation run Bubble Sort avec checklist F-46 active (cycle suivant).

## Jalons de l'Itération (cycle Static Tester déterministe — F-49)
- [x] Étape ST-1 : Module `graph_orchestrator/static_tester.py` — Tier 1a (`node --check`
      sur JS inline → TS-in-vanilla, bug n°1 = page blanche), Tier 1b (wiring
      `addEventListener` → slider non branché, piège n°1 indétectable par screenshot),
      Tier 2 (visibilité DOM DevTools `getBoundingClientRect().height` → barres invisibles,
      le bug CSS height:% que le LLM a raté par biais de confirmation). Déclenchement de
      l'action primaire (clic start) combiné au probe en UN appel synchrone (éléments créés
      au clic, pas au load). Générique (découvre sélecteurs + ids depuis le HTML, ne hardcode rien).
- [x] Étape ST-2 : Intégration `workflows.py` — inséré entre Linter et Tester LLM, même
      pattern de court-circuit (réfutation DuckDB source='static_tester' + continue).
- [x] Étape ST-3 : Tests `tests/test_static_tester.py` — 29 tests (l'agent joue le Coder
      avec des HTML bubble-sort buggés). 29/29 PASS. Bug barres invisibles ATTRAPÉ.
- [x] Étape ST-4 : Config `.env` + `.env.example` — STATIC_TESTER_ENABLED, STATIC_TESTER_DEVTOOLS.
- [x] Étape ST-5 : Fichiers état synchronisés (feature_list F-49, contract C180-C189, README,
      AGENTS.md, log, progress).
- [x] Étape ST-6 : Suite pytest complète → 592 passed / 0 failed (563 baseline + 29 nouveaux).
      0 régression. web_tester_functional désélectionné (nécessite Chrome/npx live).
- [ ] Étape ST-7 : Validation run live (HTML corrompu → FAILURE ciblé, HTML correct → SUCCESS).

## Jalons de l'Itération (cycle Scripts isolation « l'agent joue le nœud » — F-55)
- [x] Étape ISO-1 : Plan approuvé (périmètre = Linter + 4 DSPy Router/Architect/Judge/Security ;
  PromptRefiner/Escalation hors périmètre). Convention debug/isolation/ (conforme F-55).
  Exploration (3 agents parallèles) : signatures exactes nœuds, clés dict task lues, sites
  d'appel workflows.py, tests mockés, config. Leçon clé : nœuds DSPy instancient eux-mêmes
  leur LLM via _configure_dspy (param *_model reçu IGNORÉ, relicat d'API).
- [x] Étape ISO-2 (première version, CORRIGÉE ensuite) : 5 scripts Python appelant le LLM du
  graphe (run_router.py etc.). VALIDÉS par py_compile + 1 exécution Router réelle (18.9s).
- [x] Étape ISO-2b (CORRECTION MAJEURE après feedback user) : « l'agent joue le nœud » =
  MOI (ZCode) qui joue le nœud à la main, PAS un script qui appelle le LLM du graphe.
  Pattern découvert : debug/MANUAL_TESTER_METHODOLOGY.md (le Tester joué à la main, doc
  d'étapes fail-fast + biais) + audit_coder/ (le Coder joué avec screenshots). Les 4 scripts
  DSPy (router/architect/judge/security) SUPPRIMÉS — design mauvais. run_linter.py GARDÉ
  (déterministe, valide la vraie fct prod, 7/7 ✅).
- [x] Étape ISO-3 : MANUAL_ROUTER_METHODOLOGY.md — étapes fail-fast (mots-clés → extensions
  → résolution multi-techno → décision), tableau de décision par langage, 3 biais.
- [x] Étape ISO-4 : MANUAL_ARCHITECT_METHODOLOGY.md — 3 stratégies F-29 (techno-driven),
  5 étapes (livrables/stratégie/sections/description/assemblage), 4 biais.
- [x] Étape ISO-5 : MANUAL_JUDGE_METHODOLOGY.md — rubric sévérité F-44, 6 étapes (Read
  in-diff/couverture/test_res/security_res/décision/feedback), 5 biais.
- [x] Étape ISO-6 : MANUAL_SECURITY_METHODOLOGY.md — grille OWASP Top 10, 6 étapes
  (Read/grep OWASP/contexte input/CVSS/findings defensive/is_secure), 5 biais.
- [x] Étape ISO-7 : MANUAL_LINTER_METHODOLOGY.md (compléter le set, cohérence).
- [x] Étape ISO-8 : README isolation réécrit (convention doc méthodologie + run_linter.py
  seul script). README racine corrigé. État disque synchronisé (feature_list F-55,
  contract C196-C204, progress, log). Suite pytest 586 passed / 0 failed (0 régression).
  Commit + PR.

## Jalons de l'Itération (cycle F-56 durcissement prompts nœuds — P14)
- [x] Étape P14-1 : Plan approuvé (2 décisions user : P14-E=warning non bloquant, F-57=planifié
  après F-56). Exploration clé : seul test_prompts.py asserte le contenu des docstrings (tests
  de présence de marqueurs) → durcir les docstrings ne casse aucun test si marqueurs préservés.
- [x] Étape P14-E : Linter warning fichier absent (linter.py + execute_linter_node + 2 tests).
  Défense is_valid=True conservée + avertissement remonté dans details pour observabilité.
- [x] Étape P14-A : Router — MOTS-CLÉS CANONIQUES + RÈGLE DE PRIORITÉ + ANTI-BIAIS.
- [x] Étape P14-B : Architect — RÈGLES sections incremental + BIAIS incremental/multifile.
- [x] Étape P14-D : Security — PATTERNS OWASP concrets + DISCRIMINATION INPUT + A09 + FP.
- [x] Étape P14-C : Judge — PROCÉDURE OBLIGATOIRE 5 étapes + croisement défiant + localisation.
- [x] Étape P14-F : Validation — pytest 587 passed / 0 failed. Marqueurs préservés (grep 3/3).
  run_linter 7/7 ✅. Correspondance 1:1 audit→implémentation vérifiée.
- [x] Étape F-57 : PLANIFIÉ (feature_list pending + plan_usine §P10) — lazy loading cycle suivant.
- [x] Étape P14-9 : État disque synchronisé (feature_list F-56 completed + F-57 pending,
  contract, progress, log, plan_usine P14 coché).

## Jalons de l'Itération (cycle Intégration llama.cpp dynamique — F-58)
- [x] Étape LCP-1 : `llama_server.py` créé avec le context manager `model_lifecycle`.
- [x] Étape LCP-2 : `_configure_dspy` (dspy_nodes.py) et les runners (`CodeAgent` / `WebTester`) adaptés pour accepter l'API base issue du `model_lifecycle` spawn.
- [x] Étape LCP-3 : Configurations .env et config.py adaptées (backends `spawn`, `FAST_MODEL` etc.)
- [x] Étape LCP-4 : Ajustements mock tests pour respecter les `_SpawnedServer`.
- [x] Étape LCP-5 : Tests unitaires (598 passed).
- [x] Étape LCP-6 : Run E2E (Bubble Sort validé avec crash DSPy et régression Coder capturés pour F-59).
- [x] Étape LCP-7 : Fix DSPy Rescue (ajout de l'alias dans llama_server) et Warning top-level await Web Tester.
- [x] Étape LCP-8 : Implémentation outil multi_replace (F-59) pour le Coder et modification de nodes.py.


## Jalons de l'Itération (cycle Analyse des Runs & Amélioration Continue — F-60 / F-61)
- [x] Étape RAA-1 : Création de 
un_analyzer.py (F-60) pour parser les logs 	ask-*.log et extraire les métriques de graph_orchestrator.db. Filtres robustes contre les bordures de logs (Rich).
- [x] Étape RAA-2 : Validation en direct du rôle de Meta-Analyste de l'assistant IA (F-61). Diagnostic des crashes InterpreterError et injection dynamique de la règle import time dans 
odes.py et web_tester.py.
- [x] Étape RAA-3 : Remplacement du write_file par multi_replace_file_content validé et acté (F-59) pour le Coder.
- [x] Étape RAA-4 : Application en direct (F-61) d'un deuxième correctif : le run E2E a crashé sur le Web Tester à cause de la règle "IIFE" passée au MCP chrome-devtools. Analyse + correction de 
odes.py et web_tester.py pour exiger une DÉCLARATION de fonction asynchrone non invoquée (sync () => { await ... }) à la place de l'IIFE.
- [x] Étape RAA-5 : Mise à jour exhaustive des documents de suivi (eature_list.json, plan_usine_logicielle.md, README.md, progress.md).
- [ ] Étape RAA-6 : Attente de la fin du run E2E, analyse post-mortem finale avec un_analyzer.py, rapport de validation, et préparation pour commit/PR.

## Jalons de l'Itération (cycle Audit cohérence INDEX références — enrichissement plan)
- [x] Étape ACI-1 : Constat initial — fiches 19-23 déjà intégrées via F-66 (completed). INDEX.md + inventory.json = commit 9dc59c0.
- [x] Étape ACI-2 : Audit de cohérence exhaustif (agent Explore) — Hall of Fame INDEX croisé contre plan_usine_logicielle.md. 18 écarts identifiés, gisement principal = qm (4 briques 🟢 Haute sur 9 oubliées).
- [x] Étape ACI-3 : Enrichissement plan_usine_logicielle.md (cases `[ ]` uniquement, 0 code modifié) — P3-bis (+2), P6-bis (+2), P6-ter NOUVELLE sous-section (+1 bloc), P9 (+1 case + garde), P1 (+1 case + précision source), P2 (+1 case), P10 (+2 cases), tableau état avancement mis à jour.
- [x] Étape ACI-4 : feature_list.json +4 features pending (F-68 mémoire KG qm, F-69 budget+queue qm, F-70 diff+métriques Judge, F-71 skeleton libcst). 72 features total. JSON validé.
- [x] Étape ACI-5 : progress.md synchronisé (journal migré DuckDB). Périmètre = travail documentaire uniquement (aucun code de production modifié, aucun test impacté).

## Jalons de l'Itération (cycle Read-Before-Write Gate — F-67, Priorité 1)
- [x] Étape RBW-1 : Exploration (2 agents parallèles) — design Deer Flow lu (issue #3857,
  middleware read_before_write_middleware.py 269 lignes) : hash SHA256 contenu complet,
  stamp après read_file, « newest mark wins », fail-open, gate write_file+str_replace,
  un write réussi invalide la mark (Strict). Archi smolagents cartographiée (SanitizedTool
  = template parfait à copier, step_callbacks existants, read_file non tracé).
- [x] Étape RBW-2 : Décision design (AskUserQuestion) — mode STRICT (fidèle Deer Flow) :
  un write réussi n'auto-stamp PAS la mark → force re-read avant chaque édition.
- [x] Étape RBW-3 : `graph_orchestrator/read_gate.py` (~310 lignes) — compute_content_hash,
  _normalize_path (Windows-safe), ReadGate (dict thread-safe), _GatedWriteTool,
  _ReadTrackingTool, wrap_tools_with_read_gate. 0 LLM, 100% déterministe.
- [x] Étape RBW-4 : Branchement `nodes.py execute_coder_node` (~10 lignes) — gate inséré
  ENTRE wrap_screenshot_tools et sanitize_tools (ordre : gate AVANT sanitizer).
- [x] Étape RBW-5 : Config `read_before_write_enabled` (défaut True) dans config.py +
  .env.example + .env local (AGENTS.md §7). Opt-out READ_BEFORE_WRITE_ENABLED=false.
- [x] Étape RBW-6 : `tests/test_read_gate.py` — 35 tests (helpers 5, ReadGate logic 4,
  fail-open 6, Strict mode 3, newest-wins 1, thread-safety 1, _GatedWriteTool 5,
  _ReadTrackingTool 3, wrap 3, E2E 4). 35/35 PASS.
- [x] Étape RBW-7 : Validation — py_compile OK (3 fichiers) + suite pytest complète
  651 passed / 0 failed (616 baseline + 35 nouveaux), 0 régression.
- [x] Étape RBW-8 : État disque synchronisé (feature_list.json +F-67, contract.md
  +critères 215-227, plan_usine_logicielle.md P1 case cochée, progress.md, README.md).
  Commit + push + PR.

## Jalons de l'Itération (cycle Skills à la demande / Coder — F-57 Phase 1, Priorité 10)
> **Note de pivot (v3)** : le design initial v1 (lazy loading via tool `load_skill`
> + flag `SKILL_LAZY_LOADING_ENABLED`) a **échoué en run de validation** : le Coder
> 9B n'appelait pas l'outil, perdant les skills conditionnels. Pivot vers v3 =
> **sélection par l'Architect** (injection directe fiable à 100%) + budget tokens.
> Le tool `load_skill` reste disponible pour la flexibilité (re-consulter un skill),
> mais n'est plus le mécanisme principal.
- [x] Étape F57-1 : Plan approuvé (2 phases : Phase 1 = Coder pour prouver le gain
  tokens ; Phase 2 = généralisation aux nœuds DSPy UNIQUEMENT si Phase 1 performante).
  Baseline = run 2026-08-04_1816_bubble_sort (index.html 255 lignes one-shot).
  Décisions : mécanisme input field methodology_context pour DSPy (Phase 2),
  socle ALWAYS (3 skills critiques) vs skills conditionnels (sélection regex).
- [x] Étape F57-2 : `graph_orchestrator/skills_loader.py` — API additive :
  ALWAYS_SKILLS_CODER (set de 3, ex-EAGER_SKILLS_CODER renommé), _parse_frontmatter_yaml
  (défensif, jamais lève), parse_skill_meta (tuple name+desc, None si absent, pour
  nœuds DSPy), count_skill_tokens (tiktoken cl100k_base + mémo + repli chars/4),
  enforce_skill_budget (rogne « petits d'abord », socle ALWAYS toujours conservé),
  build_conditional_skills_block (repli regex si Architect n'a rien sélectionné).
  build_skills_catalog / build_eager_skills_block / EAGER_SKILLS_CODER CONSERVÉS
  en alias dépréciés (rétrocompat tests). build_skills_block + select_skills_for_coder
  CONSERVÉS (WebTester en dépend).
- [x] Étape F57-3 : `graph_orchestrator/skill_loader_tool.py` — @tool
  load_skill(skill_name) retourne corps complet (load_skill_body) ou message si
  introuvable, fail-open jamais ne lève. Déterministe, 0 LLM, 0 réseau. Rôle v3 =
  flexibilité (re-consulter un skill), PAS mécanisme principal d'injection.
- [x] Étape F57-4 : `graph_orchestrator/nodes.py execute_coder_node` — branchement v3 :
  l'Architect sélectionne `subtask.skills` → `enforce_skill_budget(budget=skill_budget_tokens)`
  → injection corps complet directe. Repli `build_conditional_skills_block` (regex) si
  l'Architect n'a rien sélectionné. Outil `load_skill` ajouté à coder_tools pour la
  flexibilité. ArchitectOutput/SubTask gagnent les champs `skills`/`tester_skills`/
  `judge_skills` (models.py l.76-81).
- [x] Étape F57-5 : **Pivot F-57 v3** (le lazy loading via tool a échoué en run :
  le Coder 9B n'appelait pas `load_skill`, cf. commentaire skills_loader.py l.166-179).
  Nouveau design = **sélection par l'Architect** (`subtask.skills` dans ArchitectOutput,
  models.py l.76-81) + budget tokens anti-saturation. `config.py` + `.env.example` +
  `.env` local — `skill_budget_tokens: int = 8000` (défaut, ~24% du contexte Qwen 9B)
  + `_get_int("SKILL_BUDGET_TOKENS", 8000)`. AUCUN flag `skill_lazy_loading_enabled`
  (abandonné : le mécanisme n'est plus conditionnel à un opt-out).
- [x] Étape F57-6 : `tests/test_skill_lazy_loading.py` — 33 tests / 8 classes v3
  (AlwaysSkillsCoder 3, CountSkillTokens 6, EnforceSkillBudget 6, BuildConditional-
  SkillsBlock 4, LoadSkillTool 3, ArchitectTaskSkillsField 3, CatalogueEtendu 4,
  NonRegression 4). 33/33 PASS.
- [x] Étape F57-7 : Validation — py_compile OK (5 fichiers) + smoke test (system prompt
  -36.8% par step : 17386→10988 chars sur tâche web) + suite pytest complète 678 passed
  / 0 failed hors 3 pré-existants test_run_logging.py (non liés, confirmés par git stash),
  11 deselected (test_web_tester_functional). 0 régression.
- [x] Étape F57-8 : État disque synchronisé (feature_list.json F-57 pending→completed,
  contract.md +critères 228-237, plan_usine_logicielle.md P10 PARTIEL + case cochée,
  progress.md, README.md section Coder). ATTENTE commit/PR.
- [ ] Étape F57-9 : Run de validation Bubble Sort. Critères v3 : HTML complet +
  l'Architect sélectionne `subtask.skills` + `enforce_skill_budget` plafonne la
  sélection + le Coder reçoit les corps complets (plus de dépendance à un appel
  `load_skill` du modèle). SI réussite → déclenche Phase 2 (nœuds DSPy via
  `methodology_context`).

## Jalons de l'Itération (cycle Static Tester Tier 3 — détection animations instantanées, F-81)
- [x] Étape T3-1 : Diagnostic du bug réel (runs/2026-08-05_1602_bubble_sort/index.html) —
  `performStep()` appelée par `requestAnimationFrame` contient les deux boucles imbriquées
  complètes du bubble sort → tout le tri en 1 tick JS → animation instantanée invisible.
  Tier 1 (JS valide, wiring OK) et Tier 2 (barres visibles) PASS ce fichier ; Tester LLM
  aussi (son pattern animation = wait 2s puis check état final, qui passe même si
  l'animation a duré 0 ms). Zone aveugle confirmée.
- [x] Étape T3-2 : Prévention Coder (Partie A) — règle 9 (nodes.py RÈGLES CRITIQUES :
  une itération par frame, jamais l'algorithme complet, ❌ FAUX/✅ JUSTE) + paragraphe
  granularité step (skills/coding/SKILL.md, complément de la règle threading existante).
- [x] Étape T3-3 : Détection LLM Tester (Partie C) — règle 4 (web_tester.py : test
  temporel pas état final) + recette temporelle (skills/web-tester/SKILL.md : snapshot
  T0/clic/wait 400ms/snapshot T1 au lieu du pattern wait-2s-check-final qui rate le bug).
- [x] Étape T3-4 : Détection déterministe Static Tester Tier 3 (Partie B) —
  `static_tester.py _evaluate_temporal()` : sonde DevTools en UN seul evaluate_script
  async (snapshot progression T0 → clic bouton primaire → await 400ms → snapshot T1 ;
  verdict : état terminal atteint pendant la fenêtre = animation instantanée).
  Terminaison générique (hauteurs .bar ordonnées OU toutes .sorted — ne compare PAS le
  compteur au nombre de barres). Opt-out STATIC_TESTER_TEMPORAL=0. Branché après Tier 2
  (même session Chrome) → court-circuite le Tester LLM via l'existing failure path
  (aucune modif workflows.py). `_parse_devtools_json` corrigé (gère les dicts stringifiés,
  pas seulement les arrays).
- [x] Étape T3-5 : Tests — `tests/test_static_tester.py` +5 tests Tier 3 (instant détecté,
  progressive non-flaggué, opt-out env-var ×2, no-signal skip). Suite complète 33 passed /
  1 skipped (le skip = test Tier 2 pré-existant, Chrome timing entre tests).
- [x] Étape T3-6 : Validation V1 (harness standalone sur le VRAI fichier bugué) —
  `debug/validate_tier3_temporal.py` : Scénario 1 (runs/.../index.html bugué) → FAILURE
  en 4.5s (signal 0→435 comparaisons = tout le tri en 1 tick), Scénario 2 (animation
  légitime ~2s) → SUCCESS (pas de faux positif). 🎉 VALIDATION RÉUSSIE.
- [ ] Étape T3-7 (V2, optionnel, ~3-5 min GPU) : Coder corrige le fichier bugué —
  `debug/test_gate_live_bubble.py` adapté, iteration=2 (mode correction), la règle 9
  doit pousser le modèle à corriger performStep en une iteration par frame. Re-run V1
  sur le corrigé doit passer.
- [ ] Étape T3-8 (V3, optionnel, ~10-25 min GPU) : Tester LLM valide le fichier corrigé —
  `debug/run_web_tester_standalone.py` corrigé (lit REASONING_NO_THINK_* au lieu de
  FAST_BACKEND_URL). La règle 4 + recette temporelle doivent faire écrire une assertion
  temporelle. Bonus : Tester LLM sur le fichier bugué non corrigé doit maintenant FAIL.

### Résultats V2 + V3 (validations standalone GPU, 2026-08-05)
- [x] **V2 — Coder corrige le fichier bugué** (`debug/validate_tier3_coder_fix.py`) :
  iteration=2 (mode correction read_file + search_replace), feedback Tier 3 injecté +
  règle 9 du prompt. **13 steps, 816s (~13.6 min), Qwen3.5-9B.** SUCCÈS : le Coder a
  correctement transformé performStep (double boucle → if/else une itération par frame,
  variables i/j persistées hors fonction), puis auto-validation visuelle complète
  (navigate, console OK, screenshot avant/après clic). `final_answer: success`.
- [x] **V2-4 — Static Tester Tier 3 sur le corrigé** : `success` (tier3 atteint, 7.9s,
  0 LLM). Le Tier 3 ne flaggue PLUS l'animation → la correction est prouvée déterministe.
- [x] **V3 — Tester LLM (Ornith-9B) sur le corrigé** (`debug/validate_tier3_tester_llm.py`) :
  **timeout à 600s (step 25)** — MAIS valide Parts C1+C2 : le Tester a explicitement
  annoncé "Now let me do the temporal test - click Start and measure progression over
  400ms" (step 15) → la règle 4 + recette temporelle guident le LLM. Il a détecté un
  bug réel (régression Coder : `i`/`j` non resetés dans `init()` → 2e clic inopérant,
  counter=0). Le timeout vient de l'over-exploration du Tester (failure mode pré-existant
  documenté TIMINGS_ANALYSE, pas lié au Tier 3).
- [x] **V3-3 — Fix manuel i/j + runtime probe** : ajout de `i=0; j=0; isSorting=false;`
  dans `init()`. Static Tester re-passé (`success`, tier3). Runtime probe manuelle :
  `c0=0 → c1=10` en 600ms, `progressed=True`, `finished=False` (animation progressive,
  non terminale). **L'animation marche pour de vrai maintenant.**

Bilan global V1+V2+V3 : les 3 couches (Coder prévient, Static Tester rattrape, Tester
LLM confirme) fonctionnent. Le Tier 3 déterministe est validé end-to-end (détecte le
bug en 4.5s, ne flaggue pas le corrigé, 0 faux positif). Le Tester LLM applique bien
le test temporel mais reste limité par son over-exploration (pré-existant). La règle 9
Coder est appliquée correctement par Qwen3.5-9B.
- [x] Étape T3-9 : État disque synchronisé (feature_list.json +F-81, progress.md, README.md).
  Branche `feat/static-tester-tier3-temporal`. Commit.

## Jalons de l'Itération (cycle Diff + métriques Judge — F-70, P6-bis)
- [x] Étape F70-1 : Reconnaissance (2 agents Explore parallèles) — Judge plumbing
  cartographié (`execute_code_judge_node` dspy_nodes.py:777 recevait le full-file
  concaténé `:799-805` passé au champ `code` `:858`, alors que le docstring + rôle
  exigent IN-DIFF ONLY), F-53 git_snapshot fournit `get_last_diff` (déjà propagé dans
  `sub_dict["git_diff"]` workflows.py:583, consommé seulement par le web_tester),
  pattern d'injection `build_targeted_retest_block` identifié. Références localisées
  (scorer.py, pr_diff.py, SKILL.md) — `compute_risk_score` (KG structural) et
  `build_pr_diff_files` (fetcher GitHub UI) écartés justifiés.
- [x] Étape F70-2 : `graph_orchestrator/judge_diff.py` — `build_judge_code_block`
  (0 LLM). Iter 1 (diff vide) = full-file rétrocompat ; iter >1 = bloc diff annoté
  IN-DIFF ONLY en tête + full-file tronqué (`truncate_output`, contexte vérif
  exigences). Fail-open (fichier absent sauté). Miroir `targeted_retest`.
- [x] Étape F70-3 : Branchement `dspy_nodes.py execute_code_judge_node` — boucle
  full-file remplacée par `build_judge_code_block(...)`, import ajouté. Aucune
  modif workflows.py (git_diff déjà propagé).
- [x] Étape F70-4 : `graph_orchestrator/judge_metrics.py` (offline, 0 LLM) —
  `canonicalize_finding` (ID stable `location|category|severity`, insensible
  paraphrase), `compute_precision_recall`, `compute_mrr`, `judge_verdict_accuracy`
  (TP/FP/FN). Ports typés de code-review-graph/eval/scorer.py.
- [x] Étape F70-5 : Tests — `test_judge_diff.py` (12, miroir test_targeted_retest)
  + `test_judge_metrics.py` (18, pure logique) + `test_dspy_nodes.py` +2 Judge
  (git_diff non vide → mock reçoit bloc diff ; iter1 full-file pas de bloc).
  32/32 PASS. Correctifs : Literal severity Pydantic stricte, marqueur troncature
  "tronqu" matchait tmp_path → "lignes tronquées".
- [x] Étape F70-6 : Validation — 0 régression confirmée par `git stash` (25 échecs
  préexistants sur HEAD strictement identiques avant/après, tous E2E workflow +
  guard + read_gate + skill_lazy_loading, AUCUN lié au Judge). `test_judge_diff` +
  `test_judge_metrics` + Judge `test_dspy_nodes` tous PASS.
- [x] Étape F70-7 : État disque synchronisé (feature_list.json F-70 completed,
  contract +critères 238-244, plan P6-bis 2 cases cochées, progress, log).

## Jalons de l'Itération (cycle F-61 Meta-Analyste — post-mortem run coding_d72dc8e36445c4b6)
> Run Bubble Sort du 2026-08-06 17:16 : verdict `failure` (Coder crash). Post-mortem
> via `run_analyzer.py` → 3 failure modes Coder récurrents identifiés (F-70 non impliqué,
> Judge iter 1 OK). Correctifs appliqués (AGENTS.md §8 : diagnostiquer → proposer → valider
> → appliquer).

- [x] Étape F61-1 : Diagnostic (run_analyzer.py + lecture log) — 3 causes racines :
  (1) `}` au lieu de `)` fermant search_replace (failure mode historique, règle prompt n°8
  insuffisante) ; (2) Coder boucle 87 steps / 80 min / 18M tokens (max_steps=25 trop permissif
  × worker_max_retries=3 × retries internes) ; (3) tours idle répétés sans tool call
  (_detect_idle_step F-33 réinjecte un message mais ne coupe JAMAIS → boucle jusqu'à
  épuisement). Crash final : litellm.InternalServerError Connection error (serveur llama.cpp
  saturé sous charge).
- [x] Étape F61-2 : Correctif 1 (Guard anti-`}`) — hook dans run_with_retry except Exception.
  Détection INDEPENDANTE de la condition Syntax/parse (le message smolagents "Code parsing
  failed" ne contient ni "Syntax" ni "parse" mais "parsing" — bug de condition corrigé :
  la branche `}` est testée en PREMIER). Message SPÉCIFIQUE actionnable (Règle n°8 + exemple
  correct) au lieu du générique "découpe".
- [x] Étape F61-3 : Correctif 2 (CODER_MAX_STEPS configurable) — config coder_max_steps
  (défaut 18, avant 25 hardcoded) + .env.example. Choix : Coder produit en 6-14 steps nominal,
  18 laisse une marge sans brider.
- [x] Étape F61-4 : Correctif 3 (Circuit-breaker idle consécutifs) — compteur consecutive_idle
  dans run_with_retry, param idle_breaker_threshold (défaut 3). N idles consécutifs → échec
  définitif propre. Reset sur run productif. Nœuds non-Coder (Judge/Synth/Adversary/Worker)
  reçoivent threshold=10**9 (jamais coupés — le Judge réfléchit légitimement).
- [x] Étape F61-5 : Tests tests/test_coder_hardening.py — 8 tests (config 3, hook `}` 2, idle
  breaker 3). Découvertes de mock : type(agent).__name__ nécessite une vraie sous-classe
  dynamique (MagicMock.__class__ assign + spec= ne changent pas type()) ; agent.memory.steps
  purgé en fin d'attempt → repeupler dans le mock pour simuler N idles consécutifs.
- [x] Étape F61-6 : Validation — 8/8 nouveaux tests PASS. Suite pytest complète 673 passed
  (+8 vs baseline 665) / 25 échecs préexistants strictement identiques (confirmés via la
  baseline F-70), 0 régression. py_compile OK (nodes.py + config.py).
- [x] Étape F61-7 : État disque synchronisé (feature_list.json F-61 description + cycle,
  contract +critères 245-250, progress, log).

## Jalons de l'Itération (cycle F-61 itération 3 — final_answer valide vs LoopGuard)
> Run E2E Bubble Sort multi-fichier du 2026-08-06 20:16 : verdict `failure` (Coder crash),
> mais les 3 fichiers générés étaient fonctionnels. Post-mortem via `run_analyzer.py` →
> bug logiciel `run_with_retry` identifié (un final_answer valide éjecté par le LoopGuard).

- [x] Étape F61-8 : Run E2E Bubble Sort multi-fichier (WORKFLOW_MODE=coding, FRESH_START=true)
  — 2390s (~40 min), 294k tokens. Validations E2E réussies : F-58 (llama.cpp dyn.), F-59
  (multi_replace en mode correction), F-67 (Read-Before-Write Gate a BLOCKÉ une édition
  sans relecture), F-61 (max_steps 18 + idle breaker), F-33 (rattrapage parsing triple-quote),
  F-50 (auto-validation visuelle Coder). Verdict failure (cause logicielle, pas code produit).
- [x] Étape F61-9 : Post-mortem `run_analyzer.py` — cause racine : `run_with_retry` lignes
  296-297 `if loop_msg: pass`. Le LoopGuard (F-36) scanne tout l'historique et comptabilise
  comme "répétition" l'itération de correction légitime, puis le bloc `if validated:` jette
  silencieusement le final_answer valide (`pass` au lieu de `return`). 3 retries reproduisent
  → échec définitif. Diagnostic confirmé par agent Explore (lecture code nodes.py + loop_guard).
- [x] Étape F61-10 : Correctif — bloc `if validated:` inversé. Un `validated` réussi prime
  TOUJOURS sur `loop_msg`. Le `if loop_msg: pass` supprimé. `loop_msg` reste dans le prompt
  de retry (ligne 279) pour guider le retry UNIQUEMENT quand `validated is None`. Message
  d'observabilité ajouté pour tracer le chemin. Branche `fix/coder-final-answer-loopguard-priority`.
- [x] Étape F61-11 : Test de non-régression `test_valid_final_answer_wins_over_loop_guard`
  (test_coder_hardening.py) — agent avec 3× write_file identique (déclenche loop_guard) +
  final_answer valide → assert succès retourné (pas None), 0 retry consommé. 9/9 PASS.
- [x] Étape F61-12 : Validation — suite pytest 674 passed (+1 vs baseline 673) / 26 échecs
  préexistants strictement identiques (confirmés via `git stash` : 26 failed avant ET après,
  aucun lié au LoopGuard). py_compile OK. 0 régression.
- [x] Étape F61-13 : État disque synchronisé (feature_list.json F-61 description + itération 3,
  contract +critères 251-254, progress, log).

## Jalons de l'Itération (audit approfondi TencentDB-Agent-Memory — fiche 28 enrichie)
> Re-analyse de `references/TencentDB-Agent-Memory` (audit F-83 initial superficiel : 4
> briques seulement, noté 🟡 Moyenne). Objectif : récupérer les infos pour enrichir les
> prompts actuels et la roadmap (plan_usine_logicielle.md / feature_list.json).

- [x] Étape AUDIT-1 : Exploration exhaustive (2 subagents parallèles) — carte complète des
  prompts/méthodologie de TencentDB (7 modules : l1-extraction, l1-dedup, scene-extraction,
  persona-generation, offload L1/L1.5/L2, skill-review) + map de nos prompts actuels
  (prompts.py, dspy_nodes.py, nodes.py, web_tester.py) et de l'existant mémoire (F-68, F-83).
- [x] Étape AUDIT-2 : Enrichissement fiche 28 (`docs/references-audit/projects/28-TencentDB-Agent-Memory.md`)
  — table "Documentation pertinente" (4→14 lignes) + table "Code réutilisable" (4→13 lignes)
  + synthèse + correspondance plan. Renotée 🟡 Moyenne → 🟢 Haute.
- [x] Étape AUDIT-3 : Enrichissement `plan_usine_logicielle.md` — 2 items sous P6-ter (pipeline
  L0→L3 extraction+dédup+oubli par chaleur ; recall hybride + split stable/dynamic), 1 item
  sous P9 (context-offload Mermaid scoré + cognitive tombstones), 1 item sous P10 (Skill
  Review gate 5-critères + 4-dim/100pts). En-tête P6-ter + dashboard P6 mis à jour.
- [x] Étape AUDIT-4 : Enrichissement `feature_list.json` — F-68 étoffée (pipeline L0-L3 complet,
  2 références qm+TencentDB nécessaires ensemble), +2 nouveaux IDs F-86 (context-offload P9,
  pending) et F-87 (Skill Review gate P10, pending). Total 85→87 features. JSON validé.
- [x] Étape AUDIT-5 : Analyse prompts runtime (3 candidats) — VERDICT : les 3 sont soit
  redondants (Coder règle 4+5 couvre déjà "独立完整"), soit prématurés (Skill Review gate =
  dépend F-65/F-80/F-87 pending, pas de pipeline génération aujourd'hui), soit contre
  l'architecture (compaction 0-LLM par design = tombstones LLM régresserait). Décision
  VALIDÉE par l'utilisateur : ne pas toucher aux prompts runtime (AGENTS.md §8 respecté).
- [x] Étape AUDIT-6 : Mise à jour INDEX (`docs/references-audit/INDEX.md`) — résumé fiche 28,
  compteur (1H/3M → 8H/5M), totaux (217/186/84 → 224/188/84), constat dédié.
- [x] Étape AUDIT-7 : Branche `feat/tencent-memory-prompts-enrichment` créée (règle d'or Git).

> **Décision clé** : la valeur de l'audit TencentDB se situe dans la **roadmap** (mémoire
> durable F-68 complétée, F-86/F-87 ajoutés), PAS dans des modifications spéculatives du
> runtime aujourd'hui. Les 3 changements de prompts envisagés auraient été contre-productifs
> ou redondants — la validation humaine (AGENTS.md §8) a protégé d'un changement inutile.

## Jalons de l'Itération (cycle F-65 — pépites prompts différenciantes, scope A)
> Successeur direct de F-85 (lignée F-44 → F-56 → F-85 → F-65). F-85 n'avait ingéré que les
> quick wins de la fiche 29. F-65 porte les 5 mécanismes différenciants prioritaires + 3
> quick wins, **en enrichissement de prompts uniquement** (scope A validé utilisateur).

- [x] Étape F65-1 : Branche `feat/prompt-pepites-f65` créée (règle d'or Git).
- [x] Étape F65-2 : Exploration code (3 subagents parallèles) — map précis des attach points
  (prompts.py invariants/rôles, dspy_nodes.py signatures, models.py Finding, workflows.py
  fan-out, testers/ contrat) + extraction fidèle des 5 mécanismes avec attributions exactes
  (corrections d'erreurs initiales du plan confirmées par grep indépendant).
- [x] Étape F65-3 : `prompts.py` — invariant n°5 enrichi (grille réversibilité/blast-radius,
  Codex 4-tier + Claude Code 3-tier fiche 29) + nouvel invariant n°12 (self-correction
  vérifiable « don't end with a promise », Claude Code fiche 29 + Cursor fiche 17) + 7 role
  blocks enrichis (router write-lock policy, architect EARS, coder/coder_frontend engineering
  mindset, web_tester deltas+requirements coverage, judge self-correction+citation file:start-end,
  security réversibilité+`{{secret_name}}` canary) + commentaires stale corrigés (10→12).
- [x] Étape F65-4 : `tests/test_prompts.py` — 28 cas paramétrés (11 nouveaux marqueurs
  doctrinaux) + test compte invariants mis à jour (10→12) + test grille réversibilité.
- [x] Étape F65-5 : `uv run pytest tests/test_prompts.py` → **52 passed / 0 failed**.
- [x] Étape F65-6 : Suite complète `uv run pytest tests/ --ignore=tests/test_static_tester.py`
  → **711 passed / 12 failed**. Comparatif sur `main` : **mêmes 12 échecs pré-existants**
  (test_static_tester collection error, test_read_gate, test_skill_lazy_loading, etc. —
  tests appelant vrais modèles/env, non mockés). **0 régression F-65.**
- [x] Étape F65-7 : `docs/NODES_AND_SKILLS.md` — passage de 11 à 12 invariants + nouvelle
  section F-65 (tableau attributions exactes + corrections d'erreurs d'attribution).
- [x] Étape F65-8 : État disque finalisé (`plan_usine_logicielle.md` items F-65 cochés + stub
  corrigé, `feature_list.json` F-65 → completed, `progress.md` ce bloc).

> **Hors scope (cycles futurs)** : gate logicielle `requires_approval` réelle sur bash_command
> (scope B, étend bash_guard F-38) ; modèle `TestResult` structuré PASS/FAIL delta (scope B,
> touche contrat runners + extraction Judge) ; parallélisation réelle fan-out Coder (scope C,
> risky sur VRAM 6 Go, ReadGate à durcir) ; compatibilité Synth/Drafter avec système
> d'invariants ; autres secondaires F-65 (notify vs ask Manus, 8 templates Qoder).

## Jalons de l'Itération (cycle Anti-loop v2 — F-88, P3-bis)
> Le plan P3-bis (lignes 109-114) demande 3 patterns anti-loop de la référence loopx
> (fiche 19) : stall detector + hash d'output matériel + vocabulaire delivery_outcome.
> F-36 (LoopGuard) ne hashe que ToolName + Input → aveugle à 2 failure modes :
> (a) même contenu réécrit avec input cosmétiquement différent, (b) série de turns
> sans livrable matériel nouveau.

- [x] Étape SD-1 : Exploration (3 agents parallèles) — contrat F-36 exhaustif (LoopGuard,
  run_with_retry, _detect_idle_step, breaker idle, test_valid_final_answer_wins_over_loop_guard),
  patterns loopx vérifiés en Python pur stdlib (recent_runs.py, pr_monitor_materialization.py,
  delivery_outcome.py + transaction.py), conventions projet (modules/tests/config/contract).
- [x] Étape SD-2 : Plan approuvé (décision design clé : module ORTHOGONAL, LoopGuard intact —
  préserve la cohérence F-36 et le test fragile test_valid_final_answer_wins_over_loop_guard).
- [x] Étape SD-3 : Module `graph_orchestrator/stall_detector.py` (~210 lignes, 0 LLM, 100%
  Python natif, thread-safe) — DeliveryOutcome enum (3 valeurs) + ACCOUNTABLE_OUTCOMES +
  WRITE_TOOLS + classify_turn + compute_material_fingerprint (port _group_fingerprint, hash
  contenu tronqué 16 hex) + _dominant_material_hash + StallDetector (threshold=2, table de
  vérité ACCOUNTABLE-différent→reset / ACCOUNTABLE-identique→incrément / PROGRESS-IDLE→incrément).
- [x] Étape SD-4 : Tests `tests/test_stall_detector.py` — 26 tests (enum 2, classify_turn 4,
  compute_material_fingerprint 6, StallDetector 8, thread-safety 1, intégration run_with_retry 3,
  non-régression F-36 2). Style test_loop_guard.py (une fonction par cas, @pytest.mark.anyio,
  SimpleNamespace, bannières # ===).
- [x] Étape SD-5 : Branchement `nodes.py run_with_retry` — nouveau param optionnel
  `stall_detector=None` (non-cassant). Pour chaque step de agent.memory.steps : classify_turn +
  compute_material_fingerprint + record. Si is_stalled() ET validated is None → message au prompt.
  reset() aligné sur loop_guard.reset(). Priorité validated conservée (log informatif dédié).
  Correctif pendant dev : record par STEP (pas par attempt) — sinon un run multi-steps ne déclenche
  qu'1 incrément et le stall n'est jamais atteint.
- [x] Étape SD-6 : Branchement production `execute_coder_node` — instancie StallDetector à côté
  du LoopGuard et le passe à run_with_retry. WebTester hérite du défaut (actif). Judge/Synth/
  Adversary ne le passent pas (nœuds de raisonnement, idle_breaker_threshold=10**9).
- [x] Étape SD-7 : Config — config.py (stall_detector_enabled défaut True + stall_detector_threshold
  défaut 2, bloc commenté style loop_guard) + load_settings (_get_bool/_get_int) + .env.example
  (bloc # --- Stall Detector ---) + .env local (AGENTS.md §7).
- [x] Étape SD-8 : Validation — 26/26 tests stall_detector PASS. Suite pytest complète 714 passed
  / 12 failed (les 12 échecs PRÉ-EXISTANTS confirmés via git stash : architect/escalation/guard-
  timeout/prompt_refiner(3)/read_gate(4)/skill_lazy_loading(2), AUCUN lié au stall detector),
  1 error collection test_static_tester (pré-existant sur main, import extract_inline_js manquant).
  0 régression. py_compile OK (stall_detector.py + nodes.py + config.py).
- [x] Étape SD-9 : État disque synchronisé (feature_list.json +F-88 completed deps [F-36],
  contract.md +critères 255-267, plan_usine_logicielle.md P3-bis 3 cases cochées + écarts
  justifiés, progress.md). Branche `feat/stall-detector-p3bis`.

> **Décision clé** : module orthogonal (LoopGuard intact) plutôt qu'extension de LoopGuard.
> La case P3-bis "Hash d'output matériel" disait "Étendre notre LoopGuard (F-36)" — décision
> contraire justifiée : le docstring loop_guard.py:10-12 dit "on n'inclut pas l'Output" (inverser
> casserait la cohérence F-36) ET le test test_valid_final_answer_wins_over_loop_guard est fragile
> (asserte guard.repeated_action() is not None après return validated). Le stall detector opère à
> un autre niveau (step/turn) que le LoopGuard (tool call isolé) — gardes complémentaires.

## Jalons de l'Itération (cycle Hotfix F-88 — hash CodeAgent vide, post-run E2E 2026-08-08)
> Run E2E Bubble Sort multi-fichier (FRESH_START=true) : verdict FAILURE après 1h10. Le stall
> detector s'est déclenché 8 fois à tort (jusqu'à "17 turns consécutifs sans changement matériel")
> sur du debug légitime du Coder, polluant son prompt avec des messages "CHANGE D'APPROCHE" →
> confusion → max_steps atteint sans final_answer valide. Régression réelle vs main (sans F-88).
> Leçon : un test unitaire mocké ne suffit pas — il faut un run réel (ou isolé) pour valider une
> feature qui touche au chemin chaud du Coder.

- [x] Étape HF-1 : Diagnostic — grep du log E2E révèle 8 déclenchements stall + "CIRCUIT BREAKER
  (Stall Detector) : 17 turns". 0 LoopGuard (le Coder ne bouclait pas — il debuguait). Le compteur
  stall ne resetait JAMAIS sur matériel nouveau (write_file répétés en phase de debug).
- [x] Étape HF-2 : Reproduction isolée sur le VRAI parseur (pas un mock) — `extract_tool_calls_from_step`
  CodeAgent retourne args = ligne source Python strippée (ex: 'write_file(path="a", content="x")'),
  PAS un dict. Or `_extract_str` ne gérait que dict + JSON-string. Pour une ligne source Python,
  retournait "" → tous les writes CodeAgent avaient le même hash SHA256("") → jamais de reset.
  BUG CONFIRMÉ : deux writes au contenu totalement différent (AAA vs BBB) → même hash e3b0c44298fc1c14.
- [x] Étape HF-3 : Fix `stall_detector.py _extract_str` — 3e cas ajouté (ligne source Python CodeAgent)
  via regex qui extrait la valeur après `key=` (guillemets doubles/simples, DOTALL). Best-effort :
  suffisant pour distinguer deux writes au contenu différent (le but du stall detector).
- [x] Étape HF-4 : Validation sur le vrai parseur — write(content=AAA) → hash X ; write(content=BBB)
  → hash Y (différent → reset) ; write(content=AAA) → hash X (identique → reproduction = stall).
  search_replace → hash non vide. CORRECT.
- [x] Étape HF-5 : 2 tests de non-régression ajoutés (test_stall_detector.py) :
  `test_material_fingerprint_codeagent_source_line_differs_on_content` (unitaire) +
  `test_stall_detector_resets_on_codeagent_write_with_new_content` (end-to-end sur la vraie chaîne
  extract_tool_calls_from_step → classify_turn → record). 28 tests PASS (26 + 2 nouveaux).
- [x] Étape HF-6 : Script d'isolation `debug/run_coder.py` créé (multi-fichier + draft injecté
  optionnel + vrai execute_coder_node). Convention F-55 étendue aux nœuds LLM. Permet la boucle
  de debug "couper si erreur, corriger, relancer" en minutes au lieu de 30-40 min.
- [x] Étape HF-7 : Validation run Coder isolé multi-fichier + draft (F-88 activé, STALL_DETECTOR=true
  seuil 2) : 0 stall sur 8 steps avec 43 tool calls d'écriture. Le fix tient en conditions E2E réelles.
- [x] Étape HF-8 : État disque synchronisé — hotfix commit + push PR #47. contract.md +critère 268.
  feature_list.json +F-89 (jeux de tests par nœud P17 MAX). plan_usine_logicielle.md +Priorité 17
  (Jeux de tests par nœud, priorité MAX) + dashboard P17 🟡 PARTIEL.

> **Leçon structurante (alimente P17/F-89)** : le bug du hash CodeAgent vide était reproductible
> en <1s sur le vrai parseur, mais a mis 1h10 de run E2E + post-mortem manuel à diagnostiquer.
> C'est la preuve que les scripts d'isolation par nœud + jeux de fixtures sont INDISPENSABLES —
> pas un nice-to-have. Placé en priorité MAX (P17) pour le cycle suivant.

## Jalons de l'Itération (cycle Jeux de tests par nœud — F-89, P17 MAX)
> Priorité MAX du plan usine logicielle. 6 scripts d'isolation LLM créés — chacun appelle la
> VRAIE fonction de production (0 mock, 0 duplication) avec fixtures figées. Permet d'itérer
> en secondes/minutes sur un nœud sans relancer le workflow E2E de 30-40 min.

- [x] Étape F89-1 : Exploration (2 agents parallèles) — signatures exactes des 6 nœuds LLM
  cartographiées (Router/PromptRefiner/Architect/Drafter/Security/Judge), clés dict lues,
  modèles utilisés (tous ignorent le param *_model → _run_dspy_node → model_lifecycle(spec)),
  config settings + 3 backends spawn. Modèles Pydantic output listés. Pattern run_coder.py
  (existant fix F-88) = référence pour la convention.
- [x] Étape F89-2 : `debug/run_router.py` — 5 prompts figés (Python mots-clés web piège /
  React JSX / HTML-CSS-JS vanilla / Rust / ambigu). Valide bug F-56a (débordement JS).
- [x] Étape F89-3 : `debug/run_prompt_refiner.py` — 3 prompts figés (vagues / déjà structuré /
  minimaliste). Affiche ambiguities_detected + refined_prompt.
- [x] Étape F89-4 : `debug/run_architect.py` — spec Bubble Sort figée. Affiche ArchitectOutput
  (plan_id, global_architecture, sous-tâches + stratégie + skills).
- [x] Étape F89-5 : `debug/run_drafter.py` — sub_dict Bubble Sort figé (configurable). Sauvegarde
  draft_markdown dans debug/drafter_isolation_out/ pour réinjection run_coder.py --draft.
- [x] Étape F89-6 : `debug/run_security.py` — 4 codes figés (propre/XSS-innerHTML/eval-URL/
  pickle.loads). Fixtures en tempfile (le nœud lit target_files depuis disque).
- [x] Étape F89-7 : `debug/run_judge.py` — 4 scénarios figés (correct+PASS / bug+FAIL / nit+PASS /
  fail-closed security=None). SecurityOutput Pydantic + test_res dict construits. Le fail-closed
  valide le hard block SANS LLM (post-mortem run 123955).
- [x] Étape F89-8 : `debug/fixtures/golden/README.md` — convention golden files (déterministe =
  golden possible ; LLM = non-golden, entrées figées seulement).
- [x] Étape F89-9 : `debug/isolation/README.md` mis à jour — 2 familles (méthodologies manuelles
  F-55 + scripts d'isolation LLM F-89) + tableau des 8 scripts.
- [x] Étape F89-10 : `debug/` retiré du `.gitignore` — 37 fichiers d'outillage versionnés
  (F-55 croyait l'avoir fait, ne l'était pas). Artefacts régénérables gardés ignorés
  (coder_isolation_out, drafter_isolation_out, run dirs, __pycache__).
- [x] Étape F89-11 : Validation — py_compile OK (6 scripts), imports OK (3 backends spawn
  validés), suite pytest 729 passed / 12 échecs pré-existants (confirmés identiques, AUCUN
  lié à F-89). 0 code de production modifié. 0 régression.
- [x] Étape F89-12 : État disque synchronisé (feature_list.json F-89 pending→completed,
  contract.md +critères 280-293, plan_usine_logicielle.md P17 🟡→🟢 + cases cochées,
  progress.md, README.md). Commit + push + PR.

## Jalons de l'Itération (cycle Consolidation mémoire KG — F-68 Phase 1, P6-ter)
> Priorité HAUTE (gisement d'écarts le plus massif de l'audit de cohérence INDEX qm).
> Le KG DuckDB grossit indéfiniment : dedup_key ne capte que les doublons EXACTS (case/
> espace), le nœud d'escalade F-23 concatène toutes les réfutations sans réduction, et
> rien n'oublie jamais. Découpage en 3 phases (décision utilisateur : Phase 1 seule ce
> cycle). Phase 1 = socle directement actionnable : consolidation LLM-juge (format qm
> UPDATE/DELETE/ADD en JSON typé) + oubli par rétention temporelle. Phase 2 (scratch/
> notebook cross-run) et Phase 3 (extraction sémantique L0-L3 TencentDB + heat) reportées.

- [x] Étape F68-1 : Exploration (3 agents parallèles) — KG actuel cartographié (6 tables,
  dedup_key = SHA1 lower/strip, add_claim dedup seulement si status='open', AUCUNE
  consolidation aujourd'hui), références qm + TencentDB analysées (qm = contrat stockage
  + consolidation UPDATE/DELETE/ADD line-oriented + oubli FIFO ; TencentDB = sémantique
  riche store/skip/update/merge + heat + L0-L3 + recall hybride), points d'intégration
  identifiés (fin de run workflows.py:858, miroir pattern escalation F-23).
- [x] Étape F68-2 : Modèles Pydantic `models.py` — ConsolidationAction (kind update/delete/
  add, index 1-based, text) + ConsolidationOutput (entity_id, actions, summary). Convention
  additive (défauts []) — non-cassant.
- [x] Étape F68-3 : Méthodes KG `knowledge_graph.py` — get_claims_by_run (JOIN provenance),
  get_entities_by_run (distinct, fidèle qm ScopeId), update_claim_content (UPDATE + recalcul
  dedup_key), delete_claim (CASCADE manuelle provenance+edges, jamais d'exception),
  prune_old_claims (miroir prune_idempotency, preserve_kinds escalation+insight par défaut).
  AUCUNE migration schéma (created_at/kind/status existent déjà).
- [x] Étape F68-4 : Applier déterministe `apply_consolidation_actions` (module-level, 0 LLM,
  port qm applyConsolidationActions) — ordre DELETE-d'abord puis UPDATE puis ADD, index
  1-based, invalide → skip fail-open, ADD via add_claim kind='insight' source='consolidation'.
- [x] Étape F68-5 : Config `config.py` + `.env.example` + `.env` — memory_consolidation_enabled
  (défaut True), memory_consolidation_after (défaut 10 = qm DEFAULT_CONSOLIDATE_AFTER),
  memory_retention_days (défaut 30). Opt-out MEMORY_CONSOLIDATION_ENABLED=false.
- [x] Étape F68-6 : Nœud DSPy `dspy_nodes.py` — ConsolidationSignature (rôle judge + invariants
  F-44 + procédure obligatoire 5 étapes + anti-nits + index 1-based) + execute_consolidation_node
  (parcourt entités par run, skip si < seuil, numérote 1-based, truncate_output, _run_dspy_node
  spec=no_think_spec think=False, applique via apply_consolidation_actions, NodeMetrics par
  entité, dégradation gracieuse None/None si LLM down).
- [x] Étape F68-7 : Branchement `workflows.py` fin de run — execute_consolidation_node si
  enabled + prune_old_claims TOUJOURS (indépendant du flag). Dégradation gracieuse try/except.
  Import execute_consolidation_node ajouté au bloc différé dspy_nodes.
- [x] Étape F68-8 : Tests `tests/test_consolidation.py` — 24 tests (Tier 1 applier+KG 17,
  Tier 2 nœud DSPy mocké 5, Tier 3 E2E workflow 3). Miroir test_escalation.py (mock
  _configure_dspy + dspy.ChainOfThought, _setup_workflow_mocks avec fake_consolidation).
- [x] Étape F68-9 : Script d'isolation `debug/run_consolidation.py` (convention F-89) — 3
  scénarios figés (doublons/mixed/clean), KG temporaire isolé (ne pollue pas data/), affiche
  claims avant/après + actions émises + vérif leçons préservées.
- [x] Étape F68-10 : Validation — py_compile OK (7 fichiers), suite pytest 763 passed / 13
  failed (12 pré-existants + 1 flaky `test_e2e_resume_reuses_same_run_dir` confirmé passant
  en isolation). 0 régression F-68. 24/24 tests consolidation PASS.
- [x] Étape F68-11 : État disque synchronisé (feature_list.json F-68 pending→in_progress,
  contract.md +critères 294-303, plan_usine_logicielle.md P6-ter case consolidation cochée +
  dashboard P6 mis à jour, progress.md, .env.example). Branche `feat/kg-memory-consolidation-f68`.

> **Décision clé** : Phase 1 seule ce cycle (consolidation + oubli). Le plan original F-68
> combinait 4 briques de 2 références (consolidation + scratch/notebook + extraction L0-L3 +
> recall hybride) — trop pour un cycle unique. Le format JSON typé (OutputField DSPy) a été
> préféré au format line-oriented pur qm car la convention projet (Judge/Security/Escalation)
> émet du JSON structuré, plus fiable sur 9B. L'oubli par rétention temporelle a été préféré
> au heat TencentDB (plus simple, miroir prune_idempotency, Pas de migration schéma).
> Phases 2+3 = cycles futurs conditionnels.

## Jalons de l'Itération (cycle F-68 Phase 2 — Recall cross-run scratch/notebook)
> Deux-tier DÉJÀ IMPLICITE après Phase 1 : scratch = observation/refutation (éphémère,
> pruné 30j), notebook = insight/escalation (durable, préservé cross-run par
> prune_old_claims). Promotion = consolidation Phase 1 (déjà câblée). Ce qui manquait =
> le RECALL (qm memory-service.ts:recall = 0 LLM). Décision utilisateur : Recall-centric +
> Global unique (top-N par récence, note « ignore si non pertinent »).

- [x] Étape P2-1 : `graph_orchestrator/knowledge_graph.py` — méthode `recall_lessons(kinds,
  limit)` (query SQL globale : SELECT content,kind,created_at WHERE kind IN (insight,
  escalation) AND status='open' ORDER BY created_at DESC LIMIT N, PAS de filtre entity_id
  ni run_id = global). Kinds défaut {insight,escalation} cohérent avec preserve_kinds.
- [x] Étape P2-2 : `graph_orchestrator/lesson_recall.py` (nouveau module, 0 LLM, miroir
  targeted_retest.py/judge_diff.py) — `recall_lessons` (wrapper) + `build_lessons_block`
  (formatage markdown numéroté + badges [LEÇON]/[ESCALATION] + note explicite + troncature
  truncate_output) + `DEFAULT_LESSON_KINDS`.
- [x] Étape P2-3 : `config.py` + `load_settings()` — memory_recall_enabled (défaut True),
  memory_recall_limit (défaut 8), memory_recall_max_chars (défaut 1500). `.env.example`
  + `.env` local (AGENTS.md §7). Opt-out MEMORY_RECALL_ENABLED=false.
- [x] Étape P2-4 : `workflows.py` — recall DÉBUT de run (après Router, avant boucle sous-
  tâches) → lessons_block → sub_dict['lessons']. Dégradation gracieuse try/except. Pas de
  checkpoint (cheap, refait pour fraîcheur).
- [x] Étape P2-5 : `nodes.py` — injection prompt Coder (pattern conditionnel original_content
  étendu, task.get('lessons') après original_content avant RAPPEL récence).
- [x] Étape P2-6 : `tests/test_lesson_recall.py` — 31 tests / 6 classes (recall_lessons KG
  10 + wrapper 2 + build_lessons_block 8 + prompt injection 4 + E2E workflow 4 + config 3).
  Migration tempfile.mkdtemp() → tmp_path fixture (review Kilo, anti-fuite disque).
- [x] Étape P2-7 : Script isolation `debug/run_lesson_recall.py` (convention F-89) — 3
  scénarios default/empty/scratch, KG temporaire isolé, vérif d'invariance (scratch non
  rappelé). `debug/print_lessons.py` corrigé (table 'claims' → 'claim', review Kilo CRITICAL).
- [x] Étape P2-8 : Validation — py_compile OK (7 fichiers), 31 tests PASS, suite pytest main
  final 785 passed / 11 failed (pré-existants confirmés identiques). Smoke recall : 4 leçons
  durables rappelées, scratch ignoré. 0 régression.

## Jalons de l'Itération (cycle F-76 — Contextualisation par package AGENTS.md localisés)
- [x] Étape F76-1 : `nodes.py execute_coder_node` — lecture `AGENTS.md` au commonpath des
  dirname des target_files, injection sous `### DIRECTIVES SPÉCIFIQUES AU COMPOSANT`.
- [x] Étape F76-2 : Défense path traversal (review Kilo WARNING) — containment realpath,
  workspace_root = os.path.realpath(os.getcwd()), fail-open silencieux.
- [x] Étape F76-3 : feature_list.json F-76 completed + plan_usine_logicielle.md case cochée.

## Synthèse merge (#50 + #51)
- [x] PR #50 (F-76) squash-merged → main (37e6ec0). Branche supprimée.
- [x] PR #51 (F-68 Phase 2) squash-merged → main (0694fac) après rebase (skip commit F-76
  base déjà mergé). Branche supprimée.
- [x] 3 retours Kilo adressés : CRITICAL print_lessons.py table + WARNING ×2 tempfile leaks
  + WARNING path traversal F-76.
- [x] Validation main final : py_compile OK, 785 passed / 11 pré-existants (0 régression),
  smoke recall OK, branches nettoyées.

## Jalons de l'Itération (cycle F-82 — Skill Finder, durcissement du scaffold)
> Constat initial : F-82 était **déjà scaffoldé et commité sur main** (`tools.py:586`
> + ReAct Architect `dspy_nodes.py:759`) mais marqué `pending` — sans tests, sans flag
> config, avec `shell=True` interpolé (injection), une regex dégénérée `\b(query)\b`,
> et une **réécriture du fichier source skills_loader.py** à l'exécution (salissait
> git, fragile). Décisions utilisateur : (1) durcir le scaffold ; (2) sécurité par
> **marqueurs skills.sh** (safe/verified) + allowlist configurable (pas d'API Socket) ;
> (3) **persistance durable** par manifeste (pas de mutation de source) ; (4) **toujours
> ON** + flag ; (5) **ligne regex dédiée multi-mots-clés** par skill installé.
- [x] Étape F82-1 : Branche `feat/f-82-skill-finder` + exploration (3 agents parallèles)
  cartographiant Architect/ReAct, skills_loader API, skills/ + config + patterns HTTP.
- [x] Étape F82-2 : `graph_orchestrator/skill_finder.py` (logique pure, standalone à
  l'import) — parse_skills_find_output (ANSI + marqueurs safe/unsafe), is_trusted
  (allowlist + blocage marqueur négatif), extract_trigger_keywords + build_trigger_regex
  (regex dédiée multi-mots-clés), install_skill (subprocess shell=False + validation
  regex composants + cmd.exe /c npx cross-plateforme), manifeste durable (register/
  load/refresh), search_and_install (orchestrateur fail-open).
- [x] Étape F82-3 : `tools.py` — `search_and_install_skill` devient wrapper mince (+
  param `triggers` hints). **Suppression** de `shell=True` et de la réécriture de
  `skills_loader.py` (→ manifeste).
- [x] Étape F82-4 : `skills_loader.py` — `DYNAMIC_SKILL_RULES.extend(load_dynamic_manifest())`
  au démarrage + helper `register_dynamic_rule` (no-op en fresh checkout → 0 régression).
- [x] Étape F82-5 : `dspy_nodes.py` — bloc ReAct F-82 gate par `if settings.skill_finder_enabled:`
  + wrapper propage `triggers`. ReAct + injection `research_summary` conservés.
- [x] Étape F82-6 : `config.py` — `skill_finder_enabled` (défaut True) +
  `skill_finder_trusted_authors` (CSV) + `.env.example` + `.env` local + `.gitignore`
  (`skills/installed-skills.json`).
- [x] Étape F82-7 : `tests/test_skill_finder.py` — 37 tests (parsing, trust, keywords/regex,
  install shell=False, manifeste, search_and_install E2E mocké, intégration skills_loader,
  @tool wrapper, config+gate source guard). 37/37 PASS.
- [x] Étape F82-8 : Validation — py_compile OK (6 fichiers) + suite complète 883 passed /
  7 failed / 1 skipped / 11 deselected. **0 régression confirmée** : les 7 échecs
  (test_read_gate ×4 + test_skill_lazy_loading ×3) sont pré-existants, strictement
  identiques au baseline via `git stash` (AUCUN lié au Skill Finder).
- [x] Étape F82-9 : État disque synchronisé (feature_list F-82 completed, contract
  critères 315-326, progress, README section 6). Branche `feat/f-82-skill-finder`. Commit + PR.
- [x] Étape F82-9b : Persistance des prompts de validation (retour user « ne pas perdre
  les prompts des bulles ») — `prompts/validation/` versionné (bubble_sort.md snapshot
  du prompt canonique + skill_finder_ai_sdk.md + skill_finder_react.md forceurs F-82) +
  README de convention + `scripts/load_prompt.py` (charge un .md → tasks.json coding[0],
  parse frontmatter id/target_files/expected_skill_finder). Le Prompt-Vault
  (references/, gitignoré) reste la banque externe ; prompts/validation/ est l'instantané
  minimal versionné. Loader smoke-testé (round-trip OK, cible temp, 0 modif tasks.json).
- [x] Étape F82-10 : Validation live (pipeline direct `search_and_install("react")`) —
  RÉUSSIE. `vercel-labs/agent-skills@vercel-react-best-practices` (auteur de confiance)
  installé dans `skills/`, manifeste `skills/installed-skills.json` écrit avec **regex
  dédiée** `\b(react|next|performance|optimization|...)\b`, `select_skills_for_coder`
  l'inclut (`[file-creation, coding, context7-research, vercel-react-best-practices]`).
  ⚠️ Bug trouvé + corrigé en live : `install_skill` n'injectait pas `-y --copy` → la CLI
  skills demandait une confirmation en subprocess non-tty (hang/timeout). Fix appliqué
  + test `assert "-y" in cmd and "--copy" in cmd`. Stopwords enrichis (should/shall/must).
  ⚠️ Finding production (suivi requis) : `npx skills add --copy` reproduit le skill dans
  ~27 dossiers d'agents (`.augment/`, `.codebuddy/`, `.continue/`...) — seul `skills/`
  nous intéresse. Nettoyage post-install (parse sortie CLI → rm agent dirs ≠ skills/) ou
  gitignore des patterns d'agents à ajouter dans un cycle futur. Working tree nettoyé
  post-démo (skill non bundlé — réinstallable en 1 commande).
- [x] Étape F82-11 : Validation **ReAct Architect LLM** — RÉUSSIE (Ornith-9B, GPU).
  `debug/run_architect.py @prompts/validation/skill_finder_ai_sdk.md` (corps seul) → le
  ReAct `SkillResearchSignature` a **appelé `search_and_install_skill`** et installé
  `vercel-labs/ai@ai-sdk` (auteur de confiance). Manifeste écrit avec **regex dédiée**
  `\b(ai-sdk|ai|streamtext|usechat|...)\b` (mots-clés extraits de la vraie description),
  `skills/ai-sdk/` créé, refresh_dynamic_rules in-memory, Architect terminé (exit 0,
  177.9s, plan 2 sous-tâches multifile). Le 9B décide donc bien d'invoquer l'outil.
  2 corrections appliquées lors de la validation :
  (1) ReAct `think=False` (avant `think=True` → hang 580s en thinking sur 9B, miroir F-47) ;
  (2) prompt `SkillResearchSignature` directif (« tu DOIS appeler l'outil si une techno est
  nommée ») — avant, le 9B répondait « Aucun » par défaut (décision paresseuse).
  ⚠️ Trouvaille wiring (suivi) : si le résumé ReAct finit en « Aucun » malgré l'install
  (incohérence petit modèle), l'Architect ne sélectionne pas le skill dans `subtask.skills`
  → le Coder (voie F-57 prioritaire sur subtask.skills) ne le voit pas au run courant ;
  en revanche les runs futurs le voient via le manifeste (catalogue Architect). À durcir si
  besoin (propager le nom installé au-delà du seul résumé LLM). Working tree nettoyé
  post-démo (skill non bundlé). Témoin négatif `bubble_sort.md` → « Aucun skill ajouté »
  (vanilla, pas de techno nommée) reste à confirmer en run.

## Jalons de l'Itération (cycle F-90 validation run + 7 hardening fixes, 2026-08-11)
> Objectif utilisateur : « faire un run complet sans erreur, si erreur corriger puis
> relancer jusqu'à un run réussi ». 9 runs E2E Bubble Sort pour diagnostiquer et fixer
> toute la chaîne. SUCCÈS au run #9 : sous-tâche 1 APPROUVÉE par le Judge au 1er cycle
> (1ère approbation en 9 runs). F-90 marquée completed.

- [x] F-90 : Architecte produit les 3 champs (visual/functional/rubric), injectés aux 3
  nœuds. Validé en isolation (debug/run_architect.py affiche les critères) + E2E (run #9).
- [x] Fix screenshot `filePath` : `_ScreenshotCapturingTool.forward()` (vision_callback.py)
  strippe le kwarg `filePath` avant délégation. Le mode `--isolated` de chrome-devtools-mcp
  rejette toute écriture disque → l'outil échouait AVANT de retourner l'image → la callback
  vision ne capturait rien → boucle de 25 steps (run #1). Règle anti-filePath dans
  devtools-preview/SKILL.md. Test test_strip_filepath_avant_delegation. Documenté AGENTS.md §7.
- [x] Fix Tester convergence : tester_max_steps 25→8, tester_timeout_s 600→480, règle 6
  « budget steps » (web_tester.py). 8 steps × ~55s pire cas = 440s < 480s → le Tester
  converge (max_steps gagne la course contre le wall-clock) au lieu de timeout.
- [x] Fix Tester fallback verdict : `_tester_max_steps_fallback` (nodes.py) scanne le step
  history et dérive un verdict comportemental (FAIL observé → failure, assertions PASS sans
  FAIL → success) quand l'auto-final-answer à max_steps ne parse pas. Évite la boucle de
  3 retries (~15 min) puis None. 6 tests (test_coder_hardening.py). Validé E2E run #5/#9.
- [x] Fix Judge vue deliverable complet : `_judge_deliverable_files` (dspy_nodes.py) UNION de
  target_files avec TOUS les fichiers source du run dir. Cause racine escalade run #5 :
  l'Architect split un app 3-fichiers en 3 sous-tâches → le Judge ne voyait qu'1 fichier
  → « css/js manquants » → rejet systématique ×3. 3 tests (test_judge_diff.py).
- [x] Fix règle CSS height inline : `coding/SKILL.md` section « RÈGLES CRITIQUES » eager-loaded
  (pas derrière une resource lazy). Pattern EXACT : ❌ `bar.style.height='0px'` à la création
  = BUG n°1 (barres invisibles au load), ✅ `(value*SCALE)+'px'` dès le createElement. Le 4B
  l'applique dès le run #9 (`Math.max(10, value*2)px`). C'était LE failure mode persistant
  (Static Tester catchait « height=0 » à chaque run).
- [x] Fix Static Tester settle wait : `_evaluate_visibility` (static_tester.py) probe maintenant
  `async () => { click; await setTimeout(150); probe; }` au lieu de `() => { click; probe; }`
  synchrone. Laisse les handlers async/re-render se stabiliser (réduit faux-positifs).
- [x] debug/run_architect.py : affiche les 3 champs F-90 (visual/functional/rubric) dans la
  sortie isolation (était manquant).
- [x] Validation run #9 : sous-tâche ts-html-structure APPROUVÉE par le Judge au 1er cycle.
  Tous les fixes actifs simultanément : barres visibles (height rule) → Static Tester PASS →
  Tester fallback=success → Judge deliverable view (3 fichiers) → APPROUVÉ. 52+ tests unitaires
  PASS (chrome_devtools + coder_hardening + config + judge_diff), 0 régression confirmée.

## Jalons de l'Itération (Meta-Analyste — post-mortem run9 F-90, 2026-08-12)
> Rôle Meta-Analyste (AGENTS.md §8) : `uv run python scripts/run_analyzer.py --log
> logs/e2e_f90_validation_run9.log`. Run9 = SUCCÈS (2 Judge APPROUVED) mais coûteux
> (7.59M tokens input, ~41 min). 3 problèmes récurrents identifiés, 1 traité ce cycle.

- [x] **MA-1 Diagnostic** : 3 signaux — (1) explosion contexte Coder (6.39M tokens / 43 steps,
  ~84% du budget, chantier lourd Context Epochs laissé hors périmètre) ; (2) `InterpreterError:
  Import of os is not allowed` côté Tester (log lignes 2771/2789) — le Tester (CodeAgent) a
  généré `import os` pour lire ses ressources de skill, la sandbox n'autorise que
  ['unicodedata','collections','re','math','time','random','statistics','itertools','queue',
  'datetime','stat'] → crash + code fragmenté (variable `resource_files` perdue entre steps) ;
  (3) saturation llama-server (2× Pydantic→DSPy rescue→Connection error, déjà atténué par
  AUDIT_PARALLEL=false, infra).
- [x] **MA-2 Fix `import os` Tester** (jumeau du fix `import time` F-61/RAA-2, même failure
  mode) : (a) règle n°4 `web_tester.py` réécrite — OUTILS `read_file`/`list_directory` préférés
  pour LIRE, built-ins `open()`/`read()` restent interdits par la sandbox ; (b) safety net
  `additional_authorized_imports=["os", "subprocess"]` sur le `CompactingCodeAgent` du Tester.
  **DÉCISION UTILISATEUR (principe TESTER = CODER)** : le Tester écrit des scripts de test et
  doit pouvoir coder comme le Coder → même set d'imports que `nodes.py:1071` (os + subprocess,
  1:1). Premiere version du fix n'avait mis que `["os"]` (subprocess écarté par « frontière de
  périmètre » — sur-prudent, corrigé). Doctrine F-33 « un prompt seul ne suffit jamais » :
  la règle steer vers les outils, le safety net rattrape le slip sans crash. Validation :
  py_compile OK + sous-ensemble pytest (test_tester_dispatch + test_config + test_static_tester)
  47 passed / 1 skipped / 0 failed. Branche `fix/tester-import-os-guard`.
- [ ] **MA-3 (à évaluer, hors petite tâche)** : explosion contexte Coder (compaction L4
  existante via CompactingCodeAgent mais insuffisante — envisager Context Epochs / budget
  par step plus strict). Cycle lourd, reporté.
- [x] **MA-4 Validation live GPU** (`debug/run_web_tester_standalone.py` retargeté vers
  `runs/2026-08-11_2109_bubble_sort_multifile_v6/index.html`, Ornith-9B reasoning off, 8 steps).
  **RÉSULTAT : bug `import os` ÉLIMINÉ.** Sur les 8 steps, le Tester n'a JAMAIS tenté `import os`
  — il a utilisé l'outil `read_file` (steering règle n°4). Zéro `InterpreterError: Import of os`.
  Le safety net `additional_authorized_imports=["os","subprocess"]` n'a même pas eu à agir (cas
  idéal : la règle a suffi). Le fix MA-2 est donc VALIDÉ en run réel.
- [ ] **MA-5 (révélé par la validation, AUTRE cycle, hors périmètre MA)** : le run s'est terminé
  en `failure` non à cause d'`import os` mais d'un failure mode DISTINCT pré-existant — (a) le
  Tester a brûlé ses 8 steps à lire les 5 `resources/` F-92 de la skill (progressive disclosure)
  sans jamais atteindre le test réel (0 navigate_page, 0 assertion, 0 screenshot) ; (b) 3 steps
  perdus sur des erreurs de format de chemin Windows (`file:///...` → [Errno 22], `/D:/GIT/...`
  (préfixe MSYS) → WinError 123) avant de trouver `D:/GIT/...`. Le fallback F-90 a dérivé un
  verdict `failure` correct. Pistes cycle futur : plafonner/réduire le nb de resources lues par
  le Tester (ou injecter leur contenu en eager plutôt que lazy), et durcir le prompt chemin
  Windows (la directive existante n'a pas empêché le modèle d'utiliser `file:///` depuis les
  liens markdown de la skill).

## Jalons de l'Itération (cycle MA-5 — durcir le Tester : resources skill + chemins Windows, F-97)
> Reprise du thread MA-5 laissé ouvert ci-dessus. Périmètre = les 2 failure modes révélés par la
> validation live du fix MA-2. Investigation approfondie (2 subagents Explore) → les racines
> réelles étaient PLUS PRÉCISES que le framing MA-5 initial (bug générateur `view_file` n'existe
> pas + piège `file:///` correct pour un outil, fatal pour l'autre).

- [x] Étape MA5-1 : Plan approuvé (EnterPlanMode → ExitPlanMode). Décisions clés : (a) résoudre
  la progressive disclosure F-92 **côté serveur** pour le Tester (inline) plutôt que compter sur
  le prompt — l'inline est strictement meilleur pour un agent one-shot qui a besoin de TOUT le
  contenu ; (b) garde logiciel de normalisation en tête des outils fichier (doctrine F-33) + prompt
  réécrit, pas prompt seul.
- [x] Étape MA5-2 : `graph_orchestrator/path_utils.py` (NEW) — `normalize_tool_path` (pur chaîne,
  SANS abspath pour préserver relatifs + hashing read_gate ; strippe `file:///` variantes + MSYS
  `/d/` ; fail-open). Aucune règle `^([a-zA-Z])/` sans slash initial (sinon `src/a.js` → `S:/rc/a.js`).
- [x] Étape MA5-3 : `tests/test_path_utils.py` (NEW, 19 tests) — 3 variantes de slashes, `/X:/`,
  MSYS `/x/`, anti-corruption relatifs, backslash inchangé, déjà-correct, vide/non-str, idempotence.
  19/19 PASS.
- [x] Étape MA5-4 : `tools.py` — `read_file` + `list_directory` appliquent `normalize_tool_path`
  en tête (défense en profondeur, bénéficie au Coder). Import ajouté. +2 tests d'intégration
  dans `test_tools.py` (read_file/list_directory acceptent un `file:///` sur tmp_file/tmp_dir).
- [x] Étape MA5-5 : `skills_loader.py` — `load_skill_body_resolved(name)` : inline les
  `resources/*.md` sous `### <title>` (tri déterministe) + RETIRE la section pointeur
  « ## Dynamic Resources » (sinon l'instruction `view_file` reste, contradictoire) + bannière
  anti-re-read. Fallback corps brut si pas de `resources/`. Skill absent → `""`.
- [x] Étape MA5-6 : `tests/test_skill_resolve.py` (NEW, 7 tests) — mécaniques (tmp skills via
  monkeypatch SKILLS_DIR) + intégration sur la VRAIE skill `web-tester` (resources inlinées, plus
  de `view_file`, plus de liens `file:///.../resources/`). 7/7 PASS.
- [x] Étape MA5-7 : `web_tester.py` — `:150` utilise `load_skill_body_resolved` (gated flag,
  défaut ON) ; `:250` règle chemins réécrite (`file:///` RÉSERVÉ à `navigate_page` ;
  `read_file`/`list_directory` attendent un chemin simple, note que la normalisation auto rattrape).
- [x] Étape MA5-8 : `config.py` + `.env.example` + `.env` — `tester_inline_skill_resources: bool
  = True` + `_get_bool("TESTER_INLINE_SKILL_RESOURCES", True)` + report local.
- [x] Étape MA5-9 : Racine générateur — `scripts/refactor_skills.py` `view_file` → `read_file` +
  « read on-demand, NOT all upfront ». Hygiène ressource `evaluation_criteria` : « 12 max steps »
  (stale, cap réel 8) → « TESTER_MAX_STEPS, par défaut 8 ».
- [x] Étape MA5-10 : Validation — py_compile OK (9 fichiers). 28 nouveaux tests PASS. Suite
  complète **892 passed / 8 failed** (les 8 STRICTEMENT pré-existants `test_read_gate` ×4 +
  `test_skill_lazy_loading` ×3 + `test_guard` ×1, confirmés identiques via `git stash`). **0 régression.**
- [x] Étape MA5-11 : État disque synchronisé — feature_list.json +F-97 (completed), contract.md
  +critères 327-336, progress.md (ce bloc), .gitignore (.pytest_tmp/). Branche
  `fix/tester-resources-paths-ma5`. Commit + push + PR.

> **Décision clé (a)** : résoudre la progressive disclosure côté serveur plutôt que durcir le stub.
> Le Tester (one-shot, 8 steps) a besoin de TOUT le contenu de la skill — lire 5 resources
> dynamiquement = 5 steps + 5× tokens en contexte dynamique, alors que l'inline = 1× tokens en
> system prompt (cached). La progressive disclosure F-92 n'est bénéfique QUE pour les agents qui
> lisent à la demande ; le Tester non. Le bug générateur `view_file` (qui n'existe pas dans le
> projet) rendait en plus la consigne inapplicable. Le loader `load_skill_body_resolved` est
> générique (réutilisable par d'autres nœuds si besoin) et préserve F-92 sur disque.
> **Décision clé (b)** : un garde logiciel de normalisation (et pas seulement un prompt) —
> `file:///` est un token correct pour `navigate_page` et fatal pour `read_file`/`list_directory` ;
> aucun prompt ne peut rendre ce dualisme infaillible. `normalize_tool_path` rend le bug impossible
> quel que soit le comportement du modèle, SANS corrompre les chemins relatifs (pas d'abspath).

## Jalons de l'Itération (cycle Coder Stop Condition & Navigation HTML-only — PR #70)
- [x] Étape CSC-1 : Diagnostic empirique du run de 2 heures — le Coder naviguait sur `styles.css` avec DevTools MCP, générant un DOM vide (`<pre>`), entraînant des assertions JS fausses et une boucle de 35 steps de tests redondants.
- [x] Étape CSC-2 : Ajout de l'Invariant universel 13 (Deterministic Stop Condition) dans `graph_orchestrator/prompts.py` (obligation d'appeler `final_answer` dès les tests initiaux validés).
- [x] Étape CSC-3 : Interdiction formelle de naviguer sur des fichiers non-HTML (`.css`, `.js`, etc.) dans `skills/devtools-preview/SKILL.md` et dans le prompt du `coder_frontend`.
- [x] Étape CSC-4 : Validation en isolation via `debug/run_coder.py` (Qwen 4B) : 3 fichiers générés (`index.html`, `styles.css`, `script.js`), 0 erreur console, rendu visuel validé, fuzzing boutons réussi, sortie propre via `final_answer` à l'étape 14 (sans boucle).
- [x] Étape CSC-5 : Revue Kilo validée sans réserve ("No Issues Found | Recommendation: Merge"), PR #70 squash-mergée et branche supprimée.

## Jalons de l'Itération (cycle Update References — pull amont 2026-08-14)
> Workflow `references/PROCEDURE-UPDATE-REFERENCES.md` (5 étapes). Synchronisation périodique
> des dépôts amont + veille + backlog. AUCUN code de production modifié.

- [x] Étape UR1 : `update_references.py` exécuté — **25 dépôts mis à jour / 19 à jour /
      1 erreur** (LlamaBot : historique réécrit en amont « forced update » → resynchronisé
      `git reset --hard origin/main` @884cd2a, fix SSRF page-clone). Rapport
      `references/update_report.md` régénéré (25 sections, ~5 700 fichiers changés).
- [x] Étape UR2 : analyse des nouveautés par **3 subagents Explore parallèles** (7 dépôts
      harness cœur + 7 skills/prompts + 12 frameworks). Faits saillants : qm `goal.ts`
      (enforcement de but anti faux-« fini »), hermes `verify/` (recettes d'exécution +
      readiness HTTP), opencode compaction réécrite POUR PETITS MODÈLES, learn-claude-code
      s08 réordonné (archive disque .transcripts), pi §3.9 `overflowRecoveryUsed`, open-swe
      `turn_checkpoint.py` (snapshot git PAR TOUR), Anthropic `prompt-audit` (signaux
      greppables), Claude Code v2.1.224→v2.1.232 (WaitForMcpServers + anti
      permission-laundering + safety=frontière non retryable), `claude-science.md` (folds =
      search queries + frame), davidondrej groupe 10 password managers, brooklyn `babysit`,
      deer-flow budgets AGENTS.md + fix dangling tool calls, crush MCP init gate, openfox
      retry pré/mid-stream. Fiches déjà auditées : fichiers clés inchangés ou évolutions
      sans changement de design (qm context-compaction, hermes trajectory_compressor,
      loopx event_sourced_state).
- [x] Étape UR3 : `feature_list.json` + **7 features F-99..F-105** (toutes `pending` ;
      invariant respecté : AUCUNE feature `completed` modifiée). 104 features au total
      (84 completed / 19 pending / 1 in_progress).
- [x] Étape UR4 : `plan_usine_logicielle.md` + **10 cases `[ ]` datées « update références
      2026-08-14 »** (P3 enforcement de but, P6 recettes verify, P8 retry v2, P8-bis
      checkpoint git/tour + sécurité groupe 10, P9 compaction v2, P0-bis prompt-audit +
      budgets guidance + invariants CC, P10 routeur skills + skills écrites par l'agent,
      P11 prompt envelopes + event bus). Invariant respecté : 0 case cochée modifiée
      (10 insertions pures, vérifiées par `git diff`).
- [x] Étape UR5 : état disque synchronisé (progress.md ce bloc) + commit et push
      sur main via cherry-pick (procédure « branche feature active » — la session était sur
      `fix/update-llamacpp-asset-matching`).

## Jalons de l'Itération (cycle F-106 — clôture du journal plat, 2026-08-14)
> Décision utilisateur : « toute mention du journal plat doit disparaître, ainsi que le
> fichier à la fin, pour ne plus jamais l'utiliser ». Diagnostic préalable (réponse à la
> question « pourquoi écrit-on encore dedans ? ») : l'écrivain était l'ASSISTANT en fin
> de cycle (convention héritée), pas le code de production ; et la migration F-75 avait
> perdu les dates historiques (194 événements tous horodatés à la date de migration —
> bug migrate_log.py : la date d'en-tête était capturée mais jamais utilisée) avant que
> le fichier ne soit supprimé PUIS re-créé à la main le 2026-08-12.

- [x] Étape F106-1 : Diagnostic — base event_stream.duckdb dormante (dernier write
  2026-08-05 : seul le Coder 4B pouvait l'alimenter de sa propre initiative via l'outil
  log_event ; aucun nœud du graphe n'émet d'événement lifecycle) tandis que le fichier
  plat reprenait sa croissance à chaque cycle docs.
- [x] Étape F106-2 : `scripts/recover_log_history.py` — récupération depuis git (47
  versions, les deux ères du fichier via --follow, pic 198 entrées avant la suppression
  F-75), parsing `## [date] type | titre` (regex `[\w-]+` corrigeant l'absorption de
  `P8-bis` par l'ancienne regex), union dédupliquée par (date, type, titre), sous-titres
  non datés rattachés au corps, import DATÉ (created_at = date d'en-tête, fallback date
  du commit de première apparition), idempotent (clé event_type+titre), backup base +
  remplacement documenté des 194 lignes 'legacy' non datées.
- [x] Étape F106-3 : Migration exécutée — base finale 199 événements datés
  (2026-07-29 → 2026-08-14, run_id legacy_md) ; 3 coquilles source corrigées
  ([2026-01-08] → 2026-08-01 pour F-41/F-42/F-43) ; entrée P8-bis F-43 récupérée ;
  préambule « 🔧 INFOS À SAVOIR » préservé.
- [x] Étape F106-4 : `scripts/log_event.py` — CLI d'historisation pour l'ASSISTANT
  (même table/canal que l'outil du graphe ; options --run-id/--node/--date). Dogfoodé
  immédiatement (événements #394 diag + #395 done, run_id f-106).
- [x] Étape F106-5 : Suppression définitive (git rm) du fichier journal et de
  `scripts/migrate_log.py` (obsolète). Purge de TOUTES les mentions : AGENTS.md §2D
  réécrit (règle critique « AUCUN JOURNAL PLAT », interdiction de recréation, deux
  canaux runtime/assistant documentés), progress.md 21→0, contract.md (Critère 4
  réécrit + section F-106 critères 354-358), feature_list.json (F-04/F-74 réécrits,
  +F-106), plan_usine §P11 annoté FAIT-partie-plate, references_audit.md, commentaire
  nodes.py, docstrings log_event.py. Tombstones assumées (3) : la règle d'interdiction
  AGENTS.md, le script de récupération (qui doit nommer le chemin git), l'audit du
  dépôt externe opencode (fichiers du tiers).
- [x] Étape F106-6 : Validation — 13 tests PASS (`tests/test_log_recovery.py` : parser
  6, created_at fallbacks 1, dedup multi-versions 1, insertion remplacement legacy +
  idempotence + dry-run 3, git-walk réel sur repo tmp 1, CLI 2). py_compile OK.
  Sanity 43/43 (test_guard + test_stall_detector, import nodes.py). Sweep grep final
  vérifié. F-74 reste pending pour la part runtime (instrumentation workflows +
  runs_history + rétention).

## Jalons de l'Itération (cycle F-99 — Goal Enforcement, P3, 2026-08-14)
> 1re feature du backlog F-99..F-105 (update références 2026-08-14). Prolonge le fil
> anti-loop signature (F-36 LoopGuard → F-88 StallDetector → F-99 garde comportementale
> du faux « j'ai fini »). Rebasée sur main post-merge F-106 (4227b55).

- [x] Étape F99-1 : Exploration qm (`src/harness/goal.ts` + `grind.ts`) + points
  d'insertion (`run_with_retry` où F-36/F-88 sont déjà branchés, `execute_coder_node`,
  config). Design : audit de complétion DÉTERMINISTE (le disque = état autoritaire)
  + prompt de continuation qm + bornes (impasse/deadlock/cap).
- [x] Étape F99-2 : Module `graph_orchestrator/goal_enforcer.py` — 4 mécanismes qm
  (continuation prompt « NON PROUVÉE » avec preuves manquantes concrètes, blocked
  après 3 MÊME impasse, auto-waiver après 5 rounds sans tool call, token cap 2M =
  wind-down unique). Audit mode-aware (création stricte / correction allégée).
  Objectif échappé HTML + encapsulé <objectif> (anti-injection, miroir qm).
- [x] Étape F99-3 : Branchement — `run_with_retry` (param `goal_enforcer`, metering
  par attempt, RAPPEL générique supprimé sur les rounds de continuation) +
  `execute_coder_node` (GoalEnforcer depuis task content/target_files/iteration/
  _is_web_task) + config (4 settings) + .env.example + .env.
- [x] Étape F99-4 : Tests — 22 PASS. BUG D'INTÉGRATION découvert et corrigé :
  `loop_guard.known_tools` (F-36) ignorait multi_replace/check_js_syntax/outils
  DevTools → aucune preuve verify-after visible en chemin CodeAgent (l'audit
  web échouait systématiquement). Liste étendue (13 outils), exemptés
  observationnels préservés dans record().
- [x] Étape F99-5 : Validation — suite complète **1035 passed / 0 failed / 1 skipped**
  (+22 vs baseline 1013), py_compile OK. Écarts consciencieux vs qm documentés
  (boucle bornée max_retries, delta tool calls adapté à la purge mémoire, pas
  d'outil update_goal, objectif tronqué 4000).
- [x] Étape F99-6 : État disque synchronisé (feature_list F-99 completed, contract
  critères 359-364, plan case P3 cochée, progress ce bloc, événements journalisés
  via scripts/log_event.py run_id f-99 — convention F-106).

## Jalons de l'Itération (runs E2E de validation F-99/F-97/PR#70 — 2026-08-14)
> Objectif : valider en live les 5 changements comportementaux accumulés depuis le run #9
> (F-72, F-97, PR #70, F-99, F-106). Prompt canonique Bubble Sort (multifile-v6),
> WORKFLOW_MODE=coding, spawn backends. 3 runs, dont l'analyse a produit 2 durcissements (PR #74).

- [x] Run #1 (échec infra) : Coder 3/3 tentatives en `exceed_context_size_error` — requests
  33-39k tokens > n_ctx 32768 du llama-server Qwen. Correctif : FAST_CONTEXT 32768 → 49152
  (local .env + défaut .env.example). F-99 non en cause (0 déclenchement, mort par 400 serveur).
- [x] Run #2 (échec révélateur) : final_answer VALIDE + 3 fichiers sur disque au 3e attempt,
  mais (a) continuation F-99 sur le DERNIER attempt (budget épuisé → échec technique au lieu
  du Judge) et (b) audit sur mémoire purgée (preuves des tentatives précédentes invisibles).
  Correctifs PR #74 : waiver dernier attempt + preuves cumulées cross-attempts + reason
  listant les preuves manquantes.
- [x] Run #3 (SUCCÈS) : **F-82-ts-01 APPROUVÉ par le Judge** 🚀 (2e approbation du projet).
  F-99 en action : T1/T2 défiées (le 4B voulait finir SANS AUCUN write — « Je peux maintenant
  appeler final_answer ») → le modèle a produit les 3 fichiers au fil des tentatives (styles
  21:57, script 22:05, index 22:08) → T3 même impasse → blocked-waive → Judge a arbitré et
  approuvé. Chaîne complète : Linter → Static Tester (4.1s) → Tester (fallback verdict) →
  Security → Judge → consolidation. Métriques attempt réussie : Coder 130.7s/184k tokens,
  Tester 286s/180k. Signaux validés : PR #70 (0 navigation non-HTML), F-97 (0 erreur de
  chemin réelle — l'unique grep = le texte du prompt), F-90 (critères présents), F-68
  (8 leçons rappelées), F-106 (event stream + consolidation OK).
- [x] Durcissement final (run #3 a révélé le dernier angle mort : la COMPACTION ampute
  memory.steps — « AUCUN appel d'écriture » alors qu'index.html venait d'être écrit) :
  preuve par le DISQUE d'abord (création), git status des cibles (correction, source
  autoritaire F-53), verify-after retiré des bloqueurs (redondant F-50 + Static Tester).
  28 tests F-99 PASS, 87 guards, py_compile OK.
- [x] État disque synchronisé : feature_list F-99 (validation E2E consignée), contract
  critères 365-367, progress ce bloc, événements #398-#402 (run_id e2e-f99-validation),
  analysis_report.md régénéré.
