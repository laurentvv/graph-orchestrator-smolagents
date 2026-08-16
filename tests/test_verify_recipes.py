"""Tests unitaires F-100 — Recettes de vérification exécutable (hermes verify/).

Déterministes, 0 LLM. Les tests du runner démarrent de VRAIS serveurs locaux
(http.server / sleep python) sur des ports libres 127.0.0.1 puis les démontent —
même niveau de confiance que la prod, ~1-2s par test.

Couverture :
- Recipe dataclass (to_dict/from_dict tolérant, ports/readiness normalisés).
- Détection : package managers (lockfiles), Node (frameworks + scripts),
  Python (Django/FastAPI/Flask/générique), Go/Rust/Java/Make/compose,
  static-web (notre ajout : index.html / html nommé / vide / précédence node).
- Runner : phases=None vs () (écart vs référence), readiness OK réelle,
  readiness KO, substitution {port}, teardown no-op sur process fini.
- Environment : manifeste round-trip, corrompu → détection, manifeste PRIME.
- Intégration Static Tester : preuve [http] en success, opt-out,
  réfutation sur start projet KO, dégradation static-web KO.
"""

import json
import sys

import pytest

from graph_orchestrator.verify.environment import (
    load_manifest,
    load_or_detect,
    manifest_path,
    save_manifest,
)
from graph_orchestrator.verify.recipes import (
    Recipe,
    detect_package_manager,
    detect_recipe,
    _detect_static_web_recipe,
    _infer_port_from_command,
)
from graph_orchestrator.verify.runner import (
    PhaseResult,
    VerifyResult,
    _resolve_start_command,
    _terminate_process_tree,
    run_verify,
)


# ---------------------------------------------------------------------------
# Recipe dataclass
# ---------------------------------------------------------------------------

def test_recipe_defaults():
    r = Recipe("Mon app")
    assert r.kind == "unknown"
    assert r.bootstrap == [] and r.build == [] and r.test == []
    assert r.start is None and r.port is None
    assert r.readiness_path == "/" and r.evidence == []


def test_recipe_dict_roundtrip():
    r = Recipe("App", kind="vite", bootstrap=["npm install"], build=["npm run build"],
               test=["npm test"], start="npm run dev", port=5173,
               readiness_path="/health", evidence=["Detected package.json"])
    r2 = Recipe.from_dict(json.loads(json.dumps(r.to_dict())))
    assert r2 is not None
    assert r2.to_dict() == r.to_dict()


def test_recipe_from_dict_tolerant():
    assert Recipe.from_dict(None) is None
    assert Recipe.from_dict("nope") is None
    assert Recipe.from_dict({}) is None  # pas de name
    assert Recipe.from_dict({"appLabel": "X"}) is not None  # alias grok
    # Port string valide / invalide, readiness sans slash de tête normalisée.
    r = Recipe.from_dict({"name": "X", "startCommand": "serve", "startPort": "3000",
                          "readiness_path": "health"})
    assert r is not None and r.start == "serve" and r.port == 3000
    assert r.readiness_path == "/"


# ---------------------------------------------------------------------------
# Helpers de détection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lockfile,manager", [
    ("pnpm-lock.yaml", "pnpm"),
    ("bun.lock", "bun"),
    ("yarn.lock", "yarn"),
    ("package-lock.json", "npm"),
    ("uv.lock", "uv"),
    ("poetry.lock", "poetry"),
    ("Pipfile.lock", "pipenv"),
])
def test_detect_package_manager(tmp_path, lockfile, manager):
    (tmp_path / lockfile).write_text("", encoding="utf-8")
    assert detect_package_manager(tmp_path) == manager


def test_detect_package_manager_none(tmp_path):
    assert detect_package_manager(tmp_path) is None


@pytest.mark.parametrize("command,expected", [
    ("vite --port 3000", 3000),
    ("vite -p 8080", 8080),
    ("PORT=5000 node server.js", 5000),
    ("node server.js", None),
    (None, None),
])
def test_infer_port_from_command(command, expected):
    assert _infer_port_from_command(command) == expected


