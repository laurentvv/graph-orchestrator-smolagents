"""Tests du Goal Enforcer (F-99, Priorité 3-ter du plan usine logicielle).

Couverture (style test_stall_detector.py — une fonction par cas, SimpleNamespace
pour les mocks, @pytest.mark.anyio pour async, 0 LLM, 0 réseau) :

  - audit_completion : extraction de path (CodeAgent ligne / TCA dict), preuve
    manquante sans écriture, livrables sur DISQUE (état autoritaire), mode
    correction allégé (itération > 1), verify-after web exigé en création
  - prompts : continuation (discipline qm « NON PROUVÉE » + échappement
    anti-injection de l'objectif) et cap (wind-down, jamais fausse complétion)
  - GoalEnforcer : table de vérité enforce (accept/continue/waive) — complétion
    prouvée, même impasse N rounds → blocked, impasse différente reset, stalled
    rounds sans tool call → auto-waiver, cap tokens → wind-down unique,
    disabled, validations d'entrée, thread-safety du metering
  - intégration run_with_retry : continuation consomme un attempt SANS le
    RAPPEL générique mensonger, blocked-accept au 3e round (worker_max_retries=3
    ↔ GOAL_BLOCKED_MIN_ROUNDS=3), accept immédiat si prouvé, no-op sans enforcer
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from graph_orchestrator.goal_enforcer import (
    GoalAction,
    GoalEnforcer,
    audit_completion,
    goal_cap_prompt,
    goal_continuation_prompt,
)
from graph_orchestrator.models import CoderOutput


# ==========================================
# Helpers (mocks step / tool_call, pattern test_stall_detector.py)
# ==========================================

def _make_toolcall(name: str, arguments: dict) -> SimpleNamespace:
    """Mock un ToolCall smolagents (chemin ToolCallingAgent)."""
    return SimpleNamespace(name=name, arguments=arguments)


def _make_step(tool_calls=None, code_action=None) -> SimpleNamespace:
    step = SimpleNamespace()
    if tool_calls is not None:
        step.tool_calls = tool_calls
    if code_action is not None:
        step.code_action = code_action
    return step


def _make_agent(steps: list) -> MagicMock:
    agent = MagicMock()
    agent.memory = SimpleNamespace(steps=steps)
    return agent


# ==========================================
# audit_completion
# ==========================================

def test_audit_extrait_path_depuis_ligne_codeagent():
    """CodeAgent : extract_tool_calls_from_step rend (nom, ligne de code) — le
    path doit être re-extrait par regex depuis la ligne."""
    step = _make_step(code_action='resultat = write_file(path="index.html", content=r"""<html>...""")\nprint(resultat)')
    ev = audit_completion([step], target_files=["index.html"], iteration=1)
    assert ev.write_calls == 1
    assert ev.written_basenames == {"index.html"}
    assert ev.total_calls == 1


def test_audit_extrait_path_depuis_dict_tca():
    tc = _make_toolcall("search_replace", {"path": "src/app.py", "old_string": "a", "new_string": "b"})
    ev = audit_completion([_make_step(tool_calls=[tc])])
    assert ev.write_calls == 1
    assert "app.py" in ev.written_basenames


def test_audit_sans_ecriture_preuve_manquante():
    step = _make_step(code_action='print(read_file(path="index.html"))')
    ev = audit_completion([step])
    assert any("AUCUN changement matériel" in m for m in ev.missing)
    assert not ev.proven


def test_audit_livrables_sur_disque_etat_autoritaire(tmp_path):
    """Le DISQUE est l'état autoritaire (qm) : la preuve d'existence ne vient
    pas de l'historique mais du système de fichiers."""
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    step = _make_step(code_action='write_file(path="index.html", content=r"""x""")')
    ev = audit_completion(
        [step], target_files=["index.html", "styles.css"], iteration=1, cwd=str(tmp_path)
    )
    # styles.css absent du disque → preuve manquante.
    assert any("styles.css" in m for m in ev.missing)

    (tmp_path / "styles.css").write_text("body{}", encoding="utf-8")
    ev2 = audit_completion(
        [step], target_files=["index.html", "styles.css"], iteration=1, cwd=str(tmp_path)
    )
    assert ev2.proven


