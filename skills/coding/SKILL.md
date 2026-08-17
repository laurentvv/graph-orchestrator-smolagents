---
name: coding
description: Patterns de codage et bonnes pratiques pour un agent développeur
---

# Skill : Agent de codage

Tu es un agent développeur expert. Tu écris, lis et exécute du code pour aider l'utilisateur.

## ⚠️ RÈGLES CRITIQUES (à appliquer IMMÉDIATEMENT — pas besoin de lire les resources)

Ces 4 failure modes reviennent à CHAQUE run. Applique-les PAR DÉFAUT, ils ne sont pas
négociables. Les resources ci-dessous donnent le détail, mais la règle ci-dessous suffit.

1. **HAUTEURS CSS en `%` ET height=0 = BUG INVISIBLE n°1** (visualiseurs, barres, graphiques) :
   - **JAMAIS `bar.style.height = '0px'` à la création** — c'est LE failure mode n°1. La hauteur
     DOIT être la VRAIE valeur AU MOMENT du `createElement`/`appendChild` :
     - ❌ `const bar = document.createElement('div'); bar.style.height = '0px'; container.appendChild(bar);`
       (update différé au swap → barres INVISIBLES au chargement)
     - ✅ `const bar = document.createElement('div'); bar.style.height = (value * 3) + 'px'; container.appendChild(bar);`
       (hauteur réelle dès la création → barres VISIBLES au chargement)
   - `height: 80%` ne marche QUE si le parent DIRECT a une `height` EXPLICITE (pas `min-height`).
     Si le parent n'a que `min-height`, le `%` résout à **0 → invisible**.
     - ❌ `#viz { min-height: 300px; } .bar { height: 80%; }` → barres invisibles
     - ✅ `#viz { height: 300px; } .bar { height: 80%; }` (parent a `height`)
   - **En cas de doute, utilise des px absolus (`(value * 3) + 'px'`), pas de `%`, et JAMAIS 0.**
   - **Barres verticales = conteneur flex ROW** : `display:flex` (row, défaut) +
     `align-items:flex-end` + hauteurs px inline. JAMAIS `flex-direction:column` +
     `flex:1` sur les barres : en colonne, `flex-basis:0` du flex ÉCRASE `style.height`
     inline → bandes horizontales ÉGALES figées, le tri ne se voit pas (bug isolation
     F-124 2026-08-18 : effets glow/cubic-bezier parfaits mais viz dégénérée).


2. **JAVASCRIPT VANILLA PUR dans `<script>`** : aucune syntaxe TypeScript
   (`: type`, `as`, `interface`, `: void`, `?` sur paramètres) → SyntaxError → page blanche.

3. **Fermeture d'appel Python `)` pas `}`** : quand un `write_file`/`search_replace`
   contient du code avec des `{}`, ferme l'appel Python par `)`, jamais `}`.

4. **Animations = 1 itération par frame** (requestAnimationFrame/setTimeout) : NE JAMAIS
   mettre la boucle complète de l'algorithme dans une seule fonction appelée par frame.

5. **BOUCLE D'ANIMATION CANONIQUE — rends et rafraîchis TOUT à CHAQUE étape** (visualiseurs) :
   - **Canvas OU div, JAMAIS les deux mêlés** : les enfants d'un `<canvas>` ne s'affichent
     JAMAIS → n'appendChild PAS de divs dans un canvas. Canvas = `ctx.fillRect` uniquement ;
     div = `style.height` uniquement.
   - Le rendu DOIT être rappelé DANS la boucle (sinon l'animation est invisible) :
     ```js
     async function bubbleSort() {
         for (let i = 0; i < data.length - 1; i++) {
             if (data[i] > data[i + 1]) { [data[i], data[i+1]] = [data[i+1], data[i]]; }
             comparisons++;
             counterEl.textContent = comparisons;   // RAFRAÎCHIR le compteur DANS la boucle
             draw();                                 // REDESSINER le canvas DANS la boucle
             await sleep(delay);                     // delay = 50-300 ms par étape
         }
     }
     ```
   - ❌ Incrémenter `comparisons` sans réassigner `counterEl.textContent` après → compteur
     affiché figé à 0. ❌ `draw()` appelé seulement à l'init → le tri s'exécute de façon
     INVISIBLE (le canvas montre éternellement les barres initiales).


## Dynamic Resources (Progressive Disclosure)

This skill is large. To save context, its detailed instructions are split into separate files in the `resources/` directory.
**You MUST use your `view_file` tool to read the relevant file when you reach that stage of the process.**

- **[resources/quand_utiliser_quels_outils.md](file:///D:/GIT/graph-orchestrator-smolagents/skills/coding/resources/quand_utiliser_quels_outils.md)**: Read this to understand Quand utiliser quels outils.
- **[resources/r_gles_d_or.md](file:///D:/GIT/graph-orchestrator-smolagents/skills/coding/resources/r_gles_d_or.md)**: Read this to understand Règles d'or.
- **[resources/r_gle_critique_javascript_vanila_pur_dans_script_failure_mode_n_1.md](file:///D:/GIT/graph-orchestrator-smolagents/skills/coding/resources/r_gle_critique_javascript_vanila_pur_dans_script_failure_mode_n_1.md)**: Read this to understand ⚠️ RÈGLE CRITIQUE — JavaScript VANILA PUR dans `<script>` (failure mode n°1).
- **[resources/r_gle_critique_fermeture_d_appel_python_pas_failure_mode_parsing_n_1.md](file:///D:/GIT/graph-orchestrator-smolagents/skills/coding/resources/r_gle_critique_fermeture_d_appel_python_pas_failure_mode_parsing_n_1.md)**: Read this to understand ⚠️ RÈGLE CRITIQUE — Fermeture d'appel Python `)` pas `}` (failure mode parsing n°1).
- **[resources/r_gle_critique_hauteurs_css_en_pourcentage_failure_mode_visuel_n_1.md](file:///D:/GIT/graph-orchestrator-smolagents/skills/coding/resources/r_gle_critique_hauteurs_css_en_pourcentage_failure_mode_visuel_n_1.md)**: Read this to understand ⚠️ RÈGLE CRITIQUE — Hauteurs CSS en pourcentage (failure mode visuel n°1).
- **[resources/r_gle_critique_animations_js_et_boucles_bloquantes_failure_mode_timeout_n_1.md](file:///D:/GIT/graph-orchestrator-smolagents/skills/coding/resources/r_gle_critique_animations_js_et_boucles_bloquantes_failure_mode_timeout_n_1.md)**: Read this to understand ⚠️ RÈGLE CRITIQUE — Animations JS et Boucles bloquantes (failure mode timeout n°1).
- **[resources/format_de_r_ponse_final.md](file:///D:/GIT/graph-orchestrator-smolagents/skills/coding/resources/format_de_r_ponse_final.md)**: Read this to understand Format de réponse final.
