"""Lance le nœud Tester en isolation (sans tout le workflow).

Usage :
    uv run python run_tester.py [fichier_html] [description_tache]

Défauts :
    fichier_html      = le plus récent runs/*/index.html (ou bubble_sort/index.html)
    description_tache = spec Bubble Sort au format PromptRefiner (checklist F-46 active)

Permet d'itérer sur le tester (skill, prompt, checklist F-46) sans relancer les ~25 min
du workflow complet (Architect → Coder → Tester → Judge). Le tester reçoit EXACTEMENT
ce qu'il recevrait en production : le cahier des charges (original_content) + le fichier
à tester. La spec est au format structuré (## Fonctionnalités attendues) pour que la
checklist F-46 se déclenche (extract_functionalities).

Exemples :
    # Tester le HTML du dernier run avec la spec Bubble Sort par défaut :
    uv run python run_tester.py

    # Tester un fichier spécifique :
    uv run python run_tester.py runs/2026-08-02_1237_bubble_sort/index.html

    # Tester avec une spec personnalisée (doit contenir ## Fonctionnalités attendues) :
    uv run python run_tester.py mon_site/index.html "## Objectif\\nSite vitrine\\n\\n## Fonctionnalités attendues\\n- Hero section\\n- Formulaire contact\\n- Responsive"

    # Récupérer la spec réelle d'un run passé (depuis le checkpoint DuckDB) :
    # (voir debug/extract_spec.py — la spec y est persistée)
"""
import asyncio
import glob
import os
import sys

from dotenv import load_dotenv

load_dotenv()


# Spec au format PromptRefiner (structurée) — pas du texte libre. C'est CRUCIAL :
# c'est ce format qui déclenche extract_functionalities() → checklist F-46 obligatoire.
# Si on mettait du texte libre, extract_functionalities retournerait [] et le tester
# retomberait sur le mode historique (2-3 fonctionnalités testées au hasard).
DEFAULT_TASK = """## Objectif
Créer un visualiseur interactif de l'algorithme Bubble Sort (tri à bulles) en HTML/CSS/JS
vanilla (un seul fichier index.html). L'utilisateur doit voir le tri s'animer en temps réel.

## Fonctionnalités attendues
- Bouton « Démarrer le tri » qui lance l'animation pas-à-pas de Bubble Sort avec un délai visible entre chaque comparaison/échange
- Bouton « Réinitialiser » qui génère un nouveau tableau aléatoire
- Curseur/slidebar pour régler la vitesse d'animation
- Compteur affichant le nombre de comparaisons effectuées pendant le tri
- Code couleur clair : barre en cours de comparaison = une couleur, barre déjà triée = une autre couleur, barres non traitées = couleur par défaut

## Contraintes techniques
HTML5/CSS3/JS vanilla, un seul fichier index.html, pas de framework ni CDN externe.
Design soigné, responsive, thème sombre (dark mode).

## Critères de validation
- Le tableau est trié après exécution complète du tri (assertion sur l'ordre final)
- Les barres s'animent visuellement pendant le tri
- Le compteur de comparaisons affiche une valeur > 0 après le tri
"""


def find_latest_html() -> str:
    """Trouve le fichier index.html le plus récent dans runs/ (ou bubble_sort/)."""
    # Cherche dans runs/*/index.html (dossiers de run datés)
    candidates = sorted(glob.glob("runs/*/index.html"), key=os.path.getmtime, reverse=True)
    if candidates:
        return candidates[0]
    # Fallback : bubble_sort/index.html (legacy)
    if os.path.exists("bubble_sort/index.html"):
        return "bubble_sort/index.html"
    return ""


