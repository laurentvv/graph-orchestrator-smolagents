"""Tests F-166 — auto-fixer au Coder (0 LLM, 0 réseau).

Post-mortem run 0857 (2026-08-24) : ~15 rejets F-132 d'affilée sur des
`\n` littéraux dans old/new_string, 80 steps LLM brûlés, run terminé en
« Coder crash » fail-closed. F-166 remplace le rejet pédagogique par un
DÉCODAGE mécanique (doctrine §8.3 « code pur d'abord »), complète la cascade
aider P3 (RelativeIndenter + diff par lignes) et expose fix_known_error au
Coder des deux moteurs.
"""

import shutil

import pytest

from graph_orchestrator.search_replace_utils import (
    CODE_SEPARATOR_NL_RE,
    RelativeIndenter,
    decode_literal_escapes,
    replace_most_similar_chunk,
    _fuzzy_line_window_replace,
    _relative_indent_replace,
    _prep,
)
from graph_orchestrator.tools import (
    _f166_effective_args,
    append_file,
    edit_file,
    multi_replace,
    search_replace,
    write_file,
)


def _needs_node():
    return shutil.which("node") is None


# ============================================================
# decode_literal_escapes — le décodeur d'arguments (critère 530)
# ============================================================

class TestDecodeLiteralEscapes:
    def test_separator_decoded(self):
        """Séquence exacte du run 0857 : `;\\n` avant un mot-clé."""
        dec, n = decode_literal_escapes("const a = 1;\\nconst b = 2;")
        assert dec == "const a = 1;\nconst b = 2;"
        assert n == 1

    def test_legit_newline_in_js_string_untouched(self):
        """`\\n` interne à une chaîne affichée n'est PAS un séparateur : intact."""
        src = 'const msg = "l1\\nl2";\nconsole.log(msg);\n'
        dec, n = decode_literal_escapes(src)
        assert dec == src
        assert n == 0

    def test_leading_literal_tabs_decoded(self):
        """`\\t` d'indentation en tête de ligne (bloc tout-littéral)."""
        dec, n = decode_literal_escapes("foo();\\n\\tbar();\\n\\tbaz();")
        assert "\\t" not in dec
        assert "\tbar();" in dec and "\tbaz();" in dec
        assert n >= 2

    def test_empty_and_clean_texts_untouched(self):
        for s in ("", "a = 1;\nb = 2;", "\\n"):
            dec, n = decode_literal_escapes(s)
            assert dec == s
            assert n == 0

    def test_canonical_regex_shared_with_guard(self):
        """Le décodeur et la garde F-132 partagent LA MÊME définition (domicile
        canonique search_replace_utils) : ce que la garde juge fautif est
        exactement ce que le décodeur sait décoder."""
        faulty = "a = 1;\\nconst b"
        assert CODE_SEPARATOR_NL_RE.search(faulty)
        dec, n = decode_literal_escapes(faulty)
        assert n == 1 and "\\n" not in dec


# ============================================================
# RelativeIndenter (port aider :18-171 — critère 531)
# ============================================================

class TestRelativeIndenter:
    def test_round_trip(self):
        text = "start\n    Foo\n        Bar\n    Baz\nend\n"
        ri = RelativeIndenter([text])
        assert ri.make_absolute(ri.make_relative(text)) == text

    def test_replace_with_global_indent_shift(self):
        """Fichier indenté 8/12, bloc fourni à 0/4 : structure relative
        identique → remplacement réussi avec ré-indentation cible."""
        whole = "top\n        Foo\n            Bar\n        Baz\nbottom\n"
        part = "Foo\n    Bar\nBaz\n"
        res = _relative_indent_replace(whole, part, "Foo\n    Bar\nQUX\n")
        assert res is not None
        assert "        QUX" in res  # ré-indenté au niveau de la cible (8)

    def test_absent_block_returns_none(self):
        """Bloc introuvable même relativisé → None (fail-closed, la cascade
        continue). NB : la collision de marqueur ← est neutralisée par
        construction chez aider (_select_unique_marker choisit un caractère
        absent des textes) — pas de path d'erreur testable ici."""
        assert _relative_indent_replace("a\nb\n", "xyz\n", "c\n") is None

    def test_cascade_uses_relative_indent(self):
        whole = "top\n        Foo\n            Bar\n        Baz\nbottom\n"
        part = "Foo\n    Bar\nBaz\n"
        out = replace_most_similar_chunk(whole, part, "Foo\n    Bar\nQUX\n")
        assert out is not None and "QUX" in out


# ============================================================
# Fuzzy line window (équivalent difflib de dmp_lines_apply — critère 531)
# ============================================================

