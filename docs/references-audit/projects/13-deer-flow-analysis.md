# 13 — deer_flow_analysis.md

## En-tête
- **Nom** : deer_flow_analysis.md (note d'analyse DeerFlow 2.0)
- **Chemin** : `references/deer_flow_analysis.md`
- **Type** : Note d'analyse technique en français (document unique à la racine de `references/`)
- **Langage principal** : Markdown (français)
- **Statistiques** : 1 fichier, 5,9 Ko

## Synthèse
C'est le document le plus directement orientant pour le projet cible. Il analyse DeerFlow 2.0 (système "Super Agent" bytedance basé sur LangGraph/LangChain, donc **Python** — contrairement à opencode/openfox qui sont TS) et propose **3 idées concrètes et actionnables** à réutiliser dans `graph-orchestrator-smolagents`, plus 2 concepts annexes (orchestration sous-agents, gestion d'erreurs LLM). Synthèse hautement réutilisable car directement applicable à un orchestrateur Python (DSPy/smolagents). Note de réutilisabilité globale : **Haute**.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/deer_flow_analysis.md` | Analyse DeerFlow 2.0 : 5 sections (gestion état ThreadState, chaîne middlewares, framework Skills, orchestration sous-agents, gestion erreurs) + synthèse de 3 idées à appliquer. Liens vers code source bytedance/deer-flow (Python) | Haute |

## Les 3 idées proposées par le document

### Idée 1 — Boucle de middlewares (hooks) autour du nœud Agent
Au lieu de laisser `smolagents` appeler l'API LLM directement, intercepter l'entrée/sortie du nœud "Agent" du graphe pour : (a) vérifier la limite de tokens (`TokenBudget`), (b) stopper les boucles (`LoopDetectionMiddleware` → force une réponse finale type `loop_capped`), (c) tronquer les résultats d'outils trop longs (`ToolOutputBudgetMiddleware`), (d) détecter la stagnation d'outil (`ToolProgressMiddleware` avertit puis bloque temporairement l'outil), (e) assainir les entrées/sorties d'outils distants (`InputSanitization`/`ToolResultSanitization` contre l'injection de prompt). Source : `backend/packages/harness/deerflow/agents/middlewares/`.

### Idée 2 — Reducers typés pour l'état du graphe
Étendre l'état du graphe (au-delà d'une simple `list[BaseMessage]`) avec des reducers personnalisés : maintenir une trace des `delegations` (sous-agents lancés, N=50 max, dernier statut préservé via `merge_delegations`) et du `skill_context` (références des skills uniquement — nom, description courte, chemin — via `merge_skill_context`). Inclure aussi `artifacts`, `todos`, `summary_text`. Permet de compacter l'état sans perte d'information critique. Source : `backend/packages/harness/deerflow/agents/thread_state.py`.

### Idée 3 — Contexte à la demande (Prompt-Vault / Skills)
Ne mettre que les résumés/titres des outils dans le prompt système de base (économie de contexte). Quand le modèle veut utiliser un outil/skill spécifique, déclencher un nœud qui lit le `SKILL.md` (ou le "Vault") et l'injecte dans les messages à ce moment-là (`SkillActivationMiddleware`). Couplé à `SkillToolPolicyMiddleware` qui autorise dynamiquement les schémas d'outils associés au skill activé. Évite de saturer le prompt initial avec toutes les instructions détaillées. Source : `backend/packages/harness/deerflow/skills/`.

> Concepts annexes documentés mais non repris dans la synthèse des 3 idées : isolation d'event loop pour sous-agents via `_isolated_subagent_loop`, et extraction de résultat pur via `_extract_final_result` — cf. section 4 du document.

## Code réutilisable
*(Document de synthèse — pas de code directement, mais pointe vers des fichiers sources Python réutilisables conceptuellement, qu'on retrouve dans la fiche 08 deer-flow.)*

| Chemin (source DeerFlow) | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/deer-flow/backend/packages/harness/deerflow/agents/thread_state.py` | `ThreadState`, `merge_delegations`, `merge_skill_context` | État graphe étendu avec reducers : `artifacts`, `todos`, `delegations` (N=50 max, statut préservé), `skill_context` (références uniquement), `summary_text` | Haute | Python (LangGraph) ; pattern de reducers transposable à smolagents |
| `references/deer-flow/backend/packages/harness/deerflow/agents/middlewares/` | `InputSanitization`, `ToolResultSanitization`, `ToolProgressMiddleware`, `LoopDetectionMiddleware`, `ToolOutputBudgetMiddleware`, `TokenBudget`, `SubagentLimit`, `ToolErrorHandlingMiddleware` | Chaîne middlewares pré/post LLM : anti-injection, anti-stagnation, détection boucles, troncature output, budgets tokens/sous-agents, erreurs en faux ToolMessage | Haute | Python ; directement transposable (hooks autour du nœud Agent) |
| `references/deer-flow/backend/packages/harness/deerflow/skills/` | `SkillActivationMiddleware`, `SkillToolPolicyMiddleware` | Skills à chargement différé : `SKILL.md` injecté uniquement à l'activation, autorisation dynamique des outils du skill | Haute | Python ; équivalent "Prompt-Vault" pour le projet cible |
| `references/deer-flow/backend/packages/harness/deerflow/subagents/executor.py` | `SubagentExecutor`, `_isolated_subagent_loop`, `_extract_final_result`, `_extract_llm_error_fallback` | Délégation sous-agents : event loop isolé, extraction résultat pur (sans polluer le parent), marquage AIMessage défectueux | Haute | Python ; pertinent pour workflow coding multi-agent |

## Contrats / Specs / Config
*(Aucun — document d'analyse ne contenant pas de contrat/spec/config propre.)*

## Exclusions conscientes
- Aucune : fichier unique lu intégralement, intégralement pertinent.
