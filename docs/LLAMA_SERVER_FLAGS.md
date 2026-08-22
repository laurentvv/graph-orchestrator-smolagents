# Flags llama-server — Guide de décision pour l'intégration de nouveaux modèles

> Document de référence lié à [`AGENTS.md`](../AGENTS.md) (F-123, 2026-08-17). Source de
> vérité pour choisir les flags `llama-server` quand on ajoute ou change un modèle GGUF.
> Tout flag cité ici a été **mesuré sur notre matériel** (RTX 3060 Laptop 6 Go, CUDA 13,
> build b10509) ou sourcé des docs officielles llama.cpp/Qwen — pas copié d'exemples
> trouvés sur internet sans vérification (leçon `--spec-default`, cf. §4).

## 1. Où vivent les flags dans ce projet

Aucun flag n'est écrit en dur dans une commande shell : tout passe par `ModelSpec`
(`graph_orchestrator/config.py`) lu depuis le `.env`, puis assemblé par
`_build_cmd()` (`graph_orchestrator/llama_server.py`). Un nouvel modèle = un bloc
`.env` de rôle :

```
<PREFIX>_BACKEND=spawn          # spawn | external | none
<PREFIX>_MODEL=<chemin .gguf>   # blob exact
<PREFIX>_MMPROJ=<chemin .mmproj># vision (tous nos modèles sont multimodaux)
<PREFIX>_REASONING=on|off       # thinking via --reasoning
<PREFIX>_CONTEXT=49152          # -c
<PREFIX>_NGL=0                  # 0 = auto-fit (recommandé), sinon nombre forcé
<PREFIX>_FLASH_ATTN=auto        # auto | on | off
<PREFIX>_SPEC_MTP=false         # décodage spéculatif MTP (voir §3.1)
<PREFIX>_KV_QUANT=              # q8_0 | vide (= f16)
<PREFIX>_CACHE_REUSE=0          # 256 pour boucles agents multi-tours
<PREFIX>_TOP_K=20               # sampling Qwen officiel (0 = défaut serveur 40)
<PREFIX>_MIN_P=0                # sampling Qwen officiel (-1 = défaut serveur 0.05)
```

## 2. Config actuelle validée (2026-08-22)

| Rôle | Modèle | Flags actifs | Résultat mesuré |
|---|---|---|---|
| FAST (Coder, Router) | Qwen3.5-4B-MTP Q4_K_M | `cache-reuse 256`, **MTP off** | -10% préfill multi-tours ; MTP = **-42%** (acceptance 0,47) → proscrit |
| REASONING (Architect) | Ornith-1.5-9B Q4_K_M | **MTP off**, KV q8_0, ngl 99 | **1342 t/s prefill + 41 t/s gen** |
| REASONING_NO_THINK (Judge, Security, Tester…) | Ornith-1.5-9B Q4_K_M | idem | idem |

