"""Tests F-101 — Compaction v2 : archive disque + persisted-output + garde-fous.

Couvre les 5 volets de la fusion (plan P9, case « Compaction v2 — alignée
petits modèles + anti-boucle de compaction ») :
(1) prompts opencode petits modèles (compaction_prompts.py) ;
(2) archive disque s08 (transcripts JSONL + <persisted-output> + micro v2) ;
(3) garde overflow pi §3.9 (OverflowGuard + branchement run_with_retry) ;
(4) fold claude-science (règles search queries + frame survivant) ;
(5) budget hermes remboursé sur usage vérifié (CompactionBudget).
"""

import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from smolagents import AgentMemory, CodeAgent
from smolagents.agents import ActionStep, TaskStep
from smolagents.monitoring import Timing

from graph_orchestrator.compaction import (
    ARCHIVE_MARKER_RE,
    CompactingCodeAgent,
    apply_micro_compact,
    apply_snip_compact,
    apply_tool_result_budget,
    archive_steps,
    persist_large_output,
)
from graph_orchestrator.compaction_guards import (
    CompactionBudget,
    OverflowGuard,
    is_context_overflow_error,
)
from graph_orchestrator.compaction_prompts import (
    FOLD_KEY_RULES,
    SUMMARY_SYSTEM_PROMPT,
    SUMMARY_TEMPLATE,
    SUMMARY_UPDATE_INSTRUCTIONS,
    build_summary_prompt,
    select_head_recent,
)


# ---------- Fixtures ----------

def _make_memory(n_steps: int = 0, task: str = "Construire un visualiseur") -> AgentMemory:
    mem = AgentMemory(system_prompt={"role": "system", "content": "You are a coder."})
    mem.steps.append(TaskStep(task=task))
    now = time.time()
    for i in range(1, n_steps + 1):
        s = ActionStep(step_number=i, timing=Timing(start_time=now, end_time=now))
        s.model_output = f"thought {i}"
        s.observations = f"obs {i}"
        mem.steps.append(s)
    return mem


def _make_step(i: int, observations: str = "obs", model_output: str = "") -> ActionStep:
    now = time.time()
    s = ActionStep(step_number=i, timing=Timing(start_time=now, end_time=now))
    s.model_output = model_output
    s.observations = observations
    return s


# ---------- (2) archive_steps : JSONL perte-zéro ----------

class TestArchiveSteps:
    def test_ecrit_jsonl_une_ligne_par_step(self, tmp_path):
        steps = [_make_step(1, "contenu 1"), _make_step(2, "contenu 2")]
        path = archive_steps(steps, tmp_path / ".transcripts")
        assert path is not None and path.exists()
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["step_number"] == 1
        assert first["observations"] == "contenu 1"

    def test_sans_dir_retourne_none(self):
        assert archive_steps([_make_step(1)], None) is None

    def test_steps_vides_retourne_none(self, tmp_path):
        assert archive_steps([], tmp_path / ".transcripts") is None

    def test_unicite_uuid_deux_archives_differents(self, tmp_path):
        d = tmp_path / ".transcripts"
        p1 = archive_steps([_make_step(1)], d)
        p2 = archive_steps([_make_step(2)], d)
        assert p1 != p2

    def test_champ_non_serialisable_converti_sans_crash(self, tmp_path):
        class Weird:
            def __str__(self):
                return "<weird>"

        s = _make_step(1)
        s.task = Weird()  # attribut exotique → str() de défense
        path = archive_steps([s], tmp_path / ".transcripts")
        assert path is not None
        data = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        assert data["task"] == "<weird>"

    def test_tool_calls_serialises(self, tmp_path):
        s = _make_step(1)
        s.tool_calls = [{"name": "write_file", "arguments": {"path": "x"}}]
        path = archive_steps([s], tmp_path / ".transcripts")
        data = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        assert data["tool_calls"][0]["name"] == "write_file"


# ---------- (2) apply_snip_compact v2 : archive + chaînage + frame ----------

