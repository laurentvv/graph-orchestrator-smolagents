# 03 — nanocode

## En-tête
- **Nom** : nanocode
- **Chemin** : `references/nanocode/`
- **Type** : alternative minimale à Claude Code (un seul fichier Python, zéro dépendance)
- **Langage principal** : Python (stdlib uniquement : `glob`, `re`, `subprocess`, `urllib.request`, `json`, `os`)
- **Statistiques** : 3 fichiers (1 `.py` de 272 lignes / ~8.7 Ko, 1 `.md` de ~1.5 Ko, 1 screenshot PNG ~173 Ko)

## Synthèse
`nanocode` est un clone minimaliste de "Claude Code" tenu en un seul fichier Python (~250 lignes annoncées, 272 effectives), sans aucune dépendance externe (stdlib uniquement). Il implémente un **agent à outils** complet : une boucle agentic qui continue tant que le modèle émet des blocs `tool_use`, six outils orientés editing de code (`read`, `write`, `edit`, `glob`, `grep`, `bash`), une génération dynamique du schéma d'outils (`make_schema()`), et un rendu terminal ANSI couleur.

Le projet communique directement avec l'API Anthropic Messages (ou OpenRouter via `OPENROUTER_API_KEY`) au moyen de `urllib.request` — pas de SDK. C'est un **modèle pédagogique exemplaire** d'un agent tool-using minimal : toute la mécanique (boucle, dispatch, schéma, streaming) tient en ~250 lignes lisibles. Pour le projet cible `graph-orchestrator-smolagents`, l'intérêt principal réside dans (1) le **pattern d'outils `edit` avec imposition d'unicité du `old_string`** — plus sûr qu'un replace naïf et transposable aux outils des Coders, (2) un **schéma d'outils dynamique compact** basé sur un suffixe `?` pour les paramètres optionnels, et (3) les implémentations `read/glob/grep/bash` candidates pour des outils smolagents légers. Le couplage au format de réponse Anthropic (`content` blocks typés `text`/`tool_use`) et le rendu ANSI sont spécifiques et faiblement réutilisables.

> ⚠️ Le README mentionne les clés `old_string`/`new_string` pour `edit`, mais **le code réel utilise `old`/`new`** (à vérifier si réutilisation).

Note de réutilisabilité globale : **Moyenne** (pédagogique / inspiration pour un Coder minimal).

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/nanocode/README.md` | Présentation, usage (clés `ANTHROPIC_API_KEY`/`OPENROUTER_API_KEY`, var `MODEL`), commandes `/c` `/q` `exit`, table des 6 outils, exemple de session, licence MIT | Moyenne — décrit l'API et le contrat d'usage des outils |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/nanocode/nanocode.py` | `edit` (l.38-51) | Remplacement de chaîne dans un fichier avec **imposition d'unicité** : erreur si `old` absent ; erreur explicite avec le compte si `old` apparaît >1 fois sans `all=true`. Clés réelles : `path`, `old`, `new`, `all` (optionnel) | **Haute** | Bonne pratique anti-ambiguïté directement transposable aux outils d'editing des Coders ; plus sûr qu'un `str.replace` naïf |
| `references/nanocode/nanocode.py` | `make_schema` (l.143-167) + `TOOLS` (l.102-133) | Génération **dynamique** du schéma JSON d'outils depuis un dict `(description, params, fn)`. Convention suffixe `?` = paramètre optionnel ; `number` mappé vers `integer` ; séparation auto `required`/`optional` | Moyenne | Schéma d'outils compact et déclaratif, adaptable pour déclarer des outils smolagents légers |
| `references/nanocode/nanocode.py` | `read` (l.24-29), `glob` (l.54-62), `grep` (l.65-75), `bash` (l.78-97) | Implémentations stdlib d'outils de lecture/recherche/exécution. `read` : numéros de ligne + `offset`/`limit`. `glob` : tri par mtime desc. `grep` : regex récursive, plafonné à 50 hits. `bash` : streaming ligne à ligne + timeout 30s + kill | Moyenne | Bons squelettes d'outils autonomes pour agents smolagents ; `bash` illustre timeout+streaming robuste |
| `references/nanocode/nanocode.py` | Boucle agentic dans `main` (l.222-260) + `run_tool` (l.136-140) | Boucle interne qui rappelle l'API tant que des blocs `tool_use` sont présents (break si `tool_results` vide) ; dispatch `run_tool` avec catch-all `Exception` retournant `error: {err}` | Moyenne | Modèle pédagogique de boucle tool-use transposable, mais couplé au format de réponse Anthropic |
| `references/nanocode/nanocode.py` | `write` (l.32-35) | Écriture simple de contenu dans un fichier | Faible | Trivial, équivalent à un one-liner |
| `references/nanocode/nanocode.py` | `call_api` (l.170-189) | Appel HTTP brut via `urllib.request` à Anthropic ou OpenRouter (header `Authorization` vs `x-api-key`), `max_tokens=8192` | Faible | Couplage fort aux APIs Anthropic/OpenRouter ; la cible utilise DSPy/smolagents |
| `references/nanocode/nanocode.py` | `separator` (l.192-193), `render_markdown` (l.196-197), constantes ANSI (l.11-18) | Rendu terminal couleur (RESET/BOLD/DIM/BLUE/CYAN/GREEN/YELLOW/RED), séparateur pleine largeur, gras `**markdown**` | Faible | Cosmétique CLI, non pertinent pour l'orchestrateur cible |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/nanocode/README.md` | Spec d'usage | Contrat d'interface : variables d'env (`ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `MODEL`), commandes slash (`/c`, `/q`, `exit`), table des 6 outils et leur description |
| `references/nanocode/nanocode.py` (constantes l.6-8) | Config inline | `OPENROUTER_KEY`, `API_URL` (Anthropic vs OpenRouter), `MODEL` par défaut (`claude-opus-4-5` / `anthropic/claude-opus-4.5`) |
| `references/nanocode/nanocode.py` (`TOOLS`, l.102-133) | Spec d'outils | Définition déclarative des 6 outils : `(description, params_typés, fonction)`. Paramètres optionnels marqués par suffixe `?` |

## Exclusions conscientes
- `references/nanocode/screenshot.png` : média (capture d'écran ~173 Ko), exclu de l'analyse de code
- `references/nanocode/.git/` : historique de version, hors périmètre
