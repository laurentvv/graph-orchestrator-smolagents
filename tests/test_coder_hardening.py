"""Tests des durcissements Coder post-mortem run coding_d72dc8e36445c4b6 (F-61).

3 failure modes corrigés :
1. Guard anti-`}` fermant — le modèle ferme search_replace(new_string="<JS>{...}") par
   `}}}` au lieu de `)`. La règle prompt n°8 existait mais ne suffisait pas (leçon F-33).
   Désormais le hook run_with_retry détecte le pattern dans l'exception et réinjecte un
   message spécifique + exemple correct (au lieu du générique "découpe").
2. CODER_MAX_STEPS configurable (défaut 18, avant 25 hardcoded).
3. Circuit-breaker sur idles consécutifs — _detect_idle_step (F-33) ne coupait JAMAIS,
   désormais N idles consécutifs → échec définitif propre.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from graph_orchestrator.config import load_settings
from graph_orchestrator.models import CoderOutput
from graph_orchestrator.nodes import run_with_retry


# Helpers dupliqués de test_guard.py (tests indépendants, pas d'import cross-test).
def _make_step(tool_calls=None, code_action=None, observations=None):
    """Construit un faux ActionStep smolagents."""
    return SimpleNamespace(
        tool_calls=tool_calls,
        code_action=code_action,
        observations=observations,
    )


def _make_agent_of_type(type_name, steps):
    """Crée un mock agent dont ``type(agent).__name__ == type_name``.

    Nécessaire car ``run_with_retry`` calcule ``is_code_agent = type(agent).__name__``
    == "CodeAgent"`` — ``MagicMock.__class__ = ...`` et ``spec=`` ne changent PAS
    ``type(agent)`` (seulement ``__class__``). Une vraie sous-classe dynamique est
    la seule façon fiable d'avoir ``type(agent).__name__`` correct.
    """
    klass = type(type_name, (MagicMock,), {})
    agent = klass()
    agent.name = f"{type_name.lower()}_test"
    agent.model = MagicMock(model_id="test-model")
    agent.memory = SimpleNamespace(steps=steps)
    return agent


def _make_idle_agent(name="CodeAgent"):
    """Agent dont le dernier step est idle (aucun tool call — modèle réfléchit sans agir)."""
    return _make_agent_of_type(name, [_make_step()])


# ==========================================
# Correctif 2 — CODER_MAX_STEPS configurable (défaut 18)
# ==========================================

class TestCoderMaxStepsConfig:
    def test_default_is_30(self, monkeypatch):
        """Le défaut de la dataclass est 30."""
        # Nettoie l'env pour tester le défaut réel.
        monkeypatch.delenv("CODER_MAX_STEPS", raising=False)
        s = load_settings()
        assert s.coder_max_steps == 30

    def test_env_override(self, monkeypatch):
        """CODER_MAX_STEPS=25 dans l'env → valeur lue appliquée."""
        monkeypatch.setenv("CODER_MAX_STEPS", "25")
        s = load_settings()
        assert s.coder_max_steps == 25

    def test_idle_breaker_threshold_default_3(self, monkeypatch):
        """Le défaut du breaker idle est 3 (tolère 2 ratées, coupe à la 3e)."""
        monkeypatch.delenv("IDLE_BREAKER_THRESHOLD", raising=False)
        s = load_settings()
        assert s.idle_breaker_threshold == 3


# ==========================================
# Correctif 1 — Guard anti-`}` fermant : message spécifique Règle n°8
# ==========================================

