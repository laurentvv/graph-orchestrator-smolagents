"""Moniteur de progrès par similarité des RÉSULTATS d'outils (P5/F-138).

Port deer-flow `middlewares/tool_progress_middleware.py` (ToolProgressMiddleware,
jaccard_threshold=0.8) : détecte les boucles que le fingerprint d'APPELS
(LoopGuard F-36) ne voit pas — l'agent VARIE ses arguments mais l'outil retourne
quotidiennement la même chose (re-lectures décalées, re-tests identiques,
re-erreurs identiques). Un « succès » dont le word-set du résultat est
near-duplicate du précédent n'est PAS du progrès.

Différence assumée avec la référence : deer-flow BLOQUE l'outil (machine à
états ACTIVE→WARNED→BLOCKED par thread) ; notre usine privilégie le nudge
contextuel injecté dans les observations (pattern F-114/125/130 éprouvé sur
ce 4B) — pas de veto, le nudge escalade le message mais l'agent garde la main.

Fail-open total, état module-level avec reset par nœud (même lifecycle que les
autres compteurs vision).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

# Mots < 3 chars ignorés (bruit syntaxique), lowercased (miroir deer-flow word_set).
_WORD_RE = re.compile(r"[a-zA-Z_]\w{2,}")
JACCARD_THRESHOLD = 0.8
_STREAK_THRESHOLD = 3


def word_set(text: str) -> frozenset:
    """Word-set d'un texte de résultat (mots ≥3 chars, lowercase)."""
    return frozenset(_WORD_RE.findall((text or "").lower()))


def jaccard(a: frozenset, b: frozenset) -> float:
    """Similarité Jaccard ; 1.0 si deux ensembles vides identiques, 0.0 sinon."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class ToolProgressMonitor:
    """Compte, par outil, les résultats consécutifs quasi identiques.

    `record(tool, result_text)` à chaque step ; renvoie un nudge au 3e résultat
    consécutif near-duplicate (Jaccard ≥ 0.8), puis à chaque suivant. Un
    résultat différent reset la série de l'outil.
    """

    def __init__(self, threshold: float = JACCARD_THRESHOLD, streak: int = _STREAK_THRESHOLD):
        self.threshold = threshold
        self.streak = streak
        self._last_words: Dict[str, frozenset] = {}
        self._counts: Dict[str, int] = {}

    def reset(self) -> None:
        self._last_words.clear()
        self._counts.clear()

    def record(self, tool: str, result_text: str) -> Optional[str]:
        """Enregistre le résultat d'un outil pour CE step. Nudge si série stérile."""
        try:
            tool = (tool or "").strip() or "?"
            words = word_set(result_text)
            prev = self._last_words.get(tool)
            if prev is not None and jaccard(prev, words) >= self.threshold:
                self._counts[tool] = self._counts.get(tool, 0) + 1
            else:
                self._counts[tool] = 1
            self._last_words[tool] = words
            n = self._counts[tool]
            if n < self.streak:
                return None
            return (
                f"[RÉSULTATS EN BOUCLE] L'outil {tool} retourne {n} fois de suite un "
                f"contenu quasi identique (similarité ≥{self.threshold:.0%}) — tu exécutes "
                f"des VARIANTES du même appel sans information nouvelle. CHANGE d'approche "
                f"pour de bon : (1) si tu cherchais un bug, applique MAINTENANT le fix "
                f"(search_replace) au lieu de re-vérifier ; (2) si tu vérifies, passe à la "
                f"suite du plan (screenshot/visual_check si ce n'est pas fait) ; "
                f"(3) sinon final_answer honnête."
            )
        except Exception:
            return None


# État module-level (lifecycle : reset par exécution de nœud, cf. vision resets).
_MONITOR = ToolProgressMonitor()


def reset_tool_progress() -> None:
    _MONITOR.reset()


def record_tool_result(tool: str, result_text: str) -> Optional[str]:
    """API module-level : enregistre et renvoie le nudge éventuel."""
    return _MONITOR.record(tool, result_text)


def dominant_action_tool(code_action: str) -> Optional[str]:
    """Nom du 1er outil d'ACTION appelé dans le code du step (write/search/etc.).

    Les outils observationnels (read/console/screenshot) ne sont pas comptés :
    leurs résultats se ressemblent légitimement (re-lecture d'une même section).
    On cible les OUTILS D'ACTION dont la répétition du résultat signale une
    action qui ne change rien (ex: search_replace qui échoue pareil à chaque
    variante d'arguments).
    """
    action_tools = (
        "write_file", "append_file", "edit_file", "search_replace",
        "multi_replace", "check_js_syntax",
    )
    for line in (code_action or "").splitlines():
        s = line.strip()
        for t in action_tools:
            if f"{t}(" in s:
                return t
    return None
