"""Recall des leçons durables cross-run (F-68 Phase 2, P6-ter).

Le Knowledge Graph DuckDB accumule des claims au fil des runs. La Phase 1
(F-68, commit 47e3b97) a posé les deux autres piliers de la mémoire :

  - **Promotion** (consolidation, fin de run) : un LLM-juge fusionne/déduplique
    les réfutations rabâchées et en extrait des ``insight`` (leçons durables).
  - **Oubli** (prune_old_claims) : les claims obsolètes sont supprimées par
    rétention temporelle, MAIS ``insight`` + ``escalation`` sont préservés
    (ce sont les leçons qui survivent d'un run à l'autre).

Ce qui manquait = le **RECALL** : réinjecter ce notebook de leçons durables dans
le prompt du Coder au DÉBUT d'un run, pour fermer la boucle d'apprentissage.
Un run qui a appris qu'« une itération par requestAnimationFrame » évite le bug
d'animation instantanée (F-81) transmet cette leçon aux runs suivants.

Two-tier implicite (pas de nouvelle table) :
  - ``scratch``  = ``observation`` / ``refutation`` (éphémère, pruné 30j).
  - ``notebook`` = ``insight`` / ``escalation`` (durable, préservé cross-run).

Design (décision utilisateur) : **Recall-centric + Global**.
  - Recall-centric : on réutilise la consolidation Phase 1 comme mécanisme de
    promotion (déjà câblé). Ce module ne fait QUE le recall (0 LLM, déterministe).
  - Global : 1 notebook partagé, top-N par récence, note "ignore si non pertinent".
    Maximise l'apprentissage transversal (une leçon web aide une autre tâche web).

Référence : qm ``memory-service.ts`` recall = 0 LLM (lit juste le fichier). On
suit ce pattern — un nœud LLM de filtrage par pertinence serait Phase 2.5/3.
"""

from __future__ import annotations

from typing import List, Optional

from .feedback_utils import truncate_output


# Kinds durables = le notebook cross-run (survit à l'oubli temporel).
# Doit rester cohérent avec prune_old_claims.preserve_kinds (knowledge_graph.py).
DEFAULT_LESSON_KINDS = {"insight", "escalation"}

# Badge lisible injecté devant chaque leçon selon son kind.
_KIND_BADGE = {
    "insight": "[LEÇON]",
    "escalation": "[ESCALATION]",
}


def recall_lessons(kg, limit: int = 8, kinds: Optional[set] = None) -> List[dict]:
    """Récupère les leçons durables du notebook global (cross-run).

    Wrapper mince sur ``KnowledgeGraph.recall_lessons``. Exposé au niveau module
    pour que ``workflows.py`` importe tout depuis ici (un seul point d'entrée).

    Args:
        kg: instance KnowledgeGraph.
        limit: top-N leçons par récence.
        kinds: kinds à rappeler (défaut ``{"insight", "escalation"}``).

    Returns:
        Liste de dicts ``{"content", "kind", "created_at"}``, la plus récente
        d'abord. Vide si rien.
    """
    return kg.recall_lessons(kinds=kinds, limit=limit)


def build_lessons_block(
    claims: List[dict],
    max_chars: int = 1500,
) -> str:
    """Formate les leçons rappelées en bloc markdown injectable au Coder.

    Structure ::
        ### LEÇONS DE RUNS PRÉCÉDENTS (mémoire cross-run)
        Ce sont des leçons durables extraites de runs antérieurs. Applique
        celles pertinentes pour ta tâche ; ignore les autres.

        1. [LEÇON] <content>
        2. [ESCALATION] <content>
        ...

    Args:
        claims: liste de dicts (au moins ``content`` + ``kind``).
        max_chars: budget en caractères (troncation transparente via
            ``truncate_output`` sur le corps, l'en-tête est préservé).

    Returns:
        Le bloc formaté, ou ``""`` si la liste est vide (injection
        conditionnelle côté prompt — ne pollue pas le contexte si rien).
    """
    if not claims:
        return ""

    header = (
        "### LEÇONS DE RUNS PRÉCÉDENTS (mémoire cross-run)\n"
        "Ce sont des leçons durables extraites de runs antérieurs. Applique "
        "celles pertinentes pour ta tâche ; ignore les autres.\n"
    )

    lines: List[str] = []
    for i, c in enumerate(claims, start=1):
        kind = c.get("kind", "insight")
        content = (c.get("content") or "").strip()
        if not content:
            continue
        badge = _KIND_BADGE.get(kind, f"[{kind.upper()}]")
        lines.append(f"{i}. {badge} {content}")

    if not lines:
        return ""

    body = "\n".join(lines)
    # Tronque le corps (préserve l'en-tête pédagogique). head_lines généreux car
    # les leçons sont numérotées : perdre le début casse la numérotation.
    body = truncate_output(body, head_lines=50, tail_lines=20, max_chars=max_chars)
    return f"{header}\n{body}"
