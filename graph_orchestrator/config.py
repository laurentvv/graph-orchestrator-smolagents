"""Configuration externalisée via fichier .env + valeurs par défaut.

Aucune nouvelle dépendance lourde : python-dotenv et pydantic sont déjà disponibles
(transitives de smolagents). On évite pydantic-settings pour ne pas surcharger le projet.

Usage :
    from graph_orchestrator.config import settings
    print(settings.fast_model_id)
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Charge un éventuel .env à la racine du projet. Par défaut (override=False), les
# variables d'environnement système PRIMENT sur .env — comportement attendu : les
# secrets vivent dans .env, les overrides ponctuels (CI, FRESH_START=1 au shell,
# tests) passent par l'env. L'ancien override=True écrasait l'env shell depuis .env,
# ce qui rendait `FRESH_START=1 uv run ...` inopérant (toujours repris depuis .env).
load_dotenv()

# Chemin par défaut de la base DuckDB du Knowledge Graph, ancré au paquet
# (résolu depuis graph_orchestrator/config.py → repo_root/data/). Indépendant du
# cwd : la DB reste au même endroit quel que soit le répertoire de lancement,
# et résiste au chdir du workflow dans le run output dir. Cohérent avec
# event_stream.py (DEFAULT_EVENT_DB_PATH) et runs_history.py (DEFAULT_HISTORY_DB_PATH)
# qui placent aussi leurs .duckdb dans data/. Override via KG_PATH dans .env.
DEFAULT_KG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "graph_orchestrator.db")


def _get_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    return int(raw) if raw else default


def _get_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    return float(raw) if raw else default


def _get_str(key: str, default: str) -> str:
    raw = os.getenv(key)
    return raw.strip() if raw and raw.strip() else default


# ==========================================
# Spécification d'un modèle (F-58 : backend-agnostique)
# ==========================================
# Chaque rôle du graphe (fast/reasoning/no_think) pointe vers un ModelSpec qui décrit
# COMMENT contacter le modèle. 3 backends possibles (détectés via FAST_BACKEND etc.) :
# - "spawn"    : GPU local, llama-server. Le graphe spawn/tue un process par nœud
#                (model_lifecycle). blob = chemin absolu du .gguf. reasoning on/off via flag.
# - "external" : endpoint déjà lancé (Ollama local, serveur distant, API cloud OpenAI/
#                OpenRouter). Le graphe ne spawn rien — il pointe vers api_base externe.
#                model = nom chez le provider (ex: "gpt-4o", "gemma-4-e4b" sur Ollama).
# - "none"/""  : pas de modèle (tests unitaires mockés). model_lifecycle = no-op.
# Tout est piloté par le .env (1 var par attribut, préfixe par rôle : FAST_, REASONING_,
# REASONING_NO_THINK_). Aucune dépendance à models.ini côté runtime (models.ini reste une
# doc/référence des chemins blobs, mais le code ne le lit plus).
@dataclass(frozen=True)
class ModelSpec:
    """Description complète d'un modèle pour un rôle du graphe."""
    backend: str = "none"          # "spawn" | "external" | "none"
    model: str = ""                # spawn: chemin .gguf ; external: nom provider ; none: ""
    reasoning: str = "off"         # spawn: "on"/"off" (flag --reasoning) ; external: ignoré
    mmproj: str = ""               # spawn: chemin .mmproj (vision) ; external: ignoré
    api_base: str = ""             # external: endpoint http(s) ; spawn: ignoré (port dyn)
    api_key: str = ""              # external: clé API ; spawn: ignoré ; none: ""
    context: int = 8192            # spawn: taille contexte (-c) ; external: ignoré
    # --- Offload GPU (F-58-bis : fix bridage 20% GPU) ---
    # Nombre de layers à offloader en VRAM (-ngl). 0 = AUTO-FIT (défaut, recommandé) :
    # llama.cpp mesure la VRAM libre et offload autant de layers que possible SANS OOM
    # (mécanisme common_fit_params). C'est la config "sûre" qu'utilise Ollama.
    # ATTENTION : -ngl ≥ modèle/VRAM → OOM au chargement (le backend Vulkan alloue par
    # gros blocs contigus). Sur gemma-12B / RTX 3060 6 Go (build Vulkan), -ngl 99 crash ;
    # -ngl 32 passe sur build CUDA mais OOM sur Vulkan. D'où auto-fit par défaut.
    # Benchmark debug/Gemma4_Thinking_Audit.md : auto-fit ~8 tok/s, -ngl 32 ~11 tok/s
    # (CUDA). Setter <PREFIX>_NGL (ex: REASONING_NGL=32) pour forcer si build CUDA.
    gpu_layers: int = 0
    # Flash Attention (--flash-attn) : accélère le préfill des longs contextes.
    # Défaut "auto" = laisse llama-server choisir selon le modèle.
    flash_attn: str = "auto"
    # --- Décodage spéculatif MTP (bench debug/test_mtp_spec.py 2026-08-17) ---
    # Les GGUF "-MTP" portent des couches nextn que llama-server IGNORE sans
    # --spec-type draft-mtp. Gain mesuré sur Ornith-9B @ctx32k/ngl99 : +13% spec
    # seul, +29% avec KV q8_0. RÉGRESSION sur Qwen-4B (-42%, acceptance 0,47) →
    # activer sur les rôles 9B (REASONING, REASONING_NO_THINK) UNIQUEMENT.
    spec_mtp: bool = False
    # Quantization KV cache (--cache-type-k/-v). Ex "q8_0" : divise ~2 la VRAM KV,
    # gain net au GRAND contexte (réduit le spill WDDM), légère perte au petit.
    # Vide = f16 (défaut llama-server).
    kv_quant: str = ""
    # Réutilisation de chunks KV via shifting (--cache-reuse N) quand le MILIEU du
    # prompt change entre deux tours (compaction F-101, résumés d'anciens steps) :
    # le cache de préfixe du slot est sinon invalidé au premier token modifié.
    # 256 = presets officiels llama.cpp Qwen Coder ; bench debug/bench_prefill_flags.py
    # 2026-08-17 : -10% préfill sur charge agent multi-tours (FAST @ctx49152 : OK).
    # 0 = off (défaut). NB : non testé combiné à spec_mtp (rôles 9B) — FAST only.
    cache_reuse: int = 0
    # --- Sampling serveur (défauts Qwen, validés run E2E 2026-08-18) ---
    # Nos clients n'envoient que temperature → les DÉFAUTS serveur s'appliquent au
    # reste (llama-server : top_k 40, min_p 0.05). Recos officielles Qwen : top_k 20,
    # min_p 0. top_p laissé au défaut serveur 0.95 (= reco thinking Qwen).
    # top_k 0 / min_p < 0 = ne pas passer le flag.
    top_k: int = 0
    min_p: float = -1.0


