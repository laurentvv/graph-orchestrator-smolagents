# Rapport d'Analyse Post-Mortem
**Source** : `logs/run_coding_2026-08-22_163103/run_full.log`
**Date** : 2026-08-22 20:13:08

## 📊 Métriques Globales
- **Durée totale (steps)** : 1477.58 s
- **Tokens (Input)** : 5,719,799
- **Tokens (Output)** : 61,225
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
| `Coder (fast/multimodal)` | 36 | 1477.58 | 5,719,799 | 61,225 |

## 🚨 Erreurs de Logique / Syntaxe
Aucune erreur détectée.

## 💥 Crashes Framework & LLM (Sauvetage, Pydantic, Exceptions)
Aucun crash détecté.

## ⚠️ Signaux Qualité & Dégradation (infra/outils)
Problèmes d'infrastructure ou d'outils (crash framework, MCP, outils interdits, timeout, connexion LLM) — distincts des bugs de logique du code produit. Impact typique : nœud sans verdict, Judge à l'aveugle, gaspillage de budget.

Aucun signal de dégradation détecté.
