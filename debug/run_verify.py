"""Script d'isolation F-100 (déterministe, 0 LLM) — joue la vérification exécutable.

Démarre le serveur détecté pour un dossier (recette statique grok/hermes, ou
manifeste ``.verify/environment.json`` s'il PRIME), sonde la readiness HTTP,
démonte l'arbre de process, et imprime le verdict structuré. Miroir live du
Tier HTTP du Static Tester — pour valider un livrable ``runs/...`` sans
relancer le graphe.

Usage :
    uv run python debug/run_verify.py [dossier]        # défaut : cwd, start+readiness
    uv run python debug/run_verify.py [dossier] --full # + bootstrap/build/test
    uv run python debug/run_verify.py [dossier] --port 8123
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from graph_orchestrator.verify.environment import load_or_detect  # noqa: E402
from graph_orchestrator.verify.runner import PHASE_ORDER, run_verify  # noqa: E402


def _free_port() -> int | None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
        except OSError:
            return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Vérification exécutable (F-100)")
    parser.add_argument("dossier", nargs="?", default=".", help="Dossier projet (défaut : cwd)")
    parser.add_argument("--full", action="store_true",
                        help="Exécute aussi bootstrap/build/test (défaut : start seul)")
    parser.add_argument("--port", type=int, default=None, help="Port forcé (défaut : libre)")
    parser.add_argument("--timeout", type=float, default=15.0, help="Readiness timeout (s)")
    args = parser.parse_args()

    root = Path(args.dossier).resolve()
    if not root.is_dir():
        print(f"[KO] dossier introuvable : {root}")
        return 2

    recipe, source = load_or_detect(root)
    if recipe is None:
        print(f"[SKIP] aucune recette détectée dans {root}")
        return 0

    print(f"Recette  : {recipe.name} (kind={recipe.kind}, source={source})")
    print(f"  start  : {recipe.start or '(aucune)'}")
    print(f"  phases : bootstrap={recipe.bootstrap} build={recipe.build} test={recipe.test}")
    print(f"  probe  : port={recipe.port or 'dynamique'} readiness={recipe.readiness_path}")
    for line in recipe.evidence:
        print(f"  évidence: {line}")

    if not recipe.start:
        print("[SKIP] recette sans commande start — readiness impossible.")
        return 0

    port = args.port or _free_port()
    phases = None if args.full else ()
    print(f"\nExécution (phases={list(phases) if phases is not None else list(PHASE_ORDER) + ['start']}) "
          f"sur 127.0.0.1:{port}…")
    result = run_verify(root, recipe, phases=phases,
                        ready_timeout=args.timeout, port_override=port)

    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    print(f"\nVerdict : {'OK' if result.ok else 'ÉCHEC'}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
