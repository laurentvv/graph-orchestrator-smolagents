# Planification : Usine Logicielle Autonome (Graph Engineering)

Ce document traduit l'audit des références (`references_audit.md`) en une feuille de route concrète, triée par ordre d'importance critique. L'objectif est d'atteindre le "Fire and Forget" complet.

> **🎯 Principe directeur (filtre qualité des références)** — Chaque feature à venir s'appuie sur une référence qui a **fait le job en production** :
> - **Références production-éprouvées** (transposables avec confiance) : `aider` (PyPI top OpenRouter), `crush` (Charm/Go), `deer-flow` (ByteDance), `qm` (plateforme Slack/Web), `open-swe` (dérivé SWE-agent).
> - **Référence mature mais collectée** (prompts, à adapter) : `claude-code-unified-agents`.
> - **Références recherche/POC** ( RepoGraph, axon, graphify) : **non retenues** comme base de feature — trop académiques, ROI faible sur l'usage actuel (création de code de zéro, pas exploration de gros dépôts).
> Le détail des références est dans [`docs/references-audit/`](./docs/references-audit/INDEX.md).

> **📊 ÉTAT D'AVANCEMENT (2026-07-31)**
> | Priorité | Statut |
> |---|---|
> | 🔴 0. Cadre système & prompts | **Partiel** (Coder autonome ✅, Architect Read-Only ✅ via DSPy, CodeAgent ❌) |
> | 🔴 1. Édition sécurisée | **✅ TERMINÉE** (PR #3) — la plus critique, validée au run #12 |
> | 🟠 2. Auto-correction (stderr) | **✅ TERMINÉE** — troncature + Tester polyvalent multi-techno (web+python) |
> | 🟡 3. Graphe autonome (breaker/checkpoints) | **✅ TERMINÉE** — `max_iter=3` ✅, checkpoints ✅, nœud d'escalade ✅ (F-23) |
> | 🟢 4. Cartographie de code (Repo Map + KG structural) | ⏸️ **HORS-SCOPE** (références académiques/POC + usage = création de code de zéro). Palliatif conservé : tags de confiance sur claims DuckDB. |
> | 🔵 5. Auto-dépendances | **✅ TERMINÉE** (F-26) — auto-install `pip` non-persistante + relance sur `ModuleNotFoundError` |
> | 🟣 6. Feedback & Évaluation Avancée | **PARTIEL** ❌→🟡 *(Nettoyage DOM ✅ F-37 ; reste Code Review/TDD persistant/Findings/Plan lifecycle/Prompts spécialisés)* |
> | 🟤 7. Le "Shift Left" (Linter-as-a-Reviewer) | **✅ TERMINÉ** — `linter.py` (317 lignes) existe et est branché dans `workflows.py` (court-circuite le Tester si erreur de syntaxe). *Cohérence doc/code corrigée le 2026-07-31.* |
> | ⚪ 8. Middlewares d'Auto-Réparation | ❌ à faire |
> | 🔧 8-bis. Robustesse Runtime (Sandbox + Idempotence) | **PARTIEL** ❌→🟡 *(Guard bash denylist ✅ F-38 ; reste Sandbox Docker + Idempotence replays)* |
> | 🟢 9. Optimisation de l'État (Reducers/Compaction) | ❌ à faire |
> | 🔵 10. Contexte à la Demande (Skills) | ❌ à faire |
> | 🟠 11. Observabilité (Event Stream) | ❌ à faire |
> | ✨ 12. Meta-prompt (PromptRefiner avant Architect) | **✅ TERMINÉ (Phase 1)** — nœud DSPy F-39 (Kilo/Cline "Enhance Prompt" pattern). Phase 2 MIPROv2 écartée (signal biaisé mono-modèle 6 Go VRAM). |
>
> **Levier hors-plan majeur découvert et appliqué** : température du Coder 0.2 (vs 1.0 serveur) — a éliminé la moitié de la corruption.

---

## 🔴 Priorité 0 : Le Cadre Système & L'État d'Esprit (La Fondation)
*Ce sont les réglages natifs de smolagents et des prompts qui dictent le comportement global.*

> **🔎 État Actuel :** Le prompt du Coder a été amélioré, mais l'Architecte utilise la même base d'outils et peut être tenté d'écrire du code. On utilise probablement l'agent par défaut de smolagents.
> **🚀 Pourquoi ce sera mieux :** En interdisant à l'Architecte d'écrire via ses prompts système (Read-Only) et en forçant le format `CodeAgent` (génération de scripts Python pour appeler les outils au lieu de JSON), on gagne massivement en précision avec les petits LLM locaux.

- [x] **Prompts Read-Only (Architecte)** : Mettre à jour le prompt système de l'Architecte avec une directive absolue : interdiction d'utiliser des outils d'édition. Son unique livrable est le `contract.md` (TDD). — *FAIT via DSPy : l'Architect (dspy_nodes.py) n'a aucun tool d'écriture, il ne fait que planifier en JSON (ArchitectOutput).*
- [x] **Directive d'Autonomie Pure (Coder)** : Ajouter au prompt du Coder : "Ne t'arrête jamais pour poser une question. Effectue l'action suivante." — *FAIT : prompt Coder avec plan d'action strict + règle anti-boucle ("une passe unique").*
- [ ] **Transition vers `CodeAgent`** : S'assurer que tous les agents dans `dspy_nodes.py`/`nodes.py` instancient un `CodeAgent` de *smolagents* (beaucoup plus robuste que le `ToolCallingAgent` JSON classique). — *REPORTÉ. À nuancer : les 5 « Brain » (Router/Architect/Security/Judge/Escalation) ont migré en **DSPy** (meilleur pour le raisonnement pur, pas besoin d'outils) ; le **Coder** est déjà un `CodeAgent` (`nodes.py:437`). Restent en `ToolCallingAgent` : Worker/Judge/Synth/Adversary (modes one-shot/exploration) et le Web Tester. CodeAgent exécute du Python (risque `bash_command` non-sandboxé, voir Priorité 0-bis), nécessite réécriture des prompts JSON→Python. **Prérequis : nettoyer d'abord les ~400 lignes de nœuds smolagents dépréciés dans `nodes.py` (l.306-688).***
- [ ] **Spécialisation des Agents (Inspiré de claude-code-unified-agents)** : Étendre la flotte d'agents actuels (Coder, Tester, Judge) avec des profils hautement spécialisés (ex: `frontend-specialist`, `security-auditor`) en s'inspirant des prompts de la fiche **15-claude-code-unified-agents**. — *Précision (audit refondu 2026-07-31) : il y a **53** agents (et non 54), et la valeur est concentrée dans ~8 prompts purs : `python-pro` (Coder), `code-reviewer` (Judge), `security-auditor` (Security), `test-engineer` (Tester), `frontend-specialist` (Coder web), `backend-architect` (Architect), `orchestrator` (Router). Le schéma `AgentCapabilitySchema` de `agent-generator.md` fournit un modèle pour déclarer formellement un rôle. Les autres fichiers sont du code TS non portable.*

