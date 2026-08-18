# Rapport d'Analyse Post-Mortem
**Source** : `logs/e2e_f120_run.log`
**Date** : 2026-08-18 15:46:35

## 📊 Métriques Globales
- **Durée totale (steps)** : 6220.36 s
- **Tokens (Input)** : 74,749,542
- **Tokens (Output)** : 615,167
- **Verdicts Judge** : 0 approuvé(s) / 0 rejeté(s)
- **Redémarrages Tester** : 0 (un 'Step 1' réapparu = reset de boucle)

## 🗄️ Base de Connaissances (DuckDB)
- **Entités créées** : 54
- **Revendications (Claims)** : 105 (dont 66 'open')

## 🏗️ Répartition par Nœud
| Nœud | Étapes | Durée (s) | Input Tokens | Output Tokens |
|------|--------|-----------|--------------|---------------|
| `PromptRefiner (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Router (fast)` | 0 | 0.00 | 0 | 0 |
| `Architect (reasoning)` | 0 | 0.00 | 0 | 0 |
| `Coder (fast/multimodal)` | 186 | 6220.36 | 74,749,542 | 615,167 |

## 🚨 Erreurs de Logique / Syntaxe
- **Ligne 6688** (Coder (fast/multimodal)) : `Code parsing failed on line 1 due to: SyntaxError: unmatched ']' (<unknown>,`
- **Ligne 7047** (Coder (fast/multimodal)) : `SyntaxError: Unexpected token '<'`
- **Ligne 9213** (Coder (fast/multimodal)) : `Code parsing failed on line 2 due to: SyntaxError: unterminated string literal`
- **Ligne 10762** (Coder (fast/multimodal)) : `msgid=1 [error] Uncaught SyntaxError: Invalid or unexpected token (0 args)`

## 💥 Crashes Framework & LLM (Sauvetage, Pydantic, Exceptions)
- **Ligne 4513** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 7789** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 12571** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`
- **Ligne 17851** (Coder (fast/multimodal)) : `[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour CoderOutput...`

## ⚠️ Signaux Qualité & Dégradation (infra/outils)
Problèmes d'infrastructure ou d'outils (crash framework, MCP, outils interdits, timeout, connexion LLM) — distincts des bugs de logique du code produit. Impact typique : nœud sans verdict, Judge à l'aveugle, gaspillage de budget.

**Résumé par catégorie** :
- Forbidden function (outil non déclaré) : **3**
- Crash framework (retry/échec définitif) : **3**
- Échec génération LLM (connection/infra) : **2**
- Erreur outil MCP (-32602 validation) : **1**

**Détail** (max 20) :
- **Ligne 14325** (Coder (fast/multimodal)) — *Forbidden function (outil non déclaré)* : `Error reading index.html: Forbidden function evaluation: 'open' is not among`
- **Ligne 14327** (Coder (fast/multimodal)) — *Forbidden function (outil non déclaré)* : `Error reading styles.css: Forbidden function evaluation: 'open' is not among`
- **Ligne 14329** (Coder (fast/multimodal)) — *Forbidden function (outil non déclaré)* : `Error reading script.js: Forbidden function evaluation: 'open' is not among the`
- **Ligne 14988** (Coder (fast/multimodal)) — *Erreur outil MCP (-32602 validation)* : `Out: MCP error -32602: Input validation error: Invalid arguments for tool`
- **Ligne 15713** (Coder (fast/multimodal)) — *Échec génération LLM (connection/infra)* : `Error in generating model output:`
- **Ligne 15716** (Coder (fast/multimodal)) — *Crash framework (retry/échec définitif)* : `[-] Erreur interne (Tentative 1/3): Error in generating model output:`
- **Ligne 18430** (Coder (fast/multimodal)) — *Échec génération LLM (connection/infra)* : `Error in generating model output:`
- **Ligne 18433** (Coder (fast/multimodal)) — *Crash framework (retry/échec définitif)* : `[-] Erreur interne (Tentative 3/3): Error in generating model output:`
- **Ligne 18436** (Coder (fast/multimodal)) — *Crash framework (retry/échec définitif)* : `[-] Échec définitif pour CoderOutput après 3 tentatives.`
