# Rapport d'Analyse Post-Mortem
**Source** : `logs/e2e_f113_dedicated.log`
**Date** : 2026-08-17 21:20:04

## 📊 Métriques Globales
- **Durée totale (steps)** : 1351.78 s
- **Tokens (Input)** : 14,347,323
- **Tokens (Output)** : 119,098
- **Verdicts Judge** : 1 approuvé(s) / 0 rejeté(s)
- **Redémarrages Tester** : 1 (un 'Step 1' réapparu = reset de boucle)

## 🗄️ Base de Connaissances (DuckDB)
- **Entités créées** : 52
- **Revendications (Claims)** : 100 (dont 63 'open')

## 🏗️ Répartition par Nœud
| Nœud | Étapes | Durée (s) | Input Tokens | Output Tokens |
|------|--------|-----------|--------------|---------------|
| `PromptRefiner (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Router (fast)` | 0 | 0.00 | 0 | 0 |
| `Architect (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Coder (fast/multimodal)` | 45 | 851.12 | 12,895,851 | 112,621 |
| `Tester (fast/multimodal)` | 16 | 500.66 | 1,451,472 | 6,477 |
| `Security (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Judge (reasoning)` | 0 | 0.00 | 0 | 0 |

## 🚨 Erreurs de Logique / Syntaxe
- **Ligne 1659** (Coder (fast/multimodal)) : `Code parsing failed on line 20 due to: SyntaxError: unterminated triple-quoted`
- **Ligne 3733** (Tester (fast/multimodal)) : `ValueError: tool evaluate_script does not support multiple positional arguments`

## 💥 Crashes Framework & LLM (Sauvetage, Pydantic, Exceptions)
- **Ligne 3843** (Tester (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 6691** (Tester (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`

## ⚠️ Signaux Qualité & Dégradation (infra/outils)
Problèmes d'infrastructure ou d'outils (crash framework, MCP, outils interdits, timeout, connexion LLM) — distincts des bugs de logique du code produit. Impact typique : nœud sans verdict, Judge à l'aveugle, gaspillage de budget.

**Résumé par catégorie** :
- Erreur outil MCP (-32602 validation) : **1**

**Détail** (max 20) :
- **Ligne 5143** (Coder (fast/multimodal)) — *Erreur outil MCP (-32602 validation)* : `MCP error -32602: Input validation error: Invalid arguments for tool`
