# Rapport d'Analyse Post-Mortem
**Source** : `logs/run_coding_2026-08-22_173220/run_full.log`
**Date** : 2026-08-22 20:13:09

## 📊 Métriques Globales
- **Durée totale (steps)** : 4890.26 s
- **Tokens (Input)** : 45,252,439
- **Tokens (Output)** : 328,753
- **Verdicts Judge** : 0 approuvé(s) / 0 rejeté(s)
- **Redémarrages Tester** : 1 (un 'Step 1' réapparu = reset de boucle)

## 🗄️ Base de Connaissances (DuckDB)
- **Entités créées** : 63
- **Revendications (Claims)** : 132 (dont 61 'open')

## 🏗️ Répartition par Nœud
| Nœud | Étapes | Durée (s) | Input Tokens | Output Tokens |
|------|--------|-----------|--------------|---------------|
| `PromptRefiner (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Router (fast)` | 0 | 0.00 | 0 | 0 |
| `Architect (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Coder (fast/multimodal)` | 95 | 3079.31 | 41,501,178 | 308,690 |
| `Tester (fast/multimodal)` | 27 | 1810.95 | 3,751,261 | 20,063 |
| `Security (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Judge (reasoning)` | 0 | 0.00 | 0 | 0 |

## 🚨 Erreurs de Logique / Syntaxe
- **Ligne 4043** (Tester (fast/multimodal)) : `Code parsing failed on line 1 due to: SyntaxError: unexpected character after`
- **Ligne 4101** (Tester (fast/multimodal)) : `Code parsing failed on line 1 due to: SyntaxError: closing parenthesis '}' does`
- **Ligne 4187** (Tester (fast/multimodal)) : `Code parsing failed on line 1 due to: SyntaxError: '(' was never closed`
- **Ligne 9368** (Tester (fast/multimodal)) : `Code parsing failed on line 1 due to: SyntaxError: '(' was never closed`

## 💥 Crashes Framework & LLM (Sauvetage, Pydantic, Exceptions)
- **Ligne 2820** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 4310** (Tester (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 6744** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`

## ⚠️ Signaux Qualité & Dégradation (infra/outils)
Problèmes d'infrastructure ou d'outils (crash framework, MCP, outils interdits, timeout, connexion LLM) — distincts des bugs de logique du code produit. Impact typique : nœud sans verdict, Judge à l'aveugle, gaspillage de budget.

**Résumé par catégorie** :
- Forbidden function (outil non déclaré) : **4**
- Timeout de nœud (sans verdict) : **1**
- Échec génération LLM (connection/infra) : **1**

**Détail** (max 20) :
- **Ligne 8182** (Tester (fast/multimodal)) — *Forbidden function (outil non déclaré)* : `swapped = true;\n            }")' due to: InterpreterError: Forbidden function`
- **Ligne 8561** (Tester (fast/multimodal)) — *Forbidden function (outil non déclaré)* : `updateSpeedDisplay();\n}")' due to: InterpreterError: Forbidden function`
- **Ligne 8929** (Tester (fast/multimodal)) — *Forbidden function (outil non déclaré)* : `f.write(content)' due to: InterpreterError: Forbidden function evaluation:`
- **Ligne 9232** (Tester (fast/multimodal)) — *Forbidden function (outil non déclaré)* : `f.write(content)' due to: InterpreterError: Forbidden function evaluation:`
- **Ligne 9432** (Tester (fast/multimodal)) — *Timeout de nœud (sans verdict)* : `[-] Timeout du nœud tester après 1800s (Chrome/DevTools/Puppeteer bloqué ?) — passage au nœud suivant.`
- **Ligne 9433** (Tester (fast/multimodal)) — *Échec génération LLM (connection/infra)* : `Error in generating model output:`
