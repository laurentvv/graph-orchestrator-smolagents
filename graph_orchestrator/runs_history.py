"""Runs History persistant sur DuckDB (Base séparée).

Gère l'historisation des runs (statistiques globales) et le suivi budgétaire 
(Budget Tracker) dans une base DuckDB dédiée (par défaut `data/runs_history.duckdb`).
Cette base séparée stocke :
1. Les statistiques complètes de chaque run (durée, tokens, succès/échec, modèle).
2. Les dépenses en tokens/USD pour le mécanisme de coupe-circuit financier (Budget Tracker).
"""

import os
import duckdb
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

DEFAULT_HISTORY_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "runs_history.duckdb")
DEFAULT_BUDGET_WINDOW_S = 86400  # 24 heures

class RunsHistoryDB:
    def __init__(self, path: str = DEFAULT_HISTORY_DB_PATH):
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._init_schema()

    def _get_conn(self):
        return duckdb.connect(self.path, read_only=False)

    def _init_schema(self) -> None:
        try:
            with self._get_conn() as c:
                # Table des statistiques globales de run
                c.execute("""
                    CREATE TABLE IF NOT EXISTS run_stats (
                        run_id      VARCHAR PRIMARY KEY,
                        status      VARCHAR NOT NULL,
                        model_id    VARCHAR,
                        start_time  TIMESTAMP,
                        end_time    TIMESTAMP,
                        total_cost_usd DOUBLE DEFAULT 0.0,
                        input_tokens   BIGINT DEFAULT 0,
                        output_tokens  BIGINT DEFAULT 0
                    )
                """)
                # Table des dépenses unitaires pour le Budget Tracker
                c.execute("CREATE SEQUENCE IF NOT EXISTS spend_seq")
                c.execute("""
                    CREATE TABLE IF NOT EXISTS spend_event (
                        id           BIGINT DEFAULT nextval('spend_seq'),
                        principal_id VARCHAR NOT NULL,
                        run_id       VARCHAR,
                        cost_usd     DOUBLE NOT NULL,
                        created_at   TIMESTAMP DEFAULT now(),
                        PRIMARY KEY (id)
                    )
                """)
        except Exception:
            pass

    def record_spend(self, principal_id: str, run_id: Optional[str], cost_usd: float) -> None:
        """Enregistre une dépense pour un identifiant donné."""
        try:
            with self._get_conn() as c:
                c.execute(
                    "INSERT INTO spend_event(principal_id, run_id, cost_usd) VALUES (?, ?, ?)",
                    [principal_id, run_id, cost_usd]
                )
                if run_id:
                    # Met à jour le run_stats si le run_id existe
                    c.execute("""
                        UPDATE run_stats 
                        SET total_cost_usd = total_cost_usd + ?
                        WHERE run_id = ?
                    """, [cost_usd, run_id])
        except Exception as e:
            print(f"[RunsHistory Fallback] Failed to record spend: {e}")

    def check_budget(self, principal_id: str, limit_usd: float, window_s: int = DEFAULT_BUDGET_WINDOW_S) -> Dict[str, Any]:
        """Vérifie si le principal_id a dépassé son budget sur la fenêtre donnée."""
        try:
            with self._get_conn() as c:
                cutoff = datetime.now() - timedelta(seconds=window_s)
                res = c.execute("""
                    SELECT SUM(cost_usd) 
                    FROM spend_event 
                    WHERE principal_id = ? AND created_at >= ?
                """, [principal_id, cutoff]).fetchone()
                
                spent_usd = res[0] if res and res[0] is not None else 0.0
                return {
                    "allowed": spent_usd < limit_usd,
                    "spent_usd": spent_usd,
                    "limit_usd": limit_usd,
                    "window_s": window_s
                }
        except Exception as e:
            print(f"[RunsHistory Fallback] Failed to check budget: {e}")
            return {"allowed": True, "spent_usd": 0.0, "limit_usd": limit_usd, "window_s": window_s}

    def start_run(self, run_id: str, model_id: str) -> None:
        """Enregistre le début d'un nouveau run."""
        try:
            with self._get_conn() as c:
                c.execute("""
                    INSERT INTO run_stats(run_id, status, model_id, start_time) 
                    VALUES (?, 'running', ?, now())
                    ON CONFLICT (run_id) DO UPDATE SET status='running', start_time=now()
                """, [run_id, model_id])
        except Exception:
            pass

    def end_run(self, run_id: str, status: str, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """Enregistre la fin d'un run avec ses stats globales."""
        try:
            with self._get_conn() as c:
                c.execute("""
                    UPDATE run_stats 
                    SET status = ?, end_time = now(), input_tokens = input_tokens + ?, output_tokens = output_tokens + ?
                    WHERE run_id = ?
                """, [status, input_tokens, output_tokens, run_id])
        except Exception:
            pass

# Instance globale (lazily instanciated)
_global_runs_history_db = None

def get_runs_history_db() -> RunsHistoryDB:
    global _global_runs_history_db
    if _global_runs_history_db is None:
        _global_runs_history_db = RunsHistoryDB()
    return _global_runs_history_db
