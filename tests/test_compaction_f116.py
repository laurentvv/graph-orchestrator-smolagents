"""Tests F-116 — Compaction v3 résiliente : payloads + chunks + ponytail.

Couvre les 4 volets du plan approuvé :
(A) déterministe compaction.py v3 — clip model_output (le trou n°1 du mur
    #13/#16), purge images perte-zéro (archive + placeholder), trace bornée
    (chunks kilocode), tombstones culs-de-sac, soft retry reset, preflight ;
(B) branchement nodes.py — chemin overflow (strip escaladé) + boundary de
    retry soft/hard ;
(C) LLM sémantique opt-in (ex-F-86) — résumé via compaction_prompts, verdict
    CompactionBudget sur usage réel ;
(D) doctrine ponytail (fiche 48) — injection dans le header Coder.
"""

import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image
from smolagents import AgentMemory, CodeAgent
from smolagents.agents import ActionStep, TaskStep
from smolagents.monitoring import Timing

from graph_orchestrator.compaction import (
    MO_CLIP_MARKER,
    MO_CLIP_THRESHOLD,
    CompactingCodeAgent,
    apply_image_purge,
    apply_model_output_clip,
    apply_soft_retry_reset,
    collect_dead_ends,
    estimate_history_tokens,
    render_transcript_block,
)
from graph_orchestrator.compaction_guards import CompactionBudget
from graph_orchestrator.compaction_llm import llm_compact_history
from graph_orchestrator.nodes import run_with_retry
from graph_orchestrator.prompts import build_role_header


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


def _make_image(w: int = 8, h: int = 8) -> Image.Image:
    return Image.new("RGB", (w, h), color=(30, 30, 30))


def _big_model_output(n_chars: int = 5000, step: int = 1) -> str:
    """Simule le failure mode du mur : pensée + write_file avec fichier entier."""
    return (
        f"Thought: je génère le fichier complet.\n"
        f"```python\nwrite_file('index.html', '<html>" + "x" * n_chars + "</html>')\n```"
    )


# ---------- (A) apply_image_purge v2 : archive + placeholder ----------

class TestImagePurgeV2:
    def test_archive_anciens_screenshots_avec_placeholder(self, tmp_path):
        mem = _make_memory(n_steps=3)
        mem.steps[1].observations_images = [_make_image()]
        d = tmp_path / ".transcripts" / "images"
        apply_image_purge(mem, images_dir=d)
        assert mem.steps[1].observations_images == []
        assert "[Screenshot archivé:" in str(mem.steps[1].observations)
        archived = list(d.iterdir())
        assert len(archived) == 1 and archived[0].suffix == ".png"

    def test_garde_limage_du_dernier_step(self, tmp_path):
        mem = _make_memory(n_steps=3)
        img = _make_image()
        mem.steps[3].observations_images = [img]
        apply_image_purge(mem, images_dir=tmp_path / "images")
        assert mem.steps[3].observations_images == [img]

    def test_dernier_step_plusieurs_images_garde_la_derniere(self, tmp_path):
        mem = _make_memory(n_steps=2)
        img1, img2 = _make_image(), _make_image()
        mem.steps[2].observations_images = [img1, img2]
        d = tmp_path / "images"
        apply_image_purge(mem, images_dir=d)
        assert mem.steps[2].observations_images == [img2]
        assert "[Screenshot archivé:" in str(mem.steps[2].observations)

    def test_sans_dir_comportement_historique_silencieux(self):
        mem = _make_memory(n_steps=3)
        mem.steps[1].observations_images = [_make_image()]
        apply_image_purge(mem, images_dir=None)
        assert mem.steps[1].observations_images == []
        assert "Screenshot archivé" not in str(mem.steps[1].observations)

    def test_observations_none_placeholder_devient_observations(self, tmp_path):
        mem = _make_memory(n_steps=2)
        mem.steps[1].observations = None
        mem.steps[1].observations_images = [_make_image()]
        apply_image_purge(mem, images_dir=tmp_path / "images")
        assert str(mem.steps[1].observations).startswith("[Screenshot archivé:")

    def test_second_pass_ne_ajoute_pas_de_placeholder(self, tmp_path):
        mem = _make_memory(n_steps=2)
        mem.steps[1].observations_images = [_make_image()]
        d = tmp_path / "images"
        apply_image_purge(mem, images_dir=d)
        obs_after_first = str(mem.steps[1].observations)
        # les images sont purgées : un second appel ne re-note rien
        apply_image_purge(mem, images_dir=d)
        assert str(mem.steps[1].observations) == obs_after_first
        assert obs_after_first.count("[Screenshot archivé:") == 1


