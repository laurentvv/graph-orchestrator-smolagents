# État d'Avancement du Sprint

## Objectif Actuel
- [ ] Valider le coding workflow de bout en bout sur un prompt "landing page premium"
      (Architect → Coder → Tester → Judge → verdict). Run #11 en cours sur localhost.

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
- [ ] Étape 13 : Run validation reprise (interrompre un run CPU-only, relancer → reprise).
- [ ] Étape 14 : Cycle suivant (CodeAgent, repo-map, ou Nœud d'Escalade).

## Jalons bootstrap (faits)
- [x] Création agent.md (specs gestion d'état).
- [x] Initialisation feature_list.json, contract.md, progress.md, log.md.

