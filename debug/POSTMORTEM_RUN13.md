# Post-mortem Run #13 — Validation E2E F-120 (plan.md + task.md)

> **ÉPILOGUE (mêne journée) — dénouement complet en 3 runs** :
> - **#13** (11:30) : échec 0/2 — faux positif gradient (fix P0, commit f801716)
>   + thrash TS-01 (cap steps 40→30) ; F-120 validé.
> - **#14** (16:20, fixes actifs) : **2/2 APPROUVÉES, code OK** (TS-01 it2 :
>   correction chirurgicale du compteur F-110 ; TS-02 it1 ; 35 min, 1,07 M
>   tokens ; 0 faux positif gradient). MAIS validation visuelle humaine :
>   50 bandes plates de 4px pleine largeur — le DRAFT de l'Architect
>   prescrivait `#viz{flex-direction:column}+.bar{flex:1}` (flex-basis écrase
>   style.height, bug exact documenté F-124) et le 4B suit le draft contre le
>   skill ; auto-approuvé par le rituel visuel. Fixes 3 étages (commit b01fee4) :
>   draft_gate `flex_column_bars` (REJECT), règle géométrie prompt Architect,
>   sonde Tier 2 « barres plates » (preuve live flat_DETECTE=true sur le
>   livrable #14).
> - **#15** (17:17) : **SUCCÈS COMPLET — code OK + graphique OK** : 1/1
>   approuvé en PREMIÈRE itération (24 min, 429k tokens, record). Draft sain
>   (#chart flex-end ROW — Fix B suivi). Validation visuelle chrome-devtools :
>   30 barres verticales proportionnelles (hauteurs inline 5,6→182px
>   variées), gradient turquoise→violet (backgroundImage — accepté à juste
>   titre par la sonde corrigée P0), 30/30 triées, compteur 225, thème sombre.

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
- **« 10 serveurs spawnés / 0 arrêt » — piste LEAK RÉFUTÉE après coup** (lecture
  `llama_server.py` + `tasklist` post-run : 0 processus résiduel) : le design de
  `model_lifecycle` est spawn/stop PAR NŒUD (context manager), 10 nœuds = 10
  cycles spawn/stop normaux ; les stops allaient au `logger.info` — invisible en
  console — d'où l'illusion d'empilement dans le log. Fix d'observabilité ajouté :
  le stop imprime désormais `[~] llama-server : arrêté (port X)` symétrique du
  « prêt ». Explication restante des timeouts : conjonction (a) préfill ÉNORME
  (le contexte Coder atteignait ~990k input tokens/step — 3 retries de prefill
  de cette taille sur RTX 3060) et (b) chevauchement structurel 4B (serveur du
  Coder, vivant tout le run) + 9B (nœuds DSPy) au-delà des 6 Go de VRAM →
  débordement mmap/RAM. Le run #12 tenait sur la même topologie : la différence
  du jour est le volume du contexte (990k vs ~90k), lui-même conséquence du
  thrash 2.a et du faux positif 2.b qui a multiplié les itérations.
- **Cap steps élargi localement** : `.env` avait `CODER_MAX_STEPS=40` (écart non
  tracké vs défaut documenté 30, doctrine F-61 : « le défaut 25 laissait boucler
  jusqu'à 87 steps » ; production typique 6-14 steps). Réaligné sur 30 — TS-01
  aurait été coupé ~25 % plus tôt.

## 3. Métriques (`run_analyzer.py` + tableau d'observabilité)

- Durée nœuds : 4 176 s (~70 min) ; wall ~80 min. Coder TS-01 : 2 053 s.
- Tokens : 74,7 M input / 615 k output (cumul steps) ; 516 k trackés (table run).
- 0 verdict Judge ; 54 entités / 105 claims KG ; checkpoint effacé en fin (propre).

## 4. Propositions — état après session debug 2026-08-18 (feu vert user : « corrige tout, run final sans erreur »)

1. **P0 — Fix Static Tester Tier 2 : ✅ FAIT** — la sonde exige désormais
   `backgroundImage === 'none'` pour flagguer « sans fond » ; +3 tests
   (`test_gradient_bars_visible_run13` live, `test_truly_transparent_bars_still_flagged`
   live anti-faux-négatif, `test_sonde_tier2_couvre_background_image` garde source).
   **Preuve live sur le VRAI livrable du run #13** (chrome-devtools, sonde exacte
   reproduite) : `hidden_AVANT_fix=true, hidden_APRES_fix=false` — barres 293 px,
   gradient orange dans `backgroundImage`, `backgroundColor` transparent.
2. **P1 — Observabilité lifecycle : ✅ FAIT** (le « leak » était une illusion de
   log, cf. 2.c ; le stop s'imprime maintenant en console). Aucun bug à corriger.
3. **Cap steps local : ✅ FAIT** — `CODER_MAX_STEPS` 40 → 30 (défaut documenté).
4. **P2 — Re-run E2E Bubble Sort : EN COURS** après validation suite complète —
   critère de succès exigé par l'utilisateur : run sans erreur, code OK ET
   graphique OK.
5. **P3 — Micro-améliorations F-120 restantes (cycle futur)** : statut `failed`
   pour sous-tâche en échec (TS-01 affichée `pending` en fin de run, ambigu).
   Goal par section `## Objective` : ✅ déjà corrigé (28/28 tests).

## 5. Artefacts

- Log : `logs/e2e_f120_run.log` ; analyse : `analysis_report.md` (régénéré).
- Livrables partiels : `runs/2026-08-18_1130_bubble_sort_multifile_v6/`
  (index.html 879 o, styles.css 3 197 o, script.js 4 108 o — complets mais non
  approuvés ; bug `.comparing` = faux positif, code sain).
- journal F-120 : `task.md` du run (6 transitions datées).
