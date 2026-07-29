"""Tests du HITL stratégique (Phase 6) : routage conditionnel.

On teste UNIQUEMENT la logique de routage (should_trigger_hitl) — pas l'interaction
console (qui nécessiterait un mock d'input). Tous sans appel LLM.
"""

import pytest

from graph_orchestrator.config import Settings
from graph_orchestrator.hitl import should_trigger_hitl


def _settings(**overrides) -> Settings:
    """Construit des Settings avec overrides (les autres champs ont des défauts valides)."""
    base = dict(
        ollama_api_base="http://localhost:11434/v1",
        ollama_reasoning_api_base="http://localhost:11434/v1",
        ollama_api_key="sk-local",
        fast_model_id="qwen3.5:2b",
        reasoning_model_id="gemma",
        reasoning_max_tokens=8192,
        fast_max_tokens=6000,
        coder_temperature=0.2,
        llm_timeout_s=600.0,
        judge_confidence_threshold=0.7,
        worker_max_retries=3,
        adversary_count=3,
        adversary_threshold=0.5,
        max_iterations=3,
        hitl_enabled=False,
        hitl_nodes="synth",
        kg_path=":memory:",
        workflow_mode="one_shot",
        log_level="LOW",
    )
    base.update(overrides)
    return Settings(**base)


class TestShouldTriggerHitl:
    def test_desactive_globalement(self):
        """hitl_enabled=False => jamais, quel que soit le nœud."""
        s = _settings(hitl_enabled=False, hitl_nodes="synth")
        assert should_trigger_hitl("synth", s) is False

    def test_active_sur_noeud_cible(self):
        s = _settings(hitl_enabled=True, hitl_nodes="synth")
        assert should_trigger_hitl("synth", s) is True

    def test_pas_sur_autre_noeud(self):
        """Les workers ne déclenchent pas le HITL (routage stratégique)."""
        s = _settings(hitl_enabled=True, hitl_nodes="synth")
        assert should_trigger_hitl("worker_t1", s) is False

    def test_plusieurs_noeuds_cibles(self):
        s = _settings(hitl_enabled=True, hitl_nodes="synth,transaction")
        assert should_trigger_hitl("synth", s) is True
        assert should_trigger_hitl("transaction", s) is True
        assert should_trigger_hitl("worker", s) is False

    def test_csv_avec_espaces(self):
        """Le parsing CSV doit tolérer les espaces (ex 'synth, transaction')."""
        s = _settings(hitl_enabled=True, hitl_nodes="synth, transaction , publish")
        assert should_trigger_hitl("synth", s) is True
        assert should_trigger_hitl("transaction", s) is True
        assert should_trigger_hitl("publish", s) is True

    def test_hitl_nodes_vide(self):
        """Si HITL_NODES est vide, aucun nœud ne déclenche (même si hitl_enabled=True)."""
        s = _settings(hitl_enabled=True, hitl_nodes="")
        assert should_trigger_hitl("synth", s) is False

    @pytest.mark.parametrize("enabled,node,expected", [
        (True, "synth", True),
        (True, "worker", False),
        (False, "synth", False),
        (False, "worker", False),
    ])
    def test_table_de_verite(self, enabled, node, expected):
        s = _settings(hitl_enabled=enabled, hitl_nodes="synth")
        assert should_trigger_hitl(node, s) is expected
