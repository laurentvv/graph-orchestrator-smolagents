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
@patch("graph_orchestrator.dspy_nodes.dspy.ReAct")
@patch("graph_orchestrator.dspy_nodes.dspy.ChainOfThought")
def test_execute_architect_node(mock_cot, mock_react, mock_configure, mock_settings):
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

    mock_react_instance = MagicMock()
    mock_react_prediction = MagicMock()
    mock_react_prediction.research_summary = "Aucun skill ajouté"
    mock_react_instance.return_value = mock_react_prediction
    mock_react.return_value = mock_react_instance

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


@patch("graph_orchestrator.dspy_nodes._configure_dspy")
@patch("graph_orchestrator.dspy_nodes.dspy.ChainOfThought")
def test_execute_code_judge_node_injects_git_diff_block(mock_cot, mock_configure, mock_settings, tmp_path):
    """F-70 : en iter >1, le Judge reçoit le bloc diff (doctrine IN-DIFF ONLY) dans ``code``.

    ``subtask["git_diff"]`` est déjà propagé par F-53 ; le nœud le lit et le passe
    au LLM en tête du champ ``code``, suivi du code complet. Ce test garantit que
    le branchement F-70 (a) envoie bien le diff jusqu'au predictor mocké.
    """
    mock_instance = MagicMock()
    mock_prediction = MagicMock()
    mock_prediction.output = CodeJudgeOutput(
        task_id="T2", is_approved=True, final_feedback="ok"
    )
    mock_instance.return_value = mock_prediction
    mock_cot.return_value = mock_instance

    f = tmp_path / "index.html"
    f.write_text("<html><body>hi</body></html>", encoding="utf-8")
    diff = "diff --git a/index.html b/index.html\n-old\n+new"

    subtask_dict = {"id": "T2", "target_files": [str(f)], "git_diff": diff}
    security_res = SecurityOutput(task_id="T2", is_secure=True, vulnerabilities=[])

    asyncio.run(execute_code_judge_node(
        subtask_dict, "TESTS: SUCCESS", security_res,
        mock_settings.reasoning_model_id, mock_settings,
    ))

    code_arg = mock_instance.call_args.kwargs["code"]
    assert "DIFF MODIFIÉ" in code_arg        # bloc diff injecté en tête
    assert diff in code_arg                  # contenu du diff
    assert "CODE COMPLET" in code_arg        # full-file tronqué pour le contexte
    assert "IN-DIFF ONLY" in code_arg        # doctrine ancrée


@patch("graph_orchestrator.dspy_nodes._configure_dspy")
@patch("graph_orchestrator.dspy_nodes.dspy.ChainOfThought")
def test_execute_code_judge_node_iter1_full_file_no_diff_block(mock_cot, mock_configure, mock_settings, tmp_path):
    """F-70 : en iter 1 (diff absent), le Judge reçoit le full-file sans bloc diff (rétrocompat)."""
    mock_instance = MagicMock()
    mock_prediction = MagicMock()
    mock_prediction.output = CodeJudgeOutput(
        task_id="T3", is_approved=True, final_feedback="ok"
    )
    mock_instance.return_value = mock_prediction
    mock_cot.return_value = mock_instance

    f = tmp_path / "app.js"
    f.write_text("console.log('hello');", encoding="utf-8")

    subtask_dict = {"id": "T3", "target_files": [str(f)]}  # pas de clé git_diff
    security_res = SecurityOutput(task_id="T3", is_secure=True, vulnerabilities=[])

    asyncio.run(execute_code_judge_node(
        subtask_dict, "TESTS: SUCCESS", security_res,
        mock_settings.reasoning_model_id, mock_settings,
    ))

    code_arg = mock_instance.call_args.kwargs["code"]
    assert "console.log('hello');" in code_arg   # contenu du fichier
    assert "DIFF MODIFIÉ" not in code_arg        # pas de bloc diff en iter 1
    assert "```diff" not in code_arg


@patch("graph_orchestrator.dspy_nodes._configure_dspy")
@patch("graph_orchestrator.dspy_nodes.dspy.ChainOfThought")
def test_execute_code_judge_node_blocks_when_security_unavailable(mock_cot, mock_configure, mock_settings):
    """Fail-closed (post-mortem run 123955) : security_res=None → approbation bloquée,
    SANS appeler le LLM Judge. Avant ce fix, None était transformé en "Aucune vulnérabilité"
    → le Juge approuvait à l'aveugle un code non audité."""
    subtask_dict = {"id": "T2", "target_files": []}

    output, metrics = asyncio.run(execute_code_judge_node(
        subtask_dict,
        "TESTS: SUCCESS",
        None,  # security_res=None : audit Security en échec
        mock_settings.reasoning_model_id,
        mock_settings,
    ))

    # Verdict fail-closed : jamais approuvé sans audit sécurité
    assert output is not None
    assert output.is_approved is False
    # Un finding critical documente le blocage
    assert any(f.severity == "critical" for f in output.findings)
    assert "INDISPONIBLE" in output.final_feedback or "bloqué" in output.final_feedback.lower()

    # Hard block : le LLM Judge ne doit PAS être appelé (économise le budget,
    # rend l'approbation impossible quelle que soit la sortie du modèle)
    mock_cot.assert_not_called()
    assert mock_configure.call_count == 0

    # Métriques présentes (pour l'observabilité du post-mortem)
    assert metrics is not None
    assert metrics.input_tokens == 0  # aucun appel LLM

