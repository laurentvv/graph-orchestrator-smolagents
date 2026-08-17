"""Tests unitaires du nœud PromptRefiner (F-39, meta-prompt avant l'Architect).

Déterministes, 0 appel réseau, 0 LLM réel (mock DSPy comme test_dspy_nodes.py).

Couvre :
- Exécuteur : sortie PromptRefinerOutput + métriques + available_capabilities bien passé.
- Dégradation gracieuse : LLM down → (None, None).
- Helper _build_capabilities_summary : skills via list_skills + statut Context7 + testers + repli.
- E2E toggle : prompt_refiner_enabled=False → prompt brut non modifié, nœud jamais appelé.
- E2E checkpoint skip : refined_prompt en checkpoint → nœud jamais appelé, prompt hydraté.
"""
import tempfile
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


from graph_orchestrator.dspy_nodes import (
    PromptRefinerSignature,
    _build_capabilities_summary,
    execute_prompt_refiner_node,
)
from graph_orchestrator.models import PromptRefinerOutput


# ==========================================
# Helper : mock settings minimal (les toggles ont des défauts dans la dataclass)
# ==========================================
def _mock_settings():
    """Settings mocké — seuls les champs lus par execute_prompt_refiner_node sont requis."""
    s = MagicMock()
    s.reasoning_model_id = "mock-reasoning-model"
    s.fast_model_id = "mock-fast-model"
    s.local_reasoning_api_base = "http://localhost:11434/v1"
    s.local_api_base = "http://localhost:11434/v1"
    s.llm_timeout_s = 1.0
    s.prompt_refiner_enabled = True
    s.prompt_refiner_model_id = ""  # défaut vide = fallback sur reasoning_model_id
    # F-58 : reasoning_no_think_model_id mocké vide (sinon MagicMock truthy casse le
    # fallback `or` dans _no_think_model_id). Cohérent avec le défaut dataclass "".
    s.reasoning_no_think_model_id = ""
    
    s.fast_spec = MagicMock(backend="external", model="mock-fast-model", api_base="http://localhost:11434/v1", api_key="sk-mock")
    s.reasoning_spec = MagicMock(backend="external", model="mock-reasoning-model", api_base="http://localhost:11434/v1", api_key="sk-mock")
    s.no_think_spec = MagicMock(backend="external", model="", api_base="http://localhost:11434/v1", api_key="sk-mock")

    return s


# ==========================================
# Exécuteur : signature + available_capabilities propagé + métriques
# ==========================================
@patch("graph_orchestrator.dspy_nodes._configure_dspy")
@patch("graph_orchestrator.dspy_nodes.dspy.ChainOfThought")
def test_execute_prompt_refiner_node(mock_cot, mock_configure):
    """Le nœud renvoie un PromptRefinerOutput + métriques, et passe available_capabilities."""
    mock_instance = MagicMock()
    mock_prediction = MagicMock()
    expected = PromptRefinerOutput(
        refined_prompt="## Objectif\nCréer un tri à bulles visuel.",
        ambiguities_detected=["beau", "rapide"],
    )
    mock_prediction.output = expected
    mock_instance.return_value = mock_prediction
    mock_cot.return_value = mock_instance

    settings = _mock_settings()
    output, metrics = asyncio.run(
        execute_prompt_refiner_node("fais un tri à bulles beau et rapide", "FAKE_REASON", settings)
    )

    assert output is not None
    assert isinstance(output, PromptRefinerOutput)
    assert "Objectif" in output.refined_prompt
    assert output.ambiguities_detected == ["beau", "rapide"]
    assert metrics is not None
    assert metrics.node == "prompt_refiner_dspy"
    assert metrics.model == "mock-fast-model"
    # Le predictor a été instancié avec NOTRE signature.
    mock_cot.assert_called_once_with(PromptRefinerSignature)
    # L'appel au predictor a bien reçu les 2 inputs (raw_prompt + available_capabilities).
    mock_instance.assert_called_once()
    _, kwargs = mock_instance.call_args
    assert "fais un tri à bulles" in kwargs["raw_prompt"]
    assert "CAPACITÉS DISPONIBLES" in kwargs["available_capabilities"]


