## ⚠️ RÈGLE CRITIQUE — Animations JS et Boucles bloquantes (failure mode timeout n°1)

Quand tu crées un visualiseur d'algorithme (comme un tri) ou toute animation en JS, **NE JAMAIS UTILISER DE BOUCLE `while` OU `for` CONTINUE/BLOQUANTE**.
Le navigateur n'a qu'un seul thread. Une boucle `while (swapped)` ou un `for` lourd bloque l'Event Loop. Le DOM ne se mettra jamais à jour visuellement, la page gèlera, et le Tester (Puppeteer) plantera sur un timeout de 120 secondes.

**RÈGLE OBLIGATOIRE** : Pour toute animation, ton algorithme DOIT libérer le Main Thread à chaque étape. Utilise une fonction asynchrone avec un délai manuel :
`const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));`
Puis dans tes boucles : `await sleep(vitesse);`. Sans ça, l'agent de test échouera à voir la moindre animation.

### Granularité de la fonction de step (complément indispensable)

La règle ci-dessus porte sur le **threading** (libérer le Main Thread). Il en manque une
seconde, sur la **structure** : la fonction appelée à chaque étape (`step`, `tick`,
`performStep`, le callback de `requestAnimationFrame`) ne doit avancer que d'**UNE SEULE**
étape de l'algorithme par appel — **JAMAIS** contenir les boucles `for`/`while` complètes
de l'algorithme.

Pourquoi : si tu mets la totalité de l'algorithme dans la fonction de step, tout
s'exécute en un seul tick JS. Le navigateur ne repeint qu'après → l'utilisateur ne voit que
l'état final, le `delay`/slider de vitesse ne contrôle plus rien, et le Static Tester Tier 3
détectera une animation « instantanée » (bug).

**Pattern correct (abstrait)** : conserve l'état de progression (indices, données) dans des
variables persistantes hors de la fonction. À chaque appel, avance d'**un seul pas** de
l'algorithme, mets à jour le rendu, puis re-programme la frame suivante :
```js
// état persistant hors de la fonction (adapte à TON algorithme)
function step() {
  if (estTermine()) { terminer(); return; }
  avancerUnSeulPas();      // UNE étape de l'algorithme, pas tout
  rendre();                // met à jour le DOM
  requestAnimationFrame(step);  // re-programme la frame suivante
}
```
Avec `await sleep(vitesse)` dans une boucle `async`, l'équivalent est une boucle qui `await`
à chaque itération — mais **une seule itération par `await`**, jamais l'algorithme complet
d'un bloc.