> ⚠️ **MTP PROSCRIT sur ce matériel (RTX 3060 Laptop 6 Go) — décision 2026-08-21.**
> Le bench F-123 qui validait MTP (+50 % tok/s) ne mesurait que la GÉNÉRATION courte,
> jamais le **préfill long** (charge réelle des nœuds 9B : Tester/Judge). Matrice
> préfill mesurée (4,5k tokens, b10549, cuda-13.3 = cuda-12.4 à ±10 % près) :
> `ngl99+kvq8` = **1308-1342 t/s** ; `ngl99+kvq8+MTP` = **84 t/s** (×16 plus lent —
> le contexte draft MTP fait déborder la VRAM 6 Go → offload CPU silencieux, le
> serveur démarre sans erreur) ; `auto+kvq8+MTP` = 497 t/s mais gen 7-11 t/s.
> Cause des runs lents 2026-08-21 (tester 80 s/step, run #6 47 min) : MTP+ngl99
> actif depuis le swap b10472. Symptôme reconnaissable : `common_fit_params:
> failed to fit params ... n_gpu_layers already set by user` + `12 ms per token`
> dans `prompt eval time`. → **REASONING_SPEC_MTP=false,
> REASONING_NO_THINK_SPEC_MTP=false** tant que 6 Go.

Build vendé : `vendor/llamacpp-cuda13/` (**b10549, CUDA 13.3** — monté depuis b10517
le 2026-08-21, validation post-swap : MTP compatible (+59 % en bench GEN court —
sans objet, MTP désactivé en prod), 8/8 tests flags ; cuda-12.4 testé identique en
prefill). Historique : b10509 ← b10472 (2026-08-20), b10517, b10549.
**Mise à jour** (releases
llama.cpp quasi-quotidiennes, veille hebdo programmée) :
`uv run python scripts/update_llamacpp.py` vérifie sans rien toucher (exit 2 si
nouvelle version) ; `--apply` télécharge build+cudart `cuda-13.3`, vérifie version ET
flags critiques avant le swap, garde 1 backup `.bak` (rollback = renommer). TOUJOURS
valider après `--apply` : `debug/test_mtp_spec.py --only reasoning` + tests. Driver
NVIDIA ≥ 580 requis pour CUDA 13.

## 3. Guide de décision par flag (nouveau modèle)

### 3.1 Décodage spéculatif MTP (`--spec-type draft-mtp`) — GROS GAIN potentiel

**Prérequis détectable en 10 secondes** : le GGUF doit contenir des couches MTP
(tenseurs `blk.N.nextn.*`). Si le log de spawn contient
`model has unused tensor blk.XX.nextn... -- ignoring` → le modèle est MTP-capable
mais le draft est **gaspillé** (c'est le diagnostic qui a ouvert F-123 : les couches
étaient là depuis le début, ignorées).

**Procédure** : `uv run python debug/test_mtp_spec.py --only <rôle>` fait l'A/B
complet (baseline vs `draft-mtp` vs `+KV q8_0`), vérifie la consommation des tenseurs
nextn et lit le taux d'acceptation dans le log (`draft acceptance = 0.70 ...`).

**Règles empiriques (mesurées chez nous + confirmées par Unsloth/mer.vin)** :
- Modèle **dense ≥ ~7B** avec acceptance ≥ ~0,6 → activer. L'acceptance dépend du
  domaine : raisonnement/code structuré = bon, texte créatif libre = moyen.
- **Petit modèle déjà rapide (≤ ~5B)** → ne PAS activer : le coût de vérification
  dépasse le gain (notre 4B : -42% à acceptance 0,47).
- `--spec-draft-n-max 2` sur les denses (notre 9B : 27,5 vs 25,6 t/s au défaut 3).
  MoE : garder 3. Tuner 1-6 si besoin.
- **NE PAS passer `--spec-default`** : il n'active QUE ngram-mod (pas le MTP !) ;
  empilé au draft il a mesuré **plus lent** chez nous (24,1 vs 25,6 t/s), cf. issue
  llama.cpp #24266. Piège : beaucoup d'exemples web le combinent avec draft-mtp.
- VRAM : le draft ajoute ses poids (~165 Mo sur un 9B) + son KV → sur 6 Go ça passe
  mais réduit la marge ; le KV du draft en `q8_0` atténue.
- Compatibilité prouvée chez nous avec `--mmproj` (vision) ET `--reasoning on`
  (bug #22867 corrigé dans les builds ≥ ~b10400 ; utiliser un build récent).

### 3.2 Quantization KV (`--cache-type-k/-v q8_0`)

- Divise ~2 la VRAM du KV → **gain net au grand contexte** sur 6 Go (réduit le spill
  WDDM, notre 9B passait par la mémoire partagée) ; **légère perte** au petit contexte
  (coût de déquant, tout tient déjà en VRAM).
- **Requiert Flash Attention** pour le V quantizé (`-fa on`, ou `auto` qui résout FA
  sur nos modèles — si le serveur refuse `-ctv q8_0`, c'est que FA n'est pas actif).
- Qualité : consensus (benchs NVIDIA forums/Reddit) = q8_0 quasi sans perte ;
  q4_0 dégrade. Ne pas descendre sous q8_0 pour du code.

### 3.3 Cache-reuse (`--cache-reuse 256`)

- Pour les **boucles agents multi-tours** (Coder smolagents) où le MILIEU de
  l'historique est réécrit entre deux tours (compaction F-101, résumés d'anciens
  steps) : sans ce flag, le cache de préfixe du slot est invalidé au premier token
  modifié ; avec, llama-server réutilise les chunks de queue via KV shifting.
- 256 = valeur des **presets officiels llama.cpp Qwen Coder** + reco particula.tech
  (juil. 2026) pour les agents ; 32-64 pour usage conversationnel simple.
- Mesuré : **-10% préfill** sur charge multi-tours simulée ; validé @ctx49152.
- ⚠️ **LIMITATION MULTIMODAL (constat 2026-08-19, F-126)** : llama-server loggue
  `cache_reuse is not supported by multimodal, it will be disabled` — dès qu'un
  `--mmproj` est attaché (notre Coder est multimodal), le flag est **silencieusement
  désactivé**. Le `-10%` préfill n'est donc PAS actif pour le Coder aujourd'hui ;
  il le reste pour tout rôle textuel sans mmproj.
- Non testé combiné à `spec_mtp` (nous : FAST seulement, sans MTP). À bencher si un
  jour on active les deux sur le même rôle (`debug/bench_prefill_flags.py`).

### 3.4 Offload GPU (`-ngl`)

- **0/auto-fit par défaut** (comportement Ollama) : s'adapte à la VRAM libre sans
  OOM. Sur Vulkan les gros blocs contigus OOM plus vite qu'en CUDA (leçon
  gemma-12B : -ngl 99 crash Vulkan, passe CUDA).
