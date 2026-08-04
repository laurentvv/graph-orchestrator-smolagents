---
name: devtools-preview
description: Auto-validation visuelle via Chrome DevTools MCP — le Coder vérifie sa page (screenshot + console) avant final_answer.
---

# DevTools Preview Skill (F-45)

Tu disposes d'un navigateur Chrome pilotable (**Chrome DevTools MCP**) pour vérifier
visuellement ta page **AVANT** de la déclarer terminée. Le screenshot que tu prends
**te revient en image** — tu le vois, tu peux juger le rendu.

## Pourquoi
Un fichier HTML syntaxiquement valide peut afficher une page blanche, un layout cassé,
ou des éléments superposés. Sans preview, tu envoies une page visuellement ratée au
Tester, qui échouera → cycle de correction long. Le preview court-circuite ça.

## Workflow (obligatoire pour les tâches web, après write_file)

1. **Navigue** : `navigate_page(url="<URL ABSOLUE file:///">...")`
   - L'URL exacte de ton fichier principal est donnée dans le prompt. Utilise-la telle quelle.
   - Exemple : `navigate_page(url="file:///D:/.../runs/2024-01-01_1200_slug/landing_page/index.html")`
2. **Console (OBLIGATOIRE — AVANT le screenshot)** : `list_console_messages()` → erreurs JS ?
   - ⚠️ **C'EST L'ÉTAPE LA PLUS IMPORTANTE.** Une erreur de syntaxe JS (ex: annotation
     TypeScript dans `<script>` vanilla) fait échouer TOUT le script silencieusement : la
     page rend correctement (le CSS marche) mais AUCUNE interaction ne fonctionne (boutons
     morts, éléments vides, pas de barres générées). Un screenshot seul ne détecte PAS ce
     bug — seule la console le révèle.
   - Si tu vois `SyntaxError`, `Unexpected token`, `Uncaught` → c'est un bug CRITIQUE.
     Corrige-le AVANT de continuer. Ne fais JAMAIS `final_answer` avec une erreur console.
3. **Capture** : `take_screenshot()` → l'image te revient. **Analyse-la de façon CRITIQUE** :
   - La page est-elle vide/blanche ? → erreur JS (vérifié étape 2 normalement).
   - Le layout est-il cassé (éléments superposés, débordement, texte coupé) ?
   - **L'occupation de l'espace est-elle harmonieuse ?** (Traque les énormes zones de vide injustifiées. Si un graphique, un canevas ou une grille n'occupe que la moitié de son conteneur, c'est un BUG visuel à corriger).
   - Les couleurs/polices correspondent-elles au cahier des charges ?
4. **Interactions (si la page en a)** : teste un bouton clé via `click(uid=...)` ou
   `evaluate_script` pour confirmer que le JS fonctionne (ex: cliquer "Démarrer" et vérifier
   que quelque chose change). Un screenshot "joli" ne prouve pas que le JS marche.
5. **Corrige** si bug visuel/erreur console/interaction morte : `search_replace` sur le
   fragment fautif, puis re-`navigate_page` + re-`list_console_messages` + re-`take_screenshot`.
6. **final_answer** uniquement quand : rendu visuellement correct **ET** 0 erreur console
   **ET** interactions fonctionnelles vérifiées.

## Quand NE PAS preview
- **Tâche non-web** (Python, data, CLI) : pas de navigateur pertinent, saute cette section.
- **Mode correction** (itération > 1) : preview pour **confirmer** que ton fix a marché,
  pas pour tout re-vérifier from scratch.

## Pièges à éviter
- **URL relative** : `navigate_page(url="index.html")` ne marche pas. Toujours `file:///` absolu.
- **Page dans un sous-dossier** : si ta page est `landing_page/index.html`, l'URL est
  `file:///.../landing_page/index.html`, PAS `file:///.../index.html` (sinon 404 / page racine).
- **Boucle de screenshots** : max 1 screenshot par étape de correction. Si tu ne vois pas
  le bug après 2 screenshots, lis le DOM via `evaluate_script` au lieu de re-capturer.
- **Interactions** : pour tester un bouton (ex: "Démarrer le tri"), `click(uid=...)` après
  avoir identifié l'élément via `take_snapshot()`. Mais pour un simple check visuel,
  screenshot + console suffisent dans 90% des cas.

## Outils clés (rappel compact)
| Outil | Rôle |
|-------|------|
| `navigate_page(url)` | Ouvre l'URL (file:/// absolu) dans Chrome. |
| `take_screenshot()` | Capture → image TE REVIENT (tu la vois). |
| `list_console_messages()` | Erreurs/warnings JS (avec source maps). |
| `evaluate_script(function)` | JS dans la page (lire une valeur DOM). |
| `take_snapshot()` | Arbre a11y (IDs/textes, pour cibler un click). |
| `click(uid)` / `fill(uid, value)` | Interactions (optionnel). |
