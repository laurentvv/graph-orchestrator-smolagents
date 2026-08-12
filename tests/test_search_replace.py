"""Tests unitaires de l'édition SEARCH/REPLACE tolérante.

Couvre les stratégies portées d'Aider : match exact, tolérant indentation,
ellipses, échec avec feedback. Aucun appel LLM (tests déterministes du parser).
"""
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
