"""F-82 — Skill Finder : recherche/installation sécurisée de skills depuis skills.sh.

Remplace le scaffold initial (tools.py) par une logique pure, testable et durcie :

  * **Sécurité** : gate double — allowlist d'auteurs configurable (env
    ``SKILL_FINDER_TRUSTED_AUTHORS``) **ET** prise en compte des marqueurs de
    confiance exposés par skills.sh (``safe``/``verified``/``audited`` → info ;
    ``unsafe``/``malicious``/``deprecated`` → blocage). ``subprocess`` en liste
    d'args (``shell=False``) avec validation regex stricte de chaque composant
    ``owner/repo/skill`` — défense en profondeur anti-injection (F-38/F-26).
  * **Persistance sans mutation de source** : un **manifeste durable**
    ``skills/installed-skills.json`` (lazy summary) est relu au démarrage par
    ``skills_loader`` pour étendre ``DYNAMIC_SKILL_RULES`` en mémoire. Fini la
    réécriture du fichier source ``skills_loader.py`` qui salissait ``git status``.
  * **Ligne regex dédiée multi-mots-clés** : chaque skill installé obtient une
    regex construite depuis sa ``description`` (frontmatter) + la requête + des
    hints optionnels de l'Architect (``extract_trigger_keywords``), identique en
    comportement aux règles codées en dur (ex: ``frontend-design``).
  * **Intégration pipeline F-57** : le skill installé atterrit dans
    ``skills/<name>/SKILL.md`` → automatiquement visible du catalogue
    (``parse_skill_meta``), du budget (``count_skill_tokens``/``enforce_skill_budget``)
    et du lazy loading (``load_skill``) — « comme les autres ».

Fail-open garanti : aucune fonction de ce module ne lève — un échec réseau/CLI
    dégrade silencieusement (le run n'est jamais crashé).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Racines (calcul local pour rester standalone à l'import — pas de import
# skills_loader au top-level, sinon cycle : skills_loader importe ce module).
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(_REPO_ROOT, "skills")
MANIFEST_PATH = os.path.join(SKILLS_DIR, "installed-skills.json")

# Allowlist d'auteurs par défaut (surchargeable via SKILL_FINDER_TRUSTED_AUTHORS).
DEFAULT_TRUSTED_AUTHORS = "vercel-labs,microsoft,google-labs-code,clerk,greensock"

# Marqueurs de confiance exposés par skills.sh dans la sortie de `skills find`.
# Best-effort : la sortie CLI n'est pas contractuelle, on tolère l'absence.
POSITIVE_MARKERS = ("safe", "verified", "audited", "trusted", "official")
NEGATIVE_MARKERS = ("unsafe", "malicious", "unverified", "deprecated", "archived", "malware")

# Validation stricte des composants avant tout appel subprocess (anti-injection).
# owner/repo/skill n'acceptent que des caractères sûrs ; la requête autorise
# aussi l'espace (recherche multi-mots possible).
_COMPONENT_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_QUERY_RE = re.compile(r"^[A-Za-z0-9 _.-]{1,64}$")

# Timeouts (séparés : le `add` télécharge, le `find` ne fait que lister).
FIND_TIMEOUT_S = 60.0
ADD_TIMEOUT_S = 120.0

# ANSI escape stripper (la sortie de `npx` est colorée).
_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
# Format d'un hit dans la sortie : owner/repo@skill.
_HIT_RE = re.compile(r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)@([A-Za-z0-9_:.-]+)")

# Stopwords FR/EN pour l'extraction de mots-clés (garder court mais utile).
_STOPWORDS = {
    # FR
    "les", "des", "une", "aux", "par", "sur", "pour", "avec", "sans", "dans",
    "est", "sont", "mais", "plus", "très", "cette", "cela", "ces", "ses", "mes",
    # EN
    "the", "and", "for", "with", "without", "from", "that", "this", "these",
    "those", "your", "you", "are", "not", "but", "all", "any", "use", "using",
    "used", "when", "will", "can", "may", "has", "have", "been", "into", "their",
    "skill", "agent", "agents", "description", "tool", "tools", "also",
    "should", "shall", "must",  # verbules fréquents dans les descriptions skills.sh
}


@dataclass
class SkillHit:
    """Un résultat de `npx skills find` : owner/repo@skill + signaux de confiance."""
    owner: str
    repo: str
    skill: str
    positive: bool = False  # marqueur safe/verified/audited détecté à proximité
    negative: bool = False  # marqueur unsafe/malicious/deprecated détecté


@dataclass
class InstalledSkill:
    """Un skill installé avec succès."""
    name: str   # nom du dossier sous skills/ (= partie @skill)
    source: str  # owner/repo@skill


# ===========================================================================
# Parsing de la sortie `npx skills find`
# ===========================================================================
def parse_skills_find_output(raw_stdout: str) -> List[SkillHit]:
    """Extrait les hits `owner/repo@skill` de la sortie de `npx skills find`.

    Strip les codes ANSI, détecte les marqueurs de confiance skills.sh dans une
    fenêtre autour de chaque hit (best-effort : la sortie CLI n'est pas stable).
    Pure, déterministe, ne lève jamais.
    """
    text = _ANSI_RE.sub("", raw_stdout or "")
    hits: List[SkillHit] = []
    for m in _HIT_RE.finditer(text):
        owner, repo, skill = m.group(1), m.group(2), m.group(3)
        # Fenêtre élargie autour du hit pour capter un badge/balisage de confiance.
        window = text[max(0, m.start() - 40): m.end() + 60].lower()
        positive = any(marker in window for marker in POSITIVE_MARKERS)
        negative = any(marker in window for marker in NEGATIVE_MARKERS)
        hits.append(SkillHit(owner, repo, skill, positive=positive, negative=negative))
    return hits


def is_trusted(hit: SkillHit, trusted_authors: List[str]) -> bool:
    """Gate de confiance double (spec F-82 : auteurs de confiance + signaux skills.sh).

    Logique (conservatrice — on télécharge du code externe) :
      * l'auteur DOIT être dans l'allowlist configurable (hard gate, spec
        « n'autoriser que les auteurs de confiance ») ;
      * un marqueur négatif skills.sh (unsafe/malicious/deprecated…) BLOQUE même
        un auteur de confiance (défense en profondeur) ;
      * un marqueur positif (safe/verified/audited) est enregistré (info) ;
      * l'absence de marqueur n'est pas bloquante (la CLI n'émet pas toujours de
        signal — repli allowlist seule, documenté).
    """
    if hit.owner not in trusted_authors:
        return False
    if hit.negative:
        return False
    return True


def parse_trusted_authors(value: Optional[str]) -> List[str]:
    """Parse une liste CSV d'auteurs depuis la valeur brute de settings/env."""
    raw = value or DEFAULT_TRUSTED_AUTHORS
    return [a.strip().lower() for a in raw.split(",") if a.strip()]


# ===========================================================================
# Installation (subprocess shell=False, args validés)
# ===========================================================================
def _run_skills_cli(args: List[str], timeout_s: float):
    """Exécute `npx -y skills <args...>`. Retourne (CompletedProcess | None, erreur | None).

    ``shell=False`` + liste d'args (anti-injection F-38/F-26). Cross-plateforme :
    sur Windows, ``npx`` est un shim ``.cmd`` qu'CreateProcess ne sait pas lancer
    directement → on passe par ``cmd.exe /c`` (les args sont validés par regex en
    amont, donc aucun métacaractère shell n'est possible). Fail-open (jamais lève).
    """
    if sys.platform.startswith("win"):
        cmd = ["cmd.exe", "/c", "npx", "-y", "skills"] + list(args)
    else:
        npx = shutil.which("npx") or "npx"
        cmd = [npx, "-y", "skills"] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            encoding="utf-8",
            errors="replace",
        )
        return result, None
    except Exception as e:  # fail-open : réseau/CLI/npx absent → None
        return None, str(e)


def install_skill(hit: SkillHit, timeout_s: float = ADD_TIMEOUT_S) -> Optional[InstalledSkill]:
    """Installe un skill via `npx -y skills add owner/repo@skill`.

    Valide chaque composant (owner/repo/skill) par regex stricte AVANT tout appel
    subprocess (défense en profondeur). Retourne l'InstalledSkill ou None sur
    échec/invalidité. Ne lève jamais.
    """
    for comp in (hit.owner, hit.repo, hit.skill):
        if not _COMPONENT_RE.match(comp):
            return None
    target = f"{hit.owner}/{hit.repo}@{hit.skill}"
    # `-y` (skills-level) skip les prompts de confirmation (non-interactif subprocess —
    # sans ça la CLI hang en attendant un tty). `--copy` copie de vrais fichiers au lieu
    # de symlink (le graphe lit skills/<name>/SKILL.md ; un symlink cassé = skill vide).
    # Découvert en validation live F82-10 : sans ces flags, l'install hang/timeout.
    result, err = _run_skills_cli(["add", target, "-y", "--copy"], timeout_s=timeout_s)
    if err is not None or result is None or result.returncode != 0:
        return None
    return InstalledSkill(name=hit.skill, source=target)


# ===========================================================================
# Mots-clés déclencheurs → ligne regex dédiée (point central F-82)
# ===========================================================================
def extract_trigger_keywords(
    description: Optional[str],
    query: Optional[str],
    hints: Optional[List[str]] = None,
    max_keywords: int = 8,
) -> List[str]:
    """Produit les mots-clés déclencheurs d'un skill installé.

    Sources fusionnées (ordre de priorité) :
      1. la ``query`` de recherche (toujours — c'est le terme ciblé) ;
      2. les ``hints`` émis par l'Architect/ReAct (il connaît le contexte tâche) ;
      3. les termes significatifs extraits de la ``description`` du skill
         (frontmatter) — stopwords FR/EN retirés, longueur ≥ 3.

    Dédoublonne (insensible à la casse) et plafonne à ``max_keywords`` pour garder
    la regex lisible. Pure, déterministe.
    """
    out: List[str] = []
    seen: set = set()

    def add(token: Optional[str]) -> None:
        t = (token or "").lower().strip()
        if len(t) < 2 or t in seen:
            return
        seen.add(t)
        out.append(t)

    add(query)
    for hint in (hints or []):
        add(hint)
    for tok in re.findall(r"[a-z0-9][a-z0-9_'-]+", (description or "").lower()):
        if len(tok) >= 3 and tok not in _STOPWORDS:
            add(tok)
    return out[:max_keywords]


def build_trigger_regex(keywords: List[str]) -> str:
    """Construit la regex ``\\b(kw1|kw2|...)\\b`` (même forme que DYNAMIC_SKILL_RULES).

    ``re.escape`` par mot-clé (défense : un mot-clé pourrait contenir un spécial).
    Si aucun mot-clé, retourne une regex no-op (ne matchera jamais) plutôt que de
    tout déclencher.
    """
    kws = [re.escape(k) for k in keywords if k]
    if not kws:
        return r"\b(__skill_finder_no_keyword__)\b"
    return r"\b(" + "|".join(kws) + r")\b"


# ===========================================================================
# Manifeste durable (lazy summary) — remplace la réécriture de skills_loader.py
# ===========================================================================
def _read_manifest() -> dict:
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_manifest(data: dict) -> None:
    try:
        os.makedirs(SKILLS_DIR, exist_ok=True)
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass  # fail-open : échec d'écriture ne crash pas le run


def register_installed_skill(
    name: str,
    description: str,
    triggers: List[str],
    regex: str,
    source: str,
) -> None:
    """Upsert d'une entrée skill dans le manifeste durable. Idempotent.

    Le manifeste est la source de vérité des skills installés pour les TÂCHES
    FUTURES (relu au démarrage → ``DYNAMIC_SKILL_RULES`` en mémoire). Pour le run
    courant, c'est la voie ``subtask.skills`` (F-57) qui couvre l'injection Coder.
    """
    if not name:
        return
    data = _read_manifest()
    data[name] = {
        "source": source or "",
        "description": description or "",
        "triggers": list(triggers or []),
        "regex": regex or "",
        "installed_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_manifest(data)


def load_dynamic_manifest() -> List[Tuple[str, str]]:
    """Lit le manifeste → liste de règles ``(regex, skill_name)``.

    Standalone (os+json uniquement) — appelé à l'import de ``skills_loader`` et
    après chaque installe réussie. Retourne ``[]`` si manifeste absent/illisible
    (no-op → 0 régression en fresh checkout).
    """
    data = _read_manifest()
    rules: List[Tuple[str, str]] = []
    for name, entry in data.items():
        if not isinstance(entry, dict):
            continue
        regex = entry.get("regex") or ""
        if regex and name:
            rules.append((regex, name))
    return rules


def refresh_dynamic_rules_in_memory() -> int:
    """Étend ``skills_loader.DYNAMIC_SKILL_RULES`` des règles du manifeste (same-run).

    Import lazy de ``skills_loader`` (évite le cycle à l'import). Dédoublonne les
    règles déjà présentes. Retourne le nb de règles ajoutées. Ne lève jamais.
    """
    try:
        from . import skills_loader  # noqa: WPS433 (lazy délibéré)
    except Exception:
        return 0
    existing = {(p, n) for p, n in skills_loader.DYNAMIC_SKILL_RULES}
    added = 0
    for pattern, name in load_dynamic_manifest():
        if (pattern, name) not in existing:
            skills_loader.DYNAMIC_SKILL_RULES.append((pattern, name))
            existing.add((pattern, name))
            added += 1
    return added


# ===========================================================================
# Orchestrateur — point d'entrée appelé par le @tool (tools.py) / le ReAct
# ===========================================================================
def search_and_install(
    query: str,
    author: Optional[str] = None,
    triggers: Optional[List[str]] = None,
    settings=None,
) -> str:
    """Recherche + installe un skill de confiance depuis skills.sh.

    Pipeline : parse ``skills find`` → gate de confiance (allowlist + marqueurs
    skills.sh) → ``skills add`` (shell=False, args validés) → extrait les
    mots-clés déclencheurs depuis la ``description`` du skill installé → inscrit
    la ligne regex dédiée dans le manifeste → refresh ``DYNAMIC_SKILL_RULES``.

    Retourne un **résumé** (consommé par l'Architect) ou un message d'erreur
    explicite. **Fail-open** : ne lève jamais.
    """
    try:
        if not query or not _QUERY_RE.match(query):
            return "Error: requête invalide (alphanumérique + espaces, ≤64)."

        trusted = parse_trusted_authors(
            getattr(settings, "skill_finder_trusted_authors", None)
            if settings is not None
            else None
        )
        # Si l'auteur est explicitement fourni mais n'est pas de confiance, on sort
        # vite (le ReAct peut proposer un auteur non fiable).
        if author and author not in trusted:
            return f"Error: auteur '{author}' pas dans l'allowlist de confiance ({', '.join(trusted)})."

        find_args = ["find", query]
        if author:
            find_args += ["--owner", author]
        result, err = _run_skills_cli(find_args, timeout_s=FIND_TIMEOUT_S)
        if err is not None or result is None:
            return f"Error: `skills find` indisponible ({err})."
        hits = parse_skills_find_output(result.stdout or "")

        for hit in hits:
            if not is_trusted(hit, trusted):
                continue
            if author and hit.owner != author:
                continue
            installed = install_skill(hit)
            if not installed:
                continue
            # Lecture du frontmatter du skill installé (lazy import pour break cycle).
            try:
                from .skills_loader import parse_skill_meta
                meta = parse_skill_meta(installed.name)
                description = (meta[1] if meta else "") or ""
            except Exception:
                description = ""
            keywords = extract_trigger_keywords(description, query, hints=triggers)
            regex = build_trigger_regex(keywords)
            register_installed_skill(installed.name, description, keywords, regex, installed.source)
            refresh_dynamic_rules_in_memory()
            marker = " [skills.sh: safe/verified]" if hit.positive else ""
            desc_short = (description[:140] + "…") if len(description) > 140 else description
            return (
                f"Skill installé : {installed.name} (source={installed.source}){marker}. "
                f"Mots-clés déclencheurs : {', '.join(keywords) if keywords else '(aucun)'}. "
                f"Description : {desc_short}"
            )
        return "Aucun skill trouvé d'un auteur de confiance correspondant à la requête."
    except Exception as e:  # fail-open absolu
        return f"Error: échec search_and_install ({e})."
