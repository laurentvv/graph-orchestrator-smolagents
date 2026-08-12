# Fiche d'Analyse : Scrapling (Fiche 31)

**Date** : 2026-08-12
**Projet** : Scrapling
**Type** : Framework de Web Scraping / Extraction de données / Anti-bot
**Catégorie Principale** : P3 (Web Scraping / Data Collection)

## Résumé
Scrapling est un framework Python de Web Scraping adaptatif et très performant. Il intègre un parseur robuste (basé sur `lxml`) capable de retrouver des éléments web même après des changements de structure (adaptive scraping), des "fetchers" capables de contourner nativement les protections anti-bot (ex. Cloudflare Turnstile), ainsi qu'un moteur de "spiders" asynchrones complet (concurrence, pause/reprise, AutoThrottle). Il fournit de plus un serveur MCP (Model Context Protocol) pour une intégration native avec des agents IA (LLM).

## Composants Réutilisables

| Composant | Type | Priorité | Réutilisabilité | Description |
|-----------|------|----------|-----------------|-------------|
| **Scrapling Parser (Selector)** | Web Parsing Engine | P3 | 🟢 | Parseur lxml très complet supportant CSS, XPath, regex, et un suivi adaptatif des éléments. Indépendant du reste du framework. |
| **StealthyFetcher** | Web Automation | P3 | 🟢 | Client de récupération de pages (basé Chromium/Playwright) conçu pour contourner les blocages type Cloudflare Turnstile. |
| **Scrapling Spiders** | Crawling Framework | P3 | 🟡 | Moteur asynchrone de requêtes et de parsing concurrent (semblable à Scrapy) avec support multi-session. Couplé aux objets `Response` de la lib. |
| **AutoThrottle** | Rate Limiting | P3 | 🟢 | Logique d'ajustement dynamique des délais de requêtes selon la latence et les limites (429) des sites. Facilement portable. |
| **Scrapling MCP Server** | AI Agents Integration | P2 | 🟢 | Serveur MCP permettant à un agent de piloter des navigateurs ou d'extraire des données de manière furtive via Scrapling. |
| **LinkExtractor** | Link Parsing Utility | P3 | 🟢 | Outil de filtrage et de canonisation de liens avec expressions régulières. Portable et utilitaire. |

## Dépendances Clés
- `lxml` : Base du moteur de parsing.
- `cssselect` : Pour la conversion des sélecteurs CSS.
- `playwright` : Pour les `DynamicFetcher` et `StealthyFetcher`.
- `mcp` : Pour le serveur Model Context Protocol.

## Notes d'Intégration
- `Scrapling` offre une excellente alternative "tout-en-un" à la combinaison `Scrapy` + `BeautifulSoup` + `Selenium`/`Playwright` stealth.
- Le serveur MCP intégré en fait un excellent candidat pour être branché directement sur des graphes d'orchestration ou des LLM.