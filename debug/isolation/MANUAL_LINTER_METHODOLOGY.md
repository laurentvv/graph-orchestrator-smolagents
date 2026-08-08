# Méthodologie de linting manuel (= spec du Linter idéal)

Ce document décrit **exactement** ce que je fais (l'agent) quand je joue le nœud Linter à la
main, étape par étape. C'est le cahier des charges du Linter idéal.

## Rôle du nœud Linter

**Entrée** : `subtask` dict avec `target_files` (fichiers générés par le Coder, à valider).

**Sortie** : `CoderOutput(task_id, status: "success"|"failure", details)` — status="success"
si TOUS les fichiers sont syntaxiquement valides, "failure" sinon (avec les erreurs dans
details, exploitables comme feedback pour le Coder).

Le Linter est un **gatekeeper déterministe (0 LLM, 0 réseau)** inséré entre le Coder et le
Tester (F-30). S'il détecte une erreur de syntaxe triviale, il **court-circuite** le Tester
coûteux et renvoie le feedback au Coder. C'est l'anti-gaspillage de cycles LLM : ne pas
envoyer un code syntaxiquement cassé au Tester/Judge.

## Les langages couverts (détection par extension)

| Extension | Langage | Vérifications |
|---|---|---|
| `.py` | python | tree-sitter (SyntaxError génériques) + **py_compile** (IndentationError, le point noir) |
| `.html`/`.htm` | html | **vérifs structurelles uniquement** (tree-sitter-html trop tolérant sur CSS/JS inline → sauté) |
| `.js`/`.mjs`/`.cjs` | javascript | tree-sitter (attrape TS-in-vanilla) |
| `.ts` | typescript | tree-sitter |
| `.tsx` | tsx | tree-sitter (language_tsx) |
| `.css` | css | tree-sitter |
| autre | unknown | `is_valid=True` (pas de faux positif, on laisse Tester/Judge juger) |

## Les étapes (dans l'ordre, fail-fast)

### Étape 1 — Détection de la langue (extension = source de vérité)
**Ce que je fais** : pour chaque fichier, je regarde l'extension. C'est **déterministe et
fiable** — pas d'inférence de contenu.
**Outil** : `os.path.splitext`
**Échec type évité** : essayer de deviner la langue en lisant le contenu (source d'erreurs).
L'extension est la source de vérité (même heuristique que le dispatch Tester F-27).

### Étape 2 — tree-sitter (SyntaxError génériques, SAUF HTML)
**Ce que je fais** : je parse le code avec tree-sitter et je compte les nœuds ERROR +
MISSING.
**Outil** : `tree-sitter` (parseur grammatical)
**Coût** : 0 LLM, millisecondes
**⚠️ EXCEPTION HTML** : tree-sitter-html parse le CSS/JS inline comme du texte HTML →
des dizaines de faux positifs sur du code valide (les `#`, `{}`, `let`, `;` du
`<style>`/`<script>` sont incompréhensibles pour le parser HTML). C'était la cause de la
boucle Linter infinie sur Bubble Sort (77 faux positifs). **Pour le HTML, on saute
tree-sitter** et on se fie uniquement aux vérifs structurelles (étape 4).
**Échec type détecté** : accolades non fermées, strings non fermées, structures cassées (JS,
CSS, Python), TS-in-vanilla dans un `.js` (le failure mode n°1 du Coder : gemma écrit du TS
par réflexe → SyntaxError → page blanche).

### Étape 3 — py_compile (IndentationError Python — LE point noir)
**Ce que je fais** : pour Python uniquement, je lance `py_compile.compile(path,
doraise=True)`.
**Outil** : `py_compile` (stdlib, toujours dispo)
**Coût** : 0 LLM, millisecondes
**Pourquoi pas tree-sitter seul** : tree-sitter est un parser grammatical **tolérant** — il
parse un IndentationError sans flagger (la grammaire "accepte"). py_compile, lui, lève une
exception réelle. L'IndentationError est le **point noir reconnu par tous les audits**
(failure mode récurrent des petits LLM sur Python). py_compile est le contre-mesure canonique.
**Échec type détecté** : IndentationError, SyntaxError Python (le point noir).

### Étape 4 — Vérifs structurelles HTML (tree-sitter-html tolérant ne suffit pas)
**Ce que je fais** : pour HTML uniquement, des vérifications structurelles explicites :
1. Pas de contenu significatif après `</html>` (le bug exact du dashboard cassé : CSS/JS
   appendés après la fermeture du document → rendu texte brut).
2. Présence d'un `<!DOCTYPE html>`.
3. Équilibrage des balises structurelles (`<html>`, `<head>`, `<body>`).
**Outil** : regex sur le source HTML
**Coût** : 0 LLM, millisecondes
**Échec type détecté** : contenu après `</html>` (le bug du run CodeAgent incrémental : le
Coder appendait du CSS/JS après la fermeture).

### Étape 5 — Verdict agrégé (success si tous valides)
**Ce que je fais** : `status = "success"` si TOUS les fichiers sont valides, `"failure"`
sinon. En cas d'échec, j'agrège les erreurs par fichier (lisible pour le Coder).
**Format details** (failure) :
```
ERREURS DE SYNTAXE DÉTECTÉES (à corriger avant de continuer) :

Fichier path/to/code.py (python) :
  - [py_compile] Sorry: IndentationError: expected an indented block after 'if' statement on line 4
```

## Ordre optimal (fail-fast)

```
1. Détection langue (extension)               ──▶ python | html | js | ts | css | unknown
   │
   ▼
2. tree-sitter (SAUF html)                    ── ERROR/MISSING ──▶ FAILURE "erreur de syntaxe"
   │ valide
   ▼
3. py_compile (Python uniquement)             ── PyCompileError ──▶ FAILURE "IndentationError"
   │ valide (ou pas Python)
   ▼
4. Vérifs structurelles (HTML uniquement)     ── contenu après </html> ──▶ FAILURE
   │ valide (ou pas HTML)
   ▼
5. Verdict agrégé                             ──▶ success si tous valides, sinon failure + details
```

## ⚠️ BIAIS & LIMITES — Les pièges du Linter

**Limite n°1 — Dégradation gracieuse** : si tree-sitter n'est pas installé, le Linter
retombe sur py_compile (Python) + vérifs structurelles (HTML) — il reste utile mais rate le
TS-in-vanilla (JS). À savoir : `run_linter.py` affiche un warning si le scénario JS ne
faille pas (probable tree-sitter absent).

**Biais n°1 — Faux positifs sur HTML (le piège historique)**. tree-sitter-html est TROP
tolérant sur le CSS/JS inline → il génère 77 faux positifs sur un HTML correct. C'est pour
ça qu'on **saute tree-sitter pour le HTML** (étape 2). Ne JAMAIS réactiver tree-sitter sur
le HTML sans avoir vérifié qu'il n'y a pas de régression.

**Biais n°2 — Confondre syntaxe et comportement**. Le Linter valide la **syntaxe**, pas la
**logique**. Un code syntaxiquement valide peut être fonctionnellement faux (ex: tri à
l'envers). C'est le rôle du Tester (et du Static Tester F-54) de capter ça, pas du Linter.

**Biais n°3 — Ignorer le contenu après `</html>`**. C'est un bug subtil (le navigateur
affiche le contenu en texte brut, pas une erreur). La vérif structurelle HTML (étape 4) est
la seule à le détecter — tree-sitter ne le flagge pas.

## Pourquoi cette méthode plutôt que le LLM

Le Linter est **déterministe par design** (0 LLM). Il n'y a pas de "LLM Linter" — le nœud
de production (`linter.py`) utilise déjà tree-sitter + py_compile. Cette doc décrit donc
simplement **ce que le nœud fait**, et le script d'isolation `run_linter.py` le valide en
exécution (7 scénarios buggés/corrects, 7/7 ✅).

**Conclusion** : le Linter est le nœud le plus simple à isoler (déterministe, ms, assertion
binaire possible). Le script `run_linter.py` (ce dossier) reproduit fidèlement la
méthodologie ci-dessus et la valide en direct — c'est le template pour tout script
d'isolation d'un nœud déterministe.
