// Helper fonction pour le délai d'animation
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Configuration
const canvas = document.getElementById('chart');
const ctx = canvas.getContext('2d');
const startBtn = document.getElementById('startBtn');
const resetBtn = document.getElementById('resetBtn');
const speedRange = document.getElementById('speedRange');
const speedLabel = document.getElementById('speedLabel');
const counter = document.getElementById('counter');

// Variables d'état
let arr = [];
let bars = [];
let isSorting = false;
let comparisons = 0;
let speed = 320; // ms par étape (défaut, ajusté par slider)

// Dimensions du canvas
const canvasWidth = canvas.width;
const canvasHeight = canvas.height;
const barWidth = canvasWidth / 30; // 30 barres
const maxHeight = canvasHeight - 40;

// Génération d'un tableau aléatoire
function generateArray() {
    arr = [];
    for (let i = 0; i < 30; i++) {
        arr.push(Math.floor(Math.random() * 100) + 1);
    }
}

// Dessin des barres
function draw() {
    ctx.clearRect(0, 0, canvasWidth, canvasHeight);
    
    bars.forEach((bar, index) => {
        const barHeight = (arr[index] / 100) * maxHeight;
        const x = index * barWidth;
        const y = canvasHeight - barHeight;
        
        ctx.fillStyle = bar.color;
        ctx.fillRect(x, y, barWidth - 1, barHeight);
    });
}

// Mise à jour d'une barre spécifique
function updateBar(index) {
    const bar = bars[index];
    bar.color = '#454545';
    bar.height = (arr[index] / 100) * maxHeight;
    bar.y = canvasHeight - bar.height;
}

// Algorithme Bubble Sort avec animation
async function bubbleSort() {
    if (isSorting) return;
    isSorting = true;
    comparisons = 0;
    counter.textContent = comparisons;
    
    // Initialiser les barres avec la couleur non triée
    bars.forEach(bar => {
        bar.color = '#454545';
    });
    
    // S'assurer que bars est initialisé
    if (bars.length === 0) {
        bars = [];
        for (let i = 0; i < arr.length; i++) {
            bars.push({
                index: i,
                color: '#454545',
                height: (arr[i] / 100) * maxHeight,
                y: canvasHeight - (arr[i] / 100) * maxHeight
            });
        }
    }
    
    // Marquer toutes les barres comme non triées
    bars.forEach(bar => {
        bar.sorted = false;
    });
    
    let swapped = true;
    while (swapped) {
        swapped = false;
        for (let i = 0; i < arr.length - 1; i++) {
            if (arr[i] > arr[i + 1]) {
                // Marquer les barres en cours de comparaison
                bars[i].color = '#ffb74d';
                bars[i + 1].color = '#ffb74d';
                
                comparisons++;
                counter.textContent = comparisons;
                
                // Swap
                [arr[i], arr[i + 1]] = [arr[i + 1], arr[i]];
                
                // Sync DOM après swap
                updateBar(i);
                updateBar(i + 1);
                
                swapped = true;
            }
        }
        
        // Attendre avant de continuer
        await sleep(320 - speed * 2);
        
        // Marquer les barres comme non comparées
        for (let j = 0; j < arr.length - 1; j++) {
            bars[j].color = '#454545';
            bars[j + 1].color = '#454545';
        }
    }
    
    // Marquer toutes les barres comme triées
    bars.forEach(bar => {
        bar.color = '#66bb6a';
        bar.sorted = true;
    });
    draw();
    
    isSorting = false;
}

// Initialisation au chargement
function init() {
    generateArray();
    bars = [];
    for (let i = 0; i < arr.length; i++) {
        bars.push({
            index: i,
            color: '#454545',
            height: (arr[i] / 100) * maxHeight,
            y: canvasHeight - (arr[i] / 100) * maxHeight
        });
    }
    draw();
    counter.textContent = comparisons;
}

// Gestion des événements
startBtn.addEventListener('click', async () => {
    if (isSorting) return;
    await bubbleSort();
});

resetBtn.addEventListener('click', () => {
    if (isSorting) return;
    generateArray();
    bars = [];
    for (let i = 0; i < arr.length; i++) {
        bars.push({
            index: i,
            color: '#454545',
            height: (arr[i] / 100) * maxHeight,
            y: canvasHeight - (arr[i] / 100) * maxHeight
        });
    }
    draw();
    comparisons = 0;
    counter.textContent = comparisons;
});

speedRange.addEventListener('input', (e) => {
    speed = parseInt(e.target.value) * 50;
    speedLabel.textContent = e.target.value;
});

// Lancer l'initialisation au chargement
init();
