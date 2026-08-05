"""Tests de l'intégration Chrome DevTools MCP (F-45).

Couvre :
  - agent_server/mcp.build_chrome_devtools_params() : construction des params stdio.
  - graph_orchestrator/chrome_devtools_tool.py : context manager + dégradation.
  - graph_orchestrator/vision_callback.py : wrapper screenshot + step_callback.
  - agent_server/mcp.list_mcp_servers_status : diagnostic /health.

Pattern du projet : SYNCHRONE + monkeypatch, AUCUNE connexion réseau réelle (calqué
sur tests/test_context7_tool.py). On mocke au point d'entrée réseau.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock

from PIL import Image

from graph_orchestrator import chrome_devtools_tool, vision_callback
from agent_server import mcp as mcp_module


# ==========================================
# build_chrome_devtools_params (config)
# ==========================================

class TestBuildParams:
    def test_retourne_none_si_desactive(self, monkeypatch):
        """CHROME_DEVTOOLS_ENABLED=0 → None (opt-out global)."""
        monkeypatch.setenv("CHROME_DEVTOOLS_ENABLED", "0")
        assert mcp_module.build_chrome_devtools_params() is None

    def test_retourne_none_si_desactive_variantes(self, monkeypatch):
        """Toutes les formes falsy (0/false/no/off) désactivent."""
        for val in ("false", "no", "off", "0"):
            monkeypatch.setenv("CHROME_DEVTOOLS_ENABLED", val)
            assert mcp_module.build_chrome_devtools_params() is None, f"val={val}"

    def test_retourne_stdio_params_si_active(self, monkeypatch):
        """Activé → StdioServerParameters avec commande npx + chrome-devtools-mcp."""
        monkeypatch.setenv("CHROME_DEVTOOLS_ENABLED", "1")
        monkeypatch.delenv("CHROME_PATH", raising=False)
        monkeypatch.delenv("CHROME_DEVTOOLS_HEADLESS", raising=False)
        params = mcp_module.build_chrome_devtools_params()
        assert params is not None
        assert params.command == "npx"
        # L'arg principal doit contenir chrome-devtools-mcp@latest
        assert any("chrome-devtools-mcp@latest" in a for a in params.args)
        # Options par défaut : isolated + viewport + screenshot-format
        assert "--isolated" in params.args
        assert "1280x800" in params.args
        assert "jpeg" in params.args

    def test_chrome_path_ajoute_executable_path(self, monkeypatch):
        """CHROME_PATH set → ajoute --executable-path <path> aux args."""
        monkeypatch.setenv("CHROME_DEVTOOLS_ENABLED", "1")
        monkeypatch.setenv("CHROME_PATH", "/usr/bin/google-chrome")
        monkeypatch.delenv("CHROME_DEVTOOLS_HEADLESS", raising=False)
        params = mcp_module.build_chrome_devtools_params()
        assert "--executable-path" in params.args
        idx = params.args.index("--executable-path")
        assert params.args[idx + 1] == "/usr/bin/google-chrome"

    def test_headless_ajoute_option(self, monkeypatch):
        """CHROME_DEVTOOLS_HEADLESS=1 → ajoute --headless."""
        monkeypatch.setenv("CHROME_DEVTOOLS_ENABLED", "1")
        monkeypatch.setenv("CHROME_DEVTOOLS_HEADLESS", "1")
        monkeypatch.delenv("CHROME_PATH", raising=False)
        params = mcp_module.build_chrome_devtools_params()
        assert "--headless" in params.args

    def test_headless_absent_par_defaut(self, monkeypatch):
        """Sans CHROME_DEVTOOLS_HEADLESS, pas de --headless (visible pour debug)."""
        monkeypatch.setenv("CHROME_DEVTOOLS_ENABLED", "1")
        monkeypatch.delenv("CHROME_DEVTOOLS_HEADLESS", raising=False)
        params = mcp_module.build_chrome_devtools_params()
        assert "--headless" not in params.args


# ==========================================
# chrome_devtools_tools() — context manager + dégradation
# ==========================================

class TestChromeDevtoolsToolsDegration:
    def test_params_none_yield_liste_vide(self, monkeypatch):
        """Params None (désactivé) → yield [] sans crash, sans réseau."""
        monkeypatch.setattr(chrome_devtools_tool, "_build_params", lambda: None)
        with chrome_devtools_tool.chrome_devtools_tools() as tools:
            assert tools == []

    def test_connexion_echouee_yield_vide(self, monkeypatch):
        """from_mcp lève (réseau down / Chrome absent) → yield [] (pas de crash)."""
        monkeypatch.setattr(chrome_devtools_tool, "_build_params", lambda: {"fake": True})
        monkeypatch.setattr(
            chrome_devtools_tool, "ToolCollection",
            MagicMock(from_mcp=MagicMock(side_effect=ConnectionError("chrome not found"))),
        )
        with chrome_devtools_tool.chrome_devtools_tools() as tools:
            assert tools == []


class TestChromeDevtoolsToolsMocked:
    def test_connexion_ok_yield_outils(self, monkeypatch):
        """Connexion OK → yield la liste des outils MCP."""
        monkeypatch.setattr(chrome_devtools_tool, "_build_params", lambda: {"fake": True})

        fake_nav = MagicMock()
        fake_nav.name = "navigate_page"
        fake_shot = MagicMock()
        fake_shot.name = "take_screenshot"
        fake_collection = MagicMock()
        fake_collection.tools = [fake_nav, fake_shot]

        @contextmanager
        def fake_from_mcp(params, **kwargs):
            yield fake_collection

        monkeypatch.setattr(chrome_devtools_tool, "ToolCollection", MagicMock(from_mcp=fake_from_mcp))

        with chrome_devtools_tool.chrome_devtools_tools() as tools:
            assert len(tools) == 2
            assert {t.name for t in tools} == {"navigate_page", "take_screenshot"}

    def test_click_et_fill_autorises(self, monkeypatch):
        """click/fill ne doivent PAS être filtrés (post-mortem run 123955).

        La doc/skills recommandent click(uid=...) pour tester les interactions, mais
        ces outils étaient exclus par l'allowlist → le Coder/Tester générait click(...)
        que smolagents rejetait ("Forbidden function") 6 fois par run. Ils doivent
        maintenant passer le filtre."""
        monkeypatch.setattr(chrome_devtools_tool, "_build_params", lambda: {"fake": True})

        fake_click = MagicMock()
        fake_click.name = "click"
        fake_fill = MagicMock()
        fake_fill.name = "fill"
        fake_nav = MagicMock()
        fake_nav.name = "navigate_page"
        # Outil volontairement hors allowlist : doit rester filtré
        fake_perf = MagicMock()
        fake_perf.name = "performance_start_trace"
        fake_collection = MagicMock()
        fake_collection.tools = [fake_click, fake_fill, fake_nav, fake_perf]

        @contextmanager
        def fake_from_mcp(params, **kwargs):
            yield fake_collection

        monkeypatch.setattr(chrome_devtools_tool, "ToolCollection", MagicMock(from_mcp=fake_from_mcp))

        with chrome_devtools_tool.chrome_devtools_tools() as tools:
            names = {t.name for t in tools}
            assert "click" in names, "click doit être autorisé (tests d'interaction)"
            assert "fill" in names, "fill doit être autorisé (tests d'interaction)"
            assert "navigate_page" in names
            # Le filtrage strict reste actif sur les autres outils (anti context-overflow)
            assert "performance_start_trace" not in names



# ==========================================
# list_mcp_servers_status (diagnostic /health)
# ==========================================

class TestMcpStatusDiagnostic:
    def test_status_inclut_chrome_devtools(self, monkeypatch):
        """Le diagnostic /health liste chrome-devtools."""
        monkeypatch.setenv("CHROME_DEVTOOLS_ENABLED", "1")
        status = mcp_module.list_mcp_servers_status()
        names = [s["name"] for s in status]
        assert "chrome-devtools" in names

    def test_status_reflete_configuration(self, monkeypatch):
        """Désactivé → configured=False pour chrome-devtools."""
        monkeypatch.setenv("CHROME_DEVTOOLS_ENABLED", "0")
        status = mcp_module.list_mcp_servers_status()
        cdt = next(s for s in status if s["name"] == "chrome-devtools")
        assert cdt["configured"] is False
        assert cdt["transport"] == "stdio"


# ==========================================
# vision_callback — wrapper de capture screenshot
# ==========================================

class TestWrapScreenshotTools:
    def test_wrap_uniquement_les_outils_screenshot(self):
        """Seuls take_screenshot / puppeteer_screenshot sont wrappés, pas les autres."""
        from smolagents import Tool

        class FakeScreenshot(Tool):
            name = "take_screenshot"
            description = "shot"
            inputs = {}
            output_type = "object"
            is_initialized = True
            def forward(self):
                return Image.new("RGB", (2, 2))

        class FakeNav(Tool):
            name = "navigate_page"
            description = "nav"
            inputs = {}
            output_type = "object"
            is_initialized = True
            def forward(self):
                return "ok"

        holder = []
        tools = vision_callback.wrap_screenshot_tools([FakeScreenshot(), FakeNav()], holder)
        assert isinstance(tools[0], vision_callback._ScreenshotCapturingTool)
        assert not isinstance(tools[1], vision_callback._ScreenshotCapturingTool)

    def test_wrap_puppeteer_screenshot_aussi(self):
        """puppeteer_screenshot (Tester) est aussi wrappé."""
        from smolagents import Tool

        class FakePuppet(Tool):
            name = "puppeteer_screenshot"
            description = "puppet shot"
            inputs = {}
            output_type = "object"
            is_initialized = True
            def forward(self):
                return Image.new("RGB", (1, 1))

        holder = []
        tools = vision_callback.wrap_screenshot_tools([FakePuppet()], holder)
        assert isinstance(tools[0], vision_callback._ScreenshotCapturingTool)

    def test_capture_holder_none_pas_de_wrap(self):
        """capture_holder=None → outils intacts (capture désactivée)."""
        from smolagents import Tool

        class FakeShot(Tool):
            name = "take_screenshot"
            description = "shot"
            inputs = {}
            output_type = "object"
            is_initialized = True
            def forward(self):
                return "x"

        tools = vision_callback.wrap_screenshot_tools([FakeShot()], None)
        assert not isinstance(tools[0], vision_callback._ScreenshotCapturingTool)


class TestScreenshotCapture:
    def test_forward_capture_image_pil(self):
        """Le wrapper capture l'image PIL retournée dans le holder."""
        from smolagents import Tool

        class FakeShot(Tool):
            name = "take_screenshot"
            description = "shot"
            inputs = {}
            output_type = "object"
            is_initialized = True
            def forward(self):
                return Image.new("RGB", (3, 3), color=(0, 255, 0))

        holder = []
        wrapped = vision_callback.wrap_screenshot_tools([FakeShot()], holder)[0]
        result = wrapped()
        # L'image est retournée (comportement original préservé)
        assert isinstance(result, Image.Image)
        # ET capturée dans le holder
        assert len(holder) == 1
        assert holder[0].size == (3, 3)

    def test_forward_pas_image_pas_capture(self):
        """Un outil qui retourne du texte n'est pas capturé (même si wrappé par erreur)."""
        from smolagents import Tool

        class FakeShot(Tool):
            name = "take_screenshot"
            description = "shot"
            inputs = {}
            output_type = "object"
            is_initialized = True
            def forward(self):
                return "not an image"

        holder = []
        wrapped = vision_callback.wrap_screenshot_tools([FakeShot()], holder)[0]
        result = wrapped()
        assert result == "not an image"
        assert len(holder) == 0


