"""Script d'isolation LIVE de la robustesse FS (F-95, Priorité 8-bis).

Convention F-89 : appelle les VRAIES fonctions de production (0 mock, 0 LLM,
déterministe). Valide en conditions réelles les 3 couches du port OpenKB :

1. **Transaction + crash-recovery** : snapshot → mutation → « process mort »
   (journal actif laissé sur disque) → le drain au moment de prendre le verrou
   exclusif roule back l'état pré-mutation.
2. **Verrou exclusif cross-process** : un subprocess tient le lock → le
   parent reçoit FsLockTimeout (borné), puis acquiert après libération.
3. **Cloisonnement IO** : racines enregistrées → write_file dehors bloqué,
   dedans fonctionnel ; sans racines → fail-open.

Usage : ``uv run python debug/run_fs_safety.py``
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from graph_orchestrator.fs_locks import FsLockTimeout, write_lock  # noqa: E402
from graph_orchestrator.fs_tx import recover_pending_journals, snapshot_paths  # noqa: E402
from graph_orchestrator.io_guard import scoped_allowed_roots  # noqa: E402
from graph_orchestrator.tools import write_file  # noqa: E402


def _check(name: str, condition: bool, detail: str = "") -> bool:
    status = "✅" if condition else "❌"
    print(f"  {status} {name}" + (f" — {detail}" if detail and not condition else ""))
    return condition


def demo_transaction_crash_recovery(root: Path) -> bool:
    print("\n[1] Transaction FS + crash-recovery (fs_tx + drain au verrou)")
    ok = True
    victim = root / "index.html"
    victim.write_text("<!-- état CONNU pré-mutation -->", encoding="utf-8")

    snap = snapshot_paths(root, [victim], operation="demo:coder:iter1")
    victim.write_text("<!-- mutation À MOITIÉ APPLIQUÉE (process tué) -->", encoding="utf-8")
    created = root / "script.js"
    created.write_text("// créé par la mutation crashée", encoding="utf-8")
    snap.track_new([created])
    # Process « mort » : ni commit ni rollback, journal "active" sur disque.

    with write_lock(root):  # 1re acquisition exclusive → drain
        pass
    ok &= _check(
        "fichier modifié roulé back à l'état CONNU",
        victim.read_text(encoding="utf-8") == "<!-- état CONNU pré-mutation -->",
        victim.read_text(encoding="utf-8"),
    )
    ok &= _check("fichier créé par la mutation crashée supprimé", not created.exists())
    ok &= _check("journal + backup nettoyés (discard)", not snap.journal_path.exists())
    ok &= _check("recover idempotent (2e appel = silence)", recover_pending_journals(root) == [])
    return ok


_CHILD = """
import sys, time
sys.path.insert(0, {repo!r})
from pathlib import Path
from graph_orchestrator.fs_locks import write_lock
root = Path({root!r})
with write_lock(root, timeout_s=30):
    (root / "CHILD_READY").write_text("held", encoding="utf-8")
    time.sleep(2)
(root / "CHILD_DONE").write_text("done", encoding="utf-8")
"""


def demo_cross_process_lock(root: Path) -> bool:
    print("\n[2] Verrou exclusif cross-process (.fs_tx/dir.lock)")
    ok = True
    child = subprocess.Popen(
        [sys.executable, "-c", _CHILD.format(repo=str(REPO), root=str(root))],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        while not (root / "CHILD_READY").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        ok &= _check("subprocess tient le lock (CHILD_READY)", (root / "CHILD_READY").exists())
        try:
            with write_lock(root, timeout_s=1.0):
                pass
            ok &= _check("parent BLOQUÉ pendant détention (FsLockTimeout)", False, "pas d'exception")
        except FsLockTimeout:
            ok &= _check("parent BLOQUÉ pendant détention (FsLockTimeout)", True)
        deadline = time.monotonic() + 15
        while not (root / "CHILD_DONE").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        with write_lock(root, timeout_s=10.0):
            held_ok = True
        ok &= _check("parent acquiert après libération", held_ok)
    finally:
        child.wait(timeout=30)
    return ok


def demo_io_guard(root: Path) -> bool:
    print("\n[3] Cloisonnement IO (allowlist de chemins, tools.write_file)")
    ok = True
    run_dir = root / "run"
    run_dir.mkdir()
    factory_file = root / "graph_orchestrator_tools.py"

    with scoped_allowed_roots([run_dir]):
        denied = write_file(str(factory_file), "print('corruption de l usine')")
        ok &= _check(
            "write_file HORS racine bloqué ('Access denied')",
            "Access denied" in denied and not factory_file.exists(),
        )
        inside = write_file(str(run_dir / "app.js"), "console.log('livrable du run');")
        ok &= _check(
            "write_file DANS la racine fonctionnel",
            inside.startswith("Successfully wrote") and (run_dir / "app.js").is_file(),
        )
    free = write_file(str(root / "libre.txt"), "fail-open hors run (tests/debug)")
    ok &= _check(
        "fail-open sans racine enregistrée",
        free.startswith("Successfully wrote") and (root / "libre.txt").is_file(),
    )
    return ok


def main() -> int:
    print("=" * 64)
    print("  F-95 — Robustesse FS LIVE (fs_tx + fs_locks + io_guard)")
    print("=" * 64)
    with tempfile.TemporaryDirectory(prefix="f95_live_") as td:
        root = Path(td)
        results = [
            demo_transaction_crash_recovery(root),
            demo_cross_process_lock(root),
            demo_io_guard(root),
        ]
    print("\n" + ("=" * 64))
    if all(results):
        print("  🟢 RÉSULTAT : 3/3 démos PASS — F-95 validé en isolation LIVE.")
        return 0
    print(f"  🔴 RÉSULTAT : {sum(results)}/3 démos PASS — voir ❌ ci-dessus.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
