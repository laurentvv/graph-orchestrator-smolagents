# ADR 0002 : Hard-Dependency vs Soft-Dependency (Graceful Degradation)

**Statut** : Accepté
**Date** : 2026-08-05

## Contexte
L'Usine Logicielle repose sur des outils externes (serveurs MCP, navigateurs headless, clés d'API). L'indisponibilité d'un de ces services ne doit pas systématiquement faire crasher la boucle principale (le Graphe d'Agents). Il est crucial de définir quand une erreur d'infrastructure bloque la pipeline ("fail-loud") et quand elle est ignorée silencieusement en mode dégradé ("degrade-gracefully").

## Décision

### 1. Hard Dependencies (Fail-Loud)
Une dépendance est considérée "hard" (bloquante) si le graphe est physiquement incapable de continuer ou si le code généré serait gravement compromis sans elle.
- **Exemples** :
  - L'interpréteur Python local (`uv`).
  - La base de données de graphe (`duckdb`).
  - Le modèle LLM (Ollama / vLLM / Gemini).
  - Les tools fondamentaux (`write_file`, `read_file`).
- **Comportement attendu** : Une exception explicite est levée et le processus s'arrête (circuit breaker). L'utilisateur doit intervenir.

### 2. Soft Dependencies (Graceful Degradation)
Une dépendance est "soft" si son absence diminue la qualité de l'audit ou réduit les informations contextuelles, mais n'empêche pas le LLM de coder.
- **Exemples** :
  - **Serveur MCP Chrome DevTools** : S'il est offline ou si `node` n'est pas installé, le Coder ne pourra pas voir de screenshot (l'outil retourne un avertissement au lieu d'une image, ou la liste d'outils n'inclut pas les actions web). L'agent doit continuer à coder "à l'aveugle".
  - **Serveur MCP Context7** : Si la clé d'API est absente, les outils de recherche de doc en direct ne sont pas injectés. Le Coder s'appuiera sur sa base de connaissances interne.
  - **Outils statiques optionnels** : Si `radon` (pour l'audit de complexité) n'est pas dispo, le pipeline ne plante pas, il indique simplement `(Non disponible)`.
- **Comportement attendu** :
  - L'orchestrateur (ex: `build_skills_block`, `chrome_devtools_tools()`) doit catcher les erreurs d'initialisation (socket error, key missing) et retourner une liste vide `[]` ou un outil "dummy" qui explique au LLM que la feature est désactivée.
  - Journalisation locale pour prévenir le développeur, sans crasher.

## Conséquences
- Plus grande résilience du système sur des machines non configurées (ex: onboarding d'un nouveau développeur sans toutes les clés d'API).
- Évite les boucles de retry infinies où un agent LLM essaie d'appeler un serveur MCP éteint.
- Oblige les développeurs du framework à bien encapsuler la logique d'initialisation des tools dans des blocs `try/except` stricts avec fallback silencieux (cf `ContextManager`).
