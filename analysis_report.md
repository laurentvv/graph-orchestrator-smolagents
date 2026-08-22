# Rapport d'Analyse Post-Mortem
**Source** : `logs/run_coding_2026-08-22_123746/run_full.log`
**Date** : 2026-08-22 14:33:54

## 📊 Métriques Globales
- **Durée totale (steps)** : 2828.82 s
- **Tokens (Input)** : 37,917,037
- **Tokens (Output)** : 415,047
- **Verdicts Judge** : 0 approuvé(s) / 0 rejeté(s)
- **Redémarrages Tester** : 0 (un 'Step 1' réapparu = reset de boucle)

## 🗄️ Base de Connaissances (DuckDB)
- **Entités créées** : 63
- **Revendications (Claims)** : 127 (dont 60 'open')

## 🏗️ Répartition par Nœud
| Nœud | Étapes | Durée (s) | Input Tokens | Output Tokens |
|------|--------|-----------|--------------|---------------|
| `PromptRefiner (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Router (fast)` | 0 | 0.00 | 0 | 0 |
| `Architect (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Coder (fast/multimodal)` | 90 | 2828.82 | 37,917,037 | 415,047 |

## 🚨 Erreurs de Logique / Syntaxe
- **Ligne 8376** (Coder (fast/multimodal)) : `Code parsing failed on line 1 due to: SyntaxError: '(' was never closed`
- **Ligne 8501** (Coder (fast/multimodal)) : `Code parsing failed on line 1 due to: SyntaxError: '(' was never closed`
- **Ligne 9023** (Coder (fast/multimodal)) : `Code parsing failed on line 1 due to: SyntaxError: '(' was never closed`

## 💥 Crashes Framework & LLM (Sauvetage, Pydantic, Exceptions)
- **Ligne 3530** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 6676** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`

## ⚠️ Signaux Qualité & Dégradation (infra/outils)
Problèmes d'infrastructure ou d'outils (crash framework, MCP, outils interdits, timeout, connexion LLM) — distincts des bugs de logique du code produit. Impact typique : nœud sans verdict, Judge à l'aveugle, gaspillage de budget.

**Résumé par catégorie** :
- Forbidden function (outil non déclaré) : **1**

**Détail** (max 20) :
- **Ligne 9138** (Coder (fast/multimodal)) — *Forbidden function (outil non déclaré)* : `content = f.read()' due to: InterpreterError: Forbidden function`