class TestSnipArchive:
    def test_marqueur_s08_avec_chemin_et_archive(self, tmp_path):
        mem = _make_memory(n_steps=17)
        d = tmp_path / ".transcripts"
        apply_snip_compact(mem, max_steps=15, transcript_dir=d)
        markers = [s for s in mem.steps if "messages archived at" in str(getattr(s, "model_output", ""))]
        assert len(markers) == 1
        m = ARCHIVE_MARKER_RE.search(markers[0].model_output)
        assert m is not None
        archived_path = Path(m.group(2))
        assert archived_path.exists()
        # 17 steps + 1 task = 18 ; head 3, tail 12 → 3 snippés
        assert int(m.group(1)) == 3
        assert len(archived_path.read_text(encoding="utf-8").splitlines()) == 3

    def test_retrocompat_sans_dir_marqueur_historique(self):
        mem = _make_memory(n_steps=17)
        apply_snip_compact(mem, max_steps=15, transcript_dir=None)
        markers = [s for s in mem.steps if "Snipped" in str(getattr(s, "model_output", ""))]
        assert len(markers) == 1
        assert "archived at" not in markers[0].model_output

    def test_chainage_archives_precedentes_survivent(self, tmp_path):
        d = tmp_path / ".transcripts"
        # 1er snip : produit une archive
        mem = _make_memory(n_steps=17)
        apply_snip_compact(mem, max_steps=15, transcript_dir=d)
        # On régénère assez de steps pour re-snipper (le marqueur du 1er snip
        # est en position 3 = DANS la zone snippée du second passage).
        now = time.time()
        for i in range(18, 40):
            s = ActionStep(step_number=i, timing=Timing(start_time=now, end_time=now))
            s.model_output = f"thought {i}"
            s.observations = "obs"
            mem.steps.append(s)
        apply_snip_compact(mem, max_steps=15, transcript_dir=d)
        markers = [s for s in mem.steps if "archived at" in str(getattr(s, "model_output", ""))]
        assert len(markers) == 1
        # Le marqueur final reporte l'archive précédente (chaînage opencode :
        # rien n'échappe aux compactions successives)
        assert "Earlier archives kept:" in markers[0].model_output
        assert len(list(d.iterdir())) == 2  # 2 archives distinctes

    def test_frame_survit_au_snip(self, tmp_path):
        mem = _make_memory(n_steps=17)
        apply_snip_compact(
            mem, max_steps=15, transcript_dir=tmp_path / ".transcripts",
            frame=["hypothèse A invalide", "fichier clé: runs/x/index.html"],
        )
        markers = [s for s in mem.steps if "archived at" in str(getattr(s, "model_output", ""))]
        assert "FRAME" in markers[0].model_output
        assert "hypothèse A invalide" in markers[0].model_output
        assert "runs/x/index.html" in markers[0].model_output

    def test_noop_sous_le_seuil(self, tmp_path):
        mem = _make_memory(n_steps=10)
        before = list(mem.steps)
        apply_snip_compact(mem, max_steps=15, transcript_dir=tmp_path / ".transcripts")
        assert mem.steps == before


# ---------- (2) persist_large_output : bloc <persisted-output> ----------

class TestPersistLargeOutput:
    def test_sous_seuil_inchange(self, tmp_path):
        out = persist_large_output("s1", "court", tmp_path / "out")
        assert out == "court"

    def test_au_dessus_bloc_persisted_avec_preview(self, tmp_path):
        big = "X" * 35_000
        out = persist_large_output("s1", big, tmp_path / "out")
        assert out.startswith("<persisted-output>")
        assert f"Full output: {tmp_path / 'out' / 's1.txt'}" in out
        assert "Preview:" in out
        # Le fichier contient l'intégralité (perte zéro)
        assert (tmp_path / "out" / "s1.txt").read_text(encoding="utf-8") == big
        # Le bloc est BEAUCOUP plus court que l'original
        assert len(out) < 2_500

    def test_identifier_sanitise(self, tmp_path):
        out = persist_large_output("step../../1 ?*", "Y" * 31_000, tmp_path / "out")
        files = list((tmp_path / "out").iterdir())
        assert len(files) == 1
        assert "/" not in files[0].name and "?" not in files[0].name

    def test_sans_dir_inchange(self):
        assert persist_large_output("s1", "Z" * 40_000, None) == "Z" * 40_000

    def test_fichier_existant_pas_reecrit(self, tmp_path):
        d = tmp_path / "out"
        d.mkdir()
        (d / "s1.txt").write_text("ANCIEN", encoding="utf-8")
        persist_large_output("s1", "N" * 31_000, d)
        assert (d / "s1.txt").read_text(encoding="utf-8") == "ANCIEN"


