# Méthodologie de routage manuel (= spec du Router idéal)

Ce document décrit **exactement** ce que je fais (l'agent) quand je joue le nœud Router à
la main, étape par étape. C'est le cahier des charges du Router idéal.

## Rôle du nœud Router

**Entrée** : le prompt utilisateur brut (une `str`, ex: « Crée un visualiseur Bubble Sort
en HTML/CSS/JS vanilla »).

**Sortie** : `RouterOutput(language)` — le langage technique principal (`javascript`,
`python`, `typescript`, `html`, `rust`, `go`...).

Ce langage est ensuite propagé jusqu'au Coder, au Tester (dispatch techno F-27 : web→
Puppeteer, python→pytest) et au Linter. Un mauvais routage cascade : un prompt Python
classé `javascript` ferait lancer le WebTester sur du code qui n'a pas de HTML → échec.

## Les étapes (dans l'ordre, fail-fast)

### Étape 1 — Lecture du prompt + détection des signaux forts (mots-clés explicites)
**Ce que je fais** : je `Read` le prompt, je cherche des **mots-clés techniques non
ambigus**. Un seul signal fort suffit la plupart du temps.
**Outil** : `grep -iE "<pattern>"` sur le prompt (ou lecture directe)
**Coût** : 0 LLM, instantané
**Tableau de décision** (signaux forts par langage) :
| Signal dans le prompt | → language |
|---|---|
| `.py`, `python`, `pip`, `pandas`, `numpy`, `pytest`, `flask`, `django`, `fastapi` | `python` |
| `.html`/`.htm`, `landing page`, `page web`, `HTML5`, `CSS3` (sans JS métier) | `html` |
| `vanilla js`, `javascript`, `DOM`, `navigateur`, `canvas`, `<script>`, `addEventListener` | `javascript` |
| `react`, `vue`, `svelte`, `next.js`, `.tsx`, `typescript`, `: type`, `interface` | `typescript` |
| `rust`, `cargo`, `tokio`, `actix` | `rust` |
| `go`, `golang`, `gin`, `echo` | `go` |
| `node.js`, `express`, `npm` (backend) | `javascript` |
**Échec type évité** : prompt « script Python pandas » classé `javascript` parce que je n'ai
pas lu les mots-clés et que j'ai déduit « web » par défaut.

### Étape 2 — Analyse des extensions de fichiers cibles (le signal le plus fiable)
**Ce que je fais** : si le prompt mentionne des fichiers cibles (`target_files`), je regarde
leurs extensions. C'est **le signal le plus fort** (explicite, pas d'interprétation).
**Outil** : lecture des extensions dans le prompt / la spec
**Tableau** : `.py`→python, `.html/.htm`→html, `.js/.mjs/.cjs`→javascript, `.ts`→typescript,
`.tsx`→typescript, `.css`→css, `.rs`→rust, `.go`→go.
**Règle** : si le langage des extensions **diffère** du langage déduit des mots-clés, les
**extensions gagnent** (détection redondante F-27, le code source est la source de vérité).
**Exemple** : prompt « Crée une app Node.js » + `target_files=["server.ts"]` → `typescript`
(l'extension `.ts` prime sur le mot-clé `node.js`).

### Étape 3 — Résolution des ambiguïtés (prompts multi-techno)
**Ce que je fais** : si le prompt mentionne **plusieurs** technologies (ex: « backend Python
Flask + frontend React »), je choisis le langage **dominant** = celui qui représente le plus
de travail, ou celui qui dicte le type de tests.
**Heuristique** :
- Frontend + backend → le **frontend** gagne si la majorité du livrable est web (tests
  Puppeteer) ; le backend gagne si c'est une API pure (tests pytest).
- Si équiprobable → je choisis `javascript` (le Coder est le plus à l'aise sur le web, et le
  WebTester est le plus mature).
**Outil** : mon jugement (pas de grep)
**Coût** : ~un tour de réflexion
**Échec type évité** : sur un prompt fullstack, classer un langage secondaire et lancer le
mauvais type de tests.

### Étape 4 — Décision finale + justification courte
**Ce que je fais** : je pose le verdict `language` + une justification en 1 phrase (le signal
qui a决定). La justification est cruciale : elle permet à un humain de vérifier mon choix.
**Sortie attendue** : `RouterOutput(language="javascript")` + note « extension .html + mots
vanilla/js ».
**Anti-pattern** : verdict sans justification → impossible à auditer.

## Ordre optimal (fail-fast)

```
1. Mots-clés forts (python? rust? react?)  ── signal unique clair ──▶ language = <ce signal>
   │ ambigu / multi-techno
   ▼
2. Extensions target_files (.py? .ts?)     ── extensions présentes ──▶ language = <extension>
   │ pas de fichiers cibles / toujours ambigu
   ▼
3. Résolution multi-techno (frontend wins?) ── verdict dominant
   │
   ▼
4. Décision + justification courte         ──▶ RouterOutput(language=...)
```

## ⚠️ BIAIS — Le piège du routeur (vécu)

**Biais n°1 — Défaut paresseux vers "javascript/web"**. Le graphe a été conçu pour le web en
priorité (WebTester mature, skills frontend-design). En cas de doute, la tentation est de
routage `javascript` « parce que c'est ce qu'on sait tester ». Contre-mesure : si le prompt
mentionne `python`/`.py` ne fut-ce qu'une fois, ce n'est PAS du web — forcer `python`.

**Biais n°2 — Confondre "app web" et "javascript"**. Une landing page en HTML/CSS pur (sans
JS métier) est du `html`, pas du `javascript`. Le Linter traite les deux différemment
(tree-sitter-html vs tree-sitter-javascript). Ne pas coller `javascript` sur tout ce qui
est web.

**Biais n°3 — Ignorer TypeScript**. Un prompt React/Next.js est presque toujours du
`.tsx`/`typescript`. Le classer `javascript` fait que le Linter ne vérifiera pas les
annotations de type — perte d'un garde-fou.

## Pourquoi cette méthode plutôt que le LLM Router (gemma)

| Critère | Router LLM (gemma-4-E4B) | Méthode manuelle (étapes 1-2) |
|---|---|---|
| Temps | ~19s (fast model) | ~2s (grep + lecture) |
| Tokens | ~2k | 0 |
| Fiabilité mots-clés | Bonne | **Binaire** (présence/absence) |
| Fiabilité extensions | Moyenne (interprète) | **Binaire** (extension = source de vérité) |
| Ambiguïtés multi-techno | Variable | Nécessite jugement (étape 3) |

**Conclusion** : 80% des prompts (étapes 1-2) sont routables de façon **déterministe et
instantanée**. Le LLM n'apporte de la valeur que sur les prompts **genuinely ambigus**
(multi-techno sans fichiers cibles), qui sont rares. Un Router déterministe par
mots-clés + extensions couvrirait la majorité des cas à 0 coût.
