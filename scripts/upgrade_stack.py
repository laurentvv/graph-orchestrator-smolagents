#!/usr/bin/env python3
"""
scripts/upgrade_stack.py — F-98 : Maintenance proactive des dépendances et de Python

Automatise le cycle de mise à niveau de la stack technique :
1. Lecture des versions actuelles dans uv.lock
2. Exécution de `uv lock --upgrade` et `uv sync`
3. Calcul et affichage du différentiel des versions (Majeure, Mineure, Patch)
4. Lancement automatisé des tests de non-régression (`pytest`)
5. Génération d'un résumé de montée de version prêt pour la PR / documentation
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Fix encodage console Windows (cp1252 / emojis)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass



def _parse_lockfile(lock_content: str) -> Dict[str, str]:
    """Parse sommaire de uv.lock pour extraire le dictionnaire {nom_paquet: version}."""
    packages: Dict[str, str] = {}
    current_name = None
    for line in lock_content.splitlines():
        line = line.strip()
        if line.startswith("name = "):
            current_name = line.split("=", 1)[1].strip().strip('"\'')
        elif line.startswith("version = ") and current_name:
            version = line.split("=", 1)[1].strip().strip('"\'')
            packages[current_name] = version
            current_name = None
    return packages


def _classify_bump(old_ver: str, new_ver: str) -> str:
    """Classifie le changement de version : MAJEURE, MINEURE, PATCH ou AUTRE."""
    old_parts = [int(p) for p in re.findall(r"\d+", old_ver)]
    new_parts = [int(p) for p in re.findall(r"\d+", new_ver)]
    if not old_parts or not new_parts:
        return "AUTRE"
    # Normalise à au moins 3 composants (major, minor, patch)
    while len(old_parts) < 3:
        old_parts.append(0)
    while len(new_parts) < 3:
        new_parts.append(0)
    if new_parts[0] > old_parts[0]:
        return "🔴 MAJEURE"
    if new_parts[1] > old_parts[1]:
        return "🟡 MINEURE"
    if new_parts[2] > old_parts[2]:
        return "🟢 PATCH"
    return "🟢 PATCH"


def run_upgrade(skip_tests: bool = False, pytest_args: str = "", save_report: bool = True) -> int:
    root_dir = Path(__file__).resolve().parent.parent
    os.chdir(root_dir)

    lock_file = root_dir / "uv.lock"
    old_packages: Dict[str, str] = {}
    if lock_file.exists():
        old_packages = _parse_lockfile(lock_file.read_text(encoding="utf-8"))

    print("=" * 70)
    print("  🚀 UPGRADE STACK (F-98) — Mise à jour des dépendances du projet")
    print("=" * 70)
    print(f"[*] Répertoire de travail : {root_dir}")
    print(f"[*] Paquets actuellement verrouillés : {len(old_packages)}")

    # 1. uv lock --upgrade
    print("\n[1/4] 📦 Exécution de 'uv lock --upgrade'...")
    res = subprocess.run(["uv", "lock", "--upgrade"], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[❌] Erreur lors de uv lock --upgrade :\n{res.stderr}")
        return res.returncode

    # 2. uv sync
    print("[2/4] 🔄 Synchronisation de l'environnement virtuel ('uv sync')...")
    res = subprocess.run(["uv", "sync"], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[❌] Erreur lors de uv sync :\n{res.stderr}")
        return res.returncode

    new_packages: Dict[str, str] = {}
    if lock_file.exists():
        new_packages = _parse_lockfile(lock_file.read_text(encoding="utf-8"))

    # 3. Différentiel
    print("[3/4] 📊 Calcul du différentiel des versions...")
    updated: List[Tuple[str, str, str, str]] = []
    added: List[Tuple[str, str]] = []
    removed: List[Tuple[str, str]] = []

    for name, new_v in sorted(new_packages.items()):
        if name in old_packages:
            old_v = old_packages[name]
            if old_v != new_v:
                bump = _classify_bump(old_v, new_v)
                updated.append((name, old_v, new_v, bump))
        else:
            added.append((name, new_v))

    for name, old_v in sorted(old_packages.items()):
        if name not in new_packages:
            removed.append((name, old_v))

    if not updated and not added and not removed:
        print("  ✨ Tous les paquets sont déjà à jour ! Aucun changement détecté.")
    else:
        print(f"\n  📦 {len(updated)} paquet(s) mis à jour, {len(added)} ajouté(s), {len(removed)} supprimé(s) :\n")
        print(f"  {'PAQUET':<30} {'ANCIENNE':<12} {'NOUVELLE':<12} {'TYPE'}")
        print("  " + "-" * 66)
        for name, old_v, new_v, bump in updated:
            print(f"  {name:<30} {old_v:<12} {new_v:<12} {bump}")
        for name, new_v in added:
            print(f"  + {name:<28} {'-':<12} {new_v:<12} ➕ AJOUT")
        for name, old_v in removed:
            print(f"  - {name:<28} {old_v:<12} {'-':<12} ➖ SUPPRIMÉ")

    # 4. Lancement des tests
    test_exit_code = 0
    if not skip_tests:
        print("\n[4/4] 🧪 Exécution des tests de non-régression (pytest)...")
        cmd = ["uv", "run", "pytest", "-v"]
        if pytest_args:
            cmd.extend(shlex.split(pytest_args))
        print(f"[*] Commande : {' '.join(cmd)}")
        test_res = subprocess.run(cmd)
        test_exit_code = test_res.returncode
        if test_exit_code == 0:
            print("\n[✅] Tous les tests sont passés avec succès !")
        else:
            print(f"\n[⚠️] Certains tests ont échoué (code de sortie {test_exit_code}). Diagnostic requis.")
    else:
        print("\n[4/4] ⏭️ Tests sautés (--skip-tests).")

    # Sauvegarde optionnelle du rapport
    if save_report:
        logs_dir = root_dir / "logs"
        logs_dir.mkdir(exist_ok=True)
        report_file = logs_dir / f"upgrade_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        report_content = [
            f"# Rapport de Mise à Niveau des Dépendances — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"- **Statut des tests :** {'✅ PASS' if test_exit_code == 0 else '❌ FAIL'}",
            f"- **Paquets mis à jour :** {len(updated)}",
            f"- **Paquets ajoutés :** {len(added)}",
            f"- **Paquets supprimés :** {len(removed)}\n",
            "## Détail des Changements\n",
            "| Paquet | Ancienne Version | Nouvelle Version | Type de Montée |",
            "|---|---|---|---|",
        ]
        for name, old_v, new_v, bump in updated:
            report_content.append(f"| `{name}` | `{old_v}` | `{new_v}` | {bump} |")
        for name, new_v in added:
            report_content.append(f"| `{name}` | - | `{new_v}` | ➕ Ajout |")
        for name, old_v in removed:
            report_content.append(f"| `{name}` | `{old_v}` | - | ➖ Supprimé |")
        report_file.write_text("\n".join(report_content), encoding="utf-8")
        print(f"\n[📄] Rapport de mise à niveau enregistré : {report_file}")

    print("\n" + "=" * 70)
    print("  🏁 UPGRADE TERMINÉ")
    print("=" * 70)
    return test_exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description="Automatisation de la montée de version des dépendances (F-98).")
    parser.add_argument("--skip-tests", action="store_true", help="Ne pas exécuter la suite pytest après la mise à jour.")
    parser.add_argument("--pytest-args", type=str, default="", help="Arguments supplémentaires à passer à pytest.")
    parser.add_argument("--no-report", action="store_true", help="Ne pas générer de rapport Markdown dans logs/.")
    args = parser.parse_args()

    exit_code = run_upgrade(
        skip_tests=args.skip_tests,
        pytest_args=args.pytest_args,
        save_report=not args.no_report,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
