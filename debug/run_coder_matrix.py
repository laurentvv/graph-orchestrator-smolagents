"""Matrice d'essais Coder isolé — compare plusieurs configs en séquence.

Lance execute_coder_node (vraie fonction prod) avec différents réglages pour
identifier la config optimale. Chaque essai écrit dans un dossier séparé
(debug/coder_matrix_out/essaiN/) et mesure : statut, taille fichiers,
tokens in/out, durée, qualité (présence du bug canvas).

Usage :
    uv run python debug/run_coder_matrix.py            # tous les essais
    uv run python debug/run_coder_matrix.py 2           # essai 2 seulement

Configs testées (matrice) :
    1. DevTools ON + skills + F-90 critères  (config E2E complète actuelle)
    2. DevTools OFF + skills + F-90 critères (Coder générateur pur, Tester validera)
    3. DevTools OFF + skills + SANS F-90     (baseline pré-F-90)
    4. DevTools OFF + SANS skills + SANS F-90 (Coder minimal nue)

But : trouver la config qui produit le meilleur code (bug canvas évité) SANS
exploser le contexte (DevTools = 20k tokens/step).
"""
import argparse
import os
import shutil
import sys

from dotenv import load_dotenv

load_dotenv()

OUT_BASE = "debug/coder_matrix_out"

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

# Critères visuels F-90 (produits par l'Architecte dans le run E2E).
VISUAL_CRITERIA = [
    "Au chargement de la page, >=10 barres colorées VISIBLES dans le canvas (un canvas vide = BUG)",
    "Le compteur affiche '0' au chargement",
    "Les boutons Demarrer/Reinitialiser sont visibles et cliquables",
    "Le slider vitesse est visible avec une valeur par defaut",
    "Le theme sombre est applique (fond sombre, texte clair)",
]

SKILLS_WEB = ["frontend-design", "devtools-preview"]


# Définition de la matrice d'essais.
# Chaque essai = (nom, env_overrides, task_extras, description).
MATRIX = [
    {
        "id": 1,
        "nom": "DevTools ON + skills + F-90",
        "env": {"CHROME_DEVTOOLS_ENABLED": "1"},
        "task_extra": {"skills": SKILLS_WEB, "visual_success_criteria": VISUAL_CRITERIA},
        "desc": "Config E2E complète (celle qui explose le contexte à 375k)",
    },
    {
        "id": 2,
        "nom": "DevTools OFF + skills + F-90",
        "env": {"CHROME_DEVTOOLS_ENABLED": "0"},
        "task_extra": {"skills": SKILLS_WEB, "visual_success_criteria": VISUAL_CRITERIA},
        "desc": "Coder générateur pur (le Tester fera la validation visuelle F-90)",
    },
    {
        "id": 3,
        "nom": "DevTools OFF + skills (sans F-90)",
        "env": {"CHROME_DEVTOOLS_ENABLED": "0"},
        "task_extra": {"skills": SKILLS_WEB},
        "desc": "Baseline pré-F-90 (skills seulement)",
    },
    {
        "id": 4,
        "nom": "DevTools OFF + nue (sans skills ni F-90)",
        "env": {"CHROME_DEVTOOLS_ENABLED": "0"},
        "task_extra": {},
        "desc": "Coder minimal absolu",
    },
]


