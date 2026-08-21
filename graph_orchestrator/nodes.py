"""Nœuds du graphe : Worker (Fan-out), Judge (vérification qualitative), Synth (synthèse).

Chaque nœud :
- instancie son propre ToolCallingAgent (stateless),
- exécute avec retry automatique sur échec de parsing JSON,
- collecte les métriques (tokens/durée) via return_full_result=True.
"""

import asyncio
import json
import os
from typing import List, Optional, Tuple

from pydantic import BaseModel
from smolagents import OpenAIServerModel, ToolCallingAgent, tool

from .config import Settings
from .logging_utils import NodeMetrics, resolve_verbosity
from .models import (
    AdversaryVerdict,
    FinalSynthesis,
    JudgeOutput,
    ReduceOutput,
    TaskAssessment,
    WorkerOutput,
    CoderOutput,
    extract_and_validate,
)
from .tools import record_run_error, _RUN_ERRORS, reset_visual_audit, get_visual_audit, reset_screenshot_proof, screenshot_was_taken
from .skills_loader import (
    build_conditional_skills_block,
    enforce_skill_budget,
    ALWAYS_SKILLS_CODER,
)
from .skill_loader_tool import load_skill
from .skills_loader import load_skill_body
from .loop_guard import LoopGuard, extract_tool_calls_from_step
from .stall_detector import StallDetector, classify_turn, dominant_material_hash
from .goal_enforcer import GoalAction, GoalEnforcer
from .compaction_guards import OverflowGuard, is_context_overflow_error
from .llama_server import model_lifecycle
from .orphan_repair import repair_orphan_steps
from .sanitizer import sanitize_tools
from .prompts import build_role_header
from .llm_retry import RetryPolicy, with_llm_retry

@tool
def query_duckdb_knowledge_graph(sql_query: str) -> str:
    """Execute une requête SQL (SELECT) sur le Graphe de Connaissances (DuckDB) pour chercher d'anciens bugs, failles ou feedbacks de l'équipe IA.
    
    Schéma de la base :
    - entity(id VARCHAR, kind VARCHAR, name VARCHAR)
    - claim(id BIGINT, entity_id VARCHAR, content VARCHAR, kind VARCHAR, status VARCHAR) : contient les bugs (kind='refutation') ou le code (kind='observation')
    - provenance(claim_id BIGINT, source VARCHAR, model_id VARCHAR, run_id VARCHAR)
    
    Exemple: "SELECT content FROM claim WHERE kind = 'refutation' ORDER BY created_at DESC LIMIT 10"
    
    Args:
        sql_query: La requête SQL commençant par SELECT.
    """
    import duckdb
    from graph_orchestrator.config import settings
    if not sql_query.strip().upper().startswith("SELECT"):
        return "Erreur: Seules les requêtes SELECT sont autorisées."
        
    try:
        conn = duckdb.connect(settings.kg_path, read_only=True)
        results = conn.execute(sql_query).df()
        conn.close()
        return results.to_markdown(index=False) if not results.empty else "Aucun résultat."
    except Exception as e:
        return f"Erreur SQL: {str(e)}"

# ==========================================
# Modèles (construits une fois depuis la config)
# ==========================================

def _resolve_agent_api_base(agent_model) -> Optional[str]:
    """Résout le VRAI endpoint du modèle d'un agent (post-mortem run #8, F-113).

    ``smolagents.OpenAIServerModel`` n'expose PAS ``self.api_base`` — il range
    l'URL uniquement dans ``client_kwargs["base_url"]``. L'ancien
    ``getattr(agent_model, "api_base", None)`` rendait donc TOUJOURS None → le
    sauvetage Pydantic (``extract_and_validate``) retombait sur
    ``settings.local_api_base`` (port 8000, RIEN n'écoute en mode spawn) →
    ``Connection error`` déterministe 3/3 au run #8, serveurs dynamiques sains.
    Ordre : propriété ``api_base`` de LoggedOpenAIServerModel, puis
    ``client_kwargs["base_url"]`` en repli (modèles non-Logged).
    """
    return getattr(agent_model, "api_base", None) or (
        getattr(agent_model, "client_kwargs", None) or {}
    ).get("base_url")


