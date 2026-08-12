"""Event Stream persistant sur DuckDB (Base séparée).

Gère l'historisation des événements (logs chronologiques) dans une base DuckDB dédiée
(par défaut `data/event_stream.duckdb`), séparée de la base de graphe (`data/graph_orchestrator.db`).
Cette séparation évite de bloquer la base principale (Knowledge Graph) lors d'un run,
et permet à des scripts d'analyse externes ou au terminal UI de lire les logs sans conflits de verrous.
"""

import os
import duckdb

DEFAULT_EVENT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "event_stream.duckdb")

class EventStreamDB:
    def __init__(self, path: str = DEFAULT_EVENT_DB_PATH):
        self.path = path
        # S'assurer que le dossier data/ existe
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        # On ouvre et referme la connexion rapidement à chaque appel pour éviter de hold le lock
        self._init_schema()

    def _get_conn(self):
        return duckdb.connect(self.path, read_only=False)

    def _init_schema(self) -> None:
        """Crée le schéma de l'event stream."""
        try:
            with self._get_conn() as c:
                c.execute("CREATE SEQUENCE IF NOT EXISTS event_seq")
                c.execute("""
                    CREATE TABLE IF NOT EXISTS run_event (
                        id          BIGINT DEFAULT nextval('event_seq'),
                        run_id      VARCHAR NOT NULL,
                        node        VARCHAR NOT NULL,
                        event_type  VARCHAR NOT NULL,
                        message     VARCHAR NOT NULL,
                        created_at  TIMESTAMP DEFAULT now(),
                        PRIMARY KEY (id)
                    )
                """)
        except Exception:
            pass # Si une autre process l'initialise en même temps ou la lock

    def log_event(self, run_id: str, node: str, event_type: str, message: str) -> None:
        """Enregistre un événement dans la base de logs séparée."""
        try:
            with self._get_conn() as c:
                c.execute(
                    "INSERT INTO run_event(run_id, node, event_type, message) VALUES (?, ?, ?, ?)",
                    [run_id, node, event_type, message]
                )
        except Exception as e:
            # Fallback console silencieux si locké ou erreur
            print(f"[EventStream Fallback] {run_id} | {node} | {event_type} | {message} (Error: {e})")

# Instance globale (lazily instanciated) pour usage direct si on ne veut pas la passer dans le contexte
_global_event_db = None

def get_event_db() -> EventStreamDB:
    global _global_event_db
    if _global_event_db is None:
        _global_event_db = EventStreamDB()
    return _global_event_db
