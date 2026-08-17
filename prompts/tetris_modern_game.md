# Modern Tetris — Single-File Game

Create a single self-contained `index.html` — a fully functional, modern Tetris game that **works correctly on the first run** and has the **best possible appearance**. High resolution, refined visuals. A REAL modern Tetris. Be meticulous — no errors.

## Core Mechanics

- Board: 10 × 20 visible rows, standard 7 tetrominoes (I, J, L, O, S, T, Z)
- **7-bag randomizer** (pieces shuffled per bag — no true-random floods of the same piece)
- Rotation **with wall kicks** (SRS kick tables or a correct equivalent); the O piece never shifts off-grid
- **Ghost piece** — translucent outline showing where the active piece will land
- **Hold** slot (usable once per drop), **Next queue** showing the next 3 pieces
- Soft drop (accelerated gravity while held), **hard drop** on Space (instant lock)
- **Lock delay** (~500 ms) reset on move/rotate, with a capped number of resets per piece
- Line clear detection with a short animation, then collapse; topping out = Game Over overlay + restart button

## Scoring & Progression

- Guideline scoring: 100 / 300 / 500 / 800 × level for 1 / 2 / 3 / 4 lines; soft drop +1/cell, hard drop +2/cell; combos and back-to-back Tetris optional bonus
- Level up every 10 lines; speed curve per Guideline (level 1 ≈ 1 s per row, decreasing, capped at level 15+)
- HUD: Score / Lines / Level / Best — Best persisted to `localStorage`

## Controls

- ← / → move · ↓ soft drop · ↑ or X rotate CW · Z rotate CCW · Space hard drop · C or Shift hold · P pause · R restart
- **Custom DAS/ARR key-repeat timing** (do NOT rely on the browser's native key repeat)
- Game keys ignored while paused or on Game Over; **auto-pause on window blur**

## Visual Bar (high resolution, NO garish "AI palette")

- Canvas rendered at native resolution with **devicePixelRatio scaling** — crisp cells, zero blur, no stretched pixels
- **Deliberate color system**: 4–6 named colors, dark refined theme, ONE signature accent — strictly NO neon rainbow soup, no garish gradient look, no muddy colors. Each tetromino gets ONE consistent, tasteful color
- Effects — maximal but intentional: subtle bevel/highlight on each cell, soft glow on the active piece, ghost outline, line-clear flash + smooth collapse, score popup on clears (+800 TETRIS), level-up banner, small particle burst on hard drop
- Layout (APP/TOOL): board centered in a card, side panels for HOLD / NEXT / STATS; no layout shift at any window size; `:focus-visible` and `prefers-reduced-motion` respected

## Constraints

- Vanilla HTML/CSS/JS in ONE file — zero CDN, zero external asset, runs from `file://`
- 60 fps loop with delta-time (game speed never tied to frame rate); **zero console errors**
- Works first try: no syntax errors, no dead event handlers, every listed key binding functional

---

*Prompt original (FR, 2026-08-18) : « Crée-moi le Tetris le plus génial et le plus impressionnant visuellement en un seul fichier HTML. Fais un réel effort pour qu'il fonctionne correctement du premier coup et qu'il ait la meilleure apparence possible. Haute résolution, PAS de couleurs baveuses d'IA. Un vrai jeu Tetris moderne. Sois minutieux, ne fais pas d'erreurs. »*
