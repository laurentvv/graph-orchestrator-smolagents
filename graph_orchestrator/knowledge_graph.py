"""Knowledge Graph persistant (Phase 5) sur DuckDB.

Externalise l'état partagé du graphe : au lieu de se passer des messages volatils,
les agents lisent/écrivent dans un graphe de connaissances durable composé de :
  - Entités (ancres stables : tasks, hosts, services...)
  - Claims (assertions émises par les agents, avec kind/confidence/status)
  - Provenance (QUI a produit chaque claim : agent + modèle + run)
  - Arêtes typées (relations entre claims : REFUTES, SUPPORTS, DERIVED_FROM)

Avantages clés (cf. guide §5) :
  - Traçabilité absolue : origine de chaque information.
  - Survie à l'effacement du contexte (persistance fichier).
  - Déduplication durable (clé de hash normalisée).

Persistance : fichier DuckDB unique (KG_PATH, défaut "data/graph_orchestrator.db"
ancré au paquet via config.DEFAULT_KG_PATH — indépendant du cwd).
Pour les tests : KnowledgeGraph(":memory:") — graphe volatil en RAM.
"""

import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import List, Optional

import duckdb


def dedup_key(content: str) -> str:
    """Hash normalisé d'un contenu textuel pour la déduplication.

    Normalisation : trim + lower. Deux summaries variant juste par la casse/espaces
    produisent la même clé (évite de reboucler sur des quasi-doublons, règle d'or §5).
    """
    norm = (content or "").strip().lower()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