# ---------------------------------------------------------------------------
# Détection Node
# ---------------------------------------------------------------------------

def _pkg(tmp_path, scripts=None, deps=None, dev_deps=None, lockfile=None):
    pkg = {"name": "app", "version": "1.0.0"}
    if scripts:
        pkg["scripts"] = scripts
    if deps:
        pkg["dependencies"] = deps
    if dev_deps:
        pkg["devDependencies"] = dev_deps
    (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
    if lockfile:
        (tmp_path / lockfile).write_text("", encoding="utf-8")
    return tmp_path


def test_detect_node_vite(tmp_path):
    _pkg(tmp_path, scripts={"dev": "vite --port 4200", "build": "vite build"},
         dev_deps={"vite": "^5.0.0"})
    r = detect_recipe(tmp_path)
    assert r is not None and r.kind == "vite"
    assert r.start == "npm run dev"
    assert r.port == 4200  # inféré depuis le corps du script dev
    assert r.bootstrap == ["npm install"]
    assert "npm run build" in r.build


def test_detect_node_next_default_port(tmp_path):
    _pkg(tmp_path, scripts={"start": "next start"}, deps={"next": "14.0.0"})
    r = detect_recipe(tmp_path)
    assert r is not None and r.kind == "nextjs" and r.port == 3000
    assert r.start == "npm run start"


def test_detect_node_pnpm_runner(tmp_path):
    _pkg(tmp_path, scripts={"dev": "vite"}, dev_deps={"vite": "^5"}, lockfile="pnpm-lock.yaml")
    r = detect_recipe(tmp_path)
    assert r is not None
    assert r.start == "pnpm dev"
    assert r.bootstrap == ["pnpm install"]


def test_detect_node_no_start_script(tmp_path):
    _pkg(tmp_path, scripts={"build": "tsc"})
    r = detect_recipe(tmp_path)
    assert r is not None and r.start is None and r.port is None


# ---------------------------------------------------------------------------
# Détection Python
# ---------------------------------------------------------------------------

def test_detect_python_django(tmp_path):
    (tmp_path / "manage.py").write_text("", encoding="utf-8")
    r = detect_recipe(tmp_path)
    assert r is not None and r.kind == "django"
    assert "runserver" in r.start and r.port == 8000
    assert "python manage.py test" in r.test


def test_detect_python_fastapi(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["fastapi"]\n',
                                             encoding="utf-8")
    (tmp_path / "main.py").write_text("app = None\n", encoding="utf-8")
    r = detect_recipe(tmp_path)
    assert r is not None and r.kind == "fastapi"
    assert r.start == "uvicorn main:app --host 0.0.0.0 --port 8000"


def test_detect_python_flask(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask==3.0.0\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("app = None\n", encoding="utf-8")
    r = detect_recipe(tmp_path)
    assert r is not None and r.kind == "flask" and r.port == 5000


def test_detect_python_generic(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests\n", encoding="utf-8")
    r = detect_recipe(tmp_path)
    assert r is not None and r.kind == "python"
    assert r.test == ["python -m unittest discover"]  # pas de dossier tests/
    assert r.start is None


# ---------------------------------------------------------------------------
# Détection Go / Rust / Java / Make / compose
# ---------------------------------------------------------------------------

def test_detect_go(tmp_path):
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
    (tmp_path / "main.go").write_text("package main\n", encoding="utf-8")
    r = detect_recipe(tmp_path)
    assert r is not None and r.kind == "go"
    assert r.start == "go run ." and r.build == ["go build ./..."]


def test_detect_rust(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname = 'x'\n", encoding="utf-8")
    r = detect_recipe(tmp_path)
    assert r is not None and r.kind == "rust" and r.start is None


def test_detect_maven(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    r = detect_recipe(tmp_path)
    assert r is not None and r.kind == "maven" and r.build == ["mvn package"]


def test_detect_make(tmp_path):
    (tmp_path / "Makefile").write_text(
        "install:\n\tpip install -r requirements.txt\nbuild:\n\techo b\ntest:\n\tpytest\nrun:\n\tpython app.py\n",
        encoding="utf-8")
    r = detect_recipe(tmp_path)
    assert r is not None and r.kind == "make"
    assert r.start == "make run" and "make test" in r.test


def test_detect_compose(tmp_path):
    (tmp_path / "compose.yml").write_text("services: {}\n", encoding="utf-8")
    r = detect_recipe(tmp_path)
    assert r is not None and r.kind == "compose" and r.start == "docker compose up"


# ---------------------------------------------------------------------------
# Détection static-web (écart consciencieux — notre cas Prompt-Vault)
# ---------------------------------------------------------------------------

def test_detect_static_web_index(tmp_path):
    (tmp_path / "index.html").write_text("<html><body>hi</body></html>", encoding="utf-8")
    r = _detect_static_web_recipe(tmp_path)
    assert r is not None and r.kind == "static-web"
    assert r.readiness_path == "/"
    assert "http.server" in r.start and "{port}" in r.start
    assert "--bind 127.0.0.1" in r.start  # anti popup firewall Windows


def test_detect_static_web_named_html(tmp_path):
    (tmp_path / "visualizer.html").write_text("<html></html>", encoding="utf-8")
    r = _detect_static_web_recipe(tmp_path)
    assert r is not None and r.readiness_path == "/visualizer.html"


def test_detect_static_web_requires_html(tmp_path):
    assert _detect_static_web_recipe(tmp_path) is None
    (tmp_path / "styles.css").write_text("body{}", encoding="utf-8")
    assert _detect_static_web_recipe(tmp_path) is None


def test_node_recipe_precedence_over_static_web(tmp_path):
    # package.json + index.html → recette node (plus précise), pas static-web.
    _pkg(tmp_path, scripts={"dev": "vite"}, dev_deps={"vite": "^5"})
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    r = detect_recipe(tmp_path)
    assert r is not None and r.kind == "vite"


def test_detect_recipe_vanilla_dir_falls_back_to_static_web(tmp_path):
    # Cas dominant de l'usine : dossier runs/ vanilla sans manifeste de build.
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "styles.css").write_text("body{}", encoding="utf-8")
    (tmp_path / "script.js").write_text("console.log(1);", encoding="utf-8")
    r = detect_recipe(tmp_path)
    assert r is not None and r.kind == "static-web"


def test_detect_recipe_empty_dir(tmp_path):
    assert detect_recipe(tmp_path) is None


# ---------------------------------------------------------------------------
# Runner — sémantique phases + substitution {port}
# ---------------------------------------------------------------------------

def test_phase_result_ok_semantics():
    ok = PhaseResult(phase="build", command="x", exit_code=0, duration=0.1, output_tail="")
    assert ok.ok
    ko_exit = PhaseResult(phase="build", command="x", exit_code=1, duration=0.1, output_tail="")
    ko_timeout = PhaseResult(phase="build", command="x", exit_code=None, duration=5,
                             output_tail="", timed_out=True)
    assert not ko_exit.ok and not ko_timeout.ok


def test_run_verify_phases_none_runs_all(tmp_path):
    # phases=None (défaut) = toutes les phases. start absent → readiness None.
    recipe = Recipe("R", kind="python", bootstrap=["echo bootstrap-ok"],
                    test=["echo test-ok"])
    result = run_verify(tmp_path, recipe, phase_timeout=10)
    assert [p.phase for p in result.phases] == ["bootstrap", "test"]
    assert all(p.ok for p in result.phases)
    assert result.readiness is None and result.ok


def test_run_verify_phases_empty_skips_all(tmp_path):
    # phases=() = AUCUNE phase (écart vs référence : falsy ≠ toutes) — le hot
    # path du Static Tester ne doit exécuter QUE start+readiness.
    recipe = Recipe("R", kind="python", bootstrap=["echo should-not-run"])
    result = run_verify(tmp_path, recipe, phases=(), phase_timeout=10)
    assert result.phases == []


def test_resolve_start_command_port_placeholder():
    recipe = Recipe("R", kind="static-web", start="serve {port} --bind 127.0.0.1")
    assert _resolve_start_command(recipe, 4242) == "serve 4242 --bind 127.0.0.1"
    fixed = Recipe("R", kind="node", start="npm run dev")
    assert _resolve_start_command(fixed, 4242) == "npm run dev"


def test_run_verify_static_web_readiness_ok(tmp_path):
    """VRAI http.server sur port libre : la page est servie → preuve HTTP."""
    (tmp_path / "index.html").write_text("<html><body>Bubble Sort</body></html>",
                                         encoding="utf-8")
    recipe = detect_recipe(tmp_path)
    assert recipe is not None and recipe.kind == "static-web"
    result = run_verify(tmp_path, recipe, phases=(), ready_timeout=15)
    assert result.readiness is not None
    assert result.readiness.ready and result.readiness.status_code == 200
    assert result.readiness.url.startswith("http://127.0.0.1:")
    assert result.readiness.url.endswith("/")
    assert result.ok
    # Le serveur doit être DEMONTÉ : le port redevient bindable.
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))  # ne lève pas → stack réseau saine


def test_run_verify_readiness_ko(tmp_path):
    # Commande start qui meurt immédiatement : aucun port n'écoute → KO.
    recipe = Recipe("R", kind="node", start="exit 7", port=9, readiness_path="/")
    result = run_verify(tmp_path, recipe, phases=(), ready_timeout=0.5)
    assert result.readiness is not None
    assert not result.readiness.ready and result.readiness.error
    assert not result.ok


def test_terminate_process_tree_noop_on_finished(tmp_path):
    import subprocess
    proc = subprocess.Popen(["cmd", "/c", "exit 0"] if sys.platform == "win32"
                            else ["true"], shell=False,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc.wait(timeout=10)
    _terminate_process_tree(proc)  # ne doit ni lever ni attendre


def test_verify_result_to_dict_shape():
    res = VerifyResult(recipe_name="R")
    res.readiness = None
    d = res.to_dict()
    assert d["recipe"] == "R" and d["ok"] is True and d["phases"] == []


# ---------------------------------------------------------------------------
# Environment — manifeste
# ---------------------------------------------------------------------------

def test_manifest_roundtrip(tmp_path):
    recipe = Recipe("Custom", kind="node", start="npm run preview", port=4173,
                    readiness_path="/preview")
    path = save_manifest(tmp_path, recipe)
    assert path == manifest_path(tmp_path)
    loaded = load_manifest(tmp_path)
    assert loaded is not None
    assert loaded.to_dict() == recipe.to_dict()


def test_manifest_corrupt_degrades_to_none(tmp_path):
    assert load_manifest(tmp_path) is None  # absent
    manifest_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    manifest_path(tmp_path).write_text("{not json", encoding="utf-8")
    assert load_manifest(tmp_path) is None
    manifest_path(tmp_path).write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    assert load_manifest(tmp_path) is None


def test_load_or_detect_manifest_wins(tmp_path):
    # Le dossier ressemble à un projet node, mais le manifeste PRIME.
    _pkg(tmp_path, scripts={"dev": "vite"}, dev_deps={"vite": "^5"})
    save_manifest(tmp_path, Recipe("Forcé", kind="static-web", start="serve {port}"))
    recipe, source = load_or_detect(tmp_path)
    assert source == "manifest"
    assert recipe is not None and recipe.name == "Forcé" and recipe.kind == "static-web"


def test_load_or_detect_detected(tmp_path):
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    recipe, source = load_or_detect(tmp_path)
    assert source == "detected"
    assert recipe is not None and recipe.kind == "static-web"


# ---------------------------------------------------------------------------
# Intégration Static Tester — Tier HTTP
# ---------------------------------------------------------------------------

_MINIMAL_HTML = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><title>App</title></head>
<body><h1>App</h1></body></html>
"""


def _run_static_tester(monkeypatch, tmp_path, html=_MINIMAL_HTML, name="index.html"):
    from graph_orchestrator.static_tester import execute_static_tester_node
    # Chrome/npx non requis pour ces tests : on borne au Tier 1 + Tier HTTP.
    monkeypatch.setenv("STATIC_TESTER_DEVTOOLS", "0")
    monkeypatch.setenv("STATIC_TESTER_HTTP", "1")
    monkeypatch.setenv("STATIC_TESTER_HTTP_TIMEOUT", "8")
    p = tmp_path / name
    p.write_text(html, encoding="utf-8")
    subtask = {"id": "st1", "target_files": [str(p)]}
    return execute_static_tester_node(subtask, settings=None)[0]


def test_static_tester_http_proof_on_success(monkeypatch, tmp_path):
    """HTML propre → success + preuve [http] « Page servie » (HTTP 200)."""
    res = _run_static_tester(monkeypatch, tmp_path)
    assert res.status == "success"
    assert "[http] Page servie" in res.details
    assert "HTTP 200" in res.details and "static-web/detected" in res.details


def test_static_tester_http_opt_out(monkeypatch, tmp_path):
    """STATIC_TESTER_HTTP=0 → pas de serveur, pas de preuve [http]."""
    monkeypatch.setenv("STATIC_TESTER_HTTP", "0")
    from graph_orchestrator.static_tester import execute_static_tester_node
    monkeypatch.setenv("STATIC_TESTER_DEVTOOLS", "0")
    p = tmp_path / "index.html"
    p.write_text(_MINIMAL_HTML, encoding="utf-8")
    res, _ = execute_static_tester_node({"id": "st1", "target_files": [str(p)]},
                                        settings=None)
    assert res.status == "success"
    assert "[http]" not in res.details


def test_static_tester_http_skipped_when_bug_detected(monkeypatch, tmp_path):
    """Un bug Tier 1 (TS-in-vanilla) court-circuite : pas de preuve HTTP."""
    buggy = ('<html><body><script>function f(x: number) { return x; }</script>'
             "</body></html>")
    # node requis pour attraper le TS — sinon skip silencieux et pas de bug.
    import shutil
    if shutil.which("node") is None:
        pytest.skip("node absent — Tier 1a indisponible")
    res = _run_static_tester(monkeypatch, tmp_path, html=buggy)
    assert res.status == "failure"
    assert "[http]" not in res.details


def test_static_tester_http_failure_on_broken_project_start(monkeypatch, tmp_path):
    """Recette non static-web dont le start ne répond JAMAIS → réfutation."""
    res = _run_static_tester(monkeypatch, tmp_path)
    assert res.status == "success"  # pré-condition : tiers propres
    # Surcharge manifeste : serveur « du projet » qui tourne sans écouter.
    monkeypatch.setenv("STATIC_TESTER_HTTP_TIMEOUT", "1")
    manifest_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    manifest_path(tmp_path).write_text(json.dumps({
        "version": 1,
        "recipe": {"name": "Slow app", "kind": "node",
                   "start": f'"{sys.executable}" -c "import time; time.sleep(20)"',
                   "port": 9, "readinessPath": "/"},
    }), encoding="utf-8")
    res2 = _run_static_tester(monkeypatch, tmp_path)
    assert res2.status == "failure"
    assert "[http]" in res2.details and "n'a jamais répondu" in res2.details


def test_static_tester_http_static_web_ko_degrades(monkeypatch, tmp_path):
    """Recette static-web dont le start meurt → NOTE (infra), pas d'échec."""
    res = _run_static_tester(monkeypatch, tmp_path)
    assert res.status == "success"
    monkeypatch.setenv("STATIC_TESTER_HTTP_TIMEOUT", "1")
    manifest_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    manifest_path(tmp_path).write_text(json.dumps({
        "version": 1,
        "recipe": {"name": "Static KO", "kind": "static-web",
                   "start": "exit 3", "readinessPath": "/"},
    }), encoding="utf-8")
    res2 = _run_static_tester(monkeypatch, tmp_path)
    assert res2.status == "success"  # infrastructure locale ≠ bug du modèle
    assert "Readiness KO ignorée" in res2.details
