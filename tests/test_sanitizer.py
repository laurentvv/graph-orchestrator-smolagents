"""Tests unitaires du Sanitizer (Auto-typage) — Priorité 8 (F-42).

Valide la coercition best-effort des arguments d'outil malformés émis par un
petit LLM, via le schéma `tool.inputs` réel. Déterministe, 0 LLM.

Couvre :
- coercion par type : integer (`"1, 80"` → 80), number, boolean (`"true"`/`1` →
  True), string (int → str), array/object (string JSON → structure).
- best-effort : valeur non coercible laissée inchangée (la validation smolagents
  reste l'arbitre final) ; `None` respecté.
- sanitize_tool_arguments : clés inconnues/absentes inchangées, non-dict intact.
- SanitizedTool : copie name/description/inputs/output_type + délègue à l'outil
  réel en coercant.
- wrap_tool / sanitize_tools : enabled enveloppe, disabled = no-op.
"""
from smolagents import BaseTool

from graph_orchestrator.sanitizer import (
    SanitizedTool,
    coerce_value,
    sanitize_tool_arguments,
    sanitize_tools,
    wrap_tool,
)


# ==========================================
# coerce_value — scalar coerci par type
# ==========================================
def test_coerce_integer_extracts_last_number():
    """`"1, 80"` → 80 (dernier entier de la chaîne), le cas cible F-42."""
    assert coerce_value("1, 80", {"type": "integer"}) == 80


def test_coerce_integer_already_int_and_float():
    assert coerce_value(42, {"type": "integer"}) == 42
    assert coerce_value(42.7, {"type": "integer"}) == 42


def test_coerce_integer_uncoercible_left_intact():
    assert coerce_value("abc", {"type": "integer"}) == "abc"


def test_coerce_integer_bool_preserved():
    # bool est un sous-type d'int ; on le laisse tel quel (pas de faux 0/1).
    assert coerce_value(True, {"type": "integer"}) is True


def test_coerce_number():
    assert coerce_value("3.5", {"type": "number"}) == 3.5
    assert coerce_value(2, {"type": "number"}) == 2
    assert coerce_value("x", {"type": "number"}) == "x"


def test_coerce_boolean():
    assert coerce_value("true", {"type": "boolean"}) is True
    assert coerce_value("1", {"type": "boolean"}) is True
    assert coerce_value("yes", {"type": "boolean"}) is True
    assert coerce_value("false", {"type": "boolean"}) is False
    assert coerce_value("0", {"type": "boolean"}) is False
    assert coerce_value("big", {"type": "boolean"}) == "big"


def test_coerce_boolean_already_bool():
    assert coerce_value(True, {"type": "boolean"}) is True


def test_coerce_string():
    assert coerce_value("keep", {"type": "string"}) == "keep"
    assert coerce_value(42, {"type": "string"}) == "42"


# ==========================================
# coerce_value — structures array/object + cas limites
# ==========================================
def test_coerce_array_from_json_string():
    assert coerce_value('["a", "b"]', {"type": "array"}) == ["a", "b"]


def test_coerce_object_from_json_string():
    assert coerce_value('{"k": 1}', {"type": "object"}) == {"k": 1}


def test_coerce_unparseable_structure_left_intact():
    assert coerce_value("pas une liste", {"type": "array"}) == "pas une liste"


def test_coerce_none_respected():
    assert coerce_value(None, {"type": "integer", "nullable": True}) is None


def test_coerce_type_spec_none_or_invalid():
    assert coerce_value("x", None) == "x"
    assert coerce_value("x", "not-a-dict") == "x"


# ==========================================
# sanitize_tool_arguments
# ==========================================
def test_sanitize_known_keys_only():
    inputs = {"offset": {"type": "integer"}, "limit": {"type": "integer"}}
    out = sanitize_tool_arguments({"offset": "1, 80", "limit": 10}, inputs)
    assert out == {"offset": 80, "limit": 10}


def test_sanitize_unknown_keys_untouched():
    inputs = {"offset": {"type": "integer"}}
    out = sanitize_tool_arguments({"path": "a.txt", "offset": "7"}, inputs)
    assert out["path"] == "a.txt"  # clé inconnue inchangée
    assert out["offset"] == 7


def test_sanitize_non_dict_arguments_untouched():
    assert sanitize_tool_arguments("just a string", {}) == "just a string"
    assert sanitize_tool_arguments(["a"], {"offset": {"type": "integer"}}) == ["a"]


def test_sanitize_non_dict_inputs_noop():
    assert sanitize_tool_arguments({"offset": "1, 80"}, None) == {"offset": "1, 80"}

# ==========================================
# SanitizedTool — proxy
# ==========================================
class _Probe(BaseTool):
    """Outil factice : enregistre les arguments reçus par `forward`."""

    def __init__(self):
        self.calls = []
        self.name = "probe"
        self.description = "probe tool"
        self.inputs = {
            "offset": {"type": "integer", "nullable": True},
            "path": {"type": "string"},
            "replace_all": {"type": "boolean", "nullable": True},
        }
        self.output_type = "string"
        super().__init__()

    def __call__(self, *args, **kwargs):
        return self.forward(*args, **kwargs)

    def forward(self, *args, **kwargs):
        self.calls.append(kwargs)
        return str(kwargs)


def test_sanitized_tool_copies_metadata():
    probe = _Probe()
    proxy = SanitizedTool(probe)
    assert proxy.name == "probe"
    assert proxy.description == "probe tool"
    assert proxy.inputs == probe.inputs
    assert proxy.output_type == "string"


def test_sanitized_tool_coerces_and_delegates():
    probe = _Probe()
    proxy = SanitizedTool(probe)
    result = proxy(offset="1, 80", path="a.txt", replace_all="true")
    # L'outil réel a reçu des arguments COERCIS (int + bool), pas les strings.
    assert probe.calls == [{"offset": 80, "path": "a.txt", "replace_all": True}]
    assert result == str({"offset": 80, "path": "a.txt", "replace_all": True})


def test_sanitized_tool_valid_callable_isinstance():
    """Le proxy reste un BaseTool (satisfait les vérifications de type)."""
    proxy = SanitizedTool(_Probe())
    assert isinstance(proxy, BaseTool)


# ==========================================
# wrap_tool / sanitize_tools
# ==========================================
def test_wrap_tool_wraps_base_tool():
    proxy = wrap_tool(_Probe())
    assert isinstance(proxy, SanitizedTool)


def test_sanitize_tools_enabled_wraps_all():
    tools = [_Probe(), _Probe()]
    wrapped = sanitize_tools(tools, enabled=True)
    assert all(isinstance(t, SanitizedTool) for t in wrapped)


def test_sanitize_tools_disabled_is_noop():
    tools = [_Probe(), _Probe()]
    wrapped = sanitize_tools(tools, enabled=False)
    assert wrapped is tools  # même objet, aucune copie ni wrap
    assert all(isinstance(t, _Probe) for t in wrapped)

