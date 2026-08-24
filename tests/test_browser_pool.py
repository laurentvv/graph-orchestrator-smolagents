"""Tests du pool navigateur run-scoped (F-163).

Couvre :
  - graph_orchestrator/browser_pool.py : machine à états (configure/lease/
    refcount/shutdown), respawn sur Chrome mort, repli historique (Chrome
    introuvable), watch_spawn (repli puppeteer), sweep automation, primitives
    Windows (tasklist/taskkill/PowerShell/health HTTP).
  - agent_server/mcp.build_chrome_devtools_params(browser_url=...) : injection
    --browserUrl (et retrait --isolated/--executable-path).
  - Façades : chrome_devtools_tools (lease → params), build_devtools_mcp_toolset
    (transport --browserUrl), wrapper run_coding_workflow (shutdown garanti).

Pattern du projet : SYNCHRONE + monkeypatch, AUCUN spawn réel de process ni
réseau (les primitives subprocess/urllib sont mockées au point d'entrée). Le
pool est BYPASSÉ sous pytest par défaut (browser_pool._PYTEST) : les tests le
réactivent en posant explicitement ``monkeypatch.setattr(browser_pool, "_PYTEST", False)``.
"""

import asyncio
import json
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from agent_server import mcp as mcp_module
from graph_orchestrator import browser_pool as bp
from graph_orchestrator import chrome_devtools_tool
from graph_orchestrator.browser_pool import BrowserPool


# ==========================================
# Helpers : stubs process/HTTP zéro side-effect
# ==========================================


