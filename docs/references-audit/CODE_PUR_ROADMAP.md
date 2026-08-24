# Roadmap « Code pur d'abord » — inventaire des mécanismes déterministes portables

> Généré le 2026-08-20 (session Tetris), minage des 44 projets de `references/`
> par 2 agents d'exploration parallèles (gardes/vérification + fix/repair).
> Doctrine AGENTS.md §8.3 : **à chaque problème, demander d'abord si du code
> pur le résout** (garde / sonde / auto-fixer), le LLM pour le diagnostic et
> le jugement qualitatif uniquement.
>
> ⚠️ Rien n'est porté sans feu vert utilisateur (validation humaine §8.4).
> Tous les chemins sont relatifs à `references/`.

## Priorités proposées (ROI décroissant pour une usine web monofichier)

### P1 — Valideur HTML stdlib (Tier 0 avant Puppeteer)
**OpenKB** `openkb/deck/validator.py:128` `validate_deck` — validation structurelle
d'un livrable HTML généré en stdlib pur (`html.parser`) : parse OK, ≥N sections
requises, **self-contained** (toute `<link href>/<script src>/<img src>` externe =
erreur), taille bornée, grammaire déclarative (`required`/`allowed`/`min_distinct`).
Portage : invariants par type de page (jeu → canvas requis + score numérique),
ids dupliqués, `getElementById('x')` sans `id="x"` dans le DOM. Tourne AVANT le
navigateur — shift-left du Static Tester.

### P2 — Boucle serrée Coder sans LLM : format + diagnostics injectés
**kilocode** `packages/opencode/src/kilocode/tool/apply_patch.ts:276-323` —
après chaque édition : lance le formateur (prettier pour .html/.css/.js,
`src/format/formatter.ts:38-85`) puis **injecte les diagnostics de parse dans
l'output de l'outil** (« LSP errors detected… please fix »). Le modèle apprend
immédiatement qu'il a produit une syntaxe invalide → boucle d'itérations stériles
coupée sans appel LLM supplémentaire.
> ✅ PORTÉ (F-164 pour write/edit/search/multi + **F-166 pour append_file**, le
> dernier gap : `_post_edit_syntax_directive` sur tous les outils d'écriture,
> node --check + détecteurs statiques, sans le formateur prettier).

### P3 — Cascade de réparation des search/replace ratés
**aider** `aider/coders/search_replace.py:565` `flexible_search_and_replace` —
cascade exact → strip lignes vides (:611) → **indentation relative**
(`RelativeIndenter` :18-171, marqueur unicode `←`) → whitespace-tolerant
(`editblock_coder.py:243`) → élision `...` (:190) → diff-match-patch par lignes
(:338). Se branche EN AVAL de nos gardes F-132 : un edit raté pour raison
d'indentation est appliqué mécaniquement au lieu de coûter un tour LLM.
⚠️ Piège documenté : le fuzzy SequenceMatcher (:296) est **désactivé** chez aider
(`return` mort :184) — mauvais edits. À ne pas porter sans garde.
> ✅ PORTÉ (F-137 puis **F-166** : RelativeIndenter + fallback diff par lignes
> en difflib stdlib [équivalent dmp_lines_apply, 0 dépendance, gardes ratio
> ≥ 0.75 / marge 0.05 / ≥ 4 lignes] complètent la cascade existante ; fuzzy
> SequenceMatcher caractères NON porté, conforme au piège). Le préprocesseur de
> TÊTE est l'auto-décodeur `\n` littéraux F-166 (`decode_literal_escapes`,
> domicile canonique de la regex F-132 partagé garde/décodeur/repair F-133).

### P4 — Upgrade fence-aware du repair `\n` (F-133)
**deer-flow** `models/mindie_provider.py:154-164`
`_decode_escaped_newlines_outside_fences` — décode les `\n` littéraux
**uniquement hors des blocs de code** (split regex sur les fences). Notre
repair F-133 actuel peut dégrader du contenu où `\n` est légitime ; 10 lignes.