# ---------- (A) apply_model_output_clip : le trou n°1 du mur ----------

class TestModelOutputClip:
    def test_clip_anciens_steps_conserve_recents(self, tmp_path):
        mem = _make_memory(n_steps=6)
        for i in range(1, 7):
            mem.steps[i].model_output = _big_model_output(step=i)
        apply_model_output_clip(mem, keep_recent=3, transcript_dir=tmp_path / ".transcripts")
        clipped = mem.steps[1].model_output
        assert MO_CLIP_MARKER in clipped and "version intégrale" in clipped
        # les 3 derniers sont intacts
        for i in (4, 5, 6):
            assert "xxxxx" in mem.steps[i].model_output

    def test_version_integrale_persistee(self, tmp_path):
        mem = _make_memory(n_steps=5)
        big = _big_model_output()
        mem.steps[1].model_output = big
        d = tmp_path / ".transcripts"
        apply_model_output_clip(mem, keep_recent=3, transcript_dir=d)
        saved = [p for p in d.iterdir() if p.name.startswith("mo_step_")]
        assert len(saved) == 1
        assert saved[0].read_text(encoding="utf-8") == big

    def test_idempotent_second_pass_noop(self, tmp_path):
        mem = _make_memory(n_steps=5)
        mem.steps[1].model_output = _big_model_output()
        d = tmp_path / ".transcripts"
        apply_model_output_clip(mem, keep_recent=3, transcript_dir=d)
        first = mem.steps[1].model_output
        apply_model_output_clip(mem, keep_recent=3, transcript_dir=d)
        assert mem.steps[1].model_output == first

    def test_court_model_output_intouchable(self, tmp_path):
        mem = _make_memory(n_steps=5)
        apply_model_output_clip(mem, keep_recent=3, transcript_dir=tmp_path / "t")
        assert mem.steps[1].model_output == "thought 1"

    def test_sans_dir_marqueur_sans_chemin(self, tmp_path):
        mem = _make_memory(n_steps=5)
        mem.steps[1].model_output = _big_model_output()
        apply_model_output_clip(mem, keep_recent=3, transcript_dir=None)
        clipped = mem.steps[1].model_output
        assert MO_CLIP_MARKER in clipped and "chars réduits]" in clipped

    def test_taskstep_jamais_clippe(self, tmp_path):
        mem = _make_memory(n_steps=5)
        apply_model_output_clip(mem, keep_recent=3, transcript_dir=tmp_path / "t")
        assert isinstance(mem.steps[0], TaskStep)
        assert mem.steps[0].task == "Construire un visualiseur"


# ---------- (A) render_transcript_block : chunks kilocode déterministes ----------

class TestTranscriptBlock:
    def test_rendu_par_step_avec_clips(self):
        steps = [
            _make_step(1, observations="console clean", model_output="Thought courte"),
            _make_step(2, observations="o" * 500, model_output="t" * 500),
        ]
        block = render_transcript_block(steps, max_chars=3000)
        assert "[step 1]" in block and "[step 2]" in block
        assert "chars omis]" in block  # le step 2 est clippé

    def test_cap_global_avec_marqueur(self):
        steps = [_make_step(i, observations="obs", model_output=f"m{i}") for i in range(1, 30)]
        block = render_transcript_block(steps, max_chars=200)
        assert len(block) < 400
        assert "chars omis (transcript)]" in block

    def test_vide_pour_steps_sans_action(self):
        assert render_transcript_block([]) == ""

    def test_erreur_incluse(self):
        s = _make_step(3, model_output="attempt")
        s.error = Exception("SyntaxError: unexpected token")
        assert "ERR:" in render_transcript_block([s])


# ---------- (A) collect_dead_ends : tombstones déterministes ----------

