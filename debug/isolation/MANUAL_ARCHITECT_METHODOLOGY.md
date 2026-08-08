# Méthodologie d'architecture manuelle (= spec de l'Architect idéal)

Ce document décrit **exactement** ce que je fais (l'agent) quand je joue le nœud Architect à
la main, étape par étape. C'est le cahier des charges de l'Architect idéal.

## Rôle du nœud Architect

**Entrée** : le cahier des charges (une `str`, ex: « Crée un visualiseur Bubble Sort… »).

**Sortie** : `ArchitectOutput(plan_id, global_architecture, subtasks[])` où chaque sous-tâche
est un `ArchitectTask(task_id, description, target_files, strategy, sections)`.

L'Architect est le **seul nœud DSPy qui conserve le thinking** (F-47, `think=True`) — le
raisononnement aide au découpage et au choix de stratégie. Il ne produit pas de code, il
**dicte au Coder COMMENT construire**, pas juste QUOI (F-29 techno-driven).

## Les 3 stratégies de construction (F-29, decision techno-driven)

| Stratégie | Quand | Comment le Coder construit |
|---|---|---|
| **simple** | Petit fichier unique (≤ ~200 lignes), un concept | 1 `write_file` (one-shot) |
| **incremental** | Gros fichier **monolithique imposé** (HTML/CSS/JS single-file 3000+ lignes) | `write_file` squelette + N `append_file` sections |
| **multifile** | Plusieurs modules logiques (Python/TS, 1 module = 1 fichier < ~200 lignes) | 1 `write_file` par fichier, sous-tâche = 1 fichier |

**Règle de décision techno-driven** : HTML/CSS/JS vanilla = souvent **simple** ou
**incremental** (le navigateur veut un seul fichier) ; Python/TS = souvent **multifile**
(modularité naturelle). La stratégie est dictée par la **techno**, pas par préférence.

## Les étapes (dans l'ordre)

### Étape 1 — Identifier les livrables testables (1 LIVRABLE TESTABLE = 1 sous-tâche)
**Ce que je fais** : je `Read` le cahier des charges et j'identifie les **livrables
testables**. La règle F-15 (version production, `ArchitectSignature` docstring) est :
**1 livrable testable = 1 sous-tâche, 2-4 max** — et un livrable peut contenir PLUSIEURS
fichiers liés que le Tester valide ENSEMBLE.
**⚠️ CORRECTION IMPORTANTE** : la première version de cette doc disait « 1 fichier = 1
sous-tâche ». C'est FAUX et c'est le **failure mode n°1** selon le prompt de production :
si on découpe un livrable par fichier (ex: index.html / styles.css / script.js en 3
sous-tâches séparées), le Tester valide des fichiers ISOLÉS qui ne marchent pas seuls
(index.html sans styles.css → rejeté systématique → boucle infinie). **Il faut regrouper
les fichiers liés dans UNE sous-tâche multifile** pour que le Tester valide l'ensemble rendu.
**Outil** : lecture du prompt / de la spec
**Coût** : 0 LLM, 1 tour de réflexion
**Cas typiques** (alignés sur le prompt prod) :
- 1 fichier unique (Bubble Sort dans index.html) → 1 sous-tâche, `target_files=[index.html]`.
- Site HTML+CSS+JS liés (landing_page/) → **1 sous-tâche multifile**, `target_files=[index.html,
  styles.css, script.js]` (le Coder crée les 3, le Tester valide l'ensemble rendu).
- App Python 3 modules indépendants → 1 sous-tâche multifile SI testés ensemble, OU plusieurs
  sous-tâches UNIQUEMENT si chaque module est réellement testable isolément (rare).

### Étape 2 — Choisir la stratégie par sous-tâche (techno-driven)
**Ce que je fais** : pour chaque sous-tâche (livrable), je détermine la stratégie selon sa
techno et sa taille estimée.
**Outil** : tableau de décision ci-dessus + mon jugement sur la taille
**Tableau de décision** :
| Cas | Stratégie |
|---|---|
| `index.html` seul, bubble sort (~300 lignes attendues) | `simple` |
| `index.html` seul, dashboard admin (~3000 lignes) | `incremental` (sections: html_structure, css_styles, js_logic) |
| `index.html` + `styles.css` + `script.js` liés (landing page) | `multifile` (1 sous-tâche, les 3 fichiers) |
| `app.py` + `utils.py` + `models.py` liés (Python, testés ensemble) | `multifile` (1 sous-tâche) |
| `server.ts` + `routes.ts` (TypeScript, liés) | `multifile` |
**Échec type évité** : un dashboard 3000 lignes en stratégie `simple` → le Coder (gemma 4B)
s'essouffle, JSON corrompu, fichier tronqué (vécu run CodeAgent incrémental : TCA 1h sans
step 1 fini). La stratégie `incremental` + sections est le contre-mesure.

### Étape 3 — Définir les `sections` (uniquement pour `incremental`)
**Ce que je fais** : si la stratégie est `incremental`, je découpe le fichier en **sections
logiques** que le Coder écrira une par une via `append_file`. Les noms de sections doivent
être des **noms parlants** que le Coder comprend (pas des numéros).
**Outil** : mon jugement structurel
**Exemple** (dashboard admin HTML) : `sections: ['html_structure', 'header_nav',
'sidebar', 'data_table', 'forms', 'css_theme', 'js_interactions']`
**Règle** : 3-7 sections typiquement. Chaque section = un `append_file` de ~50-100 lignes
(gérable pour le 4B). La première section DOIT être le squelette HTML (`<!DOCTYPE>`…
`</body></html>`) — c'est le socle sur lequel les autres s'appendent.

### Étape 4 — Rédiger la `description` de chaque sous-tâche (actionnable)
**Ce que je fais** : pour chaque sous-tâche, j'écris une description qui dit au Coder **quoi
construire** (pas comment — la stratégie dit comment). La description doit être **spécifique
et bornée** : fonctionnalités précises, contraintes (dark mode, responsive), pas de vague.
**Outil** : rédaction
**Bon exemple** : « Créer la structure HTML + CSS dans index.html : conteneur pour les
barres, zone de contrôle (boutons Start/Reset, slider vitesse), compteur de comparaisons.
Thème sombre moderne responsive. »
**Mauvais exemple** : « Fais le HTML » (trop vague, le Coder improvise).

### Étape 5 — Assembler le plan (global_architecture + subtasks)
**Ce que je fais** : je produis le `ArchitectOutput` final : un `plan_id` court, un
`global_architecture` (1-2 phrases qui résument la vision d'ensemble), et la liste des
sous-tâches (chacune avec task_id unique, description, target_files, strategy, sections).
**Vérif** : `len(subtasks)` entre 2 et 4 ; chaque `target_files` non vide ; `strategy` dans
{simple, incremental, multifile} ; `sections` non vide seulement si strategy=incremental.

## Ordre optimal

```
1. Livrables testables (1 livrable = 1 sous-tâche, 2-4 max)  ──▶ liste des target_files
   │
   ▼
2. Stratégie par sous-tâche (techno + taille)     ──▶ simple | incremental | multifile
   │ si incremental
   ▼
3. Sections logiques (3-7, noms parlants)         ──▶ sections[]
   │
   ▼
4. Description actionnable par sous-tâche         ──▶ description
   │
   ▼
5. Assemblage ArchitectOutput                     ──▶ plan_id + global_architecture + subtasks
```

## ⚠️ BIAIS — Les pièges de l'Architect (vécus)

**Biais n°1 — Découper un livrable par fichier (LE failure mode n°1)**. La tentation est de
faire 1 sous-tâche par fichier (ex: index.html / styles.css / script.js en 3 sous-tâches
séparées). C'est CATASTROPHIQUE : le Tester valide des fichiers ISOLÉS qui ne marchent pas
seuls (index.html sans styles.css → rejeté systématique → boucle infinie Coder↔Tester).
Contre-mesure : **1 livrable testable = 1 sous-tâche**, en regroupant les fichiers liés dans
une sous-tâche `multifile` pour que le Tester valide l'ensemble rendu. Ne découper en
plusieurs sous-tâches QUE si chaque fichier est réellement testable isolément (rare).

**Biais n°1-bis — Sur-découpage par dimension**. Avant F-15, l'Architect produisait 5
sous-tâches pour 3 fichiers (ex: 1 pour la structure, 1 pour le style, 1 pour le JS du MÊME
fichier). Ça multipliait les appels LLM et les sources de corruption. Contre-mesure : vise
le MINIMUM de sous-tâches. Si un fichier est gros, on joue la stratégie `incremental`
(sections), pas la multiplication de sous-tâches.

**Biais n°2 — Stratégie par défaut vers `simple`**. Sur un gros fichier, `simple` condamne
le Coder (gemma 4B) à l'échec (fichier tronqué, JSON corrompu). Contre-mesure : si le
fichier attendu dépasse ~500 lignes, **forcer `incremental`** avec sections, même si le
prompt ne le demande pas. C'est le pattern n°1 recommandé par les audits pour les petits
modèles : accumulateur incrémental.

**Biais n°3 — Confondre `multifile` et `incremental`**. `multifile` = plusieurs FICHIERS
séparés (Python/TS modulaire). `incremental` = UN gros fichier construit par morceaux
(HTML monolithique). Ne pas mettre `incremental` sur un projet Python (le Coder écrirait un
seul gros .py au lieu de le modulariser).

**Biais n°4 — Ignorer la propagation**. La stratégie choisie ici DOIT être propagée au
Coder via `subtask.strategy` + `subtask.sections`. Si l'Architect choisit `incremental` mais
que le Coder ne reçoit pas les sections, il fait du `simple` (et échoue). Toujours vérifier
que `sections` est non vide quand `strategy=incremental`.

## Pourquoi cette méthode plutôt que le LLM Architect (gemma-12B)

| Critère | Architect LLM (12B, think=True) | Méthode manuelle |
|---|---|---|
| Temps | ~1-3 min (thinking) | ~30s (réflexion structurée) |
| Fiabilité règles F-15/F-29 | Variable (peut sur-découper) | **Binaire** (1 livrable testable = 1 sous-tâche) |
| Choix stratégie | Bon (reasoning) | Déterministe (techno-driven) |
| Sections incremental | Parfois oubliées | **Toujours fournies** |

**Conclusion** : le découpage (F-15) et le choix de stratégie (F-29 techno-driven) sont
**largement déterministes** — le tableau de décision ci-dessus couvre 90% des cas. Le LLM
12B avec thinking apporte surtout de la valeur sur les cahiers des charges **complexes /
mal structurés** où la détection des livrables demande de l'interprétation.