class TestFuzzyLineWindow:
    def test_similar_window_matched(self):
        whole = "header\nalpha()\nbeta()\ngamma_typo()\ndelta()\nfooter\n"
        part = "alpha()\nbeta()\ngamma_rewritten()\ndelta()\n"
        _, wl = _prep(whole)
        _, pl = _prep(part)
        _, rl = _prep("alpha()\nbeta()\ngamma_fixed()\ndelta()\n")
        res = _fuzzy_line_window_replace(wl, pl, rl)
        assert res is not None
        new_text, ratio = res
        assert ratio >= 0.75
        assert "gamma_fixed()" in new_text

    def test_short_block_rejected(self):
        _, wl = _prep("a\nb\nc\nd\n")
        _, pl = _prep("a\nb\n")  # 2 lignes non vides < seuil 4
        _, rl = _prep("X\nY\n")
        assert _fuzzy_line_window_replace(wl, pl, rl) is None

    def test_low_ratio_rejected(self):
        whole = "one\ntwo\nthree\nfour\nfive\nsix\n"
        part = "xxx\nyyy\nzzz\nwww\n"
        _, wl = _prep(whole)
        _, pl = _prep(part)
        _, rl = _prep("A\nB\nC\nD\n")
        assert _fuzzy_line_window_replace(wl, pl, rl) is None

    def test_ambiguous_windows_rejected(self):
        """Deux fenêtres aussi similaires → ambiguïté → refus (anti
        mauvais-edit silencieux)."""
        whole = "dup()\nx()\ndup()\nx()\ndup()\nx()\ndup()\n"
        part = "dup()\nx()\ndup()\nx()\n"
        _, wl = _prep(whole)
        _, pl = _prep(part)
        _, rl = _prep("A\nB\nC\nD\n")
        assert _fuzzy_line_window_replace(wl, pl, rl) is None

    def test_cascade_sets_note_on_fuzzy(self):
        whole = "header\nalpha()\nbeta()\ngamma_typo()\ndelta()\nfooter\n"
        part = "alpha()\nbeta()\ngamma_rewritten()\ndelta()\n"
        out = replace_most_similar_chunk(whole, part, "alpha()\nbeta()\ngamma_fixed()\ndelta()\n")
        assert out is not None
        assert "fuzzy line window" in replace_most_similar_chunk.last_note

    def test_cascade_note_empty_on_exact(self):
        out = replace_most_similar_chunk("a\nb\nc\n", "b\n", "X\n")
        assert out is not None
        assert replace_most_similar_chunk.last_note == ""


# ============================================================
# _f166_effective_args — résolution des arguments effectifs
# ============================================================

class TestEffectiveArgs:
    def test_raw_priority_when_matching(self):
        old, new, note, rej = _f166_effective_args(
            "a.js", "let a = 1;\n", "let a = 2;\n", "let a = 1;\n"
        )
        assert (old, new, note, rej) == ("let a = 1;\n", "let a = 2;\n", "", None)

    def test_repair_pattern_raw_literal_kept(self):
        """Fichier CORROMPU : old_string littéral matche le fichier tel quel
        (pattern de réparation F-133) — on ne décode PAS old."""
        corrupted = "const a = 1;\\nconst b = 2;\n"
        old_lit = "const a = 1;\\nconst b = 2;"
        old, new, note, rej = _f166_effective_args(
            "a.js", old_lit, "const a = 1;\nconst b = 2;", corrupted
        )
        assert rej is None
        assert old == old_lit  # brut prioritaire : il matche le fichier corrompu

    def test_decoded_when_file_clean(self):
        """Fichier PROPRE + arguments littéraux (cas run 0857) → décodés."""
        original = "const a = 1;\nconst b = 2;\n"
        old, new, note, rej = _f166_effective_args(
            "a.js",
            "const a = 1;\\nconst b = 2;",
            "let a = 1;\\nlet b = 2;",
            original,
        )
        assert rej is None
        assert old == "const a = 1;\nconst b = 2;"
        assert new == "let a = 1;\nlet b = 2;"
        assert "auto-fix F-166" in note

    def test_decoded_noop_rejected(self):
        original = "let a = 1;\n"
        old, new, note, rej = _f166_effective_args(
            "a.js", "let a = 1;\n", "let a = 1;\\n", original
        )
        assert rej is not None and "NO-OP" in rej and "F-166" in rej


# ============================================================
# Intégration outils (critère 530 — le piège du run 0857)
# ============================================================

class _Js:
    def __init__(self, tmp_path, content):
        self.p = tmp_path / "script.js"
        self.p.write_text(content, encoding="utf-8")
        self.path = str(self.p)

    def read(self):
        return self.p.read_text(encoding="utf-8")


