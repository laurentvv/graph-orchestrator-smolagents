# 19 — loopx

## En-tête
- **Nom** : loopx (github.com/huangruiteng/loopx)
- **Chemin** : `references/loopx/`
- **Type** : Framework de contrôle d'agents longue durée (control plane) — couche de gouvernance au-dessus de runtimes d'agents (Codex/Claude/Cursor), pas un runtime lui-même
- **Langage principal** : Python 3.11+ (**stdlib pure, zéro dépendance runtime** — `dependencies = []` dans `pyproject.toml`)
- **Statistiques** : ~2150 fichiers (1568 `.py`, 422 `.md`) hors `.git/` ; projet mature (~2757 PRs) ; licence MIT
- **Persistance** : **JSONL sur disque + file locks** (aucune base SQL — différence clé avec le projet cible qui est DuckDB)

## Synthèse
LoopX est un « local control plane for long-running AI agent work » : un noyau d'état durable (objectives, gates, todos, evidence, quota, handoffs) qui gouverne des agents longue durée en exécutant des turns bornés. Ce n'est pas un runtime d'agent mais la couche de contrôle au-dessus (un « Kanban agent-native »). Le vocabulaire (quota, gate, evidence, ledger, handoff, turn transaction) mappe presque 1:1 avec les besoins de notre nœud d'escalade et de notre boucle Coder→Tester.

