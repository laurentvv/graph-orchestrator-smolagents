"""Tests des checkpoints git par itération Coder (F-102, port open-swe).

Valide le mécanisme SANS contamination du worktree (scratch GIT_INDEX_FILE +
update-ref refs/graph-orchestrator/turns/<key>), la sémantique de reprise (une
ref existante n'est jamais avancée), le diff structuré (numstat + name-status +
contenus base/head), la garde d'isolation F-53 (anti-pollution repo parent) et
l'intégration avec le bloc Judge (build_judge_code_block).

Utilise un dossier temporaire (tmp_path) avec un VRAI git local — pas de mock,
même doctrine que test_git_snapshot.py : on wrap subprocess, on veut valider le
comportement réel (surtout la non-contamination de l'index/HEAD/worktree).
"""

import subprocess

import pytest

from graph_orchestrator.git_snapshot import commit_iteration, get_last_diff, init_run_git
from graph_orchestrator.judge_diff import build_judge_code_block
from graph_orchestrator.turn_checkpoint import (
    _MAX_FILES,
    _TURNS_NS,
    build_diff_files,
    checkpoint_ref,
    parse_name_status,
    parse_numstat,
    read_turn_diff,
    record_turn_checkpoint,
    summarize_turn_diff,
)


def _git(args, cwd):
    """Helper test : git brut, échoue le test si la commande plante."""
    r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, f"git {args} → {r.returncode}: {r.stderr}"
    return r.stdout


@pytest.fixture
def git_repo(tmp_path):
    """Run dir temporaire avec le git local F-53 initialisé (chemin de production)."""
    assert init_run_git(repo_path=str(tmp_path)) is True
    return tmp_path


# ==========================================
# checkpoint_ref — sanitization + namespace
# ==========================================

class TestCheckpointRef:
    def test_namespace_et_cle_simple(self):
        assert checkpoint_ref("st1-iter1") == f"{_TURNS_NS}/st1-iter1"

    def test_caracteres_unsafe_remplaces(self):
        assert checkpoint_ref("a/b c:d?*") == f"{_TURNS_NS}/a-b-c-d--"

    def test_cap_100_caracteres(self):
        ref = checkpoint_ref("x" * 250)
        assert ref == f"{_TURNS_NS}/{'x' * 100}"
        assert len(ref) == len(_TURNS_NS) + 1 + 100


# ==========================================
# record_turn_checkpoint — snapshot sans contamination
# ==========================================

