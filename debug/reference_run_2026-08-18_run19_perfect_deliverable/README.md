# Run de référence #19 — Le livrable PARFAIT (2026-08-18, 22:09)

> **Pourquoi ce dossier existe** : `runs/` est vidé cycliquement par la rétention
> (OUTPUT_RETENTION). Ce run est le **premier livrable 100 % conforme validé
> jusqu'à l'œil humain** — approuvé par le Judge en **itération 1**, puis
> vérifié critère par critère dans le navigateur (chrome-devtools) par
> l'utilisateur et l'assistant. Il est préservé ici comme **étalon de la
> qualité 2026-08-18**, aux côtés du Golden Run historique
> (`debug/reference_run_qwen4b_bubble_sort/`) et de la première approbation
> E2E (`debug/reference_run_2026-08-17_first_e2e_approval/`).

## La mesure du « parfait » (validation chrome-devtools, poste à poste)

| Critère | Mesure |
|---|---|
| **Chargement** | **29/30 barres visibles dès l'ouverture** (hauteurs inline 4→250px proportionnelles — pas de conteneur vide) |
| **Compteur** | **0 → 44 → 168 → 249** : incrémenté en direct pendant le tri |
| **Tri** | **30/30 barres triées, ordre croissant vérifié** (mesure des hauteurs) |
| **États** | 2 barres `comparing` actives en cours de tri, `sorted` en fin |
| **Rendu** | barres verticales (23px / 836px conteneur), thème sombre `rgb(11,16,32)` |

Et surtout : **une seule itération** — le Coder 4B a produit juste du premier
coup (`run_git_history.txt` : un unique commit « Iteration 1 »).

## Contexte : le 7ᵉ run d'une journée de durcissement

Ce run n'est pas un coup de chance isolé — il est la **synthèse de 6 runs
précédents**, chacun ayant ajouté un garde déterministe ou corrigé une
consigne en amont (boucle méta-analyste AGENTS.md §8, à chaud) :

| Run | Défaut constaté | Garde/fix ajouté |
|---|---|---|
| #13 | Faux positif Static Tester (gradient = « invisible ») | Sonde `backgroundImage === 'none'` (f801716) |
| #14 | Barres plates (`flex-direction:column` du DRAFT) | 3 étages : draft_gate `flex_column_bars` + règle flex ROW prompt Architect + sonde « quasi IDENTIQUES » (b01fee4) |
| #15 | Conteneur vide au chargement (`height:0` à la création) | Snapshot PRE-clic `[CHARGEMENT]` (1975736) |
| #16 | Thrash 772k tokens (mur F-116) | Documenté — échec PROPRE, aucun faux succès |
| #17 | Compteur figé, littéraux `'0'` purs | Check (a-bis) compteur statique (c5c2370) |
| #18 | Compteur figé, littéral `'Comparaisons: 0'` | (a-bis) v2 identifiants hors littéraux + (a) concaténations (2549d0f) |
| **#19** | — | **Tous actifs simultanément → parfait sans en avoir eu besoin** |

Le draft de l'Architect (lignes 25-27) prescrit **exactement** la règle flex
ROW + `align-items:flex-end` du Fix B — le plan était sain dès l'origine, le
4B suit le plan, le livrable est juste. Plus 8 leçons durables cross-run
(F-68) injectées au Coder au démarrage.

## Où tout se trouve

| Fichier | Contenu |
|---|---|
| `index.html` / `styles.css` / `script.js` | **Le livrable parfait** (3 fichiers vanilla, thème sombre, gradients, transitions) |
| `plan.md` / `task.md` | **Première préservation des artefacts F-120** : miroir fidèle de l'ArchitectOutput + checklist vivante (2 transitions : démarrage → APPROUVÉ) |
| `draft_bsv_001.md` | Le draft de l'Architecte (Ornith-9B) — géométrie flex-end prescrite, preuve du Fix B |
| `run_git_history.txt` | Historique git du run (F-53/F-102) : UN SEUL commit `Iteration 1` |
| `run_full.log` | Journal complet (~6 000 lignes) : 21 steps Coder, checklist visuelle, verdicts, approbation it1 |
| `llama-server/` | Les 8 logs llama-server (21:55→22:08) |

## Contexte de reproduction

- Commande : `FRESH_START=1 uv run agent_graph.py`
- Tâche : `bubble-sort-multifile-v6` (`tasks.json`, coding)
- Modèles : Qwen3.5-4B (Coder), Ornith-1.0-9B (Architect/Security/Judge)
- Branche : `feat/f-120-plan-task-md` (PR #97, commit 2549d0f — tous les
  gardes de la journée actifs)
- Durée : boucle Coder 21:55:35 → 22:09:27 (**~14 min**), 21 steps,
  approbation itération 1
- Écart mineur noté par le Judge : cahier des charges demande
  `requestAnimationFrame`, le code utilise `setTimeout` (fonctionnellement
  équivalent ici, animation fluide validée visuellement)

## Pour rejouer le livrable

```bash
uv run python -m http.server 8798 --bind 127.0.0.1 --directory debug/reference_run_2026-08-18_run19_perfect_deliverable
# → http://127.0.0.1:8798/index.html — clique Start Sort, puis Reset pour regénérer
```
