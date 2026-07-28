# Agent Graph Architecture with Smolagents & Asyncio

Ce dépôt implémente une architecture de **Graph Engineering** pour agents IA en utilisant le framework [`smolagents`](https://github.com/huggingface/smolagents) et `asyncio`.

Le but de cette architecture est de sortir d'une exécution IA linéaire basique (souvent fragile) pour aller vers un modèle distribué, parallèle et vérifiable (pattern *Fan-out -> Reduce -> Adversaire -> Synth*).

> 📖 Ce projet implémente le [Guide de Standardisation : Architecture de Systèmes Agentiques en Graphes](docs/guide-graphes.md). Le manifeste y est archivé avec un mappage d'écart concept ↔ implémentation.

## Fonctionnalités clés

1. **Topologie Diamant (§3)** : *Fan-out → Reduce → Adversaire → (HITL) → Synth*
   - **Fan-out** : les tâches indépendantes sont distribuées en asynchrone via `asyncio.gather()`, chaque tâche gérée par son propre agent (stateless).
   - **Reduce** : nœud de code pur (`flatten + dedupe + filter`) — 0 token, isole les échecs.
2. **Vérification Adversaire (§5)** :
   - Une **flotte de N "sceptiques"** indépendants tourne en parallèle pour tenter de réfuter chaque résultat (personas divergents : hallucinations, contre-sens, omissions…).
   - Vote à la majorité : une tâche est rejetée si `>= threshold × N` sceptiques la réfutent. *« La confiance naît de l'examen contradictoire »*.
3. **Cycles de Convergence loop-until-dry (§5)** :
   - Mode `exploration` : le graphe boucle tant que de nouveaux insights émergent, avec **3 garanties anti-boucle-infinie** (hard cap, critère "dry", dédup contre le déjà-vu **y compris les rejets**).
4. **Human-in-the-loop (§5)** :
   - Checkpoint bloquant optionnel (`HITL_ENABLED=true`) avant la synthèse, pour les points à haut risque.
5. **Contrats de Données Stricts (Pydantic)** :
   - Chaque nœud a une entrée/sortie strictement typées. **Retry automatique** si le LLM échoue à générer un JSON valide.
6. **Tiering des Modèles (§4)** :
   - Fan-out sur modèle léger (`qwen3.5:2b`), raisonnement (adversaire + synthèse) sur modèle costaud (`hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL`).

   > ⚠️ **Contrainte tool-calling** : `smolagents.ToolCallingAgent` s'appuie sur le *function-calling* natif de l'API. Tous les modèles ne le supportent pas correctement via Ollama (`lfm2.5` finit en `finish_reason: length` sans `tool_calls`). Les deux modèles ci-dessus ont été testés et validés via `/v1/chat/completions`. Le `max_tokens=8192` sur le modèle de raisonnement est **obligatoire** pour Gemma (sinon il n'émet jamais son `tool_call`).
7. **Configuration externalisée & Observabilité** :
   - Tous les paramètres sont surchargeables via `.env` (voir [`.env.example`](.env.example)). Une table récapitulative (tokens in/out, durée par nœud) est affichée en fin de run.

## Pré-requis

- Python 3.12+
- [Ollama](https://ollama.com/) installé et en cours d'exécution localement.
- [uv](https://github.com/astral-sh/uv) installé pour la gestion rapide des dépendances.

## Installation

Ce projet utilise `uv` pour gérer les dépendances et l'environnement virtuel.

```bash
# 1. Télécharger les modèles via Ollama (s'assurer qu'Ollama tourne)
#    - Fan-out (léger) :
ollama pull qwen3.5:2b
#    - Adversaire + Synthèse (raisonnement) :
ollama pull hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL

# 2. Synchroniser les dépendances Python via uv (inclut le groupe dev : pytest)
uv sync

# 3. (Optionnel) Copier le template de configuration
cp .env.example .env
```

## Utilisation

Assurez-vous que le serveur Ollama tourne en arrière-plan (`ollama serve`).

### Mode one-shot (défaut) : Fan-out → Reduce → Adversaire → Synth

```bash
uv run agent_graph.py
```

### Mode exploration : loop-until-dry (§5)

Le mode exploration boucle tant que de nouveaux insights émergent. On l'active via `WORKFLOW_MODE` ou directement :

```bash
# Via le module workflows (définit sur WORKFLOW_MODE=exploration dans .env)
WORKFLOW_MODE=exploration uv run python -m graph_orchestrator.workflows
```

### Tests

Les tests unitaires (schémas, extraction JSON, vote adversaire, terminaison des cycles, config) ne font **aucun appel LLM** et tournent en <1s :

```bash
uv run pytest tests/ -v   # 57 tests, <1s, aucun appel LLM
```

## Exemple de sortie

À la fin de chaque run, le graphe affiche les verdicts adversaires par tâche puis une **table d'observabilité** (tokens et durée par nœud) :

```
[+] Verdict adversaire : Vote adversaire : 3/3 approuvées.
    ✓ t1 — 0/3 réfutations (sous le seuil 0.5).
    ✓ t2 — 0/3 réfutations (sous le seuil 0.5).
    ✓ t3 — 0/3 réfutations (sous le seuil 0.5).

┌───────────┬────────────────┬────────┬─────────────────┬────────┐
│ Nœud      │ Modèle         │  Durée │ Tokens (in/out) │  Total │
├───────────┼────────────────┼────────┼─────────────────┼────────┤
│ worker_t1 │ qwen3.5        │  38.0s │     1 274 / 648 │  1 922 │
│ worker_t2 │ qwen3.5        │  56.0s │   6 422 / 1 905 │  8 327 │
│ worker_t3 │ qwen3.5        │  31.4s │     1 270 / 538 │  1 808 │
│ skeptic_0 │ gemma-4-E4B-it │  71.5s │     1 393 / 760 │  2 153 │
│ skeptic_1 │ gemma-4-E4B-it │  80.7s │   3 036 / 1 906 │  4 942 │
│ skeptic_2 │ gemma-4-E4B-it │  34.2s │     1 392 / 921 │  2 313 │
│ synth     │ gemma-4-E4B-it │  29.3s │   2 457 / 1 538 │  3 995 │
│ TOTAL     │                │ 341.1s │                 │ 25 460 │
└───────────┴────────────────┴────────┴─────────────────┴────────┘
```

> 💡 **Coût de la fiabilité** : la flotte de N sceptiques multiplie le coût de la vérification (~13k → ~25k tokens pour 3 sceptiques). C'est le trade-off assumé du §5 du guide (« la confiance naît de l'examen contradictoire »). Il se pilote via `ADVERSARY_COUNT`.

## Configuration

Tous les paramètres sont optionnels (des valeurs par défaut s'appliquent) et surchargeables via des variables d'environnement ou un fichier `.env` :

| Variable | Défaut | Rôle |
|----------|--------|------|
| `OLLAMA_API_BASE` | `http://localhost:11434/v1` | endpoint OpenAI-compatible (le `/v1` est ajouté auto si manquant) |
| `OLLAMA_API_KEY` | `sk-local` | clé (factice locale) |
| `FAST_MODEL_ID` | `qwen3.5:2b` | Fan-out (workers) |
| `REASONING_MODEL_ID` | `hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL` | Adversaire + Synthèse |
| `REASONING_MAX_TOKENS` | `8192` | obligatoire pour Gemma |
| `JUDGE_CONFIDENCE_THRESHOLD` | `0.7` | seuil de confiance du worker |
| `WORKER_MAX_RETRIES` | `3` | tentatives de parsing JSON |
| `ADVERSARY_COUNT` | `3` | nombre de sceptiques (vérification adversaire) |
| `ADVERSARY_THRESHOLD` | `0.5` | fraction de sceptiques requise pour réfuter |
| `MAX_ITERATIONS` | `3` | hard cap du mode exploration (anti-boucle) |
| `HITL_ENABLED` | `false` | checkpoint humain bloquant avant synthèse |
| `WORKFLOW_MODE` | `one_shot` | `one_shot` ou `exploration` |
| `LOG_LEVEL` | `LOW` | verbosité workers (`LOW`/`MEDIUM`/`HIGH`) |

## Structure du projet

```
agent_graph.py                 ← entry point one-shot (uv run agent_graph.py)
graph_orchestrator/
  __init__.py                  ← exports publics du package
  config.py                    ← chargement config (.env + defaults)
  models.py                    ← contrats Pydantic + extraction JSON robuste
  logging_utils.py             ← verbosité + table d'observabilité rich
  nodes.py                     ← nœuds worker / reduce / adversaire / synth / hitl + retry
  runner.py                    ← orchestration one-shot async + récap + main()
  workflows.py                 ← mode exploration (loop-until-dry) + sample tasks
docs/
  guide-graphes.md             ← manifeste de référence (§1-6) + mappage d'écart
.env.example                   ← template de configuration
tests/
  test_models.py               ← validation des schémas Pydantic
  test_extract.py              ← robustesse de l'extraction JSON
  test_judge_logic.py          ← logique de filtrage approuvés/rejetés
  test_config.py               ← defaults + override par env
  test_reduce.py               ← nœud Reduce (flatten+dedupe+filter)
  test_adversary.py            ← vote adversaire (table de vérité)
  test_cycles.py               ← terminaison loop-until-dry + dédup déjà-vu
```

## Structure du Graphe

1. **`execute_worker_node`** : Prend une tâche brute, l'analyse et retourne un `WorkerOutput`. Exécuté en parallèle via `asyncio.gather`.
2. **`execute_reduce_node`** : Déduplique (sur `task_id`) et filtre les `None`/doublons. Code pur, 0 token.
3. **`execute_adversary_node`** : Lance N sceptiques en parallèle (personas divergents) qui votent pour réfuter/approuver chaque tâche.
4. **`hitl_checkpoint`** *(optionnel)* : approbation humaine bloquante avant la synthèse.
5. **`execute_synth_node`** : Rédige le `FinalSynthesis` à partir des données approuvées.

```
        ┌── worker_t1 ──┐
tasks ──┼── worker_t2 ──┼──→ Reduce ──→ Adversaires (N sceptiques) ──→ [HITL] ──→ Synth
        └── worker_t3 ──┘   (dedup)      (vote majorité)                        │
                                                                                ▼
                                                                         FinalSynthesis
```

En mode `exploration`, ce graphe est encapsulé dans une boucle loop-until-dry avec déduplication du déjà-vu.
