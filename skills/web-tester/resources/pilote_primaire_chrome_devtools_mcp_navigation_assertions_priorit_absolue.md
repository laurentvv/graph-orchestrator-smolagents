## 🚨 PILOTE PRIMAIRE = Chrome DevTools MCP (navigation + assertions) — PRIORITÉ ABSOLUE
**[BUG CONNU ENVIRONNEMENT]** : le serveur `puppeteer_navigate` répond "Navigated to ..." mais
ne charge PAS réellement les fichiers `file://` locaux — la page reste `about:blank` et tout
test échoue silencieusement puis timeout (600s) → FAILURE systématique.
**SOLUTION OBLIGATOIRE** : pour la navigation initiale ET toutes les assertions, utilise les
outils **Chrome DevTools MCP** (SANS préfixe `puppeteer_`) :
- `navigate_page(url="file:///D:/.../index.html", type="url")` — ouvre la page (le SEUL qui marche).
- `evaluate_script(function="async () => { ... }")` — assertions fonctionnelles (fonction NON invoquée).
- `take_snapshot(verbose=True)` — arbre a11y (structure, IDs, visibilité).
- `list_console_messages()` — erreurs JS avec source maps.
- `click(uid=...)` / `fill(uid=..., value=...)` — interactions (uid depuis take_snapshot).
- `take_screenshot(fullPage=True)` — capture visuelle (l'image te revient).
**[2 NAVIGATEURS SÉPARÉS]** : Puppeteer et DevTools pilotent chacun LEUR Chrome. Ne mélange
JAMAIS : si tu navigues avec `navigate_page`, fais TOUT le reste avec DevTools. Un
`puppeteer_evaluate` verrait l'AUTRE navigateur (vide). En revanche, les outils helper
`clean_dom` / `add_visual_tags` / `fuzz_click_all_buttons` (SANS préfixe puppeteer_) sont
branchés sur DevTools (`evaluate_script`) et donc OK à utiliser sur le navigateur actif.
La syntaxe `evaluate_script` DIFFÈRE de `puppeteer_evaluate` (voir section syntaxe ci-dessous) :
`evaluate_script` prend une **fonction non-invoquée** `async () => {...}`, PAS une IIFE.