class TestRecordTurnCheckpoint:
    def test_cree_la_ref_et_la_retourne(self, git_repo):
        (git_repo / "index.html").write_text("<html>v0</html>", encoding="utf-8")
        ref = record_turn_checkpoint("st1-iter1", repo_path=str(git_repo))
        assert ref == f"{_TURNS_NS}/st1-iter1"
        # La ref existe réellement dans la base d'objets.
        _git(["rev-parse", "--verify", ref], cwd=git_repo)

    def test_head_et_historique_inchanges(self, git_repo):
        """Le snapshot ne crée AUCUN commit : HEAD et rev-list inchangés."""
        (git_repo / "a.txt").write_text("v0", encoding="utf-8")
        assert commit_iteration(1, repo_path=str(git_repo)) is True
        head_before = _git(["rev-parse", "HEAD"], cwd=git_repo)
        count_before = _git(["rev-list", "--count", "HEAD"], cwd=git_repo)
        (git_repo / "b.txt").write_text("nouveau", encoding="utf-8")
        record_turn_checkpoint("st1-iter2", repo_path=str(git_repo))
        assert _git(["rev-parse", "HEAD"], cwd=git_repo) == head_before
        assert _git(["rev-list", "--count", "HEAD"], cwd=git_repo) == count_before

    def test_index_reel_non_contamine(self, git_repo):
        """Le scratch index n'écrit PAS dans le vrai index : un fichier untracked
        reste untracked (?? dans git status) après le snapshot."""
        (git_repo / "nouveau.html").write_text("<p>x</p>", encoding="utf-8")
        record_turn_checkpoint("st1-iter1", repo_path=str(git_repo))
        status = _git(["status", "--porcelain"], cwd=git_repo)
        assert status.strip() == "?? nouveau.html"

    def test_repo_sans_commit_snapshot_racine(self, git_repo):
        """Run vide (aucun commit F-53) : read-tree --empty, commit-tree sans parent."""
        (git_repo / "index.html").write_text("<html></html>", encoding="utf-8")
        ref = record_turn_checkpoint("st1-iter1", repo_path=str(git_repo))
        assert ref is not None
        _git(["rev-parse", "--verify", ref], cwd=git_repo)

    def test_reprise_ref_existante_jamais_avancee(self, git_repo):
        """Invariant « earliest wins » (merge_checkpoint réf) encodé au niveau de la
        ref : un replay après crash NE DOIT PAS faire glisser la base du tour."""
        (git_repo / "a.txt").write_text("etat-initial", encoding="utf-8")
        ref = record_turn_checkpoint("st1-iter2", repo_path=str(git_repo))
        sha1 = _git(["rev-parse", ref], cwd=git_repo)
        # Crash → replay : le Coder a déjà écrit entre-temps.
        (git_repo / "b.txt").write_text("modif-post-crash", encoding="utf-8")
        (git_repo / "a.txt").write_text("etat-modifie", encoding="utf-8")
        ref2 = record_turn_checkpoint("st1-iter2", repo_path=str(git_repo))
        assert ref2 == ref
        assert _git(["rev-parse", ref], cwd=git_repo) == sha1

    def test_sans_git_dir_retourne_none(self, tmp_path):
        """Dossier sans .git (git absent du run) → None silencieux, jamais d'exception."""
        assert record_turn_checkpoint("k", repo_path=str(tmp_path)) is None

    def test_sous_dossier_d_un_repo_parent_aucune_pollution(self, git_repo):
        """Garde F-53 : un repo_path qui découvrirait le repo PARENT ne crée NI ref
        NI objet dans le parent (anti-pollution repo principal)."""
        child = git_repo / "sub"
        child.mkdir()
        assert record_turn_checkpoint("k", repo_path=str(child)) is None
        refs = _git(["for-each-ref", _TURNS_NS], cwd=git_repo)
        assert refs.strip() == ""


# ==========================================
# Parseurs purs — ports fidèles de la référence
# ==========================================

class TestParsers:
    def test_parse_numstat(self):
        raw = "3\t1\tindex.html\0-\t-\tlogo.png\0"
        assert parse_numstat(raw) == [("index.html", 3, 1), ("logo.png", None, None)]

    def test_parse_numstat_ignore_fragments_vides(self):
        assert parse_numstat("") == []
        assert parse_numstat("\0\0") == []

    def test_parse_name_status(self):
        # Format réel de ``git diff --name-status -z`` : paires statut\0path\0.
        raw = "A\0new.css\0M\0index.html\0D\0old.js\0"
        parsed = parse_name_status(raw)
        assert parsed == {"new.css": "added", "index.html": "modified", "old.js": "removed"}

    def test_build_diff_files_sans_contenus(self):
        files = build_diff_files("2\t0\tstyles.css\0", "A\0styles.css\0", None)
        assert files == [{
            "path": "styles.css",
            "previousPath": None,
            "status": "added",
            "additions": 2,
            "deletions": 0,
            "originalContent": None,
            "modifiedContent": None,
            "unrenderable": False,
        }]

    def test_build_diff_files_binaire_unrenderable(self):
        files = build_diff_files("-\t-\timg.png\0", "M\0img.png\0", None)
        assert files[0]["unrenderable"] is True


# ==========================================
# read_turn_diff — diff structuré best-effort
# ==========================================

