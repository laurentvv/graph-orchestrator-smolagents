# État d'Avancement du Sprint

## Objectif Actuel
- [x] Valider le coding workflow de bout en bout sur un prompt "landing page premium"
      (Architect → Coder → Tester → Judge → verdict). ATTEINT (run #12 HTML propre,
      run #13 cycle complet + reprise après crash multi-crash).
- [ ] Cycle TESTER POLYVALENT + AUTO-CORRECTION stderr (Priorité 2) : dispatch
      multi-techno (web+python) + troncature anti Context-Overflow. En cours.

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

## Jalons bootstrap (faits)
- [x] Création agent.md (specs gestion d'état).
- [x] Initialisation feature_list.json, contract.md, progress.md, log.md.