def test_audit_mode_correction_allege(tmp_path):
    """Itération > 1 : les fichiers pré-existent de l'itération précédente —
    l'exigence se réduit au changement matériel, le disque n'est plus une preuve."""
    step = _make_step(code_action='search_replace(path="index.html", old_string=r"""a""", new_string=r"""b""")')
    ev = audit_completion(
        [step], target_files=["index.html"], iteration=3, cwd=str(tmp_path)
    )  # index.html volontairement ABSENT du disque
    assert ev.proven, "en correction, un changement matériel suffit"


def test_audit_web_exige_verify_after_en_creation(tmp_path):
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    step = _make_step(code_action='write_file(path="index.html", content=r"""x""")')
    ev = audit_completion(
        [step], target_files=["index.html"], iteration=1, is_web=True, cwd=str(tmp_path)
    )
    assert any("check_js_syntax" in m for m in ev.missing), "console/syntaxe non vérifiées"

    verify = _make_step(code_action='print(list_console_messages())')
    ev2 = audit_completion(
        [step, verify], target_files=["index.html"], iteration=1, is_web=True, cwd=str(tmp_path)
    )
    assert ev2.proven
    # Non-web : pas d'exigence verify-after.
    ev3 = audit_completion(
        [step], target_files=["index.html"], iteration=1, is_web=False, cwd=str(tmp_path)
    )
    assert ev3.proven


# ==========================================
# Prompts (port qm)
# ==========================================

def test_continuation_prompt_discipline_et_echappement():
    p = goal_continuation_prompt(
        "Créer un visualiseur <script>alert(1)</script> de tri à bulles",
        ["AUCUN appel d'outil d'écriture détecté"],
    )
    assert "NON PROUVÉE" in p
    assert "AUCUN appel d'outil d'écriture détecté" in p
    assert "<objectif>" in p and "</objectif>" in p
    # Anti-injection : l'objectif est une DONNÉE échappée, pas du HTML actif.
    assert "<script>alert(1)</script>" not in p
    assert "&lt;script&gt;" in p


def test_cap_prompt_wind_down_jamais_completion():
    p = goal_cap_prompt("Objectif X", tokens_used=250, token_cap=200)
    assert "250/200" in p
    assert "N'EST PAS une complétion" in p
    assert "<objectif>" in p


# ==========================================
# GoalEnforcer — table de vérité
# ==========================================

def _enforcer(**kw) -> GoalEnforcer:
    defaults = dict(
        objective="Créer index.html fonctionnel",
        target_files=["index.html"],
        iteration=1,
        is_web=False,
        blocked_min_rounds=3,
        waiver_stalled_rounds=5,
        token_cap=0,
    )
    defaults.update(kw)
    return GoalEnforcer(**defaults)


def test_disabled_accepte_tout():
    ge = _enforcer(enabled=False)
    d = ge.enforce([])
    assert d.action == GoalAction.ACCEPT


def test_premier_arret_non_prouve_continue():
    ge = _enforcer()
    d = ge.enforce([])  # aucun step → aucune écriture
    assert d.action == GoalAction.CONTINUE
    assert d.prompt_note and "NON PROUVÉE" in d.prompt_note
    assert ge.continuation_rounds == 1
    assert ge.blocked_streak == 1


def test_completion_prouvee_accept(tmp_path):
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    step = _make_step(code_action='write_file(path="index.html", content=r"""x""")')
    ge = _enforcer(cwd=str(tmp_path))
    d = ge.enforce([step])
    assert d.action == GoalAction.ACCEPT
    assert ge.status == "complete"


def test_meme_impasse_3_rounds_blocked(tmp_path):
    """GOAL_BLOCKED_MIN_ROUNDS=3 : la 3e déclaration de la MÊME impasse est
    acceptée comme blocked (le résultat est conservé, le Judge arbitre)."""
    ge = _enforcer(blocked_min_rounds=3)
    d1 = ge.enforce([])
    d2 = ge.enforce([])
    d3 = ge.enforce([])
    assert d1.action == GoalAction.CONTINUE
    assert d2.action == GoalAction.CONTINUE
    assert d3.action == GoalAction.WAIVE
    assert "impasse" in d3.reason.lower() or "blocked" in d3.reason.lower()
    assert ge.status == "blocked"


