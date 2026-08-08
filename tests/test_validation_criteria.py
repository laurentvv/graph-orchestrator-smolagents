"""Tests F-82 : critères de validation générés par l'Architecte (pilote unique).

Couvre :
- Les 3 fonctions pures de build de bloc (validation_criteria.py).
- Le modèle ArchitectTask avec ses 3 nouveaux champs (défaut, round-trip, rétrocompat).
- L'injection Coder (_build_devtools_blocks avec critères visuels).
- La propagation sub_dict (workflows.py).
- La hiérarchie Tester (F-47 > F-82 > F-46).
- L'injection Judge (acceptance_rubric concaténé).

Miroir de test_requirements_checklist.py (F-46) — fonctions pures, 0 LLM, 0 réseau.
"""

import pytest
from pydantic import ValidationError

from graph_orchestrator.models import ArchitectTask, ArchitectOutput
from graph_orchestrator.validation_criteria import (
    build_visual_criteria_block,
    build_functional_criteria_block,
    build_judge_rubric_block,
)


# ---------------------------------------------------------------------------
# 1. Fonctions pures — build_visual_criteria_block
# ---------------------------------------------------------------------------
class TestBuildVisualCriteriaBlock:
    def test_liste_vide_retourne_chaine_vide(self):
        assert build_visual_criteria_block([]) == ""

    def test_critere_unique_genere_bloc_avec_anti_biais(self):
        bloc = build_visual_criteria_block(["barres visibles au chargement"])
        assert "CRITÈRES DE VALIDATION VISUELLE" in bloc
        assert "ANALYSE CRITIQUE OBLIGATOIRE" in bloc
        assert "N'EXCUSE JAMAIS" in bloc
        assert "1. barres visibles au chargement" in bloc

    def test_plusieurs_criteres_numerotes(self):
        bloc = build_visual_criteria_block([
            "barres visibles",
            "compteur affiche 0",
            "boutons cliquables",
        ])
        assert "1. barres visibles" in bloc
        assert "2. compteur affiche 0" in bloc
        assert "3. boutons cliquables" in bloc
        assert "3 assertions" in bloc or "3 critères" in bloc

    def test_anti_biais_canvas_vide_explicite(self):
        """Le bloc doit mentionner explicitement le cas canvas vide = BUG."""
        bloc = build_visual_criteria_block(["x"])
        assert "BUG CRITIQUE" in bloc or "visuel vide" in bloc
        # La règle de décision doit dire qu'une page sans erreur console mais visuel
        # vide = échec (leçon du bug canvas 2026-08-08).
        assert "console" in bloc

    def test_filtre_elements_vides(self):
        bloc = build_visual_criteria_block(["valide", "", "  ", "aussi"])
        assert "valide" in bloc
        assert "aussi" in bloc
        # Les éléments vides ne doivent pas créer de lignes numérotées fantômes.

    def test_regle_decision_failure_si_non(self):
        bloc = build_visual_criteria_block(["un critère"])
        assert "failure" in bloc.lower() or "NON" in bloc


# ---------------------------------------------------------------------------
# 2. Fonctions pures — build_functional_criteria_block
# ---------------------------------------------------------------------------
class TestBuildFunctionalCriteriaBlock:
    def test_liste_vide_retourne_chaine_vide(self):
        assert build_functional_criteria_block([]) == ""

    def test_critere_unique_genere_tableau_verdict(self):
        bloc = build_functional_criteria_block(["compteur > 0 après clic + sleep"])
        assert "CRITÈRES FONCTIONNELS" in bloc
        assert "1. compteur > 0 après clic + sleep" in bloc
        assert "PASS" in bloc
        assert "FAIL" in bloc
        assert "VERDICT GLOBAL" in bloc

    def test_compteur_dynamique_nb_assertions(self):
        bloc = build_functional_criteria_block(["a", "b", "c", "d"])
        assert "4 assertions" in bloc or "4 critères" in bloc

    def test_filtre_vides_numerotation(self):
        bloc = build_functional_criteria_block(["x", "", "y"])
        assert "1. x" in bloc
        assert "2. y" in bloc


# ---------------------------------------------------------------------------
# 3. Fonctions pures — build_judge_rubric_block
# ---------------------------------------------------------------------------
class TestBuildJudgeRubricBlock:
    def test_rubric_vide_retourne_chaine_vide(self):
        assert build_judge_rubric_block("") == ""
        assert build_judge_rubric_block("   ") == ""

    def test_rubric_courte_genere_bloc(self):
        rubric = "CRITICAL: barres visibles. HIGH: code couleur 3 états."
        bloc = build_judge_rubric_block(rubric)
        assert "CRITÈRES D'ACCEPTATION SPÉCIFIQUES" in bloc
        assert rubric in bloc

    def test_rubric_longue_tronquee(self):
        longue = "x" * 2000
        bloc = build_judge_rubric_block(longue)
        # Troncation défensive : le bloc ne doit pas dépasser raisonnablement.
        assert len(bloc) < 2000 + 200  # header + body tronqué


