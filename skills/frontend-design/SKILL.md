---
name: frontend-design
description: Design frontend pro — palettes, typographie, layout, responsive. Injecté dans le Coder pour les tâches web (landing, portfolio, doc).
---

# Skill : Frontend Design Pro (condensé)

Fais des choix **délibérés et spécifiques**, jamais génériques. Le hero est une thèse.

## Système de tokens (à définir AVANT de coder, en :root)
**Palette — 4 à 6 hex nommés, fort contraste, un seul accent signature :**
```css
:root{ --bg:#0b1020; --surface:#121a33; --text:#e6ebff; --muted:#94a0c4; --accent:#6c8cff; --accent-2:#39e6c4; }
```
**Typo — 2 rôles, stack système (pas de CDN) :**
```css
--font-display:"Segoe UI",system-ui,sans-serif; /* titres 700/800 */
--font-body:system-ui,-apple-system,sans-serif;  /* corps 400/500 */
```
Échelle de type : hero 3.5rem / h2 2rem / lead 1.25rem / body 1rem. Interlignage corps 1.6.

## Layout & mouvement
- **CSS Grid** pour macro-layouts (sections, grille features), **Flexbox** pour alignement local.
- **Mobile-first** : 1 colonne défaut, media queries (min-width: 640px, 1024px).
- **Une seule signature mémorable** (ex: dégradé animé subtil sur le hero), pas un saupoudrage d'effets.
- Animations subtiles : `transition: transform .2s`, apparition au scroll via IntersectionObserver.

## Finition (non négociable)
Responsive mobile · focus clavier visible (`:focus-visible`) · `prefers-reduced-motion` respecté · contraste WCAG AA · sémantique HTML5 (`<header><nav><main><section><article><footer>`, un seul `<h1>`).

Concentre ton audace sur UN élément, garde le reste discipliné. La copy est un matériau de design, pas de la décoration.
