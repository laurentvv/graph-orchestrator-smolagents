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

Pour notre projet (orchestrateur Python/DuckDB), bien que l'implémentation soit en TypeScript, les architectures conceptuelles de `SkillExtractor` (séparation stricte transcript/instruction via tags non-naturels), de `SqliteSkillStore` (multiversioning, is_head) et d'interfaces agnostiques sont d'excellents blueprints. La valeur est 🟡 Moyenne (car non Python), voire 🟢 Haute sur la doctrine Skill et l'extraction.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/TencentDB-Agent-Memory/README.md` | Concepts L0-L3 et "Memory Assets". Doctrine "One Agent Team: Shared Experience". | medium |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/skill/skill-store.ts` | `SqliteSkillStore`, `appendVersion`, `archiveHead` | Stockage SQLite pour skills avec multi-versioning (is_head=1). | medium | Modèle direct pour la persistance DuckDB des skills. |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/skill/skill-extractor.ts` | `SkillExtractor`, `formatTranscript`, `truncateHeadTail` | Extraction de skills. Utilise des tags `<<past-user>>` pour isoler le transcript et éviter l'hallucination LLM. | high | Pattern anti-hallucination critique (role isolation) transposable au pipeline Python. |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/types.ts` | `LLMRunner`, `RuntimeContext`, `TraceContext` | Interfaces agnostiques isolant le Core du Host. | medium | Bonne inspiration d'architecture pour le découplage. |
| `references/TencentDB-Agent-Memory/MemoryCore/src/core/conversation/l0-recorder.ts` | `L0MessageRecord`, `L0ConversationRecord` | Structure d'enregistrement brut des conversations (L0). | medium | Format d'idempotence et journalisation. |

## Exclusions conscientes
- `MemoryPanel/` et `MemoryProxy/` : UI React/TypeScript et backend hors-scope pour l'orchestrateur local CLI/Tauri.
- Les plugins spécifiques à Hermes et OpenClaw.

## Correspondance avec `plan_usine_logicielle.md`
- **P9** : Doctrine d'extraction sémantique (L0-L3) et structuration d'un système de mémoire.
- **P10** : Modèle de skill store multi-versionné et d'extraction de skills.
