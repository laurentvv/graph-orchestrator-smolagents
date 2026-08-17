"""Tests du git local de suivi des modifications du Coder (F-48).

Valide init_run_git, commit_iteration, get_last_diff, has_git_history, et la
propagation du diff au Tester via build_targeted_retest_block(git_diff=...).

Utilise un dossier temporaire (tmp_path fixture) avec un vrai git local — pas de mock,
car git_snapshot wrap subprocess et on veut valider le comportement réel.
"""

import pytest

from graph_orchestrator.git_snapshot import (
    init_run_git,
    commit_iteration,
    get_last_diff,
    has_git_history,
)
from graph_orchestrator.targeted_retest import build_targeted_retest_block


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """Crée un dossier temporaire avec git init, chdir dedans."""
    monkeypatch.chdir(tmp_path)
    assert init_run_git() is True
    return tmp_path


class TestInitRunGit:
    def test_init_cree_git(self, git_repo):
        """init_run_git crée bien un .git."""
        assert (git_repo / ".git").is_dir()

    def test_init_idempotent(self, git_repo):
        """Re-appeler init_run_git ne casse rien (déjà initialisé)."""
        assert init_run_git() is True


class TestCommitAndGetDiff:
    def test_iter_1_pas_de_diff(self, git_repo):
        """Itération 1 (commit initial) → pas de diff (création, rien à comparer)."""
        (git_repo / "index.html").write_text("<html>v1</html>")
        assert commit_iteration(1) is True
        assert has_git_history() is False
        assert get_last_diff() == ""

    def test_iter_2_diff_extrait(self, git_repo):
        """Itération 2 → diff contient les lignes modifiées."""
        (git_repo / "index.html").write_text("<html>v1</html>")
        commit_iteration(1)
        # Modification
        (git_repo / "index.html").write_text("<html>v2<p>added</p></html>")
        commit_iteration(2)
        assert has_git_history() is True
        diff = get_last_diff()
        assert diff != ""
        assert "added" in diff  # la ligne ajoutée est dans le diff

    def test_diff_vide_si_rien_modifie(self, git_repo):
        """Si iter 2 ne modifie rien, diff est vide (--allow-empty commit)."""
        (git_repo / "index.html").write_text("<html>v1</html>")
        commit_iteration(1)
        commit_iteration(2)  # rien changé
        # has_git_history est True (2 commits) mais diff vide
        diff = get_last_diff()
        assert diff == ""

    def test_nouveau_fichier_apparait_dans_diff(self, git_repo):
        """Ajout d'un nouveau fichier (ex: style.css) apparaît dans le diff."""
        (git_repo / "index.html").write_text("<html>v1</html>")
        commit_iteration(1)
        (git_repo / "style.css").write_text("body { color: red; }")
        commit_iteration(2)
        diff = get_last_diff()
        assert "style.css" in diff
        assert "color: red" in diff


class TestDiffTruncation:
    def test_diff_tronque_au_plafond(self, git_repo):
        """Un diff énorme est tronqué avec marqueur [...]."""
        (git_repo / "big.txt").write_text("v1\n")
        commit_iteration(1)
        # Génère un énorme changement
        (git_repo / "big.txt").write_text("v2\n" + "x" * 10000 + "\n")
        commit_iteration(2)
        diff = get_last_diff(max_chars=500)
        assert len(diff) <= 600  # ~500 + marges
        assert "[... diff tronqué]" in diff


class TestRobustesse:
    def test_get_last_diff_sans_git(self, tmp_path, monkeypatch):
        """Pas de .git → get_last_diff retourne '' (pas de crash)."""
        monkeypatch.chdir(tmp_path)
        assert get_last_diff() == ""
        assert has_git_history() is False

    def test_commit_sans_git_retourne_false(self, tmp_path, monkeypatch):
        """commit_iteration sans .git → False (pas de crash)."""
        monkeypatch.chdir(tmp_path)
        assert commit_iteration(1) is False


