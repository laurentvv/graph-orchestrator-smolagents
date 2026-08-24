"""Tests F-165 : intégrité de l'ENREGISTREMENT des verdicts (post-mortem 021543).

Run 2026-08-24_021543 (F164-6, coupé comme faussé) : la réfutation KG lue par
le Coder en itération 2 (claim 255) était dupliquée, tronquée et mensongère.
Chaîne prouvée :
1. Tester step 5 : code-mode émet write_file(probe1.js) → l'interpréteur pydantic
   rejette « InterpreterError: Forbidden function evaluation ». L'EN-TÊTE
   multi-lignes « Code execution failed at line '…' » matche le marqueur FAIL
   "failed" sans être dans _TESTER_TOOL_ERROR_MARKERS → erreur d'OUTIL classée
   « assertion en échec » de l'app.
2. snippet = première ligne FAIL [:300] → amputé au milieu de l'écho de code,
   l'exception réelle (« due to: … » arrive après) est perdue.
3. Le fail-closed (dspy_nodes) embarque déjà 🎯 CAUSE RACINE / 🛠️ INSTRUCTION
   dans final_feedback ; le wrapper workflows.py les ré-empilait → réfutation
   dupliquée en base.

Fixes testés (0-LLM, fonctions pures) :
- A) marqueur « code execution failed » + exclusion PAR BLOC des step.error ;
- B) snippet = segment « due to: … » (±3 lignes de la première ligne FAIL),
    cap 300 avec ellipsis explicite ;
- C) build_rejection_feedback : jamais de double embedding.
"""

from types import SimpleNamespace

from graph_orchestrator.feedback_utils import build_rejection_feedback
from graph_orchestrator.nodes import _tester_max_steps_fallback

_PROMPT = 'final_answer({"task_id": "bubble-sort-visualizer", "status": "success", "details": "..."})'


def _step(obs: str = "", err: str = ""):
    return SimpleNamespace(observations=obs or None, error=err or None)


# L'erreur d'outil EXACTE du run 021543 (step 5 du Tester) : en-tête + écho de
# code multi-lignes + exception en queue de bloc.
_RUN21543_ERROR = '''Code execution failed at line 'write_file(path="probe1.js", content="""async () => {
  const startBtn = document.getElementById('start-btn');
  const resetBtn = document.getElementById('reset-btn');
  const slider = document.getElementById('speed-slider');
  return JSON.stringify({ start: !!startBtn, reset: !!resetBtn, slider: !!slider });
}""")' due to: InterpreterError: Forbidden function evaluation: 'write_file' is not among the explicitly allowed tools or defined/imported in the preceding code'''


# ==========================================
# Fix A — erreurs d'outils ≠ FAIL de l'app (par BLOC)
# ==========================================

class TestFixABlockExclusion:

    def test_run21543_write_file_block_not_a_fail(self):
        """Le cas exact du run faussé : write_file interprêt comme échec d'assertion.

        Avant F-165-A : l'en-tête « Code execution failed… » matchait "failed"
        → failure → Judge fail-closed → itération 2 sur un bug fantôme.
        """
        steps = [
            _step(err=_RUN21543_ERROR),
            _step('{"start": true, "reset": true, "slider": true} — assertion passed'),
        ]
        out = _tester_max_steps_fallback(steps, _PROMPT)
        assert out is not None and out.status == "success"

    def test_header_only_code_execution_failed_excluded(self):
        """Variante : l'en-tête seul (sans queue d'exception) dans une observation."""
        steps = [
            _step("Out: evaluate | Code execution failed at line 'write_file(path=\"probe1.js\"'"),
            _step("verdict: pass — les 3 boutons répondent"),
        ]
        out = _tester_max_steps_fallback(steps, _PROMPT)
        assert out is not None and out.status == "success"

    def test_block_excluded_when_marker_on_later_line(self):
        """Sémantique BLOC : le marqueur d'outil peut être sur une ligne suivante.

        Avant F-165-A : ligne 1 (« …failed ») fuyait le filtre ligne par ligne.
        """
        err = "Comparison against reference failed\nNameError: name 'probe2' is not defined"
        steps = [
            _step(err=err),
            _step("status: pass — tableau trié vérifié"),
        ]
        out = _tester_max_steps_fallback(steps, _PROMPT)
        assert out is not None and out.status == "success"

    def test_genuine_app_error_still_fails(self):
        """Garde anti-sur-correction : une vraie erreur de l'app reste un FAIL."""
        steps = [
            _step("Console: [error] Uncaught TypeError: bars.forEach is not a function"),
        ]
        out = _tester_max_steps_fallback(steps, _PROMPT)
        assert out is not None and out.status == "failure"


