"""Chargement et routage des skills vers les nœuds du graphe.

Architecture en 2 couches (cf. discussion DSPy-vs-config) :
  1. BASE_SKILLS (déterministe, statique) : chaque nœud reçoit TOUJOURS son socle
     de skills obligatoires (ex: le Coder a toujours 'coding' + 'file-creation').
     Aucun appel LLM : c'est un simple dict.
  2. Skills spécialisés (sélection dynamique) : selon le contenu de la tâche, on
     ajoute des skills à valeur conditionnelle (ex: 'frontend-design' pour du web,
     'python-health-audit' pour du Python).

Le contenu des SKILL.md est lu et nettoyé du frontmatter YAML avant injection,
pour économiser le contexte du LLM. Le corps (instructions + code inline) est
injecté directement dans le prompt — pas une liste de chemins à explorer (ce qui
dispersait le Coder vers l'exploration stérile des fichiers .md).
"""

import os
import re
from typing import List

# Racine des skills du projet.
SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")

# ==========================================
# Couche 1 — Base skills statiques par nœud
# ==========================================
# Socle obligatoire, toujours injecté. Gardé MINIMAL : chaque skill injecté
# alourdit le prompt du Coder à CHAQUE step (coûteux en CPU). On ne garde que
# l'essentiel : file-creation (garde anti-contenu-vide, critique) + coding
# (méthodo). windows-file-management retiré du socle (verbeux, peu utile au
# Coder qui crée des fichiers via write_file auto-mkdir).
BASE_SKILLS_BY_NODE: dict[str, List[str]] = {
    "coder": ["file-creation", "coding", "context7-research"],
    "tester": ["web-tester"],
    # architect : pas de skill socle (il planifie, ne code pas). Il reçoit
    # néanmoins un brief Context7 pré-fetché via fetch_context7_brief (dspy_nodes).
    "architect": [],
}


# ==========================================
# Couche 2 — Sélection dynamique de skills spécialisés
# ==========================================
# Mots-clés dans le contenu de la tâche → skills à valeur conditionnelle.
# Cette sélection est déterministe (regex), pas LLM — un DSPy SkillRouter serait
# pertinent si le catalogue de skills grossissait, mais pour ~5 skills la
# couche statique + heuristique suffit et évite latence/coût.
DYNAMIC_SKILL_RULES: List[tuple] = [
    # (regex sur le contenu de la tâche, skill à ajouter)
    (r"\b(html5?|css|landing\s*page|front[- ]?end|landing|portfolio|interface web|page web|responsive)\b",
     "frontend-design"),
    (r"\bpython\b", "python-health-audit"),
    # Libs/frameworks externes → force le skill context7-research (double sécurité
    # avec le socle). Le skill lui-même dit "ne cherche PAS pour du vanilla" : ces
    # libs sont précisément les cas où il FAUT consulter la doc (signature API).
    # Ponctuation officielle gérée (Chart.js, Three.js, Vue.js...).
    (r"\b(chart\.?js|d3\.?js|three\.?js|vue\.?js|react|svelte|solid\.?js|angular|"
     r"tailwind|bootstrap|material[- ]ui|antd|next\.?js|tauri|electron|"
     r"pandas|numpy|scipy|requests|fastapi|django|flask|sqlalchemy|"
     r"pytest|beautifulsoup|selenium|playwright)\b",
     "context7-research"),
]


def _strip_frontmatter(md: str) -> str:
    """Retire le frontmatter YAML (--- ... ---) d'un SKILL.md pour alléger le contexte."""
    return re.sub(r"^---\n.*?\n---\n*", "", md, count=1, flags=re.DOTALL).strip()


def load_skill_body(skill_name: str) -> str:
    """Lit le corps d'un skill par son nom, sans le frontmatter. Retourne '' si absent."""
    path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return _strip_frontmatter(f.read())
    except Exception:
        return ""


def select_skills_for_tester(task: dict, router_lang: str = None) -> List[str]:
    """Retourne les skills de test adaptés à la techno de la sous-tâche (Tester polyvalent).

    Contrairement au Coder (socle statique + regex sur le contenu), le Tester
    choisit son skill PRINCIPAL selon la techno détectée (détection redondante
    Router + extensions, via testers.detect_tech). Chaque techno a son skill de
    test dédié ; inconnu → web-tester (compatibilité arrière).

    Args:
        task: La sous-tâche (target_files, content...).
        router_lang: La techno détectée par le routeur (RouterOutput.language).
    """
    # Import local : testers importe skills_loader indirectement via les runners ;
    # on évite tout cycle d'import au niveau module.
    from .testers import detect_tech
    tech = detect_tech(task, router_lang)
    return [_TESTER_SKILL_BY_TECH.get(tech, "web-tester")]


# Techno canonique → skill de test dédié. Ajouter une techno = ajouter ici une
# entrée + créer le skill correspondant dans skills/<tech>-tester/SKILL.md.
_TESTER_SKILL_BY_TECH: dict[str, str] = {
    "web": "web-tester",
    "python": "python-tester",
}


def select_skills_for_coder(task_content: str) -> List[str]:
    """Retourne la liste des noms de skills à injecter dans le Coder pour cette tâche.

    Combine le socle statique (coder) et les skills spécialisés détectés
    dynamiquement dans le contenu de la tâche.
    """
    skills = list(BASE_SKILLS_BY_NODE["coder"])
    text = (task_content or "").lower()
    for pattern, skill_name in DYNAMIC_SKILL_RULES:
        if skill_name not in skills and re.search(pattern, text):
            skills.append(skill_name)
    return skills


def build_skills_block(task_content: str) -> str:
    """Construit le bloc de texte des skills à injecter dans le prompt du Coder.

    Injecte directement le CONTENU des skills (nettoyé), pas une liste de chemins.
    Évite ainsi que le Coder parte explorer les .md au lieu de coder.
    """
    names = select_skills_for_coder(task_content)
    blocks: List[str] = []
    for name in names:
        body = load_skill_body(name)
        if body:
            blocks.append(f"### SKILL: {name}\n{body}")
    if not blocks:
        return ""
    return "Voici tes COMPÉTENCES (skills) — applique leurs consignes directement :\n\n" + "\n\n".join(blocks)
