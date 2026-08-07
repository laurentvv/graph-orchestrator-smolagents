# 28 — TencentDB-Agent-Memory

## En-tête
- **Nom** : TencentDB-Agent-Memory
- **Chemin** : `references/TencentDB-Agent-Memory/`
- **Type** : Framework de mémoire / Asset Hub pour agents
- **Langage principal** : TypeScript (Node.js)
- **Statistiques** : ~836 fichiers (majoritairement `.ts`, `.tsx`, `.md`).

## Synthèse
TencentDB-Agent-Memory est un système avancé de gestion de mémoire pour agents LLM, structuré en couches d'abstraction sémantique (L0 Conversation, L1 Atom, L2 Scenario, L3 Persona). Il propose une séparation très claire entre un Memory Core (extraction/stockage), un Memory Hub (panel de contrôle humain) et un Proxy pour l'interfaçage.

Sa proposition de valeur principale réside dans le concept de "Memory Assets" : Chat Memory, Skills, Wiki, et CodeGraph. L'expérience n'est pas qu'un log de chat, mais des entités partageables et assignables à des agents spécifiques avec un système ACL (private, team, restricted).

### Gisement de prompts/méthodologie (audit approfondi 2026-08-07)
L'audit initial (superficiel) n'avait retenu que 4 briques (skill-store `is_head`, skill-extractor `<<past-user>>`, types, l0-recorder). L'exploration approfondie des **prompts** révèle un second gisement, plus valuable pour nous : **7 modules de prompts TypeScript** implémentant une méthodologie de mémoire complète et éprouvée. Tous les prompts sont stockés comme constantes string exportées (pas de fichiers `.txt` séparés). Plusieurs concepts n'apparaissent dans **aucune** autre référence auditée et sont **supérieurs** aux équivalents cités dans notre P6-ter (qui ne référence que qm) :