class TestCollectDeadEnds:
    def test_collecte_erreur_avec_nom_outil(self):
        s = _make_step(2, model_output="```python\nsearch_replace(path='a', old='b', new='c')\n```")
        s.error = Exception("Code parsing failed: unterminated string")
        ends = collect_dead_ends([s])
        assert len(ends) == 1 and ends[0].startswith("search_replace: Code parsing failed")

    def test_deduplique(self):
        s1 = _make_step(2, model_output="write_file('a')")
        s1.error = Exception("Identical error")
        s2 = _make_step(3, model_output="write_file('a')")
        s2.error = Exception("Identical error")
        assert len(collect_dead_ends([s1, s2])) == 1

    def test_cappe_a_8(self):
        steps = []
        for i in range(12):
            s = _make_step(i, model_output="write_file('a')")
            s.error = Exception(f"Erreur differente {i}")
            steps.append(s)
        assert len(collect_dead_ends(steps)) == 8

    def test_ignere_prose_sans_erreur_reelle(self):
        s = _make_step(1, observations="[Compacted: 0 console errors observed]")
        assert collect_dead_ends([s]) == []


# ---------- (A) apply_soft_retry_reset : reset hiérarchique ----------

class TestSoftRetryReset:
    def test_garde_queue_et_summary_pas_taskstep_par_defaut_drop(self, tmp_path):
        mem = _make_memory(n_steps=8)
        marker = apply_soft_retry_reset(mem, transcript_dir=tmp_path / ".transcripts", keep_tail=4)
        assert marker is not None
        # drop_task_steps=False (preflight) → TaskStep conservé
        assert isinstance(mem.steps[0], TaskStep)
        summary = mem.steps[1]
        assert isinstance(summary, ActionStep)
        assert "messages archived at" in summary.model_output or "Soft retry reset" in summary.model_output
        # queue = 4 derniers steps d'origine
        nums = [getattr(s, "step_number", None) for s in mem.steps]
        assert nums[-4:] == [5, 6, 7, 8]

    def test_drop_task_steps_au_boundary(self, tmp_path):
        mem = _make_memory(n_steps=8)
        apply_soft_retry_reset(
            mem, transcript_dir=tmp_path / "t", keep_tail=4, drop_task_steps=True
        )
        assert not any(isinstance(s, TaskStep) for s in mem.steps)

    def test_archive_jsonl_des_evicques(self, tmp_path):
        mem = _make_memory(n_steps=8)
        d = tmp_path / ".transcripts"
        marker = apply_soft_retry_reset(mem, transcript_dir=d, keep_tail=4, drop_task_steps=True)
        assert "messages archived at" in marker
        archives = [p for p in d.iterdir() if p.name.startswith("transcript_")]
        assert len(archives) == 1
        lines = archives[0].read_text(encoding="utf-8").splitlines()
        # 4 anciens steps archivés (le TaskStep est également sérialisé)
        assert len(lines) == 5

    def test_queue_clipped_et_images_purgees(self, tmp_path):
        mem = _make_memory(n_steps=8)
        big = _big_model_output(n_chars=4000)
        # gros model_output + image sur le DERNIER step (dans la queue conservée)
        mem.steps[8].model_output = big
        mem.steps[8].observations_images = [_make_image()]
        d = tmp_path / ".transcripts"
        apply_soft_retry_reset(mem, transcript_dir=d, keep_tail=4, drop_task_steps=True)
        assert MO_CLIP_MARKER in mem.steps[-1].model_output
        assert mem.steps[-1].observations_images == []

    def test_marqueur_contient_trace_et_culs_de_sac(self, tmp_path):
        mem = _make_memory(n_steps=8)
        mem.steps[2].error = Exception("TypeError: cannot read property")
        marker = apply_soft_retry_reset(mem, transcript_dir=tmp_path / "t", keep_tail=4)
        assert "Compacted trace:" in marker
        assert "CULS-DE-SAC" in marker
        assert "TypeError" in marker

    def test_memoire_vide_retourne_none(self):
        mem = AgentMemory(system_prompt={"role": "system", "content": "s"})
        assert apply_soft_retry_reset(mem) is None

    def test_reduction_massive_estimation_tokens(self, tmp_path):
        mem = _make_memory(n_steps=20)
        for i in range(1, 21):
            mem.steps[i].model_output = _big_model_output(n_chars=3000)
        before = estimate_history_tokens(mem)
        apply_soft_retry_reset(mem, transcript_dir=tmp_path / "t", keep_tail=4, drop_task_steps=True)
        after = estimate_history_tokens(mem)
        assert after < before * 0.5


