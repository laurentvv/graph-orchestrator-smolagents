"""Re-test ciblé façon git diff : ne re-valider QUE les bugs signalés. F-47.

PROBLÈME : à chaque itération, le Tester re-valide TOUT from scratch (navigate +
screenshot + console + 12 steps, ~233k tokens). Or en itération N+1, le Coder n'a
modifié que les fragments pointés par les réfutations du Judge (ex: "compteur
manquant", "code couleur absent"). 90% du re-test re-vérifie ce qui marchait déjà.

SOLUTION (calquée sur git diff + tests impactés) : en itération >1, le Tester reçoit
la liste EXPLICITE des bugs à vérifier (lus depuis DuckDB kind='refutation') + un
budget de steps réduit (6 au lieu de 12). Il teste EN PRIORITÉ ces points (3-4
assertions ciblées) puis un smoke-test rapide (console + screenshot). Économie
attendue ~60% temps/tokens.

SOURCE DE VÉRITÉ : les réfutations DuckDB (kind='refutation', source='judge_panel').
Elles contiennent le `final_feedback` du Judge avec les findings structurés
(severity/category/location/description). C'est plus fiable que de parser
l'historique des search_replace du Coder (qui peut échouer/retry/bugger).

Pas de risque de faux négatif : si le Coder a "corrigé" un bug mais introduit une
régression ailleurs, le smoke-test (console + screenshot) le détectera. Le re-test
ciblé n'omet que les vérifications de zones NON modifiées (qui marchaient déjà).
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# Budget de steps du mode ciblé (vs settings.tester_max_steps en mode complet).
# F-127 (post-mortem run 2026-08-19_2104) : 6 steps tuaient le re-test ciblé en
# découverte d'UI (IDs canvas à deviner) → final_answer en prose au max-steps →
# rejet fantôme d'un livrable sain. 10 couvrent : navigate(1) + discover_ui(1)
# + console smoke(1) + 3-4 assertions ciblées + screenshot + final_answer.
# F-141 (post-mortem run 2026-08-20_1817) : le re-test ciblé a découvert un VRAI
# bug (jeu en pause au chargement) et a été coupé à 10 steps EN PLEINE vérification
# (reprise clavier + clic Resume + assertion post-reprise) → timeout + Judge
# fail-closed sur un livrable pourtant propre. 16 couvrent découverte →
# interaction corrective → re-assertion.
TARGETED_MAX_STEPS = 16


def extract_bug_points(refutations: List[dict], max_chars: int = 1200) -> Optional[str]:
    """Extrait une liste concise de bugs à vérifier depuis les réfutations DuckDB.

    Args:
        refutations: Liste des claims DuckDB kind='refutation' (champ 'content'
            = final_feedback du Judge, potentiellement long/verbeux).
        max_chars: Plafond de caractères pour ne pas saturer le prompt du Tester.

    Returns:
        Texte formaté listant les bugs à vérifier (numérotés), ou None si aucune
        réfutation (= itération 1, ou Judge n'a pas produit de feedback).
    """
    if not refutations:
        return None

    # Concatène les feedbacks (il peut y en avoir plusieurs si iterations multiples).
    # On prend les plus récents en premier (le Judge peut affiner son diagnostic).
    feedbacks = []
    total = 0
    for ref in reversed(refutations):  # reversed = plus récent d'abord
        content = (ref.get("content") or "").strip()
        if not content:
            continue
        if total + len(content) > max_chars:
            # Tronque le dernier feedback pour rester sous le plafond.
            remaining = max_chars - total
            if remaining > 100:  # ne garde pas un fragment trop court/inutile
                feedbacks.append(content[:remaining].rsplit("\n", 1)[0] + " [...]")
            break
        feedbacks.append(content)
        total += len(content)

    if not feedbacks:
        return None

    # Formate en bloc lisible pour le prompt du Tester.
    bugs_text = "\n\n".join(f"--- Feedback {i} ---\n{fb}" for i, fb in enumerate(feedbacks, 1))
    return bugs_text


def build_targeted_retest_block(
    bugs_feedback: str, iteration: int, git_diff: str = ""
) -> str:
    """Construit le bloc prompt de re-test ciblé pour le Tester.

    Args:
        bugs_feedback: Texte des bugs à vérifier (extrait par extract_bug_points).
        iteration: Numéro d'itération courant (pour contexte dans le prompt).
        git_diff: Diff git (lignes EXACTES modifiées par le Coder, F-48). Optionnel —
            si présent, le Tester sait QUOI a changé précisément (plus fiable que les
            bugs texte). Vide en iter 1 ou si git indisponible.

    Returns:
        Bloc texte à injecter dans le prompt du Tester. Remplace la checklist
        générique F-46 par une checklist CIBLÉE sur les bugs signalés + zones modifiées.
    """
    # Section diff (F-48) — seulement si non vide.
    diff_section = ""
    if git_diff.strip():
        diff_section = f"""
#### Zones EXACTES modifiées par le Coder (git diff — concentre tes assertions dessus) :
```diff
{git_diff}
```
Ces lignes sont ce que le Coder a touché depuis l'itération précédente. Teste en priorité
les comportements liés à ces modifications. Les zones NON listées ici marchaient déjà
(pas besoin de les re-valider exhaustivement).
"""

    return f"""
### 🎯 RE-TEST CIBLÉ (itération {iteration} — façon git diff)
Le Coder a Corrigé les bugs ci-dessous depuis le précédent rejet du Judge. Tu DOIS
vérifier EN PRIORITÉ que chaque bug signalé est désormais RÉSOLU. Ne re-valide PAS
tout from scratch — concentre-toi sur ces points + un smoke-test rapide.

#### Bugs signalés par le Judge (à vérifier EN PRIORITÉ) :
{bugs_feedback}
{diff_section}
#### Workflow de re-test ciblé (max {TARGETED_MAX_STEPS} steps) :
1. `navigate_page(url=...)` — ouvre la page corrigée.
2. `list_console_messages()` — smoke-test : 0 nouvelle erreur JS (régression ?).
3. `evaluate_script` pour vérifier que les éléments des zones modifiées sont bien RENDUS
   (ex: `document.querySelectorAll('.bar').length > 0` — un bug CSS les rendrait invisibles).
4. Pour CHAQUE bug signalé ci-dessus : écris 1 assertion (`puppeteer_evaluate` ou
   `evaluate_script`) qui vérifie que le bug est RÉSOLU (ex: "le compteur affiche > 0
   après le tri" si le bug était "compteur manquant"). Note PASS/FAIL pour chacun.
5. `take_screenshot()` — confirm visuel rapide (pas d'analyse exhaustive du layout).
6. `final_answer` — verdict: success (TOUS les bugs résolus + 0 régression console)
   ou failure (un bug persiste OU une nouvelle erreur console est apparue).

RÈGLE : un bug signalé TOUJOURS présent après correction = FAILURE (le fix du Coder
n'a pas marché). Une NOUVELLE erreur console (qui n'existait pas avant) = FAILURE
(régression introduite par le fix). Sois concis — 1 assertion par bug, pas d'exploration
superflue des zones non modifiées.
"""


def should_use_targeted_retest(iteration: int, refutations: List[dict]) -> bool:
    """Décide si le Tester doit utiliser le mode re-test ciblé vs complet.

    Mode ciblé activé SI : iteration > 1 ET au moins une réfutation disponible.
    Sinon (itération 1, ou pas de feedback Judge), mode complet (checklist F-46).

    Args:
        iteration: Numéro d'itération (1 = création initiale).
        refutations: Liste des claims DuckDB kind='refutation' pour cette sous-tâche.
    """
    return iteration > 1 and bool(refutations)
