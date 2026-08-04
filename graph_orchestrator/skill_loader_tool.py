"""Outil smolagents ``load_skill`` — lazy loading niveau 2 (F-57, Priorité 10).

Blueprint : ``references/learn-claude-code/s07_skill_loading/code.py``.
Le Coder reçoit en system prompt le catalogue (name + description) de tous les
skills applicables (build_skills_catalog). Quand il a besoin du contenu complet
d'un skill LAZY (frontend-design, devtools-preview, python-health-audit), il
appelle ``load_skill(name)`` qui retourne le corps du SKILL.md.

Cela évite de réinjecter ~8k chars de skills à chacun des 12+ steps du Coder —
économie massive de tokens (cf. logs/run-20260804-114314 : context overflow
32891 > 32768 ctx observé sur l'ancien eager loading).

Déterministe, 0 LLM, 0 réseau. Réutilise ``load_skill_body`` du skills_loader.
"""

from smolagents import tool

from .skills_loader import load_skill_body


@tool
def load_skill(skill_name: str) -> str:
    """Charge le contenu complet d'un skill listé dans le catalogue des compétences.

    À utiliser pour les skills marqués (lazy) dans ### COMPÉTENCES À LA DEMANDE.
    Les skills EAGER sont déjà chargés dans ton prompt — ne PAS les recharger.

    Args:
        skill_name: Nom exact du skill tel que listé dans le catalogue
            (ex: "frontend-design", "devtools-preview", "python-health-audit").

    Returns:
        Le corps complet du SKILL.md (instructions détaillées), ou un message
        d'erreur si le skill est introuvable.
    """
    body = load_skill_body(skill_name)
    if not body:
        return (
            f"Skill '{skill_name}' introuvable ou vide. Vérifie le nom dans le "
            f"catalogue ### COMPÉTENCES À LA DEMANDE. Les noms valides sont ceux "
            f"marqués (lazy)."
        )
    return body
