"""Tests unitaires de la stratégie de découpage adaptative (F-29, Architect évolué).

Vérifie que l'Architect peut émettre une stratégie PAR sous-tâche et qu'elle se
propage jusqu'au sub_dict consommé par le Coder. Déterministe, 0 LLM.
"""
from graph_orchestrator.models import ArchitectTask, ArchitectOutput


def test_architect_task_default_strategy_is_simple():
    """Rétro-compat : une sous-tâche sans stratégie explicite = 'simple'."""
    t = ArchitectTask(task_id="s1", description="d", target_files=["x.py"])
    assert t.strategy == "simple"
    assert t.sections == []


def test_architect_task_strategy_incremental_with_sections():
    """Strategy 'incremental' + sections (le cas dashboard)."""
    t = ArchitectTask(
        task_id="dashboard",
        description="d",
        target_files=["index.html"],
        strategy="incremental",
        sections=["css", "sidebar", "kpi", "table", "js"],
    )
    assert t.strategy == "incremental"
    assert len(t.sections) == 5


def test_architect_task_strategy_multifile():
    """Strategy 'multifile' (le cas Python/TS multi-modules)."""
    t = ArchitectTask(
        task_id="api",
        description="d",
        target_files=["models.py", "api.py", "utils.py"],
        strategy="multifile",
    )
    assert t.strategy == "multifile"
    assert t.sections == []  # multifile n'utilise pas de sections


def test_architect_task_invalid_strategy_rejected():
    """Une stratégie invalide est rejetée par Pydantic (Literal)."""
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ArchitectTask(task_id="s", description="d", target_files=["x"], strategy="bogus")


def test_architect_output_roundtrip_preserves_strategy():
    """Round-trip sérialisation (comme le checkpoint fait ArchitectOutput(**dict))."""
    t = ArchitectTask(
        task_id="s1", description="d", target_files=["index.html"],
        strategy="incremental", sections=["css", "js"],
    )
    out = ArchitectOutput(plan_id="p", global_architecture="g", subtasks=[t])
    d = out.model_dump()
    out2 = ArchitectOutput(**d)
    assert out2.subtasks[0].strategy == "incremental"
    assert out2.subtasks[0].sections == ["css", "js"]


def test_subtask_strategy_propagates_to_sub_dict():
    """La stratégie de l'Architect se propage dans le sub_dict consommé par le Coder.

    Reproduit la logique de workflows.py process_subtask_loop (sub_dict construction),
    SANS lancer le workflow complet. Vérifie que getattr(subtask, 'strategy', 'simple')
    et getattr(subtask, 'sections', []) récupèrent bien les valeurs de l'Architect.
    """
    # Cas 1 : sous-tâche avec stratégie explicitement 'incremental'
    subtask = ArchitectTask(
        task_id="dash", description="d", target_files=["index.html"],
        strategy="incremental", sections=["css", "js"],
    )
    sub_dict = {
        "id": subtask.task_id,
        "strategy": getattr(subtask, "strategy", "simple"),
        "sections": getattr(subtask, "sections", []),
    }
    assert sub_dict["strategy"] == "incremental"
    assert sub_dict["sections"] == ["css", "js"]

    # Cas 2 : sous-tâche sans stratégie (rétro-compat) → défaut 'simple', sections vides
    subtask_simple = ArchitectTask(task_id="x", description="d", target_files=["x.py"])
    sub_dict2 = {
        "id": subtask_simple.task_id,
        "strategy": getattr(subtask_simple, "strategy", "simple"),
        "sections": getattr(subtask_simple, "sections", []),
    }
    assert sub_dict2["strategy"] == "simple"
    assert sub_dict2["sections"] == []
