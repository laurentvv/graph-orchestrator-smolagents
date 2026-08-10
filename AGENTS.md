# AGENTS.md - Spécifications de l'Agent : Gestion de l'État sur Disque

# PARTIE 1 : DIRECTIVES POUR L'AGENT (PROMPT)

## 1. Principe Fondamental
Tu ne dois jamais te fier uniquement à ta fenêtre de contexte pour suivre l'avancement du projet. Le contexte s'altère, se compresse et s'efface. L'unique source de vérité concernant l'état du système réside dans quatre fichiers de suivi, stockés à la racine du projet. À chaque initialisation, plantage ou redémarrage, tu dois lire ces fichiers pour reconstruire ton état de manière déterministe.

## 2. Architecture des Fichiers à Initialiser

### A. `feature_list.json`
* **Rôle** : Cartographie complète et structurée des fonctionnalités du projet.
* **Cycle de vie** : Généré lors de la planification initiale, mis à jour dès qu'une fonctionnalité change de statut.
* **Format strict** :
    ```json
    {
      "features": [
        {
          "id": "F-01",
          "name": "Nom de la fonctionnalité",
          "description": "Description claire et périmètre technique",
          "status": "pending | in_progress | completed",
          "dependencies": []
        }
      ]
    }
    ```

### B. `contract.md`
* **Rôle** : Le contrat de validation technique négocié entre la planification et l'évaluation. Il contient la liste d'assertions strictes et testables (viser entre 15 et 30 critères pour une couverture robuste).
* **Cycle de vie** : Figé juste avant l'écriture de la première ligne de code. Ne peut plus être modifié par le générateur.
* **Format strict** :
    ```markdown
    # Contrat de Validation

    ## Critères d'Acceptation Automatisés
    - [ ] Critère 1 : Le point de terminaison retourne un code 200.
    - [ ] Critère 2 : La validation du schéma JSON rejette les entrées malformées.
    - [ ] Critère 3 : Les variables d'environnement requises sont validées au démarrage.

    ## Protocole d'Évaluation
    * Commande d'exécution des tests : `pytest` / `npm test`
    * Comportement attendu : Zéro avertissement, zéro échec.
    ```

### C. `progress.md`
* **Rôle** : Tableau de bord macroscopique du sprint en cours. Permet à l'agent de savoir instantanément ce qu'il est en train de faire s'il doit redémarrer.
* **Cycle de vie** : Mis à jour à la fin de chaque itération de la boucle.
* **Format strict** :
    ```markdown
    # État d'Avancement du Sprint

    ## Objectif Actuel
    - [ ] Implémentation du module de validation des contrats.

    ## Jalons de l'Itération
    - [x] Étape 1 : Définition des interfaces et types.
    - [ ] Étape 2 : Écriture des tests unitaires (TDD).
    - [ ] Étape 3 : Écriture du code logique.
    ```

### D. Historisation Événementielle (DuckDB)
* **Rôle** : L'ancien fichier `log.md` est supprimé au profit d'une base de données analytique structurée (DuckDB). Cela évite la saturation du contexte et permet des requêtes avancées post-mortem.
* **Cycle de vie** : À chaque événement majeur (début de tâche, erreur inattendue, validation de sous-tâche), tu DOIS appeler l'outil `log_event` au lieu d'écrire dans un fichier texte.
* **Usage** : 
    ```python
    # Appel d'outil (Python CodeAgent)
    log_event(
        event_type="init", # ou "gen", "eval", "fix", "error"
        details="Initialisation du workspace et négociation du contrat."
    )
    ```

## 3. Directives Opérationnelles pour la Boucle d'Exécution

1. **Phase de Bootstrap** : Avant toute action, vérifie la présence de ces quatre fichiers. S'ils sont absents, crée-les selon les formats ci-dessus. S'ils sont présents, lis-les pour reconstruire ta mémoire immédiate.
2. **Phase d'Action** : Avant d'exécuter une tâche, écris la ligne correspondante dans le `log.md`.
3. **Phase de Synchronisation** : Après chaque écriture de fichier ou test, mets à jour le fichier de statut associé (`progress.md` ou `feature_list.json`).
4. **Gestion des Erreurs** : Si une exception survient ou si le processus s'interrompt, l'état valide est celui extrait de la dernière ligne du `log.md` combiné aux assertions de `progress.md`.
5. **Mise à jour du `README.md`** : À chaque fois que tu termines une nouvelle fonctionnalité importante, tu dois impérativement mettre à jour le fichier `README.md` avant de terminer ta tâche.

# PARTIE 2 : GUIDE D'UTILISATION POUR LE DÉVELOPPEUR

