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
    fast_max_tokens: int  # obligatoire pour le Coder : un fichier HTML/CSS/JS complet
    # peut dépasser 2000 tokens ; sans max_tokens généreux, la génération est coupée
    # en plein milieu d'un tool_call JSON -> corruption du contenu du fichier.
    coder_temperature: float  # CRITIQUE pour le code : température basse (déterministe)
    # pour éviter la corruption aléatoire de la syntaxe. Le défaut serveur de qwen3.5:4b
    # est 1.0 (chat créatif) — inadapté au code. 0.2 = quasi-déterministe, idéal.

    # --- Robustesse (tolérance aux pauses d'un endpoint Ollama distant) ---
    # Timeout (secondes) d'un appel LLM. Au-delà, l'appel échoue (et peut être
    # retryé par smolagents). Sans timeout, un endpoint distant muet fige le
    # workflow indéfiniment (bug observé sur le serveur distant 10.201.12.50).
    llm_timeout_s: float

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

    # --- Reprise après crash (Priorité 3 : Checkpoints) ---
    # Si True, ignore tout checkpoint existant et repart de zéro (nouvelle exécution
    # fraîche même si le contenu de la tâche correspond à un run interrompu).
    fresh_start: bool

    # --- Boucle d'auto-correction (Priorité 2 : capture/troncature stderr) ---
    # Sans plafond, un gros traceback (500+ lignes) avalé à chaque itération fait
    # exploser le contexte du LLM ("Context Overflow") → la boucle diverge.
    # Voir graph_orchestrator/feedback_utils.py (truncate_output / truncate_history).
    test_timeout_s: int  # timeout d'un runner de tests en subprocess (pytest, etc.)
    stderr_head_lines: int  # lignes de tête à garder (l'erreur, en haut du log)
    stderr_tail_lines: int  # lignes de queue à garder (la cause racine, en bas)
    feedback_max_chars: int  # plafond global du feedback injecté au Coder

    # --- Nœud d'Escalade (Priorité 3 : post-mortem sur circuit breaker) ---
    # Quand une sous-tâche épuise le Circuit Breaker (3 itérations toutes rejetées),
    # un nœud DSPy synthétise les réfutations accumulées en un diagnostic post-mortem
    # (cause racine + leçon), le persiste dans le KG (kind="escalation"). Si False,
    # on retombe sur le comportement historique : la sous-tâche sort avec le statut
    # brut "max_iterations_reached" sans diagnostic. Opt-out utile pour A/B ou tests.
    # Valeur par défaut dans la dataclass : évite de casser les helpers de test qui
    # construisent Settings(...) à la main à chaque ajout de champ (load_settings()
    # passe toujours la vraie valeur lue depuis l'env en production).
    escalation_enabled: bool = True

    # --- Auto-Résolution des Dépendances (Priorité 5 : Tester Python) ---
    # Quand le PythonTestRunner détecte un `ModuleNotFoundError` dans le stderr, il
    # installe lui-même le package manquant (`pip install`, non-persistant) puis
    # relance les tests — au lieu de gaspiller un cycle LLM pour ça. Si False, on
    # retombe sur le comportement historique (échec immédiat, feedback au Coder).
    # Opt-out utile en environnement verrouillé (CI sans réseau, sandbox stricte).
    # Valeur par défaut dans la dataclass : même raison que escalation_enabled
    # (évite de casser les helpers de test qui construisent Settings(...) à la main).
    auto_install_deps: bool = True

    # --- Anti-Loop Cryptographique (Priorité 3 : circuit-breaker par hash) ---
    # Détecte quand un agent (Coder) répète EXACTEMENT le même tool call (même
    # outil + mêmes arguments, hashés en SHA256) plusieurs fois de suite — le
    # failure mode "tourne en rond" qui brûle des tokens sans progresser.
    # Inspiré de Crush. Si `loop_guard_threshold` répétitions sont atteintes,
    # `run_with_retry` interrompt l'agent avec un message pédagogique au lieu de
    # le laisser boucler. Seuil 3 = un humain ne refait jamais 3x le même appel
    # identique sans boucler. Opt-out utile pour A/B ou debug.
    loop_guard_enabled: bool = True
    loop_guard_threshold: int = 3

    # --- Sanitizer (Auto-typage, Priorité 8 / F-42) ---
    # Coerce best-effort les arguments d'outil malformés émis par un petit LLM
    # (ex: `"1, 80"` → `80` pour un champ integer) AVANT l'appel d'outil, pour
    # éviter les retries gaspillés sur les erreurs de validation de type.
    # Déterministe, 0 LLM. Opt-out `SANITIZER_ENABLED=0` pour A/B ou debug.
    sanitizer_enabled: bool = True

    # --- Guard bash denylist (Priorité 8-bis : robustesse runtime) ---
    # `bash_command` exécute des commandes issues du LLM via shell=True. Un guard
    # denylist bloque les commandes destructrices (rm -rf /, format, mkfs, dd vers
    # un disque, shutdown, git push --force...) AVANT le subprocess. C'est le
    # premier pas vers la robustesse runtime (la sandbox Docker complète reste un
    # chantier séparé). Opt-out utile pour les environnements de confiance.
    # Valeur par défaut True : on sécurise par défaut (fail-safe).
    bash_guard_enabled: bool = True

    # --- Nœud PromptRefiner (meta-prompt avant l'Architect) ---
    # Un nœud DSPy (gemma REASONING) reformule le prompt utilisateur brut en spec structurée
    # AVANT l'Architect, inspiré du pattern "Enhance Prompt" (Kilo Code / Cline / Roo Code).
    # Connaît le catalogue des capacités (skills + statut Context7 + testers) pour orienter la
    # spec. Si False, l'Architect reçoit le prompt brut tel quel (comportement historique).
    # Opt-out utile si la latence du nœud supplémentaire n'est pas acceptable.
    prompt_refiner_enabled: bool = True

    # --- Modèle dédié pour le PromptRefiner (optionnel) ---
    # Si vide (défaut), le PromptRefiner utilise reasoning_model_id (gemma-12B). Test réel :
    # le 12B met ~5min/prompt (overkill pour de la reformulation). Sur GPU 6 Go, le gemma-4-E4B
    # (5.2 Go, ~8× plus rapide pour qualité équivalente — voir log.md test comparatif) est un
    # bien meilleur choix. Setter PROMPT_REFINER_MODEL_ID dans .env pour cibler un modèle dédié.
    prompt_refiner_model_id: str = ""

    # --- Output daté par run (Priorité 13 : isolation des artefacts) ---
    # Racine du dossier où chaque run écrit ses fichiers générés. Le workflow coding crée un
    # sous-dossier daté `runs/YYYY-MM-DD_HHMM_slug/` et s'y chdir avant les nœuds Coder/Tester,
    # au lieu de polluer la racine du projet. Le chemin du run est persisté dans le checkpoint
    # (DuckDB) pour que la reprise après crash reprenne dans le MÊME dossier (fichiers préservés).
    # Accepte un chemin relatif (résolu en absolu au runtime) ou absolu. Défaut "runs".
    output_dir: str = "runs"

    # --- Idempotence des effets de bord (Priorité 8-bis : replays/retries) ---
    # Si True, un store d'idempotence (backing DuckDB) garantit que les effets de
    # bord non-idempotents (append_file, pip install) ne sont appliqués qu'UNE
    # FOIS par run_id — même après un replay de checkpoint (reprise après crash).
    # Inspiré de qm (idempotency-store.ts). Opt-out pour A/B/debug.
    idempotence_enabled: bool = True
    # Rétention des records d'idempotence en jours (défaut 14, aligné sur qm).
    idempotency_retention_days: int = 14


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
        fast_max_tokens=_get_int("FAST_MAX_TOKENS", 12000),
        coder_temperature=_get_float("CODER_TEMPERATURE", 0.2),
        llm_timeout_s=_get_float("LLM_TIMEOUT_S", 600.0),
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
        fresh_start=_get_bool("FRESH_START", False),
        test_timeout_s=_get_int("TEST_TIMEOUT_S", 120),
        stderr_head_lines=_get_int("STDERR_HEAD_LINES", 20),
        stderr_tail_lines=_get_int("STDERR_TAIL_LINES", 20),
        feedback_max_chars=_get_int("FEEDBACK_MAX_CHARS", 2000),
        escalation_enabled=_get_bool("ESCALATION_ENABLED", True),
        auto_install_deps=_get_bool("AUTO_INSTALL_DEPS", True),
        loop_guard_enabled=_get_bool("LOOP_GUARD_ENABLED", True),
        loop_guard_threshold=_get_int("LOOP_GUARD_THRESHOLD", 3),
        sanitizer_enabled=_get_bool("SANITIZER_ENABLED", True),
        bash_guard_enabled=_get_bool("BASH_GUARD_ENABLED", True),
        prompt_refiner_enabled=_get_bool("PROMPT_REFINER_ENABLED", True),
        prompt_refiner_model_id=_get_str("PROMPT_REFINER_MODEL_ID", ""),
        output_dir=_get_str("OUTPUT_DIR", "runs"),
        idempotence_enabled=_get_bool("IDEMPOTENCE_ENABLED", True),
        idempotency_retention_days=_get_int("IDEMPOTENCY_RETENTION_DAYS", 14),
    )


# Instance singleton chargée à l'import.
settings = load_settings()
