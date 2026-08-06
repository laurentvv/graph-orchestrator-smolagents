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
- [x] Initialisation feature_list.json, contract.md, progress.md, log.md.

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
  Résultats consignés dans log.md.
- [ ] Étape CA-8 : Décision : migrer execute_coder_node vers CodeAgent (si gain prouvé)
  OU garder TCA (si CodeAgent n'apporte rien). Création feature F-XX le cas échéant.
  → EN ATTENTE : un 2e test sur contenu plus lourd (multi-fichiers / HTML 3000+
  lignes) confirmerait le gain sur le scénario-douleur (corruption JSON du TCA).


## Jalons de l'Itération (Amélioration Plan Usine Logicielle)
- [x] Étape 1 : Analyse des audits LlamaBot, Deer Flow, Crush, OpenCode, Aider.
- [x] Étape 2 : Création de l'artefact Implementation Plan soumis pour validation.
- [x] Étape 3 : Application des modifications au plan_usine_logicielle.md.
- [x] Étape 4 : Mise à jour de log.md, progress.md, et feature_list.json.

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
  +F-40, progress.md, plan_usine_logicielle.md case P13 cochée, .gitignore runs/, log.md).

## Jalons de l'Itération (nœud PromptRefiner — F-39, meta-prompt avant l'Architect)
- [x] Étape PR-1 : Exploration (Router/Architect DSPy, checkpoint, test patterns) + recherche web
  Kilo Code/Cline "Enhance Prompt" (sources consignées log.md). Plan approuvé (Phase 1 seule ;
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
  .env.example, log.md). Commit + push + PR.

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
  +F-36/F-37, progress.md, plan_usine_logicielle.md, .env.example, log.md).
- [x] Étape TR-7 (Tâche 3 — Guard bash denylist, F-38, P8-bis) : bash_guard.py
  (check_bash_command, denylist regex case-insensitive Unix+Windows+cross, message
  pédagogique jamais d'exception). Branché dans tools.py bash_command AVANT subprocess.run.
  Config BASH_GUARD_ENABLED. Patterns debuggés via fichier temp (lookbehind/lookahead pour
  flags /s /q /f, `-[rRfF]{1,3}` pour rm). 66 tests PASS.
- [x] Étape TR-8 : Suite pytest complète → 371 passed / 0 failed (305 avant + 66 nouveaux).
  0 régression.
- [x] Étape TR-9 : État disque synchronisé (contract.md +8 critères 88-95, feature_list.json
  +F-38, progress.md, plan_usine_logicielle.md P8-bis ❌→🟡 + sous-case guard, README.md,
  .env.example, log.md). Commit + push + PR.

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
  +F-36/F-37, progress.md, plan_usine_logicielle.md, .env.example, log.md).

## Jalons de l'Itération (P8 — Orphan Repair, anti-corruption d'historique, F-41)
- [x] Étape OP-1 : Contexte — P8 du plan (ligne 129), blueprint s08_context_compact, structure smolagents memory.steps/ActionStep lue.
- [x] Étape OP-2 : `orphan_repair.py` — niveau messages (`repair_orphan_tool_results`, FAKE_INTERRUPTED={{status:error,error:Interrompu}}) gérant tool_use + forme sérialisée type=function/function.name, réponse via tool_use_id/tool_call_id/id.
- [x] Étape OP-3 : `orphan_repair.py` — niveau steps (`repair_orphan_steps` : ActionStep avec tool_calls sans observations/error/is_final_answer → observations=FAKE_INTERRUPTED).
- [x] Étape OP-4 : Intégration défensive (`try/except Exception: pass`) dans `nodes.run_with_retry` (bloc P8, ~lignes 174-189) AVANT chaque `agent.run`.
- [x] Étape OP-5 : Tests — `tests/test_orphan_repair.py` 11 tests ; vérif `orphan+guard+loop_guard` = 35 passed ; suite complète = 405 passed / 0 failed (0 régression).
- [x] Étape OP-6 : État disque synchronisé — feature_list.json +F-41, contract.md +critères 114-121, plan_usine_logicielle.md P8 [x], progress.md, README.md, log.md.

