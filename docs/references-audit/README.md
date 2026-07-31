# Audit des références — Mode d'emploi

Ce dossier est le **document de suivi** de l'audit radical du dossier `references/` (15 projets, ~10 000 fichiers pertinents). Il permet de retrouver instantanément n'importe quelle information, feature ou code utile, avec son **emplacement complet** et une **évaluation de réutilisabilité** pour `graph-orchestrator-smolagents`.

## 🚀 Par où commencer ?

| Tu veux… | Va à |
|---|---|
| Une vue d'ensemble + la liste des 15 projets | **[INDEX.md](./INDEX.md)** ← document maître |
| Le top des fichiers les plus réutilisables | **[INDEX.md > Hall of Fame](./INDEX.md#-hall-of-fame--top-25-fichiers-les-plus-réutilisables)** |
| Savoir où chercher pour un besoin précis | **[INDEX.md > Guide de recherche](./INDEX.md#-guide-de-recherche--comment-retrouver-x)** |
| Le détail d'un projet précis | **[projects/](./projects/)** (15 fiches) |
| Filtrer/querier l'inventaire par programmation | **[inventory.json](./inventory.json)** (356 entrées) |

## 📚 Structure

```
docs/references-audit/
├── README.md              ← tu es ici (mode d'emploi)
├── INDEX.md               ← document maître (navigation + synthèse + Hall of Fame + matrice + guide)
├── inventory.json         ← inventaire machine-lisible (15 projets, 356 entrées)
└── projects/              ← 15 fiches détaillées (1 par projet)
    ├── 01-prompt-vault.md  …  13-deer-flow-analysis.md
    └── 14-qm.md  …  15-claude-code-unified-agents.md
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
