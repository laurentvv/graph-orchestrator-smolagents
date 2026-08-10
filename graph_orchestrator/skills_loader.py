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
    # architect : pas de skill socle
    "architect": ["to-spec"],
}


# ==========================================
# Couche 2 — Sélection dynamique de skills spécialisés
# ==========================================
# Pattern des libs/frameworks externes — SOURCE UNIQUE DE VÉRITÉ.
# Utilisé à 2 endroits : (1) règle dynamique context7-research ci-dessous,
# (2) garde-fou _mentions_external_lib dans dspy_nodes (pré-fetch Architect).
# Centralisé ici pour éviter la dérive (Kilo review : éviter la duplication).
EXTERNAL_LIB_PATTERN = (
    r"\b("
    r"chart\.?js|d3\.?js|three\.?js|vue\.?js|react|svelte|solid\.?js|angular|nuxt\.?js|astro|remix|nest\.?js|express|"
    r"tailwind|bootstrap|material[- ]ui|antd|shadcn|radix|framer[- ]?motion|gsap|bulma|chakra[- ]ui|"
    r"next\.?js|tauri|electron|vite|webpack|rollup|esbuild|parcel|"
    r"pandas|numpy|scipy|requests|fastapi|django|flask|sqlalchemy|pydantic|celery|"
    r"pytest|beautifulsoup|selenium|playwright|jest|vitest|cypress|puppeteer|mocha|chai|"
    r"dspy|langchain|llama[- ]index|huggingface|transformers|pytorch|torch|tensorflow|scikit[- ]learn|keras|"
    r"prisma|drizzle|supabase|firebase|mongoose|sequelize|typeorm|"
    r"redux|zustand|react[- ]query|trpc|graphql|apollo"
    r")\b"
)

