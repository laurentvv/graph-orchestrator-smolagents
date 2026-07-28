"""Contrats de données (Pydantic) échangés entre les nœuds du graphe.

Chaque nœud a une entrée et une sortie strictement typées. Le juge enrichit désormais
son verdict d'une évaluation détaillée par tâche (assessments), pour juger la qualité
réelle des summaries et pas seulement le confidence_score.
"""

import json
import re
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ValidationError


# ==========================================
# Sorties des nœuds
# ==========================================

class WorkerOutput(BaseModel):
    """Résultat d'un worker (nœud Fan-out)."""
    task_id: str
    summary: str
    confidence_score: float


class AdversaryVerdict(BaseModel):
    """Verdict d'un sceptique sur UNE tâche (§5 : vérification adversaire)."""
    task_id: str
    refuted: bool  # True = le sceptique a réussi à réfuter le summary
    reason: str


class ReduceOutput(BaseModel):
    """Résultat du nœud Reduce : flatten + dedupe + filter (§3, code pur, 0 token)."""
    kept: List[WorkerOutput]
    dropped_count: int
    reason: str


class TaskAssessment(BaseModel):
    """Évaluation qualitative d'une tâche par le Juge (agrégation des sceptiques)."""
    task_id: str
    verdict: Literal["approved", "rejected"]
    reason: str


class JudgeOutput(BaseModel):
    """Verdict du Juge, avec détail par tâche.

    En mode adversaire, les assessments sont construits par agrégation des sceptiques
    (vote à la majorité), pas par un seul LLM.
    """
    is_valid: bool
    reason: str
    approved_tasks: List[str]
    assessments: List[TaskAssessment]


class FinalSynthesis(BaseModel):
    """Synthèse finale agrégée."""
    global_summary: str
    key_insights: List[str]


# ==========================================
# Extraction / validation JSON robuste
# ==========================================

def extract_and_validate(response: Any, model_class: type[BaseModel]) -> Optional[BaseModel]:
    """Extrait et valide le JSON, qu'il soit dict natif, string, ou encapsulé dans
    un bloc markdown ```json ... ```.

    smolagents renvoie généralement une string (le contenu de l'outil final_answer),
    mais on tolère aussi un dict ou un objet déjà validé.
    """
    try:
        if isinstance(response, model_class):
            return response

        if isinstance(response, dict):
            raw_json = json.dumps(response)
        else:
            text = str(response)
            # 1) Bloc markdown explicite : ```json ... ``` ou ``` ... ```
            match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
            raw_json = match.group(1).strip() if match else text.strip()

            # 2) Si ce n'est pas encore un objet JSON, on extrait la première {...}
            if not raw_json.startswith('{'):
                match = re.search(r'(\{.*\})', text, re.DOTALL)
                if match:
                    raw_json = match.group(1).strip()

        return model_class.model_validate_json(raw_json)
    except (ValidationError, json.JSONDecodeError) as e:
        print(f"[-] Échec de validation du contrat de données pour {model_class.__name__} : {e}")
        return None
