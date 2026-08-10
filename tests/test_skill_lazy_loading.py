"""Tests de la sélection de skills par l'Architect + budget tokens (F-57, Priorité 10).

Architecture (run F-57 2026-08-04 + révisions) : l'Architect sélectionne les skills
pertinents dans son plan (subtask.skills), et le Coder reçoit leur corps complet
(rogne par budget tokens anti-saturation). Le tool load_skill reste disponible pour
la flexibilité (re-consulter, explorer). build_conditional_skills_block est le repli
contextuel (regex) si l'Architect n'a rien sélectionné.

Couvre :
  - ALWAYS_SKILLS_CODER : socle toujours injecté (failure modes fatals).
  - count_skill_tokens : comptage tiktoken (mémoïsé, repli chars/4).
  - enforce_skill_budget : rogne la sélection sous le budget (petits d'abord).
  - build_conditional_skills_block : repli contextuel (regex).
  - load_skill tool : flexibilité (re-consulter, explorer).
  - ArchitectTask.skills : champ additif non-cassant (défaut []).
  - Catalogue étendu : 15 skills (dont 4 nouveaux : code-review, systematic-debugging,
    frontend-design-anthropic, python-testing-patterns).

Pattern du projet : SYNCHRONE, AUCUNE connexion réseau, AUCUN LLM.
"""

import pytest

from graph_orchestrator.skills_loader import (
    ALWAYS_SKILLS_CODER,
    build_conditional_skills_block,
    build_skills_block,
    count_skill_tokens,
    enforce_skill_budget,
    load_skill_body,
    select_skills_for_coder,
)


# ==========================================
# ALWAYS_SKILLS_CODER : socle de référence
# ==========================================

class TestAlwaysSkillsCoder:
    """Le socle ALWAYS est un contrat critique (failure modes fatals si oubli)."""

    def test_contient_les_3_skills_critiques(self):
        # file-creation + coding + context7-research = socle universel ALWAYS.
        # web-animation est sélectionné DYNAMIQUEMENT par l'Architect (catalogue F-57)
        # quand la tâche est un visualiseur/animation, pas en ALWAYS.
        assert ALWAYS_SKILLS_CODER == {"file-creation", "coding", "context7-research"}

    def test_est_un_set(self):
        assert isinstance(ALWAYS_SKILLS_CODER, set)

    def test_tous_les_skills_always_existent_sur_disque(self):
        for name in ALWAYS_SKILLS_CODER:
            assert load_skill_body(name), f"Skill ALWAYS '{name}' introuvable ou vide"


# ==========================================
# count_skill_tokens : comptage tiktoken (mémoïsé)
# ==========================================

class TestCountSkillTokens:
    """count_skill_tokens retourne un entier positif, mémoïsé, repli défensif."""

    def test_retourne_un_entier_positif(self):
        tok = count_skill_tokens("coding")
        assert isinstance(tok, int)
        assert tok > 0

    def test_skill_existant_est_realiste(self):
        # coding fait ~1375 tokens. Ordre de grandeur vérifié.
        tok = count_skill_tokens("coding")
        assert 500 < tok < 3000, f"count inattendu pour coding: {tok}"

    def test_skill_inexistant_retourne_zero(self):
        assert count_skill_tokens("skill-qui-n-existe-pas") == 0

    def test_est_memoise(self):
        from graph_orchestrator.skills_loader import _SKILL_TOKENS_CACHE
        _SKILL_TOKENS_CACHE.pop("coding", None)
        count_skill_tokens("coding")
        assert "coding" in _SKILL_TOKENS_CACHE

    def test_est_proportionnel_a_la_taille(self):
        # web-tester (~3344 tok) > file-creation (~736 tok).
        assert count_skill_tokens("web-tester") > count_skill_tokens("file-creation")

    def test_nouveaux_skills_ont_un_compte(self):
        # Les 4 nouveaux skills du catalogue étendu doivent avoir un compte valide.
        for name in ["code-review", "systematic-debugging", "python-testing-patterns", "frontend-design-anthropic"]:
            tok = count_skill_tokens(name)
            assert tok > 0, f"Skill '{name}' non compté (introuvable sur disque ?)"


