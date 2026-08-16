# Tests F-103 — budgets de guidance (port deer-flow check_agent_guidance.py).
#
# scripts/ n'est pas un package importable par défaut (pas de __init__.py) :
# on ajoute la racine du repo à sys.path, même convention que
# tests/test_run_analyzer_discovery.py.

import subprocess
import sys
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_agent_guidance import (  # noqa: E402
    AUDIT_CAVEAT,
    CHAIN_SOFT,
    LOCAL_HARD,
    LOCAL_SOFT,
    MODULE_HARD,
    MODULE_SOFT,
    PRESSURE_DENSITY_PER_KB,
    ROOT_HARD,
    ROOT_SOFT,
    _audit_signal_findings,
    _budget_finding,
    analyze,
    chain_paths,
    default_eager_skills,
    guidance_paths,
    main,
    normalized_utf8_size,
    surface_budget,
)


def git_init(path: Path) -> None:
    subprocess.run(
        ["git", "init"], cwd=path, check=True, capture_output=True
    )

ROOT = PurePosixPath("AGENTS.md")
MODULE = PurePosixPath("graph_orchestrator/prompts.py")
SKILL_CODING = PurePosixPath("skills/coding/SKILL.md")
SKILL_FILE_CREATION = PurePosixPath("skills/file-creation/SKILL.md")


def make_files(**sizes: int) -> dict[PurePosixPath, str]:
    """Contenus factices : chaque fichier rempli de 'a' * size octets."""
    return {PurePosixPath(name): "a" * size for name, size in sizes.items()}


class TestNormalizedUtf8Size:
    def test_crlf_normalize_vers_lf(self):
        # "a\r\n" (3 octets bruts) -> "a\n" (2 octets normalisés).
        assert normalized_utf8_size("a\r\n") == 2

    def test_cr_isole_normalize_vers_lf(self):
        assert normalized_utf8_size("a\rb") == 3

    def test_utf8_multibyte_compte_en_octets(self):
        # "é" = 2 octets UTF-8.
        assert normalized_utf8_size("é") == 2


class TestSurfaceBudget:
    def test_root(self):
        assert surface_budget(ROOT) == (ROOT_SOFT, ROOT_HARD)

    def test_module(self):
        assert surface_budget(MODULE) == (MODULE_SOFT, MODULE_HARD)

    def test_local_skill(self):
        assert surface_budget(SKILL_CODING) == (LOCAL_SOFT, LOCAL_HARD)

    def test_autres_fichiers_hors_budget(self):
        assert surface_budget(PurePosixPath("README.md")) is None
        assert surface_budget(PurePosixPath("skills/coding/resources/x.md")) is None
        assert surface_budget(PurePosixPath("graph_orchestrator/nodes.py")) is None


class TestGuidancePaths:
    def test_filtre_les_surfaces_uniquement(self):
        paths = {
            ROOT,
            MODULE,
            SKILL_CODING,
            PurePosixPath("README.md"),
            PurePosixPath("graph_orchestrator/nodes.py"),
        }
        assert guidance_paths(paths) == {ROOT, MODULE, SKILL_CODING}


class TestBudgetFinding:
    def test_hard_depasse_sans_base_erreur(self):
        finding = _budget_finding(
            code="AG001", path=ROOT, actual=ROOT_HARD + 1, soft=ROOT_SOFT,
            hard=ROOT_HARD, base_actual=None, relevant_change=True, label="AGENTS.md",
        )
        assert finding is not None and finding.severity == "error"

    def test_hard_depasse_et_a_grandi_erreur(self):
        finding = _budget_finding(
            code="AG001", path=ROOT, actual=ROOT_HARD + 10, soft=ROOT_SOFT,
            hard=ROOT_HARD, base_actual=ROOT_HARD + 1, relevant_change=True, label="AGENTS.md",
        )
        assert finding is not None and finding.severity == "error"

    def test_hard_depasse_sans_croissance_fichier_change_warning(self):
        # Sémantique d'adoption deer-flow : au-dessus du hard mais pas grossi
        # + fichier touché dans la PR = warning, pas error.
        finding = _budget_finding(
            code="AG001", path=ROOT, actual=ROOT_HARD + 10, soft=ROOT_SOFT,
            hard=ROOT_HARD, base_actual=ROOT_HARD + 10, relevant_change=True, label="AGENTS.md",
        )
        assert finding is not None and finding.severity == "warning"

    def test_hard_depasse_sans_croissance_fichier_intact_aucun_finding(self):
        finding = _budget_finding(
            code="AG001", path=ROOT, actual=ROOT_HARD + 10, soft=ROOT_SOFT,
            hard=ROOT_HARD, base_actual=ROOT_HARD + 10, relevant_change=False, label="AGENTS.md",
        )
        assert finding is None

    def test_soft_depasse_fichier_change_warning(self):
        finding = _budget_finding(
            code="AG001", path=ROOT, actual=ROOT_SOFT + 1, soft=ROOT_SOFT,
            hard=ROOT_HARD, base_actual=None, relevant_change=True, label="AGENTS.md",
        )
        assert finding is not None and finding.severity == "warning"

    def test_soft_depasse_fichier_intact_aucun_finding(self):
        finding = _budget_finding(
            code="AG001", path=ROOT, actual=ROOT_SOFT + 1, soft=ROOT_SOFT,
            hard=ROOT_HARD, base_actual=None, relevant_change=False, label="AGENTS.md",
        )
        assert finding is None

    def test_sous_soft_aucun_finding(self):
        finding = _budget_finding(
            code="AG001", path=ROOT, actual=ROOT_SOFT, soft=ROOT_SOFT,
            hard=ROOT_HARD, base_actual=None, relevant_change=True, label="AGENTS.md",
        )
        assert finding is None


