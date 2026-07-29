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


class ArchitectTask(BaseModel):
    """Une sous-tâche de codage isolée générée par l'Architecte."""
    task_id: str
    description: str
    target_files: List[str]


class RouterOutput(BaseModel):
    """Contrat JSON strict et minimaliste pour le routage par le petit modèle."""
    language: str

class ArchitectOutput(BaseModel):
    """Le plan global généré par l'Architecte."""
    plan_id: str
    global_architecture: str
    subtasks: List[ArchitectTask]


class CoderOutput(BaseModel):
    """Résultat d'un nœud Coder (exécution de code / modification de fichiers)."""
    task_id: str
    status: Literal["success", "failure"]
    details: str


class SecurityOutput(BaseModel):
    """Verdict du noeud d'audit de sécurité sur le code généré."""
    task_id: str
    is_secure: bool
    vulnerabilities: List[str]


class CodeJudgeOutput(BaseModel):
    """Verdict final de la Pull Request par le Juge du code."""
    task_id: str
    is_approved: bool
    final_feedback: str


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
        print(f"[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour {model_class.__name__}...")
        try:
            import dspy
            from graph_orchestrator.config import settings
            import logging
            logging.getLogger("dspy").setLevel(logging.CRITICAL)
            
            # Utilisation du petit modèle (très rapide) via Ollama Guided Decoding ou DSPy typed
            lm = dspy.LM(f"ollama_chat/{settings.fast_model_id}", api_base=settings.ollama_api_base.replace("/v1", ""), api_key=settings.ollama_api_key)
            with dspy.context(lm=lm):
                class JSONFixSignature(dspy.Signature):
                    """Extract the exact JSON fields from the broken text into the correct schema."""
                    broken_text: str = dspy.InputField()
                    fixed_data: model_class = dspy.OutputField()
                
                predictor = dspy.Predict(JSONFixSignature)
                result = predictor(broken_text=str(response))
                return result.fixed_data
        except Exception as dspy_e:
            print(f"[-] Le sauvetage DSPy a échoué : {dspy_e}")
            return None