- Forcer (`REASONING_NGL=99`) seulement après bench `debug/optimize_gpu_layers_server.py`
  : sur RTX 3060 CUDA, ~11 t/s forcé vs ~8 t/s auto-fit (gemma-12B).

### 3.5 Incontournables non négociables (leçons de post-mortems)

- **`--parallel 1`** : sinon llama-server default n_slots=4 et réserve 4×n_ctx de KV
  (196k tokens de KV pour un 4B @49k !) → pression VRAM massive → crash marathon
  Coder (post-mortem run #4). Nos nœuds sont séquentiels, 1 slot suffit.
- **`--flash-attn auto`** : prérequis du KV V quantizé, accélère le préfill.
- Contexte par rôle calibré sur les mesures réelles : Coder **65536 + KV q8_0**
  (F-126, post-mortem run 2026-08-19_1552 : 49152 @f16 dépassé — deux réécritures
  complètes d'un gros fichier ont monté la requête à 54 115 tokens → 400
  exceed_context_size → run perdu ; 65536 @q8_0 consomme MOINS de VRAM KV que
  49152 @f16, cf. §3.2 ; 32768 = trop juste, leçon 2026-08-14).
- **Quant Q6_K dispo pour le Coder** (`debug/bench_q6_coder.py`, 2026-08-19) : le
  blob Qwen3.5-4B-Q6_K (3,64 Go vs 2,83 Go) **PASSE** aux flags production exacts
  (ctx 65536 + KV q8_0 + mmproj, chargé en 8,6 s, VRAM 4423 MiB — l'auto-fit
  délesté plus de layers sur CPU). Prix mesuré vs Q4_K_M : **-16,5% préfill**
  (1092 → 912 tok/s) et **-39% génération** (19,3 → 11,8 t/s) → un livrable
  complet de 12k tokens passe de ~10 à ~17 min. Levier qualité ponctuel
  (swap `FAST_MODEL` dans .env) si le Q4 reste trop faible en correction APRÈS
  les durcissements F-126 — pas un défaut recommandé.

## 4. Flags écartés — ne pas réessayer sans nouvelle preuve

| Flag | Raison du rejet (mesure ou source) |
|---|---|
| `--spec-default` | ngram-mod seul ; **mesuré plus lent** empilé au draft-mtp (24,1 vs 25,6 t/s) — issue #24266 |
| `--swa-full` | no-op sur Qwen3.5 hybride (Gated DeltaNet, pas SWA) ; ne concerne que Gemma 2/3 |
| `--kv-unified` | no-op à 1 slot (`--parallel 1`) |
| `--agent` | web-tools serveur + proxy CORS localhost : redondant avec nos MCP, note sécurité |
| `--mlock` / `--no-mmap` | **dépréciés** (remplacés par `--load-mode`) ; défaut mmap correct sous Windows |
| `-ub 1024/2048` | +2/+6% préfill seulement sur 8k tokens ; VRAM compute buffer en jeu → défaut 512 conservé |
| `xtc` / `dynatemp` / `top-n-sigma` | samplers "créativité" — contre-productifs pour du code déterministe |
| `--yarn` | extension de contexte ; nos ctx 8k-49k sont natifs |

## 5. Sujets qualité en réserve (à valider par run E2E, pas au bench)

- **Sampling serveur** — *adopté le 2026-08-18, validé par run E2E complet* : nos
  clients n'envoient que `temperature` → les défauts llama-server (`top_k 40,
  min_p 0,05`) s'appliquaient au reste. Recos officielles Qwen appliquées via
  `<PREFIX>_TOP_K=20` + `<PREFIX>_MIN_P=0` sur les 3 rôles (famille Qwen) ;
  `top_p` laissé au défaut serveur 0,95 (= reco thinking Qwen, sûr à basse
  température). Recos complètes Qwen si besoin : thinking `temp 0,6 / top_p 0,95 /
  top_k 20 / min_p 0` ; non-thinking `temp 0,7 / top_p 0,8 / top_k 20 / min_p 0`.
- **`--reasoning-preserve`** : conserve les traces thinking dans l'historique →
  stabilise le préfixe (évite le reprocessing complet à chaque tour sur modèles
  thinking multi-tours). Actuellement aucun rôle ne combine thinking ON + multi-tours
  (Coder = off, Architect = single-shot). À activer si ça change. Le serveur nous le
  suggère lui-même au chargement quand le template le supporte.
- **`--reasoning-budget N`** : piloter le budget thinking par rôle (utile si un
  modèle pense trop longtemps sur des tâches simples).

## 6. Méthodologie de bench (le protocole, pas juste les scripts)

1. **Détection MTP** : grep `nextn` dans le log de spawn → couches présentes mais
   ignorées = potentiel dormant.
2. **A/B avec flags production exacts** : `debug/test_mtp_spec.py` (MTP/KV) ou
   `debug/bench_prefill_flags.py` (préfill multi-tours) — ils rebuildent la commande
   de `_build_cmd`, pas une approximation.
3. **Lire l'acceptance** : ligne `draft acceptance = X (n accepted / m generated)` du
   log serveur — c'est LE prédicteur du gain MTP.
4. **Tester au contexte de production** (`--ctx 32768`), pas seulement petit : le
   comportement VRAM/spill change tout (KV q8 = perdant @8k, gagnant @32k+).
5. **Charger la vision + le mode reasoning du rôle** dans le bench (nos 3 rôles
   chargent tous un mmproj) — les incompatibilités MTP/vision ne se voient qu'ainsi.
6. Compléter par un **run E2E Bubble_Sort** avant tout merge (le bench ne prédit pas
   la qualité de génération).

## 7. Sources principales

- `llama-server --help` du build vendé (source finale des flags supportés) et
  `common/arg.cpp` du dépôt ggml-org/llama.cpp (sémantique exacte, ex. `--spec-default`).
- [docs/speculative.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md) ·
  [Qwen quickstart (sampling)](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html) ·
  [Unsloth MTP](https://unsloth.ai/docs/models/mtp) ·
  [mer.vin Qwen MTP](https://mer.vin/2026/05/run-qwen-3-6-mtp-in-llama-cpp-faster-local-inference-with-built-in-speculative-decoding/) ·
  [particula.tech — cache/reprocessing hybrides](https://particula.tech/blog/prompt-reprocessing-swa-hybrid-models-kv-cache).
- Historique interne : logs `logs/llama-server/mtp-test-*.log` et
  `prefill-bench-*.log`, événements DuckDB #1258 (diag) et #1383 (F-123).
