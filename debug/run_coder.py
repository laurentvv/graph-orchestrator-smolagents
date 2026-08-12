"""Lance le nœud Coder (production) en isolation — multi-fichiers + draft optionnel.

Usage :
    uv run python debug/run_coder.py                       # Bubble Sort 3 fichiers, sans draft
    uv run python debug/run_coder.py @prompts/bubble_sort_spec.md   # spec perso
    uv run python debug/run_coder.py --draft runs/2026-08-08_0909_bubble_sort_multifile_v6/draft_bubble_sort_viz_001.md
    uv run python debug/run_coder.py --draft @runs/.../draft_*.md   # draft + spec par défaut

Reproduit fidèlement les conditions E2E du workflow coding (workflows.py:556-570) :
  - target_files = [index.html, styles.css, script.js] (multi-fichiers, pas 1 seul)
  - Drafter injecté optionnellement : copie le draft_*.md dans le dossier de sortie +
    ajoute l'instruction '### BROUILLON DE L'ALGORITHM DRAFTER' au content (le Coder
    fait read_file du draft puis l'injecte dans les fichiers cibles).

Appelle DIRECTEMENT execute_coder_node de nodes.py (0 duplication) → comportement réel :
run_with_retry, prompt F-44/F-56/F-88, sauvetage DSPy, stall_detector, loop_guard.

Isolation stricte : écrit EXCLUSIVEMENT dans debug/coder_isolation_out/. Le dossier est
nettoyé puis recréé à chaque lancement (write_file from scratch garanti).

BUT : itérer rapidement (couper si erreur, corriger, relancer) sur le nœud Coder sans
relancer le workflow complet de 30-40 min (Architect/Drafter/Tester/Judge sautés).
"""
import argparse
import os
import shutil
import sys

from dotenv import load_dotenv

load_dotenv()


# 🔒 DOSSIER DE SORTIE HARDCODÉ — isolation stricte.
OUT_DIR = "debug/coder_isolation_out"

# Multi-fichiers Bubble Sort (le cas de validation E2E standard).
DEFAULT_TARGET_FILES = ["index.html", "styles.css", "script.js"]

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
    """Résout un arg CLI : @fichier → contenu du fichier, chemin existant → contenu, sinon texte brut."""
    if not arg:
        return arg
    # @fichier : convention explicite.
    if arg.startswith("@"):
        path = arg[1:]
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    # Chemin de fichier existant : on lit le contenu (sinon le draft contiendrait
    # juste le chemin au lieu du code — bug qui faisait boucler le Coder).
    if os.path.isfile(arg):
        with open(arg, "r", encoding="utf-8") as f:
            return f.read().strip()
    return arg


def _reset_out_dir() -> None:
    """Nettoie et recrée le dossier de sortie (write_file from scratch garanti)."""
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.makedirs(OUT_DIR, exist_ok=True)


