# Plan d'implémentation — F-18 (réouverture) : Nœud Feeder AIFeeder

> **Statut** : plan approuvé pour implémentation (en attente de feu vert GO).
> **Date** : 2026-08-22 · **Branche prévue** : `feat/f-18-feeder-node`
> **Décideur** : utilisateur. **Rédacteur** : assistant ZCode.

---

## 0. Décisions actées (utilisateur, session 2026-08-22)

| # | Décision |
|---|----------|
| D1 | **Nœud dans le graphe** — la recherche de référence se fait naturellement pendant le run, SANS intervention humaine (pas de `.md` copié à la main dans `tasks.json`). |
| D2 | **AIFeeder cherche des mots-clés** — le nœud fournit des keywords au pipeline, pas une spec complète. |
| D3 | **Le Coder reçoit le `.md` du pack dans son prompt de départ**, exactement comme le draft aujourd'hui (pattern de pré-injection F-149 `draft_instruction`). |
| D4 | **Intégration = paquet uv** (`aifeeder` ajouté aux dépendances du projet), pas un appel subprocess à la CLI d'un repo externe. |
| D5 | **Modèles copiés** depuis `D:\GIT\AIFeeder\models` vers `models/` du graphe, chemins référencés dans `.env`. |

F-18 (« Nœud dédié recherche web », annulé 2026-08-18) est **rouvert et rescopé** : l'architecture
change (pipeline externe éprouvé appelé en library), le nom historique reste.

---

## 1. Objectif & périmètre

