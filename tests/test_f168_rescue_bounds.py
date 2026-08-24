"""Tests F-168 — sauvetage verdict borné + cap no-think dédié.

Post-mortem run 1835 (E2E bubble-sort post-F-167, tué à 1h51) :
  1. Le sauvetage DSPy du verdict échouait de 2 façons — ValidationError
     ``string_type`` (la règle LLM « mets null si un champ manque » viole les
     champs requis str/Literal) puis ``JSONAdapter failed to parse`` (réponse
     dégénérée) — et son ``dspy.LM`` n'avait NI max_tokens NI timeout :
     génération en fuite de 7172+ tokens / 25+ min sur le 9B à 5,4 t/s.
  2. Le Tester pydantic et le Coder ULTRA héritaient de
     ``REASONING_MAX_TOKENS=16384`` sur le même 9B no-think → pire cas ~50 min
     pour UNE réponse dégénérée.

Fixes testés ici (0 LLM réel, 0 GPU) :
  - ``_fill_required_defaults`` : null/absent sur champ requis → défaut typé,
    Literal → "failure" (fail-closed) ;
  - passe déterministe AVANT le sauvetage LLM (nulls réparés sans réseau) ;
  - ``dspy.LM`` du sauvetage borné (max_tokens=1200, timeout=300, temp 0) ;
  - signature du sauvetage en ``fixed_json`` texte brut (plus de parsing
    typé DSPy → plus de JSONAdapter crash) ;
  - ``settings.no_think_max_tokens`` (défaut 4096) câblé Tester + ULTRA.
"""

import os
from types import SimpleNamespace

import pytest

from graph_orchestrator.models import CoderOutput, _fill_required_defaults, extract_and_validate


# Le verdict cassé du run 1835 : nulls sur les champs requis (le LLM Tester
# suit l'ancienne règle du sauvetage « mets null si absent »).
_RUN1835_NULL_VERDICT = '{"task_id": "bubble-sort-visualizer", "status": null, "details": null}'


class TestFillRequiredDefaults:
    def test_null_string_fields_filled(self):
        data = _fill_required_defaults(
            {"task_id": "st1", "status": None, "details": None}, CoderOutput
        )
        assert data["status"] == "failure"  # Literal → fail-closed
        assert data["details"] == ""        # str → vide, pas de contenu inventé

    def test_missing_field_filled(self):
        data = _fill_required_defaults({"task_id": "st1", "status": "success"}, CoderOutput)
        assert data["details"] == ""

    def test_optional_fields_untouched(self):
        # linter_ok/vision_ok ont des défauts → pas requis → None laissé (valide
        # après validation Pydantic qui appliquera le défaut du schéma).
        data = _fill_required_defaults(
            {"task_id": "st1", "status": "success", "details": "x", "linter_ok": None},
            CoderOutput,
        )
        assert data["linter_ok"] is None

    def test_valid_values_preserved(self):
        data = _fill_required_defaults(
            {"task_id": "st1", "status": "success", "details": "ok"}, CoderOutput
        )
        assert data["status"] == "success"


class TestDeterministicPass:
    """La passe déterministe répare les nulls SANS réseau (le garde pytest
    renverrait None si le chemin LLM était atteint — un résultat non-None
    prouve que 0 appel LLM n'a eu lieu)."""

    def test_run1835_null_verdict_recovered_deterministically(self):
        out = extract_and_validate(_RUN1835_NULL_VERDICT, CoderOutput)
        assert out is not None
        assert out.status == "failure"  # fail-closed
        assert out.task_id == "bubble-sort-visualizer"

    def test_garbage_json_still_none_under_pytest(self):
        assert extract_and_validate("pas du tout du json {{{", CoderOutput) is None

    def test_broken_structure_still_none_under_pytest(self):
        # JSON structurellement cassé (quotes/braces) → la passe déterministe
        # échoue, le garde pytest coupe avant le sauvetage LLM.
        assert extract_and_validate('{"task_id": "st1", "status": ', CoderOutput) is None


