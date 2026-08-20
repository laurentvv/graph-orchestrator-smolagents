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

### P3 — Cascade de réparation des search/replace ratés
**aider** `aider/coders/search_replace.py:565` `flexible_search_and_replace` —
cascade exact → strip lignes vides (:611) → **indentation relative**
(`RelativeIndenter` :18-171, marqueur unicode `←`) → whitespace-tolerant
(`editblock_coder.py:243`) → élision `...` (:190) → diff-match-patch par lignes
(:338). Se branche EN AVAL de nos gardes F-132 : un edit raté pour raison
d'indentation est appliqué mécaniquement au lieu de coûter un tour LLM.
⚠️ Piège documenté : le fuzzy SequenceMatcher (:296) est **désactivé** chez aider
(`return` mort :184) — mauvais edits. À ne pas porter sans garde.

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