- **Pipeline mémoire L0→L3** avec extraction (`l1-extraction.ts`), dédup/conflict (`l1-dedup.ts`), consolidation narrative (`scene-extraction.ts`), persona incrémental (`persona-generation.ts`).
- **Dualité chat/code** : chaque prompt a une variante "chat" (mémoire personnelle : persona/episodic/instruction) et "code" (mémoire d'équipe partagée : work_fact/work_task/work_method/work_artifact).
- **Oubli par chaleur (heat)** : la consolidation L2 implémente un vrai mécanisme d'oubli/compaction absent de qm (`new=1`, `update=old+1`, `merge=sum+1`, soft-delete `[DELETED]`).
- **Context-offload LLM** : un sous-système séparé (`offload/`) résume les tool-results en graphe Mermaid scoré — complément sémantique à notre `compaction.py` déterministe (P9).
- **Skill Review avec gate formelle** : 5-critères de classification + 4-dim/100pts d'acceptation — va au-delà du pattern `<<past-user>>` seul.

Pour notre projet (orchestrateur Python/DuckDB), bien que l'implémentation soit en TypeScript, ces prompts sont des **blueprints directement transposables** (ce sont des prompts, pas du code runtime). La valeur est 🟡 Moyenne sur l'architecture TypeScript, **🟢 Haute sur la doctrine Skill, le pipeline mémoire L0-L3, l'oubli par chaleur et la gate Skill Review**.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/TencentDB-Agent-Memory/README.md` | Concepts L0-L3 et "Memory Assets". Doctrine "One Agent Team: Shared Experience". Tableau comparatif Chat History vs RAG vs TencentDB. Benchmark PersonaMem (+59%). | medium |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/prompts/l1-extraction.ts` | **Prompt L1** : extraction d'atomes mémoire. Principes clés : 宁缺毋滥 (qualité>quantité), 独立完整 (valide hors-contexte), 归纳合并 (fusion causale). Dual chat/code (3 vs 4 types). | **high** |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/prompts/l1-dedup.ts` | **Prompt dédup L1** : actions `store/skip/update/merge`, merge cross-type + many-to-many (`target_ids`), **bump de priorité sur merge**. Supérieur au `UPDATE/DELETE/ADD` de qm. | **high** |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/prompts/scene-extraction.ts` | **Prompt consolidation L2** : "Memory Consolidation Architect", `maxScenes` cap, warnings red/orange/yellow, MERGE-before-CREATE, **heat = oubli** (new=1/update=old+1/merge=sum+1), soft-delete `[DELETED]`. | **high** |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/prompts/persona-generation.ts` | **Prompt persona L3** : scan 4-couches (Base/Facts→Interest Graph→Interface→Core), budget ≤2000/1200 chars, évolution incrémentale ("Incremental Evolution Protocol"). | medium |
| `references/TencentDB-Agent-Memory/MemoryCore/src/offload/local-llm/prompts/l1-prompt.ts` (+ `offload_server/` jumeau) | **Prompt context-offload L1** : tool-result → résumé JSON scoré 0-10 (3-step : 任务对齐/价值过滤/影响评估). | **high** |
| `references/TencentDB-Agent-Memory/MemoryCore/src/offload/local-llm/prompts/l15-prompt.ts` | **Prompt gatekeeper cycle de tâche** : `taskCompleted`/`isLongTask`/`isContinuation`/`continuationMmdFile`/`newTaskLabel`. | medium |
| `references/TencentDB-Agent-Memory/MemoryCore/src/offload/local-llm/prompts/l2-prompt.ts` | **Prompt graphe Mermaid** : machine à états cognitive, "cognitive tombstones" (`status: blocked` pour culs-de-sac), budget ≤4000 chars, `node_mapping` exhaustif. | **high** |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/skill/prompts/skill-review-prompt.ts` | **Prompt Skill Review Agent** : gate classification 5-critères (Skill vs Memory vs Wiki vs CodeGraph vs Temporal) + gate acceptation 4-dim/100pts (≥72 total, ≥12/dim). Role-isolation `<<past-*>>`. | **high** |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/skill/prompts/skill-listing-prompt.ts` | En-tête/footer/guidance d'injection `<available_skills>` (byte-equal avec Hermes). | medium |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/hooks/auto-recall.ts` | **Recall hybride** : BM25 + vecteur + RRF, caps (count/chars/timeout), **split stable/dynamic** (persona+scène cacheable vs L1 per-turn pour préserver le prompt caching). | **high** |
| `references/TencentDB-Agent-Memory/MemoryProxy/src/injection/injectors/tdai-profile-memory-injector.ts` | **`MEMORY_TOOLS_GUIDE`** : 4 trigger conditions "must-search-before-answering" + règle anti-hallucination "我在记忆里没找到". | high |
| `references/TencentDB-Agent-Memory/MemoryKnowledge/src/engines/wiki/ingest-v2/prompts.ts` | **Prompt ingestion Wiki** (analysis + generation) : protocole FILE-block `<<<FILE path="...">>>`, `[[wikilink]]`, test de granularité. Inspiration Karpathy. | medium |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/skill/skill-store.ts` | `SqliteSkillStore`, `appendVersion`, `archiveHead` | Stockage SQLite pour skills avec multi-versioning (is_head=1). | medium | Modèle direct pour la persistance DuckDB des skills. |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/skill/skill-extractor.ts` | `SkillExtractor`, `formatTranscript`, `truncateHeadTail` | Extraction de skills. Utilise des tags `<<past-user>>` pour isoler le transcript et éviter l'hallucination LLM. | high | Pattern anti-hallucination critique (role isolation) transposable au pipeline Python. |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/types.ts` | `LLMRunner`, `RuntimeContext`, `TraceContext` | Interfaces agnostiques isolant le Core du Host. | medium | Bonne inspiration d'architecture pour le découplage. |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/conversation/l0-recorder.ts` | `L0MessageRecord`, `L0ConversationRecord` | Structure d'enregistrement brut des conversations (L0). | medium | Format d'idempotence et journalisation. |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/prompts/l1-extraction.ts` | `EXTRACT_MEMORIES_SYSTEM_PROMPT`, `EXTRACT_WORK_MEMORIES_SYSTEM_PROMPT`, `getExtractMemoriesSystemPrompt(mode)` | **Prompt L1** segmentation scène + extraction atomes (chat : persona/episodic/instruction ; code : work_fact/task/method/artifact) + scoring priorité. | **high** | Prompt transposable quasi-directement pour F-68 (extraction claims KG). Les 3 principes (qualité>quantité, valide hors-contexte, fusion causale) sont une doctrine d'extraction supérieure. |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/prompts/l1-dedup.ts` | `CONFLICT_DETECTION_SYSTEM_PROMPT`, `WORK_CONFLICT_DETECTION_SYSTEM_PROMPT`, `formatBatchConflictPrompt` | **Prompt dédup L1** : batch compare vs "unified candidate pool", actions `store/skip/update/merge`, merge cross-type + many-to-many, bump priorité sur merge. | **high** | **Supérieur** au `UPDATE/DELETE/ADD` de qm cité en P6-ter : gère les merges many-to-many et l'augmentation de priorité. Contrat d'actions plus riche pour F-68. |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/prompts/scene-extraction.ts` | `buildSceneSystemPrompt(maxScenes)`, `buildWorkSceneSystemPrompt(maxScenes)` | **Prompt consolidation L2** : "Memory Consolidation Architect", cap `maxScenes`, warnings red/orange/yellow, MERGE-before-CREATE, **heat = oubli** (new=1/update=old+1/merge=sum+1), soft-delete `[DELETED]`, sandbox `scene_blocks/`. | **high** | **Mécanisme d'oubli/compaction par chaleur absent de qm et de notre KG** (qui grossit indéfiniment). Comble le gap F-74/F-68 sur le nettoyage. |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/prompts/persona-generation.ts` | `PERSONA_SYSTEM_PROMPT`, `TEAM_MEMORY_SYSTEM_PROMPT`, `buildPersonaPrompt` | **Prompt persona L3** : scan 4-couches (Base/Facts→Interest Graph→Interface→Core), ≤2000/1200 chars, "Incremental Evolution Protocol". | medium | Profil durable cross-run (L3) — actuellement chaque run repart de zéro (P6-ter). |
| `references/TencentDB-Agent-Memory/MemoryCore/src/offload/local-llm/prompts/l1-prompt.ts` (+ `offload_server/prompts/` jumeau) | `L1_SYSTEM_PROMPT` | **Prompt context-offload L1** : tool-result → résumé JSON scoré 0-10 (任务对齐/价值过滤/影响评估), compresse descriptions tool-call ≤150 chars. | **high** | **Complément sémantique à notre `compaction.py`** (P9, déterministe 0 LLM). Le scoring 0-10 + tombstones manquent dans notre compaction. |
| `references/TencentDB-Agent-Memory/MemoryCore/src/offload/local-llm/prompts/l2-prompt.ts` | `L2_SYSTEM_PROMPT` | **Prompt graphe Mermaid L2** : machine à états cognitive, "cognitive tombstones" (`status: blocked`), ≤4000 chars, `node_mapping` exhaustif (1 tool_call = 1 nœud). | **high** | Alternative visuelle au résumé textuel pour P9 — préserve la topologie des tâches. |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/skill/prompts/skill-review-prompt.ts` | `SKILL_REVIEW_PROMPT` | **Prompt Skill Review Agent** : gate 5-critères (Skill/Memory/Wiki/CodeGraph/Temporal) + gate 4-dim/100pts (≥72 total, ≥12/dim) + template SKILL.md canonique. | **high** | Va **au-delà** du pattern `<<past-user>>` seul (déjà capté P10). Objective l'acceptation/rejet des skills générés (F-65, F-80). |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/hooks/auto-recall.ts` | `MEMORY_TOOLS_GUIDE`, `appendSystemContext`, `prependContext` | **Recall hybride** : BM25+vecteur+RRF, caps count/chars/timeout, split stable (persona+scène, cacheable) / dynamic (L1 per-turn). | **high** | Contrat `recall`/cache pour F-68. Le split stable/dynamic préserve le prompt caching — subtilité absente du scratch/notebook qm. |
| `references/TencentDB-Agent-Memory/MemoryProxy/src/injection/injectors/tdai-profile-memory-injector.ts` | `MEMORY_TOOLS_GUIDE` (proxy twin), `renderProfileMemoryBlock` | **4 trigger conditions "must-search-before-answering"** + règle anti-hallucination "我在记忆里没找到" (ne pas inventer si pas trouvé). | high | Doctrine d'injection de mémoire runtime transposable aux prompts de nos nœuds. |

## Exclusions conscientes
- `MemoryPanel/` : UI React/TypeScript hors-scope pour l'orchestrateur local CLI/Tauri. Aucun prompt de raisonnement.
- `MemoryProxy/` : runtime d'injection HTTP pour frameworks tiers (OpenClaw/Hermes/Claude Code). On retient les **blocs de prompt** (`MEMORY_TOOLS_GUIDE`, trigger conditions) comme doctrine, pas l'infra proxy.
- Les plugins spécifiques à Hermes et OpenClaw.
- `hermes-plugin/memory/memory_tencentdb/` (Python `supervisor.py`/`client.py`) : ne contient aucun prompt de raisonnement ( pont plugin uniquement).

## Correspondance avec `plan_usine_logicielle.md`
- **P6-ter** (F-68) : pipeline L0→L3 complet — extraction (`l1-extraction.ts`), dédup `store/skip/update/merge` **supérieure** à qm (`l1-dedup.ts`), consolidation narrative + **oubli par chaleur** (`scene-extraction.ts`), persona L3 4-couches (`persona-generation.ts`). Recall hybride BM25+RRF + split stable/dynamic (`auto-recall.ts`).
- **P9** : context-offload LLM (résumé tool-result scoré + graphe Mermaid ≤4000 chars + cognitive tombstones) — complément sémantique à notre `compaction.py` déterministe.
- **P10** (F-65/F-80) : Skill Review gate 5-critères + 4-dim/100pts (au-delà de l'isolation `<<past-user>>` déjà captée), modèle de skill store multi-versionné `is_head`.
- **P11** : `<available_skills>` listing byte-equal Hermes + doctrine d'injection runtime.
- **Prompts runtime** : 3 transferts de doctrine directement applicables (Coder "独立完整"/valide hors-contexte, Skill Review gate, compaction relevance-score + tombstones).
