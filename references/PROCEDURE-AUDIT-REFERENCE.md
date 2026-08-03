# Procédure : Audit d'une nouvelle référence

> **Workflow reproductible** pour intégrer un nouveau dépôt dans `references/` vers `docs/references-audit/` + `plan_usine_logicielle.md`. Inspiré du travail réel effectué sur les fiches 01–18.
>
> **Objectif** : transformer un dépôt de référence en matière actionnable pour `graph-orchestrator-smolagents` — fiche d'audit, entrées d'inventaire, intégrations au plan — en gardant une cohérence stricte (chiffres, format, traçabilité).

---

## 📋 Étape 0 — Détection des dépôts non audités

Avant de traiter une nouvelle référence, identifier ce qui manque. Comparer le contenu de `references/` avec les fiches existantes.

### Procédure manuelle
```bash
# Lister les dépôts dans references/
ls -d references/*/ | sed 's|references/||'

# Lister les fiches déjà créées
ls docs/references-audit/projects/*.md | sed 's|.*/||;s|\.md||'

# Croiser : un dépôt sans fiche NN-<nom>.md est à traiter
```

### Script de détection automatique (à exécuter)
```bash
# Affiche les dépôts de references/ qui n'ont pas encore de fiche d'audit
python -c "
import os, re
deps = sorted(d for d in os.listdir('references') if os.path.isdir(f'references/{d}'))
# Normalise les noms de fiches vers un slug comparable (minuscules, sans casse)
fiches = set()
for f in os.listdir('docs/references-audit/projects'):
    name = re.sub(r'^\d+-', '', f.replace('.md','')).lower()
    fiches.add(name)
for d in deps:
    # heuristique : comparaison insensible à la casse (LlamaBot <-> llamabot)
    dl = d.lower()
    matched = any(dl in f or f in dl for f in fiches)
    if not matched:
        print(f'AUDITER: {d}')
"
```

### État courant (2026-08-01)
- **Dépôts dans `references/`** : 22
- **Fiches d'audit existantes** : 18 (`docs/references-audit/projects/01-*.md` à `18-*.md`)
- **À traiter (5 nouveaux)** : `code-review-graph`, `davidondrej-skills`, `llm-council`, `loopx`, `mattpocock-skills`

---

## 🔍 Étape 1 — Cartographie rapide du dépôt

**Objectif** : comprendre en 2 minutes la nature, la taille, le langage, la stack du dépôt.

### À exécuter
```bash
D="references/<nom-du-dépôt>"
echo "=== total fichiers (hors .git/node_modules) ==="
find "$D" -type f ! -path "*/.git/*" ! -path "*/node_modules/*" | wc -l
echo "=== extensions top 10 ==="
find "$D" -type f ! -path "*/.git/*" ! -path "*/node_modules/*" | sed 's/.*\.//' | sort | uniq -c | sort -rn | head -10
echo "=== top-level listing ==="
ls "$D" | head -30
echo "=== README head ==="
head -10 "$D/README.md" 2>/dev/null
```

