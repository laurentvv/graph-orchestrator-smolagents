"""Tests du branchement retry sur LoggedOpenAIServerModel (F-104, P8).

Vérifie le câblage (pas la mécanique de retry, couverte par test_llm_retry.py) :
retry transparent d'un appel LLM transitoire, re-création du client entre les
tentatives (openfox), propagation du NOUVEL api_base après revive (serveur
respawné), opt-out LLM_RETRY_ENABLED=0, fail-fast 4xx. 0 réseau : __call__ du
parent est monkeypatché.

NB : Settings est une dataclass FROZEN — on remplace le singleton du module
par une copie modifiée (dataclasses.replace). Les fonctions de prod font
``from .config import settings`` À L'APPEL (pas à l'import du module
appelant), donc le remplacement d'attribut de module est bien visible.
"""

import dataclasses
from unittest.mock import MagicMock

import pytest

from smolagents import OpenAIServerModel

from graph_orchestrator import config as config_module
from graph_orchestrator.nodes import LoggedOpenAIServerModel


@pytest.fixture()
def fast_settings(monkeypatch):
    """Rend les délais de retry quasi instantanés pour les tests."""
    replacement = dataclasses.replace(
        config_module.settings,
        llm_retry_enabled=True,
        llm_retry_base_delay_s=0.0,
        llm_retry_max_delay_s=0.0,
        llm_retry_jitter=0.0,
        llm_transport_retries=5,
    )
    monkeypatch.setattr(config_module, "settings", replacement)


def _disable_retry(monkeypatch):
    replacement = dataclasses.replace(config_module.settings, llm_retry_enabled=False)
    monkeypatch.setattr(config_module, "settings", replacement)


def _make_model(revive=None):
    return LoggedOpenAIServerModel(
        model_id="test-model",
        api_base="http://127.0.0.1:9/v1",
        api_key="k",
        client_kwargs={"timeout": 5.0, "max_retries": 0},
        revive=revive,
    )


class TestLoggedModelRetryWiring:
    def test_retry_transparent_sur_connection_error(self, monkeypatch, fast_settings):
        """2 échecs transitoires puis succès : __call__ passe, 3 appels LLM,
        AUCUNE exception ne sort du modèle (l'agent ne voit rien)."""
        calls = {"n": 0}

        def fake_call(self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("llama-server down (blip VRAM)")
            res = MagicMock()
            res.token_usage = None
            return res

        monkeypatch.setattr(OpenAIServerModel, "__call__", fake_call)
        model = _make_model()
        model()  # ne lève pas
        assert calls["n"] == 3

    def test_client_recree_entre_tentatives(self, monkeypatch, fast_settings):
        """openfox « re-résolution du client à chaque tentative » : le client
        OpenAI est un objet NEUF à la tentative suivante."""
        clients_vus = []

        def fake_call(self, *args, **kwargs):
            clients_vus.append(self.client)
            if len(clients_vus) < 2:
                raise ConnectionError("pool corrompu")
            res = MagicMock()
            res.token_usage = None
            return res

        monkeypatch.setattr(OpenAIServerModel, "__call__", fake_call)
        model = _make_model()
        model()
        assert len(clients_vus) == 2
        assert clients_vus[0] is not clients_vus[1]

    def test_revive_propage_le_nouvel_api_base(self, monkeypatch, fast_settings):
        """Serveur respawné sur un NOUVEAU port : le revive retourne la nouvelle
        base, le client est re-créé dessus (client_kwargs mis à jour)."""
        revive_calls = {"n": 0}
        state = {"orig": None}

        def revive():
            revive_calls["n"] += 1
            return "http://127.0.0.1:7777/v1"

        def fake_call(self, *args, **kwargs):
            if state["orig"] is None:
                state["orig"] = self.client
                raise ConnectionError("port fermé")
            if self.client is state["orig"]:
                raise ConnectionError("encore l'ancien client")
            res = MagicMock()
            res.token_usage = None
            return res

        monkeypatch.setattr(OpenAIServerModel, "__call__", fake_call)
        model = _make_model(revive=revive)
        model()
        assert revive_calls["n"] == 1
        assert model.client_kwargs["base_url"] == "http://127.0.0.1:7777/v1"

    def test_opt_out_desactive_le_retry(self, monkeypatch):
        """LLM_RETRY_ENABLED=0 : l'exception transitoire ressort immédiatement
        (rétro-compatibilité — comportement pré-F-104)."""
        _disable_retry(monkeypatch)
        calls = {"n": 0}

        def fake_call(self, *args, **kwargs):
            calls["n"] += 1
            raise ConnectionError("down")

        monkeypatch.setattr(OpenAIServerModel, "__call__", fake_call)
        model = _make_model()
        with pytest.raises(ConnectionError):
            model()
        assert calls["n"] == 1

    def test_4xx_fail_fast_sans_retry(self, monkeypatch, fast_settings):
        calls = {"n": 0}

        def fake_call(self, *args, **kwargs):
            calls["n"] += 1
            raise ValueError("Error code: 401 - Unauthorized")

        monkeypatch.setattr(OpenAIServerModel, "__call__", fake_call)
        model = _make_model()
        with pytest.raises(ValueError):
            model()
        assert calls["n"] == 1

    def test_constructeur_accepte_revive_optionnel(self):
        """Le kwarg revive est optionnel (sites statiques sans serveur spawné)."""
        model = _make_model()
        assert model._llm_revive is None
        model2 = _make_model(revive=lambda: None)
        assert model2._llm_revive is not None
