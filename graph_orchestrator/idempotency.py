"""Idempotence des effets de bord (Priorité 8-bis du plan usine logicielle).

Port Python fidèle de ``references/qm/src/idempotency/idempotency-store.ts``.

Garantit qu'un effet de bord non-idempotent (``append_file``, ``pip install``)
n'est appliqué QU'UNE FOIS par ``run_id`` — même après un replay de checkpoint
(reprise après crash) ou un retry. Sans cela, un ``append`` ré-appliqué au replay
duplique une section, et un ``pip install`` ré-appliqué gaspille du réseau.

Fonctionnement
--------------
``IdempotencyStore.once(key, fn)`` :
  1. Si ``key`` est déjà *inflight* (appel en cours dans ce process) → skip.
  2. Si ``key`` est déjà *committed* (RAM ``done`` map dans la rétention, OU
     backing DuckDB) → skip.
  3. Sinon → exécute ``fn``. Si ``fn`` retourne SANS lever → marque ``key`` done
     (RAM + DuckDB). Si ``fn`` LÈVE → NE marque PAS done (retryable).

Backing durable (DuckDB) : critique pour le crash-recovery. Un nouveau process
(reprise après crash) perd le ``done`` map en RAM ; le backing DuckDB survit.

Rétention : 14 jours par défaut (cf. qm). Pruning lazy à intervalle régulier.

Contexte module-level : les ``@tool`` smolagents ont une signature figée
(exposée au LLM) → impossible d'ajouter un param ``store``. On utilise un
contexte global set au démarrage de ``run_coding_workflow`` via
``_scoped_idempotency(store)``, lu par ``tools.py`` et ``python_tester.py`` via
``get_current_store()``. Si pas de store (scripts standalone, tests, opt-out) →
no-op (backward compatible). 1-run/process → un global suffit (cf. _FILE_LOCKS).
"""

from __future__ import annotations

import hashlib
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Optional

DEFAULT_RETENTION_S = 14 * 24 * 60 * 60  # 14 jours (aligné sur qm)
DEFAULT_PRUNE_INTERVAL_S = 60 * 60       # 1 heure


class IdempotencyStore:
    """Store d'idempotence avec backing durable (DuckDB via KnowledgeGraph).

    Thread-safe (les ``@tool`` tournent dans des threads via ``asyncio.to_thread``).
    Le backing DuckDB survit à un crash / nouveau process (reprise checkpoint).
    """

    def __init__(
        self,
        kg: Any = None,
        run_id: Optional[str] = None,
        retention_s: float = DEFAULT_RETENTION_S,
        prune_interval_s: float = DEFAULT_PRUNE_INTERVAL_S,
        now: Callable[[], float] = time.time,
    ):
        self.kg = kg
        self.run_id = run_id
        self.retention_s = retention_s
        self.prune_interval_s = prune_interval_s
        self._now = now
        self._done: dict[str, float] = {}
        self._inflight: set[str] = set()
        self._lock = threading.Lock()
        self._last_prune = self._now()

    def committed(self, key: str) -> bool:
        """Vrai si ``key`` est déjà committed (RAM rétention OU backing DuckDB)."""
        cutoff = self._now() - self.retention_s
        with self._lock:
            cached = self._done.get(key)
            if cached is not None and cached >= cutoff:
                return True
        if self.kg is not None and self.run_id:
            try:
                if self.kg.is_idempotency_committed(self.run_id, key):
                    # Hydrate la RAM pour les checks suivants (évite de re-quêter la DB).
                    with self._lock:
                        self._done[key] = self._now()
                    return True
            except Exception:
                # DB indisponible → dégrade vers la RAM seule (jamais de crash bloquant).
                pass
        return False
    def once(self, key: str, fn: Callable[[], Any]) -> bool:
        """Exécute ``fn`` une seule fois pour ``key``.

        Retourne ``True`` si ``fn`` a tourné, ``False`` si déjà committed/inflight.
        Marque ``key`` done SEULEMENT si ``fn`` retourne sans lever. Si ``fn``
        lève, l'exception propage et ``key`` n'est PAS marqué done (retryable) —
        comportement identique au store qm.
        """
        with self._lock:
            if key in self._inflight:
                return False
            cutoff = self._now() - self.retention_s
            cached = self._done.get(key)
            if cached is not None and cached >= cutoff:
                return False
            self._inflight.add(key)
        try:
            # Re-check durable hors lock (la DB peut être lente ; on ne veut pas
            # tenir le lock pendant la requête — d'autres threads progressent).
            if self.kg is not None and self.run_id:
                try:
                    if self.kg.is_idempotency_committed(self.run_id, key):
                        with self._lock:
                            self._done[key] = self._now()
                        return False
                except Exception:
                    pass
            fn()
            at = self._now()
            with self._lock:
                self._done[key] = at
            if self.kg is not None and self.run_id:
                try:
                    self.kg.save_idempotency(self.run_id, key)
                except Exception:
                    pass
            self._prune_if_due(at)
            return True
        finally:
            with self._lock:
                self._inflight.discard(key)

    def reset(self) -> None:
        """Vide le cache RAM (utile entre deux runs dans le même process de test)."""
        with self._lock:
            self._done.clear()
            self._inflight.clear()

    def _prune_if_due(self, t: float) -> None:
        """Pruning lazy : supprime les records expirés à intervalle régulier."""
        if t - self._last_prune < self.prune_interval_s:
            return
        self._last_prune = t
        cutoff = t - self.retention_s
        with self._lock:
            for k, at in list(self._done.items()):
                if at < cutoff:
                    del self._done[k]
        if self.kg is not None:
            try:
                self.kg.prune_idempotency(self.retention_s)
            except Exception:
                pass


def make_op_key(run_id: str, kind: str, *parts: Any) -> str:
    """Construit une clé d'opération stable : ``{run_id}:{kind}:{sha256(parts)}``.

    Le hash garantit que la clé est déterministe (deux appels identiques → même
    clé) et bornée (pas de clé arbitrairement longue si un part est un gros
    ``content``). ``kind`` segmente l'espace de noms (ex: ``"append"``,
    ``"pip"``) pour éviter toute collision entre opérations différentes.
    """
    payload = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{run_id}:{kind}:{digest}"


# ==========================================
# Contexte module-level (single-run-per-process)
# ==========================================
_CURRENT_STORE: Optional[IdempotencyStore] = None
_CURRENT_STORE_LOCK = threading.Lock()


def set_current_store(store: Optional[IdempotencyStore]) -> None:
    """Set le store courant (appelé par _scoped_idempotency / run_coding_workflow)."""
    global _CURRENT_STORE
    with _CURRENT_STORE_LOCK:
        _CURRENT_STORE = store


def get_current_store() -> Optional[IdempotencyStore]:
    """Retourne le store courant, ou None (scripts standalone / opt-out / tests)."""
    with _CURRENT_STORE_LOCK:
        return _CURRENT_STORE


def clear_current_store() -> None:
    """Clear le store courant (idempotent)."""
    set_current_store(None)


@contextmanager
def _scoped_idempotency(store: Optional[IdempotencyStore]):
    """Set le store courant le temps d'un bloc, clear TOUJOURS à la sortie.

    Garantit qu'aucun store ne fuite hors de ``run_coding_workflow`` (critical
    pour les tests E2E qui enchaînent plusieurs runs : sans clear, le 2e run
    hériterait du store du 1er → opérations sklearn à tort). À composer avec
    ``_scoped_chdir`` : ``with _scoped_chdir(d), _scoped_idempotency(s):``.
    """
    set_current_store(store)
    try:
        yield store
    finally:
        clear_current_store()