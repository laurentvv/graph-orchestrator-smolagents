# ==============================================================================
# Tests : graph_orchestrator/path_utils.py — normalize_tool_path (F-97 / MA-5)
# ==============================================================================
# Garde logiciel de normalisation des chemins passés aux outils fichier.
# 0 LLM, 0 réseau, 100% déterministe.
# ==============================================================================

from graph_orchestrator.path_utils import normalize_tool_path


# === file:// scheme (3 variantes de slashes) → on garde le chemin Windows ===

def test_file_scheme_triple_slash():
    assert normalize_tool_path("file:///D:/GIT/proj/index.html") == "D:/GIT/proj/index.html"

def test_file_scheme_double_slash():
    assert normalize_tool_path("file://D:/GIT/proj/index.html") == "D:/GIT/proj/index.html"

def test_file_scheme_single_slash():
    assert normalize_tool_path("file:/D:/GIT/proj/index.html") == "D:/GIT/proj/index.html"

def test_file_scheme_case_insensitive():
    assert normalize_tool_path("FILE:///D:/GIT/x.html") == "D:/GIT/x.html"

def test_file_scheme_with_subpath_landing_page():
    assert normalize_tool_path("file:///D:/GIT/runs/2026-08-11_run/landing_page/index.html") \
        == "D:/GIT/runs/2026-08-11_run/landing_page/index.html"


# === Slash initial parasite devant une lettre + deux-points ===

def test_leading_slash_drive_forward():
    assert normalize_tool_path("/D:/GIT/proj/index.html") == "D:/GIT/proj/index.html"

def test_leading_slash_drive_backslash():
    assert normalize_tool_path("/D:\\GIT\\proj\\index.html") == "D:\\GIT\\proj\\index.html"


# === Préfixe MSYS Git Bash /x/... → X:/... ===

def test_msys_prefix_lowercase():
    assert normalize_tool_path("/d/GIT/proj/index.html") == "D:/GIT/proj/index.html"

def test_msys_prefix_uppercase_drive_out():
    # Le drive ressort en majuscule (convention Windows) quelle que soit la casse entrée.
    assert normalize_tool_path("/D/GIT/proj/index.html") == "D:/GIT/proj/index.html"


# === Non-corruption : chemins relatifs et formes valides laissés intacts ===

def test_relative_simple_unchanged():
    # CRITIQUE : un chemin relatif ne doit JAMAIS être transformé en chemin absolu.
    assert normalize_tool_path("index.html") == "index.html"

def test_relative_nested_unchanged():
    # Anti-régression du piège `^([a-zA-Z])/` : `src/a.js` ne doit pas devenir `S:/rc/a.js`.
    assert normalize_tool_path("src/a.js") == "src/a.js"

def test_already_correct_forward_unchanged():
    assert normalize_tool_path("D:/GIT/proj/index.html") == "D:/GIT/proj/index.html"

def test_backslash_unchanged():
    # Le backslash est déjà valide sous Windows (open() l'accepte).
    assert normalize_tool_path("D:\\GIT\\proj\\index.html") == "D:\\GIT\\proj\\index.html"

def test_path_with_spaces_unchanged():
    assert normalize_tool_path("D:/My Project/index.html") == "D:/My Project/index.html"


# === Edge cases / fail-open ===

def test_empty_string_unchanged():
    assert normalize_tool_path("") == ""

def test_non_string_returned_as_is():
    assert normalize_tool_path(None) is None  # type: ignore[arg-type]
    assert normalize_tool_path(123) == 123  # type: ignore[arg-type]

def test_strips_surrounding_whitespace():
    assert normalize_tool_path("  file:///D:/x.html  ") == "D:/x.html"

def test_idempotent():
    p = "file:///D:/GIT/proj/index.html"
    once = normalize_tool_path(p)
    twice = normalize_tool_path(once)
    assert once == twice == "D:/GIT/proj/index.html"

def test_unix_style_abs_path_left_unchanged():
    # /var/log/x n'a pas de forme reconnue (pas de lettre+":"+ ni 1 lettre+/x/)
    # → laissé tel quel (fail-open). Sur Windows il échouerait de toute façon.
    assert normalize_tool_path("/var/log/x") == "/var/log/x"
