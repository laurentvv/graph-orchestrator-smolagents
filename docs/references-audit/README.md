# Audit des références — Mode d'emploi

Une base de connaissances structurée regroupant l'audit profond de **44 projets** de référence (frameworks, agents de coding, collections de prompts). L'objectif est d'alimenter `graph-orchestrator-smolagents` en algorithmes, patterns d'orchestration et system prompts de la plus haute qualité.

## 🚀 Par où commencer ?

1. [**INDEX.md**](./INDEX.md) : le document de navigation principal (la liste des 44 projets, la matrice de réutilisabilité et le guide « comment retrouver X »).
2. [**projects/**](./projects/) : le dossier contenant les rapports d'audit détaillés (44 fiches au format Markdown canonique).
3. [**inventory.json**](./inventory.json) : l'inventaire machine (569 entrées), généré automatiquement par `update_inventory.py`, permettant d'interroger la base programmatiquement.

## 📚 Structure

```
docs/references-audit/
├── README.md              ← Ce document
├── INDEX.md               ← Point d'entrée principal
├── inventory.json         ← Inventaire JSON des 494 briques réutilisables
└── projects/              ← 44 fiches d'audit
    ├── 01-prompt-vault.md  …  13-deer-flow-analysis.md
    ├── 14-qm.md  …  18-awesome-claude-skills.md
    └── 19-loopx.md  …  29-system-prompts-leaks.md
```

## 🎯 Convention de réutilisabilité

Chaque fichier inventorié est noté selon sa valeur d'export directe pour `graph-orchestrator-smolagents` :

| Note | Signification | Action typique |
|---|---|---|
| 🟢 **Haute** | Code/pattern directement adaptable | Étudier en priorité pour intégration |
| 🟡 **Moyenne** | Pattern intéressant, adaptation non-triviale | Source d'inspiration / calibrage |
| 🔴 **Faible** | Non portable (autre langage, écosystème spécifique) | Référence conceptuelle au mieux |

Cette note est **relative au projet cible** (orchestrateur multi-agent Python DSPy/smolagents avec persistance DuckDB). Un fichier TypeScript brillant sera noté Faible même s'il est excellent en soi, parce qu'il n'est pas portable vers Python.

## 🗂️ Format d'une fiche projet

Chaque fiche de `projects/` suit la même structure :
1. **En-tête** : nom, chemin, type, langage, statistiques.
2. **Synthèse** : à quoi sert le projet + utilité perçue + note globale.
3. **Documentation pertinente** : table `Chemin | Description | Réutilisabilité`.
4. **Code réutilisable** : table `Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification`.
5. **Contrats / Specs / Config** : JSON/YAML de spec ou de protocole.
6. **Exclusions conscientes** : ce qui a été ignoré et pourquoi.

> Les chemins sont **toujours relatifs à la racine du repo** (`references/<projet>/...`), cliquables depuis un IDE.

## 🔎 Rechercher dans l'inventaire

### Recherche manuelle
Le **[Guide de recherche](./INDEX.md#-guide-de-recherche--comment-retrouver-x)** dans l'INDEX répond aux besoins typiques (« je cherche un anti-loop », « un modèle de nœud Tester », etc.).

### Recherche programmatique (`inventory.json`)
```python
import json

with open('docs/references-audit/inventory.json', encoding='utf-8') as f:
    inv = json.load(f)

# Tous les fichiers à réutilisabilité Haute, triés par projet
for p in inv['projects']:
    high = [f for f in p['files'] if f['reuse'] == 'high']
    if high:
        print(f"\n{p['name']} ({len(high)} Haute):")
        for f in high:
            print(f"  {f['path']}  →  {f.get('key_symbols', [])}")

# Chercher un symbole précis
keyword = 'pagerank'
hits = [(p['name'], f) for p in inv['projects'] for f in p['files']
        if keyword in str(f.get('key_symbols', [])).lower()
        or keyword in f.get('description', '').lower()]
```

### Recherche en ligne de commande
```bash
# Tous les fichiers notés Haute dans l'inventaire
python -c "
import json
inv = json.load(open('docs/references-audit/inventory.json', encoding='utf-8'))
for p in inv['projects']:
    for f in p['files']:
        if f['reuse']=='high': print(f['path'])
"

# grep dans les fiches Markdown
grep -rl 'circuit' docs/references-audit/projects/
```

## 📅 Maintenance

- **Audit initial** : 2026-07-31
- **Périmètre** : filtered-useful (docs + code + specs ; excludes `.git/`, `node_modules/`, médias, fixtures, traductions README).
- Si un nouveau projet est ajouté à `references/`, créer une fiche `projects/NN-<nom>.md`, ajouter une entrée à `inventory.json`, et mettre à jour l'`INDEX.md`.
- Si un projet existant évolue significativement, rafraîchir sa fiche et les entrées correspondantes de l'`inventory.json`.

## ⚠️ Limites connues

- **Sous-clones non audités en détail** : `RepoGraph/SWE-agent/` (sous-clone externe, signalé en exclusion dans la fiche 04).
- **Gros projets sous-filtrés** : `opencode` (4 454 fichiers) et `deer-flow` (2 023 fichiers) ont été inventoriés de façon représentative — les fichiers Haute/Moyenne sont exhaustifs, les Faibles regroupés par package/module.
- **Code non portable intentionnellement compacté** : UI TypeScript (opencode TUI/web, openfox React, axon dashboard, deer-flow/frontend) regroupé en entrées agrégées (`"aggregate": true` dans le JSON).
- Les noms de symboles (`key_symbols`) ont été vérifiés par lecture du code pour les fichiers Haute/Moyenne ; pour les entrées agrégées, ils peuvent être représentatifs plutôt qu'exhaustifs.
