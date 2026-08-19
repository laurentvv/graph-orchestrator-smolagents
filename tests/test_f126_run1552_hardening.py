"""Tests F-126 (post-mortem run 2026-08-19_1552, Tetris) : durcissements Coder.

Run 2026-08-19_1552 (`logs/run_coding_2026-08-19_155243/run_full.log`) : le 4B
« corrigeait » un bug local (merge() d'index.html itérait ROWS sur une matrice
shape 2-4 lignes) en réécrivant TOUT le fichier (600+ lignes, 3 fois, ~15 min de
prefill/passe) → contexte inondé → 400 exceed_context_size (54 115 > 49 152) →
run perdu ("Coder crash"). Le gate screenshot F-109 a par ailleurs produit un
faux négatif (« PAS utilisé take_screenshot » alors que le screenshot avait été
pris à l'étape 7 du retry 3) car il scannait une mémoire purgée. Fixes testés :

R1. write_file REFUSE d'écraser un fichier EXISTANT de plus de N lignes
    (CODER_WRITEFILE_MAX_LINES, défaut 100) — la correction est chirurgicale.
R2. Contexte serveur Coder 65536 + KV q8_0 (config .env — test du setting voisin
    coder_writefile_max_lines seulement, les flags serveur se valident via
    debug/bench_prefill_flags.py).
R3. Preuve durable de screenshot (tools._SCREENSHOT_PROOF, marquée à l'exécution
    par vision_callback) — la gate F-109 ne dépend plus de agent.memory.steps.
R4. list_console_messages enrichi des stack traces (get_console_message) avec
    directive read_file ciblée fichier:ligne.
"""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from graph_orchestrator import tools
from graph_orchestrator.config import load_settings, settings
from graph_orchestrator.models import CoderOutput
from graph_orchestrator.tools import (
    mark_screenshot_taken,
    reset_screenshot_proof,
    screenshot_was_taken,
    write_file,
)
from graph_orchestrator.vision_callback import (
    _ConsoleEnrichingTool,
    _enrich_console_output,
    _mark_screenshot_proof,
    wrap_console_enrichment,
)


@pytest.fixture(autouse=True)
def _clean_proof_state():
    reset_screenshot_proof()
    tools.reset_visual_audit()
    yield
    reset_screenshot_proof()
    tools.reset_visual_audit()


# ==========================================
# Config — CODER_WRITEFILE_MAX_LINES
# ==========================================

class TestWriteFileMaxLinesConfig:
    def test_default_is_100(self, monkeypatch):
        monkeypatch.delenv("CODER_WRITEFILE_MAX_LINES", raising=False)
        assert load_settings().coder_writefile_max_lines == 100

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("CODER_WRITEFILE_MAX_LINES", "250")
        assert load_settings().coder_writefile_max_lines == 250

    def test_zero_disables(self, monkeypatch):
        monkeypatch.setenv("CODER_WRITEFILE_MAX_LINES", "0")
        assert load_settings().coder_writefile_max_lines == 0


# ==========================================
# R1 — garde anti-réécriture totale de write_file
# ==========================================

class TestWriteFileRewriteGuard:

    def test_big_existing_file_refused(self, tmp_path):
        """Fichier existant de 150 lignes → REFUS pédagogique, contenu intact."""
        target = tmp_path / "index.html"
        original = "\n".join(f"line {i}" for i in range(1, 151)) + "\n"
        target.write_text(original, encoding="utf-8")

        out = write_file(path=str(target), content=original + "EXTRA\n")

        assert out.startswith("REFUS")
        assert "150" in out and "100" in out
        assert "search_replace" in out
        assert target.read_text(encoding="utf-8") == original  # inchangé

    def test_small_existing_file_allowed(self, tmp_path):
        """Fichier existant de 50 lignes (≤ seuil) → écrasement autorisé."""
        target = tmp_path / "small.js"
        target.write_text("\n".join(f"l{i}" for i in range(50)) + "\n", encoding="utf-8")

        out = write_file(path=str(target), content="// nouveau contenu valide\n")

        assert out.startswith("Successfully wrote")
        assert "// nouveau contenu valide" in target.read_text(encoding="utf-8")

    def test_new_big_file_allowed(self, tmp_path):
        """CRÉATION d'un gros fichier (inexistant) → toujours autorisée."""
        target = tmp_path / "new_index.html"
        content = "<html>\n" + "\n".join(f"<!-- ligne {i} -->" for i in range(1, 300)) + "\n</html>\n"

        out = write_file(path=str(target), content=content)

        assert out.startswith("Successfully wrote")
        assert target.exists()

    def test_threshold_respected_from_settings(self, tmp_path, monkeypatch):
        """Seuil lu dans settings : 50 → un fichier de 60 lignes est refusé."""
        monkeypatch.setattr(
            "graph_orchestrator.config.settings",
            replace(settings, coder_writefile_max_lines=50),
        )
        target = tmp_path / "sixty.css"
        target.write_text("\n".join(f"r{i} {{}}" for i in range(60)) + "\n", encoding="utf-8")

        out = write_file(path=str(target), content="body { color: red; }\n")

        assert out.startswith("REFUS")

    def test_zero_disables_guard(self, tmp_path, monkeypatch):
        """CODER_WRITEFILE_MAX_LINES=0 → garde inactive (opt-out A/B)."""
        monkeypatch.setattr(
            "graph_orchestrator.config.settings",
            replace(settings, coder_writefile_max_lines=0),
        )
        target = tmp_path / "big.txt"
        target.write_text("\n".join(f"l{i}" for i in range(500)) + "\n", encoding="utf-8")

        out = write_file(path=str(target), content="contenu de remplacement entièrement nouveau, non HTML.\n" * 3)

        assert out.startswith("Successfully wrote")


