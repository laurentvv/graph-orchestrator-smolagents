"""Reaper de process orphelins (P7/F-140, port qm process-reaper).

Port qm `src/processes/process-reaper.ts` (createReaperKillHook /
createProcessReaper) adapté sans psutil (Windows + stdlib) :

- REGISTRE : `data/.process_registry.json` — {pid: {kind, cmd_hint,
  started}} — alimenté par llama_server au spawn, nettoyé au stop. Survit aux
  crashes de l'orchestrateur (c'est le but).
- REAP : `reap_orphans(keep_pids)` au boot du workflow — tout pid enregistré,
  encore vivant, qui n'appartient PAS au process courant = orphelin d'un run
  précédent → `taskkill /F /T /PID` (kill de l'arbre), entrée purgée.
  Aliveness via `tasklist /FI "PID eq n"` (pas de psutil).
- Idempotent (reap déjà mort = simple purge d'entrée), fail-open TOTAL :
  jamais d'exception vers l'appelant.

Motivation (post-mortem run #13 : 10 llama-server spawnés / 0 arrêt loggé ;
fuites VRAM des runs interrompus) : les context managers python ne survivent
pas à un kill de l'orchestrateur — le registre disque, si.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from typing import Dict, List, Optional

_REGISTRY_PATH = os.path.join("data", ".process_registry.json")


def _load_registry() -> Dict[str, dict]:
    try:
        with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): v for k, v in data.items()} if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_registry(reg: Dict[str, dict]) -> None:
    try:
        os.makedirs(os.path.dirname(_REGISTRY_PATH) or ".", exist_ok=True)
        with open(_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def _pid_alive(pid: int) -> bool:
    """tasklist-based aliveness (Windows, pas de psutil). Best-effort."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=10,
        )
        return str(pid) in (out.stdout or "")
    except Exception:
        return False


def _kill_tree(pid: int) -> bool:
    """taskkill /F /T sur l'arbre du pid. Best-effort."""
    try:
        out = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True, text=True, timeout=15,
        )
        return out.returncode == 0
    except Exception:
        return False


def register_process(pid: int, kind: str, cmd_hint: str = "") -> None:
    """Déclare un process spawné (appelé au spawn). Fail-open."""
    if not pid:
        return
    try:
        reg = _load_registry()
        reg[str(pid)] = {
            "kind": kind,
            "cmd_hint": cmd_hint[:160],
            "started": datetime.now().isoformat(timespec="seconds"),
        }
        _save_registry(reg)
    except Exception:
        pass


def unregister_process(pid: int) -> None:
    """Retire un process proprement arrêté (appelé au stop). Fail-open."""
    try:
        reg = _load_registry()
        if reg.pop(str(pid), None) is not None:
            _save_registry(reg)
    except Exception:
        pass


def reap_orphans(keep_pids: Optional[set] = None) -> List[str]:
    """Tue les process enregistrés orphelins d'un run précédent.

    Args:
        keep_pids: pids à préserver (process du run COURANT — par défaut les
            descendants du process courant sont épargnés via keep de soi-même).

    Retourne la liste des actions (pour log/observabilité). Idempotent,
    fail-open : ne lève JAMAIS.
    """
    actions: List[str] = []
    try:
        keep = set(keep_pids or set())
        keep.add(os.getpid())
        reg = _load_registry()
        if not reg:
            return actions
        changed = False
        for pid_str, meta in list(reg.items()):
            try:
                pid = int(pid_str)
            except ValueError:
                reg.pop(pid_str, None)
                changed = True
                continue
            if pid in keep:
                continue
            if not _pid_alive(pid):
                # Déjà mort : purge silencieuse de l'entrée.
                reg.pop(pid_str, None)
                changed = True
                continue
            # Vivant ET pas à nous : orphelin d'un run précédent.
            kind = (meta or {}).get("kind", "?")
            hint = (meta or {}).get("cmd_hint", "")
            if _kill_tree(pid):
                actions.append(f"REAPED pid={pid} ({kind} {hint})")
                reg.pop(pid_str, None)
            else:
                actions.append(f"REAP FAILED pid={pid} ({kind} {hint}) — entrée conservée")
            changed = True
        if changed or actions:
            _save_registry(reg)
        return actions
    except Exception as e:
        actions.append(f"reaper erreur (fail-open) : {e}")
        return actions