## 4. Banque de Prompts de Test (Prompt-Vault)

**Où trouver les prompts** : `references/Prompt-Vault/` (sous-module git). Classés par difficulté :
- `Easy/` — Bubble_Sort_Visualizer, Color_Palette_Generator, ToDo_List
- `Medium/` — Sorting_Visualization, Pixel_Art_Editor
- `Hard/` — Kanban_Board, Markdown_Editor_Desktop, Local_OCR
- `Advanced/` — LLM_Speedometer, Feed_Aggregator, Hantavirus_Simulation, File_Listing

Chaque `.md` est un cahier des charges structuré (souvent "1 fichier `index.html`, HTML+CSS+JS vanilla"). Voir `references/Prompt-Vault/README.md` pour le tableau récapitulatif.

## 5. Projets de Référence
**Code et audits** : Consulter `docs/references-audit/` (lié au code GitHub stocké dans `references/`). C'est une véritable mine d'or d'implémentations déjà faites, fiables et prêtes à l'emploi. N'hésitez pas à y piocher du code et à vous inspirer de ces solutions existantes plutôt que de tout réinventer.

**Cartographie Nœuds & Skills** : [`docs/NODES_AND_SKILLS.md`](./docs/NODES_AND_SKILLS.md) — inventaire complet des system prompts forcés par nœud (rôles, invariants, docstrings DSPy), des 11 skills et de leur mode de chargement (eager vs lazy F-57). À consulter pour savoir ce que voit chaque agent LLM à l'exécution, ou pour ajouter/modifier un skill.

**Refactoring Automatique des Skills (Progressive Disclosure - F-92)** : Le script `scripts/refactor_skills.py` permet de restructurer automatiquement les compétences complexes. Il découpe les longs fichiers `SKILL.md` (plus de 80 lignes) en extrayant les sections secondaires vers un sous-dossier `resources/`, et met à jour le `SKILL.md` original pour forcer l'agent à les lire à la demande (lazy loading) via l'outil `view_file`. À exécuter dès qu'un nouveau skill ajouté au dossier `skills/` devient trop volumineux.
## 6. Git & GitHub
- **Règle d'or Git** : Ne JAMAIS travailler ou pousser directement sur `main`. Avant toute modification, tu DOIS créer une nouvelle branche (ex: `feat/...` ou `fix/...`).
- **Kilo Code Review** : L'agent GitHub doit approuver la PR avant le merge. *(Note pour l'agent IA : une fois la PR soumise, arrête-toi. Ne reste pas en boucle d'attente. Tu seras réveillé une fois la review validée pour supprimer la branche et retourner sur `main`).*

## 7. Tests du Graphe (Workflow Coding)
0. **Préparation des modèles** : Utiliser le script `powershell .\scripts\download_models.ps1` pour télécharger automatiquement les fichiers `.gguf` requis (Qwen et Ornith) depuis Hugging Face vers le dossier `models/`.
1. **Préparation du prompt** : Copier un prompt depuis `references/Prompt-Vault/`. Le coller dans `tasks.json` (`coding.content`) et adapter `target_files`.
2. **Configuration** : `WORKFLOW_MODE=coding` dans `.env`. Vérifier que les chemins GGUF (`FAST_MODEL`, `REASONING_MODEL`) pointent bien vers les fichiers locaux du dossier `models/` téléchargés à l'étape 0. S'assurer que `FAST_BACKEND=spawn` et `REASONING_BACKEND=spawn` sont définis dans le `.env`.
3. **Exécution** : `uv run agent_graph.py` (ajouter `PYTHONUNBUFFERED=1` si pipe).
4. **Déroulement** : voir le diagramme complet du graphe (nœuds, modèles LLM, flux de données) dans `README.md` § « Node Graph & Data Flow ». En résumé : PromptRefiner → Router → Architect → (Coder → Linter → **Static Tester** → Tester+Security → Judge, max 3 itérations par sous-tâche) → Escalation si circuit breaker. Logs : `CODING WORKFLOW` (succès) ou `Fan-out asynchrone` (one-shot).
   - **Static Tester (F-49, 0 LLM, web-only)** : inséré entre Linter et Tester LLM. Implémente la méthodologie `debug/MANUAL_TESTER_METHODOLOGY.md` — `node --check` sur le JS inline (attrape TS-in-vanilla = page blanche), wiring `addEventListener` (attrape contrôle non branché, indétectable par screenshot), visibilité DOM DevTools (attrape éléments invisibles = bug CSS height:%). Court-circuite le Tester LLM (25 min) sur les bugs évidents en <6s. Dégradation gracieuse si `node`/Chrome absents. Opt-out `STATIC_TESTER_ENABLED=0` / `STATIC_TESTER_DEVTOOLS=0`.
   - **Tiering modèles** : `fast_model` (Qwen3.5-4B) → Coder, Router. `reasoning_model` (Ornith-1.0-9B) → PromptRefiner, Architect, Drafter, Tester, Security, Judge, Escalation. Les deux sont multimodaux (vision).
   - **Audits séquentiels sur GPU local** : `AUDIT_PARALLEL=false` (défaut) lance Tester PUIS Security (pas en parallèle) pour éviter la saturation VRAM.

