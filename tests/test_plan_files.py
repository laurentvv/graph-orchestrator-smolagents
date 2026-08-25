"""Tests F-120 — matérialisation plan.md + task.md (planning-with-files).

Périmètre :
- build_plan_markdown : miroir FIDÈLE de TOUT l'ArchitectOutput (test
  anti-perte : chaque champ d'ArchitectTask doit apparaître dans plan.md).
- build_task_markdown : checklist vivante + journal des verdicts daté.
- build_coder_anchor : bloc court STABLE, SANS les critères visuels (ils sont
  injectés par le bloc F-82 existant — anti-redondance).
- write_plan_files : best-effort total (échec IO → pas d'exception).
- Intégration workflow (nœuds mockés, pattern tests/test_checkpoint.py) :
  fichiers écrits dans le run dir, anchor dans chaque sub_dict Coder,
  journal "APPROUVÉ", opt-out PLAN_TASK_MATERIALIZE=false → rien.

0 LLM, 0 réseau, 0 mock réseau. Conventions F-89/F-95 (tmp_path, basetemp).
"""

import asyncio
import glob
import inspect
import os
import tempfile

from graph_orchestrator.models import (
    ArchitectOutput,
    ArchitectTask,
    CoderOutput,
    CodeJudgeOutput,
    RouterOutput,
    SecurityOutput,
)
from graph_orchestrator.plan_files import (
    PLAN_FILENAME,
    TASK_FILENAME,
    build_coder_anchor,
    build_plan_markdown,
    build_task_markdown,
    derive_goal,
    make_event,
    write_plan_files,
)


def _arch() -> ArchitectOutput:
    """ArchitectOutput complet : chaque famille de champs F-29/F-57/F-82 posée."""
    return ArchitectOutput(
        plan_id="plan-120",
        global_architecture="3 fichiers HTML/CSS/JS vanilla",
        subtasks=[
            ArchitectTask(
                task_id="st-1",
                description="Créer la structure HTML",
                target_files=["index.html"],
                strategy="multifile",
                sections=[],
                skills=["frontend-design"],
                tester_skills=["web-tester"],
                judge_skills=["code-review"],
                visual_success_criteria=["barres visibles au chargement"],
                functional_test_criteria=["le tri se déroule étape par étape"],
                acceptance_rubric="visuel 40%, fonctionnel 60%",
            ),
            ArchitectTask(task_id="st-2", description="CSS", target_files=["styles.css"]),
        ],
    )


# ==========================================
# 1. Builders purs
# ==========================================


class TestDeriveGoal:
    def test_aplatit_et_garde_court(self):
        goal = derive_goal("Crée un   visualiseur\nde bubble sort très joli")
        assert goal == "Crée un visualiseur de bubble sort très joli"

    def test_section_objective_extraite_sans_titres(self):
        """Run #13 : le Goal ne doit plus contenir les titres markdown de la
        spec PromptRefiner (F-115) ni le contenu des sections suivantes."""
        spec = (
            "## Objective\nCreate a vanilla Bubble Sort visualizer in three files.\n\n"
            "## Expected Features\n- Start button\n- Counter\n\n"
            "## Technical Constraints\nNo CDN."
        )
        goal = derive_goal(spec)
        assert goal == "Create a vanilla Bubble Sort visualizer in three files."
        assert "##" not in goal
        assert "Expected Features" not in goal
        assert "Start button" not in goal

    def test_section_objectif_retrocompat_francais(self):
        goal = derive_goal("## Objectif\nCrée un visualiseur de tri.\n## Suite")
        assert goal == "Crée un visualiseur de tri."

    def test_section_objective_tronquee(self):
        spec = "## Objective\n" + "x" * 500 + "\n\n## Next"
        goal = derive_goal(spec)
        assert len(goal) == 201  # 200 + '…'
        assert goal.endswith("…")

    def test_section_vide_repli_document_entier(self):
        goal = derive_goal("## Objective\n\n## Expected Features\n- item\nFais un tri visuel sympa")
        assert goal == "## Expected Features - item Fais un tri visuel sympa"

    def test_sans_section_repli_texte_brut(self):
        assert derive_goal("Fais un visualiseur de tri à bulles.") == "Fais un visualiseur de tri à bulles."

    def test_tronque_avec_ellipse(self):
        goal = derive_goal("x" * 500)
        assert len(goal) == 201  # 200 + '…'
        assert goal.endswith("…")

    def test_vide(self):
        assert derive_goal("") == ""
        assert derive_goal(None) == ""


