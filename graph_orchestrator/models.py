"""Contrats de données (Pydantic) échangés entre les nœuds du graphe.

Chaque nœud a une entrée et une sortie strictement typées. Le juge enrichit désormais
son verdict d'une évaluation détaillée par tâche (assessments), pour juger la qualité
réelle des summaries et pas seulement le confidence_score.
"""

import json
import os
import requests
import re
from typing import List, Optional, Any, Literal, get_args, get_origin
from pydantic import BaseModel, Field, ValidationError


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
    # F-82 : critères de validation générés par l'Architecte (pilote unique). Remplacent
    # les prompts fixes/génériques par des critères spécifiques au cahier des charges.
    # Vides = repli sur le comportement historique (rétrocompat checkpoint + tests mockés).
    #   - visual_success_criteria : assertions visuelles concrètes pour l'auto-validation
    #     du Coder (ex: "barres visibles au chargement"). Anti-biais : force le Coder à
    #     ANALYSER son screenshot au lieu d'excuser un visuel vide (bug canvas 2026-08-08).
    #   - functional_test_criteria : assertions de comportement pour le Tester (remplace
    #     la checklist F-46 regex quand non vide). Plus précis car produit par compréhension.
    #   - acceptance_rubric : critères d'acceptation pondérés pour le Judge (concaténé au
    #     task_requirements global). Évite que le Judge devine l'importance relative.
    visual_success_criteria: List[str] = []
    functional_test_criteria: List[str] = []
    acceptance_rubric: str = ""


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
    vision_ok: bool = Field(default=False, description="Pour une tâche Frontend, as-tu navigué sur la page ET vérifié la console (screenshot n'est plus requis) ?")

class DrafterOutput(BaseModel):
    """Résultat du nœud Algorithm Drafter (plan d'implémentation, pas du code brut)."""
    task_id: str
    draft_markdown: str = Field(description="Plan d'implémentation structuré par fichier (intention + logique + edge cases). PAS de code brut complet.")

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
    root_cause: str = Field(default="", description="Cause racine précise du bug ou du rejet (ex: variable hors de portée à la ligne 286).")
    fix_instruction: str = Field(default="", description="Instruction chirurgicale de correction pour le Coder (ex: remplacer l'accès board[i][c] par une boucle for dédiée).")
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


class ConsolidationAction(BaseModel):
    """Action de consolidation émise par le LLM-juge sur un claim numéroté (1-based).

    Port Python du type ConsolidationAction de qm (consolidation.ts) en JSON typé.
    Le LLM-juge reçoit N claims numérotés 1..N et émet des actions pour dédupliquer
    et fusionner les claims redondants ou évolutifs. L'applier déterministe
    (apply_consolidation_actions, 0 LLM) consomme ensuite ces actions.
    """
    kind: Literal["update", "delete", "add"]
    index: Optional[int] = None  # 1-based pour update/delete (numérotation qm)
    text: Optional[str] = None  # nouveau texte pour update/add


class ConsolidationOutput(BaseModel):
    """Résultat d'une consolidation de claims par le LLM-juge (F-68 Phase 1, P6-ter).

    Le nœud execute_consolidation_node lit les claims d'une entité (file:task_id),
    les numérote, demande à un LLM-juge d'émettre des actions UPDATE/DELETE/ADD
    (format qm line-oriented adapté en JSON typé — plus fiable sur 9B que du texte
    libre), puis applique ces actions via apply_consolidation_actions (déterministe,
    0 LLM). But : éviter que le KG DuckDB ne grossisse indéfiniment avec des
    réfutations rabâchées d'une itération à l'autre.
    """
    entity_id: str
    actions: List[ConsolidationAction] = []
    summary: str = ""


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

