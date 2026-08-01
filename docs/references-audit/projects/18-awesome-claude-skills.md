# 18 — awesome-claude-skills

## En-tête
- **Nom** : awesome-claude-skills (ComposioHQ)
- **Chemin** : `references/awesome-claude-skills/`
- **Type** : Marketplace officielle Claude de skills (plugin distribué via Claude Code marketplace, `marketplace.json` v2.0.0).
- **Langage principal** : Markdown (SKILL.md) + Python (scripts de skills) + XSD (schémas OOXML de `document-skills`).
- **Statistiques** : 30 skills top-level + un sous-dossier `composio-skills/` de **832 wrappers SaaS** (Rube/Composio). 1 142 fichiers au total dont 892 `.md`, 78 `.xsd`, 62 `.py`, 54 `.ttf` (polices de `canvas-design`/`slack-gif-creator`). Sur les 30 skills top-level, **seulement 5 sont pertinentes** pour un orchestrateur de coding ; les 25 autres sont business/marketing/productivité perso.

## Synthèse
La valeur de ce dépôt n'est **pas le contenu métier** (majoritairement business/marketing/SaaS) mais le **patrimoine méthodologique** : il formalise exactement ce que notre **Priorité 10 (Skill loading)** veut construire. Trois apports distincts :

1. **Le format SKILL.md canonique + le modèle 3-niveaux** (« Progressive Disclosure ») — défini dans `skill-creator/SKILL.md`. C'est la **caution externe** du modèle lazy loading de P10 : (1) Metadata ~100 mots toujours en contexte, (2) corps SKILL.md <5k mots chargé au déclenchement, (3) ressources bundled illimitées car les scripts s'exécutent sans être lus dans le contexte.
2. **L'outillage méta** (`init_skill.py` scaffolding + `quick_validate.py` CI gate) — réutilisable tel quel pour normaliser la création/validation de nos skills.
3. **`mcp-builder`** — manuel de référence pour construire des serveurs MCP, avec des principes de design d'outils transposables à nos « Hands » smolagents.

**Gap identifié vs notre `skills_loader.py` actuel** : nos skills sont **mono-fichiers** (tout inline dans SKILL.md, `build_skills_block` injecte tous les bodies dans le prompt). Le format canonique utilise `SKILL.md` + `scripts/` + `references/` + `assets/` — c'est précisément le changement structurel que P10 implique (lazy loading + découplage instructions/scripts).

