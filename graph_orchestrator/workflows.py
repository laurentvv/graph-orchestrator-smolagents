"""Workflows de plus haut niveau : one-shot (défaut) et exploration (loop-until-dry).

Le mode exploration (§5 du guide) boucle tant que de nouveaux éléments émergent.
Trois garanties anti-boucle-infinie :
  1. MAX_ITERATIONS — hard cap, sortie forcée.
  2. Critère "dry" — un tour n'apporte aucun nouvel insight (après dédup) => arrêt.
  3. Dédup contre TOUT le déjà-vu, y compris rejets — sinon on reboucle sur les dead-ends.

Phase 5 : la dédup est désormais PERSISTANTE via le Knowledge Graph (DuckDB) — l'état
des insights déjà vus survit à l'effacement du contexte et aux redémarrages.
"""

import asyncio
import hashlib
import json
import os
import re
import sys
from contextlib import contextmanager
from typing import List, Optional, Tuple

# --- Flushing temps-réel (observabilité) -------------------------------------
# En contexte non-TTY (pipe, redirection, serveur, agent), Python bufferise stdout
# et les print() n'apparaissent qu'à la fin du process — impossible d'observer la
# progression d'un workflow qui peut durer plusieurs minutes. On force le mode
# line-buffered pour que chaque print() soit visible immédiatement.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(line_buffering=True, encoding="utf-8")
    except Exception:
        # Fallback : si reconfigure() n'est pas dispo, on force l'unbuffered via
        # write+flush à l'ancienne n'est pas trivial sans wrapper ; on ignore.
        pass

from rich.console import Console
from rich.panel import Panel

from .config import Settings, settings as default_settings
from .hitl import hitl_checkpoint, should_trigger_hitl
from .idempotency import IdempotencyStore, _scoped_idempotency
from .knowledge_graph import KnowledgeGraph
from .logging_utils import NodeMetrics, render_observability_table
from .models import ArchitectOutput, FinalSynthesis, WorkerOutput
from .nodes import (
    aggregate_adversary_verdicts,
    build_fast_model,
    build_reasoning_model,
    execute_adversary_node,
    execute_reduce_node,
    execute_synth_node,
    execute_worker_node,
    execute_coder_node,
)

console = Console()


