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
from typing import Optional

from .config import ModelSpec

logger = logging.getLogger(__name__)

_LLAMA_SERVER_BIN = "llama-server"  # dans le PATH Windows (WinGet). Si absent → no-op.
import threading
_spawn_lock = threading.Lock()  # sérialise les spawns (évite 2 modèles concurrents).


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
        "-ngl", "99",
        "--reasoning", spec.reasoning or "off",
    ]
    if spec.mmproj and os.path.exists(spec.mmproj):
        cmd += ["--mmproj", spec.mmproj]

    # model_id logique = nom de fichier du blob (le serveur s'en fiche, mais le provider
    # openai/ a besoin d'un model_id non-vide dans le body).
    model_id = os.path.basename(blob)[:40] or "model"

    logger.info("[llama-server] spawn blob %s (reasoning=%s, port %d)",
                os.path.basename(blob)[:20], spec.reasoning, port)
    print(f"[*] llama-server : chargement {os.path.basename(blob)[:25]} (port {port}, reasoning={spec.reasoning})...")
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
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
