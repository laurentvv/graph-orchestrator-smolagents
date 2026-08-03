# 22 — llm-council

## En-tête
- **Nom** : llm-council
- **Chemin** : `references/llm-council/`
- **Type** : Application web locale de « council LLM » — ChatGPT-like qui, au lieu d'interroger un seul modèle, en fait débattre plusieurs via OpenRouter, avec **jugement mutuel à l'aveugle** puis synthèse par un Chairman
- **Langage principal** : Python 3.10+ (backend FastAPI) + React/Vite (frontend)
- **Statistiques** : 39 fichiers hors `.git/` (7 `.py`, 7 `.jsx`, 7 `.css`, 3 `.md`, 3 `.js`, 2 `.svg`, 2 `.json`). Backend minimaliste : 6 modules + 1 root `main.py`.
- **Stack backend** : FastAPI + httpx async + pydantic. Persistance : **fichiers JSON plats** dans `data/conversations/` (PAS de DB). Multi-LLM : **OpenRouter** (API payante).
- **Statut** : explicitement **« 99% vibe coded »** (README « Vibe Code Alert » : *« I'm not going to support it in any way »*, *« Code is ephemeral now »*). **Aucun test** (`test_openrouter.py` cité dans CLAUDE.md est absent du dépôt).

## Synthèse
Valeur pour le projet cible : **réelle mais étroite, concentrée sur un pattern unique**. Le dépôt incarne exactement le **pattern « council anonymisé »** cité en Annexe D (P6 Judge) : N LLM répondent, se jugent mutuellement sans connaître les identités de leurs pairs, un Chairman compile. Le mécanisme d'anonymisation est simple, lisible (~80 lignes pour le cœur du pattern) et **transposable** à un enrichissement du Judge. La parallélisation `asyncio.gather` et le parsing strict sont des bribes directement réutilisables.

Réserves **MAJEURES** :
- **Vibe-coded, non testé, non maintenu** — à traiter comme une inspiration/pseudocode, **pas comme une dépendance**.
- **Coût N×LLM** : chaque requête déclenche ~N appels (Stage 1) + ~N appels (Stage 2) + 1 (Chairman) = **2N+1 appels LLM**. Pour N=4 → 9 appels par tour. **Incompatible avec une exécution GPU locale systématique** ; à réserver à des cas tactiques (validation de findings critiques).
- **Couplage OpenRouter** : tous les appels passent par OpenRouter (payant, cloud). Pour GPU local, il faudrait remplacer `openrouter.query_model` par un client local.
- **Persistance JSON éphémère** : métadonnées (`label_to_model`, `aggregate_rankings`) non persistées — incompatible avec DuckDB.
- Le pattern est **synchrone/batch** (pas de streaming inter-agents), ce qui sied mal à un orchestrateur réactif.

Note globale : **🟡 Moyenne** (à miner pour le pattern, pas pour le code). Fiche brève justifiée par la légèreté du code réutilisable (~250 lignes utiles) et les réserves.

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/llm-council/backend/council.py` | `stage1_collect_responses`, `stage2_collect_rankings`, `stage3_synthesize_final`, `run_full_council`, `label_to_model`, `parse_ranking_from_text`, `calculate_aggregate_rankings` | **Cœur du pattern council anonymisé (~250 L).** Pipeline 3 stages : (1) first opinions en parallèle, (2) review/rank avec anonymisation A/B/C + prompt strict `FINAL RANKING:`, (3) Chairman compile. Anonymisation = labels neutres `chr(65+i)` + mapping réversible `label_to_model` jamais envoyé aux juges. | Moyenne | Pattern compact et bien illustré. **Réutiliser le pattern d'anonymisation** (labels + mapping réversible + prompt strict `FINAL RANKING:`) comme option d'enrichissement du Judge, activable pour valider des findings à enjeu (justifie le coût 2N+1). Transcrire en ~150 L plutôt qu'importer |
| `references/llm-council/backend/openrouter.py` | `query_model`, `query_models_parallel` | Parallélisation multi-LLM via `asyncio.gather` + `httpx.AsyncClient`. Dégénérescence gracieuse (None si échec, on continue). ~80 lignes. | **Haute** | Réutiliser comme patron de parallélisation, **mais branché sur le client LLM local (DSPy/smolagents), pas OpenRouter** |
| `references/llm-council/backend/config.py` | `COUNCIL_MODELS` (4 modèles), `CHAIRMAN_MODEL` (Gemini), `OPENROUTER_API_URL` | Config minimale hardcoded. | Faible | Patron à remplacer par une config dynamique (nos modèles locaux) |
| `references/llm-council/backend/main.py` | `send_message`, `send_message_stream` | Endpoints FastAPI + **streaming SSE** stage-par-stage (`stage1_start`→`stage1_complete`→…). | Faible | Patron de progression utile pour un Judge long (mais nous n'avons pas d'UI web) |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/llm-council/backend/council.py` | spec (pattern) | **Le pattern council anonymisé** — le contrat d'anonymisation (labels A/B/C + mapping réversible + format `FINAL RANKING:` + agrégation Borda par position moyenne) |

### Le mécanisme d'anonymisation en détail (cœur de la valeur)
Concentré dans `stage2_collect_rankings()`, en 5 temps :
1. **Génération de labels neutres** : `labels = [chr(65 + i) for i in range(len(stage1_results))]` → `A, B, C, …` (limite pratique ~26 modèles).
2. **Mapping réversible** : `label_to_model = {"Response A": "openai/gpt-5.1", …}`. Ce dict est retourné au caller mais **jamais envoyé aux modèles juges**.
3. **Construction du prompt anonymisé** : chaque réponse devient `Response {label}:\n{response}` — **le nom du modèle auteur n'apparaît jamais**. Le prompt ajoute explicitement la mention `(anonymized)`.
4. **Format de sortie imposé** : le reviewer doit terminer par un bloc `FINAL RANKING:` suivi d'une liste numérotée stricte → parsing déterministe.
5. **De-anonymisation pour l'agrégation** : `calculate_aggregate_rankings()` reçoit `label_to_model` et calcule la **position moyenne** (style Borda).

**Nuance importante** : l'anonymisation ne s'applique **qu'au Stage 2 (peer review)**. Au Stage 3, le Chairman reçoit les **vrais noms** des modèles. Postulat : le Chairman synthétise et peut savoir qui a dit quoi. **À décider** si ce relâchement est acceptable pour le Judge cible (recommandation : garder l'anonymat jusqu'au Chairman pour cohérence).

## Exclusions conscientes
- `references/llm-council/frontend/` (11 fichiers `.jsx`/`.css`) — UI React complète, hors-scope pour un orchestrateur backend Python.
- **OpenRouter payant** — couplage fort à un service cloud ; incompatible avec l'objectif GPU local sans réécriture du client.
- `references/llm-council/backend/storage.py` — persistance JSON plats (un `.json` par conversation, `datetime.utcnow()` déprécié en 3.12+, aucune concurrence gérée). À jeter pour DuckDB.
- `references/llm-council/backend/openrouter.py` : `httpx.AsyncClient` instancié par appel (pas de pooling de connexion) — inefficace à grande échelle.
- Parsing regex fragile : `parse_ranking_from_text` dépend du respect strict du format par le LLM ; fallback laxiste peut produire des rankings erronés silencieusement.
- Pas de tests, pas de CI, pas de versionning sémantique — cohérent avec le statut « vibe coded ».
- Sécurité : clé API lue via `dotenv`, aucun rate-limiting, aucune gestion d'erreur de coût/quota.
- Modèles hardcoded (`gpt-5.1`, `gemini-3-pro-preview`, `claude-sonnet-4.5`, `grok-4`) — noms OpenRouter spécifiques, non portables.

## Correspondance avec `plan_usine_logicielle.md`
- **P6 (Judge / Findings)** : `council.py` (anonymisation A/B/C + 3 stages + agrégation Borda) + `openrouter.py` (parallélisation `asyncio.gather`). **Ne pas intégrer comme dépendance** (vibe-coded, coût 2N+1 appels, OpenRouter-only). Réutiliser le **pattern** comme option d'enrichissement du Judge pour valider des findings à enjeu (le coût élevé se justifie alors). Décision à prendre : garder l'anonymat jusqu'au Chairman (contrairement au dépôt). Complémentaire d'open-swe (09, findings de revue) et code-review-graph (20, risk score quantitatif) — pas en concurrence (council = arbitrage multi-juges, open-swe = format findings, code-review-graph = signaux quantitatifs).