@pytest.mark.anyio
async def test_brace_closing_error_emits_rule_8_message():
    """Une exception "closing parenthesis '}' does not match" → message Règle n°8.

    Post-mortem run coding_d72dc8e36445c4b6 (failure mode n°1) : le modèle ferme
    search_replace(..., new_string="<JS>{...}") par `}` au lieu de `)`. Le hook
    détecte ce pattern précis dans le message d'exception et réinjecte un message
    SPÉCIFIQUE (Règle n°8 + exemple correct) au lieu du générique "découpe".

    Validation : le hook mute le prompt AVANT le retry. On capture cette mutation en
    interceptant la 2e invocation de agent.run (qui reçoit le prompt augmenté).
    """
    agent = _make_agent_of_type("CodeAgent", [_make_step(tool_calls=[{"name": "x"}])])

    prompts_seen = []
    attempt = {"n": 0}

    def agent_run_side_effect(prompt, **kwargs):
        # Enregistre le prompt reçu à chaque invocation de agent.run.
        prompts_seen.append(prompt)
        rr = MagicMock()
        rr.output = "invalide"
        rr.timing = MagicMock(duration=0.1)
        rr.token_usage = MagicMock(input_tokens=1, output_tokens=1)
        return rr

    agent.run = agent_run_side_effect

    async def thread_wrapper(fn, *args, **kwargs):
        attempt["n"] += 1
        if attempt["n"] == 1:
            # 1er attempt : lève l'exception pour déclencher le hook `}`.
            raise Exception("Code parsing failed: closing parenthesis '}' does not match opening '('")
        # 2e attempt : exécute agent.run (fn) avec le prompt muté.
        return fn(*args, **kwargs)

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=thread_wrapper):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
            await run_with_retry(agent, "PROMPT_INITIAL", CoderOutput, max_retries=2)

    # Le 2e attempt a reçu le prompt augmenté du message Règle n°8.
    assert len(prompts_seen) >= 1, "agent.run doit être appelé au 2e attempt"
    retry_prompt = prompts_seen[-1]
    assert "RÈGLE n°8" in retry_prompt
    assert "fermé par `}`" in retry_prompt
    assert "search_replace" in retry_prompt  # exemple correct cité
    assert "Réessaie en fermant l'appel par `)`" in retry_prompt
    # La branche `}` est prioritaire sur la branche générique.
    assert "DÉCOUPE en plus petits" not in retry_prompt


@pytest.mark.anyio
async def test_generic_syntax_error_keeps_decoupe_message():
    """Une exception de syntaxe SANS pattern `}` → message générique "découpe" conservé.

    Rétro-compat : le hook `}` est une BRANCHE SPÉCIFIQUE. Les autres erreurs de syntaxe
    (string non fermée, etc.) doivent toujours recevoir le message générique historique.
    """
    agent = _make_agent_of_type("CodeAgent", [_make_step(tool_calls=[{"name": "x"}])])

    prompts_seen = []
    attempt = {"n": 0}

    def agent_run_side_effect(prompt, **kwargs):
        prompts_seen.append(prompt)
        rr = MagicMock()
        rr.output = "invalide"
        rr.timing = MagicMock(duration=0.1)
        rr.token_usage = MagicMock(input_tokens=1, output_tokens=1)
        return rr

    agent.run = agent_run_side_effect

    async def thread_wrapper(fn, *args, **kwargs):
        attempt["n"] += 1
        if attempt["n"] == 1:
            raise Exception("SyntaxError: unterminated string literal")
        return fn(*args, **kwargs)

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=thread_wrapper):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
            await run_with_retry(agent, "PROMPT_INITIAL", CoderOutput, max_retries=2)

    retry_prompt = prompts_seen[-1]
    assert "RÈGLE n°8" not in retry_prompt  # pas de pattern `}` → pas de branche R8
    assert "DÉCOUPE en plus petits" in retry_prompt  # message générique conservé


# ==========================================
# Correctif 3 — Circuit-breaker sur idles consécutifs
# ==========================================

