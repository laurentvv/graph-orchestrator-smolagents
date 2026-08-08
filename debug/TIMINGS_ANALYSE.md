# Analyse des timings par nœud — Bubble Sort Visualizer

**Date** : 2026-08-01 | **Source** : 2 runs réels (GPU local vs CPU distant) + audit utilisateur

---

## ✅ ACTION CORRIGÉE : Tester (`document.querySelector`) — fix F-45 appliqué

Le **bloqueur n°1** identifié est désormais corrigé (cycle F-45, 2026-08-02).

**Symptôme observé** : le Web Tester (gemma-12B + MCP Puppeteer) bouclait sur l'erreur
`document.querySelector is not a function` pendant **10 steps** (run GPU) sans jamais
produire de verdict valide. Le run s'épuise sans que le Judge ne soit jamais appelé.

**Racine RÉELLE (diagnostic empirique corrigé)** : lecture du log GPU révèle que la cause
n'était PAS "Puppeteer n'expose pas querySelector" (hypothèse initiale, fausse). Le modèle
(gemma-12B) a écrit `document.querySelector='input[type="range"]'` (**assignation** `=`)
au lieu de `document.querySelector('...')` (**appel** `()`). En JS, cette assignation
**écrase la fonction native** dans le contexte page → tous les appels suivants échouent
"not a function". Le modèle bouclait car il cherchait une cause externe (Puppeteer,
contexte Node vs navigateur) sans réaliser qu'il avait lui-même corrompu `document`.

**Le code généré n'était PAS en cause** : le HTML utilise `getElementById` (qui marche),
validé visuellement dans Chrome par l'audit utilisateur (`audit_coder/`).

**Fix appliqué** (F-45, 3 axes) :
1. ✅ **Skill `web-tester`** enrichi : directive ciblée anti "querySelector assigné au lieu
   d'appelé" (le `=` vs `()` fatal) + garde anti-pollution du contexte (jamais réassigner
   une méthode native) + replis robustes (`getElementById`/`getElementsByTagName` quand on
   doute des sélecteurs) + pattern DOMContentLoaded (anti faux échec sur DOM non peuplé).
2. ✅ **Cap steps configurable** : `TESTER_MAX_STEPS` (défaut 12, avant 24 hardcoded) borne
   la durée — le verdict est clair à 10-12 steps, éviter de brûler ~30 min sur une boucle.
3. ✅ **Guard anti-idle (F-33) étendu au Tester** : `LoopGuard` désormais passé au Web Tester
   (détecte la répétition exacte du même `puppeteer_evaluate`) + message idle contextuel
   (`node_kind="tester"` → cite `puppeteer_*`/`final_answer`, pas `write_file`).
4. ✅ **Suite pytest** : 487 passed / 0 failed (482 baseline + 5 nouveaux). 0 régression.

---

## 📊 Tableau comparatif (run complet Bubble Sort, 1 fichier index.html)

## 📊 Tableau comparatif (run complet Bubble Sort, 1 fichier index.html)

| Nœud / Métrique | GPU local (4B+12B) | CPU distant (run 6) | Ratio CPU/GPU |
|-----------------|--------------------|-----------------------|---------------|
| **PromptRefiner** (12B, DSPy) | ~20s | ~180s | ~9× |
| **Router** (4B, DSPy) | ~8s | ~15s | ~2× |
| **Architect** (12B, DSPy) | ~90s | ~300s | ~3× |
| **Coder** (4B, smolagents) | **77s (2 steps)** | 695s (6 steps) | **9×** |
| **Linter** (déterministe) | <1s | <1s | = |
| **Tester** (12B, Puppeteer) | 1839s (10 steps) | 1628s (10 steps) | **0.9×** |
| **Security** (12B, DSPy) | ~40s (parallèle Tester) | ~60s (parallèle) | — |
| **Judge** (12B, DSPy) | (non atteint) | ~30s | — |

**Total observé** : ~35 min (GPU) vs ~50 min (CPU), dont **~30 min rien que pour le Tester**.

---

## 🔍 Le verdict : le Coder est réglé, le Tester est le goulot

### ✅ Coder : 9× plus rapide sur GPU (le fix Architect décisif)

Le fix de l'Architect ("1 livrable testable = 1 sous-tâche, `simple` par défaut") a un effet **massif** :
- **Avant** (CPU, 2 sous-tâches `incremental`) : 6 steps, 695s — squelette + appends + bugs de structure
- **Après** (GPU, 1 sous-tâche `simple`) : **2 steps, 77s** — one-shot, fichier complet et correct (9726 octets)

Step 1 = génération du fichier complet (69s). Step 2 = `final_answer` (8s). C'est optimal.

### ⚠️ Tester : LE goulot d'étranglement (~30 min, même sur GPU)

Le Tester (gemma-12B + Puppeteer) consomme **~30 min** dans les 2 configs. Pourquoi :

