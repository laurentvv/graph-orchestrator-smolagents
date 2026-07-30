# Guide de Standardisation : Architecture de Systèmes Agentiques en Graphes

> Ce document est le manifeste de référence du projet, synthétisant les meilleures pratiques d'ingénierie IA (Andrew Ng, Google, Anthropic, IBM). Il encode la philosophie d'architecture (transition du linéaire vers l'ingénierie de graphes) et sert de boussole pour les décisions de conception futures.

---

## Mappage guide ↔ implémentation

Tableau d'écart entre les concepts du guide et leur couverture actuelle dans `graph_orchestrator/`.

| § | Concept du guide | Statut | Implémentation |
|---|------------------|--------|----------------|
| 2 | Nœud atomique + schéma JSON + retry sur non-conformité | ✅ | `models.py` (Pydantic) + `run_with_retry` |
| 2 | Arête = vrai transfert de donnée (supprimer fausses arêtes) | ✅ | worker→judge→synch passent des données réelles |
| 3 | Topologie Diamant (Fan-out → **Reduce** → Synth) | ✅ | `execute_reduce_node` (flatten + dedupe + filter) |
| 3 | Pipeline vs Barrière (`asyncio.gather`) | ✅ | `asyncio.gather` justifié car le juge dépend de tous les workers. |
| 4 | Orchestration par code (0 token de coordination) | ✅ | Python async, pas de routeur LLM |
| 4 | Tiering de modèles (Fast Tokens vs Heavy) | ✅ | `qwen3.5:2b` (Fan-out) / `gemma-4-E4B-it` (Raisonnement) |
| 5 | **Vérification Adversaire** (sceptiques indépendants) | ✅ | `execute_adversary_node` : N sceptiques en parallèle |
| 5 | **Cycles de Convergence** (loop-until-dry + dédup vs déjà-vu) | ✅ | `run_exploration_workflow` : dédup persistante sur DuckDB |
| 5 | Traçabilité absolue (provenance de chaque info) | ✅ | Table `provenance` : source + modèle + run par claim |
| 5 | **Exploitation de la Mémoire par les Agents** | ✅ | Outil `query_duckdb_knowledge_graph` permettant à l'Architecte de requêter SQL les bugs passés |
| 6 | **Intégration Humaine Stratégique** (routage conditionnel) | ✅ | `HITL_NODES` déclenché seulement sur les nœuds à enjeu |

---

# 1. Introduction : La Théorie de l'Externalisation Cognitive

L'architecture de l'IA n'est pas passée directement d'un script linéaire au graphe complexe. Selon le manuel d'Andrew Ng (juillet 2026), le graphe n'est pas le point de départ, mais l'aboutissement d'un besoin croissant de mémoire et de spécialisation. Chaque étape de ce cheminement externalise une fonction différente de la pensée humaine :

1. **La Boucle (Loop) externalise la révision :** Elle permet à un agent d'itérer sur son propre travail.
   > **Les 4 "Questions d'Or" de Google :** Avant de créer une boucle agentique, validez ces 4 critères stricts : (1) Est-ce répétitif ? (Un prompt manuel est plus rapide pour une tâche unique). (2) La vérification est-elle automatique ? (3) L'agent peut-il agir de bout en bout sans permission humaine constante ? (4) Le critère de réussite est-il "objectif" (ex: "Les tests passent") ?
2. **La Chaîne (Chain) externalise l'ordre des tâches :** Elle fixe la séquence de travail (le flux de contrôle via le code) de manière déterministe.
3. **Le Réseau (Network) externalise la spécialisation des rôles :** Il orchestre plusieurs agents spécialisés (ex: l'orchestrateur et les sous-agents).
4. **Le Graphe (Graph) externalise l'état partagé et les relations :** Il justifie son coût d'infrastructure *uniquement* lorsque les agents doivent partager des faits (mémoire persistante) d'une session à l'autre sans copier des historiques de conversation entiers.

# 2. Les Nouveaux Anti-Patterns (Erreurs d'Architecture)

Pour maintenir la pureté de ce Graphe, nous fuyons ces modèles toxiques documentés par les leaders de l'industrie :

- **La Chambre d'écho (Echo Chamber) :** Lancer plusieurs agents en parallèle avec le même prompt et le même modèle n'apporte rien, si ce n'est de multiplier l'erreur par trois à un coût exorbitant. Chaque agent doit avoir une grille d'évaluation distincte (Sécurité vs Logique vs Performance).
- **La "Missing Baseline" (L'absence de référence) :** Déployer un système d'agents complexe sans avoir d'abord mesuré le taux de réussite d'un simple "prompt zero-shot". Sans cela, il est impossible de savoir si le surcoût de l'architecture est justifié.
- **L'Agent Prématuré (Premature Agent) :** Créer un système multi-agents pour une tâche qu'un seul appel de modèle bien prompté pourrait résoudre.
- **Le Goulot d'étranglement conversationnel :** Si l'orchestrateur lit le *transcript complet* de tous ses agents, sa fenêtre de contexte implose. Les agents doivent communiquer via des **contrats structurés (JSON)** ou des états réduits dans DuckDB.
- **Le Graphe Fantôme (Phantom Graph) :** Créer une ontologie de graphe complexe que finalement aucun agent ne vient jamais interroger (un coût d'infrastructure sans valeur). Si on stocke, il faut que le LLM puisse faire des requêtes (`query_duckdb_knowledge_graph`).
- **L'Agent "À tout faire" (Everything-Agent) :** Un agent avec 20 outils et un prompt de 50 pages est intraçable. Son échec est impossible à déboguer. Le maître mot est **l'atomicité du rôle**.

# 3. Le Piège de la "Dette de Compréhension" (Comprehension Debt)

Risque majeur en ingénierie logicielle par IA : si le graphe d'agents génère, valide et fusionne du code trop rapidement en totale autonomie, **le code évolue plus vite que la compréhension humaine de l'équipe technique**.

Pour l'éviter, l'architecture intègre un **droit de veto humain (Human-in-the-Loop)** en fin de chaîne. L'humain peut (et doit) refuser un code validé par l'IA (le Nœud Juge) pour l'une de ces 3 raisons fondamentales, qui seront consignées dans DuckDB comme "Tickets de Bug Humain" :
1. **La Dette de Compréhension absolue :** Le code généré est fonctionnel, mais trop alambiqué ou "trop intelligent". L'humain le refuse pour forcer l'IA à réécrire une solution lisible et maintenable par l'équipe.
2. **L'Écart de Produit (Product Misalignment) :** Le code est techniquement parfait et sans bug, mais le résultat fonctionnel (UX/UI, comportement) ne correspond pas à l'attente métier (ex: la vitesse du jeu est injouable). Le Juge IA ne peut évaluer que le code, seul l'humain évalue le ressenti.
3. **La Violation Silencieuse des Conventions :** Le code enfreint une norme stylistique ou architecturale propre à l'entreprise que l'Architecte ou le Juge ignoraient (ex: nommage des variables, structure des dossiers).

Autres protections techniques mises en place :
- Limiter les boucles à de petites sous-tâches (via le découpage strict de l'Architecte).
- Imposer des portes de validation objectives (Testeurs MCP + Juge).
- Bloquer les modifications d'architecture globales décidées par les agents sans validation Humaine.

# 4. Règles de Décision et Optimisation des Performances

L'architecture système est le levier premier de réduction des coûts et d'augmentation de l'intelligence globale.

- **Compter les tokens, pas les agents :** Un système de trois agents consommant chacun 20 000 tokens coûte le même prix qu'un seul Everything-Agent à 60 000 tokens. Diviser pour régner !
- **Vitesse d'inférence (Fast Tokens) :** Un petit modèle rapide (`qwen3.5:2b`) inséré dans une boucle de vérification robuste est souvent supérieur à un modèle ultra-lourd (`gemma-4`) utilisé en *one-shot*. L'architecture compense la puissance brute.
- **Pipeline vs Barrière (Optimisation de Latence Anthropic) :** Lors de la parallélisation (Fan-out), il faut privilégier le streaming continu (`pipeline()`) par défaut. Cela permet aux éléments rapides de passer à l'étape suivante (ex: la synthèse) sans attendre l'agent le plus lent du lot. La barrière d'attente (`parallel()`, comme `asyncio.gather`) ne doit être utilisée que lorsqu'une étape requiert absolument de voir *tous* les résultats en même temps (comme une déduplication croisée ou le Fan-In d'un Juge).

# 5. L'impératif de Traçabilité Absolue et de Fiabilité

Un graphe de qualité doit répondre à une exigence stricte : **tout résultat important doit pouvoir être retracé jusqu'à une tâche, un plan, une source, une décision d'évaluateur et un journal d'exécution précis**.
Si cette affirmation est fausse, ajouter de l'autonomie ne fera qu'augmenter le chaos.

### Protocoles de Confiance et Résilience
- **Vérification Adversaire :** Déploiement de "sceptiques" indépendants pour tenter de réfuter chaque résultat.
- **Cycles de Convergence :** Pattern "loop-until-dry" (boucler jusqu'à épuisement). Le système boucle tant que de nouveaux éléments sont découverts (déduplication stricte contre les succès ET les rejets stockés dans DuckDB).
- **Human-in-the-loop :** Insérer des nœuds d'approbation humaine sur les points critiques, garantissant une sécurité de niveau entreprise grâce à la lecture de la provenance DuckDB.

# 6. Conclusion : Les Graphes Dynamiques (Self-Routing par l'IA)

L'Architecte Principal ne conçoit plus des scripts, mais des écosystèmes. Selon l'avancée technologique majeure d'Anthropic (comme dans *Claude Code*), il n'est plus nécessaire de dessiner le graphe à la main. En utilisant les "workflows dynamiques", vous fournissez l'objectif, et **c'est le modèle d'IA lui-même qui écrit le script d'orchestration JavaScript**. L'IA décide de la parallélisation, lance une flotte de sous-agents coordonnés, et synthétise le résultat pour cette exécution spécifique.

> **Appel à l'action technique :** Cessez de construire des files d'attente. Construisez des graphes traçables. Adoptez des structures capables de créer du désaccord avant de converger. C'est ainsi que l'IA devient une infrastructure de production robuste.