def test_impasse_differente_reset_le_streak(tmp_path):
    """Une impasse DIFFÉRENTE (autre ensemble de preuves manquantes) remet le
    compteur à 1 — qm compte la MÊME impasse, pas n'importe quel échec.
    (run3 : preuve par le disque — l'écriture du fichier entre 2 rounds change
    l'impasse.)"""
    ge = _enforcer(target_files=["styles.css", "index.html"], cwd=str(tmp_path))
    # Round 1 : les 2 cibles absentes → impasse {styles.css, index.html}.
    d1 = ge.enforce([])
    assert d1.action == GoalAction.CONTINUE
    # Round 2 : styles.css créé entre-temps → impasse DIFFÉRENTE {index.html}
    # → streak reset à 1.
    (tmp_path / "styles.css").write_text("body{}", encoding="utf-8")
    d2 = ge.enforce([])
    assert d2.action == GoalAction.CONTINUE
    assert ge.blocked_streak == 1, "impasse différente → reset, pas 2"


def test_stalled_rounds_sans_tool_call_auto_waiver():
    """qm enforceGoal : N rounds de continuation sans AUCUN nouveau tool call →
    auto-waiver anti-deadlock."""
    ge = _enforcer(waiver_stalled_rounds=2)
    d1 = ge.enforce([])  # 0 tool call → stalled 1
    d2 = ge.enforce([])  # 0 tool call → stalled 2 → waive
    assert d1.action == GoalAction.CONTINUE
    assert d2.action == GoalAction.WAIVE
    assert "deadlock" in d2.reason.lower() or "anti-deadlock" in d2.reason.lower()


def test_stalled_reset_par_tool_calls():
    ge = _enforcer(waiver_stalled_rounds=2)
    ge.enforce([])  # stalled 1
    step = _make_step(code_action='write_file(path="autre.html", content=r"""x""")')
    d2 = ge.enforce([step])  # tool calls présents → stalled reset
    assert d2.action == GoalAction.CONTINUE
    assert ge.stalled_rounds == 0


def test_token_cap_wind_down_unique():
    """Cap épuisé → UN prompt de wind-down, puis l'arrêt suivant est accepté
    (« un budget épuisé n'est pas une complétion » — on ne feint pas le succès,
    le verdict passe au Judge)."""
    ge = _enforcer(token_cap=100)
    ge.record_tokens(SimpleNamespace(input_tokens=80, output_tokens=40))  # 120 ≥ 100
    d1 = ge.enforce([])
    assert d1.action == GoalAction.CONTINUE
    assert "plafond de tokens" in d1.prompt_note
    d2 = ge.enforce([])
    assert d2.action == GoalAction.WAIVE
    assert "wind-down déjà notifié" in d2.reason


def test_record_tokens_cumulatif_et_thread_safe():
    ge = _enforcer()
    errors: list[Exception] = []

    def worker():
        try:
            for _ in range(50):
                ge.record_tokens(SimpleNamespace(input_tokens=1, output_tokens=1))
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert ge.tokens_used == 10 * 50 * 2


def test_validations_entree():
    with pytest.raises(ValueError):
        GoalEnforcer(objective="   ")
    with pytest.raises(ValueError):
        _enforcer(blocked_min_rounds=0)
    with pytest.raises(ValueError):
        _enforcer(waiver_stalled_rounds=0)


def test_objectif_tronque_4000():
    ge = _enforcer(objective="x" * 10_000)
    assert len(ge.objective) == 4000


def test_evidence_accumulee_cross_attempts(tmp_path):
    """Fix run2 F-99 : la mémoire est purgée entre retries, mais un write de la
    tentative 1 reste une preuve à la tentative 3 (comptes cumulés). Mode
    correction (itération 3, pas de repo git → repli sur les writes cumulés)."""
    ge = _enforcer(iteration=3, target_files=["index.html"], cwd=str(tmp_path))
    # Tentative 1 : rien → manqué {changement matériel}.
    d1 = ge.enforce([])
    assert d1.action == GoalAction.CONTINUE
    # Tentative 2 : mémoire purgée MAIS write présent → cumul > 0 → prouvé.
    write_step = _make_step(code_action='write_file(path="index.html", content=r"""x""")')
    d2 = ge.enforce([write_step])
    assert d2.action == GoalAction.ACCEPT