1. **Step 1 systématiquement long** : 429-477s (7-8 min) — c'est le chargement du navigateur Puppeteer + la lecture du system prompt + le 1er raisonnement. Incompressible sauf à précharger le navigateur.

2. **Friction `querySelector is not a function`** (17 occurrences sur le run GPU !) : le Tester boucle dessus pendant les Steps 5-10. **Racine réelle (diagnostic empirique post-mortem, F-45)** : le modèle a écrit `document.querySelector='...'` (**assignation** `=`) au lieu de `document.querySelector('...')` (**appel** `()`) au Step 4. Cette assignation écrase la fonction native dans le contexte page → tous les appels suivants échouent. Le modèle cherchait une cause externe sans réaliser qu'il avait corrompu `document` lui-même. **Corrigé (F-45)** : directive skill ciblée `=` vs `()` + replis `getElementById` + garde anti-pollution du contexte.

3. **Friction "does not contain any JSON blob"** (3×) : le modèle réfléchit (gemma-12B thinking) sans émettre de tool call. **Corrigé (F-45)** : le guard anti-idle (F-33) est désormais étendu au Tester avec un message contextuel (`node_kind="tester"` → cite `puppeteer_*`/`final_answer`).

4. **Contexte qui gonflé** : les tokens INPUT passent de 8k (Step 1) à 91k (Step 10). Chaque step ajoute le précédent + les observations Puppeteer (DOM, screenshots). Le nettoyage DOM (F-37) aide mais le 12B reste lent sur un gros contexte.

### Friction CPU-distante spécifique : Step à 1658s (28 min !)
Sur le run CPU, un step Coder a duré **28 minutes** (input 140k tokens). C'est un appel LLM qui a failli timeout (LLM_TIMEOUT_S=600) — probablement des retries internes silencieux de smolagents sur une génération très longue. Non observé sur GPU.

---

## 🎯 Recommandations par priorité (impact sur la durée)

> **MISE À JOUR F-47 (2026-08-02)** — la cause racine des "Step à 1658s" et du hang Judge
> a été identifiée et résolue : **le mode thinking de Gemma 4 est forcé sur l'endpoint `/v1`
> d'Ollama** et consomme tout le budget `max_tokens` avant d'émettre la réponse → lenteur
> extrême voire hang. Fix F-47 : tous les nœuds DSPy parlent désormais `/api/chat` (provider
> litellm `ollama/`) avec `think=False` (sauf l'Architect où le raisonnement aide). Validé :
> ~6 s vs ~23 min. Ce levier dépasse les recommandations ci-dessous (il agit sur TOUS les
> nœuds 12B, pas seulement le Tester). Le Coder (4B) subit aussi le thinking — traité au
> cycle F-48 (vision Coder). Détails : `debug/GAPS_TESTER_JUDGE.md`.

| # | Recommandation | Impact estimé | Effort | Statut |
|---|----------------|---------------|--------|--------|
| 1 | **Cap Tester steps à 12** (au lieu de 24) — le verdict est généralement clair à 10-12 steps | -30% durée Tester | 1 ligne config | ✅ F-45 |
| 2 | **Fix friction `querySelector`** : enrichir le skill web-tester avec un exemple `puppeteer_evaluate` correct + directive "si querySelector échoue, utilise getElementById" | -3-4 steps gaspillés | édit skill | ✅ F-45 |
| 3 | **Précharger navigateur Puppeteer** au démarrage du workflow (pas à chaque Step 1 Tester) | -7 min par sous-tâche testée | moyen | ⬜ échéance |
| 4 | **Tester en CodeAgent** (pas ToolCallingAgent) — comme le Coder, pour bénéficier du guard anti-idle (F-33) sur "does not contain JSON blob" | -2-3 steps gaspillés | refacto | 🟡 F-45 : guard étendu au Tester sans refacto CodeAgent (message idle contextuel + LoopGuard) |
| 5 | **Compaction contexte Tester** : les observations DOM/screenshot gonflent le contexte à 91k tokens → le 12B ralentit. Tronquer/agréger les vieilles observations | -20% durée steps 5+ | moyen | ⬜ échéance |
| 6 | **Garder le config GPU** : le Coder est 9× plus rapide. Le Tester n'est pas accéléré par le GPU (gemma-12B tient déjà en VRAM) mais l'évite le swapping | stable | .env | ℹ️ config actuelle |

---

## 📁 Logs source
- **Run GPU** : `debug/run_gpu_*/run_log.txt` (1932 lignes, 165 Ko) + `index.html` (9726 octets)
- **Run CPU** : `debug/run6_20260801_200231/run_log.txt` (7237 lignes, 514 Ko) + `index.html` (7014 octets)
- **Audit utilisateur** : `audit_coder/` (7 tests progressifs + screenshots Chrome)
- **Script parsing** : `/tmp/parse_timings.py` (réutilisable pour futurs runs)
