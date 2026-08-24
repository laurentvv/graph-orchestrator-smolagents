"""Utilitaires de troncature du feedback (Priorité 2 — Boucle d'auto-correction).

Au fil des itérations Coder↔Tester↔Judge, les sorties (stderr Python, traceback,
console JS web, rapport QA) s'accumulent sans limite dans le contexte du LLM.
Un gros traceback (500+ lignes) avalé à chaque itération fait exploser la fenêtre
de contexte ("Context Overflow") → le LLM oublie les directives de l'Architecte et
la boucle diverge.

Ce module fournit une troncature **techno-agnostique** (valable pour du stderr
Python ET du log console web) : on garde la "tête" (l'erreur, en haut) et la
"queue" (la cause/traceback final, en bas), on coupe le milieu bruyant.

La troncature s'applique **à la lecture** (injection au LLM), jamais à l'écriture
en base (DuckDB garde le contenu intégral pour ne pas casser la dédup par hash).

F-105 : `truncate_output` est aussi le point de branchement de la REDACTION de
secrets (redaction.py, directive « Redact » mattpocock) — tout ce qui transite
vers le LLM passe par ici (Tester→Judge, Judge→Coder, bash_command).
"""

from __future__ import annotations

from typing import List, Optional

from .config import settings
from .redaction import redact_secrets


# Tronçon inséré entre tête et queue quand on coupe. Le compte de lignes coupées
# est injecté pour que le LLM sache qu'une information a été omise (transparence).
_TRUNCATION_MARKER = "… [{dropped} lignes tronquées pour économiser le contexte] …"


def truncate_output(
    text: Optional[str],
    head_lines: int = 20,
    tail_lines: int = 20,
    max_chars: int = 2000,
) -> str:
    """Tronque un texte long en gardant tête + queue, anti "Context Overflow".

    Stratégie "head + tail" (inspirée d'Aider / Cursor) :
    - Texte court (≤ max_chars ET ≤ head+tail lignes) → retourné tel quel.
    - Texte long → on garde les `head_lines` premières lignes (l'erreur, en haut)
      et les `tail_lines` dernières (la cause racine / résolution, en bas), et on
      remplace le milieu bruyant par un marqueur transparent.

    Args:
        text: Le texte à tronquer (None/"" → chaîne vide, sans crash).
        head_lines: Nombre de lignes à garder en tête.
        tail_lines: Nombre de lignes à garder en queue.
        max_chars: Plafond global en caractères (défense complémentaire, au cas où
            les lignes sont très longues — ex. un minified JS en une seule ligne).

    Returns:
        Le texte tronqué (str, jamais None).
    """
    if not text:
        return ""

    # F-105 : redaction de secrets AVANT tout autre traitement (y compris le
    # cas "court" qui retourne le texte tel quel) — un secret dans une sortie
    # courte doit être masqué exactement comme dans une sortie longue. Opt-out
    # REDACTION_ENABLED (défaut True). Doctrine : à la lecture (LLM/logs),
    # DuckDB conserve l'intégral.
    if settings.redaction_enabled:
        text = redact_secrets(text)

    # Garde-fou : si la chaîne dépasse max_chars même après découpage ligne par
    # ligne, on borne aussi en caractères. On traite d'abord le cas "court".
    if len(text) <= max_chars and text.count("\n") < head_lines + tail_lines:
        return text

    lines = text.split("\n")
    total = len(lines)

    # Cas limite : head+tail couvre déjà tout → rien à couper.
    if total <= head_lines + tail_lines:
        # Toujours le plafond caractères à appliquer si lignes très longues.
        return _cap_chars(text, max_chars)

    head = lines[:head_lines]
    tail = lines[total - tail_lines:]
    dropped = total - head_lines - tail_lines

    marker = _TRUNCATION_MARKER.format(dropped=dropped)
    truncated = "\n".join(head + [marker] + tail)
    return _cap_chars(truncated, max_chars)


