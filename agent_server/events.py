"""Sérialiseur d'événements : convertit les ActionStep smolagents en dictionnaires JSON.

Utilisé par step_callbacks pour pousser des événements vers la WebSocket.
Extrait de chaque ActionStep : step_number, tool_calls, observations, tokens, durée, erreurs.
"""



def action_step_to_event(step) -> dict:
    """Convertit un ActionStep smolagents en dict sérialisable JSON.

    Gère gracieusement les champs manquants (None) — un step précoce peut ne pas
    avoir encore tool_calls/observations.
    """
    data: dict = {
        "step_number": getattr(step, "step_number", 0),
    }

    # Tool calls : [{name, arguments, id}]
    tool_calls = getattr(step, "tool_calls", None)
    if tool_calls:
        calls = []
        for tc in tool_calls:
            calls.append({
                "name": getattr(tc, "name", "?"),
                "arguments": _safe_str(getattr(tc, "arguments", None)),
                "id": getattr(tc, "id", None),
            })
        data["tool_calls"] = calls

    # Observations (sortie de l'outil)
    observations = getattr(step, "observations", None)
    if observations:
        # Tronque les observations énormes
        obs = str(observations)
        if len(obs) > 5000:
            obs = obs[:5000] + "\n... [tronqué]"
        data["observations"] = obs

    # Code action (pour CodeAgent : le code Python généré)
    code_action = getattr(step, "code_action", None)
    if code_action:
        data["code_action"] = str(code_action)[:5000]

    # Token usage
    token_usage = getattr(step, "token_usage", None)
    if token_usage is not None:
        data["input_tokens"] = getattr(token_usage, "input_tokens", None)
        data["output_tokens"] = getattr(token_usage, "output_tokens", None)

    # Durée
    timing = getattr(step, "timing", None)
    if timing is not None:
        duration = getattr(timing, "duration", None)
        if duration is not None:
            data["duration_s"] = round(duration, 2)

    # Erreur
    error = getattr(step, "error", None)
    if error is not None:
        data["error"] = _safe_str(error)[:1000]

    # Final answer ?
    is_final = getattr(step, "is_final_answer", False)
    if is_final:
        action_output = getattr(step, "action_output", None)
        if action_output is not None:
            data["final_output"] = _safe_str(action_output)[:5000]

    return data


def _safe_str(obj) -> str:
    """Convertit un objet en string de façon sûre (gère dict, list, None)."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    try:
        import json
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)
