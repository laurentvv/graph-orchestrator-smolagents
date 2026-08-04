"""Anti-Loop Cryptographique (Priorité 3 du plan usine logicielle, ligne 73).

Détecte quand un agent (typiquement le Coder) répète EXACTEMENT la même action
d'outil plusieurs fois de suite — le failure mode "tourne en rond" qui vide les
tokens sans progresser. Inspiré de Crush (hash déterministe des interactions).

Fonctionnement
--------------
À chaque ActionStep smolagents, on calcule une empreinte SHA256 de l'interaction :
    ToolName + Input normalisé (arguments triés, whitespace collapse)
(Au sens "interaction d'outil" du plan : ToolName + Input ; on n'inclut pas
l'Output car il varie même si l'agent boucle sur la même action fausse.)

Si la MÊME empreinte apparaît `threshold` fois dans l'historique de la session
courante, on déclenche le circuit-breaker : `run_with_retry` interrompt l'agent
et renvoie une erreur pédagogique au lieu de le laisser brûler un nouveau cycle.

Ce garde-fou est COMPLÉMENTAIRE du `max_iterations` du workflow (qui limite les
itérations Coder→Judge au niveau graphe) et de `_detect_idle_step` (qui détecte
un tour sans AUCUN tool call). Ici on cible le cas précis : l'agent agit, mais
agis À L'IDENTIQUE en boucle.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Optional


def _normalize_arguments(arguments: Any) -> str:
    """Normalise les arguments d'un tool call pour un hash stable.

    On sérialise en JSON avec `sort_keys=True` pour que l'ordre des clés d'un
    dict n'ait pas d'importance, et on strippe le whitespace de tête/queue de
    chaque valeur string (les petits LLM ajoutent/suppriment des espaces au
    hasard — ce ne doit PAS casser la détection de boucle).
    """
    if arguments is None:
        return ""
    try:
        if isinstance(arguments, str):
            # Les arguments peuvent arriver en JSON-string ou en dict déjà parsé.
            try:
                arguments = json.loads(arguments)
            except (json.JSONDecodeError, ValueError):
                return arguments.strip()
        if isinstance(arguments, dict):
            return json.dumps(
                {k: _normalize_scalar(v) for k, v in arguments.items()},
                sort_keys=True,
                ensure_ascii=False,
            )
        return json.dumps(arguments, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(arguments).strip()


def _normalize_scalar(value: Any) -> Any:
    """Strippe le whitespace d'une valeur scalaire string (récursif sur list/dict)."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return {k: _normalize_scalar(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_scalar(v) for v in value]
    return value


