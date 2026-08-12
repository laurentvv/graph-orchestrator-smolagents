"""Chargeur de skills au format SKILL.md.

Un skill est un fichier Markdown qui fournit des instructions/patterns à injecter
dans le prompt d'un agent (paramètre `instructions` de CodeAgent/ToolCallingAgent).

Format attendu (inspiré de skills.sh) :
    ---
    name: nom-du-skill
    description: à quoi sert ce skill
    ---
    # Titre

    Instructions/patterns en Markdown...

Les skills sont chargés depuis le dossier `skills/` à la racine du projet.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

# Dossier racine des skills (relatif à la racine du projet)
SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def parse_skill_md(content: str) -> Optional[dict]:
    """Parse un fichier SKILL.md : extrait le frontmatter (name, description) + le corps.

    Retourne {"name", "description", "instructions"} ou None si invalide.
    """
    # Frontmatter YAML entre --- ... ---
    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)', content, re.DOTALL)
    if not fm_match:
        # Pas de frontmatter : on prend tout comme instructions, nom = premier H1
        h1 = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        name = h1.group(1).strip().lower().replace(" ", "-") if h1 else "unnamed"
        return {"name": name, "description": "", "instructions": content.strip()}

    frontmatter = fm_match.group(1)
    body = fm_match.group(2).strip()

    # Parse simple du frontmatter (clé: valeur)
    meta = {}
    for line in frontmatter.splitlines():
        m = re.match(r'^(\w+)\s*:\s*(.+)$', line)
        if m:
            meta[m.group(1).strip()] = m.group(2).strip().strip('"').strip("'")

    name = meta.get("name", "unnamed")
    description = meta.get("description", "")

    return {"name": name, "description": description, "instructions": body}


def load_skills(skills_dir: Optional[Path] = None) -> Dict[str, dict]:
    """Charge tous les skills depuis skills_dir (défaut: SKILLS_DIR).

    Retourne {name: {"description", "instructions"}}.
    """
    base = skills_dir or SKILLS_DIR
    skills: Dict[str, dict] = {}
    if not base.exists():
        return skills

    for skill_path in sorted(base.glob("*/SKILL.md")):
        try:
            content = skill_path.read_text(encoding="utf-8")
            parsed = parse_skill_md(content)
            if parsed:
                skills[parsed["name"]] = {
                    "description": parsed["description"],
                    "instructions": parsed["instructions"],
                    "path": str(skill_path),
                }
        except Exception as e:
            print(f"[skills] Erreur lecture {skill_path}: {e}")

    return skills


def get_skill_instructions(name: str, skills_dir: Optional[Path] = None) -> Optional[str]:
    """Retourne les instructions d'un skill par nom, ou None si absent."""
    skills = load_skills(skills_dir)
    skill = skills.get(name)
    return skill["instructions"] if skill else None


def list_skills(skills_dir: Optional[Path] = None) -> List[dict]:
    """Liste les skills disponibles (pour l'UI / health)."""
    skills = load_skills(skills_dir)
    return [
        {"name": name, "description": s["description"]}
        for name, s in skills.items()
    ]
