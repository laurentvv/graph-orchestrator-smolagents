# 01 — Prompt-Vault

## En-tête
- **Nom** : Prompt-Vault
- **Chemin** : `references/Prompt-Vault/`
- **Type** : bibliothèque de prompts / cahiers des charges de coding (Markdown pur)
- **Langage principal** : aucun (Markdown) — génère du HTML/CSS/JS, Python, Nim, Rust, Tauri/Vue
- **Statistiques** : 13 fichiers (1 README + 12 prompts répartis sur 4 niveaux)

## Synthèse
Prompt-Vault est une collection curatoriale de **cahiers des charges de coding** prêts à l'emploi, conçue explicitement pour tester des LLM sur des tâches de génération de code. Chaque fichier `.md` décrit un projet autonome avec exigences fonctionnelles, contraintes techniques (stack imposée, nombre de fichiers, périmètre) et critères de finition.

**Utilité pour graph-orchestrator-smolagents** : c'est la **ressource d'évaluation clé-en-main** du projet. Les prompts se branchent directement dans `tasks.json` (édition → `WORKFLOW_MODE=coding` → `agent_graph.py`) pour exercer le workflow Routeur → Architect → Coders fan-out → Tester → Judge. La granularité par difficulté permet de calibrer la charge :
- Les prompts **Easy/Medium** (single `index.html`, Vanilla JS) sont vérifiables par le **Tester web Puppeteer** — lancement en browser, assertions DOM, captures d'écran. `Bubble_Sort_Visualizer` est le point d'entrée idéal recommandé par le README : périmètre borné, sortie unique, assertions déterministes (compteur de comparaisons, barres colorées).
- Les prompts **Hard/Advanced** multi-fichiers (Tauri, Python, Nim, Rust) testent l'Architect (squelette projet) et le **Tester pytest** (ex: Local_OCR, Hantavirus_Simulation). Ils servent de benchmarks de montée en complexité pour le Judge.

Réutilisabilité **Haute** : 100 % du matériel est directement utilisable comme cas de test ; aucun déchet.

## Prompts par difficulté

### Easy (3)
| Chemin | Titre | Stack/Fichiers imposés | Description courte | Intérêt comme cas de test |
|---|---|---|---|---|
| `references/Prompt-Vault/Easy/Bubble_Sort_Visualizer.md` | Basic Sorting Visualizer (Bubble Sort) | 1 fichier `index.html`, HTML/CSS/JS Vanilla, dark mode | Visualise le tri à bulles via barres verticales colorées (défaut / comparaison / trié), boutons Start/Reset, slider de vitesse, compteur de comparaisons. | **Idéal / recommandé** par le README. Périmètre minimal, sorties vérifiables (compteur, couleurs), assertions déterministes pour le Tester Puppeteer |
| `references/Prompt-Vault/Easy/ToDo_List.md` | Task Manager (7 étapes guidées) | 1 page HTML unique, Vanilla JS, `localStorage` | Tutoriel incrémental en 7 tâches : page statique → ajout → toggle done → delete → compteurs Active/Completed/Total → persistance localStorage → Clear All | Bon cas de test de la logique d'évolution/refactor. Vérifiable via clics Puppeteer + rechargement pour tester la persistance |
| `references/Prompt-Vault/Easy/Color_Palette_Generator.md` | Color Palette Generator | 1 fichier `index.html`, Vanilla JS, Clipboard API | 5 swatches plein écran avec HEX, génération aléatoire (bouton + Spacebar), verrouillage par swatch, copie au presse-papier avec toast, transitions CSS | Teste API navigateur (Clipboard) et interactions clavier. Léger bruit aléatoire (couleurs) à gérer par le Judge |

