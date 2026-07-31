"""Nettoyage DOM pour Web Tester (Priorité 6 du plan usine logicielle, ligne 108).

Avant d'envoyer le HTML capturé par le navigateur au LLM (Web Tester), on strippe
les balises volumineuses et non pertinentes pour la vérification logique :
`<script>`, `<style>`, `<svg>`, `<canvas>`, `<iframe>`, `<noscript>`, et les
commentaires HTML. Ces blocs représentent souvent l'essentiel des tokens d'une
page (un `<svg>` d'icônes peut peser 50 Ko) sans apporter d'information pour
assertionner le comportement de l'UI.

Inspiré de LlamaBot (nettoyage DOM avant envoi au LLM). Implémentation sans
dépendance (regex + parser tolérant) pour rester léger et ne pas ajouter
BeautifulSoup/lxml au socle.

On ne supprime PAS le contenu sémantique (`<div>`, texte, attributs `aria-*`,
`id`, `class`) : c'est précisément ce que le Web Tester doit inspecter pour ses
assertions fonctionnelles (ex: vérifier qu'un tableau a N lignes triées).
"""

from __future__ import annotations

import re
from typing import Optional

# Balises à supprimer ENTIÈREMENT (contenu inclus). Pour le Web Tester :
# - <script>  : le JS exécuté n'a aucun intérêt de re-lu par le LLM (le tester
#   l'a déjà exécuté via puppeteer) ; c'est juste du bruit tokenique.
# - <style>   : idem pour le CSS (le rendu visuel est capturé par screenshot).
# - <svg>     : les icônes vectorielles sont très verbeuses (paths) et n'aident
#   pas à valider une logique applicative.
# - <canvas>  : blob de pixels, illisible en tant que texte.
# - <iframe>/<noscript>/<template> : contenu imbriqué hors flux principal.
_TAGS_TO_STRIP = (
    "script",
    "style",
    "svg",
    "canvas",
    "iframe",
    "noscript",
    "template",
    "head",  # meta/link/title : bruit pour la logique applicative
)

# Regex précompilée : supprime la balise OUVRANTE, le contenu, et la FERMANTE.
# DOTALL pour que `.` matche les newlines (le contenu des balises est multi-ligne).
# Case-insensitive (HTML tolère <SCRIPT>, <Style>...).
# On construit l'alternance une seule fois à l'import pour la perf.
_STRIP_RE = re.compile(
    r"<(?P<tag>" + "|".join(_TAGS_TO_STRIP) + r")\b[^>]*>.*?</(?P=tag)\s*>",
    re.IGNORECASE | re.DOTALL,
)

# Commentaires HTML <!-- ... --> (peuvent contenir du gros contenu conditionnel).
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# Balises auto-fermantes des mêmes familles (ex: <svg ... />, <canvas ... />, et
# les variants sans fermeture explicite dans un HTML cassé). On supprime aussi.
_SELF_CLOSING_RE = re.compile(
    r"<(?P<tag>" + "|".join(_TAGS_TO_STRIP) + r")\b[^>]*/>",
    re.IGNORECASE,
)

# Colle les whitespace excessive (les suppressions laissent des séries d'espaces
# / newlines vides) pour que le LLM reçoive un texte compact.
_WS_RE = re.compile(r"[ \t]+\n")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def clean_dom_for_llm(html: Optional[str], max_chars: int = 8000) -> str:
    """Nettoie un document HTML avant envoi au LLM.

    Pipeline (chaque étape réduit le bruit tokenique sans perte sémantique pour
    la validation logique) :
      1. Strippe <script>/<style>/<svg>/<canvas>/<iframe>/<noscript>/<template>/<head>.
      2. Supprime les commentaires HTML.
      3. Compacte les whitespace résiduels (espaces en fin de ligne, >=3 newlines).
      4. Tronque à `max_chars` (garde la tête) — filet de sécurité ultime.

    Args:
        html: Le HTML brut capturé (ex: `puppeteer_evaluate("document.documentElement.outerHTML")`).
            None ou chaîne vide renvoie "".
        max_chars: Plafond de longueur du résultat. 8000 par défaut (~2000 tokens),
            cohérent avec les autres budgets du projet (FEEDBACK_MAX_CHARS).

    Returns:
        Le HTML nettoyé, prêt à être injecté dans un prompt LLM.
    """
    if not html:
        return ""

    # 1. Suppression des balises à contenu non-pertinent (ouvrante + contenu + fermante).
    out = _STRIP_RE.sub("", html)
    # 1-bis. Variants auto-fermants (au cas où le HTML est cassé / XHTML).
    out = _SELF_CLOSING_RE.sub("", out)

    # 2. Suppression des commentaires HTML.
    out = _COMMENT_RE.sub("", out)

    # 3. Compactage whitespace : espaces en fin de ligne, puis series de newlines.
    out = _WS_RE.sub("\n", out)
    out = _BLANK_LINES_RE.sub("\n\n", out)

    # 4. Troncature finale (filet de sécurité — un <div> gigantesque pourrait
    # encore dépasser le budget après nettoyage).
    out = out.strip()
    if len(out) > max_chars:
        out = out[:max_chars] + "\n... [tronqué par dom_filter]"

    return out