# ==========================================
# R3 — preuve durable de screenshot
# ==========================================

class TestScreenshotProof:

    def test_lifecycle(self):
        assert not screenshot_was_taken()
        mark_screenshot_taken()
        assert screenshot_was_taken()
        reset_screenshot_proof()
        assert not screenshot_was_taken()

    def test_mark_on_success_text(self):
        """Texte de succès (« Took a screenshot. ») → preuve marquée."""
        _mark_screenshot_proof("take_screenshot", "Took a screenshot.")
        assert screenshot_was_taken()

    def test_mark_on_pil_image(self):
        import PIL.Image

        img = PIL.Image.new("RGB", (2, 2))
        _mark_screenshot_proof("take_screenshot", img)
        assert screenshot_was_taken()

    def test_no_mark_on_error_text(self):
        """Erreur outil (timeout / access denied) → PAS une preuve d'audit visuel."""
        _mark_screenshot_proof("take_screenshot", "Error: Page.captureScreenshot timed out.")
        assert not screenshot_was_taken()
        _mark_screenshot_proof("take_screenshot", "Access denied for write")
        assert not screenshot_was_taken()

    def test_no_mark_for_non_screenshot_tools(self):
        """take_snapshot (a11y texte) / navigate_page ne prouvent pas un audit visuel."""
        import PIL.Image

        _mark_screenshot_proof("take_snapshot", "arbre a11y")
        _mark_screenshot_proof("navigate_page", "navigated")
        _mark_screenshot_proof("take_screenshot", PIL.Image.new("RGB", (1, 1)))  # contrôle positif
        reset_screenshot_proof()
        _mark_screenshot_proof("navigate_page", "navigated")
        assert not screenshot_was_taken()


# ==========================================
# R3-bis — gate F-109 via run_with_retry (régression run 1552)
# ==========================================

def _make_gate_agent(steps=None):
    """Agent CodeAgent factice dont le dict tools expose take_screenshot (gate active)."""
    agent = MagicMock()
    agent.name = "coder_test"
    agent.model = MagicMock(model_id="test-model")
    agent.memory = SimpleNamespace(steps=steps or [])  # mémoire PURGÉE (run 1552)
    fake_shot = SimpleNamespace(name="take_screenshot")
    agent.tools = {"take_screenshot": fake_shot}
    return agent


@pytest.mark.anyio
async def test_gate_accepts_durable_proof_after_memory_purge():
    """Régression run 1552 : screenshot PRIS puis mémoire purgée → gate doit PASSER.

    L'ancien scan agent.memory.steps (vide ici) refusait à tort final_answer ;
    le flag durable posé à l'exécution (vision_callback) doit suffire.
    """
    from graph_orchestrator.nodes import run_with_retry

    agent = _make_gate_agent(steps=[])  # mémoire vide = pire cas de l'ancien scan
    validated_output = CoderOutput(
        task_id="t1", status="success", details="ok", linter_ok=True, vision_ok=True
    )

    def agent_run_side_effect(prompt, **kwargs):
        rr = MagicMock()
        rr.output = "final_answer({'task_id': 't1', 'status': 'success', 'details': 'ok'})"
        rr.timing = MagicMock(duration=0.1)
        rr.token_usage = MagicMock(input_tokens=1, output_tokens=1)
        return rr

    agent.run = agent_run_side_effect
    mark_screenshot_taken()  # preuve durable posée pendant le run

    async def thread_wrapper(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=thread_wrapper):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=validated_output):
            result, _metrics = await run_with_retry(
                agent, "PROMPT", CoderOutput, max_retries=1, node_kind="coder"
            )

    assert result is validated_output