class TestIsolationRobustesse:
    """F-53 (fix pollution repo principal) : isolation cwd-indépendante + garde défensive.

    Contexte : un run E2E a créé un commit vide « Iteration 1 » dans le repo principal
    (reflog 9e860af, droppé ensuite). Le code reposait sur _run_git(cwd=None) qui hérite
    du cwd process, sans garde vérifiant que le repo découvert EST bien le run dir.
    Fix : param ``repo_path`` explicite (cwd-indépendant) + garde ``show-toplevel`` qui
    refuse tout commit vers un repo parent. Publication du run dir jamais polluée.
    """

    def test_init_with_explicit_repo_path(self, tmp_path, monkeypatch):
        """init_run_git(repo_path=...) crée .git dans run_dir SANS chdir (cwd ailleurs)."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        monkeypatch.chdir(tmp_path)  # cwd volontairement ailleurs
        assert init_run_git(repo_path=str(run_dir)) is True
        assert (run_dir / ".git").is_dir()
        # Le cwd (tmp_path) ne doit PAS recevoir un .git par erreur
        assert not (tmp_path / ".git").exists()

    def test_commit_with_explicit_repo_path_from_other_cwd(self, tmp_path, monkeypatch):
        """commit_iteration(repo_path=...) opère sur run_dir même si le cwd process est ailleurs."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        monkeypatch.chdir(tmp_path)  # cwd ≠ run_dir
        assert init_run_git(repo_path=str(run_dir)) is True
        (run_dir / "index.html").write_text("<html>v1</html>")
        assert commit_iteration(1, repo_path=str(run_dir)) is True
        # Le commit atterrit dans run_dir ; le parent (cwd) reste vierge de .git
        assert (run_dir / ".git").is_dir()
        assert not (tmp_path / ".git").exists()

    def test_get_last_diff_with_explicit_repo_path(self, tmp_path, monkeypatch):
        """get_last_diff(repo_path=...) extrait le diff cwd-indépendamment."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        init_run_git(repo_path=str(run_dir))
        (run_dir / "f.txt").write_text("v1\n")
        commit_iteration(1, repo_path=str(run_dir))
        (run_dir / "f.txt").write_text("v2-added\n")
        commit_iteration(2, repo_path=str(run_dir))
        diff = get_last_diff(repo_path=str(run_dir))
        assert "v2-added" in diff

    def test_has_git_history_with_explicit_repo_path(self, tmp_path, monkeypatch):
        """has_git_history(repo_path=...) reflète l'état du run_dir cwd-indépendamment."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        init_run_git(repo_path=str(run_dir))
        (run_dir / "f.txt").write_text("v1")
        commit_iteration(1, repo_path=str(run_dir))
        assert has_git_history(repo_path=str(run_dir)) is False  # 1 commit
        commit_iteration(2, repo_path=str(run_dir))
        assert has_git_history(repo_path=str(run_dir)) is True  # 2 commits

    def test_commit_refuses_parent_repo_pollution(self, tmp_path, monkeypatch):
        """GARDE DÉFENSIVE (cœur du fix F-53) : si run_dir n'a pas de .git propre, git
        découvrirait le repo parent. commit_iteration(repo_path=run_dir) DOIT refuser
        (False) et NE PAS créer de commit dans le parent."""
        import subprocess
        # Parent repo = simule le repo principal
        parent = tmp_path / "main_repo"
        parent.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(parent), check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=str(parent), check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=str(parent), check=True)
        (parent / "README").write_text("base")
        subprocess.run(["git", "add", "-A"], cwd=str(parent), check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=str(parent), check=True)
        head_before = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(parent),
            capture_output=True, text=True, check=True,
        ).stdout.strip()

        # run_dir = sous-dossier du parent SANS .git propre (simule l'échec d'isolation)
        run_dir = parent / "runs" / "foo"
        run_dir.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)  # cwd ailleurs

        # commit_iteration DOIT refuser (run_dir n'est pas un repo isolé)
        assert commit_iteration(1, repo_path=str(run_dir)) is False

        # AUCUN nouveau commit dans le parent → pas de pollution
        head_after = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(parent),
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert head_before == head_after, "POLLUTION : un commit a atterri dans le repo parent !"

    def test_init_isolation_verified_after_init(self, tmp_path, monkeypatch):
        """init_run_git(repo_path) garantit que le repo créé est isolé (toplevel == run_dir)."""
        import os as _os
        import subprocess
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        assert init_run_git(repo_path=str(run_dir)) is True
        toplevel = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=str(run_dir),
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        norm = lambda p: _os.path.normpath(_os.path.normcase(p))
        assert norm(toplevel) == norm(str(run_dir))


class TestTargetedRetestWithDiff:
    def test_bloc_contient_diff_quand_fourni(self):
        """build_targeted_retest_block injecte le diff git dans le prompt."""
        block = build_targeted_retest_block(
            "compteur manquant", iteration=2, git_diff="+<p id='counter'>0</p>"
        )
        assert "Zones EXACTES modifiées" in block
        assert "git diff" in block.lower()
        assert "<p id='counter'>0</p>" in block
        assert "concentre tes assertions" in block

    def test_bloc_sans_diff_pas_de_section_diff(self):
        """Sans git_diff, la section diff est absente (iter 1 ou git indispo)."""
        block = build_targeted_retest_block("bug", iteration=2, git_diff="")
        assert "Zones EXACTES modifiées" not in block
        # mais le reste du prompt ciblé est bien là
        assert "RE-TEST CIBLÉ" in block

    def test_bloc_mentionne_elements_rendus(self):
        """Le bloc inclut l'étape evaluate_script (vérif éléments rendus, bug CSS)."""
        block = build_targeted_retest_block("bug", iteration=2)
        assert "evaluate_script" in block
        assert "length > 0" in block or "querySelectorAll" in block


class TestFsTxExclusion:
    """F-95 : le namespace transactionnel (.fs_tx/) ne pollue ni git status,
    ni les commits, ni le worktree (exclusion via .git/info/exclude, PAS via
    un .gitignore qui apparaîtrait lui-même comme fichier ajouté)."""

    def test_fs_tx_absent_du_git_status(self, git_repo):
        lock = git_repo / ".fs_tx" / "dir.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text("", encoding="utf-8")
        import subprocess

        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=git_repo, capture_output=True, text=True
        ).stdout
        assert ".fs_tx" not in status
        assert status.strip() == ""  # worktree propre : le lock est invisible

    def test_exclusion_idempotent_et_sans_gitignore_worktree(self, git_repo):
        assert init_run_git() is True  # re-init : n'ajoute pas la ligne 2 fois
        exclude = git_repo / ".git" / "info" / "exclude"
        assert exclude.read_text(encoding="utf-8").count(".fs_tx/") == 1
        assert (git_repo / ".gitignore").exists() is False  # pas de pollution worktree

    def test_commit_n_inclut_pas_fs_tx(self, git_repo):
        (git_repo / "index.html").write_text("<html>v1</html>")
        lock = git_repo / ".fs_tx" / "dir.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text("", encoding="utf-8")
        assert commit_iteration(1) is True
        import subprocess

        tracked = subprocess.run(
            ["git", "ls-files"], cwd=git_repo, capture_output=True, text=True
        ).stdout
        assert ".fs_tx" not in tracked
        assert "index.html" in tracked
