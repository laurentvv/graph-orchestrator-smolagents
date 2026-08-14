"""CLI d'historisation événementielle pour l'ASSISTANT IA (ZCode).

Remplace l'ancien journal texte (supprimé définitivement — F-106) : les
événements de fin de cycle (init/plan/fix/doc/merge/pr...) s'écrivent dans
`data/event_stream.duckdb` (table `run_event`), le même canal que l'outil
`log_event` exposé aux agents du graphe (tools.py). La base devient la source
de vérité unique du suivi — queryable en SQL, sans fichier plat croissant.

Usage
-----
    uv run python scripts/log_event.py <event_type> "<message>"
    uv run python scripts/log_event.py fix "Cycle F-99 terminé : GoalEnforcer branché" \
        --run-id f-99 --date 2026-08-14

Arguments
---------
    event_type  : type court (init, gen, eval, fix, error, doc, plan, merge,
                  pr, rch, audit, diag, cfg, run, sync, dec, note, test, done...).
    message     : description de l'événement (1+ lignes).
    --run-id    : identifiant de run (défaut : "assistant").
    --node      : émetteur (défaut : "assistant").
    --date      : date d'horodatage YYYY-MM-DD (défaut : maintenant — utile
                  pour rattraper un événement du jour).
    --db        : chemin de la base (défaut : data/event_stream.duckdb).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graph_orchestrator.event_stream import DEFAULT_EVENT_DB_PATH

# Vocabulaire recommandé (hérité de l'ancien journal plat — la liste n'est PAS
# bloquante, un type inconnu est accepté avec un avertissement).
RECOMMENDED_TYPES = {
    "init", "gen", "eval", "fix", "error", "doc", "docs", "plan", "merge",
    "pr", "rch", "audit", "diag", "cfg", "run", "sync", "dec", "note",
    "test", "done", "escalation",
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Journalise un événement dans data/event_stream.duckdb (canal assistant)."
    )
    p.add_argument("event_type", help="Type court : init/gen/eval/fix/error/doc/plan/merge/pr...")
    p.add_argument("message", help="Description de l'événement.")
    p.add_argument("--run-id", default="assistant", help="Identifiant de run (défaut : assistant).")
    p.add_argument("--node", default="assistant", help="Émetteur (défaut : assistant).")
    p.add_argument("--date", default=None, help="YYYY-MM-DD (défaut : maintenant).")
    p.add_argument("--db", default=DEFAULT_EVENT_DB_PATH, help="Chemin de la base DuckDB.")
    args = p.parse_args(argv)

    if args.event_type not in RECOMMENDED_TYPES:
        print(f"[warn] type '{args.event_type}' hors vocabulaire recommandé "
              f"({', '.join(sorted(RECOMMENDED_TYPES))}) — accepté quand même.")

    import duckdb

    created_at = None
    if args.date:
        try:
            created_at = datetime.strptime(args.date[:10], "%Y-%m-%d")
        except ValueError:
            print(f"[error] --date invalide : {args.date!r} (attendu YYYY-MM-DD).")
            return 2

    os.makedirs(os.path.dirname(os.path.abspath(args.db)), exist_ok=True)
    con = duckdb.connect(args.db)
    try:
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
        if created_at is not None:
            con.execute(
                "INSERT INTO run_event(run_id, node, event_type, message, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                [args.run_id, args.node, args.event_type, args.message, created_at],
            )
        else:
            con.execute(
                "INSERT INTO run_event(run_id, node, event_type, message) "
                "VALUES (?, ?, ?, ?)",
                [args.run_id, args.node, args.event_type, args.message],
            )
        row_id, total = con.execute(
            "SELECT max(id), count(*) FROM run_event"
        ).fetchone()
    finally:
        con.close()

    print(f"[ok] événement #{row_id} journalisé "
          f"({args.event_type} | run_id={args.run_id} | base {args.db} | "
          f"{total} événements au total).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
