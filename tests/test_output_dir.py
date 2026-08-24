"""Tests unitaires de l'Output daté par run (Priorité 13 du plan usine logicielle).

Valide l'isolation des artefacts : chaque run écrit dans `runs/YYYY-MM-DD_HHMM_slug/`,
avec reprise après crash qui préserve le dossier, et restoration du cwd original.

Déterministes, 0 LLM (nœuds mockés comme test_checkpoint.py / test_escalation.py).
"""
import asyncio
import os
import re

import pytest

from graph_orchestrator.workflows import (
    _slugify,
    _resolve_run_output_dir,
    _scoped_chdir,
    run_coding_workflow,
)


# ==========================================
# _slugify
# ==========================================
def test_slugify_basic():
    assert _slugify("Bubble Sort Visualizer") == "bubble_sort_visualizer"


def test_slugify_special_chars_and_spaces():
    """Caractères spéciaux et espaces → underscores, collapse des multiples."""
    assert _slugify("To-Do: List @home!") == "to_do_list_home"


def test_slugify_windows_safe():
    """Pas de caractères interdits Windows (:, ?, *, <, >, |)."""
    slug = _slugify("file:name?*<>|test")
    for forbidden in (":", "?", "*", "<", ">", "|"):
        assert forbidden not in slug


def test_slugify_empty_fallback():
    """Texte vide ou que des caractères spéciaux → fallback 'run'."""
    assert _slugify("") == "run"
    assert _slugify("???") == "run"
    assert _slugify(None) == "run"


def test_slugify_truncation():
    """Troncation à max_len pour garder des chemins lisibles."""
    long = "a" * 100
    assert len(_slugify(long, max_len=24)) == 24
    assert _slugify(long, max_len=10) == "a" * 10


# ==========================================
# _resolve_run_output_dir
# ==========================================
def _mock_settings(output_dir="runs"):
    from graph_orchestrator.config import Settings
    return Settings(
        local_api_base="http://x/v1", local_reasoning_api_base="http://x/v1",
        local_api_key="sk", fast_model_id="m", reasoning_model_id="m",
        reasoning_max_tokens=8, fast_max_tokens=8, coder_temperature=0.2,
        llm_timeout_s=1.0, judge_confidence_threshold=0.5,
        worker_max_retries=1, adversary_count=1, adversary_threshold=0.5,
        max_iterations=3, hitl_enabled=False, hitl_nodes="synth",
        kg_path=":memory:", workflow_mode="coding", log_level="LOW",
        fresh_start=True,
        test_timeout_s=120, stderr_head_lines=20, stderr_tail_lines=20,
        feedback_max_chars=2000,
        output_dir=output_dir,
    )


def test_resolve_output_dir_new_run_dated(tmp_path):
    """Nouveau run (pas de checkpoint) → dossier daté sous output_dir, absolu."""
    s = _mock_settings(output_dir=str(tmp_path / "runs"))
    tasks = [{"id": "bubble_sort", "content": "tri à bulles", "target_files": ["index.html"]}]
    out = _resolve_run_output_dir(s, tasks, checkpoint=None)
    # Absolu, sous runs/, avec date + slug.
    assert os.path.isabs(out)
    assert "runs" in out
    assert re.search(r"\d{4}-\d{2}-\d{2}_\d{4}_bubble_sort$", out.replace("\\", "/"))


def test_resolve_output_dir_resume_uses_checkpoint(tmp_path):
    """Reprise : checkpoint avec output_dir → on REPRED ce dossier (pas de nouveau daté)."""
    s = _mock_settings(output_dir=str(tmp_path / "runs"))
    tasks = [{"id": "x", "content": "x"}]
    saved_dir = str(tmp_path / "previous_run")
    checkpoint = {"output_dir": saved_dir}
    out = _resolve_run_output_dir(s, tasks, checkpoint=checkpoint)
    assert os.path.abspath(out) == os.path.abspath(saved_dir)


def test_resolve_output_dir_fallback_id_missing(tmp_path):
    """id manquant → slug 'run'."""
    s = _mock_settings(output_dir=str(tmp_path / "runs"))
    tasks = [{"content": "pas d'id"}]
    out = _resolve_run_output_dir(s, tasks, checkpoint=None)
    assert "_run" in os.path.basename(out)


