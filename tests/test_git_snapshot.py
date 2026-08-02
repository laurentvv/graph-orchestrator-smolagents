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
