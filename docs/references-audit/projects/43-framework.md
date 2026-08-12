# 43 — framework

## En-tête
- **Nom** : framework (AI-Driven Dev Framework)
- **Chemin** : `references/framework/`
- **Type** : framework d'orchestration / collection de skills
- **Langage principal** : Markdown (Prompts) / TypeScript (Hooks)
- **Statistiques** : 48 skills, 2 agents, 7 plugins

## Synthèse
Le framework AI-Driven Dev est une collection très structurée de "skills" et "plugins" pour divers agents de codage (Claude Code, Cursor, Copilot). Il définit un SDLC (Software Development Life Cycle) autonome, depuis le ticket jusqu'à la Pull Request, par le biais d'un orchestrateur `01-sdlc` et de skills sous-jacents.

La valeur majeure de ce dépôt réside dans sa formalisation documentaire des processus d'agent. Chaque "skill" est un fichier YAML+Markdown (`SKILL.md`) décrivant le comportement, les actions (avec des tables d'actions claires), et un schéma Mermaid décrivant le flux d'états (state machine). C'est un blueprint exceptionnel pour la conception de prompts d'orchestration et d'outillage, directement aligné avec la vision d'une "usine logicielle" multi-agents.

Le système de revue de code (`05-review`), découpé en 3 axes (code, functional, relevancy) avec une grille de sévérité stricte (`review-rubric.md`), est d'une grande valeur pour la spécialisation d'un Agent Juge (P6). Le système de débogage structuré par validation d'hypothèses (`08-debug`) est également très qualitatif.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/framework/README.md` | Point d'entrée, description du SDLC et des plugins. | 🟡 Moyenne |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/framework/plugins/aidd-orchestrator/skills/01-sdlc/SKILL.md` | `01-sdlc` flowchart | Orchestrateur SDLC avec phases Frame, Deliver, Check. Modélisation par state machine Mermaid. | 🟢 Haute | Excellent blueprint pour P0 (orchestration multi-agent). |
| `references/framework/plugins/aidd-dev/skills/05-review/SKILL.md` | `review-code`, `review-functional`, `review-relevancy` | Processus de revue de code à 3 axes avec template de rapport imposé. | 🟢 Haute | Modèle direct pour P6 Judge. |
| `references/framework/plugins/aidd-dev/skills/05-review/references/review-rubric.md` | `critical`, `approve`, `blocked` | Grille de sévérité et de verdict stricte pour les revues automatiques. | 🟢 Haute | Essentiel pour P6 Judge (verdict déterministe). |
| `references/framework/plugins/aidd-dev/skills/08-debug/SKILL.md` | `reproduce`, `debug`, `reflect-issue` | Skill de débogage empêchant les drive-by refactors et forçant la recherche de cause racine. | 🟢 Haute | Modèle de prompt pour les fix de bugs sans dérive. |
| `references/framework/plugins/aidd-dev/skills/08-debug/actions/02-debug.md` | `summarize`, `whys`, `causes` | Séquence en 11 étapes (5 why's, hypotheses validation) pour trouver l'origine d'un bug. | 🟡 Moyenne | Procédure prescriptive utile pour P6 ou un agent développeur. |
| `references/framework/plugins/aidd-vcs/skills/02-pull-request/SKILL.md` | `collect`, `draft`, `create` | Skill structurant la création d'une PR sans jamais forcer un push direct. | 🟡 Moyenne | Bonne approche sécurisée pour P0-bis. |

## Contrats / Specs / Config
(non applicable - principalement des prompts)

## Exclusions conscientes
- Toute la partie TypeScript/Hooks qui est spécifique à l'intégration dans des outils comme Claude Code. On s'intéresse ici à la logique conceptuelle des prompts.

## Correspondance avec `plan_usine_logicielle.md`
- **P0** : Architecture des skills et flow SDLC (`01-sdlc`).
- **P6** : Mécanique de revue (`05-review`, rubric) et débogage rigoureux (`08-debug`).
- **P10** : Format des skills avec actions explicites et machines à état Mermaid.