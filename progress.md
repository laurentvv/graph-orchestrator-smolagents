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

## Jalons bootstrap (faits)
- [x] Création agent.md (specs gestion d'état).
- [x] Initialisation feature_list.json, contract.md, progress.md, log.md.