class LoggedOpenAIServerModel(OpenAIServerModel):
    """OpenAIServerModel + log tokens + retry transport F-104 (P8).

    F-104 (openfox + opencode, cf. llm_retry.py) : un « Connection error »
    transitoire (llama-server mort sous pression VRAM, endpoint en pause)
    est retryé AU NIVEAU DE L'APPEL — de façon transparente pour l'agent
    (pré-contenu : rien n'entre dans l'historique, aucun step gaspillé).
    Avant, l'exception remontait jusqu'à run_with_retry qui purgeait toute
    la mémoire de l'agent pour relancer le nœud complet (très coûteux).

    ``revive`` (optionnel) : callback ``model_lifecycle.revive`` passé par
    les nœuds qui spawnent leur serveur (Coder/Tester). Si le serveur local
    est mort mid-run, il est re-spawné sur un NOUVEAU port entre deux
    tentatives, puis le client OpenAI est re-créé dessus (openfox :
    « re-résolution du client LLM à chaque tentative »).

    NB : les constructions via ce wrapper mettent ``max_retries=0`` dans
    client_kwargs — le retry interne du SDK openai est DÉSACTIVÉ pour que
    RetryPolicy (délais/jitter/cap observables) soit l'unique autorité.
    """

    def __init__(self, *args, revive=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._llm_revive = revive

    @property
    def api_base(self) -> Optional[str]:
        """Le VRAI endpoint de ce modèle (post-mortem run #8, F-113).

        ``smolagents.OpenAIServerModel`` n'assigne PAS ``self.api_base`` — il
        range l'URL uniquement dans ``client_kwargs["base_url"]``. Le sauvetage
        Pydantic (``run_with_retry`` → ``extract_and_validate``) lisait
        ``getattr(agent_model, "api_base", None)`` → None → fallback
        ``settings.local_api_base`` (port 8000, RIEN n'écoute en mode spawn)
        → ``Connection error`` déterministe 3/3 au run #8 alors que les
        serveurs dynamiques étaient sains. Cette propriété expose l'URL réelle
        (suivie par ``_between_attempts`` lors d'un revive).
        """
        return self.client_kwargs.get("base_url")

    def _between_attempts(self) -> None:
        """openfox : re-résolution du client entre deux tentatives de retry."""
        if self._llm_revive is not None:
            new_base = self._llm_revive()
            if new_base and new_base != self.client_kwargs.get("base_url"):
                self.client_kwargs["base_url"] = new_base
        # Client OpenAI re-créé : un pool de connexions pointant vers un
        # serveur mort/respawné ne doit pas empoisonner la tentative suivante.
        try:
            self.client = self.create_client()
        except Exception:
            pass

    def __call__(self, *args, **kwargs):
        from .config import settings as _settings

        if not _settings.llm_retry_enabled:
            res = super().__call__(*args, **kwargs)
        else:
            def _call():
                return super(LoggedOpenAIServerModel, self).__call__(*args, **kwargs)

            def _on_retry(n: int, delay_s: float, exc: BaseException) -> None:
                print(
                    f"\033[33m[LLM Retry F-104] tentative {n} dans {delay_s:.1f}s "
                    f"après : {type(exc).__name__}: {str(exc)[:120]}\033[0m"
                )

            res = with_llm_retry(
                _call,
                policy=RetryPolicy(
                    max_retries=_settings.llm_transport_retries,
                    base_delay_s=_settings.llm_retry_base_delay_s,
                    max_delay_s=_settings.llm_retry_max_delay_s,
                    jitter_factor=_settings.llm_retry_jitter,
                ),
                on_retry=_on_retry,
                between_attempts=self._between_attempts,
            )
        if hasattr(res, "token_usage") and res.token_usage:
            # Affichage clair du VRAI contexte envoyé au LLM
            print(f"\033[96m[LLM Local] Contexte réel de ce step : {res.token_usage.input_tokens} tokens\033[0m")
        return res

def build_fast_model(settings: Settings) -> OpenAIServerModel:
    # max_tokens généreux OBLIGATOIRE pour le Coder : un fichier HTML/CSS/JS complet
    # dépasse facilement 2000-4000 tokens. Sans budget suffisant, Ollama coupe la
    # génération en plein milieu d'un tool_call JSON (finish_reason=length) et le
    # contenu du fichier est corrompu/tronqué (cf. bug run #3 : garbage échappé).
    # NOTE : les Qwen3.5 ont un mode "thinking" qui consomme une partie du budget ;
    # on le laisse activé (aide au raisonnement tool-calling) mais le budget haut
    # garantit qu'il reste assez de tokens pour le contenu réel du fichier.
    # Timeout : sans lui, un endpoint Ollama distant muet fige le workflow.
    # Température BASSE (0.2) : CRITIQUE pour le code. Le défaut serveur de
    # qwen3.5:4b est temperature=1.0 (chat créatif) → choix de tokens aléatoires
    # qui corrompent la syntaxe HTML/JSON. Une température basse rend le Coder
    # quasi-déterministe : code cohérent, moins d'hallucinations de format.
    return LoggedOpenAIServerModel(
        model_id=settings.fast_model_id,
        api_base=settings.local_api_base,
        api_key=settings.local_api_key,
        max_tokens=settings.fast_max_tokens,
        temperature=settings.coder_temperature,
        # max_retries=0 : retry SDK openai désactivé, l'autorité = RetryPolicy F-104.
        client_kwargs={"timeout": settings.llm_timeout_s, "max_retries": 0},
    )


def build_reasoning_model(settings: Settings) -> OpenAIServerModel:
    # max_tokens généreux obligatoire pour Gemma : sans ça, Ollama renvoie
    # finish_reason=length sans tool_calls (le raisonnement interne consomme tout).
    return LoggedOpenAIServerModel(
        model_id=settings.reasoning_model_id,
        api_base=settings.local_reasoning_api_base,
        api_key=settings.local_api_key,
        max_tokens=settings.reasoning_max_tokens,
        # max_retries=0 : retry SDK openai désactivé, l'autorité = RetryPolicy F-104.
        client_kwargs={"timeout": settings.llm_timeout_s, "max_retries": 0},
    )


# ==========================================
# Retry + métriques
# ==========================================

def _detect_idle_step(agent, node_kind: str = "coder") -> Optional[str]:
    """F-33 (guard logiciel) : détecte un tour SANS tool call exécuté (modèle réfléchit sans agir).

    Inspecte le dernier step de agent.memory.steps. Si ce step n'a produit AUCUN appel
    d'outil (uniquement du text/reasoning), c'est le failure mode "reasoning-action dilemma"
    observé sur gemma (le modèle dit "I will start by generating the CSS" mais n'émet
    jamais l'appel). On renvoie un message pédagogique à ré-injecter (style openfox
    FORMAT_CORRECTION_PROMPT) ; sinon None.

    Un ActionStep smolagents est "productif" s'il a : tool_calls (TCA), code_action
    (CodeAgent), ou des observations (résultat d'outil). Un step "idle" = aucun des 3.

    ``node_kind`` adapte le message au contexte : le Coder parle de write_file/search_replace,
    le Tester de puppeteer_evaluate/puppeteer_navigate (fix TIMINGS_ANALYSE — le Tester
    souffrait du "does not contain any JSON blob", modèle thinking sans tool call, car le
    guard était codé en dur avec les outils du Coder et n'existait qu'à l'intérieur de
    run_with_retry sans différenciation).
    """
    try:
        steps = getattr(getattr(agent, "memory", None), "steps", None)
        if not steps:
            return None
        last = steps[-1]
        # Champs réels d'un ActionStep smolagents (dataclass) :
        # tool_calls (TCA) | code_action (CodeAgent) | observations (résultat d'outil).
        has_tool_use = (
            bool(getattr(last, "tool_calls", None))
            or bool(getattr(last, "code_action", None))
            or bool(getattr(last, "observations", None))
        )
        if not has_tool_use:
            if node_kind == "tester":
                return (
                    "ATTENTION : ta dernière réponse ne contenait AUCUN appel d'outil exécuté "
                    "(tu as réfléchi sans agir). Tu DOIS appeler un outil Puppeteer "
                    "(puppeteer_navigate, puppeteer_screenshot, puppeteer_evaluate, "
                    "puppeteer_click, puppeteer_fill) ou final_answer dans ton prochain tour. "
                    "Si tu penses à un script JS à exécuter, utilise DIRECTEMENT "
                    "puppeteer_evaluate au lieu de le décrire en texte. Une réponse sans "
                    "action est un ÉCHEC."
                )
            return (
                "ATTENTION : ta dernière réponse ne contenait AUCUN appel d'outil exécuté "
                "(tu as réfléchi sans agir). Tu DOIS appeler un outil (write_file, append_file, "
                "search_replace) ou final_answer dans ton prochain bloc de code. Une réponse "
                "sans action est un ÉCHEC."
            )
    except Exception:
        pass
    return None


# Marqueurs de FAIL dans les observations du Tester (retours evaluate_script).
# Indicateurs qu'une assertion fonctionnelle a ÉCHOUÉ ou qu'une exception est apparue.
_TESTER_FAIL_MARKERS = (
    ": fail", "fail:", "failed", '"fail"', "'fail'", "[fail]",
    "uncaught", "typeerror", "referenceerror", "syntaxerror",
    "est faux", "incorrect", "non passé", "pas trié", "assertion failed",
)
# Marqueurs de succès explicite (assertion passée). Présence = le test a tourné et réussi.
_TESTER_PASS_MARKERS = (
    '"pass"', "'pass'", ": pass", "pass:", "[pass]", "status: pass", "verdict: pass",
    "assertion passed", "test passed", "succès", "valide ✓",
)
# F-127 (post-mortem run 2026-08-19_2104) : signatures d'échecs des OUTILS du Tester
# lui-même — ≠ bug de l'app testée. Les 2 rejets fantômes du run venaient de lignes
# de ce type matchées par _TESTER_FAIL_MARKERS ("typeerror", "failed"...) alors que
# le livrable était sain (0 erreur console) :
#  - le probe interroge un ID DOM inexistant → "Error: Cannot read properties of null"
#  - appel MCP invalide (enum types) → "MCP error -32602: ... Invalid enum value"
#  - le code Python du Tester → NameError/InterpreterError/Forbidden (sandbox)
# Ces lignes sont EXCLUES du scan FAIL (une vraie erreur d'app se voit dans les
# entrées console "[error] Uncaught ..." ou les verdicts FAIL explicites, qui restent
# couverts par les marqueurs ci-dessus).
_TESTER_TOOL_ERROR_MARKERS = (
    "mcp error", "nameerror", "interpretererror", "forbidden access",
    "forbidden function", "is not defined", "code parsing failed",
    "invalid enum value", "error in generating model output", "access denied",
)


def _visual_checklist_error(criteria_count):
    """F-109 : évalue l'audit visuel matérialisé (outils ``visual_check``).

    Post-mortem run #5 : le 4B déclarait « all 6 criteria verified » sans RIEN
    écrire, puis le Tester trouvait un crash. L'audit doit être MATÉRIALISÉ
    par un appel visual_check par critère (verdict + observation factuelle).
    Retourne un message bloquant si checklist incomplète / verdict False /
    observations creuses, sinon None.
    """
    from .tools import get_visual_audit
    audit = get_visual_audit()
    audited = {a.get("criterion_number") for a in audit}
    missing = sorted(set(range(1, criteria_count + 1)) - audited)
    if missing:
        return (
            "ERREUR FATALE: checklist visuelle INCOMPLÈTE — critère(s) non audité(s) : "
            + str(missing)
            + ". Tu dois appeler visual_check(criterion_number=i, verdict=True|False, "
              "observation=\"ce que tu vois\") pour CHAQUE critère (1 à " + str(criteria_count)
            + ") APRÈS le screenshot, puis final_answer. Une déclaration globale ne suffit plus."
        )
    failed = sorted({a.get("criterion_number") for a in audit if not a.get("verdict")})
    if failed:
        return (
            "ERREUR FATALE: critère(s) visuel(s) en ÉCHEC (verdict=False) : " + str(failed)
            + ". Corrige le code via search_replace, re-navigue, re-capture "
              "(take_screenshot), puis ré-audite ces critères avec visual_check AVANT final_answer."
        )
    weak = sorted({a.get("criterion_number") for a in audit
                   if len(str(a.get("observation", ""))) < 10})
    if weak:
        return (
            "ERREUR FATALE: observation(s) vide(s) ou trop courte(s) pour les critères "
            + str(weak)
            + " — décris ce que tu VOIS concrètement sur la capture "
              "(ex: \"30 barres grises visibles dans le canvas\"), pas une généralité."
        )
    return None



def _select_coder_spec(task: dict, settings) -> tuple:
    """F-111 : escalade à signaux du Coder — l'exécution réelle fait foi.

    Échelle (calée sur les preuves des runs #6/#7, resserrée F-122) :
      - itérations 1-2 → fast 4B (création : convergence 12-13 steps runs
        #6/#10 ; correction : le 4B SAIT corriger sur un feedback qualitatif
        précis — prouvé run #11) ;
      - itération ≥ 3 (dernière chance avant escalade F-23) → Ultra toujours.

    F-122 (post-mortems runs #8/#10) : les déclencheurs historiques « rejet
    déterministe à l'itération 2 » et « Coder mort techniquement » sont
    RETIRÉS — l'Ultra (Ornith-9B no-think) est trop lent (3.8 t/s, mega-blocs
    > timeout 600 s observés run #8) pour s'activer tôt. En bornant à
    l'itération 3 : AU PLUS UNE activation par run, coût borné, et une vraie
    dernière chance quand le 4B a échoué 2× (run #10 : bug compteur reproduit
    3× face aux gardes déterministes). Les signaux prev_deterministic_reject /
    prev_coder_died restent calculés (workflows) à titre d'observabilité.

    Retourne (spec, max_tokens, is_ultra). L'Ultra = no_think_spec (gros modèle
    sans thinking, REASONING_NO_THINK_*) si configurée, sinon repli fast.
    """
    iteration = int(task.get("iteration", 1) or 1)
    no_think_model = str(getattr(getattr(settings, "no_think_spec", None), "model", "") or "")
    ultra_ok = (
        getattr(settings, "coder_ultra_correction", False)
        and bool(no_think_model)
        and iteration >= 3
    )
    if ultra_ok:
        return settings.no_think_spec, settings.reasoning_max_tokens, True
    return settings.fast_spec, settings.fast_max_tokens, False


def _tester_max_steps_fallback(steps, prompt: str):
    """Verdict de secours quand le Tester atteint max_steps sans final_answer propre.

    Le Web Tester (9B + Chrome DevTools) over-explore : à max_steps, smolagents
    auto-génère un final_answer depuis le dernier step, mais c'est du PROSE (pas un
    dict {task_id, status, details}) → extract_and_validate échoue → 3 retries gaspillés
    (~15 min) → None → Judge sans signal test. Runs 2026-08-11.

    Ce fallback scanne le step history (observations des evaluate_script) et construit
    un verdict COMPORTEMENTAL :
    - si une observation contient un marqueur de FAIL → status="failure" + feedback
      (le Coder reçoit l'échec et peut corriger).
    - sinon (assertions ont tourné sans FAIL observé) → status="success" + détails
      "max_steps atteint, N observations sans échec explicite".

    CONSERVATIF vs OPTIMISTE : on ne dit success QUE si des assertions ont tourné
    (≥1 observation avec marqueur PASS) sans aucun FAIL. Si 0 observation (le Tester
    n'a même pas testé), on reste sur failure (ne valide pas à l'aveugle).

    Args:
        steps: agent.memory.steps (liste d'ActionStep smolagents).
        prompt: le prompt du Tester (pour extraire le task_id).

    Returns:
        CoderOutput ou None (si pas de signal exploitable).
    """
    import re as _re
    from .models import CoderOutput

    # task_id : extrait du prompt (la template contient final_answer({"task_id": "X"}...).
    task_id = "unknown"
    m = _re.search(r'"task_id"\s*:\s*"([^"]+)"', prompt)
    if m:
        task_id = m.group(1)

    # Collecte toutes les observations textuelles des steps.
    obs_blob = ""
    n_obs = 0
    for step in steps or []:
        obs = getattr(step, "observations", None) or ""
        if obs:
            obs_blob += "\n" + str(obs)
            n_obs += 1
        # Les erreurs d'outil (error) sont aussi du signal.
        err = getattr(step, "error", None)
        if err:
            obs_blob += "\n" + str(err)

    # F-127 : on filtre les lignes = erreurs des OUTILS du Tester (probe sur ID
    # inexistant, MCP -32602, NameError sandbox...) — elles ne prouvent PAS un
    # échec de l'app testée. Le scan FAIL/PASS porte sur le reste.
    # NB : « Uncaught » (erreur console de l'APP) n'est JAMAIS exclu, et le
    # pattern du probe null est ANCRÉ en tête de ligne (« Error: Cannot read
    # properties of null » tel que le retourne evaluate_script) pour ne pas
    # masquer un « Uncaught TypeError: ... properties of null » de l'app.
    def _is_tool_error_line(line_lower: str) -> bool:
        if "uncaught" in line_lower:
            return False
        if any(m in line_lower for m in _TESTER_TOOL_ERROR_MARKERS):
            return True
        stripped = line_lower.lstrip()
        return stripped.startswith("error: cannot read properties of null") or (
            stripped.startswith("out: error: cannot read properties of null")
        )

    app_lines = [
        ln for ln in obs_blob.splitlines()
        if ln.strip() and not _is_tool_error_line(ln.lower())
    ]
    app_blob = "\n".join(app_lines).lower()
    has_fail = any(marker in app_blob for marker in _TESTER_FAIL_MARKERS)
    has_pass = any(marker in app_blob for marker in _TESTER_PASS_MARKERS)

    if has_fail:
        # Un échec explicite a été observé → verdict failure + feedback.
        # Extrait un extrait de l'observation contenant le FAIL (pour guider le Coder).
        snippet = ""
        for line in app_lines:
            ll = line.lower()
            if any(marker in ll for marker in _TESTER_FAIL_MARKERS):
                snippet = line.strip()[:300]
                break
        return CoderOutput(
            task_id=task_id,
            status="failure",
            details=f"Tester (max_steps fallback) : assertion en échec — {snippet}" if snippet
            else "Tester (max_steps fallback) : assertion en échec observée.",
        )

    if has_pass and n_obs > 0:
        # Des assertions ont tourné sans FAIL observé → succès partiel.
        return CoderOutput(
            task_id=task_id,
            status="success",
            details=f"Tester (max_steps fallback) : {n_obs} observation(s), aucune en échec explicite. "
            "Le Tester a atteint max_steps sans final_answer structuré — verdict dérivé du step history.",
        )

    # F-61 (post-mortem run partiel 1h30, 2026-08-13) : on NE retourne PLUS None.
    # Renvoyer None déclenchait un retry complet du Tester (run_with_retry) qui
    # re-thrashait à l'identique (5 retries observés, ~43 steps, 1h30 sans verdict)
    # car le Tester reproduit le même échec de convergence. Un run à max_steps
    # SANS conclusion est lui-même un signal : le Tester n'a pas pu valider →
    # failure pour le Coder (feedback "test inconclusive"), qui retente à
    # l'itération suivante ou déclenche l'escalation après max_iterations cycles.
    # Strictement meilleur que brûler des retries vains : on ne valide rien à
    # l'aveugle (status=failure, pas success), on rapporte juste honnêtement
    # que le Tester n'a pas convergé.
    return CoderOutput(
        task_id=task_id,
        status="failure",
        details=(
            f"Tester n'a pas convergé (max_steps atteint sans conclusion claire : "
            f"0 assertion PASS/FAIL observée sur {n_obs} observation(s)). "
            "Le Tester a probablement thrashé (erreurs outils, navigation sans "
            "assertion utilisable). Réexaminer la testabilité du code ou la "
            "stabilité du Tester."
        ),
    )


async def run_with_retry(
    agent: ToolCallingAgent,
    prompt: str,
    model_class: type,
    max_retries: int,
    loop_guard: Optional["LoopGuard"] = None,
    node_kind: str = "coder",
    model_id: Optional[str] = None,
    api_base: Optional[str] = None,
    timeout_s: Optional[float] = None,
    idle_breaker_threshold: int = 3,
    stall_detector: Optional["StallDetector"] = None,
    goal_enforcer: Optional["GoalEnforcer"] = None,
    visual_criteria_count: int = 0,
) -> Tuple[Optional[object], Optional[NodeMetrics]]:
    """Exécute un agent avec retry. Retourne (données_validées, métriques).

    Les métriques (tokens/durée) viennent du RunResult de smolagents
    (return_full_result=True). En cas d'échec définitif, les métriques du dernier
    essai sont quand même renvoyées pour l'observabilité.

    F-33 (guard logiciel) : un prompt seul ne suffit jamais (leçon majeure des audits —
    les 5 projets matures couplent le prompt à un guard logiciel). On ajoute 2 détections :
    (1) tour sans tool call exécuté → message anti "reasoning sans action" ;
    (2) exception de parsing (code Python cassé) → message "découpe au lieu de recommencer"
        (inspiration deer-flow dangling_tool_call_middleware).

    P3 (Anti-Loop Cryptographique) : si un `loop_guard` est passé, on enregistre
    chaque tool call exécuté. Quand l'agent répète EXACTEMENT le même appel
    `threshold` fois, on interrompt immédiatement (circuit-breaker) au lieu de
    le laisser brûler des tokens. Inspiré de Crush.

    ``node_kind`` (fix TIMINGS_ANALYSE) : adapte le message idle au contexte (coder =
    write_file/search_replace, tester = puppeteer_*). Le Tester souffrait du failure mode
    "does not contain any JSON blob" (modèle thinking sans tool call) que le guard F-33
    n'existait que pour le Coder. Désormais tout agent appelant run_with_retry en bénéficie.

    P3-ter (F-99, Goal Enforcement) : si un `goal_enforcer` est passé, un final_answer
    VALIDE n'est plus accepté tel quel — le harnais audite les preuves matérielles de
    complétion (écritures, livrables sur disque, verify-after). Non prouvé → prompt de
    continuation qm (« treat completion as unproven ») ; même impasse 3 rounds → accepté
    blocked (le Judge arbitre) ; aucun tool call → auto-waiver anti-deadlock ; plafond
    tokens → wind-down unique. Complète F-36/F-88 (déterministe tool-level) par la garde
    comportementale du faux « j'ai fini ».
    """
    last_metrics: Optional[NodeMetrics] = None
    # Détecte si l'agent est un CodeAgent (P1) pour adapter le message de retry
    is_code_agent = type(agent).__name__ == "CodeAgent"

    # Post-mortem run coding_d72dc8e36445c4b6 (F-61) : circuit-breaker sur idles
    # consécutifs. _detect_idle_step (F-33) réinjecte un message à chaque tour idle
    # mais ne coupait JAMAIS → un Coder pouvait enchaîner N runs idle (chacun jusqu'à
    # max_steps sans tool call) jusqu'à épuisement de max_retries. On borne : si
    # `idle_breaker_threshold` runs consécutifs finissent idle, on casse tôt (échec
    # définitif propre) au lieu de brûler des retries vains. Un run productif reset.
    consecutive_idle = 0

    # F-101 (pi §3.9 overflowRecoveryUsed) : UNE SEULE récupération d'overflow
    # par exécution de nœud. Un dépassement de contexte est classé fatal par
    # le retry transport (F-104) et remonte ici ; la purge mémoire (fin de
    # boucle) est notre récupération. Si la requête recompactée déborde
    # ENCORE, c'est que le prompt système + tâche est incompressible →
    # échec propre immédiat (failure_drain pi), plus de retries brûlés.
    # Un appel run_with_retry = un tour utilisateur logique → garde locale,
    # réarmée naturellement à l'appel suivant.
    overflow_guard: Optional[OverflowGuard] = None
    try:
        from .config import settings as _settings

        if _settings.compaction_overflow_guard:
            overflow_guard = OverflowGuard()
    except Exception:
        overflow_guard = OverflowGuard()

    # Réinitialise les erreurs enregistrées pour ce nouveau run du nœud
    _RUN_ERRORS.clear()

    for attempt in range(max_retries):
        # F-99 : le final_answer peut être valide MAIS non prouvé (audit de
        # complétion) → continuation injectée. Le flag supprime le RAPPEL
        # générique "JSON invalide" qui serait mensonger dans ce cas.
        goal_continued = False
        # P8 (Orphan Repair) : avant chaque exécution, on répare les appels d'outil
        # orphelins de la mémoire (tool_calls sans observation/erreur). Un historique
        # restauré depuis un checkpoint peut contenir un appel interrompu ; renvoyé
        # tel quel à l'API, il ferait crasher le graphe. On injecte une fausse réponse
        # "Interrompu" pour permettre la reprise. Défensif (jamais bloquant).
        try:
            mem_steps = getattr(getattr(agent, "memory", None), "steps", None)
            if mem_steps:
                n_orphan = repair_orphan_steps(mem_steps)
                if n_orphan:
                    print(
                        f"[Orphan Repair] {n_orphan} appel(s) d'outil orphelin(s) "
                        f"réparé(s) avant exécution."
                    )
        except Exception:
            pass
        # F-33 (2) : tool call cassé (ex: triple-quote non fermée en CodeAgent).
        # On attrape l'exception de parsing et on renvoie un message "découpe" (deer-flow).
        try:
            # asyncio.to_thread : smolagents est synchrone, on le déporte hors de la loop.
            # IMPORTANT : return_full_result doit être nommé — sinon `True` positionnel
            # tombe sur `stream` (2e paramètre) et renvoie un générateur au lieu d'un RunResult.
            #
            # timeout_s (fix blocage Tester Chrome DevTools) : hard deadline wall-clock.
            # Si fourni, on wrap le to_thread dans asyncio.wait_for. À l'expiration, on
            # rend un échec propre (None) pour que le graphe continue (Judge → itération).
            # NOTE : le thread sous-jacent (agent.run + Chrome/npx bloqué) ne peut pas être
            # tué par Python — il reste zombie jusqu'à la fin du process. C'est un compromis
            # accepté : strictement meilleur que le blocage total du graphe.
            coro = asyncio.to_thread(
                agent.run, prompt, stream=False, return_full_result=True
            )
            if timeout_s and timeout_s > 0:
                run_result = await asyncio.wait_for(coro, timeout=timeout_s)
            else:
                run_result = await coro

            # smolagents renvoie un RunResult quand return_full_result=True
            raw_output = run_result.output if hasattr(run_result, "output") else run_result
            
            agent_model = getattr(agent, "model", None)
            api_base_val = _resolve_agent_api_base(agent_model)
            model_id_val = getattr(agent_model, "model_id", None)
            
            validated = extract_and_validate(raw_output, model_class, api_base=api_base_val, model_id=model_id_val)

            # Fallback & Hard-Gate (Tester) : si le LLM Tester atteint max_steps sans
            # final_answer structuré, ou si DSPy a sauvé avec "success" alors que des erreurs
            # critiques (TypeError, Uncaught, syntax error) existent dans les observations des steps,
            # on applique le verdict comportemental déterministe.
            if node_kind == "tester":
                _fb_steps = getattr(getattr(agent, "memory", None), "steps", None) or []
                _fallback = _tester_max_steps_fallback(_fb_steps, prompt)
                if _fallback is not None:
                    if validated is None or (_fallback.status == "failure" and validated.status == "success"):
                        if validated is not None:
                            print(
                                f"[!] Tester Hard-Gate : écrasement du verdict complaisant par failure "
                                f"suite à une anomalie critique détectée dans les logs ({_fallback.details[:120]}...)."
                            )
                        else:
                            print(
                                f"[i] Tester max_steps fallback activé : verdict dérivé du step "
                                f"history (status={_fallback.status})."
                            )
                        validated = _fallback

            # Collecte métriques depuis le RunResult
            last_metrics = _metrics_from_run(agent, run_result)
            # F-99 : metering cumulatif (même tentative échouée) pour le
            # plafond de tokens du goal enforcer (meterGoalCall qm : in+out).
            if goal_enforcer is not None:
                goal_enforcer.record_tokens(last_metrics)

            # P3 (Anti-Loop) : enregistre les tool calls de CETTE exécution dans
            # le guard. On profite de la boucle sur les steps pour extraire les tool
            # calls UNE fois (servira aussi au stall_detector ci-dessous).
            loop_msg = None
            all_calls: list[tuple[str, object]] = []
            steps = getattr(getattr(agent, "memory", None), "steps", None) or []
            if loop_guard is not None or stall_detector is not None:
                for step in steps:
                    all_calls.extend(extract_tool_calls_from_step(step))
            if loop_guard is not None:
                for tname, targs in all_calls:
                    loop_guard.record(tname, targs)
                loop_msg = loop_guard.repeated_action()
                if loop_msg:
                    print(
                        f"[!] Anti-Loop (Tentative {attempt + 1}/{max_retries}) : "
                        f"action répétée {loop_guard.threshold}+ fois → circuit-breaker."
                    )
                    prompt += f"\n\n{loop_msg}"

            # P3-bis (Stall Detector, F-88) : classifie chaque STEP (un step = un
            # turn loopx) + hashe le matériel produit pour détecter soit une
            # reproduction (même contenu réécrit) soit une série de turns sans
            # livrable nouveau. Complément de F-36 qui ne hashe que l'input. Le
            # signal guide le retry UNIQUEMENT si validated est None.
            stall_msg = None
            if stall_detector is not None:
                for step in steps:
                    step_calls = extract_tool_calls_from_step(step)
                    outcome = classify_turn(step_calls)
                    material_hash = dominant_material_hash(step_calls)
                    stall_detector.record(outcome, material_hash)
                if stall_detector.is_stalled():
                    stall_msg = stall_detector.signal()
                    if stall_msg:
                        print(
                            f"[!] Stall Detector (Tentative {attempt + 1}/{max_retries}) : "
                            f"{stall_detector.threshold}+ turns sans matériel nouveau → circuit-breaker."
                        )
                        prompt += f"\n\n{stall_msg}"

            if validated:
                error_msg = None
                if hasattr(validated, "vision_ok") and node_kind == "coder":
                    is_frontend = any(t.name == "take_screenshot" for t in getattr(agent, "tools", {}).values())
                    if is_frontend:
                        # F-126 : preuve DURABLE d'abord — le flag est posé à
                        # l'EXÉCUTION réelle par vision_callback, insensible à la
                        # compaction/purge qui vidait agent.memory.steps (run
                        # 2026-08-19_1552 : screenshot étape 7, refusé étape 41).
                        # Le scan mémoire reste en fallback (agents sans wrapper).
                        used_vision = screenshot_was_taken()
                        if not used_vision:
                            steps = getattr(getattr(agent, "memory", None), "steps", None) or []
                            for step in steps:
                                code = str(getattr(step, "model_output", "")) + str(getattr(step, "code_action", ""))
                                if "take_screenshot" in code:
                                    used_vision = True
                                    break
                        if not used_vision:
                            error_msg = "ERREUR FATALE: Tu as déclaré la tâche terminée mais tu n'as PAS utilisé 'take_screenshot' pour vérifier visuellement ton UI. C'est OBLIGATOIRE. Recommence, navigue sur la page, prends le screenshot, et vérifie que ça marche vraiment."
                        elif visual_criteria_count > 0:
                            # F-109 : l'audit visuel doit être MATÉRIALISÉ — le
                            # « all N criteria verified » déclaratif du 4B (run #5)
                            # ne suffit plus : chaque critère doit avoir un appel
                            # visual_check avec verdict + observation factuelle.
                            error_msg = _visual_checklist_error(visual_criteria_count)
                
                if error_msg:
                    print(f"[-] Checklist échouée : {error_msg}")
                    prompt += f"\n\n{error_msg}"
                    validated = None
                else:
                    # P3-ter (F-99, Goal Enforcement) : le final_answer est valide,
                    # mais la COMPLÉTION n'est pas prouvée pour autant. Audit
                    # déterministe des preuves matérielles (écritures + disque +
                    # verify-after) ; non prouvé → prompt de continuation qm et on
                    # boucle (consomme un attempt) ; impasse répétée/deadlock/cap →
                    # waiver : résultat conservé, le Judge arbitre en aval.
                    if goal_enforcer is not None:
                        decision = goal_enforcer.enforce(steps)
                        if decision.action == GoalAction.CONTINUE:
                            if attempt == max_retries - 1:
                                # Fix run2 F-99 (2026-08-14) : une continuation
                                # sur le DERNIER attempt ne pourrait pas être
                                # honorée (plus de budget node) — elle convertirait
                                # un final_answer valide en échec technique et
                                # priverait le Judge de son arbitrage. On waive :
                                # résultat conservé, la boucle graphe
                                # (max_iterations) reste l'enceinte externe.
                                print(
                                    f"[i] Goal enforcement (dernier attempt) : "
                                    f"{decision.reason} → résultat conservé, le "
                                    f"Judge arbitre (pas de budget de continuation)."
                                )
                            else:
                                print(
                                    f"[!] Goal enforcement (Tentative {attempt + 1}/{max_retries}) : "
                                    f"{decision.reason}"
                                )
                                record_run_error(
                                    f"Goal enforcement : complétion non prouvée — {decision.reason}"
                                )
                                prompt += f"\n\n{decision.prompt_note}"
                                validated = None
                                goal_continued = True
                        elif decision.action == GoalAction.WAIVE:
                            print(
                                f"[i] Goal enforcement : {decision.reason}"
                            )
                    if validated is not None:
                        # Un final_answer valide prime sur le LoopGuard (F-36). Le guard
                        # scanne tout l'historique du run et peut comptabiliser comme
                        # "répétition" une itération de correction légitime (même write_file
                        # /search_replace rejoué après lecture). Éjecter un résultat réussi
                        # pour ça le transforme en échec technique (post-mortem run
                        # coding_d72dc8e36445c4b6 : final_answer success jeté → verdict
                        # failure). loop_msg reste ajouté au prompt de retry (ligne ci-dessus)
                        # pour le cas où validated est None — il guide alors le retry suivant.
                        if loop_msg:
                            print(
                                "[i] LoopGuard a signalé une répétition, mais le "
                                "final_answer est valide → succès conservé (priorité au "
                                "résultat sur le guard F-36)."
                            )
                        if stall_msg:
                            print(
                                "[i] Stall Detector a signalé un stall, mais le "
                                "final_answer est valide → succès conservé (priorité au "
                                "résultat sur le stall detector F-88)."
                            )
                        return validated, last_metrics

            # F-33 (1) : tour sans tool call exécuté ? (modèle réfléchit sans agir)
            idle_msg = _detect_idle_step(agent, node_kind=node_kind)
            if idle_msg:
                consecutive_idle += 1
                # F-61 : circuit-breaker sur idles consécutifs. Si le seuil est atteint,
                # on casse tôt (échec définitif propre) — réinjecter un message vain une
                # Nème fois ne sert à rien, le modèle a déjà prouvé qu'il ne sort pas de
                # sa boucle de réflexion sans action. last_metrics rendu pour l'observabilité.
                if consecutive_idle >= idle_breaker_threshold:
                    print(
                        f"[-] Circuit-breaker idle : {consecutive_idle} runs consécutifs sans "
                        f"appel d'outil pour {model_class.__name__} (seuil {idle_breaker_threshold}). "
                        f"Échec définitif propre au lieu de brûler des retries vains."
                    )
                    record_run_error(
                        f"Circuit-breaker idle : {consecutive_idle} runs consécutifs sans tool call "
                        f"(seuil {idle_breaker_threshold}). Le modèle boucle sur de la réflexion "
                        f"sans agir — abort pour économiser le budget."
                    )
                    return None, last_metrics
                print(
                    f"[!] Tentative {attempt + 1}/{max_retries} : tour sans appel d'outil "
                    f"({model_class.__name__}, idle consécutif {consecutive_idle}/{idle_breaker_threshold}). "
                    f"Ré-injection d'une consigne d'action..."
                )
                prompt += f"\n\n{idle_msg}"
            else:
                # Un run productif (avec tool calls) reset le compteur d'idles consécutifs.
                consecutive_idle = 0
                if goal_continued:
                    # F-99 : le final_answer ÉTAIT valide — c'est l'audit de
                    # complétion qui a exigé une continuation. Le message qm est
                    # déjà injecté ; le RAPPEL générique "JSON invalide" serait
                    # mensonger ici.
                    pass
                else:
                    print(
                        f"[!] Tentative {attempt + 1}/{max_retries} échouée pour "
                        f"{model_class.__name__}. Nouvelle tentative..."
                    )
                    record_run_error(f"Tentative {attempt + 1} échouée : JSON non valide ou outil final non utilisé.")
                    # Message de retry adapté au type d'agent (Python pour CodeAgent, JSON pour TCA).
                    if is_code_agent:
                        prompt += (
                            f"\n\nRAPPEL: ton dernier essai n'a pas abouti. Appelle final_answer(...) "
                            f"en PYTHON avec un dict conforme au schéma {model_class.__name__}."
                        )
                    else:
                        prompt += (
                            f"\n\nRAPPEL CRITIQUE: Tu as échoué au dernier essai. Renvoie STRICTEMENT "
                            f"un JSON valide pour ce schéma : {model_class.model_json_schema()} "
                            f"via l'outil final_answer."
                        )
        except asyncio.TimeoutError:
            # Fix blocage Tester Chrome DevTools : timeout wall-clock expiré.
            # Le thread agent.run (et le Chrome/npx bloqué) reste zombie — Python ne peut
            # pas tuer un thread — mais on NE bloque PLUS le graphe : on rend un échec
            # propre (None) pour que le Judge puisse enchaîner sur ce qu'il a.
            # last_metrics peut être None (rien n'a été collecté si le 1er run a timeout).
            print(
                f"[-] Timeout du nœud {node_kind} après {timeout_s}s "
                f"(Chrome/DevTools/Puppeteer bloqué ?) — passage au nœud suivant."
            )
            record_run_error(f"Tentative {attempt + 1} échouée : TIMEOUT ({timeout_s}s). La page a pu crasher ou boucler à l'infini.")
            return "TIMEOUT ERROR: L'exécution du testeur a dépassé le délai imparti (120s). Le test a planté (boucle infinie ou gel de l'UI).", last_metrics
        except Exception as e:
            # F-33 (2) : exception pendant l'exécution (code Python cassé en CodeAgent,
            # payload invalide en TCA). On renvoie un message "découpe" au lieu de planter.
            msg = str(e)
            print(f"[-] Erreur interne (Tentative {attempt + 1}/{max_retries}): {msg}")
            record_run_error(f"Tentative {attempt + 1} échouée (Exception Interne Python/LLM) : {msg}")
            # F-101 (pi §3.9) : dépassement de contexte → UNE SEULE récupération.
            # La purge mémoire de fin de boucle est la compaction de récupération ;
            # si ça déborde encore après elle, la requête est incompressible
            # (system prompt + tools schemas + tâche) → failure_drain : échec
            # propre immédiat, le graphe continue (Judge/itération suivante).
            if is_context_overflow_error(e):
                if overflow_guard is None or overflow_guard.on_overflow():
                    print(
                        "[!] Overflow recovery (F-101) : contexte débordé → mémoire "
                        "purgée, tentative compactée. Un second overflow interrompra "
                        "définitivement ce nœud."
                    )
                    record_run_error(
                        "Overflow recovery : contexte débordé, récupération unique engagée "
                        "(purge mémoire + retry compacté)."
                    )
                    prompt += (
                        "\n\nATTENTION : ta dernière exécution a fait DÉBORDE la fenêtre "
                        "de contexte. La mémoire de l'historique a été purgée. Reprends "
                        "DIRECTEMENT l'action utile suivante, SANS relire ni réexpliquer "
                        "l'historique."
                    )
                else:
                    print(
                        f"[-] Failure drain (F-101, pi §3.9) : {overflow_guard.failure} "
                        f"→ échec définitif propre, plus de retry (le prompt système/"
                        f"tâche dépasse la fenêtre)."
                    )
                    record_run_error(
                        f"Failure drain overflow : {overflow_guard.failure} — la requête "
                        f"reste incompressible après récupération unique, abort du nœud "
                        f"pour économiser le budget."
                    )
                    return None, last_metrics
            # Post-mortem run coding_d72dc8e36445c4b6 (F-61) : failure mode récurrent n°1, le modèle
            # ferme search_replace(..., new_string="<JS>{...}") par `}}}` au lieu de `)`. La règle
            # prompt n°8 existe mais ne suffit pas sous charge (leçon F-33 : un prompt seul ne suffit
            # jamais). On donne un message SPÉCIFIQUE et actionnable (exemple correct) plutôt que le
            # générique "découpe". Messages observés : "closing parenthesis '}' does not match
            # opening '('", "Code parsing failed ... '}' does", etc.
            # NB : cette détection est INDEPENDANTE de la condition Syntax/parse ci-dessous — le
            # message smolagents "Code parsing failed" ne contient ni "Syntax" ni "parse" (mais
            # "parsing"), donc on la teste en premier pour ne pas rater le failure mode n°1.
            if is_code_agent and "}" in msg and ("parenthesis" in msg.lower() or "match" in msg.lower() or "closing" in msg.lower() or "parsing" in msg.lower()):
                prompt += (
                    "\n\nATTENTION — RÈGLE n°8 VIOLÉE : ton bloc Python s'est fermé par `}` au lieu "
                    "de `)`. Quand `content`/`new_string` contient du JS/HTML avec des `{...}`, le `}` "
                    "appartient au CONTENU, l'appel Python se termine TOUJOURS par `)`. Exemple correct :\n"
                    "    search_replace(path=\"x\", old_string=\"...\", new_string=\"function() { startSort(); }\")\n"
                    "Réessaie en fermant l'appel par `)`."
                )
            elif is_code_agent and ("Syntax" in msg or "parse" in msg.lower() or "unterminated" in msg.lower()):
                prompt += (
                    "\n\nATTENTION : ton dernier bloc de code Python a échoué (syntaxe invalide : "
                    "string non fermée, parenthèse manquante...). NE RECOMMENCE PAS le même gros "
                    "payload — DÉCOUPE en plus petits append_file, chaque bloc syntaxiquement complet."
                )

        # F-109-bis : rappel de checklist au BOUNDARY d'attempt. Constat de la
        # boucle Coder isolée (2026-08-15, 60 steps, 0 appel) : le 4B exécute le
        # pipeline visuel (screenshot/fuzz/console) mais n'appelle JAMAIS
        # visual_check tant que l'exigence ne lui est pas RÉINJECTÉE — elle
        # n'était que dans le prompt initial + au final_answer qu'un run
        # thrashant n'atteint jamais (mort à max_steps). On réinjecte le décompte
        # exact à chaque fin de tentative sans verdict.
        if visual_criteria_count > 0:
            _audited = {a.get("criterion_number") for a in get_visual_audit()}
            _missing_vc = sorted(set(range(1, visual_criteria_count + 1)) - _audited)
            if _missing_vc:
                prompt += (
                    f"\n\nCHECKLIST VISUELLE INCOMPLÈTE ({visual_criteria_count - len(_missing_vc)}/"
                    f"{visual_criteria_count} critères audités — manquants : {_missing_vc}). "
                    f"Avant final_answer tu DOIS appeler visual_check(criterion_number=i, "
                    f"verdict=True|False, observation=\"ce que tu vois\") pour CHAQUE critère "
                    f"manquant, après un take_screenshot frais. final_answer sera REFUSÉ sans "
                    f"checklist complète."
                )
                print(
                    f"[!] Visual audit : {len(_missing_vc)}/{visual_criteria_count} critère(s) "
                    f"non audité(s) → rappel checklist injecté au retry."
                )

        # FIX TOKEN EXPLOSION: Si on est arrivé ici (erreur ou JSON invalide),
        # l'agent a gardé tout son historique d'échec dans sa mémoire interne.
        # Au prochain tour de la boucle for, si on rappelle agent.run, il va TOUT renvoyer !
        # On doit purger la mémoire de l'agent avant le prochain essai.
        if hasattr(agent, "memory") and hasattr(agent.memory, "steps"):
            agent.memory.steps = []
        # P3 : alignement du guard sur la purge — le retry repart d'un historique
        # vierge, donc les comptes de répétition doivent repartir de zéro aussi
        # (sinon un bug d'une tentative précédente fait déclencher la suivante).
        if loop_guard is not None:
            loop_guard.reset()
        # P3-bis (F-88) : même alignement pour le stall detector.
        if stall_detector is not None:
            stall_detector.reset()


    print(f"[-] Échec définitif pour {model_class.__name__} après {max_retries} tentatives.")
    return None, last_metrics


def _metrics_from_run(agent: ToolCallingAgent, run_result) -> NodeMetrics:
    """Extrait les métriques d'un RunResult smolagents."""
    model_id = getattr(getattr(agent, "model", None), "model_id", "?")
    node_name = getattr(agent, "name", "agent")

    duration = None
    in_tok = None
    out_tok = None

    timing = getattr(run_result, "timing", None)
    if timing is not None:
        duration = getattr(timing, "duration", None)

    token_usage = getattr(run_result, "token_usage", None)
    if token_usage is not None:
        in_tok = getattr(token_usage, "input_tokens", None)
        out_tok = getattr(token_usage, "output_tokens", None)

    return NodeMetrics(
        node=node_name,
        model=model_id,
        duration_s=duration,
        input_tokens=in_tok,
        output_tokens=out_tok,
    )


# ==========================================
# Nœuds
# ==========================================

async def execute_worker_node(
    task: dict,
    fast_model: OpenAIServerModel,
    settings: Settings,
) -> Tuple[Optional[WorkerOutput], Optional[NodeMetrics]]:
    """Nœud Fan-out : analyse une tâche de manière isolée et parallèle."""
    # name affiché dans le panneau "New run - worker_t1" ; verbosity réduite pour
    # éviter l'entrelacement des logs quand plusieurs workers tournent en parallèle.
    # smolagents exige un identifiant Python valide (pas de crochets).
    local_worker = ToolCallingAgent(
        tools=[],
        model=fast_model,
        name=f"worker_{task['id'].replace('-', '_')}",
        description="Analyse une tâche d'infrastructure et produit un summary + score de confiance.",
        verbosity_level=resolve_verbosity(settings.log_level),
    )

    prompt = f"""Analyse cette tâche et retourne le résultat STRICTEMENT en utilisant l'outil 'final_answer'.
    N'ajoute AUCUN texte avant ou après le JSON.
    Ton JSON DOIT absolument respecter ce format exact pour appeler l'outil final_answer :
    {{
      "name": "final_answer",
      "arguments": {{
        "answer": {{
          "task_id": "{task['id']}",
          "summary": "ton résumé détaillé de la tache",
          "confidence_score": 0.95
        }}
      }}
    }}
    Contenu de la tâche : {task['content']}
    """
    return await run_with_retry(local_worker, prompt, WorkerOutput, settings.worker_max_retries, idle_breaker_threshold=10**9)


def _is_web_task(task: dict) -> bool:
    """Détecte si la tâche produit du contenu web (HTML/CSS/JS) → preview DevTools pertinent.

    Défense en profondeur : routeur (router_lang) OU extensions des target_files.
    Le routeur peut se tromper (ex: prompt ambigu), les extensions sont plus fiables.
    """
    router_lang = (task.get("router_lang") or "").lower()
    if any(k in router_lang for k in ("web", "html", "css", "front", "javascript")):
        return True
    target_files = task.get("target_files") or []
    web_exts = (".html", ".htm", ".css", ".js")
    return any(str(f).lower().endswith(web_exts) for f in target_files)


def _build_devtools_blocks(task: dict, cdt_tools: list) -> tuple[str, str]:
    """Construit les blocs prompt pour Chrome DevTools (preview + doc outils). F-45.

    Retourne (preview_block, tools_doc) :
      - Si cdt_tools est vide (serveur indisponible ou désactivé) → chaînes vides.
        Le Coder tourne sans preview (backward-compat, comme avant F-45).
      - Si la tâche n'est PAS web → doc outils absente, preview absent. Les outils
        restent disponibles (au cas où) mais le prompt ne les pousse pas.
      - Si web + outils dispos → preview block (workflow de validation visuelle) +
        doc des outils clés (navigate_page, take_screenshot, list_console_messages).

    F-82 : si l'Architecte a produit des ``visual_success_criteria``, ils sont intégrés
    au preview_block sous forme de checklist anti-biais (force le Coder à ANALYSER son
    screenshot au lieu d'excuser un visuel vide — bug canvas 2026-08-08). Rétrocompat :
    liste vide = workflow DevTools historique (pas de checklist forcée).

    Le screenshot pris est vu par le modèle (gemma-4-E4B est multimodal, validé runtime).
    """
    if not cdt_tools:
        return "", ""
    # Calcule l'URL file:/// absolue du fichier HTML principal (le Coder s'exécute
    # dans le dossier du run après _scoped_chdir, donc os.getcwd() = dossier du run).
    target_files = task.get("target_files") or ["index.html"]
    primary_target = target_files[0]
    primary_url = "file:///" + os.path.abspath(primary_target).replace("\\", "/")

    if not _is_web_task(task):
        # Pas web : on liste les outils mais sans workflow de preview poussé.
        return "", _DEVTOOLS_TOOLS_DOC

    # F-82 : critères visuels générés par l'Architecte (anti-biais de confirmation).
    from .validation_criteria import build_visual_criteria_block
    visual_block = build_visual_criteria_block(task.get("visual_success_criteria") or [])
    # Si critères présents, l'étape 5 du workflow devient une checklist concrète au
    # lieu du "rendu conforme" flou. Sinon, on garde le workflow historique.
    if visual_block:
        criteria_note = (
            "\n5. VALIDATION CRITÈRES VISUELS : confirme OUI/NON chaque critère ci-dessous"
            " sur ta capture. UN seul NON = failure → corrige."
        )
    else:
        criteria_note = "\n5. final_answer uniquement quand : 1) le rendu est conforme, 2) 0 erreur console."

    preview_block = f"""### 🖥️ VALIDATION VISUELLE (Chrome DevTools — F-45)
Tu disposes d'un navigateur Chrome pilotable pour VÉRIFIER ta page AVANT final_answer.

⚠️ PIÈGE FRÉQUENT : une page au rendu "joli" (CSS ok) peut avoir TOUT son JS cassé
silencieusement (boutons morts, éléments non générés). Seule la console le révèle.

Workflow de validation (À FAIRE après avoir créé les fichiers, AVANT final_answer) :
1. `navigate_page(url="{primary_url}")` — ouvre ta page dans Chrome (URL absolue ci-dessous).
2. `take_screenshot()` — OBLIGATOIRE EN PREMIER pour voir l'état initial.
3. FUZZING UI OBLIGATOIRE : Exécute `fuzz_click_all_buttons()` pour cliquer sur tous les boutons et réveiller les bugs JS cachés (monkey testing en 1 appel, encapsule le snippet JS).
4. `list_console_messages()` — OBLIGATOIRE EN DERNIER. Vérifie 0 erreur JS (SyntaxError, undefined, Uncaught). Sans l'étape 3, tu rateras 80% des erreurs !
5. Si erreur : CORRIGE via `search_replace` (jamais de rewrite total), puis recommence le cycle (navigate, screenshot, fuzzing, console).
6. JEU/CANVAS ANIMÉ : un screenshot ne prouve PAS l'animation — appelle `probe_canvas_activity()`
   et exige le statut ANIMATING avant final_answer (STATIC_PAINTED = tu dessines probablement
   avec la mauvaise variable, ex: ghostY au lieu de la position réelle — vérifie ta fonction draw).
⚠️ Si `navigate_page` TIMEOUT sur ta page LOCALE : le JS bloque le thread (boucle while/do-while infinie — un fichier local se charge en <1s). Relire le code, corriger la boucle via search_replace, re-naviguer — ne JAMAIS retenter la navigation à l'identique.
{criteria_note}

URL exacte de ta page (primary target) : {primary_url}
ATTENTION : si ta page n'est pas à la racine du run, navigate_page DOIT pointer sur le
vrai fichier (ex: landing_page/index.html), pas sur la racine du workspace.{visual_block}"""
    return preview_block, _DEVTOOLS_TOOLS_DOC


# Doc compacte des outils Chrome DevTools injectée dans la section OUTILS du Coder.
# F-72 (Prompt Offloading) : signatures communes factorisées dans DEVTOOLS_BASE_DOC
# (chrome_devtools_tool.py, partagée avec le WebTester). Le Coder n'ajoute que sa note
# spécifique (pas Lighthouse/perf ni take_snapshot avancé = réservés au Tester).
from .chrome_devtools_tool import DEVTOOLS_BASE_DOC
_DEVTOOLS_TOOLS_DOC = DEVTOOLS_BASE_DOC + """
Note : pour un check rapide de syntaxe, `navigate_page` puis `list_console_messages` suffisent dans 90% des cas. (Lighthouse/perf et take_snapshot avancé sont réservés au Tester, pas au Coder.)"""
async def execute_coder_node(
    task: dict,
    fast_model: OpenAIServerModel,
    settings: Settings,
) -> Tuple[Optional[CoderOutput], Optional[NodeMetrics]]:
    """Nœud Coder : utilise des outils pour créer/éditer des fichiers et exécuter des commandes bash."""
    from smolagents import DuckDuckGoSearchTool
    from .context7_tool import context7_tools
    from .chrome_devtools_tool import chrome_devtools_tools
    from .vision_callback import wrap_screenshot_tools, make_screenshot_callback, wrap_console_enrichment

    import sys
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

    # La connexion Context7 (MCP) doit rester ouverte PENDANT tout le run de
    # l'agent (sinon les outils deviennent inertes). On englobe donc la création
    # ET l'exécution de l'agent dans le `with`. Tolérance aux pannes : si pas de
    # clé ou connexion échouée, c7 = [] et le Coder tourne sans doc (backward-compat).
    # F-45 : Chrome DevTools MCP (auto-validation visuelle) est imbriqué selon le
    # même pattern. Si indisponible, cdt = [] et le Coder tourne sans preview.
    with context7_tools() as c7_tools, chrome_devtools_tools() as cdt_tools:
        # Outils fichiers + recherche. Context7 (doc de libs à jour) est ajouté si
        from .tools import (
            read_file, write_file, append_file, list_directory,
            search_replace, multi_replace, edit_file,
            read_python_skeleton, check_js_syntax, check_run_state, log_event,
            visual_check
        )
        coder_tools = [list_directory, read_file, read_python_skeleton, check_js_syntax, write_file, append_file, edit_file, search_replace, multi_replace, check_run_state, log_event, visual_check, DuckDuckGoSearchTool()]
        coder_tools.extend(c7_tools)
        # On redonne tous les outils web au coder, incluant vision (DevTools ON par
        # défaut — le feedback console est critique pour que le Coder corrige ses
        # bugs de structure HTML/CSS). Le screenshot coûteux est géré par le
        # step_callback vision (F-45), pas désactivable ici.
        coder_tools.extend(cdt_tools)
        # F-72 (Prompt Offloading) : helpers DevTools (clean_dom, add_visual_tags,
        # fuzz_click_all_buttons) — encapsulent des snippets JS récurrents pour
        # décharger le prompt (ex: fuzzing UI). Fail-open si DevTools indispo.
        from .devtools_dom_tools import build_devtools_helper_tools
        coder_tools.extend(build_devtools_helper_tools(cdt_tools))
        effective_cdt_tools = cdt_tools  # DevTools ON → preview_block actif
        # F-57 (Priorité 10) : tool load_skill pour la flexibilité. Les skills
        # sélectionnés par l'Architect sont déjà injectés en corps complet dans le
        # system prompt (voir skills_block ci-dessous), mais le Coder peut appeler
        # load_skill pour re-consulter un skill ou en explorer un autre non sélectionné.
        coder_tools.append(load_skill)
        # F-45 : wrap les outils de screenshot pour capturer l'image PIL et la faire
        # remonter au LLM via observations_images (step_callback). Sans ça, smolagents
        # garde l'image pour lui ("Stored 'image.png' in memory.") et le modèle ne la
        # voit jamais. capture_holder est partagé entre le wrapper et le callback.
        screenshot_capture: list = []
        coder_tools = wrap_screenshot_tools(coder_tools, screenshot_capture)
        # F-126 : enrichit list_console_messages avec les stack traces des erreurs
        # (fichier:ligne → guide le 4B vers le bug LOCAL au lieu de réécrire tout
        # le fichier — post-mortem run 2026-08-19_1552). Fail-open si l'outil
        # détail get_console_message est absent.
        coder_tools = wrap_console_enrichment(coder_tools)
        # F-66 (Read-Before-Write Gate) : bloque write_file / search_replace / edit_file /
        # multi_replace / append_file sur un fichier EXISTANT dont le contenu n'a pas été
        # lu (hash SHA256 du contenu complet). Inspiré de Deer Flow (issue #3857). Mode
        # Strict : un write réussi invalide la mark → force re-read avant chaque édition.
        # Fail-open garanti (fichier absent = création OK). Opt-out via settings.
        # ORDRE : AVANT sanitize_tools — le sanitizer coerce les args (path str), puis
        # délègue au gate qui check le path. Le gate voit donc des kwargs déjà typés.
        from .read_gate import ReadGate, wrap_tools_with_read_gate
        read_gate = ReadGate()
        coder_tools = wrap_tools_with_read_gate(
            coder_tools, read_gate, enabled=settings.read_before_write_enabled
        )
        # F-42 (Sanitizer) : coerce best-effort les arguments malformés du petit
        # LLM (ex: offset="1, 80" → 80) avant l'appel d'outil → moins de retries
        # gaspillées sur les erreurs de validation de type. Opt-out via settings.
        coder_tools = sanitize_tools(coder_tools, enabled=settings.sanitizer_enabled)

        # P1 : migration ToolCallingAgent → CodeAgent. Les petits modèles locaux (gemma)
        # ne savent pas émettre de tool_call JSON fiable (tool_calls=None, finish_reason=
        # 'stop' — le modèle "parle" de l'action au lieu de l'exécuter). CodeAgent génère
        # du PYTHON qui appelle les outils (write_file(path=..., content=...)) — beaucoup
        # plus naturel. Preuves empiriques : 3 comparatifs (consignés dans le
        # journal d'événements DuckDB) — CodeAgent produit
        # jusqu'à 91× plus de contenu que le TCA sur une même tâche.
        # final_answer s'appelle maintenant en SYNTAXE PYTHON : final_answer({...}) ou
        # final_answer("texte"), pas en JSON. extract_and_validate gère les 2 (dict + str).
        # L'instanciation de local_coder a été déplacée plus bas, à l'intérieur du bloc `with model_lifecycle`.

        target_files_instruction = ""
        if "target_files" in task and task["target_files"]:
            files_list = "\n".join([f"- {f}" for f in task["target_files"]])
            target_files_instruction = f"""
### ⚠️ FICHIERS CIBLES — TU DOIS CRÉER CES FICHIERS (priorité absolue)
{files_list}

- 📍 TON DOSSIER DE TRAVAIL ACTUEL EST LE DOSSIER DE RUN. Cela signifie que pour
  créer `index.html`, tu utilises le chemin COURT `index.html` (PAS de préfixe
  `runs/...` ni de chemin absolu). Le fichier atterrira au bon endroit.
  → JAMAIS de `write_file(path="runs/2026-..._bubble_sort/index.html", ...)` :
  cela créerait un sous-dossier imbriqué `runs/.../runs/.../index.html` et la
  validation visuelle échouerait (ERR_FILE_NOT_FOUND). Utilise `index.html`.
- 'write_file' crée automatiquement les sous-répertoires manquants NÉCESSAIRES
  (ex: pour `landing_page/index.html`, le dossier `landing_page/` est créé) — mais
  ne préfixe JAMAIS par le dossier de run lui-même.
- ⚠️ AVANT TOUTE CHOSE : Si tu as un BROUILLON DRAFTER (section '### BROUILLON DE L'ALGORITHM DRAFTER' ci-dessous), SAUTE check_run_state et va DIRECTEMENT lire le draft — c'est ton point de départ, pas la peine de vérifier l'état (tu es en iteration 1 propre). Sinon (pas de draft), appelle `check_run_state()` pour vérifier si tu es dans une boucle de redémarrage.
- ⚠️ AVANT DE CRÉER UN FICHIER : Vérifie TOUJOURS s'il existe déjà en utilisant l'outil `list_directory(path=".")`. S'il est listé et semble complet, NE LE RÉÉCRIS PAS en entier (utilise search_replace/append_file).
- Sinon, tu DOIS créer le fichier avant de passer au reste.
- 🚀 AUTO-VALIDATION RAPIDE (JS) : Si tu génères ou modifies du JavaScript, vérifie instantanément sa syntaxe AVANT final_answer en appelant l'outil `check_js_syntax(path="ton_script.js")`. Cela te coûte 1 step et t'évite un rejet du Linter."""

        # Skills ciblés pour cette tâche. F-57 (Priorité 10) : L'ARCHITECT SÉLECTIONNE
        # les skills dans son plan (subtask.skills), et le Coder reçoit leur corps
        # complet directement. C'est le mécanisme principal — fiable à 100% (pas de
        # décision du modèle, l'Architect a déjà choisi). Le tool load_skill reste
        # disponible pour la flexibilité (re-consulter un skill, en explorer un autre).
        # Si l'Architect n'a pas sélectionné de skills (vieille sous-tâche, fallback),
        # on utilise la sélection contextuelle (regex sur le contenu) en repli.
        architect_skills = task.get("skills", [])
        if architect_skills:
            # F-57 v3 : budget de tokens anti-saturation. L'Architect peut sélectionner
            # trop de skills → on rogne pour rester sous skill_budget_tokens (défaut 16000,
            # Application du budget de tokens pour les skills (F-57)
            architect_skills = enforce_skill_budget(
                selected_skills=architect_skills,
                budget_tokens=16000,
                always_skills=ALWAYS_SKILLS_CODER
            )
            blocks: list = []
            for name in architect_skills:
                body = load_skill_body(name)
                if body:
                    blocks.append(f"### SKILL: {name}\n{body}")
            skills_block = (
                "Voici tes COMPÉTENCES (skills) — applique leurs consignes directement :\n\n"
                + "\n\n".join(blocks)
            ) if blocks else ""
        else:
            # Repli : sélection contextuelle (regex) si l'Architect n'a rien sélectionné.
            skills_block = build_conditional_skills_block(task.get("content", ""))

        # F-76 : Contextualisation par package (AGENTS.md localisés)
        local_agents_md_block = ""
        if "target_files" in task and task["target_files"]:
            import os
            try:
                target_dirs = [os.path.dirname(f) for f in task["target_files"]]
                common_dir = os.path.commonpath(target_dirs) if target_dirs else ""
                agents_md_path = os.path.join(common_dir, "AGENTS.md") if common_dir else "AGENTS.md"
                # Défense path traversal (review Kilo) : target_files vient potentiellement
                # d'un LLM (Architect). On valide que le chemin résolu reste dans le workspace
                # (cwd = dossier du run, cf F-40 _scoped_chdir). Un chemin comme
                # "../../etc/passwd" est rejeté silencieusement (fail-open, pas de crash).
                workspace_root = os.path.realpath(os.getcwd())
                resolved = os.path.realpath(agents_md_path)
                if os.path.exists(resolved) and (
                    resolved == workspace_root or resolved.startswith(workspace_root + os.sep)
                ):
                    with open(resolved, "r", encoding="utf-8") as f:
                        local_agents_content = f.read()
                    local_agents_md_block = f"\n### DIRECTIVES SPÉCIFIQUES AU COMPOSANT (AGENTS.md)\n{local_agents_content}\n"
            except Exception:
                pass

        # F-32 : prompt réécrit selon la structure canonique des audits (references aider/
        # crush/opencode/openfox/deer-flow + web Anthropic/OpenAI/Cline/SWE-agent) :
        # Rôle → Règles critiques → Format sortie → One-shot → Workflow (adapté stratégie)
        # → Rappels (double-marquage primacy/recency). Corrige les 2 bugs observés :
        # (1) "réfléchit sans agir" (reasoning-action dilemma, petits modèles overthinkent),
        # (2) triple-quote non fermée (limite fenêtre génération).
        strategy = task.get("strategy", "simple")
        sections = task.get("sections", [])
        iteration = task.get("iteration", 1)

        # MODE CORRECTION (itération > 1) : les fichiers cible EXISTENT DÉJÀ (créés à
        # l'itération 1). Le Coder doit CORRIGER chirurgicalement les bugs signalés dans
        # ### Contenu de la tâche (tickets [LINTER] / [JUDGE]), PAS réécrire from-scratch.
        # Sans cette branche, le modèle suit le workflow de création (write_file) → écrase
        # tout le travail précédent à chaque itération = gaspillage + boucle de frustration.
        # Correction = read_file (voir l'état actuel) + search_replace (cibler le fragment
        # fautif). C'est l'invariant n°1 (read-before-write) et n°2 (pas de whole-file rewrite).
        if iteration > 1:
            strategy_block = f"""### WORKFLOW — MODE CORRECTION (itération {iteration}, les fichiers EXISTENT DÉJÀ)
NE RECOMMENCE PAS DE ZÉRO. Les fichiers cible ont été créés à l'itération précédente et
contiennent du vrai code. Le bug à corriger est décrit dans ### Contenu de la tâche (tickets
[LINTER] / [JUDGE]). Procède ainsi :
1. read_file(path) sur CHAQUE fichier signalé fautif pour voir son état ACTUEL.
2. Identifie le fragment précis qui cause le bug (ex: balise </html> placée trop tôt,
   fonction manquante, syntaxe cassée). Les tickets te donnent la ligne et l'aperçu.
3. Utilise l'outil `multi_replace` pour appliquer une ou plusieurs corrections chirurgicales.
   Exemple: `multi_replace(path="index.html", replacements=[{{"old_string": "fragment fautif", "new_string": "fragment corrigé"}}])`
   Donne le fragment EXACT à remplacer (copie de read_file).
4. Répète pour chaque bug signalé. final_answer quand tous les bugs sont corrigés.
ATTENTION : NE JAMAIS appeler write_file sur un fichier déjà créé (ça l'écrase et perd
tout le travail). Uniquement read_file + multi_replace en mode correction."""

        # MODE CRÉATION (itération 1) — workflow adapté à la stratégie dictée par l'Architect (F-29).
        elif strategy == "incremental":
            sections_str = ", ".join(sections) if sections else "(sections à définir)"
            strategy_block = f"""### WORKFLOW (stratégie INCREMENTAL imposée par l'Architect)
Construis ce gros fichier monolithique EN PLUSIEURS PETITES ÉTAPES. NE TENTE PAS un seul
write_file massif (ça s'essouffle/tronque). Procède ainsi :
1. write_file(squelette) UNE SEULE FOIS : la structure HTML de base AVEC des MARQUEURS
   d'insertion ouverts (ex: <!-- INSERT_CSS -->, <!-- INSERT_JS -->). Le squelette ne doit
   PAS être fermé par </html> tant que les sections ne sont pas injectées — sinon les
   appends arrivent après </html> et le navigateur affiche du texte brut.
2. Pour CHAQUE section ({sections_str}) : append_file(content=section) qui remplace/ajoute
   le contenu au bon endroit. Chaque appel ≤ 60 lignes, chaque bloc syntaxiquement complet.
3. Une fois toutes les sections injectées, ferme proprement (</body></html>).
4. final_answer quand c'est terminé."""
        elif strategy == "multifile":
            strategy_block = """### WORKFLOW (stratégie MULTIFILE imposée par l'Architect)
Construis chaque fichier cible de façon autonome (1 module logique = 1 fichier).
⚠️ CRITIQUE ET OBLIGATOIRE : Chaque fichier est écrit UNE SEULE FOIS via write_file avec son contenu COMPLET.
Si un draft Drafter est fourni, extrais son code via le script du skill `draft-extraction`, puis AMÉLIORE-le.
1. Étape 1 : Extrait le code du draft (skill draft-extraction) → write_file pour chaque fichier (contenu complet).
2. Étape 2 : RELIS chaque fichier (read_file) et AMÉLIORE-le en appliquant tes skills (frontend-design pour le
   design, coding pour les bonnes pratiques). Utilise search_replace/multi_replace pour les améliorations.
   Points d'amélioration OBLIGATOIRES pour un visualiseur : sync DOM après swap (bar.style.height), init du
   tableau au chargement (pas de barres vides), animation avec await sleep (pas setTimeout en rafale).
3. Teste l'interface visuellement (navigate_page + take_screenshot + list_console_messages).
4. final_answer quand tout marche (0 console error + barres visibles + tri fonctionnel).
🚫 JAMAIS append_file sur un fichier créé avec write_file → doublerait le contenu."""
        else:  # simple (défaut, rétro-compat)
            strategy_block = """### WORKFLOW (stratégie SIMPLE)
1. `write_file(path=..., content=...)` avec le contenu COMPLET du fichier. Un seul write_file par fichier.
2. Si un draft Drafter est fourni : extrais son code (skill draft-extraction), puis AMÉLIORE-le avec tes skills
   (frontend-design, coding) via search_replace/multi_replace. Points clés : sync DOM, init au chargement, animation await.
3. Teste visuellement (navigate_page + take_screenshot + list_console_messages). final_answer quand tout marche.
🚫 JAMAIS append_file sur un fichier créé avec write_file."""

        # F-45 : section preview visuelle (Chrome DevTools) — ACTIVE uniquement pour
        # les tâches web (HTML/CSS/JS). Pour les autres technos (Python), les outils
        # DevTools ne sont pas pertinents (pas de page à ouvrir dans un navigateur).
        # On détecte le web via router_lang OU extensions des target_files (défense en
        # profondeur : le routeur peut se tromper, les extensions non).
        devtools_preview_block, devtools_tools_doc = _build_devtools_blocks(task, effective_cdt_tools)

        prompt = f"""{build_role_header("coder")}
Tu DOIS produire du code en appelant tes outils via du PYTHON (CodeAgent). NE JAMAIS expliquer sans agir.

### RÈGLES CRITIQUES (numérotées)
1. AGIS, ne raconte pas : quand tu dis "je vais faire X", tu DOIS faire X dans la foulée.
   Une réponse sans appel d'outil est considérée comme une TÂCHE TERMINÉE (échec).
2. INTERDICTION ABSOLUE d'utiliser des backticks (`) dans ta pensée (Thought).
   Utilise-les UNIQUEMENT pour ouvrir et fermer le bloc de code ```python.
3. ARGUMENTS NOMMÉS OBLIGATOIRES : Pour TOUS tes appels d'outils, tu DOIS utiliser des arguments nommés (ex: evaluate_script(function="...")). Les arguments positionnels feront crasher l'exécution.
4. BLOCS COMPLETS : chaque appel write_file/append_file doit contenir un bloc SYNTAXIQUEMENT
   COMPLET (quotes/braces/parenthèses équilibrées). NE JAMAIS laisser une string/brace
   ouverte entre 2 appels. Si le contenu dépasse ~60 lignes, DÉCOUPE en plusieurs append_file.
5. PAS DE PLACEHOLDER : interdiction absolue de "TODO", "...", "Logique ici", fonctions vides
   ou mocks. Implémentation COMPLÈTE, RÉELLE et FONCTIONNELLE.
6. ANTI-DOUBLON : Chaque fichier cible ne doit être écrit qu'UNE SEULE FOIS via write_file.
   Pour MODIFIER un fichier existant → search_replace/multi_replace (JAMAIS write_file ni append_file).
   append_file UNIQUEMENT pour compléter un fichier incomplet (ex: squelette sans </html>).
   ❌ FAUX : write_file("index.html") puis append_file("index.html") → 2 pages collées !
   ✅ JUSTE : write_file("index.html") une fois, puis search_replace pour les modifs.
7. PYTHON BUILT-INS : Si tu utilises `time.sleep()` ou d'autres modules standards dans ton code Python, n'oublie pas de les importer (ex: `import time` au début du bloc).
8. FORMATAGE DES STRINGS (TRIPLE QUOTES) : Pour éviter les erreurs de parsing Python liées aux quotes (`'`) et accolades (`{{`) du code source (JS/CSS/HTML), tu DOIS TOUJOURS encadrer tes arguments `content`, `old_string`, et `new_string` par des triples guillemets : `r\"\"\"...\"\"\"` ou `'''...'''`. N'utilise JAMAIS de simples guillemets pour encadrer du code.
   ❌ FAUX : search_replace(path="x", old_string="function() {{ ... }}")
   ✅ JUSTE : search_replace(path="x", old_string=r\"\"\"function() {{ ... }}\"\"\", new_string=r\"\"\"function() {{ startSort(); }}\"\"\")
9. ANIMATION PAS-À-PAS (Visualiseurs/Algos) : Pour les visualisations d'algorithmes (tri, pathfinding, etc.), utilise TOUJOURS `async`/`await` avec une fonction `sleep` (ex: `const sleep = ms => new Promise(r => setTimeout(r, ms));`). N'utilise JAMAIS de boucle `while` ou `for` classique contenant un simple `setTimeout` asynchrone, cela exécute tout instantanément.
   ❌ FAUX : function sort() {{ while(swapped) {{ setTimeout(() => swap(), delay); }} }}
   ✅ JUSTE : async function sort() {{ while(swapped) {{ await sleep(delay); swap(); }} }}
10. VOIS LES RÉSULTATS DE TES OUTILS : une assignation `x = read_file(...)` retourne
   `None` (tu ne vois PAS le contenu). Pour LIRE un résultat, tu DOIS soit faire
   `print(read_file(path="..."))` soit appeler l'outil directement comme dernière
   expression du bloc (`read_file(path="...")` sans assignation). SANS le print,
   le contenu est INVISIBLE → tu boucleras en croyant que la lecture a échoué.
   ❌ FAUX : contenu = read_file(path="draft.md")  → Out: None (aveugle)
   ✅ JUSTE : print(read_file(path="draft.md"))    → Out: <le contenu>

### FORMAT DE SORTIE (obligatoire)
Tu écris du code Python dans un bloc ````python ... ```` qui appelle tes outils. Exemple one-shot :
```python
# Thought courte (1 phrase) PUIS appel immédiat — pas de longue réflexion
resultat = write_file(path="index.html", content=r\"\"\"<!DOCTYPE html>\\n<html>...</html>\"\"\")
print(resultat)
# Exemple search_replace avec code JS : utilise toujours des triples guillemets
fix = search_replace(path="index.html", old_string=r\"\"\"function() {{}}\"\"\", new_string=r\"\"\"function() {{ startSort(); }}\"\"\")
print(fix)
# ... autres appels ...
final_answer({{"task_id": "{task['id']}", "status": "success", "details": "Fichiers créés.", "linter_ok": True, "vision_ok": True}})
```
NOTE CRITIQUE : "linter_ok" doit être True SEULEMENT si tu as vérifié ton code via linter/test.
"vision_ok" doit être True SEULEMENT pour une UI ET si tu as pris un screenshot via take_screenshot. Sinon False.


        {strategy_block}
        {target_files_instruction}
        {devtools_preview_block}

### OUTILS DISPONIBLES
- `write_file(path, content)` : CRÉE un fichier complet (sous-dossiers créés auto). REFUSÉ sur un fichier EXISTANT de plus de ~100 lignes — la correction d'un gros fichier passe par search_replace/multi_replace.
- `append_file(path, content)` : AJOUTE un bloc à la FIN d'un fichier existant (garde anti-doublon).
- `multi_replace(path, replacements)` : MODIFIE un ou plusieurs fragments (matching tolérant). À utiliser après read_file.
- `search_replace(path, old_string, new_string)` : MODIFIE un fragment unique.
- `read_file(path)` / `list_directory(path)` : lecture/exploration.
- `context7` (resolve_library_id/query_docs) : UNIQUEMENT pour une lib externe (React, Chart.js...). JAMAIS pour du vanilla.
- Évite DuckDuckGoSearchTool (lent/imprécis).
{devtools_tools_doc}

### EXIGENCE DE QUALITÉ
Code prêt pour la production, respectant les conventions du langage.
{skills_block}{local_agents_md_block}

{task.get('plan_anchor', '')}### Contenu de la tâche
{task['content']}
{task.get('draft_instruction', '')}
""" + (f"\n### Contexte global (Rappel du cahier des charges initial)\n{task['original_content']}\n" if task.get("original_content") else "") + (
    f"\n{task['lessons']}\n" if task.get("lessons") else ""
) + """
### RAPPEL (récence)
- AGIS via des appels d'outils Python, ne raconte pas.
- Chaque bloc syntaxiquement complet, ≤ 60 lignes ou découpe via append_file.
- AUCUN placeholder. final_answer quand les fichiers cibles sont créés.
- Une erreur console = un bug LOCAL (stack trace fichier:ligne) : corrige via search_replace, JAMAIS en réécrivant tout le fichier.
- Après un fix : re-teste la PAGE (navigate_page + list_console_messages) AVANT de relire le code — seule la console prouve que l'erreur a disparu. Console propre → final_answer.
"""
        # P3 (Anti-Loop Cryptographique) : instancie un guard pour CETTE exécution
        # du Coder. Seul le Coder appelle des outils d'écriture → seul candidat
        # où la boucle "même tool call X fois" est un failure mode réel (le
        # failure mode classique : le modèle ré-écrit le même fichier à l'identique
        # en boucle jusqu'à épuisement des steps). Le guard est aussi réinitialisé
        # entre les retries dans run_with_retry (aligné sur la purge mémoire).
        guard = LoopGuard(
            threshold=settings.loop_guard_threshold,
            enabled=settings.loop_guard_enabled,
        )
        # P3-bis (F-88) : Stall Detector — complément du LoopGuard pour détecter
        # (a) un même contenu réécrit (hash d'output identique) et (b) une série de
        # turns sans livrable matériel nouveau. Orthogonal à F-36 (niveau turn vs
        # niveau tool call isolé). Reset entre retries (aligné sur loop_guard).
        stall = StallDetector(
            threshold=settings.stall_detector_threshold,
            enabled=settings.stall_detector_enabled,
        )
        # P3-ter (F-99) : Goal Enforcer — garde comportementale du faux « j'ai
        # fini ». Un final_answer valide est audité contre l'état autoritaire
        # (écritures + livrables sur disque + verify-after web). Contrairement
        # aux guards ci-dessus, son état (impasse, streak, tokens) VIT à travers
        # les retries : les rounds de continuation sont ce qu'on compte (qm
        # goal.ts GOAL_BLOCKED_MIN_ROUNDS=3 ↔ worker_max_retries=3).
        goal = GoalEnforcer(
            objective=(
                task.get("content")
                or task.get("description")
                or task.get("original_content")
                or ""
            ),
            target_files=task.get("target_files") or [],
            iteration=task.get("iteration", 1),
            is_web=_is_web_task(task),
            blocked_min_rounds=settings.goal_blocked_min_rounds,
            waiver_stalled_rounds=settings.goal_waiver_stalled_rounds,
            token_cap=settings.goal_token_cap,
            enabled=settings.goal_enforcement_enabled,
        )
        # F-109 : audit visuel matérialisé — reset pour CE run du nœud, et
        # comptage des critères F-90 que l'enforcement va exiger (0 = gate
        # inactive, ex. opt-out config ou tâche sans critères).
        reset_visual_audit()
        # F-126 : reset de la preuve durable de screenshot (même lifecycle que
        # l'audit visuel — traverse volontairement les retries de run_with_retry).
        reset_screenshot_proof()
        # F-114 : reset du compteur de screenshots du nudge checklist (même
        # lifecycle que l'audit visuel ; traverse volontairement les retries).
        # F-125 : reset du compteur anti-gel navigateur (même lifecycle).
        from .vision_callback import (
            reset_browser_stall,
            reset_nav_freeze_nudge,
            reset_read_stall,
            reset_screenshot_nudge,
        )
        reset_screenshot_nudge()
        reset_browser_stall()
        reset_nav_freeze_nudge()
        reset_read_stall()
        # P5/F-138 : reset du moniteur de résultats en boule (même lifecycle).
        try:
            from .tool_progress import reset_tool_progress

            reset_tool_progress()
        except Exception:
            pass
        # F-141 : reset du plafond de lectures identiques (même lifecycle).
        try:
            from .tools import reset_read_supply

            reset_read_supply()
        except Exception:
            pass
        # F-128 : reset de l'état « erreurs console en attente de re-vérification »
        # (même lifecycle que les autres resets vision).
        from .vision_callback import reset_console_pending
        reset_console_pending()
        _vc = task.get("visual_success_criteria") or []
        visual_criteria_count = (
            len([c for c in _vc if str(c).strip()]) if settings.visual_audit_enabled else 0
        )
        # max_retries can be slightly higher for coding since it involves tool use steps
        # max_retries can be slightly higher for coding since it involves tool use steps
        # F-111 CODER ULTRA : la CORRECTION (itération > 1) mérite le gros modèle
        # sans thinking. Constat run #7 : le 4B a reproduit le même bug (compteur
        # jamais incrémenté) sur 3 itérations en thrashant à max_steps — il exécute
        # mais ne CORRIGE pas. L'Ultra (Ornith-9B, reasoning=off) prend le relais
        # dès la 1re itération corrective ; la création (it. 1) reste sur le 4B
        # rapide. Opt-out CODER_ULTRA_CORRECTION=false.
        coder_spec, coder_max_tokens, _is_ultra = _select_coder_spec(task, settings)
        if _is_ultra:
            print(
                f"[⚡] CODER ULTRA (correction, itération {task.get('iteration', 1)}) : "
                f"{os.path.basename(coder_spec.model or '?')} (gros modèle no-think) "
                f"au lieu du 4B rapide."
            )
        with model_lifecycle(coder_spec) as srv:
            # F-104 : LoggedOpenAIServerModel (retry transport pré-contenu) +
            # revive=srv.revive — si le serveur spawné meurt mid-run (crash VRAM
            # observé run #4), il est re-spawné entre deux tentatives et le
            # client re-créé sur le nouveau port, SANS perdre la mémoire agent
            # (contrairement au retry de run_with_retry qui purge tout).
            dynamic_fast_model = LoggedOpenAIServerModel(
                model_id=srv.model_id or settings.fast_model_id,
                api_base=srv.api_base or settings.local_api_base,
                api_key=srv.api_key or settings.local_api_key,
                max_tokens=coder_max_tokens,
                temperature=settings.coder_temperature,
                # max_retries=0 : retry SDK openai désactivé, autorité = F-104.
                client_kwargs={"timeout": settings.llm_timeout_s, "max_retries": 0},
                revive=srv.revive,
            )
            from .compaction import CompactingCodeAgent
            local_coder = CompactingCodeAgent(
                tools=coder_tools,
                model=dynamic_fast_model,
                name=f"coder_{task['id'].replace('-', '_')}",
                description="Agent développeur capable d'explorer le projet, d'écrire, lire, modifier du code.",
                verbosity_level=resolve_verbosity("HIGH"),
                max_steps=settings.coder_max_steps,
                add_base_tools=False,
                code_block_tags="markdown",
                # F-114 : visual_criteria_count → le callback vision nourrit le
                # nudge checklist (rappel visual_check au 3e screenshot sans
                # audit complet). 0 par défaut (Tester : nudge inactif).
                step_callbacks=[make_screenshot_callback(
                    screenshot_capture, visual_criteria_count=visual_criteria_count
                )],
                additional_authorized_imports=["os", "subprocess"],
                executor_kwargs={"timeout_seconds": settings.tester_timeout_s},
            )
            return await run_with_retry(
                local_coder, prompt, CoderOutput, settings.worker_max_retries, loop_guard=guard,
                idle_breaker_threshold=settings.idle_breaker_threshold,
                stall_detector=stall,
                goal_enforcer=goal,
                visual_criteria_count=visual_criteria_count,
            )


async def execute_tester_node(
    task: dict,
    reasoning_model: OpenAIServerModel,
    settings: Settings,
) -> Tuple[Optional[CoderOutput], Optional[NodeMetrics]]:
    """Nœud Testeur POLYVALENT : dispatche vers le runner adapté à la techno.

    Historiquement, ce nœud était 100% dédié au web (MCP Puppeteer). Il est
    désormais techno-agnostique : il détecte la techno de la sous-tâche
    (détection redondante Router + extensions) puis route vers le bon runner
    (WebTestRunner, PythonTestRunner, ...). Fallback web si techno inconnue
    (compatibilité arrière).

    La logique spécifique à chaque techno vit dans `graph_orchestrator/testers/`.
    """
    from .testers import detect_tech, get_runner

    # La techno peut être déjà fournie structurellement (ex: propagated depuis le
    # routeur), sinon on la détecte depuis les extensions + le lang routeur.
    tech = task.get("tech") or detect_tech(task, task.get("router_lang"))

    print(f"[*] Tester polyvalent : techno détectée = '{tech}' pour {task.get('id')}")

    runner = get_runner(tech)
    return await runner.run(task, reasoning_model, settings)


# ==========================================
# Nœud Reduce (§3 : flatten + dedupe + filter, code pur, 0 token)
# ==========================================

def execute_reduce_node(
    worker_results: List[WorkerOutput],
) -> ReduceOutput:
    """Nœud Reduce : déduplique sur task_id et filtre les None/doublons.

    Code déterministe, aucun appel LLM. Implémente le pattern du guide §3 :
    on garde la première occurrence de chaque task_id, on jette le reste.
    """
    seen_ids: set[str] = set()
    kept: List[WorkerOutput] = []
    dropped = 0
    for r in worker_results:
        if r is None or r.task_id in seen_ids:
            dropped += 1
            continue
        seen_ids.add(r.task_id)
        kept.append(r)
    return ReduceOutput(
        kept=kept,
        dropped_count=dropped,
        reason=f"Dédupliqué sur task_id ; {dropped} doublon(s)/None écarté(s).",
    )


async def execute_judge_node(
    worker_results: List[WorkerOutput],
    original_tasks: List[dict],
    reasoning_model: OpenAIServerModel,
    settings: Settings,
) -> Tuple[Optional[JudgeOutput], Optional[NodeMetrics]]:
    """Nœud Juge : évaluation QUALITATIVE (fidélité, actionnabilité), pas seulement le score.

    Reçoit les tâches originales pour comparer le summary du worker au contenu source,
    et détecter les hallucinations ou summaries creux/incohérents.
    """
    local_judge = ToolCallingAgent(
        tools=[],
        model=reasoning_model,
        name="judge",
        description="Juge impitoyable : évalue fidélité et actionnabilité des summaries.",
        verbosity_level=resolve_verbosity("HIGH"),  # séquentiel : verbose OK
    )

    # Map task_id -> contenu original pour permettre la comparaison fidélité.
    original_by_id = {t["id"]: t["content"] for t in original_tasks}

    prompt = f"""Tu es un juge expert en monitoring/DevOps. Pour chaque résultat de worker, évalue sa QUALITÉ RÉELLE,
pas seulement le confidence_score. Tu reçois le contenu original de chaque tâche pour comparer.

Pour chaque tâche, vérifie 3 critères :
1. FIDÉLITÉ : le summary reflète-t-il fidèlement le contenu original ? (rejeter si hallucination, contresens, ou omission de l'info clé)
2. ACTIONNABILITÉ : le summary est-il diagnostique et utile ? (rejeter s'il est creux, générique, ou se contente de paraphraser la consigne)
3. CONFIANCE : confidence_score >= {settings.judge_confidence_threshold} ? (rejeter si inférieur)

Retourne ton verdict STRICTEMENT au format JSON via l'outil 'final_answer'.
Schéma exact attendu : {{
  "is_valid": true,
  "reason": "résumé global du verdict",
  "approved_tasks": ["task_id1", "task_id2"],
  "assessments": [
    {{"task_id": "t1", "verdict": "approved", "reason": "fidèle et actionnable"}},
    {{"task_id": "t2", "verdict": "rejected", "reason": "hallucination sur la cause"}}
  ]
}}
Une tâche est rejetée si elle échoue à L'UN AU MOINS des 3 critères.
Si toutes les tâches sont rejetées, is_valid = false. Si au moins une est approuvée, is_valid = true.

Résultats des workers : {json.dumps([r.model_dump() for r in worker_results], ensure_ascii=False)}
Contenus originaux : {json.dumps(original_by_id, ensure_ascii=False)}
"""
    return await run_with_retry(local_judge, prompt, JudgeOutput, settings.worker_max_retries, idle_breaker_threshold=10**9)


async def execute_synth_node(
    approved_data: List[WorkerOutput],
    reasoning_model: OpenAIServerModel,
    settings: Settings,
) -> Tuple[Optional[FinalSynthesis], Optional[NodeMetrics]]:
    """Nœud de Synthèse : agrège les résultats approuvés."""
    local_synth = ToolCallingAgent(
        tools=[],
        model=reasoning_model,
        name="synth",
        description="Synthétise les résultats approuvés en un résumé global + insights clés.",
        verbosity_level=resolve_verbosity("HIGH"),
    )

    prompt = f"""Tu es un synthétiseur expert. Rédige une synthèse globale à partir des données fournies et retourne-la STRICTEMENT au format JSON via l'outil 'final_answer'.

RÈGLES :
- CONCISION : privilégie la prose dense aux listes à rallonge. 1-2 paragraphes pour le
  global_summary suffisent la plupart du temps.
- SOLUTION-FIRST : énonce d'abord la synthèse/le point clé, puis le détail si utile.
- HONNÊTETÉ : si une donnée validée est absente/incomplète, dis-le clairement. N'invente
  jamais un résumé pour combler un trou.
- KEY_INSIGHTS : 2-4 insights vraiment actionnables (pas des paraphrases du résumé).

Schéma exact attendu : {{"global_summary": "ton résumé global des problèmes", "key_insights": ["insight 1", "insight 2"]}}
Données validées : {json.dumps([r.model_dump() for r in approved_data], ensure_ascii=False)}
"""
    return await run_with_retry(local_synth, prompt, FinalSynthesis, settings.worker_max_retries, idle_breaker_threshold=10**9)


# ==========================================
# Nœud Adversaire (§5 : flotte de N sceptiques indépendants)
# ==========================================

# Personas divergents : chacun cherche une faille différente pour forcer le désaccord.
_ADVERSARY_PERSONAS = [
    "Tu es un détecteur d'hallucinations : traque toute affirmation du summary NON justifiée par le contenu original.",
    "Tu es un vérificateur de contre-sens : cherche les interprétations erronées ou inversion du sens des chiffres/mots.",
    "Tu es un chasseur d'omissions : identifie les informations CLÉS du contenu original absentes du summary.",
    "Tu es un critique d'actionnabilité : rejette si le summary est creux, générique, ou paraphrase la consigne sans diagnostiquer.",
    "Tu es un contrôleur de cohérence : cherche les contradictions internes du summary ou scores absurdes.",
]


async def execute_adversary_node(
    worker_results: List[WorkerOutput],
    original_tasks: List[dict],
    reasoning_model: OpenAIServerModel,
    settings: Settings,
) -> Tuple[Optional[List[AdversaryVerdict]], Optional[List[NodeMetrics]]]:
    """Lance N sceptiques en parallèle pour tenter de réfuter chaque tâche.

    Renvoie (liste_agrégée_de_verdicts, liste_de_métriques). Chaque sceptique évalue
    TOUTES les tâches d'un coup ; les verdicts sont ensuite agrégés par vote (cf.
    aggregate_adversary_verdicts dans le runner).
    """
    original_by_id = {t["id"]: t["content"] for t in original_tasks}
    n = max(1, settings.adversary_count)
    personas = [_ADVERSARY_PERSONAS[i % len(_ADVERSARY_PERSONAS)] for i in range(n)]

    async def run_one_skeptic(idx: int, persona: str):
        # name doit être un identifiant Python valide ; verbosity HIGH (séquentiel après fan-out).
        skeptic = ToolCallingAgent(
            tools=[],
            model=reasoning_model,  # partagé entre sceptiques — sûr (aucun état mutable muté)
            name=f"skeptic_{idx}",
            description="Sceptique indépendant qui tente de réfuter les summaries.",
            verbosity_level=resolve_verbosity("HIGH"),
        )
        prompt = f"""{persona}

Pour chaque résultat de worker ci-dessous, décide si tu PEUX le réfuter (refuted=true) ou non (refuted=false).
Un summary est réfutable s'il contient une hallucination, un contre-sens, une omission clé, ou manque d'actionnabilité.

Retourne ton verdict STRICTEMENT en utilisant l'outil 'final_answer'.
Ton JSON DOIT absolument respecter ce format exact pour appeler l'outil final_answer :
{{
  "name": "final_answer",
  "arguments": {{
    "answer": {{
      "verdicts": [
        {{"task_id": "t1", "refuted": false, "reason": "fidèle au contenu"}},
        {{"task_id": "t2", "refuted": true, "reason": "hallucination : chiffre inventé"}}
      ]
    }}
  }}
}}

Résultats des workers : {json.dumps([r.model_dump() for r in worker_results], ensure_ascii=False)}
Contenus originaux : {json.dumps(original_by_id, ensure_ascii=False)}
"""
        # run_with_retry attend un contrat à un seul objet ; on enveloppe la liste dans un contrat wrapper.
        validated, metrics = await run_with_retry(
            skeptic, prompt, _AdversaryBatch, settings.worker_max_retries, idle_breaker_threshold=10**9
        )
        return validated, metrics

    pairs = await asyncio.gather(*[run_one_skeptic(i, p) for i, p in enumerate(personas)])

    # Aplatit les verdicts de tous les sceptiques + collecte les métriques
    all_verdicts: List[AdversaryVerdict] = []
    all_metrics: List[NodeMetrics] = []
    for batch, metrics in pairs:
        if batch is not None:
            all_verdicts.extend(batch.verdicts)
        if metrics is not None:
            all_metrics.append(metrics)
    return all_verdicts, all_metrics


class _AdversaryBatch(BaseModel):
    """Contrat wrapper : un sceptique renvoie une liste de verdicts."""
    verdicts: List[AdversaryVerdict]


def aggregate_adversary_verdicts(
    verdicts: List[AdversaryVerdict],
    worker_results: List[WorkerOutput],
    adversary_count: int,
    threshold: float,
) -> JudgeOutput:
    """Logique PURE de vote : une tâche est rejetée si >= threshold*N sceptiques l'ont réfutée.

    threshold=0.5 (défaut) => majorité requise pour réfuter.
    Construit un JudgeOutput (assessments agrégés) — pas d'appel LLM.
    """
    # Compte les réfutations par task_id
    refute_counts: dict[str, int] = {}
    reasons_by_task: dict[str, List[str]] = {}
    for v in verdicts:
        if v.refuted:
            refute_counts[v.task_id] = refute_counts.get(v.task_id, 0) + 1
        reasons_by_task.setdefault(v.task_id, []).append(v.reason)

    needed_to_reject = adversary_count * threshold  # ex: 3 * 0.5 = 1.5 => >=2 pour réfuter

    assessments: List[TaskAssessment] = []
    approved_tasks: List[str] = []
    for w in worker_results:
        refutes = refute_counts.get(w.task_id, 0)
        if refutes >= needed_to_reject:
            assessments.append(TaskAssessment(
                task_id=w.task_id,
                verdict="rejected",
                reason=f"{refutes}/{adversary_count} sceptiques l'ont réfutée : "
                       + " | ".join(reasons_by_task.get(w.task_id, []))[:200],
            ))
        else:
            assessments.append(TaskAssessment(
                task_id=w.task_id,
                verdict="approved",
                reason=f"{refutes}/{adversary_count} réfutations (sous le seuil {threshold}).",
            ))
            approved_tasks.append(w.task_id)

    return JudgeOutput(
        is_valid=len(approved_tasks) > 0,
        reason=f"Vote adversaire : {len(approved_tasks)}/{len(worker_results)} approuvées.",
        approved_tasks=approved_tasks,
        assessments=assessments,
    )


# NOTE: hitl_checkpoint a été déplacé vers graph_orchestrator/hitl.py (HITL stratégique,
# Phase 6) avec un routage conditionnel (should_trigger_hitl) et un affichage de provenance.