class TestSearchReplaceAutofix:
    def test_run0857_trap_decoded_and_applied(self, tmp_path):
        """CAS EXACT du run 0857 : old/new tout-littéraux sur fichier propre
        → édit DÉCODÉ appliqué (avant : rejet ×15, 80 steps brûlés)."""
        js = _Js(tmp_path, "const a = 1;\nconst b = 2;\n")
        res = search_replace(
            path=js.path,
            old_string="const a = 1;\\nconst b = 2;",
            new_string="let a = 1;\\nlet b = 2;",
        )
        assert "Successfully edited" in res
        assert "auto-fix F-166" in res
        assert js.read() == "let a = 1;\nlet b = 2;\n"

    def test_encoded_noop_rejected(self, tmp_path):
        js = _Js(tmp_path, "let a = 1;\nlet b = 2;\n")
        res = search_replace(
            path=js.path,
            old_string="let a = 1;\nlet b = 2;",
            new_string="let a = 1;\\nlet b = 2;",
        )
        assert "NO-OP" in res and "F-166" in res
        assert js.read() == "let a = 1;\nlet b = 2;\n"

    def test_repair_of_corrupted_file_still_works(self, tmp_path):
        """La réparation F-133 (fichier contient les littéraux) survit :
        old brut littéral matche, new contient les vraies lignes."""
        js = _Js(tmp_path, "const a = 1;\\nconst b = 2;\n")
        res = search_replace(
            path=js.path,
            old_string="const a = 1;\\nconst b = 2;",
            new_string="const a = 1;\nconst b = 2;",
        )
        assert "Successfully edited" in res
        assert js.read() == "const a = 1;\nconst b = 2;\n"


class TestWriteAppendAutofix:
    def test_write_file_decoded(self, tmp_path):
        p = tmp_path / "w.js"
        res = write_file(path=str(p), content="function f() { return 1; }\\ndocument.title = 'x';")
        assert "Successfully wrote" in res and "auto-fix F-166" in res
        assert p.read_text(encoding="utf-8") == "function f() { return 1; }\ndocument.title = 'x';"

    def test_write_file_legit_untouched(self, tmp_path):
        p = tmp_path / "ok.js"
        src = 'const msg = "a\\nb";\nconsole.log(msg);\n'
        res = write_file(path=str(p), content=src)
        assert "Successfully wrote" in res and "auto-fix" not in res
        assert p.read_text(encoding="utf-8") == src

    def test_append_file_decoded(self, tmp_path):
        js = _Js(tmp_path, "var x = 1;\n")
        res = append_file(path=js.path, content="var y = 2;\\nvar z = 3;")
        assert "Appended" in res and "auto-fix F-166" in res
        assert js.read() == "var x = 1;\nvar y = 2;\nvar z = 3;"

    def test_append_file_syntax_directive(self, tmp_path):
        """P2 (critère 532) : la SyntaxError du JS APPENDU est détectée à la
        seconde — l'erreur `Identifier ... already been declared` du run 0857
        serait remontée ICI, pas 80 steps plus tard."""
        if _needs_node():
            pytest.skip("node absent")
        js = _Js(tmp_path, "const startBtn = 1;\n")
        res = append_file(path=js.path, content="\nconst startBtn = 2;\n")
        assert "Appended" in res
        assert "SYNTAXE INVALIDE" in res
        assert "already been declared" in res

    def test_edit_file_decoded(self, tmp_path):
        js = _Js(tmp_path, "return 1;\n")
        res = edit_file(path=js.path, old_string="return 1;", new_string="return 2;\\n")
        assert "Successfully updated" in res and "auto-fix F-166" in res
        assert "return 2;\n" in js.read()

    def test_multi_replace_decoded(self, tmp_path):
        js = _Js(tmp_path, "var x = 1;\nvar y = 2;\n")
        res = multi_replace(
            path=js.path,
            replacements=[
                {"old_string": "var x = 1;\\nvar y = 2;", "new_string": "let x = 1;\\nlet y = 2;"},
            ],
        )
        assert "1/1" in res and "auto-fix F-166" in res
        assert js.read() == "let x = 1;\nlet y = 2;\n"


# ============================================================
# fix_known_error exposé au Coder (critère 533)
# ============================================================

class TestFixKnownErrorExposedToCoder:
    def test_pydantic_custom_tools_include_it(self):
        from graph_orchestrator.coder_pydantic import build_coder_custom_tools

        names = {t.__name__ for t in build_coder_custom_tools()}
        assert "fix_known_error" in names

    def test_pydantic_correction_prompt_mentions_it(self):
        from graph_orchestrator.coder_pydantic import _build_devtools_block

        block = _build_devtools_block(
            {"target_files": ["index.html"], "content": "sorting visualizer"},
            vision_available=True,
        )
        assert "fix_known_error" in block

    def test_smolagents_nodes_import_it(self):
        """Le prompt de validation smolagents documente l'outil (source de
        nodes.py — la liste coder_tools vit dans execute_coder_node, contexte
        MCP live non testable sans LLM : la présence dans le prompt + l'import
        garantissent le câblage)."""
        import inspect

        from graph_orchestrator import nodes

        src = inspect.getsource(nodes)
        assert "fix_known_error" in src
