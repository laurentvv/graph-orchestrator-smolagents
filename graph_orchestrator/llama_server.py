"""Lancement à la volée d'llama-server par nœud du graphe (F-58, spawn/kill, backend-agnostique).

3 backends possibles (détectés via <PREFIX>_BACKEND dans le .env, cf. config.ModelSpec) :
- "spawn"    : GPU local. Le graphe SPAWN un process llama-server par nœud avec le blob GGUF
               exact + --reasoning on/off. À la fin du nœud, on TUE le process → VRAM libérée
               PAR L'OS, garantie (1 process = 1 modèle, impossible que 2 cohabitent).
- "external" : endpoint déjà lancé (Ollama local, serveur distant, API cloud OpenAI/OpenRouter).
               No-op : model_lifecycle expose juste l'api_base externe (on ne spawn/tue rien).
- "none"/""  : pas de modèle (tests mockés). No-op total.

CONFIG : tout dans le .env (1 var par attribut). models.ini reste une doc/référence des
chemins blobs mais n'est PLUS lu au runtime — le code lit ModelSpec (config.py). Exemple .env :

    FAST_BACKEND=spawn
    FAST_MODEL=D:\\LLM_MODELS\\blobs\\sha256-df0fd4ee...
    FAST_REASONING=off
    FAST_MMPROJ=D:\\LLM_MODELS\\blobs\\sha256-7c9bafa2...
    REASONING_BACKEND=spawn
    REASONING_MODEL=D:\\LLM_MODELS\\blobs\\sha256-93567e57...
    REASONING_REASONING=on
    ...
    # API cloud alternative :
    # FAST_BACKEND=external
    # FAST_MODEL=gpt-4o
    # FAST_API_BASE=https://api.openai.com/v1
    # FAST_API_KEY=sk-...

Usage (dans les nœuds) :
    with model_lifecycle(settings.reasoning_spec) as srv:
        lm = dspy.LM(f"openai/{srv.model_id}", api_base=srv.api_base, api_key=srv.api_key, ...)
        ...  # inférence
    # ← si spawn : process tué, VRAM libérée. Si external/none : no-op.
"""
import logging
import os
import shutil
import socket
import subprocess
import time
from datetime import datetime
from typing import Optional

from .config import ModelSpec

logger = logging.getLogger(__name__)

import threading
_spawn_lock = threading.Lock()  # sérialise les spawns (évite 2 modèles concurrents).


