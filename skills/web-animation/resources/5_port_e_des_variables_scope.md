## 5. Portée des Variables (Scope & Block Scope)
1. **Variables globales vs locales** :
   Fais extrêmement attention aux variables globales vs locales. Si tu as déclaré `let j = 0;` en haut de ton fichier, ne fais jamais `let j = value;` dans ta fonction d'animation, car cela "shadow" la variable globale (crée une copie locale) et tes autres fonctions (comme `draw()`) liront l'ancienne variable globale inchangée.

2. **Block Scope dans les boucles `for (let ...)`** :
   Une variable déclarée avec `let` dans une boucle `for (let c = 0; c < COLS; c++)` est strictement limitée à ce bloc. Ne l'utilise JAMAIS en dehors ou dans une autre boucle sans la redéclarer, sous peine de déclencher un `ReferenceError: c is not defined` qui bloque toute l'exécution du script.