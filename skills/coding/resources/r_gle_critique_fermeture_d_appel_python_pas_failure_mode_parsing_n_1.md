## ⚠️ RÈGLE CRITIQUE — Fermeture d'appel Python `)` pas `}` (failure mode parsing n°1)

Quand tu passes du JS/HTML à `write_file`/`search_replace`/`append_file` (via l'argument
`content`/`new_string`), le CONTENU contient des accolades `{ ... }` (blocs JS, objets,
CSS). Ces accolades appartiennent au CONTENU, pas à l'appel Python. L'appel se ferme
TOUJOURS par `)`. Confondre les deux provoque `SyntaxError: closing parenthesis '}' does
not match` → l'appel d'outil entier est rejeté, le fichier n'est pas écrit.

| ❌ Faux (SyntaxError fatal) | ✅ Correct |
|---|---|
| `write_file(path="a.html", content="function() { return 1; }"}` | `write_file(path="a.html", content="function() { return 1; }")` |
| `search_replace(path="x", old="f() {}", new="f() { return 2; }"}` | `search_replace(path="x", old="f() {}", new="f() { return 2; }")` |

**RÈGLE** : compte les `(` ouvrants et ferme-les tous par `)`. Les `{}` du JS/HTML sont
à l'INTÉRIEUR de la string Python (entre guillemets) — ils ne ferment jamais l'appel.
