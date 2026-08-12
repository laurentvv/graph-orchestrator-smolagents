# Fiche d'audit : sentrux (XX)

**Date** : 2026-08-12
**Projet** : [sentrux](https://github.com/sentrux/sentrux)
**Description** : The sensor that helps AI agents close the feedback loop. Recursive self-improvement of code quality via structural analysis and MCP integration.

## 1. Top 5 Composants Réutilisables

### 1. Moteur de Métriques Structurelles (P6 Judge / Findings)
- **Fichiers** : `sentrux-core/src/metrics/root_causes.rs`, `sentrux-core/src/metrics/types.rs`
- **Réutilisabilité** : 🟢 Haute
- **Description** : Calcule 5 métriques racines (modularité, acyclicité, profondeur, égalité, redondance) pour donner un score continu de 0 à 10000 sur la santé du code. Indispensable pour un Judge (P6) validant si l'agent a dégradé l'architecture.

### 2. Pipeline d'Analyse Multi-langages (Tree-sitter) (P4 Repo Map / Extraction)
- **Fichiers** : `sentrux-core/src/analysis/lang_registry.rs`, `sentrux-core/src/analysis/parser/`
- **Réutilisabilité** : 🟢 Haute
- **Description** : Registre dynamique et parseur utilisant des plugins `tree-sitter` pour plus de 50 langages (sans logique compilée en dur). Très utile pour bâtir un Knowledge Graph ou extraire des dépendances sans bloquer sur un langage spécifique.

### 3. Serveur MCP (Tools pour Agents) (P10 Skill loading)
- **Fichiers** : `sentrux-core/src/app/mcp_server/handlers.rs`, `sentrux-core/src/app/mcp_server/registry.rs`
- **Réutilisabilité** : 🟢 Haute
- **Description** : Implémentation du Model Context Protocol offrant 9 outils (`scan`, `health`, `session_start`, `session_end`, etc.) pour interagir avec le graphe du projet, servant de modèle pour exposer des "skills" d'analyse de code via MCP.

### 4. Moteur de Règles d'Architecture (P6 Judge)
- **Fichiers** : `sentrux-core/src/metrics/rules/checks.rs`, `sentrux-core/src/metrics/rules/mod.rs`
- **Réutilisabilité** : 🟡 Moyenne
- **Description** : Valide des contraintes définies en TOML (cycles max, couplage, god files, layers). Peut être réutilisé pour créer un linter d'architecture bloquant les actions d'un LLM si les frontières architecturales sont violées.

### 5. Algorithme de Layout Treemap Squarified (Visualisation / Repo Map)
- **Fichiers** : `sentrux-core/src/layout/treemap_layout.rs`, `sentrux-core/src/layout/squarify.rs`
- **Réutilisabilité** : 🟢 Haute
- **Description** : Implémentation de l'algorithme "squarified" pour afficher une hiérarchie de fichiers sous forme de carte proportionnelle. Parfait pour une interface de suivi visuel de la Repo Map (P4) pour les développeurs gouvernant l'IA.

## 2. Pépites (Hall of Fame)
- L'approche conceptuelle majeure : "L'IA génère vite, mais dégrade l'architecture à la même vitesse". L'outil agit comme un **capteur de feedback (Sensor)** indispensable dans la boucle.
- Le plugin system Tree-sitter 100% data-driven avec `tags.scm`.
- Les endpoints MCP (`session_start` / `session_end`) comparant la qualité avant/après l'action de l'agent pour empêcher les régressions silencieuses.

## 3. Risques & Biais
- Base de code 100% Rust, nécessité d'intégration via FFI, CLI ou requêtes MCP si notre usine est en Python.
- L'analyse est statique et orientée dépendances structurelles, ignorant le comportement dynamique ou la justesse algorithmique (à compléter avec un test runner P6).

---