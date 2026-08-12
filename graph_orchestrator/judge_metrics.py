"""Métriques de benchmark du Judge (Precision/Recall/F1, MRR, verdict). F-70 (c).

Ces métriques sont des évaluations **offline** (0 LLM, 0 appel réseau) : elles ne
tournent PAS dans la boucle chaude du graphe. Elles servent à :
- la **P15 (Meta-Analyste)** : quantifier la qualité du Judge au fil des runs
  pour détecter les régressions (un Judge qui se met à valider à tort) ;
- les **regression tests** du Judge : comparer les ``findings`` prédits à un jeu
  de findings attendus (ground truth) sur des cas étiquetés.

Aujourd'hui le Judge n'est évalué que qualitativement (lecture de logs). Ces
métriques rendent l'évaluation reproductible et automatisable.

Référence : ``references/code-review-graph/code_review_graph/eval/scorer.py``
(``compute_precision_recall`` + ``compute_mrr``). Le scorer de référence est
identity-based (matching exact sur des sets/strings opaques) : pour l'appliquer à
nos ``Finding`` (severity/category/location/description), on canonicalise chaque
finding en un ID stable ``"{location}|{category}|{severity}"`` avant le set-match.
La canonicalisation est l'extension consciente vs le scorer de référence (qui ne
gère pas la notion de "même finding détecté à deux endroits").

Politique de match : deux findings sont considérés équivalents s'ils pointent la
même zone (location) avec la même catégorie et la même sévérité. La description
varie d'un run à l'autre (LLM) et n'est PAS inclus dans l'ID — sinon aucun match
ne serait jamais obtenu (paraphrase systématique).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Sequence, Set, Union

from .models import Finding

# Union des formes d'entrée acceptées : objet ``Finding`` (Pydantic, chemin prod)
# ou dictplat (chemin tests/CLIs qui construisent des dicts à la main).
FindingLike = Union[Finding, Dict[str, Any], str]


def _norm(value: Any) -> str:
    """Normalise une chaîne pour l'ID canonique : lowercase + collapse whitespace.

    Défensif sur les types hétérogènes (location peut être absente/None).
    """
    if value is None:
        return ""
    return " ".join(str(value).lower().split())


def canonicalize_finding(finding: FindingLike) -> str:
    """ID stable d'un finding pour le set-matching, insensible à la paraphrase.

    Format : ``"{location}|{category}|{severity}"`` (tous normalisés via ``_norm``).
    La ``description``/``suggestion`` sont volontairement EXCLUES : elles varient
    à chaque run LLM (paraphrase), ce qui rendrait tout match impossible. Le
    triplet location+catégorie+sévérité identifie une "même zone, même problème,
    même gravité" — c'est la sémantique de match attendue pour un benchmark.

    Args:
        finding: Objet ``Finding`` (Pydantic), dict plat
            (``{"severity":..., "category":..., "location":...}``), ou string
            brute (cas dégénéré : la string entière devient l'ID, pour permettre
            le bench sur d'anciennes sorties plates de strings pré-F-44).

    Returns:
        L'ID canonique (str, jamais None, jamais vide si le finding est porteur).
    """
    if isinstance(finding, str):
        return _norm(finding)
    if isinstance(finding, Finding):
        loc = _norm(finding.location)
        cat = _norm(finding.category)
        sev = _norm(finding.severity)
    elif isinstance(finding, dict):
        loc = _norm(finding.get("location", ""))
        cat = _norm(finding.get("category", ""))
        sev = _norm(finding.get("severity", ""))
    else:
        # Type inattendu : stringify défensif plutôt que crasher le bench.
        return _norm(str(finding))
    return f"{loc}|{cat}|{sev}"


def _to_id_set(findings: Iterable[FindingLike]) -> Set[str]:
    """Convertit une collection de findings en set d'IDs canoniques (non vides)."""
    return {fid for fid in (canonicalize_finding(f) for f in findings) if fid}


def compute_precision_recall(
    predicted: Sequence[FindingLike],
    actual: Sequence[FindingLike],
) -> Dict[str, float]:
    """Precision / Recall / F1 sur les findings (set-match par ID canonique).

    Port typé de ``references/code-review-graph/.../eval/scorer.py`` adapté à nos
    ``Finding``. Deux ensembles vides → score parfait (1.0/1.0/1.0) : c'est le
    comportement de la référence (un Judge qui ne signale rien sur un cas sans
    problème attendu est dans le vrai), gardé fidèlement.

    Args:
        predicted: Findings prédits par le Judge.
        actual: Findings attendus (ground truth étiqueté).

    Returns:
        Dict ``{"precision", "recall", "f1"}`` arrondis à 4 décimales.
    """
    pred_set = _to_id_set(predicted)
    actual_set = _to_id_set(actual)

    if not pred_set and not actual_set:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}

    true_positive = len(pred_set & actual_set)
    precision = true_positive / len(pred_set) if pred_set else 0.0
    recall = true_positive / len(actual_set) if actual_set else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def compute_mrr(correct: FindingLike, ranked: Sequence[FindingLike]) -> float:
    """Mean Reciprocal Rank : position du 1er finding attendu dans le classement.

    Utile pour évaluer si le Judge ORDONNE bien ses findings (les plus graves en
    tête). Port de la référence : ``1/rank`` (1-indexé) si le finding attendu est
    présent dans ``ranked``, ``0.0`` sinon.

    Args:
        correct: Le finding attendu (ground truth).
        ranked: Liste ordonnée des findings prédits (meilleur en premier).

    Returns:
        ``1.0/rank`` du premier match, ou ``0.0`` si absent. Arrondi à 4 dp.
    """
    target = canonicalize_finding(correct)
    for i, f in enumerate(ranked, start=1):
        if canonicalize_finding(f) == target:
            return round(1.0 / i, 4)
    return 0.0


def judge_verdict_accuracy(
    predicted_approved: bool,
    actual_should_approve: bool,
) -> Dict[str, bool]:
    """Justesse du verdict binaire ``is_approved`` du Judge.

    Complément de P/R/F1 (qui évalue la finesse des findings) : ici on évalue la
    DÉCISION finale. Un Judge peut avoir de bons findings mais une mauvaise
    décision (ex: signale un critical mais valide quand même) — ces deux axes
    sont indépendants et doivent être benchés séparément.

    Args:
        predicted_approved: Verdict du Judge (``CodeJudgeOutput.is_approved``).
        actual_should_approve: Ground truth (le code était-il réellement valide ?).

    Returns:
        Dict avec ``accuracy`` (justesse globale) + décomposition des erreurs
        ``false_positive`` (validé à tort = code mauvais accepté = le plus grave)
        et ``false_negative`` (rejeté à tort = code bon refusé = gaspillage de
        cycle LLM, moins grave mais coûteux).
    """
    if predicted_approved == actual_should_approve:
        return {"accuracy": True, "false_positive": False, "false_negative": False}
    if predicted_approved and not actual_should_approve:
        return {"accuracy": False, "false_positive": True, "false_negative": False}
    return {"accuracy": False, "false_positive": False, "false_negative": True}
