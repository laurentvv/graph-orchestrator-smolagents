"""Tests F-128 (post-mortem run 2026-08-19_2250) : nudge post-fix console.

Run 2026-08-19_2250 : le 4B corrigeait une erreur console (4 search_replace
chirurgicaux guidés par les stacks R4) mais ne re-testait JAMAIS la page — il
relisait le fichier → jamais la preuve que l'erreur avait disparu → 17 turns de
stall, 2×40 steps épuisés, livrable sain perdu.

Fix : vision_callback maintient « erreurs console vues, pas re-vérifiées » ;
search_replace / multi_replace / edit_file collent une directive post-fix au
retour ; un check console propre lève l'attente.
"""

import pytest

from graph_orchestrator import tools
from graph_orchestrator.tools import edit_file, multi_replace, search_replace
from graph_orchestrator.vision_callback import (
    _CONSOLE_PENDING,
    _enrich_console_output,
    pending_post_fix_directive,
    reset_console_pending,
)


class _FakeDetailTool:
    name = "get_console_message"

    def __call__(self, msgid: int) -> str:
        return (
            "ID: 1\nMessage: error> Uncaught TypeError\n### Stack trace\n"
            "at createPiece (index.html:106:39)\n"
            "Note: line and column numbers use 1-based indexing\n"
        )


_ERR_LIST = (
    "## Console messages\nShowing 1-1 of 1.\n"
    "msgid=1 [error] Uncaught TypeError: Cannot read properties of undefined (0 args)\n"
)
_CLEAN_LIST = "## Console messages\nShowing 0 of 0.\n"


@pytest.fixture(autouse=True)
def _clean():
    reset_console_pending()
    yield
    reset_console_pending()


class TestPendingStateLifecycle:

    def test_initially_no_directive(self):
        assert pending_post_fix_directive() is None

    def test_errors_set_pending_with_hint(self):
        _enrich_console_output(_ERR_LIST, _FakeDetailTool())
        d = pending_post_fix_directive()
        assert d is not None
        assert "navigate_page" in d and "list_console_messages" in d
        assert "createPiece (index.html:106:39)" in d  # hint fraîche

    def test_clean_console_clears_pending(self):
        _enrich_console_output(_ERR_LIST, _FakeDetailTool())
        assert _CONSOLE_PENDING["pending"] is True
        _enrich_console_output(_CLEAN_LIST, _FakeDetailTool())
        assert pending_post_fix_directive() is None

    def test_reset(self):
        _enrich_console_output(_ERR_LIST, _FakeDetailTool())
        reset_console_pending()
        assert pending_post_fix_directive() is None


class TestEditToolsCarryDirective:

    def test_search_replace_appends_directive(self, tmp_path):
        target = tmp_path / "game.js"
        target.write_text("const x = 1;\n", encoding="utf-8")
        _enrich_console_output(_ERR_LIST, _FakeDetailTool())  # erreurs en attente

        out = search_replace(path=str(target), old_string="const x = 1;", new_string="const x = 2;")

        assert out.startswith("Successfully edited")
        assert "PROCHAINE ACTION OBLIGATOIRE" in out
        assert target.read_text(encoding="utf-8") == "const x = 2;\n"  # edit réel

    def test_search_replace_silent_when_no_pending(self, tmp_path):
        target = tmp_path / "game.js"
        target.write_text("const x = 1;\n", encoding="utf-8")
        out = search_replace(path=str(target), old_string="const x = 1;", new_string="const x = 2;")
        assert out == f"Successfully edited {target} via SEARCH/REPLACE."

    def test_multi_replace_appends_directive(self, tmp_path):
        target = tmp_path / "game.js"
        target.write_text("const a = 1;\nconst b = 2;\n", encoding="utf-8")
        _enrich_console_output(_ERR_LIST, _FakeDetailTool())

        out = multi_replace(path=str(target), replacements=[
            {"old_string": "const a = 1;", "new_string": "const a = 10;"},
        ])

        assert "Successfully applied 1/1" in out
        assert "PROCHAINE ACTION OBLIGATOIRE" in out

    def test_edit_file_appends_directive(self, tmp_path):
        target = tmp_path / "game.js"
        target.write_text("const x = 1;\n", encoding="utf-8")
        _enrich_console_output(_ERR_LIST, _FakeDetailTool())

        out = edit_file(path=str(target), old_string="const x = 1;", new_string="const x = 2;")

        assert out.startswith("Successfully updated")
        assert "PROCHAINE ACTION OBLIGATOIRE" in out

    def test_failed_edit_no_directive_noise(self, tmp_path):
        target = tmp_path / "game.js"
        target.write_text("const x = 1;\n", encoding="utf-8")
        _enrich_console_output(_ERR_LIST, _FakeDetailTool())

        out = search_replace(path=str(target), old_string="INEXISTANT", new_string="y")

        assert out.startswith("ERROR")
        assert "PROCHAINE ACTION" not in out  # pas de directive sur un échec
