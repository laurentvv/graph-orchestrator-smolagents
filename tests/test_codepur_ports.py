"""Tests des ports « code pur » P1/P3/P5/P6/P7 (session focus 2026-08-20).

P1/F-136 : valideur HTML monofichier (port OpenKB deck/validator).
P3/F-137 : cascade search/replace — stratégie lignes vides internes (aider).
P5/F-138 : moniteur Jaccard des résultats d'outils (deer-flow tool_progress).
P6/F-139 : heal_selector (Scrapling retrieve_similar, JS).
P7/F-140 : reaper de process orphelins (qm process-reaper).
"""

import json

import pytest

from graph_orchestrator.html_validator import validate_html_monofile
from graph_orchestrator.search_replace_utils import replace_most_similar_chunk
from graph_orchestrator.tool_progress import (
    ToolProgressMonitor,
    dominant_action_tool,
    jaccard,
    word_set,
)


# ==========================================
# P1 — Valideur HTML monofichier
# ==========================================

VALID_PAGE = """<!DOCTYPE html>
<html><head><title>Jeu</title></head>
<body>
  <canvas id="board"></canvas>
  <div id="hud">Score <span id="score">0</span></div>
  <script>
    const board = document.getElementById('board');
    const score = document.getElementById('score');
    function loop() { requestAnimationFrame(loop); }
    loop();
  </script>
</body></html>
"""


class TestHtmlValidator:
    def test_page_saine_passe(self, tmp_path):
        p = tmp_path / "index.html"
        p.write_text(VALID_PAGE, encoding="utf-8")
        res = validate_html_monofile(str(p))
        assert res.ok, res.errors
        assert not res.warnings or all("canvas" not in w for w in res.warnings)

    def test_ressource_externe_refusee(self, tmp_path):
        p = tmp_path / "index.html"
        p.write_text(
            '<html><head><link href="https://cdn.example.com/x.css"></head>'
            '<script src="https://cdn.example.com/x.js"></script></html>',
            encoding="utf-8",
        )
        res = validate_html_monofile(str(p))
        assert not res.ok
        assert any("link href" in e for e in res.errors)
        assert any("script src" in e for e in res.errors)

    def test_script_src_local_aussi_signale(self, tmp_path):
        """Le livrable attendu est MONOfichier : même un src local est signalé."""
        p = tmp_path / "index.html"
        p.write_text('<html><script src="game.js"></script></html>', encoding="utf-8")
        res = validate_html_monofile(str(p))
        assert not res.ok

    def test_id_duplique(self, tmp_path):
        p = tmp_path / "index.html"
        p.write_text('<html><body><div id="a"></div><div id="A"></div></body></html>',
                     encoding="utf-8")
        res = validate_html_monofile(str(p))
        assert any("dupliqué" in e for e in res.errors)

    def test_getelementbyid_sans_id_dans_dom(self, tmp_path):
        p = tmp_path / "index.html"
        p.write_text(
            "<html><body><div id='x'></div><script>"
            "document.getElementById('y').textContent = '1';"
            "</script></body></html>",
            encoding="utf-8",
        )
        res = validate_html_monofile(str(p))
        assert any("'y'" in e and "getElementById" in e for e in res.errors)

    def test_raf_sans_canvas_warning(self, tmp_path):
        p = tmp_path / "index.html"
        p.write_text(
            "<html><script>function l(){requestAnimationFrame(l)}l()</script></html>",
            encoding="utf-8",
        )
        res = validate_html_monofile(str(p))
        assert res.ok  # warning, pas erreur
        assert any("canvas" in w for w in res.warnings)

    def test_fichier_absent_erreur(self, tmp_path):
        res = validate_html_monofile(str(tmp_path / "absent.html"))
        assert not res.ok

    def test_taille_bornee(self, tmp_path):
        p = tmp_path / "big.html"
        p.write_text("<html>" + "x" * (2 * 1024 * 1024 + 10) + "</html>", encoding="utf-8")
        res = validate_html_monofile(str(p))
        assert any("hors bornes" in e for e in res.errors)


# ==========================================
# P3 — Cascade search/replace : lignes vides internes
# ==========================================

class TestBlankLinesStrategy:
    def test_lignes_vides_integrees_dans_search(self):
        """Le SEARCH contient des lignes vides parasites absentes du fichier."""
        whole = "def foo():\n    a = 1\n    b = 2\n    return a + b\n"
        part = "def foo():\n\n    a = 1\n\n    b = 2\n"  # vides parasites
        replace = "def foo():\n    a = 10\n    b = 2\n"
        out = replace_most_similar_chunk(whole, part, replace)
        assert out is not None
        assert "a = 10" in out

    def test_match_exact_prioritaire_inchange(self):
        whole = "l1\nl2\nl3\n"
        out = replace_most_similar_chunk(whole, "l2", "X")
        assert out is not None and "X" in out


