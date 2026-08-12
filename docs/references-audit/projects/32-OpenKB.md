# 32 — OpenKB

## En-tête
- **Nom** : openkb
- **Chemin** : `references/OpenKB/`
- **Type** : Knowledge Base compiler & Agent framework (CLI)
- **Langage principal** : Python
- **Statistiques** : ~293 fichiers

## Synthèse
OpenKB est un système open-source en ligne de commande qui compile des documents bruts en une base de connaissances (Wiki) structurée à l'aide de LLMs et de requêtes sémantiques. L'originalité repose sur une indexation via arbres (PageIndex) et la compilation systématique (concepts, entités, résumés croisés) qui permet une approche cumulative plutôt que purement extractive (RAG traditionnel).

La valeur pour l'usine logicielle réside dans ses gardes-fous architecturaux extrêmement poussés : un moteur de mutation robuste (`mutation.py`) exploitant un système de snapshots et hardlinks pour annuler des opérations de manière O(touched), des verrous inter-processus (`locks.py`) pour la concurrence, un cloisonnement réseau/FS sur les IO d'agents (`agent/tools.py`), ainsi qu'une très bonne doctrine déclarative d'agent (`SKILL.md`) et une usine de compétences (`skill/creator.py`).

La note globale est 🟢 **Haute**, en raison de la qualité des primitives de robustesse (idempotence, rollback, isolation). C'est une matière précieuse pour l'exécution sécurisée (sandbox) et l'enrichissement des compétences (skill loading).

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/OpenKB/README.md` | Concepts clés et flow d'intégration d'un LLM sur document long | 🟡 Moyenne |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/OpenKB/openkb/mutation.py` | `MutationSnapshot`, `snapshot_paths`, `_restore_hardlinked_dir` | Journalisation des écritures et rollbacks déterministes O(touched) (hardlinks) au crash. | 🟢 Haute | S'intègre avec P8-bis pour fiabiliser les manipulations de graphes et les modifications sur le repo (Idempotence). |
| `references/OpenKB/openkb/locks.py` | `kb_lock`, `atomic_write_bytes`, `_LocalRwLock` | Verrous d'accès concurentiels et d'écriture atomique multi-OS. | 🟢 Haute | Pattern solide pour P8-bis pour l'intégrité de la sandbox et les threads parallèles. |
| `references/OpenKB/openkb/agent/tools.py` | `read_kb_file`, `write_kb_file` | Outillage d'agents LLM imposant des limites strictes aux paths d'I/O (sandbox). | 🟢 Haute | Blue-print direct pour sécuriser l'usage d'outils Bash / I/O dans P8-bis. |
| `references/OpenKB/openkb/skill/creator.py` | `build_skill_create_agent`, `run_skill_create` | Pipeline de compilation d'agents dynamiques sur une cible donnée avec contraintes. | 🟡 Moyenne | Fournit une implémentation pour une Skill Factory via LLM pour P10. |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/OpenKB/skills/openkb/SKILL.md` | Prompt / Doctrine | Cadre déclaratif complet pour un agent de coding et de recherche (Trust boundaries explicites, actions proscrites). |

## Exclusions conscientes
- Tout le cœur de conversion et d'indexation PageIndex/LLM (`core/`, `compilers/`, `indexer/`...) qui est orienté "recherche textuelle / Wiki" et non ingénierie logicielle.
- La web-UI et les endpoints FastAPI associés.

## Correspondance avec `plan_usine_logicielle.md`
- **P8-bis** : `mutation.py` et `locks.py` pour un système de rollback transactionnel du repo map et l'idempotence des opérations sur fichiers locaux.
- **P8-bis** : `agent/tools.py` pour un modèle d'accès restreint (sandbox fs).
- **P10** : `skill/creator.py` et `skills/openkb/SKILL.md` pour l'infrastructure d'agents dynamiques spécialisés et leur définition.