### P5 — Jaccard sur les RÉSULTATS d'outils (boucles à arguments variables)
**deer-flow** `middlewares/tool_progress_middleware.py:194`
`ToolProgressMiddleware` — machine à états ACTIVE→WARNED→BLOCKED par (thread,
outil) : un succès dont le word-set est near-duplicate (Jaccard ≥0.8) des
résultats précédents = tour stérile. Attrape ce que notre fingerprint F-36 ne
voit pas (arguments variés, même résultat). Bloque UN outil, pas le nœud.

### P6 — Self-healing de sélecteurs DOM au Tester
**Scrapling** `scrapling/parser.py:530-564` `retrieve_similar` + score
Similarité (:805) — re-localise un élément disparu en scorant les candidats
(tag exact + SequenceMatcher texte/attributs), seuil 40 %, log top-5. Portage :
le Web Tester sauvegarde la signature (tag+texte+attrs) des éléments vérifiés
et re-localise par score si le sélecteur casse après un fix → évite des
itérations Coder entières pour des false-negatives de test.

### P7 — Process-reaper + requeue (cycle kill→cleanup→replan)
**qm** `src/processes/process-reaper.ts:14` + `src/runs/reaper.ts:47` — registre
de process avec TTL, TERM → wait 5s → KILL → wait 2s → throw, flip idempotent
`reaped`, requeue/park des nœuds interrompus + force-release des leases morts.
Complète nos checkpoints git côté process (llama-server/Chrome orphelins,
« in progress » fantômes en DuckDB).

## Second rang (cités, à arbitrer)

| Pattern | Projet | file:line | Note |
|---|---|---|---|
| Cap fréquence PAR OUTIL (30 warn/50 strip) | deer-flow | `loop_detection_middleware.py:81` | Évasion du fingerprint par thrashing multi-args |
| Budget tokens PAR NŒUD + stop-reasons typés | deer-flow | `token_budget_middleware.py:62` | `budget_capped` ≠ `clean`, persisté |
| Streak « sans transition matérielle », bookkeeping ne reset pas | loopx | `quota/recent_runs.py:6` | Durcit l'idle breaker contre la fausse activité |
| Self-repair borné (1 tour) après stall | loopx | `quota/stall_repair.py:46` | Ni kill ni spin |
| Re-spawn à contexte frais + handoff 16 KB | deepseek-harness | `tool-ralph/src/index.ts:37` | Réponse au Coder « empoisonné » par son contexte |
| Retries LLM persistés dans l'event log | deepseek-harness | `llm-retry/src/index.ts:182` | Survit aux crashes (anti retry-storm) |
| Repair tool_calls avant sérialisation provider | deer-flow | `dangling_tool_call_middleware.py:429` | Durcissement production de notre orphan repair |
| Coercition d'arguments par schéma (int/bool) | open-swe | `sanitize_tool_inputs.py:24` | `offset='1, 80'` → 1, avant Pydantic |
| Repair de nom d'outil (trim+lowercase) | kilocode | `session/llm.ts:371` | Trivial |
| `json_repair` (rebalancing quotes/virgules) + garde finish_reason | OpenKB | `agent/compiler.py:540` | Seul user réel de la lib dans references/ |
| Strip `<think>`/fences + coupe troncature | deer-flow | `utils/llm_text.py:13-44` | Pré-parseur 60 lignes de toutes sorties LLM |
| Taxonomie ~25 classes d'erreurs API → action | hermes-agent | `error_classifier.py:30-119` | Politique retry/compress/fallback/abort unifiée |
| Paires tool_call/résultat réparées à la compaction | qm | `context-compaction.ts:159-224` | Complément F-101 |
| Boutons morts : listeners réels via CDP `getEventListeners` (cap 100) | browser-use | `dom/service.py:34,456-510` | Hard-gate « interactif mais sans handler » |
| Health-check « vivant mais figé » (`Runtime.evaluate` 1s, psutil ZOMBIE) | browser-use | `watchdogs/crash_watchdog.py:281` | Au-delà du readiness HTTP ponctuel |
| Erreur→action déterministe pour sous-tâches + finalizer garanti | open-swe | `middleware/task_retry.py:3-21` | Pas de « in progress » fantôme après crash |
| Canonisation récursive des args JSON (fingerprint) | deepseek-harness | `repeat-tool-reminder/src/index.ts` | 3 lignes, durcit F-36 |
| Deadline coopérative PAR OUTIL | deepseek-harness | `timeout-policy/src/index.ts` | Tool MCP pend alors que le nœud a du budget |
| Détection finish_reason « length » (sortie tronquée silencieuse) | deer-flow | `model_length_termination_detectors.py:14` | Voisin émetteur de notre hard-gate console |

