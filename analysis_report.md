# Rapport d'Analyse Post-Mortem
**Source** : `logs\run-f65-validation-fix-20260807_200337.log`
**Date** : 2026-08-10 16:26:32

## 📊 Métriques Globales
- **Durée totale (steps)** : 1394.38 s
- **Tokens (Input)** : 1,569,081
- **Tokens (Output)** : 15,302
- **Verdicts Judge** : 1 approuvé(s) / 0 rejeté(s)
- **Redémarrages Tester** : 2 (un 'Step 1' réapparu = reset de boucle)

## 🗄️ Base de Connaissances (DuckDB)
- **Entités créées** : 47
- **Revendications (Claims)** : 85 (dont 45 'open')

## 🏗️ Répartition par Nœud
| Nœud | Étapes | Durée (s) | Input Tokens | Output Tokens |
|------|--------|-----------|--------------|---------------|
| `Router (fast)` | 0 | 0.00 | 0 | 0 |
| `Coder (fast/multimodal)` | 5 | 580.77 | 237,708 | 6,564 |
| `Tester (fast/multimodal)` | 21 | 813.61 | 1,331,373 | 8,738 |
| `Security (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Judge (reasoning)` | 0 | 0.00 | 0 | 0 |

## 🚨 Erreurs de Logique / Syntaxe
Aucune erreur détectée.

## 💥 Crashes Framework & LLM (Sauvetage, Pydantic, Exceptions)
- **Ligne 2484** (Tester (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 2485** (Tester (fast/multimodal)) : `[-] Le sauvetage DSPy a échoué : litellm.InternalServerError: InternalServerError: OpenAIException - Connection error.`
- **Ligne 3790** (Tester (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 3791** (Tester (fast/multimodal)) : `[-] Le sauvetage DSPy a échoué : litellm.InternalServerError: InternalServerError: OpenAIException - Connection error.`
- **Ligne 5089** (Tester (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 5090** (Tester (fast/multimodal)) : `[-] Le sauvetage DSPy a échoué : litellm.InternalServerError: InternalServerError: OpenAIException - Connection error.`

## ⚠️ Signaux Qualité & Dégradation (infra/outils)
Problèmes d'infrastructure ou d'outils (crash framework, MCP, outils interdits, timeout, connexion LLM) — distincts des bugs de logique du code produit. Impact typique : nœud sans verdict, Judge à l'aveugle, gaspillage de budget.

Aucun signal de dégradation détecté.
