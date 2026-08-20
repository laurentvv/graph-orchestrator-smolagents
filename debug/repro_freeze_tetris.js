// Repro du gel de la page Tetris (run 2026-08-20_0901) :
// exécute le JS inline extrait du HTML dans un sandbox vm avec timeout.
// Si le thread principal est bloqué par une boucle infinie, vm l'interrompt
// et la stack pointe la fonction fautive. 0 LLM, déterministe.
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync(process.argv[2], 'utf8');
const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)].map((m) => m[1]);
const code = scripts.join('\n;\n');
console.log(`scripts extraits: ${scripts.length}, ${code.length} chars`);

// Proxy universel : absorbe tout appel/accès/assignation (DOM factice).
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
  cancelAnimationFrame: () => {},
  setTimeout: () => 0,
  setInterval: () => 0,
  console,
};
try {
  vm.runInNewContext(code, sandbox, { timeout: 5000 });
  console.log('SCRIPT TERMINÉ SANS GEL (pas de boucle infinie synchrone)');
} catch (e) {
  console.log('INTERROMPU/ERREUR:', e.message);
  console.log((e.stack || '').split('\n').slice(0, 15).join('\n'));
}
