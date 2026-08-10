## Fichier : index.html
- Structure : `<div id="container">` avec `<h1>Bubble Sort</h1>`, `<div id="chart">` (canvas ou div), `<div id="controls">` avec `<button id="startBtn">`, `<button id="resetBtn">`, `<input id="speedRange" type="range">`, `<span id="counter">`
- `<link href="styles.css">` + `<script src="script.js">`
- Canvas : id="chart", width/height 600x400
- IDs DOM : startBtn, resetBtn, speedRange, counter, chart

## Fichier : styles.css
- Thème sombre : bg #1a1a2e, texte #e0e0e0, canvas bg #16213e
- Layout flex vertical pour controls, canvas plein écran
- .bar : div avec transition height 0.3s, width 10px, margin 2px, bg #0f3460
- 3 classes d'état :
  - .comparing : bg #e94560 (rouge)
  - .sorted : bg #0f3460 → #533483 (violet)
  - .default : bg #0f3460 (bleu foncé)
- #counter : font monospace, color #e94560

## Fichier : script.js
- Variables : arr[] (tableau de nombres), isSorting (bool), speed (ms), comparisons (int), N=50, barWidth=10, barGap=2
- generateArray() : crée N valeurs aléatoires 1-100, appelle draw()
- draw() : pour chaque valeur, crée div.bar avec height = (valeur/100)*canvas.height, ajoute classe .default, met à jour DOM
- bubbleSort() : async, boucle while(swapped) avec await sleep(speed) à chaque itération :
  - swapped = false
  - boucle i de 0 à arr.length-1 :
    - ajouter classe .comparing aux bars[i] et bars[i+1]
    - si arr[i] > arr[i+1] : swap(arr[i], arr[i+1]), mettre à jour DOM (bar.style.height), ajouter classe .sorted aux deux, sinon ajouter .default
    - await sleep(speed)
  - si swapped=false → break
- Event listeners :
  - startBtn → bubbleSort()
  - resetBtn → generateArray()
  - speedRange → update speed variable
- Init : generateArray() au chargement (barres visibles immédiatement)
- Canvas : utiliser fillRect pour fond, puis dessiner chaque bar avec rect(x, canvas.height - barHeight, barWidth, barHeight)