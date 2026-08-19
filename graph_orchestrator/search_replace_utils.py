"""Logique d'édition SEARCH/REPLACE tolérante, portée depuis Aider.

Les petits LLM locaux (qwen3.5:4b, Gemma) corrompent les gros contenus passés
en argument JSON d'un tool_call (cf. bug run #11 : HTML cassé). La solution est
l'édition par bloc SEARCH/REPLACE : on ne demande au modèle que le fragment à
remplacer et son substitut, ce qui limite la quantité de texte à générer dans un
seul argument, et on tolère les imprécisions de formatage classiques des petits
modèles (indentation, lignes vides, ellipses).

Porté depuis references/aider/aider/coders/editblock_coder.py :
  - replace_most_similar_chunk (l.157) : orchestrateur des stratégies.
  - replace_part_with_missing_leading_whitespace (l.243) : tolérant indentation.
  - try_dotdotdots (l.190) : gère les ellipses `...`.
  - find_similar_lines (adapté) : feedback "Did you mean..." en cas d'échec.

Aide: https://aider.chat — licence MIT. Cette réimplémentation est volontairement
allégée (pas de fuzzy edit-distance, qui est neutralisé dans aider lui-même).
"""

import re
from typing import Optional

# Longueur minimale de la sous-chaîne pour le fallback 6) de
# replace_most_similar_chunk : en dessous, une occurrence unique est trop
# probablement un aiguillage générique (identifiant court, ponctuation...).
_SUBSTRING_MIN_LEN = 8


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
    gracieuse : match exact → tolérant indentation → ellipses → match stripped lines.
    Renvoie le nouveau `whole` ou None si rien ne matche. Porté d'aider (l.157), sans fuzzy edit-distance.
    """
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

    # 6) sous-chaîne exacte (post-mortem run 2026-08-19, Tetris) : le 4B fournit
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

    return None


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