@pytest.mark.anyio
async def test_idle_breaker_cuts_after_threshold_consecutive_idles():
    """N idles consécutifs (seuil) → échec définitif propre, pas de retry vain.

    Post-mortem run coding_d72dc8e36445c4b6 (failure mode n°3) : _detect_idle_step
    (F-33) réinjectait un message à chaque tour idle mais ne coupait JAMAIS → le Coder
    pouvait enchaîner N runs idle jusqu'à épuisement de max_retries. Désormais le breaker
    coupe après `idle_breaker_threshold` idles consécutifs.
    """
    agent = _make_idle_agent()  # dernier step idle

    run_result = MagicMock()
    run_result.output = "invalide"  # extract_and_validate → None (jamais validé)
    run_result.timing = MagicMock(duration=0.1)
    run_result.token_usage = MagicMock(input_tokens=1, output_tokens=1)

    call_count = {"n": 0}

    async def counting_to_thread(fn, *args, **kwargs):
        call_count["n"] += 1
        # Simule un Coder qui finit son run par un step idle à CHAQUE attempt.
        # run_with_retry purge agent.memory.steps à la fin de chaque attempt, donc
        # sans ce repeuplement _detect_idle_step verrait steps=[] (→ None → branche
        # non-idle) et le breaker ne déclencherait jamais. Ici on veut N idles de suite.
        agent.memory.steps = [_make_step()]  # idle
        return run_result

    # max_retries=5 (large), threshold=3 → doit couper au 3e idle, pas au 5e retry.
    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=counting_to_thread):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
            result, metrics = await run_with_retry(
                agent, "PROMPT", CoderOutput,
                max_retries=5, idle_breaker_threshold=3,
            )

    assert result is None  # échec définitif
    assert call_count["n"] == 3, f"doit couper après 3 idles consécutifs, pas {call_count['n']}"


@pytest.mark.anyio
async def test_idle_breaker_resets_on_productive_run():
    """Un run productif (avec tool call) reset le compteur d'idles consécutifs.

    Comportement clé : le breaker ne coupe que sur des idles CONSÉCUTIFS. Si un run
    productif s'intercale, le compteur repart de 0 (le modèle est sorti de sa boucle).
    """
    # Agent dont le dernier step alterne idle/productif selon l'attempt.
    agent = _make_agent_of_type("CodeAgent", [_make_step()])  # idle au départ

    run_result = MagicMock()
    run_result.output = "invalide"
    run_result.timing = MagicMock(duration=0.1)
    run_result.token_usage = MagicMock(input_tokens=1, output_tokens=1)

    state = {"n": 0}

    async def alternating_to_thread(fn, *args, **kwargs):
        state["n"] += 1
        # Alterne : attempt 1 idle, attempt 2 productif (tool_calls), attempt 3 idle,
        # attempt 4 productif... Le breaker (threshold=3) ne doit JAMAIS déclencher car
        # jamais 3 idles de suite.
        if state["n"] % 2 == 0:
            agent.memory.steps = [_make_step(tool_calls=[{"name": "write_file"}])]  # productif
        else:
            agent.memory.steps = [_make_step()]  # idle
        return run_result

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=alternating_to_thread):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
            with patch("builtins.print") as mock_print:
                result, metrics = await run_with_retry(
                    agent, "PROMPT", CoderOutput,
                    max_retries=4, idle_breaker_threshold=3,
                )

    # Pas de coupure par breaker (jamais 3 idles consécutifs) → épuise les 4 retries.
    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "Circuit-breaker idle" not in printed
    assert state["n"] == 4  # tous les retries consommés
    assert result is None


@pytest.mark.anyio
async def test_idle_breaker_disabled_for_non_coder_nodes():
    """Les nœuds non-Coder (Judge/Synth/Adversary) reçoivent threshold=10**9 → jamais coupés.

    Rétro-compat : le breaker idle est spécifique au Coder (le seul qui écrit et boucle).
    Les nœuds de raisonnement (Judge) peuvent légitimement avoir des steps idle (longue
    réflexion). On leur passe un seuil très élevé pour préserver leur comportement.
    """
    agent = _make_idle_agent(name="ToolCallingAgent")  # Judge-like
    run_result = MagicMock()
    run_result.output = "invalide"
    run_result.timing = MagicMock(duration=0.1)
    run_result.token_usage = MagicMock(input_tokens=1, output_tokens=1)

    call_count = {"n": 0}

    async def counting_to_thread(fn, *args, **kwargs):
        call_count["n"] += 1
        return run_result

    # threshold=10**9 (comme l'appel Judge en prod) + max_retries=3 → 3 retries, pas de coupure.
    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=counting_to_thread):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
            result, metrics = await run_with_retry(
                agent, "PROMPT", CoderOutput,
                max_retries=3, idle_breaker_threshold=10**9,
            )

    assert call_count["n"] == 3  # tous les retries consommés, pas de coupure anticipée
    assert result is None