**Note de réutilisabilité globale : Moyenne** (🟡 sur l'ensemble car 25/30 skills sont hors-scope, mais 🟢 forte sur le pivot méthodologique).

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/awesome-claude-skills/skill-creator/SKILL.md` | Méta-skill : créer/éditer/valider/packager des skills. Définit l'anatomie d'une skill + le modèle 3-niveaux (Progressive Disclosure). **La première source à citer dans P10.** | Haute |
| `references/awesome-claude-skills/mcp-builder/SKILL.md` | Guide 4 phases (Research→Implementation→Review→Evaluation) pour bâtir des serveurs MCP. Principes de design d'outils pour agents | Haute |
| `references/awesome-claude-skills/mcp-builder/reference/mcp_best_practices.md` | Bonnes pratiques MCP (« Build for Workflows », « Optimize for Limited Context », « Actionable Error Messages ») | Haute |
| `references/awesome-claude-skills/mcp-builder/reference/python_mcp_server.md` | Implémentation FastMCP Python (modèle pour exposer nos tools) | Moyenne |
| `references/awesome-claude-skills/mcp-builder/reference/evaluation.md` | Pattern « créer 10 questions d'évaluation XML + vérifier » — transposable au nœud Judge | Moyenne |
| `references/awesome-claude-skills/CONTRIBUTING.md` | Comment contribuer une skill (format, conventions) | Faible |

## Code réutilisable
> Ici le « code » = les **scripts d'outillage des skills** (déterministes, exécutables sans LLM). Les 62 `.py` du dépôt se répartissent : ~30 dans `document-skills` (OOXML), ~13 dans `slack-gif-creator` (hors-scope), 3 dans `skill-creator`, 2 dans `mcp-builder`, 4 dans `webapp-testing`.

| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/awesome-claude-skills/skill-creator/scripts/init_skill.py` | `init_skill`, scaffolding `SKILL.md` + 3 dossiers | Génère le squelette canonique d'une skill (SKILL.md + `scripts/` + `references/` + `assets/`). Réutilisable en l'état comme `scripts/new_skill.py` | **Haute** | Normalise la création de nos skills selon le format canonique. À adapter dans notre pipeline |
| `references/awesome-claude-skills/skill-creator/scripts/quick_validate.py` | `validate_frontmatter`, regex `^[a-z0-9-]+$`, check chevrons `<>` | Valide : `name` en hyphen-case strict, pas de `--`, pas de chevrons dans `description`, description explicite. ~64 lignes | **Haute** | **À adopter comme gate CI/pre-commit** sur notre dossier `skills/` pour garantir la conformité avec `skills_loader.py`. Évite les skills malformées qui cassent le parsing |
| `references/awesome-claude-skills/skill-creator/scripts/package_skill.py` | `package_skill`, zip bundling | Packaging zip d'une skill pour distribution | Moyenne | Mécanisme utile à comprendre ; moins pertinent pour nous (pas de distribution marketplace) |
| `references/awesome-claude-skills/webapp-testing/scripts/with_server.py` | gestion cycle de vie serveur, `wait_for_port`, multi-serveur | Démarre/arrête un serveur local proprement pendant les tests Playwright, attend que le port soit prêt | Moyenne | Complément Playwright-native à notre `web_tester` (qui utilise Puppeteer MCP). Pattern « reconnaissance-then-action » (screenshot → sélecteurs → agir) |
| `references/awesome-claude-skills/document-skills/docx/ooxml/scripts/pack.py` + `unpack.py` + `validate.py` | manipulation zip OOXML, validation XML par format | Manipulation OOXML complète (pack/unpack zip, redlining/tracked-changes, validation). ~30 des 62 `.py` du dépôt sont ici | Moyenne | **Exemple le plus abouti de skill « scripts-heavy »** : modèle de découplage SKILL.md (instructions) / scripts/ (déterministe) / references/ (doc). Illustre la philosophie « exécuter sans lire la source » |
| `references/awesome-claude-skills/skill-creator/SKILL.md` (§Anatomy + §Progressive Disclosure) | `three-level loading`, `Metadata`, `SKILL.md body`, `Bundled resources` | **Doctrine du modèle 3-niveaux.** Citation clé : *« Skills use a three-level loading system : Metadata (always in context ~100 words) → SKILL.md body (when triggered <5k words) → Bundled resources (as needed, unlimited because scripts can be executed without reading into context) »* | **Haute** | **Caution externe du modèle P10.** À citer comme référence doctrinale dans notre implémentation de lazy loading |
| `references/awesome-claude-skills/changelog-generator/SKILL.md` | `pure-instructions`, catégorisation commits → changelog | Transforme des commits git en changelog user-friendly catégorisé. 0 script, tout en prompt | Moyenne | **Branchable sur un post-hook Coder.** Bon contre-point : exemple de skill « pure-instructions » (vs docx tout-script) |
| `references/awesome-claude-skills/artifacts-builder/SKILL.md` | workflow `init→dev→bundle→test` | Scaffold React+Vite+Tailwind+shadcn → bundle single-HTML | Faible | Contenu spécifique claude.ai (frontend React), mais la structure de workflow est un bon template de skill |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/awesome-claude-skills/composio-skills/.claude-plugin/marketplace.json` | config (marketplace v2.0.0) | Définit la marketplace officielle (owner ComposioHQ, classification `development`/`devops`/`business-marketing`/…) |
| `references/awesome-claude-skills/document-skills/docx/ooxml/schemas/*.xsd` (78 fichiers) | spec (schémas OOXML) | Schémas XSD de validation OOXML — référence pour la skill `docx` |

## ⚡ Le format SKILL.md canonique (la valeur transversale)
> Vérifié sur les 28 SKILL.md lus. Structure récurrente adoptée par la marketplace officielle Claude.

```yaml
---
name: <hyphen-case>           # OBLIGATOIRE, doit matcher le nom du dossier
description: <texte>          # OBLIGATOIRE, déclencheur de routage (3e personne, "This skill should be used when...")
license: Complete terms...    # OPTIONNEL (~40% des skills)
---
# <Titre>
## When to Use This Skill       # section récurrente
## What This Skill Does
## How to Use / Workflow
## (scripts/ references/ assets/ référencés)
```

**Règles de validation** (extraites de `quick_validate.py`) :
- `name` en **hyphen-case strict** (`^[a-z0-9-]+$`), pas de `-` en début/fin, pas de `--`.
- **Pas de chevrons `<>`** dans `description` (casserait le parsing).
- `description` doit être un **déclencheur** (« QUAND déclencher », pas juste « ce que ça fait »).
- **Style** : impératif/infinitif, 3e personne (« This skill should be used when… »).

**Comparaison avec notre `skills_loader.py`** : nos SKILL.md sont **déjà compatibles** (même frontmatter `name`/`description`, même regex de strip `_strip_frontmatter`). L'écart majeur : (1) **pas de sous-dossiers** `scripts/`/`references/`/`assets/` (tout est inline), (2) **chargement eager** (`build_skills_block` injecte tous les bodies) vs le lazy loading canonique. C'est ce que P10 vient corriger.

## Exclusions conscientes
- **832 `composio-skills/`** : wrappers Rube/Composio générés en série (Ably, Accelo, …) pour automatisations SaaS. **Zéro valeur pour du coding Python** — bruit massif, ignoré totalement.
- **Skills business/marketing/perso (🔴 Faible)** : `lead-research-assistant`, `competitive-ads-extractor`, `content-research-writer`, `domain-name-brainstormer`, `internal-comms`, `invoice-organizer`, `meeting-insights-analyzer`, `raffle-winner-picker`, `tailored-resume-generator`, `twitter-algorithm-optimizer`, `brand-guidelines`, `developer-growth-analysis`, `skill-share`, `connect`/`connect-apps`/`connect-apps-plugin`.
- **Skills créatifs hors-scope coding** : `canvas-design`, `image-enhancer`, `slack-gif-creator` (13 `.py` de génération GIF), `video-downloader`, `theme-factory`.
- **54 `.ttf`** (polices de canvas-design/slack-gif-creator) : assets créatifs, non pertinents.
- `assets/`, `README.md` (41 Ko, catalogue marketplace), `LICENSE.md` : non pertinents.

## Correspondance avec `plan_usine_logicielle.md`
- **P10 (Skill loading à la demande)** : ce dépôt est la **caution externe** du modèle 3-niveaux (Progressive Disclosure). `skill-creator/SKILL.md` formalise exactement le lazy loading que P10 veut implémenter (Metadata → body → resources). `init_skill.py` + `quick_validate.py` = outillage actionnable. Introduction de la structure `scripts/`+`references/`+`assets/` = changement structurel concret.
- **P0 (Judge)** : `mcp-builder/reference/evaluation.md` (pattern « 10 QA XML + vérification ») = input pour le nœud Judge.
- **P6 (Tester web)** : `webapp-testing/with_server.py` = complément Playwright à notre `web_tester` Puppeteer.
