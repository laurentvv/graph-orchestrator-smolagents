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
    FAST_MODEL=D:\\OLLAMA_MODELS\\blobs\\sha256-df0fd4ee...
    FAST_REASONING=off
    FAST_MMPROJ=D:\\OLLAMA_MODELS\\blobs\\sha256-7c9bafa2...
    REASONING_BACKEND=spawn
    REASONING_MODEL=D:\\OLLAMA_MODELS\\blobs\\sha256-93567e57...
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
import socket
import subprocess
import time
from datetime import datetime
from typing import Optional

from .config import ModelSpec

logger = logging.getLogger(__name__)

import threading
_spawn_lock = threading.Lock()  # sérialise les spawns (évite 2 modèles concurrents).


def _resolve_llama_bin() -> str:
    """Résout le binaire llama-server : priorise un build CUDA bundlé, puis le PATH.

    Ordre de recherche (le 1er trouvé gagne) :
      1. vendor/llamacpp-cuda/llama-server(.exe) — build CUDA précompilé inclus dans
         le projet (gitignoré). ~2-3x plus rapide que Vulkan sur GPU NVIDIA, et gère
         mieux l'offload (gros blocs contigus Vulkan → OOM même à -ngl 10).
      2. llama-server dans le PATH système (fallback — ex: build Vulkan WinGet).

    Retourne le chemin absolu ou "llama-server" (résolution PATH au spawn).
    """
    # 1. Build CUDA bundlé : vendor/llamacpp-cuda/ relatif à la racine du projet.
    #    On remonte depuis ce fichier (graph_orchestrator/) pour trouver la racine.
    _pkg_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(_pkg_dir)
    for exe_name in ("llama-server.exe", "llama-server"):
        candidate = os.path.join(_project_root, "vendor", "llamacpp-cuda", exe_name)
        if os.path.isfile(candidate):
            return candidate
    # 2. Fallback : binaire système (PATH). Résolu par subprocess au spawn.
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


class _SpawnedServer:
    """Un process llama-server lancé à la volée. Tué via stop() → VRAM libérée par l'OS."""

    def __init__(self, port: int, proc: subprocess.Popen, model_id: str):
        self.port = port
        self.proc = proc
        self.model_id = model_id  # nom logique pour le provider openai/ (le serveur s'en fiche)

    @property
    def api_base(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def stop(self) -> None:
        if self.proc.poll() is not None:
            return  # déjà mort
        try:
            self.proc.terminate()  # SIGTERM
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()  # SIGKILL
                self.proc.wait(timeout=5)
            logger.info("[llama-server] process port %s (%s) terminé — VRAM libérée",
                        self.port, self.model_id)
        except Exception as e:
            logger.warning("[llama-server] échec stop port %s : %s", self.port, str(e)[:120])


def _spawn(spec: ModelSpec) -> Optional[_SpawnedServer]:
    """Spawn un llama-server depuis un ModelSpec (backend=spawn). None si échec/no-op."""
    blob = spec.model
    if not blob or not os.path.exists(blob):
        logger.warning("[llama-server] blob manquant/introuvable (%s) — no-op", blob)
        print(f"[!] llama-server : blob introuvable ({blob[:40]}...) — no-op")
        return None

    port = _free_port()
    cmd = [
        _LLAMA_SERVER_BIN,
        "-m", blob,
        "--host", "127.0.0.1",
        "--port", str(port),
        "-c", str(spec.context),
        "--reasoning", spec.reasoning or "off",
        "--alias", "default",
        # Flash Attention : accélère le préfill des longs contextes (Architect).
        # Configurable via <PREFIX>_FLASH_ATTN (défaut "auto").
        "--flash-attn", spec.flash_attn or "auto",
    ]
    # -ngl : AUTO-FIT si gpu_layers=0 (défaut, façon Ollama — s'adapte à la VRAM sans
    # OOM). Sinon force le nombre de layers (override : REASONING_NGL=32 optimal sur
    # gemma-12B / RTX 3060 build CUDA, cf. debug/Gemma4_Thinking_Audit.md §5).
    if spec.gpu_layers and spec.gpu_layers > 0:
        cmd += ["-ngl", str(spec.gpu_layers)]
    if spec.mmproj and os.path.exists(spec.mmproj):
        cmd += ["--mmproj", spec.mmproj]

    # model_id logique = "default" garanti de matcher l'alias côté llama-server.
    # openai/ a besoin d'un model_id non-vide dans le body.
    model_id = "default"

    ngl_desc = f"ngl={spec.gpu_layers}" if spec.gpu_layers > 0 else "ngl=auto-fit"
    bin_short = os.path.basename(_LLAMA_SERVER_BIN) if os.path.sep in _LLAMA_SERVER_BIN else _LLAMA_SERVER_BIN
    logger.info("[llama-server] spawn blob %s (backend=%s, reasoning=%s, port %d, %s, flash=%s)",
                os.path.basename(blob)[:20], _LLAMA_BACKEND, spec.reasoning, port, ngl_desc, spec.flash_attn)
    print(f"[*] llama-server : chargement {os.path.basename(blob)[:25]} (backend={_LLAMA_BACKEND}, "
          f"port {port}, reasoning={spec.reasoning}, {ngl_desc}, flash={spec.flash_attn})...")

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
        print(f"[!] llama-server introuvable dans le PATH — no-op")
        return None
    except Exception as e:
        logger.warning("[llama-server] spawn échec : %s — no-op", str(e)[:120])
        return None

    if not _wait_for_health(port, timeout=300):
        logger.warning("[llama-server] /health timeout après 300s — kill + no-op")
        _SpawnedServer(port, proc, model_id).stop()
        print(f"[!] llama-server : timeout de chargement — no-op")
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
