# Planification : Usine Logicielle Autonome (Graph Engineering)

Ce document traduit l'audit des références (`references_audit.md`) en une feuille de route concrète, triée par ordre d'importance critique. L'objectif est d'atteindre le "Fire and Forget" complet.

> **📊 ÉTAT D'AVANCEMENT (2026-07-30)**
> | Priorité | Statut |
> |---|---|
> | 🔴 0. Cadre système & prompts | **Partiel** (Coder autonome ✅, Architect Read-Only ✅ via DSPy, CodeAgent ❌) |
> | 🔴 1. Édition sécurisée | **✅ TERMINÉE** (PR #3) — la plus critique, validée au run #12 |
> | 🟠 2. Auto-correction (stderr) | **✅ TERMINÉE** (PR en cours) — troncature + Tester polyvalent multi-techno (web+python) |
> | 🟡 3. Graphe autonome (breaker/checkpoints) | **Partiel** (`max_iter=3` ✅, checkpoints ✅, nœud d'escalade ❌) |
> | 🟢 4. Repo Map (tree-sitter) | ❌ à faire |
> | 🔵 5. Auto-dépendances | ❌ à faire |
>
> **Levier hors-plan majeur découvert et appliqué** : température du Coder 0.2 (vs 1.0 serveur) — a éliminé la moitié de la corruption.

---

## 🔴 Priorité 0 : Le Cadre Système & L'État d'Esprit (La Fondation)
*Ce sont les réglages natifs de smolagents et des prompts qui dictent le comportement global.*

> **🔎 État Actuel :** Le prompt du Coder a été amélioré, mais l'Architecte utilise la même base d'outils et peut être tenté d'écrire du code. On utilise probablement l'agent par défaut de smolagents.
> **🚀 Pourquoi ce sera mieux :** En interdisant à l'Architecte d'écrire via ses prompts système (Read-Only) et en forçant le format `CodeAgent` (génération de scripts Python pour appeler les outils au lieu de JSON), on gagne massivement en précision avec les petits LLM locaux.

- [x] **Prompts Read-Only (Architecte)** : Mettre à jour le prompt système de l'Architecte avec une directive absolue : interdiction d'utiliser des outils d'édition. Son unique livrable est le `contract.md` (TDD). — *FAIT via DSPy : l'Architect (dspy_nodes.py) n'a aucun tool d'écriture, il ne fait que planifier en JSON (ArchitectOutput).*
- [x] **Directive d'Autonomie Pure (Coder)** : Ajouter au prompt du Coder : "Ne t'arrête jamais pour poser une question. Effectue l'action suivante." — *FAIT : prompt Coder avec plan d'action strict + règle anti-boucle ("une passe unique").*
- [ ] **Transition vers `CodeAgent`** : S'assurer que tous les agents dans `dspy_nodes.py`/`nodes.py` instancient un `CodeAgent` de *smolagents* (beaucoup plus robuste que le `ToolCallingAgent` JSON classique). — *REPORTÉ : 7 agents en ToolCallingAgent. CodeAgent exécute du Python (risque bash_command non-sandboxé), nécessite réécriture des prompts JSON→Python. Cycle suivant.*

## 🔴 Priorité 1 : L'Édition Sécurisée des Fichiers (Le socle critique) ✅ TERMINÉE
*Si l'agent corrompt les fichiers, tout le reste de la boucle plantera. C'est l'urgence absolue pour les petits modèles locaux.*

> **🔎 État Actuel (`tools.py`) :** L'outil `edit_file` exige une correspondance exacte (`content.replace(old, new)`) au caractère et à l'espace près. De plus, il n'y a aucun verrou lors du Fan-out asynchrone (`asyncio.gather` dans `workflows.py`).
> **🚀 Pourquoi ce sera mieux :** Les petits LLMs échouent constamment sur l'indentation stricte. Un format `SEARCH/REPLACE` tolérant résout ce problème d'hallucination de format. Le Mutex (verrou) évitera que deux sous-tâches n'écrasent le même fichier en même temps.

- [x] **Outil "SEARCH/REPLACE" textuel** : Supprimer l'édition basée sur le remplacement strict/JSON. Créer un outil Python qui parse le format texte brut `<<<< ==== >>>>` (inspiré de `aider`). — *FAIT (PR #3) : `search_replace_utils.py` (portage Aider) + outil `@tool search_replace(path, search, replace)` avec matching tolérant (exact → indentation → ellipses).*
- [x] **Verrou d'accès (Mutex)** : Implémenter un verrou asynchrone par fichier (inspiré de `openfox`) dans `tools.py` pour empêcher l'exécution en parallèle de deux opérations d'écriture sur le même fichier. — *FAIT : `_FILE_LOCKS` (threading.Lock) dans tools.py.*
- [x] **Validation Anti-Vide** : Rejeter immédiatement toute édition qui remplace le code par des placeholders (`// ... code ici ...`). — *FAIT : garde anti-placeholder + anti-effacement dans `search_replace` ET `write_file`.*
- [x] *(bonus hors-plan)* **Température du Coder 0.2** — *FAIT (PR #3) : le défaut serveur était 1.0 (chat créatif) → corruption aléatoire. Config `CODER_TEMPERATURE=0.2` + Modelfile. Levier découvert par l'utilisateur, a éliminé la moitié du problème de corruption.*

## 🟠 Priorité 2 : La Boucle d'Auto-Correction (Le feedback)
*Un modèle fera toujours des erreurs de syntaxe. L'autonomie passe par sa capacité à se réparer seul.*

> **🔎 État Actuel :** Le graphe ne filtre pas intelligemment la sortie d'erreur (`stderr`) du nœud Tester.
> **🚀 Pourquoi ce sera mieux :** Si un script Python crache 500 lignes de Traceback, le LLM va les avaler à chaque itération. Au bout du 3ème essai, la fenêtre de contexte explosera ("Context Overflow"), provoquant un "oubli" des instructions de l'Architecte. La troncature garantit une boucle infinie stable en mémoire.

- [x] **Capture robuste du `stderr`** : Dans le nœud `Tester`, exécuter le code dans un sous-processus isolé et capturer la sortie d'erreur exacte. — *FAIT : `PythonTestRunner` (package `testers/`) lance `pytest` en subprocess via `sys.executable`, capture stdout+stderr+exit code. Le `WebTestRunner` capture les erreurs console JS via MCP Puppeteer (skill enrichi exigeant un rapport structuré).*
- [x] **Troncature anti "Context Overflow"** : Créer une fonction utilitaire qui coupe les grosses Tracebacks Python (ex: garder les 20 premières et 20 dernières lignes) avant de les renvoyer au `Coder`, pour sauver la mémoire du LLM. — *FAIT : `feedback_utils.py` (`truncate_output` head+tail + `truncate_history` plafonné) branché aux 3 points de la boucle (Tester→Judge, Judge→DuckDB→Coder, `bash_command`). Troncature à la LECTURE (contenu DuckDB intégral). 4 settings config.*
- [x] *(bonus hors-plan, décision utilisateur)* **Tester polyvalent multi-techno** : le nœud Tester n'est plus cloisonné au web. `execute_tester_node` est un dispatcher qui route selon la techno détectée (redondance Router + extensions) vers N runners dédiés (web, python, rust/ts futurs). Architecture extensible : ajouter une techno = 1 module + 1 skill + 1 ligne registre.

## 🟡 Priorité 3 : Le Graphe Autonome et ses Sécurités (L'Orchestration)
*Sans limites, un agent bloqué bouclera à l'infini et videra vos ressources.*

> **🔎 État Actuel (`workflows.py`) :** Il y a déjà un concept de `max_iter = 3` (bravo !), et les découvertes sont stockées dans `DuckDB`. Cependant, l'exécution elle-même reste une boucle Python en RAM.
> **🚀 Pourquoi ce sera mieux :** En cas de micro-coupure réseau (API) ou de plantage inattendu, une boucle Python en RAM est détruite. L'ajout de Checkpoints (comme dans *LangGraph*) permet de sauvegarder l'état sur disque à chaque nœud et de reprendre l'usine exactement là où elle a planté, économisant du temps et de l'argent.

- [x] **Le Coupe-Circuit (Circuit Breaker)** : Renforcer le compteur `retry_count` existant dans l'état global du graphe (`GraphState`). — *FAIT (préexistant) : `max_iterations=3` dans le workflow coding, la boucle s'arrête et passe à la sous-tâche suivante.*
- [ ] **Nœud d'Escalade (Judge/Summarizer)** : Si le Coupe-Circuit s'active au bout de 3 essais, router vers un nouveau nœud qui résume les échecs ou fait appel à une API distante (modèle lourd) pour corriger l'erreur vicieuse.
- [x] **Persistance d'État (Checkpoints)** : Connecter la base `DuckDB` existante au cycle de vie du graphe pour écrire l'état d'exécution à chaque changement de nœud (Reprise sur erreur). — *FAIT : table `checkpoint` dans knowledge_graph.py (save/load/clear) + run_id stable (hash du contenu de tâche) + branchement dans run_coding_workflow (skip Architect + skip sous-tâches completed + reprise à l'itération). Granularité "début d'itération" (sûre/idempotente). Config FRESH_START. 12 tests PASS.* **Besoin critique résolu** : avec ~10-15 min/fichier en CPU-only, une coupure ne perd plus 40 min — la reprise est automatique.

## 🟢 Priorité 4 : L'Intelligence Contextuelle (Repo Map)
*Sans cela, l'architecte navigue à l'aveugle dans les gros dépôts.*

> **🔎 État Actuel :** L'agent doit utiliser `list_directory` et lire les fichiers manuellement, ce qui consomme énormément de tokens.
> **🚀 Pourquoi ce sera mieux :** L'injection automatique d'un arbre syntaxique permet au LLM de comprendre instantanément l'architecture du projet (quelles classes sont où) sans ouvrir les fichiers.

- [ ] **Générateur de Repo Map** : Intégrer `tree-sitter` (ou `ctags`) pour parser le dépôt de l'utilisateur et générer un squelette (classes, fonctions) à injecter dans le prompt initial.

## 🔵 Priorité 5 : L'Automatisation de l'Environnement
- [ ] **Auto-Résolution des Dépendances** : Si le nœud `Tester` détecte un `ModuleNotFoundError`, lancer automatiquement un `uv add <package>` ou `pip install` avant de relancer les tests, évitant de gâcher un cycle LLM pour ça.

