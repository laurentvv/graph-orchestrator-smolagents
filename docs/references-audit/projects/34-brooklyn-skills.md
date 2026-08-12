# 34 - brooklyn-skills

## En-tête
- **Nom** : brooklyn-skills
- **Chemin** : `references/brooklyn-skills/`
- **Type** : Collection de skills portables pour agents de coding.
- **Langage principal** : Markdown (prompts purs).
- **Statistiques** : ~24 fichiers, principalement du markdown (.md).

## Synthèse
Le dépôt `brooklyn-skills` propose une collection de "skills" (compétences ou instructions ciblées) portables pour des agents de codage (Claude Code, Hermes Agent, Cursor, etc.). Chaque skill est encapsulé dans un fichier `SKILL.md` et cible un flux de travail précis (ex: préparation d'une PR, debug de runtime, nettoyage de code). 

La valeur pour `graph-orchestrator-smolagents` est extrêmement élevée (🟢 Haute), notamment pour enrichir la doctrine des agents (les Invariants P0-bis) et fournir des "skills" prêts à l'emploi (P10) orientés sur la qualité, la discipline et les flux git. Les instructions sont concises, sans fioritures et dictent un comportement professionnel à l'agent.

Une pépite particulière est le skill `no-tropes` qui liste les tics d'écriture des LLM (tropes) et fournit un protocole de révision pour les éliminer.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/brooklyn-skills/README.md` | Explication du concept de skills portables sans commandes ni hooks. | 🟢 Haute |

## Code réutilisable (Prompts & Skills)
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/brooklyn-skills/defaults.md` | `# Always-on defaults` | Comportements de base applicables à toutes les sessions (invariants universels). | 🟢 Haute | Base idéale pour le P0-bis (Invariants universels) : UI first, pas de format/lint intempestif, isolation. |
| `references/brooklyn-skills/skills/no-tropes/tropes-reference.md` | `AI Writing Tropes` | Catalogue des tics d'écriture des IA (magic adverbs, em-dash, listicles). | 🟢 Haute | Parfait pour le P6 (Judge) ou P0-bis pour garantir des outputs professionnels et directs. |
| `references/brooklyn-skills/skills/cpr/SKILL.md` | `clean then pr-update` | Skill combinant le nettoyage (KISS/DRY) et la création/mise à jour de PR. | 🟢 Haute | Un workflow clé pour P10 (Skill loading) et la délégation. |
| `references/brooklyn-skills/skills/runtime-debug/SKILL.md` | `# Runtime Debug` | Doctrine forçant l'agent à lire les logs/observabilité avant de toucher au code. | 🟢 Haute | Indispensable pour éviter que l'agent ne modifie du code à l'aveugle (P6 / P10). |
| `references/brooklyn-skills/skills/ui-only/SKILL.md` | `# UI Only` | Bloque les suites de tests, le lint et les commits tant que l'UI n'est pas validée. | 🟢 Haute | Optimisation des cycles de développement front-end (P10). |
| `references/brooklyn-skills/skills/work/SKILL.md` | `git worktree` | Isolation des tâches via git worktree. | 🟡 Moyenne | Intéressant pour P8-bis (Sandbox), mais dépend de l'environnement git local. |

## Exclusions conscientes
- `skills/notarize-mac`, `skills/free-disk-space` : Trop spécifiques à macOS et au hardware, hors-scope de l'usine logicielle.

## Correspondance avec `plan_usine_logicielle.md`
- **P0-bis Invariants universels** : `defaults.md` et `no-tropes` dictent des règles universelles de ton, de style et de discipline (ne pas répondre sans chercher, UI first, pas de prose verbeuse).
- **P6 Judge / Findings** : Le protocole de révision de `no-tropes` sert de standard pour juger la qualité des outputs texte. `runtime-debug` force la vérification des logs avant édition.
- **P8-bis Sandbox + Idempotence** : Le concept de `work` utilisant `git worktree` offre une alternative aux sandboxes docker.
- **P10 Skill loading** : L'approche de `brooklyn-skills` (des dossiers contenant un `SKILL.md` portable) est un excellent modèle d'implémentation. Les skills `cpr` et `ui-only` sont à reprendre tels quels.

---