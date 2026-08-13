"""Grounding des findings du Judge — anti-hallucination de localisation. F-93.

PROBLÈME : le Judge (F-44/F-65) exige « LOCALISATION OBLIGATOIRE : chaque finding
DOIT citer ligne/fragment exact », mais aucun garde logiciel ne vérifiait que cette
localisation existe RÉELLEMENT dans le code source. Un LLM peut citer une ligne
inexistante ou un fragment inventé (hallucination de localisation) : le finding
était accepté tel quel → un ``critical`` inventé pouvait faire rejeter le code à
tort et gaspiller des itérations Coder sur un bug absent.

SOLUTION : vérification post-hoc déterministe (0 LLM) qui ancre chaque finding dans
le code source. Deux signaux complémentaires :
  (a) **line-range check** (déterministe, fort) : si le finding cite ``file:NN`` et
      que ``NN`` dépasse le nb de lignes du fichier → non ancré (ligne inexistante) ;
      si ``NN`` est dans les bornes → ancré (la localisation cite une ligne réelle).
  (b) **alignement flou de tokens** (port simplifié du ``WordAligner`` de langextract,
      fiche 39) : on extrait les fragments code-ish cités (spans backtick, chaînes
      d'identifiers ``a.b.c``) et on vérifie qu'au moins un s'ancre dans un fichier
      source via fenêtre glissante + couverture de tokens. Tolérant au formatage/
  whitespace/casse/singulier-pluriel.

Politique Option 1 (non-destructive, décision utilisateur F-93) : les findings non
ancrés sont **rétrogradés d'un cran** de sévérité (``critical→high``, …, ``low``
inchangé) + flagués ``[ungrounded: <raison>]`` dans leur description. Le verdict
``is_approved`` du LLM est **inchangé** : on calibre d'abord (mesure du taux de faux
positifs par le Meta-Analyste P15) avant d'automatiser une éventuelle inversion de
verdict. Non-destructif = ne peut jamais approuver à tort.

Complément de F-70 : ``judge_metrics`` = métriques quantitatives OFFLINE (P/R/F1) ;
``judge_diff`` = ancrage IN-DIFF ONLY du code montré au Judge ; ``judge_grounding``
= vérification d'intégrité QUALITATIVE des findings émis (en ligne, post-LLM).

Référence : ``references/langextract/langextract/resolver.py``. ÉCART CONSCIENT :
on porte l'algorithme **legacy** ``_fuzzy_align_extraction`` (fenêtre glissante
difflib, resolver.py:591-715) plutôt que le DP LCS ``_best_lcs_span`` (resolver.py:
1287). Plus simple, tout aussi fidèle au ``WordAligner``, et le bornage de fenêtre
``max_window = 2·len(needle)`` implique une densité ≥ ~0.5 — un seul seuil de
couverture (0.75, = ``_FUZZY_ALIGNMENT_MIN_THRESHOLD``) suffit, sans DP tightest-
span ni gate densité séparée. Pure stdlib (``re``/``math``/``difflib``/
``collections``) : on droppe la prise en charge unicode/regex de langextract (non
nécessaire pour du code ASCII) et la machinery exact-match/monotonic-DP (le besoin
est un oui/non « ce fragment existe-t-il », pas le placement d'intervalles
char-offset). Tokenizer word+digit seul (pas de ponctuation : bruit répétitif en
code, écart vs langextract dont le cas d'usage est le NLP médical).
"""

from __future__ import annotations

import collections
import difflib
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

from .models import CodeJudgeOutput, Finding, Severity


# ==========================================
# Constantes (langextract defaults, calibrage différé — pas de config)
# ==========================================

# Couverture : matched_tokens / len(needle_tokens). Un fragment de 4 tokens dont 3
# matchent = 0.75 → accepté. Port de ``_FUZZY_ALIGNMENT_MIN_THRESHOLD`` (0.75).
_GROUNDING_THRESHOLD: float = 0.75