def _model_spec_from_env(prefix: str) -> ModelSpec:
    """Construit un ModelSpec depuis les vars d'env <PREFIX>_BACKEND/MODEL/REASONING/....

    prefix = "FAST" | "REASONING" | "REASONING_NO_THINK". Lit :
      <PREFIX>_BACKEND, <PREFIX>_MODEL, <PREFIX>_REASONING, <PREFIX>_MMPROJ,
      <PREFIX>_API_BASE, <PREFIX>_API_KEY, <PREFIX>_CONTEXT.
    Valeurs par défaut non-bloquantes (none) pour ne pas casser les helpers de test qui
    construisent Settings() sans ces vars.
    """
    backend = _get_str(f"{prefix}_BACKEND", "none").lower()
    # Rétro-compatibilité : si BACKEND n'est pas setté mais MODEL_ID l'est (ancienne config
    # Ollama/llama-server router), on déduit "external". Sinon "none".
    if backend == "none":
        legacy = _get_str(f"{prefix}_MODEL_ID", "")
        if legacy:
            backend = "external"
    return ModelSpec(
        backend=backend,
        model=_get_str(f"{prefix}_MODEL", ""),
        reasoning=_get_str(f"{prefix}_REASONING", "off").lower(),
        mmproj=_get_str(f"{prefix}_MMPROJ", ""),
        api_base=_normalize_api_base(_get_str(f"{prefix}_API_BASE", "")) if _get_str(f"{prefix}_API_BASE", "") else "",
        api_key=_get_str(f"{prefix}_API_KEY", ""),
        context=_get_int(f"{prefix}_CONTEXT", 8192),
        gpu_layers=_get_int(f"{prefix}_NGL", 0),
        flash_attn=_get_str(f"{prefix}_FLASH_ATTN", "auto").lower(),
        spec_mtp=_get_bool(f"{prefix}_SPEC_MTP", False),
        kv_quant=_get_str(f"{prefix}_KV_QUANT", "").lower(),
        cache_reuse=_get_int(f"{prefix}_CACHE_REUSE", 0),
        top_k=_get_int(f"{prefix}_TOP_K", 0),
        min_p=_get_float(f"{prefix}_MIN_P", -1.0),
    )


def _normalize_api_base(raw: str) -> str:
    """Normalise la base de l'API OpenAI-compatible.

    La variable d'env LOCAL_API_BASE pointe souvent vers l'hôte SANS le suffixe /v1. Or smolagents
    (client OpenAI) attend l'endpoint OpenAI-compatible, qui est sous /v1.
    Sans /v1, on obtient un 404 sur /chat/completions.
    On ajoute donc /v1 si manquant.
    """
    base = raw.rstrip("/")
    if not base.endswith("/v1"):
        base = base + "/v1"
    return base