class TestScreenshotCallback:
    def test_callback_peuple_observations_images(self):
        """Le step_callback pousse le dernier screenshot dans observations_images."""
        holder = [Image.new("RGB", (4, 4))]
        cb = vision_callback.make_screenshot_callback(holder)

        step = MagicMock()
        step.observations_images = None
        cb(step, agent=MagicMock())

        assert step.observations_images is not None
        assert len(step.observations_images) == 1
        assert step.observations_images[0].size == (4, 4)

    def test_callback_reset_holder_apres_push(self):
        """Après le callback, le holder est vidé (pas de fuite au step suivant)."""
        holder = [Image.new("RGB", (2, 2))]
        cb = vision_callback.make_screenshot_callback(holder)
        cb(MagicMock(), agent=MagicMock())
        assert len(holder) == 0

    def test_callback_holder_vide_noop(self):
        """Pas de screenshot ce step → callback ne fait rien (n'écrase pas)."""
        holder = []
        cb = vision_callback.make_screenshot_callback(holder)
        step = MagicMock()
        step.observations_images = None
        cb(step, agent=MagicMock())
        # observations_images reste None (pas d'image à pousser)
        assert step.observations_images is None


# ==========================================
# Coder helpers : _is_web_task + _build_devtools_blocks
# ==========================================

