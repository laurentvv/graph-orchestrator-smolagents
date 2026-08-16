"""Tests du retry transport LLM v2 (graph_orchestrator/llm_retry.py, F-104).

Priorité 8 du plan usine logicielle : retry PRÉ-CONTENU openfox (la même
requête rejouée, rien dans l'historique) + jitter 25 %/cap 30 s/retry-after
prioritaire opencode + fail-fast sur le 4xx. SYNCHRONE, 0 réseau : le sleep
est injecté, les classifications sont unitaires.
"""

import socket
from unittest.mock import MagicMock

import pytest

from graph_orchestrator.llm_retry import (
    RetryPolicy,
    classify_llm_error,
    compute_delay,
    extract_retry_after_ms,
    with_llm_retry,
)


# ==========================================
# Classification des erreurs
# ==========================================

class TestClassifyLlmError:
    def test_connection_error_par_type(self):
        """Une ConnectionError (type réseau) est retryable même à message vide."""
        assert classify_llm_error(ConnectionRefusedError()) == "retryable"
        assert classify_llm_error(ConnectionResetError("x")) == "retryable"
        assert classify_llm_error(TimeoutError()) == "retryable"
        assert classify_llm_error(socket.timeout()) == "retryable"

    def test_connection_error_par_message(self):
        """openai/litellm lèvent souvent une Exception générique portant le texte."""
        assert classify_llm_error(Exception("Connection error.")) == "retryable"
        assert classify_llm_error(Exception("HTTPConnectionPool: Read timed out.")) == "retryable"
        assert classify_llm_error(Exception("llama server error: slot unavailable")) == "retryable"
        assert classify_llm_error(Exception("Rate limit reached (429)")) == "retryable"
        assert classify_llm_error(Exception("503 Service Unavailable")) == "retryable"
        assert classify_llm_error(Exception("server overloaded")) == "retryable"

    def test_4xx_fatal(self):
        """Les erreurs de requête ne se retryent pas : rejouer échouera pareil."""
        assert classify_llm_error(Exception("Error code: 401 - Unauthorized")) == "fatal"
        assert classify_llm_error(Exception("403 forbidden")) == "fatal"
        assert classify_llm_error(Exception("Error code: 404 - model not found")) == "fatal"
        assert classify_llm_error(Exception("invalid_request_error: bad request")) == "fatal"
        assert classify_llm_error(Exception("context length exceeded")) == "fatal"

    def test_inconnu_fatal_par_defaut(self):
        """Fail-fast conservateur : une erreur inconnue n'est PAS retryée ici
        (le retry de surface reste le job de run_with_retry)."""
        assert classify_llm_error(ValueError("n'importe quoi")) == "fatal"

    def test_code_http_ne_matche_pas_un_port(self):
        """Un numéro de port dans un message réseau ne doit pas déclencher un
        marqueur de code HTTP (frontières de mots)."""
        assert classify_llm_error(Exception("Connection error on port 5030")) == "retryable"
        assert classify_llm_error(Exception("connect ECONNREFUSED 127.0.0.1:4043")) == "retryable"

    def test_fatal_prime_sur_retryable_dans_le_message(self):
        """Un message contenant à la fois 'timeout' et 'invalid request' est fatal
        (l'ordre fatal-d'abord est significatif)."""
        assert classify_llm_error(Exception("Request timeout but also invalid request")) == "fatal"


# ==========================================
# Extraction du retry-after
# ==========================================

class TestExtractRetryAfter:
    def test_aucune_source(self):
        assert extract_retry_after_ms(Exception("rien ici")) is None

    def test_header_retry_after_ms(self):
        exc = Exception("rate limited")
        exc.response = MagicMock()
        exc.response.headers = {"retry-after-ms": "1500"}
        assert extract_retry_after_ms(exc) == 1500

    def test_header_retry_after_en_secondes(self):
        """La clé 'retry-after' s'exprime en secondes → convertie en ms."""
        exc = Exception("rate limited")
        exc.response = MagicMock()
        exc.response.headers = {"retry-after": "3"}
        assert extract_retry_after_ms(exc) == 3000

    def test_message_try_again_in(self):
        assert extract_retry_after_ms(Exception("Please try again in 2.5s")) == 2500

    def test_message_ms_explicite(self):
        assert extract_retry_after_ms(Exception("retry in 1200 ms")) == 1200


# ==========================================
# Calcul de délai
# ==========================================

