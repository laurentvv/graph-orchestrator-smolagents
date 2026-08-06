# 26 — cloudflare-os

## En-tête
- **Nom** : cloudflare-os
- **Chemin** : `references/cloudflare-os/`
- **Type** : Environnement de productivité agentique (OS)
- **Langage principal** : TypeScript (Cloudflare Workers)
- **Statistiques** : ~800 fichiers, ~400 `.ts`, ~170 `.tsx`.

## Synthèse
Cloudflare OS est un "système d'exploitation" pour la productivité IA, initialement conçu pour l'usage interne chez Cloudflare. Il propose un environnement sécurisé où les agents peuvent générer des "Gadgets" (applications web personnelles isolées) pour les utilisateurs. Son architecture s'appuie massivement sur les Cloudflare Workers, les Durable Objects et les websockets avec Cap'n Web RPC.

La valeur majeure de ce dépôt pour notre projet réside dans son architecture de sécurité basée sur les capacités (Capability-based access control) et, surtout, le concept de **Gatekeepers**. Ces derniers agissent comme des serveurs MCP survitaminés : ils gèrent l'authentification OAuth, restreignent l'accès par session, et implémentent un mécanisme asynchrone de "human-in-the-loop". Lorsqu'une action nécessite une approbation, le Gatekeeper simule le résultat localement pour l'agent, permettant à ce dernier de continuer son travail sans être bloqué en attente d'une validation humaine synchrone.

La note de réutilisabilité globale est 🟡 **Moyenne** : le code TypeScript / Cloudflare n'est pas directement portable dans un orchestrateur Python local (smolagents), mais les patterns architecturaux (Gatekeepers asynchrones, sandbox réseau, gestion des autorisations fines) sont des blueprints conceptuels de très haute qualité pour concevoir nos propres mécanismes d'isolation et d'interruption.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/cloudflare-os/README.md` | Concepts clés (Gatekeepers, Gadgets, Human-in-the-loop via simulation). | 🟢 Haute |
| `references/cloudflare-os/AGENTS.md` | Architecture interne, notion de "ambient gatekeeper record" et de trust boundaries. | 🟢 Haute |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/cloudflare-os/packages/mcp-shared/src/tools.ts` | `readOnlyHint`, annotations | Implémentation de la frontière de confiance (trust boundary). Seuls les outils annotés read-only s'exécutent en direct, le reste est mis en file d'attente pour approbation. | 🟡 Moyenne | Logique d'autorisation et annotations très transposable en Python pour sécuriser l'exécution d'outils. |
| `references/cloudflare-os/packages/workshop-backend/src/overseer.ts` | `prepareChatBindings` | Injection granulaire et sécurisée des "bindings" (capacités) dans le contexte d'exécution de l'agent. | 🟡 Moyenne | Pattern intéressant pour limiter le scope des outils MCP selon la session utilisateur (Capability-based security). |
| `references/cloudflare-os/packages/workshop-backend/src/user.ts` | `getGatekeeperClassFor` | Point de contrôle central pour vérifier si un module de sécurité est activé avant de distribuer une capacité. | 🟡 Moyenne | Inspirant pour le routage des permissions d'agent. |

## Exclusions conscientes
- **UI & Frontend (`packages/workshop-frontend`)** : Interface React spécifique, hors scope pour le backend de notre graphe.
- **Intégrations spécifiques Cloudflare** : Code hyper-spécifique aux Durable Objects et Dynamic Workers.

## Correspondance avec `plan_usine_logicielle.md`
- **P8-bis Sandbox + Idempotence** : *Référence : fiche **26-cloudflare-os** → `references/cloudflare-os/README.md` (Capability-based security, modèle de Gatekeeper pour l'exécution sandboxée isolée du réseau).*
- **P10 Skill loading** : *Référence : fiche **26-cloudflare-os** → `references/cloudflare-os/packages/mcp-shared/src/tools.ts` (Trust boundary, exécution "human-in-the-loop" asynchrone via simulation des résultats pour éviter les stalls de l'agent).*
- **P12 Scopes multi-utilisateurs** : *Référence : fiche **26-cloudflare-os** → `references/cloudflare-os/AGENTS.md` (Gestion des singletons de Gatekeeper isolés par account/session avec `sharingDomain`).*
