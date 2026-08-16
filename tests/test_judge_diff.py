"""Tests du bloc code ancré IN-DIFF ONLY pour le Judge (F-70).

Valide que ``build_judge_code_block`` :
- en iter 1 (diff vide) renvoie le full-file concaténé (rétrocompat stricte) ;
- en iter >1 (diff présent) injecte le diff en tête + le full-file tronqué ;
- est tolérant (fichier absent/illisible, diff whitespace, target_files vide).
"""



from graph_orchestrator.judge_diff import build_judge_code_block


# ==========================================
# Iter 1 — diff vide = full-file (rétrocompat)
# ==========================================

class TestIteration1FullFile:
    def test_diff_vide_renvoie_full_file(self, tmp_path):
        """Iter 1 (diff vide) → format ``--- {path} ---`` historique, pas de bloc diff."""
        f = tmp_path / "index.html"
        f.write_text("<html><body>hello</body></html>", encoding="utf-8")
        result = build_judge_code_block([str(f)], "")
        assert result == f"--- {f} ---\n<html><body>hello</body></html>\n\n"
        # Aucun marqueur IN-DIFF en iter 1.
        assert "DIFF MODIFIÉ" not in result
        assert "```diff" not in result

    def test_diff_whitespace_seul_traite_comme_vide(self, tmp_path):
        """Un diff composé uniquement d'espaces/sauts = iter 1 (strip)."""
        f = tmp_path / "a.py"
        f.write_text("print('hi')", encoding="utf-8")
        result = build_judge_code_block([str(f)], "   \n\t  \n")
        assert "DIFF MODIFIÉ" not in result
        assert result == f"--- {f} ---\nprint('hi')\n\n"

    def test_target_files_vide_et_diff_vide_renvoie_manquant(self):
        """Rien à lire + pas de diff → ``Code manquant`` (jamais vide, never brick)."""
        assert build_judge_code_block([], "") == "Code manquant"


# ==========================================
# Iter >1 — diff présent = bloc diff + full-file tronqué
# ==========================================

class TestIterationSupDiff:
    def test_diff_present_injecte_bloc_diff_en_tete(self, tmp_path):
        """Iter >1 : le diff apparaît en tête, annoté doctrine IN-DIFF ONLY."""
        f = tmp_path / "script.js"
        f.write_text("function f(){return 1;}", encoding="utf-8")
        diff = "diff --git a/script.js b/script.js\n-return 1;\n+return 2;"
        result = build_judge_code_block([str(f)], diff)
        assert "DIFF MODIFIÉ" in result
        assert "```diff" in result
        assert diff in result
        # Le full-file est aussi présent (contexte vérif exigences).
        assert "CODE COMPLET" in result
        assert "function f" in result

    def test_ordre_diff_puis_full_file(self, tmp_path):
        """Le bloc diff précède toujours le bloc full-file (priorité IN-DIFF)."""
        f = tmp_path / "x.py"
        f.write_text("a = 1", encoding="utf-8")
        result = build_judge_code_block([str(f)], "+a = 2")
        pos_diff = result.index("DIFF MODIFIÉ")
        pos_full = result.index("CODE COMPLET")
        assert pos_diff < pos_full

    def test_fichier_absent_silencieux_fail_open(self, tmp_path):
        """Un target_file inexistant est sauté sans crash ; le diff passe quand même."""
        missing = str(tmp_path / "nope.html")
        result = build_judge_code_block([missing], "+line added")
        assert "DIFF MODIFIÉ" in result
        # Le fallback full-file indique l'indisponibilité plutôt que bloc vide.
        assert "indisponible" in result

    def test_multi_fichiers_concatenes_dans_full_file(self, tmp_path):
        """Plusieurs target_files : full-file concatène avec séparateurs ``---``."""
        f1 = tmp_path / "a.html"
        f2 = tmp_path / "b.css"
        f1.write_text("<a/>", encoding="utf-8")
        f2.write_text("a{}", encoding="utf-8")
        result = build_judge_code_block([str(f1), str(f2)], "+x")
        assert f"--- {f1} ---" in result
        assert f"--- {f2} ---" in result


# ==========================================
# Troncature du full-file en iter >1
# ==========================================

class TestTruncationFullFile:
    def test_full_file_tronque_en_iter_sup(self, tmp_path):
        """En iter >1, un full-file énorme est tronqué (le diff porte l'essentiel)."""
        f = tmp_path / "big.py"
        # ~300 lignes, bien au-delà du plafond head=60/tail=20.
        f.write_text("\n".join(f"line_{i} = {i}" for i in range(300)), encoding="utf-8")
        result = build_judge_code_block([str(f)], "+line_250 = 999")
        assert "lignes tronquées" in result  # marqueur de troncature injecté par truncate_output
        assert "line_0 =" in result   # tête conservée
        assert "line_299 =" in result  # queue conservée
        assert "line_150 =" not in result  # milieu coupé

    def test_full_file_court_non_tronque_en_iter_sup(self, tmp_path):
        """Un full-file court n'est pas tronqué même en iter >1."""
        f = tmp_path / "tiny.py"
        f.write_text("x = 1\ny = 2", encoding="utf-8")
        result = build_judge_code_block([str(f)], "+x = 3")
        assert "lignes tronquées" not in result
        assert "x = 3" in result  # diff
        assert "y = 2" in result  # full-file intact

    def test_full_file_jamais_tronque_en_iter1(self, tmp_path):
        """Iter 1 : le full-file n'est jamais tronqué (rétrocompat stricte)."""
        f = tmp_path / "big.py"
        f.write_text("\n".join(f"l{i}" for i in range(200)), encoding="utf-8")
        result = build_judge_code_block([str(f)], "")
        # Pas de marqueur de troncature en iter 1 (comportement historique préservé).
        assert "lignes tronquées" not in result
        assert "l0" in result and "l199" in result


