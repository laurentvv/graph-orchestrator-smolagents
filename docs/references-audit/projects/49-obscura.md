# 49 — obscura

## En-tête
- **Nom** : Obscura (`obscura`)
- **Chemin** : `references/obscura/`
- **Type** : Moteur de navigateur headless ultra-léger et furtif écrit en Rust pour agents IA et web scraping — exécution JavaScript réelle via V8, serveur Chrome DevTools Protocol (CDP) compatible Puppeteer/Playwright, serveur Model Context Protocol (MCP) natif, moteur de rendu headless sans Chromium (Skia/tiny-skia/resvg) et système de snapshotting par identifiants stables (`interactive_refs`).
- **Langage principal** : Rust (356 fichiers : 265 `.rs`, 23 `.toml`, 21 `.md`, 12 `.png`, 8 `.yml`, 6 `.svg`) ; monorepo Cargo avec 9 crates (`obscura`, `obscura-browser`, `obscura-cdp`, `obscura-cli`, `obscura-dom`, `obscura-js`, `obscura-mcp`, `obscura-net`, `obscura-render`).
- **Licence** : Apache-2.0

## Synthèse
Obscura est un moteur de navigateur headless indépendant conçu sur-mesure pour les agents autonomes et le web scraping, s'affranchissant totalement de la lourdeur d'une instance Chromium complète :
- **Empreinte mémoire** : ~30 Mo de RAM (contre 200+ Mo pour headless Chromium).
- **Taille de binaire** : ~70 Mo (contre 300+ Mo).
- **Temps de chargement de page** : ~85 ms (contre ~500 ms).
- **Démarrage** : instantané (contre ~2 s pour spawn Chromium).
- **Furtivité / Anti-détection** : intégrée nativement dans la pile réseau et le runtime DOM/JS (pas de flags Puppeteer traçables).

Pour `graph-orchestrator-smolagents`, Obscura apporte des patterns d'une valeur inestimable pour nos nœuds de test web (`Web Tester`, `Static Tester`, MCP Chrome DevTools) :
1. **P8 & P6 (Interaction Agent Stable & Économie de Contexte)** : Dans `crates/obscura-mcp/src/lib.rs`, Obscura implémente une table de références interactives (`interactive_refs` générant des identifiants stables type `"e3"`, `"e4"` lors du snapshotting). L'agent clique, saisit et navigue via ces identifiants sans jamais risquer de casser des sélecteurs CSS fragiles. De plus, une constante `DEFAULT_TEXT_LIMIT = 4000` bride systématiquement les dumps textuels pour empêcher un appel d'outil unique de saturer la fenêtre de contexte du LLM.
2. **P8-bis (Sandbox Web Ultra-Légère)** : Permet d'envisager une alternative ultra-performante à headless Chrome pour tester localement les applications web générées (HTML5, JS, CSS, Canvas) sans consommer la VRAM et la RAM nécessaires aux LLM locaux (Qwen, Ornith).
3. **P6 (CDP Server Drop-in)** : `crates/obscura-cdp` implémente le protocole Chrome DevTools, assurant une compatibilité immédiate avec les scripts et outils existants fondés sur Puppeteer ou Playwright.
4. **P8 (Gestion Multi-Onglets Déterministe)** : Stockage des onglets dans un `BTreeMap<String, Page>` garantissant un ordre stable entre appels d'outils successifs, évitant les hallucinations de l'agent sur l'index des onglets.

