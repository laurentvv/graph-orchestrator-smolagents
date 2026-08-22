[TICKET BUG — iteration 2 — échec checklist visuelle, critère 5 en ÉCHEC (verdict=False)]

Critère 5 : « Les barres triées affichent une couleur distincte (ex: vert) des barres en
cours de comparaison (ex: orange) et des barres non traitées (ex: bleu) » — votre propre
audit visual_check a répondu NON 3 fois de suite. Diagnostic précis des 4 défauts dans
script.js (fusion Static Tester + lecture du code) :

1. Le compteur de comparaisons n'est incrémenté QUE dans le bloc `if (arr[i] > arr[i + 1])`
   (swap). Une comparaison a lieu pour CHAQUE paire examinée : `comparisons++` doit être
   exécuté pour chaque paire i, i+1 examinée, swap ou pas.

2. La classe `comparing` n'est ajoutée QUE si un swap suit. Deux barres en cours de
   COMPARAISON doivent être marquées `.comparing` à CHAQUE comparaison (avant le test
   d'échange), puis démarquées après — qu'il y ait swap ou non.

3. `bars.forEach(bar => bar.classList.add('sorted'))` est DANS la boucle `while (swapped)` :
   à la fin de la PREMIÈRE passe, TOUTES les barres passent en « trié » alors que le tri
   n'est pas fini. Le marquage `sorted` doit être PROGRESSIF : après chaque passe, seule
   la barre définitivement à sa place (l'élément remonté en fin de tableau, index
   arr.length - 1 - passe) reçoit `.sorted` ; le marquage complet ne vient qu'à la fin.

4. `updateBar()` fait `bar.className = 'bar default'` : ça ÉCRASE les classes `sorted` et
   `comparing` des barres lors de chaque échange. Il faut préserver l'état : ne réinitialiser
   la classe que si la barre n'est ni `.sorted` ni `.comparing`, ou reconstruire la classe
   selon l'état courant de la barre.

Contrat visuel attendu (styles.css doit définir 3 couleurs distinctes, ex: défaut bleu,
comparing orange, sorted vert) : pendant le tri on doit VOIR simultanément les 3 états ;
le fond reste sombre.