class TestChainPaths:
    def test_composition_module_plus_eager_presents(self):
        available = {MODULE, SKILL_CODING, SKILL_FILE_CREATION, ROOT}
        chain = chain_paths(["coding", "file-creation", "absent-skill"], available)
        assert chain == [MODULE, SKILL_CODING, SKILL_FILE_CREATION]

    def test_module_absent_chain_vide_ou_skills_seuls(self):
        # Sans prompts.py dans les disponibles, la chaîne se réduit aux skills.
        chain = chain_paths(["coding"], {SKILL_CODING})
        assert chain == [SKILL_CODING]

    def test_eager_skills_defaut_depuis_skills_loader(self):
        # Source de vérité unique : la liste vient de skills_loader, pas d'une copie.
        eager = default_eager_skills()
        assert "coding" in eager and "file-creation" in eager


class TestAnalyze:
    def test_tout_sous_budget_aucun_finding(self):
        files = make_files(**{"AGENTS.md": 1000})
        files[MODULE] = "a" * 1000
        files[SKILL_CODING] = "a" * 1000
        assert analyze(files, eager_skills=["coding"]) == []

    def test_root_au_dessus_hard_sans_base_error(self):
        files = make_files(**{"AGENTS.md": ROOT_HARD + 1})
        findings = analyze(files, eager_skills=[])
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert findings[0].code == "AG001"
        assert findings[0].path == ROOT

    def test_root_au_dessus_hard_incrémental_sans_croissance_warning(self):
        size = ROOT_HARD + 500
        head = make_files(**{"AGENTS.md": size})
        base = make_files(**{"AGENTS.md": size})
        findings = analyze(
            head,
            base_files=base,
            changed_paths={ROOT},
            eager_skills=[],
        )
        assert len(findings) == 1
        assert findings[0].severity == "warning" and findings[0].code == "AG001"

    def test_root_au_dessus_hard_incrémental_avec_croissance_error(self):
        head = make_files(**{"AGENTS.md": ROOT_HARD + 600})
        base = make_files(**{"AGENTS.md": ROOT_HARD + 100})
        findings = analyze(
            head,
            base_files=base,
            changed_paths={ROOT},
            eager_skills=[],
        )
        assert len(findings) == 1
        assert findings[0].severity == "error" and findings[0].code == "AG001"

    def test_soft_ignore_si_fichier_non_touché(self):
        head = make_files(**{"AGENTS.md": ROOT_SOFT + 1})
        findings = analyze(head, changed_paths=set(), eager_skills=[])
        assert findings == []

    def test_chaine_coder_budget(self):
        # Chaîne = module + skills eager. Chaque fichier reste SOUS son budget
        # individuel soft, mais leur somme dépasse le hard de chaîne : seul
        # AG002 se déclenche (2 skills × 40 Ko + module 24 Ko ≈ 104 Ko > 96 Ko).
        module_size = MODULE_SOFT - 576        # < MODULE_SOFT (24 Ko)
        skill_size = LOCAL_SOFT - 960          # < LOCAL_SOFT (40 Ko)
        files = {
            MODULE: "a" * module_size,
            SKILL_CODING: "a" * skill_size,
            SKILL_FILE_CREATION: "a" * skill_size,
        }
        findings = analyze(files, eager_skills=["coding", "file-creation"])
        assert findings != []
        # Aucun finding de fichier individuel (AG001) : chacun sous son soft.
        assert all(f.code != "AG001" for f in findings)
        chain_errors = [f for f in findings if f.code == "AG002"]
        assert len(chain_errors) == 1
        assert chain_errors[0].severity == "error"
        assert chain_errors[0].path == MODULE

    def test_chaine_sous_budget(self):
        files = {MODULE: "a" * 1000, SKILL_CODING: "a" * 1000}
        findings = analyze(files, eager_skills=["coding"])
        assert findings == []

    def test_skill_local_au_dessus_hard(self):
        files = {SKILL_CODING: "a" * (LOCAL_HARD + 1)}
        findings = analyze(files, eager_skills=[])
        assert len(findings) == 1
        assert findings[0].severity == "error" and findings[0].path == SKILL_CODING


