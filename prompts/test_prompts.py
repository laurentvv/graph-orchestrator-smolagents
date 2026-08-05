"""Catalogue des prompts de test du graphe (workflow coding).

Chaque entrée est un dict au format ``tasks.json`` (section ``coding``) :
    {"id": str, "content": str, "target_files": list[str], "notes": str}

Pour lancer un test sur un de ces prompts, deux options :
  1. Copier le dict dans ``tasks.json`` → ``coding`` puis ``uv run agent_graph.py``.
  2. Script standalone (cf. debug/) qui charge ce catalogue et invoque le nœud
     voulu directement.

Convention de nommage des ids : <algo/outil>-<variante>. Le target_files reflète
la stratégie attendue (mono-fichier vs multi-fichiers) — c'est ce qui pousse
l'Architecte vers la bonne stratégie de découpage (F-29).

## Tests disponibles

| id                            | stratégie        | ce qu'il valide                                   |
|-------------------------------|------------------|---------------------------------------------------|
| bubble-sort-monofile          | 1 fichier HTML   | baseline : visualiseur + animation pas-à-pas      |
| bubble-sort-multifile         | 3 fichiers       | séparation html/css/js + wiring inter-fichiers    |
"""

from __future__ import annotations

# ==========================================
# Test 1 — Bubble Sort MONO-fichier (baseline)
# ==========================================
# Référence : le cas test historique (tasks.json coding[0] + Prompt-Vault Easy).
# Valide : animation pas-à-pas visible, slider vitesse, compteur, code couleur.
# C'est le test borné recommandé pour valider une modif du graphe (AGENTS.md §7).
BUBBLE_SORT_MONOFILE = {
    "id": "bubble-sort-monofile",
    "content": (
        "Crée un visualiseur d'algorithme Bubble Sort (tri à bulles) interactif en "
        "HTML/CSS/JS vanilla (un seul fichier index.html, pas de framework ni CDN externe). "
        "L'interface doit montrer un tableau de barres verticales (hauteurs proportionnelles "
        "aux valeurs) qui s'animent pendant le tri. Fonctionnalités attendues : "
        "(1) un bouton « Démarrer le tri » qui lance l'animation pas-à-pas de Bubble Sort "
        "avec un délai visible entre chaque comparaison/échange ; "
        "(2) un bouton « Réinitialiser » qui génère un nouveau tableau aléatoire ; "
        "(3) un curseur/slidebar pour régler la vitesse d'animation ; "
        "(4) un compteur affichant le nombre de comparaisons effectuées ; "
        "(5) un code couleur clair : barre en cours de comparaison = une couleur, "
        "barre déjà triée = une autre couleur, barres non encore traitées = couleur par défaut. "
        "Design soigné, responsive, avec un thème sombre (dark mode)."
    ),
    "target_files": ["index.html"],
    "notes": (
        "Baseline mono-fichier. Le piège classique : performStep() qui contient tout "
        "l'algorithme (double boucle) → animation instantanée (détecté par Tier 3). "
        "Valide la règle 9 Coder + Tier 3 Static Tester."
    ),
}

# ==========================================
# Test 2 — Bubble Sort MULTI-fichiers (html/css/js séparés)
# ==========================================
# Variante du test 1 en architecture multi-fichiers. Valide en PLUS :
#  - L'Architecte choisit la stratégie "multifile" (1 module = 1 fichier, F-29).
#  - Le Coder crée 3 fichiers cohérents et les wire (link CSS, script JS, ids DOM).
#  - Le Linter valide chaque fichier séparément (HTML, CSS, JS).
#  - Le Static Tester Tier 1 (node --check) valide le JS EXTERNE (extraction script[src] ?
#    non — le JS est dans script.js, pas inline → le Tier 1a actuel ne le valide PAS,
#    c'est un gap connu : le Static Tester n'extrait que le JS inline).
#  - Le Static Tester Tier 3 (temporal) détecte toujours l'animation instantanée
#    (la sonde DevTools charge index.html qui référence script.js → marche).
BUBBLE_SORT_MULTIFILE = {
    "id": "bubble-sort-multifile",
    "content": (
        "Crée un visualiseur d'algorithme Bubble Sort (tri à bulles) interactif en "
        "HTML/CSS/JS vanilla, réparti sur TROIS fichiers séparés : index.html "
        "(structure + lien vers le CSS et le JS), styles.css (tout le style), script.js "
        "(toute la logique). Pas de framework ni de CDN externe.\n"
        "\n"
        "L'interface doit montrer un tableau de barres verticales (hauteurs proportionnelles "
        "aux valeurs) qui s'animent pendant le tri. Fonctionnalités attendues :\n"
        "- un bouton « Démarrer le tri » qui lance l'animation pas-à-pas de Bubble Sort "
        "avec un délai visible entre chaque comparaison/échange ;\n"
        "- un bouton « Réinitialiser » qui génère un nouveau tableau aléatoire ;\n"
        "- un curseur/slidebar pour régler la vitesse d'animation ;\n"
        "- un compteur affichant le nombre de comparaisons effectuées ;\n"
        "- un code couleur clair : barre en cours de comparaison = une couleur, "
        "barre déjà triée = une autre couleur, barres non encore traitées = couleur par défaut.\n"
        "\n"
        "Contraintes techniques : index.html doit référencer styles.css via <link> et "
        "script.js via <script src>. Le JS accède au DOM via les ids définis dans le HTML. "
        "Design soigné, responsive, avec un thème sombre (dark mode)."
    ),
    "target_files": ["index.html", "styles.css", "script.js"],
    "notes": (
        "Variante multi-fichiers. Valide la stratégie multifile de l'Architecte (F-29), "
        "le wiring inter-fichiers du Coder (link/script src + cohérence ids DOM), et le "
        "Linting séparé HTML/CSS/JS. Le Tier 3 temporal marche (DevTools charge index.html). "
        "Gap connu : le Tier 1a (node --check) ne valide que le JS inline, pas script.js "
        "externe — à étendre si ce test échoue sur une erreur de syntaxe JS non détectée."
    ),
}

# ==========================================
# Catalogue exporté
# ==========================================
# Liste ordonnée. Ajoute ici les nouveaux prompts de test.
TEST_PROMPTS = [
    BUBBLE_SORT_MONOFILE,
    BUBBLE_SORT_MULTIFILE,
]

# Index par id pour accès direct (ex: by_id("bubble-sort-multifile")).
_BY_ID = {p["id"]: p for p in TEST_PROMPTS}


def by_id(prompt_id: str) -> dict:
    """Retourne le prompt de test par son id. Lève KeyError si introuvable."""
    if prompt_id not in _BY_ID:
        raise KeyError(
            f"Prompt de test '{prompt_id}' introuvable. Disponibles : "
            f"{list(_BY_ID)}"
        )
    return _BY_ID[prompt_id]


def to_coding_task(prompt_id: str) -> dict:
    """Retourne le prompt au format ``coding`` de tasks.json (sans 'notes').

    Prêt à injecter dans tasks.json ou à passer à un harness standalone :
        {"id": ..., "content": ..., "target_files": [...]}
    """
    p = by_id(prompt_id)
    return {
        "id": p["id"],
        "content": p["content"],
        "target_files": p["target_files"],
    }


if __name__ == "__main__":
    # Aperçu CLI : liste les prompts disponibles.
    print(f"Catalogue de {len(TEST_PROMPTS)} prompt(s) de test :\n")
    for p in TEST_PROMPTS:
        print(f"  • {p['id']}")
        print(f"    target_files : {p['target_files']}")
        print(f"    notes        : {p['notes'][:100]}...")
        print()