Réserves : Développé en Rust avec bindings V8 natifs (`rusty_v8`), ce qui nécessite une compilation Cargo ou l'utilisation du binaire standalone / serveur MCP plutôt qu'une inclusion directe sous forme de script Python. Note globale : **🟢 Haute** (sur le plan de l'architecture MCP agentique, des refs stables et de l'alternative légère à Chromium) / **🟡 Moyenne** (pour l'intégration native Python directe).

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/obscura/AGENTS.md` | Directives et invariants d'architecture d'Obscura pour agents autonomes | **Haute** (P0-bis / P8-bis — charte de robustesse Rust) |
| `references/obscura/README.md` | Présentation globale, métriques comparatives vs Chromium, architecture et exemples | **Haute** (P6 / P8-bis — documentation de l'architecture headless) |
| `references/obscura/crates/obscura/README.md` | Documentation de l'API de haut niveau pour l'automatisation de pages et de sessions | Moyenne (P6 — API de scripting de test) |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/obscura/crates/obscura-mcp/src/lib.rs` | `BrowserState`, `DEFAULT_TEXT_LIMIT = 4000`, `interactive_refs`, `RpcMessage`, `RpcResponse`, `RpcError`, `page_mut` | Serveur MCP complet pour navigateur : table d'identifiants d'éléments stables (`interactive_refs`), plafond de tokens strict (4000 chars), multi-onglets ordonné en `BTreeMap` | **Haute** | P8+P6 : Blueprint parfait pour concevoir ou durcir nos outils MCP d'interaction web et nos callbacks de vision |
| `references/obscura/crates/obscura-mcp/src/http.rs` | `HttpServer`, `handle_sse`, `handle_post` | Transport MCP standardisé combinant flux SSE et requêtes HTTP POST pour agents distants | **Haute** | P11+P8 : Architecture de transport MCP standardisée |
| `references/obscura/crates/obscura-browser/src/context.rs` | `BrowserContext`, `stealth`, `proxy`, `with_options` | Gestion du contexte de navigation avec options d'isolation, profils, proxying et furtivité | **Haute** | P8-bis : Modèle d'isolation de contexte de navigation |
| `references/obscura/crates/obscura-browser/src/page.rs` | `Page`, `navigate`, `evaluate`, `screenshot`, `pdf`, `content` | Contrôleur de cycle de vie de page web avec exécution JS, injection de scripts et capture d'écran | **Haute** | P6+P8-bis : API de contrôle de page headless sans Chromium |
| `references/obscura/crates/obscura-browser/src/lifecycle.rs` | `PageLifecycle`, `NavigationState`, `waitFor` | Machine à états de cycle de vie de page (chargement, DOM ready, network idle) avec timeouts configurables | **Haute** | P6+P8 : Algorithmes d'attente déterministe pour éviter les tests intermittents (flaky tests) |
| `references/obscura/crates/obscura-cdp/src/server.rs` | `CdpServer`, `start`, `handle_connection` | Serveur Chrome DevTools Protocol autonome multiplexant les connexions CDP WebSocket | Moyenne | P6+P8-bis : Passerelle CDP drop-in pour Puppeteer/Playwright |
| `references/obscura/crates/obscura-cdp/src/dispatch.rs` | `CdpDispatcher`, `dispatch_domain_command` | Routeur de commandes CDP vers les domaines Page, Runtime, DOM, Network, Emulation | Moyenne | P6 : Table de correspondance et dispatching CDP |
| `references/obscura/crates/obscura-render/src/paint.rs` | `Renderer`, `paint_tree`, `capture_frame` | Moteur de rendu graphique 2D pur (tiny-skia) permettant le rendu de page et la capture sans GPU lourd | Moyenne | P6 : Moteur de capture visuelle léger |
| `references/obscura/crates/obscura-dom/src/lib.rs` | `DomTree`, `NodeId`, `querySelector`, `querySelectorAll` | Arbre DOM léger en mémoire avec moteur de requêtes de sélecteurs CSS optimisé | Moyenne | P6 : Extraction DOM légère sans overhead navigateur |
| `references/obscura/crates/obscura-js/src/lib.rs` | `JsRuntime`, `V8Context`, `eval_script`, `isolate` | Runtime d'évaluation JavaScript confiné sur moteur V8 | Moyenne | P8-bis : Confinement d'exécution JS |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/obscura/crates/obscura-cdp/src/types.rs` | CDP Schemas | Types et structures de données du protocole Chrome DevTools |
| `references/obscura/crates/obscura/src/config.rs` | Engine Config | Configuration du moteur : options réseau, proxies, stealth, timeouts, viewport |

## Exclusions conscientes
| Chemin | Motif d'exclusion |
|---|---|
| `references/obscura/assets/sponsors/` | Logos et bannières des sponsors proxy commerciaux. Ignorer. |
| `references/obscura/crates/obscura-cli/` | Binaire CLI interactif utilisateur (hors contexte orchestrateur headless). Ignorer. |
| `references/obscura/deny.toml`, `.cargo/` | Fichiers de configuration de chaîne de compilation Rust Cargo. Ignorer. |

## Correspondance avec `plan_usine_logicielle.md`
- **P6** : `interactive_refs` & `BrowserState` (snapshots stables par identifiants élémentaires pour le Web Tester) + `lifecycle.rs` (attente déterministe d'état de page).
- **P8** : `DEFAULT_TEXT_LIMIT` (garde anti-saturation de contexte LLM lors des snapshots DOM) + `BTreeMap` tabs ordonnés.
- **P8-bis** : Moteur Obscura headless 30MB (alternative ultra-légère à Chromium pour sandbox de test web locale).
- **P11** : `http.rs` (serveur MCP avec transport SSE et traçabilité d'événements).
