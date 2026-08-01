"""Tests de la fondation de prompts partagée — Priorité 0-bis (Invariants universels) +
Priorité 0 (Spécialisation) + Priorité 6 (Rubric Judge/Security).

Valide que :
1. Les 10 patterns universels sont présents et numérotés.
2. Les 9 rôles spécialisés existent dans ROLE_BLOCKS.
3. ``build_role_header`` assemble rôle + invariants pour smolagents ; rôle inconnu →
   invariants seuls (robustesse).
4. ``with_invariants`` assemble rôle + invariants + métier spécifique pour DSPy.
5. Les 6 Signatures DSPy ont bien les invariants injectés dans leur ``__doc__``
   (mécanisme d'injection via ``__doc__ = with_invariants(...)`` validé empiriquement).
6. Les Judge/Security signatures contiennent la rubric de sévérité P6 (critical/high/
   medium/low) et les marqueurs doctrinaux (in-diff only, anti-nits, OWASP).
7. ``Finding`` (models.py) — schéma Pydantic de sévérité, rétro-compatible (défaut []).

Déterministe, 0 LLM, 0 réseau.
"""

import pytest

from graph_orchestrator.models import (
    CodeJudgeOutput,
    Finding,
    SecurityOutput,
)
from graph_orchestrator.prompts import (
    ROLE_BLOCKS,
    UNIVERSAL_INVARIANTS,
    build_invariants_header,
    build_role_header,
    with_invariants,
)


# ==========================================
# 1. Invariants universels (P0-bis)
# ==========================================

class TestUniversalInvariants:
    def test_all_10_patterns_present(self):
        """Les 10 patterns universels sont numérotés 1 à 10 dans la constante."""
        for i in range(1, 11):
            assert f"{i}." in UNIVERSAL_INVARIANTS, f"Pattern universel n°{i} manquant"

    def test_key_doctrinal_markers_present(self):
        """Les marqueurs doctrinaux clés (fiche 17) sont présents."""
        markers = [
            "READ-BEFORE-WRITE",
            "VÉRIFIE LES DÉPENDANCES",  # never assume library available
            "VÉRIFIE APRÈS CHAQUE ÉDITION",  # verify-after
            "APPROVAL GATING",
            "ANTI-BOUCLE",
            "CONCISION",
            "PARALLEL TOOL CALLS",
            "FACTUEL ET OBJECTIF",  # professional objectivity
            "SÉCURITÉ DÉFENSIVE",  # defensive security only
        ]
        for marker in markers:
            assert marker in UNIVERSAL_INVARIANTS, f"Marqueur doctrinal manquant : {marker}"


# ==========================================
# 2. Rôles spécialisés (P0)
# ==========================================

class TestRoleBlocks:
    def test_all_9_roles_defined(self):
        """Les 9 rôles du graphe sont présents dans ROLE_BLOCKS."""
        expected = {
            "router", "architect", "prompt_refiner", "coder", "coder_frontend",
            "web_tester", "judge", "security", "escalation",
        }
        assert set(ROLE_BLOCKS.keys()) == expected

    @pytest.mark.parametrize("role,marker", [
        ("router", "ROUTEUR"),
        ("architect", "READ-ONLY STRICT"),
        ("architect", "scalabilité"),
        ("prompt_refiner", "STRUCTURES"),
        ("coder", "Type hints"),
        ("coder", "VÉRIFIE"),
        ("coder_frontend", "accessibilité"),
        ("web_tester", "AAA"),
        ("web_tester", "Pyramide"),
        ("judge", "professional objectivity"),
        ("judge", "IN-DIFF ONLY"),
        ("judge", "ANTI-NITS"),
        ("security", "OWASP"),
        ("security", "CVSS"),
        ("security", "DEFENSIVE"),
        ("escalation", "POST-MORTEM"),
        ("escalation", "racine"),
    ])
    def test_role_contains_doctrinal_marker(self, role, marker):
        """Chaque rôle porte ses marqueurs doctrinaux spécifiques (fiches 15 + 17).

        NB : on cherche des mots-clef compacts (pas des phrases) car le wrapping de ligne
        peut couper une expression au milieu (« cause\\nracine »). On teste la présence du
        token, pas sa position exacte.
        """
        assert marker in ROLE_BLOCKS[role], f"Rôle '{role}' manque le marqueur '{marker}'"


# ==========================================
# 3. build_role_header (smolagents)
# ==========================================

class TestBuildRoleHeader:
    def test_known_role_assembles_role_plus_invariants(self):
        """Un rôle connu produit l'en-tête rôle + les invariants universels."""
        header = build_role_header("coder")
        assert "AGENT DÉVELOPPEUR" in header
        assert "INVARIANTS UNIVERSELS" in header

    def test_unknown_role_returns_invariants_only(self):
        """Un rôle inconnu ne crash pas — renvoie les invariants seuls (robustesse)."""
        header = build_role_header("nonexistent_role")
        assert "INVARIANTS UNIVERSELS" in header
        assert "RÔLE" not in header  # pas de bloc rôle fantôme

    def test_build_invariants_header_standalone(self):
        """build_invariants_header renvoie les invariants seuls."""
        assert build_invariants_header() == UNIVERSAL_INVARIANTS


