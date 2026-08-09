## ⚠️ RÈGLE CRITIQUE — JavaScript VANILA PUR dans `<script>` (failure mode n°1)

Quand tu écris du JS dans une balise `<script>` HTML (sans `type="module"` avec build step),
c'est du **JAVASCRIPT PUR** — PAS du TypeScript. Les navigateurs ne comprennent PAS les
annotations de type. Une seule annotation TS → **erreur de syntaxe au parsing → TOUT le
script échoue silencieusement** (la page rend mais aucune interaction ne marche).

**SYNTAXES INTERDITES** dans un `<script>` vanilla :

| ❌ Interdit (TypeScript) | ✅ Correct (JavaScript) |
|---|---|
| `let x: number = 0` | `let x = 0` |
| `function f(a: string): void` | `function f(a) {` |
| `async function g(): Promise<void>` | `async function g() {` |
| `arr.map((x: number) => x * 2)` | `arr.map((x) => x * 2)` |
| `(e.target as HTMLInputElement).value` | `e.target.value` |
| `interface Foo { ... }` | (supprimer — n'existe pas en JS) |
| `type Bar = string \| number` | (supprimer) |
| `<script lang="ts">` | `<script>` |

**RÈGLE** : si tu hésites entre TS et JS, c'est JS. Le JS vanilla n'a AUCUNE annotation
de type. Vérifie ton code : aucun `: type` après une variable, aucun `as Cast`, aucun
`interface`/`type` hors d'un commentaire. Si tu écris `function foo(x: number)`, le
navigateur lèvera `SyntaxError: Unexpected token ':'` et RIEN ne s'exécutera.
