# Fixtures Golden — sorties figées des nœuds déterministes

Ce dossier contient les **sorties attendues** (golden files) des nœuds **déterministes**
(0 LLM, 0 réseau) pour détecter les régressions de comportement. Une régression = la
sortie réelle diffère du golden → quelque chose a cassé silencieusement.

## Convention

| Nœud | Type | Golden ? | Pourquoi |
|---|---|---|---|
| Linter (F-30) | Déterministe (tree-sitter + py_compile) | ✅ Oui | Sortie stable → régression détectable |
| Static Tester (F-54) | Déterministe (node --check + DevTools DOM) | ✅ Oui | Sortie stable (success/failure + bugs nommés) |
| Router | LLM | ❌ Non | Non-déterministe (le verdict dépend de la réflexion) |
| PromptRefiner | LLM | ❌ Non | Non-déterministe |
| Architect | LLM | ❌ Non | Non-déterministe |
| Drafter | LLM | ❌ Non | Non-déterministe |
| Security | LLM | ❌ Non | Non-déterministe |
| Judge | LLM | ❌ Non | Non-déterministe |
| Coder | LLM | ❌ Non | Non-déterministe |
| Tester | LLM | ❌ Non | Non-déterministe |

## Les nœuds LLM restent non-golden

Les nœuds LLM ne peuvent pas avoir de golden file : leur sortie varie d'un run à l'autre
(température > 0, reflexion non reproductible). **Mais leurs entrées sont figées** dans les
scripts d'isolation (`debug/run_*.py`) — on peut ainsi comparer la *qualité* de la sortie
(visuelle / heuristique) sans attendre une égalité bit-parfait.

## Comment ajouter un golden file (nœud déterministe)

1. Lancer le script d'isolation du nœud déterministe (ex: `uv run python debug/isolation/run_linter.py`).
2. Sauvegarder la sortie dans un fichier `<node>_<scenario>.txt` ici.
3. Ajouter une assertion dans le script d'isolation : la sortie réelle == contenu du golden.

Exemple pour le Linter :
```
debug/fixtures/golden/linter_python_indentation.txt   → "failure\nIndentationError..."
debug/fixtures/golden/linter_js_ts_in_vanilla.txt     → "failure\nTS annotation..."
debug/fixtures/golden/linter_html_trailing.txt        → "failure\ncontenu après </html>"
```

## Scripts de validation des nœuds déterministes

- `debug/isolation/run_linter.py` — 7 scénarios buggés/corrects, validés en millisecondes.
- `debug/validate_static_tester_live.py` — Static Tester (F-54), 2 scénarios (corrompu/correct).

Ces scripts n'ont pas encore de comparaison golden file automatique (assertion stricte).
C'est une évolution future — pour l'instant ils affichent les verdicts ✅/❌ pour
inspection visuelle, ce qui suffit au dépannage rapide (le but de F-89).
