# Rapport d'Analyse Post-Mortem
**Source** : `logs/run_coding_2026-08-06_171636/run_full.log`
**Date** : 2026-08-06 19:16:05

## 📊 Métriques Globales
- **Durée totale (steps)** : 5436.78 s
- **Tokens (Input)** : 18,391,575
- **Tokens (Output)** : 234,111
- **Verdicts Judge** : 0 approuvé(s) / 0 rejeté(s)
- **Redémarrages Tester** : 0 (un 'Step 1' réapparu = reset de boucle)

## 🗄️ Base de Connaissances (DuckDB)
- **Entités créées** : 42
- **Revendications (Claims)** : 64 (dont 32 'open')

## 🏗️ Répartition par Nœud
| Nœud | Étapes | Durée (s) | Input Tokens | Output Tokens |
|------|--------|-----------|--------------|---------------|
| `PromptRefiner (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Router (fast)` | 0 | 0.00 | 0 | 0 |
| `Architect (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Coder (fast/multimodal)` | 87 | 4831.51 | 18,245,966 | 230,448 |
| `Tester (fast/multimodal)` | 4 | 552.30 | 145,609 | 3,663 |
| `Security (reasoning)` | 1 | 52.97 | 0 | 0 |
| `Judge (reasoning)` | 0 | 0.00 | 0 | 0 |

## 🚨 Erreurs de Logique / Syntaxe
- **Ligne 1121** (Coder (fast/multimodal)) : `Code parsing failed on line 1 due to: SyntaxError: closing parenthesis '}' does`
- **Ligne 1591** (Coder (fast/multimodal)) : `Code parsing failed on line 1 due to: SyntaxError: closing parenthesis '}' does`
- **Ligne 3050** (Tester (fast/multimodal)) : `src=\"script.js\"></script>\n</body>\n</html>\n")' due to: InterpreterError:`
- **Ligne 3647** (Tester (fast/multimodal)) : `Code execution failed at line 'import os' due to: InterpreterError: Import of`
- **Ligne 6833** (Coder (fast/multimodal)) : `SyntaxError: Unexpected identifier 'array'`
- **Ligne 7242** (Coder (fast/multimodal)) : `SyntaxError: Unexpected identifier 'data'`
- **Ligne 10739** (Coder (fast/multimodal)) : `print(f"Terminé par: {repr(content[-50:])}")' due to: InterpreterError:`

## 💥 Crashes Framework & LLM (Sauvetage, Pydantic, Exceptions)
- **Ligne 5393** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 5394** (Coder (fast/multimodal)) : `[-] Le sauvetage DSPy a échoué : litellm.InternalServerError: InternalServerError: OpenAIException - Connection error.`
- **Ligne 8523** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 8524** (Coder (fast/multimodal)) : `[-] Le sauvetage DSPy a échoué : litellm.InternalServerError: InternalServerError: OpenAIException - Connection error.`
- **Ligne 11761** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 11762** (Coder (fast/multimodal)) : `[-] Le sauvetage DSPy a échoué : litellm.InternalServerError: InternalServerError: OpenAIException - Connection error.`

## ⚠️ Signaux Qualité & Dégradation (infra/outils)
Problèmes d'infrastructure ou d'outils (crash framework, MCP, outils interdits, timeout, connexion LLM) — distincts des bugs de logique du code produit. Impact typique : nœud sans verdict, Judge à l'aveugle, gaspillage de budget.

**Résumé par catégorie** :
- Forbidden function (outil non déclaré) : **2**
- Timeout de nœud (sans verdict) : **1**
- Échec génération LLM (connection/infra) : **1**
- Crash framework (retry/échec définitif) : **1**

**Détail** (max 20) :
- **Ligne 3051** (Tester (fast/multimodal)) — *Forbidden function (outil non déclaré)* : `Forbidden function evaluation: 'write_file' is not among the explicitly allowed`
- **Ligne 3653** (Tester (fast/multimodal)) — *Timeout de nœud (sans verdict)* : `[-] Timeout du nœud tester après 600s (Chrome/DevTools/Puppeteer bloqué ?) — passage au nœud suivant.`
- **Ligne 3658** (Security (reasoning)) — *Échec génération LLM (connection/infra)* : `Error in generating model output:`
- **Ligne 10740** (Coder (fast/multimodal)) — *Forbidden function (outil non déclaré)* : `Forbidden function evaluation: 'open' is not among the explicitly allowed tools`
- **Ligne 11765** (Coder (fast/multimodal)) — *Crash framework (retry/échec définitif)* : `[-] Échec définitif pour CoderOutput après 3 tentatives.`
