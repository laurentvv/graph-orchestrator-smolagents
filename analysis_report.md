# Rapport d'Analyse Post-Mortem
**Source** : `logs/run_coding_2026-08-19_225020/run_full.log`
**Date** : 2026-08-19 23:50:35

## 📊 Métriques Globales
- **Durée totale (steps)** : 2377.14 s
- **Tokens (Input)** : 29,525,592
- **Tokens (Output)** : 303,938
- **Verdicts Judge** : 0 approuvé(s) / 0 rejeté(s)
- **Redémarrages Tester** : 0 (un 'Step 1' réapparu = reset de boucle)

## 🗄️ Base de Connaissances (DuckDB)
- **Entités créées** : 59
- **Revendications (Claims)** : 125 (dont 72 'open')

## 🏗️ Répartition par Nœud
| Nœud | Étapes | Durée (s) | Input Tokens | Output Tokens |
|------|--------|-----------|--------------|---------------|
| `PromptRefiner (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Router (fast)` | 0 | 0.00 | 0 | 0 |
| `Architect (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Coder (fast/multimodal)` | 72 | 2377.14 | 29,525,592 | 303,938 |

## 🚨 Erreurs de Logique / Syntaxe
- **Ligne 10814** (Coder (fast/multimodal)) : `print("No draft file found")' due to: InterpreterError: Forbidden access to`

## 💥 Crashes Framework & LLM (Sauvetage, Pydantic, Exceptions)
- **Ligne 4523** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 9963** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`

## ⚠️ Signaux Qualité & Dégradation (infra/outils)
Problèmes d'infrastructure ou d'outils (crash framework, MCP, outils interdits, timeout, connexion LLM) — distincts des bugs de logique du code produit. Impact typique : nœud sans verdict, Judge à l'aveugle, gaspillage de budget.

Aucun signal de dégradation détecté.
