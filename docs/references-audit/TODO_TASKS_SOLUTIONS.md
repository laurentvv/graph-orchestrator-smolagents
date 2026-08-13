# Audit des Solutions de Gestion des TODOs et Tâches (Task/Plan Trackers)

Ce document rassemble et analyse en détail les 4 approches majeures trouvées dans le dossier `references/` pour la gestion dynamique des tâches (TODO list) par les agents IA. 

L'objectif de ces systèmes est double :
1. **Empêcher l'agent de boucler** ou de perdre son focus en le forçant à structurer son exécution.
2. **Fournir un retour visuel (UX)** à l'utilisateur pour qu'il comprenne ce que l'agent est en train de faire.

---

## 1. L'Approche "State Reducer & UI Feedback" (LlamaBot)
**Idéale pour :** Un retour visuel direct à l'utilisateur et une intégration simple avec LangGraph.

LlamaBot utilise une approche où la liste de TODOs fait partie intégrante de l'état (State) de l'agent. Les TODOs servent de pont de communication asynchrone entre le raisonnement caché de l'agent et l'interface utilisateur.

### 🔗 Fichiers de référence pour copie de code :
- **L'outil :** [`references/LlamaBot/app/agents/leonardo/rails_agent/tools.py`](references/LlamaBot/app/agents/leonardo/rails_agent/tools.py#L162-L172)
- **Le schéma de l'état :** [`references/LlamaBot/app/agents/leonardo/rails_agent/state.py`](references/LlamaBot/app/agents/leonardo/rails_agent/state.py#L19)
- **Les prompts :** [`references/LlamaBot/app/agents/leonardo/rails_agent/prompt_with_capybara.py`](file:///D:/GIT/graph-orchestrator-smolagents/references/LlamaBot/app/agents/leonardo/rails_agent/prompt_with_capybara.py#L55)

### 💡 Mécanismes Clés :
- **L'état (State) :** Les TODOs sont définis dans le `AgentState` avec un *reducer* (`operator.add` ou remplacement selon la configuration) : 
  ```python
  todos: Annotated[NotRequired[list[Todo]], operator.add]
  ```
- **L'outil `write_todos` :** L'outil prend simplement une liste d'objets `Todo` (avec `content` et `status`) et remplace l'état actuel.
- **Directives de Prompting (Le secret de la réussite) :** L'agent est contraint très fortement par son prompt système pour qu'il n'oublie pas de cocher les cases :
  - *"The user cannot see your reasoning - TODOs show your progress. Create a visible task list for any code change."*
  - *"ALWAYS make sure that you end with updating the TODOs, and then telling the user what you have accomplished."*
  - *"Keep TODOs accurate in real time; do not leave work “done” but unmarked."*

---

## 2. L'Approche "Nag Reminder" (learn-claude-code / s05_todo_write)
**Idéale pour :** Les petits modèles locaux qui ont tendance à oublier leurs instructions après quelques itérations.

Cette approche est une implémentation pure Python (sans framework externe) qui inclut des gardes-fous contre les hallucinations du modèle.

### 🔗 Fichiers de référence pour copie de code :
- **L'orchestrateur complet :** [`references/learn-claude-code/s05_todo_write/code.py`](references/learn-claude-code/s05_todo_write/code.py)

### 💡 Mécanismes Clés :
- **Validation Défensive (`_normalize_todos`) :** Les LLMs (surtout les petits) peuvent renvoyer un tableau JSON mal formaté ou une chaîne Python au lieu d'un vrai JSON. Cette fonction utilise un fallback `ast.literal_eval` pour récupérer la donnée coûte que coûte.
- **Le Nag Reminder (Rappel insistant) :** La boucle principale compte les itérations (`rounds_since_todo`). Si l'agent fait **3 appels d'outils consécutifs sans mettre à jour ses TODOs**, le système force un rappel :
  ```python
  if rounds_since_todo >= 3 and messages:
      messages.append({"role": "user",
                       "content": "<reminder>Update your todos.</reminder>"})
      rounds_since_todo = 0
  ```
- **Affichage console :** L'outil `todo_write` génère automatiquement un affichage propre dans le terminal avec des icônes (`▸` en cours, `✓` terminé).

---

## 3. L'Approche DAG / Graphe de Dépendances (learn-claude-code / s12_task_system)
**Idéale pour :** Les gros chantiers découpés par un Architecte, où certaines tâches sont bloquées par d'autres (ex: "Créer la DB avant de coder l'API").

Au lieu d'une simple liste, ce système implémente un "Directed Acyclic Graph" (DAG) complet, adossé à des fichiers physiques.

### 🔗 Fichiers de référence pour copie de code :
- **Le gestionnaire de tâches :** [`references/learn-claude-code/s12_task_system/code.py`](file:///D:/GIT/graph-orchestrator-smolagents/references/learn-claude-code/s12_task_system/code.py)

### 💡 Mécanismes Clés :
- **Persistance JSON sur disque :** Chaque tâche est modélisée par une `dataclass` et sauvegardée sous forme de fichier JSON unique (ex: `.tasks/task_16234.json`).
- **Dépendances Bloquantes (`blockedBy`) :** Le schéma de la tâche inclut un tableau d'IDs de tâches dont elle dépend.
  ```python
  def can_start(task_id: str) -> bool:
      # Vérifie que toutes les dépendances (blockedBy) sont en status 'completed'
  ```
- **Flotte d'Outils (5 outils distincts) :** L'agent dispose d'outils atomiques : `create_task`, `list_tasks`, `get_task`, `claim_task`, et `complete_task`.
- **Feedback "Unblocked" :** Lorsque l'agent appelle `complete_task`, la fonction vérifie si d'autres tâches viennent d'être débloquées et l'affiche à l'agent : `Unblocked: Setup Database`.

---

## 4. L'Approche "Fichier Markdown & Lifecycle" (open-swe)
**Idéale pour :** Avoir un document "cahier des charges" manipulable directement par un humain dans le dossier de travail.

L'agent n'a pas d'outils "spéciaux" pour ses TODOs. Il lit et écrit dans un fichier Markdown classique, et l'orchestrateur supervise le statut global de ce fichier.

### 🔗 Fichiers de référence pour copie de code :
- **Le gestionnaire de cycle de vie :** [`references/open-swe/agent/dashboard/plan_store.py`](file:///D:/GIT/graph-orchestrator-smolagents/references/open-swe/agent/dashboard/plan_store.py)

### 💡 Mécanismes Clés :
- **Fichier Sandboxé (`/workspace/plans`) :** Le plan est un fichier `.md` injecté dans le dossier cible. L'agent doit le modifier en utilisant ses outils standards d'édition de texte (ex: `search_replace`).
- **Gestionnaire d'États (Macro-Statut) :** Le fichier en lui-même (et non ses sous-tâches) possède un cycle de vie contrôlé par l'orchestrateur : `PLAN_STATUS_PLANNING`, `READY`, `SHARED`, `REVISING`, `APPROVED`, `CANCELLED`.
- **Commentaires des Reviewers :** Lorsqu'un agent Evaluateur/Juge intervient, il ne modifie pas le plan, mais ajoute des commentaires dans un store externe (`PLAN_COMMENTS_NAMESPACE`), qui sont ensuite restitués au codeur pour qu'il corrige le tir.

---

## 5. Stratégies de Découpage (Task Decomposition)
Au-delà du simple suivi, les références mettent en œuvre des stratégies spécifiques (Prompt Engineering + Rôles) pour forcer le LLM à découper intelligemment une demande utilisateur floue en "mini-tâches" concrètes.

### A. La décomposition itérative orientée MVP (LlamaBot)
LlamaBot ne possède pas d'agent "Planner" distinct, il oblige l'agent d'exécution à planifier avant d'agir via son prompt système.
- **🔗 Fichier :** [`references/LlamaBot/app/agents/leonardo/rails_agent/prompt_with_capybara.py`](file:///D:/GIT/graph-orchestrator-smolagents/references/LlamaBot/app/agents/leonardo/rails_agent/prompt_with_capybara.py)
- **💡 Mécanisme :** Le prompt dicte : *"Create a tiny, testable MVP roadmap as TODOs... Define explicit acceptance criteria per step"*. L'obligation d'utiliser l'outil `write_todos` dès le premier tour force le LLM à structurer son approche (Chain-of-Thought) avant d'écrire la moindre ligne de code.

### B. Le "Split Check" par Couches Architecturales (LlamaBot - Ticket Mode)
C'est la méthode de décomposition algorithmique la plus aboutie des références. 
- **🔗 Fichier :** [`references/LlamaBot/app/agents/leonardo/rails_ticket_mode_agent/prompts.py`](file:///D:/GIT/graph-orchestrator-smolagents/references/LlamaBot/app/agents/leonardo/rails_ticket_mode_agent/prompts.py)
- **💡 Mécanisme :** Le LLM doit remplir une grille stricte d'évaluation des "Layers" (Modèle, Contrôleur, Vue, DB). S'il détecte que 3+ couches sont touchées, le prompt l'oblige à la scinder immédiatement en 2 ou 3 sous-tickets séquentiels. Il génère alors une section obligatoire **"Recommended Split"** et refuse de coder un ticket global.

### C. La décomposition déléguée via Subagents (learn-claude-code / deer-flow)
- **🔗 Fichier :** [`references/learn-claude-code/README.md`](file:///D:/GIT/graph-orchestrator-smolagents/references/learn-claude-code/README.md) (s06_subagent)
- **💡 Mécanisme :** *"Big tasks split small, each subtask gets clean context"*. Plutôt que de lister des TODOs à cocher dans sa propre boucle, l'agent principal éclate le problème et délègue chaque morceau à un sous-agent isolé (via un outil `task_tool`). C'est l'approche privilégiée par **deer-flow** pour empêcher l'agent de saturer sa mémoire sur les gros chantiers.

---

## 📝 Recommandations d'Implémentation pour le Projet Actuel
Si l'objectif est d'avoir des TODOs générés par l'Architecte qui se cochent **au fur et à mesure de l'exécution du Codeur**, la meilleure combinaison serait :

1. **Génération initiale (Architecte)** : L'architecte définit le tableau initial des TODOs (format JSON) et le stocke dans le Knowledge Graph (DuckDB).
2. **Exécution (Codeur)** : Utiliser le modèle de **LlamaBot** en équipant le Coder d'un outil `update_task_status(task_id, status)`.
3. **Robustesse (Nag Reminder)** : Intégrer le **Nag Reminder** de `learn-claude-code (s05)` dans la boucle `run_with_retry` du Coder. Si le Coder boucle sur du code sans mettre à jour les tâches terminées, le `LoopGuard` lui injecte un rappel ferme.
4. **Validation (Web Tester / Judge)** : L'agent de test peut invalider une tâche et repasser son statut à `in_progress` s'il détecte une anomalie.