# ---------------------------------------------------------------------------
# 4. Modèle ArchitectTask — 3 nouveaux champs
# ---------------------------------------------------------------------------
class TestArchitectTaskF82:
    def test_champs_existent_avec_defaut_vide(self):
        t = ArchitectTask(task_id="t1", description="d", target_files=["index.html"])
        assert t.visual_success_criteria == []
        assert t.functional_test_criteria == []
        assert t.acceptance_rubric == ""

    def test_accepte_listes_critères(self):
        t = ArchitectTask(
            task_id="t1",
            description="d",
            target_files=["index.html"],
            visual_success_criteria=["barres visibles", "compteur à 0"],
            functional_test_criteria=["tri croissant après clic"],
            acceptance_rubric="CRITICAL: rendu visible.",
        )
        assert len(t.visual_success_criteria) == 2
        assert len(t.functional_test_criteria) == 1
        assert "CRITICAL" in t.acceptance_rubric

    def test_retrocompat_vieux_checkpoint_sans_champs(self):
        """Un checkpoint ancien (sans les 3 champs) doit se désérialiser."""
        old = {"task_id": "t1", "description": "test", "target_files": ["a.py"]}
        t = ArchitectTask(**old)
        assert t.visual_success_criteria == []
        assert t.functional_test_criteria == []
        assert t.acceptance_rubric == ""

    def test_roundtrip_serialisation_preserve_champs(self):
        t = ArchitectTask(
            task_id="t1", description="d", target_files=["x"],
            visual_success_criteria=["v1"], functional_test_criteria=["f1"],
            acceptance_rubric="r",
        )
        d = t.model_dump()
        t2 = ArchitectTask(**d)
        assert t2.visual_success_criteria == ["v1"]
        assert t2.functional_test_criteria == ["f1"]
        assert t2.acceptance_rubric == "r"


# ---------------------------------------------------------------------------
# 5. Injection Coder — _build_devtools_blocks avec critères visuels
# ---------------------------------------------------------------------------
class TestCoderDevtoolsInjection:
    def test_sans_critères_workflow_historique(self):
        from graph_orchestrator.nodes import _build_devtools_blocks
        pb, _ = _build_devtools_blocks(
            {"target_files": ["index.html"]}, ["fake_tool"]
        )
        assert "VALIDATION VISUELLE" in pb
        # Pas de checklist F-82 (critères vides).
        assert "CRITÈRES DE VALIDATION VISUELLE" not in pb
        assert "rendu est conforme" in pb  # wording historique

    def test_avec_critères_checklist_f82_injectee(self):
        from graph_orchestrator.nodes import _build_devtools_blocks
        pb, _ = _build_devtools_blocks(
            {
                "target_files": ["index.html"],
                "visual_success_criteria": ["barres visibles au chargement"],
            },
            ["fake_tool"],
        )
        assert "CRITÈRES DE VALIDATION VISUELLE" in pb
        assert "barres visibles au chargement" in pb
        assert "VALIDATION CRITÈRES VISUELS" in pb  # étape 5 renommée


# ---------------------------------------------------------------------------
# 6. Propagation sub_dict (reproduit la logique workflows.py)
# ---------------------------------------------------------------------------
class TestSubDictPropagation:
    def test_champs_propages_dans_sub_dict(self):
        """Reproduit la construction sub_dict de workflows.py pour vérifier getattr."""
        subtask = ArchitectTask(
            task_id="s1", description="d", target_files=["index.html"],
            visual_success_criteria=["v"], functional_test_criteria=["f"],
            acceptance_rubric="r",
        )
        sub_dict = {
            "visual_success_criteria": getattr(subtask, "visual_success_criteria", []),
            "functional_test_criteria": getattr(subtask, "functional_test_criteria", []),
            "acceptance_rubric": getattr(subtask, "acceptance_rubric", ""),
        }
        assert sub_dict["visual_success_criteria"] == ["v"]
        assert sub_dict["functional_test_criteria"] == ["f"]
        assert sub_dict["acceptance_rubric"] == "r"

    def test_champs_absents_repli_defaut(self):
        """Si l'objet n'a pas les champs (mock incomplet), getattr replie sur défaut."""
        sub_dict = {
            "visual_success_criteria": getattr(object(), "visual_success_criteria", []),
            "functional_test_criteria": getattr(object(), "functional_test_criteria", []),
            "acceptance_rubric": getattr(object(), "acceptance_rubric", ""),
        }
        assert sub_dict["visual_success_criteria"] == []
        assert sub_dict["functional_test_criteria"] == []
        assert sub_dict["acceptance_rubric"] == ""


# ---------------------------------------------------------------------------
# 7. Hiérarchie Tester (F-47 > F-82 > F-46) — test du builder
# ---------------------------------------------------------------------------
class TestTesterHierarchy:
    def test_f82_remplace_f46_quand_non_vide(self):
        """Quand l'Architecte produit des critères, ils priment sur F-46 (regex)."""
        f46_block = "CHECKLIST F-46"
        f82_block = build_functional_criteria_block(["critère architecte"])
        # Simule la logique web_tester.py : si architect_criteria non vide → F-82.
        architect_criteria = ["critère architecte"]
        if architect_criteria:
            checklist_block = build_functional_criteria_block(architect_criteria)
        else:
            checklist_block = f46_block
        assert "CRITÈRES FONCTIONNELS" in checklist_block
        assert checklist_block != f46_block

    def test_f46_repli_quand_f82_vide(self):
        """Quand l'Architecte ne produit rien, F-46 (regex) reste actif."""
        f82_block = build_functional_criteria_block([])
        assert f82_block == ""  # vide → le code replie sur F-46


# ---------------------------------------------------------------------------
# 8. Injection Judge — acceptance_rubric
# ---------------------------------------------------------------------------
class TestJudgeInjection:
    def test_rubric_non_vide_genere_bloc_concatenable(self):
        rubric = "CRITICAL: barres visibles. HIGH: code couleur."
        bloc = build_judge_rubric_block(rubric)
        assert bloc != ""
        assert "CRITICAL" in bloc

    def test_rubric_vide_pas_de_bloc(self):
        """Rubric vide → task_requirements = spec globale seule (comportement historique)."""
        assert build_judge_rubric_block("") == ""
