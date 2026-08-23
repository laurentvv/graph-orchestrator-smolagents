/**
 * Bubble Sort Visualizer - JavaScript
 * Tri à bulles interactif avec visualisation pas-à-pas
 */

(function() {
  'use strict';

  // Configuration par défaut
  const CONFIG = {
    barWidth: 12,
    barGap: 2,
    colors: {
      comparing: '#3498db',
      sorted: '#2ecc71',
      default: '#9b59b6'
    }
  };

  // État de l'application
  let state = {
    array: [],
    isSorting: false,
    isPaused: false,
    speed: 1000,
    size: 30,
    comparisons: 0,
    swaps: 0,
    startTime: null,
    endTime: null,
    sortedCount: 0,
    comparisonIndex: 0,
    swapIndex: 0
  };

  // Éléments DOM
  const elements = {
    arrayBars: document.getElementById('arrayBars'),
    startBtn: document.getElementById('startBtn'),
    resetBtn: document.getElementById('resetBtn'),
    stepBtn: document.getElementById('stepBtn'),
    speedRange: document.getElementById('speedRange'),
    speedValue: document.getElementById('speedValue'),
    sizeRange: document.getElementById('sizeRange'),
    sizeValue: document.getElementById('sizeValue'),
    compareRange: document.getElementById('compareRange'),
    compareValue: document.getElementById('compareValue'),
    swapRange: document.getElementById('swapRange'),
    swapValue: document.getElementById('swapValue'),
    comparisons: document.getElementById('comparisons'),
    swaps: document.getElementById('swaps'),
    time: document.getElementById('time')
  };

  /**
   * Génère un tableau aléatoire
   */
  function generateRandomArray(size) {
    const array = [];
    for (let i = 0; i < size; i++) {
      array.push(Math.floor(Math.random() * 100) + 1);
    }
    return array;
  }

  /**
   * Dessine le tableau dans le DOM
   */
  function drawArray() {
    elements.arrayBars.innerHTML = '';

    const containerWidth = elements.arrayBars.clientWidth;
    const availableWidth = containerWidth - 20;
    const barWidth = CONFIG.barWidth;
    const barGap = CONFIG.barGap;
    const totalBarWidth = barWidth + barGap;

    const barCount = state.array.length;
    const barWidthPx = Math.max(8, Math.min(30, availableWidth / barCount));

    state.array.forEach((value, index) => {
      const bar = document.createElement('div');
      bar.className = 'bar default';
      bar.style.height = (value * 2) + 'px';
      bar.dataset.index = index;
      bar.dataset.value = value;
      
      // Événement au clic sur une barre
      bar.addEventListener('click', () => handleBarClick(index));
      
      elements.arrayBars.appendChild(bar);
    });
  }

  /**
   * Gère le clic sur une barre
   */
  function handleBarClick(index) {
    if (state.isSorting) return;

    // Sélectionner la barre
    const bars = elements.arrayBars.children;
    if (bars[index]) {
      bars[index].classList.toggle('selected');
    }
  }

  /**
   * Compare deux éléments
   */
  function compareElements(i, j) {
    state.comparisons++;
    elements.comparisons.textContent = state.comparisons;

    const barI = elements.arrayBars.children[i];
    const barJ = elements.arrayBars.children[j];

    // Mettre en classe "comparing"
    barI.classList.add('comparing');
    barJ.classList.add('comparing');

    setTimeout(() => {
      barI.classList.remove('comparing');
      barJ.classList.remove('comparing');
    }, 500);
  }

  /**
   * Échange deux éléments
   */
  function swapElements(i, j) {
    state.swaps++;
    elements.swaps.textContent = state.swaps;

    const temp = state.array[i];
    state.array[i] = state.array[j];
    state.array[j] = temp;

    // Mettre à jour les hauteurs
    updateBarHeights();

    // Mettre en classe "comparing" pendant l'échange
    const barI = elements.arrayBars.children[i];
    const barJ = elements.arrayBars.children[j];
    barI.classList.add('comparing');
    barJ.classList.add('comparing');

    setTimeout(() => {
      barI.classList.remove('comparing');
      barJ.classList.remove('comparing');
    }, 500);
  }

  /**
   * Met à jour les hauteurs des barres
   */
  function updateBarHeights() {
    const bars = elements.arrayBars.children;
    for (let i = 0; i < bars.length; i++) {
      const value = state.array[i];
      bars[i].style.height = (value * 2) + 'px';
      bars[i].dataset.value = value;
    }
  }

  /**
   * Algorithme Bubble Sort principal
   */
  function bubbleSort() {
    const array = [...state.array];
    const n = array.length;
    let swapped = true;

    while (swapped && state.comparisonIndex < n) {
      swapped = false;
      
      for (let i = 0; i < n - 1; i++) {
        if (state.isPaused) break;

        compareElements(i, i + 1);

        if (array[i] > array[i + 1]) {
          swapElements(i, i + 1);
          swapped = true;
          state.swapIndex++;
        }
      }

      // Marquer les éléments triés
      for (let i = 0; i < n; i++) {
        if (state.isPaused) break;
        
        const bar = elements.arrayBars.children[i];
        if (bar && !bar.classList.contains('comparing')) {
          bar.classList.add('sorted');
          state.sortedCount++;
        }
      }

      state.comparisonIndex++;
    }

    // Fin du tri
    finishSorting();
  }

  /**
   * Termine le tri
   */
  function finishSorting() {
    state.isSorting = false;
    state.isPaused = false;
    state.startTime = null;
    state.endTime = null;
    state.comparisonIndex = 0;
    state.swapIndex = 0;

    // Mettre à jour les classes des barres
    const bars = elements.arrayBars.children;
    for (let i = 0; i < bars.length; i++) {
      const value = state.array[i];
      bars[i].className = 'bar sorted';
      bars[i].dataset.value = value;
    }

    // Afficher le temps
    if (state.startTime && state.endTime) {
      const duration = state.endTime - state.startTime;
      elements.time.textContent = duration + 'ms';
    }

    // Désactiver les boutons
    elements.startBtn.disabled = true;
    elements.stepBtn.disabled = true;
  }

  /**
   * Lance le tri
   */
  function startSorting() {
    if (state.isSorting) return;

    state.isSorting = true;
    state.isPaused = false;
    state.comparisons = 0;
    state.swaps = 0;
    state.sortedCount = 0;
    state.comparisonIndex = 0;
    state.swapIndex = 0;

    elements.comparisons.textContent = '0';
    elements.swaps.textContent = '0';
    elements.time.textContent = '0ms';

    // Réinitialiser les classes des barres
    const bars = elements.arrayBars.children;
    for (let i = 0; i < bars.length; i++) {
      bars[i].className = 'bar default';
      bars[i].dataset.value = state.array[i];
    }

    // Démarrer
    state.startTime = performance.now();
    runSortingLoop();
  }

  /**
   * Boucle de tri asynchrone
   */
  async function runSortingLoop() {
    if (!state.isSorting) return;

    // Attendre le délai de vitesse
    await sleep(state.speed);

    // Vérifier si le tri est terminé
    if (state.isPaused || state.comparisonIndex >= state.array.length) {
      finishSorting();
      return;
    }

    // Lancer le tri
    bubbleSort();
    runSortingLoop();
  }

  /**
   * Pause le tri
   */
  function pauseSorting() {
    if (!state.isSorting) return;

    state.isPaused = true;
    elements.startBtn.textContent = '▶ Démarrer le tri';
  }

  /**
   * Résume le tri
   */
  function resumeSorting() {
    if (!state.isSorting) return;

    state.isPaused = false;
    elements.startBtn.textContent = '⏸ Pause';
  }

  /**
   * Étape par étape
   */
  function stepByStep() {
    if (!state.isSorting) return;

    if (state.isPaused) {
      resumeSorting();
    } else {
      pauseSorting();
    }

    // Avancer d'une étape
    state.comparisonIndex++;
    if (state.comparisonIndex < state.array.length) {
      bubbleSort();
    } else {
      finishSorting();
    }
  }

  /**
   * Fonction utilitaire pour le délai
   */
  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * Réinitialise l'application
   */
  function reset() {
    state.isSorting = false;
    state.isPaused = false;
    state.comparisons = 0;
    state.swaps = 0;
    state.sortedCount = 0;
    state.comparisonIndex = 0;
    state.swapIndex = 0;
    state.startTime = null;
    state.endTime = null;

    elements.comparisons.textContent = '0';
    elements.swaps.textContent = '0';
    elements.time.textContent = '0ms';

    // Réinitialiser les classes des barres
    const bars = elements.arrayBars.children;
    for (let i = 0; i < bars.length; i++) {
      bars[i].className = 'bar default';
      bars[i].dataset.value = state.array[i];
    }

    // Désactiver les boutons
    elements.startBtn.disabled = false;
    elements.stepBtn.disabled = false;
    elements.startBtn.textContent = '▶ Démarrer le tri';
  }

  /**
   * Génère un nouveau tableau aléatoire
   */
  function generateNewArray() {
    state.array = generateRandomArray(state.size);
    drawArray();
    reset();
  }

  /**
   * Met à jour les valeurs affichées pour les curseurs
   */
  function updateSliderValues() {
    elements.speedValue.textContent = elements.speedRange.value;
    elements.sizeValue.textContent = elements.sizeRange.value;
    elements.compareValue.textContent = elements.compareRange.value;
    elements.swapValue.textContent = elements.swapRange.value;
  }

  /**
   * Initialisation de l'application
   */
  function init() {
    // Générer le tableau initial
    generateNewArray();

    // Événements pour les boutons
    elements.startBtn.addEventListener('click', () => {
      if (state.isSorting) {
        pauseSorting();
      } else {
        startSorting();
      }
    });

    elements.resetBtn.addEventListener('click', () => {
      generateNewArray();
    });

    elements.stepBtn.addEventListener('click', () => {
      stepByStep();
    });

    // Événements pour les curseurs
    elements.speedRange.addEventListener('input', () => {
      state.speed = parseInt(elements.speedRange.value, 10);
      updateSliderValues();
    });

    elements.sizeRange.addEventListener('input', () => {
      state.size = parseInt(elements.sizeRange.value, 10);
      generateNewArray();
    });

    elements.compareRange.addEventListener('input', () => {
      updateSliderValues();
    });

    elements.swapRange.addEventListener('input', () => {
      updateSliderValues();
    });

    // Événement de redimensionnement pour mettre à jour la largeur
    window.addEventListener('resize', () => {
      drawArray();
    });

    // Initialiser la largeur
    setTimeout(() => {
      drawArray();
    }, 100);
  }

  // Démarrer l'application
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
