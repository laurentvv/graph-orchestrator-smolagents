// Sleep helper for async animation
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// DOM Elements
const startBtn = document.getElementById('start-btn');
const resetBtn = document.getElementById('reset-btn');
const speedSlider = document.getElementById('speed-slider');
const speedValue = document.getElementById('speed-value');
const comparisonCounter = document.getElementById('comparison-counter');
const barsContainer = document.getElementById('bars-container');

// State
let arr = [];
let isSorting = false;
let comparisons = 0;
let bars = [];

// Generate random array (1-100)
function generateArray(size = 50) {
    arr = Array.from({ length: size }, () => Math.floor(Math.random() * 100) + 1);
    return arr;
}

// Draw bars
function draw() {
    barsContainer.innerHTML = '';
    const maxVal = Math.max(...arr);
    
    arr.forEach((value, index) => {
        const bar = document.createElement('div');
        bar.className = 'bar';
        bar.style.height = `${(value / maxVal) * 250}px`;
        barsContainer.appendChild(bar);
        bars[index] = bar;
    });
}

// Update bar height
function updateBar(index, maxVal) {
    if (bars[index]) {
        bars[index].style.height = `${(arr[index] / maxVal) * 250}px`;
    }
}

// Bubble Sort with animation
async function bubbleSort() {
    if (isSorting) return;
    isSorting = true;
    startBtn.disabled = true;
    comparisons = 0;
    comparisonCounter.textContent = `Comparaisons : ${comparisons}`;
    
    const maxVal = Math.max(...arr);
    let swapped = true;
    
    while (swapped) {
        swapped = false;
        for (let i = 0; i < arr.length - 1; i++) {
            // Mark bars as comparing
            bars[i].classList.add('comparing');
            bars[i + 1].classList.add('comparing');
            
            // Wait for animation speed
            await sleep(speedSlider.value);
            
            // Compare
            if (arr[i] > arr[i + 1]) {
                // Swap values
                [arr[i], arr[i + 1]] = [arr[i + 1], arr[i]];
                comparisons++;
                comparisonCounter.textContent = `Comparaisons : ${comparisons}`;
                swapped = true;
                
                // Sync DOM after swap
                updateBar(i, maxVal);
                updateBar(i + 1, maxVal);
            }
            
            // Remove comparing class
            bars[i].classList.remove('comparing');
            bars[i + 1].classList.remove('comparing');
        }
    }
    
    // Mark all as sorted
    bars.forEach(bar => bar.classList.add('sorted'));
    
    isSorting = false;
    startBtn.disabled = false;
}

// Reset
function reset() {
    isSorting = false;
    startBtn.disabled = false;
    comparisons = 0;
    comparisonCounter.textContent = `Comparaisons : ${comparisons}`;
    generateArray();
    draw();
}

// Event Listeners
startBtn.addEventListener('click', bubbleSort);
resetBtn.addEventListener('click', reset);
speedSlider.addEventListener('input', (e) => {
    speedValue.textContent = e.target.value;
});

// Initialize
generateArray();
draw();
