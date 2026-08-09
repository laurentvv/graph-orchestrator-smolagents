## ⚠️ RÈGLE CRITIQUE — Hauteurs CSS en pourcentage (failure mode visuel n°1)

Quand tu crées des éléments dynamiques (barres, colonnes, graphiques) dont la hauteur
est proportionnelle à une valeur, NE JAMAIS utiliser `height: X%` SI le container
parent n'a pas de `height` EXPLICITE (pas juste `min-height`).

**Pourquoi** : en CSS, `height: 50%` se calcule par rapport à la hauteur du parent.
Si le parent n'a que `min-height` (ou aucune hauteur), le `%` se résout à `auto` →
**hauteur effective = 0** → élément **invisible**. La page semble vide alors que le JS
a bien créé les éléments.

| ❌ Buggé (invisible) | ✅ Correct (visible) |
|---|---|
| `#viz { min-height: 300px; }` | `#viz { height: 300px; }` |
| `.bar { height: 80%; }` | `.bar { height: 80%; }` (parent a `height`) |
| OU sans % : `.bar { height: calc(...) }` en px | OU `.bar { height: 240px }` (absolu) |

**RÈGLE** : si tu utilises `height: X%` sur un élément, le parent DIRECT doit avoir une
hauteur fixée en `px`, `vh`, ou `%` (avec son propre parent heighté). En cas de doute,
utilise des **px absolus** (`height: ${value * 3}px`) plutôt que des `%`.

**VÉRIFICATION OBLIGATOIRE** : après rendu, vérifie via DevTools
(`evaluate_script`) que `document.querySelectorAll('.bar').length > 0` ET que les
barres ont une hauteur visible (`getBoundingClientRect().height > 0`).
