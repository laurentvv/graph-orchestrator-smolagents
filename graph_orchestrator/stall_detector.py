"""Stall Detector — Anti-loop v2 (Priorité 3-bis du plan usine logicielle, F-88).

Complète l'Anti-Loop Cryptographique F-36 (`loop_guard.py`) avec de la matière
déterministe issue de la référence loopx (fiche 19). Trois briques conçues pour
fonctionner ensemble :

1. **Vocabulaire `DeliveryOutcome`** (loopx `delivery_outcome.py`) — classifie
   chaque turn en `ACCOUNTABLE` (livrable matériel), `PROGRESS` (avance sans
   livrable) ou `IDLE` (aucun tool call).
2. **Hash d'output matériel** (loopx `pr_monitor_materialization.py`) — hashe le
   CONTENU que l'outil cherche à écrire (le "matériel" produit), pas le message
   de retour ni l'input brut.
3. **Stall detector** (loopx `recent_runs.py`) — compte les turns consécutifs
   "sans changement matériel" ; au-delà du seuil (2 par défaut), signale un
   stall au lieu de laisser l'agent spinner.

Fonctionnement
--------------
On distingue 2 cas de stall que F-36 rate :

  (a) **Reproduction** : le Coder appelle `write_file` avec un contenu
      *matériellement identique* au tour précédent (même hash d'output), même si
      l'input normalisé change subtilement (whitespace, ordre des clés). F-36
      hashe `ToolName + Input`, donc un changement cosmétique d'input le rend
      aveugle. Ici on hashe le `content` du write → un même fichier réécrit
      déclenche le stall même si l'appel diffère en surface.

  (b) **Tour gratuit** : un turn PROGRESS/IDLE (read/bash/rien) n'avance pas le
      livrable — pas de matériel nouveau. Une série de turns gratuits consécutifs
      = graine de stall. Métrique absente de F-36 (qui ne voit que les tool calls
      répétés, pas l'absence de progression).

`StallDetector.record(outcome, material_hash)` implémente la table de vérité :
  - ACCOUNTABLE + hash *différent* du précédent → reset (matériel nouveau, on progresse)
  - ACCOUNTABLE + hash *identique* au précédent → incrément (reproduction = stall)
  - PROGRESS / IDLE → incrément (tour sans matériel nouveau)

`reset()` est appelé entre deux retries dans `run_with_retry` (aligné sur
`loop_guard.reset()` et la purge `agent.memory.steps`).

Écart consciencieux vs loopx
---------------------------
- loopx hashe un *set trié de clés membres* (`_group_fingerprint`) car son
  domaine est le lifecycle PR. On aplatit au cas de l'agent : un seul hash par
  turn (celui du dernier outil d'écriture du turn, le plus représentatif de
  l'intention de livraison).
- loopx exclude le "bookkeeping" (quota accounting, state_refreshed) via une
  classification de control plane. Notre équivalent = classifier PROGRESS/IDLE
  via `classify_turn` (outils d'écriture = ACCOUNTABLE, le reste = non-matériel).
- Seuil loopx `MONITOR_DEBT_UNCHANGED_TURN_THRESHOLD = 2` (défaut). On garde 2 :
  au-delà de 2 turns consécutifs sans matériel nouveau, le stall est avéré.
"""

from __future__ import annotations

import hashlib
import threading
from enum import Enum
from typing import Any, Optional

# Outils qui produisent du "matériel" (livrable sur disque). Mis en dur pour
# éviter une dépendance circulaire avec `nodes.py` (même convention que
# `known_tools` dans loop_guard.py:179). Si un nouvel outil d'écriture est
# ajouté au Coder, l'ajouter ici ET dans loop_guard.py:179.
WRITE_TOOLS = frozenset(
    {"write_file", "append_file", "edit_file", "search_replace", "multi_replace"}
)

# F-151 : Outils de vérification et de validation visuelle (immunité stall).
# L'exécution de ces outils constitue une phase active et légitime de test
# qui ne doit pas déclencher prématurément le circuit-breaker de stall.
VISUAL_VERIFICATION_TOOLS = frozenset(
    {
        "visual_check",
        "take_screenshot",
        "navigate_page",
        "list_console_messages",
        "get_console_message",
        "fuzz_click_all_buttons",
        "probe_canvas_activity",
        "fuzz_keyboard_controls",
        "evaluate_script",
        "check_js_syntax",
        "clean_dom",
        "add_visual_tags",
        "expose_game_state",
        "instrument_calls",
        "dump_function_source",
        "force_advance",
    }
)


def is_verification_turn(tool_calls: list[tuple[str, Any]] | None) -> bool:
    """True si au moins un outil d'inspection/validation visuelle est appelé."""
    if not tool_calls:
        return False
    for name, _args in tool_calls:
        if (name or "").strip() in VISUAL_VERIFICATION_TOOLS:
            return True
    return False


