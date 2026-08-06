---
name: web-animation
description: "Patterns et bonnes pratiques pour les animations JS complexes (requestAnimationFrame, setTimeout, state machines, visualiseurs)."
---

# Skill : Web Animation & Visualizers (JS Vanilla)

Ce skill documente les pièges fréquents et les patterns robustes pour créer des animations interactives ou des visualiseurs d'algorithmes en Javascript vanilla.

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

## 5. Portée des Variables (Scope)
Fais extrêmement attention aux variables globales vs locales.
Si tu as déclaré `let j = 0;` en haut de ton fichier, ne fais jamais `let j = value;` dans ta fonction d'animation, car cela "shadow" la variable globale (crée une copie locale) et tes autres fonctions (comme `draw()`) liront l'ancienne variable globale inchangée.
