## Objectif
Créer un visualiseur interactif de l'algorithme Bubble Sort (tri à bulles) en HTML/CSS/JS
vanilla (un seul fichier index.html). L'utilisateur doit voir le tri s'animer en temps réel.

## Fonctionnalités attendues
- Bouton « Démarrer le tri » qui lance l'animation pas-à-pas de Bubble Sort avec un délai visible entre chaque comparaison/échange
- Bouton « Réinitialiser » qui génère un nouveau tableau aléatoire
- Curseur/slidebar pour régler la vitesse d'animation
- Compteur affichant le nombre de comparaisons effectuées pendant le tri
- Code couleur clair : barre en cours de comparaison = une couleur, barre déjà triée = une autre couleur, barres non traitées = couleur par défaut

## Contraintes techniques
HTML5/CSS3/JS vanilla, un seul fichier index.html, pas de framework ni CDN externe.
Design soigné, responsive, thème sombre (dark mode).
ATTENTION CRITIQUE : JavaScript PUR dans la balise <script>. JAMAIS d'annotations
TypeScript (: type, as Cast, : void, interface). Une seule annotation TS fait échouer
TOUT le script (SyntaxError au parsing).

## Critères de validation
- Le tableau est trié après exécution complète du tri (assertion sur l'ordre final)
- Les barres s'animent visuellement pendant le tri
- Le compteur de comparaisons affiche une valeur > 0 après le tri
- Le slider de vitesse MODIFIE réellement la vitesse (event listener branché)
- Les boutons Start et Reset déclenchent leurs actions (event listeners branchés)
