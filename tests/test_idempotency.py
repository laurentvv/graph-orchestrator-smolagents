"""Tests unitaires de l'Idempotence des effets de bord (Priorité 8-bis, F-43).

Valide le store ``once(key, fn)`` avec backing DuckDB durable. Déterministe, 0 LLM.

Couvre :
- once exécute fn la 1re fois (True), skip la 2e (False).
- committed reflète l'état RAM + DuckDB.
- Inflight : 2e appel skip (fn tourne 1 fois).
- Durable : nouveau store (même kg + run_id, simulant crash/nouveau process) → committed True.
- Pruning rétention : key expirée → re-runnable.
- Thread-safety : once concurrent → fn exactement 1 fois.
- fn lève → pas marqué done (retryable).
- clear_idempotency(run_id) → committed False (re-run même tâche).
- make_op_key stable + différencié.
- _scoped_idempotency set/clear le store courant.
- Intégration append_file / _install_module / opt-out / KnowledgeGraph.
"""
import threading

import pytest

from graph_orchestrator.idempotency import (
    IdempotencyStore,
    _scoped_idempotency,
    get_current_store,
    make_op_key,
)
from graph_orchestrator.knowledge_graph import KnowledgeGraph


# ==========================================
# once — exécution unique
# ==========================================
def test_once_runs_fn_first_time_skips_second():
    """once retourne True la 1re fois (fn exécutée), False la 2e (skippée)."""
    store = IdempotencyStore()
    calls = []
    assert store.once("k1", lambda: calls.append(1)) is True
    assert store.once("k1", lambda: calls.append(1)) is False
    assert len(calls) == 1  # fn exécutée une seule fois


def test_committed_reflects_state():
    """committed False avant, True après once."""
    store = IdempotencyStore()
    assert store.committed("k") is False
    store.once("k", lambda: None)
    assert store.committed("k") is True


def test_once_different_keys_both_run():
    """Deux clés différentes → fn exécutée pour chacune."""
    store = IdempotencyStore()
    assert store.once("a", lambda: None) is True
    assert store.once("b", lambda: None) is True


# ==========================================
# Inflight — appel concurrent skip
# ==========================================
def test_inflight_blocks_concurrent_same_key():
    """Si un appel est inflight, un 2e concurrent sur la même clé skip (False)."""
    store = IdempotencyStore()
    started = threading.Event()
    proceed = threading.Event()
    ran = []

    def slow_fn():
        started.set()
        proceed.wait(timeout=2)
        ran.append(1)

    def caller():
        started.wait(timeout=2)
        return store.once("k", lambda: None)

    t = threading.Thread(target=caller)
    t.start()
    result_main = store.once("k", slow_fn)
    proceed.set()
    t.join(timeout=3)

    assert result_main is True  # main a tourné fn
    assert len(ran) == 1  # fn exécutée une seule fois


# ==========================================
# fn lève → pas marqué done (retryable)
# ==========================================
def test_fn_raises_not_marked_done_retryable():
    """Si fn lève, once propage l'exception et ne marque PAS done (retryable)."""
    store = IdempotencyStore()
    attempts = []

    def failing():
        attempts.append(1)
        raise ValueError("boom")

    with pytest.raises(ValueError):
        store.once("k", failing)
    assert not store.committed("k")  # PAS marqué done

    def ok():
        attempts.append(1)

    assert store.once("k", ok) is True  # retry : fn re-tourne
    assert len(attempts) == 2  # échec + retry
# ==========================================
# Durable — backing DuckDB survit à un "nouveau process"
# ==========================================
def test_durable_backing_survives_new_store(tmp_path):
    """Nouveau store (RAM fraîche, même kg+run_id) → committed True via backing."""
    kg = KnowledgeGraph(str(tmp_path / "test.db"))
    run_id = "coding_abc"
    store1 = IdempotencyStore(kg=kg, run_id=run_id)
    assert store1.once("k1", lambda: None) is True

    # Simule un crash / nouveau process : nouveau store, même backing DuckDB.
    store2 = IdempotencyStore(kg=kg, run_id=run_id)
    assert store2.committed("k1") is True  # lu depuis le backing
    assert store2.once("k1", lambda: None) is False  # skip (déjà committed)
    kg.close()


def test_durable_different_run_id_not_committed(tmp_path):
    """Un run_id différent ne voit pas les records d'un autre run."""
    kg = KnowledgeGraph(str(tmp_path / "test.db"))
    store_a = IdempotencyStore(kg=kg, run_id="run_A")
    store_a.once("k1", lambda: None)
    store_b = IdempotencyStore(kg=kg, run_id="run_B")
    assert store_b.committed("k1") is False  # isolation par run_id
    kg.close()


