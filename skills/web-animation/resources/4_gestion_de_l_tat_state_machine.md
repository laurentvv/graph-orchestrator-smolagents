## 4. Gestion de l'état (State Machine)
Un algorithme complexe (comme un tri) contient des boucles imbriquées (`for` dans un `for`).
Dans une animation pas-à-pas, **tu ne peux pas utiliser de vraies boucles `for` ou `while`**, sinon l'algorithme s'exécute d'un coup en une milliseconde.

**Solution : "Dérouler" les boucles en variables d'état globales.**
Au lieu de :
```javascript
for (let i = 0; i < n; i++) {
    for (let j = 0; j < n - i - 1; j++) {
        // Swap
    }
}
```
Fais ceci :
```javascript
let i = 0;
let j = 0;

function step() {
    // Équivalent de la condition d'arrêt de la boucle externe
    if (i >= n) {
        finish();
        return;
    }
    
    // Équivalent de la condition d'arrêt de la boucle interne
    if (j >= n - i - 1) {
        i++; // Incrémente boucle externe
        j = 0; // Reset boucle interne
        setTimeout(step, delay); // Passe direct à l'itération suivante
        return;
    }
    
    // ... Logique de swap utilisant i et j ...
    
    j++; // Incrémente boucle interne
    setTimeout(step, delay);
}
```
