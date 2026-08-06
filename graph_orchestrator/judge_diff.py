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

Miroir du pattern ``targeted_retest.build_targeted_retest_block`` (F-52/F-53) qui
injecte le diff dans un bloc prompt plutôt qu'en nouveau champ DSPy → cohérence
+ zéro drift sur les tests Judge existants.
"""

from __future__ import annotations

from typing import List, Optional

from .feedback_utils import truncate_output


def build_judge_code_block(
    target_files: List[str],
    git_diff: str,
    *,
    full_max_chars: int = 6000,
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

    # Itération 1 (ou git indisponible) : pas de diff, tout est nouveau.
    # Rétrocompatibilité stricte avec le comportement historique (full-file).
    if not git_diff or not git_diff.strip():
        return full_code or "Code manquant"

    # Itération >1 : diff présent → on l'injecte en tête (doctrine IN-DIFF ONLY),
    # suivi du code complet tronqué (contexte pour la vérification des exigences).
    full_truncated = truncate_output(
        full_code,
        head_lines=60,
        tail_lines=20,
        max_chars=full_max_chars,
    ) or "Code complet indisponible (fichiers illisibles)."

    return (
        "=== DIFF MODIFIÉ (à juger EN PRIORITÉ — doctrine IN-DIFF ONLY) ===\n"
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
