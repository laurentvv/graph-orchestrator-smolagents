---
id: bubble-sort-multifile-v6
title: Bubble Sort Visualizer (vanilla, multi-fichier)
purpose: >
  Prompt canonique de validation E2E du coding workflow (AGENTS.md §7 et §10).
  Borné, "1 livrable testable = 1 fichier", vanilla (pas de framework). Le Golden Run
  de référence (Qwen-4B) est archivé dans debug/reference_run_qwen4b_bubble_sort/.
target_files:
  - index.html
  - styles.css
  - script.js
expected_skill_finder: none
  # Tâche vanilla : frontend-design + devtools-preview + context7 couvrent le besoin.
  # Le ReAct F-82 DOIT répondre "Aucun skill ajouté" (pas d'install inutile). Sert donc
  # aussi de témoin "négatif" pour valider que le Skill Finder ne sur-déclenche pas.
---

Crée un visualiseur d'algorithme Bubble Sort (tri à bulles) interactif en HTML/CSS/JS vanilla, réparti sur TROIS fichiers séparés : index.html (structure + lien vers le CSS et le JS), styles.css (tout le style), script.js (toute la logique). Pas de framework ni de CDN externe.

L'interface doit montrer un tableau de barres verticales (hauteurs proportionnelles aux valeurs) qui s'animent pendant le tri. Fonctionnalités attendues :
- un bouton « Démarrer le tri » qui lance l'animation pas-à-pas de Bubble Sort avec un délai visible entre chaque comparaison/échange ;
- un bouton « Réinitialiser » qui génère un nouveau tableau aléatoire ;
- un curseur/slidebar pour régler la vitesse d'animation ;
- un compteur affichant le nombre de comparaisons effectuées ;
- un code couleur clair : barre en cours de comparaison = une couleur, barre déjà triée = une autre couleur, barres non encore traitées = couleur par défaut.

Contraintes techniques : index.html doit référencer styles.css via <link> et script.js via <script src>. Le JS accède au DOM via les ids définis dans le HTML. Design soigné, responsive, avec un thème sombre (dark mode).
