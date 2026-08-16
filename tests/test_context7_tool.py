"""Tests de l'intégration Context7 (graph_orchestrator/context7_tool.py).

Pattern du projet : SYNCHRONE + monkeypatch, AUCUNE connexion réseau réelle
(calqué sur tests/test_skills_and_mcp.py). On mocke au point d'entrée réseau
(build_context7_params, ToolCollection.from_mcp) et on vérifie le comportement
de dégradation gracieuse (la spec centrale de ce module).
"""

from unittest.mock import MagicMock


from graph_orchestrator import context7_tool
from graph_orchestrator import skills_loader
from graph_orchestrator import mcp_connect


# ==========================================
# Dégradation gracieuse sans clé API
# ==========================================

class TestNoApiKey:
    def test_context7_tools_sans_cle_yield_liste_vide(self, monkeypatch):
        """Sans CONTEXT7_API_KEY, context7_tools() yield [] (pas de crash, pas de réseau)."""
        monkeypatch.delenv("CONTEXT7_API_KEY", raising=False)
        monkeypatch.setattr(context7_tool, "_build_params", lambda: None)
        with context7_tool.context7_tools() as tools:
            assert tools == []

    def test_fetch_context7_brief_sans_cle_retourne_vide(self, monkeypatch):
        """Sans clé, fetch_context7_brief() retourne '' (l'Architect planifie sans doc)."""
        monkeypatch.setattr(context7_tool, "_build_params", lambda: None)
        assert context7_tool.fetch_context7_brief("Build a React app") == ""

    def test_fetch_context7_brief_ne_depend_pas_du_contenu_sans_cle(self, monkeypatch):
        """Même avec un contenu riche (libs externes), pas de clé = pas de brief = pas d'appel réseau."""
        monkeypatch.setattr(context7_tool, "_build_params", lambda: None)
        # Ne doit jamais lever, quel que soit l'input.
        assert context7_tool.fetch_context7_brief("") == ""
        assert context7_tool.fetch_context7_brief("Chart.js + React + pandas") == ""


# ==========================================
# context7_tools() avec clé (mock réseau)
# ==========================================

class TestGetToolsMocked:
    def test_context7_tools_avec_cle_yield_outils(self, monkeypatch):
        """Avec clé + connexion OK, context7_tools() yield les outils MCP."""
        fake_params = {"url": "https://mcp.context7.com/mcp", "transport": "streamable-http"}
        monkeypatch.setattr(context7_tool, "_build_params", lambda: fake_params)

        # Mock de ToolCollection.from_mcp : c'est un @contextmanager, donc on doit
        # mocker via un faux context manager qui yield une ToolCollection factice.
        fake_tool_a = MagicMock()
        fake_tool_a.name = "resolve_library_id"
        fake_tool_b = MagicMock()
        fake_tool_b.name = "query_docs"

        fake_collection = MagicMock()
        fake_collection.tools = [fake_tool_a, fake_tool_b]

        from contextlib import contextmanager

        @contextmanager
        def fake_from_mcp(params, **kwargs):
            yield fake_collection

        monkeypatch.setattr(mcp_connect, "ToolCollection", MagicMock(from_mcp=fake_from_mcp))

        with context7_tool.context7_tools() as tools:
            assert len(tools) == 2
            assert {t.name for t in tools} == {"resolve_library_id", "query_docs"}

    def test_context7_tools_connexion_echouee_yield_vide(self, monkeypatch):
        """Si from_mcp lève (réseau down), context7_tools() yield [] (pas de crash)."""
        monkeypatch.setattr(context7_tool, "_build_params", lambda: {"url": "http://x"})
        monkeypatch.setattr(
            mcp_connect, "ToolCollection",
            MagicMock(from_mcp=MagicMock(side_effect=ConnectionError("network down"))),
        )
        with context7_tool.context7_tools() as tools:
            assert tools == []


# ==========================================
# fetch_context7_brief (mock des outils MCP)
# ==========================================

