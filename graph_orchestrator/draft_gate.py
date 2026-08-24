"""Gate déterministe entre le Drafter et le Coder (F-91).

L'Algorithm Drafter produit un brouillon de code (Markdown avec blocs ```langage)
réinjecté dans le Coder via ``sub_dict["draft_instruction"]``. Si ce draft est
malformé ou incomplet, l'injecter fait perdre du temps au Coder qui part sur de
mauvaises bases.

Ce gate détecte et CORRIGE (quand c'est possible déterministement) des classes
génériques de défauts — applicables à TOUT projet (pas seulement Bubble Sort) :

  - BLOCS MALFORMÉS       : blocs ``` non fermés → le Coder lit du code tronqué.
                            CORRIGE : ajoute la clôture manquante.
  - PLACEHOLDERS          : TODO / "..." / "Logique ici" / FIXME → draft non fini.
                            REJETE : le Coder part de zéro (le draft est inutilisable).
  - DOUBLONS DE DÉFINITION : même function/def défini 2 fois → bug runtime.
                            REJETE : draft contradictoire, source de confusion.
  - IMPORTS MANQUANTS     : Python utilisant time/json/os/sys sans import → NameError.
                            CORRIGE : ajoute la ligne d'import au début du bloc Python.
  - BALISE NON FERMÉE     : <div>/<script>/<style> non fermés en HTML → rendu cassé.
                            CORRIGE : ajoute la balise de fermeture si évident.

0 LLM, 0 réseau, 100% déterministe (miroir de ``static_tester.py`` / ``linter.py``).
Référence de design : les gatekeepers shift-left du workflow (Linter F-30,
Static Tester F-49) qui court-circuitent les nœuds coûteux sur les bugs évidents.

Le gate est ADDITIF et ne duplique PAS le Linter (syntaxe) ni le Static Tester
(wiring, runtime) qui opèrent plus tard sur les fichiers écrits. Il agit sur le
draft markdown AVANT écriture, là où les autres nœuds n'ont pas accès.

  - ANIMATION INSTANTANÉE     : 3 variantes génériques (détectées au niveau code,
                                + spec pour la variante 3). WARN.
                                Variante 1 : setTimeout/setInterval dans une boucle
                                bornée sans await → exécution en rafale.
                                Variante 2 : requestAnimationFrame appelant une fonction
                                qui contient la boucle bornée complète → 1 frame = tout.
                                Variante 3 : boucle bornée sans AUCUN mécanisme de délai,
                                ET la spec demande une animation/visualisation → instant.

Usage ::
    from .draft_gate import check_draft
    result = check_draft(draft_res.draft_markdown, spec_hint=original_content)
    if result.should_reject:
        sub_dict["draft_instruction"] = ""  # Coder part de zéro
    elif result.corrected_markdown != draft_markdown:
        # Réécrit le draft corrigé sur disque
        ...
    if result.warnings_block:
        sub_dict["draft_instruction"] += result.warnings_block
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class DraftIssue:
    """Un défaut détecté dans le draft."""
    kind: str           # 'malformed_block' | 'placeholder' | 'dup_definition' | ...
    severity: str       # 'critical' | 'high' | 'medium'
    description: str    # description lisible
    action: str         # 'correct' | 'reject' | 'warn'


@dataclass
class DraftCheck:
    """Résultat du gate Drafter → Coder."""
    is_valid: bool = True
    issues: List[DraftIssue] = field(default_factory=list)
    corrected_markdown: str = ""
    warnings_block: str = ""

    @property
    def should_reject(self) -> bool:
        """True si le draft doit être jeté (au moins 1 issue REJECT)."""
        return any(i.action == "reject" for i in self.issues)


# --- Patterns génériques ------------------------------------------------------

# Placeholders = draft non fini. On tolère un "..." isolé dans un CSS/HTML (ex:
# background: radial-gradient(...) est valide), donc on cible les marqueurs
# explicites de travail inachevé + les points de suspension EN dehors des appels
# de fonction. Heuristique simple : TODO/FIXME/XXX/Logique ici/À implémenter.
_PLACEHOLDER_RE = re.compile(
    r"\b(TODO|FIXME|XXX|Logique ici|À implémenter|A implémenter|votre code ici)\b",
    re.IGNORECASE,
)

# Doublons de définition. Détecte function foo() ET def foo() définies > 1 fois.
_FUNC_DEF_RE = re.compile(r"(?:function|def)\s+(\w+)\s*\(", re.MULTILINE)

# --- Animation instantanée (3 variantes génériques) ---------------------------
# Boucle bornée sur une collection (for/while avec .length ou condition de fin).
_BOUNDED_LOOP_RE = re.compile(r"\bfor\s*\(\s*\w+.*?\.length|\bwhile\s*\(")
# Mécanisme de délai asynchrone correct : await sleep/await new Promise(setTimeout).
# Si présent ET bien utilisé → l'animation est progressive (pas instantanée).
_AWAIT_DELAY_RE = re.compile(r"\bawait\s+(?:sleep|new\s+Promise)")
# requestAnimationFrame (variante 2) — l'animation est correcte SEULEMENT si la
# fonction appelée ne contient pas elle-même la boucle complète (1 itération/frame).
_RAF_RE = re.compile(r"requestAnimationFrame\s*\(\s*([\w$]+)\s*\)")
# setTimeout/setInterval (variante 1).
_SET_TIMEOUT_RE = re.compile(r"(setTimeout|setInterval)\s*\(")
# Mots-clés de spec indiquant une intention d'animation/visualisation (variante 3).
_ANIM_SPEC_KEYWORDS = re.compile(
    r"\b(animation|animée?|pas[ -]?à[ -]?pas|step[- ]?by[- ]?step|visuali[sz]"
    r"|visualis|délai\s+visible|delay\s+visible|frame)\b",
    re.IGNORECASE,
)

# --- Barres plates : flex-direction column + flex:1 (run #14, F-124) -----------
# LE bug de géométrie du visualiseur : un conteneur de barres en
# flex-direction:column avec flex:1 sur les barres → flex-basis:0 ÉCRASE
# style.height → N bandes horizontales égales (min-height) pleine largeur,
# au lieu de barres verticales proportionnelles. La règle flex ROW existe dans
# le skill coding du Coder, mais si le DRAFT (Architect/Drafter) prescrit
# column le 4B suit le draft — le gate doit rejeter AVANT injection.
_FLEX_COLUMN_RE = re.compile(r"flex-direction\s*:\s*column", re.IGNORECASE)
_FLEX_ONE_RE = re.compile(r"flex\s*:\s*1\b|flex-grow\s*:", re.IGNORECASE)
_BAR_CONTEXT_RE = re.compile(
    r"\.bar[s]?\b|\bbarres?\b|\bchart\b|\bviz\b|visuali[sz]", re.IGNORECASE
)


def _find_code_blocks(md: str) -> List[Tuple[int, int, str]]:
    """Retourne les blocs de code (début, fin, langue).

    début = index du marqueur d'ouverture, fin = index du marqueur de fermeture
    (ou -1 si non fermé). langue = le mot après ``` (peut être "").
    """
    blocks = []
    # Tous les marqueurs ``` (avec ou sans langue).
    fence_iter = list(re.finditer(r"```(\w*)", md))
    i = 0
    while i < len(fence_iter) - 1:
        open_m = fence_iter[i]
        # Le prochain marqueur est soit la fermure de ce bloc, soit l'ouverture
        # du suivant (si bloc non fermé). On assume appariement séquentiel.
        close_m = fence_iter[i + 1]
        lang = open_m.group(1) or ""
        # Une fermure est un ``` sans langue (group(1) == ""). Une ouverture
        # suivante a une langue non vide. Si close_m a une langue → bloc non fermé.
        if close_m.group(1) == "":
            blocks.append((open_m.start(), close_m.start(), lang))
            i += 2
        else:
            # Bloc non fermé : pas de fermure avant l'ouverture suivante.
            blocks.append((open_m.start(), -1, lang))
            i += 1
    # Dernier marqueur orphelin (ouverture sans fermure).
    if i < len(fence_iter):
        open_m = fence_iter[i]
        blocks.append((open_m.start(), -1, open_m.group(1) or ""))
    return blocks


