"""Isolation LIVE du mécanisme de checkpoint git par itération (F-102). 0 LLM.

Déterministe (convention F-89) : joue la SÉQUENCE EXACTE de production sur un
run dir jetable — record_turn_checkpoint (début d'itération) → écritures
« Coder » → commit_iteration F-53 → read_turn_diff + summarize_turn_diff →
build_judge_code_block — et vérifie les 5 invariants du port open-swe :

  1. la ref refs/graph-orchestrator/turns/<key> existe ;
  2. HEAD/historique NON contaminés (aucun commit ajouté) ;
  3. l'index réel NON contaminé (untracked reste untracked) ;
  4. reprise : une ref existante n'est JAMAIS avancée ;
  5. le résumé structuré est disponible DÈS l'itération 1 (vs diff texte F-53 vide).

Usage : ``uv run python debug/run_turn_checkpoint.py`` (scénario démo temporaire).
"""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph_orchestrator.git_snapshot import commit_iteration, get_last_diff, init_run_git
from graph_orchestrator.judge_diff import build_judge_code_block
from graph_orchestrator.turn_checkpoint import (
    read_turn_diff,
    record_turn_checkpoint,
    summarize_turn_diff,
)

REF_NS = "refs/graph-orchestrator/turns"


def _git(args, cwd):
    r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout.strip()


def _has_head(cwd) -> bool:
    """HEAD existe ? (rev-parse --verify -q retourne 1 sur repo vide — attendu.)"""
    r = subprocess.run(["git", "rev-parse", "--verify", "-q", "HEAD"],
                       cwd=cwd, capture_output=True, text=True)
    return r.returncode == 0


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="go-turn-demo-") as td:
        run_dir = Path(td) / "run"
        run_dir.mkdir()
        repo = str(run_dir)
        print(f"[demo] run dir jetable : {repo}\n")

        assert init_run_git(repo_path=repo), "init_run_git a échoué"

        # --- Itération 1 : snapshot pré-Coder, puis le « Coder » écrit ----------
        ref1 = record_turn_checkpoint("st1-iter1", repo_path=repo)
        print(f"[1] ref du tour iter 1 : {ref1}")
        (run_dir / "index.html").write_text("<html>v1</html>\n", encoding="utf-8")
        (run_dir / "styles.css").write_text("body{margin:0}\n", encoding="utf-8")

        # Invariants 2+3 : le snapshot n'a RIEN écrit dans HEAD/index réels.
        head_count = _git(["rev-list", "--count", "HEAD"], repo) if _has_head(repo) else "0"
        status = _git(["status", "--porcelain"], repo)
        print(f"[2] commits HEAD après snapshot : {head_count} (attendu 0)")
        print(f"[3] status après snapshot      : {status!r} (attendu '?? index.html\\n?? styles.css')")
        assert head_count == "0" and "??" in status, "CONTAMINATION détectée"

        commit_iteration(1, repo_path=repo)
        text_diff_iter1 = get_last_diff(repo_path=repo)
        summary1 = summarize_turn_diff(read_turn_diff(ref1, repo_path=repo, include_contents=False))
        print(f"[4] diff texte F-53 iter 1 : {len(text_diff_iter1)} chars (attendu 0 — <2 commits)")
        print(f"[5] résumé F-102 iter 1     : {len(summary1)} fichiers (attendu 2 — DÈS l'iter 1)")
        for s in summary1:
            print(f"      - [{s['status']}] {s['path']} (+{s['additions']}/-{s['deletions']})")
        assert text_diff_iter1 == "" and len(summary1) == 2

        # --- Itération 2 : snapshot, correction « Coder », reprise simulée ------
        ref2 = record_turn_checkpoint("st1-iter2", repo_path=repo)
        (run_dir / "index.html").write_text("<html>v2 corrigé</html>\n", encoding="utf-8")
        sha_avant = _git(["rev-parse", ref2], repo)
        # Simule un crash-replay : le même tour re-snapshotte APRÈS d'autres écritures.
        (run_dir / "index.html").write_text("<html>v2 bis</html>\n", encoding="utf-8")
        ref2bis = record_turn_checkpoint("st1-iter2", repo_path=repo)
        sha_apres = _git(["rev-parse", ref2], repo)
        print(f"[6] reprise : ref avancée ? {sha_avant != sha_apres} (attendu False)")
        assert ref2bis == ref2 and sha_avant == sha_apres, "la base du tour a glissé"

        commit_iteration(2, repo_path=repo)
        summary2 = summarize_turn_diff(read_turn_diff(ref2, repo_path=repo, include_contents=False))
        block = build_judge_code_block(
            ["index.html", "styles.css"], get_last_diff(repo_path=repo), turn_diff_files=summary2
        )
        print(f"[7] résumé iter 2 : {summary2}")
        print("[8] bloc Judge (extrait) :")
        for line in block.splitlines()[:8]:
            print(f"      {line}")
        assert "[modified] index.html" in block and "CE QUE GIT DIT" in block

        refs = _git(["for-each-ref", REF_NS], repo)
        n_refs = len([l for l in refs.splitlines() if l.strip()])
        print(f"\n[ok] {n_refs} refs {REF_NS}/* créées, 8/8 invariants OK, teardown propre.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
