#!/usr/bin/env python3
"""
parse_run_result.py — Lit le verdict d'un run dans son log et l'injecte dans
le tableau de bord ``prompts/test_results.md``.

Le verdict est émis par ``graph_orchestrator/workflows.py`` (run_workflow) sous
la forme d'un panneau « RÉSULTAT FINAL DU GRAPHE » contenant un JSON :
    {
      "architect_plans": <int>,
      "final_results": [ {"status": "success"|"failure"|"escalated"|
                                     "max_iterations_reached"|"replayed",
                          "task_id": "..."} ]
    }

Usage ::
    # Run le plus récent
    uv run python scripts/parse_run_result.py

    # Run spécifique (dossier ou log)
    uv run python scripts/parse_run_result.py logs/run_coding_2026-08-05_160251
    uv run python scripts/parse_run_result.py logs/run_coding_2026-08-05_160251/run_full.log

    # Associé à un test du catalogue (recommandé : pour le suivi)
    uv run python scripts/parse_run_result.py --test-id bubble-sort-multifile

    # Aperçu seulement, sans écrire dans test_results.md
    uv run python scripts/parse_run_result.py --dry-run

Règles de statut :
  - tous les final_results à "success" (ou "replayed")  → ✅ Succès
  - au moins un "failure" / "max_iterations_reached"     → ❌ Échec
  - au moins un "escalated" (sans failure)               → ⚠️ Escaladé
  - aucun bloc « RÉSULTAT FINAL » trouvé dans le log     → ⏹️ Interrompu
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Racine du projet = parent du dossier scripts/.
ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = ROOT / "logs"
RESULTS_MD = ROOT / "prompts" / "test_results.md"

# Bornes du panneau affiché par Rich Panel (titre "RÉSULTAT FINAL DU GRAPHE").
# Rich intègre le titre DANS la bordure du haut : ┌── RÉSULTAT FINAL DU GRAPHE ──┐
# On capture les lignes entre cette bordure du haut et la bordure du bas └ … ┘.
_FINAL_BLOCK_RE = re.compile(
    r"┌.*?RÉSULTAT FINAL DU GRAPHE.*?┐\s*\n(?P<body>.*?)└.*?┘",
    re.DOTALL,
)


# ==========================================
# 1. Résolution du log à analyser
# ==========================================
def _resolve_log_path(target: str | None) -> Path:
    """Retourne le chemin du fichier run_full.log à analyser.

    - target=None → le run le plus récent sous logs/ (par mtime).
    - target=dossier → <dossier>/run_full.log.
    - target=fichier → le fichier lui-même.
    """
    if target:
        p = Path(target)
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        if p.is_dir():
            log = p / "run_full.log"
            if not log.exists():
                sys.exit(f"[!] {log} introuvable dans le dossier {p}")
            return log
        if p.is_file():
            return p
        sys.exit(f"[!] Cible introuvable : {p}")
    # Cible par défaut : run le plus récent.
    candidates = sorted(LOGS_DIR.glob("run_coding_*/run_full.log"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not candidates:
        sys.exit(f"[!] Aucun log trouvé sous {LOGS_DIR}/run_coding_*/run_full.log")
    return candidates[0]


# ==========================================
# 2. Parsing du verdict
# ==========================================
def _strip_panel_borders(body: str) -> str:
    """Retire les bordures verticales │ et le remplissage de Rich Panel."""
    lines = []
    for raw in body.splitlines():
        line = raw
        # Retire un éventuel │ de début et de fin (bordures Rich).
        if line.startswith("│"):
            line = line[1:]
        if line.rstrip().endswith("│"):
            line = line.rstrip()[:-1]
        lines.append(line)
    return "\n".join(lines)


def parse_verdict(log_path: Path) -> dict:
    """Extrait le verdict du log. Lève ValueError si bloc introuvable."""
    text = log_path.read_text(encoding="utf-8", errors="replace")
    m = _FINAL_BLOCK_RE.search(text)
    if not m:
        raise ValueError("bloc « RÉSULTAT FINAL DU GRAPHE » introuvable (run interrompu ?)")
    body = _strip_panel_borders(m.group("body"))
    data = json.loads(body)  # may raise JSONDecodeError
    return data


def aggregate_status(data: dict) -> tuple[str, str]:
    """Retourne (emoji, statut_global). Voir règles en docstring du module."""
    results = data.get("final_results", [])
    statuses = [r.get("status") for r in results if isinstance(r, dict)]
    if not statuses:
        return "⏹️", "interrompu"
    ok = {"success", "replayed"}
    hard_fail = {"failure", "max_iterations_reached"}
    if any(s in hard_fail for s in statuses):
        return "❌", "échec"
    if any(s == "escalated" for s in statuses):
        return "⚠️", "escaladé"
    if all(s in ok for s in statuses):
        return "✅", "succès"
    return "🟡", "partiel"


def extract_test_id(log_path: Path) -> str | None:
    """Tente de retrouver l'id du test (ligne « Exécution de l'Architecte pour … »)."""
    text = log_path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"Exécution de l'Architecte pour la tâche globale\s*:\s*(\S+)", text)
    return m.group(1).strip() if m else None


def detect_run_dir(log_path: Path) -> str:
    """Retourne le chemin relatif du dossier de run (pour la colonne « run »)."""
    run_dir = log_path.parent
    try:
        return run_dir.relative_to(ROOT).as_posix()
    except ValueError:
        return str(run_dir)


def infer_date_from_dirname(run_dir: str) -> str:
    """Extrait la date YYYY-MM-DD d'un nom type run_coding_2026-08-05_160251."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", run_dir)
    return m.group(1) if m else datetime.now().strftime("%Y-%m-%d")


