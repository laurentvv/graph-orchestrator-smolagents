## Fichier : index.html

**Structure :**
- `<div id="container">` conteneur principal flex
- `<h1 id="title">` titre "Bubble Sort Visualizer"
- `<div id="chart">` conteneur des barres (flex, gap)
- `<div id="controls">` flex row avec :
  - `<button id="startBtn">` Start Sort
  - `<button id="resetBtn">` Reset
  - `<input id="speedRange" type="range" min="1" max="100">` slider vitesse
  - `<span id="counter">` compteur comparaisons
- `<script src="script.js"></script>`

**IDs DOM exacts :** container, title, chart, startBtn, resetBtn, speedRange, counter

**Initialisation :** appeler `generateArray()` au chargement pour afficher ≥1 barre immédiatement.

---

## Fichier : styles.css

**Thème sombre avec variables CSS :**
- `--bg: #1a1a2e`, `--bar-default: #6366f1`, `--comparing: #f59e0b`, `--sorted: #10b981`, `--text: #e2e8f0`
- Body : bg `--bg`, text `--text`, font sans-serif, margin 0, padding 20px
- `#container` : display flex, flex-direction column, align-items center, max-width 900px, margin auto
- `#chart` : display flex, gap 4px, height 200px, align-items flex-end, overflow-x auto
- `.bar` : width 20px, min-width 20px, transition height 0.3s ease, transition background-color 0.3s ease, border-radius 3px 3px 0 0, flex 1
- `#controls` : display flex, gap 12px, align-items center, margin-top 20px, flex-wrap wrap
- `#startBtn` : bg `--sorted`, color white, padding 10px 20px, border none, border-radius 6px, cursor pointer, font-weight bold
- `#resetBtn` : bg `--comparing`, color white, padding 10px 20px, border none, border-radius 6px, cursor pointer
- `#speedRange` : width 150px
- `#counter` : font-size 16px, color `--text`
- **Responsive :** `@media (max-width: 600px)` → max-width 100%, padding 10px, gap 2px, bar width 15px, font-size 14px

---

## Fichier : script.js

**Variables globales :**
- `arr = []` tableau de valeurs
- `isSorting = false` verrouillage pendant le tri
- `speed = 50` délai par défaut (ms)
- `comparisons = 0` compteur
- `N = 30` nombre d'éléments
- `maxVal = 100` valeur max

**Fonctions :**

1. **`generateArray()`**
   - Créer tableau `arr` de N valeurs aléatoires entre 1 et maxVal
   - Appeler `draw()` pour afficher les barres
   - Reset `comparisons = 0`

2. **`draw()`**
   - Nettoyer `#chart`
   - Pour chaque valeur dans `arr` :
     - Créer `<div class="bar">` avec `style.height = value + 'px'`
     - Ajouter au `#chart`
   - Utiliser `requestAnimationFrame` pour sync DOM après chaque ajout

3. **`bubbleSort()`**
   - Vérifier `!isSorting`, sinon return
   - Appeler `startBtn.disabled = true`
   - Boucle externe `while (true)` :
     - `let swapped = false`
     - Boucle interne `for (i = 0; i < arr.length - 1; i++)` :
       - Incrémenter `comparisons`
       - Si `arr[i] > arr[i+1]` :
         - Changer couleur des barres i et i+1 vers `--comparing`
         - Échanger `arr[i]` et `arr[i+1]`
         - Mettre à jour `bar.style.height` des deux barres correspondantes
         - `swapped = true`
       - `await sleep(speed)`
     - Si `!swapped` → break
   - Changer toutes les barres vers `--sorted`
   - Appeler `draw()` pour sync final
   - Appeler `startBtn.disabled = false`

4. **`sleep(ms)`**
   - `return new Promise(r => setTimeout(r, ms))`

5. **Event listeners :**
   - `startBtn` → `bubbleSort()`
   - `resetBtn` → `generateArray()`
   - `speedRange` → `speed = parseInt(this.value)`

**Edge cases :**
- Verrouillage `isSorting` empêche double clic Start Sort
- `await sleep` avec 1 itération par appel async (pas de boucle for complète)
- Sync DOM après chaque swap (hauteur + couleur)
- Init : `generateArray()` au chargement → ≥1 barre visible
- Responsive : layout s'adapte sans casser la visualisation