"""LLM Retry v2 — retry transport pré-contenu (Priorité 8, F-104).

Avant ce module, AUCUN retry transport n'existait : un « Connection error »
transitoire (serveur llama-server mort sous pression VRAM, endpoint distant
en pause) remontait comme exception générique dans ``run_with_retry``
(niveau AGENT : purge mémoire + relance complète = très coûteux) ou tuait
définitivement un nœud DSPy. Ce module ajoute la couche manquante : le retry
au niveau de l'APPEL LLM, transparent pour l'agent.

Portages (plan_usine_logicielle.md P8, case F-104) :
- **openfox** (agent-loop.ts) : distinction pré-contenu vs mid-stream. Nos
  clients sont non-streamants → tout échec d'appel est « pré-contenu » : on
  retry LA MÊME requête sans rien mettre à l'historique (l'agent ne voit
  jamais l'échec, aucun step gaspillé). openfox « re-résolution du client LLM
  à chaque tentative » → callback ``between_attempts`` (revive serveur +
  client OpenAI re-créé, cf. LoggedOpenAIServerModel).
- **opencode** (session/retry.ts) : jitter 25 %, ``RETRY_MAX_RETRIES=5``,
  cap 30 s, respect prioritaire du ``retry-after`` (ms) renvoyé par le
  serveur.
- **crush** (coordinator.go) : un serveur pendu ne bloque jamais le run —
  volet init MCP bornée (cf. mcp_connect.py), ce module couvre le volet
  « serveur mort mid-run » via le revive.

Classification des erreurs (fail-fast sur le 4xx) :
- retryable : erreurs réseau/transports (ConnectionError, timeout, EOF),
  429 rate-limit, 5xx serveur, surcharge.
- fatal : 4xx de requête (401/403/404, requête invalide, contexte dépassé),
  et par défaut toute erreur inconnue — le retry d'une erreur de parsing
  n'est pas le job de cette couche (c'est celui de ``run_with_retry``).

100 % Python natif, 0 LLM, 0 dépendance (injectable ``sleep`` pour les tests).
"""

from __future__ import annotations

import random
import re
import socket
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

# Marqueurs d'erreurs FATALES (pas de retry : la même requête échouera encore).
# Ordre important : on teste le fatal AVANT le retryable (ex. « timeout »
# apparaît dans certains messages 4xx). Regex avec frontières de mots : un
# code nu ne doit PAS matcher un numéro de port au milieu d'un message.
_FATAL_RES = (
    re.compile(r"unauthorized|forbidden|permission denied|authentication", re.I),
    re.compile(r"invalid request|invalid_request_error|bad request", re.I),
    re.compile(r"api key|model_not_found|not found error|does not exist", re.I),
    re.compile(r"context length|maximum context|too long", re.I),
    re.compile(r"\b(401|403|404)\b"),
)

# Marqueurs d'erreurs RETRYABLE (transitoires : réseau, surcharge, 429/5xx).
_RETRYABLE_RES = (
    re.compile(r"connection (error|refused|reset|aborted|closed)", re.I),
    re.compile(r"econn(refused|reset|aborted|closed)", re.I),
    re.compile(r"remote end closed|broken pipe|write error|eof occurred", re.I),
    re.compile(r"timed ?out|timeout", re.I),
    re.compile(r"temporarily unavailable|overloaded|service unavailable", re.I),
    re.compile(r"rate[ _-]?limit|too many requests", re.I),
    re.compile(r"internal server error|server_error|llama server error", re.I),
    re.compile(r"\b(429|502|503|504)\b"),
)

# Types d'exception retryables par construction (avant même de lire le message).
_RETRYABLE_TYPES = (
    ConnectionError,
    ConnectionResetError,
    ConnectionAbortedError,
    ConnectionRefusedError,
    BrokenPipeError,
    TimeoutError,
    socket.timeout,
)

# Regex du délai conseillé par le serveur dans un message texte.
# Formes : "try again in 3s", "please retry in 1.5 seconds", "retry-after: 2000ms".
_RETRY_AFTER_S_RE = re.compile(
    r"(?:retry|try again)[^.;]{0,40}?\bin ([0-9]+(?:\.[0-9]+)?)\s*s", re.I
)
_RETRY_AFTER_MS_RE = re.compile(r"\b([0-9]{3,})\s*ms\b", re.I)


@dataclass(frozen=True)
class RetryPolicy:
    """Paramètres du retry transport (valeurs par défaut = portage opencode).

    - ``max_retries``      : RETRY_MAX_RETRIES=5 (opencode).
    - ``base_delay_s``     : délai du 1er retry, double à chaque tentative.
    - ``max_delay_s``      : cap absolu 30 s (opencode).
    - ``jitter_factor``    : RETRY_JITTER_FACTOR=0.25 — jitter DÉCORRÉLÉ de
      ±25 % autour du délai calculé (évite le tonnerre synchrone de retries).
    - ``honor_retry_after``: si le serveur a conseillé un délai (header ou
      message), il PRIME sur le backoff exponentiel (clampé au cap).
    """

    max_retries: int = 5
    base_delay_s: float = 1.0
    max_delay_s: float = 30.0
    jitter_factor: float = 0.25
    honor_retry_after: bool = True


