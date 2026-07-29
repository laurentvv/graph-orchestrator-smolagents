# AGENTS.md - Spécifications de l'Agent : Gestion de l'État sur Disque

## 1. Principe Fondamental
Tu ne dois jamais te fier uniquement à ta fenêtre de contexte pour suivre l'avancement du projet. Le contexte s'altère, se compresse et s'efface. L'unique source de vérité concernant l'état du système réside dans quatre fichiers stockés sur le disque. À chaque initialisation, plantage ou redémarrage, tu dois lire ces fichiers pour reconstruire ton état de manière déterministe.

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
* **Format strict obligatoire** :
    ```markdown
    # Journal d'Exécution (Append-Only)

    ## [AAAA-MM-JJ] init | Initialisation du workspace et négociation du contrat.md
    ## [AAAA-MM-JJ] gen  | Écriture du script principal et génération des structures JSON.
    ## [AAAA-MM-JJ] eval | Échec de la validation du contrat sur le critère 2 (Structure incorrecte).
    ## [AAAA-MM-JJ] fix  | Correction de la sérialisation et ré-exécution de la boucle.
    ```

## 3. Directives Opérationnelles pour la Boucle d'Exécution

1. **Phase de Bootstrap** : Avant toute action, vérifie la présence de ces quatre fichiers. S'ils sont absents, crée-les selon les formats ci-dessus. S'ils sont présents, lis-les pour reconstruire ta mémoire immédiate.
2. **Phase d'Action** : Avant d'exécuter une tâche, écris la ligne correspondante dans le `log.md`.
3. **Phase de Synchronisation** : Après chaque écriture de fichier ou test, mets à jour le fichier de statut associé (`progress.md` ou `feature_list.json`).
4. **Gestion des Erreurs** : Si une exception survient ou si le processus s'interrompt, l'état valide est celui extrait de la dernière ligne du `log.md` combiné aux assertions de `progress.md`.
