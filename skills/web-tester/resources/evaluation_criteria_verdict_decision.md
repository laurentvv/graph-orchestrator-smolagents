## Evaluation Criteria (verdict decision)
- **Errors**: any hidden JavaScript error in the console? → FAILURE.
- **Functional assertions**: do ALL core behaviors return the expected result? → a single failing assertion = FAILURE.
- **Visuals & Aesthetics**: any blatant CSS rendering bug? Is the space occupation harmonious? (If a chart, canvas, or grid only occupies a tiny fraction of its container leaving huge unjustified empty spaces, this is an AESTHETIC BUG). → FAILURE.
- **Interactivity**: do buttons/inputs work? → broken interaction = FAILURE.

**`status: "success"` requires ALL of: 0 console error + every core assertion PASS + no visual/interaction bug.**
Otherwise return `status: "failure"` with the specific failing assertion and steps to reproduce.

### ⚠️ ANTI-ACHARNEMENT — Conclure VITE sur un bug réel (failure mode observé)
Tu as un budget limité de steps (12 max). Ne gaspille PAS tes steps à explorer 15
sélecteurs différents si un comportement clé échoue. Si une assertion CRITIQUE échoue
deux fois de suite (ex: élément attendu introuvable, ou résultat faux), c'est un **bug
réel** — déclare FAILURE immédiatement avec un rapport clair.

**Règle des 2 essais** : pour chaque comportement testé, max 2 tentatives (ex: `.bar`
puis `[data-value]`). Si toujours échec au 2e → la page est cassée, n'essaie pas un 3e
sélecteur. Conclus FAILURE et documente :
- CE QUE TU AS TESTÉ (sélecteur + assertion)
- CE QUE TU ATTENDAIS (comportement du cahier des charges)
- CE QUE TU AS EU (résultat réel, ex: `[]`, `"No bars found"`, `undefined`)

Un échec **documenté et reproductible** vaut mieux que 20 steps d'exploration stérile.
Le Coder recevra ton rapport et saura exactement quoi corriger (ex: "les éléments ne sont
pas générés car le JS a une erreur de syntaxe"). N'oublie pas NON PLUS de vérifier la
console (`list_console_messages` ou `puppeteer_evaluate`) — un JS cassé explique souvent
pourquoi les éléments attendus n'existent pas.