---
id: skill-finder-react-best-practices
title: Landing React production (force la recherche de skill — F-82)
purpose: >
  Prompt de validation F-82 (Skill Finder), variante la plus SÛRE côté install :
  la skill "React best-practices" de vercel-labs est l'exemple canonique de skills.sh
  (documentée par Vercel + multiples tutos). Le ReAct F-82 voyant uniquement le prompt
  brut (pas le catalogue local), l'angle "production best-practices" pousse le modèle à
  chercher la skill dédiée plutôt qu'à se satisfaire de frontend-design.
target_files:
  - index.html
  - src/App.jsx
  - src/main.jsx
  - src/components/Hero.jsx
  - src/components/Pricing.jsx
expected_skill_finder: search "react" → install du skill React best-practices vercel-labs
note_validation: >
  Léger recouvrement local (context7 peut pré-fetcher la doc React) — c'est voulu pour
  comparer. Critère F-82 : le ReAct appelle search_and_install_skill ET installe une
  skill vercel-labs (manifeste skills/installed-skills.json non vide).
---

Construis une landing page SaaS en **React (Vite)** aux standards production : composants fonctionnels réutilisables, hooks (useState/useEffect), accessibilité (aria), responsive Tailwind, structure de fichiers propre. Cible : convertir un visiteur.

Sections attendues :
- **Hero** : titre percutant, sous-titre, CTA primaire (« Commencer ») + CTA secondaire (« Démo ») ;
- **Features** : 3 atouts produit en grille (icône + titre + description) ;
- **Pricing** : 3 offres (Free / Pro / Enterprise) avec bouton par offre ;
- **Footer** : liens + copyright.

Contraintes techniques : composants découpés (Hero, Features, Pricing, Footer), props typées, aucun framework UI lourd, design soigné responsive (mobile-first), sémantique HTML accessible.