def _detect_placeholders(md: str) -> List[DraftIssue]:
    """Placeholders = draft non fini → REJECT."""
    issues = []
    for m in _PLACEHOLDER_RE.finditer(md):
        issues.append(DraftIssue(
            kind="placeholder",
            severity="high",
            description=(
                f"Placeholder détecté ({m.group(0)}) : le draft n'est pas terminé. "
                f"Le Coder recopierait ce placeholder dans le code final."
            ),
            action="reject",
        ))
    return issues


def _detect_dup_definitions(md: str) -> List[DraftIssue]:
    """Doublons function/def → REJECT (draft contradictoire)."""
    names = _FUNC_DEF_RE.findall(md)
    counts: dict = {}
    for n in names:
        counts[n] = counts.get(n, 0) + 1
    issues = []
    for n, c in counts.items():
        if c > 1:
            issues.append(DraftIssue(
                kind="dup_definition",
                severity="high",
                description=(
                    f"La fonction '{n}' est définie {c} fois dans le draft. "
                    f"Le Coder hériterait d'une redéfinition contradictoire."
                ),
                action="reject",
            ))
    return issues


def _detect_instant_animation(md: str, spec_hint: str = "") -> List[DraftIssue]:
    """Animation instantanée — 3 variantes génériques. WARN.

    Le bug fondamental : une boucle bornée sur une collection qui s'exécute
    complètement en 1 tick JS → animation invisible (l'utilisateur attend une
    progression visible). 3 variantes, toutes génériques (pas spécifiques à un
    algorithme particulier) :

    V1. setTimeout/setInterval dans une boucle bornée SANS await → les timeouts
        s'empilent au même tick → exécution en rafale (instantané).
    V2. requestAnimationFrame appelant une fonction qui contient la boucle bornée
        complète → 1 frame = tout le traitement (instantané).
    V3. Boucle bornée sans AUCUN mécanisme de délai (setTimeout/rAF/await absent)
        ET la spec demande une animation/visualisation → instantané par construction.

    Si ``await`` (sleep/new Promise) est présent, on considère que l'animation est
    progressive (pas instantanée) — l'auteur a explicitement attendu entre les pas.
    """
    issues: List[DraftIssue] = []
    has_bounded_loop = bool(_BOUNDED_LOOP_RE.search(md))
    if not has_bounded_loop:
        return issues  # Pas de boucle bornée = pas de risque d'animation instantanée.

    has_await_delay = bool(_AWAIT_DELAY_RE.search(md))
    if has_await_delay:
        # await sleep/await new Promise présent → animation progressive, OK.
        return issues

    has_settimeout = bool(_SET_TIMEOUT_RE.search(md))

    # V1 : setTimeout sans await dans une boucle bornée → exécution en rafale.
    if has_settimeout:
        issues.append(DraftIssue(
            kind="animation_instant_v1",
            severity="high",
            description=(
                "setTimeout/setInterval dans une boucle bornée SANS await : les "
                "délais s'empilent au même tick → exécution en rafale (animation "
                "instantanée, invisible). Utilise `await sleep(ms)` ou "
                "`await new Promise(r => setTimeout(r, ms))` avec UNE itération "
                "par appel asynchrone."
            ),
            action="warn",
        ))

    # V2 : requestAnimationFrame dont la fonction callback contient la boucle.
    raf_match = _RAF_RE.search(md)
    if raf_match:
        # Cherche le corps de la fonction callback : si elle contient une boucle
        # bornée, tout le traitement est fait en 1 frame.
        cb_name = raf_match.group(1)
        # Heuristique : on cherche 'function cbName' / 'const cbName =' / 'cbName ='
        # et on regarde si une boucle bornée suit dans les ~300 chars.
        cb_def = re.search(
            rf"(?:function\s+{re.escape(cb_name)}|{re.escape(cb_name)}\s*=).{{0,400}}",
            md, re.DOTALL,
        )
        if cb_def and _BOUNDED_LOOP_RE.search(cb_def.group(0)):
            issues.append(DraftIssue(
                kind="animation_instant_v2",
                severity="high",
                description=(
                    f"requestAnimationFrame appelle '{cb_name}' qui contient une "
                    f"boucle bornée complète → tout le traitement en 1 frame "
                    f"(animation instantanée, invisible). La fonction callback ne "
                    f"doit faire qu'UNE itération par frame, pas la boucle entière."
                ),
                action="warn",
            ))

    # V3 : boucle bornée sans AUCUN délai (setTimeout/rAF absent) + spec animation.
    if not has_settimeout and not raf_match and spec_hint:
        if _ANIM_SPEC_KEYWORDS.search(spec_hint):
            issues.append(DraftIssue(
                kind="animation_instant_v3",
                severity="high",
                description=(
                    "Boucle bornée sans AUCUN mécanisme de délai (pas de "
                    "setTimeout/requestAnimationFrame/await), mais le cahier des "
                    "charges demande une animation/visualisation. Le traitement "
                    "s'exécutera instantanément (invisible pour l'utilisateur). "
                    "Ajoute `await sleep(ms)` dans la boucle pour une progression visible."
                ),
                action="warn",
            ))

    return issues


