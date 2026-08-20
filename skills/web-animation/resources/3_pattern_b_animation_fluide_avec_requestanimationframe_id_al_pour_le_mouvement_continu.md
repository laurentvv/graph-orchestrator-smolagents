## 3. Pattern B : Animation fluide avec `requestAnimationFrame` (idéal pour le mouvement continu et jeux)
Si tu fais un jeu, un canvas interactif fluide ou une simulation physique, utilise `requestAnimationFrame` en mesurant le delta de temps (`performance.now()`) avec un **accumulateur de temps** pour découpler la physique du taux de rafraîchissement écran :

```javascript
// ✅ PATTERN UNIVERSEL (Boucle 60 FPS avec accumulateur de temps)
let lastTime = performance.now();
let accumulator = 0;

function gameLoop(currentTime) {
    if (!isRunning) return;
    
    const deltaTime = currentTime - lastTime;
    lastTime = currentTime;
    accumulator += deltaTime;
    
    // Mise à jour logique à pas fixe (ex: tickInterval = 1000ms ou 50ms)
    while (accumulator >= tickInterval) {
        accumulator -= tickInterval;
        updateLogicOrStep(); // avance la logique (physique, déplacement, etc.)
    }
    
    draw(); // Rendu graphique fluide à chaque frame
    requestAnimationFrame(gameLoop); // Synchronisé avec l'écran
}

// Initialisation au démarrage :
lastTime = performance.now();
accumulator = 0;
requestAnimationFrame(gameLoop);
```