# ==========================================
# Correctif 4 — final_answer valide prioritaire sur LoopGuard (F-36)
# ==========================================

@pytest.mark.anyio
async def test_valid_final_answer_wins_over_loop_guard():
    """Un final_answer valide (CoderOutput success) doit être retourné même si le
    LoopGuard (F-36) détecte une répétition d'outil dans l'historique.

    Post-mortem run coding_d72dc8e36445c4b6 (failure mode n°4, découvert itération 3) :
    le Coder a atteint max_steps=18 en itérant légitimement (write_file/search_replace
    rejoués après relecture du fichier). Le LoopGuard a comptabilisé ces répétitions
    légitimes et a éjecté un final_answer ``{"status":"success",...}`` pourtant valide
    → verdict graphe ``failure`` (Coder crash) alors que les 3 fichiers étaient bons.

    Cause racine : ``run_with_retry`` faisait ``if loop_msg: pass`` dans le bloc
    ``if validated:``, jetant silencieusement le résultat. Désormais un validated
    réussi prime toujours sur loop_msg.
    """
    from graph_orchestrator.loop_guard import LoopGuard

    # Agent dont l'historique contient 3× le même write_file (itération de correction
    # légitime → déclenche loop_guard.repeated_action()).
    repeated_step = _make_step(code_action='write_file(path="index.html", content="x")')
    agent = _make_agent_of_type("CodeAgent", [repeated_step, repeated_step, repeated_step])

    valid_output = CoderOutput(
        task_id="ts-001", status="success",
        details="Visualiseur Bubble Sort créé.",
        linter_ok=True, vision_ok=True,
    )
    run_result = MagicMock()
    run_result.output = valid_output  # extract_and_validate le retourne tel quel (déjà un CoderOutput)
    run_result.timing = MagicMock(duration=0.1)
    run_result.token_usage = MagicMock(input_tokens=1, output_tokens=1)

    call_count = {"n": 0}

    async def counting_to_thread(fn, *args, **kwargs):
        call_count["n"] += 1
        return run_result

    guard = LoopGuard(threshold=3, enabled=True)

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=counting_to_thread):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=valid_output):
            result, metrics = await run_with_retry(
                agent, "PROMPT", CoderOutput,
                max_retries=3, loop_guard=guard,
            )

    # Le final_answer valide est retourné (pas jeté par le LoopGuard).
    assert result is valid_output, "un final_answer valide doit primer sur loop_msg"
    assert result.status == "success"
    assert call_count["n"] == 1, "succès au 1er attempt, aucun retry ne doit être consommé"
    # Le LoopGuard a bien détecté la répétition (confirme qu'on teste le bon chemin) :
    assert guard.repeated_action() is not None


# ==========================================
# Tests du fallback verdict Tester (max_steps, F-90 run 2026-08-11)
# ==========================================