def _detect_flex_column_bars(md: str) -> List[DraftIssue]:
    """Barres de visualiseur en flex-direction:column + flex:1 (run #14).

    Signature exacte du bug : le draft prescrit le CONTENEUR DE BARRES en
    colonne ET flex:1/flex-grow sur les enfants ET un contexte barres/chart.
    Affinage F-167 (faux positif run C) : la directive column doit appartenir
    au MÊME BLOC que le contexte barres/chart/viz — une règle CSS (du sélecteur
    à l'accolade fermante) ou une ligne de prose. C'est la forme réelle du bug
    (« #viz { flex-direction: column } », run #14, ou « #viz (barres) : colonne »
    en prose). Une colonne dans un AUTRE bloc (body en colonne pour empiler
    header/contrôles/board) est légitime même quand les barres sont flex:1
    dans un conteneur #board correctement en row + flex-end.
    Rejet (le Coder part de zéro) : le corriger à la main dans le draft
    laisserait la géométrie incohérente avec le reste du plan.
    """
    if not _FLEX_ONE_RE.search(md):
        return []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        # Bloc courant : règle CSS (ligne sélecteur → '}') ou ligne seule (prose).
        if "{" in lines[i]:
            j = i
            while j < len(lines) and "}" not in lines[j]:
                j += 1
            block = "\n".join(lines[i:j + 1])
            i = j + 1
        else:
            block = lines[i]
            i += 1
        if _FLEX_COLUMN_RE.search(block) and _BAR_CONTEXT_RE.search(block):
            return [DraftIssue(
                kind="flex_column_bars",
                severity="critical",
                description=(
                    "Conteneur de barres en flex-direction:column avec flex:1 sur les "
                    "barres : flex-basis:0 ÉCRASE style.height → N bandes horizontales "
                    "égales pleine largeur (barres plates), au lieu de barres verticales "
                    "proportionnelles. Géométrie correcte : conteneur flex ROW + "
                    "align-items:flex-end + hauteurs px inline sur chaque barre (règle "
                    "skill coding F-124). Le draft est rejeté : le Coder repart de zéro."
                ),
                action="reject",
            )]
    return []


