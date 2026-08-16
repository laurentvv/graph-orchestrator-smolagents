"""Runner de vérification : exécute les phases d'une Recipe et sonde l'app (F-100).

Port du flux d'exécution que le sub-agent verify de grok-cli effectue (et que
``references/hermes-agent/agent/verify/runner.py`` réimplémente en subprocess
pur) : install/bootstrap → build → test → start en arrière-plan → boucle de
readiness HTTP (curl-like) → teardown. Les commandes viennent de la recette du
projet (scripts package.json, cibles Makefile, …) et sont exécutées avec
``shell=True`` à dessein : outil de développeur exécutant les commandes de
build du projet dans son propre checkout — même niveau de confiance que le
terminal. (Dans l'usine, l'appelant du hot path ne sélectionne QUE la phase
``start`` ; bootstrap/build/test restent disponibles pour l'outillage debug.)

Écarts consciencieux vs la référence (adaptations à l'usine, documentés F-100) :
- ``phases=None`` (défaut = toutes) est distingué de ``phases=()`` (aucune),
  et ``phases`` ne sélectionne que bootstrap/build/test — le start est piloté
  par ``skip_start``. La référence encode ``"start"`` DANS la liste des phases
  (tout itérable falsy = toutes), ce qui rend « start seul » inexprimable.
- Substitution du placeholder ``{port}`` dans ``recipe.start`` : les recettes
  static-web (notre ajout) reçoivent le port effectif (port libre dynamique)
  au lieu d'un port figé en dur.
- Sonde readiness via opener SANS proxy (127.0.0.1 ne doit pas passer par un
  éventuel HTTP_PROXY d'environnement).
- Teardown Windows : ``taskkill /F /T /PID`` pour tuer l'ARBRE (cmd.exe + ses
  enfants — ``proc.terminate()`` ne tuerait que le shell et laisserait le
  serveur orphelin). Branche POSIX (killpg) = référence inchangée.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from graph_orchestrator.verify.recipes import Recipe

DEFAULT_PHASE_TIMEOUT = 600.0
DEFAULT_READY_TIMEOUT = 60.0
_TAIL_CHARS = 2000
PHASE_ORDER = ("bootstrap", "build", "test")


@dataclass
class PhaseResult:
    phase: str
    command: str
    exit_code: int | None
    duration: float
    output_tail: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "command": self.command,
            "exitCode": self.exit_code,
            "duration": round(self.duration, 3),
            "ok": self.ok,
            "timedOut": self.timed_out,
            "outputTail": self.output_tail,
        }


@dataclass
class ReadinessResult:
    url: str
    ready: bool
    status_code: int | None
    duration: float
    error: str | None = None
    output_tail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "ready": self.ready,
            "statusCode": self.status_code,
            "duration": round(self.duration, 3),
            "error": self.error,
            "outputTail": self.output_tail,
        }


@dataclass
class VerifyResult:
    recipe_name: str
    phases: list[PhaseResult] = field(default_factory=list)
    readiness: ReadinessResult | None = None

    @property
    def ok(self) -> bool:
        phases_ok = all(p.ok for p in self.phases)
        readiness_ok = self.readiness.ready if self.readiness is not None else True
        return phases_ok and readiness_ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipe": self.recipe_name,
            "ok": self.ok,
            "phases": [p.to_dict() for p in self.phases],
            "readiness": self.readiness.to_dict() if self.readiness else None,
        }


def _tail(text: str, limit: int = _TAIL_CHARS) -> str:
    return text[-limit:] if len(text) > limit else text


def _run_phase_command(
    phase: str,
    command: str,
    root: Path,
    timeout: float,
    on_output: Callable[[str], None] | None = None,
) -> PhaseResult:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            shell=True,  # commandes du projet ; cf. docstring module
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            text=True,
            errors="replace",
        )
        output = proc.stdout or ""
        exit_code: int | None = proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        raw = exc.output
        if isinstance(raw, bytes):
            output = raw.decode("utf-8", errors="replace")
        else:
            output = raw or ""
        exit_code = None
        timed_out = True
    duration = time.monotonic() - started
    if on_output and output:
        on_output(output)
    return PhaseResult(
        phase=phase,
        command=command,
        exit_code=exit_code,
        duration=duration,
        output_tail=_tail(output),
        timed_out=timed_out,
    )


def _poll_readiness(url: str, timeout: float, interval: float = 1.0) -> tuple[bool, int | None, str | None]:
    deadline = time.monotonic() + timeout
    last_error: str | None = None
    # Opener SANS proxy : la sonde vise 127.0.0.1 — un proxy d'environnement
    # (HTTP_PROXY corporate) ne doit pas intercepter le localhost (écart
    # défensif vs référence, qui utilise urlopen nu).
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        try:
            with opener.open(url, timeout=5) as resp:
                return True, resp.status, None
        except urllib.error.HTTPError as exc:
            # Le serveur a répondu — il est debout, même en 4xx/5xx.
            return True, exc.code, None
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last_error = str(exc)
        time.sleep(interval)
    return False, None, last_error


def _terminate_process_tree(proc: subprocess.Popen) -> None:
    """Termine le serveur démarré ET son arbre de process proprement.

    POSIX : l'enfant est spawné avec ``start_new_session=True`` → on signale
    tout le groupe (comportement référence, ``_terminate_process_group``).
    Windows (pas de killpg, et ``proc.terminate()`` ne tuerait que cmd.exe en
    laissant le serveur orphelin) : ``taskkill /F /T /PID`` tue l'arbre entier.
    """
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass
        return
    killpg = getattr(os, "killpg", None)
    getpgid = getattr(os, "getpgid", None)
    pgid = None
    if killpg is not None and getpgid is not None:
        try:
            pgid = getpgid(proc.pid)
        except (ProcessLookupError, PermissionError):
            pgid = None
    try:
        if pgid is not None and killpg is not None:
            killpg(pgid, signal.SIGTERM)
        else:
            proc.terminate()
    except (ProcessLookupError, PermissionError):
        return
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            if pgid is not None and killpg is not None:
                killpg(pgid, signal.SIGKILL)
            else:
                proc.kill()
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def _resolve_start_command(recipe: Recipe, port: int) -> str:
    """Substitue le placeholder ``{port}`` (recettes static-web) si présent."""
    if recipe.start and "{port}" in recipe.start:
        return recipe.start.replace("{port}", str(port))
    return recipe.start or ""


def _run_start_phase(
    recipe: Recipe,
    root: Path,
    ready_timeout: float,
    port_override: int | None = None,
) -> ReadinessResult:
    assert recipe.start is not None
    port = port_override or recipe.port or 8000
    command = _resolve_start_command(recipe, port)
    url = f"http://127.0.0.1:{port}{recipe.readiness_path}"
    started = time.monotonic()
    proc = subprocess.Popen(
        command,
        shell=True,  # commande de démarrage du projet ; cf. docstring module
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # groupe de process propre (POSIX) ; ignoré sous Windows
        text=True,
        errors="replace",
    )
    output = ""
    try:
        ready, status, error = _poll_readiness(url, ready_timeout)
    finally:
        _terminate_process_tree(proc)
        try:
            if proc.stdout is not None:
                output = proc.stdout.read() or ""
        except (OSError, ValueError):
            output = ""
    return ReadinessResult(
        url=url,
        ready=ready,
        status_code=status,
        duration=time.monotonic() - started,
        error=error,
        output_tail=_tail(output),
    )


def run_verify(
    root: Path,
    recipe: Recipe,
    phases: tuple[str, ...] | list[str] | None = None,
    phase_timeout: float = DEFAULT_PHASE_TIMEOUT,
    ready_timeout: float = DEFAULT_READY_TIMEOUT,
    skip_start: bool = False,
    port_override: int | None = None,
    stop_on_failure: bool = True,
    on_output: Callable[[str], None] | None = None,
) -> VerifyResult:
    """Exécute une passe de vérification pour ``recipe`` à la racine ``root``.

    Exécute séquentiellement les phases sélectionnées, puis (sauf
    ``skip_start``/échec de phase) lance ``recipe.start`` en arrière-plan,
    sonde l'URL de readiness et démonte l'arbre de process.

    ``phases`` ne sélectionne que les phases bootstrap/build/test :
    ``None`` (défaut) = toutes, ``()`` = aucune (start seul). Le start est
    piloté par ``skip_start`` (écart vs référence, qui encode ``"start"``
    dans la liste des phases — ce qui rend « start seul » inexprimable).
    """
    root = Path(root)
    selected = tuple(phases) if phases is not None else PHASE_ORDER
    result = VerifyResult(recipe_name=recipe.name)

    failed = False
    for phase in PHASE_ORDER:
        if phase not in selected:
            continue
        for command in getattr(recipe, phase):
            phase_result = _run_phase_command(phase, command, root, phase_timeout, on_output)
            result.phases.append(phase_result)
            if not phase_result.ok:
                failed = True
                if stop_on_failure:
                    return result

    if skip_start or failed or not recipe.start:
        return result

    result.readiness = _run_start_phase(recipe, root, ready_timeout, port_override)
    return result
