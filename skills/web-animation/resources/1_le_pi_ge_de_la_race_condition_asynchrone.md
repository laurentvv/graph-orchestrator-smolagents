## 1. Le Piège de la Race Condition Asynchrone
**Règle d'or : NE MÉLANGE JAMAIS `setTimeout` et `requestAnimationFrame` dans la même boucle.**

Si tu écris ceci :
```javascript
// ❌ ANTI-PATTERN MORTEL
function step() {
    setTimeout(swap, delay); // Planifie une action dans le futur
    requestAnimationFrame(step); // Relance instantanément la boucle à la frame suivante !
}
```
Tu vas créer des centaines de boucles parallèles en quelques millisecondes. Les `setTimeout` vont s'empiler, écraser les variables locales/globales, et le navigateur va freezer ou l'animation sera chaotique.
