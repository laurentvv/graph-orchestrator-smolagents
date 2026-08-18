## 6. Calcul de Coordonnées Grille ➔ Pixels (Canvas 2D)

Pour tout affichage sur <canvas> basé sur une grille (Tetris, Snake, Démineur, Pathfinding, Tableaux), respecte impérativement la règle des parenthèses :

`javascript
// ✅ RÈGLE STRICTE DES PARENTHÈSES : (coordonnée_grille + offset) * taille_cellule
// Toujours additionner les coordonnées de grille AVANT de multiplier par la taille en pixels :
const pixelX = (gridX + col) * cellSize;
const pixelY = (gridY + row) * cellSize;

ctx.fillStyle = color;
ctx.fillRect(pixelX, pixelY, cellSize - 1, cellSize - 1);

// ❌ PIÈGE COURANT : gridX + col * cellSize
// La multiplication étant prioritaire en JS, cela calcule gridX + (col * cellSize),
// ce qui écrase tous les éléments dans les premiers pixels du Canvas !
`
