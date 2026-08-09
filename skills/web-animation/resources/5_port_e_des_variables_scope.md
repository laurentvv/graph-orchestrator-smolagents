## 5. Portée des Variables (Scope)
Fais extrêmement attention aux variables globales vs locales.
Si tu as déclaré `let j = 0;` en haut de ton fichier, ne fais jamais `let j = value;` dans ta fonction d'animation, car cela "shadow" la variable globale (crée une copie locale) et tes autres fonctions (comme `draw()`) liront l'ancienne variable globale inchangée.