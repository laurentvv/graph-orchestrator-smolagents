// Configuration
const MAX_VALUE = 100;
const BAR_COUNT = 50;
const COLORS = {
    unprocessed: '#4a4a6a',
    comparing: '#e94560',
    sorted: '#0f3460'
};

// State
let arr = [];
let bars = [];
let isRunning = false;
let comparisons = 0;
let speed = 20;

// DOM Elements
const chart = document.getElementById('chart');
const startBtn = document.getElementById('startBtn');
const resetBtn = document.getElementById('resetBtn');
const speedRange = document.getElementById('speedRange');
const counter = document.getElementById('counter');

// Generate random array
function generateArray() {
    arr = Array.from({ length: BAR_COUNT }, () => Math.floor(Math.random() * MAX_VALUE) + 1);
}

// Create bars
function createBars() {
    chart.innerHTML = '';
    bars = [];
    for (let i = 0; i < arr.length; i++) {
        const bar = document.createElement('div');
        bar.className = 'bar';
        bar.id = `bar-${i}`;
        bar.style.height = '0px';
        chart.appendChild(bar);
        bars.push(bar);
    }
}

// Update bar heights
function updateBars() {
    bars.forEach((bar, i) => {
        const height = (arr[i] / MAX_VALUE) * 240;
        bar.style.height = `${height}px`;
    });
}

// Bubble Sort with animation
async function bubbleSort() {
    isRunning = true;
    startBtn.disabled = true;
    resetBtn.disabled = true;
    comparisons = 0;
    counter.textContent = `Comparaisons : ${comparisons}`;
    
    // Initialize all bars as unprocessed
    bars.forEach(bar => bar.classList.remove('comparing', 'sorted'));
    
    let swapped = true;
    while (swapped) {
        swapped = false;
        for (let i = 0; i < arr.length - 1; i++) {
            if (arr[i] > arr[i + 1]) {
                // Mark as comparing
                bars[i].classList.add('comparing');
                bars[i + 1].classList.add('comparing');
                
                // Wait for speed
                await sleep(speed);
                
                // Swap values
                [arr[i], arr[i + 1]] = [arr[i + 1], arr[i]];
                swapped = true;
                
                // Sync DOM after swap
                updateBar(i);
                updateBar(i + 1);
                
                // Mark swapped bars as sorted
                bars[i].classList.add('sorted');
                bars[i + 1].classList.add('sorted');
            }
        }
        // Remove comparing class
        bars.forEach(bar => bar.classList.remove('comparing'));
    }
    
    // Mark all as sorted
    bars.forEach(bar => bar.classList.add('sorted'));
    
    isRunning = false;
    startBtn.disabled = false;
    resetBtn.disabled = false;
}

// Helper to update a single bar
function updateBar(index) {
    const bar = bars[index];
    const height = (arr[index] / MAX_VALUE) * 240;
    bar.style.height = `${height}px`;
}

// Sleep helper
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Start sorting
function startSort() {
    if (isRunning) return;
    generateArray();
    createBars();
    updateBars();
    bubbleSort();
}

// Reset
function reset() {
    generateArray();
    createBars();
    updateBars();
    comparisons = 0;
    counter.textContent = `Comparaisons : ${comparisons}`;
    isRunning = false;
    startBtn.disabled = false;
    resetBtn.disabled = false;
}

// Event listeners
startBtn.addEventListener('click', startSort);
resetBtn.addEventListener('click', reset);
speedRange.addEventListener('input', (e) => {
    speed = parseInt(e.target.value);
});

// Initialize on load
generateArray();
createBars();
updateBars();