Sa valeur pour le projet cible est **exceptionnellement concentrée sur trois priorités indépendantes** :
1. **P3 (anti-loop)** — au lieu d'une détection naïve par similarité d'output, loopx combine (a) un **quota comptable** (chaque turn « coûte » un slot et doit être justifié par une `delivery_outcome` matérielle), (b) un **stall self-repair** (turn borné pour réparer la projection plutôt que de spinner), (c) un **hash de changement matériel** (`result_hash`/`material_change`).
2. **P9 (compaction)** — compaction par **whitelist de champs par type de payload** + rétention du contexte durable le plus récent par agent (compaction structurelle, pas sémantique).
3. **P11 (event stream)** — **event sourcing append-only idempotent** (fingerprint, checksum SHA256, détection de conflit, rebuild d'état) + **event ledger classifié** en 5 classes (accounting/decision/evidence/state/work) + modèle de **turn transaction** ordonné.

**Réserves importantes** :
- Le code est extrêmement verbeux (Python très défensif, `dict[str, Any]` partout ; `quota.py` fait 2784 lignes). Il faut **extraire les algorithmes, pas copier le code**.
- **Aucune intégration LLM/DSPy** — loopx est agnostique au runtime. La compaction est structurelle (champs), pas sémantique (pas de résumé LLM) : à compléter par-dessus pour les petits modèles.
- Domaine très spécifique (issue/PR/benchmark loops) — beaucoup de code est du bruit (Lark, Codex CLI, terminal-bench). Privilégier `loopx/control_plane/`.
- Persistance JSONL+filelock vs DuckDB : la **logique d'idempotence/reprise** se transpose, le **store** se reloge sur DuckDB.

Note globale : **🟢 Haute** (algorithmes matures, testés, projet à 2757 PRs, stdlib pure donc portable). Les trois briques P3/P9/P11 sont de portabilité différente mais chacune apporte un blueprint que ne fournit aucune des 18 fiches existantes.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/loopx/README.md` | Présentation du control plane, vocabulaire (objective, gate, todo, evidence, quota, handoff, turn) | Moyenne |
| `references/loopx/AGENTS.md` | Conventions du dépôt (rôles, statuts) | Moyenne |
| `references/loopx/docs/` | Documentation conceptuelle (cycles de vie, projections) | Moyenne |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/loopx/loopx/control_plane/quota/recent_runs.py` | `consecutive_unchanged_monitor_observations`, `build_monitor_debt_arbitration`, `_run_is_unchanged_monitor_observation`, `_run_is_controller_bookkeeping`, `MONITOR_DEBT_UNCHANGED_TURN_THRESHOLD=2` | **Détecteur de stall déterministe (~160 L).** Compte les turns consécutifs « sans transition matérielle » ; ignore explicitement le bookkeeping (accounting/state_refreshed) ; au-delà du seuil=2, l'arbitration change la priorité (backoff). C'est exactement le complément déterministe manquant à crush (10) qui ne fait que du hash d'output. | **Haute** | Algorithme pur transposable direct à la boucle Coder→Linter→Tester (max 3 itérations) pour détecter le stall au-delà de la simple répétition |
| `references/loopx/loopx/capabilities/issue_fix/pr_monitor_materialization.py` | `_group_fingerprint(member_keys)`, `result_hash`, `previous_hash != result_hash` → `material_change`, `consecutive_no_change` | **Pattern de détection de boucle par hash d'output.** Calcule un hash canonique de la sortie, le compare au précédent ; si inchangé, incrémente un compteur de stall. C'est le **pattern exact** transposable pour hasher la sortie du Coder à chaque itération. | **Haute** | Complément direct à notre LoopGuard (F-36) actuel qui ne fingerprint que les tool_calls, pas l'output matériel |
| `references/loopx/loopx/control_plane/work_items/delivery_outcome.py` | `DeliveryOutcome` (enum), `DeliveryTurnKind`, `ACCOUNTABLE_DELIVERY_OUTCOMES`, `PROGRESS_DELIVERY_OUTCOMES`, `normalize_delivery_outcome`, `delivery_turn_kind_for_run` | **Vocabulaire normalisé du résultat d'un turn** (accountable/progress/followthrough). Un turn sans outcome matérielle = pas de progression = graine de stall. C'est la **métrique qui alimente tout l'anti-loop** loopx. | **Haute** | Petit module d'enum transposable direct : classifier chaque itération Coder→Tester en accountable/progress/idle pour alimenter le détecteur de stall |
| `references/loopx/loopx/control_plane/quota/stall_repair.py` | `build_quota_stall_self_repair_hint`, `apply_stall_repair_delivery_guard`, `RUNTIME_RECOVERY_ACTION_TOKENS`, `control_plane_self_repair_allows`, triggers `health_blocker`/`waiting_without_owner_projection` | Au lieu de bloquer ou spinner, déclenche un **self-repair turn borné** : un seul spend autorisé après réparation+validation+writeback. Décide si l'action recommandée est une réparation runtime (retry/repair/restore). | Moyenne | Pattern transposable mais lié aux concepts loopx (goal/todo/projection) — adapter au nœud d'escalade |
| `references/loopx/loopx/control_plane/quota/slot_accounting.py` | `build_quota_slot_spend_event`, `record_quota_slot_spend_from_preview`, `_latest_unspent_accountable_delivery_run`, `build_quota_slot_void_event` | **Comptabilité des « slots » de quota** : chaque delivery accountable consomme un slot, détection du dernier run accountable non dépensé, void/annulation. C'est le **budget anti-boucle** (au-delà du quota → escalade). | Moyenne | Algorithme transposable mais lié au modèle « goal/run » loopx ; inspire notre circuit breaker max 3 itérations |
| `references/loopx/loopx/control_plane/turn_driver/transaction.py` | `LoopXTurnResultKind` (enum: `VALIDATED_PROGRESS`/`REPAIR_REQUIRED`/`REPLAN_REQUIRED`/`QUOTA_SPEND_FAILED`…), `build_loopx_turn_transaction_plan`, `validate_loopx_turn_receipt`, `NO_SPEND_RESULT_KINDS`, `STOP_RESULT_KINDS`, commit_policy `result<validate<writeback<spend` | **Modèle de transaction pour un turn d'agent.** Plan avec `turn_key` (hash canonique de l'identité), phases ordonnées, receipt validé, gating du spend selon le résultat. Distingue les turns qui « coûtent » des turns gratuits (wait/user_action). | **Haute** | Enum + fonctions pures directement transposables au workflow Coder→Linter→Tester ; `NO_SPEND`/`STOP` distinguent turns productifs vs gratuits |
| `references/loopx/loopx/event_sourced_state.py` | `AppendOnlyStateEventStore`, `normalize_state_event`, `event_fingerprint`, `event_stream_checksum`, `_dedupe_events`, `build_state_projection`, `StateEventConflictError` | **Event sourcing append-only JSONL : idempotence par `event_id`+fingerprint, détection de conflit, séquence auto, rebuild d'état par projection, checksum SHA256 du flux.** Lock fichier exclusif sur append. | **Haute** | La logique d'idempotence/reprise est directement adaptable — à reloger sur DuckDB au lieu de JSONL+filelock (le projet cible utilise déjà DuckDB). Complète notre F-43 (idempotence effets de bord) côté event stream |
| `references/loopx/loopx/control_plane/runtime/event_ledger.py` | `EVENT_LEDGER_CLASSES` (`accounting`/`decision`/`evidence`/`state`/`work`), `event_ledger_event_class`, `build_event_ledger_summary`, `blank_event_ledger_goal` | **Journal d'événements classifiés en 5 classes, agrégés sur fenêtres 24h/7d par goal, avec dernier event/benchmark.** Projection depuis l'historique de runs (pas un store séparé). Idéal pour observabilité. | **Haute** | Pur (~197 L), transposable ; blueprint pour notre event stream (P11) au-delà du contrat deer-flow (08/13) |
| `references/loopx/loopx/control_plane/runtime/run_compaction.py` + `run_context_retention.py` | `compact_run_base`, `compact_human_reward`, `compact_operator_gate`, `compact_vision_checkpoint`, `RUN_BASE_COMPACT_FIELDS`, `latest_runs_with_agent_context`, `PER_AGENT_CONTEXT_RUN_FIELDS` | **Compaction par whitelist de champs par type de payload** (un tuple de champs à garder) + **rétention du contexte durable le plus récent par agent** (vision/checkpoint). Évite le trim bête : garde l'essentiel structurel, jette le verbose. | **Haute** | Pattern simple et portable (listes de champs) ; transposable quasi-direct. Réserve : compaction structurelle seulement, pas de résumé LLM — à compléter pour petits modèles |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/loopx/pyproject.toml` | config | `dependencies = []` — preuve du zero-dependency runtime ; utile comme garde-fou de portabilité |
| `references/loopx/loopx/control_plane/quota/recent_runs.py` | spec (constante) | `MONITOR_DEBT_UNCHANGED_TURN_THRESHOLD = 2` — seuil canonique du stall detector |