# --- Densité prescriptive (F-167) : draft creux = livrable creux ---------------
# Leçon F164-6 + runs 0857/1448 (A/B F-167 : Ornith-1.0 ET 1.5 clonaient le même
# draft creux de 1260 octets — cause racine : l'exemple de FORMAT DE SORTIE du
# prompt Drafter, creux, copié à la lettre). Un draft « d'intentions » sans
# valeurs produit un livrable creux : le Coder 4B suit le draft À LA LETTRE.
# Deux signatures exactes, prouvées sur les runs réels :
#   1. Variables CSS listées SANS valeurs (« --bg, --surface, --text ») → le
#      Coder consomme var(--bg) dans styles.css mais n'écrit JAMAIS le bloc
#      :root (aucune valeur à écrire) → thème sombre mort.
#   2. Hauteurs de barres en % SANS hauteur fixe (px) du conteneur parent →
#      pourcentage sans référent → hauteur 0 → board vide au chargement.
# Les deux sont REJETÉS mais RETRYABLES : le workflow réinjecte le feedback du
# gate au Drafter pour une 2e tentative (workflows.py, DENSITY_REJECT_KINDS)
# avant de laisser le Coder partir de zéro.

# Kinds de rejet « densité » : retryables par le workflow (feedback au Drafter),
# contrairement aux rejets structurels (placeholder, doublons, géométrie) = zéro.
DENSITY_REJECT_KINDS = frozenset({"css_vars_no_values", "pct_height_no_parent"})