# ==========================================
# _scoped_chdir (restoration cwd garantie)
# ==========================================
def test_scoped_chdir_restores_cwd(tmp_path):
    """Le contexte restore TOUJOURS le cwd original à la sortie."""
    original = os.getcwd()
    target = str(tmp_path / "subdir")
    os.makedirs(target)
    with _scoped_chdir(target):
        assert os.getcwd() == os.path.abspath(target)
    assert os.getcwd() == original  # restauré


def test_scoped_chdir_restores_on_exception(tmp_path):
    """Même en cas d'exception mid-bloc, le cwd est restauré (critical pour tests E2E)."""
    original = os.getcwd()
    target = str(tmp_path / "subdir")
    os.makedirs(target)
    with pytest.raises(RuntimeError):
        with _scoped_chdir(target):
            raise RuntimeError("boom")
    assert os.getcwd() == original


# ==========================================
# E2E : run_coding_workflow écrit dans le run dir + reprise
# ==========================================
def _mock_nodes_for_output_test(monkeypatch, coder_writes_file):
    """Mocke les nœuds ; le Coder écrit un fichier (pour valider qu'il atterrit dans run dir)."""
    import graph_orchestrator.nodes as nodes_mod
    import graph_orchestrator.dspy_nodes as dspy_mod
    import graph_orchestrator.workflows as wf_mod
    from graph_orchestrator.models import (
        ArchitectOutput, ArchitectTask, RouterOutput, CoderOutput,
        SecurityOutput, CodeJudgeOutput,
    )

    monkeypatch.setattr(wf_mod, "build_fast_model", lambda s: "FAKE_FAST")
    monkeypatch.setattr(wf_mod, "build_reasoning_model", lambda s: "FAKE_REASON")

    async def fake_router(content, model, s):
        return RouterOutput(language="HTML"), None
    monkeypatch.setattr(dspy_mod, "execute_router_node", fake_router)
    async def fake_prompt_refiner(raw, model, s):
        return None, None
    monkeypatch.setattr(dspy_mod, "execute_prompt_refiner_node", fake_prompt_refiner)

    async def fake_architect(task, model, s):
        return ArchitectOutput(
            plan_id="p1", global_architecture="1 fichier",
            subtasks=[ArchitectTask(task_id="st1", description="tri à bulles",
                                    target_files=["index.html"])],
        ), None
    monkeypatch.setattr(dspy_mod, "execute_architect_node", fake_architect)

    # Drafter mocké (F-167) : le helper mocke TOUS les nœuds LLM ; l'oubli du
    # Drafter était masqué par des spawns llama-server qui échouaient vite en
    # suite (timeout 1 s) — mais avec le GPU libre le VRAI serveur démarrait
    # (~30 s/test, non-déterminisme : draft réel injecté ou pas selon l'état
    # GPU). Retour (None, None) = « Drafter crashé » → pas de draft, chemin
    # identique à l'historique de ces tests.
    async def fake_drafter(sub, model, s):
        return None, None
    monkeypatch.setattr(dspy_mod, "execute_drafter_node", fake_drafter)

    async def fake_coder(sub, model, s):
        # Le Coder écrit un fichier RELATIF → doit atterrir dans le run dir (cwd courant).
        coder_writes_file(sub)
        return CoderOutput(task_id=sub["id"], status="success", details="ok"), None

    # Linter : mock SYNCHRONE (execute_linter_node n'est pas async — appel direct en l.506).
    # Renvoie None = pas d'erreur de syntaxe → on passe au Tester sans court-circuit.
    # ATTENTION : execute_linter_node est importé LOCALEMENT dans run_coding_workflow
    # (from .linter import ...), donc on patche sur le module SOURCE linter, pas workflows.
    import graph_orchestrator.linter as linter_mod
    def fake_linter(sub, s):
        return None, None

    async def fake_tester(sub, model, s):
        return CoderOutput(task_id=sub["id"], status="success", details="ok"), None
    async def fake_security(sub, model, s):
        return SecurityOutput(task_id=sub["id"], is_secure=True, vulnerabilities=[]), None
    monkeypatch.setattr(nodes_mod, "execute_coder_node", fake_coder)
    monkeypatch.setattr(linter_mod, "execute_linter_node", fake_linter)
    monkeypatch.setattr(nodes_mod, "execute_tester_node", fake_tester)
    monkeypatch.setattr(dspy_mod, "execute_security_reviewer_node", fake_security)
    async def fake_judge(sub, t, sec, model, s):
        return CodeJudgeOutput(task_id=sub["id"], is_approved=True, final_feedback="ok"), None
    monkeypatch.setattr(dspy_mod, "execute_code_judge_node", fake_judge)