class TestCoderWebDetection:
    def test_is_web_task_par_router_lang(self):
        from graph_orchestrator.nodes import _is_web_task
        assert _is_web_task({"router_lang": "web", "target_files": []}) is True
        assert _is_web_task({"router_lang": "HTML/CSS/JS", "target_files": []}) is True

    def test_is_web_task_par_extension(self):
        from graph_orchestrator.nodes import _is_web_task
        assert _is_web_task({"router_lang": "", "target_files": ["index.html"]}) is True
        assert _is_web_task({"router_lang": "", "target_files": ["style.css"]}) is True
        assert _is_web_task({"router_lang": "", "target_files": ["app/main.js"]}) is True

    def test_is_web_task_false_pour_python(self):
        from graph_orchestrator.nodes import _is_web_task
        assert _is_web_task({"router_lang": "python", "target_files": ["main.py"]}) is False
        assert _is_web_task({"router_lang": "", "target_files": ["script.py"]}) is False

    def test_build_devtools_blocks_vide_sans_outils(self):
        from graph_orchestrator.nodes import _build_devtools_blocks
        pb, td = _build_devtools_blocks({"target_files": ["index.html"]}, [])
        assert pb == "" and td == ""

    def test_build_devtools_blocks_web_avec_outils(self):
        from graph_orchestrator.nodes import _build_devtools_blocks
        pb, td = _build_devtools_blocks(
            {"target_files": ["landing_page/index.html"]}, ["fake_tool"]
        )
        assert "VALIDATION VISUELLE" in pb
        assert "take_screenshot" in pb
        assert "file:///" in pb
        assert "navigate_page" in td

    def test_build_devtools_blocks_python_doc_seule(self):
        """Tâche non-web + outils dispos → doc outils seule (pas de workflow preview)."""
        from graph_orchestrator.nodes import _build_devtools_blocks
        pb, td = _build_devtools_blocks({"target_files": ["main.py"]}, ["fake_tool"])
        assert pb == ""
        assert "navigate_page" in td


# ==========================================
# skills_loader : routage devtools-preview
# ==========================================

class TestSkillRouting:
    def test_devtools_preview_pour_tache_web(self):
        from graph_orchestrator.skills_loader import select_skills_for_coder
        skills = select_skills_for_coder("Crée une landing page responsive HTML5 CSS")
        assert "devtools-preview" in skills

    def test_devtools_preview_absent_pour_python(self):
        from graph_orchestrator.skills_loader import select_skills_for_coder
        skills = select_skills_for_coder("Crée un script python de tri à bulles")
        assert "devtools-preview" not in skills

    def test_skill_body_se_charge(self):
        from graph_orchestrator.skills_loader import load_skill_body
        body = load_skill_body("devtools-preview")
        assert body != ""
        assert "Chrome DevTools" in body or "DevTools" in body
