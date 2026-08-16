"""Bloc code pour le Judge : diff multi-fichiers ancré IN-DIFF ONLY. F-70.

PROBLÈME : le Judge (``execute_code_judge_node``) recevait le contenu COMPLET des
fichiers lus sur disque, alors que sa propre doctrine (``prompts.py`` rôle judge +
``CodeJudgeSignature`` docstring) exige « IN-DIFF ONLY : juge le code MODIFIÉ, pas
tout le fichier ». La règle existait, l'input la contredisait — le juge évaluait
un périmètre plus large que ce que sa rubric prescrit.

SOLUTION : injecter le ``git_diff`` (déjà calculé par F-53 ``git_snapshot`` et
propagé dans ``subtask["git_diff"]``, nativement multi-fichiers au format unified
diff) en TÊTE du champ ``code`` du Judge, suivi du code complet tronqué pour la
vérification des exigences (procédure obligatoire étape 2 du docstring Judge :
« pour CHAQUE exigence, vérifie dans ``code`` : Présente ? Implémentée ? »).

COMPORTEMENT DIFFÉRENCIÉ :
- itération 1 (diff vide, <2 commits git) → ``code`` = full-file concaténé
  (format ``--- {path} ---`` historique, tout est nouveau donc tout est "in-diff").
- itération >1 (diff présent) → ``code`` = bloc diff annoté (priorité, doctrine
  IN-DIFF ONLY) + full-file tronqué (contexte secondaire pour vérifier que le
  diff ne casse pas une exigence existante).

F-102 (turn checkpoint) : ``turn_diff_files`` (résumé structuré lu depuis la ref
``refs/graph-orchestrator/turns/<key>``) préfixe un bloc « CE QUE GIT DIT » —
statut + ajouts/suppressions PAR FICHIER, disponible dès l'itération 1 (là où le
diff texte F-53 est vide, <2 commits). Absent/vide → comportement inchangé
(rétrocompat stricte).

Miroir du pattern ``targeted_retest.build_targeted_retest_block`` (F-52/F-53) qui
injecte le diff dans un bloc prompt plutôt qu'en nouveau champ DSPy → cohérence
+ zéro drift sur les tests Judge existants.
"""

from __future__ import annotations

from typing import List, Optional

from .feedback_utils import truncate_output


def _render_turn_summary(files: List[dict]) -> str:
    """Rend le résumé F-102 en lignes compactes ``- [status] path (+A/-D)``."""
    lines = []
    for f in files:
        additions, deletions = f.get("additions"), f.get("deletions")
        if additions is None or deletions is None:
            counts = "binaire"
        else:
            counts = f"+{additions}/-{deletions}"
        marker = " (binaire)" if f.get("unrenderable") else ""
        lines.append(f"- [{f.get('status', 'modified')}] {f.get('path', '')} ({counts}){marker}")
    return "\n".join(lines)


def build_judge_code_block(
    target_files: List[str],
    git_diff: str,
    *,
    full_max_chars: int = 6000,
    turn_diff_files: Optional[List[dict]] = None,
) -> str:
    """Construit le contenu du champ ``code`` du Judge, ancré IN-DIFF ONLY.

    Lit le contenu complet des ``target_files`` sur disque et l'assemble avec le
    ``git_diff`` (F-53) selon le schéma itération-dépendant décrit en tête de
    module. Tolérant : un fichier illisible/absent est silencieusement sauté
    (fail-open, ne brique jamais le Judge).

    Args:
        target_files: Liste des chemins de fichiers cibles de la sous-tâche
            (lus relatifs au cwd du run, comme l'historique).
        git_diff: Diff git unified multi-fichiers (``git_snapshot.get_last_diff``).
            Chaîne vide en itération 1 (création initiale, <2 commits) ou si git
            indisponible → fallback full-file seul (rétrocompatibilité).
        full_max_chars: Plafond du bloc code complet en caractères. En iter >1,
            le diff porte l'essentiel ; le full-file devient contexte secondaire
            pour la vérification des exigences, donc tronqué pour économiser le
            budget tokens du LLM.
        turn_diff_files: Résumé structuré F-102 (``turn_checkpoint.summarize_turn_diff``,
            propagé dans ``subtask["turn_diff_summary"]``) — ``None``/vide = pas de
            bloc (rétrocompat). Préfixe « CE QUE GIT DIT » quelle que soit
            l'itération (dès la 1re : manifeste des fichiers créés).

    Returns:
        Le bloc texte à passer au champ ``code`` de ``CodeJudgeSignature``.
        Jamais vide (retourne ``"Code manquant"`` si rien n'a pu être lu et
        qu'aucun diff n'est fourni).
    """
    full_code = ""
    for file_path in target_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                full_code += f"--- {file_path} ---\n{f.read()}\n\n"
        except Exception:
            pass

    # F-102 : résumé structuré « ce que git dit » (par fichier). En tête, quelle
    # que soit l'itération — c'est le manifeste des fichiers touchés par le tour.
    turn_block = ""
    if turn_diff_files:
        turn_block = (
            "=== CE QUE GIT DIT (turn checkpoint F-102) ===\n"
            "Fichiers touchés par le Coder à CETTE itération (statut git, "
            "+ajouts/-suppressions) :\n"
            f"{_render_turn_summary(turn_diff_files)}\n\n"
        )

    # Itération 1 (ou git indisponible) : pas de diff, tout est nouveau.
    # Rétrocompatibilité stricte avec le comportement historique (full-file).
    if not git_diff or not git_diff.strip():
        return turn_block + (full_code or "Code manquant")

    # Itération >1 : diff présent → on l'injecte en tête (doctrine IN-DIFF ONLY),
    # suivi du code complet tronqué (contexte pour la vérification des exigences).
    full_truncated = truncate_output(
        full_code,
        head_lines=60,
        tail_lines=20,
        max_chars=full_max_chars,
    ) or "Code complet indisponible (fichiers illisibles)."

    return (
        turn_block
        + "=== DIFF MODIFIÉ (à juger EN PRIORITÉ — doctrine IN-DIFF ONLY) ===\n"
        "Les lignes ci-dessous sont EXACTEMENT ce que le Coder a touché depuis la "
        "itération précédente. Juge en priorité ces modifications ; les zones NON "
        "listées ici marchaient déjà à l'itération précédente (ne les re-juge pas "
        "sauf régression visible dans le diff).\n"
        f"```diff\n{git_diff}\n```\n\n"
        "=== CODE COMPLET (contexte pour la vérification des exigences) ===\n"
        "Le code complet ci-dessous sert à vérifier que chaque exigence du cahier "
        "des charges est bien implémentée (procédure obligatoire étape 2). Il peut "
        "être tronqué si volumineux ; le diff ci-dessus reste la source de vérité "
        "pour l'ancrage IN-DIFF.\n"
        f"{full_truncated}"
    )
