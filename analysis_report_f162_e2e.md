# Rapport d'Analyse Post-Mortem — E2E F-162 (moteurs pydantic) vs Golden #19

**Run analysé** : `runs/2026-08-23_1959_bubble_sort_multifile_v6/` (log : `logs/e2e_f162_pydantic.log`)
**Étalon** : `debug/reference_run_2026-08-18_run19_perfect_deliverable/` (golden #19, 2026-08-18)
**Date** : 2026-08-23 — run interrompu à l'entrée de l'itération 3 sur budget user (85 min vs objectif 30 min).

> ⚠️ L'analyzer F-60 retourne des métriques nulles sur ce run : il parse le
> format smolagents (markers « Step N » + tokens par step) et le moteur
> pydantic n'émet pas ce format. Ce rapport remplace à la main — écart
> d'observabilité consigné (voir §6).

## 1. Verdict global

| Axe | Golden #19 (smolagents) | E2E F-162 (pydantic) | Écart |
|---|---|---|---|
| Issue du run | **1/1 APPROUVÉ it.1**, livrable validé à l'œil humain | **0/2 rejeté** (kill à l'entrée it.3) | — |
| Durée totale | **~851 s (~14 min)** | **~5 100 s (85 min)** | **6,0×** |
| Verdict final livrable | Parfait (étalon) | Fonctionnellement sain, design défaillant | — |
| Faux positif / fausse approbation | 0 | 0 | ✓ parité |
| Crashes framework | 0 | 0 (2× Judge fail-closed = comportement voulu) | ✓ parité |

**La boucle qualité a fonctionné** : le Tester complet it.1 a trouvé un VRAI bug
(boucle morte `for (let i = 0; i < i + 1; i++)` ligne 99, tableau non trié
observé `[36, 27, 33, 33, 34…]`), le Coder it.2 l'a corrigé chirurgicalement
(1 ligne), le Tester ciblé it.2 **a confirmé le fix** (« targeted fix works »,
isSorted=true) — puis a échoué honnêtement sur des « deeper spec violations »
non énumérées (verdict vague, voir §5).

## 2. Métriques par nœud (llama-server + log run)

| Nœud | Golden #19 | E2E F-162 | Détail écart |
|---|---|---|---|
| Coder it.1 | ~446 s / 12 req / ~425 k prefill | **474 s / 13 req / 317 k in / 3,2 k out** | ✓ COMPARABLE — le Coder pydantic tient la parité |
| Static Tester | OK | OK ×2 (tier3 + HTTP 200 ×2) | ✓ |
| Tester it.1 (complet) | **~234 s / 10 req** | **1 342 s / 26 req / 633 k in** | **5,7× temps, 2,6× requêtes** |
| Coder it.2 (correction) | (n/a — approuvé it.1) | **1 691 s / 40 req / 1 134 k in / 9,9 k out** | goulot n°1 du run |
| Tester it.2 (ciblé) | (n/a) | 1 099 s / 16 req / 393 k in | wind-down → final_result au tour 16 |
| Security / Judge | OK / APPROUVE | OK ×2 / fail-closed ×2 | ✓ (fail-closed correct) |
| Spawns llama-server | 9 | 12 | churn VRAM similaire |
| Spawns MCP navigateur | 2 (Coder+Tester) | **8** (4/itération : Coder, Static, Tester-devtools, Tester-puppeteer) + FUITE Windows des arbres (2 Chromes orphelins) | → F-163 |

## 3. Livrables : E2E (état final it.2) vs golden

| Mesure | Golden #19 | E2E F-162 | Verdict |
|---|---|---|---|
| Tailles | 22/174/118 lignes (html/css/js) | 30/202/128 | comparable |
| Barres visibles au chargement | 29/30 | **30/30** | ✓ |
| Remplissage du board | **23 px/barre ≈ 96 %** (flex implicite) | **10 px/barre = 48 %** (max-width fixe) | ✗ moitié vide |
| Police rendue | sans-serif moderne (`--font-*` **définies** dans :root, discipline F-154) | **Times New Roman** (`--font-body`/`--font-display` référencées mais JAMAIS définies) | ✗ bug CSS |
| Compteur | 0→249 vivant | 0→3→30 vivant (mesuré) | ✓ |
| Tri fonctionnel | 30/30 trié | corrigé it.2 (`i < n - 1`), confirmé par le Tester ciblé | ✓ |
| Diff it.1→it.2 | (1 commit) | **1 ligne** (`i < i + 1` → `i < n - 1`) | fix chirurgical exact |

Détail du bug typographique : le 4B a écrit `font-family: var(--font-body),
system-ui, …` — fallback placé HORS des parenthèses, syntaxe qui ne protège de
rien quand la variable est indéfinie (la forme protectrice est
`var(--font-body, system-ui)`). Le golden, post-F-154, définissait ses vars
dans `:root`. La garde `_css_undefined_vars_directive` (tools.py) ne voit pas
ce cas car elle se déclenche uniquement après une ÉDITION via les custom tools
— le Coder pydantic écrit via le `write_file` du FileSystem harness (écart déjà
documenté F-159 pour write_proof) → **F-164** (audit var() en Tier 1 du Static
Tester, agnostique moteur).

## 4. Les deux goulots de performance