@patch("graph_orchestrator.dspy_nodes._configure_dspy")
@patch("graph_orchestrator.dspy_nodes.dspy.ChainOfThought")
def test_execute_prompt_refiner_node_graceful_failure(mock_cot, mock_configure):
    """LLM down → (None, None), pas d'exception (l'appelant repliera sur le prompt brut)."""
    mock_instance = MagicMock()
    mock_instance.side_effect = RuntimeError("LLM endpoint muet")
    mock_cot.return_value = mock_instance

    settings = _mock_settings()
    output, metrics = asyncio.run(
        execute_prompt_refiner_node("prompt vague", "FAKE_REASON", settings)
    )
    assert output is None
    assert metrics is None


@patch("graph_orchestrator.dspy_nodes.model_lifecycle")
@patch("graph_orchestrator.dspy_nodes._configure_dspy")
@patch("graph_orchestrator.dspy_nodes.dspy.ChainOfThought")
def test_prompt_refiner_uses_fast_spec_no_override(mock_cot, mock_configure, mock_lifecycle):
    """PromptRefiner utilise fast_spec (Qwen3.5-4B, comme le Coder), think=False, sans override.

    Migration 2026-08-10 : ce nœud était avant sur reasoning_spec + override gemma-4-E4B
    (PROMPT_REFINER_MODEL_ID). C'était incohérent (un spawn 9B + un serveur séparé pour
    une simple reformulation). Désormais fast_spec uniquement — le modèle rapide suffit
    largement pour reformatter un prompt. Le champ prompt_refiner_model_id est DORMANT :
    même s'il est setté, il ne doit plus être lu.
    """
    mock_instance = MagicMock()
    mock_prediction = MagicMock()
    mock_prediction.output = PromptRefinerOutput(refined_prompt="spec")
    mock_instance.return_value = mock_prediction
    mock_cot.return_value = mock_instance

    # Simule un model_lifecycle context manager qui yield un serveur fast.
    fake_srv = SimpleNamespace(model_id="mock-fast-model", api_base="http://localhost:11434/v1", api_key="sk-mock")
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=fake_srv)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    mock_lifecycle.return_value = mock_ctx

    settings = _mock_settings()
    # Même si l'override dormant est setté, il ne doit PAS être utilisé.
    settings.prompt_refiner_model_id = "dormant-should-be-ignored"
    output, metrics = asyncio.run(
        execute_prompt_refiner_node("prompt", "FAKE_REASON", settings)
    )

    # model_lifecycle a été appelé avec fast_spec (pas reasoning_spec).
    mock_lifecycle.assert_called_once()
    spec_arg = mock_lifecycle.call_args[0][0]
    assert spec_arg is settings.fast_spec
    # _configure_dspy reçoit le modèle fast (mock-fast-model), think=False.
    mock_configure.assert_called_once_with(
        settings, "mock-fast-model", think=False,
        api_base="http://localhost:11434/v1", api_key="sk-mock",
    )
    # La métrique reflète le modèle fast réellement utilisé.
    assert metrics.model == "mock-fast-model"


# ==========================================
# Helper _build_capabilities_summary
# ==========================================
def test_capabilities_summary_includes_skills_context7_testers(monkeypatch):
    """Le résumé contient : skills (via list_skills) + statut Context7 + testers."""
    fake_skills = [
        {"name": "web-tester", "description": "Test des apps web via Puppeteer."},
        {"name": "python-tester", "description": "Test Python via pytest."},
        {"name": "frontend-design", "description": "Design frontend pro."},
    ]
    # Mocke list_skills (source agent_server).
    import sys
    fake_module = MagicMock()
    fake_module.list_skills = MagicMock(return_value=fake_skills)
    monkeypatch.setitem(sys.modules, "agent_server.skills", fake_module)
    monkeypatch.setenv("CONTEXT7_API_KEY", "fake-key")

    settings = _mock_settings()
    summary = _build_capabilities_summary(settings)

    assert "CAPACITÉS DISPONIBLES" in summary
    assert "web-tester" in summary and "Puppeteer" in summary
    assert "python-tester" in summary
    assert "context7" in summary.lower() and "DISPONIBLE" in summary  # clé présente


def test_capabilities_summary_context7_disabled(monkeypatch):
    """Sans clé CONTEXT7_API_KEY, le résumé indique context7 'désactivé'."""
    import sys
    fake_module = MagicMock()
    fake_module.list_skills = MagicMock(return_value=[])
    monkeypatch.setitem(sys.modules, "agent_server.skills", fake_module)
    monkeypatch.delenv("CONTEXT7_API_KEY", raising=False)

    settings = _mock_settings()
    summary = _build_capabilities_summary(settings)

    assert "désactivé" in summary.lower() or "pas de clé" in summary.lower()


