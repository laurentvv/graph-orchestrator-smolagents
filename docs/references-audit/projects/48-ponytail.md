# 48 — ponytail

## En-tête
- **Nom** : Ponytail (`ponytail`)
- **Chemin** : `references/ponytail/`
- **Type** : Doctrine et framework de concision anti-over-engineering pour agents de coding ("The lazy senior dev mode") — règles universelles de parcimonie, échelle YAGNI en 7 échelons, skills d'audit/review de diffs (`ponytail-review`, `ponytail-audit`, `ponytail-debt`) et plugins multi-agents (OpenClaw, Claude Code, Cursor, OpenCode, Codex, Devin, Groq, Kiro).
- **Langage principal** : Markdown (règles et skills) / JavaScript (plugins CJS/MJS) ; 153 fichiers : 45 `.md`, 35 `.json`, 18 `.cjs`, 18 `.mjs`, 12 `.yaml`, 10 `.svg`, 6 `.png`, 5 `.mdc`.
- **Licence** : MIT

## Synthèse
Ponytail incarne la philosophie du développeur senior pragmatique et volontairement « paresseux » : le meilleur code est celui qu'on n'écrit pas. Conçu pour contrer la tendance naturelle des LLM à la sur-ingénierie (création de couches d'abstraction inutiles, composants wrappers surdimensionnés, ajout de dépendances superflues au lieu d'utiliser la bibliothèque standard ou les fonctionnalités natives de la plateforme), Ponytail formalise une échelle de décision stricte en 7 échelons (*The Ponytail Ladder*) que l'agent doit gravir avant d'émettre la moindre ligne de code :
1. *Est-ce nécessaire ?* ➔ Non : ignorer (YAGNI).
2. *Existe-t-il déjà dans la base de code ?* ➔ Réutiliser l'utilitaire existant.
3. *La bibliothèque standard le fait-elle ?* ➔ Utiliser la stdlib (`urllib`, `pathlib`, `json`, `datetime`...).
4. *Une fonctionnalité native de la plateforme le couvre-t-elle ?* ➔ Utiliser le natif (ex. `<input type="date">` HTML5 vs Flatpickr).
5. *Une dépendance déjà installée le résout-elle ?* ➔ Utiliser la dépendance déjà présente.
6. *Peut-on l'écrire en une ligne ?* ➔ Faire une ligne concise.
7. *Seulement alors* : écrire le code minimal fonctionnel.