## Déjà couvert par l'usine (écarté)

crush loop-detection ≈ F-36 · loopx material-hash ≈ F-88 · open-swe
timeout-wrapup ≈ wind-down F-131 · OpenKB mutation/rollback ≈ checkpoints git +
fs_tx · OpenSandbox retry transport ≈ F-104.

## Vague 3 — Gestion de contexte/mémoire déterministe (minage 2026-08-20, agent 3)

> Problème cible : le Coder atteint 900k-1,2M tokens d'INPUT par step (writes
> monolithiques + relectures empilées). Déjà porté avant ce minage : F-101
> (compaction 5 couches + archives + persisted-output + overflow guard).

| # | Projet | file:line | Ce que ça fait | Complexité |
|---|---|---|---|---|
| C1 | learn-claude-code | `s08_context_compact/code.py:271` `unseen_tool_result_positions` + :343 `micro_compact` | Tool_results déjà « vus » (antérieurs à la dernière réponse) remplacés par `[Earlier tool result saved at <path>]`, sauf les 3 derniers — tue les relectures empilées | **Faible** |
| C2 | learn-claude-code | idem :305 `tool_result_budget` (:230 constantes batch 200k/large 30k) | Budget de chars sur le BATCH du tour : trie par taille, persiste+preview les plus gros AVANT l'appel LLM — prévention du 900k input | **Faible** |
| C3 | kilocode | `session/compaction.ts:269` `prune` (:40 PRUNE_PROTECT=40k / MINIMUM=20k / PROTECTED_TOOLS) | Fenêtre glissante par outil avec seuil de rentabilité + protection par nom d'outil, idempotent, frontières cache-validantes | Moyenne |
| C4 | kilocode | idem :97 `preserveRecentBudget` + :207 `select` + `message-v2.ts:417` truncateToolOutput 2000c | Budget du récent = clamp(2k..8k, 25% ctx) ; coupe INTRA-step (un step n'est pas insécable) ; rendu modèle tranché à 2000 chars | Moyenne |
| C5 | deepseek-harness | `compaction-tool-result-pruner/src/index.ts:83` | Pruning tête/milieu/queue par tool result + accounting « shadow-price » (ce que la compaction masque) | **Faible** |
| C6 | loopx | `run_context_retention.py:229` + `run_compaction.py:75` | Rétention « dernier-par-type » (une seule observation par catégorie sémantique) + whitelists de champs par type de payload | **Faible** |
| C7 | open-swe | `middleware/plan_mode.py:78` | Liste d'outils recalculée par appel modèle, mutateurs retirés en phase plan, reset par run — schemas d'outils inutiles hors payload | **Faible** |
| C8 | deepseek-harness | tool-ralph `maxHandoffChars=16384` | Agent frais par round, workspace = état, handoff structuré borné (échec plutôt que troncature silencieuse) | Moyenne |
| C9 | deepseek-harness | `session-reference/src/config.ts:3` | Handoff inter-sessions borné en OCTETS, projection user/assistant uniquement, stats omittedBytes | Moyenne |
| C10 | learn-claude-code | `s07_skill_loading/code.py:108` | Catalogue lazy dans le system prompt (≈100 tokens/skill), corps à la demande — miroir de notre F-57 pour les TOOLS | **Faible** |

Bonus : hermes `trajectory_compressor.py:526` boundary snapping (coupes pair-safe pour notre compaction existante) · browser-use `agent/views.py:157` `ActionLoopDetector` (fenêtre 20 hashes SHA256 + fingerprints de page, nudges 5/8/12) · kilocode `DiffFull.detail` (table d'état fichiers : statut+numstat in-context, diff complet lazy) · deepseek-harness token-meter (budgets ancrés sur la vraie usage provider).

**ROI max immédiat pour notre 1M/step** : C1 + C2 (faibles, learn-claude-code, complémentaires : C1 nettoie l'existant, C2 prévient le futur), puis C6 (dernier-par-type sur les observations de fichiers).
