# Contrat de Validation

## Critères d'Acceptation Automatisés
- [ ] Critère 1 : Le fichier `feature_list.json` existe et respecte le schéma JSON attendu.
- [ ] Critère 2 : Le fichier `contract.md` est présent à la racine.
- [ ] Critère 3 : Le fichier `progress.md` liste les jalons du sprint courant.
- [ ] Critère 4 : Le fichier `log.md` respecte le format d'ajout continu avec horodatage.
- [ ] Critère 5 : Les tests pytest s'exécutent sans erreur.

## Critères de Validation du Coding Workflow (objectif sprint)
- [ ] Critère 6 : Le Router classifie correctement la techno (HTML/JS pour une landing page).
- [ ] Critère 7 : L'Architect produit un plan avec 1 sous-tâche par fichier cible (2-4 max).
- [ ] Critère 8 : Le Coder crée des fichiers NON vides via write_file (garde anti-vide active).
- [ ] Critère 9 : Les 3 fichiers cibles sont créés : landing_page/{index.html, styles.css, script.js}.
- [ ] Critère 10 : Le HTML généré est valide (présence de `<!DOCTYPE html>`, `<html>`, `</html>`).
- [ ] Critère 11 : Le Coder termine par final_answer (pas de boucle de re-écriture infinie).
- [ ] Critère 12 : Le Judge émet un verdict (is_approved booléen) à la fin.
- [ ] Critère 13 : Le Knowledge Graph trace les observations/refutations du run.

## Critères de l'édition sécurisée SEARCH/REPLACE (cycle en cours)
- [ ] Critère 14 : Le Coder peut éditer un fichier existant via search_replace sans corruption (matching tolérant).
- [ ] Critère 15 : search_replace rejette les placeholders (TODO, '...') dans le bloc replace.
- [ ] Critère 16 : search_replace renvoie un feedback didactique (lignes proches) quand le bloc search n'est pas trouvé.
- [ ] Critère 17 : Le Mutex par fichier sérialise les écritures concurrentes (tests test_search_replace.py PASS).
- [ ] Critère 18 : La suite pytest complète passe (0 régression, 11 nouveaux tests inclus).

## Critères de la Persistance d'État (Checkpoints — Priorité 3)
- [ ] Critère 19 : Le `run_id` est stable (dérivé du hash du contenu de tâche) — relancer la même tâche reprend là où c'était arrêté ; deux contenus différents donnent deux run_id différents.
- [ ] Critère 20 : La reprise court-circuite l'Architect (plan rechargé depuis le checkpoint via `ArchitectOutput(**dict)`) et saute les sous-tâches déjà approuvées (résultat `replayed=True`).
- [ ] Critère 21 : La granularité "début d'itération" persiste un état cohérent avant chaque Coder (le checkpoint reflète `(current_subtask_idx, current_iteration)` + `architect_result` + `completed_subtasks`) ; à la reprise on rejoue l'itération complète (idempotent, jamais un état intermédiaire).
- [ ] Critère 22 : `FRESH_START=1` efface le checkpoint existant ; un run allant au bout efface son propre checkpoint (run "terminé"). `save_checkpoint`/`load_checkpoint`/`clear_checkpoint` validés sur DuckDB (upsert, round-trip, absence → None).
- [ ] Critère 23 : La suite pytest ciblée passe (0 régression, 12 nouveaux tests test_checkpoint.py inclus).

## Critères du Tester polyvalent multi-techno + Boucle d'auto-correction (Priorité 2)
- [ ] Critère 24 : `detect_tech` combine Router + extensions de `target_files` ; les extensions l'emportent en cas de conflit (déterministe > LLM) ; fallback `web` si rien de détectable.
- [ ] Critère 25 : `execute_tester_node` dispatche vers le bon runner selon la techno (`get_runner`) ; `task["tech"]` explicite prime sur la détection.
- [ ] Critère 26 : `PythonTestRunner` (subprocess) : exit 0 → `status="success"` ; exit≠0 → `"failure"` + stderr/stdout capturé et tronqué. Le subprocess utilise `sys.executable` (interpréteur du projet, qui a pytest).
- [ ] Critère 27 : Le `WebTestRunner` refactorisé conserve le comportement du bloc Puppeteer d'origine (MCP Chrome DevTools, calcul d'URL, skill web-tester) ; chargé via le loader centralisé.
- [ ] Critère 28 : `truncate_output` préserve head + tail + insère un marqueur transparent (`… [X lignes tronquées] …`) ; texte court retourné intact ; `None`/vide → `""`.
- [ ] Critère 29 : `truncate_history` plafonne l'historique cumulé des réfutations injecté au Coder (≤ `feedback_max_chars`), bugs récents prioritaires ; garde au moins le 1er item (tronqué) pour ne pas laisser le Coder sans info.
- [ ] Critère 30 : La troncature opère **à la lecture** (injection au Coder/Judge) — le contenu écrit en DuckDB reste intégral (pas de collision de `dedup_key`).
- [ ] Critère 31 : Le skill `web-tester` exige désormais un rapport structuré (section « ERREURS CONSOLE JS » = le « stderr » du web) ; le skill `python-tester` documente le verdict pytest (exit code) et la lecture d'un échec.
- [ ] Critère 32 : La suite pytest complète passe (0 régression, nouveaux tests inclus : feedback_utils, tech_detection, python_runner, tester_dispatch, feedback_integration).

## Protocole d'Évaluation
* Tests unitaires : `uv run pytest tests/ -v` → zéro échec.
* Validation process : `uv run python -m graph_orchestrator.workflows` (WORKFLOW_MODE=coding) →
  vérifier que le workflow aboutit (Architect→Coder→Tester→Judge) et produit les 3 fichiers.
* Vérification livrable : `ls landing_page/` (3 fichiers) + inspection HTML (non corrompu).

