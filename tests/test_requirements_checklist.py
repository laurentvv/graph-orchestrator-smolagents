"""Tests de l'extraction de checklist de fonctionnalités (F-46).

Valide que le parser extrait fiablement les fonctionnalités de la spec PromptRefiner
et que le bloc checklist forcé est bien injecté au Tester.
"""

from graph_orchestrator.requirements_checklist import (
    extract_functionalities,
    build_checklist_block,
)


# ==========================================
# extract_functionalities — cas nominaux
# ==========================================

class TestExtractFunctionalities:
    def test_spec_complete_5_fonctionnalites(self):
        """Spec structurée standard → extrait les 5 puces."""
        spec = """## Objectif
Créer un visualiseur.

## Fonctionnalités attendues
- Bouton Démarrer
- Bouton Réinitialiser
- Curseur de vitesse
- Compteur de comparaisons
- Code couleur

## Contraintes techniques
Vanilla JS.
"""
        funcs = extract_functionalities(spec)
        assert len(funcs) == 5
        assert "Bouton Démarrer" in funcs
        assert "Compteur de comparaisons" in funcs

    def test_spec_avec_styled_quotes(self):
        """Les guillemets « » (courants en français) ne cassent pas le parsing."""
        spec = """## Fonctionnalités attendues
- Bouton « Démarrer le tri »
- Curseur « vitesse »
"""
        funcs = extract_functionalities(spec)
        assert len(funcs) == 2
        assert "Démarrer le tri" in funcs[0]

    def test_puces_asterisk_aussi_supportees(self):
        """Le modèle peut utiliser * au lieu de - comme puce."""
        spec = """## Fonctionnalités attendues
* Fonction A
* Fonction B
"""
        funcs = extract_functionalities(spec)
        assert funcs == ["Fonction A", "Fonction B"]

    def test_arret_a_la_section_suivante(self):
        """Le parsing s'arrête à la prochaine section ## (ne déborde pas)."""
        spec = """## Fonctionnalités attendues
- Feature 1
- Feature 2

## Contraintes techniques
- Pas de framework
- Un seul fichier
"""
        funcs = extract_functionalities(spec)
        assert len(funcs) == 2
        assert "Pas de framework" not in funcs
        assert "Un seul fichier" not in funcs


# ==========================================
# extract_functionalities — robustesse
# ==========================================

class TestExtractRobustesse:
    def test_spec_vide_retourne_liste_vide(self):
        assert extract_functionalities("") == []

    def test_prompt_brut_sans_section_retourne_vide(self):
        """Un prompt brut (sans ## Fonctionnalités) → [] (fallback historique)."""
        prompt = "Crée un visualiseur de tri à bulles avec un bouton et un compteur."
        assert extract_functionalities(prompt) == []

    def test_section_sans_puces_retourne_vide(self):
        """Section présente mais sans puces → [] (pas de fallback hasardeux)."""
        spec = """## Fonctionnalités attendues
Il faut un bouton et un compteur. Le design doit être soigné.
"""
        assert extract_functionalities(spec) == []

    def test_insensible_casse_et_accents(self):
        """Tolérant aux variantes 'Fonctionnalité' / 'Fonctionnalités' / casse."""
        for header in (
            "## Fonctionnalités attendues",
            "## Fonctionnalité attendue",
            "## fonctionnalités attendues",
            "## FONCTIONNALITÉS ATTENDUES",
        ):
            spec = f"{header}\n- Item test\n"
            funcs = extract_functionalities(spec)
            assert funcs == ["Item test"], f"header '{header}' non reconnu"

    def test_doublons_supprimes(self):
        """Si le modèle répète une puce, on la dédoublonne (préserve l'ordre)."""
        spec = """## Fonctionnalités attendues
- Feature A
- Feature B
- Feature A
"""
        funcs = extract_functionalities(spec)
        assert funcs == ["Feature A", "Feature B"]


# ==========================================
# build_checklist_block
# ==========================================

class TestBuildChecklistBlock:
    def test_bloc_contient_compteur_et_format(self):
        """Le bloc forcé contient le nb d'exigences + le format tableau imposé."""
        funcs = ["Bouton Démarrer", "Compteur", "Code couleur"]
        block = build_checklist_block(funcs)
        assert "3 exigences" in block
        assert "CHECKLIST" in block
        assert "Bouton Démarrer" in block
        assert "Compteur" in block
        assert "PASS/FAIL" in block or "PASS" in block
        assert "FONCTIONNALITÉS TESTÉES" in block

    def test_bloc_vide_si_liste_vide(self):
        """Liste vide → bloc vide (fallback historique, pas de checklist forcée)."""
        assert build_checklist_block([]) == ""

    def test_numerotation_1_a_n(self):
        """Les items sont numérotés 1..N pour référence claire."""
        funcs = ["A", "B", "C"]
        block = build_checklist_block(funcs)
        assert "1. A" in block
        assert "2. B" in block
        assert "3. C" in block

    def test_une_seule_fail_implique_failure(self):
        """Le bloc rappelle la règle : 1 FAIL = status failure."""
        funcs = ["Feature"]
        block = build_checklist_block(funcs)
        assert "failure" in block.lower() or "FAIL" in block


# ==========================================
# Intégration : le Tester injecte bien la checklist
# ==========================================

class TestTesterInjection:
    def test_web_tester_importe_le_module(self):
        """Le web_tester.py importe requirements_checklist (pas de cycle d'import)."""
        import inspect

        from graph_orchestrator.testers.web_tester import WebTestRunner
        source = inspect.getsource(WebTestRunner.run)
        assert "extract_functionalities" in source
        assert "build_checklist_block" in source
        assert "checklist_block" in source


# ==========================================
# F-115 : sections anglaises (spec PromptRefiner désormais en anglais)
# ==========================================
class TestExtractEnglish:
    def test_spec_anglaise_complete(self):
        """Section '## Expected Features' parsée comme l'ancienne section française."""
        spec = """## Objective
Build a bubble sort visualizer.

## Expected Features
- Start button
- Reset button
- Speed slider
- Comparison counter

## Technical Constraints
Vanilla JS.
"""
        funcs = extract_functionalities(spec)
        assert len(funcs) == 4
        assert "Start button" in funcs
        assert "Comparison counter" in funcs

    def test_insensible_casse_anglais(self):
        spec = "## expected features\n- Start button\n"
        funcs = extract_functionalities(spec)
        assert funcs == ["Start button"]

    def test_retrocompat_francais_preservee(self):
        """Les specs/checkpoints hérités en français continuent d'être parsés."""
        spec = "## Fonctionnalités attendues\n- Bouton Démarrer\n- Compteur\n"
        funcs = extract_functionalities(spec)
        assert funcs == ["Bouton Démarrer", "Compteur"]
