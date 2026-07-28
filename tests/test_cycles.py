"""Tests des cycles loop-until-dry (§5) : terminaison garantie + dédup contre le déjà-vu.

On teste la logique de déduplication et les garanties anti-boucle-infinie SANS LLM.
"""

from graph_orchestrator.workflows import _hash_summary
from graph_orchestrator.models import WorkerOutput


class TestDedupDejaVu:
    """Règle d'or §5 : la dédup se fait contre TOUT ce qui a été vu, y compris les rejets."""

    def test_hash_stable(self):
        w = WorkerOutput(task_id="t1", summary="CPU à 95%", confidence_score=0.9)
        assert _hash_summary(w) == _hash_summary(w)

    def test_hash_normalise_casse_et_espaces(self):
        a = WorkerOutput(task_id="t1", summary="  CPU À 95%  ", confidence_score=0.9)
        b = WorkerOutput(task_id="t2", summary="cpu à 95%", confidence_score=0.9)
        # normalisation lower+strip => même hash => dédup détecte le doublon sémantique
        assert _hash_summary(a) == _hash_summary(b)

    def test_hash_differe_pour_contenu_different(self):
        a = WorkerOutput(task_id="t1", summary="CPU à 95%", confidence_score=0.9)
        b = WorkerOutput(task_id="t2", summary="Disque à 12%", confidence_score=0.9)
        assert _hash_summary(a) != _hash_summary(b)


class TestSimulationBoucle:
    """Simule la logique de boucle du workflow pour garantir la TERMINAISON."""

    def test_boucle_se_termine_sur_dry(self):
        """Si un tour n'apporte rien de nouveau, la boucle doit s'arrêter (critère dry)."""
        seen_summaries = set()
        # Tour 1 : 2 nouveaux => on continue
        tour1 = [
            WorkerOutput(task_id="t1", summary="cause A", confidence_score=0.9),
            WorkerOutput(task_id="t2", summary="cause B", confidence_score=0.9),
        ]
        # Tour 2 : que du déjà-vu => dry
        tour2 = [
            WorkerOutput(task_id="t1", summary="cause A", confidence_score=0.9),  # déjà vu
            WorkerOutput(task_id="t2", summary="cause B", confidence_score=0.9),  # déjà vu
        ]

        iterations = 0
        accumulated = []
        max_iter = 5
        # Simule le corps de boucle (sans LLM)
        for tour in [tour1, tour2]:
            iterations += 1
            new = []
            for w in tour:
                h = _hash_summary(w)
                if h in seen_summaries:
                    continue
                seen_summaries.add(h)
                new.append(w)
            if not new:
                break  # dry
            accumulated.extend(new)

        assert iterations == 2  # s'est arrêté au tour 2 (dry)
        assert len(accumulated) == 2

    def test_boucle_se_termine_sur_hard_cap(self):
        """Même si on trouve toujours du nouveau, le hard cap arrête la boucle."""
        max_iter = 3
        iterations = 0
        accumulated = []
        # Chaque tour apporte du nouveau (jamais dry) => doit buter sur le hard cap
        tours = [
            [WorkerOutput(task_id=f"t{i}", summary=f"cause {i}", confidence_score=0.9)]
            for i in range(10)  # plus de tours que le cap
        ]
        seen = set()
        for tour in tours:
            if iterations >= max_iter:
                break
            iterations += 1
            for w in tour:
                h = _hash_summary(w)
                if h not in seen:
                    seen.add(h)
                    accumulated.append(w)
        assert iterations == max_iter  # buté sur le cap, pas avant

    def test_les_rejets_sont_marques_comme_vus(self):
        """Règle d'or §5 : un summary rejeté doit être marqué vu pour éviter de reboucler dessus."""
        seen = set()
        # Un summary qui serait rejeté par les adversaires au tour 1
        rejeté = WorkerOutput(task_id="t1", summary="dead end halluciné", confidence_score=0.9)
        seen.add(_hash_summary(rejeté))  # marqué vu même si rejeté

        # Tour 2 : le même dead end réapparaît => doit être ignoré
        de_nouveau = WorkerOutput(task_id="t1", summary="dead end halluciné", confidence_score=0.9)
        assert _hash_summary(de_nouveau) in seen  # déjà vu => pas de rebouclage
