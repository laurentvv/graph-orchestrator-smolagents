"""Tests des skills et de la config MCP (Phase B).

Sans LLM et sans connexion MCP réelle — on teste le parsing et la construction de config.
"""



from agent_server.skills import parse_skill_md, load_skills, get_skill_instructions, list_skills
from agent_server import mcp as mcp_mod


# ==========================================
# Skills
# ==========================================

class TestParseSkillMd:
    def test_parse_avec_frontmatter(self):
        content = """---
name: mon-skill
description: un skill de test
---
# Mon Skill

Instructions ici.
"""
        parsed = parse_skill_md(content)
        assert parsed is not None
        assert parsed["name"] == "mon-skill"
        assert parsed["description"] == "un skill de test"
        assert "Instructions ici" in parsed["instructions"]

    def test_parse_sans_frontmatter(self):
        content = """# Skill Sans FM

Pas de frontmatter.
"""
        parsed = parse_skill_md(content)
        assert parsed is not None
        assert parsed["name"] == "skill-sans-fm"
        assert "Pas de frontmatter" in parsed["instructions"]


class TestLoadSkills:
    def test_skills_reels_charges(self):
        """Les skills du dossier skills/ doivent être chargés."""
        skills = load_skills()
        assert len(skills) >= 2  # coding + python-health-audit
        names = set(skills.keys())
        assert "coding" in names
        assert "python-health-audit" in names

    def test_skill_coding_a_des_instructions(self):
        skills = load_skills()
        assert "coding" in skills
        assert len(skills["coding"]["instructions"]) > 50  # non vide

    def test_get_skill_instructions_par_nom(self):
        instr = get_skill_instructions("coding")
        assert instr is not None
        assert "agent" in instr.lower() or "code" in instr.lower()

    def test_get_skill_inexistant_retourne_none(self):
        assert get_skill_instructions("nimporte-quoi") is None

    def test_list_skills_pour_ui(self):
        result = list_skills()
        assert isinstance(result, list)
        assert all("name" in s and "description" in s for s in result)

    def test_skills_depuis_dossier_temporaire(self, tmp_path):
        """Le chargeur doit fonctionner avec un dossier arbitraire."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test\ndescription: d\n---\n# Test\nInstructions.",
            encoding="utf-8",
        )
        skills = load_skills(tmp_path)
        assert "test" in skills
        assert "Instructions" in skills["test"]["instructions"]


# ==========================================
# MCP config (sans connexion)
# ==========================================

class TestMcpConfig:
    def test_context7_sans_cle_retourne_none(self, monkeypatch):
        """Sans CONTEXT7_API_KEY, Context7 n'est pas configuré."""
        monkeypatch.delenv("CONTEXT7_API_KEY", raising=False)
        assert mcp_mod.build_context7_params() is None

    def test_context7_avec_cle_construit_config(self, monkeypatch):
        monkeypatch.setenv("CONTEXT7_API_KEY", "test-key-123")
        params = mcp_mod.build_context7_params()
        assert params is not None
        assert params["url"] == "https://mcp.context7.com/mcp"
        assert params["transport"] == "streamable-http"
        assert params["headers"]["CONTEXT7_API_KEY"] == "test-key-123"

    def test_crawl4ai_construit_stdio_params(self):
        params = mcp_mod.build_crawl4ai_params()
        # Si mcp est installé (il l'est via smolagents[mcp]), params doit être non-None
        if mcp_mod.StdioServerParameters is not None:
            assert params is not None
            assert params.command == "uvx"
            assert "crawl4ai-mcp-llm" in params.args
        else:
            assert params is None

    def test_list_mcp_servers_status(self, monkeypatch):
        monkeypatch.delenv("CONTEXT7_API_KEY", raising=False)
        status = mcp_mod.list_mcp_servers_status()
        assert len(status) == 3
        names = {s["name"] for s in status}
        assert names == {"context7", "crawl4ai", "chrome-devtools"}

    def test_connect_mcp_server_none_yields_vide(self):
        """connect_mcp_server avec params=None doit yield [] sans crash."""
        with mcp_mod.connect_mcp_server("test", None) as tools:
            assert tools == []