# ==========================================
# Output daté par run (Priorité 13 : isolation des artefacts)
# ==========================================
def _slugify(text: str, max_len: int = 24) -> str:
    """Transforme un texte en slug sûr pour un nom de dossier (cross-plateforme).

    Lowercase, remplace tout caractère non [a-z0-9] par `_`, collapse les `__+`,
    strip les `_` de bord. Sûr Windows (pas de `:`/`?`/`*`/`<>`/`|`). Tronqué à
    `max_len` pour garder des chemins lisibles.
    """
    s = (text or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "run"
    return s[:max_len].strip("_") or "run"


def _resolve_run_output_dir(
    settings: Settings,
    seed_tasks: List[dict],
    checkpoint: Optional[dict],
) -> str:
    """Détermine le dossier de sortie absolu pour CE run (Priorité 13).

    Logique de reprise (préserve la cohérence avec les checkpoints, Priorité 3) :
      - Si un checkpoint existe ET contient `output_dir` → on REPREND ce dossier
        (le Coder retrouvera les fichiers déjà générés, pas de repartie de zéro).
      - Sinon (nouveau run ou fresh_start) → on crée un NOUVEAU dossier daté
        `{output_dir}/{YYYY-MM-DD}_{HHMM}_{slug}/` résolu en absolu.

    Le slug est dérivé de `seed_tasks[0]['id']` (stable, connu avant l'Architect).
    Fallback sur 'run' si l'id est absent.

    Args:
        settings: Configuration (lit `output_dir`).
        seed_tasks: Tâches (pour le slug).
        checkpoint: Checkpoint chargé (peut contenir `output_dir` à reprendre).

    Returns:
        Chemin absolu du dossier de run (non encore créé — l'appelant fait makedirs).
    """
    # Cas reprise : le checkpoint persiste le chemin du run interrompu.
    if checkpoint and checkpoint.get("output_dir"):
        return os.path.abspath(checkpoint["output_dir"])

    # Nouveau run : dossier daté. Racine résolue en absolu (peut être relative "runs").
    root = os.path.abspath(settings.output_dir) if settings.output_dir else os.path.abspath("runs")
    from datetime import datetime
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    task_id = (seed_tasks[0].get("id", "") if seed_tasks else "") or "run"
    slug = _slugify(task_id)
    return os.path.join(root, f"{stamp}_{slug}")


def _prune_old_runs(runs_root: str, retention: int):
    """Supprime les anciens dossiers de run pour limiter la croissance (Priorité 13)."""
    import shutil
    if retention <= 0 or not os.path.isdir(runs_root):
        return
    
    try:
        candidates = []
        for name in os.listdir(runs_root):
            path = os.path.join(runs_root, name)
            if os.path.isdir(path) and not name.startswith("."):
                # Le pattern du dossier daté est YYYY-MM-DD_HHMM_slug
                candidates.append((path, os.path.getmtime(path)))
        
        # Tri par modification la plus récente d'abord (descendant)
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        if len(candidates) > retention:
            to_delete = candidates[retention:]
            for path, _ in to_delete:
                shutil.rmtree(path, ignore_errors=True)
                print(f"[🗑️] Ancien run supprimé (rétention={retention}) : {os.path.basename(path)}")
    except Exception as e:
        print(f"[⚠️] Échec du nettoyage des anciens runs dans {runs_root} : {e}")

@contextmanager
def _scoped_chdir(target_dir: str):
    """Change de répertoire de travail le temps d'un bloc, restore TOUJOURS à la sortie.

    Garantit la restoration du cwd original même en cas d'exception mid-workflow (critical
    pour les tests E2E qui enchaînent plusieurs run_coding_workflow dans la même session :
    sans restoration, le 2e run chercherait tasks.json/le KG dans le mauvais dossier).
    """
    original = os.getcwd()
    os.chdir(target_dir)
    try:
        yield target_dir
    finally:
        os.chdir(original)


async def run_exploration_workflow(
    seed_tasks: List[dict],
    settings: Settings = default_settings,
) -> Tuple[Optional[FinalSynthesis], List[NodeMetrics]]:
    """Mode exploration : loop-until-dry sur les angles non explorés.

    À chaque itération :
      - Fan-out sur les tâches de l'itération courante
      - Reduce + adversaires
      - On ne conserve que les insights NOUVEAUX (non vus dans le KG)
      - Si rien de nouveau => "dry" => on s'arrête et on synthétise

    La dédup est persistante : le KG (DuckDB) garde trace de TOUT ce qui a été vu,
    y compris les rejets (règle d'or §5). L'état survit aux redémarrages.
    """
    fast_model = build_fast_model(settings)
    reasoning_model = build_reasoning_model(settings)
    all_metrics: List[NodeMetrics] = []

    # Knowledge Graph persistant : remplace les Set en mémoire (seen_ids/seen_summaries).
    # L'état de dédup survit désormais entre runs (Phase 5).
    kg = KnowledgeGraph(settings.kg_path)
    run_id = f"exploration_{id(kg)}"
    print(f"[*] Knowledge Graph : {settings.kg_path}")

    accumulated: List[WorkerOutput] = []
    current_tasks = seed_tasks
    iteration = 0

    while iteration < settings.max_iterations:
        iteration += 1
        print(f"\n{'='*60}")
        print(f"  EXPLORATION — Itération {iteration}/{settings.max_iterations}")
        print(f"  Tâches ce tour : {[t['id'] for t in current_tasks]}")
        print(f"{'='*60}")

        # --- Fan-out ---
        worker_pairs = await asyncio.gather(
            *[execute_worker_node(t, fast_model, settings) for t in current_tasks]
        )
        raw = []
        for result, metrics in worker_pairs:
            if result is not None:
                raw.append(result)
            if metrics is not None:
                all_metrics.append(metrics)

        # --- Reduce ---
        reduced = execute_reduce_node(raw)
        candidates = reduced.kept

        # --- Dédup persistante via le KG (remplace les Set en mémoire) ---
        # On écrit chaque observation dans le KG ; add_claim() renvoie None si doublon.
        new_outputs: List[WorkerOutput] = []
        for w in candidates:
            entity_id = f"task:{w.task_id}"
            kg.add_entity(entity_id, kind="task", name=None)
            claim_id = kg.add_claim(
                entity_id=entity_id,
                content=w.summary,
                kind="observation",
                confidence=w.confidence_score,
                source=f"worker_{w.task_id}",
                model_id=settings.fast_model_id,
                run_id=run_id,
            )
            if claim_id is not None:
                # Nouveau (non vu) => on le garde pour la suite
                new_outputs.append(w)

        if not new_outputs:
            print(f"\n[*] Itération {iteration} : RIEN de nouveau (dry). Fin de l'exploration.")
            break

        # --- Adversaires sur les nouveaux ---
        verdicts, adv_metrics = await execute_adversary_node(
            new_outputs, current_tasks, reasoning_model, settings
        )
        all_metrics.extend(adv_metrics)

        if verdicts:
            judge = aggregate_adversary_verdicts(
                verdicts, new_outputs, settings.adversary_count, settings.adversary_threshold
            )
            print(f"[+] Itération {iteration} : {judge.reason}")
            for a in judge.assessments:
                tag = "[green][OK][/green]" if a.verdict == "approved" else "[red][FAIL][/red]"
                console.print(f"    {tag} [bold]{a.task_id}[/bold] — {a.reason[:100]}")

            # Marque le statut dans le KG + trace les réfutations
            for w in new_outputs:
                entity_id = f"task:{w.task_id}"
                claims = kg.get_claims(entity_id, status="open")
                if not claims:
                    continue
                obs_id = claims[-1]["id"]
                assessment = next((a for a in judge.assessments if a.task_id == w.task_id), None)
                if assessment is None:
                    continue
                if assessment.verdict == "approved":
                    kg.mark_status(obs_id, "approved")
                else:
                    # Rejet : on marque l'obs rejetée MAIS elle reste vue (règle d'or)
                    kg.mark_status(obs_id, "rejected")
                    ref_id = kg.add_claim(
                        entity_id=entity_id, content=assessment.reason, kind="refutation",
                        confidence=None, source="adversary_panel",
                        model_id=settings.reasoning_model_id, run_id=run_id,
                    )
                    if ref_id is not None:
                        kg.add_edge(ref_id, obs_id, "REFUTES")

            approved_this_round = [w for w in new_outputs if w.task_id in judge.approved_tasks]
            accumulated.extend(approved_this_round)
        else:
            # Sceptiques échoués : on accumule quand même (isolation des échecs, §5)
            print(f"[!] Itération {iteration} : sceptiques indisponibles, accumulation directe.")
            accumulated.extend(new_outputs)

        print(f"[*] Insights accumulés : {len(accumulated)} au total.")

    else:
        print(f"\n[*] Hard cap atteint ({settings.max_iterations} itérations). Arrêt forcé.")

    if not accumulated:
        print("[-] Aucun insight accumulé au cours de l'exploration.")
        return None, all_metrics

    # --- HITL stratégique (Phase 6) ---
    if should_trigger_hitl("synth", settings):
        if not hitl_checkpoint(accumulated, node_name="synth"):
            print("[-] Synthèse refusée par l'opérateur. Arrêt propre.")
            return None, all_metrics

    # --- Synthèse finale ---
    print(f"\n[*] Synthèse finale sur {len(accumulated)} insights accumulés...")
    final_result, synth_metrics = await execute_synth_node(accumulated, reasoning_model, settings)
    if synth_metrics is not None:
        all_metrics.append(synth_metrics)

    # Trace les insights finaux dans le KG
    if final_result is not None:
        for insight in final_result.key_insights:
            kg.add_claim(
                entity_id="synthesis", content=insight, kind="insight",
                confidence=None, source="synth",
                model_id=settings.reasoning_model_id, run_id=run_id,
            )

    return final_result, all_metrics


async def run_coding_workflow(
    seed_tasks: List[dict],
    settings: Settings = default_settings,
) -> Tuple[Optional[dict], List[NodeMetrics]]:
    """Mode coding : Architect -> Fan-out Coder -> Parallel Validation -> Judge (loop)."""
    reasoning_model = build_reasoning_model(settings)
    fast_model = build_fast_model(settings)
    all_metrics: List[NodeMetrics] = []

    # Knowledge Graph persistant : Phase 5 appliquée au codage
    kg = KnowledgeGraph(settings.kg_path)
    # run_id STABLE dérivé du contenu de tâche (avant annotation du routeur).
    # id(kg) changeait à chaque processus → impossible de reprendre. Avec ce hash,
    # relancer la même tâche (même tasks.json) reprend exactement où c'était arrêté.
    _run_key = (seed_tasks[0].get("content", "") if seed_tasks else "").strip().lower()
    run_id = f"coding_{hashlib.sha1(_run_key.encode('utf-8')).hexdigest()[:16]}"
    print(f"[*] Knowledge Graph branché : {settings.kg_path}")

    print(f"\n{'='*60}")
    print(f"  CODING WORKFLOW (Multi-Agent Playbook) — run {run_id}")
    print(f"{'='*60}")

    # --- Reprise après crash (Priorité 3 : Checkpoints) -----------------------
    # FRESH_START=1 → on efface tout checkpoint existant et repart de zéro.
    # Sinon, on tente de recharger l'état d'une exécution interrompue.
    checkpoint = None
    if settings.fresh_start:
        kg.clear_checkpoint(run_id)
        kg.clear_idempotency(run_id)
        print(f"[*] FRESH_START=1 : checkpoint existant effacé, exécution fraîche.")
    else:
        checkpoint = kg.load_checkpoint(run_id)
        if checkpoint:
            print(f"[↩] Checkpoint trouvé — reprise de l'exécution {run_id}")
        else:
            print(f"[*] Nouvelle exécution {run_id} (aucun checkpoint)")

    # --- Output daté par run (Priorité 13 : isolation des artefacts) -----------
    # On chdir vers un dossier dédié PAR RUN pour que les fichiers générés (Coder/Tester)
    # n'aillent PAS polluer la racine du projet. ORDRE CRITIQUE :
    #   1. KG déjà instancié (l.273) AVANT ce point → DuckDB reste à sa place (kg_path stable).
    #      Si on chdirait avant, la DB suivrait le cwd et changerait de place à chaque run.
    #   2. checkpoint déjà chargé ci-dessus → on sait s'il faut REPREDRE le dossier existant
    #      (reprise après crash) ou en créer un nouveau daté.
    # Le chemin du run est persisté dans le checkpoint (cf. save_coding_state) pour la reprise.
    # _scoped_chdir GARANTIT la restoration du cwd original à la sortie (même en cas
    # d'exception) — critical pour les tests E2E qui enchaînent plusieurs runs.
    run_output_dir = _resolve_run_output_dir(settings, seed_tasks, checkpoint)
    os.makedirs(run_output_dir, exist_ok=True)
    _resume_tag = "REPRIS" if (checkpoint and checkpoint.get("output_dir")) else "nouveau"
    print(f"[📁] Run output dir ({_resume_tag}) : {run_output_dir}")

    # Nettoyage optionnel (Priorité 13)
    if settings.output_retention > 0:
        root = os.path.abspath(settings.output_dir) if settings.output_dir else os.path.abspath("runs")
        _prune_old_runs(root, settings.output_retention)

    # --- Idempotence des effets de bord (Priorité 8-bis : replays/retries) ---
    # Store garantissant que les effets non-idempotents (append_file, pip install)
    # ne sont appliqués qu'UNE FOIS par run_id — même après un replay de checkpoint
    # (reprise après crash). Backing DuckDB (même kg). Exposé aux @tool (tools.py)
    # et au PythonTestRunner (python_tester.py) via le contexte module-level
    # (_scoped_idempotency → get_current_store()). Si désactivé → None :
    # comportement historique (re-applique les effets au replay).
    _idem_store = (
        IdempotencyStore(
            kg=kg,
            run_id=run_id,
            retention_s=settings.idempotency_retention_days * 86400,
        )
        if settings.idempotence_enabled
        else None
    )

    with _scoped_chdir(run_output_dir), _scoped_idempotency(_idem_store):
        # Tout le corps ci-dessous (imports, nœuds, boucle Coder/Judge) s'exécute dans le
        # dossier du run. Les target_files relatifs y atterrissent naturellement.

        # F-48 : git local propre au run pour suivre les modifications du Coder.
        # Chaque itération commit l'état des fichiers ; en iter N+1, git diff HEAD
        # donne les lignes EXACTES modifiées (re-test ciblé Tester + Judge in-diff).
        # Tolérant : si git absent, has_git_history() retourne False partout → fallback
        # sur les réfutations texte (F-47). Le .git vit dans runs/<dated>/ (gitignored).
        from .git_snapshot import init_run_git
        git_ok = init_run_git()

        results = []
        from .nodes import execute_tester_node, execute_coder_node
        from .linter import execute_linter_node
        from .dspy_nodes import (
            execute_architect_node,
            execute_security_reviewer_node,
            execute_code_judge_node,
            execute_escalation_node,
            execute_router_node,
            execute_prompt_refiner_node,
            execute_drafter_node,
        )
    
        # Routine initiale de routage
        task_content = seed_tasks[0]['content'] if seed_tasks else ""

        # --- Nœud PromptRefiner (F-39, meta-prompt avant l'Architect) ---------------
        # Reformule le prompt brut en spec structurée AVANT le Router et l'Architect, inspiré
        # du pattern "Enhance Prompt" (Kilo Code / Cline). ORDE CRITIQUE : ce bloc s'exécute
        # APRÈS le calcul du run_id (l.221, hash du prompt BRUT) — sinon le hash deviendrait
        # non-déterministe (le LLM génère du texte différent à chaque run) et casserait la
        # reprise après crash. Ici on mute task_content, pas le run_id.
        #
        # Skip LLM si checkpoint contient déjà le refined_prompt (économie à la reprise).
        if checkpoint and checkpoint.get("refined_prompt"):
            task_content = checkpoint["refined_prompt"]
            if seed_tasks:
                seed_tasks[0]['content'] = task_content
            print(f"[↩] PromptRefiner : spec RECHARGÉE depuis le checkpoint ({len(task_content)} caractères).")
        elif settings.prompt_refiner_enabled and seed_tasks:
            refined, m_refine = await execute_prompt_refiner_node(task_content, reasoning_model, settings)
            if m_refine:
                all_metrics.append(m_refine)
            if refined and refined.refined_prompt.strip():
                task_content = refined.refined_prompt
                seed_tasks[0]['content'] = task_content
            # Si refined est None (LLM down), on garde task_content brut (dégradation gracieuse).

        print(f"[*] Analyse de la requête par le routeur ultra-rapide...")
        router_res, m0 = await execute_router_node(task_content, fast_model, settings)
        if m0: all_metrics.append(m0)

        if router_res:
            print(f"[*] Le routeur a classifié la technologie principale : {router_res.language.upper()}")
            # On propage la techno STRUCTURELLEMENT (clé dédiée) en plus du texte libre
            # historique, pour que le Tester polyvalent puisse dispatcher sans re-parser
            # le prompt. detect_tech combine ce signal avec les extensions de target_files.
            coding_router_lang = router_res.language
            if seed_tasks:
                seed_tasks[0]['content'] += f"\n\n[ROUTER DIRECTIVE : The primary technology to use is {router_res.language.upper()}]"
                seed_tasks[0]['router_lang'] = coding_router_lang
        else:
            coding_router_lang = None

        # --- État de progression (Persistance d'État — Priorité 3 : Checkpoints) --
        # Holder mutable partagé entre les scopes de la fonction. Contient le plan de
        # l'Architect sérialisé (évite de relancer ce nœud LLM coûteux à la reprise) +
        # la liste des sous-tâches déjà approuvées + la position (sous-tâche, itération).
        # À la reprise (checkpoint trouvé), on HYDRATE ces champs depuis le checkpoint
        # pour que les skips (sous-tâches complétées) et la position prennent effet.
        coding_state = {
            "architect_result": checkpoint.get("architect_result") if checkpoint else None,
            "completed_subtasks": (checkpoint or {}).get("completed_subtasks", []),
            "current_subtask_idx": 0,
            "current_iteration": 0,
            # Spec racine complète (cahier des charges d'origine). Propagée jusqu'au
            # Tester (via sub_dict["original_content"]) pour qu'il connaisse le
            # comportement attendu global et écrive des assertions fonctionnelles,
            # pas seulement un smoke-test. Aussi passée au Judge (task_requirements).
            "seed_content": task_content,
        }

        def save_coding_state(subtask_idx: int, iteration: int) -> None:
            """Persiste l'état courant dans DuckDB (granularité "début d'itération").

            On ne sauvegarde qu'à des points COHÉRENTS : le Coder n'a pas encore tourné
            pour cette itération. À la reprise, on rejoue donc l'itération complète
            (Coder écrase le fichier = idempotent), sans risque de reprendre sur un
            état intermédiaire (ex: Judge en cours) qui serait incohérent.
            """
            kg.save_checkpoint(run_id, {
                "architect_result": coding_state["architect_result"],
                "completed_subtasks": list(coding_state["completed_subtasks"]),
                "current_subtask_idx": subtask_idx,
                "current_iteration": iteration,
                # F-39 : on persiste le prompt raffiné par le PromptRefiner pour skipper ce
                # nœud LLM à la reprise (même logique que architect_result). task_content a
                # déjà été muté au point d'insertion du PromptRefiner, donc coding_state
                # ["seed_content"] contient la version raffinée (ou brute si désactivé/down).
                "refined_prompt": coding_state["seed_content"],
                # Priorité 13 : on persiste le chemin du dossier de run pour que la reprise
                # après crash reprenne dans le MÊME dossier (fichiers déjà générés préservés).
                # run_output_dir est absolu (résolu dans _resolve_run_output_dir).
                "output_dir": run_output_dir,
            })

        async def process_subtask_loop(subtask, start_iteration: int = 1) -> Tuple[dict, List[NodeMetrics]]:
            sub_metrics = []
            entity_id = f"file:{subtask.task_id}"
            kg.add_entity(entity_id, kind="file", name=subtask.task_id)

            max_iter = settings.max_iterations  # avant : codé en dur à 3 (ignorait la config)

            for iteration in range(start_iteration, max_iter + 1):
                # Checkpoint au DÉBUT de chaque itération (point de sauvegarde sûr).
                save_coding_state(coding_state["current_subtask_idx"], iteration)
                print(f"    [>] Itération {iteration}/{max_iter} pour {subtask.task_id} (Coder)...")

                # Reconstruction du prompt en lisant l'historique de DuckDB
                # Au lieu d'accumuler dans le contexte, on fait une requête "Bug Tracker" propre.
                # IMPORTANT : on tronque À LA LECTURE (injection au Coder) — le contenu reste
                # intégral en base. Sinon, deux bugs distincts au préfixe identique produiraient
                # le même dedup_key (hash SHA1) et le 2e serait ignoré silencieusement.
                from .feedback_utils import truncate_history
                historique = ""
                refutations_raw = []  # F-47 : brut pour le Tester (mode re-test ciblé)
                if iteration > 1:
                    claims = kg.get_claims(entity_id)
                    refutations = [c for c in claims if c.get('kind') == 'refutation']
                    if refutations:
                        ref_contents = [c.get('content', '') for c in refutations]
                        historique = "\n\n" + truncate_history(
                            ref_contents,
                            max_chars=settings.feedback_max_chars,
                            header="[TICKETS DE BUGS ACTIFS (LU DEPUIS DUCKDB)] :",
                        )
                        # F-47 : garde les réfutations brutes pour le Tester (il en fait
                        # un re-test ciblé : ne tester QUE les bugs signalés + smoke-test,
                        # en 6 steps au lieu de 12). Évite le re-test from-scratch coûteux.
                        refutations_raw = refutations

                sub_dict = {
                    "id": subtask.task_id,
                    "content": subtask.description + historique,
                    "target_files": subtask.target_files,
                    # Propagation de la techno détectée par le routeur vers le Tester
                    # polyvalent (détection redondante : ce signal + les extensions).
                    "router_lang": coding_router_lang,
                    # Spec racine complète (cahier des charges d'origine). Le Tester en
                    # a besoin pour identifier les comportements attendus à valider via
                    # assertions fonctionnelles (sinon il ne teste que l'absence de crash).
                    "original_content": coding_state.get("seed_content", ""),
                    # F-29 : stratégie de construction dictée par l'Architect. Le Coder
                    # l'utilise pour adapter son workflow (simple=1 write_file, incremental
                    # =squelette+append sections, multifile=1 fichier par module). Défaut
                    # 'simple' (rétro-compat : sous-tâche sans stratégie explicite).
                    "strategy": getattr(subtask, "strategy", "simple"),
                    "sections": getattr(subtask, "sections", []),
                    # F-57 : skills sélectionnés par l'Architect pour cette sous-tâche.
                    # Le Coder reçoit le corps complet de ces skills. Si vide, socle défaut.
                    "skills": getattr(subtask, "skills", []),
                    # Numéro d'itération (1=création initiale, 2+=correction). Le prompt
                    # Coder s'adapte : itération 1 = write_file (création), itération 2+ =
                    # read_file + search_replace (correction chirurgicale, JAMAIS rewrite).
                    # Sans ça, le Coder réécrit le fichier from-scratch à chaque itération
                    # au lieu de corriger les bugs signalés par le Linter/Judge.
                    "iteration": iteration,
                    # F-47 : réfutations brutes pour le re-test ciblé. Le Tester les lit
                    # (should_use_targeted_retest) et, si itération >1, bascule en mode
                    # ciblé (max_steps 6, prompt priorise les bugs, smoke-test rapide).
                    # Vide en itération 1 → Tester en mode complet (checklist F-46).
                    "refutations": refutations_raw,
                }

                # 0. Drafter (iteration 1 uniquement)
                if iteration == 1:
                    draft_res, m_draft = await execute_drafter_node(sub_dict, reasoning_model, settings)
                    if m_draft: sub_metrics.append(m_draft)
                    if draft_res:
                        # 'os' est importé en tête de module (ligne 16). Un import local
                        # ici ferait de 'os' une variable locale à toute la fonction
                        # run_coding_workflow → UnboundLocalError à la première autre
                        # utilisation de os (ex. os.getenv ligne ~678). Bug révélé par
                        # le fix LoopGuard qui a débloqué le chemin jusqu'aux audits.
                        draft_filename = f"draft_{subtask.task_id.replace('-', '_')}.md"
                        draft_path = os.path.join(run_output_dir, draft_filename)
                        with open(draft_path, "w", encoding="utf-8") as f:
                            f.write(draft_res.draft_markdown)
                        sub_dict["content"] += f"\n\n### BROUILLON DE L'ALGORITHM DRAFTER\nL'Algorithm Drafter (Architecte Logiciel) a conçu la logique parfaite pour toi. Il a écrit tout le code brut dans le fichier `{draft_filename}` (à la racine du projet).\n\n⚠️ INSTRUCTION CRITIQUE : Ton PREMIER appel d'outil DOIT ÊTRE `read_file(path=\"{draft_filename}\")` pour récupérer ce code. Ensuite, utilise tes outils `write_file` ou `append_file` pour l'injecter proprement dans les vrais fichiers cibles."

                # 1. Coder (smolagents, modèle FAST)
                coder_res, m1 = await execute_coder_node(sub_dict, fast_model, settings)
                if m1: sub_metrics.append(m1)

                if not coder_res or coder_res.status == "failure":
                    print(f"    [-] Le Coder a échoué techniquement sur {subtask.task_id}.")
                    return {"status": "failure", "reason": "Coder crash"}, sub_metrics

                # F-48 : commit l'état post-Coder dans le git local du run. Permet
                # d'extraire le diff (lignes modifiées) pour le Tester (re-test ciblé
                # précis) et le Judge (in-diff-only). Le diff est calculé APRÈS le commit
                # (HEAD~1..HEAD). En itération 1, pas de diff (création initiale).
                if git_ok:
                    from .git_snapshot import commit_iteration, get_last_diff
                    commit_iteration(iteration)
                    sub_dict["git_diff"] = get_last_diff()

                print(f"    [>] Coder terminé. Déclenchement des Audits parallèles (Tester & Sécurité)...")

                # On enregistre l'observation du Coder dans DuckDB
                obs_id = kg.add_claim(
                    entity_id=entity_id,
                    content=f"Code généré (Itération {iteration}): {coder_res.details}",
                    kind="observation",
                    confidence=1.0,
                    source="coder",
                    model_id=settings.reasoning_model_id,
                    run_id=run_id,
                )

                # --- Nœud Linter (Shift Left, F-30) --------------------------------
                # Gatekeeper LÉGER (0 LLM, millisecondes) qui valide la SYNTAXE des fichiers
                # générés AVANT de solliciter les nœuds lourds (Tester LLM + Judge LLM). C'est
                # l'économie massive de P3/P7 : un bug de syntaxe trivial (IndentationError
                # Python, contenu après </html>, string non fermée) ne doit pas gaspiller un
                # cycle LLM complet. Si invalide → on court-circuite le Tester, on écrit le
                # bug en DuckDB (kind='refutation', source='linter') et on relance le Coder.
                lint_res, m_lint = execute_linter_node(sub_dict, settings)
                if m_lint: sub_metrics.append(m_lint)

                if lint_res and lint_res.status == "failure":
                    print(f"    [⚠] Linter a détecté des erreurs de syntaxe sur {subtask.task_id} — "
                          f"court-circuit du Tester (Shift Left).")
                    if obs_id: kg.mark_status(obs_id, "rejected")
                    # Le feedback du Linter devient une réfutation (lu par le Coder à l'itération suivante
                    # via kg.get_claims, comme les réfutations du Judge — mécanisme existant réutilisé).
                    ref_id = kg.add_claim(
                        entity_id=entity_id,
                        content=f"[LINTER] {lint_res.details}",
                        kind="refutation",
                        confidence=None,
                        source="linter",
                        model_id="tree-sitter-linter",
                        run_id=run_id,
                    )
                    if ref_id and obs_id:
                        kg.add_edge(ref_id, obs_id, "REFUTES")
                    # On passe à l'itération suivante SANS Tester/Judge (économie de cycles LLM).
                    continue

                # --- Nœud Static Tester (F-49) ----------------------------------
                # Gatekeeper déterministe WEB (0 LLM, <6s) qui valide la SÉMANTIQUE
                # web AVANT le Tester LLM coûteux. Implémente la méthodologie prouvée
                # de debug/MANUAL_TESTER_METHODOLOGY.md :
                #   Tier 1 (<1s) : node --check sur le JS inline (attrape TS-in-vanilla =
                #                 le bug n°1 du Coder = page blanche) + wiring addEventListener
                #                 (attrape slider non branché = indétectable par screenshot).
                #   Tier 2 (~5s) : visibilité DOM via DevTools (attrape barres invisibles =
                #                 bug CSS height:% que le LLM a raté par biais de confirmation).
                # Complémentaire du Linter (qui SAUTE le JS inline du HTML — tree-sitter-html
                # trop tolérant). Court-circuite le Tester LLM (25 min) sur les bugs évidents.
                # Dégradation gracieuse : node/Chrome absents → skip silencieux (le LLM prend
                # le relais). STATIC_TESTER_ENABLED=0 désactive le nœud entièrement.
                from .static_tester import execute_static_tester_node
                static_res, m_st = execute_static_tester_node(sub_dict, settings)
                if m_st: sub_metrics.append(m_st)

                if static_res and static_res.status == "failure":
                    print(f"    [⚠] Static Tester a détecté un bug web évident sur "
                          f"{subtask.task_id} — court-circuit du Tester LLM (économie cycle).")
                    if obs_id: kg.mark_status(obs_id, "rejected")
                    # Le feedback devient une réfutation (lue par le Coder à l'itération
                    # suivante via kg.get_claims, comme Linter/Judge — mécanisme réutilisé).
                    ref_id = kg.add_claim(
                        entity_id=entity_id,
                        content=f"[STATIC TESTER] {static_res.details}",
                        kind="refutation",
                        confidence=None,
                        source="static_tester",
                        model_id="static-tester",
                        run_id=run_id,
                    )
                    if ref_id and obs_id:
                        kg.add_edge(ref_id, obs_id, "REFUTES")
                    # On passe à l'itération suivante SANS Tester/Judge LLM.
                    continue

                # 2. Vérifications Contradictoires (Tester + Security Reviewer)
                # GPU-local : on séquentialise par défaut ( Tester PUIS Security)
                # car lancer 2× le reasoning_model en parallèle sature la VRAM
                # → swap lent, timeouts, et le Security devient "silencieux"
                # (observé run F-45 : Tester à 201k tokens pendant que Security
                # n'a jamais rendu de verdict). AUDIT_PARALLEL=true restaure le
                # comportement historique (gather) sur les grosses machines.
                #
                # MODÈLE TESTER : fast_model (multimodal, ex. gemma-4-E4B) — PAS reasoning_model.
                # Le Tester capture des screenshots DevTools/Puppeteer et les envoie au modèle
                # pour validation visuelle (layout, page blanche, chevauchements). Il faut donc
                # un modèle MULTIMODAL. Or le reasoning_model (Ornith-9B) est texte uniquement.
                # Le Security Reviewer reste sur reasoning_model (audit de code, pas de vision).
                audit_parallel = os.getenv("AUDIT_PARALLEL", "false").strip().lower() in {"1", "true", "yes", "on"}

                if audit_parallel:
                    print(f"    [>] Coder terminé. Déclenchement des Audits parallèles (Tester & Sécurité)...")
                    t_task = execute_tester_node(sub_dict, fast_model, settings)
                    s_task = execute_security_reviewer_node(sub_dict, reasoning_model, settings)
                    (test_res, m2), (sec_res, m3) = await asyncio.gather(t_task, s_task)
                else:
                    print(f"    [>] Coder terminé. Audit séquentiel (GPU-local) : Tester PUIS Sécurité...")
                    test_res, m2 = await execute_tester_node(sub_dict, fast_model, settings)
                    print(f"    [>] Tester terminé. Security Reviewer en cours...")
                    sec_res, m3 = await execute_security_reviewer_node(sub_dict, reasoning_model, settings)
                if m2: sub_metrics.append(m2)
                if m3: sub_metrics.append(m3)

                # Traçage KG d'un échec Security (post-mortem run 123955) : si le
                # nœud Security n'a pas rendu de verdict (None), on persiste une
                # réfutation dédiée pour que le post-mortem et l'Escalade en
                # tiennent compte. Combiné au fail-closed côté Judge (qui bloque
                # l'approbation sans audit), l'échec n'est plus silencieux.
                if sec_res is None:
                    print(f"    [!] Security Reviewer a échoué pour {subtask.task_id} — tracé dans le KG.")
                    kg.add_claim(
                        entity_id=entity_id,
                        content="Audit sécurité INDISPONIBLE — le nœud Security n'a pas produit de verdict (échec LLM/infra). Approbation bloquée (fail-closed).",
                        kind="refutation",
                        confidence=None,
                        source="security_unavailable",
                        model_id=settings.reasoning_model_id,
                        run_id=run_id,
                    )

                # 3. Judge Panel (Fan-in) — DSPy ChainOfThought (Pydantic force le JSON Mode)
                print(f"    [>] Audits terminés. Juge ({settings.reasoning_model_id}) en cours d'évaluation...")
                judge_res, m4 = await execute_code_judge_node(sub_dict, test_res, sec_res, fast_model, settings)
                if m4: sub_metrics.append(m4)

                if judge_res and judge_res.is_approved:
                    print(f"    [+] {subtask.task_id} APPROUVÉ par le Juge ! 🚀")
                    if obs_id: kg.mark_status(obs_id, "approved")
                    # Sous-tâche validée → on la marque comme complétée pour le checkpoint
                    # (à la reprise, elle sera sautée sans ré-exécuter le Coder).
                    coding_state["completed_subtasks"].append(subtask.task_id)
                    save_coding_state(coding_state["current_subtask_idx"], iteration)
                    return {"status": "success", "task_id": subtask.task_id}, sub_metrics
                else:
                    feedback = judge_res.final_feedback if judge_res else "Erreur système du juge."
                    print(f"    [-] {subtask.task_id} REJETÉ. Sauvegarde du bug dans DuckDB...")
                    if obs_id: kg.mark_status(obs_id, "rejected")

                    # Le Juge écrit la faille ou le bug dans DuckDB (le Knowledge Graph)
                    ref_id = kg.add_claim(
                        entity_id=entity_id, 
                        content=feedback, 
                        kind="refutation",
                        confidence=None, 
                        source="judge_panel",
                        model_id=settings.reasoning_model_id, 
                        run_id=run_id
                    )
                    if ref_id and obs_id:
                        kg.add_edge(ref_id, obs_id, "REFUTES")

            print(f"    [!] Max itérations atteintes pour {subtask.task_id}.")

            # --- Nœud d'Escalade (Priorité 3, F-23) --------------------------------
            # Le Circuit Breaker s'est activé : la sous-tâche a épuisé ses itérations
            # sans approval. Au lieu d'abandonner sans retour, on synthétise les
            # réfutations accumulées dans le KG en un diagnostic post-mortem, persisté
            # et exploitable par un run futur. Dégradation gracieuse : si l'escalade
            # est désactivée (ESCALATION_ENABLED=false) ou si le nœud LLM échoue, on
            # retombe sur le statut historique 'max_iterations_reached'.
            if settings.escalation_enabled:
                from .feedback_utils import truncate_history
                # Lecture de TOUTES les réfutations accumulées pour cette sous-tâche.
                refutations = [c for c in kg.get_claims(entity_id) if c.get('kind') == 'refutation']
                failure_history = truncate_history(
                    [c.get('content', '') for c in refutations],
                    max_chars=settings.feedback_max_chars,
                    header="[HISTORIQUE DES ÉCHECS (RÉFUTATIONS DU JUGE)] :",
                )
                escalation_sub = {
                    "id": subtask.task_id,
                    "description": subtask.description,
                    "target_files": subtask.target_files,
                }
                print(f"    [↗] Activation du Nœud d'Escalade (post-mortem) pour {subtask.task_id}...")
                try:
                    esc_res, m5 = await execute_escalation_node(escalation_sub, failure_history, reasoning_model, settings)
                    if m5: sub_metrics.append(m5)
                except Exception as esc_err:
                    # Défense en profondeur : le nœud attrape déjà ses erreurs LLM en
                    # interne (→ None), mais on protège aussi contre toute exception
                    # non prévue. Le post-mortem ne doit JAMAIS faire planter le run —
                    # on replie sur le statut historique.
                    print(f"    [-] Nœud d'Escalade en erreur ({esc_err}) — repli sur le statut brut.")
                    esc_res = None

                if esc_res:
                    # Persistance du diagnostic dans le KG (kind="escalation").
                    diag_text = (
                        f"CAUSE RACINE: {esc_res.root_cause}\n"
                        f"TENTATIVES: {', '.join(esc_res.attempted_fixes) or 'non documentées'}\n"
                        f"LEÇON: {esc_res.lesson}\n"
                        f"GRAVITÉ: {esc_res.severity}"
                    )
                    esc_id = kg.add_claim(
                        entity_id=entity_id,
                        content=diag_text,
                        kind="escalation",
                        confidence=None,
                        source="escalation_node",
                        model_id=settings.reasoning_model_id,
                        run_id=run_id,
                    )
                    # Relie le diagnostic aux réfutations qu'il synthétise (traçabilité).
                    if esc_id is not None:
                        for ref in refutations:
                            kg.add_edge(esc_id, ref['id'], "ESCALATES")
                    print(f"    [⚠] {subtask.task_id} ESCALADÉ — diagnostic persisté (gravité: {esc_res.severity}).")
                    return {
                        "status": "escalated",
                        "task_id": subtask.task_id,
                        "diagnostic": esc_res.model_dump(),
                    }, sub_metrics

                print(f"    [-] Nœud d'Escalade indisponible/échoué pour {subtask.task_id} — repli sur le statut brut.")

            return {"status": "max_iterations_reached", "task_id": subtask.task_id}, sub_metrics

        for task in seed_tasks:
            # --- Reprise : l'Architect est-il déjà en checkpoint ? ----------------
            # À la reprise, on évite de relancer ce nœud de raisonnement coûteux en
            # rechargeant le plan sérialisé. Sinon, appel normal + persistance du plan.
            if checkpoint and checkpoint.get("architect_result"):
                architect_result = ArchitectOutput(**checkpoint["architect_result"])
                print(f"\n[*] 1. Plan de l'Architecte RECHARGÉ depuis le checkpoint (économise un appel LLM).")
            else:
                print(f"\n[*] 1. Exécution de l'Architecte pour la tâche globale : {task['id']}")
                architect_result, arch_metrics = await execute_architect_node(task, reasoning_model, settings)
                if arch_metrics:
                    all_metrics.append(arch_metrics)

            if architect_result is None:
                print(f"[-] L'Architecte a échoué à planifier la tâche {task['id']}.")
                continue

            # Persiste le plan (premier checkpoint utile : sauve l'appel Architect).
            coding_state["architect_result"] = architect_result.model_dump()

            print(f"[+] Plan de l'Architecte reçu : {architect_result.global_architecture}")
            print(f"[*] 2. Fan-out : Lancement des boucles d'ingénierie parallèles sur {len(architect_result.subtasks)} sous-tâches...\n")

            # Exécution Séquentielle (Pipeline) pour éviter les Race Conditions sur les fichiers
            for i, st in enumerate(architect_result.subtasks):
                coding_state["current_subtask_idx"] = i

                # --- Reprise : sous-tâche déjà approuvée ? On la saute ----------------
                if st.task_id in coding_state["completed_subtasks"]:
                    print(f"[*] Sous-tâche {i+1}/{len(architect_result.subtasks)} ({st.task_id}) déjà APPROUVÉE — skip.")
                    results.append({"status": "success", "task_id": st.task_id, "replayed": True})
                    continue

                # --- Reprise : itération de départ pour cette sous-tâche ---------------
                # Si le checkpoint pointe exactement sur (i, iteration), on reprend là.
                start_iter = 1
                if checkpoint and checkpoint.get("current_subtask_idx") == i and checkpoint.get("current_iteration"):
                    start_iter = checkpoint["current_iteration"]
                    print(f"[*] Reprise de la sous-tâche {i+1}/{len(architect_result.subtasks)} à l'itération {start_iter}...")
                    checkpoint = None  # le checkpoint n'est consommé qu'une fois

                print(f"[*] Traitement de la sous-tâche {i+1}/{len(architect_result.subtasks)}...")
                res, metrics = await process_subtask_loop(st, start_iteration=start_iter)
                all_metrics.extend(metrics)
                results.append(res)

            print(f"\n[*] 3. Fusion des sous-tâches terminée pour {task['id']}.")

        # Toutes les sous-tâches sont traitées : on marque le run comme terminé.
        kg.clear_checkpoint(run_id)
        kg.clear_idempotency(run_id)
        print(f"\n[*] Run {run_id} terminé — checkpoint effacé.")

        return {"architect_plans": len(seed_tasks), "final_results": results}, all_metrics


# ==========================================
# Tâches d'exemple selon le mode
# ==========================================

ONE_SHOT_TASKS = [
    {"id": "t1", "content": "La charge CPU du serveur DB a atteint 95% pendant 10 minutes."},
    {"id": "t2", "content": "Le reverse proxy a retourné 45 erreurs 502 dans la dernière heure."},
    {"id": "t3", "content": "L'espace disque sur /var/log est à 12%."},
]

EXPLORATION_SEED_TASKS = [
    {
        "id": "e1",
        "content": (
            "Identifie TOUTES les causes possibles d'une charge CPU à 95% sur un serveur de base "
            "de données. Explore chaque piste : requêtes, locks, index manquants, paramétrage, "
            "concurrence, fuites."
        ),
    },
    {
        "id": "e2",
        "content": (
            "Identifie TOUTES les causes possibles de 45 erreurs HTTP 502 sur un reverse proxy. "
            "Explore chaque piste : backend down, timeouts, saturation de connexions, DNS, TLS, "
            "config."
        ),
    },
]

CODING_SEED_TASKS = [
    {
        "id": "T004",
        "content": "Crée un jeu de Tetris simple mais complet en HTML, CSS et JavaScript pur (pas de framework). Le jeu doit être jouable directement dans le navigateur, avec des flèches directionnelles. L'architecture doit comporter au moins 3 fichiers : index.html, style.css et tetris.js.",
        "target_files": ["index.html", "style.css", "tetris.js"]
    }
]


def load_tasks_from_json(mode: str, fallback_tasks: List[dict]) -> List[dict]:
    tasks_file = "tasks.json"
    if os.path.exists(tasks_file):
        try:
            with open(tasks_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if mode in data and isinstance(data[mode], list):
                    print(f"[*] Chargement des tâches '{mode}' depuis {tasks_file}")
                    return data[mode]
        except Exception as e:
            print(f"[!] Erreur lors de la lecture de {tasks_file}: {e}")
    return fallback_tasks

def run_workflow(mode: str, settings: Settings = default_settings) -> None:
    """Lance le workflow selon le mode (one_shot / exploration / coding)."""
    if mode == "exploration":
        tasks = load_tasks_from_json(mode, EXPLORATION_SEED_TASKS)
        final_output, metrics = asyncio.run(run_exploration_workflow(tasks, settings))
    elif mode == "coding":
        tasks = load_tasks_from_json(mode, CODING_SEED_TASKS)
        final_output, metrics = asyncio.run(run_coding_workflow(tasks, settings))
    else:
        from .runner import run_graph_workflow
        tasks = load_tasks_from_json(mode, ONE_SHOT_TASKS)
        final_output, metrics = asyncio.run(run_graph_workflow(tasks, settings))

    if metrics:
        render_observability_table(metrics, console)

    if final_output:
        data = final_output.model_dump() if hasattr(final_output, "model_dump") else final_output
        console.print(Panel(
            json.dumps(data, indent=4, ensure_ascii=False),
            title="[bold green]RÉSULTAT FINAL DU GRAPHE[/bold green]",
            border_style="green",
        ))


def main() -> None:
    """Point d'entrée dispatchant selon WORKFLOW_MODE."""
    settings = default_settings
    # --- Logs de run auto-capturés (Priorité 13-bis) ------------------------
    # Tee posé ICI (dès main()) pour capturer 100% de la sortie : preamble Knowledge
    # Graph, run_id, checkpoint, run_output_dir... Ces lignes sont imprimées AVANT
    # la résolution du dossier de run (coding/exploration), donc on doit englober
    # run_workflow() entier. Couvre les 3 modes + les 2 entry points (agent_graph.py
    # et -m graph_orchestrator.workflows importent tous deux cette fonction).
    from .run_logging import tee_run_logging, resolve_log_path, clean_old_logs
    
    # Nettoyage des anciens logs (rétention = output_retention)
    clean_old_logs(settings.logs_dir, settings.output_retention)
    
    log_path = resolve_log_path(settings.workflow_mode, settings.logs_dir)
    with tee_run_logging(log_path, enabled=settings.log_to_file):
        # 1ère ligne du log : permet à l'utilisateur de retrouver le chemin du fichier.
        print(f"[📜] Log du run : {log_path}")
        run_workflow(settings.workflow_mode, settings)


if __name__ == "__main__":
    main()
