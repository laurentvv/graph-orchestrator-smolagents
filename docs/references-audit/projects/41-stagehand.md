# 41 — stagehand

## 1. Description Générale
**Stagehand** est un SDK conçu spécifiquement pour les agents navigateurs (browser agents). Contrairement à Playwright orienté vers les tests, Stagehand est optimisé pour les LLM avec des actions auto-réparatrices (self-healing) et un parsing optimisé du DOM (hybrid accessibility tree trimming) pour l'efficacité des tokens. Il interagit avec le navigateur en injectant une extension et communique avec elle via le protocole Chrome DevTools (CDP).

## 2. Top 5-8 des Composants Réutilisables

1. **`Stagehand` Orchestrator (P3)** 🟢
   - **Description :** Point d'entrée principal exposant les primitives LLM `act` (exécuter une action textuelle), `observe` (analyser les éléments interactifs) et `extract` (structurer les données de la page via Pydantic).
   - **Réutilisabilité :** Très forte pour tout agent LLM devant contrôler un navigateur avec des instructions naturelles.

2. **`CDPClient` (P3)** 🟡
   - **Description :** Client asynchrone interagissant via WebSockets avec l'API CDP. Intègre une logique avancée pour charger l'extension Stagehand, écouter les Target/Service Workers et configurer le `Runtime.addBinding`.
   - **Réutilisabilité :** Moyenne. Utile pour manipuler CDP manuellement, mais fortement couplé au ServiceWorker de Stagehand.

3. **Factory de Navigateurs (`LocalBrowser` & `BrowserbaseBrowser`) (P3/P8)** 🟡
   - **Description :** Logique de lancement de navigateurs locaux (recherche de l'exécutable Chrome, application des flags optimisés pour l'automatisation silencieuse) et connexion à l'infrastructure cloud Browserbase.
   - **Réutilisabilité :** Moyenne. Les flags Chrome utilisés (`_DEFAULT_CHROME_FLAGS`) sont de bonnes pratiques pour l'automatisation headless.

4. **`RPCClient` via CDP (P3)** 🟡
   - **Description :** Implémentation d'un client RPC bidirectionnel qui communique entre le SDK Python et l'extension JS injectée, en utilisant `Runtime.evaluate` et `Runtime.bindingCalled`.
   - **Réutilisabilité :** Spécifique, mais excellente inspiration pour construire un pont RPC Python <-> JS intra-navigateur sans serveur intermédiaire.

5. **Wrapper `Page` et `Locator` (P3)** 🟡
   - **Description :** Abstractions mimant l'API Playwright tout en exécutant les opérations au travers de l'engine CDP et de l'extension Stagehand, pour cibler des éléments même dans des Shadow DOMs ou iframes hors process.
   - **Réutilisabilité :** Moyenne, lié au modèle Stagehand.

## 3. Analyse de Réutilisabilité Globale
**Score :** 🟢 (Très élevée)
Stagehand offre une brique d'automatisation de navigateur (Web Automation) "Agent-First" très pertinente pour la Software Factory, en particulier pour des tâches d'intégration continue, d'extraction de données non structurées, ou de tests de bout en bout guidés par un LLM.

## 4. Recommandations pour l'Intégration
- L'approche d'utiliser une extension injectée via CDP au lieu de simples scripts Playwright est intéressante pour contourner les protections anti-bot et accéder plus profondément aux structures complexes de pages web.
- Intégrer les primitives `act`, `observe`, `extract` de Stagehand comme un outil (MCP ou direct) pour les agents chargés de l'OSINT, du test, ou de la navigation web complexe.