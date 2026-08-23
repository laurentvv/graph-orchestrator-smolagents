"""Pool navigateur run-scoped — un seul Chrome par run (F-163).

Problème (E2E F-162, 2026-08-23) : le graphe spawnait 4 serveurs MCP navigateur
par itération (Coder, Static Tester, Tester devtools, Tester puppeteer) ; chaque
serveur chrome-devtools-mcp lançait SON Chrome (--isolated), et la fermeture
stdio ne tuait JAMAIS l'arbre cmd→npx→node→Chrome sous Windows (2 Chromes
orphelins observés, ~12 processus fuis par run, arbres tués à la main).

Architecture (décision user 2026-08-23, adaptée aux contraintes stdio) :

  - UN SEUL Chrome par run, spawné par CE pool : ``--remote-debugging-port`` sur
    un port libre + user-data-dir temporaire propre au run (isolation ≡
    ``--isolated``, sans le froid). Tous les serveurs MCP chrome-devtools du run
    s'y CONNECTENT via ``--browserUrl`` (option officielle du serveur) → les
    serveurs ne lancent PLUS aucun Chrome. Écart documenté vs l'intitulé « un
    seul MCP » : stdio = 1 session par process, partager L'INSTANCE serveur
    entre mcpadapt (smolagents) et fastmcp (pydantic) est impossible — le pool
    porte donc le CHROME (le coût froid/leaky), pas le serveur npx (léger, meurt
    avec son pipe stdio).
  - PID racine capturé par diff tasklist autour du spawn + enregistré dans le
    registre disque du reaper F-140 (crash de l'orchestrateur → le run suivant
    reap l'arbre orphelin).
  - Health-check HTTP ``/json/version`` avant chaque prêt + respawn si mort.
  - ``taskkill /T /F`` de l'arbre au shutdown (+ sweep final des Chrome
    automation ``--remote-debugging-pipe`` apparus pendant le run : marqueur du
    repli puppeteer qui ne sait PAS se connecter à un Chrome existant — jamais
    présent sur le Chrome perso de l'utilisateur).
  - 0 nouvelle dépendance (tasklist/taskkill/PowerShell/urllib intégrés).

Cycle de vie :

  - ``configure_run(run_id)`` : ancre le pool au run + baseline des process
    (pour le sweep) ; appelé par run_coding_workflow une fois le run_id connu.
  - ``lease(consumer)`` : context manager refcounté — spawn/health-check le
    Chrome au besoin, yield l'URL ``--browserUrl`` (ou None si pool
    indisponible → la façade retombe sur le comportement historique : serveur
    spawnant son propre Chrome).
  - ``shutdown_run()`` : taskkill arbre + sweep + reset. En usage STANDALONE
    (scripts d'isolation F-89, sans configure_run), le DERNIER release déclenche
    le shutdown (aucune fuite en debug isolé).
  - ``watch_spawn(label)`` : fenêtre de capture des arbres chrome.exe apparus
    pendant l'ouverture d'un MCP qui lance son PROPRE Chrome (repli puppeteer) —
    enregistrés pour le taskkill final.

Sous pytest : le pool est BYPASSÉ par défaut (comportement historique exact,
suite 0-réseau préservée) sauf si un test force ``browser_pool._PYTEST = False``.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

_IS_WINDOWS = os.name == "nt"

# Détection pytest À L'APPEL (jamais à l'import : PYTEST_CURRENT_TEST n'est
# posé par pytest que PENDANT l'exécution d'un test — capturé à l'import il
# vaudrait toujours False). Sous pytest, le pool ne spawn JAMAIS de process
# (suite 0-réseau/0-LLM) et le SWEEP final est interdit (tuer de vrais process
# depuis une suite de tests serait une action destructive involontaire — prouvé
# à la première exécution : 3 arbres tués par l'atexit). Les tests dédiés
# forcent le comportement via ``browser_pool._OVERRIDE["force"]``.
_OVERRIDE: dict = {"force": None}


def _under_pytest() -> bool:
    if _OVERRIDE["force"] is not None:
        return _OVERRIDE["force"]
    return "PYTEST_CURRENT_TEST" in os.environ

# Chrome automation lancé par puppeteer (chrome-devtools-mcp historique,
# server-puppeteer) — JAMAIS présent sur le Chrome perso de l'utilisateur.
_AUTOMATION_CHROME_MARKER = "--remote-debugging-pipe"

_CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
)

_SAFE_DIR_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def find_chrome_executable() -> Optional[str]:
    """Chemin du binaire Chrome : CHROME_PATH (convention existante) puis
    emplacements standard. None si introuvable (pool → repli historique)."""
    env_path = os.getenv("CHROME_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    for candidate in _CHROME_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def pool_should_engage(settings=None) -> bool:
    """Le pool doit-il être utilisé dans CE contexte ?

    Vrai si : activé par la config ET hors pytest (ou pytest-forcé par un test).
    """
    if _under_pytest():
        return False
    if settings is None:
        from .config import settings as _default_settings

        settings = _default_settings
    return bool(getattr(settings, "browser_pool_enabled", True))


# ============================================================
# Primitives process Windows (tasklist / taskkill / PowerShell)
# ============================================================


def _pids_by_name(image_name: str) -> Set[int]:
    """PIDs vivants d'une image (tasklist /FO CSV). Vide si indisponible/erreur."""
    if not _IS_WINDOWS:
        return set()
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
        ).stdout
    except Exception:  # noqa: BLE001 — diagnostic best-effort
        return set()
    pids: Set[int] = set()
    for line in (out or "").splitlines():
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) >= 2 and parts[1].isdigit():
            pids.add(int(parts[1]))
    return pids