# ---------- (2) apply_tool_result_budget v2 : persist avant tronquer ----------

class TestToolResultBudgetV2:
    def test_persist_au_lieu_de_tronquer(self, tmp_path):
        mem = _make_memory()
        big = "A" * 5_000
        mem.steps.append(_make_step(1, big))
        mem.steps.append(_make_step(2, big))
        apply_tool_result_budget(mem, max_bytes=4_000, outputs_dir=tmp_path / "out")
        obs1 = str(mem.steps[1].observations)
        assert "<persisted-output>" in obs1
        assert "Full output: " in obs1
        # Perte zéro : le contenu intégral est sur disque
        persisted_files = list((tmp_path / "out").iterdir())
        assert any(f.read_text(encoding="utf-8") == big for f in persisted_files)

    def test_retrocompat_sans_dir_troncature_historique(self):
        mem = _make_memory()
        big = "A" * 5_000
        mem.steps.append(_make_step(1, big))
        mem.steps.append(_make_step(2, big))
        apply_tool_result_budget(mem, max_bytes=4_000, outputs_dir=None)
        assert "Output truncated due to context budget" in str(mem.steps[1].observations)

    def test_petit_output_inchange(self, tmp_path):
        mem = _make_memory()
        mem.steps.append(_make_step(1, "ok"))
        mem.steps.append(_make_step(2, "ok"))
        apply_tool_result_budget(mem, max_bytes=80_000, outputs_dir=tmp_path / "out")
        assert mem.steps[1].observations == "ok"


# ---------- (2) apply_micro_compact v2 : réutilise les chemins persistés ----------

class TestMicroCompactV2:
    def test_reutilise_chemin_persiste(self):
        mem = _make_memory()
        path = "/run/.task_outputs/tool-results/step_1.txt"
        # Preview > threshold (150) pour que la réduction s'applique
        block = (
            "<persisted-output>\n"
            f"Full output: {path}\n"
            "Preview:\n" + "x" * 400 + "\n</persisted-output>"
        )
        mem.steps.append(_make_step(1, block))
        for i in range(2, 8):
            mem.steps.append(_make_step(i, "recent"))
        apply_micro_compact(mem)
        assert str(mem.steps[1].observations) == f"[Earlier tool result saved at {path}]"

    def test_sans_chemin_placeholder_historique(self):
        mem = _make_memory()
        mem.steps.append(_make_step(1, "un très long output sans chemin persisté " * 10))
        for i in range(2, 8):
            mem.steps.append(_make_step(i, "recent"))
        apply_micro_compact(mem)
        assert "Compacted" in str(mem.steps[1].observations)

    def test_recent_epargne(self):
        mem = _make_memory()
        mem.steps.append(_make_step(1, "recent gros output intact " * 20))
        mem.steps.append(_make_step(2, "recent"))
        mem.steps.append(_make_step(3, "recent"))
        apply_micro_compact(mem, keep_recent=3, threshold=150)
        assert "Compacted" not in str(mem.steps[1].observations)


# ---------- (4) frame scratchpad sur l'agent ----------

