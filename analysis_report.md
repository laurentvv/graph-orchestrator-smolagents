# Rapport d'Analyse Post-Mortem
**Source** : `logs\run-2026-08-20_tetris_fresh7.log`
**Date** : 2026-08-20 21:12:40

## 📊 Métriques Globales
- **Durée totale (steps)** : 5559.50 s
- **Tokens (Input)** : 14,808,153
- **Tokens (Output)** : 192,427
- **Verdicts Judge** : 0 approuvé(s) / 0 rejeté(s)
- **Redémarrages Tester** : 0 (un 'Step 1' réapparu = reset de boucle)

## 🗄️ Base de Connaissances (DuckDB)
- **Entités créées** : 60
- **Revendications (Claims)** : 131 (dont 76 'open')

## 🏗️ Répartition par Nœud
| Nœud | Étapes | Durée (s) | Input Tokens | Output Tokens |
|------|--------|-----------|--------------|---------------|
| `PromptRefiner (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Router (fast)` | 0 | 0.00 | 0 | 0 |
| `Architect (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Coder (fast/multimodal)` | 57 | 4658.52 | 13,641,786 | 188,730 |
| `Tester (fast/multimodal)` | 11 | 900.98 | 1,166,367 | 3,697 |
| `Security (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Judge (reasoning)` | 0 | 0.00 | 0 | 0 |

## 🚨 Erreurs de Logique / Syntaxe
- **Ligne 6342** (Coder (fast/multimodal)) : `Code parsing failed on line 1 due to: SyntaxError: unterminated string literal`
- **Ligne 8318** (Coder (fast/multimodal)) : `Code parsing failed on line 1 due to: SyntaxError: unterminated string literal`

## 💥 Crashes Framework & LLM (Sauvetage, Pydantic, Exceptions)
Aucun crash détecté.

## ⚠️ Signaux Qualité & Dégradation (infra/outils)
Problèmes d'infrastructure ou d'outils (crash framework, MCP, outils interdits, timeout, connexion LLM) — distincts des bugs de logique du code produit. Impact typique : nœud sans verdict, Judge à l'aveugle, gaspillage de budget.

**Résumé par catégorie** :
- Timeout de nœud (sans verdict) : **1**

**Détail** (max 20) :
- **Ligne 13275** (Tester (fast/multimodal)) — *Timeout de nœud (sans verdict)* : `[-] Timeout du nœud tester après 900s (Chrome/DevTools/Puppeteer bloqué ?) — passage au nœud suivant.`
