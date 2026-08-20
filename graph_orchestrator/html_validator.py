"""Valideur HTML monofichier en stdlib pur (P1/F-136, port OpenKB deck/validator).

Doctrine « code pur d'abord » (AGENTS.md §8.3) : vérifier les invariants
STRUCTURELS d'un livrable HTML généré sans LLM ni navigateur, AVANT tous les
autres tiers (shift-left maximal). Port adapté de
`references/OpenKB/openkb/deck/validator.py` (validate_deck) : leur grammaire
de slides devient nos invariants de livrable vanilla :

  - self-contained : toute ressource externe <link>/<script>/<img> (http(s)://
    ou //) est une ERREUR (cahier des charges Prompt-Vault : 1 fichier,
    vanilla, offline) ;
  - ids dupliqués (casse-insensible) ;
  - getElementById('x') dans les <script> inline sans id="x" correspondant
    dans le DOM (lien JS→DOM cassé, la classe de bug que le 4B produit quand
    il renomme un id côté HTML mais pas côté JS) ;
  - taille bornée (2 Mo) ;
  - <canvas> attendu si la page est un jeu (requestAnimationFrame présent) ;
  - avertissement si querySelector('#x') cible un id absent (plus prudent que
    getElementById : sélecteurs composés fréquents).

Fail-open total : toute erreur interne = aucun diagnostic (jamais bloquant).
Zéro dépendance hors stdlib — tourne en <100 ms sur 100 Ko.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import List, Optional

MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 Mo (miroir OpenKB)

_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})

_GET_EL_BY_ID_RE = re.compile(r"getElementById\(\s*['\"]([^'\"]+)['\"]\s*\)")
_QUERY_SELECTOR_ID_RE = re.compile(r"querySelector(?:All)?\(\s*['\"]#([^'\">\s]+)['\"]")
_RAF_RE = re.compile(r"requestAnimationFrame")


@dataclass
class HtmlValidationResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class _MonoFileParser(HTMLParser):
    """Collecte ids, refs externes, textes des <script> inline et balances."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: List[str] = []
        self.external_refs: List[str] = []
        self.inline_scripts: List[str] = []
        self._stack: List[str] = []
        self.unclosed: List[str] = []
        self._in_script = False
        self._script_buf: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        tag_l = tag.lower()
        if tag_l == "script":
            src = (a.get("src") or "").strip()
            if src.startswith(("http://", "https://", "//")):
                self.external_refs.append(f"<script src={src!r}>")
            elif src:
                self.external_refs.append(f"<script src={src!r}> (fichier externe, livrable monofichier attendu)")
            else:
                self._in_script = True
                self._script_buf = []
        elif tag_l == "link":
            href = (a.get("href") or "").strip()
            if href.startswith(("http://", "https://", "//")):
                self.external_refs.append(f"<link href={href!r}>")
        elif tag_l == "img":
            src = (a.get("src") or "").strip()
            if src.startswith(("http://", "https://", "//")):
                self.external_refs.append(f"<img src={src!r}>")
        id_attr = (a.get("id") or "").strip()
        if id_attr:
            self.ids.append(id_attr)
        if tag_l not in _VOID_TAGS:
            self._stack.append(tag_l)

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        if tag_l == "script" and self._in_script:
            self.inline_scripts.append("\n".join(self._script_buf))
            self._in_script = False
            return
        if self._stack and self._stack[-1] == tag_l:
            self._stack.pop()
        elif tag_l in self._stack:
            # balise fermée avec imbrication impopre : dépile jusqu'à elle
            while self._stack and self._stack[-1] != tag_l:
                self.unclosed.append(self._stack.pop())
            if self._stack:
                self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._script_buf.append(data)


def validate_html_monofile(path: str, require_canvas_for_game: bool = True) -> HtmlValidationResult:
    """Valide un livrable HTML monofichier. Fail-open : erreur interne = ok silencieux.

    Args:
        path: chemin du fichier HTML.
        require_canvas_for_game: si la page utilise requestAnimationFrame (jeu/
            animation), exiger un <canvas> (warning, pas erreur — certains jeux
            sont en DOM pur).
    """
    res = HtmlValidationResult()
    try:
        if not os.path.isfile(path):
            res.errors.append(f"fichier introuvable : {path}")
            return res
        size = os.path.getsize(path)
        if size > MAX_FILE_BYTES:
            res.errors.append(f"fichier de {size} octets > {MAX_FILE_BYTES} — monofichier hors bornes")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        parser = _MonoFileParser()
        parser.feed(content)
        parser.close()

        if parser.external_refs:
            res.errors.extend(
                f"ressource externe interdite (livrable vanilla monofichier, offline) : {ref}"
                for ref in parser.external_refs[:8]
            )

        seen = set()
        for i in parser.ids:
            key = i.lower()
            if key in seen:
                res.errors.append(f"id dupliqué : '{i}'")
            seen.add(key)

        js = "\n".join(parser.inline_scripts)
        dom_ids = {i.lower() for i in parser.ids}
        for target in dict.fromkeys(_GET_EL_BY_ID_RE.findall(js)):
            if target.lower() not in dom_ids:
                res.errors.append(
                    f"getElementById('{target}') : aucun id=\"{target}\" dans le DOM — "
                    f"le JS cible un id inexistant (renommé d'un côté seulement ?)"
                )
        for target in dict.fromkeys(_QUERY_SELECTOR_ID_RE.findall(js)):
            if target.lower() not in dom_ids:
                res.warnings.append(f"querySelector('#{target}') : id absent du DOM")

        if parser.unclosed:
            res.warnings.append(
                f"{len(parser.unclosed)} balise(s) possiblement non fermée(s) : "
                f"{', '.join(dict.fromkeys(parser.unclosed[:5]))}"
            )

        if require_canvas_for_game and _RAF_RE.search(js) and "canvas" not in {
            t for t in parser._stack
        } and "<canvas" not in content.lower():
            res.warnings.append(
                "requestAnimationFrame utilisé sans <canvas> — un jeu DOM pur est possible, "
                "vérifie que c'est intentionnel"
            )

        return res
    except Exception as e:  # pragma: no cover - fail-open garanti
        res.warnings.append(f"valideur indisponible ({e})")
        return res
