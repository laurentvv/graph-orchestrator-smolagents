"""Constructeurs de blocs de critères de validation générés par l'Architecte (F-82).

L'Architecte (nœud DSPy) est désormais le **pilote unique** des validations : il produit
des critères spécifiques au cahier des charges, propagés au Coder (auto-validation
visuelle), au Tester (assertions fonctionnelles) et au Judge (rubric d'acceptation).

Ce module est l'équivalent de ``requirements_checklist.py`` (F-46) pour les critères
produits par l'Architecte plutôt qu'extraits par regex de la spec. 0 LLM, déterministe.

Chaîne de propagation ::
    Architect (LLM) → ArchitectTask.{visual,.functional,rubric}  [models.py]
                     → sub_dict  [workflows.py, OBLIGATOIRE sinon champ perdu]
                     → builders ci-dessous → blocs prompt injectés aux 3 nœuds

Anti-biais (leçon du run 2026-08-08) :
    Sans critères explicites, le Coder VOIT un canvas vide sur son screenshot mais
    l'EXCUSE ("normal avant interaction"). Le bloc visuel force une ANALYSE CRITIQUE :
    chaque critère doit être confirmé OUI/NON, et un visuel vide = BUG critique.

Hiérarchie des sources (côté Tester, préserve F-46/F-47) ::
    F-47 (itération >1, targeted retest) > F-82 (Architecte) > F-46 (regex spec)
"""

from __future__ import annotations

from typing import List

from .feedback_utils import truncate_output


def build_visual_criteria_block(criteria: List[str]) -> str:
    """Construit le bloc de critères visuels injecté au Coder (auto-validation F-45).

    Force une **ANALYSE CRITIQUE** du screenshot (anti-biais de confirmation). Chaque
    critère doit être confirmé OUI/NON sur la capture, et un visuel vide pour une
    app/visualiseur est explicitement un BUG (pas "normal").

    Args:
        criteria: Liste d'assertions visuelles concrètes produites par l'Architecte
            (ex: "barres visibles au chargement dans le canvas").

    Returns:
        Bloc texte à injecter dans le ``preview_block`` du Coder. Chaîne vide si la
        liste est vide (rétrocompat : le workflow DevTools historique reste actif).
    """
    if not criteria:
        return ""

    # Filtre les vides AVANT d'énumérer pour une numérotation continue (1, 2, 3...).
    cleaned = [c.strip() for c in criteria if c and c.strip()]
    if not cleaned:
        return ""
    items = "\n".join(
        f"  {i}. {c}" for i, c in enumerate(cleaned, 1)
    )
    n = len(cleaned)

    return f"""
### 🖼️ CRITÈRES DE VALIDATION VISUELLE (générés par l'Architecte — F-82, {n} critères)
⚠️ ANALYSE CRITIQUE OBLIGATOIRE de ton screenshot. N'EXCUSE JAMAIS un visuel vide :
une zone de rendu vide pour une app/outil/visualiseur est un BUG CRITIQUE, PAS "normal
avant interaction". Si tu vois un espace vide là où des éléments devraient apparaître,
c'est un bug → corrige AVANT final_answer (ne te raconte pas que c'est "attendu").

Pour CHAQUE critère ci-dessous, confirme OUI/NON ce que tu vois RÉELLEMENT sur ta capture :

{items}

RÈGLE DE DÉCISION :
- Si UN seul critère = NON (élément non visible/absent) → status "failure", CORRIGE.
- final_answer(status="success") uniquement si TOUS les critères = OUI (vérifiés sur
  le screenshot, pas supposés).
- Une page sans erreur console MAIS avec un critère visuel NON = ÉCHEC (le bug canvas
  du 2026-08-08 n'avait AUCUNE erreur console, juste des barres invisibles).
"""


def build_functional_criteria_block(criteria: List[str]) -> str:
    """Construit le bloc de critères fonctionnels injecté au Tester.

    Remplace la checklist F-46 (regex sur la spec) quand l'Architecte a produit des
    critères. Format miroir (tableau verdict PASS/FAIL) pour cohérence.

    Args:
        criteria: Liste d'assertions de comportement produites par l'Architecte
            (ex: "Après clic Démarrer + sleep(400ms), le compteur > 0").

    Returns:
        Bloc texte à injecter dans le prompt du Tester. Chaîne vide si la liste est
        vide (rétrocompat : repli sur F-46 regex / F-47 targeted).
    """
    if not criteria:
        return ""

    # Filtre les vides AVANT d'énumérer pour une numérotation continue (1, 2, 3...).
    cleaned = [c.strip() for c in criteria if c and c.strip()]
    if not cleaned:
        return ""
    items = "\n".join(
        f"  {i}. {c}" for i, c in enumerate(cleaned, 1)
    )
    n = len(cleaned)

    return f"""
### ✅ CRITÈRES FONCTIONNELS (générés par l'Architecte — F-82, {n} assertions à tester)
Tu DOIS tester CHACUN des {n} critères ci-dessous via evaluate_script (puppeteer). Pour
CHACUN, écris une assertion et note le verdict. NE SAUTE AUCUN critère.
Si un critère est NON satisfait → verdict FAIL pour cet item.

{items}

Ton rapport final DOIT contenir ce tableau (une ligne par critère) :
CRITÈRES FONCTIONNELS TESTÉS :
  - [1] <critère 1>: PASS (assertion: ...)
  - [2] <critère 2>: FAIL — attendu: <X>, obtenu: <Y>
  - ...
VERDICT GLOBAL: success (si TOUS PASS) ou failure (si ≥1 FAIL).
"""


def build_judge_rubric_block(rubric: str) -> str:
    """Construit le bloc de rubric d'acceptation injecté au Judge.

    Concaténé au ``task_requirements`` global du Judge (qui contient déjà la spec
    tronquée). Ce champ apporte la **pondération** spécifique à la sous-tâche
    (CRITICAL/HIGH/MEDIUM/LOW) que la spec globale ne fournit pas.

    Args:
        rubric: Texte court produit par l'Architecte (ex: "CRITICAL: barres visibles
            + tri correct. HIGH: code couleur 3 états. MEDIUM: responsive.").

    Returns:
        Bloc texte à concaténer au task_requirements du Judge. Chaîne vide si rubric
        vide (rétrocompat : task_requirements = spec globale seule, comme avant).
    """
    if not rubric or not rubric.strip():
        return ""

    # Troncation défensive (la rubric devrait être courte, mais on garde la cohérence
    # avec le task_requirements global qui est tronqué à 1500/2000 chars).
    rubric_t = truncate_output(
        rubric.strip(), head_lines=20, tail_lines=5, max_chars=800
    )
    return f"""
### CRITÈRES D'ACCEPTATION SPÉCIFIQUES (générés par l'Architecte — F-82)
{rubric_t}
"""