class TestReadTurnDiff:
    def test_ready_avec_statuts_et_comptes(self, git_repo):
        """base = ref du tour, head=None → worktree vivant : added/modified/removed."""
        (git_repo / "index.html").write_text("ligne1\nligne2\n", encoding="utf-8")
        (git_repo / "old.js").write_text("a=1\n", encoding="utf-8")
        base = record_turn_checkpoint("st1-iter1", repo_path=str(git_repo))
        # Le Coder « travaille » : modifie, ajoute, supprime.
        (git_repo / "index.html").write_text("ligne1\nligne2\nligne3\n", encoding="utf-8")
        (git_repo / "styles.css").write_text("body{}\n", encoding="utf-8")
        (git_repo / "old.js").unlink()
        diff = read_turn_diff(base, repo_path=str(git_repo))
        assert diff["status"] == "ready"
        assert diff["truncated"] is False
        by_path = {f["path"]: f for f in diff["files"]}
        assert by_path["index.html"]["status"] == "modified"
        assert by_path["index.html"]["additions"] == 1
        assert by_path["styles.css"]["status"] == "added"
        assert by_path["old.js"]["status"] == "removed"

    def test_contenus_base_head_decodes(self, git_repo):
        (git_repo / "a.txt").write_text("avant\n", encoding="utf-8")
        base = record_turn_checkpoint("st1-iter1", repo_path=str(git_repo))
        (git_repo / "a.txt").write_text("avant\napres\n", encoding="utf-8")
        diff = read_turn_diff(base, repo_path=str(git_repo))
        f = {x["path"]: x for x in diff["files"]}["a.txt"]
        assert f["originalContent"] == "avant\n"
        assert f["modifiedContent"] == "avant\napres\n"

    def test_contenu_base_absent_pour_fichier_cree(self, git_repo):
        base = record_turn_checkpoint("st1-iter1", repo_path=str(git_repo))
        (git_repo / "nouveau.txt").write_text("hello\n", encoding="utf-8")
        diff = read_turn_diff(base, repo_path=str(git_repo))
        f = {x["path"]: x for x in diff["files"]}["nouveau.txt"]
        assert f["originalContent"] is None
        assert f["modifiedContent"] == "hello\n"

    def test_entre_deux_refs(self, git_repo):
        """head explicite = une autre ref (diff entre deux snapshots du tour)."""
        (git_repo / "a.txt").write_text("v0\n", encoding="utf-8")
        r1 = record_turn_checkpoint("st1-iter1", repo_path=str(git_repo))
        (git_repo / "a.txt").write_text("v0\nv1\n", encoding="utf-8")
        r2 = record_turn_checkpoint("st1-iter1-bis", repo_path=str(git_repo))
        diff = read_turn_diff(r1, head=r2, repo_path=str(git_repo))
        assert diff["status"] == "ready"
        assert {x["path"]: x for x in diff["files"]}["a.txt"]["additions"] == 1

    def test_include_contents_false_economise_cat_file(self, git_repo):
        (git_repo / "a.txt").write_text("v0\n", encoding="utf-8")
        base = record_turn_checkpoint("st1-iter1", repo_path=str(git_repo))
        (git_repo / "a.txt").write_text("v0\nv1\n", encoding="utf-8")
        diff = read_turn_diff(base, repo_path=str(git_repo), include_contents=False)
        f = {x["path"]: x for x in diff["files"]}["a.txt"]
        assert f["originalContent"] is None
        assert f["modifiedContent"] is None
        assert f["additions"] == 1  # numstat intact : seul cat-file est sauté

    def test_base_inconnue_status_missing(self, git_repo):
        diff = read_turn_diff(f"{_TURNS_NS}/inexistant", repo_path=str(git_repo))
        assert diff["status"] == "missing"
        assert diff["files"] == []

    def test_sans_git_dir_status_error(self, tmp_path):
        diff = read_turn_diff("HEAD", repo_path=str(tmp_path))
        assert diff["status"] == "error"

    def test_binaire_unrenderable(self, git_repo):
        (git_repo / "img.bin").write_bytes(b"\xff\xfe\x00\x01binary")
        base = record_turn_checkpoint("st1-iter1", repo_path=str(git_repo))
        (git_repo / "img.bin").write_bytes(b"\xff\xfe\x00\x02binary2")
        diff = read_turn_diff(base, repo_path=str(git_repo))
        f = {x["path"]: x for x in diff["files"]}["img.bin"]
        assert f["unrenderable"] is True

    def test_blob_trop_gros_unrenderable(self, git_repo):
        from graph_orchestrator.turn_checkpoint import _MAX_FILE_BYTES
        (git_repo / "gros.txt").write_text("x", encoding="utf-8")
        base = record_turn_checkpoint("st1-iter1", repo_path=str(git_repo))
        (git_repo / "gros.txt").write_text("x" * (_MAX_FILE_BYTES + 1), encoding="utf-8")
        diff = read_turn_diff(base, repo_path=str(git_repo))
        f = {x["path"]: x for x in diff["files"]}["gros.txt"]
        assert f["unrenderable"] is True

    def test_truncated_au_dela_de_max_files(self, git_repo):
        base = record_turn_checkpoint("st1-iter1", repo_path=str(git_repo))
        for i in range(_MAX_FILES + 1):
            (git_repo / f"f{i:03d}.txt").write_text("y", encoding="utf-8")
        diff = read_turn_diff(base, repo_path=str(git_repo))
        assert diff["status"] == "ready"
        assert diff["truncated"] is True
        assert len(diff["files"]) == _MAX_FILES