class TestComputeDelay:
    def test_backoff_exponentiel_borne_au_cap(self):
        p = RetryPolicy(base_delay_s=1.0, max_delay_s=30.0, jitter_factor=0.0)
        assert compute_delay(0, None, p) == 1.0
        assert compute_delay(1, None, p) == 2.0
        assert compute_delay(2, None, p) == 4.0
        assert compute_delay(10, None, p) == 30.0  # cap opencode

    def test_retry_after_prime_mais_clampe(self):
        p = RetryPolicy(max_delay_s=30.0)
        assert compute_delay(0, 5000, p) == 5.0
        # Un serveur qui demande 10 min ne bloquera pas 10 min : clampé au cap.
        assert compute_delay(0, 600_000, p) == 30.0

    def test_jitter_dans_les_bornes(self):
        p = RetryPolicy(base_delay_s=8.0, jitter_factor=0.25)
        for _ in range(200):
            d = compute_delay(0, None, p)
            assert 6.0 <= d <= 10.0  # 8 ± 25 %

    def test_jamais_negatif_ni_au_dela_du_cap(self):
        p = RetryPolicy(base_delay_s=1.0, max_delay_s=30.0, jitter_factor=0.5)
        for attempt in range(8):
            for _ in range(50):
                d = compute_delay(attempt, None, p)
                assert 0.0 <= d <= 30.0


# ==========================================
# with_llm_retry (sémantique openfox pré-contenu)
# ==========================================

class TestWithLlmRetry:
    def _policy(self, **kw):
        return RetryPolicy(base_delay_s=0.0, max_delay_s=0.0, jitter_factor=0.0, **kw)

    def test_succes_premier_essai(self):
        calls = []
        def fn():
            calls.append(1)
            return "OK"
        assert with_llm_retry(fn, policy=self._policy()) == "OK"
        assert len(calls) == 1

    def test_retry_puis_succes_transparent(self):
        """2 échecs transitoires puis succès : le résultat passe, 3 appels."""
        state = {"n": 0}
        def fn():
            state["n"] += 1
            if state["n"] < 3:
                raise ConnectionError("transitoire")
            return "OK"
        sleeps = []
        assert with_llm_retry(fn, policy=self._policy(max_retries=5),
                              sleep=sleeps.append) == "OK"
        assert state["n"] == 3
        assert len(sleeps) == 2

    def test_fatal_fail_fast_sans_retry(self):
        state = {"n": 0}
        def fn():
            state["n"] += 1
            raise ValueError("Error code: 401 - Unauthorized")
        sleeps = []
        with pytest.raises(ValueError):
            with_llm_retry(fn, policy=self._policy(max_retries=5), sleep=sleeps.append)
        assert state["n"] == 1  # AUCUN retry sur le 4xx
        assert sleeps == []

    def test_erosion_du_budget_puis_derniere_exception(self):
        state = {"n": 0}
        def fn():
            state["n"] += 1
            raise ConnectionRefusedError("port fermé")
        with pytest.raises(ConnectionRefusedError):
            with_llm_retry(fn, policy=self._policy(max_retries=2), sleep=lambda s: None)
        assert state["n"] == 3  # 1 appel initial + 2 retries

    def test_between_attempts_et_on_retry_appelles(self):
        """openfox : re-résolution du client (between_attempts) + observabilité."""
        seen_between, seen_retry = [], []
        state = {"n": 0}
        def fn():
            state["n"] += 1
            if state["n"] == 1:
                raise ConnectionError("blip")
            return "OK"
        res = with_llm_retry(
            fn, policy=self._policy(max_retries=3),
            on_retry=lambda n, d, e: seen_retry.append((n, type(e).__name__)),
            between_attempts=lambda: seen_between.append(1),
            sleep=lambda s: None,
        )
        assert res == "OK"
        assert seen_between == [1]
        assert seen_retry == [(1, "ConnectionError")]

    def test_between_attempts_qui_leve_ne_casse_pas_le_retry(self):
        """Best-effort : un revive qui échoue n'empêche pas le retry simple."""
        state = {"n": 0}
        def fn():
            state["n"] += 1
            if state["n"] == 1:
                raise ConnectionError("blip")
            return "OK"
        def boom():
            raise RuntimeError("revive impossible")
        assert with_llm_retry(fn, policy=self._policy(), between_attempts=boom,
                              sleep=lambda s: None) == "OK"

    def test_on_retry_qui_leve_est_avale(self):
        def fn():
            raise ConnectionError("blip")
        def bad_on_retry(n, d, e):
            raise RuntimeError("log cassé")
        with pytest.raises(ConnectionError):
            with_llm_retry(fn, policy=self._policy(max_retries=0),
                           on_retry=bad_on_retry, sleep=lambda s: None)

    def test_retry_after_du_serveur_utilise_comme_delai(self):
        """Le délai conseillé par le serveur prime (clampé) — observable via sleep."""
        exc = Exception("Rate limit: please try again in 2s")
        state = {"n": 0}
        def fn():
            state["n"] += 1
            if state["n"] == 1:
                raise exc
            return "OK"
        sleeps = []
        with_llm_retry(fn, policy=RetryPolicy(base_delay_s=10.0, max_delay_s=30.0),
                       sleep=sleeps.append)
        assert sleeps == [2.0]  # 2000 ms, PAS le backoff de 10 s
