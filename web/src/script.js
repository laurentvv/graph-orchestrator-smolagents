/**
 * Tetris Game Core Logic Model (script.js)
 * Defines data structures, initializes the game state, and sets up the main loop using Canvas 2D context.
 */

// --- Constants ---
const CANVAS_WIDTH = 400; // Standard width for visualization
const CANVAS_HEIGHT = 600; // Standard height for visualization
const BLOCK_SIZE = 30;

// Colors corresponding roughly to the original Tetromino colors (optional, but helpful)
const COLORS = {
    'I': 'cyan',
    'J': 'blue',
    'L': 'orange',
    'O': 'yellow',
    'S': 'green',
    'T': 'purple',
    'Z': 'red'
};

// --- 1. PIECE SHAPES DEFINITION (Sprites/Tetromino Shapes) ---
const TETROMINO_SHAPES = {
    'I': [
        { r: -1, c: 0 }, // Adjusted to be relative to grid center for easier placement
        { r: 0, c: -1 },
        { r: 0, c: 0 },
        { r: 0, c: 1 }
    ],
    'J': [
        { r: 0, c: 0 },
        { r: 1, c: 0 },
        { r: 2, c: 0 },
        { r: 0, c: -1 }
    ],
    'L': [
        { r: 0, c: 0 },
        { r: 1, c: 0 },
        { r: 2, c: 0 },
        { r: 2, c: 1 }
    ],
    'O': [
        { r: 0, c: 0 },
        { r: 0, c: 1 },
        { r: 1, c: 0 },
        { r: 1, c: 1 }
    ],
     // Other shapes would be added here (S, T, Z)
};

/**
 * Represents a piece instance in the board.
 */
class Tetromino {
    constructor(shapeKey, initialPosition) {
        this.shape = TETROMINO_SHAPES[shapeKey];
        this.position = initialPosition; // e.g., {row: 0, col: 3} - Board coordinates
        this.type = shapeKey;
    }

    // Method to get absolute grid coordinates of the piece blocks
    getAbsoluteGridCoords() {
        return this.shape.map(offset => ({
            r: this.position.row + offset.r,
            c: this.position.col + offset.c
        }));
    } 

    // Checks a hypothetical position for collision against the board *state* and walls
    checkCollisionAt(board, shapeToTest = this.shape, posToTest = this.position) {
        return shapeToTest.some(offset => {
            const nextRow = posToTest.row + offset.r;
            const nextCol = posToTest.col + offset.c;

            // 1. Check Bounds Collision (Walls and Floor)
            if (nextCol < 0 || nextCol >= board.width) {
                return true; // Wall collision
            }
            const floorReached = nextRow >= board.height;
            if (floorReached) return true;

            // 2. Check Occupancy Collision (Settled Blocks)
            if (nextRow >= 0 && nextRow < board.height && board.grid[nextRow] && board.grid[nextRow][nextCol] !== 'empty') {
                 return true; // Bump into settled block
            }

            return false;
        });
    }

    // Generate a new rotated shape array (90 degrees clockwise)
    getRotatedShape() {
        if (this.type === 'O') return this.shape; // O piece doesn't rotate
        return this.shape.map(offset => ({
            r: offset.c,
            c: -offset.r
        }));
    }
}

// --- 2. EMPTY 2D BOARD STRUCTURE ---
class Board {
    constructor(width = CANVAS_WIDTH / BLOCK_SIZE, height = CANVAS_HEIGHT / BLOCK_SIZE) {
        this.width = width; // Grid columns
        this.height = height; // Grid rows
        // Initialize the board with 'empty' or 0s. Use strings for simplicity in state tracking.
        this.grid = Array(height).fill(null).map(() => Array(width).fill('empty'));
    }

    isWithinBounds(row, col) {
        return row >= 0 && row < this.height && col >= 0 && col < this.width;
    }

