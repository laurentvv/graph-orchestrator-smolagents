import pytest
import asyncio
from unittest.mock import patch, MagicMock

from graph_orchestrator.dspy_nodes import (
    execute_router_node,
    execute_architect_node,
    execute_security_reviewer_node,
    execute_code_judge_node,
)
from graph_orchestrator.models import (
    RouterOutput,
    ArchitectOutput,
    ArchitectTask,
    SecurityOutput,
    CodeJudgeOutput,
)


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.fast_model_id = "mock-fast-model"
    settings.reasoning_model_id = "mock-reasoning-model"
    settings.reasoning_no_think_model_id = "mock-reasoning-model"
    settings.local_api_base = "http://localhost:11434/v1"
    # F-58 specs
    settings.fast_spec = MagicMock(backend="external", model="mock-fast-model", api_base="http://localhost:11434/v1", api_key="sk-mock")
    settings.reasoning_spec = MagicMock(backend="external", model="mock-reasoning-model", api_base="http://localhost:11434/v1", api_key="sk-mock")
    settings.no_think_spec = MagicMock(backend="external", model="", api_base="http://localhost:11434/v1", api_key="sk-mock")
    
    # Champs de troncature utilisés par execute_code_judge_node (Priorité 2).
    # Doivent être des int réels, pas des MagicMock, sinon truncate_output crash.
    settings.stderr_head_lines = 20
    settings.stderr_tail_lines = 20
    settings.feedback_max_chars = 2000
    return settings


@patch("graph_orchestrator.dspy_nodes._configure_dspy")
@patch("graph_orchestrator.dspy_nodes.dspy.ChainOfThought")
def test_execute_router_node(mock_cot, mock_configure, mock_settings):
    """
    Test le nœud DSPy de routage.
    On vérifie que le JSON (typé RouterOutput) est bien extrait et retourné.
    """
    mock_instance = MagicMock()
    mock_prediction = MagicMock()
    
    mock_prediction.output = RouterOutput(
        language="javascript"
    )
    mock_instance.return_value = mock_prediction
    mock_cot.return_value = mock_instance

    output, metrics = asyncio.run(execute_router_node("Créer un jeu Tetris", mock_settings.fast_model_id, mock_settings))

    assert output is not None
    assert output.language == "javascript"
    assert metrics.node == "router_dspy"
    mock_cot.assert_called_once()


@patch("graph_orchestrator.dspy_nodes._configure_dspy")
@patch("graph_orchestrator.dspy_nodes.dspy.ChainOfThought")
def test_execute_architect_node(mock_cot, mock_configure, mock_settings):
    """
    Test le nœud DSPy Architecte.
    Vérifie qu'il décompose bien la tâche en utilisant le modèle lourd.
    """
    mock_instance = MagicMock()
    mock_prediction = MagicMock()
    
    mock_prediction.output = ArchitectOutput(
        plan_id="plan-tetris",
        global_architecture="Architecture MVC basique.",
        subtasks=[
            ArchitectTask(task_id="T1", description="Moteur de gravité", target_files=[]),
            ArchitectTask(task_id="T2", description="Interface HTML", target_files=["index.html"]),
        ]
    )
    mock_instance.return_value = mock_prediction
    mock_cot.return_value = mock_instance

    task_dict = {"id": "tetris", "content": "Jeu Tetris Complet"}
    output, metrics = asyncio.run(execute_architect_node(task_dict, mock_settings.reasoning_model_id, mock_settings))

    assert output is not None
    assert len(output.subtasks) == 2
    assert output.subtasks[0].task_id == "T1"
    assert metrics.model == "mock-reasoning-model"


@patch("graph_orchestrator.dspy_nodes._configure_dspy")
@patch("graph_orchestrator.dspy_nodes.dspy.ChainOfThought")
def test_execute_security_reviewer_node(mock_cot, mock_configure, mock_settings):
    """
    Test le nœud d'audit de sécurité.
    S'assure qu'il peut traiter le code et retourner la liste des vulnérabilités (SecurityVulnerability).
    """
    mock_instance = MagicMock()
    mock_prediction = MagicMock()
    
    # Simulation d'une faille trouvée
    mock_prediction.output = SecurityOutput(
        task_id="T2",
        is_secure=False,
        vulnerabilities=[
            "Injection XSS possible via innerHTML"
        ]
    )
    mock_instance.return_value = mock_prediction
    mock_cot.return_value = mock_instance

    subtask_dict = {"id": "T2", "description": "Interface HTML", "target_files": []}
    
    output, metrics = asyncio.run(execute_security_reviewer_node(subtask_dict, mock_settings.reasoning_model_id, mock_settings))

    assert output is not None
    assert output.is_secure is False
    assert len(output.vulnerabilities) == 1
    assert "XSS" in output.vulnerabilities[0]


@patch("graph_orchestrator.dspy_nodes._configure_dspy")
@patch("graph_orchestrator.dspy_nodes.dspy.ChainOfThought")
def test_execute_code_judge_node(mock_cot, mock_configure, mock_settings):
    """
    Test le Juge final.
    Doit vérifier que les retours (tests, sécurité) sont bien assimilés
    et aboutissent à une décision stricte (booléenne).
    """
    mock_instance = MagicMock()
    mock_prediction = MagicMock()
    
    # Simulation du refus du juge à cause du security reviewer
    mock_prediction.output = CodeJudgeOutput(
        task_id="T2",
        is_approved=False,
        final_feedback="Le code contient une faille XSS signalée par l'auditeur. Corrigez `innerHTML`."
    )
    mock_instance.return_value = mock_prediction
    mock_cot.return_value = mock_instance

    subtask_dict = {"id": "T2", "target_files": []}
    
    # Création d'un faux résultat de sécurité
    security_res = SecurityOutput(
        task_id="T2",
        is_secure=False,
        vulnerabilities=["XSS"]
    )
    
    output, metrics = asyncio.run(execute_code_judge_node(
        subtask_dict, 
        "TESTS: SUCCESS", 
        security_res, 
        mock_settings.reasoning_model_id, 
        mock_settings
    ))

    assert output is not None
    assert output.is_approved is False
    assert "faille XSS" in output.final_feedback