_CSS_VAR_TOKEN_RE = re.compile(r"--[\w-]+")
_VAR_USAGE_RE = re.compile(r"var\(\s*--[\w-]+\s*\)")
# Contexte hauteur en % : mot hauteur/height puis un % à <= 60 chars (couvre
# « hauteur (v/100)*100% », « height: 75% », « hauteurs proportionnelles ... % »).
_PCT_HEIGHT_CTX_RE = re.compile(r"(?:hauteur|height)[^\n]{0,60}%", re.IGNORECASE)
# Hauteur fixe px : « height: 240px », « height 240px », « hauteur : 300px »
# (en CSS ou en prose du plan — le référent du % est ce qui compte).
_FIXED_PX_HEIGHT_RE = re.compile(r"(?:hauteur|height)\s*[:=]?\s*\d+\s*px", re.IGNORECASE)


def _detect_css_vars_without_values(md: str) -> List[DraftIssue]:
    """Variables CSS listées sans valeurs → REJECT (thème mort). F-167.

    Signature exacte du run 1448 : une LIGNE qui mentionne >= 2 tokens ``--var``
    (hors usages ``var(--x)``) dont au moins un n'est NI suivi de ``: valeur`` sur
    la ligne NI défini avec valeur ailleurs dans le draft. Les définitions saines
    (``--bg: #1a1a2e, --sorted: #10b981``) passent ; les références en prose à
    des variables définies ailleurs (``Body : bg --bg, text --text``) passent ;
    les usages (``color: var(--bg)``) sont exclus du comptage (référence ≠
    définition) ; une ligne à token unique n'est pas une liste (tolérance).
    Retourne au plus UNE issue (la première ligne fautive suffit).
    """
    # Pass 1 : variables réellement DÉFINIES avec valeur quelque part dans le draft.
    defined = set()
    for m in _CSS_VAR_TOKEN_RE.finditer(md):
        if md[m.end():].lstrip().startswith(":"):
            defined.add(m.group(0))
    # Pass 2 : lignes-listes avec un token ni défini ni suivi de « : valeur ».
    for line in md.splitlines():
        line_wo_usage = _VAR_USAGE_RE.sub("", line)
        tokens = _CSS_VAR_TOKEN_RE.findall(line_wo_usage)
        if len(tokens) < 2:
            continue
        for m in _CSS_VAR_TOKEN_RE.finditer(line_wo_usage):
            rest = line_wo_usage[m.end():].lstrip()
            if not rest.startswith(":") and m.group(0) not in defined:
                return [DraftIssue(
                    kind="css_vars_no_values",
                    severity="critical",
                    description=(
                        f"Variables CSS listées SANS valeurs (ex: {m.group(0)} dans "
                        f"« {line.strip()[:80]} ») : le Coder consommera var(--…) "
                        f"dans styles.css mais n'écrira JAMAIS le bloc :root — "
                        f"thème mort. Réécris CHAQUE variable AVEC sa valeur exacte : "
                        f"--bg: #0f172a; --text: #e2e8f0; …"
                    ),
                    action="reject",
                )]
    return []


def _detect_pct_height_no_parent(md: str) -> List[DraftIssue]:
    """Hauteurs en % sans hauteur fixe px du parent → REJECT (board vide). F-167.

    Si le draft prescrit des hauteurs en % (contexte hauteur/height + %) mais
    qu'AUCUNE hauteur fixe en px n'apparaît dans tout le plan, le pourcentage
    n'a pas de référent → hauteur calculée 0 → board vide au chargement (le
    « board vide » des runs 0857/1448, critère visuel 1 en échec).
    """
    if not _PCT_HEIGHT_CTX_RE.search(md):
        return []
    if _FIXED_PX_HEIGHT_RE.search(md):
        return []
    return [DraftIssue(
        kind="pct_height_no_parent",
        severity="critical",
        description=(
            "Hauteurs prescrites en POURCENTAGE sans AUCUNE hauteur fixe en px du "
            "conteneur parent dans le plan : un % sans référent = hauteur 0 = "
            "board vide au chargement. Prescris la hauteur FIXE du conteneur "
            "(ex: #board { height: 240px }) en plus des hauteurs % des barres."
        ),
        action="reject",
    )]


def build_density_feedback(issues: List[DraftIssue]) -> str:
    """Bloc de feedback retry F-167 à append à la sous-tâche du Drafter.

    Vide si aucun issue de densité (les autres rejets ne se retentent pas :
    placeholder/doublon/géométrie = draft structurellement inutilisable).
    """
    density = [i for i in issues if i.kind in DENSITY_REJECT_KINDS]
    if not density:
        return ""
    lines = [
        "### ⛔ DRAFTER GATE : ton draft précédent a été REJETÉ — corrige ces défauts",
    ]
    lines.extend(f"- {i.description}" for i in density)
    return "\n".join(lines)