def test_e2e_coder_writes_in_run_dir(monkeypatch, tmp_path):
    """Le fichier généré par le Coder atterrit dans runs/.../, PAS à la racine du projet."""
    from dataclasses import replace

    written = {}
    def coder_writes(sub):
        # Écrit index.html en relatif → atterrit dans le cwd courant (= run dir).
        with open("index.html", "w", encoding="utf-8") as f:
            f.write("<html>bubble sort</html>")
        written["cwd_at_write"] = os.getcwd()

    _mock_nodes_for_output_test(monkeypatch, coder_writes)
    cwd_before = os.getcwd()
    runs_root = str(tmp_path / "runs")

    s = replace(_mock_settings(output_dir=runs_root), kg_path=str(tmp_path / "kg.db"))
    tasks = [{"id": "bubble_sort", "content": "Visualiseur de tri à bulles", "target_files": ["index.html"]}]
    asyncio.run(run_coding_workflow(tasks, s))

    # 1. Le fichier a été écrit dans un sous-dossier de runs/, PAS à la racine projet.
    assert "runs" in written["cwd_at_write"].replace("\\", "/")
    assert written["cwd_at_write"] != cwd_before
    # 2. Le fichier existe bien dans le run dir.
    assert os.path.exists(os.path.join(written["cwd_at_write"], "index.html"))
    # 3. PAS de fichier à la racine du projet (le chdir l'a isolé).
    assert not os.path.exists(os.path.join(cwd_before, "index.html"))
    # 4. Le cwd a été restauré après le workflow.
    assert os.getcwd() == cwd_before


def test_e2e_resume_reuses_same_run_dir(monkeypatch, tmp_path):
    """Reprise après crash : le 2e run REPRED le même dossier (fichiers préservés)."""
    from dataclasses import replace

    db = str(tmp_path / "kg_resume.db")
    runs_root = str(tmp_path / "runs")
    tasks = [{"id": "todo_app", "content": "Application todo list persistante", "target_files": ["app.js"]}]

    cwd_during = []
    def coder_writes(sub):
        cwd_during.append(os.getcwd())
        with open("app.js", "w", encoding="utf-8") as f:
            f.write("// todo")

    _mock_nodes_for_output_test(monkeypatch, coder_writes)

    # 1er run (fresh_start=True) → crée un dossier daté + persiste output_dir en checkpoint.
    s1 = replace(_mock_settings(output_dir=runs_root), kg_path=db, fresh_start=True)
    asyncio.run(run_coding_workflow(tasks, s1))
    first_dir = cwd_during[0]

    # 2e run (fresh_start=False) → doit REPREDRE le même dossier (checkpoint a output_dir).
    cwd_during.clear()
    s2 = replace(_mock_settings(output_dir=runs_root), kg_path=db, fresh_start=False)
    asyncio.run(run_coding_workflow(tasks, s2))

    assert len(cwd_during) == 1
    assert cwd_during[0] == first_dir  # MÊME dossier que le 1er run (reprise)


def test_e2e_kg_path_stable_after_chdir(monkeypatch, tmp_path):
    """Le chdir ne déplace PAS la DB DuckDB : elle reste à kg_path (racine projet/tmp)."""
    from dataclasses import replace

    db = str(tmp_path / "kg_stable.db")
    runs_root = str(tmp_path / "runs")
    tasks = [{"id": "x", "content": "tache test kg", "target_files": ["x.py"]}]
    _mock_nodes_for_output_test(monkeypatch, lambda sub: open("x.py", "w").write("x"))

    s = replace(_mock_settings(output_dir=runs_root), kg_path=db, fresh_start=True)
    asyncio.run(run_coding_workflow(tasks, s))

    # La DB existe bien à sa place d'origine (tmp_path), PAS dans runs/.
    assert os.path.exists(db), "La DB DuckDB doit rester à kg_path, pas suivre le chdir"
    # Pas de DB dans le run dir.
    for root, _, files in os.walk(runs_root):
        assert "kg_stable.db" not in files, "DB trouvée dans runs/ (aurait dû rester à kg_path)"
