"""Tests du chargement de configuration (defaults + override par env)."""

import importlib
import os

from graph_orchestrator.config import Settings, _normalize_api_base, load_settings


class TestNormalizeApiBase:
    """L'env OLLAMA_API_BASE (CLI Ollama natif) pointe souvent vers ...:11434 sans /v1.
    smolagents (client OpenAI) attend l'endpoint /v1 — on doit donc ajouter le suffixe."""

    def test_ajoute_v1_si_manquant(self):
        assert _normalize_api_base("http://127.0.0.1:11434") == "http://127.0.0.1:11434/v1"

    def test_garde_v1_si_deja_present(self):
        assert _normalize_api_base("http://localhost:11434/v1") == "http://localhost:11434/v1"

    def test_nettoie_slash_final(self):
        assert _normalize_api_base("http://h:11434/v1/") == "http://h:11434/v1"

    def test_sans_v1_avec_slash_final(self):
        assert _normalize_api_base("http://h:11434/") == "http://h:11434/v1"


def test_defaults_appliques():
    """Sans variable d'env, les valeurs par défaut s'appliquent."""
    # Nettoie l'env des variables connues pour ce test.
    keys = [
        "OLLAMA_API_BASE", "OLLAMA_API_KEY", "FAST_MODEL_ID",
        "REASONING_MODEL_ID", "REASONING_MAX_TOKENS",
        "JUDGE_CONFIDENCE_THRESHOLD", "WORKER_MAX_RETRIES", "LOG_LEVEL",
    ]
    old = {k: os.environ.pop(k, None) for k in keys}
    try:
        s = load_settings()
        assert s.ollama_api_base == "http://localhost:11434/v1"
        assert s.ollama_api_key == "sk-local"
        assert s.fast_model_id == "qwen3.5:2b"
        assert s.reasoning_model_id == "hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL"
        assert s.reasoning_max_tokens == 8192
        assert s.judge_confidence_threshold == 0.7
        assert s.worker_max_retries == 3
        assert s.log_level == "LOW"
    finally:
        for k, v in old.items():
            if v is not None:
                os.environ[k] = v


def test_env_override(monkeypatch):
    """Les variables d'env écrasent les defaults."""
    monkeypatch.setenv("FAST_MODEL_ID", "qwen3.5:4b")
    monkeypatch.setenv("JUDGE_CONFIDENCE_THRESHOLD", "0.85")
    monkeypatch.setenv("REASONING_MAX_TOKENS", "4096")
    monkeypatch.setenv("WORKER_MAX_RETRIES", "5")

    s = load_settings()
    assert s.fast_model_id == "qwen3.5:4b"
    assert s.judge_confidence_threshold == 0.85
    assert s.reasoning_max_tokens == 4096
    assert s.worker_max_retries == 5


def test_settings_is_frozen():
    """Settings est immuable (frozen=True) pour éviter les mutations accidentelles."""
    s = load_settings()
    import pytest
    with pytest.raises(Exception):
        s.fast_model_id = "autre"  # type: ignore


def test_tester_max_steps_default_and_override(monkeypatch):
    """TESTER_MAX_STEPS borne la durée du Web Tester (fix TIMINGS_ANALYSE). Défaut 12."""
    # Défaut = 12 (borné vs l'ancien 24 hardcoded qui laissait boucler ~30 min).
    monkeypatch.delenv("TESTER_MAX_STEPS", raising=False)
    s = load_settings()
    assert s.tester_max_steps == 12
    # Override via env.
    monkeypatch.setenv("TESTER_MAX_STEPS", "20")
    s2 = load_settings()
    assert s2.tester_max_steps == 20