class TestBuildPlanMarkdown:
    def test_miroir_fidele_tous_les_champs(self):
        """Anti-perte : chaque champ d'ArchitectOutput apparaît dans plan.md."""
        md = build_plan_markdown("Crée un visualiseur de tri", _arch())
        for expected in (
            "plan-120",  # plan_id
            "Crée un visualiseur de tri",  # Goal (cahier des charges)
            "3 fichiers HTML/CSS/JS vanilla",  # global_architecture
            "st-1",
            "Créer la structure HTML",  # description
            "- [ ] `index.html`",  # target_files en checklist
            "`multifile`",  # strategy
            "`frontend-design`",  # skills Coder
            "`web-tester`",  # tester_skills
            "`code-review`",  # judge_skills
            "barres visibles au chargement",  # visual_success_criteria (F-82)
            "le tri se déroule étape par étape",  # functional_test_criteria
            "visuel 40%, fonctionnel 60%",  # acceptance_rubric
            "**Status:** pending",
        ):
            assert expected in md, f"champ perdu de plan.md : {expected!r}"

    def test_sections_incremental_affichees(self):
        arch = _arch()
        arch.subtasks[0].strategy = "incremental"
        arch.subtasks[0].sections = ["CSS", "sidebar", "JS"]
        md = build_plan_markdown("g", arch)
        assert "`CSS`" in md and "`sidebar`" in md

    def test_statuts_complete_et_in_progress(self):
        md = build_plan_markdown("g", _arch(), completed_ids={"st-1"}, in_progress_id="st-2")
        assert "**Status:** complete" in md
        assert "**Status:** in_progress" in md
        assert "- [x] `index.html`" in md  # sous-tâche approuvée → fichiers cochés

    def test_objet_ou_dict_equivalents(self):
        assert build_plan_markdown("g", _arch()) == build_plan_markdown("g", _arch().model_dump())

    def test_architect_vide_ne_crash_pas(self):
        md = build_plan_markdown("", None)
        assert "Goal :** —" in md  # goal vide → tiret
        assert "Sous-tâches" in md


class TestBuildTaskMarkdown:
    def test_checklist_et_progression(self):
        md = build_task_markdown(_arch(), completed_ids={"st-1"})
        assert "**Progression :** 1/2 sous-tâche(s) approuvée(s)" in md
        assert "- [x] **1. st-1**" in md
        assert "- [ ] **2. st-2** (`styles.css`)" in md

    def test_in_progress_marque(self):
        md = build_task_markdown(_arch(), in_progress_id="st-2")
        assert "**2. st-2** (`styles.css`) — in_progress" in md

    def test_journal_des_verdicts_avec_pipe_echappe(self):
        events = [
            make_event("st-1", 1, "rejected", "compteur figé | NaN"),
            make_event("st-1", 2, "approved", "correction validée"),
        ]
        md = build_task_markdown(_arch(), events=events)
        assert "## Journal du run" in md
        assert "| Heure | Sous-tâche | Itér | Événement | Détail |" in md
        assert "rejet juge" in md  # libellé traduit
        assert "APPROUVÉ" in md
        assert "compteur figé \\| NaN" in md  # pipe markdown échappé

    def test_sans_journal(self):
        assert "Journal du run" not in build_task_markdown(_arch())


class TestMakeEvent:
    def test_structure_et_cap_detail(self):
        ev = make_event("st-1", 3, "rejected", "x" * 500)
        assert ev["subtask"] == "st-1" and ev["iter"] == 3
        assert ev["event"] == "rejected"
        assert len(ev["detail"]) == 161  # 160 + '…'
        assert ev["ts"]  # horodaté


class TestBuildCoderAnchor:
    def test_contenu_court_avec_pointeur_plan(self):
        anchor = build_coder_anchor(
            "st-1", "Créer la structure HTML", ["index.html", "script.js"],
            strategy="multifile", goal="Visualiseur bubble sort premium",
        )
        assert anchor.startswith("### PLAN GLOBAL")
        assert "**Goal :** Visualiseur bubble sort premium" in anchor
        assert "`st-1`" in anchor and "Créer la structure HTML" in anchor
        assert "`index.html`" in anchor and "`script.js`" in anchor
        assert "`multifile`" in anchor
        assert "`plan.md`" in anchor  # pointeur vers le plan complet

    def test_anti_redondance_criteres_visuels(self):
        """Les critères visuels circulent par le bloc F-82 (nodes.py) — jamais
        dupliqués dans l'anchor (budget prompt F-103)."""
        anchor = build_coder_anchor(
            "st", "desc", ["a.html"], strategy="simple",
            goal="g " + "critères visuels " * 3,
        )
        assert "Critères visuels" not in anchor
        assert "visual_success_criteria" not in anchor

    def test_stable_entrees_identiques(self):
        args = ("st", "desc", ["a.html"], "simple", "goal")
        assert build_coder_anchor(*args) == build_coder_anchor(*args)

    def test_sans_fichiers_ni_goal(self):
        anchor = build_coder_anchor("st", "d")
        assert "Checklist fichiers" not in anchor
        assert "Goal" not in anchor