## 🔴 Priorité 1 : L'Édition Sécurisée des Fichiers (Le socle critique) ✅ TERMINÉE
*Si l'agent corrompt les fichiers, tout le reste de la boucle plantera. C'est l'urgence absolue pour les petits modèles locaux.*

> **🔎 État Actuel (`tools.py`) :** L'outil `edit_file` exige une correspondance exacte (`content.replace(old, new)`) au caractère et à l'espace près. De plus, il n'y a aucun verrou lors du Fan-out asynchrone (`asyncio.gather` dans `workflows.py`).
> **🚀 Pourquoi ce sera mieux :** Les petits LLMs échouent constamment sur l'indentation stricte. Un format `SEARCH/REPLACE` tolérant résout ce problème d'hallucination de format. Le Mutex (verrou) évitera que deux sous-tâches n'écrasent le même fichier en même temps.

- [x] **Outil "SEARCH/REPLACE" textuel** : Supprimer l'édition basée sur le remplacement strict/JSON. Créer un outil Python qui parse le format texte brut `<<<< ==== >>>>` (inspiré de `aider`). — *FAIT (PR #3) : `search_replace_utils.py` (portage Aider) + outil `@tool search_replace(path, search, replace)` avec matching tolérant (exact → indentation → ellipses).*
- [x] **Verrou d'accès (Mutex)** : Implémenter un verrou asynchrone par fichier (inspiré de `openfox`) dans `tools.py` pour empêcher l'exécution en parallèle de deux opérations d'écriture sur le même fichier. — *FAIT : `_FILE_LOCKS` (threading.Lock) dans tools.py.*
- [x] **Validation Anti-Vide** : Rejeter immédiatement toute édition qui remplace le code par des placeholders (`// ... code ici ...`). — *FAIT : garde anti-placeholder + anti-effacement dans `search_replace` ET `write_file`.*
- [ ] **Read-Before-Write Gate (Inspiré de Deer Flow / Crush)** : Implémenter un middleware qui bloque toute tentative de `write_file` ou `edit_file` si l'agent n'a pas préalablement lu le fichier dans la session courante (suivi via un hash SHA256). Cela évite les écrasements aveugles ou les corruptions de fichiers.
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
- [x] **Anti-Loop Cryptographique (Inspiré de Crush)** : Ajouter un anti-loop déterministe qui hache en SHA256 les interactions d'outils (ToolName + Input + Output). Si un Coder répète exactement la même action X fois, le circuit-breaker s'active immédiatement pour stopper l'hémorragie financière et computationnelle. — *FAIT (F-36) : `loop_guard.py` — `compute_tool_call_fingerprint` (SHA256 de ToolName + Input normalisé via `sort_keys` + strip whitespace) ; `LoopGuard.record/repeated_action/reset` ; `extract_tool_calls_from_step` (ToolCallingAgent `tool_calls` + CodeAgent `code_action`). Branché dans `run_with_retry` (param optionnel `loop_guard=None`, non-cassant) via `execute_coder_node` (seul nœud d'écriture). Reset aligné sur purge `agent.memory.steps`. Config `LOOP_GUARD_ENABLED`/`LOOP_GUARD_THRESHOLD` (défaut 3). 16 tests PASS. Nuance : on hashe `ToolName + Input` (pas l'Output — l'Output varie même en bouclant sur la même action fausse).*
- [x] **Nœud d'Escalade (Judge/Summarizer)** : Si le Coupe-Circuit s'active au bout de 3 essais, router vers un nouveau nœud qui résume les échecs ou fait appel à une API distante (modèle lourd) pour corriger l'erreur vicieuse. — *FAIT (F-23) : nœud DSPy `execute_escalation_node` qui synthétise les réfutations accumulées dans le KG en un diagnostic post-mortem structuré (cause racine + leçon + severity), le persiste (kind="escalation" + arêtes ESCALATES vers les réfutations), marque la sous-tâche "escalated". Stratégie "diagnostic seul" (pas de retry/modèle distant — réutilise le modèle de raisonnement local). Dégradation gracieuse (repli "max_iterations_reached" si désactivé ou LLM down). 8 tests PASS.*
- [x] **Persistance d'État (Checkpoints)** : Connecter la base `DuckDB` existante au cycle de vie du graphe pour écrire l'état d'exécution à chaque changement de nœud (Reprise sur erreur). — *FAIT : table `checkpoint` dans knowledge_graph.py (save/load/clear) + run_id stable (hash du contenu de tâche) + branchement dans run_coding_workflow (skip Architect + skip sous-tâches completed + reprise à l'itération). Granularité "début d'itération" (sûre/idempotente). Config FRESH_START. 12 tests PASS.* **Besoin critique résolu** : avec ~10-15 min/fichier en CPU-only, une coupure ne perd plus 40 min — la reprise est automatique.

