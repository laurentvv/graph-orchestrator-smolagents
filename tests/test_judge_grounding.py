"""Tests du grounding des findings Judge (F-93) — anti-hallucination de localisation.

Pure logique (0 LLM, 0 réseau) + tests sur fichiers tmp (miroir ``test_judge_diff``).
Valide :
- le port langextract (normalisation, fenêtre glissante, coverage 0.75) ;
- l'extraction de fragments / refs file:line ;
- la résolution de fichier + le grounding d'un finding (ancré/inventé/prose-only/
  ligne hors-bornes/ligne valide) ;
- la politique Option 1 (rétrograde + flag, ``is_approved`` inchangé).
"""

from graph_orchestrator.judge_grounding import (
    _normalize_token,
    _raw_tokens,
    apply_grounding,
    extract_code_fragments,
    fragment_is_grounded,
    ground_finding,
    ground_findings,
    read_source_files,
)
from graph_orchestrator.judge_grounding import _extract_file_line_refs, _resolve_file
from graph_orchestrator.models import CodeJudgeOutput, Finding


# ==========================================
# _normalize_token — port langextract (lowercase + plural stem)
# ==========================================

class TestNormalizeToken:
    def test_lowercase(self):
        assert _normalize_token("BubbleSort") == "bubblesort"
        assert _normalize_token("HTML") == "html"

    def test_plural_stem(self):
        """bars → bar (strip 's' si len>3 et non 'ss')."""
        assert _normalize_token("bars") == "bar"
        assert _normalize_token("elements") == "element"

    def test_pas_de_stem_sur_court_ou_ss(self):
        """Mots courts (≤3) ou finissant en 'ss' non stemmés."""
        assert _normalize_token("css") == "css"
        assert _normalize_token("ids") == "ids"  # len 3 → pas de stem
        assert _normalize_token("process") == "process"  # 'ss' final

    def test_idempotent(self):
        once = _normalize_token("Counters")
        twice = _normalize_token(once)
        assert once == twice


# ==========================================
# fragment_is_grounded — port sliding-window langextract
# ==========================================

class TestFragmentIsGrounded:
    def test_match_exact(self):
        src = "let counter = 0;"
        assert fragment_is_grounded(src, "counter") is True

    def test_match_fuzzy_whitespace(self):
        """Le fragment tokens matchent même si whitespace diffère."""
        assert fragment_is_grounded("function bubbleSort(arr){}", "bubbleSort(arr)") is True

    def test_match_insensible_casse_et_pluriel(self):
        assert fragment_is_grounded("const Bars = [];", "bar") is True
        assert fragment_is_grounded("const bars = [];", "BAR") is True

    def test_no_match_fragment_invente(self):
        assert fragment_is_grounded("function sort(){}", "completelyMadeUpXYZ") is False

    def test_fragment_vide_fail_open(self):
        """Needle vide → True (rien à valider, ne rejette jamais à l'aveugle)."""
        assert fragment_is_grounded("n'importe quoi", "") is True

    def test_source_vide_needle_non_vide(self):
        assert fragment_is_grounded("", "quelquechose") is False

    def test_scattered_rejete_par_bornage_fenetre(self):
        """Tokens très éloignés dans le source → aucun ne tient dans une fenêtre
        ≤ 2×len(needle) → non ancré (la densité implicite sauvegarde le false positif)."""
        source = "a b c d e f g h i j"  # 'a' index 0, 'j' index 9 (span 10 > 2×2)
        assert fragment_is_grounded(source, "a j") is False

    def test_fragments_proches_acceptes(self):
        """Tokens proches (gap modéré) → accepté par la fenêtre élargie."""
        source = "foo bar baz qux"
        assert fragment_is_grounded(source, "bar baz") is True


# ==========================================
# extract_code_fragments + _extract_file_line_refs
# ==========================================

