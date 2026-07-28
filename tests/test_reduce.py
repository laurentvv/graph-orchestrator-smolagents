"""Tests du nœud Reduce (§3 : flatten + dedupe + filter, code pur)."""

from graph_orchestrator.models import WorkerOutput
from graph_orchestrator.nodes import execute_reduce_node


def _w(task_id: str, summary="x", score=0.9) -> WorkerOutput:
    return WorkerOutput(task_id=task_id, summary=summary, confidence_score=score)


class TestReduceNode:
    def test_garde_les_uniques(self):
        results = [_w("t1"), _w("t2"), _w("t3")]
        out = execute_reduce_node(results)
        assert len(out.kept) == 3
        assert out.dropped_count == 0

    def test_deduplique_sur_task_id(self):
        # deux fois t1 => on garde la première occurrence
        results = [_w("t1", "premier"), _w("t1", "deuxième"), _w("t2")]
        out = execute_reduce_node(results)
        assert len(out.kept) == 2
        assert out.kept[0].summary == "premier"  # première occurrence conservée
        assert out.dropped_count == 1

    def test_liste_vide(self):
        out = execute_reduce_node([])
        assert out.kept == []
        assert out.dropped_count == 0

    def test_filtre_les_none(self):
        # execute_reduce_node doit tolérer des None (isolation des échecs, §5)
        results = [None, _w("t1"), None, _w("t2")]  # type: ignore[list-item]
        out = execute_reduce_node(results)
        assert len(out.kept) == 2
        assert out.dropped_count == 2

    def test_aucun_appel_llm(self):
        """Le reduce est du code pur : doit être instantané et déterministe."""
        import time
        results = [_w(f"t{i}") for i in range(100)]
        t0 = time.perf_counter()
        out = execute_reduce_node(results)
        elapsed = time.perf_counter() - t0
        assert len(out.kept) == 100
        assert elapsed < 0.05  # code pur, pas de réseau