async def main():
    parser = argparse.ArgumentParser(description="Coder isolation (multi-fichiers + draft)")
    parser.add_argument("task", nargs="?", default=None,
                        help="Description de tâche (ou @fichier pour charger un spec)")
    parser.add_argument("--draft", default=None,
                        help="Chemin vers un draft_*.md à injecter (ou @fichier)")
    parser.add_argument("--out", default=OUT_DIR,
                        help=f"Dossier de sortie (défaut: {OUT_DIR})")
    args = parser.parse_args()

    out_dir = args.out
    task_desc = _resolve_arg(args.task) if args.task else DEFAULT_TASK

    # Forcer l'UTF-8 (Windows + accents dans les prompts).
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # 🔒 Isolation stricte : repartir d'un dossier vierge à chaque run.
    _reset_out_dir()

    # Imports paresseux (après load_dotenv).
    from graph_orchestrator.config import settings
    from graph_orchestrator.nodes import build_fast_model, execute_coder_node

    # Reproduit l'instruction Drafter de workflows.py:570 à l'identique.
    draft_filename = None
    if args.draft:
        draft_content = _resolve_arg(args.draft)
        # Le draft est écrit à la racine du dossier de sortie (comme en prod).
        draft_filename = "draft_bubble_sort_viz_001.md"
        draft_path = os.path.join(out_dir, draft_filename)
        with open(draft_path, "w", encoding="utf-8") as f:
            f.write(draft_content)
        task_desc += (
            f"\n\n### PLAN D'IMPLÉMENTATION DE L'ARCHITECTE LOGICIEL\n"
            f"L'Architecte Logiciel a conçu un plan d'implémentation détaillé dans `{draft_filename}`.\n"
            f"⚠️ CE N'EST PAS DU CODE À RECOPIER — c'est un plan d'intention (structure, logique, edge cases).\n\n"
            f"INSTRUCTION : Lis ce plan avec `read_file(path=\"{draft_filename}\")`, puis IMPLÉMENTE-LE en codant "
            f"from-scratch avec tes outils (write_file pour chaque fichier, contenu COMPLET).\n"
            f"Applique tes SKILLS (frontend-design, coding) pendant l'implémentation pour enrichir le code.\n"
            f"Respecte scrupuleusement la logique décrite dans le plan (algorithmes, sync DOM, init).\n\n"
            f"🚫 NE recopie PAS le plan — IMPLÉMENTE-LE. Chaque fichier écrit UNE SEULE FOIS via write_file."
        )

    print("[*] Coder isolation — PRODUCTION (execute_coder_node)")
    print(f"    Dossier sortie  : {os.path.abspath(out_dir)} (isolé, nettoyé)")
    print(f"    Fichiers cibles : {DEFAULT_TARGET_FILES}")
    print(f"    Draft injecté   : {'OUI (' + draft_filename + ')' if draft_filename else 'NON'}")
    print(f"    Modèle FAST     : {settings.fast_model_id}")
    print(f"    Endpoint        : {settings.local_api_base}")
    print(f"    max_steps       : {settings.coder_max_steps} | tempér. : {settings.coder_temperature}")
    print(f"    STALL_DETECTOR  : {settings.stall_detector_enabled} (seuil {settings.stall_detector_threshold})")
    print(f"    LOOP_GUARD      : {settings.loop_guard_enabled} (seuil {settings.loop_guard_threshold})")
    print(f"    CAHIER CHARGES  : {task_desc[:80]}...")
    print()

    # Le dict de tâche reproduit exactement sub_dict du workflow.
    # target_files pointe dans NOTRE dossier dédié (chemins relatifs au cwd = out_dir).
    task = {
        "id": "coder_isolation",
        "content": task_desc,
        "target_files": DEFAULT_TARGET_FILES,
    }

    # 🔒 chdir vers out_dir AVANT execute_coder_node (comme _scoped_chdir en prod,
    # workflows.py). Sans ça, le Coder écrit dans os.getcwd() = racine du projet,
    # ce qui pollue le repo ET fausse les tests (ReadGate/F-67 lit les fichiers
    # de la racine au lieu du dossier isolé → réécritures en boucle).
    original_cwd = os.getcwd()
    os.chdir(out_dir)
    try:
        fast_model = build_fast_model(settings)
        result, metrics = await execute_coder_node(task, fast_model, settings)
    finally:
        os.chdir(original_cwd)

    # Affichage du résultat + métriques.
    print("\n" + "=" * 60)
    print("RÉSULTAT DU CODER — isolation (production)")
    print("=" * 60)
    if result is None:
        print("[!] Le Coder n'a pas retourné de résultat (crash ou timeout).")
    else:
        print(f"Statut  : {result.status}")
        print("Détails :")
        print(result.details or "(vide)")
    print("-" * 60)

    # Vérification post-run : les fichiers sont-ils créés ?
    print("Fichiers générés :")
    for fname in DEFAULT_TARGET_FILES:
        fpath = os.path.join(out_dir, fname)
        exists = os.path.exists(fpath)
        size = os.path.getsize(fpath) if exists else 0
        marker = "✓" if exists and size > 0 else "✗"
        print(f"  {marker} {fname:<14} {'OUI' if exists else 'NON':<4} {size:>6} octets")
    if metrics:
        print("-" * 60)
        print(f"Durée            : {metrics.duration_s:.1f}s")
        print(f"Modèle           : {metrics.model}")
        print(f"Tokens (in/out)  : {metrics.input_tokens} / {metrics.output_tokens}")
    print("=" * 60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