class KnowledgeGraph:
    """Graphe de connaissances persistant sur DuckDB.

    Toutes les écritures sont transactionnelles (commit explicite). Thread-safe via
    DuckDB (un curseur par thread).
    """

    def __init__(self, path: str = ":memory:"):
        # read_write, create_if_not_exists
        self.path = path
        # S'assurer que le dossier parent existe (ex: data/). DuckDB crée le
        # fichier mais PAS le répertoire parent — sans cela, un chemin ancré au
        # paquet (data/graph_orchestrator.db) lèverait si data/ est absent.
        # Cohérent avec event_stream.py / runs_history.py qui font de même.
        if path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = duckdb.connect(path, read_only=False) if path != ":memory:" else duckdb.connect(":memory:")
        self._init_schema()

    def _init_schema(self) -> None:
        """Crée le schéma si absent (idempotent)."""
        c = self.conn
        c.execute("CREATE SEQUENCE IF NOT EXISTS claim_seq")
        c.execute("CREATE SEQUENCE IF NOT EXISTS edge_seq")
        c.execute("""
            CREATE TABLE IF NOT EXISTS entity (
                id         VARCHAR PRIMARY KEY,
                kind       VARCHAR NOT NULL,
                name       VARCHAR,
                created_at TIMESTAMP DEFAULT now()
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS claim (
                id         BIGINT DEFAULT nextval('claim_seq'),
                entity_id  VARCHAR NOT NULL,
                content    VARCHAR NOT NULL,
                kind       VARCHAR NOT NULL,
                confidence FLOAT,
                status     VARCHAR DEFAULT 'open',
                dedup_key  VARCHAR NOT NULL,
                created_at TIMESTAMP DEFAULT now(),
                PRIMARY KEY (id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS provenance (
                claim_id   BIGINT NOT NULL,
                source     VARCHAR NOT NULL,
                model_id   VARCHAR,
                run_id     VARCHAR,
                created_at TIMESTAMP DEFAULT now()
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS edge (
                id            BIGINT DEFAULT nextval('edge_seq'),
                src_claim_id  BIGINT NOT NULL,
                dst_claim_id  BIGINT NOT NULL,
                relation      VARCHAR NOT NULL,
                PRIMARY KEY (id)
            )
        """)
        # Checkpoints de reprise (Priorité 3) : un état sérialisé par run_id stable.
        # Permet de reprendre une exécution CPU-only longue (~15 min/fichier) après
        # un crash, sans perdre le plan de l'Architect ni la progression (sous-tâche,
        # itération). Payload = JSON dict construit par le workflow coding.
        c.execute("""
            CREATE TABLE IF NOT EXISTS checkpoint (
                run_id     VARCHAR NOT NULL,
                payload    VARCHAR NOT NULL,
                status     VARCHAR DEFAULT 'in_progress',
                updated_at TIMESTAMP DEFAULT now(),
                PRIMARY KEY (run_id)
            )
        """)
        # Idempotence des effets de bord (Priorité 8-bis) : records durables des
        # opérations non-idempotentes (append_file, pip install) appliquées par
        # run_id. Permet à un replay de checkpoint de ne pas ré-appliquer un effet
        # de bord déjà committé. Lié au cycle de vie du checkpoint (clear_idempotency
        # appelé aux mêmes sites que clear_checkpoint — FRESH_START + fin de run).
        # Inspiré de qm (idempotency-store.ts). Rétention 14j par défaut (prune).
        c.execute("""
            CREATE TABLE IF NOT EXISTS idempotency_record (
                run_id      VARCHAR NOT NULL,
                op_key      VARCHAR NOT NULL,
                created_at  TIMESTAMP DEFAULT now(),
                PRIMARY KEY (run_id, op_key)
            )
        """)
        # Journal d'événements (workflow introspection) : permet aux agents
        # de lire leur propre historique d'exécution (ex: erreurs internes).
        c.execute("""
            CREATE TABLE IF NOT EXISTS run_event (
                id          BIGINT DEFAULT nextval('claim_seq'),
                run_id      VARCHAR NOT NULL,
                node        VARCHAR NOT NULL,
                event_type  VARCHAR NOT NULL,
                message     VARCHAR NOT NULL,
                created_at  TIMESTAMP DEFAULT now(),
                PRIMARY KEY (id)
            )
        """)
        c.commit()

    # ==========================================
    # Écritures
    # ==========================================

    def add_entity(self, entity_id: str, kind: str, name: Optional[str] = None) -> None:
        """Ajoute une entité (ignore si déjà existante — idempotent)."""
        self.conn.execute(
            "INSERT OR IGNORE INTO entity(id, kind, name) VALUES (?, ?, ?)",
            [entity_id, kind, name],
        )
        self.conn.commit()

    def add_claim(
        self,
        entity_id: str,
        content: str,
        kind: str,
        confidence: Optional[float],
        source: str,
        model_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Optional[int]:
        """Ajoute une claim avec sa provenance. Retourne l'id de la claim, ou None si doublon.

        Déduplication : si une claim ouverte avec le même dedup_key existe déjà pour
        cette entité, on ne réinsère pas (règle d'or §5 anti-boucle).
        """
        key = dedup_key(content)
        # Doublon ? (même entité + même contenu, encore ouvert)
        dup = self.conn.execute(
            "SELECT id FROM claim WHERE entity_id = ? AND dedup_key = ? AND status = 'open'",
            [entity_id, key],
        ).fetchone()
        if dup is not None:
            return None  # déjà vu, pas de réinsertion

        self.conn.execute(
            "INSERT INTO claim(entity_id, content, kind, confidence, dedup_key) VALUES (?, ?, ?, ?, ?)",
            [entity_id, content, kind, confidence, key],
        )
        claim_id = self.conn.execute("SELECT max(id) FROM claim").fetchone()[0]
        self.conn.execute(
            "INSERT INTO provenance(claim_id, source, model_id, run_id) VALUES (?, ?, ?, ?)",
            [claim_id, source, model_id, run_id],
        )
        self.conn.commit()
        return claim_id

    def add_edge(self, src_claim_id: int, dst_claim_id: int, relation: str) -> None:
        """Ajoute une arête typée entre deux claims (ex : un sceptique REFUTES une observation)."""
        self.conn.execute(
            "INSERT INTO edge(src_claim_id, dst_claim_id, relation) VALUES (?, ?, ?)",
            [src_claim_id, dst_claim_id, relation],
        )
        self.conn.commit()

    def mark_status(self, claim_id: int, status: str) -> None:
        """Marque le cycle de vie d'une claim : open → approved / rejected."""
        self.conn.execute(
            "UPDATE claim SET status = ? WHERE id = ?",
            [status, claim_id],
        )
        self.conn.commit()

    # ==========================================
    # Checkpoints (Persistance d'État — Priorité 3)
    # ==========================================

    def save_checkpoint(self, run_id: str, payload: dict) -> None:
        """Persiste (upsert) l'état d'exécution d'un run.

        Un run_id donné n'a qu'un seul checkpoint : on écrase le précédent
        (INSERT OR REPLACE). Le payload est sérialisé en JSON (supporte le
        plan de l'Architect via model_dump, les listes de sous-tâches, etc.).
        Granularité "début d'itération" : on ne persistera que des états
        cohérents (jamais un Judge en cours), garantissant une reprise sûre.
        """
        self.conn.execute(
            "INSERT OR REPLACE INTO checkpoint(run_id, payload, status, updated_at) "
            "VALUES (?, ?, 'in_progress', now())",
            [run_id, json.dumps(payload, ensure_ascii=False)],
        )
        self.conn.commit()

    def load_checkpoint(self, run_id: str) -> Optional[dict]:
        """Retourne le payload d'un run, ou None si absent/explicitement effacé."""
        row = self.conn.execute(
            "SELECT payload FROM checkpoint WHERE run_id = ?",
            [run_id],
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def clear_checkpoint(self, run_id: str) -> None:
        """Efface le checkpoint d'un run (FRESH_START=1)."""
        self.conn.execute("DELETE FROM checkpoint WHERE run_id = ?", [run_id])
        self.conn.commit()

    # ==========================================
    # Idempotence des effets de bord (Priorité 8-bis)
    # ==========================================
    # Records durables des opérations non-idempotentes (append_file, pip install)
    # appliquées par run_id. Backing du store IdempotencyStore (idempotency.py).
    # Cycle de vie lié au checkpoint : clear_idempotency(run_id) est appelé aux
    # MÊMES sites que clear_checkpoint (FRESH_START + fin de run réussi) pour
    # éviter qu'un run terminé ne pollue un nouveau run de même run_id.

    def save_idempotency(self, run_id: str, op_key: str) -> None:
        """Persiste qu'une opération idempotente a été appliquée (INSERT OR IGNORE)."""
        self.conn.execute(
            "INSERT OR IGNORE INTO idempotency_record(run_id, op_key, created_at) "
            "VALUES (?, ?, now())",
            [run_id, op_key],
        )
        self.conn.commit()

    def is_idempotency_committed(self, run_id: str, op_key: str) -> bool:
        """Vrai si l'opération a déjà été appliquée pour ce run (backing durable)."""
        row = self.conn.execute(
            "SELECT 1 FROM idempotency_record WHERE run_id = ? AND op_key = ? LIMIT 1",
            [run_id, op_key],
        ).fetchone()
        return row is not None

    def prune_idempotency(self, retention_s: float) -> None:
        """Supprime les records d'idempotence plus anciens que ``retention_s`` secondes."""
        cutoff = datetime.now() - timedelta(seconds=retention_s)
        self.conn.execute(
            "DELETE FROM idempotency_record WHERE created_at < ?",
            [cutoff],
        )
        self.conn.commit()

    def clear_idempotency(self, run_id: str) -> None:
        """Efface tous les records d'idempotence d'un run (lié à clear_checkpoint)."""
        self.conn.execute("DELETE FROM idempotency_record WHERE run_id = ?", [run_id])
        self.conn.commit()

    def add_run_event(self, run_id: str, node: str, event_type: str, message: str) -> None:
        """Ajoute un événement d'exécution (ex: erreur interne du LLM)."""
        self.conn.execute(
            "INSERT INTO run_event(run_id, node, event_type, message) VALUES (?, ?, ?, ?)",
            [run_id, node, event_type, message],
        )
        self.conn.commit()

    # ==========================================
    # Lectures
    # ==========================================

    def get_claims(self, entity_id: str, status: Optional[str] = None) -> List[dict]:
        """Retourne les claims d'une entité (filtrable par status)."""
        if status:
            rows = self.conn.execute(
                "SELECT id, entity_id, content, kind, confidence, status FROM claim "
                "WHERE entity_id = ? AND status = ? ORDER BY id",
                [entity_id, status],
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, entity_id, content, kind, confidence, status FROM claim "
                "WHERE entity_id = ? ORDER BY id",
                [entity_id],
            ).fetchall()
        return [
            {"id": r[0], "entity_id": r[1], "content": r[2], "kind": r[3],
             "confidence": r[4], "status": r[5]}
            for r in rows
        ]

    def get_claims_by_status(self, status: str) -> List[dict]:
        """Retourne toutes les claims d'un status donné (ex : 'approved' pour la synthèse)."""
        rows = self.conn.execute(
            "SELECT id, entity_id, content, kind, confidence, status FROM claim "
            "WHERE status = ? ORDER BY id",
            [status],
        ).fetchall()
        return [
            {"id": r[0], "entity_id": r[1], "content": r[2], "kind": r[3],
             "confidence": r[4], "status": r[5]}
            for r in rows
        ]

    def get_provenance(self, claim_id: int) -> List[dict]:
        """Retourne la provenance d'une claim (qui l'a produite, avec quel modèle)."""
        rows = self.conn.execute(
            "SELECT source, model_id, run_id, created_at FROM provenance WHERE claim_id = ?",
            [claim_id],
        ).fetchall()
        return [
            {"source": r[0], "model_id": r[1], "run_id": r[2], "created_at": str(r[3])}
            for r in rows
        ]

    def seen(self, entity_id: str, content: str) -> bool:
        """Vrai si une claim ouverte identique existe déjà pour cette entité (dédup)."""
        key = dedup_key(content)
        dup = self.conn.execute(
            "SELECT 1 FROM claim WHERE entity_id = ? AND dedup_key = ? AND status = 'open' LIMIT 1",
            [entity_id, key],
        ).fetchone()
        return dup is not None

    def get_open_claims(self, entity_id: str) -> List[dict]:
        """Retourne le contenu de toutes les claims ouvertes pour une entité."""
        rows = self.conn.execute(
            """
            SELECT p.source, c.content 
            FROM claim c
            JOIN provenance p ON c.id = p.claim_id
            WHERE c.entity_id = ? AND c.status = 'open'
            """,
            [entity_id],
        ).fetchall()
        return [{"source": r[0], "content": r[1]} for r in rows]

    def get_run_events(self, run_id: str, node: Optional[str] = None) -> List[dict]:
        """Retourne les événements d'un run_id."""
        query = "SELECT node, event_type, message, created_at FROM run_event WHERE run_id = ?"
        params = [run_id]
        if node:
            query += " AND node = ?"
            params.append(node)
        query += " ORDER BY created_at DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [{"node": r[0], "event_type": r[1], "message": r[2], "created_at": r[3]} for r in rows]

    # ==========================================
    # Checkpoints (Priorité 3)
    # ==========================================

    def dump(self) -> dict:
        """Export JSON complet du graphe (pour debug/affichage)."""
        entities = self.conn.execute("SELECT id, kind, name FROM entity").fetchall()
        claims = self.conn.execute(
            "SELECT id, entity_id, content, kind, confidence, status FROM claim ORDER BY id"
        ).fetchall()
        provenance = self.conn.execute(
            "SELECT claim_id, source, model_id FROM provenance"
        ).fetchall()
        edges = self.conn.execute(
            "SELECT src_claim_id, dst_claim_id, relation FROM edge"
        ).fetchall()
        return {
            "entities": [{"id": e[0], "kind": e[1], "name": e[2]} for e in entities],
            "claims": [
                {"id": c[0], "entity_id": c[1], "content": c[2], "kind": c[3],
                 "confidence": c[4], "status": c[5]}
                for c in claims
            ],
            "provenance": [
                {"claim_id": p[0], "source": p[1], "model_id": p[2]} for p in provenance
            ],
            "edges": [
                {"src": e[0], "dst": e[1], "relation": e[2]} for e in edges
            ],
        }

    def close(self) -> None:
        self.conn.close()