# ==========================================
# 2. Écriture disque best-effort
# ==========================================


class TestWritePlanFiles:
    def test_ecrit_les_deux_fichiers(self, tmp_path):
        plan_path, task_path = write_plan_files(str(tmp_path), "goal", _arch())
        assert plan_path == os.path.join(str(tmp_path), PLAN_FILENAME)
        assert task_path == os.path.join(str(tmp_path), TASK_FILENAME)
        assert os.path.exists(plan_path) and os.path.exists(task_path)
        assert "st-1" in open(plan_path, encoding="utf-8").read()
        assert "Progression" in open(task_path, encoding="utf-8").read()

    def test_regenere_idempotent_avec_statuts(self, tmp_path):
        write_plan_files(str(tmp_path), "g", _arch())
        _, task_path = write_plan_files(
            str(tmp_path), "g", _arch().model_dump(), completed_ids={"st-1"}
        )
        assert "1/2" in open(task_path, encoding="utf-8").read()

    def test_best_effort_dossier_inexistant(self, tmp_path):
        """Échec IO avalé : aucune exception, retours None, run jamais cassé."""
        missing = os.path.join(str(tmp_path), "inexistant")
        plan_path, task_path = write_plan_files(missing, "g", _arch())
        assert plan_path is None and task_path is None


# ==========================================
# 3. Branchement du prompt Coder (garde anti-oubli)
# ==========================================


class TestBranchementPromptCoder:
    def test_prompt_coder_reference_plan_anchor(self):
        """F-169 : le prompt du Coder vit dans coder_pydantic (moteur UNIQUE)
        et doit référencer plan_anchor — sinon l'anchor serait calculé par
        workflows.py mais jamais injecté."""
        import graph_orchestrator.coder_pydantic as cp_mod

        assert "task.get('plan_anchor', '')" in inspect.getsource(cp_mod)


# ==========================================
# 4. Intégration workflow (nœuds mockés — pattern tests/test_checkpoint.py)
# ==========================================


def _seed_tasks():
    return [{
        "id": "T1",
        "content": "Crée un visualiseur de bubble sort premium",
        "target_files": ["index.html", "styles.css"],
    }]


def _setup_mocks(monkeypatch, captured_subs):
    """Mocks déterministes : le workflow tourne de bout en bout sans LLM.

    Les nœuds sont importés LOCALEMENT dans run_coding_workflow : on patche
    les attributs sur les modules source (récupérés au runtime), pattern
    éprouvé de tests/test_checkpoint.py::_setup_workflow_mocks.
    """
    import graph_orchestrator.dspy_nodes as dspy_mod
    import graph_orchestrator.nodes as nodes_mod
    import graph_orchestrator.workflows as wf_mod

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
            plan_id="plan-120",
            global_architecture="2 fichiers vanilla",
            subtasks=[
                ArchitectTask(
                    task_id="st1",
                    description="Faire le HTML",
                    target_files=["index.html"],
                    visual_success_criteria=["barres visibles au chargement"],
                ),
                ArchitectTask(task_id="st2", description="Faire le CSS", target_files=["styles.css"]),
            ],
        ), None

    monkeypatch.setattr(dspy_mod, "execute_architect_node", fake_architect)

    async def fake_drafter(sub, model, s):
        return None, None  # pas de draft (comme un Drafter en échec : dégradation)

    monkeypatch.setattr(dspy_mod, "execute_drafter_node", fake_drafter)

    async def fake_coder(sub, model, s):
        captured_subs.append(dict(sub))
        return CoderOutput(task_id=sub["id"], status="success", details="ok"), None

    monkeypatch.setattr(nodes_mod, "execute_coder_node", fake_coder)

    async def fake_tester(sub, model, s):
        return CoderOutput(task_id=sub["id"], status="success", details="tests ok"), None

    monkeypatch.setattr(nodes_mod, "execute_tester_node", fake_tester)

    async def fake_security(sub, model, s):
        return SecurityOutput(task_id=sub["id"], is_secure=True, vulnerabilities=[]), None

    monkeypatch.setattr(dspy_mod, "execute_security_reviewer_node", fake_security)

    async def fake_judge(sub, test_res, sec_res, model, s):
        return CodeJudgeOutput(task_id=sub["id"], is_approved=True, final_feedback="Parfait"), None

    monkeypatch.setattr(dspy_mod, "execute_code_judge_node", fake_judge)

    async def fake_consolidation(kg, run_id, s):
        return None, None

    monkeypatch.setattr(dspy_mod, "execute_consolidation_node", fake_consolidation)


