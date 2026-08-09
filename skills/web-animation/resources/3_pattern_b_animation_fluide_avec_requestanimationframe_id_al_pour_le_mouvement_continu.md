## 3. Pattern B : Animation fluide avec `requestAnimationFrame` (idéal pour le mouvement continu)
Si tu fais un jeu, un canvas interactif fluide ou une simulation physique, utilise `requestAnimationFrame` en mesurant le delta de temps (`performance.now()`).

```javascript
// ✅ PATTERN AVANCÉ (Mouvement 60 FPS)
let lastTime = 0;
function animate(currentTime) {
    if (!isRunning) return;
    
    const deltaTime = currentTime - lastTime;
    
    if (deltaTime > delay) { // Permet de ralentir artificiellement si besoin
        avancerAlgorithmeDUnPas();
        draw();
        lastTime = currentTime;
    }
    
    requestAnimationFrame(animate); // Synchronisé avec l'écran du navigateur
}
```