class TestExtractFragments:
    def test_backtick_span(self):
        assert "bar.style.height" in extract_code_fragments("fix `bar.style.height` now")

    def test_identifier_chain(self):
        frags = extract_code_fragments("calls document.getElementById('x')")
        assert any("getElementById" in f for f in frags)

    def test_dedup_et_trop_court(self):
        """Un même fragment n'apparaît qu'une fois ; <3 chars exclu."""
        out = extract_code_fragments("see `ab` `ab` `validone`")
        assert "validone" in out
        assert "ab" not in out  # <3 chars exclu

    def test_prose_only_renvoie_vide(self):
        """Description en langage naturel sans span code → [] (anti faux-négatif)."""
        assert extract_code_fragments("le code est mauvais et peu lisible") == []

    def test_filename_exclu_des_fragments(self):
        """Un nom de fichier (index.html, app.py) n'est PAS un fragment code — il
        est géré par le line-range check + _resolve_file. Sans ce filtre, il serait
        extrait comme chaîne d'identifiers puis causerait des faux ungrounded/grounded."""
        frags = extract_code_fragments("index.html app.py styles.css")
        assert frags == []
        # Un vrai code chain (dernier segment ≠ extension) est conservé.
        assert "bar.style.height" in extract_code_fragments("fix bar.style.height")

    def test_file_line_refs(self):
        refs = _extract_file_line_refs("bug at index.html:42 and app.py:7")
        assert ("index.html", 42) in refs
        assert ("app.py", 7) in refs


# ==========================================
# read_source_files + _resolve_file
# ==========================================

