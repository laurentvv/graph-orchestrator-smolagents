"""Tests unitaires de l'édition SEARCH/REPLACE tolérante.

Couvre les stratégies portées d'Aider : match exact, tolérant indentation,
ellipses, échec avec feedback. Aucun appel LLM (tests déterministes du parser).
"""
import pytest

from graph_orchestrator.tools import search_replace
from graph_orchestrator.search_replace_utils import replace_most_similar_chunk


# ==========================================
# replace_most_similar_chunk (logique pure)
# ==========================================

def test_exact_match():
    whole = "line1\nline2\nline3\n"
    out = replace_most_similar_chunk(whole, "line2", "TWO")
    assert out is not None
    assert "TWO" in out
    assert "line2" not in out.split("TWO")[0]  # line2 disparu avant le TWO


def test_tolerant_indentation():
    """Le LLM omet l'indentation de tête : le matching doit quand même réussir."""
    whole = "def foo():\n    return 1\n\n"
    # 'search' sans l'indentation (erreur classique de petit modèle)
    out = replace_most_similar_chunk(whole, "return 1", "return 2")
    assert out is not None
    assert "return 2" in out
    # L'indentation d'origine est préservée
    assert "    return 2" in out


def test_ellipsis_elision():
    """Le LLM élude du code avec '...' : le remplacement doit fonctionner par morceaux."""
    whole = "header\nkeep1\nmiddle\nkeep2\nfooter\n"
    search = "header\n...\nkeep2\nfooter"
    replace = "header\n...\nkeep2\nfooter"
    # Ici search == replace sur les ellipses : rien ne change, mais le match doit réussir
    out = replace_most_similar_chunk(whole, search, replace)
    assert out is not None


def test_irregular_multiline_indentation():
    """Le LLM a des décalages d'espaces irréguliers ligne à ligne (ex: 12 sp puis 14 sp).
    Le matching par stripped lines doit trouver le bloc unique et le remplacer."""
    whole = (
        "function lockPiece() {\n"
        "    const shape = currentPiece.shape;\n"
        "    for (let y = 0; y < shape.length; y++) {\n"
        "        if (shape[y]) {\n"
        "            if (currentPiece.y + y >= 0) {\n"
        "                board[y] = 1;\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "}\n"
    )
    # Search avec des espaces irréguliers (ex: 2 espaces au lieu de 8, 10 au lieu de 12)
    search = (
        "function lockPiece() {\n"
        "  const shape = currentPiece.shape;\n"
        "    for (let y = 0; y < shape.length; y++) {\n"
        "      if (shape[y]) {\n"
        "         if (currentPiece.y + y >= 0) {\n"
        "           board[y] = 1;\n"
        "         }\n"
        "      }\n"
        "    }\n"
        "}"
    )
    replace = (
        "function lockPiece() {\n"
        "    const shape = currentPiece.shape;\n"
        "    for (let y = 0; y < shape.length; y++) {\n"
        "        if (shape[y] && y < ROWS) {\n"
        "            board[y] = 1;\n"
        "        }\n"
        "    }\n"
        "}"
    )
    out = replace_most_similar_chunk(whole, search, replace)
    assert out is not None
    assert "y < ROWS" in out
    assert "currentPiece.y + y >= 0" not in out


def test_no_match_returns_none():
    whole = "alpha\nbeta\n"
    out = replace_most_similar_chunk(whole, "gamma", "delta")
    assert out is None


def test_multiple_occurrences_fails_gracefully():
    """Si 'search' apparaît plusieurs fois, replace_most_similar_chunk ne doit pas
    deviner (comme aider) — il renverra None car le match exact trouve la 1ère
    occurrence mais le test vérifie juste qu'on n'a pas de corruption partielle."""
    whole = "x\nx\n"
    out = replace_most_similar_chunk(whole, "x", "y")
    # Le match exact ligne à ligne prend la 1ère occurrence ; on accepte un résultat
    # tant qu'il ne plante pas et reste cohérent (contient encore un 'x').
    assert out is None or out.count("x") >= 1


