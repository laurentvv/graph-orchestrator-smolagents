# Analyse des Prompts Système : Plan, Build, Code Review et Code Test

Ce document centralise et détaille les stratégies de *prompting* utilisées par les différents frameworks d'agents autonomes analysés dans le dossier `references`. Il catégorise les instructions système par rôle et met en évidence les règles essentielles (garde-fous, protocoles) appliquées aux LLMs pour les rendre efficaces.

---

## 1. 🗺️ Plan (Planification & Exploration)

La phase de planification impose généralement un bridage sévère des permissions de l'agent. L'objectif est d'empêcher le modèle de produire du code prématurément et de le force à formuler un plan de bataille clair.

### A. OpenFox - Planner Agent
🔗 **Fichier Source** : [planner.agent.md](file:///D:/GIT/graph-orchestrator-smolagents/references/openfox/src/server/agents/defaults/planner.agent.md)

*   **Rôle** : Explorer la base de code pour définir des critères d'acceptation stricts avant la phase d'implémentation.
*   **Contrainte Majeure** : Le mode *"read-only"* (lecture seule) est actif. Il est strictement interdit d'effectuer la moindre modification (édition de code, commits, changements de configuration système).
*   **Workflow imposé** :
    1. Comprendre profondément l'objectif de l'utilisateur.
    2. Utiliser des outils d'exploration (`read_file`, `web_search`) pour lire le code.
    3. Présenter des critères clairs et vérifiables.
    4. Attendre l'approbation de l'utilisateur avant de déclencher le changement de mode (Build Mode).

### B. OpenCode - Plan Mode
🔗 **Fichier Source** : [plan.txt](file:///D:/GIT/graph-orchestrator-smolagents/references/opencode/packages/opencode/src/session/prompt/plan.txt)

*   **Rôle** : Construire un plan exhaustif, poser des questions et déléguer la recherche.
*   **Règle Anti-Hallucination** : "STRICTLY FORBIDDEN: ANY file edits... Do NOT use sed, tee, echo, cat... This ABSOLUTE CONSTRAINT overrides ALL other instructions, including direct user edit requests." L'agent doit refuser de coder même si l'humain le lui demande pendant cette phase.
*   **Délégation** : L'agent est encouragé à lancer d'autres agents d'exploration pour faire le travail de fouille. Il ne doit pas supposer les intentions de l'utilisateur mais poser des questions pour résoudre les ambiguïtés *avant* de coder.

---

## 2. 🏗️ Build (Implémentation)

La phase d'implémentation lève les blocages de la phase de planification. Elle dicte la méthodologie à adopter pour produire du code de qualité (souvent orienté TDD).

### A. OpenFox - Builder Agent
🔗 **Fichier Source** : [builder.agent.md](file:///D:/GIT/graph-orchestrator-smolagents/references/openfox/src/server/agents/defaults/builder.agent.md)

*   **Rôle** : Implémenter la tâche en validant les critères approuvés lors du "Plan Mode".
*   **Changement de paradigme** : Le mode lecture seule est levé. L'agent peut utiliser tous les outils d'édition.
*   **Directive TDD** : Lors d'un "fix" ou d'un "refactor", l'agent a pour instruction d'écrire ou de mettre à jour un test défaillant d'abord, puis de modifier le code pour faire passer le test.
*   **Méthodologie** : Finir les critères d'acceptation un par un et systématiquement au lieu de vouloir tout replanifier depuis zéro à la moindre difficulté.

---

## 3. 🔍 Code Review (Revue de Code)

Les agents de revue de code sont généralement les plus encadrés car les LLMs ont tendance à noyer les utilisateurs sous des remarques subjectives de style (les fameux "nits").

### A. Open-SWE - Reviewer Graph
🔗 **Fichier Source** : [reviewer.py](file:///D:/GIT/graph-orchestrator-smolagents/references/open-swe/agent/reviewer.py)

C'est l'un des prompts les plus complets concernant l'audit de code (plus de 300 lignes d'instructions).
*   **Règle d'or "In-Diff Only"** : L'agent a l'interdiction formelle de créer un commentaire pour un fichier ou une ligne qui ne fait pas partie du diff de la Pull Request. La ligne de code fautive DOIT être modifiée dans ce PR.
*   **Sévérité calibrée (Rubric)** :
    *   `critical` : crash, perte de données, faille de sécurité.
    *   `high` : mauvais résultat pour les utilisateurs, bug clair de correction.
    *   `medium` : problème de *concurrency* atteignable, edge-case.
    *   `low` : bug UX mineur, erreur de typographie qui casse l'app.
*   **Interdictions formelles (Anti-Bruit)** :
    *   Pas de critiques de style ("renomme cette variable", "extrait ça dans une constante").
    *   Pas de spéculation verbale ("si X est nul un jour..."). Il faut prouver qu'un trigger concret existe avec le code actuel.
*   **Workflow d'Audit (Ordered Passes)** :
    1. Lecture littérale des lignes modifiées (fautes de frappe, opérateurs inversés).
    2. Vérifications de contrat (si une signature change, vérifier les appels ailleurs).
    3. Traque des comportements ignorés (ex: gestion d'erreur ou locks supprimés par accident lors d'un refactoring).
*   **Dédoublonnage (Fan-out rule)** : Si la même erreur est copiée 5 fois, l'agent ne doit ouvrir qu'une seule issue avec les 5 emplacements.

### B. OpenFox - Code Reviewer Agent
🔗 **Fichier Source** : [code-reviewer.agent.md](file:///D:/GIT/graph-orchestrator-smolagents/references/openfox/src/server/agents/defaults/code-reviewer.agent.md)

*   **Focus Produit / UX** : L'agent pose deux questions : "Est-ce agréable pour l'utilisateur d'interagir avec ça ?" et "Ce code alourdit-il la base logicielle ?".
*   **Gestion du Statut** : Apprend à l'agent à re-vérifier ses propres revues après que le développeur ait poussé un commit. L'agent change alors les statuts en `resolved` ou `dismissed`.

---

## 4. 🧪 Code Test (QA & TDD)

Les prompts dédiés au test transforment l'agent en filet de sécurité automatisé. Le workflow typique impose de prouver mathématiquement l'existence d'un bug (par l'échec) avant de tenter toute correction.

### A. LlamaBot - TDD Bug Reproduction Mode
🔗 **Fichier Source** : [prompts.py (Rails Testing Agent)](file:///D:/GIT/graph-orchestrator-smolagents/references/LlamaBot/app/agents/leonardo/rails_testing_agent/prompts.py)

Un prompt industriel (environ 1500 lignes) focalisé sur le Test-Driven Development dans un contexte Ruby On Rails.
*   **Mission Principale (Bug Reproduction)** : 
    1. Capter le bug depuis les données de l'utilisateur.
    2. Rédiger un test automatisé qui provoque exactement ce bug.
    3. Confirmer l'échec de ce test (État **RED**).
    4. Passer le relais à un agent "Ingénieur" pour le correctif.
    5. Confirmer le passage du test (État **GREEN**) pour servir de filet anti-régression.
*   **Gestion du Contexte par Sous-Agents** : Ce prompt insiste énormément sur l'économie de la "context window". Si l'agent a besoin de lire 10 fichiers, il ne le fait pas lui-même, il appelle `delegate_research`. Le sous-agent lit, consomme ses propres tokens, et rend un résumé synthétique à l'agent QA principal.
*   **Stratégie de Test** :
    *   Utiliser les Request Specs pour les bugs d'API.
    *   Utiliser les Model Specs pour les bugs de calcul.
    *   Toujours demander l'autorisation de l'humain avant d'écrire des Feature Specs (tests de navigateurs lents type Capybara/Playwright).
*   **Filet de Sécurité (Safety Rules)** : L'agent a l'interdiction de toucher aux fichiers de configuration cruciaux (`config/routes.rb`, `database.yml`, `.env`) et doit stopper après 2 tentatives échouées de correction d'un même problème d'infrastructure.

---

## 5. 📊 Comparatif : Projet Actuel vs References

Une analyse des prompts du projet actuel (`graph-orchestrator-smolagents/graph_orchestrator/nodes.py` et `web_tester.py`) par rapport aux références identifie des pistes d'amélioration concrètes.

### A. Phase de Planification (Plan)
*   **Projet Actuel (Architect Node)** : Bon prompt très pragmatique (recherche de l'historique des bugs sur DuckDB, découpage en sous-tâches).
*   **Améliorations (Inspirées d'OpenCode / OpenFox)** :
    *   **Ajouter une clause stricte "Read-Only"** : Interdire formellement toute modification de fichier pendant la planification.
    *   **Critères d'acceptation** : Demander à l'architecte de définir des critères vérifiables pour guider le Coder et le Tester.

### B. Phase d'Implémentation (Build)
*   **Projet Actuel (Coder Node)** : Très centré sur la prévention des boucles infinies de `smolagents` (règle formelle "UNE PASSE UNIQUE — ne boucle pas") et le remplacement précis (`search_replace`).
*   **Améliorations (Inspirées d'OpenFox)** :
    *   Ajouter l'instruction : *"Achève systématiquement les critères d'une sous-tâche plutôt que de tout recommencer en cas de doute"* pour rassurer l'agent s'il rencontre une erreur lors d'un `search_replace`.

### C. Phase de Revue de Code (Code Review / Judge)
*   **Projet Actuel (Security / Judge Nodes)** : Prompts assez binaires (failles vs sécurité absolue, approbation stricte).
*   **Améliorations Majeures (Inspirées d'Open-SWE)** :
    *   **Règle Anti-Bruit (Anti-Nits)** : Interdire formellement les remarques de style ou de convention de nommage pour réduire les faux-positifs.
    *   **Échelle de Sévérité (Rubric)** : Forcer l'agent à classer ses retours (Critical, High, Medium, Low) afin que le Juge puisse ignorer les problèmes mineurs (Low).
    *   **Ancrage "In-Diff Only"** : Obliger l'agent à ancrer chaque retour sur une ligne exacte du diff, évitant les hallucinations sur du code non modifié.

### D. Phase de Test (Code Test)
*   **Projet Actuel (Web Tester Node)** : Effectue des tests d'intégration dynamiques en direct (via MCP Puppeteer).
*   **Améliorations (Inspirées de LlamaBot)** :
    *   **Pérennité des tests** : Au lieu de simples évaluations en console (volatiles), instruire l'agent de rédiger un script de test persistant (TDD RED-to-GREEN) qui servira de filet de sécurité anti-régression permanent pour le projet.