class TestAuditSignaux:
    def test_desactive_par_defaut(self):
        # Un texte saturé de pression ne produit RIEN sans --audit-signals.
        saturated = ("NEVER " * 400) + " try to " + ("IMPORTANT " * 200)
        files = {SKILL_CODING: saturated}
        assert analyze(files, eager_skills=[], audit_signals=False) == []

    def test_densite_pression_warning_opt_in(self):
        saturated = "JAMAIS ALWAYS MUST CRITICAL " * 100  # ~1 mot / 6 chars
        findings = _audit_signal_findings(SKILL_CODING, saturated)
        ag101 = [f for f in findings if f.code == "AG101"]
        assert len(ag101) == 1 and ag101[0].severity == "warning"
        assert str(PRESSURE_DENSITY_PER_KB) in ag101[0].message
        assert "prompt-audit" in ag101[0].message

    def test_texte_normal_aucun_signal(self):
        findings = _audit_signal_findings(SKILL_CODING, "Écris du code propre et testé.")
        assert findings == []

    def test_hedge_warning(self):
        findings = _audit_signal_findings(SKILL_CODING, "Inclus un sommaire si possible.")
        ag102 = [f for f in findings if f.code == "AG102"]
        assert len(ag102) == 1 and ag102[0].severity == "warning"
        assert "si possible" in ag102[0].message
        assert AUDIT_CAVEAT.split("(")[0].strip()[:20] in ag102[0].message

    def test_via_analyze_opt_in(self):
        saturated = "TOUJOURS INTERDIT JAMAIS MUST " * 100
        files = {SKILL_CODING: saturated}
        findings = analyze(files, eager_skills=[], audit_signals=True)
        assert any(f.code in ("AG101", "AG102") for f in findings)


class TestMainExitCodes:
    def test_repo_propre_sans_surface_exit_0(self, tmp_path, capsys):
        # Un repo git vide : 0 surface, 0 finding, exit 0.
        git_init(tmp_path)
        assert main(["--repo-root", str(tmp_path)]) == 0
        out = capsys.readouterr().out
        assert "0 surfaces" in out

    def test_repo_avec_surfaces_reelles_exit_agents_md_au_dessus_hard(
        self, tmp_path, capsys
    ):
        # Reproduit l'état du repo : AGENTS.md au-dessus du hard 16 Ko en
        # mode local (sans base) = error -> exit 1.
        git_init(tmp_path)
        (tmp_path / "AGENTS.md").write_text("a" * (ROOT_HARD + 1), encoding="utf-8")
        assert main(["--repo-root", str(tmp_path)]) == 1
        out = capsys.readouterr().out
        assert "AG001" in out and "AGENTS.md" in out

    def test_strict_warnings_exit_1(self, tmp_path):
        git_init(tmp_path)
        # Un skill au-dessus du soft (mais sous le hard) = warning seul.
        (tmp_path / "skills" / "x").mkdir(parents=True)
        (tmp_path / "skills" / "x" / "SKILL.md").write_text(
            "a" * (LOCAL_SOFT + 1), encoding="utf-8"
        )
        assert main(["--repo-root", str(tmp_path)]) == 0
        assert main(["--repo-root", str(tmp_path), "--strict-warnings"]) == 1

    def test_github_annotations_format(self, tmp_path, capsys):
        git_init(tmp_path)
        (tmp_path / "AGENTS.md").write_text("a" * (ROOT_HARD + 1), encoding="utf-8")
        main(["--repo-root", str(tmp_path), "--github-annotations"])
        out = capsys.readouterr().out
        assert "::error file=AGENTS.md,line=1,title=AG001::" in out


class TestIntegrationRepoReel:
    """Discovery réelle en lecture seule sur le repo (léger, non LLM)."""

    def test_surfaces_reelles_decouvertes(self):
        from scripts.check_agent_guidance import _load_worktree_surfaces

        surfaces = _load_worktree_surfaces(REPO_ROOT)
        assert ROOT in surfaces
        assert MODULE in surfaces
        assert SKILL_CODING in surfaces
        assert len([p for p in surfaces if len(p.parts) == 3]) >= 10

    def test_chaine_reelle_sous_budget(self):
        from scripts.check_agent_guidance import _load_worktree_surfaces

        surfaces = _load_worktree_surfaces(REPO_ROOT)
        chain = chain_paths(default_eager_skills(), surfaces)
        assert MODULE in chain and len(chain) == len(default_eager_skills()) + 1
        total = sum(normalized_utf8_size(surfaces[p]) for p in chain)
        assert total < CHAIN_SOFT, (
            f"Chaine Coder {total} octets au-dessus du soft {CHAIN_SOFT}"
        )