# ==========================================
# summarize_turn_diff — clé consommée par le Judge
# ==========================================

class TestSummarizeTurnDiff:
    def test_ready_resume_compact(self):
        diff = {"status": "ready", "files": [{
            "path": "a.css", "status": "added", "additions": 10, "deletions": 0,
            "originalContent": None, "modifiedContent": "x", "unrenderable": False,
        }]}
        assert summarize_turn_diff(diff) == [{
            "path": "a.css", "status": "added", "additions": 10, "deletions": 0,
            "unrenderable": False,
        }]

    def test_non_ready_resume_vide(self):
        assert summarize_turn_diff({"status": "missing", "files": []}) == []
        assert summarize_turn_diff(None) == []


# ==========================================
# Intégration — séquence exacte de production (workflows.py)
# ==========================================

class TestIntegrationSequenceProd:
    def test_sequence_iter1_judge_recoit_ce_que_git_dit(self, git_repo, monkeypatch):
        """Reproduit la séquence workflows.py : record pré-Coder → écriture Coder →
        commit F-53 → get_last_diff (vide en iter 1) → read+summarize → bloc Judge."""
        monkeypatch.chdir(git_repo)
        # Début d'itération 1 : snapshot pré-Coder (worktree vide).
        turn_ref = record_turn_checkpoint("st1-iter1", repo_path=str(git_repo))
        assert turn_ref is not None
        # Le Coder écrit ses livrables.
        (git_repo / "index.html").write_text("<html>v1</html>\n", encoding="utf-8")
        (git_repo / "styles.css").write_text("body{margin:0}\n", encoding="utf-8")
        # Post-Coder : commit F-53 + diff texte (VIDE en iter 1, <2 commits).
        commit_iteration(1, repo_path=str(git_repo))
        git_diff = get_last_diff(repo_path=str(git_repo))
        assert git_diff == ""
        # F-102 : le résumé structuré EST disponible dès l'iter 1.
        summary = summarize_turn_diff(
            read_turn_diff(turn_ref, repo_path=str(git_repo), include_contents=False)
        )
        paths = {s["path"]: s for s in summary}
        assert paths["index.html"]["status"] == "added"
        assert paths["styles.css"]["status"] == "added"
        # Le bloc Judge porte le manifeste même sans diff texte.
        block = build_judge_code_block(
            ["index.html", "styles.css"], git_diff, turn_diff_files=summary
        )
        assert "CE QUE GIT DIT" in block
        assert "[added] index.html" in block
        assert "DIFF MODIFIÉ" not in block  # iter 1 : full-file, rétrocompat

    def test_sequence_iter2_resume_devant_diff_texte(self, git_repo, monkeypatch):
        monkeypatch.chdir(git_repo)
        (git_repo / "index.html").write_text("<html>v1</html>\n", encoding="utf-8")
        commit_iteration(1, repo_path=str(git_repo))
        # Itération 2 : snapshot pré-correction, puis le Coder corrige.
        turn_ref = record_turn_checkpoint("st1-iter2", repo_path=str(git_repo))
        (git_repo / "index.html").write_text("<html>v2</html>\n", encoding="utf-8")
        commit_iteration(2, repo_path=str(git_repo))
        git_diff = get_last_diff(repo_path=str(git_repo))
        assert "+<html>v2</html>" in git_diff
        summary = summarize_turn_diff(
            read_turn_diff(turn_ref, repo_path=str(git_repo), include_contents=False)
        )
        assert summary and summary[0]["status"] == "modified"
        block = build_judge_code_block(
            ["index.html"], git_diff, turn_diff_files=summary
        )
        # Ordre : manifeste F-102 → diff texte IN-DIFF → code complet.
        assert block.index("CE QUE GIT DIT") < block.index("DIFF MODIFIÉ") < block.index("CODE COMPLET")