def _cmdlines_by_pid(image_name: str, timeout_s: float = 15.0) -> Dict[int, str]:
    """PID → ligne de commande d'une image (PowerShell Get-CimInstance).

    Utilisé UNIQUEMENT pour les décisions de kill du sweep : en cas d'échec
    (PowerShell absent/lent), on retourne {} → le sweep NE TUE RIEN (fail-safe
    pour le Chrome perso de l'utilisateur).
    """
    if not _IS_WINDOWS:
        return {}
    query = (
        "Get-CimInstance Win32_Process -Filter \"Name='%s'\" | "
        "ForEach-Object { [PSCustomObject]@{Pid=$_.ProcessId; Cl=$_.CommandLine} } | "
        "ConvertTo-Json -Compress" % image_name
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", query],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout_s,
        ).stdout
    except Exception:  # noqa: BLE001 — fail-safe
        return {}
    try:
        data = json.loads((out or "").strip() or "null")
    except Exception:  # noqa: BLE001 — fail-safe
        return {}
    if data is None:
        return {}
    rows = data if isinstance(data, list) else [data]
    result: Dict[int, str] = {}
    for row in rows:
        try:
            pid = int(row.get("Pid"))
            result[pid] = str(row.get("Cl") or "")
        except Exception:  # noqa: BLE001
            continue
    return result


def _kill_tree(pid: int) -> bool:
    """Tue l'ARBORESCENCE d'un pid (taskkill /T /F ; POSIX : killpg). Fail-open."""
    if not pid or pid <= 0:
        return False
    try:
        if _IS_WINDOWS:
            out = subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=15,
            )
            return out.returncode == 0
        import signal

        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
            return True
        except (ProcessLookupError, PermissionError):
            return False
    except Exception:  # noqa: BLE001 — fail-open
        return False


