"""Tests de l'init MCP bornée (graph_orchestrator/mcp_connect.py, F-104).

Priorité 8 (crush) : un serveur MCP pendu (npx qui télécharge à froid) ne
doit JAMAIS bloquer le run — timeout PAR SERVEUR → dégradation gracieuse.
SYNCHRONE + monkeypatch du point d'entrée réseau (ToolCollection), 0 npx réel.
"""

import dataclasses
import time
from contextlib import contextmanager
from unittest.mock import MagicMock

from graph_orchestrator import chrome_devtools_tool, context7_tool, mcp_connect
from graph_orchestrator import config as config_module


def _patch_setting(monkeypatch, **kw):
    """Settings est frozen : on remplace le singleton de module par une copie.
    Les modules de prod font `from .config import settings` à l'appel → visible."""
    monkeypatch.setattr(config_module, "settings",
                        dataclasses.replace(config_module.settings, **kw))


# ==========================================
# open_mcp_with_timeout ( cœur du helper )
# ==========================================

class TestOpenMcpWithTimeout:
    def test_connexion_rapide_retourne_cm_et_outils(self, monkeypatch):
        """Connexion dans le délai → (cm, tools), CM déjà ouvert (fermable)."""
        fake_tool = MagicMock()
        fake_tool.name = "navigate_page"
        fake_collection = MagicMock()
        fake_collection.tools = [fake_tool]
        exited = []

        @contextmanager
        def fake_from_mcp(params, **kwargs):
            yield fake_collection
            exited.append(1)

        monkeypatch.setattr(mcp_connect, "ToolCollection",
                            MagicMock(from_mcp=fake_from_mcp))
        cm, tools = mcp_connect.open_mcp_with_timeout({"fake": True}, 5.0, "test")
        assert cm is not None
        assert [t.name for t in tools] == ["navigate_page"]
        # Le CM retourné est fermable par __exit__ direct.
        cm.__exit__(None, None, None)
        assert exited == [1]

    def test_timeout_retourne_none_liste_vide(self, monkeypatch):
        """Connexion qui traîne > timeout → (None, []) sans lever, rapidement."""
        @contextmanager
        def fake_from_mcp(params, **kwargs):
            time.sleep(5.0)  # un npx pendu
            yield MagicMock()

        monkeypatch.setattr(mcp_connect, "ToolCollection",
                            MagicMock(from_mcp=fake_from_mcp))
        t0 = time.monotonic()
        cm, tools = mcp_connect.open_mcp_with_timeout({"fake": True}, 0.3, "test")
        elapsed = time.monotonic() - t0
        assert cm is None
        assert tools == []
        assert elapsed < 2.0  # borné, pas 5 s

    def test_erreur_init_relevee(self, monkeypatch):
        """npx absent / Chrome introuvable : l'exception d'init est relancée
        (l'appelant gère SA dégradation)."""
        monkeypatch.setattr(
            mcp_connect, "ToolCollection",
            MagicMock(from_mcp=MagicMock(side_effect=FileNotFoundError("npx absent"))),
        )
        try:
            mcp_connect.open_mcp_with_timeout({"fake": True}, 1.0, "test")
            raised = False
        except FileNotFoundError:
            raised = True
        assert raised

    def test_exception_dans_enter_remontee(self, monkeypatch):
        """__enter__ qui lève (connexion refusée après handshake) → relancée."""
        @contextmanager
        def fake_from_mcp(params, **kwargs):
            raise ConnectionError("handshake refusé")
            yield MagicMock()  # pragma: no cover

        monkeypatch.setattr(mcp_connect, "ToolCollection",
                            MagicMock(from_mcp=fake_from_mcp))
        try:
            mcp_connect.open_mcp_with_timeout({"fake": True}, 1.0, "test")
            raised = False
        except ConnectionError:
            raised = True
        assert raised


# ==========================================
# Dégradation des modules consommateurs (timeout → yield [])
# ==========================================

class TestConsumersTimeoutDegradation:
    def test_chrome_devtools_timeout_yield_vide(self, monkeypatch):
        """chrome_devtools_tools() : init > CHROME_DEVTOOLS_CONNECT_TIMEOUT_S → []."""
        @contextmanager
        def fake_from_mcp(params, **kwargs):
            time.sleep(5.0)
            yield MagicMock()

        monkeypatch.setattr(chrome_devtools_tool, "_build_params", lambda: {"fake": True})
        monkeypatch.setattr(mcp_connect, "ToolCollection",
                            MagicMock(from_mcp=fake_from_mcp))
        _patch_setting(monkeypatch, chrome_devtools_connect_timeout_s=0.3)
        t0 = time.monotonic()
        with chrome_devtools_tool.chrome_devtools_tools() as tools:
            assert tools == []
        assert time.monotonic() - t0 < 2.0

    def test_context7_timeout_yield_vide(self, monkeypatch):
        """context7_tools() : init > CONTEXT7_CONNECT_TIMEOUT_S → []."""
        @contextmanager
        def fake_from_mcp(params, **kwargs):
            time.sleep(5.0)
            yield MagicMock()

        monkeypatch.setattr(context7_tool, "_build_params", lambda: {"fake": True})
        monkeypatch.setattr(mcp_connect, "ToolCollection",
                            MagicMock(from_mcp=fake_from_mcp))
        _patch_setting(monkeypatch, context7_connect_timeout_s=0.3)
        with context7_tool.context7_tools() as tools:
            assert tools == []

    def test_fetch_brief_timeout_retourne_vide(self, monkeypatch):
        """Le pré-fetch Architect est borné lui aussi : timeout → ''."""
        @contextmanager
        def fake_from_mcp(params, **kwargs):
            time.sleep(5.0)
            yield MagicMock()

        monkeypatch.setattr(context7_tool, "_build_params", lambda: {"fake": True})
        monkeypatch.setattr(mcp_connect, "ToolCollection",
                            MagicMock(from_mcp=fake_from_mcp))
        _patch_setting(monkeypatch, context7_connect_timeout_s=0.3)
        assert context7_tool.fetch_context7_brief("Chart.js") == ""


# ==========================================
# Configuration (timeout par serveur)
# ==========================================

class TestConfigTimeouts:
    def test_settings_defauts(self):
        from graph_orchestrator.config import load_settings
        s = load_settings()
        assert s.chrome_devtools_connect_timeout_s == 25.0
        assert s.context7_connect_timeout_s == 15.0
        assert s.puppeteer_connect_timeout_s == 25.0

    def test_settings_override_env(self, monkeypatch):
        monkeypatch.setenv("CHROME_DEVTOOLS_CONNECT_TIMEOUT_S", "7")
        from graph_orchestrator.config import load_settings
        assert load_settings().chrome_devtools_connect_timeout_s == 7.0
