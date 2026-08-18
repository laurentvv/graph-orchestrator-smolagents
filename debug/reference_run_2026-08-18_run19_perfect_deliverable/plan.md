# Plan de l'Architecte

*Plan ID :* `bubble-sort-visualizer-v1`

**Goal :** Create a vanilla HTML/CSS/JS interactive Bubble Sort visualizer in three separate files (index.html, styles.css, script.js) with no external frameworks or CDNs.

## Architecture globale

Application vanilla HTML/CSS/JS en 3 fichiers séparés (index.html, styles.css, script.js) avec architecture en couches : HTML (structure + DOM), CSS (dark theme + responsive + animations), JS (logique tri + DOM + animation). Pas de framework, pas de CDN. DOM access via IDs définis dans HTML, manipulés dans JS. Animation via requestAnimationFrame + async/await pour le contrôle étape par étape.

## Sous-tâches

### 1. bsv-001 — **Status:** complete

Créer les 3 fichiers du Bubble Sort Visualizer : index.html (structure + IDs DOM), styles.css (dark theme + responsive + animations), script.js (logique Bubble Sort + animation + DOM). Le HTML doit contenir : un conteneur principal avec titre, tableau de barres, contrôles (Start Sort, Reset, Speed Slider, Comparison Counter). Le CSS doit utiliser des variables CSS pour le dark theme, Flexbox/Grid pour le layout, et des transitions fluides. Le JS doit implémenter : génération d'un tableau aléatoire (30 éléments, valeurs 1-100), algorithme Bubble Sort avec async/await et sleep(), mise à jour des hauteurs des barres via requestAnimationFrame, changement de couleur des barres (défaut, comparaison, trié), comptage des comparaisons, gestion des événements (clic boutons, changement slider). Tests : 1) Au chargement, ≥1 barre colorée visible dans le canvas. 2) Clic 'Start Sort' déclenche l'animation étape par étape avec le délai sélectionné. 3) Lors d'une comparaison, les barres concernées changent de couleur vers [Color A]. 4) Après le tri, les barres triées changent vers [Color B]. 5) Le compteur de comparaisons s'incrémente en temps réel. 6) Clic 'Reset' génère un nouveau tableau aléatoire. 7) Le layout s'adapte aux écrans mobiles sans casser la visualisation. 8) Le slider de vitesse change le délai d'animation.

**Fichiers cibles :**
- [x] `index.html`
- [x] `styles.css`
- [x] `script.js`

**Stratégie :** `multifile`
**Skills Coder :** `frontend-design`, `web-animation`, `devtools-preview`

**Critères visuels (Coder) :**
- Au chargement de la page, ≥1 barre colorée VISIBLE dans le canvas (un canvas vide au chargement = BUG critique, pas 'normal')
- Le compteur de comparaisons affiche '0' au chargement
- Les boutons Démarrer/Réinitialiser sont visibles et cliquables
- Le slider de vitesse est visible et fonctionnel
- Le layout est responsive et s'adapte aux écrans mobiles

**Critères fonctionnels (Tester) :**
- Après clic sur Démarrer puis await sleep(400ms), le compteur > 0
- Après fin du tri, le tableau est trié par ordre croissant (vérifier heights)
- Déplacer le slider de vitesse change la valeur affichée à l'écran
- Après clic sur Réinitialiser, un nouveau tableau aléatoire est généré
- Les barres comparées changent de couleur vers [Color A] pendant le tri
- Les barres triées changent de couleur vers [Color B] à la fin

**Rubric Judge :** CRITICAL: barres visibles au chargement + tri correct + couleurs 3 états. HIGH: responsive mobile + dark theme WCAG. MEDIUM: animations fluides (requestAnimationFrame). LOW: code modulaire, pas de pollution globale.
