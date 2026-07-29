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

## Protocole d'Évaluation
* Tests unitaires : `uv run pytest tests/ -v` → zéro échec.
* Validation process : `uv run python -m graph_orchestrator.workflows` (WORKFLOW_MODE=coding) →
  vérifier que le workflow aboutit (Architect→Coder→Tester→Judge) et produit les 3 fichiers.
* Vérification livrable : `ls landing_page/` (3 fichiers) + inspection HTML (non corrompu).