**Goulot 1 — Coder it.2 : 28 min / 1,13 M tokens in pour UNE ligne corrigée.**
Timeline reconstituée (llama-server req par req + timestamps fichiers) :
min 0-1 contexte 26k → compaction immédiate, plateau ~11k (TieredCompaction a
tenu) ; min 2-6 investigation (read_file + search_replace) ; **min 7 :
RÉÉCRITURE COMPLÈTE de script.js (1 007 tokens générés)** ; min 9-13
re-lectures ; **min 14 : DEUXIÈME réécriture complète (979 générés)** ; min 16-20
diagnostics ; **min 21:26 : premier appel navigateur (Chrome spawné ici — 21 min
après le début du nœud)** ; min 21-26 rituel live (probes répétitifs 44-48
s/req) ; **min 25 : LE fix chirurgical réel (search_replace 1 ligne)** ; min 27:39
final_result. 457 750 tokens de prompt cumulés, 5 requêtes à génération nulle
(réponses vides/retries).

**Trou de garde associé (découvert à l'analyse)** : la garde F-126
`coder_writefile_max_lines=100` (write_file refuse d'écraser un existant
>100 lignes, précisément anti double-réécriture) vit dans tools.py — le Coder
pydantic écrit via le write_file du FileSystem harness qui ne la porte pas :
script.js (128 lignes) a été réécrit 2× là où smolagents aurait REFUSÉ.
Troisième garde tools.py contournée par le FileSystem (après write_proof F-159
et la directive var() CSS) → à porter (F-164 élargi).

**Goulot 2 — Tester : 1 requête = 1 tool-call vs 1 step CodeAgent = N calls.**
Golden : 10 requêtes pour tout le rituel (le bloc Python chainait les appels).
E2E : 26 requêtes pour le même rituel (2,6×), et ~52 s/requête vs ~23 s
(génération structurée complète par appel + contexte repréfillé). Total
22 min vs 4 min. Par ailleurs TESTER_MAX_STEPS est passé de 8 (époque golden)
à 16 (aujourd'hui) → budget ×4 en requêtes effectives vs golden.

## 5. Écarts de process / comportement observés

1. **Verdict ciblé vague** : le Tester it.2 rend failure (« deeper spec
   violations remain ») alors que TOUTES les assertions listées passent
   (targeted fix confirmé + smoke OK). Le mode ciblé F-47 remplace la
   checklist par les bugs ciblés ; le 9B a ajouté un jugement holistique non
   étayé. Le Judge — qui arbitrerait — est fail-closed sur test failure. Le
   Coder it.3 aurait reçu un feedback sans item actionnable → thrash garanti.
   → Piste : exige du Tester ciblé que `status=failure` soit TOUJOURS accompagné
   d'au moins un item FAIL explicite dans details (format de sortie contraint).
2. **Le design n'est arbitré par personne** : le bug Times/48 % n'est vu ni
   par le Coder (rituel visuel : il a validé ses critères F-82 sans regarder
   la police), ni par le Static Tester (pas de tier typographique), ni par le
   Judge (jamais exécuté, fail-closed), ni par le Tester (critères
   fonctionnels). → F-164.
3. **Fuite des arbres MCP Windows** (découverte user) : 4 spawns/itération,
   zéro kill à la fermeture → F-163 (pool navigateur run-scoped).
4. **Arbitrage C520 résolu** : TESTER_TIMEOUT_S=1800 suffit (les deux verdicts
   ont convergé : 1 342 s / 1 099 s < plafond). Le 2 700 utilisé pour
   l'isolation était superflu.

## 6. Écarts d'observabilité (outillage post-mortem)

| Artefact | smolagents (golden) | pydantic (E2E) |
|---|---|---|
| `.system_generated/tasks/task-*.log` (steps détaillés) | ✓ | ✗ absent |
| `.transcripts/` (archives mo_step, images F-116) | ✓ | ✗ absent |
| Analyzer F-60 (`run_analyzer.py`) | ✓ métriques complètes | ✗ **0 partout** (parse « Step N ») |
| Verdicts complets | feedback tronqué | ✓ MÊME troncature (992 chars, réfutation it.2 coupée) |
| Métriques par nœud | par step | ✓ par nœud (tokens/durée dans le log) — suffisant |
| Vue live | verbosity HIGH par step | ✓ `[T] tour N : tools` (F-162) — suffisant |

→ Candidat outillage (à ajouter à F-163/F-164 ou cycle dédié) : parser les
lignes `[+] nœud : status=… (N in / M out, X s)` dans run_analyzer.py + exiger
du Tester que details contienne ses items FAIL complets AVANT troncature.

## 7. Ce qui est VALIDÉ pour la migration (plan §3.7 → phase 4)

- Chaîne complète deux moteurs pydantic : PromptRefiner→Router→Architect→
  Drafter→**Coder pydantic**→Linter→Static→**Tester pydantic (complet ET
  ciblé)**→Security→Judge fail-closed→feedback→correction. ✓
- Coder pydantic en production : it.1 à parité du golden (13 req / 474 s) ;
  it.2 convergent au budget près avec fix chirurgical exact. ✓
- Tester pydantic : verdicts convergés sous plafond, vrai bug détecté avec
  ligne + valeurs, fix confirmé. ✓
- Aucune fausse approbation, aucun crash, gardes (UsageLimits, wind-down,
  fail-closed) toutes respectées. ✓

## 8. Actions enregistrées

| ID | Action | Statut |
|---|---|---|
| F-163 | Pool navigateur run-scoped (1 MCP/Chrome par run + kill arbre garanti) | pending |
| F-164 | Garde var() CSS au Static Tester Tier 1 + règle remplissage barres skill frontend-design | pending |
| — | Analyzer F-60 : parser le format pydantic | à enregistrer |
| — | Contrainte de sortie Tester ciblé : failure ⇒ items FAIL explicites | à enregistrer |
| — | Calibrage Coder correction : le rituel de re-vérification complet après un fix 1-ligne coûte 28 min (piste : re-vérification ciblée au diff F-48 côté Coder aussi) | à enregistrer |