# Bornage de fenêtre : on glisse des fenêtres source de taille ``len(needle)`` à
# ``2·len(needle)``. Toute match doit tenir dans une fenêtre ≤ 2× le needle →
# densité (matches/span) ≥ ~0.5 implicitement (3 matchs sur 6 tokens max). C'est
# l'équivalent fonctionnel de ``_FUZZY_ALIGNMENT_MIN_DENSITY`` (1/3) de langextract,
# obtenu sans DP tightest-span (cf. écart documenté en tête de module).
_MAX_WINDOW_RATIO: int = 2

# On ne tokenize que mots et chiffres (identifiers + valeurs). Les runs de
# ponctuation (``{ } ( ) ;``) sont du bruit répétitif en code : chaque ligne en
# contient, ils ne discriminant pas un fragment. Écart vs langextract (NLP médical
# où la ponctuation est informative).
_TOKEN_RE = re.compile(r"[^\W\d_]+|\d+")

# Échelle de sévérité pour la politique de rétrogradation (Option 1).
# Index 0 = le moins grave ; un finding ungrounded descend d'un cran vers "low".
_SEVERITY_ORDER: Tuple[Severity, ...] = ("low", "medium", "high", "critical")
_SEVERITY_INDEX: Dict[Severity, int] = {sev: i for i, sev in enumerate(_SEVERITY_ORDER)}

# Extensions de fichiers courantes — pour exclure les noms de fichiers de
# l'extraction de fragments code (``index.html``, ``app.py`` ne sont PAS du code
# à ancrer : ils sont gérés par le line-range check + ``_resolve_file``). Sans ce
# filtre, un nom de fichier dans ``location`` serait extrait comme chaîne
# d'identifiers puis échouerait à s'ancrer (false ungrounded) ou, pire, s'ancrerait
# par hasard dans un fichier du repo contenant les tokens ``index``/``html``.
_FILE_EXTS = frozenset({
    "html", "htm", "css", "js", "mjs", "cjs", "py", "ts", "tsx", "jsx", "vue",
    "svelte", "json", "md", "txt", "svg", "png", "jpg", "jpeg", "gif", "xml",
    "yml", "yaml", "toml", "csv", "sql", "rs", "go", "java", "c", "cpp", "h",
    "hpp", "sh", "bat", "ps1", "lock", "log", "db",
})

# Regex d'extraction de fragments / refs (appliquées sur location + description).
# Spans backtick (markdown code) — la forme la plus fiable (le Judge est invité à
# encadrer ses fragments par des backticks).
_BACKTICK_RE = re.compile(r"`([^`\n]{2,160})`")
# Chaîne d'identifiers pointés : ``bar.style.height``, ``document.getElementById``.
_CHAIN_RE = re.compile(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]+){1,6}")
# Réf fichier:ligne : ``script.js:42``, ``index.html # 12``, ``app.py:7``.
_FILE_LINE_RE = re.compile(r"([A-Za-z0-9_./\\-]+\.[A-Za-z]{1,6})\s*[:#]\s*(\d{1,5})")


def _looks_like_filename(frag: str) -> bool:
    """Un fragment ressemble-t-il à un nom de fichier (``index.html``, ``app.py``) ?

    On split sur ``./\\`` et on regarde si le dernier segment (strippé d'un ``:NN``
    éventuel) est une extension connue. ``bar.style.height`` → last=``height`` ∉ exts
    (code) ; ``index.html`` → last=``html`` ∈ exts (filename, à exclure).
    """
    parts = re.split(r"[./\\]", frag)
    if len(parts) >= 2:
        last = parts[-1].split(":")[0].lower()
        if last in _FILE_EXTS:
            return True
    return False


# ==========================================
# Port algorithme langextract (legacy sliding-window) — pure stdlib
# ==========================================

