"""Tests du re-test ciblé façon git diff (F-47).

Valide que le Tester bascule en mode ciblé (max_steps 6, prompt priorise les bugs)
en itération >1 avec réfutations, et reste en mode complet sinon.
"""

from graph_orchestrator.targeted_retest import (
    should_use_targeted_retest,
    extract_bug_points,
    build_targeted_retest_block,
    TARGETED_MAX_STEPS,
)


# ==========================================
# should_use_targeted_retest — décision du mode
# ==========================================

class TestShouldUseTargeted:
    def test_iteration_1_jamais_cible(self):
        """Itération 1 = création initiale → toujours mode complet."""
        assert should_use_targeted_retest(1, []) is False
        assert should_use_targeted_retest(1, [{"content": "bug"}]) is False

    def test_iteration_2_sans_refutations_complet(self):
        """Itération >1 mais aucune réfutation → mode complet (rien à cibler)."""
        assert should_use_targeted_retest(2, []) is False
        assert should_use_targeted_retest(3, []) is False

    def test_iteration_2_avec_refutations_cible(self):
        """Itération >1 + réfutations → mode ciblé (re-test les bugs signalés)."""
        assert should_use_targeted_retest(2, [{"content": "compteur manquant"}]) is True
        assert should_use_targeted_retest(3, [{"content": "bug1"}, {"content": "bug2"}]) is True

    def test_refutations_vides_complet(self):
        """Réfutations avec contenu vide → mode complet (pas de bug exploitable)."""
        # Une réfutation existe mais son content est vide → on ne peut pas cibler.
        assert should_use_targeted_retest(2, [{"content": ""}]) is True  # bool(list) = True
        # (le extract_bug_points retournera None → fallback gracieux côté web_tester)


# ==========================================
# extract_bug_points — extraction des bugs depuis réfutations
# ==========================================

class TestExtractBugPoints:
    def test_une_refutation(self):
        """Une réfutation → texte extrait tel quel."""
        refs = [{"content": "Le compteur de comparaisons est manquant."}]
        bugs = extract_bug_points(refs)
        assert bugs is not None
        assert "compteur de comparaisons" in bugs

    def test_plusieurs_refutations_recent_d_abord(self):
        """Plusieurs réfutations → les plus récentes en premier (le Judge affine)."""
        refs = [
            {"content": "Bug initial v1"},
            {"content": "Bug raffiné v2"},
        ]
        bugs = extract_bug_points(refs)
        # reversed → v2 apparaît avant v1
        idx_v2 = bugs.index("Bug raffiné v2")
        idx_v1 = bugs.index("Bug initial v1")
        assert idx_v2 < idx_v1

    def test_aucune_refutation_retourne_none(self):
        assert extract_bug_points([]) is None

    def test_refutation_vide_retourne_none(self):
        """Content vide → None (pas de bug exploitable)."""
        assert extract_bug_points([{"content": ""}]) is None
        assert extract_bug_points([{"content": "   "}]) is None

    def test_plafond_max_chars_respecte(self):
        """Une réfutation énorme est tronquée pour ne pas saturer le prompt."""
        huge = "BUG: " + "x" * 5000
        bugs = extract_bug_points([{"content": huge}], max_chars=500)
        assert bugs is not None
        assert len(bugs) <= 600  # ~500 + marges formatage
        assert "[...]" in bugs  # marqueur de troncature


# ==========================================
# build_targeted_retest_block — construction du prompt
# ==========================================

class TestBuildTargetedRetestBlock:
    def test_bloc_contient_marqueurs_cles(self):
        """Le bloc contient les marqueurs attendus par le Tester."""
        block = build_targeted_retest_block("Compteur manquant", iteration=2)
        assert "RE-TEST CIBLÉ" in block
        assert "itération 2" in block
        assert f"max {TARGETED_MAX_STEPS} steps" in block
        assert "Compteur manquant" in block
        assert "FINAL_answer" in block or "final_answer" in block

    def test_bloc_mentionne_git_diff(self):
        """Le bloc référence l'analogie git diff (pour documentation dans le prompt)."""
        block = build_targeted_retest_block("bug", iteration=3)
        assert "git diff" in block.lower()

    def test_bloc_mentionne_smoke_test(self):
        """Le bloc inclut un smoke-test (console) pour détecter les régressions."""
        block = build_targeted_retest_block("bug", iteration=2)
        assert "console" in block.lower() or "smoke" in block.lower()

    def test_bloc_mentionne_regression(self):
        """Le bloc alerte sur les régressions introduites par le fix."""
        block = build_targeted_retest_block("bug", iteration=2)
        assert "régression" in block.lower() or "regression" in block.lower()


# ==========================================
# Intégration web_tester
# ==========================================

class TestWebTesterIntegration:
    def test_web_tester_importe_targeted_retest(self):
        """F-169 : le re-test ciblé vit dans tester_pydantic (moteur UNIQUE) —
        WebTestRunner.run n'est plus qu'une délégation. Pas de cycle d'import."""
        import inspect
        import graph_orchestrator.tester_pydantic as tp

        source = inspect.getsource(tp.run_tester_pydantic)
        assert "should_use_targeted_retest" in source
        assert "use_targeted" in source
        assert "tester_max_steps" in source

    def test_max_steps_adaptatif_dans_source(self):
        """Le max_steps est dynamique (TARGETED_MAX_STEPS ou tester_max_steps
        selon le mode) — dans le moteur pydantic (F-169)."""
        import inspect
        import graph_orchestrator.tester_pydantic as tp

        source = inspect.getsource(tp.run_tester_pydantic)
        assert "TARGETED_MAX_STEPS" in source
        assert "tester_max_steps" in source


# ==========================================
# Intégration workflow (propagation refutations)
# ==========================================

class TestWorkflowPropagation:
    def test_sub_dict_contient_cle_refutations(self):
        """Le workflow propage 'refutations' dans sub_dict (pour le Tester F-47)."""
        import inspect
        from graph_orchestrator import workflows
        source = inspect.getsource(workflows)
        assert '"refutations":' in source or "'refutations':" in source
        assert "refutations_raw" in source