def compute_tool_call_fingerprint(tool_name: str, arguments: Any) -> str:
    """Empreinte SHA256 d'une interaction d'outil (ToolName + Input normalisé).

    On préfixe par le nom de l'outil pour que deux outils différents appelés
    avec les mêmes arguments ne soient pas considérés comme une boucle.
    """
    payload = f"{(tool_name or '').strip()}|{_normalize_arguments(arguments)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LoopGuard:
    """Compteur d'empreintes d'interactions pour UN agent sur UNE session.

    Cycle de vie : une instance par exécution d'agent (créée dans
    `run_with_retry`). `record()` à chaque ActionStep ; `repeated_action()`
    renvoie un message pédagogique si le seuil est atteint.

    `reset()` est appelé entre deux retries dans `run_with_retry` (l'historique
    smolagents est purgé, on aligne le compteur pour ne pas polluer le retry).
    """

    def __init__(self, threshold: int = 3, enabled: bool = True):
        # threshold = nombre de RÉPÉTITIONS de la même action qui déclenche le
        # circuit-breaker. 3 par défaut (= 3 appels identiques consécutifs ou
        # cumulés : un humain ne refait JAMAIS 3x le même write_file au même
        # endroit sans boucler).
        if threshold < 2:
            raise ValueError("loop_guard_threshold doit être >= 2")
        self.threshold = threshold
        self.enabled = enabled
        self._counts: Counter[str] = Counter()

    def record(self, tool_name: str, arguments: Any) -> str:
        """Enregistre une interaction et renvoie son empreinte.

        No-op si le guard est désactivé (renvoie une chaîne vide).
        """
        if not self.enabled:
            return ""
            
        # Les outils purement observationnels sont exemptés du LoopGuard.
        # Un agent peut légitimement faire plusieurs screenshots, lire le
        # même fichier plusieurs fois, ou lire la console, sans que ce soit une boucle.
        if tool_name in ("take_screenshot", "take_snapshot", "list_console_messages", "read_file", "evaluate_script"):
            return ""
            
        fp = compute_tool_call_fingerprint(tool_name, arguments)
        self._counts[fp] += 1
        return fp

    def repeated_action(self) -> Optional[str]:
        """Renvoie un message pédagogique si une action dépasse le seuil, sinon None.

        Le message est volontairement directif : on force l'agent à CHANGER
        d'approche (lire le fichier, découper, final_answer) au lieu de
        répéter l'appel qui échoue.
        """
        if not self.enabled:
            return None
        for fp, count in self._counts.items():
            if count >= self.threshold:
                print(f"[LoopGuard] TRIPPED ON: {fp} (count={count})")
                return (
                    f"CIRCUIT BREAKER (Anti-Loop) : tu as appelé le même outil avec les "
                    f"mêmes arguments {count} fois ({self.threshold}+ = boucle avérée). "
                    f"L'action répétée ne résout rien. CHANGE D'APPROCHE : utilise "
                    f"`read_file` pour voir l'état réel du fichier, ou `final_answer` "
                    f"pour rendre ton résultat, ou découpe l'opération autrement. Ne "
                    f"répète PAS le même appel d'outil."
                )
        return None

    def reset(self) -> None:
        """Vide le compteur (entre deux retries d'agent)."""
        self._counts.clear()


def extract_tool_calls_from_step(step) -> list[tuple[str, Any]]:
    """Extrait les (tool_name, arguments) d'un ActionStep smolagents.

    smolagents expose les appels d'outil sous deux formes selon le type d'agent :
      - ToolCallingAgent : `step.tool_calls` (liste de ToolCall avec .name/.arguments)
      - CodeAgent        : `step.code_action` (source Python qui appelle les @tool)

    Pour le CodeAgent, on parse les appels de fonction du bloc Python pour
    récupérer le nom de l'outil (les arguments exacts sont moins fiables en
    parsing AST sans exec — on se contente du nom + bloc code normalisé, ce
    qui suffit à détecter la répétition caractère pour caractère).
    """
    calls: list[tuple[str, Any]] = []

    # Cas 1 : ToolCallingAgent (liste structurée de ToolCall).
    tool_calls = getattr(step, "tool_calls", None)
    if tool_calls:
        for tc in tool_calls:
            name = getattr(tc, "name", None) or ""
            args = getattr(tc, "arguments", None)
            if name:
                calls.append((name, args))
        return calls

    # Cas 2 : CodeAgent (bloc Python). On détecte les appels d'@tool connus en
    # scannant les lignes "outillage_name(" — pas un AST complet (on n'exécute
    # pas le code), juste une détection de répétition au niveau du source.
    code_action = getattr(step, "code_action", None)
    if code_action:
        src = str(code_action)
        # Les outils exposés au Coder (cf. nodes.py coder_tools). On évite une
        # dépendance circulaire en durant la liste courte des outils d'action.
        known_tools = (
            "write_file", "append_file", "edit_file", "search_replace",
            "read_file", "list_directory", "bash_command",
        )
        for line in src.splitlines():
            stripped = line.strip()
            for t in known_tools:
                if f"{t}(" in stripped:
                    # Arguments = la portion d'appel normalisée (assez pour la
                    # détection de boucle ; pas besoin d'un parse parfait).
                    calls.append((t, stripped))
                    break

    return calls
