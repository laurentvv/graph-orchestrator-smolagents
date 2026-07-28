# Guide de Standardisation : Architecture de Systèmes Agentiques en Graphes

> Ce document est le manifeste de référence du projet. Il encode la philosophie d'architecture
> (transition du linéaire vers l'ingénierie de graphes) et sert de boussole pour les décisions
> de conception futures.

---

## Mappage guide ↔ implémentation

Tableau d'écart entre les concepts du guide et leur couverture actuelle dans `graph_orchestrator/`.

| § | Concept du guide | Statut | Implémentation |
|---|------------------|--------|----------------|
| 2 | Nœud atomique + schéma JSON + retry sur non-conformité | ✅ | `models.py` (Pydantic) + `run_with_retry` |
| 2 | Arête = vrai transfert de donnée (supprimer fausses arêtes) | ✅ | worker→judge→synch passent des données réelles |
| 2 | Testable en isolation, remplaçable par contrat | ✅ | tests unitaires + tiering swappable |
| 3 | Topologie Diamant (Fan-out → **Reduce** → Synth) | ✅ | `execute_reduce_node` (flatten + dedupe + filter) |
| 3 | `parallel()` = barrière vs `pipeline()` = streaming | ✅ | `asyncio.gather` = barrière (justifiée : le juge dépend strictement de tous les workers) |
| 3 | Temps = nœud le plus lent, pas la somme | ✅ | Parallélisation effective |
| 4 | Orchestration par code (0 token de coordination) | ✅ | Python async, pas de routeur LLM |
| 4 | Tiering de modèles | ✅ | `qwen3.5:2b` / `gemma-4-E4B-it-qat` |
| 5 | **Vérification Adversaire** (sceptiques indépendants) | ✅ | `execute_adversary_node` : N sceptiques en parallèle, vote à la majorité |
| 5 | **Cycles de Convergence** (loop-until-dry + dédup vs déjà-vu) | ✅ | `run_exploration_workflow` : dédup contre approuvés **et** rejets |
| 5 | Isolation des échecs (erreur = donnée manquante) | ✅ | `execute_reduce_node` filtre les `None`/doublons sans crash |
| 5 | Isolation par Worktrees | ➖ | N/A (pas de manipulation de fichiers) |
| 5 | **Human-in-the-loop** (nœud d'approbation) | ✅ | `hitl_checkpoint` (prompt console, désactivable) |

---

# 1. Introduction : La Transition de l'IA Linéaire vers l'Ingénierie de Graphes

L'industrie de l'IA générative atteint un point d'inflexion critique : l'obsolescence du "Prompt Engineering" au profit de l'Ingénierie de Graphes. Jusqu'à présent, la majorité des implémentations en entreprise reposent sur des scripts séquentiels, de véritables "graphes dégénérés" où chaque étape attend passivement la fin de la précédente. Ce modèle linéaire constitue un plafond de verre technologique : il sature les fenêtres de contexte, explose les coûts et s'effondre à la moindre instabilité d'un nœud.

Le passage à l'architecture en graphe permet de structurer l'intelligence non plus comme une discussion, mais comme un système distribué. En isolant les tâches et en orchestrant des flottes d'agents, nous passons d'une IA qui "répond" à une IA qui "exécute" des missions complexes à une échelle auparavant inaccessible.

### Analyse comparative des approches

| Critère | L'Approche Linéaire Classique | L'Approche par Graphe Agentique |
|---------|-------------------------------|---------------------------------|
| Latence | Élevée (exécution séquentielle) | Optimisée (parallélisation massive) |
| Utilisation des jetons | Inefficace (accumulation du contexte) | Économe (contexte isolé par nœud) |
| Gestion du Contexte | Partagée & Saturée | Isolée & Localisée |
| Robustesse | Fragile (rupture en cascade) | Résiliente (isolation des échecs) |

**L'impact stratégique :** Ce changement de paradigme décuple la capacité d'absorption du contexte. Là où un agent linéaire sature après quelques documents, l'ingénierie de graphe permet de traiter des volumes virtuellement infinis (audits de code massifs, scans de marché exhaustifs) en distribuant la charge sur une topologie optimisée.

> La performance d'un système ne dépend plus de la puissance d'un prompt unique, mais de la rigueur des contrats entre ses composants.

# 2. Anatomie Technique : Nœuds, Arêtes et Contrats de Données

Pour garantir la parallélisation, l'architecte doit définir des frontières strictes entre chaque unité de travail. Sans une isolation rigoureuse, les agents interfèrent, polluant l'état global du système.

### Définition des composants

- **Le Nœud (L'Unité de Travail) :** Chaque nœud doit être une tâche atomique et délimitée. L'usage de schémas JSON est ici impératif : ils agissent comme une validation au niveau de la couche "tool-call". Si l'agent produit une sortie non conforme, le système force un nouvel essai avant même que la donnée n'atteigne le reste du graphe, garantissant l'intégrité du flux.
- **L'Arête (Le Contrat de Dépendance) :** Une arête n'est pas une simple transition chronologique ("et ensuite"), mais un transfert de données nécessaire. Si le nœud B ne consomme pas l'output du nœud A, l'arête est factice. Supprimer ces "fausses arêtes" est le premier levier pour réduire la latence inutile.

**L'impact stratégique :** Cette modularité permet de tester chaque nœud en isolation et de remplacer n'importe quel composant (par exemple, passer d'un modèle lourd à un modèle léger) sans compromettre le système global, tant que le contrat de données (entrée/sortie) est respecté.

> L'agencement de ces contrats définit la topologie du succès.

# 3. Topologie de Référence : Le Modèle "Diamant" et Parallélisme

La topologie d'un système est le levier principal de sa performance temporelle (wall-clock time). Le modèle le plus robuste pour les flux d'entreprise est le modèle en "Diamant".

### Structure du Diamant (Split → Work → Merge)

Cette architecture repose sur un cycle précis : **Fan-out → Reduce → Synthesize**.

1. **Fan-out (Éventail) :** Une phase de planification où la mission est divisée en plusieurs thunks (unités d'exécution) lancés simultanément.
2. **Reduce (Compression) :** Étape cruciale gérée par du code pur. On y effectue des opérations de type `flatten`, `dedupe` et `filter`. L'usage de `.filter(Boolean)` après un appel parallèle permet de gérer proprement les échecs (un thunk qui échoue renvoie `null` sans bloquer le reste de la flotte).
3. **Synthesize (Synthèse) :** Un agent expert compile les données filtrées pour produire le résultat final.

Le choix de la synchronisation est ici déterminant :

- La fonction `parallel()` agit comme une **barrière de latence** : elle attend que chaque nœud ait terminé. À n'utiliser que si une interdépendance stricte l'exige.
- Le `pipeline()` permet un flux continu (streaming) : chaque élément traverse le graphe dès qu'il est prêt. Le pipeline doit être votre choix par défaut pour minimiser le temps de traitement global.

**L'impact stratégique :** Le modèle diamant permet d'exécuter des audits de sécurité sur des centaines de fichiers simultanément. Séparé n'est pas égal à synchronisé : le graphe distribue la complexité pour que le temps final ne soit que celui du nœud le plus lent, et non la somme de tous.

> L'efficacité structurelle n'est viable qu'en maîtrisant l'économie des jetons.

# 4. Stratégies d'Efficacité Opérationnelle et Optimisation des Coûts

L'architecture système est le levier premier de réduction des coûts. Dans un graphe bien conçu, le coût de coordination doit être nul.

### Optimisation des ressources

- **Orchestration par Code (Déterminisme) :** Le contrôle de flux est du code, pas une conversation. Utiliser du code pour diriger les données entre les nœuds réduit le coût de coordination à zéro jeton. L'orchestration devient déterministe et prévisible, éliminant les "surprises" de routage des agents superviseurs.
- **Tiering de Modèles :** Via l'option `model` dans l'appel agent(), nous segmentons l'intelligence :
  - Les nœuds répétitifs (extraction, classification) utilisent des modèles légers.
  - Seuls les nœuds de synthèse ou de jugement critique sollicitent les modèles de pointe.

**L'impact stratégique :** Cette approche transforme un graphe potentiellement gourmand en un actif économique viable à l'échelle industrielle. On ne paie la "haute intelligence" que là où elle apporte une valeur ajoutée mesurable.

> La réduction des coûts sert de fondation à la mise en place de protocoles de fiabilité avancés.

# 5. Fiabilité et Convergence : Vérification et Cycles

La supériorité des graphes réside dans la vérification indépendante. L'auto-correction d'un agent unique est un mythe ; la confiance naît de l'examen contradictoire.

### Protocoles de Confiance et Résilience

- **Vérification Adversaire :** Déploiement de "sceptiques" indépendants pour tenter de réfuter chaque résultat. Ce mécanisme transforme l'IA d'un moteur de génération en un système de confiance.
- **Cycles de Convergence :** Pour les tâches d'exploration, nous utilisons le pattern "loop-until-dry" (boucler jusqu'à épuisement). Le système boucle tant que de nouveaux éléments sont découverts.
  - **Règle d'or :** La déduplication doit se faire contre tout ce qui a été vu (y compris les impasses et les rejets) pour éviter des boucles infinies coûteuses sur des "dead ends".
- **Isolation par Worktrees :** Pour les agents manipulant des fichiers en parallèle, l'utilisation de "worktrees" (environnements sandbox isolés) empêche les collisions d'écriture et les corruptions d'état.
- **Human-in-the-loop :** L'ingénierie de graphe permet d'insérer des nœuds d'approbation humaine sur les points à haut risque (envois d'emails, transactions), garantissant une sécurité de niveau entreprise.

**L'impact stratégique :** L'isolation des échecs au niveau du nœud empêche l'effondrement en cascade. Si un agent de la flotte échoue, le système continue, traitant l'erreur comme une donnée manquante plutôt que comme un arrêt fatal.

> L'architecture statique évolue désormais vers l'auto-organisation.

# 6. Conclusion : Vers des Flux de Travail Dynamiques et Auto-Routés

L'Architecte Principal ne conçoit plus des scripts, mais des écosystèmes capables de s'adapter. L'avenir appartient aux workflows dynamiques où l'IA, face à un objectif complexe, écrit elle-même son script d'orchestration, choisit son fan-out et déploie sa propre flotte de subagents.

Le passage au graphe apporte trois piliers de transformation :

1. **L'Échelle :** Absorption de volumes inaccessibles aux structures linéaires.
2. **La Fiabilité :** Passage de la génération à la vérification systématique.
3. **L'Économie :** Optimisation granulaire des coûts via le tiering et l'orchestration codée.

> **Appel à l'action technique :** Cessez de construire des files d'attente. Commencez à dessiner des graphes. Adoptez des structures capables de créer du désaccord (adversarial) avant de converger vers un résultat validé. C'est ainsi que l'IA sort du cadre du gadget pour devenir une infrastructure de production robuste.