class TestFetchBriefMocked:
    def _patch_mcp(self, monkeypatch, resolver_return, docs_return=None, docs_side_effect=None):
        """Branche un faux ToolCollection.from_mcp avec 2 outils (resolve + docs).

        Les outils MCP smolagents sont appelables (via __call__ → forward). On crée
        deux MagicMock simples dont on fixe .name et le .return_value/side_effect.
        """
        monkeypatch.setattr(context7_tool, "_build_params", lambda: {"url": "http://x"})

        resolver = MagicMock(return_value=resolver_return)
        resolver.name = "resolve_library_id"

        doc_tool = MagicMock()
        doc_tool.name = "query_docs"
        if docs_side_effect is not None:
            doc_tool.side_effect = docs_side_effect
        else:
            doc_tool.return_value = docs_return

        fake_collection = MagicMock()
        fake_collection.tools = [resolver, doc_tool]

        from contextlib import contextmanager

        @contextmanager
        def fake_from_mcp(params, **kwargs):
            yield fake_collection

        monkeypatch.setattr(mcp_connect, "ToolCollection", MagicMock(from_mcp=fake_from_mcp))
        return fake_collection

    def test_brief_succes_assemble_resume(self, monkeypatch):
        """Brief normal : resolve trouve un libraryId, query_docs renvoie de la doc → résumé assemblé."""
        self._patch_mcp(
            monkeypatch,
            resolver_return="Found: /chartjs/chart.js (trust 9.0)",
            docs_return="## Chart.js\nUse new Chart(ctx, {type:'line', data:{...}}).\nSignature exacte ici.",
        )
        brief = context7_tool.fetch_context7_brief("Create a line chart with Chart.js")
        assert "Context7" in brief
        assert "/chartjs/chart.js" in brief
        assert "Signature exacte" in brief

    def test_brief_aucun_libraryid_retourne_vide(self, monkeypatch):
        """Si resolve ne renvoie rien qui ressemble à un /org/project, on retourne ''."""
        self._patch_mcp(
            monkeypatch,
            resolver_return="Aucune librairie trouvée pour cette requête.",
            docs_return="",
        )
        assert context7_tool.fetch_context7_brief("query sans lib") == ""

    def test_brief_doc_tool_leve_exception_retourne_vide(self, monkeypatch):
        """Si query_docs plante (API instable), fetch_context7_brief retourne '' (pas de crash)."""
        self._patch_mcp(
            monkeypatch,
            resolver_return="Match: /vercel/next.js",
            docs_side_effect=RuntimeError("API error"),
        )
        assert context7_tool.fetch_context7_brief("Next.js setup") == ""

    def test_brief_tronque_doc_trop_longue(self, monkeypatch):
        """Une doc très longue est tronquée pour ne pas saturer le contexte de l'Architect."""
        long_doc = "X" * 5000
        self._patch_mcp(
            monkeypatch,
            resolver_return="/org/project",
            docs_return=long_doc,
        )
        brief = context7_tool.fetch_context7_brief("big lib")
        # max_chars = 1500 dans l'implémentation.
        assert len(brief) < 1800  # brief = header + doc tronquée
        assert "[...]" in brief


# ==========================================
# Branchement skills_loader (dormance vanilla vs. déclenchement libs)
# ==========================================

class TestSkillsLoaderIntegration:
    def test_skill_context7_au_socle_coder(self):
        """context7-research fait partie du socle Coder (toujours injecté)."""
        assert "context7-research" in skills_loader.BASE_SKILLS_BY_NODE["coder"]

    def test_libs_externes_declenchent_le_skill(self):
        """Les libs/frameworks externes forcent le skill context7-research."""
        for prompt in [
            "Crée un dashboard avec Chart.js",
            "Build a React single-page app",
            "Mini-jeu 3D avec Three.js",
            "Analyse de données en pandas + numpy",
            "API REST avec FastAPI",
        ]:
            skills = skills_loader.select_skills_for_coder(prompt)
            assert "context7-research" in skills, f"Devrait déclencher context7 pour: {prompt!r}"

    def test_vanilla_pur_ne_declenche_pas_de_recherche_supplementaire(self):
        """Vanilla pur / algo de base : le skill socle est présent mais c'est lui qui
        dit 'ne cherche pas' — la DÉCISION de ne pas appeler Context7 est dans le skill,
        pas dans le loader. On vérifie juste qu'aucun signal faux-positif ne force une
        recherche (pas de bug de regex)."""
        # Le socle contient context7-research (injection systématique), mais la
        # règle dynamique NE doit PAS s'ajouter en double pour du vanilla.
        skills = skills_loader.select_skills_for_coder("Tri à bulles en JavaScript vanilla, HTML et CSS.")
        assert skills.count("context7-research") == 1  # présent (socle) mais pas en doublon

    def test_mention_lib_detectee_par_architect(self):
        """Le garde-fou _mentions_external_lib de l'Architect détecte les libs."""
        from graph_orchestrator.dspy_nodes import _mentions_external_lib
        assert _mentions_external_lib("Crée une app Vue.js avec Chart.js") is True
        assert _mentions_external_lib("Tri à bulles en vanilla JS") is False
        assert _mentions_external_lib("") is False
        assert _mentions_external_lib("pandas dataframe processing") is True