class TestTesterMaxStepsFallback:
    """Le Web Tester (9B) over-exlore → max_steps → auto-final-answer en prose non
    parseable → extract_and_validate None → 3 retries gaspillés. Le fallback scanne
    le step history et dérive un verdict comportemental."""

    def test_fallback_succes_si_assertions_pass_sans_fail(self):
        """Des assertions ont tourné (PASS observé), aucun FAIL → success."""
        from graph_orchestrator.nodes import _tester_max_steps_fallback
        step = SimpleNamespace(
            observations='Script ran: {"counter": 5, "sorted": true}', error=None
        )
        r = _tester_max_steps_fallback([step], 'final_answer({"task_id": "ts-1"})')
        assert r is not None
        assert r.status == "success"
        assert r.task_id == "ts-1"

    def test_fallback_failure_si_fail_observe(self):
        """Une assertion en échec observée → failure + snippet."""
        from graph_orchestrator.nodes import _tester_max_steps_fallback
        step = SimpleNamespace(
            observations='check: fail — array not sorted', error=None
        )
        r = _tester_max_steps_fallback([step], 'final_answer({"task_id": "ts-2"})')
        assert r is not None
        assert r.status == "failure"
        assert "not sorted" in r.details
        assert r.task_id == "ts-2"

    def test_fallback_failure_si_aucun_signal(self):
        """Ni PASS ni FAIL (Tester n'a pas convergé) → failure (F-61, post-mortem 1h30) :
        ne retourne PLUS None, sinon retry complet du Tester qui re-thrash → 5 retries /
        ~43 steps / 1h30 sans verdict observés. failure est strictement meilleur
        (feedback honnête au Coder + déclenche l'itération/escalade au lieu de boucler)."""
        from graph_orchestrator.nodes import _tester_max_steps_fallback
        step = SimpleNamespace(observations="", error=None)
        r = _tester_max_steps_fallback([step], 'final_answer({"task_id": "ts-3"})')
        assert r is not None
        assert r.status == "failure"
        assert r.task_id == "ts-3"
        assert "convergé" in r.details or "max_steps" in r.details

    def test_fallback_task_id_unknown_si_absent_du_prompt(self):
        """task_id non trouvable dans le prompt → 'unknown' (ne crash pas)."""
        from graph_orchestrator.nodes import _tester_max_steps_fallback
        step = SimpleNamespace(observations='{"ok": true}', error=None)
        r = _tester_max_steps_fallback([step], "prompt sans task_id")
        assert r is not None
        assert r.task_id == "unknown"

    @pytest.mark.anyio
    async def test_fallback_active_dans_run_with_retry_node_tester(self):
        """run_with_retry(node_kind='tester') utilise le fallback quand extract_and_validate
        rend None → verdict dérivé au 1er attempt (0 retry consommé)."""
        from graph_orchestrator.models import CoderOutput
        from graph_orchestrator.nodes import run_with_retry

        # Agent dont memory.steps contient une observation PASS.
        step = SimpleNamespace(
            observations='result: {"sorted": true, "counter": 10}',
            error=None,
            model_output="",
            code_action="",
            tool_calls=None,
            is_final_answer=False,
        )
        agent = MagicMock()
        agent.memory.steps = [step]
        agent.model = None
        agent.tools = {}
        run_result = SimpleNamespace(output="prose non parseable", tokens=[])
        call_count = {"n": 0}

        async def counting_to_thread(fn, *args, **kwargs):
            call_count["n"] += 1
            return run_result

        with patch("graph_orchestrator.nodes.asyncio.to_thread", new=counting_to_thread):
            with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
                result, metrics = await run_with_retry(
                    agent, 'final_answer({"task_id": "ts-e2e"})', CoderOutput,
                    max_retries=3, node_kind="tester",
                )

        # Le fallback a produit un verdict (pas None).
        assert result is not None
        assert result.status == "success"
        assert result.task_id == "ts-e2e"
        # 1er attempt seulement (le fallback évite les retries).
        assert call_count["n"] == 1


# ==========================================
# F-111 — Coder Ultra (tiering création 4B / correction 9B no-think)
# ==========================================

