"""Contrats de données (Pydantic) échangés entre les nœuds du graphe.

Chaque nœud a une entrée et une sortie strictement typées. Le juge enrichit désormais
son verdict d'une évaluation détaillée par tâche (assessments), pour juger la qualité
réelle des summaries et pas seulement le confidence_score.
"""

import json
import os
import requests
import re
from typing import List, Optional, Any, Literal, Dict, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator, ValidationError


# ==========================================
# Schéma de sévérité partagé (Rubric Judge + Security — P6)
# ==========================================

Severity = Literal["critical", "high", "medium", "low"]


class Finding(BaseModel):
    """Un retour structuré du Judge ou du Security Reviewer (rubric de sévérité P6).

    Remplace les listes plates de strings par un retour ancré sur le code et classé par
    gravité, pour stopper l'enlisement du Judge sur des « nits » (débats de nommage) et
    forcer la priorisation (fiche 17 : In-Diff Only + Anti-Nits, inspiré Open-SWE Reviewer
    + Claude Code 2.0 « professional objectivity »).

    - ``severity`` suit l'échelle CVSS/OWASP : critical (exploitable / data loss / crash)
      > high (faille fonctionnelle) > medium (robustesse) > low (nit, style).
    - ``category`` : axe du retour (security / correctness / performance / testing /
      maintainability / documentation…).
    - ``location`` : ancrage in-diff (fichier + ligne/fragment) — JAMAIS une critique vague
      sur l'ensemble du fichier quand seul un fragment a changé.
    - ``description`` : problème observé, factuel. ``suggestion`` : correctif actionnable.
    """

    severity: Severity
    category: str
    location: str = ""
    description: str
    suggestion: str = ""


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
    # F-29 : stratégie de construction que le Coder doit suivre. L'Architect dicte
    # COMMENT construire, pas juste QUOI. Par défaut 'simple' (rétro-compat : un
    # sous-tâche historique sans stratégie = un seul write_file, comme avant).
    #   - 'simple'      : petit fichier isolé, 1 seul write_file (script Python < ~200 lignes).
    #   - 'incremental' : gros fichier monolithique (HTML dashboard) → squelette AVEC
    #                     marqueurs d'insertion ouverts + append par section (corrige le
    #                     bug dashboard : on n'append PAS après </html> fermé).
    #   - 'multifile'   : 1 module logique = 1 fichier (Python/TS) — chaque fichier
    #                     reste petit et autonome. La sous-tâche liste ses target_files.
    strategy: Literal["simple", "incremental", "multifile"] = "simple"
    # Si strategy='incremental', liste des sections à construire une par une via
    # append_file (ex: ['CSS', 'sidebar', 'KPI', 'table', 'JS']). Vide sinon.
    sections: List[str] = []
    # F-57 (Priorité 10) : skills à injecter au Coder pour cette sous-tâche. L'Architect
    # sélectionne dans le catalogue des skills disponibles (frontend-design pour du web,
    # python-health-audit pour du Python, devtools-preview pour validation visuelle...).
    skills: List[str] = []
    tester_skills: List[str] = []
    judge_skills: List[str] = []


class RouterOutput(BaseModel):
    """Contrat JSON strict et minimaliste pour le routage par le petit modèle."""
    language: str

class ArchitectOutput(BaseModel):
    """Le plan global généré par l'Architecte."""
    plan_id: str
    global_architecture: str
    subtasks: List[ArchitectTask]


class PromptRefinerOutput(BaseModel):
    """Spec structurée produite par le PromptRefiner, à consommer par l'Architect.

    Le PromptRefiner (dspy_nodes.py) reformule le prompt utilisateur brut en une spec
    claire et structurée AVANT l'Architect, en s'inspirant du pattern "Enhance Prompt"
    de Kilo Code / Cline / Roo Code (réécriture LLM du prompt). Le `refined_prompt`
    remplace le prompt brut dans `seed_tasks[0]['content']` et est propagé à l'Architect,
    au Tester (via original_content) et au Judge (via task_requirements).

    `ambiguities_detected` est une liste de transparence (termes vagues repérés dans le
    prompt brut type 'fast', 'user-friendly', 'flexible'...) : elle ne sert pas en aval,
    mais permet d'observer la qualité du raffinement dans les logs.
    """
    refined_prompt: str
    ambiguities_detected: List[str] = []