@pytest.mark.anyio
async def test_gate_still_refuses_without_any_proof():
    """Sans preuve durable NI trace mémoire → refus (comportement F-109 conservé)."""
    from graph_orchestrator.nodes import run_with_retry

    agent = _make_gate_agent(steps=[])
    validated_output = CoderOutput(
        task_id="t2", status="success", details="ok", linter_ok=True, vision_ok=True
    )

    def agent_run_side_effect(prompt, **kwargs):
        rr = MagicMock()
        rr.output = "final_answer({'task_id': 't2', 'status': 'success', 'details': 'ok'})"
        rr.timing = MagicMock(duration=0.1)
        rr.token_usage = MagicMock(input_tokens=1, output_tokens=1)
        return rr

    agent.run = agent_run_side_effect
    # pas de mark_screenshot_taken() : aucune preuve

    async def thread_wrapper(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch("graph_orchestrator.nodes.asyncio.to_thread", new=thread_wrapper):
        with patch("graph_orchestrator.nodes.extract_and_validate", return_value=validated_output):
            result, _metrics = await run_with_retry(
                agent, "PROMPT", CoderOutput, max_retries=1, node_kind="coder"
            )

    assert result is None  # refusé → pas de sortie validée


# ==========================================
# R4 — enrichment des erreurs console
# ==========================================

_LIST_OUTPUT = (
    "## Console messages\nShowing 1-2 of 2 (Page 1 of 1).\n"
    "msgid=1 [error] Uncaught TypeError: Cannot read properties of undefined (reading '4') (0 args)\n"
    "msgid=2 [warning] dépréciation quelconque (0 args)\n"
)

_DETAIL_OUTPUT = (
    "ID: 1\n"
    "Message: error> Uncaught TypeError: Cannot read properties of undefined (reading '4')\n"
    "### Stack trace\n"
    "at isCollision (index.html:352:58)\n"
    "at playerReset (index.html:588:17)\n"
    "at init (index.html:622:13)\n"
    "Note: line and column numbers use 1-based indexing\n"
)


class _FakeDetailTool:
    name = "get_console_message"

    def __call__(self, msgid: int) -> str:
        return _DETAIL_OUTPUT


class TestConsoleEnrichment:

    def test_error_enriched_with_stack_and_directive(self):
        out = _enrich_console_output(_LIST_OUTPUT, _FakeDetailTool())
        assert "at isCollision (index.html:352:58)" in out
        assert "read_file" in out and "offset=344" in out  # ligne 352 - 8
        assert "search_replace" in out
        assert "NE réécris PAS tout le fichier" in out

    def test_no_errors_unchanged(self):
        clean = "## Console messages\nShowing 0 of 0.\n"
        assert _enrich_console_output(clean, _FakeDetailTool()) == clean

    def test_no_detail_tool_unchanged(self):
        assert _enrich_console_output(_LIST_OUTPUT, None) == _LIST_OUTPUT

    def test_detail_without_stack_unchanged(self):
        class _NoStack:
            def __call__(self, msgid: int) -> str:
                return "ID: 1\nMessage: error> x\n"

        assert _enrich_console_output(_LIST_OUTPUT, _NoStack()) == _LIST_OUTPUT

    def test_too_many_errors_truncated(self):
        many = "## Console messages\n" + "\n".join(
            f"msgid={i} [error] boom {i} (0 args)" for i in range(1, 8)
        )
        out = _enrich_console_output(many, _FakeDetailTool())
        assert "+3 erreur(s) non détaillée(s)" in out  # 7 erreurs - 4 détaillées

    def test_wrapper_delegates_and_enriches(self):
        class _FakeListTool:
            name = "list_console_messages"
            description = "liste"
            inputs = {}
            output_type = "string"

            def forward(self, *args, **kwargs):
                return _LIST_OUTPUT

        wrapped = _ConsoleEnrichingTool(_FakeListTool(), _FakeDetailTool())
        assert wrapped.name == "list_console_messages"  # identité préservée
        out = str(wrapped.forward())
        assert "at isCollision (index.html:352:58)" in out


class TestWrapConsoleEnrichment:

    def _fake_tools(self):
        class _T:
            def __init__(self, name):
                self.name = name
                self.description = name
                self.inputs = {}
                self.output_type = "string"

            def forward(self, *a, **k):
                return "ok"

        return [_T("navigate_page"), _T("list_console_messages"), _T("get_console_message")]

    def test_list_tool_wrapped_others_intact(self):
        tools_list = wrap_console_enrichment(self._fake_tools())
        names = [t.name for t in tools_list]
        assert names == ["navigate_page", "list_console_messages", "get_console_message"]
        assert isinstance(tools_list[1], _ConsoleEnrichingTool)
        assert not isinstance(tools_list[0], _ConsoleEnrichingTool)

    def test_no_detail_tool_no_wrap(self):
        fake = self._fake_tools()[:2]  # sans get_console_message
        result = wrap_console_enrichment(fake)
        assert all(not isinstance(t, _ConsoleEnrichingTool) for t in result)