# ==========================================
# P5 — Moniteur Jaccard des résultats
# ==========================================

class TestToolProgress:
    def test_word_set_et_jaccard(self):
        a = word_set("const score = 100; const level = 2;")
        b = word_set("const score = 100; const level = 3;")
        c = word_set("complètement différent navigate page canvas")
        assert jaccard(a, b) > 0.8
        assert jaccard(a, c) < 0.3
        assert jaccard(word_set(""), word_set("")) == 1.0

    def test_sterile_streak_declenche_nudge(self):
        m = ToolProgressMonitor(threshold=0.8, streak=3)
        text = "ERROR: the 'old_string' block was NOT found in the file (even with tolerant matching). Closest lines: function lockPiece()"
        assert m.record("search_replace", text) is None
        assert m.record("search_replace", text.replace("lockPiece", "lockPiece2")) is None  # quasi identique
        nudge = m.record("search_replace", text)  # 3e
        assert nudge is not None and "RÉSULTATS EN BOUCLE" in nudge

    def test_resultat_different_reset(self):
        m = ToolProgressMonitor(threshold=0.8, streak=3)
        m.record("write_file", "aaa bbb ccc ddd eee")
        m.record("write_file", "aaa bbb ccc ddd eee")
        # Un résultat RADICALEMENT différent reset la série.
        m.record("write_file", "zzz yyy xxx www vvv uuu ttt")
        assert m.record("write_file", "zzz yyy xxx www vvv uuu ttt") is None  # série = 2

    def test_dominant_action_tool(self):
        assert dominant_action_tool('search_replace(path="x", old_string=r"""a""")') == "search_replace"
        assert dominant_action_tool('c = read_file(path="x")') is None  # observationnel
        assert dominant_action_tool("") is None


# ==========================================
# P6 — heal_selector (JS, testé au niveau construction)
# ==========================================

class TestHealSelectorTool:
    def test_construction_fail_open(self):
        from graph_orchestrator.devtools_dom_tools import build_devtools_helper_tools

        assert build_devtools_helper_tools([]) == []

    def test_outil_expose_signature_coherente(self):
        from graph_orchestrator.devtools_dom_tools import DevToolsHealSelectorTool

        t = DevToolsHealSelectorTool.__dict__
        assert DevToolsHealSelectorTool.name == "heal_selector"
        assert "tag" in DevToolsHealSelectorTool.inputs
        assert DevToolsHealSelectorTool.inputs["attr_hint"].get("nullable") is True

    def test_delegue_a_evaluate_avec_args(self):
        from graph_orchestrator.devtools_dom_tools import DevToolsHealSelectorTool

        class _FakeEval:
            name = "evaluate_script"
            description = "fake"
            inputs = {}
            output_type = "string"

            def __init__(self):
                self.calls = []

            def __call__(self, **kwargs):
                self.calls.append(kwargs)
                return '{"found": true}'

        fake = _FakeEval()
        tool = DevToolsHealSelectorTool(fake)
        tool.forward(tag="button", text_hint="Start", attr_hint="class=btn")
        assert len(fake.calls) == 1
        assert fake.calls[0]["args"] == ["button", "Start", "class=btn"]
        assert "score" in fake.calls[0]["function"]


# ==========================================
# P7 — Reaper de process orphelins
# ==========================================

class TestProcessReaper:
    def test_register_unregister_cycle(self, tmp_path, monkeypatch):
        from graph_orchestrator import process_reaper as pr

        monkeypatch.setattr(pr, "_REGISTRY_PATH", str(tmp_path / "reg.json"))
        pr.register_process(424242, "llama-server", "port=1 model=test")
        reg = json.load(open(tmp_path / "reg.json", encoding="utf-8"))
        assert "424242" in reg
        pr.unregister_process(424242)
        reg = json.load(open(tmp_path / "reg.json", encoding="utf-8"))
        assert "424242" not in reg

    def test_reap_purge_les_morts_sans_tuer(self, tmp_path, monkeypatch):
        from graph_orchestrator import process_reaper as pr

        monkeypatch.setattr(pr, "_REGISTRY_PATH", str(tmp_path / "reg.json"))
        pr.register_process(999999999, "llama-server", "mort")
        actions = pr.reap_orphans()
        # PID inexistant → purge silencieuse, pas d'action REAPED.
        assert all("REAPED pid=999999999" not in a for a in actions)

    def test_reap_epargne_keep_pids(self, tmp_path, monkeypatch):
        from graph_orchestrator import process_reaper as pr

        monkeypatch.setattr(pr, "_REGISTRY_PATH", str(tmp_path / "reg.json"))
        pid = 12345
        pr.register_process(pid, "llama-server", "test")
        killed = []
        monkeypatch.setattr(pr, "_kill_tree", lambda p: killed.append(p) or True)
        monkeypatch.setattr(pr, "_pid_alive", lambda p: True)
        actions = pr.reap_orphans(keep_pids={pid})
        assert killed == []  # épargné
        # Sans keep : tué et purgé.
        actions = pr.reap_orphans()
        assert killed == [pid]
        assert any(f"pid={pid}" in a for a in actions)


