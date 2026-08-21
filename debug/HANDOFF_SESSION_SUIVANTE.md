# HANDOFF — Prochaine session : Web Tester & retour au timing du golden

> Session 2026-08-21 (F-116 + chasse au goulot) : **7 runs E2E, 7 causes racines corrigées**.
> Ce document est le point de départ de la session suivante — tout y est mesuré, pas deviné.
> Branche : `feat/f-116-compaction-resiliente` (PR #102, 12 commits, review Kilo adressée).
> Événements DuckDB : #1999 → #2016. Contrat : C473-C483 + C484-C486.

---

## 0. État actuel en une phrase

L'usine fonctionne de bout en bout **jusqu'au Judge** (Coder convergent ~10 min, vrai bug
détecté et corrigé par itération, Static OK + HTTP 200, prefill réparé), mais le **Web
Tester dépasse son timeout horloge** (`TESTER_TIMEOUT_S=1200`) sur son rituel visuel →
Judge SKIPPÉ en fail-closed → REJET ×3 → circuit breaker → run en échec propre à ~45-95 min
au lieu des ≤30 min visés.

---

## 1. PROBLÈME N°1 — Le rituel visuel du Web Tester (bloqueur du verdict)

### Les mesures (run #7, `logs/e2e_f116_run7.log`)

- Le Tester tourne à **5-20 s/step côté LLM** (fix MTP efficace — cf. §3) MAIS :
- **Step 1 = 351,5 s** : un seul méga-bloc Python enchaîne ~8 outils DevTools EN SÉRIE
  (`navigate_page` → `list_console_messages` → `take_screenshot` → `click` → `evaluate_script`
  → `fill`…) — chaque aller-retour Chrome/MCP = 20-60 s.
- Steps d'assertions : 72-211 s (evaluate_script + captures).
- **Verdict prêt à ~1 525 s** (mesuré) → tué par le timeout 1 200 s → « Test timeout →
  Judge SKIPPÉ (fail-closed), approbation bloquée ».
- Anomalie connexe : en fin de passe (post step 16/16), le process est resté **figé ~5 min**
  (clôture DevTools/MCP pendante ?) — à investiguer.

### Fixes par ordre de coût

1. **`TESTER_TIMEOUT_S=1200` → `1800`** (une ligne `.env`) : le tester FINIT (1 525 s
   mesurés) et le Judge peut enfin approuver. Effet immédiat, zéro risque.
2. **Alléger le rituel** (pour viser ≤30 min/run) :
   - regrouper les assertions en **un seul `evaluate_script`** par page au lieu de
     navigate→check→screenshot→check par critère (le plus gros levier : le nombre
     d'aller-retours, pas le LLM) ;
   - échantillonner les 7 critères visuels (le golden #11 en avait **5**) — côté prompt
     Architect (génération des critères) ou prompt Tester ;
   - vérifier pourquoi le **re-test ciblé** (F-52, 16 steps) prend quand même >20 min
     (il devrait faire ~3 navigate + assertions).
3. **Clôture DevTools** : la passe figée post-step-16 → chronométrer le teardown MCP dans
   `testers/web_tester.py` (ExitStack) et borner.

---

## 2. LE GOLDEN RUN — l'étalon (timing ET code)

### Les chiffres à retrouver

| | Golden #11 (même tâche) | Parfait #19 | Runs actuels (6-7) |
|---|---|---|---|
| Durée totale | **26,6 min** | ~14 min | 45-96 min |
| Steps Coder | 61 (2 it.) | 21 (1 it.) | ~25/itération |
| Tester | **29 steps à 25 s/step = 12 min** | (approuvé it. 1) | 16-17 steps à ~90 s avg |
| Prefill 9B (prod) | **550-700 t/s** | idem | 1 342 t/s (réparé §3) |
| Critères visuels | **5** | 5 | **7** (l'Architect en génère plus) |
| Verdict | APPROUVÉ it. 2 | APPROUVÉ it. 1 | REJET (timeout tester) |

### Le CODE du golden — où le lire

- **Commit du golden #11** (2026-08-17, première approbation E2E sur
  `bubble-sort-multifile-v6`) : **`018a5b6`** — `git show 018a5b6:graph_orchestrator/testers/web_tester.py`
  (et `nodes.py`, `config.py`, `.env.example`).
- **Commit du parfait #19** (2026-08-18 soir) : **`2549d0f`** —
  `git show 2549d0f:graph_orchestrator/testers/web_tester.py`.
- Dossiers de référence : `debug/reference_run_2026-08-17_first_e2e_approval/`
  (log complet 6 743 lignes + livrable + logs llama-server) et
  `debug/reference_run_2026-08-18_run19_perfect_deliverable/`.
- **Ce qui a changé depuis `2549d0f`** : `git diff --stat 2549d0f HEAD -- graph_orchestrator/`
  = **+1 601 lignes sur les 5 surfaces du Coder** (vision_callback +817, tools +416,
  nodes +294, prompts +117, config +79). Chaque couche individually justifiée par un
  post-mortem Tetris/one-file ; ensemble elles ont produit les faux positifs et le
  rituel alourdi corrigés cette session.

### Les différences de CONFIG de l'époque dorée (déjà identifiées)

- llama.cpp : build **pré-b10472** (l'ancien serveur « auto-fittait » ngl ; le nouveau
  respecte ngl=99 à la lettre → ce qui a causé le débordement MTP, §3).
- Pas de MTP (ça tombe bien : proscrit maintenant).
- `CODER_MAX_STEPS` = 30-40 (48 était trop ; 24 actuel).
- 5 critères visuels, rituel tester plus court, `TESTER_TIMEOUT_S` pas contraint
  (le tester finissait en 12 min).

### Comment comparer les timings proprement (recette utilisée cette session)

```bash
# per-step input (delta des cumuls = entrée réelle de l'appel) :
python - <<'EOF'
import re
text = open("<log>", encoding="utf-8", errors="replace").read()
toks = [int(x.replace(",", "")) for x in re.findall(r"Input tokens: ([0-9,]+)", text)]
print([toks[0]] + [toks[i]-toks[i-1] for i in range(1, len(toks)) if toks[i]-toks[i-1] > 0])
EOF
# prefill réel en production (logs llama-server) :
grep -a -oE "prompt eval time.*" logs/llama-server/<serveur>.log | sort -t/ -k2 -rn | head
```

---

## 3. Rappel des 7 causes racines CORRIGÉES cette session (ne pas les re-déboguer)

1. `CODER_MAX_STEPS` 48→24 (+ config par défaut) — le thrash coûte 2× moins.
2. Bug ponytail `var(--bg)` sans `:root` (n=2 confirmé) → toggle `PONYTAIL_ENABLED`
   (off pour l'instant — A/B reste à faire).
3. Skill **`devtools-preview` perdu** par la sélection LLM de l'Architect → garantie
   déterministe Coder + Tester (`nodes.py` / `web_tester.py`).
4. Faux positif `detect_unbounded_while_in_js` sur le bubble sort canonique → logique
   inversée + wrapper dur/heuristique séparé (`js_utils.py`, `tools.py`).
5. `validate_html_monofile` rejetait `<script src>` local (la tâche EST multifichier)
   → référence locale légale si la cible existe (`html_validator.py`).
6. **Réfutations fantômes** : FRESH_START ne purgeait pas DuckDB → `clear_refutations`
   (`knowledge_graph.py`, branché `workflows.py`).
7. **MTP + ngl=99 déborde la VRAM 6 Go** (contexte draft) → offload CPU silencieux,
   prefill ÷16 (84 → 1 342 t/s une fois `REASONING*_SPEC_MTP=false`) — doc
   `docs/LLAMA_SERVER_FLAGS.md` §2 réécrite, symptôme documenté.

## 4. Autres problèmes ouverts (priorisés après le n°1)

- **Budget 30 min** : décomposition actuelle boot 5 + Coder 10-15 + Tester 20-25 +
  Security/Judge 3-5 ≈ 40-50 min. Sans alléger le rituel (§1.2), 30 min est inatteignable.
- **Coder it.2 mort sur « Pydantic a échoué »** (run 6, sans cause identifiée) — regarder
  le sauvetage DSPy et le payload du final_answer.
- **A/B ponytail** : on/off sur la golden task (2 runs) pour conclure le volet F-116-D.
- **Chantier modèles** (arbitré : après un run réussi) : candidats 7-8B Q4 non-MTP pour
  les nœuds raisonnement (marge VRAM + KV 49k) — méthodologie bench : `debug/test_mtp_spec.py`
  + matrice prefill + run étalon. NB : les tenseurs nextn ignorés ne coûtent PAS de VRAM
  quand mtp=off — changer de GGUF pour ça ne rapporte rien.
- **Escalade ultime** : si le Judge approuve avec timeout 1800, archiver le livrable de
  référence comme golden #2 (cf. `debug/reference_run_*/README.md`).

## 5. Où tout vit

- PR **#102** (12 commits : F-116 complet + 7 fixes + docs) — à merger après un run
  réussi. Contract `contract.md` C473-C486, `progress.md` §F116-9*, README §compaction.
- Logs runs 1-7 : `logs/e2e_f116_run{,2,3,4,5,6,7}.log` ; livrables : `runs/2026-08-21_*`.
- Benchs : `logs/llama-server/prefill-*` (matrice MTP/ngl/CUDA) — recette dans §2.
- Tâche de validation : `tasks.json` = `bubble-sort-multifile-v6` (contenu historique
  exact du golden #11). Commande run :
  `PONYTAIL_ENABLED=false FRESH_START=1 PYTHONUNBUFFERED=1 uv run agent_graph.py > logs/runX.log 2>&1`

## 6. Plan recommandé pour la prochaine session (dans l'ordre)

1. `TESTER_TIMEOUT_S=1800` dans `.env` (1 ligne) → relancer le run → objectif : **premier
   verdict Judge complet de la session** (approbation ou rejet fondé, plus de skip).
2. Si approuvé : clôturer F-116 (merge PR #102, golden #2 archivé), puis A/B ponytail.
3. Si rejet fondé : itérer sur le fix du bug réel (la boucle Coder→feedback marche
   désormais — preuve run #7 it.1→it.2).
4. Ensuite seulement : allègement du rituel tester (§1.2) pour le budget 30 min, puis
   chantier modèles 7-8B.