## Jalons de l'Itération (P8 — Sanitizer, Auto-typage des arguments d'outil, F-42)
- [x] Étape SZ-1 : Contexte — petit LLM émet des args malformés (offset="1, 80", replace_all="true") → TypeError validation smolagents → retries gaspillés. Flux de validation tracé (agents.py:1476 validate_tool_arguments). Chemin CodeAgent confirmé : executor local expose les outils et les appelle via `__call__` directement (PAS execute_tool_call/validate_tool_arguments) → proxy `__call__` intercepte avant `forward`.
- [x] Étape SZ-2 : `sanitizer.py` niveau coercition — `_parse_string_to_structure` (json.loads→ast.literal_eval fallback), `_coerce_integer` (dernier entier d'une chaîne), `_coerce_number`, `_coerce_boolean` (true/1/yes/on→True), `coerce_value` (array/object/string/None respecté, best-effort), `sanitize_tool_arguments` (clés connues seulement, non-dict intact).
- [x] Étape SZ-3 : `sanitizer.py` niveau proxy — `SanitizedTool(BaseTool)` copie name/description/inputs/output_type, intercepte `__call__` pour coerçer kwargs avant de déléguer à l'outil réel ; `wrap_tool` + `sanitize_tools(enabled)` no-op quand disabled.
- [x] Étape SZ-4 : Config `sanitizer_enabled` (env `SANITIZER_ENABLED`, défaut True) dans `config.py` (champ dataclass + load_settings).
- [x] Étape SZ-5 : Branchement `nodes.execute_coder_node` + `execute_architect_node` via `sanitize_tools(..., enabled=settings.sanitizer_enabled)`.
- [x] Étape SZ-6 : Tests — `tests/test_sanitizer.py` 23 tests (coercion 13 + sanitize 4 + proxy 3 + wrap 3) ; 23/23 PASS.
- [x] Étape SZ-7 : Suite pytest complète → 417 passed / 0 failed (394 baseline + 23 nouveaux), 0 régression. web_tester_functional désélectionné (nécessite Chrome/npx).
- [x] Étape SZ-8 : État disque synchronisé — feature_list.json +F-42, contract.md +critères 122-129, progress.md, README.md, log.md.

## Jalons de l'Itération (P8-bis — Idempotence des effets de bord, F-43)
- [x] Étape ID-1 : Contexte — replays de checkpoint réappliquent les effets de bord non-idempotents (append_file, pip install). Référence qm idempotency-store.ts (once(key, fn), inflight + done + backing + rétention 14j). Mécanisme de replay tracé (save_coding_state granularité début d'itération → Coder rejoue).
- [x] Étape ID-2 : `idempotency.py` — `IdempotencyStore` (once/committed/reset/_prune_if_due, threading.Lock, backing DuckDB) + `make_op_key` + contexte module-level (`_scoped_idempotency`/`get_current_store`/`set_current_store`/`clear_current_store`). Port Python fidèle de qm.
- [x] Étape ID-3 : `knowledge_graph.py` — table `idempotency_record(run_id, op_key, created_at, PK)` + `save_idempotency` (INSERT OR IGNORE) / `is_idempotency_committed` / `prune_idempotency` / `clear_idempotency`. Import `datetime`/`timedelta` ajouté.
- [x] Étape ID-4 : `config.py` + `.env.example` — `idempotence_enabled` (défaut True) + `idempotency_retention_days` (défaut 14).
- [x] Étape ID-5 : Branchement `workflows.py` — store créé après kg+run_id+checkpoint, corps wrappé `with _scoped_chdir(...), _scoped_idempotency(_idem_store):` (composition sans réindentation). `clear_idempotency(run_id)` aux 2 sites `clear_checkpoint` (FRESH_START + fin de run).
- [x] Étape ID-6 : Branchement `tools.py` (`append_file` via `once` + `_do_append` closure, write_file NON wrappé) + `python_tester.py` (`_install_module` via `_install_module_or_raise`/`_InstallFailed`, échec non marqué done).
- [x] Étape ID-7 : Tests — `tests/test_idempotency.py` 25 tests (store 10 + KG 4 + scoped 3 + make_op_key 4 + intégration append 2 + intégration pip 2) ; 25/25 PASS.
- [x] Étape ID-8 : Suite pytest complète → 442 passed / 0 failed (417 baseline + 25 nouveaux), 0 régression. web_tester_functional désélectionné (nécessite Chrome/npx). État disque synchronisé (feature_list.json +F-43, contract.md +critères 130-140, plan_usine_logicielle.md P8-bis [x], progress.md, README.md, log.md).

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
- [x] Étape RP-10 : État disque synchronisé (feature_list.json +F-44, contract.md +critères 141-149, plan_usine_logicielle.md P0+P0-bis+P6 cochés, progress.md, README.md, log.md).

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
  statutées), feature_list.json +F-45, contract.md +critères 150-155, progress.md, log.md.

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

## Prochain cycle planifié — F-48 : Vision Coder (auto-validation visuelle)
- [ ] Étape F48-1 : think=false Coder — smolagents OpenAIServerModel → /api/chat (prérequis :
  débloque vision + gain budget code). Le Coder subit AUSSI le thinking forcé sur /v1.
- [ ] Étape F48-2 : Outil screenshot pour le Coder — capture la page HTML générée après
  write_file, l'expose au Coder comme image (Gemma 4 multimodal).
- [ ] Étape F48-3 : Skill Coder verify-after visuel — après write_file UI, screenshot +
  auto-éval (titre lisible, layout non cassé) + search_replace si fix nécessaire.
- [ ] Étape F48-4 : Validation — comparatif qualité code avec/sans thinking + régression
  Bubble Sort et Nimbus.
- [ ] Étape VC-11 (cycle suivant) : Fix Tester querySelector (ACTION IMMÉDIATE documentée).

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
- [x] Étape RAA-5 : Mise à jour exhaustive des documents de suivi (eature_list.json, plan_usine_logicielle.md, README.md, progress.md, log.md).
- [ ] Étape RAA-6 : Attente de la fin du run E2E, analyse post-mortem finale avec un_analyzer.py, rapport de validation, et préparation pour commit/PR.

## Jalons de l'Itération (cycle Audit cohérence INDEX références — enrichissement plan)
- [x] Étape ACI-1 : Constat initial — fiches 19-23 déjà intégrées via F-66 (completed). INDEX.md + inventory.json = commit 9dc59c0.
- [x] Étape ACI-2 : Audit de cohérence exhaustif (agent Explore) — Hall of Fame INDEX croisé contre plan_usine_logicielle.md. 18 écarts identifiés, gisement principal = qm (4 briques 🟢 Haute sur 9 oubliées).
- [x] Étape ACI-3 : Enrichissement plan_usine_logicielle.md (cases `[ ]` uniquement, 0 code modifié) — P3-bis (+2), P6-bis (+2), P6-ter NOUVELLE sous-section (+1 bloc), P9 (+1 case + garde), P1 (+1 case + précision source), P2 (+1 case), P10 (+2 cases), tableau état avancement mis à jour.
- [x] Étape ACI-4 : feature_list.json +4 features pending (F-68 mémoire KG qm, F-69 budget+queue qm, F-70 diff+métriques Judge, F-71 skeleton libcst). 72 features total. JSON validé.
- [x] Étape ACI-5 : log.md + progress.md synchronisés. Périmètre = travail documentaire uniquement (aucun code de production modifié, aucun test impacté).

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
  +critères 215-227, plan_usine_logicielle.md P1 case cochée, progress.md, README.md,
  log.md). Commit + push + PR.

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
  progress.md, README.md section Coder, log.md). ATTENTE commit/PR.
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
- [x] Étape T3-9 : État disque synchronisé (feature_list.json +F-81, progress.md, README.md,
  log.md). Branche `feat/static-tester-tier3-temporal`. Commit.

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