# ==========================================
# enforce_skill_budget : rogne la sélection sous le budget
# ==========================================

class TestEnforceSkillBudget:
    """enforce_skill_budget garantit que la sélection reste sous le budget."""

    def test_sous_budget_garde_tout(self):
        sel = ["file-creation", "coding", "frontend-design"]
        kept = enforce_skill_budget(sel, budget_tokens=8000)
        assert kept == sel

    def test_budget_etroit_rogne_les_plus_gros(self):
        # Stratégie « petits d'abord » : on garde les petits, on rogne les gros.
        # Socle (file-creation+coding = 2111 tok) + 2 conditionnels. Budget 3000 ne
        # permet de garder que le socle + le plus petit conditionnel (devtools-preview 1117).
        sel = ["file-creation", "coding", "frontend-design", "devtools-preview"]
        kept = enforce_skill_budget(sel, budget_tokens=3000)
        # frontend-design (1165) est le plus gros des conditionnels → rogné en 1er.
        assert "frontend-design" not in kept
        assert "file-creation" in kept  # socle toujours gardé
        assert "coding" in kept
        total = sum(count_skill_tokens(s) for s in kept)
        assert total <= 3000

    def test_socle_always_toujours_conserve(self):
        sel = list(ALWAYS_SKILLS_CODER) + ["frontend-design", "devtools-preview"]
        kept = enforce_skill_budget(sel, budget_tokens=1)
        for s in ALWAYS_SKILLS_CODER:
            assert s in kept, f"Skill socle '{s}' rogné (devrait toujours être conservé)"

    def test_preserve_lordre_dorigine(self):
        sel = ["frontend-design", "file-creation", "coding"]
        kept = enforce_skill_budget(sel, budget_tokens=8000)
        assert kept == sel

    def test_selection_vide_retourne_vide(self):
        assert enforce_skill_budget([], budget_tokens=8000) == []

    def test_total_reel_sous_budget(self):
        sel = list(ALWAYS_SKILLS_CODER) + ["frontend-design", "devtools-preview", "python-health-audit", "code-review"]
        for budget in [3000, 5000, 8000, 10000]:
            kept = enforce_skill_budget(sel, budget_tokens=budget)
            total = sum(count_skill_tokens(s) for s in kept)
            socle_tokens = sum(count_skill_tokens(s) for s in ALWAYS_SKILLS_CODER)
            assert total <= budget or total <= socle_tokens + 1, (
                f"Budget {budget} dépassé: {total} tokens retenus"
            )


# ==========================================
# build_conditional_skills_block : repli contextuel (regex)
# ==========================================

class TestBuildConditionalSkillsBlock:
    """build_conditional_skills_block : repli si l'Architect n'a rien sélectionné."""

    def test_tache_web_contient_frontend_design(self):
        block = build_conditional_skills_block("Crée une landing page responsive HTML5 CSS")
        assert "### SKILL: frontend-design" in block

    def test_contient_le_socle_always(self):
        block = build_conditional_skills_block("Tri à bulles algorithmique")
        assert "### SKILL: file-creation" in block
        assert "### SKILL: coding" in block

    def test_tache_python_contient_python_health_audit(self):
        block = build_conditional_skills_block("Crée un script python de tri")
        assert "### SKILL: python-health-audit" in block

    def test_contient_directive_applique_consignes(self):
        block = build_conditional_skills_block("landing page HTML")
        assert "applique leurs consignes" in block


# ==========================================
# load_skill tool : flexibilité (re-consulter, explorer)
# ==========================================

class TestLoadSkillTool:
    """L'outil load_skill reste disponible pour la flexibilité du Coder."""

    def test_retourne_le_corps_complet(self):
        from graph_orchestrator.skill_loader_tool import load_skill
        body = load_skill("frontend-design")
        assert len(body) > 500

    def test_skill_inconnu_retourne_message_erreur(self):
        from graph_orchestrator.skill_loader_tool import load_skill
        result = load_skill("skill-inexistant-xyz")
        assert "introuvable" in result.lower()

    def test_ne_leve_jamais(self):
        from graph_orchestrator.skill_loader_tool import load_skill
        for weird in ["", "../../../etc/passwd", "éàç"]:
            result = load_skill(weird)
            assert isinstance(result, str)