def _fix_malformed_blocks(md: str) -> Tuple[str, List[DraftIssue]]:
    """Blocs ``` non fermés → ajoute la clôture manquante. CORRECT."""
    issues = []
    blocks = _find_code_blocks(md)
    unfenced = [b for b in blocks if b[1] == -1]
    if not unfenced:
        return md, []
    # Ajoute ``` à la fin pour chaque bloc non fermé (best-effort : on ferme à la
    # fin du markdown, ce qui est la correction la plus sûre déterministement).
    corrected = md
    if not corrected.endswith("\n"):
        corrected += "\n"
    for _ in unfenced:
        corrected += "```\n"
    issues.append(DraftIssue(
        kind="malformed_block",
        severity="medium",
        description=(
            f"{len(unfenced)} bloc(s) de code non fermé(s) (``` sans clôture). "
            f"Clôture ajoutée automatiquement pour éviter un code tronqué."
        ),
        action="correct",
    ))
    return corrected, issues


def _build_warnings_block(issues: List[DraftIssue]) -> str:
    """Construit un bloc d'avertissements à append à draft_instruction (WARN only)."""
    warns = [i for i in issues if i.action == "warn"]
    if not warns:
        return ""
    lines = ["\n\n### ⚠️ AVERTISSEMENTS DU DRAFTER GATE (F-91)"]
    lines.append(
        "Le brouillon ci-dessus présente des points de vigilance détectés "
        "automatiquement. Sois attentif à ces aspects pendant l'injection :"
    )
    for i, issue in enumerate(warns, 1):
        lines.append(f"\n{i}. [{issue.severity.upper()}] {issue.description}")
    lines.append("\nNe recopie PAS le draft aveuglément — corrige ces points.")
    return "\n".join(lines)


def check_draft(draft_markdown: str, spec_hint: str = "") -> DraftCheck:
    """Vérifie un draft Drafter pour les défauts génériques (0 LLM, déterministe).

    Args:
        draft_markdown: Le brouillon de code (Markdown avec blocs ```langage)
            produit par l'Algorithm Drafter.
        spec_hint: Le cahier des charges (original_content) optionnel, utilisé
            pour la variante 3 de l'animation instantanée (boucle sans délai +
            spec demande animation). Si absent, V3 n'est pas évaluée.

    Returns:
        Un ``DraftCheck`` avec ``is_valid``, la liste des ``issues``, le
        ``corrected_markdown`` (éventuellement modifié par les fixes CORRECT),
        et un ``warnings_block`` à append à l'injection. ``should_reject``
        indique si le draft doit être jeté (Coder part de zéro).
    """
    result = DraftCheck(corrected_markdown=draft_markdown)

    if not draft_markdown or not draft_markdown.strip():
        # Draft vide = rien à vérifier (le Coder part de zéro naturellement).
        return result

    # 1. Corrections déterministes (appliquées d'abord, sur le markdown corrigé).
    result.corrected_markdown, block_issues = _fix_malformed_blocks(draft_markdown)
    result.issues.extend(block_issues)

    # 2. Détections REJECT (sur le markdown corrigé).
    result.issues.extend(_detect_placeholders(result.corrected_markdown))
    result.issues.extend(_detect_dup_definitions(result.corrected_markdown))
    result.issues.extend(_detect_flex_column_bars(result.corrected_markdown))

    # 2bis. Détections REJECT densité prescriptive (F-167) — retryables par le
    # workflow (feedback réinjecté au Drafter, cf. DENSITY_REJECT_KINDS).
    result.issues.extend(_detect_css_vars_without_values(result.corrected_markdown))
    result.issues.extend(_detect_pct_height_no_parent(result.corrected_markdown))

    # 3. Détections WARN (animation instantanée, 3 variantes génériques).
    result.issues.extend(
        _detect_instant_animation(result.corrected_markdown, spec_hint=spec_hint)
    )

    # Statut + bloc warnings.
    if result.issues:
        result.is_valid = False
        result.warnings_block = _build_warnings_block(result.issues)

    return result