def test_enforcer_preuve_par_disque_memoire_compactee(tmp_path):
    """Fix run3 F-99 : la compaction ampute memory.steps — le write exécuté
    n'y figure plus. Le DISQUE est la preuve : fichiers présents + steps
    vides = complétion PROUVÉE (le faux positif run2/run3 est éliminé)."""
    for f in ("index.html", "styles.css", "script.js"):
        (tmp_path / f).write_text("x", encoding="utf-8")
    ge = _enforcer(cwd=str(tmp_path), is_web=True)  # même sans aucun step
    d = ge.enforce([])
    assert d.action == GoalAction.ACCEPT, "le disque prime sur la mémoire compactée"


def test_enforcer_verify_after_non_bloquant(tmp_path):
    """Fix run3 : le verify-after n'est PLUS un bloqueur du GoalEnforcer —
    redondant avec les gates F-50 (screenshot obligatoire) + Static Tester,
    et aveuglé par la compaction. (audit_completion one-shot l'exige toujours.)"""
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    ge = _enforcer(cwd=str(tmp_path), is_web=True)
    d = ge.enforce([])  # aucun check_js_syntax/list_console_messages
    assert d.action == GoalAction.ACCEPT


def test_enforcer_correction_preuve_via_git(tmp_path):
    """Mode correction : une modification git NON COMMITÉE des cibles = preuve
    matérielle (source autoritaire indépendante de la mémoire)."""
    import subprocess as sp

    repo = tmp_path / "run"
    repo.mkdir()
    sp.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True, capture_output=True)
    sp.run(["git", "-C", str(repo), "-c", "user.email=t@t.t", "-c", "user.name=t",
            "commit", "-q", "--allow-empty", "-m", "init"], check=True, capture_output=True)
    (repo / "index.html").write_text("v1", encoding="utf-8")
    sp.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    sp.run(["git", "-C", str(repo), "-c", "user.email=t@t.t", "-c", "user.name=t",
            "commit", "-q", "-m", "c1"], check=True, capture_output=True)

    # Propre + aucun write cumulé → non prouvé.
    ge = _enforcer(iteration=3, cwd=str(repo))
    d1 = ge.enforce([])
    assert d1.action == GoalAction.CONTINUE

    # Modification non commitée de la cible → prouvé (même sans write en mémoire).
    (repo / "index.html").write_text("v2 corrigée", encoding="utf-8")
    ge2 = _enforcer(iteration=3, cwd=str(repo))
    d2 = ge2.enforce([])
    assert d2.action == GoalAction.ACCEPT


def test_reason_liste_les_preuves_manquantes():
    """Observabilité (fix run2) : le reason CONTINUE cite les preuves manquantes."""
    ge = _enforcer()
    d = ge.enforce([])
    assert "preuve(s) manquante(s)" in d.reason
    assert "ABSENTS du disque" in d.reason


# ==========================================
# Intégration run_with_retry
# ==========================================

def _run_result(valid_output) -> MagicMock:
    rr = MagicMock()
    rr.output = valid_output
    rr.timing = MagicMock(duration=1.0)
    rr.token_usage = MagicMock(input_tokens=10, output_tokens=5)
    return rr