class TestCoderUltra:
    """F-111/F-122 : escalade à signaux (l'exécution réelle fait foi).

    - it.1 création → fast ; it.2 (rejet qualitatif OU déterministe OU Coder
      mort) → fast (F-122 : l'Ultra trop lent pour s'activer tôt — le 4B sait
      corriger sur feedback qualitatif, run #11) ;
    - it.3 (dernière chance) → Ultra toujours ; opt-out/sans spec → fast.
    """

    def _settings(self, ultra=True, with_no_think=True):
        from types import SimpleNamespace
        fast = SimpleNamespace(model="qwen-4b.gguf", context=49152)
        no_think = SimpleNamespace(model="ornith-9b.gguf", context=49152) if with_no_think else SimpleNamespace(model="")
        return SimpleNamespace(
            fast_spec=fast, no_think_spec=no_think,
            coder_ultra_correction=ultra,
            fast_max_tokens=4000, reasoning_max_tokens=8192,
        )

    def test_creation_iteration1_fast(self):
        from graph_orchestrator.nodes import _select_coder_spec
        spec, mt, is_ultra = _select_coder_spec({"iteration": 1}, self._settings())
        assert is_ultra is False and spec.model == "qwen-4b.gguf" and mt == 4000

    def test_correction_rejet_qualitatif_reste_fast(self):
        """Run #6 : rejet qualitatif (Tester/Judge) + feedback précis → le 4B
        a su corriger. Pas d'Ultragasillage."""
        from graph_orchestrator.nodes import _select_coder_spec
        spec, _, is_ultra = _select_coder_spec(
            {"iteration": 2, "prev_deterministic_reject": False, "prev_coder_died": False},
            self._settings(),
        )
        assert is_ultra is False and spec.model == "qwen-4b.gguf"

    def test_correction_rejet_deterministe_iteration2_reste_fast(self):
        """F-122 : rejet par garde déterministe à l'itération 2 → PLUS d'Ultra
        (verdict run #8 : 3.8 t/s, mega-blocs > timeout 600 s). L'Ultra attend
        l'itération 3 — au plus UNE activation par run."""
        from graph_orchestrator.nodes import _select_coder_spec
        spec, mt, is_ultra = _select_coder_spec(
            {"iteration": 2, "prev_deterministic_reject": True},
            self._settings(),
        )
        assert is_ultra is False and spec.model == "qwen-4b.gguf" and mt == 4000

    def test_coder_mort_iteration2_reste_fast(self):
        """F-122 : Coder mort techniquement à l'itération 2 → fast (le signal
        reste calculé pour l'observabilité mais ne déclenche plus l'Ultra)."""
        from graph_orchestrator.nodes import _select_coder_spec
        spec, _, is_ultra = _select_coder_spec(
            {"iteration": 2, "prev_coder_died": True},
            self._settings(),
        )
        assert is_ultra is False

    def test_iteration3_derniere_chance_ultra(self):
        from graph_orchestrator.nodes import _select_coder_spec
        spec, _, is_ultra = _select_coder_spec(
            {"iteration": 3, "prev_deterministic_reject": False},
            self._settings(),
        )
        assert is_ultra is True

    def test_signal_deterministeseul_sans_iteration2_reste_fast(self):
        """Le signal ne vaut que POUR une correction (it. > 1) — en it. 1 il
        n'existe de toute façon pas (première passe)."""
        from graph_orchestrator.nodes import _select_coder_spec
        spec, _, is_ultra = _select_coder_spec(
            {"iteration": 1, "prev_deterministic_reject": True},
            self._settings(),
        )
        assert is_ultra is False

    def test_opt_out_desactive_ultra(self):
        from graph_orchestrator.nodes import _select_coder_spec
        spec, _, is_ultra = _select_coder_spec(
            {"iteration": 3, "prev_coder_died": True}, self._settings(ultra=False)
        )
        assert is_ultra is False and spec.model == "qwen-4b.gguf"

    def test_sans_spec_no_think_repli_fast(self):
        from graph_orchestrator.nodes import _select_coder_spec
        spec, _, is_ultra = _select_coder_spec(
            {"iteration": 3}, self._settings(with_no_think=False)
        )
        assert is_ultra is False and spec.model == "qwen-4b.gguf"
