"""Tests F-164 — gardes d'écriture portées sur le chemin pydantic + Static Tester.

0 LLM / 0 réseau. Couvre :
  - build_write_guardrail (ToolGuardrail officiel) : F-10 (contenu vide /
    placeholder) et F-126 (anti-réécriture d'un existant > N lignes) en
    ``block`` PRÉ-exécution — le refus devient le résultat outil ; directive
    variables CSS (``replace``) appendée aux résultats d'écriture .css ;
    fail-open total ; câblage INCONDITIONNEL dans build_coder_capabilities.
  - find_undefined_css_vars (extraction pure du refactor) et le check Tier 1
    du Static Tester (« [CSS VARS] », agnostique moteur).
  - la skill frontend-design porte les 2 règles quantitatives F-164.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graph_orchestrator.config import load_settings


def _call(name, **args):
    from pydantic_ai_harness.guardrails import ToolCallInfo

    return ToolCallInfo(name=name, args=args, tool_call_id="c1")


def _result(name, args, result):
    from pydantic_ai_harness.guardrails import ToolResultInfo

    return ToolResultInfo(name=name, args=args, tool_call_id="c1", result=result)


# ============================================================
# build_write_guardrail — guard (pré-exécution)
# ============================================================

class TestWriteGuardrailGuard:
    def _rail(self, max_lines=100):
        import dataclasses

        from graph_orchestrator.coder_pydantic_guards import build_write_guardrail

        settings = dataclasses.replace(load_settings(), coder_writefile_max_lines=max_lines)
        return build_write_guardrail(settings)

    def test_blocks_empty_content(self):
        rail = self._rail()
        verdict = rail.guard(_call("write_file", path="index.html", content=""))
        assert verdict.action == "block"
        assert "EMPTY 'content'" in verdict.message

    def test_blocks_placeholder(self):
        rail = self._rail()
        verdict = rail.guard(_call("write_file", path="a.js", content="TODO"))
        assert verdict.action == "block"
        assert "placeholder" in verdict.message

    def test_blocks_overwrite_of_large_existing_file(self, tmp_path, monkeypatch):
        """F-126 : écraser un existant > max lignes = REFUS + orientation
        chirurgicale — le scénario E2E F-162 (script.js 128 lignes réécrit 2×)."""
        monkeypatch.chdir(tmp_path)
        big = tmp_path / "script.js"
        big.write_text("\n".join(f"line {i}" for i in range(150)), encoding="utf-8")
        rail = self._rail(max_lines=100)
        verdict = rail.guard(_call("write_file", path="script.js", content="x" * 200))
        assert verdict.action == "block"
        assert "150 lignes" in verdict.message
        assert "search_replace" in verdict.message  # orientation chirurgicale

    def test_allows_new_file_and_small_existing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "small.js").write_text("a\nb\n", encoding="utf-8")
        rail = self._rail(max_lines=100)
        assert rail.guard(_call("write_file", path="new.js", content="const a = 1;")).action == "allow"
        assert rail.guard(_call("write_file", path="small.js", content="const ab = 12;")).action == "allow"

    def test_creation_libre_meme_gros_contenu(self, tmp_path, monkeypatch):
        """Parité F-126 : la CRÉATION d'un nouveau fichier reste libre."""
        monkeypatch.chdir(tmp_path)
        rail = self._rail(max_lines=100)
        verdict = rail.guard(_call("write_file", path="fresh.js", content="x" * 5000))
        assert verdict.action == "allow"

    def test_other_tools_pass_through(self):
        rail = self._rail()
        assert rail.guard(_call("search_replace", path="a.js", old_string="x", new_string="y")).action == "allow"
        assert rail.guard(_call("read_file", path="a.js")).action == "allow"

    def test_missing_content_blocks(self):
        """write_file sans content = contenu vide → block pédagogique F-10."""
        rail = self._rail()
        assert rail.guard(_call("write_file")).action == "block"

    def test_blocks_narrow_fixed_width_css_content(self):
        """Boucle runs 2-4 : `.bar{width:30px}` récidive 3/4 malgré skill ET
        directive soft ignorée → blocage PRÉ-exécution sur le contenu proposé
        (le fichier n'est pas écrit, le refus porte le fix flex:1)."""
        rail = self._rail()
        verdict = rail.guard(_call(
            "write_file", path="styles.css",
            content=".board{display:flex}\n.bar{width:30px;min-width:30px}\n",
        ))
        assert verdict.action == "block"
        assert "flex: 1" in verdict.message and "N'A PAS été écrit" in verdict.message

    def test_flex_css_and_badge_pass(self):
        rail = self._rail()
        assert rail.guard(_call("write_file", path="styles.css",
                                content=".bar{flex:1}")).action == "allow"
        assert rail.guard(_call("write_file", path="styles.css",
                                content=".badge{width:24px}")).action == "allow"

    def test_flex_with_narrow_max_width_cap_blocked(self):
        """Run 5 : le modèle obéit à la lettre (flex:1) en gardant le cap
        max-width:40px — 10 barres × 40 px = 49 % vide mesuré. Le cap défait
        le flex → blocage ; min-width seul est bénin."""
        rail = self._rail()
        verdict = rail.guard(_call(
            "write_file", path="styles.css",
            content=".board{display:flex}\n.bar{flex:1;min-width:24px;max-width:40px}\n",
        ))
        assert verdict.action == "block"
        assert "max-width" in verdict.message
        # min-width seul (sans cap, sans width fixe) : allow
        assert rail.guard(_call(
            "write_file", path="styles.css",
            content=".board{display:flex}\n.bar{flex:1;min-width:24px}\n",
        )).action == "allow"

    def test_failopen_on_internal_error(self, monkeypatch, tmp_path):
        """Une exception interne (ex : OS malade) ne doit JAMAIS bloquer une
        écriture légitime — fail-open total, parité gardes tools.py."""
        import graph_orchestrator.coder_pydantic_guards as cpg

        rail = self._rail()

        def _boom(p):
            raise RuntimeError("OS malade")

        monkeypatch.setattr(cpg.os.path, "exists", _boom)
        verdict = rail.guard(_call("write_file", path="x.js", content="const a = 1;"))
        assert verdict.action == "allow"