@lru_cache(maxsize=20000)
def _normalize_token(token: str) -> str:
    """Normalise un token pour la comparaison floue.

    Port de ``langextract.resolver._normalize_token`` : lowercase + light plural
    stemming (strip le ``s`` final si len>3 et non ``ss``). Rend la comparaison
    insensible à la casse et au singulier/pluriel (``bars`` ≈ ``bar``).
    """
    token = token.lower()
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        token = token[:-1]
    return token


def _raw_tokens(text: str) -> List[str]:
    """Tokenize en tokens word/digit (sans offsets — on ne remonte pas de span)."""
    if not text:
        return []
    return _TOKEN_RE.findall(text)


def fragment_is_grounded(
    source_text: str,
    needle_text: str,
    *,
    threshold: float = _GROUNDING_THRESHOLD,
) -> bool:
    """Un fragment (``needle``) est-il ancré dans le texte source ?

    Port simplifié de ``langextract.resolver.WordAligner._fuzzy_align_extraction``
    (variante legacy fenêtre glissante). Glisse des fenêtres source de taille
    ``len(needle)`` à ``_MAX_WINDOW_RATIO·len(needle)`` ; pour chaque fenêtre dont
    l'intersection de multiset avec le needle atteint le seuil de couverture, on
    calcule le ratio via ``difflib.SequenceMatcher`` (matches / len(needle)).

    Args:
        source_text: Contenu du fichier source (ou concaténation).
        needle_text: Fragment cité à ancrer (extrait de location+description).
        threshold: Couverture minimale matched/needle (défaut 0.75).

    Returns:
        ``True`` si ≥1 fenêtre atteint le seuil, ``False`` sinon. ``needle`` vide →
        ``True`` (fail-open : rien à valider). Source vide + needle non vide →
        ``False``.
    """
    needle = [_normalize_token(t) for t in _raw_tokens(needle_text)]
    len_e = len(needle)
    if len_e == 0:
        return True  # fail-open : fragment vide, rien à ancrer
    source = [_normalize_token(t) for t in _raw_tokens(source_text)]
    n = len(source)
    if n == 0:
        return False

    max_window = min(n, max(len_e, len_e * _MAX_WINDOW_RATIO))
    needle_counts = collections.Counter(needle)
    # Pré-check de pruning (miroir langextract) : intersection de multiset.
    min_overlap = max(1, int(len_e * threshold))
    matcher = difflib.SequenceMatcher(autojunk=False, b=needle)

    for window_size in range(len_e, max_window + 1):
        for start in range(0, n - window_size + 1):
            window = source[start:start + window_size]
            # Pruning : pas assez de tokens en commun → SequenceMatcher inutile.
            if (needle_counts & collections.Counter(window)).total() < min_overlap:
                continue
            matcher.set_seq1(window)
            matches = sum(sz for _, _, sz in matcher.get_matching_blocks())
            if matches / len_e >= threshold:
                return True
    return False


# ==========================================
# Lecture source + résolution fichier + extraction fragments
# ==========================================

def read_source_files(paths: Sequence[str]) -> Dict[str, str]:
    """Lit le contenu des fichiers source (fail-open, miroir ``judge_diff``).

    Un fichier absent/illisible est silencieusement sauté (ne brique jamais le
    grounding). Retourne ``{chemin: contenu}``.
    """
    out: Dict[str, str] = {}
    for file_path in paths:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                out[file_path] = f.read()
        except Exception:
            pass
    return out


def _resolve_file(fname: str, source_files: Dict[str, str]) -> Optional[str]:
    """Résout un nom de fichier (depuis location) vers une clé de source_files.

    Match par basename (insensible à la casse), puis par sous-chaîne (fallback).
    Retourne ``None`` si rien ne matche.
    """
    if not fname:
        return None
    base = os.path.basename(fname).lower()
    for path in source_files:
        if os.path.basename(path).lower() == base:
            return path
    fl = fname.lower()
    for path in source_files:
        pl = path.lower()
        if fl in pl or pl in fl:
            return path
    return None