def _http_json_version_ok(port: int, timeout_s: float = 2.0) -> bool:
    """Health-check Chrome : GET http://127.0.0.1:<port>/json/version → 200."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/version", timeout=timeout_s
        ) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


# ============================================================
# Pool
# ============================================================


class BrowserPool:
    """Chrome unique par run, refcounté, santé surveillée, arbre tué à la fin.

    Thread-safe (RLock) : consommé depuis les nœuds async (pydantic) comme
    sync (smolagents). Toutes les primitives sont des appels courts.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._run_id: Optional[str] = None
        self._refcount = 0
        self._proc: Optional[subprocess.Popen] = None
        self._root_pid: Optional[int] = None
        self._port: Optional[int] = None
        self._user_data_dir: Optional[str] = None
        # Baselines process : capturées à la CRÉATION du pool (toujours AVANT
        # tout spawn du pool) puis rafraîchies à configure_run. Le sweep final
        # ne tue QUE des process apparus APRÈS — jamais l'existant. Sous pytest
        # : vides (le sweep est de toute façon interdit en test).
        self._baseline_chrome: Set[int] = set() if _under_pytest() else _pids_by_name("chrome.exe")
        self._baseline_node: Set[int] = set() if _under_pytest() else _pids_by_name("node.exe")
        self._watched: Set[int] = set()
        self._disabled_reason: Optional[str] = None
        self._spawn_count = 0
        # Sweep interdit sous pytest (kill de process réels interdit en test).
        self._sweep_enabled = not _under_pytest()

    # ---------- observabilité ----------

    def browser_url(self) -> Optional[str]:
        with self._lock:
            return f"http://127.0.0.1:{self._port}" if self._port else None

    def stats(self) -> dict:
        with self._lock:
            return {
                "run_id": self._run_id,
                "refcount": self._refcount,
                "root_pid": self._root_pid,
                "port": self._port,
                "spawn_count": self._spawn_count,
                "watched": sorted(self._watched),
                "disabled_reason": self._disabled_reason,
                "healthy": bool(self._port) and _http_json_version_ok(self._port),
            }

    # ---------- scope run ----------

    def configure_run(self, run_id: str) -> None:
        """Ancre le pool au run (idempotent pour le même run_id). Un NOUVEAU
        run_id tue l'éventuel arbre restant du run précédent."""
        with self._lock:
            if self._run_id == run_id:
                return
            if self._proc is not None or self._watched:
                self._shutdown_locked(reason=f"superséde par le run {run_id}")
            self._run_id = run_id
            self._baseline_chrome = _pids_by_name("chrome.exe")
            self._baseline_node = _pids_by_name("node.exe")
            logger.info(
                "[pool navigateur F-163] ancré au run %s (baseline chrome=%d node=%d)",
                run_id, len(self._baseline_chrome), len(self._baseline_node),
            )

    # ---------- acquisition ----------

    @contextmanager
    def lease(self, consumer: str = "", spawn_timeout_s: float = 30.0):
        """CM : garantit un Chrome sain pendant le consommateur, yield l'URL
        ``--browserUrl`` (None si pool indisponible → repli historique)."""
        url = self.acquire(consumer, spawn_timeout_s=spawn_timeout_s)
        try:
            yield url
        finally:
            self.release(consumer)

    def acquire(self, consumer: str = "", spawn_timeout_s: float = 30.0) -> Optional[str]:
        with self._lock:
            if self._disabled_reason:
                return None
            self._refcount += 1
        url = self._ensure_browser(spawn_timeout_s)
        if url is None:
            with self._lock:
                self._refcount = max(0, self._refcount - 1)
            logger.warning(
                "[pool navigateur F-163] indisponible pour '%s' — repli historique (serveur lance son Chrome).",
                consumer,
            )
        else:
            logger.debug("[pool navigateur F-163] lease → %s (consommateur %s, refcount %d)",
                         url, consumer, self._refcount)
        return url

    def release(self, consumer: str = "") -> None:
        with self._lock:
            self._refcount = max(0, self._refcount - 1)
            # Usage STANDALONE (aucun configure_run — scripts d'isolation F-89) :
            # le DERNIER release joue le shutdown (aucune fuite en debug isolé).
            if self._refcount == 0 and self._run_id is None and (self._proc is not None or self._watched):
                self._shutdown_locked(reason=f"dernier release standalone ({consumer})")

    # ---------- Chrome ----------

    def _ensure_browser(self, spawn_timeout_s: float) -> Optional[str]:
        """Chrome UP + prêt (health-check), respawn si mort. URL ou None."""
        with self._lock:
            if self._port and _http_json_version_ok(self._port):
                return f"http://127.0.0.1:{self._port}"
            if self._port or self._proc:
                # Cadavre/hang : nettoie l'arbre avant respawn.
                logger.warning("[pool navigateur F-163] Chrome %s:%s mort/hang — respawn.",
                               self._root_pid, self._port)
                self._kill_current_locked()

            chrome = find_chrome_executable()
            if not chrome:
                self._disabled_reason = (
                    "Chrome introuvable (CHROME_PATH non défini, emplacements standard absents)"
                )
                logger.warning("[pool navigateur F-163] %s", self._disabled_reason)
                return None

            port = _pick_free_port()
            slug = _SAFE_DIR_RE.sub("-", (self._run_id or "adhoc"))[:24]
            user_data_dir = tempfile.mkdtemp(prefix=f"chrome-pool-{slug}-")
            args = [
                chrome,
                f"--remote-debugging-port={port}",
                f"--user-data-dir={user_data_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--window-size=1280,800",
                "about:blank",
            ]
            if os.getenv("CHROME_DEVTOOLS_HEADLESS", "0").strip().lower() in {"1", "true", "yes", "on"}:
                args.insert(1, "--headless=new")

            before = _pids_by_name("chrome.exe")
            try:
                proc = subprocess.Popen(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=not _IS_WINDOWS,
                )
            except Exception as exc:  # noqa: BLE001 — spawn raté → repli historique
                logger.warning("[pool navigateur F-163] spawn Chrome KO (%s) — repli historique.", exc)
                shutil.rmtree(user_data_dir, ignore_errors=True)
                return None

            deadline = time.time() + max(float(spawn_timeout_s), 1.0)
            ready = False
            while time.time() < deadline:
                if _http_json_version_ok(port, timeout_s=1.5):
                    ready = True
                    break
                if proc.poll() is not None:
                    break
                time.sleep(0.3)

            if not ready:
                logger.warning(
                    "[pool navigateur F-163] Chrome pas prêt en %.0fs (port %d) — kill + repli historique.",
                    spawn_timeout_s, port,
                )
                # root_pid posé AVANT le kill : l'arbre du spawn raté doit
                # mourir (sinon fuite du Chrome démarré à moitié).
                self._proc = proc
                self._root_pid = proc.pid
                self._port = port
                self._kill_current_locked()
                shutil.rmtree(user_data_dir, ignore_errors=True)
                return None

            # PID racine : le Popen direct + (ceinture) les nouveaux PIDs du diff
            # tasklist — un shim/delegation éventuel ne peut pas échapper au kill.
            after = _pids_by_name("chrome.exe")
            new_pids = after - before - {proc.pid}
            self._proc = proc
            self._root_pid = proc.pid
            self._port = port
            self._user_data_dir = user_data_dir
            self._spawn_count += 1
            if new_pids:
                self._watched.update(new_pids)
            # Crash-safety F-140 : registre disque — un crash de l'orchestrateur
            # laisse l'entrée, le run suivant reap_orphans() tue l'arbre.
            try:
                from .process_reaper import register_process

                register_process(self._root_pid, kind="browser-pool-chrome",
                                 cmd_hint=f"run={self._run_id} port={port}")
            except Exception:  # noqa: BLE001 — fail-open
                pass
            logger.info(
                "[pool navigateur F-163] Chrome prêt pid=%s port=%d (spawn #%d, run=%s)",
                self._root_pid, port, self._spawn_count, self._run_id,
            )
            return f"http://127.0.0.1:{port}"

    def _kill_current_locked(self) -> Optional[int]:
        """Tue l'arbre du Chrome courant + purge (appelé sous lock). Retourne
        le PID racine si un arbre a été tué, None sinon."""
        pid, proc = self._root_pid, self._proc
        killed: Optional[int] = None
        self._proc = None
        self._root_pid = None
        self._port = None
        if pid:
            if _kill_tree(pid):
                killed = pid
            try:
                from .process_reaper import unregister_process

                unregister_process(pid)
            except Exception:  # noqa: BLE001 — fail-open
                pass
        if proc is not None:
            try:
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass
        if self._user_data_dir:
            shutil.rmtree(self._user_data_dir, ignore_errors=True)
            self._user_data_dir = None
        return killed

    # ---------- capture des spawns externes (repli puppeteer) ----------

    @contextmanager
    def watch_spawn(self, label: str, poll_s: float = 4.0):
        """Fenêtre de capture : les chrome.exe apparus pendant le bloc (et
        marqués automation) sont enregistrés pour le taskkill final."""
        before = _pids_by_name("chrome.exe")
        try:
            yield
        finally:
            # Jamais d'exception du monitoring vers le bloc surveillé.
            try:
                self._collect_new_chrome_trees(label, before, poll_s)
            except Exception:  # noqa: BLE001 — fail-open
                pass

    def _collect_new_chrome_trees(self, label: str, before: Set[int], poll_s: float) -> None:
        if not _IS_WINDOWS:
            return
        deadline = time.time() + max(float(poll_s), 0.5)
        new_pids: Set[int] = set()
        while time.time() < deadline:
            new_pids = _pids_by_name("chrome.exe") - before
            if new_pids:
                break
            time.sleep(0.5)
        if not new_pids:
            # Chrome apparaîtra peut-être plus tard (serveur lazy) : le
            # sweep final le rattrapera (baseline + marqueur automation).
            return
        cmdlines = _cmdlines_by_pid("chrome.exe")
        certain = {p for p in new_pids if p in cmdlines
                   and _AUTOMATION_CHROME_MARKER in cmdlines[p]}
        if certain:
            with self._lock:
                self._watched.update(certain)
            logger.info(
                "[pool navigateur F-163] %s : arbre(s) chrome automation capturé(s) %s (kill au shutdown).",
                label, sorted(certain),
            )
        else:
            logger.debug(
                "[pool navigateur F-163] %s : %d nouveau(x) chrome.exe sans marqueur automation — non capturé(s).",
                label, len(new_pids),
            )

    # ---------- shutdown + sweep ----------

    def shutdown_run(self, reason: str = "fin de run") -> None:
        with self._lock:
            self._shutdown_locked(reason=reason)

    def _shutdown_locked(self, reason: str) -> None:
        """Tue l'arbre du pool, les arbres capturés, puis SWEEP les Chrome
        automation apparus pendant le run (hors baseline). Reset complet.

        Le sweep est REFUSÉ sous pytest (``_sweep_enabled``) : tuer de vrais
        process depuis une suite de tests est une action destructive prohibée.
        """
        killed: List[int] = []
        root = self._kill_current_locked()
        if root:
            killed.append(root)
        for pid in sorted(self._watched):
            if _kill_tree(pid):
                killed.append(pid)
        if self._sweep_enabled:
            swept = self._sweep_automation_locked()
            killed.extend(swept)
        if killed or self._spawn_count:
            print(
                f"[pool navigateur F-163] shutdown ({reason}) : "
                f"{len(killed)} arbre(s) tué(s) {killed}, {self._spawn_count} spawn(s) Chrome ce run."
            )
        self._run_id = None
        self._refcount = 0
        self._watched = set()
        self._disabled_reason = None

    def _sweep_automation_locked(self) -> List[int]:
        """Chrome/node automation apparus pendant le run et ENCORE vivants :

        - chrome.exe hors baseline dont la cmdline contient --remote-debugging-pipe
          (puppeteer/devtools-launchés — jamais le Chrome perso de l'utilisateur) ;
        - node.exe hors baseline dont la cmdline cite chrome-devtools-mcp ou
          server-puppeteer (serveurs MCP qui n'ont pas rendu la main).
        Échec PowerShell → SWEEP ANNULÉ (fail-safe utilisateur).
        """
        if not _IS_WINDOWS:
            return []
        chrome_candidates = _pids_by_name("chrome.exe") - self._baseline_chrome - {self._root_pid or 0}
        node_candidates = _pids_by_name("node.exe") - self._baseline_node
        targets: List[int] = []
        if chrome_candidates:
            cmdlines = _cmdlines_by_pid("chrome.exe")
            if not cmdlines and chrome_candidates:
                logger.warning(
                    "[pool navigateur F-163] sweep : cmdlines indisponibles — %d chrome(s) non balayé(s) (fail-safe).",
                    len(chrome_candidates),
                )
            else:
                targets.extend(
                    p for p in chrome_candidates
                    if p in cmdlines and _AUTOMATION_CHROME_MARKER in cmdlines[p]
                )
        if node_candidates:
            cmdlines = _cmdlines_by_pid("node.exe")
            targets.extend(
                p for p in node_candidates
                if p in cmdlines and (
                    "chrome-devtools-mcp" in cmdlines[p]
                    or "server-puppeteer" in cmdlines[p]
                )
            )
        return targets


# ============================================================
# Singleton + atexit
# ============================================================

_POOL: Optional[BrowserPool] = None
_POOL_LOCK = threading.Lock()


def get_browser_pool() -> BrowserPool:
    """Singleton process-wide (le graphe exécute les nœuds dans UN process)."""
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = BrowserPool()
        return _POOL


def reset_browser_pool() -> None:
    """Réinitialise le singleton (tests). Shutdown best-effort avant."""
    global _POOL
    with _POOL_LOCK:
        if _POOL is not None:
            try:
                _POOL.shutdown_run(reason="reset")
            except Exception:  # noqa: BLE001
                pass
        _POOL = BrowserPool()


def _atexit_shutdown() -> None:
    """Filet de fin de process : kill l'arbre si le workflow a crashé sans
    shutdown (le registre F-140 reste le filet inter-process)."""
    global _POOL
    if _POOL is not None:
        try:
            _POOL.shutdown_run(reason="atexit")
        except Exception:  # noqa: BLE001
            pass


atexit.register(_atexit_shutdown)
