#!/usr/bin/env python
"""Mise à jour du build llama.cpp CUDA vendé (vendor/llamacpp-cuda13) — F-123.

llama.cpp publie des nightlies quasi-quotidiennes (b####) et, depuis le passage
au versionnage sémantique (v0.2.0, 2026-08-21), des stables vX.Y.Z SANS aucun
binaire embarqué. On suit le canal NIGHTLY b#### (le seul téléchargeable, et le
nôtre : releases stables = « downstream/casual users », nightlies = « developers
and technical users », cf. ggml-org/ggml discussion #1579). Ce script automatise
la veille et la mise à jour du build vendé, SANS jamais appliquer sans demande
explicite (philosophie AGENTS.md §8/§11 : validation humaine avant application) :

  Vérification seule (défaut, réseau léger, ~1 s) :
      uv run python scripts/update_llamacpp.py            # ou --check
      → exit 0 : à jour | exit 2 : nouvelle version dispo (détails affichés)

  Application (télécharge ~540 Mo, swap avec rollback) :
      uv run python scripts/update_llamacpp.py --apply
      → télécharge llama-bXXXX-bin-win-cuda-13.3-x64.zip + cudart-...-13.3.zip,
        extrait en .new, VÉRIFIE (version + flags critiques spec-mtp/reasoning-
        preserve/cache-type), puis swap : ancien → llamacpp-cuda13-b<old>.bak,
        nouveau → llamacpp-cuda13. 1 backup conservé (--keep-backup N).

  Après --apply, TOUJOURS valider (non-régression GPU) :
      uv run python debug/test_mtp_spec.py --only reasoning --ctx 32768 --n-predict 60
      uv run pytest tests/test_llama_server_cmd.py -q

Options : --flavor cuda-13.3|cuda-12.4 (défaut 13.3, driver ≥ 580 requis),
--keep-backup N (défaut 1), --dry-run (télécharge/vérifie mais ne swappe pas).
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = PROJECT_ROOT / "vendor" / "llamacpp-cuda13"
RELEASES_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases"
# Flags dont l'absence dans un nouveau build casserait la production (F-123).
CRITICAL_FLAGS = ("--spec-type", "--reasoning-preserve", "--cache-type-k", "--flash-attn", "--parallel")


def current_build() -> int | None:
    exe = VENDOR_DIR / "llama-server.exe"
    if not exe.is_file():
        return None
    try:
        r = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=30)
        m = re.search(r"build (\d+)", r.stdout + r.stderr)
        return int(m.group(1)) if m else None
    except (subprocess.SubprocessError, OSError) as e:
        print(f"[!] impossible de lire la version courante : {e}")
        return None


def latest_release(flavor: str) -> tuple[int, list[dict]]:
    """Plus récente NIGHTLY b#### dotée d'assets binaires Windows.

    Versionnage sémantique (v0.2.0, 2026-08-21) : les stables vX.Y.Z sont des
    releases marquées « latest » par GitHub mais n'embarquent AUCUN binaire
    (seul nightly-tag.txt pointe vers la nightly correspondante) ; les nightlies
    b#### sont prerelease=true → invisibles de /releases/latest. On itère donc
    /releases et on prend la 1re b#### (peut-être encore en cours de publication
    → on exige ses assets win-cuda, sinon on continue dans la liste).
    """
    req = urllib.request.Request(
        RELEASES_API + "?per_page=20", headers={"User-Agent": "graph-orchestrator-f123"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        releases = json.loads(r.read().decode())
    for rel in releases:
        m = re.match(r"b(\d+)$", rel.get("tag_name", ""))
        if not m:
            continue
        assets = [
            a for a in rel.get("assets", [])
            if flavor in a["name"] and a["name"].endswith(".zip")
            and ("bin-win" in a["name"] or "cudart" in a["name"])
        ]
        if assets:
            return int(m.group(1)), assets
    raise RuntimeError("aucune release nightly b#### avec assets win-cuda dans les 20 dernières releases")


def verify_new_build(new_dir: Path, expected_build: int) -> bool:
    exe = new_dir / "llama-server.exe"
    if not exe.is_file():
        print("[!] llama-server.exe absent du build extrait")
        return False
    r = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=30)
    m = re.search(r"build (\d+)", r.stdout + r.stderr)
    if not m or int(m.group(1)) != expected_build:
        print(f"[!] version inattendue après extraction : {m.group(0) if m else 'inconnue'}")
        return False
    h = subprocess.run([str(exe), "--help"], capture_output=True, text=True, timeout=30)
    help_txt = h.stdout + h.stderr
    missing = [f for f in CRITICAL_FLAGS if f not in help_txt]
    if missing:
        print(f"[!] flags critiques absents du nouveau build : {missing}")
        return False
    return True


def download(url: str, dest: Path) -> None:
    print(f"[*] téléchargement {url.split('/')[-1]} ...")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "graph-orchestrator-f123"}), timeout=600) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    print(f"    {dest.stat().st_size / 1e6:.0f} Mo")


def apply_update(flavor: str, keep_backup: int, dry_run: bool) -> int:
    cur = current_build()
    with tempfile.TemporaryDirectory(prefix="llamacpp-upd-") as td:
        tdp = Path(td)
        new_dir = tdp / "new"
        zips = []
        for asset in latest_release(flavor)[1]:
            z = tdp / asset["name"]
            download(asset["browser_download_url"], z)
            zips.append(z)
        if not any("bin-win" in z.name for z in zips) or not any("cudart" in z.name for z in zips):
            print(f"[!] assets {flavor} incomplets (build + cudart requis)")
            return 1
        new_dir.mkdir()
        for z in zips:
            with zipfile.ZipFile(z) as zf:
                zf.extractall(new_dir)
        latest = latest_release(flavor)[0]
        if not verify_new_build(new_dir, latest):
            print("[!] vérification échouée — rien n'a été modifié")
            return 1
        if dry_run:
            print(f"[ok] build b{latest} vérifié en dry-run — aucun swap effectué")
            return 0
        # Rotation : courant → backup, .new → courant, purge des vieux backups.
        if cur:
            bak = VENDOR_DIR.parent / f"llamacpp-cuda13-b{cur}.bak"
            if bak.exists():
                shutil.rmtree(bak)
            shutil.move(str(VENDOR_DIR), str(bak))
            print(f"[*] ancien build conservé : {bak.name}")
        shutil.move(str(new_dir), str(VENDOR_DIR))
        old_baks = sorted(VENDOR_DIR.parent.glob("llamacpp-cuda13-b*.bak"))
        for b in old_baks[:-keep_backup] if keep_backup > 0 else old_baks:
            shutil.rmtree(b, ignore_errors=True)
            print(f"[*] backup purgé : {b.name}")
        print(f"[ok] vendor/llamacpp-cuda13 → b{latest}")
        print("[!] VALIDER maintenant :")
        print("    uv run python debug/test_mtp_spec.py --only reasoning --ctx 32768 --n-predict 60")
        print("    uv run pytest tests/test_llama_server_cmd.py -q")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="télécharge et swap (défaut : vérifie seulement)")
    ap.add_argument("--check", action="store_true", help="vérifie seulement (défaut)")
    ap.add_argument("--flavor", default="cuda-13.3", help="saveur d'asset Windows (défaut cuda-13.3)")
    ap.add_argument("--keep-backup", type=int, default=1, help="backups .bak conservés après swap (défaut 1)")
    ap.add_argument("--dry-run", action="store_true", help="télécharge + vérifie mais ne swappe pas")
    args = ap.parse_args()

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    cur = current_build()
    if cur is None:
        print("[!] aucun build courant detecte (vendor/llamacpp-cuda13/llama-server.exe)")
        return 1
    try:
        latest, assets = latest_release(args.flavor)
    except Exception as e:
        print(f"[!] echec requete GitHub API : {e}")
        return 1

    print(f"Courant : b{cur} | Dernier : b{latest} ({args.flavor}, {len(assets)} asset(s))")
    if latest <= cur:
        print("[ok] build a jour")
        return 0
    print(f"[+] NOUVELLE VERSION disponible : b{cur} -> b{latest}")
    if not assets:
        print(f"[!] aucun asset {args.flavor} dans la release — checker --flavor cuda-12.4")
        return 1
    if args.apply or args.dry_run:
        return apply_update(args.flavor, args.keep_backup, args.dry_run)
    print("[i] pour appliquer : uv run python scripts/update_llamacpp.py --apply (puis valider, cf. docstring)")
    return 2


if __name__ == "__main__":
    sys.exit(main())