def _extract_file_line_refs(text: str) -> List[Tuple[str, int]]:
    """Extrait les refs ``file.ext:NN`` d'un texte → liste (filename, lineno)."""
    refs: List[Tuple[str, int]] = []
    for m in _FILE_LINE_RE.finditer(text or ""):
        try:
            refs.append((m.group(1), int(m.group(2))))
        except ValueError:
            pass
    return refs


def extract_code_fragments(text: str) -> List[str]:
    """Extrait les fragments code-ish cités dans un texte (location+description).

    Cible les spans backtick (markdown code) et les chaînes d'identifiers pointés
    (``a.b.c``). Clef anti-faux-positif : on n'extrait PAS la prose libre — aligner
    une description en langage naturel contre du code ferait plonger la couverture
    (mots du français/anglais non présents dans le source). On ne teste que du
    contenu code, qui est par construction discriminant.

    Returns:
        Liste de fragments (dedup, ≥3 chars, ponctuation de bord strippée).
    """
    if not text:
        return []
    found: List[str] = []
    for m in _BACKTICK_RE.finditer(text):
        found.append(m.group(1).strip())
    for m in _CHAIN_RE.finditer(text):
        found.append(m.group(0).strip())
    seen = set()
    out: List[str] = []
    for f in found:
        f = f.strip().strip(".,;:()[]\"'")
        if len(f) < 3:
            continue
        if _looks_like_filename(f):
            # Les filenames sont gérés par line-range check + _resolve_file, pas par
            # l'alignement de fragments (sinon faux ungrounded/grounded — cf. _FILE_EXTS).
            continue
        key = f.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


# ==========================================
# Data models locaux (pas de churn models.py)
# ==========================================

@dataclass
class FindingGrounding:
    """Résultat du grounding d'UN finding."""
    finding: Finding
    grounded: bool
    matched_file: Optional[str]
    reason: str


@dataclass
class GroundingReport:
    """Résultat agrégé du grounding d'une liste de findings."""
    total: int
    grounded_count: int
    ungrounded_count: int
    items: List[FindingGrounding] = field(default_factory=list)


# ==========================================
# Logique métier : grounding d'un finding
# ==========================================

def ground_finding(
    finding: Finding,
    source_files: Dict[str, str],
) -> FindingGrounding:
    """Ancre UN finding dans les fichiers source.

    Stratégie (fail-open à chaque niveau pour ne jamais bricker sur un cas tordu) :
      1. **line-range check** : si une réf ``file:NN`` est citée et résout un
         fichier existant — ``NN`` hors-bornes → non ancré (signal fort) ; ``NN``
         dans les bornes → ancré (la localisation pointe une ligne réelle).
      2. **fragments** : extracte les fragments code de ``location + description``.
         Aucun fragment → ancré (prose-only, fail-open : on ne sait pas valider).
         Sinon : ancré si ≥1 fragment s'ancre dans un fichier (résolu d'abord,
         puis tous les fichiers en fallback indulgent).
    """
    location = finding.location or ""
    text = f"{location} {finding.description or ''}"

    # (1) line-range check
    for fname, lineno in _extract_file_line_refs(text):
        resolved = _resolve_file(fname, source_files)
        if resolved is None:
            continue
        nlines = source_files[resolved].count("\n") + 1
        if lineno > nlines:
            return FindingGrounding(
                finding, False, resolved,
                f"ligne {lineno} > {nlines} lignes dans {os.path.basename(resolved)}",
            )
        # Ligne dans les bornes : localisation valide (la ligne citée existe).
        return FindingGrounding(
            finding, True, resolved,
            f"ligne {lineno} valide dans {os.path.basename(resolved)}",
        )

    # (2) fragments code
    fragments = extract_code_fragments(text)
    if not fragments:
        # Prose-only : rien à ancrer, on ne peut ni valider ni invalider → fail-open.
        return FindingGrounding(finding, True, None, "aucun fragment code (prose-only, fail-open)")

    resolved = _resolve_file(location, source_files)
    # Fichier résolu en priorité, puis tous (indulgent : réduit les faux « ungrounded »).
    candidate_paths: List[str] = []
    if resolved:
        candidate_paths.append(resolved)
    for p in source_files:
        if p != resolved:
            candidate_paths.append(p)

    for frag in fragments:
        for path in candidate_paths:
            src = source_files.get(path, "")
            if src and fragment_is_grounded(src, frag):
                return FindingGrounding(
                    finding, True, path,
                    f"fragment ancré dans {os.path.basename(path)}",
                )

    return FindingGrounding(
        finding, False, None,
        f"fragment non trouvé dans aucun fichier source ({len(fragments)} testé(s))",
    )


