# Rapport d'Audit : Compatibilité du mode "Thinking" de Gemma 4 avec Ollama et DSPy

## 1. Contexte et Objectif
L'objectif de cet audit était de valider l'utilisation des modèles **Gemma 4 (12B)** comme `REASONING_MODEL_ID` pour le nœud critique **Architect** du graphe (qui requiert une chaîne de pensée détaillée avant de découper une tâche).

Deux modèles GGUF locaux (via Ollama) ont été testés :
* `hf.co/unsloth/gemma-4-12b-it-GGUF:Q4_K_M` (Version quantifiée par Unsloth)
* `hf.co/google/gemma-4-12B-it-qat-q4_0-gguf:latest` (Version quantifiée officielle Google)

## 2. Tests Réalisés et Problèmes Rencontrés

### A. Test via le paramètre API d'Ollama (`think=True`)
* **Méthodologie** : Envoi du flag natif `think=True` via LiteLLM/DSPy.
* **Résultat** : ❌ Échec immédiat. Ollama renvoie l'erreur `{"error": "... does not support thinking"}`.
* **Explication** : L'implémentation actuelle d'Ollama réserve ce paramètre d'API à une liste blanche de modèles (famille DeepSeek-R1, QwQ). Les métadonnées GGUF de Gemma 4 ne sont pas reconnues par Ollama pour ce flag.

