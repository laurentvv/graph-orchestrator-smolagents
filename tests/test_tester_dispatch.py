"""Tests du nœud Tester polyvalent (dispatcher) — Priorité 2.

Valide que execute_tester_node route bien vers le bon runner selon la techno
détectée, sans dépendre d'un vrai LLM/MCP (on mocke get_runner). On vérifie
aussi que la techno remontée structurellement (task["tech"] ou task["router_lang"]
+ extensions) est bien utilisée pour le dispatch.
"""

import asyncio

import pytest

import graph_orchestrator.nodes as nodes_mod
from graph_orchestrator.models import CoderOutput


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _settings():
    from graph_orchestrator.config import Settings
    return Settings(
        local_api_base="http://x/v1", local_reasoning_api_base="http://x/v1",
        local_api_key="sk", fast_model_id="m", reasoning_model_id="m",
        reasoning_max_tokens=8, fast_max_tokens=8, coder_temperature=0.2,
        llm_timeout_s=1.0, judge_confidence_threshold=0.5,
        worker_max_retries=1, adversary_count=1, adversary_threshold=0.5,
        max_iterations=3, hitl_enabled=False, hitl_nodes="synth",
        kg_path=":memory:", workflow_mode="coding", log_level="LOW",
        fresh_start=False,
        test_timeout_s=30, stderr_head_lines=20, stderr_tail_lines=20,
        feedback_max_chars=2000,
    )


class _RecordingRunner:
    """Faux runner qui mémorise la techno avec laquelle il a été instancié."""
    def __init__(self, tech):
        self.tech = tech
        self.called = False

    async def run(self, task, model, settings):
        self.called = True
        return CoderOutput(task_id=task.get("id", "?"), status="success",
                           details=f"runner={self.tech}"), None


class TestTesterDispatch:

    def test_dispatches_to_python_for_py_files(self, monkeypatch):
        """target_files .py → le runner 'python' est sélectionné."""
        captured = {}

        import graph_orchestrator.testers as testers_mod
        def fake_get_runner(tech):
            captured["tech"] = tech
            return _RecordingRunner(tech)
        monkeypatch.setattr(testers_mod, "get_runner", fake_get_runner)

        task = {"id": "st1", "content": "crée app.py", "target_files": ["app.py"]}
        out, _ = _run(nodes_mod.execute_tester_node(task, reasoning_model=None, settings=_settings()))

        assert captured["tech"] == "python"
        assert out.details == "runner=python"

    def test_dispatches_to_web_for_html_files(self, monkeypatch):
        """target_files .html → le runner 'web' est sélectionné."""
        captured = {}
        import graph_orchestrator.testers as testers_mod
        monkeypatch.setattr(testers_mod, "get_runner",
                            lambda tech: (captured.setdefault("tech", tech), _RecordingRunner(tech))[1])

        task = {"id": "st2", "content": "landing page", "target_files": ["landing_page/index.html"]}
        _run(nodes_mod.execute_tester_node(task, reasoning_model=None, settings=_settings()))

        assert captured["tech"] == "web"

    def test_task_tech_overrides_detection(self, monkeypatch):
        """Si task["tech"] est posé explicitement, il prime sur la détection."""
        captured = {}
        import graph_orchestrator.testers as testers_mod
        monkeypatch.setattr(testers_mod, "get_runner",
                            lambda tech: (captured.setdefault("tech", tech), _RecordingRunner(tech))[1])

        # task["tech"] force python même si les extensions diraient web.
        task = {"id": "st3", "content": "x", "target_files": ["index.html"], "tech": "python"}
        _run(nodes_mod.execute_tester_node(task, reasoning_model=None, settings=_settings()))

        assert captured["tech"] == "python"

    def test_router_lang_used_when_no_target_files(self, monkeypatch):
        """Sans target_files, on se rabat sur router_lang pour la détection."""
        captured = {}
        import graph_orchestrator.testers as testers_mod
        monkeypatch.setattr(testers_mod, "get_runner",
                            lambda tech: (captured.setdefault("tech", tech), _RecordingRunner(tech))[1])

        task = {"id": "st4", "content": "x", "router_lang": "python"}
        _run(nodes_mod.execute_tester_node(task, reasoning_model=None, settings=_settings()))

        assert captured["tech"] == "python"

    def test_fallback_web_when_unknown(self, monkeypatch):
        """Rien de détectable → web (compatibilité arrière)."""
        captured = {}
        import graph_orchestrator.testers as testers_mod
        monkeypatch.setattr(testers_mod, "get_runner",
                            lambda tech: (captured.setdefault("tech", tech), _RecordingRunner(tech))[1])

        task = {"id": "st5", "content": "x"}
        _run(nodes_mod.execute_tester_node(task, reasoning_model=None, settings=_settings()))

        assert captured["tech"] == "web"

    def test_extension_overrides_router_in_dispatch(self, monkeypatch):
        """Conflit routeur/extensions : l'extension gagne (déterministe)."""
        captured = {}
        import graph_orchestrator.testers as testers_mod
        monkeypatch.setattr(testers_mod, "get_runner",
                            lambda tech: (captured.setdefault("tech", tech), _RecordingRunner(tech))[1])

        # routeur dit javascript, fichiers .py → python.
        task = {"id": "st6", "content": "x", "target_files": ["app.py"], "router_lang": "javascript"}
        _run(nodes_mod.execute_tester_node(task, reasoning_model=None, settings=_settings()))

        assert captured["tech"] == "python"
