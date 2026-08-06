# Rapport d'Analyse Post-Mortem
**Source** : `logs/run_coding_2026-08-06_201649/run_full.log`
**Date** : 2026-08-06 21:43:00

## 📊 Métriques Globales
- **Durée totale (steps)** : 3944.01 s
- **Tokens (Input)** : 10,268,674
- **Tokens (Output)** : 152,505
- **Verdicts Judge** : 0 approuvé(s) / 0 rejeté(s)
- **Redémarrages Tester** : 0 (un 'Step 1' réapparu = reset de boucle)

## 🗄️ Base de Connaissances (DuckDB)
- **Entités créées** : 42
- **Revendications (Claims)** : 66 (dont 33 'open')

## 🏗️ Répartition par Nœud
| Nœud | Étapes | Durée (s) | Input Tokens | Output Tokens |
|------|--------|-----------|--------------|---------------|
| `PromptRefiner (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Router (fast)` | 0 | 0.00 | 0 | 0 |
| `Architect (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Coder (fast/multimodal)` | 66 | 3944.01 | 10,268,674 | 152,505 |

## 🚨 Erreurs de Logique / Syntaxe
- **Ligne 1745** (Coder (fast/multimodal)) : `Code parsing failed on line 1 due to: SyntaxError: unterminated triple-quoted`

## 💥 Crashes Framework & LLM (Sauvetage, Pydantic, Exceptions)
- **Ligne 4172** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 4173** (Coder (fast/multimodal)) : `[-] Le sauvetage DSPy a échoué : litellm.InternalServerError: InternalServerError: OpenAIException - Connection error.`
- **Ligne 7051** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 7052** (Coder (fast/multimodal)) : `[-] Le sauvetage DSPy a échoué : litellm.InternalServerError: InternalServerError: OpenAIException - Connection error.`

## ⚠️ Signaux Qualité & Dégradation (infra/outils)
Problèmes d'infrastructure ou d'outils (crash framework, MCP, outils interdits, timeout, connexion LLM) — distincts des bugs de logique du code produit. Impact typique : nœud sans verdict, Judge à l'aveugle, gaspillage de budget.

**Résumé par catégorie** :
- Forbidden function (outil non déclaré) : **1**
- Crash framework (retry/échec définitif) : **1**

**Détail** (max 20) :
- **Ligne 2242** (Coder (fast/multimodal)) — *Forbidden function (outil non déclaré)* : `InterpreterError: Forbidden function evaluation: 'take_snapshot' is not among`
- **Ligne 9503** (Coder (fast/multimodal)) — *Crash framework (retry/échec définitif)* : `[-] Échec définitif pour CoderOutput après 3 tentatives.`
