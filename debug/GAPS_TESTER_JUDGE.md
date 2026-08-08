# Gaps ouverts : Tester (vision) + Judge (contexte)

**Date** : 2026-08-02 | **Source** : runs Bubble Sort F-45 (logs/run_bubble_f45_*.log) +
comparaison audit_coder/test_6 (HTML propre) vs runs/2026-08-01_2009_bubble_sort/index.html
(HTML visuellement cassé : titre h1 3.5rem/4rem, layout row à 1024px, pas de card).

Ces 2 gaps expliquent pourquoi **un bug visuel flagrant a traversé toute la chaîne**
Coder → Tester → Judge sans être rattrapé.

---

## 🐙 Gap 1 — Le screenshot est CAPTURÉ puis JETTÉ par smolagents (le modèle a la vision !)

### Symptôme
Le visualiseur Bubble Sort produit un HTML **visuellement cassé** (titre géant, layout
illisible) — et pourtant le Tester n'a **jamais signalé le problème visuel**. Il a testé
l'absence de crash JS (console errors) et la logique (assertion `isSorted`), pas le rendu.

### Racine — PROUVÉE par le log (logs/run_bubble_f45_*.log)
Le Web Tester appelle bien `puppeteer_screenshot` (7 fois sur le run), l'image EST capturée
— **mais smolagents la jette** au moment de construire l'observation. Trace exacte :
```
Calling tool: 'puppeteer_screenshot' with arguments: {'encoded': True, ...}
tool puppeteer_screenshot returned multiple content, using the first one   ← smolagents
Observations: Screenshot 'initial_ui' taken at 1280x800                    ← texte seul
```
Le serveur MCP Puppeteer renvoie l'image en **`multiple content`** (un `TextContent`
"Screenshot taken" + un `ImageContent` base64). **smolagents ne garde que le PREMIER**
(`using the first one`) → il conserve le texte et **jette l'ImageContent**. Le modèle ne
reçoit que le texte → il ne VOIT pas l'image. Confirmé : `grep base64 log` = 0 occurrence.