class TestRescueBounded:
    """Le dspy.LM du sauvetage doit être BORNÉ (F-168) : max_tokens 1200,
    timeout 300 s, température 0 — la génération en fuite de 25+ min du run
    1835 ne doit plus être possible par ce chemin."""

    @pytest.fixture()
    def _real_dspy(self):
        import dspy
        return dspy

    def test_lm_bounded_and_fixed_json_path(self, monkeypatch, _real_dspy):
        captured = {}

        class FakeLM:
            def __init__(self, *args, **kwargs):
                captured.update(kwargs)

        class FakePredict:
            def __init__(self, signature):
                pass

            def __call__(self, **kwargs):
                # Réponse du sauvetage : JSON en TEXTE BRUT (nouvelle signature
                # fixed_json) avec un null résiduel → la passe de remplissage
                # doit le réparer APRÈS parsing.
                return SimpleNamespace(
                    fixed_json='{"task_id": "t1", "status": null, "details": "fixé"}'
                )

        monkeypatch.setattr(_real_dspy, "LM", FakeLM)
        monkeypatch.setattr(_real_dspy, "Predict", FakePredict)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        out = extract_and_validate(
            '{"task_id": "t1", "status": ',  # structure cassée → sauvetage LLM
            CoderOutput,
            api_base="http://127.0.0.1:1/v1",  # port fermé : /models refuse vite
        )
        assert captured.get("max_tokens") == 1200
        assert captured.get("timeout") == 300
        assert captured.get("temperature") == 0.0
        assert out is not None
        assert out.status == "failure"  # null sur Literal → fail-closed
        assert out.details == "fixé"

    def test_rescue_prose_wrapped_json_extracted(self, monkeypatch, _real_dspy):
        """Le sauvetage peut encadrer le JSON de prose — extraction {...}."""

        class FakeLM:
            def __init__(self, *args, **kwargs):
                pass

        class FakePredict:
            def __init__(self, signature):
                pass

            def __call__(self, **kwargs):
                return SimpleNamespace(
                    fixed_json='Voici le JSON réparé :\n```json\n{"task_id": "t2", "status": "success", "details": "ok"}\n```'
                )

        monkeypatch.setattr(_real_dspy, "LM", FakeLM)
        monkeypatch.setattr(_real_dspy, "Predict", FakePredict)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        out = extract_and_validate(
            'garbage total', CoderOutput, api_base="http://127.0.0.1:1/v1"
        )
        assert out is not None
        assert out.status == "success"
        assert out.details == "ok"


class TestNoThinkCap:
    """settings.no_think_max_tokens (défaut 4096) câblé sur le Coder ULTRA."""

    def test_setting_default(self):
        from graph_orchestrator.config import settings as live_settings
        # Singleton : .env local porte NO_THINK_MAX_TOKENS=4096 ; sans la clé,
        # le défaut de Settings s'applique (4096). Les deux font la garantie F-168.
        assert live_settings.no_think_max_tokens == 4096

    def test_ultra_uses_no_think_cap(self):
        from graph_orchestrator.nodes import _select_coder_spec
        fake = SimpleNamespace(
            coder_ultra_correction=True,
            no_think_spec=SimpleNamespace(model="ornith-1.5.gguf"),
            no_think_max_tokens=4096,
            fast_spec=SimpleNamespace(model="qwen.gguf"),
            fast_max_tokens=12000,
        )
        spec, max_tokens, is_ultra = _select_coder_spec({"iteration": 3}, fake)
        assert is_ultra
        assert max_tokens == 4096  # plus JAMAIS reasoning_max_tokens (16384)

    def test_non_ultra_unchanged(self):
        from graph_orchestrator.nodes import _select_coder_spec
        fake = SimpleNamespace(
            coder_ultra_correction=True,
            no_think_spec=SimpleNamespace(model="ornith-1.5.gguf"),
            no_think_max_tokens=4096,
            fast_spec=SimpleNamespace(model="qwen.gguf"),
            fast_max_tokens=12000,
        )
        spec, max_tokens, is_ultra = _select_coder_spec({"iteration": 1}, fake)
        assert not is_ultra
        assert max_tokens == 12000


class TestTesterModelSettingsCap:
    """build_tester_agent doit poser max_tokens=no_think_max_tokens (pydantic
    Agent expose model_settings en attribut)."""

    def test_tester_agent_cap(self, tmp_path):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from graph_orchestrator.tester_pydantic import build_tester_agent
        from graph_orchestrator.config import settings

        # Modèle réel en construction seule (zéro réseau : port fermé).
        model = OpenAIChatModel(
            model_name="test-model",
            provider=OpenAIProvider(api_key="sk-test", base_url="http://127.0.0.1:1/v1"),
        )
        agent = build_tester_agent(
            model=model,
            task={"id": "st1", "content": "test", "target_files": ["index.html"]},
            settings=settings,
            tester_max_steps=4,
        )
        assert agent.model_settings["max_tokens"] == settings.no_think_max_tokens