# ==========================================
# Pruning rétention
# ==========================================
def test_retention_expired_key_rerunnable():
    """Une key expirée (au-delà de la rétention) est re-runnable."""
    fake_now = [1000.0]
    store = IdempotencyStore(retention_s=10, now=lambda: fake_now[0])
    store.once("k", lambda: None)
    assert store.committed("k") is True
    fake_now[0] = 1100.0  # avance au-delà de la rétention
    assert store.committed("k") is False  # expirée en RAM
    assert store.once("k", lambda: None) is True  # re-runnable


# ==========================================
# Thread-safety — fn tourne exactement 1 fois
# ==========================================
def test_concurrent_once_runs_fn_exactly_once():
    """N threads lancent once sur la même clé simultanément → fn 1 seule fois."""
    store = IdempotencyStore()
    counter = {"n": 0}
    lock = threading.Lock()

    def fn():
        with lock:
            counter["n"] += 1

    threads = [threading.Thread(target=lambda: store.once("shared", fn)) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert counter["n"] == 1  # fn exécutée exactement une fois


# ==========================================
# reset
# ==========================================
def test_reset_clears_ram_cache():
    """reset vide le cache RAM → la key redevient runnable (sans backing)."""
    store = IdempotencyStore()  # pas de backing
    store.once("k", lambda: None)
    assert store.committed("k") is True
    store.reset()
    assert store.committed("k") is False


# ==========================================
# make_op_key
# ==========================================
def test_make_op_key_stable():
    """Mêmes inputs → même clé."""
    k1 = make_op_key("run1", "append", "/a/b.txt", "content")
    k2 = make_op_key("run1", "append", "/a/b.txt", "content")
    assert k1 == k2


def test_make_op_key_differentiated_by_kind():
    """Kind différent → clé différente (pas de collision entre opérations)."""
    k_append = make_op_key("run1", "append", "x", "y")
    k_pip = make_op_key("run1", "pip", "x", "y")
    assert k_append != k_pip


def test_make_op_key_differentiated_by_parts():
    """Parts différentes → clé différente."""
    k1 = make_op_key("run1", "append", "a.txt", "c1")
    k2 = make_op_key("run1", "append", "a.txt", "c2")
    assert k1 != k2


def test_make_op_key_bounded_for_large_content():
    """Un gros content ne produit pas une clé arbitrairement longue (hash)."""
    k = make_op_key("run1", "append", "a.txt", "x" * 100000)
    assert len(k) < 200  # {run_id}:{kind}:{sha256 hex}
# ==========================================
# _scoped_idempotency — contexte module-level
# ==========================================
def test_scoped_idempotency_sets_and_clears():
    """Le contexte set le store courant, le clear à la sortie."""
    store = IdempotencyStore()
    assert get_current_store() is None
    with _scoped_idempotency(store):
        assert get_current_store() is store
    assert get_current_store() is None


def test_scoped_idempotency_clears_on_exception():
    """Même en cas d'exception, le store est cleared à la sortie."""
    store = IdempotencyStore()
    with pytest.raises(RuntimeError):
        with _scoped_idempotency(store):
            raise RuntimeError("boom")
    assert get_current_store() is None


def test_scoped_idempotency_none_store():
    """store=None → get_current_store() retourne None dans le bloc (no-op)."""
    with _scoped_idempotency(None):
        assert get_current_store() is None
    assert get_current_store() is None


# ==========================================
# KnowledgeGraph — méthodes idempotency
# ==========================================
class TestKnowledgeGraphIdempotency:

    def test_save_and_is_committed(self, tmp_path):
        """save_idempotency → is_idempotency_committed True ; absent → False."""
        kg = KnowledgeGraph(str(tmp_path / "kg.db"))
        assert kg.is_idempotency_committed("run1", "op1") is False
        kg.save_idempotency("run1", "op1")
        assert kg.is_idempotency_committed("run1", "op1") is True
        kg.close()

    def test_save_is_idempotent_insert_or_ignore(self, tmp_path):
        """Re-sauver la même (run_id, op_key) ne lève pas (INSERT OR IGNORE)."""
        kg = KnowledgeGraph(str(tmp_path / "kg.db"))
        kg.save_idempotency("run1", "op1")
        kg.save_idempotency("run1", "op1")  # pas d'exception
        assert kg.is_idempotency_committed("run1", "op1") is True
        kg.close()

    def test_clear_idempotency(self, tmp_path):
        """clear_idempotency(run_id) efface les records de CE run seulement."""
        kg = KnowledgeGraph(str(tmp_path / "kg.db"))
        kg.save_idempotency("run1", "op1")
        kg.save_idempotency("run2", "op1")
        kg.clear_idempotency("run1")
        assert kg.is_idempotency_committed("run1", "op1") is False
        assert kg.is_idempotency_committed("run2", "op1") is True  # run2 intact
        kg.close()

    def test_prune_removes_old_records(self, tmp_path):
        """prune_idempotency supprime les records plus anciens que retention_s."""
        from datetime import datetime, timedelta
        kg = KnowledgeGraph(str(tmp_path / "kg.db"))
        kg.save_idempotency("run1", "op1")
        # Force le created_at à un timestamp ancien (il y a 1 jour) — déterministe.
        old = datetime.now() - timedelta(days=1)
        kg.conn.execute(
            "UPDATE idempotency_record SET created_at = ? WHERE run_id = ? AND op_key = ?",
            [old, "run1", "op1"],
        )
        kg.conn.commit()
        # Rétention 1h → le record (âgé d'1 jour) est expiré et supprimé.
        kg.prune_idempotency(retention_s=3600)
        assert kg.is_idempotency_committed("run1", "op1") is False
        kg.close()
# ==========================================
# Intégration append_file — idempotence au replay
# ==========================================
def test_append_file_idempotent_on_replay(tmp_path):
    """Un 2e append identique (même path+content) CE RUN est skippé par le store.

    Simule un replay de checkpoint : le Coder ré-applique le même append. Sans le
    store, la garde anti-doublon textuelle ne le verrait pas si un append ultérieur
    a déplacé la fin du fichier. Ici on vérifie le guard du store directement.
    """
    from graph_orchestrator.tools import append_file

    f = tmp_path / "out.txt"
    f.write_text("BASE\n", encoding="utf-8")
    kg = KnowledgeGraph(str(tmp_path / "kg.db"))
    store = IdempotencyStore(kg=kg, run_id="run1")

    with _scoped_idempotency(store):
        r1 = append_file(str(f), "section A\n")
        # Un append ULTÉRIEUR déplace la fin (l'anti-doublon textuel ne verrait plus le dup).
        r3 = append_file(str(f), "section B\n")
        # Re-append de "section A" : l'anti-doublon textuel échoue (fin = "section B"),
        # MAIS le store d'idempotence le skip.
        r2 = append_file(str(f), "section A\n")

    assert "Appended" in r1
    assert "Appended" in r3
    assert "idempotent replay guard" in r2  # skippé par le store
    # Le fichier contient BASE + section A + section B (pas de doublon de A).
    assert f.read_text(encoding="utf-8") == "BASE\nsection A\nsection B\n"
    kg.close()


def test_append_file_no_store_historical_behavior(tmp_path):
    """Sans store (opt-out / scripts standalone) → comportement historique (append normal)."""
    from graph_orchestrator.tools import append_file

    f = tmp_path / "out.txt"
    f.write_text("BASE\n", encoding="utf-8")
    # Pas de _scoped_idempotency → get_current_store() retourne None.
    assert get_current_store() is None
    r = append_file(str(f), "section A\n")
    assert "Appended" in r  # append normal, pas de guard idempotent
    assert f.read_text(encoding="utf-8") == "BASE\nsection A\n"


# ==========================================
# Intégration _install_module — idempotence pip
# ==========================================
def test_install_module_skipped_on_second_call(tmp_path, monkeypatch):
    """Un 2e _install_module pour le même module CE RUN est skippé (backing DuckDB)."""
    import graph_orchestrator.testers.python_tester as pt
    from graph_orchestrator.testers.python_tester import _install_module_or_raise

    kg = KnowledgeGraph(str(tmp_path / "kg.db"))
    store = IdempotencyStore(kg=kg, run_id="run1")
    calls = []

    def fake_install(module, timeout_s=120.0):
        calls.append(module)
        return True

    monkeypatch.setattr(pt, "_install_module", fake_install)

    with _scoped_idempotency(store):
        key = make_op_key("run1", "pip", "requests")
        # 1er appel via le store : install réel (fn tourne, marqué done).
        ran1 = store.once(key, lambda: _install_module_or_raise("requests", timeout_s=5))
        assert ran1 is True
        # 2e appel via le store : skip (déjà committed ce run).
        ran2 = store.once(key, lambda: _install_module_or_raise("requests", timeout_s=5))
        assert ran2 is False  # skippé

    assert len(calls) == 1  # pip install appelé une seule fois
    kg.close()


def test_install_module_failure_not_marked_done_retryable(tmp_path, monkeypatch):
    """Un install qui échoue n'est PAS marqué done → retryable au prochain replay."""
    import graph_orchestrator.testers.python_tester as pt
    from graph_orchestrator.testers.python_tester import _InstallFailed, _install_module_or_raise

    kg = KnowledgeGraph(str(tmp_path / "kg.db"))
    store = IdempotencyStore(kg=kg, run_id="run1")
    calls = []

    def fake_install(module, timeout_s=120.0):
        calls.append(module)
        return False  # échec

    monkeypatch.setattr(pt, "_install_module", fake_install)

    with _scoped_idempotency(store):
        key = make_op_key("run1", "pip", "requests")
        with pytest.raises(_InstallFailed):
            store.once(key, lambda: _install_module_or_raise("requests", timeout_s=5))
        # Pas committed → retryable.
        assert not store.committed(key)
        # Retry : fn re-tourne.
        with pytest.raises(_InstallFailed):
            store.once(key, lambda: _install_module_or_raise("requests", timeout_s=5))

    assert len(calls) == 2  # 2 tentatives (échec + retry)
    kg.close()