def ground_findings(
    findings: Sequence[Finding],
    source_files: Dict[str, str],
) -> GroundingReport:
    """Ancre une liste de findings. Fail-open global si source_files vide.

    Args:
        findings: Les ``CodeJudgeOutput.findings`` (ou ``SecurityOutput.findings``).
        source_files: ``{chemin: contenu}`` des fichiers source du run.

    Returns:
        ``GroundingReport`` (counts + détail par finding). Sans source lisible,
        tout est marqué ancré (fail-open : on ne rejette jamais à l'aveugle).
    """
    if not source_files:
        items = [
            FindingGrounding(f, True, None, "aucun fichier source lisible (fail-open)")
            for f in findings
        ]
        return GroundingReport(
            total=len(items),
            grounded_count=len(items),
            ungrounded_count=0,
            items=items,
        )
    items = [ground_finding(f, source_files) for f in findings]
    grounded = sum(1 for it in items if it.grounded)
    return GroundingReport(
        total=len(items),
        grounded_count=grounded,
        ungrounded_count=len(items) - grounded,
        items=items,
    )


# ==========================================
# Politique Option 1 — rétrograder + flaguer, verdict intact
# ==========================================

def _downgrade_severity(sev: Severity) -> Severity:
    """Baisse la sévérité d'un cran vers ``low`` (politique Option 1, non-destructive)."""
    i = _SEVERITY_INDEX.get(sev, 0)
    return _SEVERITY_ORDER[max(0, i - 1)]


def apply_grounding(verdict: CodeJudgeOutput, report: GroundingReport) -> CodeJudgeOutput:
    """Applique la politique Option 1 : rétrograde + flague les findings non ancrés.

    Politique **non-destructive** (décision utilisateur F-93) :
    - chaque finding non ancré voit sa sévérité baissée d'un cran (``critical→high``,
      ``high→medium``, ``medium→low``, ``low`` inchangé) ET un marqueur
      ``[ungrounded: <raison>]`` appendé à sa description (visible Meta-Analyste) ;
    - les findings ancrés sont conservés à l'identique ;
    - **``is_approved`` est inchangé** (le verdict du LLM prime ; on calibre avant
      d'automatiser une inversion éventuelle).

    Reconstruit le verdict via ``model_copy`` (ne mute pas l'input). Si 0 finding
    non ancré, retourne le verdict à l'identique (no-op).
    """
    if not report.items or report.ungrounded_count == 0:
        return verdict

    new_findings: List[Finding] = []
    for item in report.items:
        f = item.finding
        if item.grounded:
            new_findings.append(f)
            continue
        new_findings.append(Finding(
            severity=_downgrade_severity(f.severity),
            category=f.category,
            location=f.location,
            description=f"{f.description} [ungrounded: {item.reason}]",
            suggestion=f.suggestion,
        ))
    # is_approved / final_feedback / task_id inchangés (update findings seulement).
    return verdict.model_copy(update={"findings": new_findings})