## 🟢 Priorité 4 : ⏸️ Cartographie de code (Repo Map + KG structural) — HORS-SCOPE
*Sans cela, l'architecte navigue à l'aveugle dans les gros dépôts.*

> **🔎 État Actuel :** L'agent utilise `list_directory` et lit les fichiers manuellement, ce qui consomme des tokens. Pour l'usage actuel (création de code de zéro sur de petits projets), c'est acceptable.

### ⚖️ Décision explicite : Repo Map tree-sitter ET Knowledge Graph structural — HORS-SCOPE

> L'audit des références (fiches **05-axon**, **06-graphify**, **04-repograph**) consacre 10 entrées du Hall of Fame au « knowledge graph de code » structurel (tree-sitter + networkx, schéma `NodeLabel`/`RelType`, RRF, dead-code detection, impact analysis avec provenance). Conceptuellement riche, mais ces références sont **académiques/POC** (pas production-éprouvées) et le périmètre produit actuel ne les justifie pas.

**Décision : ne PAS intégrer de Repo Map (tree-sitter) ni de KG structural dans l'immédiat.** Raisons :
1. **Périmètre produit actuel** : l'usage dominant est la **création de code de zéro** (Prompt-Vault) sur des projets neufs et petits — pas l'exploration de gros dépôts existants. Ces briques n'apportent de valeur que sur une base de code préexistante à cartographier.
2. **Références non production-éprouvées** : RepoGraph (papier SWE-bench), axon, graphify = projets académiques/perso, contraires au principe directeur (cf. en-tête).
3. **Coût / complexité** : pipeline tree-sitter multi-langage + graphe networkx + requêtes = investissement lourd (estimé 1-2 semaines) pour un ROI faible sur l'usage actuel.