class CoderOutput(BaseModel):
    """Résultat d'un nœud Coder (exécution de code / modification de fichiers)."""
    task_id: str
    status: Literal["success", "failure"]
    details: str
    linter_ok: bool = Field(default=False, description="As-tu vérifié ton code via le linter ou un test unitaire ?")
    vision_ok: bool = Field(default=False, description="Pour une tâche Frontend, as-tu navigué sur la page ET pris un screenshot pour vérifier le rendu visuel ?")
class SecurityOutput(BaseModel):
    """Verdict du noeud d'audit de sécurité sur le code généré."""
    task_id: str
    is_secure: bool
    vulnerabilities: List[str]
    # P6 (Rubric Security) : retours structurés par sévérité (échelle CVSS), ancrés sur le
    # code (location) et actionnables (suggestion). Additif — défaut [] = rétro-compatible
    # avec les checkpoints existants et les tests qui construisent SecurityOutput(...) sans
    # ce champ. ``vulnerabilities`` (liste plate) est conservé pour le Judge qui le consomme.
    findings: List[Finding] = []


class CodeJudgeOutput(BaseModel):
    """Verdict final de la Pull Request par le Juge du code."""
    task_id: str
    is_approved: bool
    final_feedback: str
    # P6 (Rubric Judge) : retours structurés par sévérité (critical/high/medium/low), ancrage
    # in-diff only (location), anti-nits (un 'low' seul ne justifie pas un rejet). Additif —
    # défaut [] = rétro-compatible avec les checkpoints existants et les tests qui construisent
    # CodeJudgeOutput(...) sans ce champ. ``final_feedback`` reste le résumé actionnable.
    findings: List[Finding] = []


class EscalationOutput(BaseModel):
    """Diagnostic post-mortem produit par le nœud d'escalade (Priorité 3, F-23).

    Quand le Circuit Breaker s'active (3 itérations Coder↔Tester↔Judge toutes
    rejetées), ce nœud synthétise les réfutations accumulées dans le Knowledge
    Graph en un diagnostic actionnable, plutôt que d'abandonner la sous-tâche
    sans retour exploitable. Le diagnostic est persisté dans le KG
    (kind="escalation") et relié aux réfutations via des arêtes ESCALATES.
    """
    task_id: str
    root_cause: str  # cause racine la plus probable de l'échec répété
    attempted_fixes: List[str]  # résumé de ce qui a été tenté (anti-répétition future)
    lesson: str  # recommandation actionnable / leçon apprise pour un run futur
    severity: Literal["low", "medium", "high"]  # gravité de l'échec


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

def extract_and_validate(response: Any, model_class: type[BaseModel], api_base: Optional[str] = None, model_id: Optional[str] = None) -> Optional[BaseModel]:
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
        # Garde anti-fuite d'abstraction : un test unitaire de parsing NE DOIT PAS
        # déclencher d'appel LLM (réseau, latence, hallucination). La variable
        # PYTEST_CURRENT_TEST est posée par pytest pendant l'exécution d'un test ;
        # on l'utilise pour court-circuiter le sauvetage et retourner None (comportement
        # strict attendu par les tests). En production, le sauvetage reste actif.
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return None

        print(f"[-] Pydantic a échoué. Tentative de sauvetage avec DSPy pour {model_class.__name__}...")
        try:
            import dspy
            from graph_orchestrator.config import settings
            import logging
            logging.getLogger("dspy").setLevel(logging.CRITICAL)
            
            # F-58 : provider openai/ contre llama-server (avant : ollama_chat/ → /api/chat Ollama).
            # api_base garde /v1 (llama-server expose /v1).
            use_api_base = api_base or settings.local_api_base
            use_model_id = model_id or settings.fast_model_id
            
            # Fetch actual model ID from llama-server to avoid litellm NotFoundError
            try:
                resp = requests.get(f"{use_api_base.rstrip('/')}/models", timeout=2)
                if resp.status_code == 200:
                    models_data = resp.json()
                    if "data" in models_data and len(models_data["data"]) > 0:
                        use_model_id = models_data["data"][0]["id"]
            except Exception:
                pass
                
            if use_model_id == "default":
                use_model_id = "llama"
            
            lm = dspy.LM(f"openai/{use_model_id}", api_base=use_api_base, api_key=settings.local_api_key)
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