# ==========================================
# Tests _judge_deliverable_files (fix run 2026-08-11 : vue deliverable complet)
# ==========================================

class TestJudgeDeliverableFiles:
    """Le Judge doit voir TOUS les fichiers source du run, pas seulement le subset
    de la sous-tâche. Sinon, un app 3-fichiers splitée en 3 sous-tâches fait rejeter
    systématiquement (« css/js manquants »)."""

    def test_union_avec_tous_les_fichiers_source_du_cwd(self, tmp_path, monkeypatch):
        """subtask=[index.html] + run dir a 3 fichiers → Judge voit les 3."""
        from graph_orchestrator.dspy_nodes import _judge_deliverable_files
        (tmp_path / "index.html").write_text("x")
        (tmp_path / "styles.css").write_text("x")
        (tmp_path / "script.js").write_text("x")
        (tmp_path / "README.md").write_text("x")  # non-source, ignoré
        monkeypatch.chdir(tmp_path)
        r = _judge_deliverable_files({"target_files": ["index.html"]})
        assert set(r) == {"index.html", "styles.css", "script.js"}

    def test_preserve_target_files_si_run_dir_vide(self, tmp_path, monkeypatch):
        """Run dir sans fichiers source → garde target_files seul (fail-open)."""
        from graph_orchestrator.dspy_nodes import _judge_deliverable_files
        monkeypatch.chdir(tmp_path)
        r = _judge_deliverable_files({"target_files": ["app.py"]})
        assert r == ["app.py"]

    def test_filtre_les_non_source(self, tmp_path, monkeypatch):
        """Les fichiers non-source (.md, .json, .txt) sont exclus de la vue Judge."""
        from graph_orchestrator.dspy_nodes import _judge_deliverable_files
        (tmp_path / "index.html").write_text("x")
        (tmp_path / "package.json").write_text("x")
        (tmp_path / "notes.md").write_text("x")
        monkeypatch.chdir(tmp_path)
        r = _judge_deliverable_files({"target_files": []})
        assert r == ["index.html"]


# ==========================================
# F-102 — bloc « CE QUE GIT DIT » (turn checkpoint)
# ==========================================

class TestTurnDiffBlock:
    TURN_FILES = [
        {"path": "index.html", "status": "modified", "additions": 8, "deletions": 3, "unrenderable": False},
        {"path": "styles.css", "status": "added", "additions": 120, "deletions": 0, "unrenderable": False},
        {"path": "old.js", "status": "removed", "additions": 0, "deletions": 45, "unrenderable": False},
    ]

    def test_resume_present_des_l_iter1(self, tmp_path):
        """Iter 1 (diff texte vide) : le manifeste F-102 préfixe le full-file."""
        f = tmp_path / "index.html"
        f.write_text("<html></html>", encoding="utf-8")
        result = build_judge_code_block([str(f)], "", turn_diff_files=self.TURN_FILES)
        assert "CE QUE GIT DIT" in result
        assert "[modified] index.html (+8/-3)" in result
        assert "[added] styles.css (+120/-0)" in result
        assert "[removed] old.js (+0/-45)" in result
        # Le full-file historique reste présent après le manifeste.
        assert "<html></html>" in result

    def test_resume_devant_le_diff_texte_iter_superieure(self, tmp_path):
        """Iter >1 : manifeste F-102 PUIS diff texte IN-DIFF PUIS code complet."""
        f = tmp_path / "index.html"
        f.write_text("v2", encoding="utf-8")
        result = build_judge_code_block(
            [str(f)], "+v2", turn_diff_files=self.TURN_FILES[:1]
        )
        assert result.index("CE QUE GIT DIT") < result.index("DIFF MODIFIÉ") < result.index("CODE COMPLET")

    def test_binaire_rendu_explicite(self, tmp_path):
        files = [{"path": "img.png", "status": "modified", "additions": None, "deletions": None, "unrenderable": True}]
        result = build_judge_code_block([], "+x", turn_diff_files=files)
        assert "[modified] img.png (binaire) (binaire)" in result

    def test_retrocompat_sans_resume(self, tmp_path):
        """turn_diff_files absent/vide → AUCUN marqueur F-102 (comportement F-70 pur)."""
        f = tmp_path / "a.py"
        f.write_text("a = 1", encoding="utf-8")
        for files in (None, []):
            result = build_judge_code_block([str(f)], "", turn_diff_files=files)
            assert "CE QUE GIT DIT" not in result
            result2 = build_judge_code_block([str(f)], "+a = 2", turn_diff_files=files)
            assert "CE QUE GIT DIT" not in result2
