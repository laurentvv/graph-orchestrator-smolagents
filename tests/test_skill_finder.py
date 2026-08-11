"""Tests F-82 — Skill Finder (logique pure + intégration pipeline F-57).

Couvre : parsing sortie `npx skills find`, gate de confiance (allowlist + marqueurs
skills.sh), extraction de mots-clés déclencheurs → regex dédiée, installation
shell=False args validés, manifeste durable, orchestrateur search_and_install
fail-open, intégration skills_loader (DYNAMIC_SKILL_RULES), @tool wrapper, config.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import pytest

from graph_orchestrator import skill_finder
from graph_orchestrator.skill_finder import (
    SkillHit,
    build_trigger_regex,
    extract_trigger_keywords,
    install_skill,
    is_trusted,
    load_dynamic_manifest,
    parse_skills_find_output,
    parse_trusted_authors,
    refresh_dynamic_rules_in_memory,
    register_installed_skill,
    search_and_install,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
@dataclass
class _FakeProc:
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


# ===========================================================================
# 1. Parsing de la sortie `npx skills find`
# ===========================================================================
class TestParseFindOutput:
    def test_extracts_owner_repo_skill(self):
        out = "found:\n  vercel-labs/skills@ai-sdk-agent-skills — desc\n"
        hits = parse_skills_find_output(out)
        assert len(hits) == 1
        assert (hits[0].owner, hits[0].repo, hits[0].skill) == (
            "vercel-labs", "skills", "ai-sdk-agent-skills",
        )

    def test_strips_ansi_color_codes(self):
        out = "\x1B[32mvercel-labs/skills@react-hooks\x1B[0m safe\n"
        hits = parse_skills_find_output(out)
        assert len(hits) == 1
        assert hits[0].skill == "react-hooks"

    def test_detects_positive_marker(self):
        out = "vercel-labs/skills@foo  [verified]\n"
        hits = parse_skills_find_output(out)
        assert hits[0].positive is True
        assert hits[0].negative is False

    def test_detects_negative_marker(self):
        out = "vercel-labs/skills@foo  deprecated\n"
        hits = parse_skills_find_output(out)
        assert hits[0].negative is True

    def test_multiple_hits_and_empty(self):
        out = (
            "microsoft/skills@bar\n"
            "evil-org/skills@malware unsafe\n"
            "not-a-hit-line\n"
        )
        hits = parse_skills_find_output(out)
        assert {h.owner for h in hits} == {"microsoft", "evil-org"}
        assert parse_skills_find_output("") == []
        assert parse_skills_find_output(None) == []


# ===========================================================================
# 2. Gate de confiance (allowlist + marqueurs skills.sh)
# ===========================================================================
class TestIsTrusted:
    TRUSTED = ["vercel-labs", "microsoft"]

    def test_allowlisted_author_is_trusted(self):
        hit = SkillHit("vercel-labs", "skills", "foo")
        assert is_trusted(hit, self.TRUSTED) is True

    def test_unlisted_author_rejected(self):
        hit = SkillHit("random-org", "skills", "foo", positive=True)
        assert is_trusted(hit, self.TRUSTED) is False

    def test_negative_marker_blocks_even_trusted(self):
        hit = SkillHit("vercel-labs", "skills", "foo", negative=True)
        assert is_trusted(hit, self.TRUSTED) is False

    def test_positive_marker_on_trusted_still_trusted(self):
        hit = SkillHit("microsoft", "skills", "foo", positive=True)
        assert is_trusted(hit, self.TRUSTED) is True

    def test_parse_trusted_authors_csv(self):
        assert parse_trusted_authors("Vercel-Labs, Microsoft ,clerk") == [
            "vercel-labs", "microsoft", "clerk",
        ]
        # défaut quand vide
        assert "vercel-labs" in parse_trusted_authors(None)
        assert "microsoft" in parse_trusted_authors("")


# ===========================================================================
# 3. Mots-clés déclencheurs → regex dédiée (cœur F-82 v2)
# ===========================================================================
class TestTriggerKeywords:
    def test_query_always_first(self):
        kws = extract_trigger_keywords("react hooks for components", "react")
        assert kws[0] == "react"

    def test_stopwords_filtered_from_description(self):
        kws = extract_trigger_keywords(
            "Use this skill with the agent for react components", "react"
        )
        # "use", "this", "skill", "with", "the", "agent", "for" sont stopwordés
        assert "use" not in kws
        assert "the" not in kws
        assert "components" in kws

    def test_hints_merged(self):
        kws = extract_trigger_keywords("desc", "react", hints=["jsx", "hooks"])
        assert "jsx" in kws and "hooks" in kws

    def test_dedup_case_insensitive(self):
        kws = extract_trigger_keywords("React react REACT", "react")
        # un seul 'react'
        assert kws.count("react") == 1

    def test_cap_at_max(self):
        desc = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        kws = extract_trigger_keywords(desc, "query", max_keywords=5)
        assert len(kws) <= 5

    def test_build_regex_form(self):
        rx = build_trigger_regex(["react", "jsx"])
        assert rx == r"\b(react|jsx)\b"
        # doit matcher (insensible à la casse via lower() côté caller)
        import re as _re
        assert _re.search(rx, "i love react today")

    def test_build_regex_escapes_specials(self):
        rx = build_trigger_regex(["c++"])
        assert "c++" not in rx  # le + est échappé
        assert "c\\+\\+" in rx

    def test_build_regex_empty_is_noop(self):
        rx = build_trigger_regex([])
        import re as _re
        assert _re.search(rx, "anything") is None  # ne matche jamais


# ===========================================================================
# 4. Installation : shell=False + args validés (anti-injection F-38/F-26)
# ===========================================================================
class TestInstallSkill:
    def test_valid_hit_calls_subprocess_arglist_noshell(self, monkeypatch):
        calls = []

        def fake_run(cmd, *args, **kwargs):
            calls.append((cmd, kwargs))
            return _FakeProc(returncode=0)

        monkeypatch.setattr(skill_finder.subprocess, "run", fake_run)
        hit = SkillHit("vercel-labs", "skills", "my-skill")
        result = install_skill(hit)

        assert result is not None
        assert result.name == "my-skill"
        assert result.source == "vercel-labs/skills@my-skill"
        # shell=False : jamais shell=True (anti-injection)
        assert calls, "subprocess.run doit être appelé"
        cmd, kwargs = calls[0]
        assert isinstance(cmd, list)  # arg-list, pas string
        assert kwargs.get("shell", False) is False
        # la cible validée passe comme UN seul élément (pas découpé par un shell)
        assert "vercel-labs/skills@my-skill" in cmd

    def test_bad_component_refused_without_subprocess(self, monkeypatch):
        called = {"n": 0}

        def fake_run(cmd, *args, **kwargs):
            called["n"] += 1
            return _FakeProc(returncode=0)

        monkeypatch.setattr(skill_finder.subprocess, "run", fake_run)
        # owner contient un ';' → refusé par validation regex avant subprocess
        hit = SkillHit("owner;evil", "skills", "foo")
        assert install_skill(hit) is None
        assert called["n"] == 0  # aucun subprocess lancé

    def test_install_failure_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            skill_finder.subprocess, "run",
            lambda *a, **k: _FakeProc(returncode=1),
        )
        hit = SkillHit("vercel-labs", "skills", "foo")
        assert install_skill(hit) is None

    def test_install_subprocess_exception_returns_none(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("npx absent")

        monkeypatch.setattr(skill_finder.subprocess, "run", boom)
        hit = SkillHit("vercel-labs", "skills", "foo")
        assert install_skill(hit) is None  # fail-open


# ===========================================================================
# 5. Manifeste durable (lazy summary) — remplace la mutation de source
# ===========================================================================
class TestManifest:
    def test_round_trip_and_idempotent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(skill_finder, "MANIFEST_PATH", str(tmp_path / "installed-skills.json"))
        monkeypatch.setattr(skill_finder, "SKILLS_DIR", str(tmp_path))
        register_installed_skill(
            "react-hooks", "desc react", ["react", "hooks"],
            r"\b(react|hooks)\b", "vercel-labs/skills@react-hooks",
        )
        # 2e appel = upsert (idempotent, 1 seule entrée)
        register_installed_skill(
            "react-hooks", "desc react 2", ["react"],
            r"\b(react)\b", "vercel-labs/skills@react-hooks",
        )
        rules = load_dynamic_manifest()
        assert len(rules) == 1
        assert rules[0] == (r"\b(react)\b", "react-hooks")
        # durable sur disque
        with open(str(tmp_path / "installed-skills.json"), encoding="utf-8") as f:
            data = json.load(f)
        assert data["react-hooks"]["source"] == "vercel-labs/skills@react-hooks"
        assert data["react-hooks"]["triggers"] == ["react"]

    def test_load_missing_manifest_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(skill_finder, "MANIFEST_PATH", str(tmp_path / "nope.json"))
        assert load_dynamic_manifest() == []


# ===========================================================================
# 6. Orchestrateur search_and_install (E2E mocké, fail-open)
# ===========================================================================
class TestSearchAndInstall:
    def test_installs_first_trusted_and_writes_manifest(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(skill_finder, "MANIFEST_PATH", str(tmp_path / "installed-skills.json"))
        monkeypatch.setattr(skill_finder, "SKILLS_DIR", str(tmp_path))
        # empêche la mutation du global skills_loader en test
        monkeypatch.setattr(skill_finder, "refresh_dynamic_rules_in_memory", lambda: 0)

        find_out = "vercel-labs/skills@react-hooks  verified\nrandom/x@y\n"
        add = _FakeProc(returncode=0)

        def fake_cli(args, timeout_s):
            if args and args[0] == "find":
                return _FakeProc(stdout=find_out, returncode=0), None
            if args and args[0] == "add":
                return add, None
            return None, "unknown"

        monkeypatch.setattr(skill_finder, "_run_skills_cli", fake_cli)

        summary = search_and_install("react", settings=None)
        assert "react-hooks" in summary
        assert "installé" in summary or "Skill installé" in summary
        # manifeste écrit avec regex dédiée contenant le mot-clé
        rules = load_dynamic_manifest()
        names = [n for _, n in rules]
        assert "react-hooks" in names
        rx = [p for p, n in rules if n == "react-hooks"][0]
        assert "react" in rx

    def test_untrusted_author_arg_rejected_early(self, monkeypatch):
        called = {"find": 0}

        def fake_cli(args, timeout_s):
            if args and args[0] == "find":
                called["find"] += 1
                return _FakeProc(stdout="", returncode=0), None
            return None, "x"

        monkeypatch.setattr(skill_finder, "_run_skills_cli", fake_cli)
        summary = search_and_install("react", author="evil-org", settings=None)
        assert "allowlist" in summary.lower() or "auteur" in summary.lower()
        # on n'a même pas lancé find (rejet avant)
        assert called["find"] == 0

    def test_no_trusted_hit_returns_none_message(self, monkeypatch):
        monkeypatch.setattr(
            skill_finder, "_run_skills_cli",
            lambda args, timeout_s: (
                _FakeProc(stdout="random/x@y unsafe\n", returncode=0), None
            ),
        )
        summary = search_and_install("obscure", settings=None)
        assert "Aucun" in summary or "aucun" in summary

    def test_invalid_query_rejected(self, monkeypatch):
        summary = search_and_install("ev;il", settings=None)
        assert "Error" in summary or "invalide" in summary

    def test_find_cli_error_fail_open(self, monkeypatch):
        monkeypatch.setattr(
            skill_finder, "_run_skills_cli",
            lambda args, timeout_s: (None, "network down"),
        )
        summary = search_and_install("react", settings=None)
        assert "Error" in summary  # fail-open, ne lève pas


# ===========================================================================
# 7. Intégration skills_loader (DYNAMIC_SKILL_RULES) — pipeline F-57
# ===========================================================================
class TestSkillsLoaderIntegration:
    def test_refresh_registers_manifest_rules_in_memory(
        self, tmp_path, monkeypatch
    ):
        from graph_orchestrator import skills_loader

        monkeypatch.setattr(skill_finder, "MANIFEST_PATH", str(tmp_path / "installed-skills.json"))
        register_installed_skill(
            "zz-dynamic-test", "d", ["zzkw"],
            r"\b(zzkw)\b", "vercel-labs/skills@zz-dynamic-test",
        )
        before = list(skills_loader.DYNAMIC_SKILL_RULES)
        try:
            added = refresh_dynamic_rules_in_memory()
            assert added >= 1
            names = [n for _, n in skills_loader.DYNAMIC_SKILL_RULES]
            assert "zz-dynamic-test" in names
            # 2e appel = idempotent (0 ajout)
            assert refresh_dynamic_rules_in_memory() == 0
        finally:
            # restaure l'état global (anti-fuite entre tests)
            skills_loader.DYNAMIC_SKILL_RULES[:] = before

    def test_dynamic_rule_visible_via_select_skills_for_coder(self, monkeypatch):
        from graph_orchestrator import skills_loader

        before = list(skills_loader.DYNAMIC_SKILL_RULES)
        try:
            skills_loader.DYNAMIC_SKILL_RULES.append((r"\b(uniquekw123)\b", "some-skill"))
            selected = skills_loader.select_skills_for_coder("task about uniquekw123 stuff")
            assert "some-skill" in selected
        finally:
            skills_loader.DYNAMIC_SKILL_RULES[:] = before


# ===========================================================================
# 8. @tool wrapper (tools.py) — délègue à skill_finder.search_and_install
# ===========================================================================
class TestToolWrapper:
    def test_wrapper_delegates_and_never_raises(self, monkeypatch):
        from graph_orchestrator import tools

        captured = {}

        def fake_search(query, author=None, triggers=None, settings=None):
            captured.update(query=query, author=author, triggers=triggers)
            return "ok"

        # Le wrapper fait `from .skill_finder import search_and_install` à chaque
        # appel (lazy) → patcher l'attribut du module skill_finder est vu à l'appel.
        monkeypatch.setattr(skill_finder, "search_and_install", fake_search)
        # .forward est l'entrée utilisée par le ReAct (dspy_nodes._search_skill_wrapper)
        result = tools.search_and_install_skill.forward("react", "vercel-labs", "react,jsx")
        assert result == "ok"
        assert captured["query"] == "react"
        assert captured["author"] == "vercel-labs"
        assert captured["triggers"] == ["react", "jsx"]

    def test_wrapper_triggers_csv_split(self, monkeypatch):
        from graph_orchestrator import tools

        captured = {}

        def fake_search(query, author=None, triggers=None, settings=None):
            captured["triggers"] = triggers
            return "ok"

        monkeypatch.setattr(skill_finder, "search_and_install", fake_search)
        tools.search_and_install_skill.forward("a", None, None)
        assert captured["triggers"] is None


# ===========================================================================
# 9. Config (flag + allowlist) + gate Architect (source-level regression guard)
# ===========================================================================
class TestConfigAndGate:
    def test_skill_finder_enabled_default_true(self, monkeypatch):
        from graph_orchestrator.config import load_settings

        monkeypatch.delenv("SKILL_FINDER_ENABLED", raising=False)
        s = load_settings()
        assert s.skill_finder_enabled is True
        assert "vercel-labs" in s.skill_finder_trusted_authors

    def test_skill_finder_enabled_env_override_false(self, monkeypatch):
        from graph_orchestrator.config import load_settings

        monkeypatch.setenv("SKILL_FINDER_ENABLED", "false")
        s = load_settings()
        assert s.skill_finder_enabled is False

    def test_skill_finder_trusted_authors_override(self, monkeypatch):
        from graph_orchestrator.config import load_settings

        monkeypatch.setenv("SKILL_FINDER_TRUSTED_AUTHORS", "foo,bar")
        s = load_settings()
        assert s.skill_finder_trusted_authors == "foo,bar"

    def test_architect_gate_and_wrapper_triggers_in_source(self):
        # Regression guard : le bloc ReAct F-82 doit être gate par
        # skill_finder_enabled, et le wrapper doit accepter `triggers`.
        import inspect

        from graph_orchestrator import dspy_nodes

        src = inspect.getsource(dspy_nodes.execute_architect_node)
        assert "skill_finder_enabled" in src  # le gate existe
        assert "triggers" in src  # le wrapper propage les hints mots-clés
