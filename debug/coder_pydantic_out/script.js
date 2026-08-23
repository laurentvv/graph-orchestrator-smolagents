// Configuration et état de l'application
const CONFIG = {
  maxArraySize: 50,
  minDelay: 10,
  maxDelay: 500,
  barWidth: 30,
  barGap: 8,
  containerHeight: 250,
  colors: {
    default: '#6c757d',
    comparing: '#f6ad55',
    sorted: '#4ecca2'
  }
};

// État de l'application
let state = {
  array: [],
  isSorting: false,
  comparisons: 0,
  swaps: 0,
  startTime: null,
  animationDelay: 100,
  sortedIndex: 0,
  currentIndex: 0
};

// Éléments du DOM
const elements = {
  arrayContainer: document.getElementById('arrayContainer'),
  speedRange: document.getElementById('speedRange'),
  speedValue: document.getElementById('speedValue'),
  startBtn: document.getElementById('startBtn'),
  resetBtn: document.getElementById('resetBtn'),
  comparisonsCount: document.getElementById('comparisonsCount'),
  swapsCount: document.getElementById('swapsCount'),
  timeCount: document.getElementById('timeCount')
};

// Initialisation
function init() {
  createArray();
  bindEvents();
  updateUI();
}

// Création d'un tableau aléatoire
function createArray() {
  const size = Math.min(CONFIG.maxArraySize, Math.floor(Math.random() * 30) + 10);
  state.array = Array.from({ length: size }, () => Math.floor(Math.random() * 100) + 1);
  state.sortedIndex = 0;
  state.currentIndex = 0;
  state.isSorting = false;
  state.comparisons = 0;
  state.swaps = 0;
  state.startTime = null;
  
  renderArray();
  updateUI();
}

// Lien des événements
function bindEvents() {
  elements.startBtn.addEventListener('click', toggleSort);
  elements.resetBtn.addEventListener('click', createArray);
  
  elements.speedRange.addEventListener('input', (e) => {
    const delay = parseInt(e.target.value, 10);
    state.animationDelay = delay;
    elements.speedValue.textContent = delay;
  });
}

// Affichage des statistiques
function updateUI() {
  elements.comparisonsCount.textContent = state.comparisons;
  elements.swapsCount.textContent = state.swaps;
  elements.timeCount.textContent = state.startTime ? Math.round((Date.now() - state.startTime) / 1000) : 0;
}

// Rendu du tableau
function renderArray() {
  elements.arrayContainer.innerHTML = '';
  
  state.array.forEach((value, index) => {
    const bar = document.createElement('div');
    bar.className = 'bar';
    bar.style.height = `${(value / 100) * CONFIG.containerHeight}px`;
    bar.style.backgroundColor = getBarColor(index);
    bar.setAttribute('data-value', value);
    elements.arrayContainer.appendChild(bar);
  });
}

// Obtention de la couleur d'une barre
function getBarColor(index) {
  if (index >= state.sortedIndex) {
    return CONFIG.colors.sorted;
  }
  if (state.isSorting && state.currentIndex === index && state.currentIndex < state.array.length - 1) {
    return CONFIG.colors.comparing;
  }
  return CONFIG.colors.default;
}

// Démarrage/arrêt du tri
function toggleSort() {
  if (state.isSorting) {
    stopSort();
  } else {
  startSort();
  }
}

// Démarrage du tri
function startSort() {
  if (state.isSorting) return;
  
  state.isSorting = true;
  state.startTime = Date.now();
  state.currentIndex = 0;
  state.sortedIndex = 0;
  elements.startBtn.disabled = true;
  elements.resetBtn.disabled = true;
  
  performBubbleSort();
}

// Arrêt du tri
function stopSort() {
  state.isSorting = false;
  elements.startBtn.disabled = false;
  elements.resetBtn.disabled = false;
  updateUI();
}

// Algorithme Bubble Sort principal
function performBubbleSort() {
  const arrayLength = state.array.length;
  
  for (let i = 0; i < arrayLength - 1; i++) {
    for (let j = 0; j < arrayLength - 1 - i; j++) {
      if (j === state.currentIndex) {
        // Barre en cours de comparaison
        renderArray();
      }
      
      state.comparisons++;
      updateUI();
      
      if (state.array[j] > state.array[j + 1]) {
        // Échange nécessaire
        [state.array[j], state.array[j + 1]] = [state.array[j + 1], state.array[j]];
        state.swaps++;
        updateUI();
        
        if (j + 1 === state.sortedIndex) {
          state.sortedIndex++;
        }
      }
      
      state.currentIndex = j;
      
      if (j === arrayLength - 2) {
        // Dernière comparaison de la passe
        renderArray();
        
        if (state.array[j] > state.array[j + 1]) {
          // Échange effectué
          [state.array[j], state.array[j + 1]] = [state.array[j + 1], state.array[j]];
          state.swaps++;
          updateUI();
          
          if (j + 1 === state.sortedIndex) {
            state.sortedIndex++;
          }
        }
        
        state.currentIndex = j + 1;
        
        // Délai avant la prochaine itération
        const delay = Math.max(CONFIG.minDelay, state.animationDelay);
        setTimeout(() => {
          if (state.isSorting) {
            performBubbleSort();
          }
        }, delay);
      }
    }
    
    if (state.isSorting) {
      renderArray();
    }
  }
  
  // Tri terminé
  if (state.isSorting) {
    stopSort();
  }
}

// Initialisation au chargement de la page
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