def truncate_history(
    items: List[str],
    max_chars: int = 2000,
    header: str = "",
) -> str:
    """Plafonne l'historique cumulé des réfutations injecté au Coder.

    À chaque itération rejetée, une réfutation (bug) est ajoutée à DuckDB. À
    l'itération suivante, TOUTES les réfutations actives sont concaténées et
    injectées au prompt du Coder (`workflows.py` historique). Sur 3 itérations
    avec de gros feedbacks, ce cumul peut dépasser plusieurs milliers de
    caractères et polluer le contexte.

    On priorise les items les plus RÉCENTS (les bugs les plus pertinents sont
    ceux du dernier cycle) : on parcourt la liste à l'envers et on arrête de
    rajouter dès que le plafond est atteint. Les anciens bugs sont résumés par
    un compteur.

    Args:
        items: Liste de chaînes (ex: contenus des claims kind="refutation").
            L'ordre est supposé chronologique (plus ancien en premier) — les
            plus récents (fin de liste) sont prioritaires.
        max_chars: Plafond total de la chaîne retournée.
        header: Préfixe optionnel (ex: "[TICKETS DE BUGS ACTIFS]").

    Returns:
        Historique tronqué (≤ max_chars), items récents d'abord.
    """
    if not items:
        return ""

    kept: List[str] = []
    used = len(header) + (1 if header else 0)
    skipped_recent = 0  # items récents qu'on n'a PAS pu garder (dépassement)

    # Parcours des plus récents vers les plus anciens (fin de liste d'abord).
    for item in reversed(items):
        chunk = item.strip() if item else ""
        if not chunk:
            continue
        # +2 pour le "- " préfixe + "\n".
        cost = len(chunk) + 2
        if used + cost > max_chars:
            # Cas particulier : si on n'a encore gardé AUCUN item, on garde quand
            # même le plus récent (tronqué individuellement) — sinon le Coder
            # n'aurait aucune info sur le bug actuel. Le reste est skippé.
            if not kept:
                kept.append(truncate_output(chunk, max_chars=max_chars - used - 2))
                used = max_chars  # budget épuisé
            skipped_recent += 1
            continue
        kept.append(chunk)
        used += cost

    # `kept` est en ordre inversé (récent d'abord) → on remet en chrono inversé
    # (récent d'abord dans l'affichage = on garde la sortie la plus récente en haut).
    kept.reverse()

    out = header + ("\n" if header else "")
    for chunk in kept:
        out += f"- {chunk}\n"

    if skipped_recent:
        out += (
            f"- … [{skipped_recent} autre(s) ticket(s) de bug(s) non affiché(s) "
            f"pour économiser le contexte] …\n"
        )
    return out


def _cap_chars(text: str, max_chars: int) -> str:
    """Borne un texte en nombre de caractères (queue prioritaire sur la tête)."""
    if len(text) <= max_chars:
        return text
    # On garde ~30% de tête + ~70% de queue : la cause racine (queue) est
    # généralement plus actionable que le début du log.
    head_budget = int(max_chars * 0.3)
    tail_budget = max_chars - head_budget
    dropped = len(text) - max_chars
    marker = _TRUNCATION_MARKER.format(dropped=dropped)
    return text[:head_budget] + "\n" + marker + "\n" + text[-tail_budget:]


def build_rejection_feedback(judge_res) -> str:
    """F-165-C : feedback de rejet SANS double embedding.

    Le chemin fail-closed (dspy_nodes, Judge SKIPPÉ sur échec Tester) construit
    déjà un final_feedback complet (« APPROBATION BLOQUÉE + 🎯 CAUSE RACINE +
    🛠️ INSTRUCTION DE CORRECTION + Détails du Tester »). Le wrapper historique de
    workflows.py ré-empilait root_cause/fix_instruction par-dessus → réfutation
    KG dupliquée (claim 255, run 021543) → ticket de correction brouillé pour le
    Coder de l'itération suivante.

    Règle : si final_feedback contient déjà les blocs CAUSE RACINE et INSTRUCTION
    (signature du fail-closed), il est renvoyé tel quel ; sinon on assemble les
    blocs (verdict Judge LLM normal, feedback brut). Compatibilité stricte :
    judge_res None → « Erreur système du juge. » (message historique).
    """
    if judge_res is None:
        return "Erreur système du juge."
    fb = str(getattr(judge_res, "final_feedback", "") or "")
    rc = str(getattr(judge_res, "root_cause", "") or "")
    fi = str(getattr(judge_res, "fix_instruction", "") or "")
    if ("🎯 CAUSE RACINE" in fb) and ("🛠️ INSTRUCTION DE CORRECTION" in fb):
        return fb
    if not (rc or fi):
        return fb or "Erreur système du juge."
    blocks = []
    if rc:
        blocks.append(f"🎯 CAUSE RACINE : {rc}")
    if fi:
        blocks.append(f"🛠️ INSTRUCTION DE CORRECTION : {fi}")
    if fb:
        blocks.append(f"📝 FEEDBACK : {fb}")
    return "\n".join(blocks)
