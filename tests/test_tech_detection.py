"""Tests de la détection de techno du Tester polyvalent (detect_tech).

Détection redondante : extensions de target_files (déterministe) + langage du
routeur (LLM). Les extensions gagnent en cas de conflit. Fallback "web".
Logique pure, sans LLM.
"""

from graph_orchestrator.testers import detect_tech, get_runner, DEFAULT_TECH
from graph_orchestrator.testers.base import detect_tech as _detect


# ==========================================
# Détection par extensions
# ==========================================

def test_python_extension_detected():
    assert detect_tech({"target_files": ["src/app.py"]}) == "python"


def test_web_extensions_detected():
    for ext in ["index.html", "styles.css", "script.js", "app.mjs"]:
        assert detect_tech({"target_files": [ext]}) == "web", ext


def test_rust_go_extensions_detected():
    assert detect_tech({"target_files": ["main.rs"]}) == "rust"
    assert detect_tech({"target_files": ["main.go"]}) == "go"


def test_typescript_extension_detected():
    assert detect_tech({"target_files": ["app.ts"]}) == "typescript"


def test_case_insensitive_extensions():
    """Les extensions en majuscules sont tolérées (.PY, .RS)."""
    assert detect_tech({"target_files": ["APP.PY"]}) == "python"
    assert detect_tech({"target_files": ["MAIN.RS"]}) == "rust"


def test_multiple_files_first_known_wins():
    """Plusieurs fichiers → première extension connue détectée (1 sous-tâche = 1 fichier en pratique)."""
    assert detect_tech({"target_files": ["readme.md", "app.py", "utils.py"]}) == "python"


# ==========================================
# Détection via le routeur
# ==========================================

def test_router_language_used_when_no_files():
    assert detect_tech({}, router_lang="python") == "python"
    assert detect_tech({}, router_lang="javascript") == "web"


def test_router_language_normalized():
    """Le langage routeur (string libre) est normalisé (casse, variantes)."""
    assert detect_tech({}, router_lang="Python") == "python"
    assert detect_tech({}, router_lang="JavaScript") == "web"
    assert detect_tech({}, router_lang="JS") == "web"
    assert detect_tech({}, router_lang="node") == "web"


# ==========================================
# Priorité + conflit + fallback
# ==========================================

def test_extension_overrides_router_on_conflict():
    """En cas de conflit, l'extension (déterministe) l'emporte sur le routeur (LLM)."""
    # Routeur dit "javascript" mais les fichiers sont .py → python.
    assert detect_tech({"target_files": ["app.py"]}, router_lang="javascript") == "python"


def test_extension_and_router_agree():
    assert detect_tech({"target_files": ["index.html"]}, router_lang="html") == "web"


def test_fallback_web_when_nothing_detected():
    """Aucun fichier + pas de routeur → "web" (compatibilité arrière)."""
    assert detect_tech({}) == DEFAULT_TECH == "web"


def test_unknown_extension_falls_back_to_router():
    """Extension inconnue (.md, .txt) → on se rabat sur le routeur."""
    assert detect_tech({"target_files": ["README.md"]}, router_lang="python") == "python"


def test_unknown_everything_falls_back_to_web():
    """Extension inconnue + routeur inconnu → web."""
    assert detect_tech({"target_files": ["README.md"]}, router_lang="klingon") == "web"


# ==========================================
# Registre des runners (get_runner)
# ==========================================

def test_get_runner_python():
    from graph_orchestrator.testers.python_tester import PythonTestRunner
    assert isinstance(get_runner("python"), PythonTestRunner)


def test_get_runner_web():
    from graph_orchestrator.testers.web_tester import WebTestRunner
    assert isinstance(get_runner("web"), WebTestRunner)


def test_get_runner_unknown_falls_back_to_web():
    """Techno sans runner dédié → WebTestRunner (compat arrière)."""
    from graph_orchestrator.testers.web_tester import WebTestRunner
    assert isinstance(get_runner("does-not-exist"), WebTestRunner)


def test_known_but_future_tech_falls_back_to_web():
    """Rust/go/etc : connus dans detect_tech mais redirigés vers web ce cycle."""
    from graph_orchestrator.testers.web_tester import WebTestRunner
    assert isinstance(get_runner("rust"), WebTestRunner)
    assert isinstance(get_runner("go"), WebTestRunner)
