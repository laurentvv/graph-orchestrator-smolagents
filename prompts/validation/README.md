# Prompts de validation (`prompts/validation/`)

Instantané **versionné** des prompts utilisés pour valider le graphe. Ces fichiers
vivent **à côté du code** (commités) pour ne pas être perdus — contrairement à la
banque externe `references/Prompt-Vault/` qui est **gitignorée** (disparaît au fresh
clone) et à `tasks.json` qui ne contient qu'un seul prompt actif à la fois.

## Convention

Chaque prompt est un fichier `.md` avec un frontmatter YAML + le corps du prompt :

```yaml
---
id: <identifiant-stable>           # devient tasks.json coding[0].id
title: <titre court lisible>
purpose: <pourquoi ce prompt / ce qu'il valide>
target_files:                       # fichiers attendus en sortie (liste)
  - index.html
  - script.js
expected_skill_finder: <none | "search X → install skill Y">   # témoin F-82
note_validation: <comment observer la réussite>                # optionnel
---

<corps du prompt — ce que reçoit le graphe>
```

Le **corps** (après le frontmatter) est injecté tel quel dans `tasks.json` (`coding[0].content`).
Le `target_files` devient `tasks.json` (`coding[0].target_files`).

## Charger un prompt dans `tasks.json`

`scripts/load_prompt.py` automatise l'étape 1 du workflow (AGENTS.md §7.1) :

```bash
# Prompt canonique (vanilla, E2E complet) :
uv run python scripts/load_prompt.py prompts/validation/bubble_sort.md

# Forceur F-82 (validation du Skill Finder) :
uv run python scripts/load_prompt.py prompts/validation/skill_finder_ai_sdk.md
uv run python scripts/load_prompt.py prompts/validation/skill_finder_react.md
```

Options : `--mode one_shot` (défaut `coding`), `--tasks tasks.json`. Le loader
remplace la 1ʳᵉ entrée du mode choisi (préserve les autres modes) et affiche un résumé.

## Catalogue

| Fichier | Type | Valide quoi |
|---|---|---|
| `bubble_sort.md` | Vanilla, multi-fichier | Coding workflow E2E (golden run §10). Témoin **négatif** F-82 : le ReAct doit répondre « Aucun skill ajouté ». |
| `skill_finder_ai_sdk.md` | React + Vercel AI SDK | **F-82** : gap garanti (`ai-sdk` absent des regex locales) + domaine vercel-labs. Le ReAct doit chercher + installer. |
| `skill_finder_react.md` | React landing « production » | **F-82** (variante sûre) : skill React best-practices vercel-labs = exemple canonique skills.sh. |

## Valider F-82 (Skill Finder)

Le ReAct F-82 tourne dans l'**Architect** (avant le plan). Pour valider en **minutes**
(pas en E2E 30 min), utiliser le script d'isolation de l'Architect avec le prompt
forçant :

```bash
uv run python debug/run_architect.py "$(cat prompts/validation/skill_finder_ai_sdk.md | sed -n '/^---$/,/^---$/!p')"
# ou simplement coller le corps du prompt en argument
```

**Critères de réussite** ( observables ) :
1. Log : `[*] Architect : Vérification des besoins en skills dynamiques (ReAct)...`
   puis `[+] Architect : Résultat de la recherche de skills : Skill installé : <name>`.
2. `skills/<name>/SKILL.md` présent sur disque.
3. `skills/installed-skills.json` contient une entrée avec sa `regex` dédiée.
4. `select_skills_for_coder(<prompt>)` (same-run via `refresh_dynamic_rules_in_memory`,
   ou au prochain run via le manifeste) inclut le skill.

Témoin négatif (`bubble_sort.md`) : le ReAct doit répondre « Aucun skill ajouté » et
`skills/installed-skills.json` ne doit **pas** gagner d'entrée fantôme.

## Relation avec `references/Prompt-Vault/`

Le **Prompt-Vault** (Easy/Medium/Hard/Advanced) reste la **banque externe de référence** :
riche et classée par difficulté, mais **gitignorée** (non versionnée). Le présent
dossier `prompts/validation/` est l'**instantané minimal et versionné** des prompts que
le projet utilise réellement pour valider. Pour ajouter un prompt du Vault ici : copier
son contenu dans un nouveau `.md` avec le frontmatter ci-dessus, puis le committer.
