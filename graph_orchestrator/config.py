"""Configuration externalisée via fichier .env + valeurs par défaut.

Aucune nouvelle dépendance lourde : python-dotenv et pydantic sont déjà disponibles
(transitives de smolagents). On évite pydantic-settings pour ne pas surcharger le projet.

Usage :
    from graph_orchestrator.config import settings
    print(settings.fast_model_id)
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Charge un éventuel .env à la racine du projet, et écrase les variables d'environnement système existantes.
load_dotenv(override=True)


def _get_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    return int(raw) if raw else default


def _get_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    return float(raw) if raw else default


def _get_str(key: str, default: str) -> str:
    raw = os.getenv(key)
    return raw.strip() if raw and raw.strip() else default


def _normalize_api_base(raw: str) -> str:
    """Normalise la base de l'API OpenAI-compatible d'Ollama.

    La variable d'env OLLAMA_API_BASE est aussi utilisée par le CLI Ollama natif et
    pointe souvent vers http://127.0.0.1:11434 SANS le suffixe /v1. Or smolagents
    (client OpenAI) attend l'endpoint OpenAI-compatible, qui est sous /v1.
    Sans /v1, on obtient un 404 sur /chat/completions.
    On ajoute donc /v1 si manquant (et qu'on est sur un serveur Ollama local).
    """
    base = raw.rstrip("/")
    if not base.endswith("/v1"):
        base = base + "/v1"
    return base


@dataclass(frozen=True)
class Settings:
    """Paramètres du graphe, surchargeables par variables d'environnement."""

    # --- Connexion Ollama (endpoint OpenAI-compatible) ---
    ollama_api_base: str
    ollama_reasoning_api_base: str
    ollama_api_key: str

    # --- Tiering des modèles ---
    fast_model_id: str  # Fan-out (workers)
    reasoning_model_id: str  # Juge + Synthèse
    reasoning_max_tokens: int  # obligatoire pour Gemma (sinon finish_reason=length)

    # --- Règles métier ---
    judge_confidence_threshold: float  # seuil de qualité du juge
    worker_max_retries: int  # tentatives de parsing JSON

    # --- Vérification adversaire (§5) ---
    adversary_count: int  # nombre de sceptiques indépendants
    adversary_threshold: float  # fraction de sceptiques requise pour réfuter (>= 0.5)

    # --- Cycles de convergence (§5) ---
    max_iterations: int  # hard cap anti-boucle-infinie pour le mode exploration

    # --- Human-in-the-loop (§5) ---
    hitl_enabled: bool  # si True, checkpoint bloquant avant la synthèse
    hitl_nodes: str  # nœuds déclenchant le HITL (CSV, ex "synth") — routage stratégique

    # --- Knowledge Graph persistant (Phase 5) ---
    kg_path: str  # chemin du fichier DuckDB (ou ":memory:")

    # --- Mode de workflow ---
    workflow_mode: str  # "one_shot" (défaut) ou "exploration"

    # --- Observabilité / logs ---
    log_level: str  # verbosité des workers (LOW / MEDIUM / HIGH)


def load_settings() -> Settings:
    """Construit les settings depuis l'environnement (avec valeurs par défaut)."""
    return Settings(
        ollama_api_base=_normalize_api_base(
            _get_str("OLLAMA_API_BASE", "http://localhost:11434/v1")
        ),
        ollama_reasoning_api_base=_normalize_api_base(
            _get_str("OLLAMA_REASONING_API_BASE", _get_str("OLLAMA_API_BASE", "http://localhost:11434/v1"))
        ),
        ollama_api_key=_get_str("OLLAMA_API_KEY", "sk-local"),
        fast_model_id=_get_str("FAST_MODEL_ID", "qwen3.5:2b"),
        reasoning_model_id=_get_str(
            "REASONING_MODEL_ID",
            "hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL",
        ),
        reasoning_max_tokens=_get_int("REASONING_MAX_TOKENS", 8192),
        judge_confidence_threshold=_get_float("JUDGE_CONFIDENCE_THRESHOLD", 0.7),
        worker_max_retries=_get_int("WORKER_MAX_RETRIES", 3),
        adversary_count=_get_int("ADVERSARY_COUNT", 3),
        adversary_threshold=_get_float("ADVERSARY_THRESHOLD", 0.5),
        max_iterations=_get_int("MAX_ITERATIONS", 3),
        hitl_enabled=_get_bool("HITL_ENABLED", False),
        hitl_nodes=_get_str("HITL_NODES", "synth"),
        kg_path=_get_str("KG_PATH", "graph_orchestrator.db"),
        workflow_mode=_get_str("WORKFLOW_MODE", "one_shot"),
        log_level=_get_str("LOG_LEVEL", "LOW"),
    )


# Instance singleton chargée à l'import.
settings = load_settings()
