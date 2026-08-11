#!/usr/bin/env python3
"""Charge un prompt de validation (prompts/validation/*.md) dans tasks.json.

Automatise l'étape 1 du workflow coding (AGENTS.md §7.1) : au lieu de copier/coller
à la main un prompt depuis references/Prompt-Vault/ (gitignoré) ou prompts/validation/,
ce script lit un fichier .md (frontmatter YAML + corps) et écrit le corps dans la 1ʳᵉ
entrée du mode choisi de tasks.json (coding par défaut), avec id + target_files.

Usage :
    uv run python scripts/load_prompt.py prompts/validation/bubble_sort.md
    uv run python scripts/load_prompt.py prompts/validation/skill_finder_ai_sdk.md
    uv run python scripts/load_prompt.py prompts/validation/bubble_sort.md --mode one_shot

Le loader remplace la 1ʳᵉ entrée du mode (préserve les autres modes). Ne lève pas sur
un tasks.json manquant (en crée un minimal). Idempotent.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_prompt_file(path: Path) -> tuple[dict, str]:
    """Lit un .md à frontmatter YAML → (meta dict, corps). Ne lève jamais.

    Repli sans yaml : parse les lignes `key: value` (target_files en CSV inline).
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text.strip()
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text.strip()
    fm, body = parts[1], parts[2].lstrip("\n")
    meta: dict = {}
    # Essai yaml (dispo dans l'env du projet via skills_loader).
    try:
        import yaml  # type: ignore
        loaded = yaml.safe_load(fm)
        if isinstance(loaded, dict):
            meta = loaded
    except Exception:
        # Repli minimal : key: value, target_files accepté en CSV inline.
        for line in fm.splitlines():
            if ":" in line and not line.startswith((" ", "\t", "-")):
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
    return meta, body.strip()


def _coerce_target_files(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    return [t.strip() for t in str(raw).split(",") if t.strip()]


def load_tasks(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Charge un prompt de validation dans tasks.json.")
    ap.add_argument("prompt_file", help="Chemin du .md (ex: prompts/validation/bubble_sort.md)")
    ap.add_argument("--mode", default="coding",
                    choices=["coding", "one_shot", "exploration"],
                    help="Section de tasks.json à peupler (défaut: coding)")
    ap.add_argument("--tasks", default="tasks.json", help="Chemin du tasks.json (défaut: tasks.json)")
    args = ap.parse_args(argv)

    prompt_path = Path(args.prompt_file)
    if not prompt_path.exists():
        print(f"[!] Fichier introuvable: {prompt_path}", file=sys.stderr)
        return 2

    tasks_path = Path(args.tasks)
    meta, body = parse_prompt_file(prompt_path)
    if not body:
        print(f"[!] Corps du prompt vide dans {prompt_path}", file=sys.stderr)
        return 2

    entry: dict = {
        "id": meta.get("id") or prompt_path.stem,
        "content": body,
    }
    target_files = _coerce_target_files(meta.get("target_files"))
    if target_files:
        entry["target_files"] = target_files

    tasks = load_tasks(tasks_path)
    tasks.setdefault(args.mode, [])
    if tasks[args.mode]:
        tasks[args.mode][0] = entry
    else:
        tasks[args.mode].append(entry)

    tasks_path.write_text(
        json.dumps(tasks, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"[+] Prompt chargé : {prompt_path.name}")
    print(f"    mode         : {args.mode}")
    print(f"    id           : {entry['id']}")
    print(f"    target_files : {entry.get('target_files', '(non défini)')}")
    print(f"    contenu      : {len(body)} cars → {tasks_path}")
    if meta.get("expected_skill_finder") and meta["expected_skill_finder"] != "none":
        print(f"    skill_finder : {meta['expected_skill_finder']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