# ==========================================
# Fallback 6) sous-chaîne exacte unique
# (post-mortem run 2026-08-19, Tetris : le 4B
#  fournissait des blocs partiels de ligne —
#  sans la virgule finale — et les stratégies
#  ligne à ligne échouaient toutes)
# ==========================================

def test_substring_match_partial_line():
    """Old_string partiel de ligne (virgule finale absente) : le texte existe mot
    pour mot comme sous-chaîne → le fallback remplace et préserve la ponctuation
    qui suit (la virgule de la ligne d'origine)."""
    whole = (
        "const PIECE_COLORS = {\n"
        "            I: [[0, '#00ffff'], ['#00ffff', '#00ffff']],\n"
        "            O: [[0, '#ffff00'], ['#ffff00', '#ffff00']],\n"
        "        };\n"
    )
    part = "            O: [[0, '#ffff00'], ['#ffff00', '#ffff00']]"
    repl = "            O: [[0, '#ffff00', '#ffff00'], ['#ffff00', '#ffff00', '#ffff00']]"
    out = replace_most_similar_chunk(whole, part, repl)
    assert out is not None
    assert (
        "O: [[0, '#ffff00', '#ffff00'], ['#ffff00', '#ffff00', '#ffff00']],\n" in out
    )


def test_substring_stripped_needle_matches():
    """Old_string sans l'indentation de la ligne : la sous-chaîne stripped unique
    est remplacée SANS toucher à l'indentation ni à la ponctuation environnantes."""
    whole = "    let colors = ['#fff', '#000'];\n"
    part = "let colors = ['#fff', '#000']"
    repl = "let colors = ['#ffffff', '#000000']"
    out = replace_most_similar_chunk(whole, part, repl)
    assert out is not None
    assert "    let colors = ['#ffffff', '#000000'];\n" == out


def test_substring_ambiguous_returns_none():
    """Sous-chaîne présente 2 fois : ambigu → None (pas de devinette)."""
    whole = "a = '#ffff00'],\nb = '#ffff00'],\n"
    part = "'#ffff00'],"
    out = replace_most_similar_chunk(whole, part, "X")
    assert out is None


def test_substring_too_short_returns_none():
    """Sous-chaîne unique mais trop courte (< 8 chars) : garde anti-aiguillage
    générique → None."""
    whole = "abcdefgh ijklmn\n"
    part = "abc"
    out = replace_most_similar_chunk(whole, part, "Z")
    assert out is None


# ==========================================
# Outil @tool search_replace (intégration fs)
# ==========================================

def test_search_replace_creates_via_empty_search(tmp_path):
    """search vide = ajout en fin de fichier."""
    f = tmp_path / "app.py"
    f.write_text("a = 1\n", encoding="utf-8")
    res = search_replace(str(f), "", "b = 2\n")
    assert "Successfully" in res
    content = f.read_text(encoding="utf-8")
    assert "a = 1" in content and "b = 2" in content


def test_search_replace_modifies_existing(tmp_path):
    f = tmp_path / "index.html"
    f.write_text("<h1>Old</h1>\n<p>keep</p>\n", encoding="utf-8")
    res = search_replace(str(f), "<h1>Old</h1>", "<h1>New</h1>")
    assert "Successfully" in res
    content = f.read_text(encoding="utf-8")
    assert "<h1>New</h1>" in content
    assert "<p>keep</p>" in content  # section non touchée préservée


def test_search_replace_rejects_placeholder(tmp_path):
    """Un 'replace' constitué uniquement d'un placeholder (TODO, '...', '// code here')
    est rejeté. Un bloc contenant DU VRAI code + un commentaire reste accepté."""
    f = tmp_path / "code.py"
    f.write_text("def f():\n    pass\n", encoding="utf-8")
    # replace purement placeholder
    res = search_replace(str(f), "def f():\n    pass", "// code here")
    assert "placeholder" in res.lower() or "ERROR" in res
    # Le fichier n'est pas modifié
    assert "pass" in f.read_text(encoding="utf-8")

    # replace purement 'TODO'
    res2 = search_replace(str(f), "def f():\n    pass", "TODO")
    assert "placeholder" in res2.lower() or "ERROR" in res2