# ==========================================
# 3. Rendu Markdown
# ==========================================
def build_md_row(test_id: str, date: str, run: str, emoji: str, status: str, details: str) -> str:
    note = f"{details}" if details else "—"
    return f"| {test_id} | {date} | `{run}` | {emoji} {status} | {note} |"


def details_from_verdict(data: dict, status_label: str) -> str:
    """Compose une note courte résumant le verdict."""
    results = data.get("final_results", [])
    parts = [f"{r.get('status')} ({r.get('task_id')})" for r in results if isinstance(r, dict)]
    summary = ", ".join(parts) if parts else "vide"
    return f"`final_results`: {summary}"


# ==========================================
# 4. Injection dans test_results.md
# ==========================================
def append_row_to_results_md(row: str, run_dir: str) -> None:
    """Insère une ligne dans le tableau « Historique des runs » de test_results.md.

    On l'ajoute juste après la ligne séparatrice d'en-tête du tableau, pour
    garder un ordre chronologique lisible (lignes les plus récentes en haut).

    Garde anti-doublon : si ``run_dir`` est déjà mentionné dans une ligne du
    tableau, on n'ajoute rien (le run est déjà consigné).
    """
    if not RESULTS_MD.exists():
        sys.exit(f"[!] {RESULTS_MD} introuvable.")
    content = RESULTS_MD.read_text(encoding="utf-8")

    # Garde anti-doublon : on cherche le chemin du run entre backticks.
    if run_dir in content:
        print(f"[!] Le run '{run_dir}' est déjà présent dans {RESULTS_MD.relative_to(ROOT)} — rien ajouté.")
        return

    header_re = re.compile(
        r"(\| test_id \| date \| run \(log\) \| statut \| notes post-run \|\n\| :--- \| :--- \| :--- \| :--- \| :--- \|\n)",
        re.MULTILINE,
    )
    if not header_re.search(content):
        sys.exit("[!] En-tête du tableau « Historique des runs » introuvable dans test_results.md.")
    new_content = header_re.sub(lambda m: m.group(1) + row + "\n", content, count=1)
    if new_content == content:
        print("[!] Aucune modification effectuée (en-tête non matché ?)")
        return
    RESULTS_MD.write_text(new_content, encoding="utf-8")
    print(f"[+] Ligne ajoutée dans {RESULTS_MD.relative_to(ROOT)}")


# ==========================================
# 5. CLI
# ==========================================
def main() -> None:
    ap = argparse.ArgumentParser(description="Parse le verdict d'un run et met à jour prompts/test_results.md.")
    ap.add_argument("target", nargs="?", default=None, help="Dossier de run ou fichier log (défaut : run le plus récent).")
    ap.add_argument("--test-id", default=None, help="id du test du catalogue (ex: bubble-sort-multifile). Sinon auto-détecté depuis le log.")
    ap.add_argument("--dry-run", action="store_true", help="Afficher le verdict sans écrire dans test_results.md.")
    args = ap.parse_args()

    log_path = _resolve_log_path(args.target)
    print(f"[*] Log analysé : {log_path.relative_to(ROOT)}")

    run = detect_run_dir(log_path)
    date = infer_date_from_dirname(run)

    try:
        data = parse_verdict(log_path)
    except ValueError as e:
        # Run interrompu : pas de bloc final.
        test_id = args.test_id or extract_test_id(log_path) or "inconnu"
        emoji, status = "⏹️", "interrompu"
        row = build_md_row(test_id, date, run, emoji, status, f"aucun bloc final ({e})")
        print(f"[*] Verdict : {emoji} {status} — {e}")
        print(row)
        if not args.dry_run:
            append_row_to_results_md(row, run)
        return
    except json.JSONDecodeError as e:
        sys.exit(f"[!] Bloc final trouvé mais JSON invalide : {e}")

    emoji, status_label = aggregate_status(data)
    test_id = args.test_id or extract_test_id(log_path) or "inconnu"
    details = details_from_verdict(data, status_label)
    row = build_md_row(test_id, date, run, emoji, status_label, details)

    print(f"[*] Verdict : {emoji} {status_label}")
    print(row)
    if args.dry_run:
        return
    append_row_to_results_md(row, run)


if __name__ == "__main__":
    main()
