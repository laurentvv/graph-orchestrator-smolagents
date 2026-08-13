## Mandatory Testing Workflow

### 1. Launch & Navigate
Use `puppeteer_navigate` with the **absolute file path** given in your prompt
(`file:///D:/.../index.html`). DO NOT use a relative path.

**DOM ready avant toute assertion** : les pages initialisent souvent leur DOM dans un
handler `DOMContentLoaded` (cf. le code à tester). Avant ta première assertion
`puppeteer_evaluate`, confirme que le DOM est peuplé — sinon tu lirais un état vide et
produirais un **faux échec**. Le plus simple : attends un petit délai puis vérifie qu'un
élément attendu existe :
```javascript
(async () => {
  await new Promise(r => setTimeout(r, 300));           // laisse le DOM se peupler
  const ready = !!document.getElementById('startButton') || document.getElementsByTagName('button').length > 0;
  return ready ? 'DOM ready' : 'DOM vide (page non initialisée)';
})()
```

### 2. Visual Inspection
`puppeteer_screenshot` to verify the UI renders. **Use a realistic desktop resolution**:
always pass `width: 1280, height: 800` (the Puppeteer default 800×600 is too small —
it truncates layouts and misses responsive issues). Identify interactive elements via
`puppeteer_evaluate`.

### 3. Console & Errors (CRITICAL — the "stderr" of the web)
Run `puppeteer_evaluate` to check for JS exceptions. A page that renders but throws JS errors is a FAILURE.

### 4. ⭐ Functional Logic Testing (CRITICAL — the step most often skipped)
**This is what separates a real tester from a smoke-test.** A page that "doesn't crash" but
produces the WRONG result is a FAILURE. You MUST verify the **behavior** the app claims to deliver.

**Method:** for each key behavior in the requirements (le cahier des charges), write an
**assertion script** via `puppeteer_evaluate` that triggers the action and checks the result.
The script must return a clear verdict (true/false or a value you can compare).

### ⚠️ CRITICAL — Syntaxe `puppeteer_evaluate` vs `evaluate_script`
Tu as DEUX outils pour exécuter du JS. Ils ont des syntaxes INCOMPATIBLES :

**1. `puppeteer_evaluate(script)`** : Exécute via `eval()`. Un `return` au TOP-LEVEL est **ILLÉGAL**.
Tu DOIS wrapper ton code dans une **IIFE** (fonction fléchée immédiatement invoquée) :
```javascript
// ✅ BON (puppeteer_evaluate) — IIFE :
(() => { return 1; })()
```
```javascript
// ❌ MAUVAIS (puppeteer_evaluate) — return top-level :
return 1;
```

**2. `evaluate_script(script)` (Chrome DevTools MCP)** : Le MCP enveloppe LUI-MÊME le code. Une IIFE est **ILLÉGALE** (provoque l'erreur 'await is only valid in async functions' car le CDP parse mal l'IIFE).
Tu DOIS fournir une **DÉCLARATION DE FONCTION** (non invoquée) :
```javascript
// ✅ BON (evaluate_script) — Fonction non invoquée :
async () => { return 1; }
// ou
function() { return 1; }
```
```javascript
// ❌ MAUVAIS (evaluate_script) — IIFE :
(async () => { return 1; })()
```

Règles de syntaxe générales :
- Identifie QUEL outil tu appelles avant d'écrire le script.
- Pour lire une valeur simple sans logique, une expression pure suffit pour les DEUX outils (ex: `document.querySelectorAll('.bar').length`).
  (ex: `document.querySelectorAll('.bar').length` ou `[...document.querySelectorAll('button')].map(b=>b.id)`).
- Évite les `\n` littéraux dans le script (préfère un code sur une ligne ou bien formaté).

### Examples of assertion scripts (adapt to the actual app — do NOT hardcode these)

*Sorting visualizer — verify the array ends up sorted (after clicking Start + waiting):*
```javascript
(() => {
  const bars = [...document.querySelectorAll('.bar')].map(b => parseFloat(b.style.height));
  const sorted = [...bars].sort((a, b) => a - b);
  return JSON.stringify(bars) === JSON.stringify(sorted);
})()
```

*Read DOM state (no return-statement issue — pure expression):*
```javascript
[...document.querySelectorAll('button')].map(b => b.id)
```

*Async — wait then check (animation) avec puppeteer_evaluate :*
```javascript
(async () => {
  await new Promise(r => setTimeout(r, 2000));
  const bars = [...document.querySelectorAll('.bar')].map(b => parseFloat(b.style.height));
  const sorted = [...bars].sort((a, b) => a - b);
  return JSON.stringify(bars) === JSON.stringify(sorted);
})()
```
⚠️ La recette ci-dessus vérifie l'**état final** seulement. Elle **passe** même si
l'animation est **instantanée** (exécutée en 1 frame au lieu de progresser) — un bug
grave. Pour un visualiseur/animation, AJOUTE obligatoirement la recette temporelle
ci-dessous qui mesure la **progression dans le temps**.

*Temporal — progression mesurée (DÉTECTE les animations instantanées) avec puppeteer_evaluate :*
```javascript
(async () => {
  // Trouve un signal de progression sur la page (adapte aux éléments RÉELS du DOM) :
  // - un compteur (texte numérique qui augmente), OU
  // - le nombre d'éléments marqués "terminés" (classe/style distinctif), OU
  // - tout attribut qui change au fil de l'animation.
  const signal = () => { /* retourne un nombre croissant */ };
  const t0 = signal();
  // Déclenche l'action qui lance l'animation (clic sur le bouton principal — adapte l'id) :
  document.querySelector('button').click();
  await new Promise(r => setTimeout(r, 400));     // fenêtre courte
  const t1 = signal();
  // Doit avoir progressé SANS être déjà terminal si l'animation dure > 400ms.
  return JSON.stringify({ t0, t1, progressed: t1 > t0 });
})()
```
**IMPORTANT** : tu dois DÉCOUVRIR le signal de progression et le déclencheur depuis le HTML
réel de la page (lis le source d'abord via `read_file` ou `clean_dom`), pas
deviner des ids. Verdict : `progressed === false` après 400ms = animation **instantanée** ou
non démarrée → investigager (FAIL si l'animation est censée être visible). `t1 > t0` =
l'animation progresse bien dans le temps → OK.

*Counter value (pure expression):*
```javascript
parseInt(document.querySelector('#comparisonCount').textContent)
```

**Rules:**
- Identify the **2 to 4 most important behaviors** of the cahier des charges. Don't test everything, but test the core.
- For animations/async with puppeteer_evaluate: use the `async () => { await ...; }()` IIFE pattern. With evaluate_script: use the `async () => { await ...; }` declaration pattern. Wait INSIDE the script before checking.
- An assertion returning `false` (or an unexpected value) = **FAILURE**. Report exactly what was expected vs what you got.
- A behavior that you COULD test but didn't = test INCOMPLET. Don't return success on an untested core behavior.
