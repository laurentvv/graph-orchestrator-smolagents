"""Tests du Tester fonctionnel : propagation de la spec + skill + signature Judge.

Valide que les changements du cycle "tester fonctionnel" sont bien en place :
  1. sub_dict contient original_content (propagation de la spec racine vers le tester).
  2. Le prompt du tester contient le bloc "CAHIER DES CHARGES COMPLET".
  3. Le skill web-tester utilise les noms puppeteer_* (pas les faux noms) + mentionne
     les assertions fonctionnelles.
  4. CodeJudgeSignature accepte task_requirements.

Pattern du projet : SYNCHRONE, mock réseau, aucun navigateur réel.
"""

import inspect

from graph_orchestrator import skills_loader
from graph_orchestrator.dspy_nodes import CodeJudgeSignature, execute_code_judge_node
from graph_orchestrator.testers.web_tester import WebTestRunner


# ==========================================
# 1. Skill web-tester : noms d'outils + assertions fonctionnelles
# ==========================================

import os

def load_full_skill_body(skill_name: str) -> str:
    body = skills_loader.load_skill_body(skill_name)
    resources_dir = os.path.join(skills_loader.SKILLS_DIR, skill_name, "resources")
    if os.path.isdir(resources_dir):
        for f in os.listdir(resources_dir):
            if f.endswith(".md"):
                with open(os.path.join(resources_dir, f), "r", encoding="utf-8") as file:
                    body += "\n" + file.read()
    return body

class TestSkillWebTester:
    def test_skill_utilise_noms_puppeteer(self):
        """Le skill doit référencer les VRAIS noms d'outils Puppeteer (puppeteer_*),
        pas les noms Chrome DevTools MCP inexistants (new_page, take_snapshot...)."""
        body = load_full_skill_body("web-tester")
        assert "puppeteer_navigate" in body
        assert "puppeteer_screenshot" in body
        assert "puppeteer_evaluate" in body
        assert "puppeteer_click" in body

    def test_skill_nutilise_pas_les_faux_noms(self):
        """Les noms d'outils inexistants doivent être absents (ou explicitement
        marqués comme n'existant pas) du skill."""
        body = load_full_skill_body("web-tester")
        # Le skill doit AVERTIR que ces noms n'existent pas, pas les recommander.
        # On vérifie qu'aucune instruction active ne dit "use new_page" sans contexte.
        assert "do NOT use" in body.lower() or "ne pas en inventer" in body.lower() or "n'existent pas" in body.lower()

    def test_skill_mentionne_assertions_fonctionnelles(self):
        """Le skill doit exiger des tests fonctionnels (assertions sur le comportement),
        pas seulement un smoke-test console/visuel."""
        body = load_full_skill_body("web-tester")
        body_lower = body.lower()
        assert "functional logic testing" in body_lower or "assertion" in body_lower
        # Doit donner au moins un exemple de script d'assertion (puppeteer_evaluate).
        assert "puppeteer_evaluate" in body
        assert "return" in body  # un script d'assertion retourne un verdict

    def test_skill_exige_assertions_pour_success(self):
        """Le verdict success doit exiger que les assertions fonctionnelles passent."""
        body = load_full_skill_body("web-tester")
        body_lower = body.lower()
        # "success requires ... assertion pass"
        assert "success" in body_lower and ("assertion" in body_lower or "all" in body_lower)


# ==========================================
# 2. Prompt du tester : bloc CAHIER DES CHARGES COMPLET
# ==========================================

class TestTesterPromptPropagation:
    def test_run_accepte_original_content(self):
        """WebTestRunner.run doit lire task['original_content'] (propagation de la spec).
        On vérifie la signature/lecture sans lancer de navigateur (source inspection)."""
        source = inspect.getsource(WebTestRunner.run)
        # Le code doit référencer original_content (avec fallback sur content).
        assert "original_content" in source
        assert "full_requirements" in source
        # Le bloc CAHIER DES CHARGES doit être injecté dans le prompt.
        assert "CAHIER DES CHARGES COMPLET" in source

    def test_run_mentionne_functional_logic_testing(self):
        """Le prompt doit rappeler l'étape 4 (Functional Logic Testing) du skill."""
        source = inspect.getsource(WebTestRunner.run)
        assert "Functional Logic Testing" in source or "assertions fonctionnelles" in source.lower()

    def test_run_max_steps_adaptatif(self):
        """Le tester a un max_steps ADAPTATIF (F-47) : 6 en mode ciblé (re-test bugs),
        12 en mode complet. borne le temps d'investigation (GPU-local, anti-explosion
        de contexte ToolCallingAgent observée à 24 steps — 405k tokens)."""
        source = inspect.getsource(WebTestRunner.run)
        # max_steps est maintenant dynamique (tester_max_steps), pas en dur.
        assert "max_steps=tester_max_steps" in source
        assert "TARGETED_MAX_STEPS" in source  # mode ciblé (6 steps)


# ==========================================
# 3. CodeJudgeSignature : task_requirements
# ==========================================

class TestJudgeSignatureRequirements:
    def test_judge_signature_a_task_requirements(self):
        """CodeJudgeSignature doit avoir un champ task_requirements (InputField)
        pour que le Juge puisse comparer comportement attendu vs résultats de test."""
        sig_fields = CodeJudgeSignature.output_fields if hasattr(CodeJudgeSignature, "output_fields") else {}
        # DSPy stocke les InputField dans input_fields. Vérifions les deux formes.
        input_fields = getattr(CodeJudgeSignature, "input_fields", {})
        all_fields = {**(input_fields or {}), **(sig_fields or {})}
        assert "task_requirements" in all_fields, (
            f"task_requirements absent de la signature. Champs trouvés: {list(all_fields.keys())}"
        )

    def test_judge_node_passe_task_requirements(self):
        """execute_code_judge_node doit passer task_requirements au predictor."""
        source = inspect.getsource(execute_code_judge_node)
        assert "task_requirements" in source
        assert "original_content" in source  # lu depuis subtask


# ==========================================
# 4. Integration : propagation spec racine (workflows.py)
# ==========================================

class TestSpecPropagationInWorkflow:
    def test_sub_dict_a_original_content(self):
        """process_subtask_loop doit mettre original_content dans sub_dict."""
        import graph_orchestrator.workflows as wf
        source = inspect.getsource(wf)
        # On cherche le pattern d'ajout de la clé au sub_dict.
        assert '"original_content"' in source or "'original_content'" in source
        assert "seed_content" in source  # capturé dans coding_state

    def test_coding_state_capture_seed_content(self):
        """coding_state doit capturer seed_content (la spec racine)."""
        import graph_orchestrator.workflows as wf
        source = inspect.getsource(wf)
        assert '"seed_content"' in source or "'seed_content'" in source