### Medium (2)
| Chemin | Titre | Stack/Fichiers imposés | Description courte | Intérêt comme cas de test |
|---|---|---|---|---|
| `references/Prompt-Vault/Medium/Pixel_Art_Editor.md` | Pixel Art Editor | 1 fichier `index.html`, Vanilla JS + Canvas API brut | Éditeur pixel-art sur `<canvas>` (16/32/64), outils Pinceau/Gomme/Seau/Pipette (flood-fill BFS maison anti-stack-overflow), palette + 8 couleurs récentes, undo/redo 20 niveaux, export PNG, autosave localStorage | Excellent défi algorithmique (flood-fill) + rendu Canvas vérifiable visuellement. Teste la robustesse (pas de stack-overflow sur 64×64) |
| `references/Prompt-Vault/Medium/Sorting_Visualization.md` | Real-time sorting visualization | 1 fichier `index.html`, Vanilla JS, CDN autorisé | Visualiseur temps réel de 6 algorithmes (Bubble, Insertion, Selection, Merge, Quick, Heap) : barres animées, sliders vitesse/taille (10-200), Start/Pause, Shuffle, stats live | Version étendue de Bubble_Sort. Teste la multiplicité d'algorithmes et la justesse des compteurs — bon benchmark de cohérence inter-algos |

### Hard (3)
| Chemin | Titre | Stack/Fichiers imposés | Description courte | Intérêt comme cas de test |
|---|---|---|---|---|
| `references/Prompt-Vault/Hard/Kanban_Board.md` | Kanban Board with Drag & Drop | 1 fichier `index.html`, Vanilla JS + HTML5 Drag&Drop natif, Google Fonts CDN, `localStorage` | Kanban complet : 4 colonnes + ajout/renommage/suppression, cartes (titre/desc/priorité/date échéance), Drag&Drop natif entre colonnes, recherche + filtre priorité, persistance totale, barre de stats, glassmorphism dark | Le plus riche des prompts single-file. Teste DnD natif, état complexe, design system — étalon pour la montée en charge sur cible Puppeteer |
| `references/Prompt-Vault/Hard/Markdown_Editor_Desktop.md` | Markdown Editor (Tauri 2 Desktop) | Projet Tauri 2 multi-fichiers, Vue 3 (Composition API) + Pinia, Vite, `marked.js` + `prism.js`, plugins Tauri fs/dialog/shell | Éditeur Markdown desktop : split editor/preview scroll synchronisé, modes Split/Preview/Focus, ouvrir/sauver natif, titre avec astérisque non-sauvé, toolbar, raccourcis, thèmes | Premier test **multi-fichiers + Architect** requis. Exige génération d'ossature Tauri/Vue cohérente — cas pytest/CLI (build, structure) plus que Puppeteer |
| `references/Prompt-Vault/Hard/Local_OCR.md` | Local LLM-powered OCR | App desktop Python, `customtkinter` + `pymupdf` (fitz) + client `ollama`, `threading`/`queue` | OCR local privacy-first via Ollama : sélection image/PDF, conversion PDF→PNG (tempfile, DPI 100-300), requêtes VLM threadées (sécurité Tk via queue), logs monospace autoscroll, sauvegarde `_extracted.md` | Cas de test **Python** (pytest) pour le workflow coding : teste threading, conventions GUI thread-safe, intégration Ollama mockable |