### Décisions à prendre à ce stade
- **Langage dominant** : Python (🟢 portabilité directe) / TypeScript (🟡 portage algorithmique) / autre (🔴 probablement hors-scope).
- **Type de dépôt** : agent de coding / framework d'orchestration / collection de prompts / collection de skills / recherche académique / produit commercial.
- **Taille** : petit (<100 fichiers, fiche courte possible) / gros (>1000 fichiers, déléguer l'exploration profonde à un subagent).

---

## 🤖 Étape 2 — Audit profond (déléguer si dépôt >200 fichiers)

**Objectif** : extraire les briques réutilisables pour `graph-orchestrator-smolagents`, avec chemins réels + symboles + mapping vers les priorités du plan.

### Si petit dépôt (<200 fichiers)
Lire directement : `README.md`, les fichiers de code principaux, les `SKILL.md`/`AGENTS.md`/`CLAUDE.md`.

### Si gros dépôt (>200 fichiers)
Déléguer à un subagent (Agent tool, `subagent_type: Explore`) avec un prompt structuré contenant :
- Le contexte du projet cible (orchestrateur multi-agent Python DSPy/smolagents, persistance DuckDB).
- Les priorités du plan (P0 spécialisation, P3 anti-loop, P6 Judge/findings, P8 middlewares, P9 compaction, P10 skills, P11 event stream).
- La demande explicite : cartographie + classification 🟢/🟡/🔴 + top 5-8 briques (chemin + symboles + valeur + mapping priorité) + points faibles + note globale argumentée.

### Grille de classification par pertinence
- 🟢 **Haute** : code/pattern directement exploitable (Python portable, ou algorithme transposable).
- 🟡 **Moyenne** : pattern intéressant mais adaptation non-triviale (autre langage, alignement partiel).
- 🔴 **Faible** : non portable (autre écosystème, hors-scope coding).
- ⚫ **Configs/assets** : JSON/YAML/media — à distinguer, rarement de la matière prompt/code.

### Livrable attendu de l'audit
Une matière exploitable pour écrire une fiche au format des 18 existantes, comprenant :
1. Nature (1 phrase), langage/stack, statistiques.
2. Synthèse (à quoi ça sert + valeur perçue + note globale argumentée + réserves éventuelles).
3. Top 5-8 briques réutilisables (chemin réel vérifié + symboles clés lus dans le code + description + 🟢/🟡/🔴 + justification par rapport au projet cible).
4. Points faibles / hors-scope à ignorer.
5. Mapping explicite vers les priorités du plan (P0-P11).
6. Note globale 🟢/🟡/🔴 + recommandation (fiche dédiée ? fusion ? court ?).

---

## ✍️ Étape 3 — Rédiger la fiche d'audit

**Objectif** : créer `docs/references-audit/projects/NN-<nom>.md` au format strict des fiches existantes.

### Format canonique (voir `02-aider.md` comme modèle de référence)
```markdown
# NN — <nom-du-dépôt>

## En-tête
- **Nom** : ...
- **Chemin** : `references/<nom>/`
- **Type** : ...
- **Langage principal** : ...
- **Statistiques** : ... fichiers, ... `.py`/`.ts`, etc.

## Synthèse
(3-5 paragraphes : à quoi ça sert, valeur pour le projet cible, note globale argumentée,
réserves éventuelles — biais stack, licence, padding, anti-patterns)

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
(relative à la racine du repo : `references/<nom>/...`)

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
(chemins TOUJOURS relatifs à la racine, cliquables depuis un IDE)

## Contrats / Specs / Config
| Chemin | Type | Description |
(optionnel, si schémas/specs pertinents)

## Exclusions conscientes
- (ce qui a été ignoré et pourquoi — UI, configs, écosystème spécifique, etc.)

## Correspondance avec `plan_usine_logicielle.md`
- **P<n>** : (mapping explicite vers chaque priorité concernée)
```

### Règles de rédaction
- **Chemins toujours relatifs à la racine du repo** (`references/<nom>/...`), cliquables.
- **Symboles clés lus dans le code** (ne pas inventer — vérifier par grep/read).
- **Note globale alignée avec la matrice** (🟢 Haute / 🟡 Moyenne / 🔴 Faible).
- **Soigner les exclusions** : elles évitent à un futur lecteur de perdre du temps sur le bruit.
- **Citer les réserves** : biais stack, licences (prompts leakés → préférer open-source pour citation verbatim), anti-patterns.

---

## 📊 Étape 4 — Mettre à jour l'inventaire machine

**Objectif** : enrichir `docs/references-audit/inventory.json` + le script `update_inventory.py`.

### Modifier `update_inventory.py` (à la racine du repo)
1. Ajouter un bloc `<INITIALES>_FILES = [...]` avec une entrée par brique réutilisable (chemin, type, reuse, key_symbols, description).
2. Ajouter une branche `elif pid == "<nom>":` dans `main()` avec l'objet projet (id, name, path, category, reuse_rating, summary, files).
3. Ajouter un repli de sécurité `if "<nom>" not in seen_ids:` à la fin de `main()`.
4. Incrémenter `data["projects_audited"]` (et `audit_date` si besoin).

### Format d'une entrée d'inventaire
```python
{"path": "references/<nom>/<chemin>", "type": "code|doc|prompt|skill|spec|test",
 "reuse": "high|medium|low",
 "key_symbols": ["symbole1", "symbole2"],
 "description": "Description concise avec mécanisme + valeur pour le projet cible."},
```

### Exécuter et valider
```bash
python update_inventory.py
# Vérifier : tous les chemins existent sur disque
python -c "
import json, os
inv = json.load(open('docs/references-audit/inventory.json', encoding='utf-8'))
p = next(p for p in inv['projects'] if p['id']=='<nom>')
missing = [f['path'] for f in p['files'] if not os.path.exists(f['path'])]
print('manquants:', missing if missing else 'AUCUN')
print('total projets:', inv['projects_audited'])
print('total entrées:', sum(len(p['files']) for p in inv['projects']))
"
```
**Règle absolue** : aucun chemin manquant. Si un chemin est invalide, le corriger dans `update_inventory.py` et re-exécuter.

---

## 🧭 Étape 5 — Mettre à jour INDEX.md et README.md

**Objectif** : garder cohérents les compteurs, la table de navigation, la matrice, le Hall of Fame, le guide de recherche.

### Dans `docs/references-audit/INDEX.md`
1. **Vue d'ensemble** : incrémenter « Projets/dossiers audités » et « Entrées de fichiers inventoriées ».
2. **Titre de navigation** : `## 🧭 Navigation — les N fiches`.
3. **Tableau de navigation** : ajouter une ligne `| NN | **<nom>** | 🟢/🟡/🔴 | [NN-<nom>](./projects/NN-<nom>.md) | résumé 1 ligne |`.
4. **Synthèse thématique** (3 familles) : ajouter le dépôt dans la famille pertinente.
5. **Matrice réutilisabilité croisée** : ajouter ligne + recalculer le total (récupérer les comptes via le script de validation de l'étape 4).
6. **Constats** (sous la matrice) : ajouter une ligne si le dépôt apporte une valeur notable.
7. **Hall of Fame** : ajouter une nouvelle section `### <thème> (<nom>)` si le dépôt apporte des briques dignes du top, avec un tableau `Fichier | Symbole(s) clé(s) | Apport`.
8. **Guide de recherche** : ajouter des lignes `| Je cherche… | Fiche NN → chemin |` pour les besoins couverts par ce dépôt.
9. **Arbre du dossier** : mettre à jour le compteur de fiches + la liste.

### Dans `docs/references-audit/README.md`
1. « N projets » dans le préambule.
2. « la liste des N projets » + « (N fiches) » + « (N entrées) » dans la table de navigation.
3. Arbre : compteur de projets/entrées + dernière fiche.

### Vérification de cohérence (critique)
```bash
# Tous les compteurs doivent être alignés
python -c "
import json
inv = json.load(open('docs/references-audit/inventory.json', encoding='utf-8'))
total = sum(len(p['files']) for p in inv['projects'])
n = inv['projects_audited']
print(f'inventory: {n} projets, {total} entrées')
assert total == <attendu> and n == <attendu>
"
grep -c "N fiches" docs/references-audit/INDEX.md      # doit matcher
grep -c "<total>" docs/references-audit/INDEX.md       # doit matcher
grep -c "N projets" docs/references-audit/README.md    # doit matcher
# Aucun résidu de l'ancien compteur
grep -c "N-1 fiches" docs/references-audit/INDEX.md    # doit être 0
```

---

## 🎯 Étape 6 — Intégrer au plan (`plan_usine_logicielle.md`)

**Objectif** : pour chaque priorité du plan où le dépôt apporte un blueprint/pattern concret, ajouter une référence à la fiche.

### Méthode (édition ciblée par priorité)
Pour chaque priorité concernée par le dépôt (P0, P3, P6, P8, P9, P10, P11…), enrichir la ligne `- [ ]` existante en ajoutant un bloc :
```
— *Référence : fiche **NN-<nom>** → `references/<nom>/<chemin>` (`symbole`, mécanisme, valeur pour ce besoin).*
```

### Règles
- **Une référence = un chemin concret + des symboles + une justification**. Pas de vague « inspiré de ».
- **Cumul avec les références existantes** : si une priorité a déjà des refs (ex: P9 cite qm + learn-claude-code), on ajoute la nouvelle en complément, pas en remplacement.
- **Décision KG structural** : si une référence touche P4 (repo map / KG structural), rappeler que P4 est HORS-SCOPE (sauf palliatif tags de confiance) — ne pas rouvrir le débat.
- **Numérotation** : pour une nouvelle priorité, éviter de tout renuméroter. Utiliser `P<n>-bis` (ex: P8-bis) ou une sous-section (ex: `### P0-bis : Invariants universels`).

### Mise à jour du tableau d'en-tête
Le tableau « ÉTAT D'AVANCEMENT » en haut du plan doit refléter toute nouvelle priorité ou changement de statut.

---

## 📝 Étape 7 — Journaliser dans `log.md`

**Objectif** : tracer l'opération dans le journal append-only du projet.

### Format d'entrée (append à la fin de `log.md`)
```markdown
## [AAAA-MM-JJ] rch  | Ajout référence <nom> (fiche NN) + intégration au plan
*Nouvelle référence : <nature en 1 phrase>.*
- **Découverte clé** : <le point le plus important>.
- **Fiche NN créée** (~N lignes, note 🟢/🟡/🔴, N entrées, chemins vérifiés).
- **inventory.json** : <ancien> → <nouveau> entrées. INDEX.md/README.md rafraîchis (...). update_inventory.py étendu.
- **plan_usine_logicielle.md enrichi** (N références) : <liste des priorités touchées avec la matière apportée>.
- **Réserves signalées** : <biais, licences, anti-patterns>.
- **Aucune modification du code du projet** — travail documentaire + plan.
```

---

## 🚀 Étape 8 — Commit et push

**Objectif** : versionner le travail documentaire sur `main`.

### Procédure (attention à la branche courante)
```bash
# 1. Vérifier la branche courante
git branch --show-current

# 2. Si sur main : commit direct
#    Si sur une branche feature : stash, checkout main, pull, cherry-pick, push, restaurer
git status --short

# ⚠️ ATTENTION : le .gitignore ignore tout references/ (sous-modules externes).
# Tout fichier créé dans references/ (ex: cette procédure) nécessite git add -f.
git add docs/references-audit/projects/NN-<nom>.md \
        docs/references-audit/INDEX.md \
        docs/references-audit/README.md \
        docs/references-audit/inventory.json \
        update_inventory.py \
        plan_usine_logicielle.md \
        log.md
git commit -m "docs: ajout référence <nom> (fiche NN) + intégration au plan

<nom> = <nature>. <point clé>.
<résumé des intégrations au plan>."

git push origin main
```

### Cas spécial : branche feature active
Si la branche courante n'est pas `main` (une autre session a créé une branche feature), faire un **cherry-pick** pour ne pas polluer la branche feature :
```bash
# 1. Commit sur la branche courante (stage sélectivement uniquement les fichiers doc)
git commit -m "docs: ajout référence <nom> (fiche NN) + intégration au plan"
SHA=$(git rev-parse HEAD)

# 2. Stasher le WIP de la branche feature, basculer sur main
git stash push -u -m "feature-WIP"
git checkout main
git pull --ff-only origin main

# 3. Cherry-pick le commit doc sur main
git cherry-pick $SHA
# (résoudre les conflits sur log.md en append-only : garder le contenu des deux)

# 4. Push
git push origin main

# 5. Restaurer la branche feature
git checkout <branche-feature>
git stash pop
```

---

## 🔄 Étape 9 — Vérification finale

**Checklist de cohérence avant de déclarer terminé** :
- [ ] `inventory.json` valide (JSON parsable) et `projects_audited` cohérent.
- [ ] Tous les chemins de la nouvelle fiche existent sur disque.
- [ ] Tous les chemins de l'inventaire (nouveau projet) existent sur disque.
- [ ] INDEX.md : « N fiches » partout, aucun résidu « N-1 fiches ».
- [ ] INDEX.md : matrice avec ligne du nouveau projet + total recalculé.
- [ ] README.md : « N projets » et « N entrées » partout.
- [ ] `plan_usine_logicielle.md` : références à la nouvelle fiche dans les priorités pertinentes.
- [ ] `log.md` : entrée append-only ajoutée à la fin.
- [ ] Commit poussé sur `main` (vérifier `git log origin/main`).
- [ ] `update_inventory.py` est **idempotent** (re-exécuter = même résultat, pas de doublon).

---

## 📎 Annexes

### A. Numérotation des fiches
Les fiches sont numérotées séquentiellement (`01-`, `02-`, … `18-`, `19-`…). Le nom après le numéro est le nom du dépôt tel quel (sans préfixe). En cas d'alias (ex: `claude-code-unified-agents`), garder le nom du dossier `references/`.

### B. Décisions de fusion (anti-redondance)
Quand plusieurs dépôts couvrent le même sujet (ex: 3× doctrine skill-authoring), **fusionner** plutôt que dupliquer :
- Une seule fiche « doctrine » prenant le meilleur de chaque source.
- Les sources secondaires citées dans la fiche principale, pas de fiches séparées.
- Cas déjà identifié : `awesome-claude-skills/skill-creator` + `mattpocock/writing-great-skills` + `davidondrej/effective-agent-skills` → une seule fiche doctrine enrichie.

### C. Priorités du plan et leurs références actuelles (2026-08-01)
| Priorité | Statut | Références |
|---|---|---|
| P0 Cadre système & spécialisation | Partiel | claude-code (15), learn-claude-code s06 (16), system-prompts (17) |
| P0-bis Invariants universels | À faire | system-prompts (17) — 10 invariants |
| P1 Édition sécurisée | ✅ Terminé | aider (02) |
| P3 Anti-loop | Partiel | crush (10) — manque matière déterministe |
| P4 Repo Map + KG structural | ⏸️ HORS-SCOPE | graphify (06) palliatif tags confiance |
| P6 Judge / Findings / TDD | À faire | open-swe (09), llamabot (07), claude-code (15), system-prompts (17) |
| P8 Middlewares anti-crash | À faire | deer-flow (13), learn-claude-code s04/s11 (16) |
| P8-bis Sandbox + Idempotence | À faire | qm (14) — sandbox + idempotence |
| P9 Reducers / Compaction | À faire | deer-flow (13), qm (14), learn-claude-code s08 (16) |
| P10 Skill loading | À faire | learn-claude-code s07 (16), awesome-claude-skills (18) |
| P11 Event stream | À faire | deer-flow (13), learn-claude-code s04 (16) |
| P12 Scopes multi-utilisateurs | À faire | qm (14) |

### D. Références par priorité ciblée (mapping inverse)
| Priorité | Références à privilégier |
|---|---|
| P3 anti-loop | **loopx (à créer)** quota/stall_repair + crush (10) |
| P6 Judge | open-swe findings (09) + **llm-council (à créer)** council anonymisé + system-prompts (17) professional objectivity + **code-review-graph (à créer)** risk score |
| P8 middlewares | learn-claude-code s04 hooks (16) + **davidondrej hooks/ (à créer)** denylist 52 regex + qm (14) idempotence |
| P8-bis sandbox | qm docker-exec (14) + aider subprocess (02) |
| P9 compaction | qm context-compaction (14) + learn-claude-code s08 (16) + **loopx (à créer)** run_compaction |
| P10 skills | awesome-claude-skills (18) + **mattpocock (à créer)** doctrine authoring + learn-claude-code s07 (16) |
| P11 event stream | deer-flow contract (08/13) + learn-claude-code s04 (16) + **loopx (à créer)** event_ledger 5 classes |

### E. Commandes utiles
```bash
# Compter les entrées par projet
python -c "
import json
inv = json.load(open('docs/references-audit/inventory.json', encoding='utf-8'))
for p in inv['projects']:
    counts = {}
    for f in p['files']:
        counts[f.get('reuse','?')] = counts.get(f.get('reuse','?'),0)+1
    print(f\"{p['id']:<32} H={counts.get('high',0):>2} M={counts.get('medium',0):>2} L={counts.get('low',0):>2} ({len(p['files'])} total, {p['reuse_rating']})\")
"

# Lister toutes les références citées dans le plan
grep -oE "fiche \*\*[0-9]+-[a-z-]+\*\*" plan_usine_logicielle.md | sort -u
```
