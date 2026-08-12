# 37 — obsidian-skills

## En-tête
- **Nom** : obsidian-skills
- **Chemin** : `references/obsidian-skills/`
- **Type** : Collection de skills agentiques
- **Langage principal** : Markdown
- **Statistiques** : 21 fichiers, 100% Markdown / docs.

## Synthèse
Le dépôt `obsidian-skills` propose une collection de skills (compétences) formatées selon la spécification `Agent Skills` (agentskills.io). Ces skills sont destinées à des agents IA comme Claude Code, Codex ou Open Code pour interagir avec des coffres-forts Obsidian.

L'intérêt principal pour le projet `graph-orchestrator-smolagents` réside dans l'architecture déclarative des skills. Chaque compétence sépare clairement son fichier principal (`SKILL.md`) contenant le prompt de comportement et les exemples, d'un répertoire `references/` qui stocke la documentation supplémentaire à injecter (Progressive Disclosure). Cette approche modulaire est extrêmement pertinente pour la priorité P10 (Skill loading).

La note globale est 🟢 **Haute**, car bien qu'il n'y ait pas de code Python, le design pattern documentaire (la "doctrine" de structuration des skills) valide notre conception pour la création de sous-agents modulaires.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/obsidian-skills/README.md` | Instruction sur la structure et l'installation d'une skill agentique | 🟡 Moyenne |

## Code réutilisable (Prompts & Patterns)
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/obsidian-skills/skills/obsidian-markdown/SKILL.md` | `name: obsidian-markdown`, `# Obsidian Flavored Markdown Skill` | Modèle de prompt pour enseigner une syntaxe spécifique. | 🟢 Haute | Pattern clair de découpage : Workflow, syntaxe (links, embeds, etc.) avec des exemples concrets. Idéal pour P10. |
| `references/obsidian-skills/skills/obsidian-markdown/references/PROPERTIES.md` | N/A | Exemple de documentation de référence déportée de la skill principale. | 🟢 Haute | Permet d'éviter de saturer le contexte de la skill (`SKILL.md`) avec des détails exhaustifs. Pattern de "chunking" pertinent pour l'orchestrateur. |
| `references/obsidian-skills/skills/obsidian-cli/SKILL.md` | `name: obsidian-cli`, `obsidian vault="My Vault" search` | Skill pour interagir avec une CLI. Montre comment documenter les flags et paramètres d'un outil en ligne de commande pour le LLM. | 🟢 Haute | Très pertinent pour apprendre aux agents à utiliser des CLI internes ou des wrappers Python. |
| `references/obsidian-skills/skills/defuddle/SKILL.md` | `name: defuddle`, `defuddle parse <url> --md` | Pattern de skill simple remplaçant une action générique (WebFetch) par un outil spécifique (defuddle) selon des critères (non-.md). | 🟢 Haute | Illustration parfaite d'une règle métier intégrée dans la description d'une skill pour guider le choix d'outil de l'agent. |

## Exclusions conscientes
- `skills/json-canvas/` : Syntaxe très spécifique à Obsidian Canvas, moins généralisable.
- `skills/obsidian-bases/` : Syntaxe Obsidian Bases, trop nichée.

## Correspondance avec `plan_usine_logicielle.md`
- **P10** : Fournit une doctrine d'architecture de skill avec séparation `SKILL.md` / `references/`.