Avant l'Architect, un nœud déterministe (0 LLM côté graphe) interroge le pipeline AIFeeder
(recherche web multi-moteurs → crawl → extraction code → élection d'un champion par LLM local)
et produit un **pack de référence** `.md` unique. Ce pack est pré-injecté dans le prompt de départ
du Coder pour l'aider à produire du code solide dès l'itération 1 (leçon du golden run #19 :
un contexte sain vaut mieux que des corrections aval).

**Dans le périmètre** : nœud Feeder, injection prompt Coder, config, tests, isolation, état disque.
**Hors périmètre** : modification d'AIFeeder (consommé tel quel), injection dans les prompts
Architect/Drafter/Tester (éventuel cycle ultérieur), gating par difficulté (v. §6-R7).

---

## 2. Architecture cible

### 2.1 Placement dans le workflow coding

```
run_coding_workflow (workflows.py)
 │
 ├─ [1] 🆕 NŒUD FEEDER (F-18)            ← AVANT PromptRefiner/Router : GPU libre,
 │      mots-clés (spec BRUTE)              zéro contention VRAM avec les serveurs du graphe
 │      → llama-server LFM 1.2B (aifeeder)
 │      → pack run_output_dir/feeder/*.md
 │
 ├─ [2] PromptRefiner (F-39)
 ├─ [3] Router
 ├─ [4] Recall leçons cross-run (F-68)     ← pattern d'inspiration : bloc calculé UNE fois
 ├─ [5] Architect → Drafter → Coder …      ← sub_dict["reference_pack"] injecté à CHAQUE
 │                                            sous-tâche/itération (comme "lessons")
```

**Pourquoi avant PromptRefiner** : (a) les mots-clés se satisfont de la spec brute (le raffiné
n'apporte rien à une requête de 5 mots) ; (b) le llama-server LFM (~1,4 Go VRAM en Q8_0) tourne
et meurt AVANT tout spawn graphé → aucune contention ; (c) la reprise par checkpoint (le
PromptRefiner est skippé) n'affecte pas le feeder, qui a son propre mécanisme de reprise (§4-V4).

### 2.2 Flux de données

```
seed_tasks[0]['content'] (spec brute)
        │  extract_keywords()           [déterministe, V3]
        ▼
List[str] queries  ──▶ aifeeder.run_pipeline(queries, settings)     [async, in-process]
        │                    │
        │                    ├─ LlamaServerRunner (binaire du GRAPHE, port dédié)
        │                    ├─ search_multiple_queries (websearch-py)
        │                    ├─ crawl + parse_and_export_code (crawl4ai)
        │                    └─ pick_champion + deep blueprint (LLM local)
        ▼
PipelineResult.pack_file_path ──▶ clip éventuel ──▶ build_reference_block()
        │
        ▼
sub_dict["reference_pack"] ──▶ prompt Coder (nodes.py, à côté de draft_instruction)
```

---

## 3. Constats d'exploration (vérifiés le 2026-08-22)

1. **Compatibilité Python** : graphe `requires-python >= 3.14` (env 3.14.0), aifeeder
   `requires-python >= 3.14`. ✅ Aucun obstacle.
2. **API in-process propre** : `aifeeder.pipeline.run_pipeline(queries, settings, skip_llm,
   extract_code, keep_raw, concurrency) -> PipelineResult` (async) ; `PipelineResult.pack_file_path`
   pointe le pack unique généré. Pas besoin de parser la sortie CLI.
3. **Config pydantic programmatique** : `aifeeder.config.Settings` (SearchConfig, CrawlConfig,
   LLMConfig, LlamaServerConfig) — constructible en Python pur. **On ne dépend JAMAIS du .env
   d'aifeeder** → zéro collision avec les clés du graphe (le `.env` du graphe a déjà
   `LLM_TIMEOUT_S`, `LLM_RETRY_*`, proches des clés aifeeder `LLM_BASE_URL`, `LLM_MODEL`…).
4. **Cycle de vie llama-server inclus** : `LlamaServerRunner` (start/wait_ready/stop + context
   manager). Le binaire est résolu par `find_llama_server_binary()` (ses propres dossiers puis
   PATH) — le graphe bundle le sien dans `bin/llamacpp-cuda13/` avec résolution maison
   (`llama_server.py`, priorité bundle CUDA > PATH). À relier (V3).
5. **Modèles présents** dans `D:\GIT\AIFeeder\models` : `LFM2.5-1.2B-Instruct-Q8_0.gguf`
   (1,25 Go) + `LFM2.5-8B-A1B-DSpark-Draft-v1-F16.gguf` (0,66 Go, draft du 8B).
   ⚠️ Le modèle 8B principal (`LFM2.5-8B-A1B-F16.gguf`, ~16 Go) n'est PAS présent localement.
   → **Choix par défaut : 1.2B Q8** (rapide ~190 tok/s, léger). Le draft DSpark ne sert QU'AVEC
   le 8B (option futur : `uv run aifeeder download-model 8b-q4`).
6. **Empreinte du pack Tetris réel** : 18 889 caractères ≈ 4,7k tokens — compatible avec le
   budget prompt Coder (prefill compaction F-116 déclenche à ~26k tokens).
7. **Dépendances tirées** : `crawl4ai-mcp-llm` (fork crawl4ai maison, lourd : playwright…),
   `websearch-py` (maison), `openai`, `typer`, `rich`, `httpx`, `pydantic`. Vérifier leur
   disponibilité PyPI vs git+ lors du `uv add` (V1).
8. **Ancrage injection** : prompt Coder construit dans `nodes.py` (~l.1468-1530) ; le placeholder
   `{task.get('draft_instruction', '')}` (l.1520) est le modèle exact à suivre pour
   `{task.get('reference_pack', '')}`.
9. **Pattern d'injection par sous-tâche** : `lessons_block` calculé UNE fois avant la boucle
   (workflows.py ~l.595-609), injecté dans chaque `sub_dict` (l.789) — même approche pour le pack.

---

## 4. Volets d'implémentation

### V1 — Dépendance uv (D4)

```bash
uv add "aifeeder @ git+https://github.com/laurentvv/AIFeeder"
# repli si sous-dépendances maison absentes de PyPI :
#   uv add "websearch-py @ git+https://github.com/laurentvv/websearch-py" \
#          "crawl4ai-mcp-llm @ git+https://github.com/laurentvv/crawl4ai-mcp-llm"
# variante dev itérative : uv add --editable D:/GIT/AIFeeder
```

- Vérifier `uv lock` + `uv sync` sans conflit de versions (pydantic/openai déjà présents côté
  graphe) ; lancer `pytest -q` (baseline 1757 passed) pour garantir 0 régression d'install.
- `pyproject.toml` : la dépendance entre dans `[project.dependencies]` (commitée).

### V2 — Modèles & binaire (D5)

- Copie : `D:\GIT\AIFeeder\models\LFM2.5-1.2B-Instruct-Q8_0.gguf` et
  `LFM2.5-8B-A1B-DSpark-Draft-v1-F16.gguf` → `models/lmf2.5/` (convention dossiers par famille,
  comme `ornith-1.0`, `qwen35-4b-mtp`). Gitignorés (comme les autres GGUF).
- `.env` + `.env.example` : `AIFEEDER_MODEL_PATH=models/lmf2.5/LFM2.5-1.2B-Instruct-Q8_0.gguf`,
  `AIFEEDER_DRAFT_MODEL_PATH=` (vide = spéculatif désactivé ; ne se branche QUE sur le 8B).
- Binaire llama-server : résolution via le mécanisme DU GRAPHE (bundle `bin/llamacpp-cuda13`
  prioritaire, cf. `docs/LLAMA_SERVER_FLAGS.md`), passé à `LlamaServerConfig` si champ exposé,
  sinon exiger le PATH. Interdiction de télécharger un 2e binaire.

### V3 — Module `graph_orchestrator/feeder.py` (0 LLM, cœur du nœud)

API publique :

```python
@dataclass
class FeederResult:
    ok: bool
    pack_path: Path | None      # pack intégral sur disque (traçabilité)
    reference_block: str        # bloc markdown CLIPPÉ prêt à injecter au Coder
    queries: list[str]
    duration_s: float
    error: str | None           # None si ok

def extract_keywords(spec: str, target_files: list[str]) -> list[str]:
    # Déterministe. Priorité :
    #   1. champ tâche "reference_query" (tasks.json) — contrôle explicite
    #   2. settings.aifeeder_query (config .env) — override global
    #   3. AUTO : 1re phrase de la spec brute (≤ 90 chars) + suffixe techno
    #      déduit des extensions de target_files (html+css+js → "html css js vanilla")

async def run_feeder(spec, target_files, output_dir, settings) -> FeederResult:
    # 1. keywords → queries (max 2 variantes pour search_multiple_queries)
    # 2. REPRISE : si output_dir/feeder/*.md existe déjà → réutilise le plus récent
    #    (crash-safe, pas de re-search ; FRESH_START => nouveau run dir => nouveau pack)
    # 3. Settings aifeeder CONSTRUITS EN PUR PYTHON (zéro .env aifeeder) :
    #    search.max_results, crawl.output_dir=<run_dir>/feeder, llm.base_url=<port dédié>
    # 4. LlamaServerRunner en context manager (modèle V2, ngl 99, port AIFEEDER_LLAMA_PORT)
    # 5. await asyncio.wait_for(run_pipeline(...), timeout=AIFEEDER_TIMEOUT_S)
    # 6. clip + build_reference_block
    # 7. FAIL-OPEN TOTAL : toute exception/timeout/absence de pack → FeederResult(ok=False)
    #    JAMAIS d'exception remontante (le run continue sans pack, log + événement DuckDB)

def clip_pack(content: str, max_chars: int) -> str:
    # ≤ max_chars → intégral. Sinon : garder l'EN-TÊTE (rationale, blueprint, gotchas,
    # checklist) + tronquer la SECTION CODE au milieu + note
    # "[champion code truncated — full pack: <run_dir>/feeder/<file>]"

def build_reference_block(pack_markdown: str, pack_path: Path) -> str:
    # Encapsule dans le bloc injecté au Coder (v. V5 pour le texte exact des consignes)
```

Points de vigilance : `run_pipeline` écrit son staging dans `data/.tmp_staging` **relatif au
CWD** → l'appeler AVANT `_scoped_chdir(run_output_dir)` OU passer par un `os.chdir` temporaire ;
le pack destination est `crawl.output_dir` résolu → pointer `run_output_dir/feeder`.

### V4 — Câblage `workflows.py` (nœud)

- Insertion dans `run_coding_workflow` juste après `_resolve_run_output_dir`/`makedirs`
  (l.488-489) et AVANT `_scoped_chdir` (l.515) — le feeder travaille en chemins absolus.
- Gating : `if settings.aifeeder_enabled and seed_tasks:` + skip silencieux si pack réutilisé.
- Sortie : `reference_block` stocké côté workflow ; injecté dans chaque `sub_dict` au même
  endroit que `"lessons": lessons_block` (l.789) sous la clé `"reference_pack"`.
- Observabilité : print `[*] Feeder : pack <name> (N mots-clés, X s, Y sources)` ou
  `[-] Feeder : échec (<erreur>) — run sans pack` ; événement DuckDB (`node="feeder"`,
  `event_type="pack"` / `"fail"`) via le helper existant du workflow.
- Aucune métrique NodeMetrics LLM (le LLM appartient à aifeeder, pas au graphe).

### V5 — Injection prompt Coder (`nodes.py`, pattern F-149)

Dans le template du prompt Coder, immédiatement APRÈS `{task.get('draft_instruction', '')}`
(l.1520) :

```
{task.get('reference_pack', '')}
```

`build_reference_block()` produit (anglais, cohérent F-150) :

```
### 📚 REFERENCE IMPLEMENTATION PACK (web research — ALREADY IN CONTEXT, NO read_file)
A scout pipeline found this VERIFIED reference implementation for your task:
```markdown
<pack clippé>
```
INSTRUCTIONS: This is REFERENCE MATERIAL, not a deliverable template.
- ADAPT the algorithms/architecture to the task spec above — the SPEC WINS on any conflict.
- Write YOUR OWN files matching the EXACT target_files names (the pack may use different names).
- Do NOT copy verbatim: skip analytics/tracking scripts, debug console.log leftovers,
  and any feature absent from the spec.
```

(les 3 défauts constatés sur le pack Tetris réel — nommage `app.js`/`tetris.js` incohérent,
`console.log` résiduel, scripts Vercel Analytics — sont précisément ce que ces consignes neutralisent.)

### V6 — Config (`config.py` + `.env` + `.env.example`)

| Clé | Défaut | Rôle |
|---|---|---|
| `AIFEEDER_ENABLED` | `true` | gate globale du nœud |
| `AIFEEDER_QUERY` | *(vide)* | override global des mots-clés (sinon auto/champ tâche) |
| `AIFEEDER_TIMEOUT_S` | `600` | timeout global du pipeline (asyncio.wait_for) |
| `AIFEEDER_MAX_RESULTS` | `8` | candidats cherchés |
| `AIFEEDER_CONCURRENCY` | `3` | crawls parallèles |
| `AIFEEDER_MODEL_PATH` | `models/lmf2.5/LFM2.5-1.2B-Instruct-Q8_0.gguf` | GGUF champion-evaluator |
| `AIFEEDER_DRAFT_MODEL_PATH` | *(vide)* | spéculatif — 8B uniquement |
| `AIFEEDER_LLAMA_PORT` | `8090` | port dédié (8080 = external backend possible) |
| `AIFEEDER_PACK_MAX_CHARS` | `20000` | budget du bloc injecté (~5k tokens) |

Reporter chaque ajout `.env.example` dans `.env` local (règle §7 AGENTS.md). Champ tâche
optionnel `reference_query` dans `tasks.json` (documenté dans le README du plan de test).

### V7 — Tests `tests/test_feeder.py` (0 LLM, `run_pipeline` mocké)

1. `extract_keywords` : priorité champ tâche > config > auto ; suffixe techno depuis
   target_files ; spec vide/vide de sens → requête minimale.
2. Fail-open : timeout levé, exception pipeline, pack absent, modèle absent, aifeeder désactivé
   → `ok=False`, AUCUNE exception.
3. Reprise : pack existant dans `<run>/feeder/` → réutilisé sans appel pipeline (mock non appelé).
4. `clip_pack` : intégral sous seuil ; troncature conserve l'en-tête + note pointant le fichier.
5. `build_reference_block` : consignes ADAPT/spec-wins présentes.
6. Câblage workflow : `sub_dict["reference_pack"]` rempli quand ok, absent/vide sinon ;
   le prompt Coder rendu contient le bloc (test template nodes.py, pattern existent).
7. Config : défauts + lecture env.
8. Gate F-103 (`scripts/check_agent_guidance.py`) : 29→30 surfaces attendues (nodes.py
   modifié), 0 erreur/0 warning.
9. Suite complète : 0 régression vs baseline.

### V8 — Script d'isolation `debug/run_feeder.py` (convention F-89)

Appelle le VRAI pipeline (spécifications Prompt-Vault en entrée CLI, ex. `uv run python
debug/run_feeder.py @references/Prompt-Vault/Hard/Tetris_Modern_Game/prompt.md`) : mots-clés
extraits → pack généré → aperçu du bloc injecté + statistiques (durée, candidats, champion,
tokens estimés). C'est la boucle de validation AVANT tout E2E.

### V9 — État disque & gouvernance

- `feature_list.json` : F-18 `cancelled → in_progress` (description rescopée : « Nœud Feeder :
  appel in-process du pipeline AIFeeder (dépendance uv), mots-clés déterministes, pack champion
  pré-injecté au Coder (pattern F-149), fail-open total ») puis `completed` en fin de cycle.
- `contract.md` : critères **C488-C494** (7 assertions : nœud avant PromptRefiner ; pack dans
  run dir ; bloc présent au prompt Coder it.1 ; fail-open timeout ; reprise sans re-search ;
  gate F-103 passée ; isolation script OK).
- `progress.md` : objectif courant + jalons F18-1…F18-6.
- `README.md` : § nœuds (Feeder avant PromptRefiner) + prérequis modèles LFM.
- DuckDB (`scripts/log_event.py`) : décision de réouverture F-18, jalons, bilan.

---

## 5. Validation

1. **Isolation** (V8) : mots-clés justes sur 2-3 prompts Prompt-Vault (Bubble Sort, Tetris) ;
   pack complet produit en < 10 min ; bloc injecté conforme.
2. **E2E Tetris** (= validation F145-6 en même temps) : `WORKFLOW_MODE=coding`, prompt
   Prompt-Vault Tetris, `uv run agent_graph.py`. Critères : le log montre le nœud Feeder
   (mots-clés, champion, durée) ; le pack est dans `runs/<dated>/feeder/` ; le Coder produit
   un livrable fonctionnel AVEC animation réelle (règle 5-bis preuve de mouvement) ; pas de
   croissance anormale du contexte (le pack ~5k tokens est compté une fois par prompt).
3. **Négatif** : `AIFEEDER_ENABLED=false` → run identique à aujourd'hui, aucune trace feeder.

---

## 6. Risques & mitigations

| # | Risque | Mitigation |
|---|---|---|
| R1 | Sous-dépendances maison (websearch-py, crawl4ai-mcp-llm) absentes de PyPI | sources git+ explicites dans `uv add` (V1) |
| R2 | Empreinte crawl4ai (playwright…) alourdit le venv / conflits de versions | `uv lock` scruté + pytest baseline post-sync |
| R3 | Réseau lent/bloqué (crawl multi-minutes) | timeout global 600 s + fail-open (le run ne meurt JAMAIS du réseau) |
| R4 | Contention VRAM/GPU avec les serveurs du graphe | feeder AVANT PromptRefiner + LlamaServerRunner.stop() garanti (context manager) + modèle 1,2B |
| R5 | Port 8080 occupé | port dédié `AIFEEDER_LLAMA_PORT=8090` configurable |
| R6 | Pack trop gros / pollue le budget Coder | clip 20 000 chars + pack intégral archivé dans le run dir |
| R7 | Crawl inutile sur tâches triviales (Bubble Sort) | champ `reference_query` vide + futur : gating difficulté (cycle ultérieur, pas bloquant) |
| R8 | Dérive de qualité web (champion pourri) | consignes ADAPT du bloc V5 + gardes aval inchangées (Static Tester, sondes) restent l'autorité |
| R9 | Reproductibilité des runs réduite (web change) | pack archivé par run = preuve de ce qui a été injecté |
| R10 | `run_pipeline` écrit en CWD relatif (staging `data/.tmp_staging`) | appeler hors `_scoped_chdir` ou chdir borné le temps de l'appel (V3) |

---

## 7. Livraison

1. Branche `feat/f-18-feeder-node` depuis `main` (règle d'or §6 AGENTS.md).
2. Commits par volet logique (V1-V2 dépendances/modèles ; V3-V5 code ; V6 config ; V7-V8
   tests/isolation ; V9 état disque).
3. PR → review Kilo Code → ARRÊT jusqu'au feu vert (convention repo).
4. Après merge : run E2E Tetris (§5.2) pour valider F-18 ET F145-6 d'un coup.