**Compromis retenu (palliatif léger, ROI bien meilleur, référencement graphify)** : enrichir le KG DuckDB existant de métadonnées de confiance/provenance — tags `EXTRACTED`/`INFERRED`/`AMBIGUOUS` + `confidence_score` + provenance edge (`via_file`/`via_location`). Concrètement : ajouter 2 colonnes au store de claims existant (pas de réécriture de persistance) pour que le Judge et le nœud d'escalade puissent distinguer un fait avéré d'une inférence. Voir fiche **06-graphify** → `graphify/extractors/models.py` et `graphify/affected.py`.

- [ ] *(palliatif, court terme)* **Tags de confiance + provenance sur les claims** : ajouter un tag `EXTRACTED`/`INFERRED`/`AMBIGUOUS` + `confidence_score` + provenance au niveau de l'edge (`via_file`/`via_location`) sur les claims/refutations DuckDB existants. Effort moyen (~2-4 jours), pas de réécriture de persistance.
- [ ] *(réévaluation, moyen terme)* **Repo Map + KG structural** : à réévaluer si l'usage évolue vers la maintenance/évolution de gros dépôts existants. Blueprints prêts (fiches **05-axon**, **06-graphify**, **04-repograph**).

## 🔵 Priorité 5 : L'Automatisation de l'Environnement
- [x] **Auto-Résolution des Dépendances** : Si le nœud `Tester` détecte un `ModuleNotFoundError`, lancer automatiquement un `uv add <package>` ou `pip install` avant de relancer les tests, évitant de gâcher un cycle LLM pour ça. — *FAIT (F-26) : `extract_missing_module` (regex + validation identifiant anti-injection) + `_install_module` (`pip install` non-persistant, jamais d'exception) branchés dans `PythonTestRunner.run()`. Au 1er échec `ModuleNotFoundError`, installe le module puis relance (cap 1 retry). Opt-out `AUTO_INSTALL_DEPS=false`. 12 tests PASS.*

## 🟣 Priorité 6 : L'Évaluation Avancée & Stratégie TDD
*Suite à l'analyse croisée des prompts systèmes de référence (Open-SWE, LlamaBot), l'évaluation du code est le prochain goulot d'étranglement qualitatif.*
Plus d'information : `system_prompts_analysis.md`

> **🔎 État Actuel :** Les nœuds Juge et Security sont binaires. Le Web Tester effectue des vérifications volatiles via Puppeteer en console sans persistance de harnais de tests.
> **🚀 Pourquoi ce sera mieux :** Empêcher le Juge de bloquer le graphe sur des "nits" (débats de nommage) accélère le workflow. Produire des tests persistants (TDD RED-to-GREEN) garantit l'anti-régression au-delà de la session courante de l'agent.

- [ ] **Code Review (Anti-Bruit & Rubric)** : Intégrer la stratégie Open-SWE dans les nœuds Security et Code Judge. Interdire les critiques de style, classer les retours (Critical, High, Medium, Low) et forcer l'ancrage strict sur le `diff` modifié pour réduire drastiquement les faux positifs et l'enlisement du Judge.
- [ ] **TDD Persistant (Web Tester)** : Modifier le workflow de test (inspiré de LlamaBot). Structurer le nœud Tester selon un pipeline strict : Bug Intake → Test Design → Failing Test (RED) → Verify (GREEN) → Hand-off. Le Testeur (web ou python) doit générer un vrai script automatisé, s'assurer qu'il échoue prouvant l'erreur, l'envoyer au Coder pour correction, puis vérifier sa réussite.
- [x] **Nettoyage DOM (Inspiré de LlamaBot)** : Pour le Web Tester, ajouter un filtre de troncature HTML (suppression des `<svg>`, `<canvas>`, et `<script>`) avant l'envoi au LLM pour économiser massivement les tokens. — *FAIT (F-37) : `dom_filter.py` — `clean_dom_for_llm` strippe `<script>/<style>/<svg>/<canvas>/<iframe>/<noscript>/<template>/<head>` + commentaires HTML (regex case-insensitive + DOTALL, variants XHTML auto-fermants), compacte whitespace, tronque à `max_chars=8000`. Sans dépendance (pas de BeautifulSoup). Branché dans `web_tester.py` : directive "NETTOYAGE DOM" dans le prompt avec un snippet JS exécuté côté navigateur via `puppeteer_evaluate` (plus efficace qu'un round-trip Python). Gain mesuré : taille ÷3 sur un HTML réaliste (test_significant_token_reduction). 18 tests PASS.*
- [ ] **Structuration des "Findings" et Déduplication (Inspiré d'Open-SWE)** : Limiter le nombre de retours du Judge (cap strict, ex: 6 maximum) pour éviter l'enlisement. Ajouter un système de fingerprinting (empreinte SHA) pour dédupliquer les erreurs d'une itération à l'autre et ne pas rabâcher les mêmes remarques.
- [ ] **Cycle de vie du Plan (Inspiré d'Open-SWE)** : Structurer l'étape de l'Architecte avec des statuts clairs (planning, ready, revising, approved). Le passage au Coder ne doit se faire que sur un statut "approved" (gate explicite). — *Référence production : fiche **09-open-swe** → `references/open-swe/agent/dashboard/plan_store.py` (`PLAN_STATUS_*`, 6 statuts, `save_plan_content`, cycle approve/reject complet).*
- [ ] **System Prompts Spécialisés (Inspiré de claude-code-unified-agents)** : Enrichir les prompts système des nœuds existants à partir des 8 prompts « purs » alignés avec les rôles du graphe — `code-reviewer` (Judge), `security-auditor` (Security), `test-engineer` (Tester : pyramide 70/20/10 + pattern AAA), `python-pro` (Coder : type hints + PEP 8), `frontend-specialist` (Coder web : a11y), `backend-architect` (Architect : 5 axes). — *Référence : fiche **15-claude-code-unified-agents** (53 agents, valeur concentrée dans ~8 prompts purs). Attention : les prompts restent souples (best practices), il faut les durcir en gates bloquants pour les rôles Judge/Security. Le schéma `AgentCapabilitySchema` de `agent-generator.md` fournit un modèle pour déclarer formellement un rôle.*

## 🟤 Priorité 7 : Le "Shift Left" (Linter-as-a-Reviewer) ✅ TERMINÉ
*Suite à l'analyse croisée des références (Aider, OpenCode), filtrer les erreurs de syntaxe de base avant d'engager l'orchestrateur lourd permet des économies massives.*

> **🔎 État Actuel :** Le graphe exécute le code (via Tester) pour capter les erreurs. C'est lent et cher si l'erreur est un simple "deux-points manquant" ou une variable non définie.
> **🚀 Pourquoi ce sera mieux :** L'utilisation de linters locaux très rapides agit comme un filtre "pas cher". Les nœuds lourdes (Tester, Judge) ne sont sollicitées que lorsque le code est syntaxiquement valide.

- [x] **Linter-as-a-Reviewer** : Intégrer un linter ultra-rapide (ex: AST Tree-sitter, Flake8, oxlint) qui s'exécute immédiatement après la génération de code du Coder. Si la compilation syntaxique échoue, forcer une boucle d'auto-correction locale et rapide sans déclencher le reste du graphe. — *FAIT : `linter.py` (317 lignes, 0 LLM) existe et est branché dans `run_coding_workflow` (`workflows.py:381-402`) — il court-circuite le nœud Tester si une erreur de syntaxe est détectée, renvoyant directement le Coder en correction. (Incohérence doc/code corrigée le 2026-07-31 : cette priorité était marquée ❌ à tort.)*

## ⚪ Priorité 8 : Middlewares d'Auto-Réparation (Anti-Crash)
*Suite à l'analyse d'Open-SWE, l'orchestrateur doit être capable de survivre aux hallucinations JSON et aux coupures systèmes.*

> **🔎 État Actuel :** Les outils crashent ou renvoient une erreur 400 (Bad Request) à l'API LLM si les arguments JSON sont mal typés. Pire, si un Checkpoint charge un historique contenant un appel d'outil sans résultat, l'API LLM plantera systématiquement en bloquant le graphe entier.
> **🚀 Pourquoi ce sera mieux :** Cacher ces erreurs au graphe principal grâce à des "Middlewares" (proxys) permet de sauver des itérations précieuses et de rendre le système 100% résilient (plus aucun crash lié à l'historique ou aux typos LLM).

- [ ] **Sanitizer (Auto-typage)** : Implémenter un proxy avant l'exécution des outils qui détecte les arguments mal formés (ex: `"1, 80"` au lieu de `80`) et les caste silencieusement pour éviter l'échec de validation Pydantic. (Validé par les approches d'Input/Output Sanitization de DeerFlow).
- [ ] **Orphan Repair (Anti-corruption d'historique)** : Au démarrage (chargement de Checkpoint), scanner l'historique des messages. Si un `ToolCall` n'a pas de réponse associée, injecter un faux message `{"status": "error", "error": "Interrompu"}` pour permettre à l'agent de reprendre au lieu de faire crasher l'API.
- [ ] **Middlewares de Contrôle d'Exécution (Inspiré de DeerFlow & Open-SWE)** :
  - *LoopDetectionMiddleware* : Détecter la stagnation et forcer une réponse finale pour stopper une boucle infinie d'outils.
  - *ToolOutputBudgetMiddleware* : Tronquer automatiquement les résultats d'outils trop longs au niveau du middleware pour protéger le budget de tokens.
  - *Circuit Breaker* : Gérer les timeouts de modèles ou les crashs distants de manière gracieuse.

## 🔧 Priorité 8-bis : Robustesse Runtime (Isolation & Idempotence)
*qm est une plateforme agent production-éprouvée (Slack/Web) ; ses primitives d'isolation et d'idempotence comblent les angles morts de l'orchestrateur actuel.*

> **🔎 État Actuel :** `bash_command` (`tools.py:208`) tourne en `subprocess.run(shell=True)` sans aucune isolation — risque d'injection et surface d'attaque réelle. C'est le **bloqueur de la transition CodeAgent** (P0 : un CodeAgent génère et exécute du Python arbitraire). Par ailleurs, les replays de checkpoint peuvent réappliquer des effets de bord (écritures fichiers, installs).
> **🚀 Pourquoi ce sera mieux :** Isoler l'exécution (sandbox) débloque le CodeAgent et sécurise le système. Garantir l'idempotence des effets de bord rend les replays/retries sûrs.

- [x] *(couche 1, faite)* **Guard bash denylist** : Avant la sandbox Docker (lourde), un guard denylist (`bash_guard.py`) bloque les commandes manifestement destructrices (`rm -rf /`, `format`, `mkfs`, `dd of=/dev/sd*`, `shutdown`, `git push --force`, `curl|sh`...) AVANT `subprocess.run(shell=True)`. C'est le premier pas concret vers la robustesse runtime ; la sandbox complète reste ci-dessous. — *FAIT (F-38) : `bash_guard.py` — `check_bash_command` renvoie `(allowed, reason)` (jamais d'exception), denylist regex case-insensitive Unix+Windows+cross. Branché dans `tools.py` `bash_command`. Opt-out `BASH_GUARD_ENABLED=false`. 66 tests PASS.*
- [ ] **Sandbox bash / pytest** : Cloisonner `bash_command` et le `PythonTestRunner` dans un environnement isolé (Docker exec ou process cloisonné avec fs/cwd restreint), au lieu du `shell=True` actuel. — *Référence production : fiche **14-qm** → `references/qm/src/sandbox/docker-exec.ts` + `local-sandbox.ts` (layers RO/RW, routing multi-backend) ; `references/aider/aider/commands.py` (`cmd_run` subprocess isolé). Débloque directement la Priorité 0 (CodeAgent). Le guard denylist (F-38) est une première couche, mais ne remplace pas l'isolation processus/fs complète.*
- [ ] **Idempotence des effets de bord (replays/retries)** : Wrapper les opérations non-idempotentes (écritures fichiers, installs pip) via un guard `once(key, fn)` indexé par `run_id`+hash, pour qu'un replay de checkpoint n'applique pas deux fois le même effet. — *Référence production : fiche **14-qm** → `references/qm/src/idempotency/idempotency-store.ts` (`once(key, fn)`, inflight set + done map, rétention 14j). Critique pour la robustesse des replays (P3 checkpoints).*

## 🟢 Priorité 9 : Optimisation de l'État du Graphe (Event-Sourcing & Reducers)
*Le maintien d'un contexte propre sur plusieurs itérations est vital pour les LLMs locaux.*

> **🔎 État Actuel :** Le graphe maintient une liste brute de messages qui grandit à l'infini, posant un risque fort de "Context Overflow".
> **🚀 Pourquoi ce sera mieux :** Inspiré par DeerFlow (Reducers typés), OpenFox (EventStore & Compaction) et surtout **qm** (compaction duale mature), structurer la mémoire par domaines empêche sa croissance linéaire.

- [ ] **Reducers d'État (DeerFlow)** : Étendre l'état du graphe (GraphState) avec des reducers (ex: `artifacts`, `todos`, `summary_text`, `delegations`) pour compacter l'état sans perte d'information critique. — *Référence : fiche **13-deer-flow-analysis** + `references/deer-flow/.../thread_state.py`.*
- [ ] **Compaction Automatique (qm)** : Intégrer un "Compactor" qui se déclenche lorsque la limite de contexte approche. Gérer la compaction via des "Context Epochs" : définir une baseline immuable et n'y rajouter que les deltas chronologiques. Remplacer l'historique brut par un résumé tout en conservant les instructions globales. — *Blueprint direct : fiche **14-qm** → `harness/context-compaction.ts` (`planCompaction`, fractions soft 0.7 / hard 0.9, préservation des paires tool_call/result, résumé incrémental via `throughSeq`) + `core/orchestrator/compaction.ts` (compaction **duale** : synchrone hard-limit + async soft-limit en tâche de fond avec lease). C'est probablement le fichier le plus précieux de tout le dossier d'audit pour ce besoin. (OpenFox/OpenCode écartés : références 🔴 non production-éprouvées.)*

## 🔵 Priorité 10 : Contexte à la Demande (Prompt-Vault / Skills)
*Le LLM n'a pas besoin de connaître toutes les documentations d'outils dès la première seconde.*

> **🔎 État Actuel :** Le prompt système initial peut devenir très lourd si on y intègre toutes les descriptions détaillées d'outils et de skills.
> **🚀 Pourquoi ce sera mieux :** Réduit drastiquement l'usage des tokens et améliore le respect des consignes grâce à un chargement "Lazy".

- [ ] **Skill Activation Middleware (Inspiré de DeerFlow)** : Ne placer que les titres et résumés des outils dans le prompt initial. Lorsqu'un outil ou skill est appelé par l'agent, le middleware s'active, lit le contenu de `SKILL.md` (ou du Prompt-Vault) et l'injecte localement dans le contexte d'exécution de cet appel.

## 🟠 Priorité 11 : Observabilité et Protocole d'Événements
*Un système opaque est impossible à déboguer.*

> **🔎 État Actuel :** Le logging se fait de manière classique vers `stdout` ou des fichiers, ce qui est difficile à exploiter par d'autres systèmes.
> **🚀 Pourquoi ce sera mieux :** Un flux d'événements strict permet l'observabilité et l'intégration de TUIs.

- [ ] **Run Event Stream (Inspiré de Deer Flow)** : Définir un contrat JSON strict (versionné) pour les événements du graphe (trace, message, tool_call, error, subagent_status). Cela permettra de brancher facilement une UI de monitoring, un TUI (terminal UI), ou de faire de l'analyse post-mortem avancée sans parser des logs texte. — *Spec concrète à ne pas réinventer : fiche **08-deer-flow** → `references/deer-flow/contracts/run_event_stream_contract.json` (17 Ko, contrat versionné avec règles frozen/additive/breaking). C'est exactement le contrat d'événements cherché. (OpenFox écarté : référence 🔴 non production-éprouvée.)*

## ✨ Priorité 12 : Meta-prompt (PromptRefiner avant l'Architect)
*L'Architect planifie mieux sur une spec bien structurée que sur un prompt utilisateur vague.*

> **🔎 État Actuel :** Le prompt utilisateur passe tel quel du fichier de tâches au Router puis à l'Architect. Aucune étape de clarification/structuration.
> **🚀 Pourquoi ce sera mieux :** Un nœud LLM qui reformule/enrichit le prompt avant l'Architect améliore la qualité du plan sur tous les runs (pattern "Enhance Prompt" éprouvé : Kilo Code, Cline, Roo Code).

- [x] **Phase 1 — Nœud PromptRefiner (F-39)** : nœud DSPy `execute_prompt_refiner_node` (gemma REASONING, `ChainOfThought`) inséré entre `task_content` et le Router dans `run_coding_workflow`. Reformule le prompt brut en spec structurée (sections Objectif/Fonctionnalités/Contraintes/Critères Given-When-Then) en connaissant le catalogue des capacités (skills + statut Context7 + testers via `_build_capabilities_summary`). Détection termes vagues (`ambiguities_detected`). Anti-invention. Branché APRÈS le `run_id` (hash sur prompt brut → reprise stable). Persistance checkpoint (`refined_prompt` skip LLM à la reprise). Opt-out `PROMPT_REFINER_ENABLED`. Dégradation gracieuse (repli prompt brut si LLM down). Context7 = citer seulement (Architect fait déjà le pré-fetch, pas de duplication). — *Inspiré de : Kilo Code/Cline/Roo Code "Enhance Prompt" + open-swe (template sortie) + claude-code requirements-analyst (liste noire termes vagues). 8 tests PASS.*
- [ ] **Phase 2 — Optimisation MIPROv2 (CHANETIER FUTUR, non démarré)** : optimiser le prompt du PromptRefiner via DSPy MIPROv2 sur métrique **end-to-end** (juger le plan produit par l'Architect, jamais le prompt réécrit isolément — doc `dspy_prompt_inconnu.md`). **Écarté ce cycle** car : (1) signal biaisé en mono-modèle GPU 6 Go (juge = architecte = même gemma qui se juge lui-même) ; (2) risque d'overfit sur 8 prompts hétérogènes du Prompt-Vault ; (3) coût GPU élevé (~75 appels) pour gain incertain. **À réévaluer** si besoin constaté en prod (specs systématiquement mauvaises sur un type de prompt récurrent) + avec un vrai dataset accumulé. La Phase 1 est la base nécessaire à toute optimisation future.