*Notes* : 
- Pour valider le graphe, commencer par **Bubble_Sort_Visualizer** (Easy, 1 fichier, borné).
- **En cas de modification `.env.example`** : il faut reporter les ajouts dans `.env` local (sans toucher au contenu "secret").
## 8. Amélioration Continue (Le Rôle du Meta-Analyste)
Pour assurer l'amélioration continue de l'usine logicielle (Feature F-61), nous ne comptons pas sur un agent local autonome, mais sur une boucle de feedback hybride Humain + IA.

**Directives pour l'Assistant IA :**
1. **Exécution Autonome** : C'est **toi (l'assistant)** qui dois lancer le script `uv run python scripts/run_analyzer.py` via ton terminal (soit après un run E2E complet, soit à la demande de l'utilisateur au début d'une session). Chaque run est désormais **journalisé automatiquement** dans `logs/run-<timestamp>-<mode>.log` (Tee posé sur stdout+stderr dans `workflows.main()`) ; le script y découvre le plus récent log de lui-même (cross-plateforme, via `$LOGS_DIR`). Fini la dépendance au chemin de l'Antigravity CLI.
2. **Analyse** : Tu dois lire la sortie du script et repérer les problèmes récurrents (ex: erreurs de parsing Pydantic, syntaxe invalide comme le top-level `await`, ou crashes d'outils MCP).
3. **Validation Humaine** : Tu ne dois **jamais** modifier les règles à l'aveugle. Tu dois faire un résumé clair à l'utilisateur des problèmes trouvés, lui proposer une solution (ex: "Je propose d'ajouter cette règle stricte dans `nodes.py`"), et attendre son feu vert ("Go").
4. **Application** : Une fois la validation obtenue, interviens directement dans le code source pour durcir les prompts ou les skills.

*Exemple réel 1 : L'interdiction du top-level await dans Puppeteer et l'obligation d'utiliser des déclarations de fonction pour `evaluate_script` ont été diagnostiquées via l'analyse des crashes et fixées en direct dans les prompts des nœuds.*
*Exemple réel 2 : Pour stabiliser le petit modèle 4B, l'obligation d'utiliser des triples quotes `r\"\"\"...\"\"\"` dans les appels d'outils et l'intégration du "Monkey Testing" (clic automatique des boutons dans `evaluate_script`) ont été ajoutées dans `nodes.py`.*

## 9. Tests Rapides par Nœud (Isolation LLM — F-89)

**Problème** : Un run E2E complet (`uv run agent_graph.py`, §7) dure 30-40 min en GPU-local. Quand on modifie le prompt, un skill ou la logique d'**un seul nœud**, relancer tout le graphe pour valider la modification est un gaspillage massif — 95% du temps est passé à valider des nœuds non modifiés.

**Solution** : Le dossier `debug/` contient un **script d'isolation par nœud LLM** (Feature F-89). Chaque script appelle la **vraie fonction de production** (0 mock, 0 duplication) avec des **entrées figées** (fixtures), ce qui permet de couper, corriger, relancer en **secondes/minutes** au lieu de dizaines de minutes.

**Quand l'utiliser** : à chaque fois qu'une modification impacte un ou plusieurs nœuds (changement de prompt, de skill, de config, de logique), **avant** de lancer le run E2E complet. C'est la boucle de debug itérative recommandée.

### Scripts disponibles

| Script | Nœud testé | Commande | Usage type |
|---|---|---|---|
| `debug/run_router.py` | Router (classification langage) | `uv run python debug/run_router.py` | Valider qu'un prompt Python ne déborde pas vers JS (bug F-56a). Jeu de 5 prompts (Python/React/HTML/Rust/ambigu). |
| `debug/run_prompt_refiner.py` | PromptRefiner (meta-prompt) | `uv run python debug/run_prompt_refiner.py` | Valider la détection de termes vagues sans inventer de scope. 3 prompts (vagues/structuré/minimaliste). |
| `debug/run_architect.py` | Architect (découpage + stratégie) | `uv run python debug/run_architect.py` | Valider le découpage (1 fichier = 1 sous-tâche, stratégie techno-driven). Spec Bubble Sort par défaut. |
| `debug/run_drafter.py` | Drafter (logique pure) | `uv run python debug/run_drafter.py` | Valider la qualité du draft de logique. Sauvegarde le draft pour réinjection dans le Coder. |
| `debug/run_security.py` | Security (audit OWASP) | `uv run python debug/run_security.py` | Valider la détection XSS/eval/pickle sans faux positifs. 4 codes (propre/XSS/eval/pickle). |
| `debug/run_judge.py` | Judge (verdict final) | `uv run python debug/run_judge.py` | Valider le verdict + le fail-closed (security=None sans LLM). 4 scénarios (correct/bug/nit/fail-closed). |
| `debug/run_coder.py` | Coder (génération code) | `uv run python debug/run_coder.py` | Valider le code produit (3 fichiers). Draft optionnel : `--draft debug/drafter_isolation_out/draft_isolation.md`. |
| `debug/run_web_tester_standalone.py` | Web Tester (assertions) | `uv run python debug/run_web_tester_standalone.py` | Valider les assertions fonctionnelles sur un HTML donné. |
| `debug/isolation/run_linter.py` | Linter (déterministe, 0 LLM) | `uv run python debug/isolation/run_linter.py` | Valider le gatekeeper syntaxe (7 scénarios buggés/corrects, millisecondes). |
| `debug/validate_static_tester_live.py` | Static Tester (déterministe) | `uv run python debug/validate_static_tester_live.py` | Valider le gatekeeper DOM + wiring (2 scénarios, <6s). |

### Boucle de debug recommandée

1. **Identifier le nœud impacté** par ta modification (ex: tu as changé le prompt du Judge dans `dspy_nodes.py`).
2. **Lancer son script d'isolation** : `uv run python debug/run_judge.py`.
3. **Observer le verdict** : le script affiche le contrat (modèle, durée) + la sortie (verdict, findings, métriques).
4. **Couper si erreur**, corriger le prompt/code, relancer (la boucle prend des secondes à minutes, pas 30 min).
5. **Input ad hoc** : pour tester un cas spécifique sans modifier le script, passe l'input en CLI — `uv run python debug/run_judge.py bug` (scénario nommé) ou `uv run python debug/run_router.py "ma description de tâche"` (prompt unique), ou `@fichier` pour charger depuis un fichier.
6. **Une fois le nœud validé isolément**, relancer le run E2E complet (§7) pour valider l'intégration de bout en bout.

### Détail technique important

Tous les nœuds DSPy (Router/PromptRefiner/Architect/Drafter/Security/Judge) **ignorent** le paramètre `*_model` qu'on leur passe — le vrai modèle vient de `_run_dspy_node → model_lifecycle(spec)` qui spawn son propre llama-server. Les scripts d'isolation reproduisent donc fidèlement le comportement production (prompts F-44/F-56/F-65, DSPy, model_lifecycle), en sautant juste le reste du graphe.

Voir [`debug/isolation/README.md`](./debug/isolation/README.md) pour la convention complète (méthodologies manuelles F-55 + scripts d'isolation LLM F-89 + golden files pour les nœuds déterministes).

## 10. Run de Référence (Golden Run)

Pour toute vérification, un "Golden Run" (run E2E parfait ayant généré le code et passé tous les tests visuels, linting et validations du Juge) a été sauvegardé définitivement.

**Emplacement :** `debug/reference_run_qwen4b_bubble_sort/`
**Contenu :**
- Fichiers générés complets (`index.html`, `styles.css`, `script.js`)
- Le brouillon de l'Architecte (`draft_bubble_sort_viz_001.md`)
- Le journal d'exécution E2E (`run_full.log`) avec le tableau d'observabilité.

**Métriques clés de ce run de référence (Bubble Sort) :**
- **Durée Totale :** 1768.1 secondes (environ 29.5 minutes) sur GPU local.
- **Jetons (Tokens) :** 648 748 tokens traités au total.
- **Itérations du Coder :** Le Coder a généré le code 2 fois. La première itération comportait une erreur interceptée par les gardiens (Static Tester / Juge). La boucle d'auto-correction (F-45) l'a relancé avec le bon contexte, et la 2ème passe a été validée avec succès.
- **Modèles :** Qwen-4B (Coder) et Ornith-9B (Architect/Judge).

Ce run sert d'étalon-or pour prouver que l'orchestrateur, le *Monkey Testing* (Fuzzing UI) et les *Guardrails* syntaxiques (triples quotes) permettent à des petits modèles (4B) de réaliser des applications Vanilla JS complexes de manière fiable.