def test_capabilities_summary_fallback_on_missing_agent_server(monkeypatch):
    """Si l'import agent_server.skills échoue → repli lecture dossier skills/ du projet.

    Le projet a un vrai dossier skills/ (avec web-tester, python-tester, etc.), donc le
    repli doit produire un résumé non vide. On force l'échec de l'import agent_server.
    """
    import sys
    # Empêche l'import d'agent_server.skills (simule agent_server absent).
    monkeypatch.setitem(sys.modules, "agent_server.skills", None)

    settings = _mock_settings()
    summary = _build_capabilities_summary(settings)

    # Le repli lit le dossier skills/ réel du projet → on retrouve au moins les testers.
    assert "CAPACITÉS DISPONIBLES" in summary
    # Les testers statiques sont TOUJOURS présents (même si le repli skills échoue).
    assert "web-tester" in summary
    assert "python-tester" in summary


# ==========================================
# E2E : branchement dans run_coding_workflow
# ==========================================
def _seed_tasks():
    return [{
        "id": "task1",
        "content": "Créer un visualiseur de tri à bulles en HTML/CSS/JS vanilla.",
        "target_files": ["index.html"],
    }]


def _settings_full(prompt_refiner_enabled=True):
    from graph_orchestrator.config import Settings
    return Settings(
        output_dir=tempfile.mkdtemp(prefix="e2e_runs_"),  # F-113 : isole du vrai runs/
        local_api_base="http://x/v1", local_reasoning_api_base="http://x/v1",
        local_api_key="sk", fast_model_id="m", reasoning_model_id="m",
        reasoning_max_tokens=8, fast_max_tokens=8, coder_temperature=0.2,
        llm_timeout_s=1.0, judge_confidence_threshold=0.5,
        worker_max_retries=1, adversary_count=1, adversary_threshold=0.5,
        max_iterations=3, hitl_enabled=False, hitl_nodes="synth",
        kg_path=":memory:", workflow_mode="coding", log_level="LOW",
        fresh_start=True,
        test_timeout_s=120, stderr_head_lines=20, stderr_tail_lines=20,
        feedback_max_chars=2000,
        prompt_refiner_enabled=prompt_refiner_enabled,
    )


def _mock_other_nodes(monkeypatch):
    """Mocke TOUS les nœuds du workflow coding (sauf prompt_refiner, testé à part)."""
    import graph_orchestrator.nodes as nodes_mod
    import graph_orchestrator.dspy_nodes as dspy_mod
    import graph_orchestrator.workflows as wf_mod
    from graph_orchestrator.models import (
        ArchitectOutput, ArchitectTask, RouterOutput, CoderOutput,
        SecurityOutput, CodeJudgeOutput,
    )

    monkeypatch.setattr(wf_mod, "build_fast_model", lambda s: "FAKE_FAST")
    monkeypatch.setattr(wf_mod, "build_reasoning_model", lambda s: "FAKE_REASON")

    async def fake_router(content, model, s):
        return RouterOutput(language="HTML"), None
    monkeypatch.setattr(dspy_mod, "execute_router_node", fake_router)

    async def fake_architect(task, model, s):
        return ArchitectOutput(
            plan_id="p1", global_architecture="1 fichier",
            subtasks=[ArchitectTask(task_id="st1", description="tri à bulles",
                                    target_files=["index.html"])],
        ), None
    monkeypatch.setattr(dspy_mod, "execute_architect_node", fake_architect)

    async def fake_coder(sub, model, s):
        return CoderOutput(task_id=sub["id"], status="success", details="ok"), None
    async def fake_tester(sub, model, s):
        return CoderOutput(task_id=sub["id"], status="success", details="ok"), None
    async def fake_security(sub, model, s):
        return SecurityOutput(task_id=sub["id"], is_secure=True, vulnerabilities=[]), None
    monkeypatch.setattr(nodes_mod, "execute_coder_node", fake_coder)
    monkeypatch.setattr(nodes_mod, "execute_tester_node", fake_tester)
    monkeypatch.setattr(dspy_mod, "execute_security_reviewer_node", fake_security)

    async def fake_judge(sub, test_res, sec_res, model, s):
        return CodeJudgeOutput(task_id=sub["id"], is_approved=True,
                               final_feedback="ok"), None
    monkeypatch.setattr(dspy_mod, "execute_code_judge_node", fake_judge)