def _fill_required_defaults(data: dict, model_class: type[BaseModel]) -> dict:
    """F-168 : remplit les champs Pydantic requis absents/None par un défaut typé.

    Le sauvetage LLM répare la STRUCTURE (quotes/braces) ; sa règle historique
    « mets null si un champ manque » violait les champs requis (str, Literal) →
    ValidationError ``string_type`` DANS le sauvetage lui-même (run 1835,
    Tester it.1). Un placeholder typé n'invente pas de contenu :
    Literal→"failure" si présent (fail-closed), str→"", int→0, float→0.0,
    bool→False. Les champs optionnels (None valide) et les annotations
    inconnues ne sont pas touchés (l'erreur restera, comportement historique).
    """
    for name, field in model_class.model_fields.items():
        if data.get(name) is not None:
            continue
        if not field.is_required():
            continue  # optionnel : None est déjà valide
        ann = field.annotation
        if get_origin(ann) is Literal:
            args = get_args(ann)
            data[name] = "failure" if "failure" in args else args[0]
        elif ann is str:
            data[name] = ""
        elif ann is int:
            data[name] = 0
        elif ann is float:
            data[name] = 0.0
        elif ann is bool:
            data[name] = False
    return data


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
    except (ValidationError, json.JSONDecodeError):
        # F-168 : passe DÉTERMINISTE avant tout LLM. Les null sur champs requis
        # (générés par les petits modèles dans final_answer) se réparent sans
        # réseau : Literal→"failure" (fail-closed), str→"", numérique→0.
        # 0 LLM, 0 latence — si le JSON est vraiment illisible, on continue
        # vers le sauvetage LLM (structure quotes/braces).
        try:
            _det = json.loads(raw_json)
            if isinstance(_det, dict):
                return model_class.model_validate(
                    _fill_required_defaults(_det, model_class)
                )
        except Exception:
            pass

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

            # F-168 : BORNÉ. Le sauvetage ne répare que la STRUCTURE d'un JSON
            # de verdict (quelques centaines de tokens) — avant : aucun cap ni
            # timeout → génération en fuite de 25+ min observée (run 1835,
            # serveur 9B à 5,4 t/s). max_tokens 1200 + timeout 300 s + temp 0.
            lm = dspy.LM(
                f"openai/{use_model_id}",
                api_base=use_api_base,
                api_key=settings.local_api_key,
                max_tokens=1200,
                timeout=300,
                temperature=0.0,
            )
            with dspy.context(lm=lm):
                class JSONFixSignature(dspy.Signature):
                    """Récupère le JSON cassé en extrayant les champs du schéma cible depuis le texte.

                    RÈGLES DE FIDÉLITÉ STRICTE :
                    1. N'invente JAMAIS une valeur absente du texte source — si un champ
                       manque, mets la chaîne vide ``""`` (JAMAIS ``null`` : les champs
                       du schéma sont requis), n'invente pas.
                    2. Ne corrige que la STRUCTURE (quotes/braces manquants, clés mal placées),
                       pas le SENS du contenu. Le texte d'origine est la seule source de vérité.
                    3. Si le texte est totalement illisible (pas du tout du JSON), renvoie ``{}``.
                    4. Préserve les chaînes exactes (ne « nettoie » pas, ne reformule pas).
                    """
                    broken_text: str = dspy.InputField(desc="Le texte JSON cassé/brisé à récupérer")
                    fixed_json: str = dspy.OutputField(desc="Le JSON réparé, en TEXTE BRUT (objet {...} valide, jamais null sur un champ)")

                predictor = dspy.Predict(JSONFixSignature)
                # F-61 (post-mortem run partiel 1h30) : tronquer le payload envoyé au
                # sauvetage LLM. Le sauvetage ne répare que la STRUCTURE (quotes/braces
                # manquants), pas le sens — les 1ers caractères contiennent le JSON
                # produit par final_answer. Sur un payload énorme (Tester rendant tout
                # son historique d'observations dans final_answer), le sauvetage lui-même
                # crashait en Connection error (serveur LLM surchargé) → feedback loop
                # (Pydantic fail → sauvetage fail → None → retry → plus de contexte →
                # Pydantic fail…). Limiter à 6000 chars casse la boucle.
                _rescue_text = str(response)[:6000]
                result = predictor(broken_text=_rescue_text)
                fixed_text = str(result.fixed_json or "").strip()
                # Extraction défensive du {...} (le modèle peut encadrer de prose).
                _m = re.search(r'(\{.*\})', fixed_text, re.DOTALL)
                payload = _m.group(1).strip() if _m else fixed_text
                _data = json.loads(payload)
                if not isinstance(_data, dict):
                    raise ValueError("le JSON réparé n'est pas un objet")
                return model_class.model_validate(
                    _fill_required_defaults(_data, model_class)
                )
        except Exception as dspy_e:
            print(f"[-] Le sauvetage DSPy a échoué : {dspy_e}")
            return None