# Mots-clés dans le contenu de la tâche → skills à valeur conditionnelle.
# Cette sélection est déterministe (regex), pas LLM — un DSPy SkillRouter serait
# pertinent si le catalogue de skills grossissait, mais pour ~5 skills la
# couche statique + heuristique suffit et évite latence/coût.
DYNAMIC_SKILL_RULES: List[tuple] = [
    # (regex sur le contenu de la tâche, skill à ajouter)
    (r"\b(html5?|css|landing\s*page|front[- ]?end|landing|portfolio|interface web|page web|responsive)\b",
     "frontend-design"),
    # F-45 : auto-validation visuelle Chrome DevTools sur les tâches web (même
    # pattern que frontend-design). Le skill documente le workflow navigate→screenshot
    #→console→corriger. Le preview n'agit que si le serveur DevTools est dispo
    # (sinon cdt_tools=[] et le prompt n'affiche pas la section preview).
    (r"\b(html5?|css|landing\s*page|front[- ]?end|landing|portfolio|interface web|page web|responsive)\b",
     "devtools-preview"),
    (r"\b(animation|visualiseur|visualizer|interactif|jeu|canvas)\b", "web-animation"),
    (r"\b(animation|visualiseur|visualizer|interactif|jeu|canvas)\b", "animation-vocabulary"),
    (r"\b(animation|visualiseur|visualizer|interactif|jeu|canvas)\b", "improve-animations"),
    (r"\b(animation|visualiseur|visualizer|interactif|jeu|canvas)\b", "review-animations"),
    (r"\bpython\b", "python-health-audit"),
    # Libs/frameworks externes → force le skill context7-research (double sécurité
    # avec le socle). Le skill lui-même dit "ne cherche PAS pour du vanilla" : ces
    # libs sont précisément les cas où il FAUT consulter la doc (signature API).
    # Ponctuation officielle gérée (Chart.js, Three.js, Vue.js...).
    (EXTERNAL_LIB_PATTERN, "context7-research"),
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

    .. deprecated:: F-57
        Remplacé par ``build_eager_skills_block`` + ``build_skills_catalog`` (lazy
        loading). Conservé pour rétro-compat (opt-out SKILL_LAZY_LOADING_ENABLED=false
        + futurs usages). Le Coder en mode lazy ne l'utilise plus.
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


# ==========================================
# F-57 : Sélection conditionnelle de skills (contextuelle)
# ==========================================
# ARCHITECTURE RÉVISÉE (retour d'expérience run F-57 du 2026-08-04) : le lazy loading
# via tool ``load_skill`` a échoué — le Coder (9B) n'appelait pas l'outil, perdant la
# connaissance des skills conditionnels (frontend-design, devtools-preview). Un petit
# LLM ne « décide » pas consciemment de consulter un skill : il code directement.
#
# NOUVEAU DESIGN : sélection contextuelle déterministe. Les skills sont injectés en
# corps complet UNIQUEMENT si la tâche les justifie (regex sur le contenu). Plus de
# tool, plus de catalogue metadata, plus de décision du modèle — le code Python choisit
# et injecte directement. C'est fiable à 100% (pas d'oubli possible) et plus simple.
#
# L'économie de tokens vient de la SÉLECTION (un skill Python n'est pas injecté sur une
# tâche web), pas du lazy loading. Le seul inconvénient vs eager-total : les skills
# conditionnels applicables sont lus à chaque step (mais ils ne le sont QUE si la regex
# matche — sur une tâche web, frontend-design est légitime à chaque step).

# Skills TOUJOURS injectés (socle critique). Failure mode fatal si oublié.
ALWAYS_SKILLS_CODER: set = {"file-creation", "coding", "context7-research", "web-animation"}


def _parse_frontmatter_yaml(text: str) -> dict:
    """Parse le frontmatter YAML d'un SKILL.md. Retourne un dict (vide si absent/malformé).

    Version défensive : utilise yaml.safe_load si dispo, sinon repli regex (name/desc).
    Ne lève jamais d'exception.
    """
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    fm_block = parts[1]
    try:
        import yaml
        meta = yaml.safe_load(fm_block) or {}
        return meta if isinstance(meta, dict) else {}
    except Exception:
        # Repli défensif : regex simple sur name/description (frontmatter plat).
        meta: dict = {}
        for key in ("name", "description"):
            m = re.search(rf"^{key}:\s*(.+)$", fm_block, re.MULTILINE)
            if m:
                meta[key] = m.group(1).strip().strip('"').strip("'")
        return meta


def parse_skill_meta(skill_name: str):
    """Retourne (name, description) du frontmatter d'un skill, ou None si absent.

    Ne lit QUE le frontmatter (pas le corps) — utile pour lister un catalogue sans
    alourdir le contexte. Conservé pour les nœuds DSPy (PromptRefiner capabilities).
    """
    path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return None
    meta = _parse_frontmatter_yaml(raw)
    name = meta.get("name", skill_name)
    desc = meta.get("description", "")
    return (name, desc)


# ==========================================
# F-57 : Comptage de tokens + budget (anti-saturation du Coder)
# ==========================================
# L'Architect sélectionne les skills à injecter au Coder. Sans budget, il pourrait
# en sélectionner trop (ex: 5 skills × 4000 tokens = 20k tokens → saturation du
# contexte 32k du Qwen 9B). On compte les tokens de chaque skill (tiktoken cl100k_base,
# approximation proche des modèles modernes) et on plafonne la sélection.
#
# Le budget est partagé entre le socle ALWAYS (toujours injecté) et les skills
# conditionnels. Si l'Architect dépasse, on rogne en gardant le socle + les skills
# les plus petits d'abord (maximise le nombre de skills sous le budget).

# Cache des comptes de tokens par skill (lecture disque + tokenize au 1er appel, puis RAM).
_SKILL_TOKENS_CACHE: dict[str, int] = {}


def _get_tokenizer():
    """Retourne un tokenizer tiktoken (cl100k_base). Repli sur estimation chars/4 si absent."""
    try:
        import tiktoken
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None  # signal pour le repli chars/4


def count_skill_tokens(skill_name: str) -> int:
    """Retourne le nombre de tokens (cl100k_base) du corps d'un skill, ou estimation chars/4.

    Mémoïsé dans ``_SKILL_TOKENS_CACHE`` (lecture disque + tokenize au 1er appel seulement).
    Repli défensif : si tiktoken absent, estimation grossière len(body) // 4.
    """
    if skill_name in _SKILL_TOKENS_CACHE:
        return _SKILL_TOKENS_CACHE[skill_name]
    body = load_skill_body(skill_name)
    if not body:
        _SKILL_TOKENS_CACHE[skill_name] = 0
        return 0
    enc = _get_tokenizer()
    if enc is not None:
        tokens = len(enc.encode(body))
    else:
        tokens = len(body) // 4  # estimation grossière (1 token ≈ 4 chars en anglais/code)
    _SKILL_TOKENS_CACHE[skill_name] = tokens
    return tokens


def enforce_skill_budget(
    selected_skills: List[str],
    budget_tokens: int = 8000,
    always_skills: set = None,
) -> List[str]:
    """Rogne la sélection de skills pour rester sous le budget de tokens.

    Garantit que la somme des tokens des skills retenus ne dépasse pas ``budget_tokens``.
    Le socle ``always_skills`` est TOUJOURS conservé (même s'il dépasse le budget à lui
    seul — ce serait un bug de config, pas de sélection). Les skills conditionnels sont
    triés par taille croissante puis ajoutés tant que le budget le permet (stratégie
    « petits d'abord » : maximise le nombre de skills utiles sous le budget).

    Args:
        selected_skills: Liste des skills sélectionnés par l'Architect.
        budget_tokens: Budget maximum en tokens (défaut 8000, ~24% du contexte Qwen 9B 32k).
        always_skills: Socle toujours conservé (défaut ALWAYS_SKILLS_CODER).

    Returns:
        Liste rognée préservant l'ordre d'origine pour les skills retenus.
    """
    if always_skills is None:
        always_skills = ALWAYS_SKILLS_CODER
    # 1. Séparer le socle (toujours gardé) des skills conditionnels.
    always = [s for s in selected_skills if s in always_skills]
    conditional = [s for s in selected_skills if s not in always_skills]
    # 2. Compter les tokens du socle.
    used = sum(count_skill_tokens(s) for s in always)
    # 3. Trier les conditionnels par taille croissante (petits d'abord = plus de skills).
    conditional_sorted = sorted(conditional, key=count_skill_tokens)
    # 4. Ajouter tant que le budget le permet.
    kept_conditional: List[str] = []
    for s in conditional_sorted:
        tok = count_skill_tokens(s)
        if used + tok <= budget_tokens:
            kept_conditional.append(s)
            used += tok
    # 5. Reconstruire en préservant l'ordre d'origine (pour la lisibilité du prompt).
    kept_set = set(always) | set(kept_conditional)
    return [s for s in selected_skills if s in kept_set]


def build_skills_catalog(task_content: str) -> str:
    """Construit le catalogue des skills applicables (name + description uniquement).

    Conservé pour rétro-compat (nœuds DSPy, tests). Le Coder n'utilise plus ce
    catalogue depuis la révision F-57 — il reçoit directement les corps complets
    via ``build_conditional_skills_block``.
    """
    names = select_skills_for_coder(task_content)
    lines: List[str] = []
    for name in names:
        meta = parse_skill_meta(name)
        if meta is None:
            continue
        skill_name, desc = meta
        tag = "always" if name in ALWAYS_SKILLS_CODER else "conditional"
        line = f"- **{skill_name}** ({tag})"
        if desc:
            line += f": {desc}"
        lines.append(line)
    if not lines:
        return ""
    return "### COMPÉTENCES DISPONIBLES\n\n" + "\n".join(lines)


def build_conditional_skills_block(task_content: str) -> str:
    """Construit le bloc des skills à injecter dans le Coder (corps complet).

    Sélection contextuelle déterministe : injecte le corps complet des skills
    ALWAYS (socle critique) + des skills CONDITIONNELS dont la regex matche le
    contenu de la tâche. Plus de tool ``load_skill`` — l'injection est directe,
    fiable à 100% (un petit LLM n'oublie jamais un skill applicable).

    C'est l'évolution du F-57 original : le lazy loading via tool échouait (le Coder
    9B n'appelait pas ``load_skill``), on revient à une injection directe mais
    SÉLECTIONNÉE par regex (pas tout-eager). Économie : un skill Python n'est pas
    injecté sur une tâche web, et vice-versa.
    """
    names = select_skills_for_coder(task_content)
    names = enforce_skill_budget(names, budget_tokens=16000)
    blocks: List[str] = []
    for name in names:
        body = load_skill_body(name)
        if body:
            blocks.append(f"### SKILL: {name}\n{body}")
    if not blocks:
        return ""
    return "Voici tes COMPÉTENCES (skills) — applique leurs consignes directement :\n\n" + "\n\n".join(blocks)


# Alias rétro-compat (tests, futur code) — l'ancien build_eager_skills_block devient
# un alias de build_conditional_skills_block (même comportement : injecte tout ce qui
# est applicable, pas seulement le socle).
EAGER_SKILLS_CODER = ALWAYS_SKILLS_CODER  # alias déprécié, conservé pour les tests existants


def build_eager_skills_block(task_content: str) -> str:
    """Alias déprécié de build_conditional_skills_block (rétro-compat tests).

    Historiquement (F-57 v1) n'injectait que le socle EAGER. Depuis la révision F-57
    (auto-injection), injecte TOUS les skills applicables — utilisez
    build_conditional_skills_block directement.
    """
    return build_conditional_skills_block(task_content)