# ==========================================
# 4. with_invariants (DSPy)
# ==========================================

class TestWithInvariants:
    def test_assembles_role_invariants_and_specific(self):
        """with_invariants assemble rôle + invariants + doc métier, dans cet ordre."""
        doc = with_invariants("judge", "LOGIQUE MÉTIER SPÉCIFIQUE.")
        assert "CODE REVIEWER" in doc          # rôle
        assert "INVARIANTS UNIVERSELS" in doc   # invariants
        assert "LOGIQUE MÉTIER SPÉCIFIQUE." in doc  # métier
        # Ordre : rôle avant invariants avant métier
        assert doc.index("CODE REVIEWER") < doc.index("INVARIANTS UNIVERSELS")
        assert doc.index("INVARIANTS UNIVERSELS") < doc.index("LOGIQUE MÉTIER")

    def test_strips_specific_doc_whitespace(self):
        """Le doc métier est stripé (pas de whitespace parasite en tête/queue)."""
        doc = with_invariants("router", "   \n  texte au milieu  \n   ")
        assert "texte au milieu" in doc


# ==========================================
# 5. Signatures DSPy (injection __doc__)
# ==========================================

class TestDSPySignaturesHaveInvariants:
    """Valide que les 6 Signatures DSPy ont bien les invariants injectés via __doc__.

    Le mécanisme : on assigne ``__doc__ = with_invariants(role, doc_métier)`` dans le
    corps de la classe. DSPy lit ``__doc__`` via sa metaclass pour construire
    l'instruction système. Ce test garantit que l'injection est effective.
    """

    @pytest.fixture(scope="class")
    def signatures(self):
        from graph_orchestrator import dspy_nodes as dn
        return {
            "router": dn.RouterSignature,
            "architect": dn.ArchitectSignature,
            "prompt_refiner": dn.PromptRefinerSignature,
            "security": dn.SecuritySignature,
            "judge": dn.CodeJudgeSignature,
            "escalation": dn.EscalationSignature,
        }

    @pytest.mark.parametrize("role", [
        "router", "architect", "prompt_refiner", "security", "judge", "escalation",
    ])
    def test_signature_has_invariants(self, signatures, role):
        sig = signatures[role]
        doc = sig.__doc__ or ""
        assert "INVARIANTS UNIVERSELS" in doc, f"{role}: invariants manquants dans __doc__"

    def test_judge_signature_has_rubric_markers(self, signatures):
        """Le Judge contient la rubric P6 (sévérité + in-diff + anti-nits)."""
        doc = signatures["judge"].__doc__ or ""
        assert "critical" in doc.lower()
        assert "IN-DIFF ONLY" in doc
        assert "ANTI-NITS" in doc

    def test_security_signature_has_rubric_markers(self, signatures):
        """Le Security contient OWASP + CVSS + defensive-only."""
        doc = signatures["security"].__doc__ or ""
        assert "OWASP" in doc
        assert "CVSS" in doc
        assert "critical" in doc.lower()

    def test_architect_signature_has_strategy_rules(self, signatures):
        """L'Architect conserve sa logique métier (stratégie F-29)."""
        doc = signatures["architect"].__doc__ or ""
        assert "strategy" in doc.lower()
        assert "incremental" in doc
        assert "multifile" in doc


# ==========================================
# 6. Finding + extensions additives (P6 — compatibilité)
# ==========================================

class TestFindingAndAdditiveModels:
    def test_finding_requires_severity_and_description(self):
        """Finding exige severity + description (les autres champs sont optionnels)."""
        f = Finding(severity="critical", category="security", description="SQL injection")
        assert f.severity == "critical"
        assert f.location == ""       # défaut
        assert f.suggestion == ""     # défaut

    def test_finding_round_trip(self):
        f = Finding(
            severity="high", category="correctness", location="api.py:42",
            description="off-by-one", suggestion="fix bound",
        )
        restored = Finding(**f.model_dump())
        assert restored == f

    def test_security_output_default_findings_empty(self):
        """Rétro-compat : SecurityOutput sans findings → [] (pas de cassure)."""
        s = SecurityOutput(task_id="t1", is_secure=True, vulnerabilities=["x"])
        assert s.findings == []

    def test_judge_output_default_findings_empty(self):
        """Rétro-compat : CodeJudgeOutput sans findings → [] (pas de cassure)."""
        j = CodeJudgeOutput(task_id="t1", is_approved=True, final_feedback="ok")
        assert j.findings == []

    def test_security_output_with_findings_round_trip(self):
        """Round-trip Pydantic (compat checkpoint : model_dump → **dict)."""
        f = Finding(severity="high", category="security", description="XSS", suggestion="escape")
        s = SecurityOutput(task_id="t1", is_secure=False, vulnerabilities=["XSS"], findings=[f])
        restored = SecurityOutput(**s.model_dump())
        assert restored.findings[0].severity == "high"
        assert restored.is_secure is False

    def test_judge_output_with_findings_round_trip(self):
        f = Finding(severity="low", category="style", description="bad name")
        j = CodeJudgeOutput(task_id="t1", is_approved=True, final_feedback="ok", findings=[f])
        restored = CodeJudgeOutput(**j.model_dump())
        assert restored.findings[0].category == "style"
        assert restored.is_approved is True