### Important — le MODELE a bien la vision
Gemma 4 12B (REASONING_MODEL_ID) est **multimodal natif** (model card Google : "Image
Understanding – screen and UI understanding, OCR..."). Donc ce n'est PAS une limite du
modèle. Le screenshot est capturé, le modèle sait voir — **c'est smolagents qui perd
l'image en route**. Bug d'intégration, pas bug modèle.

### Pourquoi c'est critique
Un bug visuel évident (un humain le voit en 1 seconde) passe inaperçu. Le Judge non plus
ne voit pas (il reçoit `code` en texte). La chaîne entière est **aveugle au rendu** alors
même que le modèle sait voir et que les screenshots sont capturés — tout le pipeline vision
est en place SAUF la transmission de l'ImageContent au modèle.

### Pistes de fix (à évaluer dans un cycle dédié)
1. **Conserver l'ImageContent** (fix racine) : intercepter le retour multi-content de
   `puppeteer_screenshot` côté smolagents et réinjecter l'`ImageContent` base64 comme un
   message image au modèle (format OpenAI : `{type: "image_url", image_url: {url:
   "data:image/png;base64,..."}}`). Le modèle Gemma 4 le consommera nativement → il
   VERRA le rendu. C'est le fix qui débloque toute la QA visuelle.
2. **Vérifier le path smolagents** : le `using the first one` vient probablement d'un
   `ToolCallingAgent` qui appelle `str(result)` ou prend `result[0]`. Localiser dans
   smolagents où le multi-content est réduit au premier (outils MCP → `handle_tool_call` /
   `_convert_tool_result`). Peut-être un réglagel ou un post-processing à ajouter dans
   web_tester.py (wrapper autour du tool).
3. **Assertions visuelles déterministes** (complément) : des checks non-LLM via
   `puppeteer_evaluate` (`getBoundingClientRect()` : débordement, titre > X% viewport,
   barres visibles). Moins puissant que la vraie vision mais rattrape les bugs grossiers
   (titre géant, layout row cassé) — aurait suffi pour F-46. Utile même après le fix 1
   (double vérification).

**Note honnête (corrigée)** : le modèle VOIT (Gemma 4 multimodal), le screenshot EST pris —
c'est smolagents qui jette l'ImageContent. Le fix est localisé et débloque une QA visuelle
fiable sans changer de modèle.

---

## 🧊 Gap 2 — Le Judge hang (mode thinking Gemma, PAS la taille du prompt)

### Symptôme
Sur le run F-45, le **Judge n'a jamais rendu de verdict** : il est resté bloqué en
"Juge en cours d'évaluation" indéfiniment (hang). Ollama ne générait plus de façon visible
(CPU/appels figés) alors que les connexions TCP restaient Established.

### Racine — CORRIGÉE par mesure réelle (l'hypothèse "prompt trop gros" est FAUSSE)
**Mesure du prompt Judge réel (run F-45)** — il est **PETIT, pas gros** :
```
system prompt (instruction F-44 + rubric) :  3743 chars (~ 935 tok)
code (index.html brut, NON tronqué)         :  8916 chars (~2229 tok)
test_results (tronqué max_chars=2000)       :  2000 chars (~ 500 tok)
task_requirements (tronqué max_chars=1500)  :  1500 chars (~ 375 tok)
TOTAL                                       : 16159 chars (~4039 tok)
```
Le rapport Tester vers Judge est **déjà tronqué** (`truncate_output`, dspy_nodes.py:543/556).
Le Judge ne reçoit PAS les 124k tokens du contexte Tester. Donc le hang **ne vient pas du
prompt input**.

**VRAIE cause : le mode "thinking" de Gemma 3/4** (confirmé par test direct) :
```
curl ... 12B "Reply with VERDICT OK" → réponse: '<|channel>thought\nThe user wants...'
```
Gemma génère un **canal de pensée interne** (`<|channel>thought`) AVANT la réponse finale.
Or `_configure_dspy` (dspy_nodes.py:234) fixe **`max_tokens=8192`** pour le modèle reasoning.
Sur un prompt Judge (rubric + findings + raisonnement), le thinking peut consommer une
grande partie des 8192 tokens **avant** d'émettre le JSON du verdict.
- 12B sur GPU (6 Go VRAM) : ~6 tok/s → 8192 tokens = **~23 min** de génération possible.
- C'est lent au point de sembler "hangé" ; le `LLM_TIMEOUT_S=600` (10 min) peut même couper
  en plein milieu du thinking → pas de verdict du tout.

### Pourquoi c'est critique
Sans verdict du Judge, **le workflow ne peut pas terminer** la sous-tâche (hang F-45).
Et même quand le Judge répond, le mode thinking non maîtrisé gaspille du budget de
génération et du temps.

### Pistes de fix (à évaluer dans un cycle dédié)
**CONSTAT TECHNIQUE DÉFINITIF (expérimenté, 2026-08-02)** : Ollama **0.32.5** (testé = BIEN
la dernière release GitHub publiée 2026-07-27 — ce n'est PAS une vieille version). Sur cette
version, le thinking est **FORCÉ via l'endpoint `/v1`** pour Gemma 4, et **aucune méthode
testée ne le désactive** :
- ❌ `think:false` au top-level du body `/v1` → ignoré.
- ❌ `extra_body={"think": False}` via client OpenAI Python → ignoré.
- ❌ `chat_template_kwargs.enable_thinking:false` → ignoré.
- ❌ Modelfile avec `TEMPLATE` minimal sans logique thinking → thinking quand même.
- ❌ Sans system prompt, sans tools → thinking quand même (`finish:length`, content vide).
- ❌ Modelfile avec template complet Jinja forçant `enable_thinking=false` en dur → erreur
  Ollama (le `TEMPLATE` du Modelfile ne supporte pas les fonctions Jinja avancées du
  chat template HF comme `key`).

**Seul `/api/chat` natif + `think:false` marche** (test : 4.8s, eval_count=6, réponse
directe) — mais DSPy utilise `/v1`, pas `/api/chat`.

Conclusion : sur Ollama 0.32.5 (dernière version), le proxy OpenAI-compat `/v1` **force le
thinking** pour Gemma 4. Ce n'est pas un bug de vieille version à MAJ — c'est le comportement
actuel d'Ollama. Il faudra soit attendre une évolution d'Ollama (issue à remonter ?), soit
contourner.

Options réalistes (par ordre de pragmatisme) :
1. **Bypass `/v1` pour le reasoning** : wrapper DSPy/litellm pour appeler `/api/chat` (avec
   `think:false`) au lieu de `/v1`. Plus invasif (custom adapter LM) MAIS c'est le seul
   contournement qui élimine VRAIMENT le thinking côté code, sans attendre Ollama.
2. **`max_tokens` bas pour les nœuds DSPy** : 8192 → ~1500-2000. N'élimine pas le thinking
   mais borne la casse (coupé plus tôt → échec gracieux plus rapide).
3. **Timeout + échec gracieux effectif** : si le Judge dépasse ~120s, ne pas attendre —
   repli sur le verdict brut du Tester (ou marquer "judge_timeout" + circuit breaker).
   Vérifier que `LLM_TIMEOUT_S` est bien propagé à l'appel DSPy (pas seulement smolagents).
   À FAIRE DE TOUTE FAÇON (défense en profondeur).
4. **Remonter le sujet à Ollama** : le thinking forcé sur `/v1` sans moyen de le désactiver
   est un manque pour les cas d'usage agent/structured-output. Vérifier si une issue existe
   sur github.com/ollama/ollama (la 0.32.5 est récente, peut-être déjà remonté).

**Note honnête (corrigée 2×)** : mon hypothèse initiale "trop de contexte input" était fausse
(prompt Judge petit, 4k tokens). La température basse (0.3) est CORRECTE pour le code, ne pas
changer. Le vrai coupable est le **thinking Gemma forcé sur /v1 par Ollama 0.32.5 (dernière
version) + non désactivable via /v1 + max_tokens 8192**. Aucune MAJ Ollama à faire (déjà à
jour) — il faut un contournement code (options 1-3 ci-dessus).

---

## Liens avec les travaux existants
- **TIMINGS_ANALYSE.md reco #5** (compaction contexte Tester) → atténue le contexte du
  Tester lui-même, mais le rapport Tester→Judge est DÉJÀ tronqué (mesuré : ~4k tokens
  total au Judge). La compaction aide surtout le Tester, pas directement le Judge.
- **F-37** (Nettoyage DOM) atténue le contexte Tester mais ne règle pas le screenshot
  non transmis (Gap 1) ni le mode thinking (Gap 2).
- **F-45** (fix Tester querySelector) a réglé la boucle querySelector mais révélé ces 2
  gaps plus profonds en permettant au run d'atteindre le Judge.

## Priorité (revue après diagnostic définitif)
- **Gap 2 (Judge thinking/hang)** → **RÉSOLU (F-47, ce cycle)** : `_configure_dspy` passe au
  provider `ollama/` (parle `/api/chat` + `think` param). Thinking désactivé pour
  Router/PromptRefiner/Security/Judge/Escalation, conservé pour Architect. Validé : 5.8s vs
  ~23 min. 487 tests / 0 régression.
- **Gap 1 (Tester aveugle au rendu)** → **prochain cycle (F-48), version élargie** : la
  meilleure piste n'est pas de bricoler le screenshot côté Tester, mais de donner la **vision
  au Coder lui-même** (auto-validation visuelle verify-after). Voir "F-48" ci-dessous.

---

## F-48 (PROCHAIN CYCLE) — Vision Coder : auto-validation visuelle verify-after

Idée (utilisateur) : le Coder (4B) a la vision (confirmé : décrit parfaitement un screenshot
via `/api/chat` + `think=false`). Il pourrait **capturer un screenshot de son propre output**
après `write_file` et **s'auto-valider visuellement** (titre correct ? layout cassé ?) dans
la boucle, avant même le Judge. C'est l'invariant "verify-after" (F-44) appliqué au visuel.

### Prérequis découvert ce cycle
1. **Le Coder subit le thinking forcé sur `/v1`** (confirmé : content vide, reasoning présent,
   finish=length — même bug que le Judge avant F-47). Donc le Coder "réfléchit" inutilement à
   chaque step (gaspille du budget code + ralentit) ET sa vision répondrait vide tant qu'il est
   sur `/v1`. **Première étape F-48 = faire parler le Coder `/api/chat` + `think=false`** (même
   mécanisme que F-47, mais pour smolagents `OpenAIServerModel`).
2. **Le 4B A la vision** (confirmé via `/api/chat` + `think=false` + screenshot
   audit_coder/test_6 : "dark-themed web interface... Title: 'Visualiseur Bubble Sort'...").

### Périmètre F-48 (décision utilisateur : "Tout 1+2+3")
1. **think=false Coder** : smolagents `OpenAIServerModel` → faire parler `/api/chat` (via litellm
   `ollama/` ou custom). Bénéfice double : + budget code utile, + débloque la vision.
2. **Outil screenshot pour le Coder** : après `write_file` d'un fichier HTML, capturer la page
   (Puppeteer ou chrome-devtools) et exposer le screenshot au Coder comme image.
3. **Skill Coder verify-after visuel** : enrichir le skill avec une étape "après write_file d'une
   UI, capture un screenshot et vérifie : titre lisible (pas géant), layout non cassé, éléments
   visibles". Auto-correction si problème détecté (search_replace pour fix).

### Pourquoi cycle dédié (pas ce cycle)
- Le Coder est le **cœur du système** (produit le code). Y toucher mérite tests/validation
  séparés (comparatif qualité code avec/sans thinking, régression sur Bubble Sort + Nimbus).
- Le scope 1+2+3 est ambitieux (smolagents + tools + skill + validation). Mieux vaut l'isoler.
