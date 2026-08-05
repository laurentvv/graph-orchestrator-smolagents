# Suivi des tests du graphe (workflow coding)

Ce fichier est le **tableau de bord manuel** des tests définis dans le catalogue
[`prompts/test_prompts.py`](./test_prompts.py). On y consigne, pour chaque run,
le statut final et des notes post-mortem utiles à l'amélioration continue
(F-61 / Meta-Analyste — AGENTS.md §8).

## Comment lancer un test

1. Choisir un prompt dans le catalogue (`uv run python -m prompts.test_prompts`
   pour lister).
2. Copier l'entrée correspondante dans `tasks.json` → section `coding`
   (utiliser `to_coding_task("bubble-sort-multifile")` pour obtenir le dict prêt
   à coller, sans le champ `notes`).
3. `WORKFLOW_MODE=coding` dans `.env`, puis `uv run agent_graph.py`.
4. Une fois le run terminé, **compléter une ligne** dans le tableau ci-dessous.

> Le statut se lit dans le bloc « RÉSULTAT FINAL DU GRAPHE » à la fin du log
> (`logs/run_coding_<timestamp>/run_full.log`). Un run sans ce bloc = interrompu.

## Légende

| Statut | Sens |
| :--- | :--- |
| ✅ Succès | Le graphe a produit un livrable validé (bloc final `"status": "success"`). |
| ❌ Échec | Run terminé en échec (circuit breaker, escalade, ou Judge reject final). |
| ⏹️ Interrompu | Run stoppé manuellement / crashé avant le bloc final. |
| ⏳ En attente | Test planifié mais pas encore lancé. |

## Historique des runs

| test_id | date | run (log) | statut | notes post-run |
| :--- | :--- | :--- | :--- | :--- |
| bubble-sort-monofile | 2026-08-05 | `logs/run_coding_2026-08-05_150721` | ❌ Échec | Branch Summarization x5 (actions en erreur), `InterpreterError: Forbidden function`. Plan mono-fichier OK mais cycles Coder en échec. |
| bubble-sort-monofile | 2026-08-05 | `logs/run_coding_2026-08-05_160251` | ✅ Succès | Bloc final : `bs-001` + `bs-002` tous deux `"status": "success"`. Animation pas-à-pas, counter=190, 0 console error. |
| bubble-sort-monofile | 2026-08-05 | `logs/run_coding_2026-08-05_190456` | ⏹️ Interrompu | Stoppé à Step 3 du Coder (`Out: None`), pas de bloc final. |
| bubble-sort-multifile | 2026-08-05 | `logs/run_coding_2026-08-05_192739` | ⏹️ Interrompu | Premier run multi-fichiers ; stoppé pendant l'élaboration du plan Architecte (chargement Ornith). Pas encore testé à terme. |

## Synthèse par test

- **bubble-sort-monofile** : baseline validée (1 succès clair sur 3 tentatives).
  Les échecs sont des cycles Coder (`InterpreterError`), pas des défauts du
  graphe lui-même. Bon test de régression borné.
- **bubble-sort-multifile** : **non encore validé à terme**. Premier essai
  interrompu tôt. C'est le **prochain test planifié**. Points de vigilance
  notés dans le catalogue : wiring inter-fichiers (link/script src + cohérence
  ids DOM), et gap connu du Tier 1a (`node --check` ne valide que le JS inline,
  pas `script.js` externe).