# ---------- (A) estimate_history_tokens ----------

class TestEstimateTokens:
    def test_echelle_avec_contenu(self):
        small = _make_memory(n_steps=2)
        big = _make_memory(n_steps=2)
        big.steps[1].model_output = "x" * 40_000
        assert estimate_history_tokens(big) > estimate_history_tokens(small) * 5

    def test_compte_les_images(self):
        mem = _make_memory(n_steps=2)
        without = estimate_history_tokens(mem)
        mem.steps[2].observations_images = [_make_image()]
        assert estimate_history_tokens(mem) > without + 1000


# ---------- (A) preflight pipeline : escalade dans write_memory_to_messages ----------

class TestPreflightPipeline:
    def _agent(self):
        agent = MagicMock(spec=["memory", "write_memory_to_messages"])
        agent.memory = _make_memory(n_steps=0)
        return agent

    def test_escalade_quand_estimation_depasse_budget(self, monkeypatch, tmp_path):
        """write_memory_to_messages avec historique énorme → escalade (steps bornés)."""
        import dataclasses

        from graph_orchestrator import config as config_module
        from graph_orchestrator.compaction import CompactingCodeAgent

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            config_module,
            "settings",
            dataclasses.replace(
                config_module.settings,
                compaction_archive_enabled=True,
                compaction_clip_enabled=True,
                compaction_preflight_enabled=True,
                compaction_preflight_budget_tokens=2_000,
            ),
        )
        agent = MagicMock()
        agent.__class__ = CompactingCodeAgent  # super() exige une instance du type
        agent.memory = _make_memory(n_steps=25)
        for i in range(1, 26):
            agent.memory.steps[i].model_output = _big_model_output(n_chars=2500)
        agent.memory.steps[25].observations_images = [_make_image()]

        with patch.object(CodeAgent, "write_memory_to_messages", return_value=[]) as base:
            CompactingCodeAgent.write_memory_to_messages(agent, summary_mode=False)
        base.assert_called_once()
        # L'escalade a eu lieu : historique réduit à ~TaskStep + summary + 3 tail
        assert len(agent.memory.steps) <= 6
        # dernière image évincée (escalade)
        assert all(
            not getattr(s, "observations_images", None) for s in agent.memory.steps
        )

    def test_pas_descalade_sous_budget(self, monkeypatch, tmp_path):
        import dataclasses

        from graph_orchestrator import config as config_module
        from graph_orchestrator.compaction import CompactingCodeAgent

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            config_module,
            "settings",
            dataclasses.replace(
                config_module.settings,
                compaction_archive_enabled=False,
                compaction_clip_enabled=False,
                compaction_preflight_enabled=True,
                compaction_preflight_budget_tokens=100_000,
            ),
        )
        agent = MagicMock()
        agent.__class__ = CompactingCodeAgent  # super() exige une instance du type
        agent.memory = _make_memory(n_steps=5)

        with patch.object(CodeAgent, "write_memory_to_messages", return_value=[]) as base:
            CompactingCodeAgent.write_memory_to_messages(agent, summary_mode=False)
        base.assert_called_once()
        # pas d'escalade : les 6 steps d'origine sont intacts
        assert len(agent.memory.steps) == 6


# ---------- (B) branchement nodes : overflow + boundary ----------

def _overflow_agent():
    agent = MagicMock()
    agent.__class__ = type("CodeAgent", (), {})
    agent.name = "coder_test"
    agent.model = MagicMock(model_id="test")
    agent.memory = SimpleNamespace(steps=[])
    return agent