@pytest.mark.anyio
async def test_run_with_retry_continuation_puis_blocked_accept():
    """3 déclarations non prouvées = exactement le budget des 3 attempts
    (worker_max_retries=3 ↔ GOAL_BLOCKED_MIN_ROUNDS=3) : les 2 premières
    consomment un attempt de continuation, la 3e est acceptée blocked."""
    from graph_orchestrator.nodes import run_with_retry

    steps = []  # le faux agent n'écrit jamais rien
    agent = _make_agent(steps)
    valid_output = CoderOutput(
        task_id="ts-001", status="success", details="ok", linter_ok=True, vision_ok=False,
    )
    rr = _run_result(valid_output)

    calls = {"n": 0}

    async def counting_to_thread(*a, **kw):
        calls["n"] += 1
        return rr

    ge = _enforcer(blocked_min_rounds=3)

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=counting_to_thread), \
         patch("graph_orchestrator.nodes.extract_and_validate", return_value=valid_output), \
         patch("builtins.print") as mock_print:
        result, _metrics = await run_with_retry(
            agent, "PROMPT", CoderOutput, max_retries=3, goal_enforcer=ge,
        )

    assert result is valid_output, "la 3e déclaration (impasse avérée) est conservée — le Judge arbitre"
    assert calls["n"] == 3, "les 2 continuations ont consommé les attempts 1 et 2"
    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "Goal enforcement" in printed
    # Le RAPPEL générique « JSON invalide » serait mensonger (le final_answer
    # ÉTAIT valide) — il ne doit PAS apparaître sur les rounds de continuation.
    assert "Nouvelle tentative" not in printed


@pytest.mark.anyio
async def test_run_with_retry_accept_immediat_si_prouve(tmp_path):
    from graph_orchestrator.nodes import run_with_retry

    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    step = _make_step(code_action='write_file(path="index.html", content=r"""x""")')
    agent = _make_agent([step])
    valid_output = CoderOutput(
        task_id="ts-001", status="success", details="ok", linter_ok=True, vision_ok=False,
    )
    rr = _run_result(valid_output)
    calls = {"n": 0}

    async def counting_to_thread(*a, **kw):
        calls["n"] += 1
        return rr

    ge = _enforcer(cwd=str(tmp_path))

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=counting_to_thread), \
         patch("graph_orchestrator.nodes.extract_and_validate", return_value=valid_output):
        result, _metrics = await run_with_retry(
            agent, "PROMPT", CoderOutput, max_retries=3, goal_enforcer=ge,
        )

    assert result is valid_output
    assert calls["n"] == 1, "complétion prouvée → succès immédiat, zéro continuation"


@pytest.mark.anyio
async def test_run_with_retry_noop_sans_enforcer():
    from graph_orchestrator.nodes import run_with_retry

    agent = _make_agent([])
    valid_output = CoderOutput(
        task_id="ts-001", status="success", details="ok", linter_ok=True, vision_ok=False,
    )
    rr = _run_result(valid_output)
    calls = {"n": 0}

    async def counting_to_thread(*a, **kw):
        calls["n"] += 1
        return rr

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=counting_to_thread), \
         patch("graph_orchestrator.nodes.extract_and_validate", return_value=valid_output):
        result, _metrics = await run_with_retry(
            agent, "PROMPT", CoderOutput, max_retries=3,
        )

    assert result is valid_output
    assert calls["n"] == 1, "sans enforcer, comportement inchangé (rétrocompat)"


@pytest.mark.anyio
async def test_run_with_retry_dernier_attempt_waive():
    """Fix run2 F-99 : une continuation sur le DERNIER attempt est convertie en
    waiver — le final_answer valide part au Judge au lieu de finir en échec
    technique (la boucle graphe max_iterations reste l'enceinte externe)."""
    from graph_orchestrator.nodes import run_with_retry

    agent = _make_agent([])
    valid_output = CoderOutput(
        task_id="ts-001", status="success", details="ok", linter_ok=True, vision_ok=False,
    )
    rr = _run_result(valid_output)
    calls = {"n": 0}

    async def counting_to_thread(*a, **kw):
        calls["n"] += 1
        return rr

    ge = _enforcer(blocked_min_rounds=3)

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=counting_to_thread), \
         patch(
             "graph_orchestrator.nodes.extract_and_validate",
             side_effect=[None, None, valid_output],  # final_answer valide SEULEMENT au 3e attempt
         ), \
         patch("builtins.print") as mock_print:
        result, _metrics = await run_with_retry(
            agent, "PROMPT", CoderOutput, max_retries=3, goal_enforcer=ge,
        )

    assert result is valid_output, "dernier attempt : waiver → résultat conservé pour le Judge"
    assert calls["n"] == 3
    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "dernier attempt" in printed
    assert "Judge arbitre" in printed
