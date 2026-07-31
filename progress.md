# État d'Avancement du Sprint

## Objectif Actuel
- [x] Valider le coding workflow de bout en bout sur un prompt "landing page premium"
      (Architect → Coder → Tester → Judge → verdict). ATTEINT (run #12 HTML propre,
      run #13 cycle complet + reprise après crash multi-crash).
- [ ] Cycle TESTER POLYVALENT + AUTO-CORRECTION stderr (Priorité 2) : dispatch
      multi-techno (web+python) + troncature anti Context-Overflow. En cours.
- [ ] Cycle CONTEXT7 (doc libs à jour, anti-hallucination d'API) : intégration sur
      3 nœuds + skill stratégique. Implémentation TERMINÉE, validation runs à venir.
- [x] Cycle TESTER FONCTIONNEL (assertions comportementales, F-20) : le tester ne
      testait que l'absence de crash → bugs de logique validés à tort. Implémentation
      TERMINÉE (skill puppeteer_* + assertions, propagation spec, Judge équipé).

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
- [ ] Étape DI-9 : Runs comparatifs TCA vs CodeAgent sur le dashboard incrémental.
  HYPOTHÈSE : CodeAgent devrait nécessiter moins de steps (N append dans 1 step) que le TCA (1 step/section).
- [ ] Étape DI-10 : Décision : migrer execute_coder_node vers CodeAgent (si gain prouvé sur le
  découpage) + intégrer append_file au prompt du Coder prod. Création PR.

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

