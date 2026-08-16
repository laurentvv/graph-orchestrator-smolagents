"""Tests du chargement de configuration (defaults + override par env)."""

import os

from graph_orchestrator.config import _normalize_api_base, load_settings


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
    # Nettoie l'env des variables connues pour ce test. NB : depuis la migration
    # F-58 (llama.cpp dynamique / llama-server spawn), les clés LOCAL_API_BASE
    # et LOCAL_API_KEY remplacent OLLAMA_API_BASE / OLLAMA_API_KEY (backend-agnostique).
    keys = [
        "LOCAL_API_BASE", "LOCAL_API_KEY", "OLLAMA_API_BASE", "OLLAMA_API_KEY",
        "FAST_MODEL_ID", "REASONING_MODEL_ID", "REASONING_MAX_TOKENS",
        "JUDGE_CONFIDENCE_THRESHOLD", "WORKER_MAX_RETRIES", "LOG_LEVEL",
    ]
    old = {k: os.environ.pop(k, None) for k in keys}
    try:
        s = load_settings()
        # F-58 : port 8000 (llama-server spawn) remplace 11434 (Ollama natif).
        assert s.local_api_base == "http://localhost:8000/v1"
        assert s.local_api_key == "sk-local"
        assert s.fast_model_id == "Qwen3.5-9B-Q4_K_M"
        # F-58 : reasoning_model_id passé de gemma-4-E4B à Ornith-1.0-9B-MTP.
        assert s.reasoning_model_id == "hf.co/protoLabsAI/Ornith-1.0-9B-MTP-GGUF"
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
    monkeypatch.setenv("FAST_MODEL_ID", "Qwen3.5-9B-Q4_K_M")
    monkeypatch.setenv("JUDGE_CONFIDENCE_THRESHOLD", "0.85")
    monkeypatch.setenv("REASONING_MAX_TOKENS", "4096")
    monkeypatch.setenv("WORKER_MAX_RETRIES", "5")

    s = load_settings()
    assert s.fast_model_id == "Qwen3.5-9B-Q4_K_M"
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
    """TESTER_MAX_STEPS borne la durée du Web Tester (fix TIMINGS_ANALYSE + over-exploration).

    Défaut = 8 (run 2026-08-11 : à 12 puis 25 steps le Web Tester ne convergeait pas —
    le wall-clock (360s puis 600s) gagnait la course contre max_steps → timeout systématique
    sans verdict. 8 steps × ~55s pire cas (9B+DevTools) = 440s < timeout 480s, donc max_steps
    gagne : le Tester auto-final-answer au lieu de timeout. Combiné à la règle 6 « budget
    steps » du prompt web_tester.py qui force le regroupement des assertions)."""
    monkeypatch.delenv("TESTER_MAX_STEPS", raising=False)
    s = load_settings()
    assert s.tester_max_steps == 8
    # Override via env.
    monkeypatch.setenv("TESTER_MAX_STEPS", "20")
    s2 = load_settings()
    assert s2.tester_max_steps == 20


def test_turn_checkpoint_enabled_default_and_override(monkeypatch):
    """TURN_CHECKPOINT_ENABLED (F-102) : snapshot git par itération sans contamination.

    Défaut = True (opt-out). Le résumé « ce que git dit » complète le diff texte
    F-53 dès l'itération 1 ; false = retour au comportement F-53 seul."""
    monkeypatch.delenv("TURN_CHECKPOINT_ENABLED", raising=False)
    s = load_settings()
    assert s.turn_checkpoint_enabled is True
    # Override via env (opt-out).
    monkeypatch.setenv("TURN_CHECKPOINT_ENABLED", "false")
    s2 = load_settings()
    assert s2.turn_checkpoint_enabled is False