### B. Test via l'injection du token de prompt (`<|think|>`)
D'après la documentation de Gemma 4, la réflexion doit s'activer en plaçant le token `<|think|>` au début du System Prompt (indépendamment du paramètre d'API).
Un script de benchmark "standalone" (`bench_gemma_standalone.py`) a été écrit pour tester ce comportement en attaquant l'API native d'Ollama sans le flag `think=True`.

* **Résultats sur le modèle Unsloth** :
  * Temps de réponse : ~260 secondes.
  * Sortie : Un JSON valide généré directement.
  * **Analyse** : ❌ Aucune balise `<|channel>thought` générée. L'injection du token n'a pas déclenché la réflexion. Il est probable que la quantification d'Unsloth ait altéré le `chat_template` complexe requis pour cette fonctionnalité.
* **Résultats sur le modèle Google officiel** :
  * **Analyse** : ❌ Crash sévère de l'instance `llama-server` sous-jacente à Ollama (Erreur 500 : `CUDA error: shared object initialization failed` / `overrun of a stack-based buffer`). Le modèle s'avère instable dans cet environnement.

## 3. Préconisations Architecturales

Au vu des résultats, l'utilisation de Gemma 4 pour les tâches nécessitant une réflexion explicite via Ollama est fortement déconseillée dans l'état actuel de l'écosystème.

1. **Pour le nœud Architect (et tout nœud nécessitant `think=True`) :**
   * **Abandonner Gemma 4** pour ce rôle spécifique.
   * **Recommandation** : Utiliser un modèle dont le reasoning est supporté nativement et testé par Ollama (ex: `DeepSeek-R1:8b`, `DeepSeek-R1:14b`, ou le modèle `Ornith-1.0-9B` qui a réussi le benchmark précédent).

2. **Pour les autres nœuds DSPy (Router, Security, Judge) :**
   * Gemma 4 (notamment les versions E4B) reste un excellent choix pour les tâches "zéro-shot" (sans réflexion).
   * **Attention** : S'assurer que le code ne lui passe jamais le paramètre `think=True`, sous peine de provoquer un crash API immédiat (comportement déjà géré et documenté dans le fichier `dspy_nodes.py`).

3. **Veille Technologique :**
   * Le support complet des tags de réflexion de Gemma 4 par `llama.cpp` (le moteur d'Ollama) est encore récent ou instable. Il conviendra de retester les versions GGUF officielles après les prochaines mises à jour majeures d'Ollama.

## 4. Complément (mis à jour) — Le Thinking MARCHE avec llama.cpp direct, PAS via Ollama

### Constat confirmé
Les tests ci-dessus échouaient **parce qu'ils passaient par Ollama**, pas parce que Gemma 4 ne
sait pas réfléchir. En utilisant **llama.cpp directement** (`llama-server` / `llama-cli`, le même
moteur qu'Ollama mais sans le wrapper), le mode Thinking de Gemma 4 **fonctionne**. C'est exactement
pourquoi « avec Ollama il n'y arrive pas, mais avec llama.cpp il y arrive ».

**Pourquoi Ollama bloque** :
- Ollama réserve le flag d'API `think=True` à une liste blanche (DeepSeek-R1, QwQ) → erreur pour Gemma 4.
- Sur `/v1`, Ollama **force** le thinking OU l'ignore selon les versions, et ne transmet jamais les
  `chat_template_kwargs` de Gemma 4 au moteur.
- Certains GGUF (Google QAT) font crasher l'instance `llama-server` noyée dans Ollama (`CUDA error`).

En revanche, llama.cpp expose nativement l'équivalent de `think=True` via le flag
**`--reasoning on`** (env `LLAMA_ARG_REASONING`), que Ollama ne permet pas d'atteindre.
C'est ce flag qui a été **validé empiriquement** (mesures en §4).

### Comment l'utiliser (llama.cpp direct) — RECETTE VALIDÉE

#### 1. Lancer `llama-server` avec le thinking activé
```powershell
llama-server -m <chemin\checkpoint.gguf> -c 8192 --reasoning on --host 127.0.0.1 --port 8080
```
> ⚠️ Ne pas surcharger la VRAM : sur la config testée, fixer `-ngl 40` provoque un **OOM**
> (serveur en échec au chargement). Préférer l'**auto-fit** (omettre `-ngl`) ou un `-ngl ≤ 32`
> pour un contexte de 8192. Voir §5.
>
> L'ancienne approche `LLAMA_ARG_CHAT_TEMPLATE_KWARGS={"enable_thinking": true}` (et le paramètre
> par-requête `chat_template_kwargs`) a été testée : elle **n'a PAS déclenché** le thinking sur ce
> modèle/build. Le flag `--reasoning on` est l'élément déclencheur fiable.

#### 2. Interroger l'endpoint OpenAI-compatible
```json
POST http://127.0.0.1:8080/v1/chat/completions
{
  "model": "gemma",
  "messages": [
    { "role": "system", "content": "<prompt système>" },
    { "role": "user", "content": "<tâche>" }
  ],
  "temperature": 0.3
}
```

#### 3. Lire la pensée dans `message.reasoning_content`
Avec `--reasoning on`, llama.cpp **extrait** la pensée dans un champ séparé (format type DeepSeek),
et ne laisse que la réponse finale dans `message.content` :
```json
"message": {
  "role": "assistant",
  "content": "<réponse finale propre>",
  "reasoning_content": "<la chaîne de pensée complète>"
}
```
Validation mesurée : clés du message = `['content', 'reasoning_content', 'role']` ; ~531 tokens,
~7 tok/s en auto-fit, contexte 8192 — le `reasoning_content` contenait bien l'analyse, la rédaction
interne et l'affinement avant la réponse finale.

### Scripts prêts à l'emploi dans `debug/`
- **`validate_gemma_thinking.py`** — LA validation : lance `llama-server` direct avec
  `--reasoning on` + auto-fit + `-c 8192`, envoie une requête `/v1` et affiche
  `reasoning_content` + `content`. C'est la preuve vérifiée que le thinking marche hors Ollama.
- **`bench_llama_server.py`** — variante historique (kwargs / extraction des canaux).
- **`optimize_gpu_layers.py`** / **`optimize_gpu_layers_server.py`** — réglage des couches GPU
  (`-ngl`) ou auto-fit pour faire tenir le GGUF dans la VRAM.

### Points d'attention
- Préférer les **GGUF officiels Google** (le fP16/fQT UNSLOTH altère le `chat_template` requis).
- **Activer le thinking avec `--reasoning on`** (et non l'env var `enable_thinking`, non concluante).
- La pensée arrive dans **`message.reasoning_content`** et la réponse finale dans
  **`message.content`** : pour le nœud Architect, injecter `content`, et stocker
  `reasoning_content` séparément (ou l'ignorer) — ne pas le concaténer tel quel dans la réponse.
- Ne **jamais** passer `think=True` depuis le code vers Ollama (crash API immédiat) — comportement
  déjà géré dans `dspy_nodes.py`.

## 5. Notes de mise en œuvre (couches GPU / auto-fit)

Pour faire tourner le GGUF en local de façon fiable : l'auto-fit de llama.cpp (comportement Ollama)
ou un `-ngl` manuel. Sur la config testée (GPU CUDA ~5 Gio libres, modèle gemma4 6,63 Go) :
- Sweep manuel à contexte 8192 : `-ngl 32` → ~11,3 tok/s (max) ; `-ngl 35` → OOM (KV cache).
- **Auto-fit** (recommandé, façon Ollama) : ~8 tok/s, jamais en OOM, s'adapte au contexte.

## 6. Synthèse — Solutions & Benchmarks

### A. Tableau récapitulatif des benchs

**Ollama (via Ollama)** — modèle 12B :

| Méthode | Résultat | Détail |
|---------|----------|--------|
| API `think=True` | ❌ | Erreur `"does not support thinking"` (liste blanche) |
| Token `<|think|>` (Unsloth) | ❌ | ~260 s, JSON valide mais **aucun** `<|channel>thought` |
| Token `<|think|>` (Google) | ❌ | **Crash** `CUDA error: shared object init` / stack overrun |

**llama.cpp direct (`llama-server`)** — modèle gemma4 6,63 Go, prompt simple, contexte 8192 :

| Config | Résultat | Débit / note |
|--------|----------|--------------|
| `-ngl 15` | ✅ | 6,26 tok/s |
| `-ngl 20` | ✅ | 6,67 tok/s |
| `-ngl 25` | ✅ | 7,96 tok/s |
| `-ngl 28` | ✅ | 8,91 tok/s |
| `-ngl 30` | ✅ | 9,40 tok/s |
| `-ngl 32` | ✅ | **11,28 tok/s (max)** |
| `-ngl 35` | ❌ OOM | KV cache (`ErrorOutOfDeviceMemory`) |
| `-ngl 40` | ❌ OOM | sortie process au chargement |
| **auto-fit** (sans `-ngl`) | ✅ | ~8,04 tok/s — jamais en OOM |
| **auto-fit + `--reasoning on`** | ✅ **THINKING** | ~7,06 tok/s, 531 tokens, 75 s → `reasoning_content` rempli |

### B. Solutions retenues

1. **Utiliser llama.cpp DIRECT** (`llama-server`), pas Ollama, pour activer le thinking.
   Commande validée :
   ```powershell
   llama-server -m <checkpoint.gguf> -c 8192 --reasoning on
   ```
   (auto-fit conseillé → omettre `-ngl` ; sinon `-ngl ≤ 32` à ctx 8192).

2. **Lire la pensée dans `message.reasoning_content`** et la réponse finale dans
   `message.content` (endpoint OpenAI-compatible `/v1/chat/completions`).

3. **VRAM** : auto-fit (recommandé) ou `-ngl 32` max ; `-ngl ≥ 35` → OOM sur cette config.

4. **Pas de `think=True` vers Ollama** depuis le code (crash API) — déjà géré dans `dspy_nodes.py`.

### C. Bench à relancer
- **`validate_gemma_thinking.py`** — preuve automatique du thinking (`--reasoning on` + auto-fit,
  affiche `reasoning_content` / `content`).
- **`optimize_gpu_layers_server.py`** — sweep `-ngl` (mode par défaut) ou **`auto`** (auto-fit façon
  Ollama) pour re-mesurer les débits sur ta config.

## 7. Héberger llama.cpp comme Ollama — mode router & chargement à la volée

llama.cpp peut **reproduire le comportement d'Ollama** (plusieurs modèles, chargement à la demande,
libération après inactivité) **sans passer par Ollama**, grâce à deux mécanismes natifs de `llama-server`.

### A. Mode router : lancer SANS modèle (standby) ✅

Lancé **sans `-m`**, `llama-server` part en *router mode* : aucun modèle n'est chargé au démarrage,
et il expose une API de chargement/déchargement dynamique.

```sh
llama-server                                  # mode router, aucun modèle chargé
llama-server --models-dir D:\OLLAMA_MODELS\blobs   # + pointe vers un dossier de GGUF
```

- Sources de modèles : cache (`LLAMA_CACHE`), un dossier (`--models-dir`), ou un preset INI (`--models-preset`).
- Le champ **`model`** du body JSON route chaque requête vers la bonne instance.
- **`--models-autoload`** (défaut activé) → chargement **à la demande** au premier appel.
- **`--models-max N`** (défaut 4, 0 = illimité) → nb max de modèles chargés en même temps ;
  au-delà, éviction des moins utilisés (logique de cache type Ollama).
- **`POST /models/unload`** → déchargement manuel.

### B. Libération après inactivité : `--sleep-idle-seconds` ✅

Equivalent natif du « keep-alive » d'Ollama (~5 min par défaut) : après N secondes sans tâche, le
modèle (et sa mémoire, KV cache inclus) est **déchargé de la RAM** ; la requête suivante déclenche
automatiquement le rechargement.

```sh
llama-server --models-dir <dir> --sleep-idle-seconds 300   # décharge après 300 s d'inactivité
```

### C. Paramètres par modèle via preset INI

Comme un Modelfile d'Ollama, un preset INI définit les arguments par modèle :

```ini
version = 1
[*]                       ; globals partagés
c = 8192
n-gpu-layers = 32

[gemma4-12b]
model = D:\OLLAMA_MODELS\blobs\sha256-0a270ec9fe6b34f4a0d33992b6135117b484ebc4766ab76b51d4ae8c457e4c42
reasoning = on            ; active le thinking pour ce modèle
c = 8192

[gemma4-e4b]
model = D:\OLLAMA_MODELS\blobs\sha256-<autremodele>
```
Lancer : `llama-server --models-preset ./models.ini --sleep-idle-seconds 300`.

### D. Différence conceptuelle

- **Ollama** = superviseur (daemon Go + scheduler + registry) construit **au-dessus** de llama.cpp ;
  il gère keep-alive et spawn/stop des `llama-server` par modèle.
- **llama.cpp router mode** = la même capacité de gestion multi-modèles **dans `llama-server`**,
  avec un contrôle plus fin (`--models-max`, presets INI, `reasoning on` par modèle).

### E. Application au graphe

Pour servir fast_model (E4B) + reasoning (gemma4) en un seul process :
- un **`llama-server` en router mode** sert les deux modèles, chacun chargé à la demande ;
- préfixer chaque modèle avec ses params dans un `models.ini` (`reasoning on`, `c=8192`, `n-gpu-layers`…).

> ⚠️ Rappel VRAM (voir §5) : sur cette config (~5 Gio libres), `n-gpu-layers ≤ 32` ou auto-fit ;
> `-ngl ≥ 35` → OOM. En router multi-modèles, `--models-max` limite les chargements simultanés
> pour rester sous la VRAM.

### F. Fichier `models.ini` (déjà présent à la racine du repo)

**Où** : `models.ini` (racine du projet).

**À quoi il sert** : preset du **mode router** de `llama-server` — décrit les modèles à servir,
leurs chemins `.gguf` et leurs paramètres par modèle (contexte, thinking, mmproj, auto-fit), pour
lancer en un seul process plusieurs modèles à la façon d'Ollama (chargement à la demande + eviction).

**Comment s'en servir** :
1. Lancer le router en pointant le preset (et un keep-alive natif) :
   ```sh
   llama-server --models-preset ./models.ini --sleep-idle-seconds 300
   ```
2. Aucun modèle n'est chargé au démarrage ; il se charge au premier appel.
3. Adresser chaque modèle via le champ `model` du body `/v1/chat/completions`
   (le **nom de section** est l'identifiant) :
   - `"model": "gemma-4-12b"` → thinking **(renvoie `reasoning_content`)**
   - `"model": "gemma-4-e4b"` → fast, sans thinking
4. Déchargement : automatique après `--sleep-idle-seconds`, manuel via `POST /models/unload`,
   ou limité par `--models-max` (nb max chargés simultanément).

**Contenu actuel** (2 sections + globals `[*]`) :
```ini
[*]            c = 8192 ; auto-fit (pas de n-gpu-layers) ; no-mmap ; flash-attn auto ; np = 2
[gemma-4-12b]  model=blob 0a270ec9… ; reasoning = on ; mmproj = 91f08697…
[gemma-4-e4b]  model=blob df0fd4ee… ; reasoning = off ; mmproj = 7c9bafa2…
```
Les chemins viennent du mapping §8.

> 💡 Astuce : pour re-générer les chemins exacts en cas de changement,
> utiliser les commandes de §8.

## 8. Emplacement des fichiers par modèle Ollama (mapping chemin réel)

### Convention de stockage

Ollama stocke ses modèles sous **`OLLAMA_MODELS`** (ici `D:\OLLAMA_MODELS`) en deux dossiers :
- **`blobs\sha256-<digest>`** : les fichiers réels (poids, mmproj, templates, params), adressés par leur hash SHA-256 ;
- **`manifests\<registry>\<namespace>\<model>\<tag>`** : un JSON qui associe chaque **nom** de modèle à ses blobs.

Un même blob peut être **partagé** entre plusieurs modèles nommés.

### Commandes pour retrouver l'emplacement

```powershell
# 1. Modèles installés (noms + tailles + IDs)
ollama list

# 2. Lister tous les manifests (un fichier par modèle:tag)
Get-ChildItem D:\OLLAMA_MODELS\manifests -Recurse -File

# 3. Pour UN modèle donné : lire son manifest et afficher les fichiers blobs résolus
$m = 'D:\OLLAMA_MODELS\manifests\hf.co\unsloth\gemma-4-12b-it-GGUF\Q4_K_M'
$j = Get-Content $m -Raw | ConvertFrom-Json
foreach ($ly in $j.layers) {
    $d = $ly.digest -replace '^sha256:', ''
    '[' + $ly.mediaType + ']  D:\OLLAMA_MODELS\blobs\sha256-' + $d
}

# 4. Scanner TOUS les modèles : nom -> fichier .gguf (modèle) unique
Get-ChildItem D:\OLLAMA_MODELS\manifests -Recurse -File | ForEach-Object {
    $j = Get-Content $_.FullName -Raw | ConvertFrom-Json
    $fichiers = $j.layers | Where-Object mediaType -eq 'application/vnd.ollama.image.model' |
        ForEach-Object { 'D:\OLLAMA_MODELS\blobs\sha256-' + ($_.digest -replace '^sha256:', '') }
    $_.FullName.Replace('D:\OLLAMA_MODELS\manifests\','') + '  ->  ' + ($fichiers -join ', ')
}
```

### Mapping actuel — Modèles LLM (graphe)

| Modèle Ollama (nom) | Fichier modèle `.gguf` (blob) | Taille | mmproj (projector) |
|---------------------|-------------------------------|--------|--------------------|
| `hf.co/unsloth/gemma-4-12b-it-GGUF:Q4_K_M` *(reasoning)* | `...\blobs\sha256-0a270ec9fe6b34f4a0d33992b6135117b484ebc4766ab76b51d4ae8c457e4c42` | 6,63 Go | `...\sha256-91f086971e56d7a7d8d39e271873fccdb49541bd259d6e02c401a4f1cb7a219e` (0,16 Go) |
| `hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL` *(fast)* | `...\blobs\sha256-df0fd4ee07072c607c29a0a1cb4f98918426cca12f45a2776bdd6ee6d09a4de3` | 3,93 Go | `...\sha256-7c9bafa27f82d658eda805c1d82ef62bb0368e1ff75f64f77de58ad318beaaf9` |
| `hf.co/google/gemma-4-12B-it-qat-q4_0-gguf:latest` | `...\blobs\sha256-93567e57a8fe10b23569b9d9ec38cd005deedf71e29477c421a4b83f418a538b` | 6,50 Go | `...\sha256-cb018338a7538a9814d994bfe54644c71eb7ed54e31eae2f721e45fd3c260da7` (0,16 Go) |
| `gemma-12B-nothink:latest` | **même blob** que le QAT Google (`...\sha256-93567e57...`, poids partagés) | 6,50 Go | idem `cb018338...` |
| `hf.co/protoLabsAI/Ornith-1.0-9B-MTP-GGUF:Q4_K_M` | `...\blobs\sha256-93c47a7e76c62706be71052cf2cc407c0e5ce7f6789263464f6b6bad8d55b297` | 5,38 Go | — |

### Mapping actuel — Embeddings

| Modèle | Fichier | Taille |
|--------|---------|--------|
| `bge-m3:latest` | `...\blobs\sha256-daec91ffb5dd0c27411bd71f29932917c49cf529a641d0168496c3a501e3062c` | 1,2 Go |
| `nomic-embed-text:latest` | `...\blobs\sha256-970aa74c0a90ef7482477cf803618e776e173c007bf957f635f1015bfcfef0e6` | 274 Mo |
| `mxbai-embed-large:335m` | `...\blobs\sha256-819c2adf5ce6df2b6bd2ae4ca90d2a69f060afeb438d0c171db57daa02e39c3d` | 669 Mo |
| `qwen3-embedding:8b` | `...\blobs\sha256-3fcd3febec8b3fd64435204db75bf0dd73b91e8d0661e0331acfe7e7c3120b85` | 4,7 Go |

### Notes
- **Blobs partagés** : `gemma-12B-nothink` et le QAT Google pointent vers le même blob de poids
  (`93567e57...`) ; la différence est dans la couche `template` (qui conditionne le thinking).
- **mmproj séparé** pour les gemma4 multi-modaux (vision) — à passer via `--mmproj` si on utilise
  le GGUF directement avec `llama-server`.

## 9. Difficultés de migration Ollama → llama.cpp

Migrer de Ollama vers `llama-server` direct n'est **pas un simple changement de port** : Ollama ajoute
une couche d'abstraction (registry, manifests, templates, Modelfile) que llama.cpp ne reproduit pas
à l'identique. Difficultés concrètes rencontrées pendant cet audit :

### A. Résolution modèle → fichier (la plus bloquante)
- Ollama adresse les modèles par **nom** (`hf.co/unsloth/gemma-4-12b-it-GGUF:Q4_K_M`) ;
  `llama-server` attend un **chemin de fichier `.gguf`**.
- Un modèle Ollama = **plusieurs blobs** (modèle + mmproj + template + params), adressés par
  `sha256-<digest>` dans `blobs\`, **sans extension**. Il faut donc résoudre chaque manifest pour
  retrouver les fichiers (commandes §8). Un humain ne peut pas deviner que `0a270ec9…` = gemma-4-12b.
- **Conséquence** : `models.ini` (§7F) doit être **manuellement maintenu** avec les chemins absolus
  des blobs. Si Ollama re-pull un modèle (nouveau digest), le preset casse silencieusement.

### B. Perte de la couche template / params d'Ollama
- Ollama stocke le `chat_template` et les `params` (stop tokens, température par défaut…) dans des
  blobs séparés (`application/vnd.ollama.image.template` / `.params`), qu'il **injecte** au lancement.
- `llama-server` direct **lit le template depuis les métadonnées GGUF** et ignore ces blobs Ollama.
- **Cas vécu** : le GGUF Unsloth a un `chat_template` altéré → Ollama pouvait compenser via son blob
  template, mais `llama-server` direct hérite du template cassé (§2B). C'est une régression silencieuse
  à la migration : un modèle qui « marchait » sous Ollama peut se comporter différemment hors Ollama.

### C. Gestion du cycle de vie (daemon vs process)
- Ollama tourne en **service Windows persistant** (démarrage auto, re-spawn, API toujours up).
- `llama-server` est un **process à lancer soi-même** (pas de daemon natif). Pour l'équivalent du
  keep-alive Ollama, il faut `--sleep-idle-seconds` + un wrapper/scheduled task pour le relancer.
- En cas de crash (`CUDA error` vu sur le QAT Google §2B), Ollama relance l'instance ;
  `llama-server` direct meurt et laisse le port inutilisé.

### D. Différences d'API / d'activation du thinking
- Ollama : API `/api/chat` + `/v1`, `think=True` **liste blanche** (Gemma 4 rejeté §2A).
- llama-server : API `/v1` OpenAI-compatible, thinking via **`--reasoning on`** au lancement
  (validé §4), résultat dans `message.reasoning_content`.
- Côté client (LiteLLM/DSPy), le code doit donc : pointer sur le port `llama-server`, **ne plus
  passer `think=True`**, et lire `reasoning_content` au lieu d'attendre les balises inline.
  Le provider `ollama/` de LiteLLM ne convient plus → utiliser `openai/` contre le `llama-server`.

### E. Modelfile ↔ preset INI (pas d'équivalent strict)
- Ollama : `Modelfile` (FROM + PARAM + TEMPLATE + SYSTEM) versionné, éditable, reproductible.
- llama.cpp : `--models-preset` INI (§7C) couvre les arguments, mais **pas** les instructions
  `SYSTEM`/`TEMPLATE` arbitraires d'Ollama — il faut les injecter côté client (system prompt) ou
  via `--chat-template`/`--chat-template-file`. Migration non automatique.

### F. Maturité du mode router multi-modèles
- Le **router mode** de `llama-server` (§7A) est plus récent et moins éprouvé que le scheduler
  Ollama (éviction LRU, rechargement, partage VRAM). À valider en charge avant de l'utiliser en
  production pour le graphe (notamment `--models-max` et le comportement à l'OOM d'un modèle).

### G. Récap des points à valider avant migration
1. Résoudre et **figer** les chemins de blobs dans `models.ini` (et les re-vérifier après chaque
   `ollama pull`).
2. Tester chaque GGUF **hors Ollama** : le template GGUF seul peut différer du comportement Ollama.
3. Mettre en place un **wrapper de lancement persistant** pour `llama-server` (service/scheduled task).
4. Adapter le code client : provider `openai/` (pas `ollama/`), lire `reasoning_content`, ne pas
   passer `think=True`.
5. Bench en charge du router mode avant de s'y fier pour la prod.

## 10. Impact sur le code du projet (DSPy / smolagents / config)

Le projet se connecte à Ollama via **3 mécanismes distincts**, chacun avec ses propres hypothèses
Ollama-spécifiques. Une migration vers `llama-server` les casse toutes — voici l'inventaire exact
(fichiers réels audités).

### A. Provider LiteLLM `ollama/` dans DSPy → CASSE (le plus critique)

**Fichier** : `graph_orchestrator/dspy_nodes.py` → `_configure_dspy()` (lignes ~326-339).
```python
api_base = ...  # ollama_reasoning_api_base ou ollama_api_base
if api_base.endswith("/v1"):
    api_base = api_base[:-3]          # ❌ RETIRE /v1 (spécifique Ollama /api/chat)
lm = dspy.LM(
    f"ollama/{model_id}",             # ❌ provider ollama/ = API native /api/chat
    api_base=api_base,
    api_key="ollama",
    think=think,                      # ❌ paramètre think = Ollama-only
)
```
**Problèmes** :
1. Le provider **`ollama/`** de LiteLLM parle l'API **native `/api/chat`** d'Ollama (pas `/v1`).
   `llama-server` n'expose **que** `/v1/chat/completions` → 404 sur `/api/chat`.
2. Le **retrait du `/v1`** (ligne 328-329) est l'inverse de ce qu'il faut pour `llama-server`
   (qui veut `/v1`).
3. Le paramètre **`think=True/False`** est traduit par LiteLLM en champ `think` du body `/api/chat`
   d'Ollama. `llama-server` l'ignore (le thinking se pilote via `--reasoning on` au lancement).
   → Le `think=True` de l'Architect devient un no-op silencieux.

**Migration** : remplacer `f"ollama/{model_id}"` par `f"openai/{model_id}"`, **garder** le `/v1`
dans `api_base`, et **retirer** `think=`. Le thinking se gère alors côté serveur (un llama-server
`--reasoning on` pour l'Architect, `off` pour les autres — via `models.ini` §7F).

### B. Provider `ollama_chat/` dans le JSON-fixer → CASSE

**Fichier** : `graph_orchestrator/models.py:239`.
```python
lm = dspy.LM(f"ollama_chat/{settings.fast_model_id}",
             api_base=settings.ollama_api_base.replace("/v1", ""), ...)
```
Même problème : `ollama_chat/` est un provider LiteLLM Ollama-spécifique (`/api/chat`).
**Migration** : `f"openai/{settings.fast_model_id}"` + `api_base` **avec** `/v1`.

### C. smolagents `OpenAIServerModel` (Coder/Tester/agents) → OK moyennant le model_id

**Fichiers** : `graph_orchestrator/nodes.py` (`build_fast_model`/`build_reasoning_model`),
`agent_server/agents.py` (`build_model`).
```python
OpenAIServerModel(
    model_id=settings.fast_model_id,          # ex: "hf.co/unsloth/gemma-4-E4B..."
    api_base=settings.ollama_api_base,        # http://localhost:11434/v1
    api_key=settings.ollama_api_key,
)
```
**Statut** : ✅ fonctionnel contre `llama-server` (smolagents parle `/v1` OpenAI-compatible,
exactement ce qu'expose llama-server). **Un seul changement** : `model_id` doit devenir un **nom
de section du `models.ini`** router (ex. `gemma-4-e4b` / `gemma-4-12b`), pas un nom Ollama.
La config `_normalize_api_base()` (config.py:46-58) qui ajoute `/v1` reste **correcte** pour
llama-server.

### D. Health check `_check_ollama()` → CASSE

**Fichier** : `agent_server/app.py:77-85`.
```python
base = settings.ollama_api_base.rstrip("/").removesuffix("/v1")
urllib.request.urlopen(f"{base}/api/tags", timeout=2)   # ❌ endpoint Ollama-only
```
`/api/tags` est l'endpoint **natif Ollama** qui liste les modèles installés. `llama-server` ne l'a
pas — il expose **`/v1/models`** (OpenAI) et **`/health`**.
**Migration** : remplacer par `GET /health` (llama-server renvoie `{"status":"ok"}`) ou
`GET /v1/models`. Le champ `ollama_reachable` du `HealthResponse` (schemas.py:53) garde du sens
mais mérite un renommage (`llm_reachable`).

### E. Config & env vars — nommage + suffixe `/v1`

**Fichiers** : `graph_orchestrator/config.py` (Settings dataclass), `.env.example`, tous les
`tests/test_*.py` (fixtures avec `ollama_api_base=...`).
- Variables : `OLLAMA_API_BASE`, `OLLAMA_REASONING_API_BASE`, `OLLAMA_API_KEY` → Settings
  `ollama_api_base`, `ollama_reasoning_api_base`, `ollama_api_key`.
- **Pour llama-server** : les valeurs restent valides (`http://127.0.0.1:8080/v1`), mais :
  - le **nom** `ollama_*` devient trompeur (option : renommer en `llm_*` / `llama_*` — impact
    large : config, .env, ~10 fichiers de tests, agent_server) ;
  - `OLLAMA_REASONING_API_BASE` (endpoint séparé pour le modèle de raisonnement) **reste utile** :
    en router mode un seul `llama-server` sert les deux modèles via le champ `model`, donc on peut
    fusionner les deux `api_base` en une seule — **ou** garder deux si on lance deux `llama-server`
    séparés (un `--reasoning on`, un `--reasoning off`).

### F. `reasoning_content` vs `content` — lecture côté client

Avec `--reasoning on`, la pensée va dans **`message.reasoning_content`** et la réponse finale dans
**`message.content`** (§4).
- **DSPy** (`dspy.ChainOfThought`) lit `content` → ✅ il récupère directement la réponse finale
  propre (le reasoning est invisible pour DSPy, ce qui est **exactement** le comportement voulu :
  la CoT est interne, la sortie est le résultat structuré).
- **smolagents** (`OpenAIServerModel`) lit `content` → ✅ idem pour le Coder/Tester.
- **Si on veut logger/exposer le raisonnement** de l'Architect : il faut lire `reasoning_content`
  explicitement (post-traitement sur la réponse LM). Aider le fait
  (`remove_reasoning_content`/`format_reasoning_content` dans `references/aider/`) — réutilisable.

### G. Multimodal (vision) — `mmproj`

Ollama gère le projector vision **automatiquement** (blob `mmproj` dans le manifest, injecté au
lancement). `llama-server` nécessite `--mmproj <fichier>` **explicite** — déjà prévu dans
`models.ini` (§7F). Côté code (smolagents image input), **rien ne change** : l'API `/v1` accepte
les `image_url` de la même façon.

### H. Récap des modifications code nécessaires

| Fichier | Changement | Criticité |
|---------|-----------|-----------|
| `dspy_nodes.py` `_configure_dspy` | `ollama/`→`openai/`, garder `/v1`, retirer `think=` | 🔴 bloquant |
| `models.py:239` | `ollama_chat/`→`openai/`, garder `/v1` | 🔴 bloquant |
| `agent_server/app.py` `_check_ollama` | `/api/tags`→`/health` ou `/v1/models` | 🟠 casse le health |
| `config.py` + `.env.example` | `model_id` = section `models.ini` (pas nom Ollama) | 🟠 config |
| `config.py` Settings | (option) renommer `ollama_*`→`llm_*` | 🟡 cosmétique |
| `nodes.py` / `agents.py` | `model_id` = section `models.ini` | 🟠 config |
| tests `test_*.py` | fixtures `ollama_api_base` (si renommage) | 🟡 si renommage |
| logging `reasoning_content` | post-traitement LM (si exposé) | 🟢 optionnel |

> 💡 **Approche pragmatique** : garder les noms `ollama_*` (minimise le diff), juste changer les
> **valeurs** (`OLLAMA_API_BASE=http://127.0.0.1:8080/v1` vers le llama-server) + patcher les 3
> points bloquants (A, B, D). Le `models.ini` router se charge du reste (thinking par modèle,
> mmproj, auto-fit).

## 11. Verdict & recommandation de migration

### A. La migration est-elle faisable ?

**Oui**, techniquement. Les 3 points bloquants (§10 A/B/D) sont identifiés et localisés, le
`models.ini` est prêt, la recette thinking est validée (§4). L'effort code est borné (~3 fichiers
core + config + tests).

### B. Apporte-t-elle de meilleures perfs et gestion ?

**Gain réel mais ciblé — pas une évidence absolue.** À pondérer honnêtement :

#### ✅ Ce que la migration apporte réellement

1. **Le thinking — c'est LE gain décisif.**
   C'était le problème initial (l'Architect hangait ~23 min sous Ollama à cause du thinking forcé
   sur `/v1`). Avec `llama-server --reasoning on`, c'est **résolu et validé** : la pensée va dans
   `reasoning_content`, la réponse finale propre dans `content`, DSPy récupère directement le
   résultat structuré. C'est le bénéfice qui justifiait toute cette investigation.

2. **Contrôle fin de la VRAM.**
   `-ngl` réglable par modèle (32 max stable, auto-fit sinon), presets INI par modèle avec
   `reasoning`/`mmproj`/`n-gpu-layers`. Ollama fait de l'auto-fit aussi, mais on n'a pas la main
   dessus — là on peut tuner.

3. **Évite les bugs Ollama-spécifiques subis.**
   La liste blanche `think=True`, le thinking forcé sur `/v1` (cf. `debug/GAPS_TESTER_JUDGE.md`),
   le crash CUDA du QAT Google noyé dans Ollama. Hors Ollama, ces comportements disparaissent.

#### ⚖️ Ce qui est neutre (ne pas se faire d'illusions)

**Perf d'inférence brute : identique.** Ollama **est** llama.cpp en dessous — même moteur, mêmes
GGUF, même CUDA. Les ~7-11 tok/s mesurés sont les mêmes qu'on obtiendrait via Ollama sur le même
modèle. La migration n'accélère pas l'inférence, elle **débloque des fonctionnalités** (thinking) et
**donne du contrôle**, c'est tout.

#### ❌ Ce qui se dégrade ou reste à charge

1. **Robustesse opérationnelle : régression.**
   Ollama = service Windows persistant (auto-restart, toujours up). `llama-server` = process nu
   qui meurt en cas de crash et laisse le port mort. Il **faut** écrire/maintenir un wrapper
   (scheduled task ou service NSSM) pour égaler Ollama. C'est du travail réel, pas anecdotique.

2. **Maintenance du `models.ini`.**
   Les chemins de blobs (`sha256-0a270ec9…`) doivent être maintenus à la main. Un `ollama pull`
   qui change le digest casse le preset silencieusement. Ollama gère ça tout seul via ses manifests.

3. **Moins éprouvé en multi-modèles.**
   Le router mode de `llama-server` est récent ; le scheduler Ollama (éviction LRU, rechargement,
   partage VRAM) est mature. À valider en charge avant prod.

4. **Effort de migration code.**
   3 points bloquants (`dspy_nodes.py`, `models.py`, `app.py`), + config + tests. Pas énorme mais
   non négligeable, et ça touche le cœur du graphe (DSPy).

### C. Recommandation : migration progressive ciblée, pas big-bang

Plutôt que de tout basculer d'un coup :

1. **Garder Ollama pour le fast_model** (Coder/Router/Judge) — ça marche, c'est robuste, pas de
   gain à migrer.
2. **Migrer uniquement le nœud Architect vers `llama-server --reasoning on`** — c'est là que le
   thinking est critique et où Ollama bloque. On pointe `OLLAMA_REASONING_API_BASE` vers un
   `llama-server` dédié (preset §7F section `[gemma-4-12b]`), le reste sur Ollama.
3. **Valider en charge** le router mode avant d'envisager un bascule totale.

### D. Bilan

Faisable techniquement **oui**, gain réel sur le thinking/contrôle, mais **pas** une amélioration
de perf brute et ça demande un effort d'ops (daemon) + maintenance (blobs). Le bénéfice vaut le
coup **si** le thinking de l'Architect est important — ce qui est le cas vu l'audit (hang de 23 min
résolu). Pour le reste, Ollama reste très bien.

**Plan pragmatique retenu** :
- Étape 1 — `llama-server` dédié `--reasoning on` pour l'Architect (1 point de code à patcher :
  `_configure_dspy` sur la branche reasoning) ;
- Étape 2 — validation en charge (run Bubble Sort + comparatif latence/qualité vs Ollama) ;
- Étape 3 — si concluant, étendre au fast_model via le router `models.ini` + wrapper daemon.

