"""Logique d'édition SEARCH/REPLACE tolérante, portée depuis Aider.

Les petits LLM locaux (qwen3.5:4b, Gemma) corrompent les gros contenus passés
en argument JSON d'un tool_call (cf. bug run #11 : HTML cassé). La solution est
l'édition par bloc SEARCH/REPLACE : on ne demande au modèle que le fragment à
remplacer et son substitut, ce qui limite la quantité de texte à générer dans
un seul argument, et on tolère les imprécisions de formatage classiques des
petits modèles (indentation, lignes vides, ellipses).

Porté depuis references/aider/aider/coders/editblock_coder.py :
  - replace_most_similar_chunk (l.157) : orchestrateur des stratégies.
  - replace_part_with_missing_leading_whitespace (l.243) : tolérant indentation.
  - try_dotdotdots (l.190) : gère les ellipses `...`.
  - find_similar_lines (adapté) : feedback "Did you mean..." en cas d'échec.

F-166 (post-mortem run 0857 du 2026-08-24 : ~15 rejets F-132 + 80 steps LLM
brûlés sur un fix mécanique) :
  - CODE_SEPARATOR_NL_RE / decode_literal_escapes : domicile canonique de la
    regex « \\n littéral en séparateur de code » (historiquement dupliquée
    tools.py [garde F-132] + auto_fixer.py [repair F-133]) et décodeur des
    arguments d'outil — le décodeur et la garde partagent LA MÊME définition.
  - RelativeIndenter (port aider search_replace.py:18-171) : préprocesseur
    d'indentation relative, exact-match insensible au décalage global
    d'indentation à variation relative près.
  - _fuzzy_line_window_replace : équivalent difflib stdlib de dmp_lines_apply
    (:338), 0 nouvelle dépendance, en DERNIER recours avec gardes anti
    mauvais-edit (ratio plancher + marge sur le second + longueur minimale).
    Le fuzzy SequenceMatcher caractères d'aider (:296) — désactivé en amont
    chez aider, mauvais edits — reste NON porté.

Aide: https://aider.chat — licence MIT. Cette réimplémentation est volontairement
allégée (pas de fuzzy edit-distance, qui est neutralisé dans aider lui-même).
"""

import difflib
import re
from typing import Optional

# Longueur minimale de la sous-chaîne pour le fallback 6) de
# replace_most_similar_chunk : en dessous, une occurrence unique est trop
# probablement un aiguillage générique (identifiant court, ponctuation...).
_SUBSTRING_MIN_LEN = 8

# =============================================================================
# F-166 : regex canonique « \n littéral en séparateur de code » + décodeur.
# =============================================================================
# Le 4B écrit parfois ses arguments d'outil tout-littéraux (effet r-string) :
# `search_replace(..., new_string="foo();\nbar()")` où `\n` est backslash+n
# (2 caractères). La garde F-132 (tools.py) rejette ces appels — le run 0857
# en a essuyé ~15 d'affilée. F-166 décode ces séquences AU LIEU de rejeter :
# même définition de part et d'autre, l'outil ne rejette jamais ce qu'il
# décode. Un `\n` littéral interne à une chaîne affichée (ex: "a\nb" dans un
# console.log) ne matche PAS la regex (pas en position séparateur) : il n'est
# jamais touché.
_NL_KEYWORDS = (
    "const|let|var|function|return|if|else|for|while|switch|case|class|"
    r"new\b|document\.|window\.|addEventListener|try|catch|import|export|"
    r"async|await|def\b|print\("
)
CODE_SEPARATOR_NL_RE = re.compile(
    r"(?:(?<=[;{}()\[\]])\\n|\\n(?=\s*(?:" + _NL_KEYWORDS + r")))"
)

# `\t` littéral en tête de ligne du texte décodé (indentation tabulée encodée
# littéralement dans le scénario « bloc tout-littéral »).
_LEADING_LITERAL_TABS_RE = re.compile(r"(?m)^(?:\\t)+")


