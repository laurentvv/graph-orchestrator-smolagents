# 19 — anydoc

## En-tête
- **Nom** : anydoc
- **Chemin** : `references/anydoc/`
- **Type** : Bibliothèque de conversion documentaire (Rust/Python)
- **Langage principal** : Rust (avec bindings Python, Node, Wasm)
- **Statistiques** : ~275 fichiers (majorité `.rs`, `.snap`, tests)

## Synthèse
`anydoc` est une bibliothèque très rapide permettant de convertir de multiples formats de documents (Word, PPT, Excel, ODT, etc.) en Markdown de façon déterministe. Bien que le cœur soit développé en Rust, le dépôt fournit des bindings Python propres (`firecrawl-anydoc`) ainsi qu'une définition d'Agent Skill prête à l'emploi.

Pour `graph-orchestrator-smolagents`, l'intérêt direct ne réside pas dans la réécriture de l'outil, mais dans les patterns périphériques qu'il expose. Son harnais de benchmark inclut un "LLM Judge" extrêmement pertinent qui utilise une évaluation pairwise (A/B testing avec inversion de position) via l'API Batch d'Anthropic. Par ailleurs, la définition déclarative de sa compétence (`SKILL.md`) et les stubs de son AST Python constituent d'excellents modèles pour la gestion des données entrantes et l'authoring de skills.

La note globale est 🟢 Haute pour la réutilisabilité des patterns (LLM Judge, Skill, AST) dans le contexte de notre orchestrateur Python.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `README.md` | Explication du modèle universel (AST) pour la conversion documentaire. | 🟡 Moyenne |
| `bench/README.md` | Méthodologie d'évaluation de la qualité par un LLM Juge (pairwise). | 🟢 Haute |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `skills/convert-documents-to-markdown/SKILL.md` | `name`, `rules` | Définition déclarative d'une compétence agentique avec frontmatter YAML et règles de comportement. | 🟢 Haute | Modèle parfait pour l'authoring de skills standardisés (P10). |
| `python/anydoc/_anydoc.pyi` | `Document`, `Block`, `Inline` | Typage strict Python de l'AST document (titres, tableaux, inlines). | 🟢 Haute | Utile pour concevoir notre propre représentation mémoire des données (compaction contextuelle, P9). |
| `bench/judge.py` | `PROMPT`, `parse_verdict` | Script d'évaluation A/B par LLM (Claude) avec inversion de position pour annuler le biais. | 🟢 Haute | Pattern d'évaluation "pairwise" directement exploitable pour le module Judge de l'orchestrateur (P6). |

## Exclusions conscientes
- Le cœur du parseur en Rust (`src/`, `tests/`) : hors-scope, notre orchestrateur (Python) se contentera d'importer la lib via `pip install firecrawl-anydoc` si nécessaire.

## Correspondance avec `plan_usine_logicielle.md`
- **P6** : Juge LLM pairwise avec inversion de position (`bench/judge.py`).
- **P9** : Structure AST pour ingérer et compacter des documents complexes (`python/anydoc/_anydoc.pyi`).
- **P10** : Modèle déclaratif clair pour la définition de compétences (`SKILL.md`).