# ==========================================
# Modèle ArchitectTask.skills (F-57 v2)
# ==========================================

class TestArchitectTaskSkillsField:
    """Le champ skills sur ArchitectTask (sélection de l'Architect)."""

    def test_champ_skills_existe_avec_defaut_vide(self):
        from graph_orchestrator.models import ArchitectTask
        t = ArchitectTask(task_id="t1", description="test", target_files=["a.py"])
        assert t.skills == []

    def test_champ_skills_accepte_une_liste(self):
        from graph_orchestrator.models import ArchitectTask
        t = ArchitectTask(
            task_id="t1", description="test", target_files=["index.html"],
            skills=["frontend-design", "devtools-preview"],
        )
        assert t.skills == ["frontend-design", "devtools-preview"]

    def test_champ_skills_est_additif_non_cassant(self):
        # Un checkpoint ancien (sans skills) doit pouvoir se désérialiser.
        from graph_orchestrator.models import ArchitectTask
        old = {"task_id": "t1", "description": "test", "target_files": ["a.py"]}
        t = ArchitectTask(**old)
        assert t.skills == []


# ==========================================
# Catalogue étendu (15 skills, F-57 enrichment)
# ==========================================

class TestCatalogueEtendu:
    """Le catalogue contient désormais 15 skills (vs 11 avant). Les 4 nouveaux
    (code-review, systematic-debugging, frontend-design-anthropic, python-testing-patterns)
    sont des copies réelles (pas symlinks) et ont un frontmatter valide."""

    NOUVEAUX_SKILLS = ["code-review", "systematic-debugging", "python-testing-patterns", "frontend-design-anthropic"]

    def test_nouveaux_skills_existent_sur_disque(self):
        for name in self.NOUVEAUX_SKILLS:
            body = load_skill_body(name)
            assert body, f"Skill nouveau '{name}' introuvable ou vide sur disque"

    def test_nouveaux_skills_sont_de_vrais_dossiers_pas_symlinks(self):
        # Windows-safe : un symlink peut casser. Les nouveaux doivent être des copies.
        import os
        for name in self.NOUVEAUX_SKILLS:
            path = os.path.join("skills", name)
            assert not os.path.islink(path), f"'{name}' est un symlink (devrait être une copie)"

    def test_nouveau_frontend_design_anthropic_a_un_nom_distinct(self):
        # Le skill Anthropic a été renommé frontend-design-anthropic pour éviter la
        # collision avec notre frontend-design custom (qui contient les règles APP/LANDING).
        from graph_orchestrator.skills_loader import parse_skill_meta
        meta = parse_skill_meta("frontend-design-anthropic")
        assert meta is not None
        assert meta[0] == "frontend-design-anthropic"  # pas "frontend-design"

    def test_frontend_design_custom_est_preserve(self):
        # Notre version custom (avec ÉTAPE 0 APP/LANDING) ne doit pas avoir été écrasée.
        body = load_skill_body("frontend-design")
        assert "APP" in body or "LANDING" in body or "APP/TOOL" in body, (
            "Notre frontend-design custom a peut-être été écrasé par la version Anthropic"
        )


# ==========================================
# Non-régression : API existante inchangée
# ==========================================

class TestNonRegression:
    """Les fonctions existantes restent inchangées."""

    def test_select_skills_for_coder_inchange_web(self):
        skills = select_skills_for_coder("Crée une landing page responsive HTML5 CSS")
        assert "devtools-preview" in skills
        assert "frontend-design" in skills

    def test_select_skills_for_coder_inchange_python(self):
        skills = select_skills_for_coder("Crée un script python de tri")
        assert "python-health-audit" in skills

    def test_build_skills_block_toujours_fonctionnel(self):
        block = build_skills_block("Crée une landing page HTML")
        assert "### SKILL: file-creation" in block
        assert "### SKILL: frontend-design" in block

    def test_load_skill_body_inchange(self):
        body = load_skill_body("web-tester")
        assert body != ""
