---
name: file-creation
description: Skill pour créer/écrire des fichiers correctement avec write_file. À injecter dans le Coder. Évite le bug critique du petit modèle qui met le contenu dans son raisonnement au lieu de l'argument `content`.
---

# Skill : Création de fichiers (write_file)

## ⚠️ RÈGLE CRITIQUE N°1 — Le contenu va DANS l'argument, pas dans ta réflexion

Quand tu crées un fichier, le **contenu complet et réel** du fichier DOIT être passé dans
l'argument `content` de l'appel à `write_file`. **JAMAIS** dans ta prose/raisonnement.

- ❌ MAUVAIS : tu expliques le HTML dans ton texte, puis appelles `write_file(path="x.html", content="")`
  → le fichier créé est VIDE. C'est un échec.
- ✅ BON : tu appelles `write_file(path="x.html", content="<!DOCTYPE html>...TOUT le code...")`

**La concision s'applique à ta PROSE uniquement, PAS au contenu des fichiers.**
Un fichier `index.html` de 200 lignes → l'argument `content` doit faire 200 lignes. C'est attendu et normal.

## Comment appeler write_file

`write_file` prend deux arguments :
- `path` (str) : le chemin du fichier, ex: `landing_page/index.html`. Les sous-dossiers sont créés automatiquement.
- `content` (str) : le **contenu intégral** du fichier. Ne doit JAMAIS être vide, ni un placeholder (`...`, `TODO`, `<votre code>`).

### Exemple correct (frontend)
```
write_file(
    path="landing_page/index.html",
    content="<!DOCTYPE html>\n<html lang=\"fr\">\n<head>\n  <meta charset=\"UTF-8\">\n  <title>...</title>\n</head>\n<body>\n  ...tout le HTML réel...\n</body>\n</html>"
)
```
Note : dans un argument JSON, les guillemets doubles du HTML (`"fr"`) doivent être échappés (`\"fr\"`),
mais le contenu reste lisible. Préfère des simples quotes pour les attributs HTML quand c'est possible
(`lang='fr'`) pour réduire l'échappement.

## ⚠️ RÈGLE CRITIQUE N°2 — Pas de guillemets multiples imbriqués

Évite d'imbriquer plusieurs niveaux de guillemets qui corrompent le JSON. Préfère :
- Simples quotes pour les attributs HTML : `<div class='hero'>` (pas de `\"`)
- Le modèle passera ton `content` tel quel au système ; ne le ré-échappe pas toi-même.

## Workflow de création d'un fichier
1. Appelle `write_file(path, content)` avec le **contenu complet** directement.
2. Relis le fichier avec `read_file(path)` pour confirmer qu'il a bien été écrit avec le bon contenu.
3. Si le contenu est vide/incomplet, re-appelle `write_file` avec le vrai contenu.

## Anti-patterns INTERDITS
- ❌ `content="\n"` ou `content=""` → fichier vide.
- ❌ `content="TODO: implement"` → placeholder.
- ❌ Mettre le code dans ton message texte puis dire "j'ai créé le fichier".
- ❌ Réécrire la même chose plusieurs fois (surcoût inutile).
