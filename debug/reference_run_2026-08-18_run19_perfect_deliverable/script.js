// Helper pour le délai d'animation
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// État global
let arr = [];
let bars = [];
let isSorting = false;
let comparisonCount = 0;
let speed = 50; // ms par étape

// Éléments DOM
const chartEl = document.getElementById('chart');
const startBtn = document.getElementById('startBtn');
const resetBtn = document.getElementById('resetBtn');
const speedRange = document.getElementById('speedRange');
const counterEl = document.getElementById('counter');

// Générer un tableau aléatoire
function generateArray(size = 30) {
    arr = Array.from({ length: size }, () => Math.floor(Math.random() * 100) + 1);
    return arr;
}

// Dessiner les barres
function draw() {
    chartEl.innerHTML = '';
    bars = [];
    const maxVal = Math.max(...arr);
    
    arr.forEach((value, index) => {
        const bar = document.createElement('div');
        bar.className = 'bar';
        bar.style.height = (value / maxVal) * 250 + 'px';
        chartEl.appendChild(bar);
        bars.push(bar);
    });
}

// Mettre à jour la hauteur d'une barre
function updateBar(index) {
    if (bars[index]) {
        bars[index].style.height = (arr[index] / Math.max(...arr)) * 250 + 'px';
    }
}

// Swap de deux éléments dans le tableau et le DOM
function swap(i, j) {
    [arr[i], arr[j]] = [arr[j], arr[i]];
    updateBar(i);
    updateBar(j);
}

// Algorithme Bubble Sort avec animation pas-à-pas
async function bubbleSort() {
    if (isSorting) return;
    isSorting = true;
    startBtn.disabled = true;
    
    comparisonCount = 0;
    counterEl.textContent = '0';
    
    let swapped = true;
    while (swapped) {
        swapped = false;
        for (let i = 0; i < arr.length - 1; i++) {
            // Marquer les barres en cours de comparaison
            bars[i].classList.add('comparing');
            bars[i + 1].classList.add('comparing');
            
            // Attendre le délai
            await sleep(speed);
            
            // Comparaison
            if (arr[i] > arr[i + 1]) {
                comparisonCount++;
                counterEl.textContent = comparisonCount.toString();
                
                // Swap
                swapped = true;
                swap(i, i + 1);
            }
            
            // Retirer le marquage de comparaison
            bars[i].classList.remove('comparing');
            bars[i + 1].classList.remove('comparing');
        }
    }
    
    // Marquer toutes les barres comme triées
    bars.forEach(bar => bar.classList.add('sorted'));
    
    isSorting = false;
    startBtn.disabled = false;
}

// Initialiser au chargement
function init() {
    generateArray(30);
    draw();
}

// Événements
startBtn.addEventListener('click', bubbleSort);

resetBtn.addEventListener('click', () => {
    if (isSorting) return;
    generateArray(30);
    draw();
});

speedRange.addEventListener('input', (e) => {
    speed = parseInt(e.target.value);
});

// Démarrage
init();
