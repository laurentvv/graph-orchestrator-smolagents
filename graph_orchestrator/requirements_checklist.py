"""Extraction déterministe d'une checklist de fonctionnalités depuis la spec. F-46.

PROBLÈME : le Tester reçoit le cahier des charges (original_content = spec PromptRefiner)
comme TEXTE LIBRE. Un petit LLM (gemma) n'extrait pas fiablement les N fonctionnalités
à tester — il en teste 2-3 au hasard et oublie le reste (ex: compteur de comparaisons
manquant non détecté sur run Bubble Sort #3).

SOLUTION : la spec du PromptRefiner contient une section structurée
`## Expected Features` (anglais depuis F-115 ; `## Fonctionnalités attendues` accepté
en rétro-compat) avec des puces testables (exigence explicite de la
signature PromptRefinerSignature). On parse cette section en liste Python
déterministe (regex, 0 LLM) et on l'injecte au Tester comme CHECKLIST OBLIGATOIRE :
pour CHAQUE fonctionnalité, 1 assertion + verdict PASS/FAIL/N-A.

Le Tester ne peut plus "oublier" une fonctionnalité — le format du rapport impose
une ligne par item de la checklist. Le Judge voit le tableau et peut rejeter si
une seule ligne est FAIL.

Robustesse : si la section est absente ou vide (spec non structurée, prompt brut),
on retourne [] et le Tester retombe sur le comportement historique (texte libre).
Aucune cassure.
"""

import re
from typing import List


def extract_functionalities(spec_text: str) -> List[str]:
    """Extrait la liste des fonctionnalités depuis la section dédiée de la spec.

    Cherche la section `## Expected Features` (PromptRefiner F-115, sortie anglais) ou,
    en rétro-compatibilité, `## Fonctionnalités attendues` (specs héritées françaises /
    checkpoints F-24 repris) — insensible casse/accents — et parse ses puces (- ou *)
    jusqu'à la section suivante (## ou fin).

    Args:
        spec_text: La spec structurée produite par le PromptRefiner (ou le prompt
            brut en fallback — la section sera alors absente).

    Returns:
        Liste des fonctionnalités (chaîne après la puce), sans doublons, préservant
        l'ordre. Liste vide si la section n'existe pas ou n'a pas de puces.

    Exemples:
        >>> spec = "## Expected Features\\n- Start button\\n- Counter\\n## Next"
        >>> extract_functionalities(spec)
        ['Start button', 'Counter']
        >>> spec_fr = "## Fonctionnalités attendues\\n- Bouton Démarrer\\n- Compteur\\n## Suite"
        >>> extract_functionalities(spec_fr)
        ['Bouton Démarrer', 'Compteur']
    """
    if not spec_text:
        return []

    # Recherche de la section. Insensible à la casse et aux variantes d'accents
    # (le modèle peut écrire "FonctionnalitéS attendueS" ou "fonctionnalités attendues").
    # F-115 : la spec PromptRefiner est désormais en ANGLAIS — on accepte les DEUX
    # en-têtes (anglais prioritaire, français = rétro-compat checkpoints/specs anciens).
    # Match jusqu'à la prochaine section (## ) ou fin de texte.
    pattern = re.compile(
        r"##\s*(?:Expected\s+Features?|Fonctionnalit[ée]s?\s+attendues?)\s*\n(.*?)(?=\n##\s|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(spec_text)
    if not match:
        # Section absente : spec non structurée (prompt brut ou PromptRefiner désactivé).
        # Pas d'erreur — on retourne [] et le Tester retombe sur le mode texte libre.
        return []

    section = match.group(1)
    # Parse les puces : lignes commençant par - ou * (avec espaces/tabs optionnels).
    # On retire la puce et les espaces de tête. On ignore les lignes vides.
    items: List[str] = []
    seen = set()
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue
        # Retire la puce et les espaces qui suivent
        item = re.sub(r"^[-*]\s*", "", stripped).strip()
        if not item:
            continue
        # Dédoublonne (préserve l'ordre) : le modèle peut répéter une puce.
        key = item.lower()
        if key not in seen:
            seen.add(key)
            items.append(item)

    return items


def build_checklist_block(functionalities: List[str]) -> str:
    """Construit le bloc prompt de checklist obligatoire pour le Tester.

    Force le Tester à tester CHAQUE fonctionnalité et à produire un verdict
    structuré (tableau fonctionnalité → PASS/FAIL/N-A). Sans ça, le petit modèle
    oublie des items (observé : compteur de comparaisons non testé).

    Args:
        functionalities: Liste des fonctionnalités (extraites par extract_functionalities).

    Returns:
        Bloc texte à injecter dans le prompt du Tester. Chaîne vide si la liste
        est vide (fallback : pas de checklist forcée, comportement historique).
    """
    if not functionalities:
        return ""

    # Numérote la checklist pour que le modèle puisse s'y référer clairement.
    items_formatted = "\n".join(
        f"  {i}. {f}" for i, f in enumerate(functionalities, 1)
    )
    n = len(functionalities)

    return f"""
### ✅ CHECKLIST DE FONCTIONNALITÉS (OBLIGATOIRE — {n} exigences à tester)
Tu DOIS tester CHACUNE des {n} fonctionnalités ci-dessous. Pour CHACUNE, écris une
assertion (puppeteer_evaluate) et note le verdict. NE SAUTE AUCUNE fonctionnalité.
Si une fonctionnalité est ABSENTE de la page → verdict FAIL pour cet item (ne mets
pas N-A sauf si c'est réellement non testable techniquement).

{items_formatted}

Ton rapport final DOIT contenir ce tableau (une ligne par fonctionnalité) :
FONCTIONNALITÉS TESTÉES:
  - [1] <fonctionnalité 1>: PASS (assertion: ...)
  - [2] <fonctionnalité 2>: FAIL — attendu: <X>, obtenu: <Y>
  - ...
VERDICT GLOBAL: success (si TOUTES PASS) ou failure (si ≥1 FAIL).

Une seule fonctionnalité FAIL = page NON conforme = status "failure".
"""