# Post-mortem run #9 — E2E validation FRESH_START (2026-08-17_1439)

> Run de validation post-merge PR #87 (F-112) + PR #88 (F-113), tâche
> `bubble-sort-multifile-v6`, ~1 h 28 (14:40 → 16:07), exit 0.
> Résultat final du graphe : `{"status": "failure", "reason": "Coder crash"}`.
> Log : `logs/e2e_f113_run.log` — rapport : `analysis_report.md` (2026-08-17 16:07).

## TL;DR

Le Coder (Qwen3.5-4B) a échoué **3/3 tentatives** de l'itération 1 sans jamais
produire de `final_answer` valide : **0 appel à `visual_check` en 3 tentatives**
alors qu'il a pris **48 screenshots**. La chaîne n'a jamais atteint
Linter/Static Tester/Web Tester/Judge → **F-112 et F-113 restent non validés
E2E** (bloqués en amont, sans régression de leur côté). Le code généré était
pourtant syntaxiquement sain (0 erreur de logique/syntaxe au rapport) et le
diagnostic visuel du modèle fonctionnait (il a trouvé et corrigé seul le bug
canvas-vide, pattern F-110).

## Métriques

| Métrique | Valeur |
|---|---|
| Durée steps Coder | 2 980 s (~50 min d'inférence) |
| Steps Coder (3 tentatives) | 103 (41 max_steps × 2 + timeout à 35) |
| Tokens input | **43,9 M** (vs 19,4 M run #8 complet) |
| Tokens output | 354 k |
| Verdicts Judge | 0 (chaîne jamais atteinte) |
| Screenshots pris | 48 (dont fullPage jusqu'à 1265×9311 px) |
| Appels `visual_check` | **0** |

## Déroulé

- Boot sain : FRESH_START respecté, PromptRefiner (spec 2502 c., 3 ambiguïtés),
  Router = HTML (pas de dérive), Architect 3 fichiers + `requestAnimationFrame`,
  8 leçons cross-run injectées, spawns llama-server cuda tous prêts.
- **Tentative 1 (41 steps)** : vrai travail de debug visuel (canvas vide →
  canvas→div corrigé à l'étape 25 après screenshot de page vide) mais conclusion
  en prose sans jamais appeler `visual_check` → max steps → Pydantic KO →
  sauvetage → cascade de gardes : Anti-Loop F-36 ✓, Stall Detector F-88 ✓,
  gate checklist F-109 (« 6/6 critères non audités ») ✓, rappel F-109-bis
  injecté au retry ✓. **Aucun `Connection error` au sauvetage** (symptôme F-113
  du run #8 absent).
- **Tentative 2 (35 steps)** : tuée par `Request timed out` (600 s = LLM_TIMEOUT_S)
  à l'étape 35 — contexte énormez (screenshots fullPage 1265×7 715 à 9 315 px
  traités par un 4B multimodal → prompt processing de plusieurs minutes).
- **Tentative 3 (41 steps)** : même schéma que la 1 — debug réel, screenshots à
  répétition, 0 `visual_check`, max steps → échec définitif déclaré proprement,
  checkpoint effacé, exit 0.

## Causes racines

1. **Comportement (bloqueur)** : le 4B n'exécute pas le rituel
   screenshot → 6 × `visual_check` → `final_answer`. Il analyse en prose
   (« tous les critères sont validés ») puis tente de conclure. La gate F-109
   refuse correctement, le rappel F-109-bis est bien injecté, mais le modèle
   reproduit le même pattern à la tentative suivante. C'est le failure mode
   originel de F-109 (« déclare sans matérialiser ») : la gate le bloque
   désormais (voulu), mais le modèle ne peut pas satisfaire l'exigence —
   boucle déterministe 3 × 41 steps, ~44 M tokens brûlés pour 0 livrable.
2. **Coût/timeout (amplificateur)** : le Coder appelle
   `take_screenshot(fullPage=True)` → images jusqu'à 9 315 px de haut dans le
   contexte vision → steps de 150 s et un timeout 600 s (tentative 2 tuée).
   Le cap viewport 1280×800 posé au spawn DevTools (F-50) ne s'applique pas au
   rendu fullPage.

## Ce qui a été validé au passage (chemin négatif, en prod)

- F-109 + F-109-bis : refus de `final_answer` sans preuve + rappel au boundary.
- F-36 anti-loop, F-88 stall detector, F-99 (idle re-injection) : tirés en
  cascade, dans l'ordre prévu.
- F-95 (`.fs_tx/`, git run dir, allowlist), F-101 (`.transcripts/`) : artefacts
  présents et actifs pendant tout le run.
- Échec définitif géré proprement (escalade côté workflow, checkpoint effacé,
  exit 0) — pas de crash de l'usine.

## Non validés par ce run

- **F-113** (cible n°1) : le Web Tester n'a jamais tourné → le parsage du
  verdict post-fix `api_base` reste à prouver. Signal partiel : le sauvetage
  Pydantic du Coder n'a produit aucun `Connection error`.
- **F-112** (cible n°2) : le Static Tester n'a jamais tourné → la sonde
  d'animation multi-signal reste à prouver en chaîne.

## Propositions (en attente feu vert utilisateur — AGENTS.md §8)

1. **Cap fullPage dans le wrapper screenshot** (`vision_callback.py`) :
   forcer `fullPage=False` (ou re-tagger l'image) pour éliminer les images
   de plusieurs milliers de pixels de haut → tue l'amplificateur timeout.
   Fix déterministe de l'usine, 0 LLM.
2. **Nudge contextuel au wrapper** (pattern repeat-tool-reminder, fiche 46,
   déjà répertorié plan P3 « anti-loop couche douce ») : au N-ième screenshot
   sans aucun `visual_check`, la sortie de l'outil exigera l'appel
   (« screenshot #N pris, 0 critère audité — appelle visual_check MAINTENANT
   pour chaque critère »). Nudge AVANT veto, au plus près du comportement.
3. **Dégradation configurable de la checklist Coder** : si le nudging ne
   suffit pas, permettre `VISUAL_AUDIT_MODE=tester` — la preuve visuelle du
   Coder devient best-effort (le rappel reste), et c'est le Web Tester
   (assertions F-20 + gate F-108 fail-closed) qui porte l'exigence de preuve.
   Rationale : depuis F-108/F-110, le Judge est fail-closed sur les tests et
   le Static Tester a 4 tiers déterministes — la double exigence de preuve
   (Coder ET Tester) est peut-être au-dessus des moyens du 4B.

Ordre proposé : 1 + 2 (cycle court, déterministe), puis re-run E2E ; 3 seulement
si la non-convergence persiste.
