## 2. Pattern A : Animation basée sur `setTimeout` (idéal pour les algorithmes pas-à-pas)
Si tu as un visualiseur d'algorithme (comme un tri à bulle) où tu veux un `delay` paramétrable par l'utilisateur, le plus simple et robuste est d'utiliser `setTimeout` pour s'auto-appeler.

```javascript
// ✅ PATTERN RECOMMANDÉ (Pas-à-pas paramétrable)
function step() {
    if (!isRunning) return; // Garde de sortie
    if (isFinished) {
        // Logique de fin
        return;
    }
    
    // 1. Logique d'avancement d'UNE SEULE étape de l'algorithme
    avancerAlgorithmeDUnPas();
    
    // 2. Mise à jour de l'UI (dessin)
    draw();
    
    // 3. Planification de l'étape suivante
    setTimeout(step, delay); // La boucle s'appelle elle-même proprement
}
```
