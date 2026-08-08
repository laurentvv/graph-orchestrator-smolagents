# Méthodologie de test manuel (= spec du Tester idéal)

Ce document décrit **exactement** ce que je fais (l'agent) quand je teste un HTML à la
main, étape par étape. C'est le cahier des charges du Tester idéal : chaque étape ici
devrait être automatisable et fiable.

L'objectif : le Tester LLM actuel (gemma-4-12B, 25 min/run) est lent et parfois peu
fiable. Cette méthodologie, si on l'automatise, donnerait un **Tester déterministe 0-LLM**
pour 80% des cas (étapes 1-5), avec le LLM uniquement pour l'analyse visuelle (étape 6).

## Les 6 étapes (dans l'ordre, fail-fast)

### Étape 1 — Lecture statique (structure HTML)
**Ce que je fais** : `Read` le fichier complet, vérifier la structure (head/body),
présence des éléments clés.
**Outil** : `Read` (lecture fichier)
**Coût** : 0 LLM, instantané
**Échec type détecté** : fichier vide, structure HTML cassée, balises non fermées

### Étape 2 — Validation syntaxique JS (déterministe, LE plus puissant)
**Ce que je fais** :
1. Extraire le JS des balises `<script>` (regex `<script[^>]*>(.*?)</script>`)
2. Lancer `node --check` dessus
**Outil** : `node --check` (binaire, instantané)
**Coût** : 0 LLM, < 1s
**Échec type détecté** : TypeScript dans vanilla JS (`: type`, `as Cast`), accolades
non fermées, syntaxe cassée. **C'est le test qui attrape le bug n°1 du Coder** (run #2 :
TS dans `<script>` → SyntaxError → page blanche). Un screenshot ne l'aurait PAS détecté.

### Étape 3 — Checklist fonctionnalités (grep ciblé par exigence)
**Ce que je fais** : pour CHAQUE fonctionnalité du cahier des charges, je grep un
pattern dans le HTML et vérifie sa présence.
**Outil** : `grep -E "<pattern>"` par fonctionnalité
**Coût** : 0 LLM, instantané
**Exemple** (Bubble Sort) :
| Fonctionnalité | Pattern grep | Verdict |
|---|---|---|
| Bouton Démarrer | `start-btn\|Démarrer` | présent ? |
| Bouton Reset | `reset-btn\|Réinitialiser\|generate-btn` | présent ? |
| Slider vitesse | `input.*range\|speed-slider` | présent ? |
| Compteur | `comparison-count\|compteur\|Comparaisons` | présent ? |
| Code couleur | `\.sorted\|\.comparing\|\.swapping` | présent ? |
**Échec type détecté** : fonctionnalité totalement absente du HTML (compteur manquant
run #3 itération 1). C'est l'équivalent déterministe de la checklist F-46.

### Étape 4 — Vérification du "branchement" (le piège n°1 du Coder)
**Ce que je fais** : pour chaque élément interactif (bouton, input), je vérifie qu'il
est **réellement connecté** au JS via un `addEventListener` ou un handler équivalent.
**Outil** : `grep -E "<elementId>.*addEventListener\|addEventListener.*<elementId>"`
**Coût** : 0 LLM, instantané
**Échec type détecté** : élément HTML présent visuellement mais inactif. Bug run #3
itération 2 : `<input id="speedSlider">` existe MAIS PAS de
`speedSlider.addEventListener('input', ...)` → slider visuellement là mais inactif.
**C'est le failure mode que le screenshot NE PEUT PAS détecter** (le slider s'affiche).

### Étape 5 — Simulation logique (exécuter l'algorithme extrait)
**Ce que je fais** :
1. Extraire la fonction principale (ex: `bubbleSort`) du JS
2. L'exécuter dans Node avec un input test : `node -e "function bubbleSort(arr){...};
   let t=[64,34,25]; bubbleSort(t); console.log(t)"`
3. Vérifier que le résultat est correct (trié)
**Outil** : `node -e` avec le code extrait
**Coût** : 0 LLM, < 1s
**Échec type détecté** : algorithme faux (ex: boucle qui ne trie pas, swap incorrect).
C'est l'assertion fonctionnelle la plus fiable — on teste la LOGIQUE pas le rendu.

### Étape 6 — DOM rendu (evaluate_script, INDISPENSABLE — avant le screenshot)
**Ce que je fais** : après `navigate_page`, j'exécute `evaluate_script` pour **compter
les éléments rendus** dans le DOM vivant. C'est la vérification qui sépare "le JS crée
les éléments" (static) de "les éléments sont visibles" (runtime).
**Outil** : Chrome DevTools `evaluate_script` (ou `puppeteer_evaluate`)
**Coût** : 0 LLM, ~1s
**Exemple** : `document.querySelectorAll('.bar').length` → doit être > 0. Si 0 alors
que le JS les crée (étape 3 passait) → bug CSS (display:none, height:0, container
sans hauteur, position absolute hors écran).
**Échec type détecté** : bug isolation #1 — barres créées en JS avec `height: X%` mais
container parent sans `height` explicite → `%` résolu à 0 → barres invisibles. **Ce
bug est indétectable par les étapes 1-5 et par un screenshot trivialement checké.**

### Étape 7 — Vérification visuelle (DevTools screenshot, INDISPENSABLE)
**Ce que je fais** : ouvre la page dans Chrome DevTools, screenshot, **regarde vraiment
l'image** (pas un check de pixels trivial). Un humain ou un LLM vision doit confirmer.
**Outil** : Chrome DevTools MCP (`navigate_page` + `take_screenshot` via
`wrap_screenshot_tools` pour récupérer une vraie PIL.Image — sinon on reçoit juste
le texte "Took a screenshot..." à cause du bug multi-content de chrome-devtools-mcp).
**Coût** : ~1-2k tokens vision, 5-10s
**Échec type détecté** : bugs CSS visuels (layout cassé, superpositions, couleurs
fausses, barres trop petites, texte coupé).
**⚠️ ATTENTION BIAIS** : ne JAMAIS conclure "page OK" sur un check trivial (pixels pas
blancs). L'étape 6 (DOM rendu) est plus fiable pour les éléments attendus. Le
screenshot sert pour les bugs que le DOM rendu ne révèle pas (proportions, couleurs).

