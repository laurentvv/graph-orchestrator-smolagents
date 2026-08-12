# 40 — skills

## En-tête
- **Nom** : skills (Anthropic)
- **Chemin** : `references/skills/`
- **Type** : Collection de skills pour agents (Claude)
- **Langage principal** : Python (scripts), Markdown (prompts)
- **Statistiques** : ~410 fichiers, principalement `.xsd`, `.md`, `.py`.

## Synthèse
Le dépôt `skills` officiel d'Anthropic propose une collection d'exemples de "skills" (compétences) pour des agents LLM. Il fournit des modèles de *prompts* (doctrine d'usage) ainsi que des scripts d'évaluation et de création de ces mêmes compétences.
La valeur pour `graph-orchestrator-smolagents` est extrêmement élevée pour la priorité P10 (Skill loading) et P6 (Judge / Findings). Les briques `skill-creator` et `mcp-builder` offrent des harnais d'évaluation concrets (split train/test, métriques) et des doctrines rigoureuses pour l'interaction avec des serveurs MCP ou le web.
Note globale : 🟢 **Haute**, l'architecture de test et d'itération de compétences via scripts Python déportés est un modèle à suivre pour `smolagents`.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/skills/skills/skill-creator/SKILL.md` | Doctrine d'orchestration pour la création de skills (boucle brouillon, test, évaluation). | 🟢 Haute |
| `references/skills/skills/mcp-builder/reference/mcp_best_practices.md` | Bonnes pratiques pour l'architecture de serveurs MCP (nommage, pagination). | 🟡 Moyenne |
| `references/skills/skills/webapp-testing/SKILL.md` | Arbre de décision pour éviter à l'agent de lire le code source des scripts complexes avant de les tester en boîte noire. | 🟢 Haute |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/skills/skills/skill-creator/scripts/run_loop.py` | `split_eval_set`, `run_eval` | Boucle d'évaluation avec un split train/test pour prévenir l'overfitting des compétences agentiques. | 🟢 Haute | Indispensable pour la priorité P6 (Judge) appliqué aux skills. |
| `references/skills/skills/mcp-builder/scripts/evaluation.py` | `EVALUATION_PROMPT`, XML parsing | Harnais d'évaluation se connectant à un serveur MCP pour évaluer la fiabilité des outils exposés via Claude. | 🟢 Haute | Permet de valider un serveur MCP généré dynamiquement. |

## Exclusions conscientes
- Les scripts `.xsd` et autres formats liés à l'application `canvas-design` ou `theme-factory` très spécifiques.
- Les implémentations d'édition de `.docx` ou `.xlsx` qui sont des outils spécialisés non cruciaux pour l'architecture centrale.

## Correspondance avec `plan_usine_logicielle.md`
- **P6** : Référence pour la boucle de test de robustesse (`run_loop.py` et `evaluation.py`).
- **P10** : Doctrine de création, test et chargement itératif de compétences (`skill-creator`).