# ==========================================
# Fix B — le snippet porte l'exception, pas l'écho de code
# ==========================================

class TestFixBSnippetExtraction:

    def test_due_to_extracted_same_line(self):
        obs = "Assertion failed: le compteur ne s'incrémente pas due to: TypeError: cannot read 'counter' of null"
        out = _tester_max_steps_fallback([_step(obs)], _PROMPT)
        assert out is not None and out.status == "failure"
        assert "TypeError: cannot read 'counter' of null" in out.details
        assert "Assertion failed: le compteur" not in out.details

    def test_due_to_extracted_next_line(self):
        steps = [_step(
            "assertion failed: le bouton Start ne déclenche rien\n"
            "due to: TimeoutError: l'animation n'a jamais démarré"
        )]
        out = _tester_max_steps_fallback(steps, _PROMPT)
        assert out is not None and out.status == "failure"
        assert "TimeoutError: l'animation n'a jamais démarré" in out.details

    def test_snippet_capped_with_ellipsis(self):
        big = "x" * 500
        out = _tester_max_steps_fallback([_step(f"assertion failed: {big}")], _PROMPT)
        assert out is not None and out.status == "failure"
        assert len(out.details.split("— ", 1)[1]) <= 300
        assert out.details.endswith("…")


# ==========================================
# Fix C — feedback de rejet sans double embedding
# ==========================================

class TestFixCRejectionFeedback:

    def _fail_closed(self):
        """Reproduit le CodeJudgeOutput du chemin fail-closed (dspy_nodes)."""
        rc = "Échec des tests fonctionnels (le nœud Tester a rapporté un ÉCHEC fonctionnel)"
        fi = "Corriger les échecs fonctionnels rapportés par l'agent QA."
        return SimpleNamespace(
            root_cause=rc,
            fix_instruction=fi,
            final_feedback=(
                "APPROBATION BLOQUÉE (fail-closed test) : le nœud Tester a rapporté un ÉCHEC fonctionnel.\n"
                f"🎯 CAUSE RACINE : {rc}\n"
                f"🛠️ INSTRUCTION DE CORRECTION : {fi}\n"
                "Détails du Tester : …"
            ),
        )

    def test_fail_closed_not_rewrapped(self):
        """Claim 255 : le wrapper ré-empilait → CAUSE RACINE présente 2× en KG."""
        judge = self._fail_closed()
        fb = build_rejection_feedback(judge)
        assert fb == judge.final_feedback
        assert fb.count("🎯 CAUSE RACINE") == 1

    def test_normal_judge_wrapped_once(self):
        """Judge LLM normal (feedback brut sans blocs) : wrap historique préservé."""
        judge = SimpleNamespace(
            root_cause="RC",
            fix_instruction="FI",
            final_feedback="rapport du juge",
        )
        fb = build_rejection_feedback(judge)
        assert fb == "🎯 CAUSE RACINE : RC\n🛠️ INSTRUCTION DE CORRECTION : FI\n📝 FEEDBACK : rapport du juge"

    def test_none_judge_res_keeps_historical_message(self):
        assert build_rejection_feedback(None) == "Erreur système du juge."

    def test_feedback_only_passthrough(self):
        judge = SimpleNamespace(root_cause="", fix_instruction="", final_feedback="seul feedback")
        assert build_rejection_feedback(judge) == "seul feedback"

    def test_all_empty_fields_returns_system_message(self):
        """Divergence délibérée vs l'ancien code inline (review Kilo PR #117).

        Avant : judge_res vide → "" stocké comme contenu de réfutation KG →
        dedup_key SHA1 CONSTANT → tout ticket vide suivant ignoré par la dédup.
        Un ticket vide n'est pas un signal exploitable pour le Coder.
        """
        judge = SimpleNamespace(root_cause="", fix_instruction="", final_feedback="")
        assert build_rejection_feedback(judge) == "Erreur système du juge."
        judge_none_fb = SimpleNamespace(root_cause="", fix_instruction="", final_feedback=None)
        assert build_rejection_feedback(judge_none_fb) == "Erreur système du juge."
