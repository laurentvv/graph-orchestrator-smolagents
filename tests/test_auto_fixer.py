"""Tests F-133 : auto-fixer déterministe pour erreurs mécaniques connues.

Post-mortem 2026-08-20 (Tetris) : le fix const→let a coûté plusieurs steps au
Coder 4B ; le \n littéral a coûté 2 runs entiers. L'outil est pluggé au Tester
(trouve → fix → reload → continue). Fail-closed : aucune classe connue =
aucune modification.
"""

from graph_orchestrator.auto_fixer import apply_known_fixes
from graph_orchestrator.tools import fix_known_error


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


class TestConstReassignment:
    def test_const_let_applique(self, tmp_path):
        p = _write(
            tmp_path,
            "index.html",
            "function loop() {\n    const ghostY = getGhostY();\n"
            "    ghostY = piece.y + drop;\n    drawGhost(ghostY);\n}\n",
        )
        res = apply_known_fixes(p, "Uncaught TypeError: Assignment to constant variable 'ghostY'")
        assert "FIX AUTO APPLIQUÉ" in res
        assert "ghostY" in res
        assert "navigate_page" in res or "reload" in res
        fixed = open(p, encoding="utf-8").read()
        assert "let ghostY =" in fixed
        assert "const ghostY" not in fixed
        # Le reste inchangé.
        assert "ghostY = piece.y + drop;" in fixed
        assert "drawGhost(ghostY);" in fixed

    def test_toutes_occurrences_converties(self, tmp_path):
        p = _write(
            tmp_path,
            "game.js",
            "const ghostY = 1;\nfunction f() {\n    const ghostY = 2;\n"
            "    ghostY = 3;\n}\n",
        )
        apply_known_fixes(p, "Assignment to constant variable 'ghostY'")
        fixed = open(p, encoding="utf-8").read()
        assert fixed.count("let ghostY") == 2
        assert "const ghostY" not in fixed

    def test_autres_const_intactes(self, tmp_path):
        p = _write(
            tmp_path,
            "game.js",
            "const CELL = 32;\nconst ghostY = 0;\nghostY = 5;\n",
        )
        apply_known_fixes(p, "Assignment to constant variable 'ghostY'")
        fixed = open(p, encoding="utf-8").read()
        assert "const CELL = 32;" in fixed  # non ciblée : intacte
        assert "let ghostY" in fixed


class TestLiteralNewlineRepair:
    def test_syntaxerror_repare_le_separator_litteral(self, tmp_path):
        p = _write(
            tmp_path,
            "index.html",
            "<script>\nconst a = PIECES[t.type];\\n                const b = 1;\n</script>\n",
        )
        res = apply_known_fixes(p, "Uncaught SyntaxError: Invalid or unexpected token")
        assert "FIX AUTO APPLIQUÉ" in res
        fixed = open(p, encoding="utf-8").read()
        assert ";\\n" not in fixed
        assert ";\n" in fixed

    def test_sans_syntaxerror_pas_de_repair(self, tmp_path):
        """La classe \\n ne s'active QUE sur SyntaxError (anti faux positifs)."""
        p = _write(
            tmp_path,
            "index.js",
            "const a = 1;\\nconst b = 2;\n",
        )
        res = apply_known_fixes(p, "Uncaught TypeError: something else")
        assert "PAS DE FIX AUTO" in res
        assert open(p, encoding="utf-8").read().count("\\n") == 1


class TestFailClosed:
    def test_erreur_inconnue_aucune_modification(self, tmp_path):
        p = _write(tmp_path, "game.js", "const a = 1;\nfoo();\n")
        before = open(p, encoding="utf-8").read()
        res = apply_known_fixes(p, "Uncaught ReferenceError: pieceData is not defined")
        assert "PAS DE FIX AUTO" in res
        assert open(p, encoding="utf-8").read() == before

    def test_fichier_non_code_refuse(self, tmp_path):
        p = _write(tmp_path, "data.json", '{"a": 1}\n')
        res = apply_known_fixes(p, "Assignment to constant variable 'a'")
        assert "PAS DE FIX AUTO" in res

    def test_fichier_inexistant_fail_open(self, tmp_path):
        res = apply_known_fixes(str(tmp_path / "absent.js"), "Assignment to constant variable 'x'")
        assert "PAS DE FIX AUTO" in res

    def test_pattern_reconnu_mais_deja_repare(self, tmp_path):
        p = _write(tmp_path, "game.js", "let ghostY = 1;\nghostY = 2;\n")
        res = apply_known_fixes(p, "Assignment to constant variable 'ghostY'")
        assert "AUCUNE occurrence" in res or "PAS DE FIX AUTO" in res


class TestToolWrapper:
    def test_outil_delegue_au_module(self, tmp_path):
        p = _write(
            tmp_path,
            "index.html",
            "const score = 0;\nscore = 100;\n",
        )
        res = fix_known_error(path=p, error_message="Assignment to constant variable 'score'")
        assert "FIX AUTO APPLIQUÉ" in res
        assert "let score" in open(p, encoding="utf-8").read()


class TestFenceAwareRepair:
    """P4 (port deer-flow) : le repair \n ne touche PAS le contenu des fences."""

    def test_n_dans_fence_preserve(self, tmp_path):
        p = tmp_path / "index.html"
        p.write_text(
            "const a = 1;\\nconst b = 2;\n<pre>```\nconst demo = 1;\\nconst x = 2;\n```</pre>\n",
            encoding="utf-8",
        )
        res = apply_known_fixes(str(p), "Uncaught SyntaxError: Invalid or unexpected token")
        assert "FIX AUTO APPLIQUÉ" in res
        fixed = p.read_text(encoding="utf-8")
        # Hors fence : réparé (vrai saut de ligne).
        assert fixed.startswith("const a = 1;\nconst b = 2;\n")
        # Dans la fence : la séquence backslash-n littérale est intacte.
        assert "const demo = 1;\\nconst x = 2;\n" in fixed

    def test_tout_dans_fence_aucun_changement(self, tmp_path):
        p = tmp_path / "notes.html"
        p.write_text("```\nconst a = 1;\\nconst b = 2;\n```\n", encoding="utf-8")
        res = apply_known_fixes(str(p), "Uncaught SyntaxError: Invalid or unexpected token")
        assert "PAS DE FIX AUTO" in res or "AUCUNE occurrence" in res
        assert "\\n" in p.read_text(encoding="utf-8")
