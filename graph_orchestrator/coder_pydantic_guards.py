"""Gardes & compaction du Coder pydantic-ai — phases 3.3-3.4 (F-159).

Portage des gardes comportementales du chemin smolagents (nodes.py run_with_retry
+ vision_callback + compaction F-116) sur les seams officiels de pydantic-ai-harness
(docs/PLAN_MIGRATION_PYDANTIC_HARNESS.md §3.3-3.4). Le profil Tester (phase 3.7)
réutilisera ces briques par configuration.

Correspondance smolagents → pydantic (volontairement explicite) :

  F-36 LoopGuard        → ``ToolGuardsCapability`` v2 : fingerprint SHA-256
                          tool+args+RÉSULTAT (vol crush), fenêtre glissante de
                          LOOP_WINDOW appels, nudges à 3 (« canonise tes args »,
                          vol deepseek) et 5 (« change d'approche »), puis
                          HARD-STOP propre à LOOP_ABORT (le nudge vient TOUJOURS
                          avant le stop — interprétation documentée de
                          « fenêtre 10 / seuil 5 / nudge [3,5,8] » du plan).
  F-88 StallDetector    → même ``ToolGuardsCapability`` : hash du livrable
                          matériel via ``stall_detector.compute_material_fingerprint``
                          (réutilisé tel quel), outils de vérification F-151
                          exemptés, seuil ``stall_detector_threshold``.
  F-61 idle breaker     → ``IdleBreakerCapability`` : réponses consécutives sans
                          AUCUN tool call → nudge puis abort propre au seuil
                          ``idle_breaker_threshold``.
  F-99 GoalEnforcer     → ``GoalGateCapability`` : preuves autoritaires disque
                          (``goal_enforcer._missing_proofs``, require_verify=False
                          comme en prod) vérifiées à la sortie ``CoderOutput`` ;
                          continuation via ``ModelRetry`` natif (couche 4 des
                          retries) — UNE continuation max, puis waive (le Judge
                          arbitre), borné pour ne pas brûler le budget retries.
  F-104 retries+revive  → ``ReviveRetryCapability`` : wrap_model_request avec
                          ``llm_retry.classify_llm_error`` (inconnu = fatal),
                          ``revive()`` llama-server entre les tentatives et
                          reconstruction du modèle si le port a changé
                          (request_context.model est le seam officiel d'échange).
  F-114/125/129/131/138 → SystemReminders DYNAMIQUES ``(RunContext) -> str|None``
                          (``build_guard_reminders``) : injection en queue derrière
                          CachePoint — ne pollue PLUS message_history (les nudges
                          smolagents s'accumulaient dans memory_step.observations),
                          préfixe cache llama-server préservé. GoalReanchor natif
                          inclus (ré-ancre le 1er user prompt, zéro LLM).
  F-116 CompactingAgent → ``build_compaction_capabilities`` : TieredCompaction
                          (ClampOversizedMessages → ClearToolResults →
                          Summarizing|SlidingWindow selon COMPACTION_LLM_ENABLED)
                          ciblé à ``compaction_preflight_budget_tokens`` (26 k),
                          DeduplicateFileReads structurel (remplace le nudge
                          F-130 par une ÉLIMINATION quasi sans perte, à chaque
                          requête), WarnNearLimits (wind-down officiel).

Écarts documentés (phases suivantes du plan) :
  - F-130 nudge relectures : remplacé par DeduplicateFileReads (choix du plan
    §3.4, « remplace le nudge par une élimination »).
  - F-125/129 (gels navigateur) : la DÉTECTION est portée génériquement sur les
    résultats d'outils (marqueurs identiques vision_callback) ; le rejeu réel
    attend les outils navigateur de la phase 3.5/3.6.
  - Purge images perte-zéro : hors périmètre tant qu'il n'y a pas d'images
    (MCP vision = phase 3.5/3.6) ; ProcessHistory sera le seam (plan §3.4).
  - Nudges multifences/r-string (F-150) : OBSOLÈTES — le moteur pydantic fait
    des tool-calls natifs, il n'y a plus de bloc Python à parser.
  - Preuve write_proof (tools.py) : seuls les custom tools déléguants la
    marquent ; le write_file du FileSystem ne la marque pas — les preuves du
    GoalGate restent correctes car AUTORITAIRES (disque pour la création,
    git-diff pour la correction), indépendantes de la mémoire du harnais.
  - Les gardes F-36/F-88 smolagents n'éjectaient JAMAIS un final_answer valide
    (post-hoc). Ici le hard-stop loop (8 répétitions) est le SEUL abort —
    un livrable déjà écrit n'est jamais détruit, l'abort est propre (le graphe
    continue vers Linter/Static Tester).

Toutes les gardes sont fail-open SAUF les aborts volontaires (GuardAbort),
attrapés proprement par run_coder_pydantic (échec de nœud, pas un crash).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from pydantic_ai.capabilities import AbstractCapability

# Imports pydantic_ai_harness différés dans les fonctions (convention
# coder_pydantic.py) ; pydantic_ai (slim) est une dépendance directe.

# --- Constantes LoopGuard v2 (plan §3.3 : fenêtre 10 / seuil 5 / nudge [3,5,8]) ---
LOOP_WINDOW = 10  # seuls les LOOP_WINDOW derniers appels comptent
LOOP_NUDGE_CANON = 3  # 3 répétitions → « canonise tes arguments » (vol deepseek)
LOOP_NUDGE_APPROACH = 5  # 5 → « CHANGE d'approche » (seuil du plan)
LOOP_ABORT = 8  # 8 → abort propre (le plan exige le nudge AVANT le hard-stop)

# Outils observationnels : répétés, ils ne sont PAS une boucle stérile (F-36 +
# exemptions F-151 étendues aux tools pydantic ; log_event est un journal).
OBSERVATIONAL_TOOLS = frozenset(
    {
        "read_file",
        "search_files",
        "find_files",
        "list_directory",
        "file_info",
        "read_python_skeleton",
        "check_js_syntax",
        "visual_check",
        "log_event",
        "check_run_state",
        "load_skill",
        # Outils navigateur (phase 3.5/3.6 — déjà exemptés par convention)
        "take_screenshot",
        "take_snapshot",
        "list_console_messages",
        "evaluate_script",
        "get_console_message",
    }
)

# Marqueurs de gel navigateur — portés à l'identique de vision_callback (F-125/129).
_BROWSER_STALL_MARKERS = (
    "timed out",
    "Not attached to an active page",
    "Navigation timeout",
)

# Échec d'édition (churn) — port du _EDIT_FAILURE_RE vision_callback.
_EDIT_FAILURE_RE = re.compile(
    r"(n'a pas été modifié|pas été modifi[ée]|refus[ée]|introuvable|"
    r"not found|no match|identiques?\s*:)",
    re.I,
)
_EDIT_SUCCESS_RE = re.compile(r"(successfully|mis à jour|updated|edited)", re.I)
_EDIT_TOOLS = frozenset({"search_replace", "multi_replace", "edit_file", "append_file"})


class GuardAbort(Exception):
    """Abort propre demandé par une garde (ex : boucle stérile établie).

    run_coder_pydantic l'attrape → échec de nœud SANS crash : le graphe
    continue (Linter/Static Tester jugent ce qui est déjà sur disque).
    """


@dataclass
class CoderGuardState:
    """État mutable partagé capacités ↔ dynamic reminders, par exécution de nœud.

    Parité lifecycle smolagents : reset au montage du nœud (before_run) ; les
    compteurs traversent les retries de sortie pydantic (un ModelRetry ne
    réinitialise PAS l'agent), comme F-114 traversait les attempts.
    """

    total_calls: int = 0
    fingerprints: dict = field(default_factory=dict)
    loop_nudge: Optional[str] = None
    stall_nudge: Optional[str] = None
    idle_nudge: Optional[str] = None
    churn_nudge: Optional[str] = None
    browser_nudge: Optional[str] = None
    # Stall F-88
    stall_count: int = 0
    prev_material_hash: Optional[str] = None
    # Churn d'édition
    churn_fail: int = 0
    # Gel navigateur F-125
    browser_stall: int = 0
    # Compteurs de preuve (GoalGate)
    verify_calls: int = 0
    goal_gate_fired: int = 0
    # Idle breaker F-61
    idle_count: int = 0

    def reset(self) -> None:
        """Réinitialisation complète (before_run / montage du nœud)."""
        self.total_calls = 0
        self.fingerprints = {}
        self.loop_nudge = None
        self.stall_nudge = None
        self.idle_nudge = None
        self.churn_nudge = None
        self.browser_nudge = None
        self.stall_count = 0
        self.prev_material_hash = None
        self.churn_fail = 0
        self.browser_stall = 0
        self.verify_calls = 0
        self.goal_gate_fired = 0
        self.idle_count = 0


def _fingerprint(tool_name: str, args: dict, result: Any) -> str:
    """Signature SHA-256 tool + args canoniques + RÉSULTAT (vol crush).

    Contrairement au F-36 smolagents (tool+args seuls), un appel répété dont le
    RÉSULTAT change (ex. list_directory après une écriture) n'est PAS une
    boucle stérile → fingerprint différent → non compté.
    """
    try:
        canonical_args = json.dumps(args, sort_keys=True, default=str)
    except Exception:  # noqa: BLE001 — args exotiques : repli textuel
        canonical_args = str(args)
    result_repr = str(result)[:4096]
    payload = (
        f"{tool_name}|{canonical_args}|"
        f"{hashlib.sha256(result_repr.encode('utf-8', 'ignore')).hexdigest()}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _result_text(result: Any) -> str:
    try:
        return result if isinstance(result, str) else str(result)
    except Exception:  # noqa: BLE001
        return ""


# ============================================================
# Capacité 1 — ToolGuards (LoopGuard v2 + StallDetector + churn + gels)
# ============================================================


class ToolGuardsCapability(AbstractCapability):
    """Combine les gardes qui observent les appels d'outils (un seul hook).

    ``after_tool_execute`` reçoit le RÉSULTAT réel — impossible en smolagents
    où les gardes F-36/F-88 scannaient la mémoire post-hoc : ici le verdict
    tombe AU MOMENT du comportement fautif.
    """

    def __init__(
        self,
        state: CoderGuardState,
        *,
        stall_threshold: int = 2,
        churn_threshold: int = 5,
        browser_stall_threshold: int = 3,
    ):
        self.id = None
        self.description = None
        self.defer_loading = False
        self._state = state
        self._stall_threshold = max(1, stall_threshold)
        self._churn_threshold = max(2, churn_threshold)
        self._browser_stall_threshold = max(1, browser_stall_threshold)

    async def before_run(self, ctx) -> None:  # noqa: ANN001
        self._state.reset()

    async def after_tool_execute(self, ctx, *, call, tool_def, args, result):  # noqa: ANN001
        try:
            self._record(call.tool_name, dict(args), result)
        except GuardAbort:
            raise  # abort volontaire, remonte jusqu'au nœud
        except Exception as exc:  # noqa: BLE001 — fail-open total
            print(f"[!] ToolGuards fail-open ({type(exc).__name__}: {exc})")
        return result

    # --- logique pure (testable sans pydantic) ---
    def _record(self, tool_name: str, args: dict, result: Any) -> None:
        from .stall_detector import (
            VISUAL_VERIFICATION_TOOLS,
            WRITE_TOOLS,
            compute_material_fingerprint,
        )

        state = self._state
        state.total_calls += 1
        text = _result_text(result)

        # Compteur de preuve verify-after (check_js_syntax ≡ VERIFY_TOOLS maison)
        if tool_name == "check_js_syntax":
            state.verify_calls += 1

        # --- Gel navigateur F-125/129 (détection générique sur le résultat) ---
        if any(marker in text for marker in _BROWSER_STALL_MARKERS):
            state.browser_stall += 1
            if "Navigation timeout" in text:  # F-129 : nudge immédiat
                state.browser_nudge = (
                    "[NAV FREEZE] Navigation timed out on a local page — the page probably "
                    "blocks loading. Do NOT retry the same URL: navigate once more, then read "
                    "list_console_messages for real errors before any screenshot."
                )
            elif state.browser_stall >= self._browser_stall_threshold:
                state.browser_nudge = (
                    f"[BROWSER STALL] {state.browser_stall} consecutive browser timeouts. "
                    "The page is frozen — do NOT repeat the same navigation. Navigate/reload "
                    "ONCE, check the console (list_console_messages), then adapt."
                )
        else:
            state.browser_stall = 0

        # --- Churn d'édition (volet nudge de F-138 ; ambigu = pas compté) ---
        if tool_name in _EDIT_TOOLS:
            if _EDIT_FAILURE_RE.search(text):
                state.churn_fail += 1
                if (
                    state.churn_fail >= self._churn_threshold
                    and state.churn_fail % self._churn_threshold == 0
                ):
                    state.churn_nudge = (
                        f"[EDIT CHURN] {state.churn_fail} consecutive edit failures. STOP "
                        "retrying the same old_string: read_file the CURRENT exact content, "
                        "then edit a smaller exact unique snippet (or rewrite the whole file)."
                    )
            elif _EDIT_SUCCESS_RE.search(text):
                state.churn_fail = 0

        # --- Stall F-88 : hash du livrable matériel ---
        if tool_name in VISUAL_VERIFICATION_TOOLS:
            state.stall_count = 0
        elif tool_name in WRITE_TOOLS:
            try:
                material = compute_material_fingerprint(tool_name, args)
            except Exception:  # noqa: BLE001
                material = None
            if material:
                if material == state.prev_material_hash:
                    state.stall_count += 1
                    if state.stall_count >= self._stall_threshold:
                        state.stall_nudge = (
                            f"[STALL DETECTOR] {state.stall_count} consecutive writes produced "
                            "IDENTICAL material. A rewrite that changes nothing cannot fix "
                            "anything — change the actual content, or verify (check_js_syntax) "
                            "and finish with final_result."
                        )
                else:
                    state.stall_count = 0
                state.prev_material_hash = material

        # --- LoopGuard v2 (fenêtre / nudges / abort) ---
        if tool_name in OBSERVATIONAL_TOOLS:
            return
        fp = _fingerprint(tool_name, args, result)
        window = state.fingerprints.get(fp)
        if window is None:
            window = deque()
            state.fingerprints[fp] = window
        window.append(state.total_calls)
        floor = state.total_calls - LOOP_WINDOW + 1
        while window and window[0] < floor:
            window.popleft()
        count = len(window)
        if count == LOOP_NUDGE_CANON:
            state.loop_nudge = (
                f"[LOOP GUARD] You called `{tool_name}` {count} times with the same arguments "
                "AND the same result. Canonicalize your arguments (stable exact values) or "
                "take a different approach."
            )
        elif count == LOOP_NUDGE_APPROACH:
            state.loop_nudge = (
                f"[LOOP GUARD] SAME `{tool_name}` call repeated {count} times — CHANGE YOUR "
                "APPROACH: different tool, smaller edits, or re-read then edit surgically. "
                "Repeating again will abort this run."
            )
        elif count >= LOOP_ABORT:
            raise GuardAbort(
                f"Loop guard: `{tool_name}` identically repeated {count} times "
                f"(window {LOOP_WINDOW}) — clean abort."
            )


# ============================================================
# Capacité 2 — Idle breaker (F-61)
# ============================================================


class IdleBreakerCapability(AbstractCapability):
    """Réponse modèle sans AUCUN tool call → nudge, puis abort propre au seuil.

    Sur smolagents ce détecteur vivait dans run_with_retry (_detect_idle_step,
    scan post-hoc) ; ici ``after_model_request`` voit la réponse AU MOMENT où
    elle arrive. La validation de sortie native (output_type) gère déjà le
    « parle sans final_result » — cette garde cible le bavardage SANS action
    répété (tour textuel qui gaspille des requêtes du budget).
    """

    def __init__(self, state: CoderGuardState, *, threshold: int = 3,
                 action_hint: Optional[str] = None):
        self.id = None
        self.description = None
        self.defer_loading = False
        self._state = state
        self._threshold = max(2, threshold)
        # F-162 (phase 3.7) : le hint d'action est paramétrable par profil —
        # le nudge Coder cite write_file/search_replace, le Tester cite
        # navigate/evaluate/final_result. Défaut None = texte Coder (rétrocompat).
        self._action_hint = action_hint

    async def before_run(self, ctx) -> None:  # noqa: ANN001
        pass  # le reset d'état est porté par ToolGuardsCapability (état partagé)

    async def after_model_request(self, ctx, *, request_context, response):  # noqa: ANN001
        try:
            from pydantic_ai.messages import ToolCallPart

            has_tool_call = any(isinstance(p, ToolCallPart) for p in response.parts)
            if has_tool_call:
                self._state.idle_count = 0
                return response
            self._state.idle_count += 1
            if self._action_hint:
                action_line = f"Act now — {self._action_hint}."
            else:
                action_line = (
                    "Act now — write_file / search_replace / check_js_syntax, or finish "
                    "with final_result."
                )
            self._state.idle_nudge = (
                f"[IDLE] Turn without any tool call (#{self._state.idle_count}). PROTOCOL "
                "rule 1: every turn MUST call at least one tool. "
                + action_line
            )
            if self._state.idle_count >= self._threshold:
                raise GuardAbort(
                    f"Idle breaker: {self._state.idle_count} consecutive turns without "
                    "any tool call — clean abort."
                )
        except GuardAbort:
            raise
        except Exception as exc:  # noqa: BLE001 — fail-open
            print(f"[!] IdleBreaker fail-open ({type(exc).__name__}: {exc})")
        return response


# ============================================================
# Capacité 3 — GoalGate (verify-after-proof F-99, continuation native)
# ============================================================


class GoalGateCapability(AbstractCapability):
    """Vérifie les PREUVES autoritaires à la sortie success du Coder.

    Preuves maison réutilisées telles quelles (goal_enforcer) : disque pour la
    création (fichiers cibles existants), git-diff/write-proof pour la
    correction. ``require_verify=False`` comme le GoalEnforcer prod (la
    vérification visuelle est arbitrée aval par le Static Tester — redondance
    assumée, cécité compaction documentée F-99).

    Continuation = ``ModelRetry`` (couche output-validation des retries
    pydantic) : le prompt de continuation part comme RetryPromptPart, le run
    continue naturellement. UNE continuation max (goal_gate_fired), puis waive
    — le Judge arbitre, et le budget retries (worker_max_retries) est préservé.
    """

    def __init__(self, state: CoderGuardState, task: dict, settings, cwd: Optional[str] = None):
        self.id = None
        self.description = None
        self.defer_loading = False
        self._state = state
        self._task = task
        self._settings = settings
        self._cwd = cwd

    async def before_run(self, ctx) -> None:  # noqa: ANN001
        pass

    async def after_output_process(self, ctx, *, output_context, output):  # noqa: ANN001
        try:
            from pydantic_ai.exceptions import ModelRetry

            from .goal_enforcer import (
                GOAL_MAX_OBJECTIVE_CHARS,
                _disk_change,
                _missing_proofs,
                goal_continuation_prompt,
            )
            from .models import CoderOutput
            from .tools import get_write_proof

            if not isinstance(output, CoderOutput) or output.status != "success":
                return output
            if not getattr(self._settings, "goal_enforcement_enabled", True):
                return output
            if self._state.goal_gate_fired >= 1:
                return output  # waive (le Judge arbitre) — parité blocked_streak

            target_files = self._task.get("target_files") or []
            if not target_files:
                return output  # rien à prouver sans cibles (parité F-99)
            iteration = int(self._task.get("iteration", 1) or 1)
            write_proof = get_write_proof()
            missing = _missing_proofs(
                write_calls=int(write_proof.get("count", 0)),
                verify_calls=self._state.verify_calls,
                target_files=target_files,
                iteration=iteration,
                is_web=True,
                cwd=self._cwd,
                require_verify=False,
                disk_change=_disk_change(self._cwd, target_files),
            )
            if not missing:
                return output
            self._state.goal_gate_fired += 1
            objective = (self._task.get("content") or "")[:GOAL_MAX_OBJECTIVE_CHARS]
            raise ModelRetry(goal_continuation_prompt(objective, missing))
        except ModelRetry:
            raise
        except Exception as exc:  # noqa: BLE001 — fail-open : ne jamais bloquer une sortie valide
            print(f"[!] GoalGate fail-open ({type(exc).__name__}: {exc})")
        return output


# ============================================================
# Capacité 4 — ReviveRetry (F-104 : transport + revive llama-server)
# ============================================================


class ReviveRetryCapability(AbstractCapability):
    """Retry transport autour de CHAQUE requête modèle + revive llama-server.

    Réutilise la classification maison (``classify_llm_error`` : fatal d'abord,
    inconnu = fatal fail-fast) et le backoff opencode (``compute_delay``).
    Entre deux tentatives : ``revive()`` du serveur spawné (sonde /health →
    stop + respawn sur un NOUVEAU port si mort) ; si l'api_base change, le
    modèle est reconstruit via ``model_factory`` et échangé sur
    ``request_context.model`` (le seam officiel — sinon le client pointerait
    sur le port mort).

    Parité F-104 : RetryPolicy était le wrapper ``__call__`` de
    LoggedOpenAIServerModel avec ``max_retries=0`` côté SDK openai ; ici
    wrap_model_request joue ce rôle au niveau run, le SDK openai sous-jacent
    reste sans retry natif. ``policy=None`` désactive (pas de retry du tout).
    """

    def __init__(
        self,
        *,
        policy: Any = None,
        revive: Optional[Callable[[], Optional[str]]] = None,
        model_factory: Optional[Callable[[str], Any]] = None,
        current_base: Optional[str] = None,
    ):
        self.id = None
        self.description = None
        self.defer_loading = False
        self._policy = policy
        self._revive = revive
        self._model_factory = model_factory
        self._current_base = current_base

    async def wrap_model_request(self, ctx, *, request_context, handler):  # noqa: ANN001
        from .llm_retry import classify_llm_error, compute_delay

        if self._policy is None:
            return await handler(request_context)

        attempt = 0
        while True:
            try:
                return await handler(request_context)
            except Exception as exc:  # noqa: BLE001 — la classification décide
                if classify_llm_error(exc) != "retryable":
                    raise  # fatal (ou contrôle de flux pydantic) : immédiat
                if attempt >= self._policy.max_retries:
                    raise
                attempt += 1
                new_base = None
                if self._revive is not None:
                    try:
                        # to_thread : un respawn bloque ~30 s (chargement GGUF) —
                        # on ne gèle pas l'event loop pendant ce temps.
                        new_base = await asyncio.to_thread(self._revive) or None
                    except Exception:  # noqa: BLE001 — revive best-effort
                        new_base = None
                if (
                    new_base
                    and self._model_factory is not None
                    and new_base != self._current_base
                ):
                    try:
                        request_context.model = self._model_factory(new_base)
                        self._current_base = new_base
                        print(f"[~] ReviveRetry : modèle reconnecté sur {new_base}")
                    except Exception:  # noqa: BLE001 — factory best-effort
                        pass
                delay = compute_delay(attempt=attempt - 1, policy=self._policy)
                print(
                    f"[~] ReviveRetry {attempt}/{self._policy.max_retries} "
                    f"({type(exc).__name__}) — retry dans {delay:.1f}s"
                )
                await asyncio.sleep(delay)


# ============================================================
# SystemReminders dynamiques (nudges — remplacement vision_callback)
# ============================================================


def build_guard_reminders(state: CoderGuardState, task: dict, settings, on_fire=None):
    """SystemReminders du profil Coder : GoalReanchor + nudges dynamiques.

    Chaque nudge est lu de l'état partagé au MOMENT de la requête (pop-once :
    un nudge part une fois, ne s'accumule pas — l'anti-thèse du comportement
    memory_step.observations qui polluait l'historique). Wind-down/checklist
    (F-131/F-114) sont DÉRIVÉS (run_step vs coder_max_steps, audit visuel
    incomplet) plutôt que comptés.
    """
    from pydantic_ai_harness import SystemReminders
    from pydantic_ai_harness.system_reminders import GoalReanchor

    max_steps = int(settings.coder_max_steps)
    wind_down_remaining = 5  # _WIND_DOWN_REMAINING vision_callback

    criteria_count = 0
    if getattr(settings, "visual_audit_enabled", True):
        criteria_count = len(
            [c for c in (task.get("visual_success_criteria") or []) if str(c).strip()]
        )

    def _pop(attr: str) -> Optional[str]:
        text = getattr(state, attr)
        setattr(state, attr, None)
        return text

    def _loop(ctx):  # noqa: ANN001
        return _pop("loop_nudge")

    def _stall(ctx):  # noqa: ANN001
        return _pop("stall_nudge")

    def _idle(ctx):  # noqa: ANN001
        return _pop("idle_nudge")

    def _churn(ctx):  # noqa: ANN001
        return _pop("churn_nudge")

    def _browser(ctx):  # noqa: ANN001
        return _pop("browser_nudge")

    def _missing_criteria() -> list:
        from .tools import get_visual_audit

        audited = set()
        for entry in get_visual_audit():
            try:
                audited.add(int(entry.get("criterion_number", 0)))
            except Exception:  # noqa: BLE001
                continue
        return sorted(set(range(1, criteria_count + 1)) - audited)

    def _checklist(ctx):  # noqa: ANN001 — F-114 : rappel checklist sur audit incomplet
        if criteria_count <= 0 or ctx.run_step < 6:
            return None
        missing = _missing_criteria()
        if not missing:
            return None
        return (
            f"[CHECKLIST] Visual criteria {missing} are NOT audited yet. Call "
            "visual_check(criterion_number=N, verdict=<honest bool>, observation=...) "
            f"for EVERY criterion (1 to {criteria_count}) before final_result."
        )

    def _wind_down(ctx):  # noqa: ANN001 — F-131 : convergence stricte en fin de budget
        if criteria_count <= 0:
            return None
        remaining = max_steps - int(ctx.run_step)
        if remaining < 1 or remaining > wind_down_remaining:
            return None
        missing = _missing_criteria()
        if not missing:
            return None
        return (
            f"[WIND-DOWN] Fewer than {wind_down_remaining + 1} requests left and the visual "
            f"checklist is incomplete ({criteria_count - len(missing)}/{criteria_count}). "
            "Converge NOW: apply the MINIMAL fix, verify with the cheapest check, record an "
            "HONEST visual_check verdict for every missing criterion (a False verdict is "
            "allowed), then call final_result IMMEDIATELY."
        )

    return SystemReminders(
        dynamic_reminders=[
            GoalReanchor(),
            _loop,
            _stall,
            _idle,
            _churn,
            _browser,
            _checklist,
            _wind_down,
        ],
        on_fire=on_fire,
    )


def build_tester_reminders(state: CoderGuardState, on_fire=None, max_requests: Optional[int] = None):
    """SystemReminders du profil Tester (F-162, phase 3.7).

    Variante de build_guard_reminders SANS les reminders Coder-spécifiques :
    pas de checklist/wind-down F-114/F-131 (portés par visual_check, outil que
    le Tester n'a pas — ses verdicts partent dans final_result.details).
    GoalReanchor + les 4 nudges d'état (loop/stall/idle/browser) restent — le
    pop-once et l'injection derrière CachePoint sont partagés.

    ``max_requests`` (leçon run 3 F-162 : verdict attendu à ~1525 s sous un
    timeout de 1800 s, 30 tours sans convergence) : ajoute un wind-down
    TESTER — à ≤6 requêtes restantes, conclure sur les preuves déjà collectées
    (verdict honnête par critère, N/A permis) et appeler final_result
    IMMÉDIATEMENT. Un verdict partiel nourrit la boucle Coder ; un timeout
    ne nourrit rien (Judge fail-closed).
    """
    from pydantic_ai_harness import SystemReminders
    from pydantic_ai_harness.system_reminders import GoalReanchor

    def _pop(attr: str) -> Optional[str]:
        text = getattr(state, attr)
        setattr(state, attr, None)
        return text

    def _wind_down(ctx):  # noqa: ANN001 — F-131 adapté au Tester
        if not max_requests:
            return None
        remaining = int(max_requests) - int(getattr(ctx, "run_step", 0))
        if remaining > 6 or remaining < 1:
            return None
        return (
            f"[WIND-DOWN] Only {remaining} request(s) left. STOP collecting evidence: "
            "give your verdict NOW from what you already observed — PASS/FAIL per "
            "criterion (honest FAIL or 'not verified' is allowed), then call "
            "final_result IMMEDIATELY. A partial verdict feeds the Coder; a timeout "
            "feeds nothing."
        )

    reminders = [
        GoalReanchor(),
        lambda ctx: _pop("loop_nudge"),
        lambda ctx: _pop("stall_nudge"),
        lambda ctx: _pop("idle_nudge"),
        lambda ctx: _pop("browser_nudge"),
    ]
    if max_requests:
        reminders.append(_wind_down)
    return SystemReminders(dynamic_reminders=reminders, on_fire=on_fire)


# ============================================================
# Compaction (F-116 → TieredCompaction officiel)
# ============================================================


def read_file_key(call) -> Optional[str]:  # noqa: ANN001 — ToolCallPart
    """file_key pour DeduplicateFileReads : lectures de fichiers par chemin.

    Couvre le read_file du FileSystem ET read_python_skeleton (même sémantique
    de lecture par chemin). Aucun défaut deviné : tout autre tool → None.
    """
    tool_name = getattr(call, "tool_name", "")
    if tool_name not in ("read_file", "read_python_skeleton"):
        return None
    try:
        args = call.args_as_dict()
    except Exception:  # noqa: BLE001
        return None
    path = args.get("path")
    return str(path) if path else None


def build_compaction_capabilities(settings, max_steps: Optional[int] = None) -> list:
    """Capabilities de compaction (§3.4) — assemblées, testables sans exécution.

    - DeduplicateFileReads STANDALONE (aucun trigger → chaque requête, quasi
      sans perte — défaut recommandé par la doc) : remplace le nudge F-130.
    - TieredCompaction ciblé à ``compaction_preflight_budget_tokens`` (26 k,
      parité preflight F-116) : Clamp (part monstre) → ClearToolResults (tier
      cheap, triggers irrelevant quand drivé) → Summarizing (si
      COMPACTION_LLM_ENABLED, opt-in comme en smolagents) sinon SlidingWindow
      (déterministe, ≡ soft reset : on garde la queue, pas d'LLM).
    - WarnNearLimits : wind-down officiel (URGENT à 70 %, CRITICAL à 3 restants)
      en complément du reminder F-131 ciblé checklist. ``max_steps`` (F-162) :
      borne du profil appelant — défaut coder_max_steps (rétrocompat Coder).
    """
    from pydantic_ai_harness import (
        ClampOversizedMessages,
        ClearToolResults,
        DeduplicateFileReads,
        SlidingWindowCompaction,
        SummarizingCompaction,
        TieredCompaction,
        WarnNearLimits,
    )

    steps = int(max_steps) if max_steps is not None else int(settings.coder_max_steps)
    last_tier = (
        SummarizingCompaction(max_messages=1, keep_messages=10)
        if getattr(settings, "compaction_llm_enabled", False)
        else SlidingWindowCompaction(max_messages=1, keep_messages=12)
    )
    return [
        DeduplicateFileReads(file_key=read_file_key),
        TieredCompaction(
            tiers=[
                ClampOversizedMessages(max_part_chars=30_000),  # ≡ LARGE_RESULT_CHAR_LIMIT
                ClearToolResults(max_tokens=1, keep_pairs=3),
                last_tier,
            ],
            target_tokens=int(settings.compaction_preflight_budget_tokens),
        ),
        WarnNearLimits(
            max_iterations=steps,
            max_context_tokens=int(settings.compaction_preflight_budget_tokens),
        ),
    ]


# ============================================================
# Assemblage final
# ============================================================


def as_capabilities(state: CoderGuardState, task: dict, settings) -> list:
    """Assemble les capacités de gardes (hors compaction/revive/reminders).

    Ordre = ordre d'enregistrement : les before_* tirent dans cet ordre, les
    after_* en ordre inverse (composition officielle des capabilities).
    """
    return [
        ToolGuardsCapability(
            state,
            stall_threshold=int(settings.stall_detector_threshold),
            churn_threshold=5,
            browser_stall_threshold=3,
        ),
        IdleBreakerCapability(state, threshold=int(settings.idle_breaker_threshold)),
        GoalGateCapability(state, task=task, settings=settings),
    ]