def classify_llm_error(exc: BaseException) -> str:
    """Classe une exception d'appel LLM : ``"retryable"`` ou ``"fatal"``.

    Les erreurs de requête (4xx : auth, requête invalide, contexte dépassé)
    sont fatales — rejouer la même requête échouera à l'identique. Les erreurs
    transitoires (réseau, timeout, 429, 5xx, surcharge) sont retryables.
    Défaut conservateur : une erreur inconnue est FATALE (fail-fast — le
    retry de surface reste la responsabilité de ``run_with_retry``).
    """
    if isinstance(exc, _RETRYABLE_TYPES):
        # Un type réseau retryable ne devient pas fatal pour un message ambigu.
        return "retryable"
    msg = f"{type(exc).__name__}: {exc}".lower()
    if any(r.search(msg) for r in _FATAL_RES):
        return "fatal"
    if any(r.search(msg) for r in _RETRYABLE_RES):
        return "retryable"
    return "fatal"


def extract_retry_after_ms(exc: BaseException) -> Optional[int]:
    """Extrait le délai conseillé par le serveur (ms), si présent.

    Deux sources, dans l'ordre :
    1. les headers de réponse accrochés à l'exception (litellm/openai
       exposent ``exc.response.headers`` — clé ``retry-after`` ou
       ``retry-after-ms``, en secondes ou ms selon la clé) ;
    2. un message texte (« try again in 3s », « retry in 1500 ms »).
    """
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if isinstance(headers, dict) and headers:
        for key in ("retry-after-ms", "retry_after_ms"):
            raw = headers.get(key)
            if raw is not None:
                try:
                    return int(float(raw))
                except (TypeError, ValueError):
                    pass
        raw = headers.get("retry-after", headers.get("Retry-After"))
        if raw is not None:
            try:
                return int(float(raw) * 1000.0)
            except (TypeError, ValueError):
                pass
    msg = str(exc)
    m = _RETRY_AFTER_S_RE.search(msg)
    if m:
        return int(float(m.group(1)) * 1000.0)
    m = _RETRY_AFTER_MS_RE.search(msg)
    if m:
        return int(m.group(1))
    return None


def compute_delay(
    attempt: int,
    retry_after_ms: Optional[int] = None,
    policy: Optional[RetryPolicy] = None,
) -> float:
    """Délai (s) avant la tentative ``attempt+1`` (0-based ``attempt``).

    Priorité opencode : ``retry_after`` du serveur PRIME sur le backoff,
    mais clampé au cap (un serveur qui demande 10 min ne bloquera pas 10 min).
    Sinon backoff exponentiel ``base * 2**attempt`` clampé au cap, puis jitter
    décorréé ±``jitter_factor`` (le jitter reste dans [0, cap]).
    """
    p = policy or RetryPolicy()
    if p.honor_retry_after and retry_after_ms is not None and retry_after_ms > 0:
        return min(retry_after_ms / 1000.0, p.max_delay_s)
    delay = min(p.base_delay_s * (2 ** max(attempt, 0)), p.max_delay_s)
    jitter = delay * p.jitter_factor
    return min(max(delay - jitter + random.random() * 2 * jitter, 0.0), p.max_delay_s)


def with_llm_retry(
    fn: Callable[[], Any],
    policy: Optional[RetryPolicy] = None,
    on_retry: Optional[Callable[[int, float, BaseException], None]] = None,
    between_attempts: Optional[Callable[[], Any]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Exécute ``fn()`` avec retry transport PRÉ-CONTENU (openfox).

    Sémantique : nos clients LLM sont non-streamants — si l'appel échoue,
    AUCUN contenu n'a été délivré, donc rien n'entre dans l'historique de
    l'agent : on rejoue LA MÊME requête, de façon totalement transparente
    (aucun step gaspillé, aucune purge mémoire). C'est le portage direct du
    « échec avant tout contenu = retry de la même requête » d'openfox ; le
    volet mid-stream (bulle partielle + prompt de continuation unique) est
    couvert en amont par ``run_with_retry`` (nœud) — au niveau transport,
    un échec non-streamant est toujours « pré-contenu ».

    - erreur FATALE (4xx requête) → relancée immédiatement (fail-fast) ;
    - épuisement de ``max_retries`` → la DERNIÈRE exception est relancée ;
    - ``between_attempts()`` (openfox « re-résolution du client à chaque
      tentative ») est appelé avant chaque sleep : revive serveur spawné,
      re-création du client OpenAI sur la base URL courante. Best-effort :
      une exception dedans est avalée (le retry simple reste valable).

    ``on_retry(n, delay_s, exc)`` sert à l'observabilité (log).
    """
    p = policy or RetryPolicy()
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — classification ci-dessous
            kind = classify_llm_error(exc)
            if kind == "fatal" or attempt >= p.max_retries:
                raise
            delay = compute_delay(attempt, extract_retry_after_ms(exc), p)
            if on_retry is not None:
                try:
                    on_retry(attempt + 1, delay, exc)
                except Exception:
                    pass
            if between_attempts is not None:
                try:
                    between_attempts()
                except Exception:
                    pass
            sleep(delay)
            attempt += 1
