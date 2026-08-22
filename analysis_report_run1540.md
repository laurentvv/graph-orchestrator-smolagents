# Rapport d'Analyse Post-Mortem
**Source** : `logs/run_coding_2026-08-22_154027/run_full.log`
**Date** : 2026-08-22 20:12:50

## 📊 Métriques Globales
- **Durée totale (steps)** : 2343.09 s
- **Tokens (Input)** : 35,070,099
- **Tokens (Output)** : 398,670
- **Verdicts Judge** : 0 approuvé(s) / 0 rejeté(s)
- **Redémarrages Tester** : 0 (un 'Step 1' réapparu = reset de boucle)

## 🗄️ Base de Connaissances (DuckDB)
- **Entités créées** : 63
- **Revendications (Claims)** : 132 (dont 61 'open')

## 🏗️ Répartition par Nœud
| Nœud | Étapes | Durée (s) | Input Tokens | Output Tokens |
|------|--------|-----------|--------------|---------------|
| `PromptRefiner (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Router (fast)` | 0 | 0.00 | 0 | 0 |
| `Architect (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Coder (fast/multimodal)` | 78 | 2343.09 | 35,070,099 | 398,670 |

## 🚨 Erreurs de Logique / Syntaxe
- **Ligne 3123** (Coder (fast/multimodal)) : `print("styles.css does not exist")' due to: InterpreterError: Forbidden`

## 💥 Crashes Framework & LLM (Sauvetage, Pydantic, Exceptions)
- **Ligne 3378** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`

## ⚠️ Signaux Qualité & Dégradation (infra/outils)
Problèmes d'infrastructure ou d'outils (crash framework, MCP, outils interdits, timeout, connexion LLM) — distincts des bugs de logique du code produit. Impact typique : nœud sans verdict, Judge à l'aveugle, gaspillage de budget.

Aucun signal de dégradation détecté.