def _settings(plan_task_materialize=True):
    from graph_orchestrator.config import Settings

    return Settings(
        output_dir=tempfile.mkdtemp(prefix="f120_runs_"),  # F-113 : isole du vrai runs/
        local_api_base="http://x/v1",
        local_reasoning_api_base="http://x/v1",
        local_api_key="sk",
        fast_model_id="m", reasoning_model_id="m",
        reasoning_max_tokens=8, fast_max_tokens=8, coder_temperature=0.2,
        llm_timeout_s=1.0, judge_confidence_threshold=0.5,
        worker_max_retries=1, adversary_count=1, adversary_threshold=0.5,
        max_iterations=3, hitl_enabled=False, hitl_nodes="synth",
        kg_path=":memory:", workflow_mode="coding", log_level="LOW",
        fresh_start=False,
        test_timeout_s=120, stderr_head_lines=20, stderr_tail_lines=20,
        feedback_max_chars=2000,
        plan_task_materialize=plan_task_materialize,
    )


def _unique_run_dir(settings_obj):
    dirs = [d for d in glob.glob(os.path.join(settings_obj.output_dir, "*")) if os.path.isdir(d)]
    assert len(dirs) == 1, f"attendu 1 run dir, trouvé {dirs}"
    return dirs[0]


class TestIntegrationWorkflow:
    def test_fichiers_ecrits_et_anchor_injecte(self, monkeypatch):
        """Run nominal 2 sous-tâches : plan.md + task.md dans le run dir,
        checklist complète, journal APPROUVÉ, anchor dans CHAQUE sub_dict."""
        from graph_orchestrator.workflows import run_coding_workflow

        captured = []
        _setup_mocks(monkeypatch, captured)
        s = _settings()
        out, _metrics = asyncio.run(run_coding_workflow(_seed_tasks(), s))

        assert all(r["status"] == "success" for r in out["final_results"])
        run_dir = _unique_run_dir(s)
        plan_md = open(os.path.join(run_dir, PLAN_FILENAME), encoding="utf-8").read()
        task_md = open(os.path.join(run_dir, TASK_FILENAME), encoding="utf-8").read()

        # plan.md : miroir fidèle (critères visuels F-82 inclus)
        assert "**Goal :**" in plan_md and "2 fichiers vanilla" in plan_md
        assert "barres visibles au chargement" in plan_md
        assert "`index.html`" in plan_md and "`styles.css`" in plan_md

        # task.md : checklist cochée après approbation + journal des verdicts
        assert "**Progression :** 2/2 sous-tâche(s) approuvée(s)" in task_md
        assert "- [x] **1. st1**" in task_md and "- [x] **2. st2**" in task_md
        assert "APPROUVÉ" in task_md

        # anchor : stable et présent à chaque appel Coder (1 par sous-tâche)
        assert len(captured) == 2
        for sub in captured:
            anchor = sub.get("plan_anchor", "")
            assert anchor.startswith("### PLAN GLOBAL")
            assert f"`{sub['id']}`" in anchor
            assert f"`{PLAN_FILENAME}`" in anchor
        # anti-redondance : l'anchor ne duplique pas les critères visuels
        assert "barres visibles" not in captured[0]["plan_anchor"]

    def test_flag_off_aucun_fichier_ni_anchor(self, monkeypatch):
        from graph_orchestrator.workflows import run_coding_workflow

        captured = []
        _setup_mocks(monkeypatch, captured)
        s = _settings(plan_task_materialize=False)
        out, _ = asyncio.run(run_coding_workflow(_seed_tasks(), s))

        assert all(r["status"] == "success" for r in out["final_results"])
        run_dir = _unique_run_dir(s)
        assert not os.path.exists(os.path.join(run_dir, PLAN_FILENAME))
        assert not os.path.exists(os.path.join(run_dir, TASK_FILENAME))
        for sub in captured:
            assert "plan_anchor" not in sub