    // Updates the grid when a piece settles or moves
    lockPiece(piece) {
        const cells = piece.getAbsoluteGridCoords();
        cells.forEach(({ r, c }) => {
            if (this.isWithinBounds(r, c)) {
                this.grid[r][c] = piece.type;
            }
        });
    }
}

// --- 3. GAME STATE AND CANVAS SETUP ---
const GameState = {
    board: null,
    currentPiece: null,
    score: 0,
    isGameOver: false,
    lastTime: 0, // For timing the game loop in ms
    animationFrameId: null,
    canvas: null,
    ctx: null,
    gravityTimer: 0, // Tracks time before gravity should pull the piece down (e.g., 500ms)

    init() {
        // --- CANVAS INITIALIZATION ---
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'tetris-canvas';
        this.canvas.width = CANVAS_WIDTH;
        this.canvas.height = CANVAS_HEIGHT;
        document.getElementById('root').appendChild(this.canvas); // Assuming #root exists in index.html

        this.ctx = this.canvas.getContext('2d');
        if (!this.ctx) {
            console.error("Error: Could not initialize 2D context.");
            return;
        }

        // Set up the board structure (using grid dimensions, not pixel size directly for logic)
        const gWidth = Math.ceil(CANVAS_WIDTH / BLOCK_SIZE);
        const gHeight = Math.ceil(CANVAS_HEIGHT / BLOCK_SIZE);
        this.board = new Board(gWidth, gHeight);

        // Initial state setup
        this.score = 0;
        this.isGameOver = false;

        console.log("Game initialized. Grid dimensions:", this.board.width, "x", this.board.height);

        // Spawn first piece (e.g., a random 'I' or fixed starting piece)
        const initialPosition = { row: 0, col: Math.floor(this.board.width / 2) - 1 }; // Start near top center
        this.currentPiece = new Tetromino('I', initialPosition);

        // Start the game loop with rendering set up
        if (window.requestAnimationFrame) {
            this.lastTime = performance.now();
            this.animationFrameId = requestAnimationFrame((time) => this.gameLoop(time));
        } else {
             console.error("Browser does not support requestAnimationFrame.");
        }
    },

    // --- 4. CORE GAME LOOP (requestAnimationFrame) ---
    gameLoop(currentTime) {
        if (this.isGameOver) return;

        const deltaTime = currentTime - this.lastTime;
        this.lastTime = currentTime;
        this.gravityTimer += deltaTime;


        // 1. Update piece state based on time/input
        if (!this.currentPiece) {
            return requestAnimationFrame((time) => this.gameLoop(time));
        }

        // Simple gravity implementation (pull down every X ms)
        const fallSpeed = 500; // Milliseconds per step
        if (this.gravityTimer >= fallSpeed) {
            this.tryMovePiece({ row: 1, col: 0 }); // Try moving down
            this.gravityTimer -= fallSpeed;
        }

        // 2. Rendering logic
        this.drawGame(); 

        this.animationFrameId = requestAnimationFrame((time) => this.gameLoop(time));
    },

    // --- MOVEMENT LOGIC (Simplified) ---
    tryMovePiece(offset) {
        const nextPos = {
            row: this.currentPiece.position.row + offset.r,
            col: this.currentPiece.position.col + offset.c
        };

         if (this.currentPiece.checkCollisionAt(this.board, this.currentPiece.shape, nextPos)) {
            // Collision detected: lock piece and spawn new one if not game over
            const crashed = !!offset.r || this.gravityTimer >= 500; // Did it crash downwards?

             if (crashed && offset.r > 0) {
                 this.board.lockPiece(this.currentPiece);
                 this.spawnNewPiece(); // Move to the next piece
             } 
             // If we crashed horizontally, do nothing

        } else {
            // Successful move
            this.currentPiece.position = nextPos;
        }
    }, 

    rotatePiece() {
        if (!this.currentPiece) return;
        const rotatedShape = this.currentPiece.getRotatedShape();
        if (!this.currentPiece.checkCollisionAt(this.board, rotatedShape, this.currentPiece.position)) {
            this.currentPiece.shape = rotatedShape;
        }
    }, 

     handlePlayerInput(direction) { // direction: 'left' | 'right' | 'down' | 'rotate'
        let move = { r: 0, c: 0 };
        if (direction === 'left') move = { r: 0, c: -1 };
        else if (direction === 'right') move = { r: 0, c: 1 };
        else if (direction === 'down') move = { r: 1, c: 0 }; // Soft drop
        else if (direction === 'rotate') {
            this.rotatePiece();
            return;
        }

        this.tryMovePiece(move);
    },

     spawnNewPiece() {
         const newShapeKey = Object.keys(TETROMINO_SHAPES)[Math.floor(Math.random() * Object.keys(TETROMINO_SHAPES).length)];
         // Spawn logic attempts to place piece at top center, then checks for Game Over
         const initialPosition = { row: -1, col: Math.floor(this.board.width / 2) - 1 };

         if (newTetrominoCollisionAt(newShapeKey, boardInstance, initialPosition)) {
            this.isGameOver = true;
            console.log("GAME OVER!");
            // TODO: handle game over rendering/state change here
            return;
        }

         this.currentPiece = new Tetromino(newShapeKey, initialPosition);
     },

};


