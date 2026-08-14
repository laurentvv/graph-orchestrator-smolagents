"""Récupère l'historique COMPLET de `log.md` depuis git et l'importe DATÉ dans
`data/event_stream.duckdb` (table `run_event`). Clôture le chantier log.md (F-106).

Contexte (pourquoi ce script existe)
------------------------------------
La migration F-75 (2026-08-05, commit 44bf56e) avait supprimé `log.md` au profit
de l'event stream DuckDB, mais avec deux défauts :

1. **Dates historiques perdues** : `migrate_log.py` capturait la date des
   en-têtes `## [YYYY-MM-DD] type | titre` (groupe 1) mais ne l'utilisait jamais
   (ligne `match.group(1)` sans affectation) → les 194 événements migrés portent
   tous `created_at` = date de migration (2026-08-05 12:20).
2. **Fichier tronqué puis ré-alimenté** : `log.md` comptait 198 entrées avant
   suppression ; il a été re-créé à la main le 2026-08-12 et a repris sa
   croissance (3 entrées) — le flux plat n'était pas fermé.

La source de vérité historique est donc **git** : 47 versions du fichier
(2026-07-29 → 2026-08-14) contiennent l'union append-only de toutes les entrées,
en-têtes datés inclus.

Mode opératoire
---------------
1. `git log --follow --format="%H %cI" -- log.md` (toutes les versions, les deux
   ères du fichier — avant/après suppression F-75).
2. `git show <sha>:log.md` → parsing des entrées (`## [date] type | titre` +
   corps multi-lignes). Les sous-titres `## ` non datés (ex. `## 🔧 INFOS À
   SAVOIR`) sont rattachés au corps de l'entrée courante, ou capturés comme
   entrée `doc` de préambule s'ils précèdent toute entrée datée.
3. Union dédupliquée par (date, type, titre) — une entrée récurrente dans N
   versions n'est comptée qu'une fois.
4. Backup de la base (`data/event_stream.duckdb.bak.<ts>`) puis remplacement
   des lignes `run_id='legacy'` (copies sans date) par les entrées datées
   (`run_id='legacy_md'`). Le remplacement est strictement supérieur : mêmes
   messages source + dates restaurées.
5. Idempotent : les entrées `legacy_md` déjà présentes ne sont pas ré-insérées
   (clé event_type+titre).

Usage
-----
    uv run python scripts/recover_log_history.py            # exécution réelle
    uv run python scripts/recover_log_history.py --dry-run  # rapport seul
    uv run python scripts/recover_log_history.py --db PATH  # base alternative
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graph_orchestrator.event_stream import DEFAULT_EVENT_DB_PATH

HEADER_RE = re.compile(
    r"^## \[(?P<date>[^\]]+)\]\s*(?P<type>[\w-]+)\s*\|\s*(?P<title>.*)"
)


@dataclass(frozen=True)
class LogEntry:
    date: str  # "YYYY-MM-DD" ("" si absent — entrée de préambule)
    event_type: str
    title: str
    body: str
    first_seen: str = ""  # date ISO du commit où l'entrée apparaît (fallback)

    @property
    def key(self) -> tuple:
        return (self.date, self.event_type, self.title.strip())

    def created_at(self) -> datetime:
        """Date d'horodatage : date de l'en-tête, sinon date du commit de
        première apparition, sinon maintenant (dernier recours défensif)."""
        for cand in (self.date, self.first_seen):
            try:
                return datetime.strptime(cand[:10], "%Y-%m-%d")
            except (ValueError, TypeError):
                continue
        return datetime.now()

    def message(self) -> str:
        return "\n".join(x for x in (self.title, self.body) if x).strip()


def parse_log_entries(text: str) -> list[LogEntry]:
    """Parse les entrées d'une version de log.md.

    - `## [date] type | titre` ouvre une entrée ; les lignes suivantes (jusqu'au
      prochain en-tête) forment son corps.
    - Un sous-titre `## ...` NON daté est rattaché au corps de l'entrée courante
      (préservation du contenu) ; s'il précède toute entrée datée, il ouvre une
      entrée `doc` de préambule.
    - Les lignes avant tout en-tête sont ignorées (bruit de tête de fichier).
    """
    entries: list[LogEntry] = []
    cur: dict | None = None

    def _flush() -> None:
        nonlocal cur
        if cur is not None:
            entries.append(
                LogEntry(
                    date=cur["date"],
                    event_type=cur["type"],
                    title=cur["title"],
                    body="\n".join(cur["body"]).strip(),
                )
            )
            cur = None

    for raw in (text or "").splitlines():
        m = HEADER_RE.match(raw)
        if m:
            _flush()
            cur = {
                "date": m.group("date").strip(),
                "type": m.group("type").strip() or "note",
                "title": m.group("title").strip(),
                "body": [],
            }
        elif raw.startswith("## "):
            if cur is None:
                # Préambule non daté (ex. "## 🔧 INFOS À SAVOIR") → entrée doc.
                cur = {"date": "", "type": "doc", "title": raw[3:].strip(), "body": []}
            else:
                cur["body"].append(raw.rstrip())
        elif cur is not None:
            cur["body"].append(raw.rstrip())
    _flush()
    return entries


def collect_git_versions(
    repo_path: str, file_path: str = "log.md"
) -> list[tuple[str, str, str]]:
    """Toutes les versions git du fichier, du plus ANCIEN au plus RÉCENT.

    Retourne [(sha, commit_date_iso, contenu)]. `--follow` traverse la
    suppression F-75 (les deux ères du fichier sont couvertes).
    """
    r = subprocess.run(
        ["git", "-C", repo_path, "log", "--follow", "--format=%H %cI", "--", file_path],
        capture_output=True,
        text=True,
        check=True,
    )
    out: list[tuple[str, str, str]] = []
    for line in reversed(r.stdout.strip().splitlines()):
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        sha, commit_date = parts[0], parts[1].strip()
        show = subprocess.run(
            ["git", "-C", repo_path, "show", f"{sha}:{file_path}"],
            capture_output=True,
            text=True,
        )
        if show.returncode == 0:
            out.append((sha, commit_date, show.stdout))
    return out


def recover_entries(repo_path: str, file_path: str = "log.md") -> list[LogEntry]:
    """Union dédupliquée des entrées de TOUTES les versions git (ordre de
    première apparition)."""
    seen: dict[tuple, LogEntry] = {}
    order: list[LogEntry] = []
    for _sha, commit_date, text in collect_git_versions(repo_path, file_path):
        for e in parse_log_entries(text):
            if e.key not in seen:
                enriched = LogEntry(
                    date=e.date,
                    event_type=e.event_type,
                    title=e.title,
                    body=e.body,
                    first_seen=commit_date,
                )
                seen[e.key] = enriched
                order.append(enriched)
    return order


def insert_entries(
    db_path: str,
    entries: list[LogEntry],
    run_id: str = "legacy_md",
    replace_run_ids: tuple[str, ...] = ("legacy",),
    dry_run: bool = False,
) -> dict:
    """Importe les entrées datées dans run_event (idempotent).

    - Dedup contre l'existant : clé (event_type, première ligne du message =
      titre) pour `run_id` cible.
    - `replace_run_ids` : lignes anciennes supprimées avant insertion (les 194
      copies 'legacy' sans date — remplacées par les mêmes événements datés).
    """
    import duckdb

    stats = {
        "recovered": len(entries),
        "already_present": 0,
        "inserted": 0,
        "deleted_legacy": 0,
    }
    con = duckdb.connect(db_path)
    try:
        # Garde base fraîche (review Kilo #72) : la table peut ne pas exister
        # si aucune écriture n'a encore initialisé le schéma. Miroir de la
        # création dans scripts/log_event.py / event_stream.py.
        con.execute(
            """
            CREATE SEQUENCE IF NOT EXISTS event_seq;
            CREATE TABLE IF NOT EXISTS run_event (
                id          BIGINT DEFAULT nextval('event_seq'),
                run_id      VARCHAR NOT NULL,
                node        VARCHAR NOT NULL,
                event_type  VARCHAR NOT NULL,
                message     VARCHAR NOT NULL,
                created_at  TIMESTAMP DEFAULT now(),
                PRIMARY KEY (id)
            )
            """
        )
        existing = {
            (row[0], row[1])
            for row in con.execute(
                "SELECT event_type, split_part(message, chr(10), 1) "
                f"FROM run_event WHERE run_id = ?",
                [run_id],
            ).fetchall()
        }
        to_insert = [
            e
            for e in entries
            if (e.event_type, e.title.strip()) not in existing
        ]
        stats["already_present"] = len(entries) - len(to_insert)

        if dry_run:
            return stats

        for rid in replace_run_ids:
            # DuckDB : un DELETE ne renvoie pas de lignes de façon portable
            # (review Kilo #72) — on compte AVANT la suppression.
            n = con.execute(
                "SELECT count(*) FROM run_event WHERE run_id = ?", [rid]
            ).fetchone()[0]
            con.execute("DELETE FROM run_event WHERE run_id = ?", [rid])
            stats["deleted_legacy"] += int(n)

        for e in to_insert:
            con.execute(
                "INSERT INTO run_event(run_id, node, event_type, message, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                [run_id, "system", e.event_type, e.message(), e.created_at()],
            )
        stats["inserted"] = len(to_insert)
    finally:
        con.close()
    return stats


def backup_db(db_path: str) -> str | None:
    if not os.path.exists(db_path):
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{db_path}.bak.{ts}"
    shutil.copy2(db_path, bak)
    return bak


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    p.add_argument("--file", default="log.md")
    p.add_argument("--db", default=DEFAULT_EVENT_DB_PATH)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    entries = recover_entries(args.repo, args.file)
    dated = sum(1 for e in entries if e.date)
    print(f"[recover] {len(entries)} entrées uniques récupérées depuis git "
          f"({dated} datées, {len(entries) - dated} préambules sans date).")

    if args.dry_run:
        stats = insert_entries(args.db, entries, dry_run=True)
        print(f"[dry-run] {stats['already_present']} déjà en base, "
              f"{stats['recovered'] - stats['already_present']} seraient insérées.")
        for e in entries[:5]:
            print(f"  - [{e.date or e.first_seen[:10]}] {e.event_type} | {e.title[:80]}")
        print("  ...")
        return 0

    bak = backup_db(args.db)
    if bak:
        print(f"[backup] base sauvegardée → {bak}")

    stats = insert_entries(args.db, entries)
    print(f"[import] {stats['inserted']} entrée(s) insérée(s) datées "
          f"(run_id='legacy_md'), {stats['already_present']} déjà présentes, "
          f"{stats['deleted_legacy']} ligne(s) 'legacy' sans date remplacée(s).")
    print("[done] l'historique complet vit dans event_stream.duckdb — le fichier "
          "plat est désormais inutile (supprimable, F-106).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
