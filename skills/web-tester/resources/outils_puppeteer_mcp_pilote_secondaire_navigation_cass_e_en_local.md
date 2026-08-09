## ⚠️ Outils Puppeteer MCP (pilote SECONDAIRE — navigation cassée en local)
The browser can ALSO be driven by the **Puppeteer MCP server** (tools prefixed `puppeteer_`).
⚠️ MAIS `puppeteer_navigate` ne charge pas les fichiers `file://` locaux dans cet environnement
(voir avertissement ci-dessus) — réserve Puppeteer aux rares cas où DevTools est indisponible.
Do NOT use names like `navigate_page`, `take_snapshot`, `evaluate_script` **comme outils Puppeteer**
— mais ces noms EXISTENT bien comme outils Chrome DevTools (cf. section PILOTE PRIMAIRE ci-dessus).
Outils Puppeteer :

| Outil | Args | Rôle |
|-------|------|------|
| `puppeteer_navigate` | `url`, `allowDangerous` | Ouvre une URL (fichier HTML local absolu). |
| `puppeteer_screenshot` | `name`, `selector`, `width`, `height` | Capture d'écran. |
| `puppeteer_click` | `selector` | Clique sur un élément (sélecteur CSS). |
| `puppeteer_fill` | `selector`, `value` | Remplit un champ input. |
| `puppeteer_evaluate` | `script` | **Exécute du JS arbitraire dans la page et retourne le résultat.** Outil CLÉ pour les tests fonctionnels. |

Pour les sélecteurs : inspecte d'abord le DOM via `puppeteer_evaluate` avec une expression
(ex: `[...document.querySelectorAll('button')].map(b=>({id:b.id, text:b.innerText.trim()}))`)
pour découvrir les IDs/classes réels, PUIS utilise-les.

### ⚠️ Sélecteurs CSS valides pour `puppeteer_click` / `puppeteer_fill`
Puppeteer utilise `document.querySelector()` (CSS standard). Les syntaxes **Playwright**
comme `button:has-text("...")` ou `text="..."` sont **INVALIDES** → erreur. Utilise :

| Besoin | ✅ Valide (CSS) | ❌ Invalide (Playwright) |
|--------|-----------------|------------------------|
| Bouton par ID | `#startButton` | `button:has-text("Start")` |
| Bouton par classe | `.btn-primary` | `button.btn >> text=Start` |
| Par attribut | `button[data-action="start"]` | `[data-action=start]` (sans guillemets) |
| Input par ID | `#taskInput` | `input[type="text"]:has-text()` |
| n-ième élément | `.bar:nth-child(3)` | — |

**Si pas d'ID/classe stable** : clique via `puppeteer_evaluate` au lieu de `puppeteer_click` :
```javascript
// Trouve le bouton par son texte puis clique (robuste) :
(() => { [...document.querySelectorAll('button')].find(b => b.innerText.includes('Start')).click(); return 'clicked'; })()
```
Attention : pas de `return` au top-level (cf. section 4 sur la syntaxe IIFE).

### ⚠️ CRITICAL — `querySelector(...)` s'APPELLE, ne s'ASSIGNE PAS (sinon boucle fatale)
`document.querySelector` / `document.querySelectorAll` sont des **fonctions natives**. La
cause n°1 de l'erreur `document.querySelector is not a function` (observée 17× sur un run
réel) est d'écrire par erreur une **assignation** `=` au lieu d'un **appel** `()` :

```javascript
// ❌ FAUX — assignation : écrase la fonction native dans le contexte de la page !
const slider = document.querySelector='input[type="range"]';   // querySelector est maintenant détruit
// Tous les appels suivants échoueront : "document.querySelector is not a function"

// ✅ CORRECT — appel avec parenthèses :
const slider = document.querySelector('input[type="range"]');
```

**Pourquoi c'est fatal** : une fois `document.querySelector = ...` exécuté dans le
contexte de la page, la fonction native est **définitivement écrasée** pour tous les
`puppeteer_evaluate` suivants. Le modèle boucle car il cherche une cause externe
(Puppeteer, environnement) sans réaliser qu'il a lui-même corrompu `document`.

**Garde anti-pollution du contexte (TOUJOURS appliquer)** :
- NE JAMAIS réassigner une méthode native (`document.querySelector=...`, `window.alert=...`).
- Stocke toujours le RÉSULTAT dans une `const` locale : `const el = document.querySelector(...)`.
- Si tu reçois `... is not a function` sur une API native standard, suppose D'ABORD une
  faute de syntaxe dans ton script (assignation oubliée, parenthèse manquante), PAS un
  problème de l'environnement Puppeteer. Relis ton script précédent avant de réessayer.

**Repli robuste si tu doutes de tes sélecteurs** — préfère les APIs qui ne risquent pas
l'assignation accidentelle, surtout quand le code à tester utilise lui-même `getElementById` :
```javascript
// ✅ Replis sûrs (jamais d'ambiguïté appel vs assignation) :
(() => {
  const startBtn = document.getElementById('startButton');     // 1 élément par ID
  const resetBtn = document.getElementById('resetButton');
  const buttons  = Array.from(document.getElementsByTagName('button'));   // tous les boutons
  const inputs   = Array.from(document.getElementsByTagName('input'));    // tous les inputs
  return JSON.stringify({
    start: !!startBtn, reset: !!resetBtn,
    buttons: buttons.map(b => ({ id: b.id, text: b.innerText.trim() })),
    inputs: inputs.map(i => ({ id: i.id, type: i.type })),
  });
})()
```
