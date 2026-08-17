# Rapport d'Analyse Post-Mortem
**Source** : `logs/e2e_f113_run.log`
**Date** : 2026-08-17 16:07:32

## 📊 Métriques Globales
- **Durée totale (steps)** : 2979.79 s
- **Tokens (Input)** : 43,909,335
- **Tokens (Output)** : 354,792
- **Verdicts Judge** : 0 approuvé(s) / 0 rejeté(s)
- **Redémarrages Tester** : 0 (un 'Step 1' réapparu = reset de boucle)

## 🗄️ Base de Connaissances (DuckDB)
- **Entités créées** : 51
- **Revendications (Claims)** : 91 (dont 59 'open')

## 🏗️ Répartition par Nœud
| Nœud | Étapes | Durée (s) | Input Tokens | Output Tokens |
|------|--------|-----------|--------------|---------------|
| `PromptRefiner (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Router (fast)` | 0 | 0.00 | 0 | 0 |
| `Architect (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Coder (fast/multimodal)` | 103 | 2979.79 | 43,909,335 | 354,792 |

## 🚨 Erreurs de Logique / Syntaxe
Aucune erreur détectée.

## 💥 Crashes Framework & LLM (Sauvetage, Pydantic, Exceptions)
- **Ligne 3372** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 10802** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`

## ⚠️ Signaux Qualité & Dégradation (infra/outils)
Problèmes d'infrastructure ou d'outils (crash framework, MCP, outils interdits, timeout, connexion LLM) — distincts des bugs de logique du code produit. Impact typique : nœud sans verdict, Judge à l'aveugle, gaspillage de budget.

**Résumé par catégorie** :
- Crash framework (retry/échec définitif) : **2**
- Échec génération LLM (connection/infra) : **1**

**Détail** (max 20) :
- **Ligne 6562** (Coder (fast/multimodal)) — *Échec génération LLM (connection/infra)* : `Error in generating model output:`
- **Ligne 6565** (Coder (fast/multimodal)) — *Crash framework (retry/échec définitif)* : `[-] Erreur interne (Tentative 2/3): Error in generating model output:`
- **Ligne 10807** (Coder (fast/multimodal)) — *Crash framework (retry/échec définitif)* : `[-] Échec définitif pour CoderOutput après 3 tentatives.`