### Advanced (4)
| Chemin | Titre | Stack/Fichiers imposés | Description courte | Intérêt comme cas de test |
|---|---|---|---|---|
| `references/Prompt-Vault/Advanced/LLM_Speedometer.md` | LLM Speedometer (Tauri + Vue) | Tauri (Rust) + Vue.js Composition API + Vite, Chart.js/ECharts, API OpenAI-compatible | Outil desktop de benchmarking de LLM locaux : métriques temps réel (TTFT, TPOT, TPS, comptes tokens), graphes de streaming live, profils de comparaison moteurs (Ollama/vLLM/llama.cpp), endpoint+clé configurables | Cas de test pour ingestion streaming JSON + visualisation haute fréquence. Bon défi de robustesse UI (charts sans lag) |
| `references/Prompt-Vault/Advanced/Feed_Aggregator.md` | Feeder (RSS Aggregator, Full-stack Nim) | Stack Nim 2.0+ uniquement (Jester/Mummy/HappyX + `htmlgen` SSR + Pico.css + `db_sqlite`), SQLite (WAL obligatoire) | Agrégateur RSS full-stack Nim : crawler async (toutes les N min), tables feeds/articles (UTC, gestion doublons), interface SSR 2 pages, WAL mode critique | Cas de test **backend/DB** hors JS : teste persistance, async, conventions SQL (WAL, FK). Excellent étalon de polyglottisme pour le Judge |
| `references/Prompt-Vault/Advanced/Hantavirus_Simulation.md` | HantaSim (Rust + Bevy 0.18) | Rust + Bevy 0.18, approche ECS, `SimulationSet` | Simulation 2D top-down de propagation hantavirus (modèle environnemental : souris → nuages contaminés → humains). Entités Humains (5 états SIR) et Souris, stats/charts/estimation R0, UI config, save/load, cycle jour/nuit | Cas de test **Rust/Bevy ECS** complexe : ordre des systèmes, déterminisme de la simulation. Bon pour tester la conformité à un cahier technique très contraint |
| `references/Prompt-Vault/Advanced/File_Listing.md` | File Listing Application (Tauri 2) | Tauri 2 + Vue 3 + TypeScript + Rust (commandes backend) | Outil desktop de listing de fichiers : sélection dossier/dialogue + drag&drop, scan récursif via backend Rust, grille éditable (nom/dates/taille/type/tags/commentaires), hachage md5/sha256 à la demande, filtre/recherche, export CSV | Cas de test **intégration Rust↔Vue IPC** : scan FS via commandes Tauri (pas de mock frontend). Vérifiable via tests d'intégration pytest sur structure de projet |

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/Prompt-Vault/README.md` | Tableau récapitulatif des 12 prompts (nom, description, difficulté), instructions d'usage ("fournir le contenu comme prompt à un assistant IA"), note sur le format single-`index.html` par défaut | Haute — index/point d'entrée pour sélectionner un cas de test à injecter dans `tasks.json` |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/Prompt-Vault/Easy/Bubble_Sort_Visualizer.md` | Spec de coding | Cahier des charges Bubble Sort (3 couleurs, 2 boutons, slider, compteur) — contrainte single `index.html` |
| `references/Prompt-Vault/Easy/ToDo_List.md` | Spec incrémentale | 7 étapes guidées d'un Task Manager (DOM + `localStorage`) |
| `references/Prompt-Vault/Easy/Color_Palette_Generator.md` | Spec de coding | Générateur de palette 5 couleurs (Clipboard, locks, transitions) |
| `references/Prompt-Vault/Medium/Pixel_Art_Editor.md` | Spec de coding | Éditeur pixel-art Canvas (outils, flood-fill BFS, undo/redo, export PNG) |
| `references/Prompt-Vault/Medium/Sorting_Visualization.md` | Spec de coding | Visualiseur 6 algorithmes de tri (stats live, sliders) |
| `references/Prompt-Vault/Hard/Kanban_Board.md` | Spec de coding | Kanban DnD natif (4 colonnes, cartes, filtre, stats, glassmorphism) |
| `references/Prompt-Vault/Hard/Markdown_Editor_Desktop.md` | Spec de projet | Éditeur Markdown Tauri 2 (structure de projet, IPC, plugins) |
| `references/Prompt-Vault/Hard/Local_OCR.md` | Spec de projet | App OCR Python (stack customtkinter/pymupdf/ollama, thread-safety) |
| `references/Prompt-Vault/Advanced/LLM_Speedometer.md` | Spec de projet | Outil benchmark LLM (Tauri+Vue, API OpenAI-compat, métriques streaming) |
| `references/Prompt-Vault/Advanced/Feed_Aggregator.md` | Spec de projet | Agrégateur RSS full-stack Nim (schéma SQLite, async crawler, WAL) |
| `references/Prompt-Vault/Advanced/Hantavirus_Simulation.md` | Spec de projet | Simulation Bevy 0.18 (ECS, entités, systèmes, save/load) |
| `references/Prompt-Vault/Advanced/File_Listing.md` | Spec de projet | App listing fichiers Tauri 2 + Vue 3 + Rust (scan FS, hashing, CSV) |

## Exclusions conscientes
- Aucune — l'intégralité des 13 fichiers est pertinente et constitue le matériel de test du workflow coding.