@dataclass(frozen=True)
class Settings:
    """Paramètres du graphe, surchargeables par variables d'environnement."""

    # --- Connexion Modèle Local (endpoint OpenAI-compatible) ---
    local_api_base: str
    local_reasoning_api_base: str
    local_api_key: str

    # --- Tiering des modèles ---
    fast_model_id: str  # Fan-out (workers)
    reasoning_model_id: str  # Juge + Synthèse
    reasoning_max_tokens: int  # obligatoire pour Gemma (sinon finish_reason=length)
    fast_max_tokens: int  # obligatoire pour le Coder : un fichier HTML/CSS/JS complet
    # peut dépasser 2000 tokens ; sans max_tokens généreux, la génération est coupée
    # en plein milieu d'un tool_call JSON -> corruption du contenu du fichier.
    coder_temperature: float  # CRITIQUE pour le code : température basse (déterministe)
    # pour éviter la corruption aléatoire de la syntaxe. Le défaut serveur
    # est 1.0 (chat créatif) — inadapté au code. 0.2 = quasi-déterministe, idéal.

    # --- Robustesse (tolérance aux pauses d'un endpoint distant) ---
    # Timeout (secondes) d'un appel LLM. Au-delà, l'appel échoue (et peut être
    # retryé par smolagents). Sans timeout, un endpoint distant muet fige le
    # workflow indéfiniment (bug observé sur le serveur distant 10.201.12.50).
    llm_timeout_s: float

    # --- Règles métier ---
    judge_confidence_threshold: float  # seuil de qualité du juge
    worker_max_retries: int  # tentatives de parsing JSON

    # --- Vérification adversaire (§5) ---
    adversary_count: int  # nombre de sceptiques indépendants
    adversary_threshold: float  # fraction de sceptiques requise pour réfuter (>= 0.5)

    # --- Cycles de convergence (§5) ---
    max_iterations: int  # hard cap anti-boucle-infinie pour le mode exploration

    # --- Human-in-the-loop (§5) ---
    hitl_enabled: bool  # si True, checkpoint bloquant avant la synthèse
    hitl_nodes: str  # nœuds déclenchant le HITL (CSV, ex "synth") — routage stratégique

    # --- Knowledge Graph persistant (Phase 5) ---
    kg_path: str  # chemin du fichier DuckDB (défaut : data/graph_orchestrator.db ancré au paquet, ou ":memory:")

    # --- Mode de workflow ---
    workflow_mode: str  # "one_shot" (défaut) ou "exploration"

    # --- Observabilité / logs ---
    log_level: str  # verbosité des workers (LOW / MEDIUM / HIGH)

    # --- Reprise après crash (Priorité 3 : Checkpoints) ---
    # Si True, ignore tout checkpoint existant et repart de zéro (nouvelle exécution
    # fraîche même si le contenu de la tâche correspond à un run interrompu).
    fresh_start: bool

    # --- Boucle d'auto-correction (Priorité 2 : capture/troncature stderr) ---
    # Sans plafond, un gros traceback (500+ lignes) avalé à chaque itération fait
    # exploser le contexte du LLM ("Context Overflow") → la boucle diverge.
    # Voir graph_orchestrator/feedback_utils.py (truncate_output / truncate_history).
    test_timeout_s: int  # timeout d'un runner de tests en subprocess (pytest, etc.)
    stderr_head_lines: int  # lignes de tête à garder (l'erreur, en haut du log)
    stderr_tail_lines: int  # lignes de queue à garder (la cause racine, en bas)
    feedback_max_chars: int  # plafond global du feedback injecté au Coder

    # --- Cap steps du Web Tester (optimisation durée, fix TIMINGS_ANALYSE) ---
    # Plafond de max_steps pour le WebTestRunner (ToolCallingAgent Puppeteer). Le défaut
    # historique (24) laissait le modèle boucler jusqu'à 10 steps sur une friction JS
    # (ex: `document.querySelector` écrasé par assignation) sans jamais final_answer —
    # ~30 min perdues. Le verdict est généralement clair à 10-12 steps (smoke-test +
    # 2-4 assertions fonctionnelles). Baisser à 12 borne la durée sans perte de
    # couverture. Opt-out : TESTER_MAX_STEPS plus haut si les assertions le nécessitent.
    # Valeur par défaut dans la dataclass : évite de casser les helpers de test qui
    # construisent Settings(...) à la main (même convention que loop_guard_threshold etc.).
    tester_max_steps: int = 8
    # Hard deadline wall-clock du Web Tester (smolagents ToolCallingAgent + MCP Puppeteer/
    # DevTools). Fix blocage : sans ce timeout, un appel MCP bloquant (Chrome hung, npx stdio
    # deadlock, page JS en boucle infinie) fige le Tester indéfiniment. À l'expiration,
    # run_with_retry rend un échec propre (None) → le Judge enchaîne. 0 = désactivé (legacy).
    # Si non setté, fallback sur test_timeout_s (rétro-compatibilité). Défaut 120 dans la
    # dataclass pour ne pas casser les helpers de test qui construisent Settings() à la main.
    # 480s (8 min) = FILET anti-MCP-hung, pas le binding. Règle : max_steps (8) × t/step
    # (~55s pire cas 9B+DevTools = 440s) DOIT gagner la course contre le wall-clock pour que
    # le Tester converge (auto-final-answer) au lieu de timeout. Runs 2026-08-11 : à 12 steps
    # le wall-clock (360s puis 600s) gagnait toujours → timeout systématique sans verdict.
    tester_timeout_s: int = 480

    # --- Inline des resources de skill pour le Tester (F-97 / MA-5) ---
    # Résout la progressive disclosure F-92 côté serveur : inline les resources/*.md
    # directement dans le bloc injecté. Sans cela, le stub SKILL.md ordonne au Tester
    # de lire chaque resource via read_file → 5 steps perdus sur 8 (diagnostiqué runs
    # e2e_f90_validation_run3/4 : 0 navigate_page, 0 assertion). Opt-out rare :
    # TESTER_INLINE_SKILL_RESOURCES=false pour revenir au comportement F-92 (lazy).
    tester_inline_skill_resources: bool = True

    # --- Cap steps du Coder (post-mortem run coding_d72dc8e36445c4b6, F-61) ---
    # max_steps du CodeAgent Coder. Le défaut historique (25 hardcoded) laissait le
    # modèle boucler jusqu'à 87 steps (observé : 80 min, 18M tokens → crash serveur
    # llama.cpp par saturation). Le Coder produit typiquement en 6-14 steps (baseline
    # Bubble Sort one-shot, audit_coder ~10 steps). 18 laisse une marge vs 25 sans
    # brider les cas nominaux ni laisser diverger un modèle qui boucle. Opt-out :
    # CODER_MAX_STEPS plus haut pour une tâche complexe nécessitant plus d'allers-
    # retours outils. Valeur par défaut dans la dataclass (convention tester_max_steps).
    coder_max_steps: int = 30
    # Circuit-breaker sur tours idle consécutifs (post-mortem idem). _detect_idle_step
    # (F-33) réinjecte un message à chaque tour "sans appel d'outil" mais ne coupe
    # JAMAIS → le Coder peut enchaîner N tours idle jusqu'à épuisement des steps
    # (l'anti-loop crypto F-36 ne déclenche pas : pas de tool call = pas de fingerprint).
    # Ce seuil borne le nombre d'idles consécutifs tolérés avant échec définitif propre.
    # 3 = tolère 2 ratées (réflexion légitime) puis coupe à la 3e (boucle avérée).
    idle_breaker_threshold: int = 3

    # --- Nœud d'Escalade (Priorité 3 : post-mortem sur circuit breaker) ---
    # Quand une sous-tâche épuise le Circuit Breaker (3 itérations toutes rejetées),
    # un nœud DSPy synthétise les réfutations accumulées en un diagnostic post-mortem
    # (cause racine + leçon), le persiste dans le KG (kind="escalation"). Si False,
    # on retombe sur le comportement historique : la sous-tâche sort avec le statut
    # brut "max_iterations_reached" sans diagnostic. Opt-out utile pour A/B ou tests.
    # Valeur par défaut dans la dataclass : évite de casser les helpers de test qui
    # construisent Settings(...) à la main à chaque ajout de champ (load_settings()
    # passe toujours la vraie valeur lue depuis l'env en production).
    escalation_enabled: bool = True

    # --- Auto-Résolution des Dépendances (Priorité 5 : Tester Python) ---
    # Quand le PythonTestRunner détecte un `ModuleNotFoundError` dans le stderr, il
    # installe lui-même le package manquant (`pip install`, non-persistant) puis
    # relance les tests — au lieu de gaspiller un cycle LLM pour ça. Si False, on
    # retombe sur le comportement historique (échec immédiat, feedback au Coder).
    # Opt-out utile en environnement verrouillé (CI sans réseau, sandbox stricte).
    # Valeur par défaut dans la dataclass : même raison que escalation_enabled
    # (évite de casser les helpers de test qui construisent Settings(...) à la main).
    auto_install_deps: bool = True

    # --- Anti-Loop Cryptographique (Priorité 3 : circuit-breaker par hash) ---
    # Détecte quand un agent (Coder) répète EXACTEMENT le même tool call (même
    # outil + mêmes arguments, hashés en SHA256) plusieurs fois de suite — le
    # failure mode "tourne en rond" qui brûle des tokens sans progresser.
    # Inspiré de Crush. Si `loop_guard_threshold` répétitions sont atteintes,
    # `run_with_retry` interrompt l'agent avec un message pédagogique au lieu de
    # le laisser boucler. Seuil 3 = un humain ne refait jamais 3x le même appel
    # identique sans boucler. Opt-out utile pour A/B ou debug.
    loop_guard_enabled: bool = True
    loop_guard_threshold: int = 3

    # --- Stall Detector (Priorité 3-bis / F-88) ---
    # Complément de l'Anti-Loop F-36 : détecte (a) un même CONTENU réécrit (hash
    # d'output identique — le cas que F-36 rate car il ne hashe que l'input), et
    # (b) une série de turns sans livrable matériel nouveau (PROGRESS/IDLE).
    # Inspiré de loopx (fiche 19 : recent_runs, pr_monitor_materialization,
    # delivery_outcome). Seuil 2 = loopx MONITOR_DEBT_UNCHANGED_TURN_THRESHOLD
    # (1 tour gratuit est légitime = réflexion/relecture, 2 = stall avéré). Opt-out
    # `STALL_DETECTOR_ENABLED=0` pour A/B ou debug.
    stall_detector_enabled: bool = True
    stall_detector_threshold: int = 2

    # --- Goal Enforcement (Priorité 3-ter / F-99) ---
    # Garde comportementale du faux « j'ai fini » (qm goal.ts) : un final_answer
    # valide est audité contre l'état autoritaire (écritures + livrables sur
    # disque + verify-after web). Non prouvé → prompt de continuation (« treat
    # completion as unproven ») ; MÊME impasse `goal_blocked_min_rounds` rounds
    # → statut blocked accepté (le Judge arbitre — calibré sur worker_max_retries=3,
    # miroir du GOAL_BLOCKED_MIN_ROUNDS=3 de qm) ; `goal_waiver_stalled_rounds`
    # rounds de continuation sans AUCUN tool call → auto-waiver anti-deadlock ;
    # `goal_token_cap` tokens cumulés (in+out) → wind-down unique, jamais fausse
    # complétion (0 = désactivé). Opt-out `GOAL_ENFORCEMENT_ENABLED=0`.
    goal_enforcement_enabled: bool = True
    goal_blocked_min_rounds: int = 3
    goal_waiver_stalled_rounds: int = 5
    goal_token_cap: int = 2_000_000

    # --- Judge Grounding (Priorité 6 / F-93) ---
    # Anti-hallucination de localisation : après le verdict LLM, chaque finding est
    # ancré dans le code source (alignement flou de tokens, port simplifié du
    # WordAligner de langextract). Les findings non ancrés (ligne inexistante ou
    # fragment inventé) sont rétrogradés d'un cran + flagués ``[ungrounded]`` —
    # ``is_approved`` inchangé (politique non-destructive : calibrage d'abord, le
    # taux de faux positifs sera mesuré par le Meta-Analyste P15 avant toute
    # automation du verdict). Opt-out ``JUDGE_GROUNDING_ENABLED=0`` pour A/B/debug.
    judge_grounding_enabled: bool = True

    # --- Judge fail-closed TEST (post-mortem run #3 / F-99-bis) ---
    # Un verdict de test FAILURE/timeout/absent ne peut PLUS être approuvé par le
    # LLM Judge (run #3 2026-08-14 : approbation d'une app à animation instantanée
    # et compteur mort malgré le verdict failure du Tester — le prompt disait déjà
    # de sanctionner, le 9B l'a ignoré, doctrine F-33 : gate logicielle). La gate
    # court-circuite le LLM (is_approved=False + feedback au Coder pour itérer).
    # Opt-out JUDGE_RESPECT_TEST_FAILURE=false pour A/B/debug.
    judge_respect_test_failure: bool = True

    # --- Visual Audit matérialisé (F-109, post-mortem run #5) ---
    # Le 4B déclarait « all N criteria verified » sans écrire l'analyse, puis le
    # Tester trouvait un crash. L'outil visual_check matérialise l'audit critère
    # par critère et final_answer est BLOQUÉ si la checklist est incomplète,
    # contient un verdict False, ou des observations creuses. Opt-out
    # VISUAL_AUDIT_ENABLED=false (et 0 critère F-90 = gate inactive).
    visual_audit_enabled: bool = True

    # --- Cap fullPage des screenshots (F-114, post-mortem run #9) ---
    # Le Coder appelle take_screenshot(fullPage=True) → images de plusieurs
    # milliers de pixels de haut (jusqu'à 1265×9315 observés run #9) → prompt
    # processing vision de plusieurs minutes → Request timed out (600 s) qui a
    # tué une tentative entière. Le wrapper vision force fullPage=False (clés
    # déjà présentes uniquement). Opt-out VISION_FULLPAGE_CAP=false.
    vision_fullpage_cap: bool = True

    # --- Coder Ultra (F-111, post-mortem run #7) ---
    # La CORRECTION (itération > 1) utilise le gros modèle SANS thinking
    # (no_think_spec = Ornith-9B) au lieu du 4B rapide : le 4B exécute mais ne
    # corrige pas (run #7 : 3 itérations mortes à max_steps sur le même bug de
    # compteur). La création (it. 1) reste sur le 4B. Opt-out
    # CODER_ULTRA_CORRECTION=false pour A/B/debug.
    coder_ultra_correction: bool = True

    # --- Checkpoint git par itération (F-102, port open-swe turn_checkpoint) ---
    # Snapshot du worktree au DÉBUT de chaque itération Coder SANS contaminer
    # HEAD/index/worktree (GIT_INDEX_FILE scratch + update-ref refs/graph-
    # orchestrator/turns/<key>). Le Judge reçoit un résumé structuré « ce que
    # git dit » (statut +ajouts/-suppressions par fichier), complément du diff
    # texte F-53 — et disponible dès l'itération 1. Opt-out
    # TURN_CHECKPOINT_ENABLED=false (retour au comportement F-53 seul).
    turn_checkpoint_enabled: bool = True

    # --- Matérialisation du plan (F-120, transposition planning-with-files) ---
    # Écrit plan.md (miroir fidèle de TOUT l'ArchitectOutput : architecture
    # globale, sous-tâches, stratégie/sections, checklist fichiers, critères
    # F-82, skills) + task.md (checklist vivante + journal des verdicts) dans
    # le dossier du run, régénérés à chaque transition par workflows.py
    # (déterministe, best-effort). Un anchor court stable est aussi injecté
    # dans le prompt Coder à chaque itération (levier de convergence 4B des
    # post-mortems #10/#11). Opt-out PLAN_TASK_MATERIALIZE=false (retour :
    # aucun fichier ni anchor). Défaut dataclass True pour ne pas casser les
    # helpers de test qui construisent Settings() à la main.
    plan_task_materialize: bool = True

    # --- Retry transport LLM v2 (Priorité 8 / F-104) ---
    # Retry PRÉ-CONTENU au niveau de l'APPEL LLM (openfox) : un « Connection
    # error » transitoire est rejoué à l'identique, de façon transparente pour
    # l'agent (rien n'entre dans l'historique — vs run_with_retry qui purge
    # toute la mémoire du nœud). Backoff exponentiel + jitter 25 % + cap 30 s
    # + retry-after prioritaire (opencode). `llm_transport_retries` sert
    # AUSSI de num_retries litellm côté nœuds DSPy. Si le serveur spawné est
    # mort mid-run (crash VRAM), il est re-spawné entre 2 tentatives (revive).
    # Opt-out LLM_RETRY_ENABLED=0 (retour : exception → run_with_retry seul).
    llm_retry_enabled: bool = True
    llm_transport_retries: int = 5
    llm_retry_base_delay_s: float = 1.0
    llm_retry_max_delay_s: float = 30.0
    llm_retry_jitter: float = 0.25

    # --- Compaction v2 (Priorité 9 / F-101, opencode + s08 + pi) ---
    # Archive disque perte-zéro : steps snippés → .transcripts/*.jsonl + gros
    # tool outputs → .task_outputs/tool-results/ (dossier du run, cwd F-40).
    # Opt-out COMPACTION_ARCHIVE_ENABLED=0 (retour : marqueur texte seul).
    compaction_archive_enabled: bool = True
    # Garde overflow pi §3.9 dans run_with_retry : UNE SEULE récupération de
    # contexte débordé par exécution de nœud ; un second overflow → échec
    # propre immédiat (plus de retries brûlés sur une requête incompressible).
    # Opt-out COMPACTION_OVERFLOW_GUARD=0.
    compaction_overflow_guard: bool = True

    # --- Init MCP non bloquante (Priorité 8 / F-104, crush) ---
    # Timeout de connexion PAR SERVEUR (un serveur npx pendu ne bloque jamais
    # le run) : chrome-devtools / context7 / puppeteer. Timeout → dégradation
    # gracieuse (le nœud tourne sans ces outils). Défauts calés sous le
    # connect_timeout=30 de mcpadapt pour rester l'autorité de borne.
    chrome_devtools_connect_timeout_s: float = 25.0
    context7_connect_timeout_s: float = 15.0
    puppeteer_connect_timeout_s: float = 25.0

    # --- Consolidation mémoire KG (Priorité 6-ter / F-68 Phase 1) ---
    # Le KG DuckDB grossit indéfiniment : dedup_key ne capte que les doublons
    # EXACTS, et rien n'oublie jamais. La consolidation (LLM-juge qm émettant
    # UPDATE/DELETE/ADD sur claims numérotés) déduplique/fusionne les réfutations
    # rabâchées à la fin d'un run. `memory_consolidation_after` = seuil minimal
    # de claims par entité pour déclencher un appel LLM (qm DEFAULT_CONSOLIDATE_AFTER
    # = 10 — en dessous, pas assez de matière pour consolider). `memory_retention_days`
    # = oubli par rétention temporelle (prune des claims obsolètes, préserve
    # escalation+insight = leçons durables). Opt-out `MEMORY_CONSOLIDATION_ENABLED=0`.
    memory_consolidation_enabled: bool = True
    memory_consolidation_after: int = 10
    memory_retention_days: int = 30

    # --- Mémoire cross-run recall (Priorité 6-ter / F-68 Phase 2) ---
    # Rappelle en DÉBUT de run les N leçons durables (insight+escalation) les plus
    # récentes de TOUS les runs passés — ce sont celles qui ont survécu à l'oubli
    # (prune_old_claims préserve escalation+insight). Injectées dans le prompt
    # Coder pour fermer la boucle d'apprentissage. Déterministe (0 LLM, 1 query
    # SQL). `memory_recall_limit` = top-N par récence (qm recall = last RECALL_MAX_CHARS
    # du notebook ; ici on borne par compte, plus prévisible sur 9B). `memory_recall_
    # max_chars` = budget caractères du bloc injecté (défense anti-saturation contexte).
    # Opt-out `MEMORY_RECALL_ENABLED=0` (A/B ou debug).
    memory_recall_enabled: bool = True
    memory_recall_limit: int = 8
    memory_recall_max_chars: int = 1500

    # --- Sanitizer (Auto-typage, Priorité 8 / F-42) ---
    # Coerce best-effort les arguments d'outil malformés émis par un petit LLM
    # (ex: `"1, 80"` → `80` pour un champ integer) AVANT l'appel d'outil, pour
    # éviter les retries gaspillés sur les erreurs de validation de type.
    # Déterministe, 0 LLM. Opt-out `SANITIZER_ENABLED=0` pour A/B ou debug.
    sanitizer_enabled: bool = True

    # --- Read-Before-Write Gate (Priorité 1 / F-66) ---
    # Middleware qui bloque write_file / search_replace / edit_file / multi_replace /
    # append_file sur un fichier EXISTANT dont le contenu n'a pas été lu (hash SHA256).
    # Inspire de Deer Flow (issue #3857). Mode Strict : un write réussi invalide la
    # mark de lecture → force re-read avant chaque édition (corrige le bug « édition
    # à partir d'une représentation mentale stale »). Fail-open garanti (fichier
    # absent = création OK, read impossible = on laisse passer). Opt-out pour debug.
    read_before_write_enabled: bool = True

    # --- Robustesse FS : verrous + transactions + cloisonnement IO (Priorité 8-bis / F-95) ---
    # Port OpenKB (fiche 32). Trois couches complémentaires, chacune opt-out :
    # 1. run_dir_lock : verrou exclusif CROSS-PROCESS sur le dossier du run
    #    (<run>/.fs_tx/dir.lock) — deux process ne peuvent pas muter le même
    #    run (ex: deux reprises du même checkpoint lancées en parallèle). La
    #    première acquisition exclusive DRAINE les journaux de transaction
    #    actifs (crash-recovery).
    # 2. fs_transactions : snapshot+journal autour de chaque appel Coder — un
    #    process mort mi-écriture laisse un journal "active" roulé back au
    #    prochain run (annulation des effets partiellement appliqués, complète
    #    l'idempotence F-43).
    # 3. io_allowlist : les outils FS du Coder (write/read/edit/list) sont
    #    confinés au dossier du run (allowlist de chemins, Windows-safe) — le
    #    Coder ne peut plus écrire dans l'usine qui l'héberge. Fail-open hors
    #    run (aucune racine enregistrée = tout passe).
    run_dir_lock_enabled: bool = True
    fs_transactions_enabled: bool = True
    io_allowlist_enabled: bool = True

    # --- Skills : sélection par l'Architect + budget tokens (Priorité 10, F-57) ---
    # L'Architect sélectionne les skills pertinents dans son plan (subtask.skills),
    # et le Coder reçoit leur corps complet. Ce budget plafonne la sélection pour
    # éviter la saturation du contexte (32k sur Qwen 9B). Défaut 8000 tokens (~24%).
    # Conservé pour la rétro-compatibilité (désormais piloté par ALWAYS_SKILLS_CODER).
    # budget_tokens = 16000 pour allouer jusqu'à ~50% du contexte de Qwen (32k) aux skills.
    skill_budget_tokens: int = 16000

    # --- Skill Finder (F-82) : recherche/install auto de skills depuis skills.sh ---
    # Active l'étape ReAct de l'Architect qui interroge skills.sh (CLI `npx skills`)
    # pour combler une lacune de compétence. Défaut True (toujours ON) — opt-out
    # SKILL_FINDER_ENABLED=false pour A/B/debug (skip le coût LLM+npx+réseau).
    skill_finder_enabled: bool = True
    # Allowlist d'auteurs de confiance (CSV) — hard gate du téléchargement (spec
    # F-82 « n'autoriser que les auteurs de confiance »). Complétée par les
    # marqueurs skills.sh (safe/verified → info ; unsafe/malicious → blocage).
    # Miroir de skill_finder.DEFAULT_TRUSTED_AUTHORS (duplication assumée pour
    # éviter un import croisé config↔skill_finder).
    skill_finder_trusted_authors: str = "vercel-labs,anthropics,openai,github,microsoft,google-labs-code,clerk,greensock,gamedev-skills,elevenlabs,omer-metin"

    # --- Guard bash denylist (Priorité 8-bis : robustesse runtime) ---
    # `bash_command` exécute des commandes issues du LLM via shell=True. Un guard
    # denylist bloque les commandes destructrices (rm -rf /, format, mkfs, dd vers
    # un disque, shutdown, git push --force...) AVANT le subprocess. C'est le
    # premier pas vers la robustesse runtime (la sandbox Docker complète reste un
    # chantier séparé). Opt-out utile pour les environnements de confiance.
    # Valeur par défaut True : on sécurise par défaut (fail-safe).
    bash_guard_enabled: bool = True

    # --- Redaction de secrets (F-105, P8-bis) ---
    # Remplace les secrets reconnaissables (API keys, tokens, passwords littéraux,
    # clés privées PEM) par <REDACTED> dans le feedback injecté au LLM (point de
    # branchement : feedback_utils.truncate_output, même doctrine que F-21 : la
    # redaction s'applique à la LECTURE, DuckDB garde l'intégral pour l'audit).
    # Fail-open documenté : un secret non reconnu passe ; du code n'est jamais
    # corrompu. Opt-out pour diagnostiquer un feedback "masqué".
    redaction_enabled: bool = True

    # --- DevTools Coder (F-90, séparation Coder/Test) ---
    # Le Coder dispose par défaut de Chrome DevTools pour son auto-validation
    # (F-45) : navigate_page + list_console_messages lui donnent un feedback
    # critique pour corriger ses bugs de structure HTML/CSS (CSS fusionné,
    # balise non fermée...). Désactivé (false) = Coder générateur pur, mais
    # régression qualité observée (bug CSS fusionné 2026-08-09). On garde ON.
    # Opt-out possible pour debug : CODER_DEVTOOLS_ENABLED=false.
    coder_devtools_enabled: bool = True

    # --- Nœud PromptRefiner (meta-prompt avant l'Architect) ---
    # Un nœud DSPy (gemma REASONING) reformule le prompt utilisateur brut en spec structurée
    # AVANT l'Architect, inspiré du pattern "Enhance Prompt" (Kilo Code / Cline / Roo Code).
    # Connaît le catalogue des capacités (skills + statut Context7 + testers) pour orienter la
    # spec. Si False, l'Architect reçoit le prompt brut tel quel (comportement historique).
    # Opt-out utile si la latence du nœud supplémentaire n'est pas acceptable.
    prompt_refiner_enabled: bool = True

    # --- Modèle dédié pour le PromptRefiner (optionnel) ---
    # DORMANT depuis la migration 2026-08-10 (fix/prompt-refiner-fast-spec). PromptRefiner
    # utilise désormais settings.fast_spec (Qwen3.5-4B, comme le Coder) — la reformulation
    # d'un prompt est une tâche légère qui ne justifie pas un 9B raisonneur ni un serveur
    # gemma séparé. Ce champ reste lu par load_settings (rétro-compat .env) mais n'est plus
    # consommé par execute_prompt_refiner_node. Conservation = ne pas casser les .env existants.
    prompt_refiner_model_id: str = ""

    # --- Modèle reasoning SANS thinking (F-58, migration llama-server) ---
    # Pour les nœuds think=False (Judge/Security/Escalation/WebTester/Consolidation) : même
    # modèle costaud que l'Architect MAIS sans le thinking (plus rapide, pas de budget gaspillé
    # en raisonnement sur des tâches de verdict/classification). En production llama-server,
    # pointe vers la section models.ini `reasoning = off` (ex: "gemma-4-12b-nothink").
    # Si vide (défaut), fallback sur reasoning_model_id (rétro-compatibilité et tests
    # qui construisent Settings() à la main — ne pas casser).
    reasoning_no_think_model_id: str = ""

    # --- Specs modèles backend-agnostiques (F-58 : spawn llama-server vs external/cloud) ---
    # Chaque rôle pointe vers un ModelSpec (backend + blob/model + reasoning + mmproj +
    # api_base + api_key). Piloté par le .env : FAST_BACKEND/FAST_MODEL/..., REASONING_*,
    # REASONING_NO_THINK_*. Si les vars BACKEND ne sont pas settées, backend="none" →
    # model_lifecycle no-op (rétro-compat : on utilise les *_model_id + local_api_base).
    fast_spec: ModelSpec = field(default_factory=ModelSpec)
    reasoning_spec: ModelSpec = field(default_factory=ModelSpec)
    no_think_spec: ModelSpec = field(default_factory=ModelSpec)

    # --- Logs de run auto-capturés (Priorité 13-bis : journalisation) ---
    # Répertoire où chaque run écrit son log stdout/stderr via un Tee (run_logging.py).
    # Fini la redirection manuelle (> logs/...log) et le chemin hardcodé dans run_analyzer.
    # Gitignoré par défaut (cf. .gitignore). Accepte un chemin relatif (logs) ou absolu.
    logs_dir: str = "logs"
    # Active/désactive la capture du log. Opt-out pour A/B ou debug (LOG_TO_FILE=0).
    log_to_file: bool = True

    # --- Output daté par run (Priorité 13 : isolation des artefacts) ---
    # Racine du dossier où chaque run écrit ses fichiers générés. Le workflow coding crée un
    # sous-dossier daté `runs/YYYY-MM-DD_HHMM_slug/` et s'y chdir avant les nœuds Coder/Tester,
    # au lieu de polluer la racine du projet. Le chemin du run est persisté dans le checkpoint
    # (DuckDB) pour que la reprise après crash reprenne dans le MÊME dossier (fichiers préservés).
    # Accepte un chemin relatif (résolu en absolu au runtime) ou absolu. Défaut "runs".
    output_dir: str = "runs"
    # Nombre de runs à conserver pour éviter que le dossier ne grossisse indéfiniment.
    # 0 = désactivé (conservation infinie).
    output_retention: int = 10

    # --- Idempotence des effets de bord (Priorité 8-bis : replays/retries) ---
    # Si True, un store d'idempotence (backing DuckDB) garantit que les effets de
    # bord non-idempotents (append_file, pip install) ne sont appliqués qu'UNE
    # FOIS par run_id — même après un replay de checkpoint (reprise après crash).
    # Inspiré de qm (idempotency-store.ts). Opt-out pour A/B/debug.
    idempotence_enabled: bool = True
    # Rétention des records d'idempotence en jours (défaut 14, aligné sur qm).
    idempotency_retention_days: int = 14