def _check_canvas_bug(script_path: str) -> dict:
    """Vérifie la présence du bug canvas (barres dessinées hors champ).

    Détecte le pattern fautif : y=bottom + height grand → dessine vers le bas.
    Le CORRECT est : y = canvas.height - barHeight (haut de la barre depuis le bas).
    """
    if not os.path.exists(script_path):
        return {"script_present": False}
    with open(script_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    # Pattern correct : canvas.height - barHeight ou height - barHeight (variable).
    correct = ("canvas.height - " in content or "- barHeight" in content
               or "height - bar." in content)
    # Pattern CSS-dans-canvas (bug secondaire) : var(--...) dans fillStyle.
    css_in_canvas = "var(--" in content
    return {
        "script_present": True,
        "canvas_bug_likely": not correct,
        "css_in_canvas_bug": css_in_canvas,
        "lignes": len(content.splitlines()),
    }


async def run_essai(essai: dict) -> dict:
    """Lance un essai de la matrice et retourne les métriques."""
    eid = essai["id"]
    out_dir = os.path.join(OUT_BASE, f"essai{eid}")
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"ESSAI {eid}/4 : {essai['nom']}")
    print(f"  {essai['desc']}")
    print(f"{'='*60}")

    # Applique les overrides d'env AVANT l'import de config (load_dotenv déjà fait
    # en tête, mais os.environ prime si on l'override ici).
    for k, v in essai["env"].items():
        os.environ[k] = v
    # Recharge settings pour prendre en compte l'override.
    import importlib
    from graph_orchestrator import config as config_mod
    importlib.reload(config_mod)
    from graph_orchestrator.config import settings

    # Construit le task dict avec les extras.
    task = {
        "id": f"essai{eid}",
        "content": DEFAULT_TASK,
        "target_files": DEFAULT_TARGET_FILES,
        **essai["task_extra"],
    }

    print(f"  DevTools       : {os.environ.get('CHROME_DEVTOOLS_ENABLED', '?')}")
    print(f"  Skills         : {task.get('skills', [])}")
    print(f"  Critères F-90  : {len(task.get('visual_success_criteria', []))} critère(s)")
    print(f"  max_steps      : {settings.coder_max_steps}")
    print()

    original_cwd = os.getcwd()
    os.chdir(out_dir)
    try:
        from graph_orchestrator.nodes import build_fast_model, execute_coder_node
        fast_model = build_fast_model(settings)
        result, metrics = await execute_coder_node(task, fast_model, settings)
    except Exception as e:
        print(f"  [!] Exception : {e}")
        result, metrics = None, None
    finally:
        os.chdir(original_cwd)

    # Collecte résultats.
    fichiers = {}
    for fname in DEFAULT_TARGET_FILES:
        fpath = os.path.join(out_dir, fname)
        if os.path.exists(fpath):
            fichiers[fname] = os.path.getsize(fpath)
        else:
            fichiers[fname] = 0

    canvas_check = _check_canvas_bug(os.path.join(out_dir, "script.js"))

    return {
        "id": eid,
        "nom": essai["nom"],
        "statut": result.status if result else "CRASH",
        "details": (result.details[:200] if result and result.details else ""),
        "fichiers": fichiers,
        "canvas_check": canvas_check,
        "duree_s": metrics.duration_s if metrics else 0,
        "tokens_in": metrics.input_tokens if metrics else 0,
        "tokens_out": metrics.output_tokens if metrics else 0,
    }


def print_report(resultats: list):
    print(f"\n\n{'='*70}")
    print("RAPPORT COMPARATIF — Matrice d'essais Coder")
    print(f"{'='*70}")
    print(f"{'Essai':<6} {'Statut':<10} {'Durée':>7} {'Tok IN':>9} {'index':>7} "
          f"{'css':>6} {'js':>6} {'Canvas':<12} {'CSS-CV':<8}")
    print("-" * 70)
    for r in resultats:
        f = r["fichiers"]
        cc = r["canvas_check"]
        canvas_bug = "BUG!" if cc.get("canvas_bug_likely") else "OK"
        css_cv = "BUG!" if cc.get("css_in_canvas_bug") else "OK"
        print(f"{r['id']:<6} {r['statut']:<10} {r['duree_s']:>6.0f}s "
              f"{r['tokens_in']:>9,} {f.get('index.html',0):>7} {f.get('styles.css',0):>6} "
              f"{f.get('script.js',0):>6} {canvas_bug:<12} {css_cv:<8} {r['nom']}")
    print("-" * 70)
    print("Légende : Canvas=BUG! si y=bottom+height (hors champ). "
          "CSS-CV=BUG! si var(--) dans fillStyle canvas.")
    print()


async def main():
    parser = argparse.ArgumentParser(description="Matrice d'essais Coder")
    parser.add_argument("essai", nargs="?", type=int, default=None,
                        help="ID d'un essai spécifique (sinon : tous)")
    args = parser.parse_args()

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    essais = MATRIX if args.essai is None else [e for e in MATRIX if e["id"] == args.essai]
    resultats = []
    for essai in essais:
        r = await run_essai(essai)
        resultats.append(r)
        print(f"\n[Essai {r['id']}] statut={r['statut']} durée={r['duree_s']:.0f}s "
              f"tokens={r['tokens_in']:,}")

    if len(resultats) > 1:
        print_report(resultats)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
