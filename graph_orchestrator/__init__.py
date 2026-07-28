"""Graph Orchestrator : architecture Fan-out -> Reduce -> Adversaire -> Synth avec smolagents.

Implémente le modèle Diamant du guide (§3), la fiabilité §5 (adversaire, cycles,
HITL) et la mémoire persistante (Phase 5 : Knowledge Graph DuckDB avec provenance).
"""

from .config import Settings, settings
from .hitl import hitl_checkpoint, should_trigger_hitl
from .knowledge_graph import KnowledgeGraph, dedup_key
from .models import (
    AdversaryVerdict,
    FinalSynthesis,
    JudgeOutput,
    ReduceOutput,
    TaskAssessment,
    WorkerOutput,
    extract_and_validate,
)

__all__ = [
    "Settings",
    "settings",
    "WorkerOutput",
    "AdversaryVerdict",
    "ReduceOutput",
    "JudgeOutput",
    "TaskAssessment",
    "FinalSynthesis",
    "extract_and_validate",
    "KnowledgeGraph",
    "dedup_key",
    "hitl_checkpoint",
    "should_trigger_hitl",
]

__version__ = "0.4.0"
