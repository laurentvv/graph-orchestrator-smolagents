"""Isolation F-158/F-159 : nœud Coder pydantic-ai-harness de PRODUCTION.

Appelle la VRAIE fonction ``graph_orchestrator.coder_pydantic.run_coder_pydantic``
(convention F-89 : 0 mock) avec une tâche figée (Bubble Sort multi-fichiers, même
tâche que debug/run_coder.py pour un A/B honnête). Le flag CODER_ENGINE n'est pas
nécessaire : l'isolation appelle le module directement ; en E2E, c'est
``CODER_ENGINE=pydantic`` qui aiguille execute_coder_node.

Phases couvertes :
  - 3.1-3.2 (F-158) : CoderOutput natif, FileSystem, custom tools, skills.
  - 3.3-3.4 (F-159) : gardes (LoopGuard v2, Stall, IdleBreaker, GoalGate,
    ReviveRetry + revive llama-server) + SystemReminders + TieredCompaction —
    actives par défaut (CODER_PYDANTIC_GUARDS=true ; false = baseline F-158).

Contrôles :
  - sortie CoderOutput VALIDÉE nativement (output_type, pas de sauvetage DSPy) ;
  - livrable conforme : 3 fichiers non vides + câblage index.html + invariants JS ;
  - pas de boucle stérile (tool calls bornés) ;
  - tokens & durée vs baselines (spike F-157 : 131,6k in / 594 s ; F-158 run1 :
    68,2k in / 7,1k out / 583 s).

Usage :
    uv run python debug/run_coder_pydantic.py            # tâche Bubble Sort par défaut
    uv run python debug/run_coder_pydantic.py @spec.md   # spec personnalisée
"""

import argparse
import asyncio
import os
import shutil
import sys
import time

from dotenv import load_dotenv

load_dotenv()

# 🔒 DOSSIER DE SORTIE HARDCODÉ — isolation stricte (nettoyé à chaque run).
OUT_DIR = "debug/coder_pydantic_out"

DEFAULT_TARGET_FILES = ["index.html", "styles.css", "script.js"]

# Même tâche que debug/run_coder.py (comparaison A/B honnête).
DEFAULT_TASK = (
    "Crée un visualiseur d'algorithme Bubble Sort (tri à bulles) interactif en "
    "HTML/CSS/JS vanilla, réparti sur TROIS fichiers séparés : index.html (structure "
    "+ lien vers le CSS et le JS), styles.css (tout le style), script.js (toute la "
    "logique). Pas de framework ni de CDN externe.\n\n"
    "L'interface doit montrer un tableau de barres verticales (hauteurs proportionnelles "
    "aux valeurs) qui s'animent pendant le tri. Fonctionnalités attendues :\n"
    "- un bouton « Démarrer le tri » qui lance l'animation pas-à-pas de Bubble Sort "
    "avec un délai visible entre chaque comparaison/échange ;\n"
    "- un bouton « Réinitialiser » qui génère un nouveau tableau aléatoire ;\n"
    "- un curseur/slidebar pour régler la vitesse d'animation ;\n"
    "- un compteur affichant le nombre de comparaisons effectuées ;\n"
    "- un code couleur clair : barre en cours de comparaison = une couleur, barre déjà "
    "triée = une autre couleur, barres non encore traitées = couleur par défaut.\n\n"
    "Contraintes techniques : index.html doit référencer styles.css via <link> et "
    "script.js via <script src>. Le JS accède au DOM via les ids définis dans le HTML. "
    "Design soigné, responsive, avec un thème sombre (dark mode)."
)


def _resolve_arg(arg: str) -> str:
    if not arg:
        return arg
    if arg.startswith("@"):
        with open(arg[1:], "r", encoding="utf-8") as f:
            return f.read().strip()
    if os.path.isfile(arg):
        with open(arg, "r", encoding="utf-8") as f:
            return f.read().strip()
    return arg


def _reset_out_dir() -> None:
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.makedirs(OUT_DIR, exist_ok=True)