// Helper function scope needed for check collision logic during spawn
function newTetrominoCollisionAt(shapeKey, boardInstance, position) {
    const tempPiece = new Tetromino(shapeKey, position);
    return tempPiece.checkCollisionAt(boardInstance);
}


/**
 * Draws the current state of the game onto the Canvas context.
 */
function drawGame() {
    // 1. Clear Canvas
    const canvas = GameState.canvas;
    if (!canvas || !GameState.ctx) return;

    const ctx = GameState.ctx;
    ctx.fillStyle = '#000'; // Black background
    ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);

    // 2. Draw settled blocks (the grid state)
    for (let r = 0; r < GameState.board.height; r++) {
        for (let c = 0; c < GameState.board.width; c++) {
            const cellType = GameState.board.grid[r][c];
            if (cellType !== 'empty') {
                ctx.fillStyle = COLORS[cellType] || 'gray';
                // Draw block at pixel coordinates
                ctx.fillRect(c * BLOCK_SIZE, r * BLOCK_SIZE, BLOCK_SIZE - 1, BLOCK_SIZE - 1);
            }
        }
    }

    // 3. Draw the current falling piece
    if (GameState.currentPiece) {
        const color = COLORS[GameState.currentPiece.type] || 'white';
        const coords = GameState.currentPiece.getAbsoluteGridCoords();

        coords.forEach(({ r, c }) => {
            // We draw the current piece in its projected position (r, c) on top of the settled blocks
            ctx.fillStyle = color;
            ctx.fillRect(c * BLOCK_SIZE, r * BLOCK_SIZE, BLOCK_SIZE - 1, BLOCK_SIZE - 1);
        });
    }

    // Instructions/Debug Overlay (Optional but helpful for verifying correctness)
     if (GameState.currentPiece && GameState.isGameOver) {
         ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
         ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
         ctx.fillStyle = 'white';
         ctx.font = "32px Arial";
         ctx.textAlign = "center";
         ctx.fillText("GAME OVER", CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2 - 10);
     }
}


// --- Execution Entry Point ---
document.addEventListener('DOMContentLoaded', () => {
    GameState.init();

    // Example of how player input would hook up (e.g., listening to keyboard events)
    window.addEventListener('keydown', e => {
        if (GameState.isGameOver) return;
        switch(e.key) {
            case 'ArrowLeft':
                GameState.handlePlayerInput('left');
                break;
            case 'ArrowRight':
                GameState.handlePlayerInput('right');
                break;
            case 'ArrowDown': // Soft drop
                GameState.handlePlayerInput('down'); 
                break;
            case 'ArrowUp': // Rotate
                GameState.handlePlayerInput('rotate');
                break;
        }
    });
});