def test_e2e_disabled_uses_raw_prompt(monkeypatch):
    """prompt_refiner_enabled=False → le nœud n'est jamais appelé, prompt brut conservé."""
    import graph_orchestrator.dspy_nodes as dspy_mod
    from graph_orchestrator.workflows import run_coding_workflow

    calls = {"n": 0}
    async def fake_refiner(raw, model, s):
        calls["n"] += 1
        return PromptRefinerOutput(refined_prompt="NE DOIT PAS ÊTRE UTILISÉ"), None
    monkeypatch.setattr(dspy_mod, "execute_prompt_refiner_node", fake_refiner)

    _mock_other_nodes(monkeypatch)
    out, _ = asyncio.run(run_coding_workflow(_seed_tasks(), _settings_full(prompt_refiner_enabled=False)))

    assert calls["n"] == 0  # nœud jamais appelé
    # Le workflow tourne jusqu'au bout malgré l'opt-out (pas de crash).
    assert out is not None


def test_e2e_enabled_calls_refiner_and_uses_refined(monkeypatch):
    """prompt_refiner_enabled=True → nœud appelé, prompt raffiné propagé à l'Architect."""
    import graph_orchestrator.dspy_nodes as dspy_mod
    from graph_orchestrator.workflows import run_coding_workflow

    refined_text = "## Objectif\nTri à bulles visuel clarifié par le PromptRefiner."
    calls = {"n": 0, "raw_received": None}
    async def fake_refiner(raw, model, s):
        calls["n"] += 1
        calls["raw_received"] = raw
        return PromptRefinerOutput(refined_prompt=refined_text, ambiguities_detected=[]), None
    monkeypatch.setattr(dspy_mod, "execute_prompt_refiner_node", fake_refiner)

    # Capture l'input reçu par l'Architect pour vérifier la propagation.
    arch_calls = {"content_received": None}
    async def fake_architect(task, model, s):
        arch_calls["content_received"] = task.get("content", "")
        from graph_orchestrator.models import ArchitectOutput, ArchitectTask
        return ArchitectOutput(
            plan_id="p1", global_architecture="x",
            subtasks=[ArchitectTask(task_id="st1", description="x", target_files=["index.html"])],
        ), None
    monkeypatch.setattr(dspy_mod, "execute_architect_node", fake_architect)
    _mock_other_nodes(monkeypatch)  # remet execute_architect_node mocké génériquement...

    # ...mais on veut le NOTRE (capture). On le remet après _mock_other_nodes.
    monkeypatch.setattr(dspy_mod, "execute_architect_node", fake_architect)

    asyncio.run(run_coding_workflow(_seed_tasks(), _settings_full(prompt_refiner_enabled=True)))

    assert calls["n"] == 1  # nœud appelé une fois
    # L'Architect reçoit le prompt RAFFINÉ (le brut + directive router, mais contient le raffiné).
    assert refined_text in arch_calls["content_received"]


def test_e2e_checkpoint_skip_refiner(monkeypatch, tmp_path):
    """refined_prompt présent en checkpoint → le nœud n'est PAS rappelé (économie)."""
    import graph_orchestrator.dspy_nodes as dspy_mod
    from graph_orchestrator.workflows import run_coding_workflow
    from dataclasses import replace

    # Pré-remplit un checkpoint avec un refined_prompt (simule une reprise).
    db = str(tmp_path / "kg_refiner.db")
    from graph_orchestrator.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph(db)
    tasks = _seed_tasks()
    import hashlib
    run_key = tasks[0]["content"].strip().lower()
    run_id = f"coding_{hashlib.sha1(run_key.encode('utf-8')).hexdigest()[:16]}"
    kg.save_checkpoint(run_id, {"refined_prompt": "PROMPT RAFFINÉ PRÉ-EXISTANT"})

    calls = {"n": 0}
    async def fake_refiner(raw, model, s):
        calls["n"] += 1
        return PromptRefinerOutput(refined_prompt="NE DOIT PAS SERVIR"), None
    monkeypatch.setattr(dspy_mod, "execute_prompt_refiner_node", fake_refiner)
    _mock_other_nodes(monkeypatch)

    s = replace(_settings_full(prompt_refiner_enabled=True), kg_path=db, fresh_start=False)
    asyncio.run(run_coding_workflow(tasks, s))

    assert calls["n"] == 0  # nœud skippé grâce au checkpoint