class DeliveryOutcome(str, Enum):
    """Classification déterministe d'un turn d'agent (loopx `DeliveryOutcome`).

    Trois valeurs (vs 4 chez loopx — on simplifie en fusionnant les "surface
    only" et "outcome gap" en IDLE, non pertinents pour un agent de coding) :
    """

    ACCOUNTABLE = "accountable"  # livrable matériel (un write a produit du contenu)
    PROGRESS = "progress"        # avance sans livrable (read/bash/search)
    IDLE = "idle"                # aucun tool call


# Turns qui comptent comme "matériel" (loopx `ACCOUNTABLE_DELIVERY_OUTCOMES`).
ACCOUNTABLE_OUTCOMES = frozenset({DeliveryOutcome.ACCOUNTABLE})


def classify_turn(tool_calls: list[tuple[str, Any]]) -> DeliveryOutcome:
    """Classifie un turn depuis la liste (tool_name, args) extraite par
    `extract_tool_calls_from_step` (loop_guard.py).

    Règle (fail-fast) :
      - Aucun tool call                          → IDLE
      - Au moins un outil d'écriture (WRITE_TOOLS) → ACCOUNTABLE
      - Sinon (read/search/bash seulement)         → PROGRESS
    """
    if not tool_calls:
        return DeliveryOutcome.IDLE
    for name, _args in tool_calls:
        if (name or "").strip() in WRITE_TOOLS:
            return DeliveryOutcome.ACCOUNTABLE
    return DeliveryOutcome.PROGRESS


def _extract_str(arguments: Any, key: str) -> str:
    """Extrait une valeur string d'un dict d'arguments.

    Gère 3 formes d'arguments (selon le type d'agent) :
      1. dict structuré (ToolCallingAgent natif) → .get(key).
      2. JSON-string (ToolCallingAgent sérialisé) → json.loads puis .get(key).
      3. Ligne source Python (CodeAgent, ex: 'write_file(path="a", content="x")')
         → regex qui extrait la valeur après `key=`. C'est le cas qui manquait
         et qui causait le bug F-88 : extract_tool_calls_from_step CodeAgent
         retourne la ligne source strippée entière, pas un dict. Sans ce
         fallback, _extract_str retournait toujours "" → tous les writes
         CodeAgent avaient le même hash → le stall detector ne resetait JAMAIS
         son compteur → faux positif à 17 turns sur du debug légitime.
    """
    if isinstance(arguments, dict):
        val = arguments.get(key, "")
        return val if isinstance(val, str) else str(val)
    if isinstance(arguments, str):
        # Cas 2 : JSON-string (ToolCallingAgent sérialisé).
        import json

        try:
            parsed = json.loads(arguments)
            if isinstance(parsed, dict):
                val = parsed.get(key, "")
                return val if isinstance(val, str) else str(val)
        except (json.JSONDecodeError, ValueError):
            pass
        # Cas 3 : ligne source Python (CodeAgent). On parse la valeur après
        # `key=` (guillemets doubles ou simples). Best-effort : si la valeur
        # contient elle-même des guillemets imbriqués, on prend tout jusqu'au
        # prochain `, <ident>=` ou fin de parenthèse. Suffisant pour distinguer
        # deux writes au contenu différent (le but du stall detector).
        import re

        # Cherche key="..." ou key='...' (gourmand, jusqu'au guillemet fermant).
        m = re.search(rf"{re.escape(key)}\s*=\s*\"(.*?)\"", arguments, re.DOTALL)
        if m:
            return m.group(1)
        m = re.search(rf"{re.escape(key)}\s*=\s*'(.*?)'", arguments, re.DOTALL)
        if m:
            return m.group(1)
    return ""


def compute_material_fingerprint(tool_name: str, arguments: Any) -> str:
    """Hash du CONTENU "matériel" produit par un outil d'écriture.

    Pour un write_file → SHA256(content).
    Pour search_replace/edit_file → SHA256(old_string + new_string).
    Pour append_file → SHA256(content).
    Pour multi_replace → SHA256 de la concaténation des (old, new).
    Pour un outil non-écriture → "" (pas de matériel).

    Port de `_group_fingerprint` (loopx pr_monitor_materialization.py:110-112).
    On tronque à 16 hex chars (64 bits) comme loopx — suffisant pour la
    détection de boucle, plus compact.
    """
    name = (tool_name or "").strip()
    if name not in WRITE_TOOLS:
        return ""

    if name == "multi_replace":
        # replacements = [{"old_string": ..., "new_string": ...}, ...]
        import json

        repl = arguments.get("replacements") if isinstance(arguments, dict) else None
        if isinstance(repl, str):
            try:
                repl = json.loads(repl)
            except (json.JSONDecodeError, ValueError):
                repl = None
        if isinstance(repl, list):
            parts = []
            for r in repl:
                if isinstance(r, dict):
                    parts.append(
                        f"{r.get('old_string', '')}|{r.get('new_string', '')}"
                    )
            payload = "\n".join(parts)
            return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        # Cas CodeAgent (ligne source Python) : _extract_str via regex extrait le
        # contenu brut de replacements= (qui peut être une repr de list Python).
        # On hashe la portion de la ligne source après "replacements=" — suffisant
        # pour distinguer deux multi_replace au contenu différent (le but du stall
        # detector). HOTFIX parallèle au 3e cas de _extract_str (bug F-88 initial
        # qui ne couvrait que write_file/append/edit/search_replace, pas multi_replace).
        if isinstance(arguments, str):
            return hashlib.sha256(arguments.encode("utf-8")).hexdigest()[:16]
        return ""

    # write_file / append_file : content. edit_file / search_replace : old + new.
    if name in ("write_file", "append_file"):
        content = _extract_str(arguments, "content")
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    # edit_file / search_replace.
    old = _extract_str(arguments, "old_string")
    new = _extract_str(arguments, "new_string")
    payload = f"{old}\n{new}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def dominant_material_hash(tool_calls: list[tuple[str, Any]]) -> str:
    """Hash matériel dominant d'un turn = celui du DERNIER write du turn.

    Un turn peut enchaîner plusieurs writes (ex: squelette + append). Le
    dernier write est le plus représentatif de l'état final produit.
    """
    last = ""
    for name, args in tool_calls:
        h = compute_material_fingerprint(name, args)
        if h:
            last = h
    return last


