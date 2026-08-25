"""Tests F-169 — moteur UNIQUE pydantic + gardiens structure DSPy.

Deux volets (décisions user 2026-08-24 soir) :
  1. « Enlève le CodeAgent de smolagents » : les exécutions smolagents du
     Coder (execute_coder_node) et du Web Tester (WebTestRunner) sont
     RETIRÉES — délégation unique à coder_pydantic / tester_pydantic ; les
     settings CODER_ENGINE/TESTER_ENGINE n'existent plus (constat des runs
     1835/2223 : les marqueurs pydantic étaient ABSENTS — moteur smolagents
     par défaut silencieux, spirales de parsing CodeAgent).
  2. « Gardiens DSPy supplémentaires » : _dspy_structure_rescue — quand le
     transport réussit mais que l'adaptateur (JSONAdapter) ne parse pas la
     sortie (Judge/Architect/Security/Drafter), cascade miroir F-168 :
     champs pydantic → extract_and_validate (déterministe puis LLM borné) ;
     champ scalaire str unique → la réponse EST la valeur (sections DSPy
     incluses) ; illisible → None → exception d'origine (historique).

0 LLM réel, 0 réseau (le garde PYTEST_CURRENT_TEST coupe le sauvetage LLM
de models.py — seule la passe déterministe s'exécute dans les tests).
"""

import dspy
import pytest
from pydantic import BaseModel

from graph_orchestrator.dspy_nodes import (
    _dspy_structure_rescue,
    _extract_dspy_section,
    _last_raw_completion,
)


class _Verdict(BaseModel):
    task_id: str
    status: str


class _JudgeSignature(dspy.Signature):
    """Signature témoin : champ de sortie pydantic (comme Judge/Architect)."""

    task_content: str = dspy.InputField()
    output: _Verdict = dspy.OutputField()


class _DrafterSignature(dspy.Signature):
    """Signature témoin : champ de sortie scalaire str unique (Drafter)."""

    subtask_description: str = dspy.InputField()
    draft_markdown: str = dspy.OutputField()


class TestDspyStructureRescue:
    def test_json_noie_dans_prose_recupere(self):
        r = _dspy_structure_rescue(
            _JudgeSignature,
            'Voici mon verdict final : {"task_id": "t1", "status": "success"} — fin.',
            api_base="http://x", model_id="m",
        )
        assert isinstance(r.output, _Verdict)
        assert r.output.status == "success"

    def test_null_sur_requis_rempli_deterministement(self):
        """Le pattern null des petits modèles (run 1835) est réparé SANS LLM
        (passe déterministe F-168) — str requis → chaîne vide, pas de crash."""
        r = _dspy_structure_rescue(
            _JudgeSignature,
            '{"task_id": "t1", "status": null}',
            api_base="http://x", model_id="m",
        )
        assert isinstance(r.output, _Verdict)
        assert r.output.task_id == "t1"
        assert r.output.status == ""

    def test_mono_champ_str_reponse_entiere(self):
        """Drafter : une sortie non parsée par l'adaptateur reste un PLAN
        VALIDE — le texte de la section DSPy (ou la réponse entière) EST la
        valeur du champ. C'est le cas où le gardien sauve le plus."""
        raw = "[[ ## draft_markdown ## ]]\n## Fichier : index.html\n- :root avec valeurs\n"
        r = _dspy_structure_rescue(
            _DrafterSignature, raw, api_base="http://x", model_id="m"
        )
        assert "## Fichier : index.html" in r.draft_markdown
        assert "[[ ##" not in r.draft_markdown  # marqueurs de section retirés

    def test_mono_champ_str_sans_section(self):
        r = _dspy_structure_rescue(
            _DrafterSignature,
            "## Fichier : script.js\n- N = 30",
            api_base="http://x", model_id="m",
        )
        assert r.draft_markdown.startswith("## Fichier : script.js")

    def test_illisible_sans_llm_sous_pytest_retourne_none(self):
        """Garbage total → la passe déterministe échoue, le garde pytest
        coupe le sauvetage LLM → None (l'exception d'origine remonte)."""
        assert _dspy_structure_rescue(
            _JudgeSignature, "aucun json nulle part {{{", api_base="http://x", model_id="m"
        ) is None

    def test_vide_retourne_none(self):
        assert _dspy_structure_rescue(_JudgeSignature, "   ", api_base="http://x", model_id="m") is None


class TestExtractDspySection:
    def test_extrait_section_par_nom(self):
        raw = "[[ ## reasoning ## ]]\nje reflechis\n[[ ## draft_markdown ## ]]\nLE PLAN\n[[ ## done ## ]]"
        assert _extract_dspy_section(raw, "draft_markdown") == "LE PLAN"

    def test_sans_section_texte_entier(self):
        assert _extract_dspy_section("brut complet", "draft_markdown") == "brut complet"


class _FakeMsg:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMsg(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeEntry:
    def __init__(self, content):
        self.response = _FakeResponse(content)


class _FakeLM:
    def __init__(self, entries):
        self.history = entries


class TestLastRawCompletion:
    def test_nouvelles_entrees_uniquement(self):
        """hist_before borne la fenêtre : une erreur de TRANSPORT (aucune
        nouvelle entrée) → None ; un parse fail APRÈS appel réussi → texte."""
        lm = _FakeLM([_FakeEntry("ancien"), _FakeEntry("le nouveau brut")])
        assert _last_raw_completion(lm, 1) == "le nouveau brut"
        assert _last_raw_completion(lm, 2) is None  # rien de nouveau (transport)

    def test_parts_multimodales(self):
        lm = _FakeLM([_FakeEntry([_FakeMsg("img"), "texte utile"])])
        assert _last_raw_completion(lm, 0) == "texte utile"

    def test_robuste_sur_entrees_deformees(self):
        lm = _FakeLM([_FakeEntry(None), object()])
        assert _last_raw_completion(lm, 0) is None


class TestEngineRemovalSmoke:
    """Complément des classes TestCoderEnginePydanticOnly /
    TestTesterEnginePydanticOnly (domiciles naturels) : le graphe n'expose
    plus de chemin smolagents pour Coder/Tester."""

    def test_web_tester_ne_reference_plus_smolagents(self):
        import inspect
        from graph_orchestrator.testers import web_tester

        # Le corps du runner (le docstring module DOCUMENTE le retrait — viser
        # le code exécutable, pas la prose).
        body = inspect.getsource(web_tester.WebTestRunner.run)
        assert "CompactingCodeAgent" not in body
        assert "run_with_retry" not in body

    @pytest.mark.anyio
    async def test_execute_coder_node_pydantic_only(self, monkeypatch):
        import graph_orchestrator.coder_pydantic as cp
        import graph_orchestrator.nodes as nodes
        from graph_orchestrator.config import settings

        calls = []

        async def _fake(task, s):
            calls.append(task)
            return None, None

        monkeypatch.setattr(cp, "run_coder_pydantic", _fake)
        await nodes.execute_coder_node({"id": "x"}, fast_model=None, settings=settings)
        assert len(calls) == 1
