# Rapport d'Analyse Post-Mortem
**Source** : `logs/e2e_f99_bubble_run3.log`
**Date** : 2026-08-14 22:26:56

## 📊 Métriques Globales
- **Durée totale (steps)** : 1424.10 s
- **Tokens (Input)** : 6,209,853
- **Tokens (Output)** : 63,844
- **Verdicts Judge** : 1 approuvé(s) / 0 rejeté(s)
- **Redémarrages Tester** : 0 (un 'Step 1' réapparu = reset de boucle)

## 🗄️ Base de Connaissances (DuckDB)
- **Entités créées** : 51
- **Revendications (Claims)** : 100 (dont 56 'open')

## 🏗️ Répartition par Nœud
| Nœud | Étapes | Durée (s) | Input Tokens | Output Tokens |
|------|--------|-----------|--------------|---------------|
| `PromptRefiner (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Router (fast)` | 0 | 0.00 | 0 | 0 |
| `Architect (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Coder (fast/multimodal)` | 37 | 1137.95 | 5,327,982 | 60,450 |
| `Tester (fast/multimodal)` | 9 | 286.15 | 881,871 | 3,394 |
| `Security (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Judge (reasoning)` | 0 | 0.00 | 0 | 0 |

## 🚨 Erreurs de Logique / Syntaxe
- **Ligne 2042** (Coder (fast/multimodal)) : `Code parsing failed on line 2 due to: SyntaxError: unterminated string literal`
- **Ligne 6074** (Tester (fast/multimodal)) : `print()' due to: InterpreterError: Forbidden access to module: ntpath`

## 💥 Crashes Framework & LLM (Sauvetage, Pydantic, Exceptions)
- **Ligne 6546** (Tester (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 6547** (Tester (fast/multimodal)) : `[-] Le sauvetage DSPy a échoué : [llama] litellm.InternalServerError: InternalServerError: OpenAIException - Connection error.`

## ⚠️ Signaux Qualité & Dégradation (infra/outils)
Problèmes d'infrastructure ou d'outils (crash framework, MCP, outils interdits, timeout, connexion LLM) — distincts des bugs de logique du code produit. Impact typique : nœud sans verdict, Judge à l'aveugle, gaspillage de budget.

Aucun signal de dégradation détecté.