# ============================================================
# build_write_guardrail — result_guard (post-exécution, .css)
# ============================================================

class TestWriteGuardrailResultGuard:
    def _rail(self):
        from graph_orchestrator.coder_pydantic_guards import build_write_guardrail

        return build_write_guardrail(load_settings())

    def test_css_write_with_undefined_vars_gets_directive(self, tmp_path, monkeypatch):
        """Le livrable E2E F-162 (var(--font-body) indéfinie) aurait reçu la
        directive :root prête à coller dans le résultat de son écriture."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "styles.css").write_text(
            ":root { --bg: #111; }\nbody { font-family: var(--font-body), system-ui; }\n",
            encoding="utf-8",
        )
        (tmp_path / "index.html").write_text("<html><body>x</body></html>", encoding="utf-8")
        rail = self._rail()
        verdict = rail.result_guard(
            _result("write_file", {"path": "styles.css"}, "Successfully wrote to styles.css")
        )
        assert verdict.action == "replace"
        assert "VARIABLES CSS INDÉFINIES" in verdict.replacement
        assert "--font-body" in verdict.replacement

    def test_clean_css_untouched(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "styles.css").write_text(
            ":root { --bg: #111; --font-body: system-ui; }\nbody { font-family: var(--font-body); }\n",
            encoding="utf-8",
        )
        rail = self._rail()
        verdict = rail.result_guard(
            _result("write_file", {"path": "styles.css"}, "Successfully wrote to styles.css")
        )
        assert verdict.action == "allow"

    def test_non_css_and_non_write_untouched(self):
        rail = self._rail()
        assert rail.result_guard(_result("write_file", {"path": "a.js"}, "ok")).action == "allow"
        assert rail.result_guard(_result("read_file", {"path": "a.css"}, "ok")).action == "allow"

    def test_failopen_non_string_result(self):
        rail = self._rail()
        assert rail.result_guard(_result("write_file", {"path": "a.css"}, None)).action == "allow"


# ============================================================
# Câblage — INCONDITIONNEL (garde de sécurité, hors toggle gardes)
# ============================================================

class TestWiring:
    def test_guardrail_present_guards_on_and_off(self):
        from pydantic_ai_harness import ToolGuardrail

        import dataclasses

        from graph_orchestrator.coder_pydantic import build_coder_capabilities

        settings = dataclasses.replace(load_settings(), coder_pydantic_guards=False)
        task = {"id": "t", "content": "c", "target_files": ["index.html"], "iteration": 1}
        for s in (load_settings(), settings):
            caps = build_coder_capabilities(task, s, guards=getattr(s, "coder_pydantic_guards", True))
            assert any(isinstance(c, ToolGuardrail) for c in caps), (
                "la garde d'écriture doit être présente même guards=false (sécurité)"
            )


# ============================================================
# Static Tester Tier 1 — [CSS VARS] (agnostique moteur)
# ============================================================

class TestStaticTesterCssVars:
    def _html(self, tmp_path):
        html = """<!DOCTYPE html><html><head><link rel="stylesheet" href="styles.css">