def decode_literal_escapes(text: str) -> tuple[str, int]:
    """Décode les séquences échappées LITTÉRALES d'un argument d'outil (F-166).

    Retourne (texte, n_remplacements). Ne décode QUE :
      - `\\n` littéral en position de séparateur de code (MÊME regex que la
        garde F-132 — cohérence garantie par le domicile canonique) ;
      - `\\t` littéral en tête de ligne du résultat intermédiaire.
    Si le texte ne contient aucun `\\n` séparateur, il est retourné INTACT
    (un `\\n` légitime dans une chaîne affichée n'est jamais décodé).
    """
    if not text:
        return text, 0
    hits = CODE_SEPARATOR_NL_RE.findall(text)
    if not hits:
        return text, 0
    decoded = CODE_SEPARATOR_NL_RE.sub("\n", text)
    n_tabs = 0

    def _tab(m: "re.Match[str]") -> str:
        nonlocal n_tabs
        n_tabs += len(m.group(0)) // 2
        return "\t" * (len(m.group(0)) // 2)

    decoded = _LEADING_LITERAL_TABS_RE.sub(_tab, decoded)
    return decoded, len(hits) + n_tabs


# =============================================================================
# RelativeIndenter (port aider search_replace.py:18-171, F-166).
# =============================================================================
class RelativeIndenter:
    """Réécrit un texte en indentation RELATIVE pour apparier des blocs dont
    l'indentation globale diffère mais dont la structure relative coïncide.

    Chaque ligne devient DEUX lignes : le delta d'indentation (nombre de
    marqueurs ← pour un outdent) puis le contenu. make_absolute recompose.
    Porté fidèlement d'aider (lic. MIT) ; ValueError en cas d'incohérence —
    les appelants traitent l'exception comme un échec de stratégie (fail-closed).
    """

    def __init__(self, texts):
        chars = set()
        for text in texts:
            chars.update(text)
        arrow = "←"
        if arrow not in chars:
            self.marker = arrow
        else:
            self.marker = self._select_unique_marker(chars)

    def _select_unique_marker(self, chars):
        for codepoint in range(0x10FFFF, 0x10000, -1):
            marker = chr(codepoint)
            if marker not in chars:
                return marker
        raise ValueError("Could not find a unique marker")

    def make_relative(self, text: str) -> str:
        if self.marker in text:
            raise ValueError(f"Text already contains the outdent marker: {self.marker}")
        lines = text.splitlines(keepends=True)
        output = []
        prev_indent = ""
        for line in lines:
            line_without_end = line.rstrip("\n\r")
            len_indent = len(line_without_end) - len(line_without_end.lstrip())
            indent = line[:len_indent]
            change = len_indent - len(prev_indent)
            if change > 0:
                cur_indent = indent[-change:]
            elif change < 0:
                cur_indent = self.marker * -change
            else:
                cur_indent = ""
            output.append(cur_indent + "\n" + line[len_indent:])
            prev_indent = indent
        return "".join(output)

    def make_absolute(self, text: str) -> str:
        lines = text.splitlines(keepends=True)
        output = []
        prev_indent = ""
        for i in range(0, len(lines), 2):
            dent = lines[i].rstrip("\r\n")
            non_indent = lines[i + 1]
            if dent.startswith(self.marker):
                len_outdent = len(dent)
                cur_indent = prev_indent[:-len_outdent]
            else:
                cur_indent = prev_indent + dent
            if not non_indent.rstrip("\r\n"):
                out_line = non_indent  # on n'indente pas une ligne vide
            else:
                out_line = cur_indent + non_indent
            output.append(out_line)
            prev_indent = cur_indent
        res = "".join(output)
        if self.marker in res:
            raise ValueError("Error transforming text back to absolute indents")
        return res


def _relative_indent_replace(whole: str, part: str, replace: str) -> Optional[str]:
    """Exact-match sur les textes relativisés (préprocesseur aider P3, F-166).

    Couvre le cas que _replace_part_with_missing_leading_whitespace rate : un
    décalage global d'indentation NON uniforme en apparence mais à structure
    relative identique (fichier 8/12/8, bloc 0/4/0). Subtilité du format aider
    (docstring RelativeIndenter) : la dent de la PREMIÈRE ligne du bloc encode
    son indentation absolue de départ, celle de la fenêtre cible encode un
    delta — elles peuvent différer légitimement. On fait donc matcher la
    structure INTERNE (lignes 2+) et on PRÉSERVE la dent cible dans le
    remplacement (le bloc est ré-indenté au niveau de la cible). Les fenêtres
    sont alignées sur les paires (dent, contenu) : index pair. Fail-closed :
    toute ValueError de RelativeIndenter → None (stratégie suivante).
    """
    try:
        ri = RelativeIndenter([whole, part, replace])
        w = ri.make_relative(whole)
        p = ri.make_relative(part)
        r = ri.make_relative(replace)
        w_lines = w.splitlines(keepends=True)
        p_lines = p.splitlines(keepends=True)
        r_lines = r.splitlines(keepends=True)
        num = len(p_lines)
        if num < 2 or len(w_lines) < num:
            return None
        # Structure interne du part (dent+contenu, lignes 2+).
        p_inner = p_lines[1:]
        for i in range(0, len(w_lines) - num + 1, 2):
            if w_lines[i + 1 : i + num] != p_inner:
                continue
            # Dent cible préservée en tête du remplacement (ré-indentation).
            new_r = [w_lines[i]] + r_lines[1:]
            res = "".join(w_lines[:i] + new_r + w_lines[i + num :])
            return ri.make_absolute(res)
    except (ValueError, IndexError):
        return None
    return None


# =============================================================================
# Fallback diff par lignes (port difflib stdlib de dmp_lines_apply, F-166).
# =============================================================================
_FUZZY_MIN_NONBLANK = 4    # bloc trop court = aiguillage trop générique
_FUZZY_MIN_RATIO = 0.75    # plancher : 3 lignes identiques sur 4 doit passer
_FUZZY_MIN_MARGIN = 0.05   # écart exigé sur le 2e meilleur candidat


def _reindent_into(replace_lines: list[str], base_indent: str, part_base_indent: str) -> list[str]:
    """Réaligne l'indentation de base de replace_lines sur la fenêtre cible."""
    out: list[str] = []
    for r in replace_lines:
        if not r.strip():
            out.append(r if r.endswith("\n") else r + "\n")
            continue
        r_indent = r[: len(r) - len(r.lstrip())]
        r_content = r.lstrip()
        if r_indent.startswith(part_base_indent):
            rel = r_indent[len(part_base_indent):]
            reindented = base_indent + rel + r_content
        else:
            reindented = base_indent + r_indent + r_content
        out.append(reindented if reindented.endswith("\n") else reindented + "\n")
    return out


def _fuzzy_line_window_replace(
    whole_lines: list[str], part_lines: list[str], replace_lines: list[str]
) -> Optional[tuple[str, float]]:
    """Dernier recours (F-166, équivalent difflib de dmp_lines_apply :338) :
    localise la fenêtre de lignes la plus similaire au bloc SEARCH (ratio
    SequenceMatcher sur lignes strippées) et la remplace — les éditeurs
    s'en tiennent aux diffs PAR LIGNES (jamais caractères). Gardes contre les
    mauvais edits silencieux : bloc ≥ 4 lignes non vides, ratio ≥ 0.8, marge
    ≥ 0.05 sur le second meilleur score. Retourne (nouveau_texte, ratio).
    """
    p_nonblank = [l for l in part_lines if l.strip()]
    if len(p_nonblank) < _FUZZY_MIN_NONBLANK:
        return None
    n = len(part_lines)
    p_stripped = [l.strip() for l in part_lines]
    sm = difflib.SequenceMatcher(None, autojunk=False)
    sm.set_seq2(p_stripped)
    best_ratio, best_idx, second = 0.0, -1, 0.0
    for i in range(len(whole_lines) - n + 1):
        sm.set_seq1([l.strip() for l in whole_lines[i : i + n]])
        r = sm.ratio()
        if r > best_ratio:
            second, best_ratio, best_idx = best_ratio, r, i
        elif r > second:
            second = r
    if best_idx < 0 or best_ratio < _FUZZY_MIN_RATIO:
        return None
    if second > 0 and (best_ratio - second) < _FUZZY_MIN_MARGIN:
        return None
    target = whole_lines[best_idx : best_idx + n]
    first_target = next((w for w in target if w.strip()), "")
    base_indent = first_target[: len(first_target) - len(first_target.lstrip())]
    first_part = next((p for p in part_lines if p.strip()), "")
    part_base_indent = first_part[: len(first_part) - len(first_part.lstrip())]
    new_replace = _reindent_into(replace_lines, base_indent, part_base_indent)
    new_text = "".join(whole_lines[:best_idx] + new_replace + whole_lines[best_idx + n :])
    return new_text, best_ratio


def _prep(text: str) -> tuple[str, list[str]]:
    """Normalise : garantit un newline final, renvoie (texte, lignes)."""
    if text and not text.endswith("\n"):
        text += "\n"
    return text, text.splitlines(keepends=True)


def _match_but_for_leading_whitespace(whole_lines: list[str], part_lines: list[str]) -> Optional[str]:
    """Si deux blocs correspondent à l'indentation près, renvoie le préfixe
    d'indentation manquant (None sinon). Adapté d'aider match_but_for_leading_whitespace."""
    num = len(part_lines)
    if len(whole_lines) < num:
        return None
    # Le contenu non-whitespace doit être identique partout.
    if not all(whole_lines[i].lstrip() == part_lines[i].lstrip() for i in range(num)):
        return None
    # Et le décalage d'indentation doit être constant.
    offsets = {
        whole_lines[i][: len(whole_lines[i]) - len(part_lines[i])]
        for i in range(num)
        if part_lines[i].strip()
    }
    if len(offsets) != 1:
        return None
    return next(iter(offsets))


def _replace_part_with_missing_leading_whitespace(
    whole_lines: list[str], part_lines: list[str], replace_lines: list[str]
) -> Optional[str]:
    """Tente un remplacement tolérant à l'indentation de tête. Adapté d'aider l.243.

    Les petits modèles omettent ou réindentent uniformément le whitespace de tête.
    On outdente part et replace du même montant, puis on cherche un match exact sur
    le contenu non-indenté. Si trouvé, on réapplique l'indentation réelle du fichier.
    """
    leading = [len(p) - len(p.lstrip()) for p in part_lines if p.strip()] + [
        len(r) - len(r.lstrip()) for r in replace_lines if r.strip()
    ]
    if leading and min(leading) > 0:
        num_leading = min(leading)
        part_lines = [p[num_leading:] if p.strip() else p for p in part_lines]
        replace_lines = [r[num_leading:] if r.strip() else r for r in replace_lines]

    num_part_lines = len(part_lines)
    for i in range(len(whole_lines) - num_part_lines + 1):
        add_leading = _match_but_for_leading_whitespace(
            whole_lines[i : i + num_part_lines], part_lines
        )
        if add_leading is None:
            continue
        new_replace = [
            add_leading + rline if rline.strip() else rline for rline in replace_lines
        ]
        return "".join(whole_lines[:i] + new_replace + whole_lines[i + num_part_lines :])
    return None


def _perfect_or_whitespace(
    whole_lines: list[str], part_lines: list[str], replace_lines: list[str]
) -> Optional[str]:
    """1) match exact ligne à ligne, puis 2) tolérant indentation."""
    # (a) match exact
    num_part_lines = len(part_lines)
    for i in range(len(whole_lines) - num_part_lines + 1):
        if whole_lines[i : i + num_part_lines] == part_lines:
            return "".join(
                whole_lines[:i] + replace_lines + whole_lines[i + num_part_lines :]
            )
    # (b) tolérant indentation
    return _replace_part_with_missing_leading_whitespace(whole_lines, part_lines, replace_lines)


def _replace_stripped_lines(
    whole_lines: list[str], part_lines: list[str], replace_lines: list[str]
) -> Optional[str]:
    """Matching tolérant par normalisation des lignes (OpenCode / Aider fuzzy fallback).

    Si toutes les lignes non vides de `part_lines` correspondent exactement aux lignes
    de `whole_lines` une fois débarrassées de leurs espaces (stripped), et que cette
    séquence est UNIQUE dans le fichier, le remplacement est appliqué en alignant
    l'indentation de base de `replace_lines` sur celle de la cible.
    """
    p_stripped = [p.strip() for p in part_lines if p.strip()]
    if not p_stripped:
        return None

    matches: list[tuple[int, int]] = []
    num_p = len(p_stripped)

    for i in range(len(whole_lines)):
        matched_indices = []
        p_idx = 0
        for j in range(i, len(whole_lines)):
            w_line = whole_lines[j].strip()
            if not w_line:
                continue
            if w_line == p_stripped[p_idx]:
                matched_indices.append(j)
                p_idx += 1
                if p_idx == num_p:
                    break
            else:
                break
        if p_idx == num_p and matched_indices:
            start_j = matched_indices[0]
            end_j = matched_indices[-1] + 1
            matches.append((start_j, end_j))

    if len(matches) != 1:
        return None

    start_idx, end_idx = matches[0]
    target_lines = whole_lines[start_idx:end_idx]

    first_target = next((w for w in target_lines if w.strip()), "")
    base_indent = first_target[: len(first_target) - len(first_target.lstrip())]

    first_part = next((p for p in part_lines if p.strip()), "")
    part_base_indent = first_part[: len(first_part) - len(first_part.lstrip())]

    new_replace: list[str] = []
    for r in replace_lines:
        if not r.strip():
            new_replace.append(r if r.endswith("\n") else r + "\n")
        else:
            r_indent = r[: len(r) - len(r.lstrip())]
            r_content = r.lstrip()
            if r_indent.startswith(part_base_indent):
                rel_indent = r_indent[len(part_base_indent):]
                reindented = base_indent + rel_indent + r_content
            else:
                reindented = base_indent + r_indent + r_content
            new_replace.append(reindented if reindented.endswith("\n") else reindented + "\n")

    return "".join(whole_lines[:start_idx] + new_replace + whole_lines[end_idx:])


def _try_dotdotdots(whole: str, part: str, replace: str) -> Optional[str]:
    """Gère les ellipses `...` que le modèle insère pour éluder du code.
    Adapté d'aider try_dotdotdots (l.190). Lève ValueError si incohérent."""
    dots_re = re.compile(r"(^\s*\.\.\.\n)", re.MULTILINE | re.DOTALL)
    part_pieces = re.split(dots_re, part)
    replace_pieces = re.split(dots_re, replace)
    if len(part_pieces) != len(replace_pieces):
        raise ValueError("Ellipses `...` incohérentes entre SEARCH et REPLACE.")
    if len(part_pieces) == 1:
        return None  # pas d'ellipses ici

    # Les morceaux d'ellipses (impairs) doivent être identiques.
    if not all(
        part_pieces[i] == replace_pieces[i] for i in range(1, len(part_pieces), 2)
    ):
        raise ValueError("Ellipses `...` non appariées entre SEARCH et REPLACE.")

    part_pieces = [part_pieces[i] for i in range(0, len(part_pieces), 2)]
    replace_pieces = [replace_pieces[i] for i in range(0, len(replace_pieces), 2)]
    for p, r in zip(part_pieces, replace_pieces):
        if not p and not r:
            continue
        if not p and r:
            if not whole.endswith("\n"):
                whole += "\n"
            whole += r
            continue
        if whole.count(p) == 0:
            raise ValueError
        if whole.count(p) > 1:
            raise ValueError
        whole = whole.replace(p, r, 1)
    return whole


def replace_most_similar_chunk(whole: str, part: str, replace: str) -> Optional[str]:
    """Recherche `part` dans `whole` et le remplace par `replace`, avec dégradation
    gracieuse : match exact → tolérant indentation → ellipses → match stripped lines
    → indentation relative (F-166) → sous-chaîne exacte → fenêtre floue par lignes
    (F-166, dernier recours gardé). Renvoie le nouveau `whole` ou None si rien ne
    matche. Porté d'aider (l.157), sans fuzzy edit-distance.

    Attribut `last_note` (F-166) : description de la stratégie qui a matché quand
    elle est « créative » (indentation relative, fenêtre floue) — l'appelant
    (tools.py) la rend visible au modèle dans le message de succès pour qu'il
    puisse vérifier l'édit appliqué. Vidé à chaque appel.
    """
    replace_most_similar_chunk.last_note = ""
    whole, whole_lines = _prep(whole)
    part, part_lines = _prep(part)
    replace, replace_lines = _prep(replace)

    # 1) exact ou tolérant indentation uniforme
    res = _perfect_or_whitespace(whole_lines, part_lines, replace_lines)
    if res is not None:
        return res

    # 2) ignore une éventuelle première ligne vide parasite (issue aider #25)
    if len(part_lines) > 2 and not part_lines[0].strip():
        skip = part_lines[1:]
        res = _perfect_or_whitespace(whole_lines, skip, replace_lines)
        if res is not None:
            return res

    # 3) ellipses
    try:
        res = _try_dotdotdots(whole, part, replace)
        if res is not None:
            return res
    except ValueError:
        pass

    # 4) tolérance souple sur l'indentation ligne à ligne (OpenCode/Aider fallback)
    res = _replace_stripped_lines(whole_lines, part_lines, replace_lines)
    if res is not None:
        return res

    # 5) stripped lines en ignorant une première ligne vide
    if len(part_lines) > 2 and not part_lines[0].strip():
        res = _replace_stripped_lines(whole_lines, part_lines[1:], replace_lines)
        if res is not None:
            return res

    # 5-bis) lignes vides INTERNES ignorées (P3/F-137, port aider
    # `flexible_search_and_replace` préprocesseur "strip blank lines" :611) :
    # le LLM insère des lignes vides parasites au milieu du bloc SEARCH — on
    # re-tente le matching ligne à ligne après filtrage des vides des DEUX côtés.
    _wf = [l for l in whole_lines if l.strip()]
    _pf = [l for l in part_lines if l.strip()]
    if len(_pf) >= 2 and len(_pf) != len(part_lines):
        res = _replace_stripped_lines(_wf, _pf, replace_lines)
        if res is not None:
            return res

    # 6) indentation relative (F-166, port aider RelativeIndenter :18-171) :
    # décalage global d'indentation à structure relative près.
    res = _relative_indent_replace(whole, part, replace)
    if res is not None:
        replace_most_similar_chunk.last_note = (
            "matched via indentation relative (aider RelativeIndenter)"
        )
        return res

    # 7) sous-chaîne exacte (post-mortem run 2026-08-19, Tetris) : le 4B fournit
    # souvent un bloc PARTIEL de ligne — ex. sans la virgule finale — présent mot
    # pour mot comme sous-chaîne du fichier. Les stratégies ligne à ligne (1-5)
    # échouent toutes sur un écart d'un caractère en bout de ligne, alors que le
    # texte existe : le Coder peut alors brûler 15+ steps sur le même échec
    # (anti-loop) jusqu'à l'échec du nœud. On remplace la sous-chaîne si elle est
    # UNIQUE et assez longue (garde anti-aiguillage générique) ; l'ambiguïté
    # (0 ou 2+ occurrences) continue d'échouer proprement avec le feedback didactique.
    if len(part) >= _SUBSTRING_MIN_LEN and whole.count(part) == 1:
        return whole.replace(part, replace, 1)
    needle = part.strip()
    if len(needle) >= _SUBSTRING_MIN_LEN and whole.count(needle) == 1:
        return whole.replace(needle, replace.strip(), 1)

    # 8) fenêtre floue par lignes (F-166, équivalent difflib de dmp_lines_apply
    # :338) — DERNIER recours gardé : ratio plancher 0.8 + marge 0.05 sur le
    # second + bloc ≥ 4 lignes non vides. L'application est signalée via
    # last_note pour que le modèle vérifie l'édit.
    fuzzy = _fuzzy_line_window_replace(whole_lines, part_lines, replace_lines)
    if fuzzy is not None:
        new_text, ratio = fuzzy
        replace_most_similar_chunk.last_note = (
            f"matched via fuzzy line window (ratio {ratio:.2f}) — VERIFIE le resultat"
        )
        return new_text

    return None


replace_most_similar_chunk.last_note = ""  # attribut de fonction (F-166)


def find_similar_lines(part: str, whole: str, threshold: float = 0.6) -> Optional[str]:
    """Feedback didactique : quand le remplacement échoue, cherche les lignes du
    fichier les plus proches du bloc SEARCH pour aider le LLM à s'ajuster.
    Renvoie un extrait indicatif, ou None si rien de suffisamment proche."""
    part_lines = [line.strip() for line in part.splitlines() if line.strip()]
    whole_lines = whole.splitlines()
    if not part_lines or not whole_lines:
        return None

    best_idx = 0
    best_score = 0.0
    n = len(part_lines)
    for i in range(len(whole_lines) - n + 1):
        window = [line.strip() for line in whole_lines[i : i + n]]
        matches = sum(1 for a, b in zip(window, part_lines) if a == b)
        score = matches / n
        if score > best_score:
            best_score = score
            best_idx = i

    if best_score < threshold:
        return None
    # Renvoie un extrait contextualisé (avec numéros de ligne) autour du meilleur match.
    start = max(0, best_idx - 1)
    end = min(len(whole_lines), best_idx + n + 1)
    excerpt_lines = []
    for j in range(end - start):
        line = whole_lines[start + j]
        if not line.endswith("\n"):
            line += "\n"
        excerpt_lines.append(f"{start + j + 1:4}| {line}")
    return "".join(excerpt_lines)