class TestNodesOverflowWiring:
    @pytest.mark.anyio
    async def test_overflow_compacte_et_pas_de_double_reset(self, monkeypatch, tmp_path):
        """Le chemin overflow compacte UNE fois ; le boundary ne re-compacte pas."""
        monkeypatch.setattr(
            "graph_orchestrator.nodes._resolve_transcript_dir", lambda: tmp_path / "t"
        )
        agent = _overflow_agent()
        now = time.time()
        steps = [
            TaskStep(task="tâche"),
            *[
                ActionStep(step_number=i, timing=Timing(start_time=now, end_time=now))
                for i in range(1, 4)
            ],
        ]
        for i, s in enumerate(steps[1:], start=1):
            s.model_output = f"mo {i}"
            s.observations = f"obs {i}"
        agent.memory = SimpleNamespace(steps=steps)

        calls = {"n": 0}

        async def fake_to_thread(fn, *a, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise Exception(
                    "Error code: 400 - This model's maximum context length is "
                    "32768 tokens. However, you requested 41208 tokens"
                )
            raise Exception("autre erreur définitive")

        with patch("graph_orchestrator.nodes.asyncio.to_thread", new=fake_to_thread):
            with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
                result, _ = await run_with_retry(agent, "PROMPT", MagicMock, max_retries=2)
        assert result is None
        # La mémoire n'est PAS vide : contient le step-synthèse F-116 + queue
        markers = [
            s.model_output
            for s in agent.memory.steps
            if "messages archived at" in str(getattr(s, "model_output", ""))
            or "Soft retry reset F-116" in str(getattr(s, "model_output", ""))
        ]
        assert markers, "le soft reset F-116 doit avoir laissé une trace compactée"

    @pytest.mark.anyio
    async def test_boundary_soft_conserve_une_trace(self, monkeypatch, tmp_path):
        """Échec NON-overflow → boundary soft : historique compacté, pas vidé."""
        monkeypatch.setattr(
            "graph_orchestrator.nodes._resolve_transcript_dir", lambda: tmp_path / "t"
        )
        agent = _overflow_agent()
        now = time.time()
        steps = [TaskStep(task="tâche")]
        for i in range(1, 6):
            s = ActionStep(step_number=i, timing=Timing(start_time=now, end_time=now))
            s.model_output = f"mo {i}"
            s.observations = f"obs {i}"
            steps.append(s)
        agent.memory = SimpleNamespace(steps=steps)

        async def fake_to_thread(fn, *a, **kw):
            raise Exception("JSON invalide définitif")

        with patch("graph_orchestrator.nodes.asyncio.to_thread", new=fake_to_thread):
            with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
                result, _ = await run_with_retry(agent, "PROMPT", MagicMock, max_retries=1)
        assert result is None
        # soft : les steps ne sont PAS vidés, une trace compactée existe
        assert agent.memory.steps, "boundary soft ne doit pas vider la mémoire"
        assert any(
            "messages archived at" in str(getattr(s, "model_output", ""))
            or "Soft retry reset F-116" in str(getattr(s, "model_output", ""))
            for s in agent.memory.steps
        )

    @pytest.mark.anyio
    async def test_boundary_hard_opt_out_vide_la_memoire(self, monkeypatch):
        import dataclasses

        from graph_orchestrator import config as config_module

        monkeypatch.setattr(
            config_module,
            "settings",
            dataclasses.replace(config_module.settings, compaction_retry_mode="hard"),
        )
        agent = _overflow_agent()
        now = time.time()
        s = ActionStep(step_number=1, timing=Timing(start_time=now, end_time=now))
        s.model_output = "mo"
        s.observations = "obs"
        agent.memory = SimpleNamespace(steps=[TaskStep(task="t"), s])

        async def fake_to_thread(fn, *a, **kw):
            raise Exception("échec définitif")

        with patch("graph_orchestrator.nodes.asyncio.to_thread", new=fake_to_thread):
            with patch("graph_orchestrator.nodes.extract_and_validate", return_value=None):
                await run_with_retry(agent, "PROMPT", MagicMock, max_retries=1)
        assert agent.memory.steps == []


# ---------- (C) llm_compact_history : volet LLM opt-in ----------

class _FakeModel:
    def __init__(self, text="## Objective\n- Finir le visualiseur\n## Work State\n### Completed\n- squelette\n## Next Move\n1. corriger le compteur\n## Relevant Files\n- (none)"):
        self.text = text
        self.calls = []

    def generate(self, messages=None, max_tokens=None):
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        resp = MagicMock()
        resp.content = [SimpleNamespace(text=self.text)]
        return resp


class _RaisingModel:
    def generate(self, messages=None, max_tokens=None):
        raise RuntimeError("llama-server down")


class TestLLMCompact:
    def _agent(self, n=10):
        """Mémoire assez volumineuse pour dépasser KEEP_RECENT_CHARS (12k)."""
        agent = MagicMock()
        mem = _make_memory(n_steps=n)
        for i in range(1, n + 1):
            mem.steps[i].model_output = f"thought {i} " + "détail technique du step. " * 150
        agent.memory = mem
        return agent

    def test_remplace_historique_par_resume_plus_queue(self):
        agent = self._agent(n=10)
        model = _FakeModel()
        agent.model = model
        ok, note = llm_compact_history(agent)
        assert ok, note
        # TaskStep + summary + queue
        assert isinstance(agent.memory.steps[0], TaskStep)
        assert "[Context compacted by LLM summary (F-116 opt-in)]" in agent.memory.steps[1].model_output
        tail_nums = [getattr(s, "step_number", None) for s in agent.memory.steps[2:]]
        assert tail_nums[-4:] == [7, 8, 9, 10]
        assert len(model.calls) == 1
        assert model.calls[0]["max_tokens"] == 1024

    def test_budget_charge_puis_commit_progres(self):
        agent = self._agent(n=10)
        agent.model = _FakeModel()
        budget = CompactionBudget(threshold_tokens=26_000)
        ok, _ = llm_compact_history(agent, budget=budget)
        assert ok
        assert budget.attempts == 1
        assert budget.verify_cleared is True
        assert budget.awaiting_real_usage is True

    def test_remboursement_sur_usage_reel_sous_seuil(self):
        budget = CompactionBudget(threshold_tokens=26_000)
        budget.charge()
        budget.on_compaction_committed(True)
        budget.on_real_usage(prompt_tokens=18_000)
        assert budget.attempts == 0  # remboursé

    def test_modele_en_echec_essai_consomme_sans_commit(self, monkeypatch, tmp_path):
        """hermes : un échec de génération NE commet rien (pas de fallback streak
        — seule une compaction COMPIE compte), mais l'essai reste consommé."""
        agent = self._agent(n=10)
        agent.model = _RaisingModel()
        budget = CompactionBudget(threshold_tokens=26_000)
        ok, note = llm_compact_history(agent, budget=budget)
        assert not ok and "échec génération" in note
        assert budget.attempts == 1  # consommé, non remboursé
        assert budget.verify_cleared is False  # rien de commis
        assert budget.fallback_streak == 0  # hermes : abort ≠ fallback commit

    def test_resume_trop_court_rejete(self):
        agent = self._agent(n=10)
        agent.model = _FakeModel(text="ok")
        ok, note = llm_compact_history(agent)
        assert not ok and "vide/tronqué" in note
        # l'historique est intact (pas de commit)
        assert len(agent.memory.steps) == 11

    def test_budget_bloque_skip_llm(self):
        agent = self._agent(n=10)
        agent.model = _FakeModel()
        budget = CompactionBudget(threshold_tokens=26_000)
        budget.ineffective_strikes = 2
        ok, note = llm_compact_history(agent, budget=budget)
        assert not ok and "bloqué" in note

    def test_petit_historique_noop_reussi(self):
        agent = self._agent(n=2)
        agent.model = _FakeModel()
        ok, note = llm_compact_history(agent)
        assert ok and "rien à résumer" in note


# ---------- (D) doctrine ponytail ----------

class TestPonytail:
    def test_coder_embarque_le_ladder(self):
        h = build_role_header("coder")
        assert "DOCTRINE PONYTAIL" in h
        assert "INTOUCHABLE" in h
        assert "INVARIANTS UNIVERSELS" in h  # invariants toujours présents

    def test_coder_frontend_aussi(self):
        assert "DOCTRINE PONYTAIL" in build_role_header("coder_frontend")

    def test_architect_et_tester_epargnes(self):
        # l'Architect garde son NIVEAU GRAPHIQUE MAXIMAL (F-124) : la doctrine
        # réduit le CODE, pas les exigences.
        assert "DOCTRINE PONYTAIL" not in build_role_header("architect")
        assert "DOCTRINE PONYTAIL" not in build_role_header("web_tester")
        assert "NIVEAU GRAPHIQUE MAXIMAL" in build_role_header("architect")

    def test_garde_anti_sous_livraison_presente(self):
        h = build_role_header("coder")
        # la clause cruciale pour un 4B : minimal décrit le CODE, pas le périmètre
        assert "sous-fonctionnalité est un ÉCHEC" in h
        assert "checklist est sacrée" in h