</head><body><button id="b">go</button><script>
document.getElementById('b').addEventListener('click', () => {});
</script></body></html>"""
        (tmp_path / "index.html").write_text(html, encoding="utf-8")

    def test_undefined_vars_flagged(self, tmp_path, monkeypatch):
        from graph_orchestrator.static_tester import static_check_html

        monkeypatch.chdir(tmp_path)
        self._html(tmp_path)
        (tmp_path / "styles.css").write_text(
            ":root { --bg: #111; }\nbody { font-family: var(--font-body), system-ui; }\n",
            encoding="utf-8",
        )
        res = static_check_html("index.html", run_devtools=False)
        css_errors = [e for e in res.errors if e.startswith("[CSS VARS]")]
        assert css_errors and "--font-body" in css_errors[0]
        assert res.is_valid is False

    def test_defined_vars_pass(self, tmp_path, monkeypatch):
        from graph_orchestrator.static_tester import static_check_html

        monkeypatch.chdir(tmp_path)
        self._html(tmp_path)
        (tmp_path / "styles.css").write_text(
            ":root { --bg: #111; --font-body: system-ui; }\nbody { font-family: var(--font-body); }\n",
            encoding="utf-8",
        )
        res = static_check_html("index.html", run_devtools=False)
        assert not [e for e in res.errors if e.startswith("[CSS VARS]")]

    def test_inline_style_sibling_no_false_positive(self, tmp_path, monkeypatch):
        """Anti-FP cross-fichiers : la var définie en <style> inline du HTML
        ne doit pas être flaggée (parité avec la garde tools.py)."""
        from graph_orchestrator.static_tester import static_check_html

        monkeypatch.chdir(tmp_path)
        html = """<!DOCTYPE html><html><head><link rel="stylesheet" href="styles.css">
<style>:root { --font-body: system-ui; }</style></head><body><script>
'use strict';</script></body></html>"""
        (tmp_path / "index.html").write_text(html, encoding="utf-8")
        (tmp_path / "styles.css").write_text(
            "body { font-family: var(--font-body); }\n", encoding="utf-8"
        )
        res = static_check_html("index.html", run_devtools=False)
        assert not [e for e in res.errors if e.startswith("[CSS VARS]")]


# ============================================================
# Directive REMPLISSAGE (narrow_fixed_width_directive — runs 2-3 de la boucle)
# ============================================================

class TestNarrowFixedWidthDirective:
    def test_bar_fixed_width_flagged_with_fix(self, tmp_path, monkeypatch):
        """Le pattern récidive des runs 2-3 (`.bar { width: 30px }`) reçoit le
        diagnostic + le correctif flex: 1 prêt à coller."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "styles.css").write_text(
            ".board { display: flex; }\n.bar { width: 30px; min-width: 30px; }\n",
            encoding="utf-8",
        )
        from graph_orchestrator.tools import narrow_fixed_width_directive

        d = narrow_fixed_width_directive("styles.css")
        assert ".bar (width: 30px)" in d and "flex: 1" in d

    def test_legit_small_elements_and_flex_spared(self, tmp_path, monkeypatch):
        """badge/dot/icon légitimement petits + barres flex:1 → silence."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "styles.css").write_text(
            ".board { display: flex; }\n.bar { flex: 1; }\n"
            ".badge { width: 24px; }\n.dot { width: 8px; }\n",
            encoding="utf-8",
        )
        from graph_orchestrator.tools import narrow_fixed_width_directive

        assert narrow_fixed_width_directive("styles.css") == ""

    def test_result_guard_carries_fill_directive(self, tmp_path, monkeypatch):
        """Le result_guard du ToolGuardrail transporte AUSSI la directive
        remplissage (canal résultat outil, miroir var() CSS)."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "styles.css").write_text(
            ":root { --bg: #111; }\n.bar { width: 30px; }\n", encoding="utf-8"
        )
        (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
        import dataclasses

        from graph_orchestrator.coder_pydantic_guards import build_write_guardrail

        rail = build_write_guardrail(load_settings())
        verdict = rail.result_guard(
            _result("write_file", {"path": "styles.css"}, "Successfully wrote to styles.css")
        )
        assert verdict.action == "replace"
        assert "LARGEUR FIXE ÉTROITE" in verdict.replacement


# ============================================================
# Skill frontend-design — règles quantitatives F-164
# ============================================================

class TestSkillRules:
    def test_filling_and_var_rules_present(self):
        skill = open(
            os.path.join(os.path.dirname(__file__), "..", "skills", "frontend-design", "SKILL.md"),
            encoding="utf-8",
        ).read()
        assert "REMPLISSAGE" in skill and "flex: 1" in skill
        assert "max-width" in skill  # interdit étroit sur les éléments de données
        assert "DANS les parenthèses" in skill and "var(--font-body, system-ui)" in skill