## Exclusions conscientes
- `references/loopx/apps/`, `examples/`, `regression/`, `man/`, `docs/` — UI, doc, démos non-portables.
- `references/loopx/loopx/extensions/lark/`, `openviking_*`, `extensions/bundled.py` — écosystème spécifique (Feishu/Lark, plugins provider) : bruit pur pour le projet cible.
- `references/loopx/loopx/cli_commands/`, `loopx/cli.py`, `codex_cli_*.py`, `opencode_goal_mode/`, `claude_goal_*.py` — CLI et adaptateurs de runtimes externes (Codex/Claude/Cursor). Non pertinents sauf si on intègre ces runtimes.
- `references/loopx/loopx/benchmarks/`, `benchmark_adapters/`, `terminal_bench*` — infrastructure de benchmark (6000+ lignes) : hors-scope massif.
- `references/loopx/packages/loopx-finance-value-discovery` — pack métier finance.
- `references/loopx/loopx/control_plane/handoff/`, `work_items/operator_inbox.py`, `capabilities/*` — intéressants conceptuellement (handoff multi-agent, queues d'attention) mais profondément liés au modèle loopx (goals/todos/operator gate) ; à n'extraire que si on veut répliquer le modèle Kanban complet.
- `references/loopx/loopx/control_plane/quota/quota.py` (2784 L) — monolithique et trop lié au `status_payload` loopx. À ne pas porter tel quel ; les sous-modules `control_plane/quota/*` ci-dessus sont la version modulaire exploitable.

## Correspondance avec `plan_usine_logicielle.md`
- **P3 (Anti-loop)** : `recent_runs.py` (stall detector déterministe, seuil=2, ignore bookkeeping) + `pr_monitor_materialization.py` (`result_hash`/`material_change`/`consecutive_no_change` — le pattern de hash d'output que notre F-36 LoopGuard n'a pas) + `delivery_outcome.py` (enum accountable/progress/idle pour classifier chaque itération) + `transaction.py` (`NO_SPEND_RESULT_KINDS`/`STOP_RESULT_KINDS` pour distinguer turns productifs vs gratuits). Apporte la **matière déterministe** qui manquait à crush (10, hash seul).
- **P9 (Reducers / Compaction)** : `run_compaction.py` + `run_context_retention.py` (whitelist de champs par type de payload + rétention du dernier contexte durable par agent). Complète qm (14, compaction sémantique token-aware) et learn-claude-code s08 (16, 4 couches) avec une approche **structurelle par champs** — utile comme première couche cheap avant le résumé LLM coûteux.
- **P11 (Event stream)** : `event_sourced_state.py` (`AppendOnlyStateEventStore` idempotent, fingerprint, checksum, conflict detection, projection rebuild) + `event_ledger.py` (classification 5 classes, fenêtres 24h/7d) + `transaction.py` (turn transaction ordonné). Apporte l'**idempotence de l'event stream** + la **classification** que deer-flow (08/13, contrat JSON) et learn-claude-code s04 (16, hookpoint) n'ont pas.
