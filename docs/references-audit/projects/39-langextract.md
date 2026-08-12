# 19 — langextract

## En-tête
- **Nom** : langextract
- **Chemin** : `references/langextract/`
- **Type** : Bibliothèque Python d'extraction structurée (Google)
- **Langage principal** : Python
- **Statistiques** : ~80 fichiers (majoritairement Python)

## Synthèse
LangExtract est une bibliothèque développée par Google pour extraire des informations structurées à partir de textes longs en utilisant des LLM. Son atout majeur est le "grounding" (ancrage), qui s'assure que chaque entité extraite correspond exactement à un segment du texte source via des algorithmes d'alignement de tokens (difflib/LCS), évitant ainsi les hallucinations.
Pour `graph-orchestrator-smolagents`, cette approche de "grounding" par alignement est très précieuse pour la vérification des "findings" (P6 Judge) : s'assurer que les problèmes de code identifiés par un agent existent réellement dans le fichier source. De plus, son traitement par morceaux avec conservation de contexte inter-chunks (`ContextAwarePromptBuilder`) est un excellent pattern pour la priorisation P9 (Compaction). L'ensemble du code est d'une très haute qualité et directement exploitable (🟢).

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| [`langextract/resolver.py`](file:///references/langextract/langextract/resolver.py) | `WordAligner`, `_fuzzy_align_extraction` | Algorithme d'alignement (difflib/LCS) pour ancrer les extractions LLM dans le texte source | 🟢 Haute | Indispensable pour s'assurer que les "findings" LLM (P6) existent bien dans le code. |
| [`langextract/prompt_validation.py`](file:///references/langextract/langextract/prompt_validation.py) | `validate_prompt_alignment` | Validation stricte de l'alignement des exemples few-shot | 🟢 Haute | Pattern applicable pour valider nos prompts (P6 / P10). |
| [`langextract/prompting.py`](file:///references/langextract/langextract/prompting.py) | `ContextAwarePromptBuilder` | Construction de prompts qui transmettent la fin du chunk précédent au chunk suivant | 🟢 Haute | Pattern crucial pour l'analyse de gros fichiers découpés en chunks (P9 Compaction). |
| [`langextract/extraction.py`](file:///references/langextract/langextract/extraction.py) | `extract`, `extraction_passes` | Stratégie multi-passes pour augmenter le rappel sur des documents longs | 🟢 Haute | Mécanisme de réduction et d'extraction parallèle (P9). |
| [`langextract/core/format_handler.py`](file:///references/langextract/langextract/core/format_handler.py) | `FormatHandler._parse_with_fallback`, `_THINK_TAG_RE` | Gestion robuste du parsing JSON/YAML, incluant le nettoyage des balises `<think>` (DeepSeek) | 🟢 Haute | Middleware idéal pour parser les sorties LLM de manière robuste (P8 Middlewares). |

## Exclusions conscientes
- `langextract/providers/` : Intégrations API spécifiques (Gemini, OpenAI, Ollama) ignorées car `smolagents` gère déjà l'interfaçage LLM.
- `langextract/visualization.py` : Génération HTML ignorée (hors-scope pour un orchestrateur backend).
- `tests/` et `examples/` : Utiles pour la documentation mais pas pour l'extraction de code.

## Correspondance avec `plan_usine_logicielle.md`
- **P6** : Validation des findings (grounding) via `WordAligner` (`resolver.py`) et `validate_prompt_alignment`.
- **P8** : Middleware robuste pour le parsing de fences et balises `<think>` via `FormatHandler`.
- **P9** : Stratégie de découpage avec `ContextAwarePromptBuilder` et multi-passes avec `extract`.