def _check_deliverable(out_dir: str) -> list[tuple[str, bool, str]]:
    """Contrôles livrable : existence, taille, câblage index.html, invariants JS clés."""
    checks: list[tuple[str, bool, str]] = []
    contents: dict[str, str] = {}
    for fname in DEFAULT_TARGET_FILES:
        path = os.path.join(out_dir, fname)
        ok = os.path.isfile(path) and os.path.getsize(path) > 100
        checks.append((f"fichier {fname}", ok, f"{os.path.getsize(path) if os.path.exists(path) else 0} octets"))
        if ok:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                contents[fname] = f.read()
    idx = contents.get("index.html", "")
    js = contents.get("script.js", "")
    checks.append(("index.html référence styles.css", "styles.css" in idx, ""))
    checks.append(("index.html référence script.js", "script.js" in idx, ""))
    checks.append(("JS init robuste (readyState/DOMContentLoaded)",
                   ("readyState" in js or "DOMContentLoaded" in js), ""))
    checks.append(("JS strict mode", "'use strict'" in js or '"use strict"' in js, ""))
    checks.append(("aucun placeholder TODO/…", not any(
        m in c for c in contents.values() for m in ("TODO", "...:</", "PLACEHOLDER")), ""))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Isolation Coder pydantic-ai-harness (F-158)")
    parser.add_argument("task", nargs="?", default=None, help="Tâche (ou @fichier)")
    args = parser.parse_args()
    task_desc = _resolve_arg(args.task) if args.task else DEFAULT_TASK

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    _reset_out_dir()

    from graph_orchestrator.config import settings

    print("[*] Isolation Coder pydantic-ai-harness — F-158 3.1-3.2 + F-159 3.3-3.4 + F-161 3.6 vision (PRODUCTION)")
    print(f"    Sortie isolée  : {os.path.abspath(OUT_DIR)}")
    print(f"    gardes F-159   : {settings.coder_pydantic_guards}")
    print(f"    vision F-161   : {settings.coder_pydantic_vision} (keep={settings.coder_pydantic_vision_keep})")
    print(f"    Modèle FAST    : {settings.fast_spec.model}")
    print(f"    tempér.        : {settings.coder_temperature} | retries sortie : {settings.worker_max_retries}")
    print(f"    max requests   : {settings.coder_max_steps}")
    print()

    # Tâche dict au format production (workflows.py sub_dict) — le Coder pydantic
    # consomme exactement les mêmes champs que le Coder smolagents.
    task = {
        "id": "ts-pydantic-isolation",
        "content": task_desc,
        "target_files": list(DEFAULT_TARGET_FILES),
        "strategy": "multifile",
        "sections": [],
        "skills": ["coding", "file-creation"],
        "iteration": 1,
    }

    from graph_orchestrator.coder_pydantic import run_coder_pydantic

    original_cwd = os.getcwd()
    os.chdir(OUT_DIR)  # miroir du chdir F-40 du workflow (le nœud écrit en relatif)
    t0 = time.time()
    try:
        coder_output, metrics = asyncio.run(run_coder_pydantic(task, settings))
    finally:
        os.chdir(original_cwd)
    duration = time.time() - t0

    print("\n" + "=" * 60)
    print("RÉSULTAT DE L'ISOLATION — Coder pydantic (production)")
    print("=" * 60)
    if coder_output is not None:
        print(f"CoderOutput VALIDÉ nativement : task_id={coder_output.task_id}")
        print(f"  status={coder_output.status} linter_ok={coder_output.linter_ok} "
              f"vision_ok={coder_output.vision_ok}")
        print(f"  details: {coder_output.details[:300]}")
    else:
        print("CoderOutput : None (échec du run)")
    if metrics is not None:
        print(f"  tokens in/out : {metrics.input_tokens} / {metrics.output_tokens}")
        print(f"  durée noeud   : {metrics.duration_s:.1f}s")
    print(f"  durée totale  : {duration:.1f}s")
    print("-" * 60)
    print("Livrable :")
    ok_count = 0
    for name, ok, detail in _check_deliverable(OUT_DIR):
        print(f"  [{'✓' if ok else '✗'}] {name} {detail}")
        ok_count += ok
    total = len(DEFAULT_TARGET_FILES) + 5
    print("-" * 60)
    verdict = (
        "GO"
        if coder_output is not None
        and coder_output.status == "success"
        and ok_count == total
        else "NO-GO"
    )
    print(f"VERDICT : {verdict} ({ok_count}/{total} contrôles livrable)")
    print("=" * 60)
    return 0 if verdict == "GO" else 1


if __name__ == "__main__":
    sys.exit(main())