def _has_nvidia_gpu() -> bool:
    """Détecte la présence d'un GPU NVIDIA via nvidia-smi (cross-plateforme, ~10 ms).

    nvidia-smi est livré avec le driver NVIDIA et présent sur tout Windows/Linux
    ayant un GPU NVIDIA actif. On l'invoque en query mode (rapide, pas de server).
    Sur Windows, le PATH contient C:\\Windows\\System32\\nvidia-smi.exe ; sur Linux,
    /usr/bin/nvidia-smi. Absent = pas de GPU NVIDIA (ou driver non installé).
    """
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return False
    try:
        # -L : liste les GPU (sortie courte, immédiate). exit 0 = GPU présent.
        r = subprocess.run(
            [nvidia_smi, "-L"], capture_output=True, text=True, timeout=10
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except (subprocess.SubprocessError, OSError):
        return False


def _resolve_llama_bin() -> str:
    """Résout le binaire llama-server : priorise un build CUDA bundlé, puis le PATH.

    Ordre de recherche (le 1er dossier contenant llama-server gagne) :
      1. vendor/llamacpp-cuda13/ — build CUDA 13.x précompilé (si GPU NVIDIA présent).
         ~2-3x plus rapide que Vulkan sur GPU NVIDIA, gère mieux l'offload. CUDA 13
         est la dernière majeure ; requiert un driver NVIDIA récent (>=570).
      2. vendor/llamacpp-cuda/ — build CUDA 12.x précompilé (repli si GPU NVIDIA
         mais driver trop ancien pour CUDA 13, ou build manuel legacy).
      3. llama-server dans le PATH système (fallback — ex: build Vulkan WinGet).

    Détection GPU NVIDIA : si aucun GPU NVIDIA n'est présent, on SAUTE les dossiers
    CUDA (sinon llama-server crash au démarrage sur ggml-cuda.dll manquante) et on
    tombe directement sur le fallback PATH (build Vulkan/CPU).

    Retourne le chemin absolu ou "llama-server" (résolution PATH au spawn).
    """
    # On remonte depuis ce fichier (graph_orchestrator/) pour trouver la racine.
    _pkg_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(_pkg_dir)

    # Dossiers candidats, ordre de préférence. On ne garde que ceux qui matchent
    # le matériel : CUDA uniquement si un GPU NVIDIA est présent.
    nvidia = _has_nvidia_gpu()
    candidates: list[str] = []
    if nvidia:
        candidates.append("llamacpp-cuda13")
        candidates.append("llamacpp-cuda")
    # Si pas de NVIDIA, on ne propose aucun dossier CUDA → fallback PATH (Vulkan/CPU).

    for sub in candidates:
        for exe_name in ("llama-server.exe", "llama-server"):
            candidate = os.path.join(_project_root, "vendor", sub, exe_name)
            if os.path.isfile(candidate):
                return candidate
    # Fallback : binaire système (PATH). Résolu par subprocess au spawn.
    return "llama-server"


_LLAMA_SERVER_BIN = _resolve_llama_bin()
# Détecte le backend (CUDA vs Vulkan) pour logger et adapter les flags. On sniff
# la présence de ggml-cuda.dll/cudart64 à côté du binaire bundlé.
def _detect_backend() -> str:
    """Retourne 'cuda', 'vulkan' ou 'unknown' selon le binaire résolu."""
    bin_dir = os.path.dirname(_LLAMA_SERVER_BIN)
    if bin_dir and os.path.isdir(bin_dir):
        files = os.listdir(bin_dir)
        if any(f.lower().startswith("ggml-cuda") or "cudart" in f.lower() for f in files):
            return "cuda"
        if any("vulkan" in f.lower() for f in files):
            return "vulkan"
    return "unknown"


_LLAMA_BACKEND = _detect_backend()


def _free_port() -> int:
    """Trouve un port TCP libre sur localhost (OS assigne un port éphémère)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(port: int, timeout: float = 300.0) -> bool:
    """Attend que llama-server réponde sur /health (modèle chargé + prêt).

    timeout généreux (5 min) : le 1er chargement du 12B peut prendre ~30-60s, et avec le
    thinking le 1er token peut être lent. /health répond dès que le serveur écoute.
    """
    import urllib.request
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(1.0)
    return False


def _port_healthy(port: int, timeout: float = 2.0) -> bool:
    """F-104 : sonde /health rapide (2 s) — le serveur est-il VIVANT là, maintenant ?

    Utilisé par ``model_lifecycle.revive()`` depuis la boucle de retry transport
    (llm_retry.py) : distingue un serveur sain (simple blip transitoire → retry
    sec) d'un serveur mort/wedged (process crashé sous pression VRAM, port
    fermé → respawn avant de rejouer la requête). Court par construction : on
    est sur le chemin d'un retry, pas au boot.
    """
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


class _SpawnedServer:
    """Un process llama-server lancé à la volée. Tué via stop() → VRAM libérée par l'OS."""

    def __init__(self, port: int, proc: subprocess.Popen, model_id: str):
        self.port = port
        self.proc = proc
        self.model_id = model_id  # nom logique pour le provider openai/ (le serveur s'en fiche)
        # P7/F-140 : registre disque — si l'orchestrateur crash (kill/VRAM/OS),
        # le context manager ne survit pas ; le reaper tuera l'orphelin au boot
        # suivant via process_reaper.reap_orphans.
        try:
            from .process_reaper import register_process

            register_process(proc.pid, "llama-server", f"port={port} model={model_id}")
        except Exception:
            pass

    @property
    def api_base(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def stop(self) -> None:
        if self.proc.poll() is not None:
            try:
                from .process_reaper import unregister_process

                unregister_process(self.proc.pid)
            except Exception:
                pass
            return  # déjà mort
        try:
            self.proc.terminate()  # SIGTERM
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()  # SIGKILL
                self.proc.wait(timeout=5)
            # Run #13 : le stop n'allait qu'au logger.info (invisible en console)
            # → « 10 spawns / 0 arrêt » dans le log a égaré le post-mortem vers
            # une piste leak. Print symétrique du « prêt » pour un cycle
            # spawn/stop lisible d'un seul regard.
            print(f"[~] llama-server : arrêté (port {self.port}, {self.model_id}) — VRAM libérée")
            logger.info("[llama-server] process port %s (%s) terminé — VRAM libérée",
                        self.port, self.model_id)
        except Exception as e:
            logger.warning("[llama-server] échec stop port %s : %s", self.port, str(e)[:120])
        finally:
            try:
                from .process_reaper import unregister_process

                unregister_process(self.proc.pid)
            except Exception:
                pass


def _build_cmd(spec: ModelSpec, port: int) -> list[str]:
    """Construit la commande llama-server depuis un ModelSpec (testable sans spawn)."""
    cmd = [
        _LLAMA_SERVER_BIN,
        "-m", spec.model,
        "--host", "127.0.0.1",
        "--port", str(port),
        "-c", str(spec.context),
        "--reasoning", spec.reasoning or "off",
        "--alias", "default",
        # Flash Attention : accélère le préfill des longs contextes (Architect).
        # Configurable via <PREFIX>_FLASH_ATTN (défaut "auto").
        "--flash-attn", spec.flash_attn or "auto",
        # Post-mortem run #4 (2026-08-15) : SANS ce flag, llama-server default à
        # n_slots=4 et réserve 4×n_ctx de KV cache (4×49152 = ~196k tokens pour
        # un 4B) — pression VRAM massive qui a fini en Connection error après un
        # marathon Coder de 35 steps × ~135 s de préfill. On ne fait JAMAIS de
        # requêtes concurrentes vers un serveur spawné (AUDIT_PARALLEL=false,
        # nœuds séquentiels, 1 agent par serveur) → 1 seul slot suffit (KV ÷ 4).
        "--parallel", "1",
    ]
    # -ngl : AUTO-FIT si gpu_layers=0 (défaut, façon Ollama — s'adapte à la VRAM sans
    # OOM). Sinon force le nombre de layers (override : REASONING_NGL=32 optimal sur
    # gemma-12B / RTX 3060 build CUDA, cf. debug/Gemma4_Thinking_Audit.md §5).
    if spec.gpu_layers and spec.gpu_layers > 0:
        cmd += ["-ngl", str(spec.gpu_layers)]
    if spec.mmproj and os.path.exists(spec.mmproj):
        cmd += ["--mmproj", spec.mmproj]
    # Décodage spéculatif MTP (bench debug/test_mtp_spec.py 2026-08-17, b10472) :
    # consomme les couches nextn sinon ignorées. Config retenue sur le 9B dense :
    # draft-mtp + n-max 2 (27,5 t/s vs 25,6 défaut 3 vs 24,1 avec --spec-default,
    # baseline 18,2 — ngram-mod de --spec-default dégrade, cf. issue #24266).
    # Le KV du draft suit la même quantization que le KV principal si kv_quant.
    if getattr(spec, "spec_mtp", False):
        kvq = spec.kv_quant or "q8_0"
        cmd += ["--spec-type", "draft-mtp",
                "--spec-draft-n-max", "2",
                "--spec-draft-type-k", kvq, "--spec-draft-type-v", kvq]
    # Quantization KV cache : gain net au grand contexte (moins de spill WDDM sur
    # 6 Go), requiert Flash Attention (résolu par --flash-attn auto/on).
    if getattr(spec, "kv_quant", ""):
        cmd += ["--cache-type-k", spec.kv_quant, "--cache-type-v", spec.kv_quant]
    # Réutilisation de chunks KV (shifting) pour les boucles agents multi-tours où
    # le milieu de l'historique est réécrit (compaction F-101). Bench FAST :
    # -10% préfill (debug/bench_prefill_flags.py) ; 256 = preset officiel Qwen Coder.
    if getattr(spec, "cache_reuse", 0):
        cmd += ["--cache-reuse", str(spec.cache_reuse)]
    # Sampling serveur (reco Qwen top_k 20 / min_p 0) : nos clients n'envoient que
    # temperature, le reste vient des défauts llama-server (top_k 40, min_p 0.05).
    if getattr(spec, "top_k", 0):
        cmd += ["--top-k", str(spec.top_k)]
    if getattr(spec, "min_p", -1.0) >= 0:
        cmd += ["--min-p", str(spec.min_p)]
    # Sampler DRY (2026-08-22) : anti-répétition de SÉQUENCES (le modèle qui
    # re-dérive le même plan en boucle). 0 = flag non passé (défaut serveur).
    if getattr(spec, "dry_multiplier", 0.0) > 0:
        cmd += ["--dry-multiplier", str(spec.dry_multiplier)]
        if getattr(spec, "dry_base", 0.0) > 0:
            cmd += ["--dry-base", str(spec.dry_base)]
        if getattr(spec, "dry_allowed_length", 0) > 0:
            cmd += ["--dry-allowed-length", str(spec.dry_allowed_length)]
        if getattr(spec, "dry_penalty_last_n", 0) > 0:
            cmd += ["--dry-penalty-last-n", str(spec.dry_penalty_last_n)]
    return cmd


def _spawn(spec: ModelSpec) -> Optional[_SpawnedServer]:
    """Spawn un llama-server depuis un ModelSpec (backend=spawn). None si échec/no-op."""
    blob = spec.model
    if not blob or not os.path.exists(blob):
        logger.warning("[llama-server] blob manquant/introuvable (%s) — no-op", blob)
        print(f"[!] llama-server : blob introuvable ({blob[:40]}...) — no-op")
        return None

    port = _free_port()
    cmd = _build_cmd(spec, port)

    # model_id logique = "default" garanti de matcher l'alias côté llama-server.
    # openai/ a besoin d'un model_id non-vide dans le body.
    model_id = "default"

    ngl_desc = f"ngl={spec.gpu_layers}" if spec.gpu_layers > 0 else "ngl=auto-fit"
    mtp_desc = "mtp=on" if getattr(spec, "spec_mtp", False) else "mtp=off"
    kvq_desc = f"kv={spec.kv_quant}" if getattr(spec, "kv_quant", "") else "kv=f16"
    logger.info("[llama-server] spawn blob %s (backend=%s, reasoning=%s, port %d, %s, flash=%s, %s, %s)",
                os.path.basename(blob)[:20], _LLAMA_BACKEND, spec.reasoning, port, ngl_desc,
                spec.flash_attn, mtp_desc, kvq_desc)
    print(f"[*] llama-server : chargement {os.path.basename(blob)[:25]} (backend={_LLAMA_BACKEND}, "
          f"port {port}, reasoning={spec.reasoning}, {ngl_desc}, flash={spec.flash_attn}, "
          f"{mtp_desc}, {kvq_desc})...")

    # F-58-bis : capture des logs llama-server dans logs/llama-server/ (diag GPU/OOM).
    # Avant, stdout/stderr → DEVNULL : impossible de diagnostiquer l'offload GPU ou un
    # OOM. llama-server écrit sa bannière de chargement (offload layers, VRAM alloc,
    # buffer sizes) sur stderr — on la redirige vers un fichier horodaté par spawn.
    try:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        base_logs_dir = os.environ.get("LOGS_DIR", os.path.join(project_root, "logs"))
        llama_logs_dir = os.path.join(base_logs_dir, "llama-server")
        os.makedirs(llama_logs_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        blob_tag = os.path.basename(blob)[:12]
        llama_log_path = os.path.join(llama_logs_dir, f"llama-{stamp}-p{port}-{blob_tag}.log")
        llama_log_file = open(llama_log_path, "w", encoding="utf-8", buffering=1)
        print(f"[*] llama-server : logs → {llama_log_path}")
    except Exception as e:
        logger.warning("[llama-server] ouverture log fichier échouée (%s) — fallback DEVNULL", str(e)[:80])
        llama_log_file = subprocess.DEVNULL
        llama_log_path = None

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=llama_log_file,
            start_new_session=True,  # groupe de process pour terminate() fiable
        )
    except FileNotFoundError:
        logger.warning("[llama-server] binaire '%s' absent du PATH — no-op", _LLAMA_SERVER_BIN)
        print("[!] llama-server introuvable dans le PATH — no-op")
        return None
    except Exception as e:
        logger.warning("[llama-server] spawn échec : %s — no-op", str(e)[:120])
        return None

    if not _wait_for_health(port, timeout=300):
        logger.warning("[llama-server] /health timeout après 300s — kill + no-op")
        _SpawnedServer(port, proc, model_id).stop()
        print("[!] llama-server : timeout de chargement — no-op")
        return None

    print(f"[*] llama-server : prêt (port {port})")
    return _SpawnedServer(port, proc, model_id)


class model_lifecycle:
    """Context manager : fournit un serveur LLM pour le nœud, backend-agnostique.

    - backend=spawn    : spawn llama-server (blob), le tue à la sortie (VRAM libérée).
    - backend=external : no-op, expose l'api_base externe (endpoint déjà lancé/cloud).
    - backend=none/""  : no-op total (tests mockés).

    Le nœud lit ``self.api_base``, ``self.api_key``, ``self.model_id`` pour configurer son
    client LLM (DSPy/smolagents) — peu importe le backend, l'API est la même.

    Usage :
        with model_lifecycle(settings.reasoning_spec) as srv:
            lm = dspy.LM(f"openai/{srv.model_id}", api_base=srv.api_base,
                        api_key=srv.api_key, ...)
            ...  # inférence
        # ← si spawn : process tué. Si external/none : no-op.
    """

    def __init__(self, spec):
        # spec = ModelSpec (config.py). Robustesse : si on passe une string (ancienne API)
        # ou un MagicMock (tests), on no-op avec des attrs vides.
        self._spec = spec
        self._server: Optional[_SpawnedServer] = None
        # Attrs exposés au nœud (seront remplis dans __enter__).
        self.api_base: str = ""
        self.api_key: str = ""
        self.model_id: str = ""

    def __enter__(self):
        spec = self._spec
        # Robustesse : si spec n'est pas un ModelSpec valide (MagicMock test, None, string),
        # no-op total (api_base vide → le nœud fallback sur settings via _configure_dspy).
        backend = getattr(spec, "backend", "none") if spec else "none"
        if not isinstance(backend, str):
            backend = "none"

        if backend == "spawn":
            with _spawn_lock:
                self._server = _spawn(spec)
            if self._server is not None:
                self.api_base = self._server.api_base
                self.model_id = self._server.model_id
                # api_key : llama-server n'en exige pas, mais litellm/openai/ en veut une.
                self.api_key = "sk-local"
            # Si spawn échoue, api_base reste "" → le nœud doit gérer (souvent fallback settings).
        elif backend == "external":
            # Endpoint externe (Ollama/cloud/distant) : on ne spawn rien, on expose les coords.
            self.api_base = getattr(spec, "api_base", "") or ""
            self.api_key = getattr(spec, "api_key", "") or ""
            self.model_id = getattr(spec, "model", "") or ""
        # backend == "none" ou autre : no-op (api_base vide).
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._server is not None:
            self._server.stop()
            self._server = None
        return False

    def revive(self) -> Optional[str]:
        """F-104 (P8) : ranime le serveur spawné s'il est mort — retourne l'api_base.

        Appelé par la boucle de retry transport (llm_retry.with_llm_retry →
        LoggedOpenAIServerModel) UNIQUEMENT après l'échec d'un appel LLM, donc
        jamais avec une requête en cours. Sémantique :

        - backend != spawn (external/none) : no-op, retourne l'api_base courante
          (le retry simple + re-création du client suffit — openfox « re-résolution
          du client à chaque tentative ») ;
        - serveur spawné encore SAIN (/health répond) : blip transitoire, rien à
          faire — on retourne l'api_base courante ;
        - serveur spawné MORT/WEDGED (crash VRAM observé en prod, post-mortem run
          #4 : « Connection error après un marathon Coder de 35 steps ») : stop des
          restes + respawn complet (nouveau port) + mise à jour des attrs exposés.
          Le client LLM sera re-créé sur le NOUVEL api_base par l'appelant.

        Retourne le nouvel api_base (str), l'api_base inchangé, ou None si le
        respawn a échoué (auquel cas le retry continuera vers le serveur mort
          et s'épuisera proprement).
        """
        if self._server is None:
            # Backend external/none ou spawn raté à l'entrée : rien à ranimer,
            # le caller retente sur la base actuelle.
            return self.api_base or None
        if _port_healthy(self._server.port):
            return self.api_base
        logger.warning(
            "[llama-server] serveur port %s (%s) mort/wedged mid-run — respawn (F-104)",
            self._server.port, self._server.model_id,
        )
        print(f"[!] llama-server : serveur port {self._server.port} mort mid-run — respawn...")
        self._server.stop()
        with _spawn_lock:
            self._server = _spawn(self._spec)
        if self._server is None:
            self.api_base = ""
            return None
        self.api_base = self._server.api_base
        self.model_id = self._server.model_id
        self.api_key = "sk-local"
        print(f"[*] llama-server : ranimé (nouveau port {self._server.port})")
        return self.api_base