def load_settings() -> Settings:
    """Construit les settings depuis l'environnement (avec valeurs par défaut)."""
    return Settings(
        local_api_base=_normalize_api_base(
            _get_str("LOCAL_API_BASE", "http://localhost:8000/v1")
        ),
        local_reasoning_api_base=_normalize_api_base(
            _get_str("LOCAL_REASONING_API_BASE", _get_str("LOCAL_API_BASE", "http://localhost:8000/v1"))
        ),
        local_api_key=_get_str("LOCAL_API_KEY", "sk-local"),
        fast_model_id=_get_str("FAST_MODEL_ID", "Qwen3.5-9B-Q4_K_M"),
        reasoning_model_id=_get_str(
            "REASONING_MODEL_ID",
            "hf.co/protoLabsAI/Ornith-1.0-9B-MTP-GGUF",
        ),
        reasoning_max_tokens=_get_int("REASONING_MAX_TOKENS", 8192),
        fast_max_tokens=_get_int("FAST_MAX_TOKENS", 12000),
        coder_temperature=_get_float("CODER_TEMPERATURE", 0.2),
        llm_timeout_s=_get_float("LLM_TIMEOUT_S", 600.0),
        judge_confidence_threshold=_get_float("JUDGE_CONFIDENCE_THRESHOLD", 0.7),
        worker_max_retries=_get_int("WORKER_MAX_RETRIES", 3),
        adversary_count=_get_int("ADVERSARY_COUNT", 3),
        adversary_threshold=_get_float("ADVERSARY_THRESHOLD", 0.5),
        max_iterations=_get_int("MAX_ITERATIONS", 3),
        hitl_enabled=_get_bool("HITL_ENABLED", False),
        hitl_nodes=_get_str("HITL_NODES", "synth"),
        kg_path=_get_str("KG_PATH", DEFAULT_KG_PATH),
        workflow_mode=_get_str("WORKFLOW_MODE", "one_shot"),
        log_level=_get_str("LOG_LEVEL", "LOW"),
        fresh_start=_get_bool("FRESH_START", False),
        test_timeout_s=_get_int("TEST_TIMEOUT_S", 120),
        tester_timeout_s=_get_int("TESTER_TIMEOUT_S", 480),
        stderr_head_lines=_get_int("STDERR_HEAD_LINES", 20),
        stderr_tail_lines=_get_int("STDERR_TAIL_LINES", 20),
        feedback_max_chars=_get_int("FEEDBACK_MAX_CHARS", 2000),
        tester_max_steps=_get_int("TESTER_MAX_STEPS", 8),
        tester_inline_skill_resources=_get_bool("TESTER_INLINE_SKILL_RESOURCES", True),
        coder_max_steps=_get_int("CODER_MAX_STEPS", 30),
        idle_breaker_threshold=_get_int("IDLE_BREAKER_THRESHOLD", 3),
        escalation_enabled=_get_bool("ESCALATION_ENABLED", True),
        auto_install_deps=_get_bool("AUTO_INSTALL_DEPS", True),
        loop_guard_enabled=_get_bool("LOOP_GUARD_ENABLED", True),
        loop_guard_threshold=_get_int("LOOP_GUARD_THRESHOLD", 3),
        stall_detector_enabled=_get_bool("STALL_DETECTOR_ENABLED", True),
        stall_detector_threshold=_get_int("STALL_DETECTOR_THRESHOLD", 2),
        goal_enforcement_enabled=_get_bool("GOAL_ENFORCEMENT_ENABLED", True),
        goal_blocked_min_rounds=_get_int("GOAL_BLOCKED_MIN_ROUNDS", 3),
        goal_waiver_stalled_rounds=_get_int("GOAL_WAIVER_STALLED_ROUNDS", 5),
        goal_token_cap=_get_int("GOAL_TOKEN_CAP", 2_000_000),
        judge_grounding_enabled=_get_bool("JUDGE_GROUNDING_ENABLED", True),
        judge_respect_test_failure=_get_bool("JUDGE_RESPECT_TEST_FAILURE", True),
        visual_audit_enabled=_get_bool("VISUAL_AUDIT_ENABLED", True),
        vision_fullpage_cap=_get_bool("VISION_FULLPAGE_CAP", True),
        coder_ultra_correction=_get_bool("CODER_ULTRA_CORRECTION", True),
        turn_checkpoint_enabled=_get_bool("TURN_CHECKPOINT_ENABLED", True),
        plan_task_materialize=_get_bool("PLAN_TASK_MATERIALIZE", True),
        llm_retry_enabled=_get_bool("LLM_RETRY_ENABLED", True),
        llm_transport_retries=_get_int("LLM_TRANSPORT_RETRIES", 5),
        llm_retry_base_delay_s=_get_float("LLM_RETRY_BASE_DELAY_S", 1.0),
        llm_retry_max_delay_s=_get_float("LLM_RETRY_MAX_DELAY_S", 30.0),
        llm_retry_jitter=_get_float("LLM_RETRY_JITTER", 0.25),
        compaction_archive_enabled=_get_bool("COMPACTION_ARCHIVE_ENABLED", True),
        compaction_overflow_guard=_get_bool("COMPACTION_OVERFLOW_GUARD", True),
        chrome_devtools_connect_timeout_s=_get_float("CHROME_DEVTOOLS_CONNECT_TIMEOUT_S", 25.0),
        context7_connect_timeout_s=_get_float("CONTEXT7_CONNECT_TIMEOUT_S", 15.0),
        puppeteer_connect_timeout_s=_get_float("PUPPETEER_CONNECT_TIMEOUT_S", 25.0),
        memory_consolidation_enabled=_get_bool("MEMORY_CONSOLIDATION_ENABLED", True),
        memory_consolidation_after=_get_int("MEMORY_CONSOLIDATION_AFTER", 10),
        memory_retention_days=_get_int("MEMORY_RETENTION_DAYS", 30),
        memory_recall_enabled=_get_bool("MEMORY_RECALL_ENABLED", True),
        memory_recall_limit=_get_int("MEMORY_RECALL_LIMIT", 8),
        memory_recall_max_chars=_get_int("MEMORY_RECALL_MAX_CHARS", 1500),
        sanitizer_enabled=_get_bool("SANITIZER_ENABLED", True),
        read_before_write_enabled=_get_bool("READ_BEFORE_WRITE_ENABLED", True),
        run_dir_lock_enabled=_get_bool("RUN_DIR_LOCK_ENABLED", True),
        fs_transactions_enabled=_get_bool("FS_TRANSACTIONS_ENABLED", True),
        io_allowlist_enabled=_get_bool("IO_ALLOWLIST_ENABLED", True),
        skill_budget_tokens=_get_int("SKILL_BUDGET_TOKENS", 8000),
        skill_finder_enabled=_get_bool("SKILL_FINDER_ENABLED", True),
        skill_finder_trusted_authors=_get_str(
            "SKILL_FINDER_TRUSTED_AUTHORS",
            "vercel-labs,anthropics,openai,github,microsoft,google-labs-code,clerk,greensock,gamedev-skills,elevenlabs,omer-metin",
        ),
        bash_guard_enabled=_get_bool("BASH_GUARD_ENABLED", True),
        redaction_enabled=_get_bool("REDACTION_ENABLED", True),
        coder_devtools_enabled=_get_bool("CODER_DEVTOOLS_ENABLED", True),
        prompt_refiner_enabled=_get_bool("PROMPT_REFINER_ENABLED", True),
        prompt_refiner_model_id=_get_str("PROMPT_REFINER_MODEL_ID", ""),
        reasoning_no_think_model_id=_get_str("REASONING_NO_THINK_MODEL_ID", ""),
        # F-58 : specs backend-agnostiques (spawn llama-server / external / cloud).
        fast_spec=_model_spec_from_env("FAST"),
        reasoning_spec=_model_spec_from_env("REASONING"),
        no_think_spec=_model_spec_from_env("REASONING_NO_THINK"),
        output_dir=_get_str("OUTPUT_DIR", "runs"),
        output_retention=_get_int("OUTPUT_RETENTION", 10),
        logs_dir=_get_str("LOGS_DIR", "logs"),
        log_to_file=_get_bool("LOG_TO_FILE", True),
        idempotence_enabled=_get_bool("IDEMPOTENCE_ENABLED", True),
        idempotency_retention_days=_get_int("IDEMPOTENCY_RETENTION_DAYS", 14),
    )


# Instance singleton chargée à l'import.
settings = load_settings()