class StallDetector:
    """Détecteur de stall pour UN agent sur UNE session.

    Cycle de vie : une instance par exécution d'agent (créée dans
    `run_with_retry`). `record()` à chaque turn ; `is_stalled()` renvoie True
    si le seuil de turns consécutifs sans matériel nouveau est atteint.

    `reset()` est appelé entre deux retries dans `run_with_retry` (l'historique
    smolagents est purgé, on aligne le compteur pour ne pas polluer le retry).
    """

    def __init__(self, threshold: int = 2, enabled: bool = True):
        # threshold = nombre de turns consécutifs "sans matériel nouveau" qui
        # déclenche le stall. 2 par défaut (loopx MONITOR_DEBT_UNCHANGED_TURN_THRESHOLD) :
        # 1 seul turn gratuit est légitime (réflexion, relecture), 2 = stall avéré.
        if threshold < 1:
            raise ValueError("stall_detector_threshold doit être >= 1")
        self.threshold = threshold
        self.enabled = enabled
        self._lock = threading.Lock()
        self._consecutive_no_material = 0
        self._last_material_hash: Optional[str] = None

    def record(self, outcome: DeliveryOutcome, material_hash: str, is_verification: bool = False) -> None:
        """Met à jour le compteur de stall selon l'outcome du turn.

        No-op si le détecteur est désactivé. Fail-open : toute exception est
        avalée (un guard ne doit jamais brick l'agent).
        """
        if not self.enabled:
            return
        try:
            with self._lock:
                if is_verification:
                    # F-151 : La validation visuelle / inspection active est une progression
                    # légitime vers final_answer. Elle ne doit pas incrémenter le compteur de stall.
                    self._consecutive_no_material = 0
                    return
                if outcome in ACCOUNTABLE_OUTCOMES and material_hash:
                    if material_hash == self._last_material_hash:
                        # Reproduction : même matériel que le tour précédent = stall.
                        self._consecutive_no_material += 1
                    else:
                        # Matériel nouveau : on progresse, reset.
                        self._consecutive_no_material = 0
                    self._last_material_hash = material_hash
                else:
                    # PROGRESS / IDLE : pas de matériel nouveau, incrément.
                    self._consecutive_no_material += 1
        except Exception:
            # Fail-open doctrine : un guard ne doit jamais bloquer l'agent.
            pass

    def is_stalled(self) -> bool:
        """True si le seuil de turns consécutifs sans matériel nouveau est atteint."""
        if not self.enabled:
            return False
        with self._lock:
            return self._consecutive_no_material >= self.threshold

    def signal(self) -> Optional[str]:
        """Message pédagogique si stall détecté, sinon None.

        Distinct du message du LoopGuard : on cible le failure mode "reproduire
        le même livrable sans progresser" plutôt que "répéter le même tool call".
        """
        if not self.enabled:
            return None
        with self._lock:
            if self._consecutive_no_material < self.threshold:
                return None
            count = self._consecutive_no_material
        return (
            f"CIRCUIT BREAKER (Stall Detector) : {count} turns consécutifs sans "
            f"changement matériel (seuil {self.threshold}). Tu réécris le même "
            f"contenu ou tu tournes sans produire de livrable nouveau. CHANGE "
            f"D'APPROCHE : `read_file` pour voir l'état réel du fichier, "
            f"`final_answer` pour rendre ton résultat, ou modifie réellement le "
            f"contenu (différent du tour précédent). Ne reproduis PAS le même "
            f"write ni n'enchaîne pas de lectures vaines."
        )

    def reset(self) -> None:
        """Remet à zéro le compteur et le hash précédent (entre deux retries)."""
        with self._lock:
            self._consecutive_no_material = 0
            self._last_material_hash = None