### Étape 7 (ajoutée après bug isolation) — Capture APRÈS interaction
**Ce que je fais** : après le screenshot statique, je **déclenche l'action principale**
(clic bouton Start) via `evaluate_script` ou `click`, j'attends, puis je re-screenshot
+ je vérifie qu'une valeur a changé (ex: compteur > 0, barres triées).
**Outil** : Chrome DevTools `evaluate_script` (clic + lecture état) + `take_screenshot`
**Coût** : ~2-3k tokens vision, 10-15s
**Rationale** : un screenshot statique ne prouve pas que les interactions marchent.
Le bug du run #3 (slider non branché) aurait pu être détecté ici : on bouge le slider
et on vérifie que la vitesse change réellement.

## Ordre optimal (fail-fast)

```
1. Read (structure OK ?)            ── non ──▶ FAILURE "structure HTML cassée"
   │ oui
   ▼
2. node --check (JS valide ?)        ── non ──▶ FAILURE "SyntaxError JS: <détail>"
   │ oui
   ▼
3. grep checklist (5 fonctions ?)    ── non ──▶ FAILURE "fonctionnalité X absente"
   │ oui
   ▼
4. grep addEventListener (branché ?) ── non ──▶ FAILURE "élément X non connecté au JS"
   │ oui
   ▼
5. node -e (algorithme correct ?)    ── non ──▶ FAILURE "logique incorrecte: <détail>"
   │ oui
   ▼
6. evaluate_script (éléments RENDUS ?) ── non ──▶ FAILURE "éléments créés en JS mais
   │                                    non visibles (bug CSS height/display/position)"
   │ oui
   ▼
7. DevTools screenshot (rendu OK ?)  ── non ──▶ FAILURE "bug visuel: <détail>"
   │ oui
   ▼
SUCCESS
```

## ⚠️ BIAIS DE CONFIRMATION — Le piège du tester (vécu)

**Récit** : lors du test du HTML d'isolation n°1, le screenshot montrait une page
**bleue vide** (juste le fond dark mode, zéro barre visible). Le script de test a
conclu "✅ Page a du contenu (couleurs variées)" parce que les pixels n'étaient ni
blancs ni noirs. Et l'agent (moi) a **prétendu valider visuellement** alors qu'il
regardait le succès attendu, pas la réalité. C'est l'œil humain (l'utilisateur) qui
a immédiatement vu que c'était vide.

**Leçon n°1 — Ne jamais se fier à un check trivial sur un screenshot**. "Pas blanc" ≠
"contenu présent". La bonne vérification est : `evaluate_script` qui **compte les
éléments rendus** (`document.querySelectorAll('.bar').length > 0`), pas un échantillon
de pixels. C'est l'étape 6 (DOM rendu), plus fiable que l'étape 7 (screenshot).

**Leçon n°2 — Un tester (LLM ou humain) a un biais vers le succès**. Après un long
travail de mise en place, on *veut* que ça marche, donc on interprète les résultats
ambigus favorablement. Contre-mesure : les assertions doivent être **binaires et
chiffrées** ("compteur > 0 après tri", "barres > 0 dans le DOM"), pas subjectives
("la page a l'air OK"). C'est tout l'intérêt de la checklist F-46 et du re-test ciblé
F-47 — imposer du mesurable.

**Leçon n°3 — L'œil humain reste l'arbitre final du visuel**. Aucun script ne remplace
un regard humain pour les bugs CSS subtils (barres invisibles, layout cassé). Le
screenshot LLM (gemma-4) est bon pour les bugs évidents mais peut rater des choses
qu'un humain voit instantanément. Le workflow idéal : automate les étapes 1-6
(déterministe), et reserve le screenshot LLM + relecture humaine pour l'étape 7.

## Pourquoi cette méthode est supérieure au Tester LLM actuel

| Critère | Tester LLM (gemma-12B) | Méthode manuelle (étapes 1-5) |
|---|---|---|
| Temps | ~25 min/itération | ~10 secondes |
| Tokens | 233k (contexte qui explose) | 0 (déterministe) |
| Fiabilité syntaxe JS | Moyenne (max steps) | **Binaire** (node --check) |
| Détection "non branché" | Faible (essaie 15 selecteurs) | **Immédiate** (grep listener) |
| Détection bug logique | Moyenne (assertions) | **Binaire** (exécution réelle) |
| Détection bug visuel | Bonne (screenshot) | Nécessite DevTools (étape 6) |

**Conclusion** : 80% des bugs (étapes 1-5) sont attrapables de façon **déterministe et
instantanée** sans LLM. Le LLM n'est utile que pour l'analyse visuelle (étape 6) et les
cas subtiles (assertions comportementales complexes). Un Tester hybride
(déterministe + LLM) serait 100× plus rapide et plus fiable.

## Ce que ça implique pour le projet

Le **Linter actuel** (linter.py, tree-sitter) fait déjà l'étape 2 partiellement. On
pourrait l'étendre aux étapes 3-5 (checklist grep + branchement + simulation logique)
pour créer un **"Static Tester"** qui court-circuite le Tester LLM sur les échecs
évidents. Le Tester LLM ne s'activerait que si le Static Tester PASS (pour valider le
visuel + les comportements subtils).