async def main():
    # Args CLI optionnels : fichier HTML + description de la tâche (spec).
    html_file = sys.argv[1] if len(sys.argv) > 1 else find_latest_html()
    # Accepte les specs multi-lignes passées en CLI (échappées avec \\n).
    task_spec = sys.argv[2].replace("\\n", "\n") if len(sys.argv) > 2 else DEFAULT_TASK

    if not html_file:
        print("[!] Aucun fichier HTML trouvé.")
        print("    Usage: uv run python run_tester.py [fichier.html] [spec]")
        print("    ou créez runs/<quelque_chose>/index.html")
        sys.exit(1)

    if not os.path.exists(html_file):
        print(f"[!] Fichier introuvable : {html_file}")
        sys.exit(1)

    # Forcer l'UTF-8 (Puppeteer/Windows + accents dans les prompts).
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # Prévisualise la checklist F-46 qui sera injectée au tester.
    from graph_orchestrator.requirements_checklist import extract_functionalities

    functionalities = extract_functionalities(task_spec)

    # Construire les settings + le modèle reasoning (comme le workflow).
    from graph_orchestrator.config import settings
    from graph_orchestrator.nodes import build_reasoning_model, execute_tester_node

    print(f"[*] Tester standalone")
    print(f"    Fichier testé     : {html_file} ({os.path.getsize(html_file)} octets)")
    print(f"    Modèle reasoning  : {settings.reasoning_model_id}")
    print(f"    Endpoint          : {settings.ollama_reasoning_api_base}")
    print(f"    DevTools activé   : {os.getenv('CHROME_DEVTOOLS_ENABLED', '1')}")
    print(f"    Audits parallèles : {os.getenv('AUDIT_PARALLEL', 'false')} (séquentiel GPU-local)")
    print(f"    max_steps tester  : 12 (GPU-local)")
    print()
    print(f"[*] Checklist F-46 extraite : {len(functionalities)} fonctionnalité(s) à tester")
    for i, f in enumerate(functionalities, 1):
        print(f"    {i}. {f}")
    if not functionalities:
        print("    (aucune — la spec n'a pas de section ## Fonctionnalités attendues)")
        print("    Le tester testera en mode historique (texte libre, couverture partielle).")
    print()

    # Le dictionnaire de tâche reproduit exactement sub_dict du workflow.
    # original_content = cahier des charges complet (propagé au tester en prod).
    # F-47 : pour simuler le mode re-test ciblé, passer --targeted (iteration=2 + fausses
    # réfutations). Sinon iteration=1 (mode complet, checklist F-46).
    targeted_mode = "--targeted" in sys.argv
    task = {
        "id": "standalone_test",
        "content": f"Teste le fichier {html_file} généré pour cette sous-tâche.",
        "target_files": [html_file],
        "original_content": task_spec,
        "router_lang": "javascript",
        "iteration": 2 if targeted_mode else 1,
        # F-47 : fausses réfutations pour forcer le mode ciblé (si --targeted).
        "refutations": (
            [{"content": "Bug signalé par le Judge (simulation --targeted) : "
                         "vérifier que toutes les fonctionnalités du cahier des charges "
                         "sont présentes ET fonctionnelles (pas seulement visuelles)."}]
            if targeted_mode else []
        ),
    }

    reasoning_model = build_reasoning_model(settings)
    result, metrics = await execute_tester_node(task, reasoning_model, settings)

    # Affichage du résultat.
    print("\n" + "=" * 60)
    print("RÉSULTAT DU TESTER")
    print("=" * 60)
    if result is None:
        print("[!] Le tester n'a pas retourné de résultat (crash, timeout, ou max_steps).")
        print("    Vérifiez les logs ci-dessus pour le détail.")
    else:
        status_icon = "✅" if result.status == "success" else "❌"
        print(f"Statut  : {status_icon} {result.status}")
        print(f"Détails :")
        print(result.details or "(vide)")
    print("=" * 60)

    if metrics:
        print(f"\nDurée : {metrics.duration_s:.1f}s | Modèle : {metrics.model}")


if __name__ == "__main__":
    asyncio.run(main())