class _FakeCompleted:
    def __init__(self, stdout: str = "", returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode


def _fake_proc(pid: int = 4242):
    proc = MagicMock()
    proc.pid = pid
    proc.poll.return_value = None
    return proc


@pytest.fixture()
def pool():
    """BrowserPool frais par test (jamais le singleton)."""
    return BrowserPool()


def _arm_spawn(monkeypatch, pool, *, pid=4242, healthy=True, chrome="C:/chrome.exe"):
    """Branche des primitives de spawn factices ; retourne les compteurs.

    Horloge FAKE (le polling de readiness n'attend jamais pour de vrai), zéro
    fichier temporaire, zéro écriture dans le registre disque du reaper F-140.
    """
    calls = {"popen": 0, "kill": [], "http": 0}
    clock = {"now": 1000.0}

    monkeypatch.setattr(bp.time, "time", lambda: clock["now"])
    monkeypatch.setattr(bp.time, "sleep", lambda s: clock.__setitem__("now", clock["now"] + s) or None)
    monkeypatch.setattr(bp, "find_chrome_executable", lambda: chrome)
    monkeypatch.setattr(bp, "_pick_free_port", lambda: 39217)
    monkeypatch.setattr(bp, "_pids_by_name", lambda name: set())
    monkeypatch.setattr(bp, "_kill_tree", lambda pid: calls["kill"].append(pid) or True)
    monkeypatch.setattr(bp.tempfile, "mkdtemp", lambda prefix="": "Z:/fake-pool-dir")
    import graph_orchestrator.process_reaper as _reaper

    monkeypatch.setattr(_reaper, "register_process", lambda *a, **k: None)
    monkeypatch.setattr(_reaper, "unregister_process", lambda *a, **k: None)

    def fake_http(port, timeout_s=2.0):
        calls["http"] += 1
        return healthy

    monkeypatch.setattr(bp, "_http_json_version_ok", fake_http)

    def fake_popen(args, **kwargs):
        calls["popen"] += 1
        return _fake_proc(pid)

    monkeypatch.setattr(bp.subprocess, "Popen", fake_popen)
    return calls


# ==========================================
# pool_should_engage — gating config + pytest
# ==========================================


class TestPoolShouldEngage:
    def test_bypass_sous_pytest(self):
        """Sous pytest, le pool ne s'engage JAMAIS par défaut (suite 0-réseau)."""
        assert bp.pool_should_engage(MagicMock(browser_pool_enabled=True)) is False

    def test_engage_hors_pytest_si_active(self, monkeypatch):
        monkeypatch.setitem(bp._OVERRIDE, "force", False)
        assert bp.pool_should_engage(MagicMock(browser_pool_enabled=True)) is True

    def test_pas_engage_si_config_desactivee(self, monkeypatch):
        monkeypatch.setitem(bp._OVERRIDE, "force", False)
        assert bp.pool_should_engage(MagicMock(browser_pool_enabled=False)) is False

    def test_defaut_settings_active(self, monkeypatch):
        monkeypatch.setitem(bp._OVERRIDE, "force", False)
        from graph_orchestrator.config import settings

        assert bp.pool_should_engage(settings) is True

    def test_detection_pytest_a_l_appel(self, monkeypatch):
        """La détection doit être dynamique (PYTEST_CURRENT_TEST posé par test,
        jamais à l'import) : _OVERRIDE force l'état inverse et EST respecté."""
        monkeypatch.setitem(bp._OVERRIDE, "force", False)
        assert bp._under_pytest() is False
        monkeypatch.setitem(bp._OVERRIDE, "force", True)
        assert bp._under_pytest() is True

    def test_sweep_interdit_sous_pytest(self, pool, monkeypatch):
        """Le shutdown d'un pool créé sous pytest ne JAMAIS balayer (kill de
        process réels interdit depuis une suite de tests)."""
        assert pool._sweep_enabled is False
        killed = []
        monkeypatch.setattr(bp, "_kill_tree", lambda pid: killed.append(pid) or True)
        pool._baseline_chrome = {100}
        monkeypatch.setattr(bp, "_pids_by_name", lambda name: {100, 200})
        monkeypatch.setattr(
            bp, "_cmdlines_by_pid",
            lambda name: {200: "chrome --remote-debugging-pipe"},
        )
        pool.shutdown_run(reason="test")
        assert killed == []  # même 200 (marqueur automation) : sweep OFF


# ==========================================
# Primitives Windows (tasklist / taskkill / PowerShell / health)
# ==========================================


class TestPrimitives:
    def test_pids_by_name_parse_csv(self, monkeypatch):
        out = '"chrome.exe","101","Console","1","12 345 K"\n"chrome.exe","202","Console","1","678 K"\n'
        monkeypatch.setattr(bp, "_IS_WINDOWS", True)
        monkeypatch.setattr(bp.subprocess, "run", lambda *a, **k: _FakeCompleted(out))
        assert bp._pids_by_name("chrome.exe") == {101, 202}

    def test_pids_by_name_ligne_info_ignoree(self, monkeypatch):
        out = "INFO: Aucune tâche ne correspond.\n"
        monkeypatch.setattr(bp, "_IS_WINDOWS", True)
        monkeypatch.setattr(bp.subprocess, "run", lambda *a, **k: _FakeCompleted(out))
        assert bp._pids_by_name("chrome.exe") == set()

    def test_pids_by_name_non_windows_vide(self, monkeypatch):
        monkeypatch.setattr(bp, "_IS_WINDOWS", False)
        assert bp._pids_by_name("chrome.exe") == set()

    def test_cmdlines_by_pid_parse_liste(self, monkeypatch):
        data = json.dumps([
            {"Pid": 1, "Cl": "chrome --remote-debugging-pipe"},
            {"Pid": 2, "Cl": None},
        ])
        monkeypatch.setattr(bp, "_IS_WINDOWS", True)
        monkeypatch.setattr(bp.subprocess, "run", lambda *a, **k: _FakeCompleted(data))
        assert bp._cmdlines_by_pid("chrome.exe") == {1: "chrome --remote-debugging-pipe", 2: ""}

    def test_cmdlines_by_pid_objet_unique(self, monkeypatch):
        data = json.dumps({"Pid": 7, "Cl": "node server.js"})
        monkeypatch.setattr(bp, "_IS_WINDOWS", True)
        monkeypatch.setattr(bp.subprocess, "run", lambda *a, **k: _FakeCompleted(data))
        assert bp._cmdlines_by_pid("node.exe") == {7: "node server.js"}

    def test_cmdlines_by_pid_sortie_vide(self, monkeypatch):
        monkeypatch.setattr(bp, "_IS_WINDOWS", True)
        monkeypatch.setattr(bp.subprocess, "run", lambda *a, **k: _FakeCompleted(""))
        assert bp._cmdlines_by_pid("node.exe") == {}

    def test_cmdlines_by_pid_erreur_fail_safe(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("powershell absent")

        monkeypatch.setattr(bp, "_IS_WINDOWS", True)
        monkeypatch.setattr(bp.subprocess, "run", boom)
        assert bp._cmdlines_by_pid("chrome.exe") == {}

    def test_kill_tree_pid_invalide(self):
        assert bp._kill_tree(0) is False
        assert bp._kill_tree(-5) is False

    def test_http_health_ok_et_ko(self, monkeypatch):
        class _Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(bp.urllib.request, "urlopen", lambda url, timeout: _Resp())
        assert bp._http_json_version_ok(1234) is True

        def boom(url, timeout):
            raise ConnectionError("down")

        monkeypatch.setattr(bp.urllib.request, "urlopen", boom)
        assert bp._http_json_version_ok(1234) is False


# ==========================================
# Machine à états du pool
# ==========================================


class TestPoolEtat:
    def test_configure_run_idempotent(self, pool, monkeypatch):
        seen = []
        monkeypatch.setattr(bp, "_pids_by_name", lambda name: seen.append(name) or {1})
        pool.configure_run("coding_aaa")
        pool.configure_run("coding_aaa")
        # baselines chrome + node UNE seule fois chacune
        assert sorted(seen) == ["chrome.exe", "node.exe"]

    def test_acquire_spawn_puis_lease_chaud(self, pool, monkeypatch):
        calls = _arm_spawn(monkeypatch, pool)
        with pool.lease("consumer-1") as url1:
            assert url1 == "http://127.0.0.1:39217"
            assert calls["popen"] == 1
            with pool.lease("consumer-2") as url2:
                # Chrome CHAUD : aucun respawn, même URL partagée.
                assert url2 == url1
                assert calls["popen"] == 1
                assert pool.stats()["refcount"] == 2
        assert pool.stats()["refcount"] == 0

    def test_release_standalone_dernier_shutdown(self, pool, monkeypatch):
        """Sans configure_run (scripts d'isolation F-89) : le DERNIER release tue."""
        calls = _arm_spawn(monkeypatch, pool)
        with pool.lease("debug"):
            pass
        assert calls["kill"] == [4242]
        st = pool.stats()
        assert st["root_pid"] is None and st["refcount"] == 0 and st["run_id"] is None

    def test_release_run_scoped_garde_chrome_chaud(self, pool, monkeypatch):
        """Configure_run ancré : refcount 0 NE tue PAS (Chrome chaud pour le run)."""
        calls = _arm_spawn(monkeypatch, pool)
        pool.configure_run("coding_x")
        with pool.lease("coder"):
            pass
        assert calls["kill"] == []
        assert pool.stats()["root_pid"] == 4242
        # ...jusqu'au shutdown explicite du workflow.
        pool.shutdown_run(reason="fin de run")
        assert calls["kill"] == [4242]
        assert pool.stats()["root_pid"] is None

    def test_respawn_si_chrome_mort(self, pool, monkeypatch):
        calls = _arm_spawn(monkeypatch, pool)
        pool.configure_run("coding_x")
        with pool.lease("a"):
            pass
        # Le Chrome meurt entre deux consommateurs : 1er health-check KO,
        # respawn, puis prêt (les checks suivants répondent à nouveau).
        checks = {"n": 0}

        def http_died_then_alive(port, timeout_s=2.0):
            checks["n"] += 1
            return checks["n"] > 1

        monkeypatch.setattr(bp, "_http_json_version_ok", http_died_then_alive)
        with pool.lease("b") as url:
            assert url == "http://127.0.0.1:39217"
            # cadavre tué PUIS respawn
            assert calls["popen"] == 2
            assert calls["kill"] == [4242]

    def test_chrome_introuvable_desactive_et_fallback(self, pool, monkeypatch):
        monkeypatch.setattr(bp, "find_chrome_executable", lambda: None)
        monkeypatch.setattr(bp, "_pids_by_name", lambda name: set())
        url = pool.acquire("coder")
        assert url is None
        assert "Chrome introuvable" in pool.stats()["disabled_reason"]
        # Acquisitions suivantes : court-circuit (aucune tempête de tentatives).
        assert pool.acquire("tester") is None

    def test_spawn_timeout_kill_et_fallback(self, pool, monkeypatch):
        calls = _arm_spawn(monkeypatch, pool, healthy=False)
        with pool.lease("coder") as url:
            assert url is None
        assert calls["popen"] == 1
        assert calls["kill"] == [4242]  # cadavre tué, pas de leak
        # Pas de disablement permanent : le consommateur suivant retente.
        with pool.lease("coder2") as url2:
            assert url2 is None
        assert calls["popen"] == 2

    def test_nouveau_run_supersede_l_arbre_precedent(self, pool, monkeypatch):
        calls = _arm_spawn(monkeypatch, pool)
        pool.configure_run("coding_ancien")
        with pool.lease("a"):
            pass
        pool.configure_run("coding_nouveau")
        assert 4242 in calls["kill"]
        assert pool.stats()["run_id"] == "coding_nouveau"

    def test_lease_acquire_ko_ne_fuit_pas_refcount(self, pool, monkeypatch):
        monkeypatch.setattr(bp, "find_chrome_executable", lambda: None)
        monkeypatch.setattr(bp, "_pids_by_name", lambda name: set())
        pool.acquire("a")
        pool.acquire("b")
        assert pool.stats()["refcount"] == 0

    def test_watch_spawn_capture_arbre_automation(self, pool, monkeypatch):
        seq = [{"old"}, {"old", 777}]
        monkeypatch.setattr(bp, "_IS_WINDOWS", True)
        monkeypatch.setattr(bp, "_pids_by_name", lambda name: seq.pop(0) if seq else {"old", 777})
        monkeypatch.setattr(
            bp, "_cmdlines_by_pid",
            lambda name: {777: "chrome --remote-debugging-pipe --user-data-dir=X"},
        )
        monkeypatch.setattr(bp.time, "sleep", lambda s: None)
        with pool.watch_spawn("puppeteer"):
            pass
        assert pool.stats()["watched"] == [777]

    def test_watch_spawn_sans_marqueur_ne_captur_pas(self, pool, monkeypatch):
        # Chrome de l'utilisateur ouvert PENDANT la fenêtre : pas de marqueur
        # automation → JAMAIS capturé (fail-safe).
        seq = [{"old"}, {"old", 888}]
        monkeypatch.setattr(bp, "_IS_WINDOWS", True)
        monkeypatch.setattr(bp, "_pids_by_name", lambda name: seq.pop(0) if seq else {"old", 888})
        monkeypatch.setattr(bp, "_cmdlines_by_pid", lambda name: {888: "chrome --profile-directory=Default"})
        monkeypatch.setattr(bp.time, "sleep", lambda s: None)
        with pool.watch_spawn("puppeteer"):
            pass
        assert pool.stats()["watched"] == []

    def test_watch_spawn_ne_avale_pas_l_exception(self, pool, monkeypatch):
        monkeypatch.setattr(bp, "_pids_by_name", lambda name: set())
        monkeypatch.setattr(pool, "_collect_new_chrome_trees", MagicMock(side_effect=RuntimeError("boom")))
        with pytest.raises(ValueError):
            with pool.watch_spawn("x"):
                raise ValueError("corps")
        # L'erreur de monitoring n'écrase pas l'exception d'origine (pas de
        # return dans finally) : c'est bien ValueError qui remonte.

    def test_sweep_chrome_automation_hors_baseline(self, pool, monkeypatch):
        pool._baseline_chrome = {100, 101}
        pool._baseline_node = {500}
        monkeypatch.setattr(bp, "_IS_WINDOWS", True)
        monkeypatch.setattr(
            bp, "_pids_by_name",
            lambda name: {100, 101, 200, 300} if name == "chrome.exe" else {500, 600},
        )
        monkeypatch.setattr(
            bp, "_cmdlines_by_pid",
            lambda name: {
                100: "chrome perso", 101: "chrome perso",
                200: "chrome --remote-debugging-pipe",
                300: "chrome --profile-directory=Default",
                600: "node chrome-devtools-mcp",
            } if name == "chrome.exe" else {600: "node .../chrome-devtools-mcp ..."},
        )
        targets = pool._sweep_automation_locked()
        assert sorted(targets) == [200, 600]  # 300 (Chrome perso du run) épargné

    def test_sweep_fail_safe_sans_cmdlines(self, pool, monkeypatch):
        pool._baseline_chrome = {100}
        monkeypatch.setattr(bp, "_IS_WINDOWS", True)
        monkeypatch.setattr(bp, "_pids_by_name", lambda name: {100, 200})
        monkeypatch.setattr(bp, "_cmdlines_by_pid", lambda name: {})
        # PowerShell indisponible → AUCUN kill (fail-safe utilisateur).
        assert pool._sweep_automation_locked() == []

    def test_shutdown_tue_arbre_et_watchés(self, pool, monkeypatch):
        calls = _arm_spawn(monkeypatch, pool)
        pool.configure_run("coding_x")
        with pool.lease("coder"):
            pool._watched.update({777, 778})
        pool.shutdown_run(reason="test")
        # Ordre : arbre racine d'abord, puis arbres capturés (triés).
        assert calls["kill"] == [4242, 777, 778]
        st = pool.stats()
        assert st["watched"] == [] and st["run_id"] is None and st["refcount"] == 0

    def test_singleton_reset(self, monkeypatch):
        bp.reset_browser_pool()
        p1 = bp.get_browser_pool()
        assert p1 is bp.get_browser_pool()
        bp.reset_browser_pool()
        assert bp.get_browser_pool() is not p1


# ==========================================
# build_chrome_devtools_params — injection --browserUrl (F-163)
# ==========================================


class TestParamsBrowserUrl:
    def test_browser_url_ajoute_browserurl_retire_isolated(self, monkeypatch):
        monkeypatch.setenv("CHROME_DEVTOOLS_ENABLED", "1")
        monkeypatch.setenv("CHROME_PATH", "/usr/bin/chrome")
        monkeypatch.delenv("CHROME_DEVTOOLS_HEADLESS", raising=False)
        params = mcp_module.build_chrome_devtools_params(browser_url="http://127.0.0.1:39217")
        assert params is not None
        idx = params.args.index("--browserUrl")
        assert params.args[idx + 1] == "http://127.0.0.1:39217"
        assert "--isolated" not in params.args
        # --executable-path sans objet : le serveur ne lance PAS de Chrome.
        assert "--executable-path" not in params.args

    def test_sans_browser_url_comportement_historique(self, monkeypatch):
        monkeypatch.setenv("CHROME_DEVTOOLS_ENABLED", "1")
        monkeypatch.setenv("CHROME_PATH", "/usr/bin/chrome")
        monkeypatch.delenv("CHROME_DEVTOOLS_HEADLESS", raising=False)
        params = mcp_module.build_chrome_devtools_params()
        assert "--isolated" in params.args
        assert "--browserUrl" not in params.args
        assert "--executable-path" in params.args


# ==========================================
# Façade smolagents : chrome_devtools_tools
# ==========================================


class TestFacadeSmolagents:
    def test_lease_transmet_browser_url_aux_params(self, monkeypatch):
        monkeypatch.setitem(bp._OVERRIDE, "force", False)
        seen = {}

        def fake_build_params(browser_url=None):
            seen["browser_url"] = browser_url
            return None  # désactivé en aval : yield [] immédiat

        monkeypatch.setattr(chrome_devtools_tool, "_build_params", fake_build_params)
        url_box = {"url": None}

        class _FakePool:
            @contextmanager
            def lease(self, consumer="", spawn_timeout_s=30.0):
                url_box["url"] = "http://127.0.0.1:39217"
                yield "http://127.0.0.1:39217"

        monkeypatch.setattr(bp, "get_browser_pool", lambda: _FakePool())
        with chrome_devtools_tool.chrome_devtools_tools() as tools:
            assert tools == []
        assert seen["browser_url"] == "http://127.0.0.1:39217"

    def test_pool_ko_repli_historique_sans_kwargs(self, monkeypatch):
        """Lease → None : appel SANS kwargs (compat lambdas de test existantes)."""
        monkeypatch.setitem(bp._OVERRIDE, "force", False)
        seen = {}

        def fake_build_params(*args, **kwargs):
            seen["args"] = args
            seen["kwargs"] = kwargs
            return None

        monkeypatch.setattr(chrome_devtools_tool, "_build_params", fake_build_params)

        class _FakePool:
            @contextmanager
            def lease(self, consumer="", spawn_timeout_s=30.0):
                yield None

        monkeypatch.setattr(bp, "get_browser_pool", lambda: _FakePool())
        with chrome_devtools_tool.chrome_devtools_tools() as tools:
            assert tools == []
        assert seen["kwargs"] == {}

    def test_sous_pytest_pas_de_pool(self, monkeypatch):
        """_PYTEST=True (défaut sous pytest) : jamais de lease, params historiques."""
        lease_called = []

        class _FakePool:
            @contextmanager
            def lease(self, consumer="", spawn_timeout_s=30.0):
                lease_called.append(consumer)
                yield "http://x"

        monkeypatch.setattr(bp, "get_browser_pool", lambda: _FakePool())
        monkeypatch.setattr(chrome_devtools_tool, "_build_params", lambda: None)
        with chrome_devtools_tool.chrome_devtools_tools() as tools:
            assert tools == []
        assert lease_called == []


# ==========================================
# Façade pydantic : build_devtools_mcp_toolset
# ==========================================


class TestFacadePydantic:
    def test_transport_porte_browser_url(self, monkeypatch):
        from graph_orchestrator.coder_pydantic_mcp import build_devtools_mcp_toolset
        from graph_orchestrator.config import load_settings

        monkeypatch.setenv("CHROME_DEVTOOLS_ENABLED", "1")
        monkeypatch.delenv("CHROME_PATH", raising=False)
        monkeypatch.delenv("CHROME_DEVTOOLS_HEADLESS", raising=False)
        ts = build_devtools_mcp_toolset(load_settings(), browser_url="http://127.0.0.1:39217")
        assert ts is not None
        args = ts.client.transport.args
        idx = args.index("--browserUrl")
        assert args[idx + 1] == "http://127.0.0.1:39217"
        assert "--isolated" not in args

    def test_transport_historique_sans_browser_url(self, monkeypatch):
        from graph_orchestrator.coder_pydantic_mcp import build_devtools_mcp_toolset
        from graph_orchestrator.config import load_settings

        monkeypatch.setenv("CHROME_DEVTOOLS_ENABLED", "1")
        monkeypatch.delenv("CHROME_PATH", raising=False)
        monkeypatch.delenv("CHROME_DEVTOOLS_HEADLESS", raising=False)
        ts = build_devtools_mcp_toolset(load_settings())
        assert "--isolated" in ts.client.transport.args
        assert "--browserUrl" not in ts.client.transport.args


# ==========================================
# Workflow : le wrapper garantit le shutdown
# ==========================================


class TestWorkflowWrapper:
    def test_shutdown_appelle_meme_sur_exception(self, monkeypatch):
        import graph_orchestrator.workflows as wf

        shutdowns = []

        async def boom(tasks, settings):
            raise RuntimeError("crash mid-run")

        monkeypatch.setattr(wf, "_run_coding_workflow_inner", boom)
        monkeypatch.setattr(bp, "pool_should_engage", lambda settings=None: True)

        class _FakePool:
            def shutdown_run(self, reason=""):
                shutdowns.append(reason)

        monkeypatch.setattr(bp, "get_browser_pool", lambda: _FakePool())
        with pytest.raises(RuntimeError):
            asyncio.run(wf.run_coding_workflow([{"content": "x"}]))
        assert shutdowns == ["fin de workflow coding"]

    def test_pas_de_shutdown_si_pool_non_engage(self, monkeypatch):
        import graph_orchestrator.workflows as wf

        shutdowns = []

        async def ok(tasks, settings):
            return {"done": True}, []

        monkeypatch.setattr(wf, "_run_coding_workflow_inner", ok)
        monkeypatch.setattr(bp, "pool_should_engage", lambda settings=None: False)

        class _FakePool:
            def shutdown_run(self, reason=""):
                shutdowns.append(reason)

        monkeypatch.setattr(bp, "get_browser_pool", lambda: _FakePool())
        out, _ = asyncio.run(wf.run_coding_workflow([{"content": "x"}]))
        assert out == {"done": True}
        assert shutdowns == []
