"""Tests des métriques de benchmark du Judge (F-70 c).

Pure logique, 0 LLM, 0 réseau. Valide :
- canonicalisation des ``Finding`` (Pydantic + dict + string) en IDs stables ;
- precision/recall/F1 (perfect, empty, partial, F1 harmonic mean) ;
- MRR (rank 1, mid, absent) ;
- justesse du verdict binaire (TP/FP/FN).
"""

from graph_orchestrator.judge_metrics import (
    canonicalize_finding,
    compute_mrr,
    compute_precision_recall,
    judge_verdict_accuracy,
)
from graph_orchestrator.models import Finding


# ==========================================
# canonicalize_finding — ID stable insensible à la paraphrase
# ==========================================

class TestCanonicalize:
    def test_finding_pydantic(self):
        f = Finding(severity="high", category="Security", location="index.html:42", description="x")
        assert canonicalize_finding(f) == "index.html:42|security|high"

    def test_dict_plat_equivalent_au_finding(self):
        """Un dict et un Finding avec les mêmes champs → même ID (interopérabilité)."""
        f = Finding(severity="high", category="security", location="index.html:42", description="d1")
        d = {"severity": "high", "category": "security", "location": "index.html:42", "description": "d2"}
        assert canonicalize_finding(f) == canonicalize_finding(d)

    def test_description_exclue_de_lid(self):
        """Descriptions différentes mais même zone/cat/sévérité → même ID (paraphrase OK)."""
        a = Finding(severity="high", category="security", location="L10", description="XSS via innerHTML")
        b = Finding(severity="high", category="security", location="L10", description="Cross-site scripting on innerHTML")
        assert canonicalize_finding(a) == canonicalize_finding(b)

    def test_normalisation_casse_et_whitespace(self):
        f = Finding(severity="high", category="  Data  Base ", location="  Foo.py:7  ", description="x")
        assert canonicalize_finding(f) == "foo.py:7|data base|high"

    def test_location_absente(self):
        """location vide/None → ID réduit à ``|{cat}|{sev}`` (pas de crash)."""
        f = Finding(severity="low", category="style", location="", description="x")
        assert canonicalize_finding(f) == "|style|low"

    def test_string_brute_degenere(self):
        """Anciennes sorties plates de strings pré-F-44 : la string normalisée devient l'ID."""
        assert canonicalize_finding("  XSS @ L42 ") == "xss @ l42"


# ==========================================
# compute_precision_recall — set-match par ID canonique
# ==========================================

class TestPrecisionRecall:
    def test_match_parfait(self):
        a = Finding(severity="high", category="sec", location="L1", description="a")
        b = Finding(severity="medium", category="perf", location="L2", description="b")
        out = compute_precision_recall([a, b], [a, b])
        assert out == {"precision": 1.0, "recall": 1.0, "f1": 1.0}

    def test_deux_ensembles_vides_score_parfait(self):
        """Comportement de la référence : rien prédit, rien attendu → 1.0 (juste)."""
        assert compute_precision_recall([], []) == {"precision": 1.0, "recall": 1.0, "f1": 1.0}

    def test_aucun_match(self):
        pred = [Finding(severity="high", category="sec", location="L1", description="x")]
        actual = [Finding(severity="low", category="style", location="L9", description="y")]
        out = compute_precision_recall(pred, actual)
        assert out == {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    def test_match_partiel_et_f1(self):
        """1 finding prédit juste sur 2 attendus + 1 faux positif → P/R/F1 corrects."""
        good = Finding(severity="high", category="sec", location="L1", description="g")
        miss = Finding(severity="medium", category="perf", location="L2", description="m")
        fp = Finding(severity="low", category="docs", location="L3", description="fp")
        out = compute_precision_recall([good, fp], [good, miss])
        # TP=1, pred=2 → P=0.5 ; actual=2 → R=0.5 ; F1=0.5
        assert out == {"precision": 0.5, "recall": 0.5, "f1": 0.5}

    def test_predicted_vide_actual_non_vide(self):
        actual = [Finding(severity="critical", category="sec", location="L1", description="x")]
        out = compute_precision_recall([], actual)
        assert out["precision"] == 0.0
        assert out["recall"] == 0.0
        assert out["f1"] == 0.0

    def test_arrondi_4_decimales(self):
        """Les scores sont arrondis à 4 dp (pas de flottants longs)."""
        a = Finding(severity="high", category="sec", location="L1", description="x")
        b = Finding(severity="medium", category="perf", location="L2", description="y")
        c = Finding(severity="low", category="docs", location="L3", description="z")
        # pred={a}, actual={a,b,c} → R = 1/3 = 0.3333
        out = compute_precision_recall([a], [a, b, c])
        assert out["recall"] == round(1 / 3, 4)


# ==========================================
# compute_mrr — Mean Reciprocal Rank
# ==========================================

class TestMRR:
    def test_trouve_rang_1(self):
        target = Finding(severity="high", category="sec", location="L1", description="t")
        assert compute_mrr(target, [target]) == 1.0

    def test_trouve_rang_3(self):
        target = Finding(severity="high", category="sec", location="L1", description="t")
        other1 = Finding(severity="low", category="x", location="L2", description="o1")
        other2 = Finding(severity="low", category="y", location="L3", description="o2")
        assert compute_mrr(target, [other1, other2, target]) == round(1 / 3, 4)

    def test_absent_renvoie_zero(self):
        target = Finding(severity="high", category="sec", location="L1", description="t")
        other = Finding(severity="low", category="x", location="L2", description="o")
        assert compute_mrr(target, [other]) == 0.0

    def test_ranking_vide(self):
        target = Finding(severity="high", category="sec", location="L1", description="t")
        assert compute_mrr(target, []) == 0.0


# ==========================================
# judge_verdict_accuracy — décision binaire is_approved
# ==========================================

class TestVerdictAccuracy:
    def test_true_positive_valide_a_tort_non(self):
        out = judge_verdict_accuracy(predicted_approved=True, actual_should_approve=True)
        assert out == {"accuracy": True, "false_positive": False, "false_negative": False}

    def test_true_negative_rejette_a_juste_titre(self):
        out = judge_verdict_accuracy(predicted_approved=False, actual_should_approve=False)
        assert out == {"accuracy": True, "false_positive": False, "false_negative": False}

    def test_false_positive_valide_a_tort(self):
        """Le cas le plus grave : code mauvais accepté."""
        out = judge_verdict_accuracy(predicted_approved=True, actual_should_approve=False)
        assert out["accuracy"] is False
        assert out["false_positive"] is True
        assert out["false_negative"] is False

    def test_false_negative_rejette_a_tort(self):
        """Code bon refusé : gaspillage de cycle LLM, moins grave."""
        out = judge_verdict_accuracy(predicted_approved=False, actual_should_approve=True)
        assert out["accuracy"] is False
        assert out["false_positive"] is False
        assert out["false_negative"] is True