class TestCompactingCodeAgentFrame:
    def test_context_frame_initialise_et_survit(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # CodeAgent complet sans LLM réel : on patche la sérialisation parente
        # (le super().write_memory_to_messages reconstruit les messages finaux).
        captured = {}

        def fake_super(self, summary_mode=False):
            captured["steps"] = list(self.memory.steps)
            return [{"role": "user", "content": "ok"}]

        with patch.object(CodeAgent, "write_memory_to_messages", fake_super):
            agent = CompactingCodeAgent.__new__(CompactingCodeAgent)
            agent.memory = _make_memory(n_steps=17)
            agent.context_frame = ["note qui doit survivre"]
            agent.write_memory_to_messages()

        markers = [s for s in captured["steps"] if "archived at" in str(getattr(s, "model_output", ""))]
        assert len(markers) == 1
        assert "note qui doit survivre" in markers[0].model_output
        # L'archive vit dans le run dir (cwd, chdir F-40)
        assert (tmp_path / ".transcripts").exists()

    def test_opt_out_settings_desactive_archive(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        import dataclasses

        from graph_orchestrator import config as config_module

        monkeypatch.setattr(
            config_module,
            "settings",
            dataclasses.replace(config_module.settings, compaction_archive_enabled=False),
        )

        def fake_super(self, summary_mode=False):
            return []

        with patch.object(CodeAgent, "write_memory_to_messages", fake_super):
            agent = CompactingCodeAgent.__new__(CompactingCodeAgent)
            agent.memory = _make_memory(n_steps=17)
            agent.context_frame = []
            agent.write_memory_to_messages()

        assert not (tmp_path / ".transcripts").exists()
        markers = [s for s in agent.memory.steps if "Snipped" in str(getattr(s, "model_output", ""))]
        assert len(markers) == 1  # marqueur historique


# ---------- (1) prompts opencode petits modèles + (4) règles fold ----------

class TestPrompts:
    def test_identite_simple_anti_derive(self):
        assert "You are a context summarization agent" in SUMMARY_SYSTEM_PROMPT
        assert "Do not continue the conversation" in SUMMARY_SYSTEM_PROMPT
        assert "same language as the conversation" in SUMMARY_SYSTEM_PROMPT

    def test_template_5_sections_et_regles(self):
        for section in ("## Objective", "## Important Details", "## Work State",
                        "## Next Move", "## Relevant Files"):
            assert section in SUMMARY_TEMPLATE
        assert "Keep every section, even when empty" in SUMMARY_TEMPLATE
        assert "Preserve exact file paths" in SUMMARY_TEMPLATE

    def test_regles_update_verbatim(self):
        assert "anything you do not carry into the new summary is lost" in SUMMARY_UPDATE_INSTRUCTIONS
        assert "the conversation wins" in SUMMARY_UPDATE_INSTRUCTIONS

    def test_regles_fold_claude_science(self):
        assert "SEARCH QUERIES" in FOLD_KEY_RULES
        assert "never reconstruct a value from memory" in FOLD_KEY_RULES.lower()

    def test_build_prompt_sans_prior(self):
        p = build_summary_prompt("la conversation")
        assert "<conversation>\nla conversation\n</conversation>" in p
        assert "<prior-summary>" not in p

    def test_build_prompt_avec_prior_ordre_fidele(self):
        p = build_summary_prompt("ctx", prior_summary="ancien résumé")
        assert "<prior-summary>\nancien résumé\n</prior-summary>" in p
        # Ordre opencode : conversation < prior-summary < update instructions < template
        i_conv, i_prior = p.index("<conversation>"), p.index("<prior-summary>")
        i_upd, i_tpl = p.index("anything you do not carry"), p.index("Output exactly the Markdown")
        assert i_conv < i_prior < i_upd < i_tpl

    def test_select_head_recent_entree_entiere_jamais_coupee(self):
        # Invariant opencode : une entrée qui déborde du budget reste ENTIÈRE
        # (elle bascule côté head à résumer), jamais coupée en deux.
        big = "user entry tres longue " * 30
        entries = ["a" * 100, big, "b" * 100, "c" * 50]
        result = select_head_recent(entries, keep_chars=250)
        assert result is not None
        head, recent = result
        # Parcours inverse : "c" (52) puis "b" (152) tiennent ; la grosse
        # entrée (700+) ne tient pas → break → split=2 : elle reste ENTIÈRE
        # dans le head (jamais tronquée), b+c forment la fenêtre récente.
        assert big in head
        assert head == "\n\n".join(entries[:2])
        assert recent == "\n\n".join(entries[2:])
        assert len(recent) <= 250

    def test_select_head_recent_recent_tient_dans_budget(self):
        entries = ["a" * 100, "b" * 100, "c" * 100]
        result = select_head_recent(entries, keep_chars=250)
        assert result is not None
        head, recent = result
        # La fenêtre récente conservée tient toujours dans le budget
        assert len(recent) <= 250
        assert head == "a" * 100

    def test_select_head_recent_tout_tient_none(self):
        assert select_head_recent(["aa", "bb"], keep_chars=100) is None

    def test_select_head_recent_budget_invalide(self):
        assert select_head_recent(["aa"], keep_chars=0) is None


# ---------- (3) garde overflow pi §3.9 ----------

class TestOverflowGuard:
    def test_premier_overflow_autorise_et_arme(self):
        g = OverflowGuard()
        assert g.on_overflow() is True
        assert g.recovery_used is True
        assert not g.is_drained()

    def test_second_overflow_drain(self):
        g = OverflowGuard()
        g.on_overflow()
        assert g.on_overflow() is False
        assert g.is_drained()
        assert "incompressible" in g.failure

    def test_drain_persiste_apres(self):
        g = OverflowGuard()
        g.on_overflow()
        g.on_overflow()
        assert g.on_overflow() is False  # toujours drainé

    def test_nouvel_input_rearme(self):
        g = OverflowGuard()
        g.on_overflow()
        g.on_overflow()
        g.on_new_user_input()
        assert not g.is_drained()
        assert g.recovery_used is False
        assert g.on_overflow() is True


class TestIsContextOverflowError:
    @pytest.mark.parametrize("msg", [
        "Error code: 400 - maximum context length is 32768 tokens, however you requested 41208 tokens",
        "prompt is too long: 45000 tokens > 32768 maximum",
        "PromptTooLongError",
        "This model's maximum context length is 8192 tokens. However, you requested...",
        "too many tokens in the request",
        "input tokens and max_tokens (30000 + 8192) exceeds the maximum allowed (32768)",
        "Context window exceeded",
    ])
    def test_overflow_detecte(self, msg):
        assert is_context_overflow_error(msg) is True

    @pytest.mark.parametrize("msg", [
        "Connection error to host http://127.0.0.1:8080",
        "Timeout of 60000ms exceeded",
        "Authentication error: invalid API key",
        "SyntaxError: unterminated string literal",
    ])
    def test_non_overflow_ignore(self, msg):
        assert is_context_overflow_error(msg) is False

    def test_accepte_exception(self):
        assert is_context_overflow_error(Exception("maximum context length exceeded")) is True
        assert is_context_overflow_error(Exception()) is False


# ---------- (5) budget hermes remboursé sur usage vérifié ----------

class TestCompactionBudget:
    def test_charge_et_epuisement(self):
        b = CompactionBudget(threshold_tokens=30_000, max_attempts=3)
        assert not b.exhausted()
        b.charge(); b.charge(); b.charge()
        assert b.exhausted()

    def test_remboursement_sur_usage_verifie(self):
        b = CompactionBudget(threshold_tokens=30_000)
        b.charge(); b.charge()
        b.on_compaction_committed(made_progress=True)
        b.on_real_usage(prompt_tokens=20_000)  # provider : sous le seuil
        assert b.attempts == 0  # REMBOURSÉ
        assert b.ineffective_strikes == 0

    def test_estimation_ne_rembourse_pas(self):
        # hermes : seul l'usage provider rembourse — pas de verdict sans usage
        b = CompactionBudget(threshold_tokens=30_000)
        b.charge()
        b.on_compaction_committed(made_progress=True)
        b.on_real_usage(prompt_tokens=None)  # pas d'usage rapporté
        assert b.attempts == 1

    def test_strike_si_pas_sous_le_seuil(self):
        b = CompactionBudget(threshold_tokens=30_000)
        b.on_compaction_committed(made_progress=True)
        b.on_real_usage(prompt_tokens=35_000)  # toujours au-dessus
        assert b.ineffective_strikes == 1
        assert not b.blocked()

    def test_breaker_apres_2_strikes(self):
        b = CompactionBudget(threshold_tokens=30_000)
        for _ in range(2):
            b.on_compaction_committed(made_progress=True)
            b.on_real_usage(prompt_tokens=40_000)
        assert b.blocked()

    def test_verdict_consomme_une_fois(self):
        # Le latch est consommé à la première lecture, même sans usage
        b = CompactionBudget(threshold_tokens=30_000)
        b.on_compaction_committed(made_progress=True)
        b.on_real_usage(prompt_tokens=None)
        b.on_real_usage(prompt_tokens=40_000)  # plus de verdict pending
        assert b.ineffective_strikes == 0

    def test_noop_n_arme_pas_le_verdict(self):
        b = CompactionBudget(threshold_tokens=30_000)
        b.charge()
        b.on_compaction_committed(made_progress=False)
        assert not b.verify_cleared
        b.on_real_usage(prompt_tokens=40_000)
        assert b.ineffective_strikes == 0

    def test_refund_noop_verrou(self):
        b = CompactionBudget(threshold_tokens=30_000)
        b.charge()
        b.refund_noop()
        assert b.attempts == 0

    def test_fallback_streak_bloque(self):
        b = CompactionBudget(threshold_tokens=30_000)
        b.on_compaction_committed(made_progress=True, used_fallback=True)
        b.on_compaction_committed(made_progress=True, used_fallback=True)
        assert b.blocked()

    def test_seuil_inconnu_pas_de_verdict(self):
        b = CompactionBudget(threshold_tokens=0)
        b.on_compaction_committed(made_progress=True)
        b.on_real_usage(prompt_tokens=10_000)
        assert b.attempts == 0  # rien chargé, aucun verdict tiré


# ---------- (3) intégration run_with_retry : une seule récupération ----------

def _overflow_agent():
    agent = MagicMock()
    agent.__class__ = type("CodeAgent", (), {})
    agent.name = "coder_test"
    agent.model = MagicMock(model_id="test")
    agent.memory = SimpleNamespace(steps=[])
    return agent


@pytest.mark.anyio
async def test_run_with_retry_overflow_une_recuperation_puis_drain():
    """Overflow ×2 → 2 appels LLM seulement (récupération puis drain), pas 3."""
    agent = _overflow_agent()
    err = Exception(
        "Error code: 400 - This model's maximum context length is 32768 tokens. "
        "However, you requested 41208 tokens"
    )
    to_thread = AsyncMock(side_effect=err)
    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=to_thread):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
            result, metrics = await run_with_retry(agent, "PROMPT", MagicMock, max_retries=3)
    assert result is None
    assert to_thread.await_count == 2  # 1er essai + 1 récupération, PAS de 3e


@pytest.mark.anyio
async def test_run_with_retry_overflow_puis_succes():
    """Overflow ×1 puis succès → la récupération (purge + retry compacté) sauve le nœud."""
    agent = _overflow_agent()
    err = Exception("Error code: 400 - maximum context length is 32768 tokens")
    ok_result = MagicMock()
    ok_result.output = "ok"
    ok_result.timing = MagicMock(duration=1.0)
    ok_result.token_usage = MagicMock(input_tokens=10, output_tokens=5)

    agent.memory = SimpleNamespace(steps=[_make_step(1, model_output="final_answer(...)")])

    # 2e appel : mémoire avec un step productif → non-idle
    side_effects = [err, ok_result]

    async def fake_to_thread(fn, *a, **kw):
        # Simule un step productif dans la mémoire pour le 2e run
        val = side_effects.pop(0)
        if isinstance(val, Exception):
            raise val
        return val

    validated = SimpleNamespace(ok=True)
    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=fake_to_thread):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=validated):
            result, metrics = await run_with_retry(agent, "PROMPT", MagicMock, max_retries=3)
    assert result is validated


@pytest.mark.anyio
async def test_run_with_retry_overflow_opt_out(monkeypatch):
    """COMPACTION_OVERFLOW_GUARD=0 → pas de drain précoce (comportement F-33 historique)."""
    import dataclasses

    from graph_orchestrator import config as config_module

    monkeypatch.setattr(
        config_module,
        "settings",
        dataclasses.replace(config_module.settings, compaction_overflow_guard=False),
    )

    agent = _overflow_agent()
    err = Exception("Error code: 400 - maximum context length is 32768 tokens")
    to_thread = AsyncMock(side_effect=err)
    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=to_thread):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
            result, metrics = await run_with_retry(agent, "PROMPT", MagicMock, max_retries=3)
    assert result is None
    assert to_thread.await_count == 3  # tous les retries brûlés (comportement historique)


from graph_orchestrator.nodes import run_with_retry  # noqa: E402  (après les mocks déclaratifs)