# ==========================================
# F-141 (post-mortem run 2026-08-20_1817)
# ==========================================

class TestPlanSanity:
    def _mk(self, plan, sub=None):
        from types import SimpleNamespace

        return SimpleNamespace(global_architecture=plan, subtasks=sub or [])

    def test_plan_aberrant_200x80_detecte(self):
        from graph_orchestrator.workflows import _plan_sanity_violations

        plan = ("Single-file autonomous Tetris game. Canvas-based rendering (200x80 grid "
                "cells, 30px each = 6000x2400px playable area) with CSS overlay for HUD.")
        v = _plan_sanity_violations(self._mk(plan))
        assert any("grille 200x80" in x for x in v)
        assert any("6000x2400" in x for x in v)

    def test_plan_standard_passe(self):
        from graph_orchestrator.workflows import _plan_sanity_violations

        plan = ("Canvas 10x20 grid, 32px cells = 320x640px, responsive via CSS max-width. "
                "1920x1080 layout dashboard acceptable.")
        assert _plan_sanity_violations(self._mk(plan)) == []

    def test_grande_dimension_sans_mot_grid_passe(self):
        """1920x1080 sans contexte grid/cell = layout légitime, pas de violation."""
        from graph_orchestrator.workflows import _plan_sanity_violations

        assert _plan_sanity_violations(self._mk("layout 3840x2160 retina")) == []

    def test_subtasks_sont_scannees_aussi(self):
        from graph_orchestrator.workflows import _plan_sanity_violations

        v = _plan_sanity_violations(self._mk("plan ok", [{"strategy": "grid 300x150 cells game"}]))
        assert any("300x150" in x for x in v)


class TestIdenticalReadGate:
    def test_troisieme_lecture_identique_refusee(self, tmp_path):
        from graph_orchestrator.tools import read_file, reset_read_supply

        reset_read_supply()
        p = tmp_path / "index.html"
        p.write_text("ligne %d\n" * 100 % tuple(range(100)), encoding="utf-8")
        r1 = read_file(path=str(p), offset=50, limit=10)
        r2 = read_file(path=str(p), offset=50, limit=10)
        assert "garde lectures identiques" not in r1
        assert "garde lectures identiques" not in r2
        r3 = read_file(path=str(p), offset=50, limit=10)
        assert "garde lectures identiques" in r3
        assert "AGIS" in r3
        # Le refus ne lit PAS le fichier : persister ne grossit plus le contexte.
        r4 = read_file(path=str(p), offset=50, limit=10)
        assert "garde lectures identiques" in r4

    def test_offsets_differents_libres(self, tmp_path):
        from graph_orchestrator.tools import read_file, reset_read_supply

        reset_read_supply()
        p = tmp_path / "game.js"
        p.write_text("code %d\n" * 60 % tuple(range(60)), encoding="utf-8")
        for off in (0, 10, 20, 0, 10, 20):  # chaque offset vu 2 fois seulement
            r = read_file(path=str(p), offset=off, limit=5)
            assert "garde lectures identiques" not in r

    def test_reset_repart_de_zero(self, tmp_path):
        from graph_orchestrator.tools import read_file, reset_read_supply

        reset_read_supply()
        p = tmp_path / "a.js"
        p.write_text("x\n" * 30, encoding="utf-8")
        read_file(path=str(p), offset=5, limit=5)
        read_file(path=str(p), offset=5, limit=5)
        reset_read_supply()
        r = read_file(path=str(p), offset=5, limit=5)
        assert "garde lectures identiques" not in r

    def test_write_resets_identical_read_gate_for_file(self, tmp_path):
        """Après une écriture réussie (mark_write_done), relire le fichier est autorisé."""
        from graph_orchestrator.tools import mark_write_done, read_file, reset_read_supply

        reset_read_supply()
        p = tmp_path / "modified.js"
        p.write_text("v1\n" * 30, encoding="utf-8")
        read_file(path=str(p), offset=0, limit=10)
        read_file(path=str(p), offset=0, limit=10)
        r3 = read_file(path=str(p), offset=0, limit=10)
        assert "garde lectures identiques" in r3

        # Le fichier est modifié et marqué via mark_write_done
        p.write_text("v2-updated\n" * 30, encoding="utf-8")
        mark_write_done(str(p))

        # Relire le fichier modifié n'est plus bloqué
        r_after = read_file(path=str(p), offset=0, limit=10)
        assert "garde lectures identiques" not in r_after
        assert "v2-updated" in r_after


class TestTargetedBudget:
    def test_targeted_max_steps_releve(self):
        from graph_orchestrator.targeted_retest import TARGETED_MAX_STEPS

        assert TARGETED_MAX_STEPS == 16
