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

### D. `log.md`
* **Rôle** : Journal d'exécution chronologique en mode ajout seul (append-only). Rien ne doit y être effacé. Chaque événement majeur y est empilé.
* **Cycle de vie** : Une entrée est ajoutée au début et à la fin de chaque action.
* **Format strict obligatoire** (inclure l'heure exacte) :
    ```markdown
    # Journal d'Exécution (Append-Only)

    ## [AAAA-MM-JJ HH:MM:SS] init | Initialisation du workspace et négociation du contrat.md
    ## [AAAA-MM-JJ HH:MM:SS] gen  | Écriture du script principal et génération des structures JSON.
    ## [AAAA-MM-JJ HH:MM:SS] eval | Échec de la validation du contrat sur le critère 2 (Structure incorrecte).
    ## [AAAA-MM-JJ HH:MM:SS] fix  | Correction de la sérialisation et ré-exécution de la boucle.
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

## 6. Git & GitHub
- **Kilo Code Review** : L'agent GitHub doit approuver la PR avant le merge. *(Note pour l'agent IA : une fois la PR soumise, arrête-toi. Ne reste pas en boucle d'attente. Tu seras réveillé une fois la review validée pour supprimer la branche et retourner sur `main`).*

## 7. Tests du Graphe (Workflow Coding)
1. **Préparation** : Copier un prompt depuis `references/Prompt-Vault/`. Le coller dans `tasks.json` (`coding.content`) et adapter `target_files`.
2. **Configuration** : `WORKFLOW_MODE=coding` dans `.env`. Vérifier les chemins GGUF (`FAST_MODEL`, `REASONING_MODEL`) et s'assurer que `FAST_BACKEND=spawn` et `REASONING_BACKEND=spawn` sont définis dans le `.env`.
3. **Exécution** : `uv run agent_graph.py` (ajouter `PYTHONUNBUFFERED=1` si pipe).
4. **Déroulement** : voir le diagramme complet du graphe (nœuds, modèles LLM, flux de données) dans `README.md` § « Node Graph & Data Flow ». En résumé : PromptRefiner → Router → Architect → (Coder → Linter → **Static Tester** → Tester+Security → Judge, max 3 itérations par sous-tâche) → Escalation si circuit breaker. Logs : `CODING WORKFLOW` (succès) ou `Fan-out asynchrone` (one-shot).
   - **Static Tester (F-49, 0 LLM, web-only)** : inséré entre Linter et Tester LLM. Implémente la méthodologie `debug/MANUAL_TESTER_METHODOLOGY.md` — `node --check` sur le JS inline (attrape TS-in-vanilla = page blanche), wiring `addEventListener` (attrape contrôle non branché, indétectable par screenshot), visibilité DOM DevTools (attrape éléments invisibles = bug CSS height:%). Court-circuite le Tester LLM (25 min) sur les bugs évidents en <6s. Dégradation gracieuse si `node`/Chrome absents. Opt-out `STATIC_TESTER_ENABLED=0` / `STATIC_TESTER_DEVTOOLS=0`.
   - **Tiering modèles** : `fast_model` (gemma-4-E4B) → Coder, Router, Judge. `reasoning_model` (gemma-4-12B) → PromptRefiner, Architect, Tester, Security, Escalation. Les deux sont multimodaux (vision).
   - **Audits séquentiels sur GPU local** : `AUDIT_PARALLEL=false` (défaut) lance Tester PUIS Security (pas en parallèle) pour éviter la saturation VRAM.

*Notes* : 
- Pour valider le graphe, commencer par **Bubble_Sort_Visualizer** (Easy, 1 fichier, borné).
- **En cas de modification `.env.example`** : il faut reporter les ajouts dans `.env` local (sans toucher au contenu "secret").