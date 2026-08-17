# Post-mortem COMPLET — Run #8 (E2E FRESH_START, 2026-08-16 22:05 → 23:52)

> **Le run de trop qui a tout appris.** 1 h 47, 19,4 M tokens input, 3 itérations
> complètes, aucune approbation — et une moisson de diagnostics dont DEUX causes
> racines prouvées par le code (sauvetage Pydantic → port mort) et par les faits
> (prune qui détruit les runs). Ce document reconstruit tout, phase par phase.

- **Run** : `coding_d72dc8e36445c4b6` — prompt `bubble-sort-multifile-v6` (Bubble
  Sort 3 fichiers, dark mode, animation pas-à-pas).
- **Config** : FRESH_START=1, backend spawn (Qwen3.5-4B fast / Ornith-9B reasoning
  no-think), RTX 3060 Laptop 6 Go, branche feat/f-95 (PR #86 ouverte — F-95 actif).
- **Résultat final** : `status=escalated` — livrable 3 fichiers syntaxiquement
  valides, servi HTTP 200, mais **tri instantané** (le bug central) → Judge
  fail-closed ×3 → escalade.
- **Artefacts** : le dossier `runs/2026-08-16_2205_*` a été **détruit à 00:21-00:23
  par le bug de prune** (§7) — les livrables ont été récupérés depuis les blobs git
  et préservés dans `debug/postmortem_run8_artifacts/`.

---

## 1. Timeline reconstructée (16 serveurs llama spawnés)

| Heure | Phase | Durée | Détail |
|---|---|---|---|
| 22:05 | Boot | — | rétention : ~20 anciens runs « supprimés » (en réalité partiellement — §7) ; verrou run dir F-95 acquis |
| 22:05-22:06 | PromptRefiner | 34,8 s | spec 2 502 chars, 3 ambiguïtés (Qwen p64431) |
| 22:06 | Router | 17,7 s | web/HTML (Qwen p62428) |
| 22:06-22:07 | Architect | 51,8 s | 1 sous-tâche `F-82-ts-01` (3 fichiers, strategy multifile) |
| 22:07 | Drafter | 20,7 s | draft 77 lignes, Drafter Gate OK |
| 22:07-22:13 | **Coder it.1** | 341 s | 263 486 tok in / 1 697 out — 3 fichiers créés, **16 archives de compaction** (.transcripts), validation visuelle + fuzzing |
| 22:07→22:13 | Linter + Static | 0,2 + 10,4 s | Tier 1c flagge 2 bugs réels (compteur figé + délai ~5 ms) |
| 22:45-22:53 | **Tester it.1** | 456,8 s | 179 830 in / 822 out — Ornith no-think, **max steps atteint**, Pydantic KO → sauvetage KO (§5) → fallback F-61 `failure` |
| 22:54-22:55 | Security it.1 | 102,8 s | OK |
| 22:54 | **Judge SKIPPÉ** | 0 s | fail-closed F-108 (« Test failure → approbation bloquée ») — REJET |
| 22:56-23:09 | **Coder it.2** | 793,9 s | le plus long (génération marathon step 31 + retry contexte purgé) ; corrections `search_replace` chirurgicales |
| 23:09-23:14 | Tester it.2 | 272,3 s | re-test ciblé — même échec de convergence → fallback failure |
| 23:15 | Security it.2 | 98,4 s | Judge SKIPPÉ — REJET |
| 23:17-23:22 | **Coder it.3** | 331,8 s | 261 441 in / 1 599 out — corrections finales (compteur au chargement) |
| 23:23-23:31 | Tester it.3 | 466,4 s | même échec → fallback failure (3/3) |
| 23:31-23:36 | Security it.3 | 281,7 s | Judge SKIPPÉ — REJET |
| 23:36-23:38 | **Escalade F-23** | 103 s | diagnostic persisté, gravité high — **mais halluciné (§6)** |
| 23:38-23:52 | **Consolidation F-68** | 838,9 s | 10 claims → 1 entité consolidée (14 min !) |
| 23:52 | Fin | — | checkpoint effacé, exit 0, tableau d'observabilité émis |

Total nœuds : 4 237,7 s (~71 min). Écart wall-clock (~36 min) = spawns serveurs
(~16 × 30-60 s de chargement GGUF), sessions DevTools/MCP, git, attentes.

## 2. Métriques clés

- **Tokens** (analyseur, cumul steps) : 19 365 962 in / 176 870 out. Table nœuds :
  1 013 568 (périmètre métriques smolagents). Le golden run de référence : 648 748
  — ce run a consommé **~30× le golden**, à cause des 3 itérations + contextes
  Tester 21-24k tokens + throttling thermique.
- **Vitesse GPU** : Qwen 4B de ~11 t/s (début) à **4,8 t/s** (fin, throttling
  laptop) ; Ornith 9B no-think **2,6-3,1 t/s** sur prompts 21-24k (générations de
  190 s observées). La fenêtre 6 Go tient (4,4-4,5 GiB utilisés).
- **Serveurs** : 16 spawns, **tous terminés proprement** (slot release, 0 erreur) —
  la théorie « serveur mort » du sauvetage est ÉCARTÉE (§5).

## 3. La génèse du bug central (prouvée par le diff git)

Le diff itération 1 → 2 (récupéré des blobs) raconte tout :

```diff
-let speed = 50; // ms par étape
+let speed = 320; // ms par étape (défaut, ajusté par slider)
-        await sleep(speed);
+        await sleep(320 - speed * 2);
+    counter.textContent = comparisons;   // ← fix compteur : CORRECT
```

1. **It.1** : `sleep(speed)` avec `speed=50` — animation à 50 ms/step (lente mais
   réelle) ; le Tier 1c flaggait « délai ~5 ms » + « compteur jamais rafraîchi ».
2. **It.2** : le Coder corrige le compteur (correct) MAIS, pour le délai, **greffe
   la formule littérale suggérée par le message pédagogique du Tier 1c**
   (`const delay = 320 - speed * 28;` — qui suppose speed = valeur slider 1-10)
   **tout en gardant speed en millisecondes (320)** et en écrivant `* 2` au lieu
   de `* 28` : `320 - 640 = −320` → `setTimeout` clampe à 0 → **instantané**.
   En plus, `draw()` n'est jamais appelé dans la boucle (le canvas ne se repeint
   qu'à la fin) et le `sleep` est par PASSE, pas par comparaison.
3. **It.3** : fix cosmétique (compteur au chargement) — le bug de délai persiste.

**Chaîne causale complète** : message pédagogique formule-littérale (F-54 Tier 1c
d'avant F-112) → greffe aveugle du 4B sur mauvaise unité → délai négatif clampé →
**cécité du Tier 3** (découvreur de signal = premier élément numérique du DOM = le
libellé du slider, une constante → skip silencieux) → **Tester LLM jamais convergé**
(§5) → personne n'a vu l'instantané → Judge fail-closed (correct) → escalade.

→ **Corrigé par F-112 (PR #87)** : sonde multi-signal (tous les compteurs par id +
hash pixels canvas + classes terminales) + résolution arithmétique des délais
(`320 - speed*2` → −320 → flag) + message sans formule copiable. La réplique exacte
du run #8 est RÉFUTÉE en < 5 s, 0 LLM.

## 4. Ce qui a FONCTIONNÉ (validation live des features)

| Feature | Preuve dans ce run |
|---|---|
| F-39/01 PromptRefiner-Router-Architect | spec structurée, 1 sous-tâche bien découpée |
| F-90/F-109 audit visuel Coder | 6/6 critères DÉMONTRÉS par screenshot (ités 1 et 2) |
| F-19/F-29 correction chirurgicale | it.2/3 en `search_replace`, jamais de rewrite complet |
| **F-101 compaction v2** | 16 archives `.transcripts/*.jsonl` en it.1 — le Coder a tenu 263k tokens de contexte sans overflow fatal |
| F-53/F-102 git du run | 3 commits + 3 refs de turn-checkpoint (…jusqu'à ce que prune les détruise, §7) |
| **F-95 (PR #86)** | verrou run dir acquis ; transactions `.fs_tx` propres (0 journal résiduel) ; allowlist IO — 0 blocage illégitime |
| F-61 fallback verdict | 3× « verdict dérivé du step history (status=failure) » — la boucle de retries infernale d'avant est morte |
| **F-108 Judge fail-closed** | 3× « Judge SKIPPÉ, approbation bloquée » — aucun code non testé n'a été approuvé à l'aveugle |
| F-104 retry/revive | les blips transport de l'agent ont été retryés ; dégradations gracieuses partout |
| **F-68 Phase 2 recall** | « 8 leçon(s) durable(s) injectée(s) au Coder » — dont la leçon compteur du 15/08, que le Coder a effectivement corrigée en it.2 |
| F-100 preuve exécutable | post-run : HTTP 200 en 0,9 s sur port libre |

## 5. CAUSE RACINE N°1 (prouvée par le code) : le sauvetage Pydagnostic tape sur un port mort

**Symptôme** (3/3, déterministe) : fin de session Tester → parsing Pydantic en
échec (max steps, `final_answer` absent/malformé) → « sauvetage DSPy » →
`litellm.InternalServerError: OpenAIException - Connection error` → None.

**Faits qui écartent les coupables obvious** : les 3 serveurs Tester (Ornith
p55933/p64517/p59573) se sont tous terminés par un `slot release` PROPRE, 0 erreur ;
le parsing a lieu DANS le `with model_lifecycle` (serveur vivant) ; pas de proxy
env ; `srv.api_base = http://127.0.0.1:<port>/v1` correct.

**La preuve** (`nodes.py` → `run_with_retry`) :

```python
api_base_val = getattr(agent_model, "api_base", None)   # ← TOUJOURS None !
validated = extract_and_validate(raw_output, model_class, api_base=api_base_val, ...)
```

`smolagents.OpenAIServerModel.__init__` **n'assigne jamais `self.api_base`** — il
range l'URL uniquement dans `client_kwargs["base_url"]` (vérifié par introspection :
`'self.api_base' in source → False`). Donc `getattr(..., "api_base", None)` rend
**None à chaque fois**, et `extract_and_validate` retombe sur
`settings.local_api_base` = `http://localhost:8000/v1` — **un port où rien
n'écoute en mode spawn** → Connection error immédiate, déterministe.

Indices convergents dans l'erreur : le préfixe `[llama]` montre que même la sonde
`GET /models` (timeout 2 s) du sauvetage échouait silencieusement (fallback
model_id `"default"`→`"llama"`) — tout le chemin sauvetage pointait au mauvais
endroit.

**Fix (prochain cycle, trivial)** : résoudre l'URL réelle —
`getattr(agent_model, "api_base", None) or (agent_model.client_kwargs or {}).get("base_url")`
— idéalement via une propriété `api_base` sur `LoggedOpenAIServerModel`. Avec ça,
le sauvetage tape le serveur vivant, le verdict du Tester est parsé, et la boucle
Coder→Tester→Judge peut enfin APPROUVER.

## 6. Découverte n°2 : le nœud d'Escalade HALLUCINE son diagnostic

Le diagnostic persisté (gravité high, rappelable par les runs futurs via F-68 !)
affirme : « *Le Juge a identifié 4 bugs récurrents : compteur non rafraîchi, délai
trop court, crash sur propriété undefined, syntaxe invalide* » et « *index.html
tronqué, script.js incomplet, le CSS est absent* ».

**Or** : le Judge n'a JAMAIS tourné (skippé 3× par F-108) ; les 3 fichiers étaient
complets (831/2 190/4 732 octets) et `node --check` passait. L'Escalade (Ornith)
a **inventé** un diagnostic plausible à partir des réfutations, sans voir les
artefacts. Risque en cascade : ces fausses « leçons » sont rappelées aux Coder
futurs (la machine à leçons apprend des erreurs qui n'existent pas). Noter aussi
que l'escalade du **15/08** (même tâche) avait déjà un diagnostic proche —
l'échec est récidiviste, la mémoire n'a pas suffi à le prévenir.

**Fix proposé** : injecter dans le prompt d'Escalade les PREUVES matérielles
(verdicts static tester bruts, liste fichiers + tailles, résultat `node --check`,
statut Judge skipper) + règle « ne cite que ce qui est dans les preuves » (et/ou
vérification déterministe post-génération, miroir du grounding F-93).

## 7. INCIDENT MAJEUR (découvert pendant l'analyse) : `_prune_old_runs` détruit les runs en silence

**Fait** : ~**290 dossiers** de `runs/` ont un `.git` éviscéré (ne reste que
`objects/`) depuis le **3 août** — et le run #8 lui-même a été **détruit à
00:21-00:23** (20 min après sa fin) : livrables + draft + `.transcripts` supprimés,
`.git` réduit à 37 objects. Seul le hasard (capture 23:56 + blobs) a permis cette
analyse.

**Mécanisme** :
1. `_prune_old_runs` fait `shutil.rmtree(path, ignore_errors=True)` — sous Windows
   certaines suppressions échouent (verrou transitoire) → rmtree **abandonne en
   silence** une partie de l'arbre (HEAD/refs/config partis, objects restants) ;
2. le message « 🗑️ Ancien run supprimé » est imprimé **sans vérifier** que la
   suppression a réussi ;
3. chaque passe suivante supprime un peu plus (vagues de destruction progressives,
   mtimes alignés sur les exécutions de la suite pytest) ;
4. **amplificateur** : des tests E2E de la suite créent de VRAIS dossiers sous
   `runs/` (output_dir non isolé — dirs `_t1`/`_task1` par dizaines) → les runs
   RÉCENTS tombent hors du top-10 de la rétention → le run qu'on vient de valider
   est détruit par le prochain `pytest tests/`.

**Fix proposé (P0)** : (a) remplacer `ignore_errors=True` par une suppression
vérifiée (re-essai, puis log BRUYANT + abandon si le dir survit) ; (b) les tests
E2E doivent isoler `output_dir` sur tmp_path ; (c) exclure les runs des N dernières
heures de la rétention (grâce période) ; (d) à terme : rétention basée sur la
taille disque plutôt qu'un compte fixe.

## 8. Autres enseignements

- **Consolidation F-68 : 14 min** pour 10 claims — le prompt multi-appels DSPy sur
  le 9B throttled est trop lourd en fin de run. Piste : batch unique + cache KV
  (préfixe commun rejoué, pattern deepseek-harness du plan P9) ou consolidation
  asynchrone.
- **Throttling thermique** : 11 → 4,8 t/s au fil du run (laptop). Le run est
  viable mais ~2× plus long que le golden ; prévoir des pauses/`ngl` réduit si ça
  se répète.
- **Judge jamais exécuté = 0 verdict** : le tableau d'observabilité montre
  `code_judge_dspy 0.0s` ×3 — le graphe a passé 3 itérations sans LIMIER
  qualitatif. Avec le fix §5, le Judge redevient le verrou qualité attendu.
- **Récupération forensique** : un `.git` éviscéré garde ses blobs — repo bare +
  `objects/info/alternates` → lecture complète des commits. Les livrables du
  run #8 sont préservés dans `debug/postmortem_run8_artifacts/`.

## 9. Roadmap issue de ce run (priorisée)

| # | Fix | Effort | Impact |
|---|---|---|---|
| P0 | **api_base du sauvetage** (§5) : lire `client_kwargs["base_url"]` (+ test régression) | ~1 h | Débloque TOUT : verdicts Tester parsés, Judge actif, approbations possibles |
| P0 | **prune vérifié + tests E2E isolés** (§7) | ~2 h | Arrête la destruction silencieuse des runs |
| ✅ | Sonde animation multi-signal (F-112, PR #87) | fait | Le bug central du run #8 est désormais réfuté en < 5 s, 0 LLM |
| P1 | Escalade appuyée sur preuves (§6) | ~0,5 j | Stoppe l'apprentissage de leçons hallucinées |
| P2 | Allèger la consolidation (§8) | ~0,5 j | −10 min par run |
| P3 | Anti-throttling (ngl/pauses) | à mesurer | −20-30 min par run sur laptop |

---
*Analyse : assistant (ZCode), 2026-08-17, sur la branche feat/f-112-animation-probe
(PR #87). Sources : log complet du run (13 042 lignes), 16 logs llama-server,
DuckDB (claims/escalations/insights), blobs git récupérés via alternates,
introspection du code (models.py:249-340, nodes.py:520-560, web_tester.py:345-382,
workflows.py:112-133, llama_server.py:181-184).*
