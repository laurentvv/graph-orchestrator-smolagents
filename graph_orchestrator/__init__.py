"""Graph Orchestrator : architecture Fan-out -> Judge -> Synthesize avec smolagents.

Implémente le modèle Diamant du guide (§3) + fiabilité avancée (§5) :
vérification adversaire, cycles loop-until-dry, human-in-the-loop.
"""

from .config import Settings, settings
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
]

__version__ = "0.3.0"