class TestReadAndResolve:
    def test_read_fail_open(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("x = 1", encoding="utf-8")
        out = read_source_files([str(f), str(tmp_path / "missing.py")])
        assert out[str(f)] == "x = 1"
        assert str(tmp_path / "missing.py") not in out

    def test_resolve_par_basename(self, tmp_path):
        sources = {str(tmp_path / "index.html"): "<html/>", str(tmp_path / "script.js"): "x"}
        assert _resolve_file("index.html", sources) == str(tmp_path / "index.html")

    def test_resolve_substring_fallback(self, tmp_path):
        sources = {"src/app/main.py": "x"}
        assert _resolve_file("main.py", sources) == "src/app/main.py"

    def test_resolve_aucun(self):
        assert _resolve_file("nope.txt", {"a.py": "x"}) is None
        assert _resolve_file("", {"a.py": "x"}) is None


# ==========================================
# ground_finding — ancrage d'UN finding (sur fichiers réels)
# ==========================================

class TestGroundFinding:
    SRC = "function bubbleSort(arr){ /* tri */ return arr; }\nlet counter = 0;"

    def _sources(self, tmp_path):
        f = tmp_path / "index.html"
        f.write_text(self.SRC, encoding="utf-8")
        return {str(f): self.SRC}, str(f)

    def test_fragment_ancre_est_grounded(self, tmp_path):
        sources, _ = self._sources(tmp_path)
        f = Finding(severity="high", category="correctness", location="index.html",
                    description="bug in `bubbleSort` logic")
        gf = ground_finding(f, sources)
        assert gf.grounded is True

    def test_fragment_invente_est_ungrounded(self, tmp_path):
        sources, _ = self._sources(tmp_path)
        f = Finding(severity="critical", category="correctness", location="index.html",
                    description="calls `totallyInventedFunctionName` which crashes")
        gf = ground_finding(f, sources)
        assert gf.grounded is False
        assert "fragment non trouvé" in gf.reason

    def test_prose_only_fail_open_grounded(self, tmp_path):
        sources, _ = self._sources(tmp_path)
        f = Finding(severity="medium", category="maintainability", location="index.html",
                    description="le code est peu clair et mal structuré")
        gf = ground_finding(f, sources)
        assert gf.grounded is True
        assert "fail-open" in gf.reason

    def test_ligne_hors_bornes_ungrounded(self, tmp_path):
        sources, _ = self._sources(tmp_path)
        f = Finding(severity="high", category="correctness", location="index.html:9999",
                    description="probleme ligne 9999")
        gf = ground_finding(f, sources)
        assert gf.grounded is False
        assert "9999" in gf.reason

    def test_ligne_valide_grounded(self, tmp_path):
        sources, _ = self._sources(tmp_path)
        f = Finding(severity="low", category="style", location="index.html:2",
                    description="nit de style ligne 2")
        gf = ground_finding(f, sources)
        assert gf.grounded is True

    def test_fichier_cible_inconnu_fallback_tous_les_fichiers(self, tmp_path):
        """location ne nomme pas un fichier résolvable → on teste TOUS les fichiers
        (indulgent : réduit les faux « ungrounded »)."""
        sources, _ = self._sources(tmp_path)
        f = Finding(severity="high", category="x", location="autrechose",
                    description="`bubbleSort` est bizarre")
        gf = ground_finding(f, sources)
        assert gf.grounded is True  # trouvé dans index.html via fallback


# ==========================================
# ground_findings — fail-open global
# ==========================================

class TestGroundFindings:
    def test_source_vide_tout_grounded_fail_open(self):
        f = Finding(severity="critical", category="x", location="a.py:5", description="`foo`")
        rep = ground_findings([f], {})
        assert rep.ungrounded_count == 0
        assert rep.grounded_count == 1
        assert rep.total == 1
        assert "fail-open" in rep.items[0].reason

    def test_mixte_comptes(self, tmp_path):
        f = tmp_path / "app.py"
        f.write_text("def real():\n    pass\n", encoding="utf-8")
        sources = {str(f): open(str(f), encoding="utf-8").read()}
        findings = [
            Finding(severity="high", category="x", location="app.py", description="`real`"),        # grounded
            Finding(severity="critical", category="y", location="app.py", description="`inventedZZZ`"),  # ungrounded
        ]
        rep = ground_findings(findings, sources)
        assert rep.total == 2
        assert rep.grounded_count == 1
        assert rep.ungrounded_count == 1


# ==========================================
# apply_grounding — politique Option 1 (non-destructive)
# ==========================================

class TestApplyGrounding:
    def _verdict(self, findings):
        return CodeJudgeOutput(task_id="t", is_approved=False, final_feedback="rejet", findings=findings)

    def test_ungrounded_critical_est_retrograde_et_flag(self):
        from graph_orchestrator.judge_grounding import FindingGrounding, GroundingReport
        crit = Finding(severity="critical", category="x", location="a.py", description="bug invente")
        grounded = Finding(severity="high", category="y", location="a.py", description="ok")
        rep = GroundingReport(total=2, grounded_count=1, ungrounded_count=1, items=[
            FindingGrounding(grounded, True, "a.py", "ok"),
            FindingGrounding(crit, False, None, "fragment non trouvé"),
        ])
        v = self._verdict([grounded, crit])
        out = apply_grounding(v, rep)
        assert out.is_approved is False  # verdict inchangé
        sev = [f.severity for f in out.findings]
        assert "high" in sev  # critical → high
        assert "high" in sev  # grounded high inchangé
        # Le finding ungrounded porte le marqueur.
        flagged = [f for f in out.findings if "[ungrounded" in f.description]
        assert len(flagged) == 1
        assert "bug invente" in flagged[0].description  # description d'origine conservée

    def test_low_ungrounded_reste_low_mais_flag(self):
        """low ne peut pas descendre → sévérité inchangée, mais flag ajouté."""
        from graph_orchestrator.judge_grounding import FindingGrounding, GroundingReport
        low = Finding(severity="low", category="x", location="a.py", description="nit")
        rep = GroundingReport(total=1, grounded_count=0, ungrounded_count=1,
                              items=[FindingGrounding(low, False, None, "invente")])
        v = self._verdict([low])
        out = apply_grounding(v, rep)
        assert out.findings[0].severity == "low"
        assert "[ungrounded" in out.findings[0].description

    def test_zero_ungrounded_est_no_op(self):
        from graph_orchestrator.judge_grounding import FindingGrounding, GroundingReport
        g = Finding(severity="high", category="x", location="a.py", description="ok")
        rep = GroundingReport(total=1, grounded_count=1, ungrounded_count=0,
                              items=[FindingGrounding(g, True, "a.py", "ok")])
        v = self._verdict([g])
        out = apply_grounding(v, rep)
        # No-op : même verdict (objet retourné inchangé, pas de copie).
        assert out is v

    def test_is_approved_true_inchange(self):
        """Même un verdict approved garde son is_approved (non-destructif)."""
        from graph_orchestrator.judge_grounding import FindingGrounding, GroundingReport
        f = Finding(severity="critical", category="x", location="a.py", description="inv")
        rep = GroundingReport(total=1, grounded_count=0, ungrounded_count=1,
                              items=[FindingGrounding(f, False, None, "x")])
        v = CodeJudgeOutput(task_id="t", is_approved=True, final_feedback="ok", findings=[f])
        out = apply_grounding(v, rep)
        assert out.is_approved is True  # jamais retourné par grounding