Le projet prouve scientifiquement son efficacité par des benchmarks agentiques rigoureux sur Claude Code éditant un dépôt réel (`fastapi/full-stack-fastapi-template`) : **-54% de lignes de code** (jusqu'à -94% sur des composants sur-conçus), **-22% de tokens**, **-20% de coût**, **-27% de latence**, avec **100% de conformité sécuritaire et fonctionnelle**.

Pour `graph-orchestrator-smolagents`, Ponytail apporte une valeur immédiate :
1. **P0 & P0-bis (Cadre de prompting Coder/Drafter & Invariants)** : L'injection de la règle de concision et de l'échelle YAGNI dans les prompts du Drafter et du Coder empêche le modèle rapide (Qwen-4B / 3.5) de s'égarer dans des architectures verbeuses, réduit drastiquement les risques de bugs et stabilise la génération en 1 itération.
2. **P6 (Judge & Revue de diffs)** : Le skill `ponytail-review` fournit un format de verdict ultra-concis (1 ligne par finding : `delete:`, `stdlib:`, `native:`, `yagni:`, `shrink:`, suivi du bilan `net: -N lines possible`), idéal pour notre nœud Judge et le Security Reviewer.
3. **P10 (Skills d'optimisation)** : Les skills `ponytail-audit` et `ponytail-debt` fournissent des outils clés-en-main pour scanner une base de code et éliminer la dette technique avant ou après refactorisation.

Note globale : **🟢 Haute** — modèle exemplaire de concision, directement transposable dans les prompts et skills de l'orchestrateur.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/ponytail/AGENTS.md` | Charte opérationnelle de Ponytail pour les agents de codage : échelle de décision, règles de minimalisme, exclusions | **Haute** (P0 / P0-bis — règles universelles de sobriété) |
| `references/ponytail/README.md` | Présentation complète, méthodologie, matrice comparative avant/après et principes de concision | **Haute** (P0 — doctrine anti-over-engineering) |
| `references/ponytail/benchmarks/results/2026-06-18-agentic.md` | Rapport de benchmark agentique sur 12 tâches réelles avec Claude Code sur FastAPI+React (-54% LOC, -22% tokens, 100% safe) | Moyenne (P6 — protocole de validation et métriques de réduction) |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/ponytail/.agents/rules/ponytail.md` | `The Ponytail Ladder`, `Rungs 1-7`, `Bug fix = root cause`, `Rules` | Règle universelle d'agent : formalisation des 7 échelons de décision, interdiction des abstractions spéculatives, minimalisme du diff | **Haute** | P0+P0-bis : Directive à injecter dans le prompt système de nos agents Coder et Drafter |
| `references/ponytail/.openclaw/skills/ponytail-review/SKILL.md` | `ponytail-review`, `delete:`, `stdlib:`, `native:`, `yagni:`, `shrink:`, `net: -<N> lines` | Skill d'analyse de diff pour détecter la sur-ingénierie : format strict en 1 ligne par constat et bilan net de réduction de lignes | **Haute** | P6+P10 : Format d'évaluation direct pour le nœud Judge et les revues de code automatisées |
| `references/ponytail/.openclaw/skills/ponytail-audit/SKILL.md` | `ponytail-audit`, `Hunt`, `Output`, `net: -<N> lines, -<M> deps` | Skill d'audit global de dépôt pour traquer le code mort, les abstractions à implémentation unique et les réinventions de stdlib | **Haute** | P6+P10 : Outil d'audit statique et de nettoyage de dette technique pour l'architecte et les phases de refactoring |
| `references/ponytail/.openclaw/skills/ponytail-debt/SKILL.md` | `ponytail-debt`, `Debt categories`, `Remediation` | Skill de cartographie de dette technique de complexité (sur-empaquetage, sur-typage, wrappers inutiles) | Moyenne | P10 : Complément d'analyse pour les audits de codebase |
| `references/ponytail/.openclaw/skills/ponytail-gain/SKILL.md` | `ponytail-gain`, `LOC diff`, `Token reduction` | Skill d'estimation et de mesure des gains de concision et de réduction de complexité | Moyenne | P6+P11 : Métrique de qualité de refactorisation |
| `references/ponytail/.openclaw/skills/ponytail-help/SKILL.md` | `ponytail-help`, `Quick reference` | Guide mémo condensé de la doctrine Ponytail pour agents interactifs | Moyenne | P10 : Référence rapide pour les sous-agents |
| `references/ponytail/.opencode/plugins/ponytail-frontmatter.cjs` | `transformFrontmatter`, `stripMetadata` | Plugin de normalisation et d'injection de frontmatter pour l'interopérabilité des règles entre formats d'agents | Moyenne | P10 : Utilitaires de conversion de skills/rules multi-formats |
| `references/ponytail/.opencode/plugins/ponytail.mjs` | `registerPlugin`, `onPreToolCall` | Intercepteur d'appels d'outils appliquant les garde-fous de concision avant modification de fichiers | Moyenne | P8 : Pattern d'interception middleware pré-écriture |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/ponytail/.openclaw/skills/ponytail/SKILL.md` | Skill definition | Définition canonique du skill OpenClaw/Claude Code Ponytail |
| `references/ponytail/plugin.json` | Plugin manifest | Manifeste d'extension multi-plateforme (outils, hooks, règles) |

## Exclusions conscientes
| Chemin | Motif d'exclusion |
|---|---|
| `references/ponytail/assets/` | Fichiers d'images, logos, badges et bannières promotionnelles. Ignorer. |
| `references/ponytail/README.es.md`, `README.ko.md` | Traductions en espagnol et coréen du README. Ignorer. |
| `references/ponytail/.cursor/`, `.clinerules/`, `.qoder/`, `.kiro/` | Fichiers de configuration spécifiques aux éditeurs IDE commerciaux tiers (redondants avec `.agents/rules/ponytail.md`). Ignorer. |

## Correspondance avec `plan_usine_logicielle.md`
- **P0 / P0-bis** : `The Ponytail Ladder` & `.agents/rules/ponytail.md` (règles de sobriété, élimination de la sur-ingénierie, réutilisation stdlib/plateforme).
- **P6** : `ponytail-review` & `ponytail-audit` (format de findings concis `delete:`, `stdlib:`, `native:`, `yagni:`, `shrink:` pour le Judge).
- **P8** : `ponytail.mjs` (garde-fous pré-écriture pour limiter la création de fichiers inutiles).
- **P10** : Suite de skills `ponytail-*` (spécialisation de la revue de code et audit de dette technique).
