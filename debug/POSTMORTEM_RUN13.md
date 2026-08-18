# Post-mortem Run #13 — Validation E2E F-120 (plan.md + task.md)

**Run** : `coding_d72dc8e36445c6` (run_id identique aux runs #10-#12, même hash de tâche)
`bubble_sort_multifile_v6` — `runs/2026-08-18_1130_bubble_sort_multifile_v6/`
**Date** : 2026-08-18 11:30 → ~12:58 (TS-01) puis 13:03 → 13:50 (TS-02). Wall ~80 min.
**Config** : FRESH_START=1, PLAN_TASK_MATERIALIZE=true, branche `feat/f-120-plan-task-md` (PR #97),
STATIC_TESTER_ENABLED=1, MTP 9B actif (flags F-123), spawn backends.
**Verdict final** : `{failure Coder crash, failure Coder crash}` — 0/2 sous-tâche approuvée,
exit 0 propre. **Judge jamais atteint** (0 verdict).

## 1. F-120 : VALIDÉ en conditions réelles (l'objet du run)

| Attendu | Observé |
|---|---|
| plan.md après l'Architect | ✅ miroir fidèle COMPLET : Plan ID, architecture globale, 2 sous-tâches (stratégie multifile/simple, checklists fichiers, 5+3 critères visuels, 4+2 critères fonctionnels, rubric CRITICAL→LOW, skills) — **rien de perdu** |
| Statuts vivants | ✅ TS-01 in_progress pendant son exécution, puis TS-02 in_progress |
| task.md checklist + journal | ✅ journal EXACT des 6 transitions : démarrage 11:35:04 → coder KO 12:58:50 → démarrage 12:58:50 → rejet static 13:03:01 → rejet static 13:09:07 → coder KO 13:50:08 (détails tronqués à 160 c.) |
| Anchor stable au Coder | ✅ 8 occurrences « PLAN GLOBAL (ancrage stable — F-120) » = 3 prompts TS-01 (retries) + 5 prompts TS-02 (3 itérations dont it3 en 3 retries). Court, identique, SANS critères visuels (pas de doublon F-82) |
| Impact charge | négligeable (~700 caractères/prompt, 2 écritures disque par transition) — **F-120 n'est PAS une cause de l'échec ci-dessous** |

La valeur post-mortem est démontrée par l'expérience même : c'est `task.md` qui a permis de
reconstituer la chronologie complète du run en une lecture.

## 2. Échec du run — 2 causes racines indépendantes (aucune liée à F-120)

### 2.a TS-01 : thrash du rituel visuel non convergé (pattern run #9)

- Coder 4B : **41 steps → "Reached max steps"**, contexte cumulé énorme
  (**963k–990k input tokens par step** en fin ; 74,7 M cumulés sur le run entier
  d'après `run_analyzer.py`).
- Rituel screenshot → `visual_check` jamais complété : au moment du final_answer,
  **5/5 critères non audités** → garde F-109 « ERREUR FATALE : pas de take_screenshot »
  → refus du final_answer ×3 tentatives (Anti-Loop F-36 + Stall Detector F-88 tirés
  à chaque fois) → **circuit-breaker idle, échec définitif propre** (le comportement
  attendu des gardes — pas de crash sale).
- Seul `index.html` (879 o) a été écrit par TS-01 (11:59).
- Régression comportementale vs runs #10-#12 (convergence 12 steps, rituel 60
  visual_check au run #10). Causes candidates non tranchées : variance du 4B,
  saturation GPU (voir 2.c), max_steps élevé (41) laissant le contexte exploser.
- Signaux secondaires du run : 4 sauvetages Pydantic, 3× `Forbidden function
  evaluation: 'open'` (le 4B tente de LIRE les fichiers avec `open()` Python inline
  au lieu de `read_file` — lignes log 14325-14329), 1× `Access denied` (piège
  filePath F-50/F-90 : contenu par le strip, pas de boucle).

### 2.b TS-02 : FAUX POSITIF Static Tester — interaction F-124 (gradients) × F-49 (Tier 2)

- Itérations 1 et 2 : livrable **visuellement correct** (`styles.css` : `.bar.comparing
  { background: linear-gradient(180deg, #ff6f00, #f57c00); animation: glow…;
  transform: scaleY(1.06) }`, barres de 84 px de haut) **rejeté 2×** par le Tier 2 :
  « 2 élément(s) ".comparing" créé(s) par le JS mais INVISIBLE(s) (height=83.98…) ».
- **Cause racine prouvée par lecture du code** (`static_tester.py`, sonde Tier 2) : un
  div est flaggué invisible si `innerText == '' && backgroundColor ==
  'rgba(0, 0, 0, 0)' && tag ∉ {img, svg, canvas}`. Or un `background:
  linear-gradient(…)` vit dans **`background-image`** — `backgroundColor` reste
  transparent. Toute barre stylée par gradient + sans texte est donc déclarée
  invisible alors qu'elle est parfaitement visible.
- **Premier run E2E post-F-124** (« niveau graphique maximal », mergé PR #96 avec
  validation E2E reportée) : F-124 pousse des linear-gradient sur `.bar`, `.sorted`,
  `.comparing` — le faux positif était structurellement attendu et le run de
  validation reporté l'aurait attrapé plus tôt.
- Itération 3 : correction du 4B (styles.css/script.js réécrits 13:21) puis
  **3× `Request timed out` à 600 s** → échec définitif (voir 2.c). Le 4B n'a de toute
  façon jamais eu de vraie chance : la réfutation qu'il recevait décrivait un bug
  inexistant.

### 2.c Timeouts finaux : serveur 4B wedged sous pression

- TS-02 it3 : 3× timeout exactement à 600.01 s (LLM_TIMEOUT_S). Le serveur 4B ne
  répondait plus.
- **10 serveurs llama-server spawnés sur le run, 0 arrêt loggé** (grep « prêt » vs
  « arrêt » : 10/0) — un leak de processus (VRAM 6 Go) est le suspect principal de
  la dégradation finale. Hier run #12 : « ZÉRO respawn F-104, zéro crash VRAM » —
  à investiguer (lifecycle : les serveurs des nœuds précédents ne seraient pas
  tous libérés ?).

## 3. Métriques (`run_analyzer.py` + tableau d'observabilité)

- Durée nœuds : 4 176 s (~70 min) ; wall ~80 min. Coder TS-01 : 2 053 s.
- Tokens : 74,7 M input / 615 k output (cumul steps) ; 516 k trackés (table run).
- 0 verdict Judge ; 54 entités / 105 claims KG ; checkpoint effacé en fin (propre).

## 4. Propositions (dans l'ordre — feu vert utilisateur requis, AGENTS.md §8)

1. **P0 — Fix Static Tester Tier 2** (déblocage majeur, déterministe, 0 LLM) : la
   sonde doit considérer un `background-image ≠ 'none'` comme VISIBLE. Changement :
   ajouter `&& cs.backgroundImage === 'none'` à la condition « background
   transparent sans texte » + tests de régression (cas gradient sans texte →
   visible ; cas transparent réel → toujours invisible). TS-02 it1/it2 avaient un
   livrable sain : ce faux positif a coûté 2 itérations complètes + la pression
   qui a mené aux timeouts.
2. **P1 — Enquête lifecycle llama-server** : compter/process-check les serveurs
   vivants mid-run (10 spawns / 0 stop loggé) ; tuer explicitement les serveurs
   des nœuds terminés ou réutiliser les ports (le run #12 n'avait pas ce profil).
3. **P2 — Re-run E2E Bubble Sort** après P0 (et idéalement P1) pour valider F-124
   E2E + F-120 en conditions nominales. F-120 lui-même n'a rien à corriger pour
   re-runner.
4. **Micro-améliorations F-120 constatées** (non bloquantes) : statut `failed`
   pour une sous-tâche terminée en échec (TS-01 affichée `pending` en fin de run,
   ambigu) ; Goal par section `## Objective` (corrigé sur la branche, tests 28/28).

## 5. Artefacts

- Log : `logs/e2e_f120_run.log` ; analyse : `analysis_report.md` (régénéré).
- Livrables partiels : `runs/2026-08-18_1130_bubble_sort_multifile_v6/`
  (index.html 879 o, styles.css 3 197 o, script.js 4 108 o — complets mais non
  approuvés ; bug `.comparing` = faux positif, code sain).
- journal F-120 : `task.md` du run (6 transitions datées).