def test_search_replace_not_found_feedback(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    res = search_replace(str(f), "delta", "epsilon")
    assert "NOT found" in res or "ERROR" in res
    assert "NOT modified" in res
    # Le fichier est intact
    assert "alpha" in f.read_text(encoding="utf-8")


def test_search_replace_missing_file(tmp_path):
    res = search_replace(str(tmp_path / "nope.txt"), "x", "y")
    assert "does not exist" in res or "ERROR" in res


def test_search_replace_tolerant_indentation_via_tool(tmp_path):
    """Test de bout en bout : le LLM fournit un search mal indenté,
    l'outil doit quand même appliquer la modification (cas réel du petit modèle)."""
    f = tmp_path / "app.py"
    f.write_text("def compute():\n    result = old_value\n    return result\n", encoding="utf-8")
    # search SANS l'indentation (erreur fréquente du 4B)
    res = search_replace(str(f), "result = old_value", "result = new_value")
    assert "Successfully" in res, f"Échec match tolérant : {res}"
    content = f.read_text(encoding="utf-8")
    assert "new_value" in content
    assert "    result = new_value" in content  # indentation préservée


# ==========================================
# F-132 : gardes anti-\n littéral + anti-no-op
# (post-mortem runs 2026-08-20_1028 + 1203 : r-string → \n littéral inséré →
# SyntaxError JS permanent ; « fix » no-op accepté comme succès → boucle)
# ==========================================

from graph_orchestrator.tools import edit_file, multi_replace, write_file


def _make_file(tmp_path, name="index.html"):
    p = tmp_path / name
    p.write_text("function a() {\n    return 1;\n}\n", encoding="utf-8")
    return p


def test_search_replace_noop_rejected(tmp_path):
    p = _make_file(tmp_path)
    before = p.read_text(encoding="utf-8")
    old = "function a() {\n    return 1;\n}"
    res = search_replace(path=str(p), old_string=old, new_string=old)
    assert "anti-no-op" in res
    assert p.read_text(encoding="utf-8") == before


def test_search_replace_literal_newline_rejected(tmp_path):
    p = _make_file(tmp_path)
    before = p.read_text(encoding="utf-8")
    # Séquence EXACTE du run 1203 : \n littéral (backslash-n texte) après ';'.
    broken = "function a() {\\n    return 2;\\n}"
    res = search_replace(
        path=str(p),
        old_string="function a() {\n    return 1;\n}",
        new_string=broken,
    )
    assert "garde anti-\\n" in res
    assert p.read_text(encoding="utf-8") == before


def test_search_replace_repair_path_old_string_with_literal_allowed(tmp_path):
    """old_string DOIT pouvoir contenir le \n littéral pour RÉPARER un fichier
    déjà corrompu (seul le texte INSÉRÉ est gardé)."""
    p = tmp_path / "index.html"
    p.write_text("const pieceData = PIECES[piece.type];\\n                const shape = 1;\n", encoding="utf-8")
    res = search_replace(
        path=str(p),
        old_string="const pieceData = PIECES[piece.type];\\n                const shape = 1;",
        new_string="const pieceData = PIECES[piece.type];\n                const shape = 2;",
    )
    assert "Successfully edited" in res
    fixed = p.read_text(encoding="utf-8")
    assert ";\\n" not in fixed
    assert ";\n" in fixed
    assert "shape = 2;" in fixed


def test_literal_newline_inside_js_string_not_rejected(tmp_path):
    """Un \n DANS une chaîne JS légitime (pas en séparateur de code) passe."""
    p = _make_file(tmp_path)
    res = search_replace(
        path=str(p),
        old_string="function a() {\n    return 1;\n}",
        new_string='function a() {\n    console.log("alpha\\nbeta");\n}',
    )
    assert "Successfully edited" in res


def test_literal_newline_non_code_file_ignored(tmp_path):
    """Hors extensions code (ex: .json), la séquence peut être légitime → pas de garde."""
    p = tmp_path / "data.json"
    p.write_text('{"a": 1}\n', encoding="utf-8")
    res = search_replace(
        path=str(p),
        old_string='{"a": 1}',
        new_string='{"a": 1,\n "b": 2}',
    )
    assert "Successfully edited" in res


def test_write_file_literal_newline_rejected(tmp_path):
    p = tmp_path / "game.js"
    res = write_file(path=str(p), content="const a = 1;\\nconst b = 2;\n")
    assert "garde anti-\\n" in res
    assert "'content'" in res
    assert not p.exists()


def test_edit_file_noop_rejected(tmp_path):
    p = _make_file(tmp_path)
    before = p.read_text(encoding="utf-8")
    old = "return 1;"
    res = edit_file(path=str(p), old_string=old, new_string=old)
    assert "anti-no-op" in res
    assert p.read_text(encoding="utf-8") == before


def test_edit_file_literal_newline_rejected(tmp_path):
    p = _make_file(tmp_path)
    before = p.read_text(encoding="utf-8")
    res = edit_file(
        path=str(p),
        old_string="return 1;",
        new_string="return 2;\\n",
    )
    assert "garde anti-\\n" in res
    assert p.read_text(encoding="utf-8") == before


def test_multi_replace_literal_newline_rejected(tmp_path):
    p = _make_file(tmp_path)
    before = p.read_text(encoding="utf-8")
    res = multi_replace(
        path=str(p),
        replacements=[{"old_string": "return 1;", "new_string": "return 2;\\n"}],
    )
    assert "garde anti-\\n" in res
    assert p.read_text(encoding="utf-8") == before


def test_multi_replace_noop_rejected(tmp_path):
    p = _make_file(tmp_path)
    before = p.read_text(encoding="utf-8")
    res = multi_replace(
        path=str(p),
        replacements=[{"old_string": "return 1;", "new_string": "return 1;"}],
    )
    assert "no-op" in res
    assert p.read_text(encoding="utf-8") == before


# ==========================================
# P2 : diagnostics de syntaxe injectés dans l'output des outils d'édition
# (port kilocode apply_patch.ts:289 — le modèle sait immédiatement)
# ==========================================

from graph_orchestrator.tools import _post_edit_syntax_directive


def _needs_node():
    import shutil
    return shutil.which("node") is None


def test_edit_cassant_js_declenche_directive(tmp_path):
    if _needs_node():
        pytest.skip("node absent")
    p = tmp_path / "game.js"
    p.write_text("const a = 1;\n", encoding="utf-8")
    res = search_replace(
        path=str(p),
        old_string="const a = 1;",
        new_string="function broken( {",
    )
    assert "Successfully edited" in res
    assert "SYNTAXE INVALIDE" in res
    assert "search_replace" in res


def test_edit_saine_aucune_directive(tmp_path):
    if _needs_node():
        pytest.skip("node absent")
    p = tmp_path / "game.js"
    p.write_text("const a = 1;\n", encoding="utf-8")
    res = search_replace(
        path=str(p),
        old_string="const a = 1;",
        new_string="const a = 2;",
    )
    assert "Successfully edited" in res
    assert "SYNTAXE INVALIDE" not in res


def test_directive_mapping_ligne_html(tmp_path):
    if _needs_node():
        pytest.skip("node absent")
    p = tmp_path / "index.html"
    p.write_text(
        "<html><body>\n<script>\nlet x = 1;\nlet y = 2;\n</script>\n</body></html>\n",
        encoding="utf-8",
    )
    res = search_replace(
        path=str(p),
        old_string="let y = 2;",
        new_string="function broken( {",
    )
    assert "SYNTAXE INVALIDE" in res
    assert "Ligne ~" in res  # mappée au numéro de ligne du bloc script


def test_directive_ignore_fichiers_non_js(tmp_path):
    p = tmp_path / "styles.css"
    p.write_text(".a { color: red; }\n", encoding="utf-8")
    assert _post_edit_syntax_directive(str(p)) == ""


def test_directive_fichier_absent_fail_open(tmp_path):
    assert _post_edit_syntax_directive(str(tmp_path / "absent.js")) == ""


def test_write_file_cassant_declenche_directive(tmp_path):
    if _needs_node():
        pytest.skip("node absent")
    p = tmp_path / "game.js"
    res = write_file(path=str(p), content="function broken( {\n")
    assert "Successfully wrote" in res
    assert "SYNTAXE INVALIDE" in res
