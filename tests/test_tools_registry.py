"""Tests du registry d'outils et des outils outillés (Phase A).

Tous sans appel LLM : on teste forward() des outils directement.
"""

import os


from agent_server.tools import TOOLS, TOOLS_BY_NAME, get_tools, list_tool_names


class TestRegistry:
    def test_registry_non_vide(self):
        assert len(TOOLS) > 0

    def test_index_par_nom_coherent(self):
        """TOOLS_BY_NAME doit référencer exactement les outils de TOOLS."""
        assert set(TOOLS_BY_NAME.keys()) == {t.name for t in TOOLS}

    def test_get_tools_all(self):
        """get_tools() sans arg retourne tous les outils."""
        all_tools = get_tools()
        assert len(all_tools) == len(TOOLS)

    def test_get_tools_subset(self):
        """get_tools(names) filtre correctement."""
        names = list_tool_names()
        if len(names) >= 2:
            subset = get_tools(names[:2])
            assert len(subset) == 2
            assert [t.name for t in subset] == names[:2]

    def test_get_tools_nom_inexistant_ignore(self):
        """Un nom inexistant est silencieusement ignoré (pas de crash)."""
        subset = get_tools(["nom_inexistant"])
        assert subset == []

    def test_outils_core_toujours_presents(self):
        """Les outils stdlib (filesystem) doivent toujours être là."""
        names = set(list_tool_names())
        assert {"read_file", "write_file", "list_dir"}.issubset(names)


class TestNodeExecTool:
    def test_exec_javascript_simple(self):
        from agent_server.tools.node_exec import NodeExecTool
        tool = NodeExecTool()
        result = tool.forward(code="console.log('hello from node');", timeout=10)
        assert "hello from node" in result

    def test_exec_avec_calcul(self):
        from agent_server.tools.node_exec import NodeExecTool
        tool = NodeExecTool()
        result = tool.forward(code="console.log(2 + 3);", timeout=10)
        assert "5" in result

    def test_exec_erreur_retourne_stderr(self):
        from agent_server.tools.node_exec import NodeExecTool
        tool = NodeExecTool()
        result = tool.forward(code="throw new Error('boum');", timeout=10)
        assert "boum" in result or "Error" in result

    def test_timeout(self):
        from agent_server.tools.node_exec import NodeExecTool
        tool = NodeExecTool()
        # Boucle infinie tronquée par le timeout
        result = tool.forward(code="while(true) {}", timeout=2)
        assert "TIMEOUT" in result


class TestFileSystemTools:
    def test_write_then_read(self, tmp_path):
        from agent_server.tools.filesystem import ReadFileTool, WriteFileTool
        writer = WriteFileTool()
        reader = ReadFileTool()
        path = str(tmp_path / "test.txt")
        w = writer.forward(path=path, content="ligne 1\nligne 2")
        assert "[OK]" in w
        r = reader.forward(path=path)
        assert "ligne 1" in r and "ligne 2" in r

    def test_read_inexistant(self):
        from agent_server.tools.filesystem import ReadFileTool
        reader = ReadFileTool()
        r = reader.forward(path="/chemin/inexistant/12345.txt")
        assert "introuvable" in r.lower()

    def test_write_cree_repertoires(self, tmp_path):
        from agent_server.tools.filesystem import WriteFileTool
        writer = WriteFileTool()
        path = str(tmp_path / "sous" / "dossier" / "f.txt")
        w = writer.forward(path=path, content="x")
        assert "[OK]" in w
        assert os.path.exists(path)

    def test_list_dir(self, tmp_path):
        from agent_server.tools.filesystem import WriteFileTool, ListDirTool
        writer = WriteFileTool()
        lister = ListDirTool()
        writer.forward(path=str(tmp_path / "a.py"), content="x")
        writer.forward(path=str(tmp_path / "b.js"), content="y")
        result = lister.forward(path=str(tmp_path))
        assert "a.py" in result and "b.js" in result
