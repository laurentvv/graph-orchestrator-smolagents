// Repro v2 : instrumente les boucles suspectes avec un garde d'itérations
// qui lève une erreur nommant la ligne exacte de la boucle infinie.
const fs = require('fs');
const vm = require('vm');

if (process.argv.length < 3) {
  console.error('Usage: node repro_freeze_tetris2.js <path-to-html>');
  process.exit(1);
}
const html = fs.readFileSync(process.argv[2], 'utf8');
let code = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)].map((m) => m[1]).join('\n;\n');

const patches = [
  ['} while (bag.includes(piece));', '} while (loopGuard(299, () => bag.includes(piece)));'],
  [
    'while (!collides(currentPiece, ghostRow - currentPiece.position.row + 1, 0)) {',
    'while (loopGuard(425, () => !collides(currentPiece, ghostRow - currentPiece.position.row + 1, 0))) {',
  ],
  ['while (true) {', 'while (loopGuard(432, () => true)) {'],
  [
    'for (let r = ROWS - 1; r >= 0 && linesCleared > 0; r--) {',
    'for (let r = ROWS - 1; loopGuard(415, () => r >= 0 && linesCleared > 0); r--) {',
  ],
];
for (const [from, to] of patches) {
  if (!code.includes(from)) {
    console.log('PATTERN INTROUVABLE:', from.slice(0, 60));
  } else {
    code = code.replaceAll(from, to);
  }
}

code = `let __g = {};
function loopGuard(id, cond) {
  __g[id] = (__g[id] || 0) + 1;
  if (__g[id] > 50000) throw new Error('BOUCLE INFINIE ligne ' + id + ' (' + __g[id] + ' iterations)');
  return cond();
}
` + code;

function makeProxy() {
  const proxy = new Proxy(function () {}, {
    get(_t, prop) {
      if (prop === Symbol.toPrimitive) return () => 0;
      if (prop === 'toString') return () => '[stub]';
      return proxy;
    },
    set() {
      return true;
    },
    apply() {
      return proxy;
    },
    construct() {
      return proxy;
    },
  });
  return proxy;
}

const sandbox = {
  document: makeProxy(),
  window: makeProxy(),
  performance: { now: () => Date.now() },
  requestAnimationFrame: () => 0,
  requestIdleCallback: () => 0,
  cancelAnimationFrame: () => {},
  setTimeout: () => 0,
  setInterval: () => 0,
  console,
};
try {
  vm.runInNewContext(code, sandbox, { timeout: 8000 });
  console.log('SCRIPT TERMINÉ SANS GEL — compteurs boucles:', JSON.stringify(sandbox.__g ?? __g));
} catch (e) {
  console.log('VERDICT:', e.message);
}
