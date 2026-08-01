"""Sanitizer (Auto-typage) — Priorité 8 (F-42) du plan usine logicielle.

Un petit modèle LLM a tendance à émettre des arguments d'outil malformés :
`offset="1, 80"` au lieu de `offset=80`, `replace_all="true"` au lieu de
`replace_all=True`, une structure sérialisée en string pour un champ `array`/
`object`, etc. Renvoyé tel quel à smolagents, ce genre de valeur déclenche une
`TypeError`/`ValueError` de validation → l'appel d'outil échoue → l'agent
retente (gâche des tokens) ou, pire, boucle.

Ce module est la couche *Sanitizer* : un proxy d'outil (`SanitizedTool`) qui,
avant de déléguer à l'outil réel, coerce de façon **best-effort** les arguments
vers le type déclaré dans le schéma `tool.inputs` (source de vérité réelle, PAS
d'inférence LLM). Déterministe, 100 % Python natif, 0 LLM.

Deux niveaux :
- `coerce_value(value, type_spec)` / `sanitize_tool_arguments(arguments, inputs)` :
  coercition pure, testable isolément.
- `SanitizedTool(BaseTool)` + `wrap_tool` / `sanitize_tools` : branchement dans
  les nœuds Coder/Architect. Le proxy copie `name/description/inputs/output_type`
  de l'outil sous-jacent — le CodeAgent smolagents expose les outils dans
  l'interpréteur et les appelle via leur `__call__` directement (chemin
  d'exécution CodeAgent, PAS `execute_tool_call`/`validate_tool_arguments`) :
  le proxy intercepte donc bien avant `forward`.

Politique de coercition : *best-effort*. Une valeur non coercible est laissée
telle quelle → la validation smolagents reste l'arbitre final (aucun faux
positif, aucune corruption silencieuse). Les clés inconnues/absentes restent
inchangées.
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any, List, Optional

from smolagents import BaseTool

# Extraction du dernier nombre entier d'une chaîne (ex: "1, 80" → 80).
_INT_RE = re.compile(r"[+-]?\d+")


# ==========================================
# Niveau 1 : coercition pure (0 dépendance smolagents possible)
# ==========================================
def _parse_string_to_structure(value: Any) -> Any:
    """Parse une string représentant une structure JSON / literal Python.

    Référence : `_normalize_todos` de learn-claude-code (fallback
    `json.loads` → `ast.literal_eval`). En cas d'échec, renvoie la valeur
    inchangée (best-effort).
    """
    s = value.strip()
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        return ast.literal_eval(s)
    except (SyntaxError, ValueError):
        return value


def _coerce_integer(value: Any) -> Any:
    """Coerce vers un entier. `"1, 80"` → 80 (dernier entier de la chaîne)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    matches = _INT_RE.findall(str(value))
    if matches:
        return int(matches[-1])
    return value


def _coerce_number(value: Any) -> Any:
    """Coerce vers un nombre (float/int). Dernier nombre trouvé dans une chaîne."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    s = str(value).strip()
    try:
        return float(s)
    except ValueError:
        matches = re.findall(r"[+-]?\d+(?:\.\d+)?", s)
        if matches:
            return float(matches[-1])
        return value


def _coerce_boolean(value: Any) -> Any:
    """Coerce vers un booléen. `"true"`/`1`/`yes`/`on` → True ; l'inverse → False."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return value


def coerce_value(value: Any, type_spec: Optional[dict]) -> Any:
    """Coerce une valeur vers le type déclaré dans `type_spec` (best-effort).

    - `value is None` → renvoyé tel quel (le flag `nullable` est laissé à la
      validation smolagents).
    - `type_spec` non-dict → valeur inchangée.
    - Valeur non coercible → valeur inchangée (la validation reste l'arbitre).
    """
    if value is None:
        return None
    if not isinstance(type_spec, dict):
        return value
    declared = (type_spec.get("type") or "string").lower()

    try:
        if declared == "array":
            # Une string pour un champ array → on tente de la parser en liste.
            if isinstance(value, str):
                parsed = _parse_string_to_structure(value)
                return parsed if isinstance(parsed, list) else value
            return value
        if declared == "object":
            # Une string pour un champ object → on tente de la parser en dict.
            if isinstance(value, str):
                parsed = _parse_string_to_structure(value)
                return parsed if isinstance(parsed, dict) else value
            return value
        if declared == "integer":
            return _coerce_integer(value)
        if declared == "number":
            return _coerce_number(value)
        if declared == "boolean":
            return _coerce_boolean(value)
        if declared == "string":
            return value if isinstance(value, str) else str(value)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return value
    return value


def sanitize_tool_arguments(arguments: Any, inputs: dict) -> Any:
    """Coerce les arguments d'un appel d'outil selon le schéma `inputs`.

    - Arguments dict : renvoie un NOUVEAU dict, chaque clé connue du schéma
      étant coerce best-effort ; les clés inconnues/absentes restent inchangées.
    - Arguments non-dict : renvoyés inchangés (le proxy gère l'appel nominal
      en kwargs ; ce repli couvre les cas dégénérés).
    """
    if not isinstance(arguments, dict):
        return arguments
    if not isinstance(inputs, dict):
        return arguments
    coerced: dict = {}
    for key, value in arguments.items():
        coerced[key] = coerce_value(value, inputs.get(key))
    return coerced


# ==========================================
# Niveau 2 : proxy d'outil (branchement CodeAgent)
# ==========================================
class SanitizedTool(BaseTool):
    """Proxy émulant un outil smolagents en coercant (auto-typage) ses arguments.

    Copie `name`/`description`/`inputs`/`output_type` de l'outil sous-jacent
    pour être transparent vis-à-vis du CodeAgent, puis intercepte `__call__`
    avant de déléguer `forward` à l'outil réel.
    """

    def __init__(self, tool: BaseTool):
        self._wrapped = tool
        self.name = getattr(tool, "name", "")
        self.description = getattr(tool, "description", "")
        self.inputs = getattr(tool, "inputs", {})
        self.output_type = getattr(tool, "output_type", "string")
        super().__init__()

    def forward(self, *args: Any, **kwargs: Any) -> Any:
        """Utile si le proxy est utilisé hors `__call__` ; coerce puis délègue."""
        coerced = sanitize_tool_arguments(kwargs, self.inputs)
        return self._wrapped.forward(*args, **coerced)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Point d'accroche : coerce les arguments avant de déléguer à l'outil réel.

        Le `__call__` de l'outil sous-jacent gère son `setup()` et son `forward()`
        natif — on ne réimplémente pas sa logique, on ne fait qu'assainir l'entrée.
        """
        coerced = sanitize_tool_arguments(kwargs, self.inputs)
        return self._wrapped(*args, **coerced)


def wrap_tool(tool: BaseTool) -> BaseTool:
    """Enveloppe un outil dans `SanitizedTool` s'il s'agit d'un `BaseTool`."""
    if isinstance(tool, BaseTool):
        return SanitizedTool(tool)
    return tool


def sanitize_tools(tools: List[BaseTool], enabled: bool = True) -> List[BaseTool]:
    """Enveloppe une liste d'outils. No-op (liste inchangée) quand désactivé."""
    if not enabled:
        return tools
    return [wrap_tool(t) for t in tools]
