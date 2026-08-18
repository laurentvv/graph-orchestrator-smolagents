"""Static Tester déterministe (F-49) — gatekeeper web AVANT le Tester LLM.

Implémente la méthodologie prouvée de `debug/MANUAL_TESTER_METHODOLOGY.md` :
un Tester 0-LLM qui attrape ~80% des bugs web en <6s, là où le Tester LLM
(gemma-4-12B) met 25 min et rate des bugs évidents (biais de confirmation
documenté sur les « barres invisibles »).

PAS DE REDONDANCE avec le Linter (F-30) : le Linter SAUTE le JS inline du
HTML (`linter.py` ligne `lang != "html"` — tree-sitter-html parse le contenu
des balises script comme du texte, d'où 77 faux positifs sur un HTML correct).
Le Static Tester, lui, extrait ce JS et le valide pour de vrai avec Node.

DEUX ÉTAGES (fail-fast) :

  Tier 1 — Statique pur (0 dépendance hors `node`, <1s) :
    (1a) node --check sur le JS extrait → SyntaxError (TS-in-vanilla,
         accolades non fermées). Le bug n°1 du Coder (page blanche).
    (1b) wiring addEventListener → élément interactif non branché. Le bug
         indétectable par screenshot (le contrôle s'affiche mais est inactif).

  Tier 2 — Runtime DevTools (~5s, si Chrome dispo) :
    (2) visibilité DOM (getBoundingClientRect().height) → éléments créés en
        JS mais invisibles (bug CSS height:% sur conteneur sans hauteur).
        C'est LE check qui a attrapé les barres invisibles que le LLM a ratées.

  Tier HTTP (F-100, niveau nœud, après les Tiers 1-4 propres) :
    preuve exécutable de service (port hermes-agent verify/) : recette
    détectée au niveau du dossier (static-web http.server par défaut, ou la
    commande start du projet si package.json/pyproject/Makefile…), start sur
    un port LIBRE, sonde readiness HTTP, teardown de l'arbre de process.
    « La page est servie et répond » au lieu de file:// seul. Readiness KO =
    réfutation SAUF recette static-web (notre infra, pas le code du modèle →
    note). STATIC_TESTER_HTTP=0 pour désactiver.

GÉNÉRIQUE : le Static Tester ne connaît PAS la demande à l'avance. Il analyse
le HTML/JS réellement produit par le Coder (découvre les contrôles, les
sélecteurs, extrait le JS). Il marche sur n'importe quelle page web, pas
seulement Bubble Sort.

ROBUSTESSE : dégradation gracieuse à tous les étages.
  - `node` absent (FileNotFoundError) → Tier 1a skip, pas d'échec faux.
  - Chrome absent / opt-out → Tier 2 skip, tier_reached="tier1".
  - STATIC_TESTER_ENABLED=0 → nœud entier en pass-through (success direct).
Aucune cassure : le Tester LLM reste l'arbitre final pour le visuel + les
comportements subtils. Le Static Tester ne fait que court-circuiter les
échecs évidents pour économiser un cycle LLM (cf. pattern Linter F-30).
"""

from __future__ import annotations

import logging
import os
import re
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# F-72 (Prompt Offloading) : _run_node_check et la constante _MAX_JS_CHARS sont
# extraits vers js_utils.py (partagés avec l'outil check_js_syntax du Coder).
# Alias privés pour préserver le code appelant (0 changement comportemental).
from .js_utils import MAX_JS_CHARS as _MAX_JS_CHARS, run_node_check as _run_node_check

from .logging_utils import NodeMetrics
from .models import CoderOutput

logger = logging.getLogger(__name__)

# ==========================================
# Tier 1a — Extraction du JS + node --check (méthode étape 2)
# ==========================================
# Matche <script ...>...</script> SANS attribut src (JS inline uniquement).
# Les <script src="app.js"> pointent vers un fichier externe qu'on n'a pas
# sous la main ici — on ne les valide pas (pas de faux négatif).
_SCRIPT_INLINE_RE = re.compile(
    r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


_SCRIPT_EXTERNAL_RE = re.compile(
    r'<script[^>]*\bsrc\s*=\s*["\']([^"\']+)["\'][^>]*>',
    re.IGNORECASE
)

def extract_all_js(html: str, html_path: str = None) -> str:
    """Extrait le JS (inline + externe) pour l'analyse statique."""
    if not html:
        return ""
    blocks = _SCRIPT_INLINE_RE.findall(html)
    js_blocks = [b.strip() for b in blocks if b.strip()]
    
    if html_path:
        base_dir = os.path.dirname(html_path)
        for m in _SCRIPT_EXTERNAL_RE.finditer(html):
            src = m.group(1)
            if src.startswith("http") or src.startswith("//") or os.path.isabs(src):
                continue
            script_path = os.path.join(base_dir, src)
            try:
                with open(script_path, "r", encoding="utf-8", errors="replace") as f:
                    js_blocks.append(f.read().strip())
            except OSError:
                pass
                
    return "\n\n".join(js_blocks)


def _check_js_syntax(js: str) -> List[str]:
    """Tier 1a : valide la syntaxe du JS via `node --check`."""
    if not js.strip():
        return []  # rien à valider

    if len(js) > _MAX_JS_CHARS:
        js = js[:_MAX_JS_CHARS]  # sécurité : éviter ligne de commande trop longue

    code, stderr = _run_node_check(js)
    if code == 0 or not stderr:
        return []

    # node --check stderr contient le type d'erreur + ligne/colonne + extrait.
    # On garde les 2 premières lignes (type + localisation) — assez pour le Coder.
    lines = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
    detail = " ; ".join(lines[:2]) if lines else "syntaxe invalide"
    return [f"[node --check] SyntaxError JS : {detail}. "
            f"Causes fréquentes : annotation TypeScript (`: type`, `as Cast`, "
            f"`interface`) dans du JS vanilla, accolade/parenthèse non fermée. "
            f"Le navigateur lèvera SyntaxError et RIEN ne s'exécutera (page blanche)."]


# ==========================================
# Tier 1b — Wiring addEventListener (méthode étape 4)
# ==========================================
# Éléments interactifs à vérifier (le « branchement » au JS).
_INTERACTIVE_RE = re.compile(
    r"<(button|input|select|a)\b([^>]*)>(?:.*?</\1>)?",
    re.IGNORECASE | re.DOTALL,
)
_ID_ATTR_RE = re.compile(r'\bid\s*=\s*["\']?([\w-]+)', re.IGNORECASE)
_TYPE_ATTR_RE = re.compile(r'\btype\s*=\s*["\']?(\w+)', re.IGNORECASE)
_ROLE_ATTR_RE = re.compile(r'\brole\s*=\s*["\']?([\w-]+)', re.IGNORECASE)
_HREF_ATTR_RE = re.compile(r'\bhref\s*=\s*["\']?([^"\s>]+)', re.IGNORECASE)
_ONCLICK_RE = re.compile(r"\bon\w+\s*=", re.IGNORECASE)  # onclick=, onchange=, ...
# Add handlers JS : addEventListener OU getElementById('id') OU querySelector('#id').
_ADD_EVENT_RE = re.compile(r"addEventListener\s*\(", re.IGNORECASE)
_GETBY_RE = re.compile(
    r"getElementById\s*\(\s*['\"]([\w-]+)['\"]|querySelector\s*\(\s*['\"]#([\w-]+)",
    re.IGNORECASE,
)


def _line_of(html: str, needle: str) -> int:
    """Retourne le numéro de ligne (1-based) de la 1ère occurrence de needle."""
    idx = html.find(needle)
    if idx == -1:
        return 0
    return html.count("\n", 0, idx) + 1


def _check_event_wiring(html: str, js: str) -> List[str]:
    """Tier 1b : vérifie que chaque contrôle interactif est branché au JS."""
    errors: List[str] = []

    combined = html + "\n" + js
    referenced_ids: set = set()
    for m in _GETBY_RE.finditer(combined):
        referenced_ids.add(m.group(1) or m.group(2))
        
    has_any_handler = bool(_ADD_EVENT_RE.search(combined)) or bool(_ONCLICK_RE.search(html))

    for tag, attrs in _INTERACTIVE_RE.findall(html):
        type_m = _TYPE_ATTR_RE.search(attrs)
        el_type = (type_m.group(1).lower() if type_m else "").lower()

        # Contournements légitimes (pas besoin de JS) :
        if tag.lower() == "a":
            href_m = _HREF_ATTR_RE.search(attrs)
            if href_m and href_m.group(1) and not href_m.group(1).startswith("#"):
                continue  # lien réel (navigation native)
        if tag.lower() == "input" and el_type in ("hidden", "submit", "button"):
            continue  # hidden pas interactif ; submit/button gérés nativement en form
        if tag.lower() == "button" and el_type == "submit":
            continue  # submit natif dans <form>

        # Attribut onclick/onchange inline → branché (OK).
        if _ONCLICK_RE.search(attrs):
            continue

        # id de l'élément — si absent, on ne peut pas conclure (le Coder peut
        # le cibler par classe via querySelector). On ne flag que les éléments
        # AVEC un id clair, non référencés en JS.
        id_m = _ID_ATTR_RE.search(attrs)
        if not id_m:
            continue  # pas d'id → pas de conclusion fiable, on laisse le LLM juger
        el_id = id_m.group(1)

        # Référencé en JS via getElementById/querySelector('#id') → branché.
        if el_id in referenced_ids:
            continue

        # id cité textuellement quelque part dans un addEventListener ?
        # (pattern : addEventListener('click', () => { ... speedSlider ... }))
        # Recherche l'occurrence de l'id hors du tag HTML lui-même.
        # Heuristique simple : l'id apparaît dans le JS extrait.
        # On refait la recherche sur le HTML complet — suffisant.
        # (on a déjà vérifié referenced_ids qui couvre les cas typiques)
        # Si pas d'handler global DU TOUT → c'est sûrement un bug de wiring.
        if not has_any_handler:
            line = _line_of(html, f'id="{el_id}"') or _line_of(html, f"id='{el_id}'")
            errors.append(
                f"[wiring] Élément interactif sans handler : <{tag} id=\"{el_id}\"> "
                f"(ligne ~{line}). Aucun addEventListener ni onclick détecté dans "
                f"la page. Un contrôle visible DOIT être connecté au JS via "
                f"addEventListener (ex: document.getElementById('{el_id}')"
                f".addEventListener('click', ...)) sinon il est inactif."
            )
        # else: il y a des handlers globaux mais l'id n'est pas explicitement
        # référencé. Risque de FP si branché par classe → on ne flag PAS
        # (le LLM Tester vérifiera le comportement réel).

    return errors


# ==========================================
# Tier 2 — Visibilité DOM via DevTools (méthode étape 6)
# ==========================================
# Le check qui a attrapé les barres invisibles : éléments créés en JS (static OK)
# mais rendus à height=0 à cause d'un CSS height:% sur conteneur sans hauteur.
# On découvre les sélecteurs candidats depuis le HTML, on ne hardcode rien.
_CLASS_RE = re.compile(r'class\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
# Classes assignées en JS : b.className = "bar" | el.classList.add("bar")
# (la classe n'apparaît PAS dans le HTML si l'élément est créé dynamiquement).
_JS_CLASSNAME_RE = re.compile(
    r'\.className\s*=\s*["\']([^"\']+)["\']|\.classList\.add\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
# Conteneurs typiquement peuplés dynamiquement (le Coder y append des enfants).
_DYNAMIC_CONTAINER_HINTS = (
    "appendchild", "innerhtml", "insertbefore", "createelement",
)
# Noms de boutons « primaire » (démarre l'action principale = peuple le DOM).
# GÉNÉRIQUE : on cherche des mots communs, pas un id spécifique.
_PRIMARY_ACTION_RE = re.compile(
    r'id\s*=\s*["\']?((?:start|go|run|play|generate|init|launch|submit)[\w-]*)',
    re.IGNORECASE,
)


# Post-mortem run #3 (2026-08-14, rejet utilisateur) : noms de variables typiques
# d'un compteur affiché à l'utilisateur (comparaisons, échanges, passes...).
_COUNTER_NAME_RE = re.compile(
    r"\b\w*(count|counter|comparisons?|comparaisons?|swaps?|moves?|steps?|iterations?|passes?)\b",
    re.IGNORECASE,
)

# Chars autorisés dans une expression de délai APRÈS substitution des variables
# (éval sécurisée : aucun nom, aucun appel — que de l'arithmétique littérale).
_SAFE_ARITH_RE = re.compile(r"^[\d+\-*/(). ]+$")


def _resolve_delay_ms(arg: str, js: str) -> Optional[int]:
    """Résout l'argument de délai `sleep(...)`/`setTimeout(...)` en millisecondes.

    F-112 (post-mortem run #8) : l'ancienne résolution ne voyait que les
    littéraux (`sleep(5)`) et les variables liées à un littéral (`speed` avec
    `let speed = 5`). Le bug du run #8 était une FORMULE : `sleep(320 - speed*2)`
    avec `let speed = 320` → −320 ms → clampé à 0 par setTimeout → animation
    instantanée, invisible du grep. On substitue donc TOUTES les variables liées
    à un littéral entier, puis on évalue l'arithmétique résultante si (et seulement
    si) il ne reste que des chiffres et des opérateurs (jamais de nom, jamais
    d'appel — pas d'eval arbitraire).

    Returns:
        Le délai en ms (peut être négatif — c'est le bug qu'on chasse), ou None
        si non résolvable (on ne conclut pas, fail-open).
    """
    arg = arg.strip()
    if not arg:
        return None
    if re.fullmatch(r"\d+", arg):
        return int(arg)
    # Substitue chaque identifiant lié à un littéral entier dans le source
    # (`let|var|const name = <int>`). Les variables non liées laissent des
    # résidus alphabétiques → l'expression est rejetée par _SAFE_ARITH_RE.
    substituted = arg
    for m in re.finditer(r"\b(?:let|var|const)\s+(\w+)\s*=\s*(\d+)\b", js):
        substituted = re.sub(rf"\b{re.escape(m.group(1))}\b", m.group(2), substituted)
    stripped = substituted.strip()
    if stripped.isdigit():
        return int(stripped)
    if not _SAFE_ARITH_RE.match(stripped):
        return None
    try:
        value = eval(substituted, {"__builtins__": {}}, {})  # noqa: S307 — whitelist arith ci-dessus
    except (ZeroDivisionError, SyntaxError, ValueError, TypeError):
        return None
    return int(round(value))


def _check_behavioral_smells(js: str) -> List[str]:
    """Tier 1c — smels comportementaux greppables (0 LLM, 0 Chrome).

    Post-mortem run #3 : le Tier 3 (temporel) était AVEUGLE sur le bug car il
    exige t1 > t0 (le compteur doit avancer) pour détecter l'animation
    instantanée — or le compteur était MORT (0→0), les deux bugs se cachaient
    mutuellement. Ces checks statiques attrapent chaque bug À LA SOURCE, dans
    le source JS :

    (a) COMPTEUR MORT : variable au nom compteur, initialisée à 0, AFFICHÉE à
        l'utilisateur (assignation textContent/innerText/innerHTML ou template
        `${var}`), mais JAMAIS incrémentée (`x++` / `x +=` / `x = x +`).
        → run3 : `let comparisons = 0` affiché mais aucun `comparisons++`.
    (b) ANIMATION INSTANTANÉE : délai par étape résoluble à < 20 ms —
        `sleep(N)` / `setTimeout(fn, N)` où N est un littéral < 20, OU un
        identifiant dont la déclaration `let x = N` vaut < 20 (run3 :
        `await sleep(speed)` avec `let speed = 5` → 5 ms/étape au lieu de
        50-300 ms). Pour setTimeout, on ne flague qu'en présence d'un mot-clé
        d'animation (animate/sort/step/frame/speed) — un `setTimeout(fn, 0)`
        de deferral reste légitime hors contexte d'animation.
    """
    errors: List[str] = []
    if not js:
        return errors

    # --- (a) compteur mort ---
    displayed: set = set()
    for m in re.finditer(
        r"(?:textContent|innerText|innerHTML)\s*=\s*[`\"']?[^`\"';]*?\b([A-Za-z_$][\w$]*)\b", js
    ):
        if _COUNTER_NAME_RE.search(m.group(1)):
            displayed.add(m.group(1))
    for m in re.finditer(r"\$\{\s*([A-Za-z_$][\w$]*)\s*\}", js):
        if _COUNTER_NAME_RE.search(m.group(1)):
            displayed.add(m.group(1))
    for name in displayed:
        incremented = re.search(
            rf"\b{re.escape(name)}\s*(?:\+\+|\+=|=\s*{re.escape(name)}\s*\+)", js
        )
        starts_at_zero = re.search(rf"\b{re.escape(name)}\s*=\s*0\b", js)
        if starts_at_zero and not incremented:
            errors.append(
                f"[behavior] Compteur '{name}' affiché à l'utilisateur mais JAMAIS "
                f"incrémenté dans le code (initialisé à 0, aucun `{name}++`/`{name} += 1`). "
                f"Le compteur restera à 0 à vie — incrémente-le à chaque comparaison/"
                f"échange/étape de l'algorithme."
            )

    # --- (b) animation instantanée ---
    has_animation_kw = bool(
        re.search(r"\b(animate|animation|sort|step|frame|speed)\w*\b", js, re.I)
    )
    delay_args: list = []
    for m in re.finditer(r"\b(?:await\s+)?sleep\(\s*([^),]+)\)", js):
        delay_args.append((m.group(1).strip(), "sleep"))
    for m in re.finditer(r"setTimeout\(\s*[^,]+,\s*([^),]+)\)", js):
        delay_args.append((m.group(1).strip(), "setTimeout"))
    for arg, kind in delay_args:
        value = _resolve_delay_ms(arg, js)
        if value is None:
            continue
        if kind == "sleep" or has_animation_kw:
            if value < 20:
                detail = (
                    f" (valeur NÉGATIVE — setTimeout la clamp à 0 → instantané total)"
                    if value < 0
                    else f" (des centaines d'étapes × {value} ms < 2 s)"
                )
                errors.append(
                    f"[behavior] Délai d'animation de {value} ms par étape "
                    f"(`{kind}({arg})` = {arg}) — l'animation entière est QUASI "
                    f"INSTANTANÉE{detail}. Invariant : le délai effectif par étape "
                    f"doit rester dans 50-300 ms pour TOUTE position du curseur — "
                    f"vérifie l'UNITÉ de ta variable (valeur slider 1-10 ≠ "
                    f"millisecondes) et évalue ta formule de bout en bout (une "
                    f"formule qui peut devenir négative est silencieusement clampée "
                    f"à 0 par setTimeout)."
                )

    # --- (c) compteur incrémenté mais jamais RAFRAÎCHI à l'écran (post-mortem
    # run #6, F-110) : le 4B incrémente la variable (Tier 1c passe) mais
    # n'assigne le textContent qu'une fois AVANT la boucle — le compteur reste
    # visuellement à 0. On exige un rafraîchi d'affichage DANS la boucle,
    # c'est-à-dire après l'incrément.
    for m in re.finditer(
        r"\b(\w*(?:count|counter|comparisons?|comparaisons?|swaps?|moves?|steps?|iterations?|passes?)\w*)\+\+",
        js,
        re.IGNORECASE,
    ):
        name = m.group(1)
        # Uniquement si ce compteur est AFFICHÉ quelque part (variable
        # user-facing) — un compteur interne jamais affiché est hors périmètre
        # (le check (a) couvre déjà « affiché mais jamais incrémenté »).
        displayed_somewhere = re.search(
            r"(?:textContent|innerText|innerHTML)\s*=\s*[^;\n]{0,80}\b" + re.escape(name) + r"\b",
            js,
        ) or re.search(r"\$\{[^}]{0,40}\b" + re.escape(name) + r"\b", js)
        if not displayed_somewhere:
            continue
        loop_tail = js[m.start():m.start() + 400]
        refreshed = re.search(
            r"textContent\s*=|innerText\s*=|innerHTML\s*=", loop_tail
        )
        if not refreshed:
            errors.append(
                f"[behavior] Compteur '{name}' incrémenté mais son affichage n'est "
                f"JAMAIS rafraîchi dans la boucle (l'assignation textContent doit "
                f"suivre l'incrément, ex: `{name}++; counterEl.textContent = {name};`). "
                f"Sans ça, le compteur affiché reste figé à sa valeur initiale."
            )
    return errors


def _check_canvas_children(html: str, js: str) -> List[str]:
    """F-110 (post-mortem run #6) : des éléments DOM ajoutés DANS un <canvas>.

    Les enfants d'un <canvas> ne sont JAMAIS rendus (le canvas ne dessine que
    via son contexte 2D). Le run #6 a produit 30 divs appendChild'd dans le
    canvas : le tri s'exécutait, mettait à jour des hauteurs... invisibles,
    et le canvas n'était jamais redessiné — animation fantôme, approbation
    Judge indue. Détection croisée HTML (id du canvas) + JS (appendChild).
    """
    errors: List[str] = []
    for cid in re.findall(r"<canvas[^>]*\bid=\"([\w-]+)\"", html):
        if re.search(
            r"getElementById\(\s*['\"]" + re.escape(cid) + r"['\"]\s*\)\s*\.\s*appendChild",
            js,
        ):
            errors.append(
                f"[behavior] Des éléments DOM sont ajoutés DANS le <canvas id=\"{cid}\"> "
                f"(appendChild) — les enfants d'un canvas ne s'affichent JAMAIS. "
                f"Deux choix exclusifs : (a) dessiner les barres via le contexte 2D "
                f"(ctx.fillRect) et rappeler draw() à CHAQUE étape de l'animation, "
                f"ou (b) utiliser un <div> conteneur pour les barres DOM. "
                f"Ne mélange jamais les deux."
            )
    return errors


def _discover_visibility_targets(html: str, js: str) -> List[str]:
    """Découvre les sélecteurs CSS candidats à vérifier pour la visibilité."""
    targets: List[str] = []
    seen = set()

    # 1. Classes assignées en JS (éléments créés dynamiquement) — PRIORITAIRE.
    if js:
        for m in _JS_CLASSNAME_RE.finditer(js):
            cls = (m.group(1) or m.group(2) or "").strip()
            if cls and cls not in seen:
                # On ne garde que le 1er token (className peut être "bar sorted").
                first = cls.split()[0]
                if first not in seen:
                    targets.append(f".{first}")
                    seen.add(first)

    # 2. Classes du HTML citées dans du JS dynamique (appendChild/innerHTML).
    if js:
        js_lower = js.lower()
        for hint in _DYNAMIC_CONTAINER_HINTS:
            if hint in js_lower:
                for m in _CLASS_RE.finditer(html):
                    for cls in m.group(1).split():
                        if cls and cls not in seen and cls in js:
                            targets.append(f".{cls}")
                            seen.add(cls)
                break

    # 3. Fallback : 1ère classe du HTML (item principal) si rien trouvé.
    if not targets:
        for m in _CLASS_RE.finditer(html):
            for cls in m.group(1).split():
                if cls and cls not in seen:
                    targets.append(f".{cls}")
                    seen.add(cls)
                    break
            if targets:
                break

    return targets[:5]  # plafond : 5 sélecteurs (évite un eval trop long)


def _find_primary_action_id(html: str) -> Optional[str]:
    """Trouve l'id d'un bouton d'action primaire (start/go/run/play/generate...).

    GÉNÉRIQUE : cherche des noms communs d'actions principales, pas un id dur.
    Sert à DÉCLENCHER l'action avant la vérif de visibilité (les éléments sont
    souvent créés au clic, pas au load — bug des barres invisibles).

    Returns:
        L'id du bouton primaire, ou None si aucun trouvé.
    """
    m = _PRIMARY_ACTION_RE.search(html)
    return m.group(1) if m else None


def _parse_devtools_json(raw) -> list:
    """Parse le retour de evaluate_script chrome-devtools-mcp en liste de dicts.

    Le retour est wrappé et parfois doublement échappé :
      'Script ran on page and returned:\\n```json\\n"[...\\\"échappé\\\"...]"\\n```'
    On déséchappe par passes successives jusqu'à obtenir une liste Python.
    """
    import json as _json
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, str):
        return []

    text = raw
    # Jusqu'à 3 passes : la string peut être JSON-stringifiée plusieurs fois
    # (le MCP wrappe le retour de la fonction dans JSON.stringify côté navigateur,
    # puis smolagents re-wrappe dans un bloc markdown ```json```).
    for _ in range(3):
        # Extrait le contenu du bloc ```json ... ``` si présent.
        m_block = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        candidate = m_block.group(1).strip() if m_block else text.strip()
        # Tente un parse direct.
        try:
            parsed = _json.loads(candidate)
        except ValueError:
            # Cherche un array ou objet JSON dans le texte.
            m_arr = re.search(r"\[.*\]", candidate, re.DOTALL)
            m_obj = re.search(r"\{.*\}", candidate, re.DOTALL)
            m = m_arr or m_obj
            if not m:
                return []
            try:
                parsed = _json.loads(m.group(0))
            except ValueError:
                # Si la string est elle-même une string JSON échappée, on la
                # déséchappe et on recommence.
                try:
                    text = _json.loads(candidate)
                    if not isinstance(text, str):
                        return text if isinstance(text, list) else []
                    continue
                except ValueError:
                    return []
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            # Un objet unique (ex: sonde Tier 3 retournant {t0, t1, ...}) → on l'enrobe
            # dans une liste pour garder une API homogène (les appelants itèrent).
            return [parsed]
        if isinstance(parsed, str):
            # parsed est encore une string (contenu doublement stringifié) → reloop.
            text = parsed
            continue
        return []  # scalar → pas ce qu'on cherche
    return []


def _evaluate_visibility(
    devtools_tools: list, url: str, selectors: List[str], primary_action_id: Optional[str] = None
) -> List[str]:
    """Tier 2 : ouvre l'URL dans DevTools, déclenche l'action primaire, vérifie
    que les éléments sont visibles.

    Étape 7 de la méthodologie (« capture APRÈS interaction ») : beaucoup de
    pages créent leurs éléments au clic (start/generate), pas au load. Sans
    déclencher l'action, un bug de visibilité sur ces éléments serait invisible.

    Args:
        primary_action_id: id d'un bouton primaire à cliquer avant la vérif.
            None = vérification à l'état initial uniquement.

    Returns:
        Liste d'erreurs. Vide si tout est visible OU si DevTools indispo/erreur.
    """
    if not devtools_tools or not selectors:
        return []

    # Trouve les outils navigate_page et evaluate_script par nom.
    by_name = {getattr(t, "name", str(t)): t for t in devtools_tools}
    navigate = by_name.get("navigate_page") or by_name.get("navigate")
    evaluate = by_name.get("evaluate_script") or by_name.get("evaluate")
    if not navigate or not evaluate:
        logger.debug("Static Tester : outils DevTools navigate/evaluate absents — skip Tier 2.")
        return []

    def _eval(js_source: str):
        """Appelle evaluate_script en s'adaptant à sa signature (function/script)."""
        inputs = getattr(evaluate, "inputs", {}) or {}
        if "script" in inputs:
            return evaluate(script=js_source)
        if "function" in inputs:
            return evaluate(function=js_source)
        return evaluate(js_source)  # fallback (1er param positionnel)

    try:
        # navigate_page(url=*)
        nav_kwargs = {"url": url}
        if "url" not in (getattr(navigate, "inputs", {}) or {}):
            nav_kwargs = {}
        navigate(**nav_kwargs)

        # Étape 7 + étape 6 COMBINÉES en UN seul evaluate_script synchrone :
        # on déclenche l'action primaire (clic) PUIS on probe la visibilité, dans
        # le même appel. C'est plus fiable qu'un clic séparé (le handler peut
        # être async, le probe séparé peut s'exécuter avant la mise à jour du DOM).
        # Sans ça, le bug des barres invisibles (créées au clic) est indétectable.
        # NB : chrome-devtools-mcp evaluate_script attend une DÉCLARATION de
        # fonction (qu'il exécute lui-même), PAS une IIFE `(() => {...})()`.
        sel_list = ", ".join(f"'{s}'" for s in selectors)
        click_clause = ""
        if primary_action_id:
            click_clause = (
                f" const _b = document.getElementById('{primary_action_id}');"
                f" if (_b) {{ _b.click(); }}"
                # Settle wait (fix faux-positif run 2026-08-11) : le handler du bouton
                # primaire peut être async ou déclencher un re-render. Sans ce wait, le
                # probe getBoundingClientRect s'exécute AVANT la mise à jour du DOM →
                # height=0 transitoire → faux "INVISIBLE". 150ms laisse le DOM se stabiliser
                # (un élément VRAIMENT invisible reste invisible après 150ms, donc pas de
                # faux négatif). Pattern async vérifié sur le Tier 3 temporal ci-dessous.
                f" await new Promise(r => setTimeout(r, 150));"
            )
        js_probe = (
            "async () => {" + click_clause +
            "  const sels = [" + sel_list + "];"
            "  const out = [];"
            "  for (const sel of sels) {"
            "    const els = document.querySelectorAll(sel);"
            "    if (els.length === 0) continue;"  # pas créé → on ne conclut pas (Tier 1 dira)
            "    const first = els[0];"
            "    const r = first.getBoundingClientRect();"
            "    const cs = getComputedStyle(first);"
            # Un élément est « invisible » si height==0 (pas de hauteur visible =
            # la cause du bug des barres invisibles : height:% résolu à 0), OU si
            # le CSS le masque explicitement (display:none / visibility:hidden).
            # On NE flag PAS sur width==0 seul : en flexbox, un enfant sans
            # flex-basis est réduit à width=0 bien qu'affiché (faux positif).
            # Run #13 (F-124) : un `background: linear-gradient(…)` vit dans
            # background-image, PAS dans backgroundColor (qui reste transparent)
            # → ne flaguer « sans fond » que si l'élément n'a NI couleur NI
            # image de fond, sinon toute barre à gradient est un faux « INVISIBLE ».
            "    const hidden = (r.height === 0 "
            "                     || cs.display === 'none' || cs.visibility === 'hidden' "
            "                     || cs.opacity === '0' "
            "                     || (first.innerText.trim() === '' && cs.backgroundColor === 'rgba(0, 0, 0, 0)' && cs.backgroundImage === 'none' && !['img','svg','canvas'].includes(first.tagName.toLowerCase())));"
            # Run #14 (barres plates, F-124) : si le JS crée ≥10 éléments pour ce
            # sélecteur (barres de visualiseur), on mesure la DISTRIBUTION des
            # hauteurs. Signature du bug flex-direction:column + flex:1 : toutes
            # les hauteurs quasi égales (flex-basis écrase style.height) ET
            # pleine largeur (bandes horizontales au lieu de barres verticales).
            "    let flat = false;"
            "    if (els.length >= 10) {"
            "      let minH = Infinity, maxH = 0;"
            "      for (const el of els) { const h = el.getBoundingClientRect().height;"
            "        if (h < minH) minH = h; if (h > maxH) maxH = h; }"
            "      const pw = (first.parentElement || document.body).getBoundingClientRect().width;"
            "      flat = (maxH - minH) <= Math.max(1, maxH * 0.1) && r.width >= pw * 0.8;"
            "    }"
            "    out.push({sel, count: els.length, h: r.height, hidden, flat});"
            "  }"
            "  return JSON.stringify(out);"
            "}"
        )
        raw = _eval(js_probe)
        # Le retour chrome-devtools-mcp est wrappé + parfois doublement échappé :
        # 'Script ran on page and returned:\n```json\n"[...échappé...]"\n```'
        # On extrait le JSON de façon robuste (plusieurs passes de déséchappement).
        result_list = _parse_devtools_json(raw)

        errors: List[str] = []
        for item in result_list:
            if not isinstance(item, dict):
                continue
            sel = item.get("sel", "?")
            count = item.get("count", 0)
            hidden = item.get("hidden", False)
            if count > 0 and hidden:
                h = item.get("h", 0)
                errors.append(
                    f"[DOM] {count} élément(s) \"{sel}\" créé(s) par le JS mais "
                    f"INVISIBLE(s) (height={h}, display:none, visibility:hidden, opacity:0, ou aucun fond (ni couleur ni image) sans texte). "
                    f"Bug CSS probable : `height` en pourcentage sur conteneur "
                    f"sans `height` explicite, élément en `position:absolute` hors écran, "
                    f"ou perte de classe CSS de couleur (ex: élément devenu transparent). Vérifie le CSS et le Javascript (classList)."
                )
            # Run #14 (barres plates, F-124) : ≥10 éléments aux hauteurs quasi
            # toutes égales ET pleine largeur = flex-basis:0 écrase style.height
            # (flex-direction:column + flex:1). Le livrable est « visible » mais
            # géométriquement FAUX (bandes plates au lieu de barres verticales).
            if count >= 10 and item.get("flat", False):
                errors.append(
                    f"[DOM] {count} éléments \"{sel}\" quasi IDENTIQUES (hauteurs égales, pleine largeur) : "
                    f"la hauteur proportionnelle des données est ÉCRASÉE. Bug de géométrie typique : "
                    f"conteneur `flex-direction:column` + `flex:1` sur les enfants (flex-basis:0 écrase "
                    f"style.height — run #14). Correction : conteneur `display:flex` (ROW) + "
                    f"`align-items:flex-end` + hauteur px/% inline par barre."
                )
        return errors
    except Exception as e:
        # Tier 2 est fragile (API DevTools, Chrome qui ne lance pas, etc.).
        # On ne fait JAMAIS échouer le nœud sur une erreur Tier 2 — on skip.
        logger.debug("Static Tester Tier 2 skip (%s).", e)
        return []


# ==========================================
# Tier 3 — Animation temporelle via DevTools (anti "animation instantanée")
# ==========================================
# Le bug : performStep() (appelée par requestAnimationFrame) contient les boucles
# imbriquées complètes de l'algorithme → tout s'exécute en 1 tick JS → animation
# instantanée invisible, delay/slider inopérants. Ni le Tier 1 (JS valide, tout wireé)
# ni le Tier 2 (barres visibles) ne le voient. Le Tester LLM non plus : son pattern
# d'animation (wait 2s then check final state) passe même si l'animation a duré 0 ms.
#
# Détection : on clique l'action primaire, on attend une fenêtre courte (400 ms), puis
# on vérifie si l'état est déjà stabilisé (ne progresse plus). F-112 (post-mortem
# run #8) : la sonde est MULTI-SIGNAL — TOUS les éléments numériques du DOM (clés
# par id) + hash des pixels du premier <canvas> + classes terminales. La version
# précédente ne suivait que le PREMIER élément numérique = le libellé du slider
# (une constante placée avant le compteur) → t0=t1=t2 → skip silencieux.
#
# Si un signal a progressé (t1 != t0) ET qu'aucun ne bouge plus dans la fenêtre de
# stabilisation (t2 == t1 partout) → tout s'est joué en < 400 ms → animation
# instantanée. Aucun signal n'a progressé → on ne conclut pas (jamais de FP).

# Fenêtre d'observation (ms). Assez courte pour rester déterministe, assez longue pour
# qu'au moins une frame ait eu lieu (une animation légitime progresse déjà à ce stade).
_TIER3_OBSERVE_MS = 400
# Fenêtre secondaire (ms) pour mesurer la stabilisation : snapshot t1, attend cette
# durée, snapshot t2. Si t2 == t1, l'animation est stabilisée (terminée).
# F-112 (post-mortem run #8) : 50 ms → 350 ms. À 50 ms, une animation LÉGITIME avec
# un pas de 100-300 ms (slider lent) pouvait sembler « stabilisée » entre deux pas
# → faux positif. 350 ms garantit qu'un pas ≤ 350 ms est vu bouger dans la fenêtre.
_TIER3_STABILIZATION_MS = 350




# Post-mortem run #5 (F-109) : exceptions JS runtime = crash déterministe.
_CONSOLE_ERROR_RE = re.compile(
    r"Uncaught|\b(TypeError|ReferenceError|SyntaxError|RangeError|URIError|ImportError)\b"
)


def _check_console_errors(devtools_tools, url, primary_action_id=None):
    """Tier 4 : charge la page à frais, déclenche l'action primaire, lit la console.

    Toute exception JS non interceptée (ex: le null textContent du run #5) est
    un crash RUNTIME avéré — indétectable par les checks statiques (syntaxe et
    wiring corrects). Best-effort : DevTools indisponible → [] (jamais de FP).
    """
    if not devtools_tools:
        return []
    by_name = {getattr(t, "name", str(t)): t for t in devtools_tools}
    navigate = by_name.get("navigate_page") or by_name.get("navigate")
    evaluate = by_name.get("evaluate_script") or by_name.get("evaluate")
    console = by_name.get("list_console_messages") or by_name.get("console")
    if not (navigate and console):
        return []
    try:
        nav_kwargs = {"url": url}
        if "url" not in (getattr(navigate, "inputs", {}) or {}):
            nav_kwargs = {}
        navigate(**nav_kwargs)
        # Déclenche l'action primaire (les crashes onClick ne se voient pas au
        # seul chargement) — best-effort, l'absence de bouton n'est pas un échec.
        if primary_action_id and evaluate:
            try:
                inputs = getattr(evaluate, "inputs", {}) or {}
                kwargs = {"function": f"() => {{ const b = document.getElementById('{primary_action_id}'); if (b) b.click(); return 'clicked'; }}"}
                if "function" not in inputs and "script" in inputs:
                    kwargs = {"script": kwargs["function"]}
                evaluate(**kwargs)
            except Exception:
                pass
        raw = console()
        text = str(raw or "")
        errs = [l.strip() for l in text.splitlines() if _CONSOLE_ERROR_RE.search(l)]
        if errs:
            return [
                "[console] Erreur(s) JS RUNTIME après chargement + clic : "
                + " | ".join(e[:170] for e in errs[:3])
                + " — crash avéré (ex: lecture d'une propriété sur null). Corrige "
                  "AVANT final_answer : l'élément ciblé n'existe pas au moment de l'accès."
            ]
        return []
    except Exception as e:
        logger.debug("Static Tester Tier 4 console skip (%s).", e)
        return []

def _temporal_verdict(snap: dict, primary_action_id: Optional[str]) -> List[str]:
    """Verdict Tier 3 (pur, testable sans Chrome) sur les snapshots multi-signal.

    F-112 (post-mortem run #8) : l'ancienne sonde ne suivait que le PREMIER
    élément numérique du DOM — dans le run #8 c'était le libellé du slider
    (``<span id="speedLabel">5</span>``, une CONSTANTE placée avant le compteur
    dans le DOM) : t0=t1=t2=5 → « aucune progression » → skip silencieux,
    l'animation instantanée passait. La nouvelle sonde suit TOUS les signaux :
      - chaque élément numérique du DOM, clé par id ;
      - le hash des pixels du premier ``<canvas>`` (les apps canvas n'ont souvent
        AUCUN signal DOM exploitable — et les barres ne vivent qu'en pixels) ;
      - le nombre d'éléments à classe terminale (.sorted/.done/...).

    Logique : un signal a PROGRESSÉ si sa valeur a changé après le clic
    (t1 != t0). Si au moins un signal a progressé ET qu'AUCUN ne bouge encore
    dans la fenêtre de stabilisation (t2 == t1 pour tous) → tout l'état final
    a été atteint en < _TIER3_OBSERVE_MS → animation instantanée (FAIL).
    Aucun signal n'a progressé → on ne conclut pas (skip, jamais de FP) ;
    un signal qui bouge encore → animation progressive légitime (OK).

    Args:
        snap: dict renvoyé par la sonde JS : {nums0, nums1, nums2: {id: int},
            term0/term1/term2: int, c0/c1/c2: int|null} ou {reason: 'no-btn'}.
        primary_action_id: id du bouton primaire (pour le message pédagogique).

    Returns:
        Liste d'erreurs (vide si OK / indéterminable).
    """
    if snap.get("reason") == "no-btn":
        return []

    nums0 = snap.get("nums0") or {}
    nums1 = snap.get("nums1") or {}
    nums2 = snap.get("nums2") or {}
    term0, term1, term2 = snap.get("term0"), snap.get("term1"), snap.get("term2")
    c0, c1, c2 = snap.get("c0"), snap.get("c1"), snap.get("c2")

    changed: list = []  # signaux ayant progressé (t1 != t0)
    for key in sorted(set(nums0) | set(nums1)):
        v0, v1 = nums0.get(key), nums1.get(key)
        if v0 is not None and v1 is not None and v0 != v1:
            changed.append(f"compteur '{key}' {v0}→{v1}")
    if term0 is not None and term1 is not None and term0 != term1:
        changed.append(f"éléments terminaux {term0}→{term1}")
    canvas_available = c0 is not None and c1 is not None
    if canvas_available and c0 != c1:
        changed.append("canvas (pixels)")

    if not changed:
        # Rien n'a bougé après le clic : animation non démarrée OU signaux
        # indétectables → on ne conclut pas (fail-open, jamais de FP).
        return []

    still_moving: list = []  # signaux qui bougent encore (t2 != t1)
    for key in sorted(set(nums1) | set(nums2)):
        v1, v2 = nums1.get(key), nums2.get(key)
        if v1 is not None and v2 is not None and v1 != v2:
            still_moving.append(key)
    if term1 is not None and term2 is not None and term1 != term2:
        still_moving.append("terminaux")
    if canvas_available and c1 is not None and c2 is not None and c1 != c2:
        still_moving.append("canvas")

    if still_moving:
        # Au moins un signal progresse encore → animation progressive réelle.
        return []

    return [
        f"[temporal] Animation instantanée détectée : l'action "
        f"'{primary_action_id}' amène l'état à son terme en moins de "
        f"{_TIER3_OBSERVE_MS} ms, au lieu de progresser sur plusieurs secondes. "
        f"Signaux observés stabilisés dès la fenêtre d'observation : "
        f"{'; '.join(changed)}. Causes typiques : (1) le délai par étape est "
        f"NÉGATIF ou ~0 (setTimeout clampe le négatif à 0 — vérifie l'unité de "
        f"ta variable vitesse : valeur slider ≠ millisecondes) ; (2) tout "
        f"l'algorithme s'exécute dans un seul tick (boucle complète sans "
        f"`await` INTERNE à la boucle de comparaison) ; (3) le rendu "
        f"(draw/render/fillRect) n'est JAMAIS appelé DANS la boucle — le canvas "
        f"ne se repeint qu'à la fin. Corrige : UN `await sleep(50-300ms)` + UN "
        f"appel de rendu PAR comparaison/échange, et le slider doit moduler ce "
        f"délai de bout en bout."
    ]


def _evaluate_temporal(
    devtools_tools: list, url: str, primary_action_id: Optional[str] = None
) -> List[str]:
    """Tier 3 : détecte une animation instantanée (stabilisée en < 400 ms au lieu de
    progresser sur plusieurs secondes).

    F-112 : sonde MULTI-SIGNAL (cf. _temporal_verdict) — tous les éléments
    numériques par id + hash pixels du premier ``<canvas>`` + classes terminales.
    La version précédente ne suivait que le premier élément numérique trouvé,
    qui était une constante (libellé du slider) dans le run #8 → cécité totale
    alors même que le compteur de comparaisons progressait juste après.

    Protocole en UN seul evaluate_script (pattern async documenté, jamais
    d'IIFE) :
      1. Snapshot t0 (tous signaux).
      2. Clic du bouton primaire.
      3. await setTimeout(OBSERVE) — fenêtre d'observation.
      4. Snapshot t1.
      5. await setTimeout(STABILIZATION) + snapshot t2 (mesure de stabilisation).
    Le verdict est rendu par _temporal_verdict (pur, testable sans Chrome).

    Args:
        primary_action_id: id du bouton primaire à cliquer (start/generate/run...).
            None → pas de déclenchement possible, on skip sans flaguer.

    Returns:
        Liste d'erreurs (vide si OK ou si DevTools indispo / indéterminable).
    """
    if not devtools_tools or not primary_action_id:
        return []

    by_name = {getattr(t, "name", str(t)): t for t in devtools_tools}
    navigate = by_name.get("navigate_page") or by_name.get("navigate")
    evaluate = by_name.get("evaluate_script") or by_name.get("evaluate")
    if not navigate or not evaluate:
        logger.debug("Static Tester Tier 3 : outils DevTools navigate/evaluate absents — skip.")
        return []

    def _eval(js_source: str):
        inputs = getattr(evaluate, "inputs", {}) or {}
        if "script" in inputs:
            return evaluate(script=js_source)
        if "function" in inputs:
            return evaluate(function=js_source)
        return evaluate(js_source)

    try:
        nav_kwargs = {"url": url}
        if "url" not in (getattr(navigate, "inputs", {}) or {}):
            nav_kwargs = {}
        navigate(**nav_kwargs)

        # Hash djb2 du dataURL du premier canvas : détection de changement de
        # pixels SANS transporter le PNG (des dizaines de Ko) — le hash tient en
        # un int. toDataURL peut lever sur canvas tainted (images externes) →
        # try/catch → null → signal canvas ignoré (fail-open).
        js_probe = (
            "async () => {"
            "  const nums = () => {"
            "    const out = {};"
            "    for (const el of document.querySelectorAll('[id],[class]')) {"
            "      const m = (el.textContent || '').trim().match(/^\\d+$/);"
            "      if (m && el.id) out[el.id] = parseInt(m[0]);"
            "    }"
            "    return out;"
            "  };"
            "  const term = () => {"
            "    let n = 0;"
            "    for (const s of ['.sorted','.done','.visited','.finished','.completed'])"
            "      n += document.querySelectorAll(s).length;"
            "    return n;"
            "  };"
            "  const canvasHash = () => {"
            "    const c = document.querySelector('canvas');"
            "    if (!c) return null;"
            "    try {"
            "      const data = c.toDataURL();"
            "      let h = 0;"
            "      for (let i = 0; i < data.length; i++)"
            "        h = ((h << 5) - h + data.charCodeAt(i)) | 0;"
            "      return h;"
            "    } catch (e) { return null; }"
            "  };"
            "  const nums0 = nums(); const term0 = term(); const c0 = canvasHash();"
            f"  const btn = document.getElementById('{primary_action_id}');"
            "  if (!btn) { return JSON.stringify({reason: 'no-btn'}); }"
            "  btn.click();"
            f"  await new Promise(r => setTimeout(r, {_TIER3_OBSERVE_MS}));"
            "  const nums1 = nums(); const term1 = term(); const c1 = canvasHash();"
            f"  await new Promise(r => setTimeout(r, {_TIER3_STABILIZATION_MS}));"
            "  const nums2 = nums(); const term2 = term(); const c2 = canvasHash();"
            "  return JSON.stringify({nums0, nums1, nums2, term0, term1, term2, c0, c1, c2});"
            "}"
        )
        raw = _eval(js_probe)
        result_list = _parse_devtools_json(raw)

        # _parse_devtools_json renvoie une liste ; on prend le 1er dict.
        item = None
        for r in result_list:
            if isinstance(r, dict):
                item = r
                break
        if not item:
            return []

        return _temporal_verdict(item, primary_action_id)
    except Exception as e:
        logger.debug("Static Tester Tier 3 skip (%s).", e)
        return []


# ==========================================
# API publique
# ==========================================
@dataclass
class StaticCheckResult:
    """Résultat du check statique d'un fichier HTML."""
    path: str
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    tier_reached: str = "skipped"  # "tier1" | "tier2" | "tier3" | "skipped"


def _detect_html(path: str) -> bool:
    """True si le fichier est du HTML (extension). Déterministe, fiable."""
    ext = os.path.splitext(path)[1].lower()
    return ext in (".html", ".htm")


def static_check_html(
    path: str,
    run_devtools: bool = True,
    devtools_url: Optional[str] = None,
    run_temporal: bool = True,
) -> StaticCheckResult:
    """Check statique complet d'un fichier HTML : Tier 1 (+ Tier 2/3 si activé).

    Args:
        path: Chemin du fichier HTML à valider.
        run_devtools: True pour lancer le Tier 2 (visibilité DOM via Chrome) et
            le Tier 3 (animation temporelle via Chrome). False = Tier 1 seul.
        devtools_url: URL file:/// à passer à navigate_page pour les Tiers 2/3.
            Si None, déduite du path.
        run_temporal: True pour lancer le Tier 3 (détection animation instantanée).
            False = Tier 2 seul. N'a d'effet que si run_devtools=True.

    Returns:
        StaticCheckResult avec is_valid=False si un bug est détecté.
    """
    if not os.path.exists(path):
        return StaticCheckResult(path=path, is_valid=True, tier_reached="skipped")

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            html = f.read()
    except OSError:
        return StaticCheckResult(path=path, is_valid=True, tier_reached="skipped")

    errors: List[str] = []

    js = extract_all_js(html, path)

    # --- Tier 1 (toujours, statique pur) ---
    errors.extend(_check_js_syntax(js))
    errors.extend(_check_event_wiring(html, js))
    # Tier 1c (post-mortem run #3) : smels comportementaux — compteur mort +
    # délai d'animation instantané (les 2 bugs du run #3 que Tier 2/3 ont ratés).
    errors.extend(_check_behavioral_smells(js))
    # F-110 (post-mortem run #6) : éléments DOM ajoutés dans un <canvas> —
    # jamais rendus (anti-pattern canvas/DOM mêlés, animation fantôme).
    errors.extend(_check_canvas_children(html, js))
    tier = "tier1"

    # Décision : si Tier 1 a déjà trouvé un bug SYNTAXE (page blanche garantie),
    # on NE lance pas le Tier 2 (Chrome afficherait juste une page blanche —
    # gaspillage de ~5s). On ne court-circuite que sur node --check FAIL.
    syntax_failed = any(e.startswith("[node --check]") for e in errors)
    if syntax_failed:
        # Page blanche garantie → Tier 2 inutile.
        return StaticCheckResult(path=path, is_valid=False, errors=errors, tier_reached="tier1")

    # --- Tier 2 + Tier 3 (optionnels, runtime DevTools) ---
    if run_devtools:
        from .chrome_devtools_tool import chrome_devtools_tools
        try:
            with chrome_devtools_tools() as cdt:
                if cdt:  # Chrome dispo
                    url = devtools_url or ("file:///" + os.path.abspath(path).replace("\\", "/"))
                    selectors = _discover_visibility_targets(html, js)
                    # Étape 7 : déclenche l'action primaire (start/generate) pour
                    # créer les éléments dynamiques avant de vérifier leur visibilité.
                    primary_id = _find_primary_action_id(html)
                    tier2_errors = _evaluate_visibility(cdt, url, selectors, primary_id)
                    errors.extend(tier2_errors)
                    tier = "tier2"

                    # --- Tier 3 (animation temporelle) ---
                    # Détecte les animations instantanées (performStep qui contient tout
                    # l'algorithme). On le lance uniquement si le Tier 2 n'a pas trouvé de
                    # barre invisible (sinon l'animation ne serait de toute façon pas
                    # visible — le bug Tier 2 est plus prioritaire). On partage la même
                    # session DevTools (un seul spawn Chrome).
                    if run_temporal:
                        tier3_errors = _evaluate_temporal(cdt, url, primary_id)
                        errors.extend(tier3_errors)
                        tier = "tier3"

                    # --- Tier 4 : console runtime (post-mortem run #5, F-109) ---
                    # Le crash « Cannot read properties of null (reading
                    # 'textContent') » était invisible des Tiers 1-3 (syntaxe OK,
                    # wiring OK, animation non mesurable car page morte). La
                    # CONSOLE est la preuve déterministe : rechargement frais +
                    # clic action primaire + lecture console — toute exception JS
                    # non interceptée = échec court-circuité (réfutation
                    # static_tester, le Coder corrige avant le Tester LLM).
                    console_errors = _check_console_errors(cdt, url, primary_id)
                    errors.extend(console_errors)
                    if console_errors:
                        tier = "tier4"
                else:
                    tier = "tier1"  # Chrome absent → on reste au Tier 1
        except Exception as e:
            logger.debug("Static Tester Tier 2/3 indisponible (%s).", e)
            tier = "tier1"

    return StaticCheckResult(
        path=path,
        is_valid=(len(errors) == 0),
        errors=errors,
        tier_reached=tier,
    )


def _find_free_port() -> Optional[int]:
    """Port TCP libre sur 127.0.0.1 (bind 0 puis relâche) — anti-collision."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
        except OSError:
            return None


def _run_http_readiness_tier(html_targets: List[str]) -> Tuple[List[str], List[str]]:
    """Tier HTTP du Static Tester (F-100) : preuve exécutable de service.

    Port hermes-agent verify/ : détection d'une recette au niveau du DOSSIER
    du livrable (manifeste ``.verify/environment.json`` ou détection statique),
    start sur un port libre, sonde readiness HTTP, teardown de l'arbre.
    « La page est servie et répond » au lieu de ``file://`` seul (les scripts
    ES-module et fetch sont bloqués par CORS en file://).

    Retourne ``(errors, notes)`` :
      - recette **static-web** (notre propre ``http.server``) : readiness KO =
        problème d'infrastructure locale, PAS un bug du code généré → note.
      - autre recette (commande start du PROJET GÉNÉRÉ, ex. ``npm run dev``) :
        readiness KO = bug réel → error (réfutation, le Coder corrige).
    """
    from graph_orchestrator.verify.environment import load_or_detect
    from graph_orchestrator.verify.runner import run_verify

    root = Path(os.path.dirname(os.path.abspath(html_targets[0]))) or Path.cwd()
    recipe, source = load_or_detect(root)
    if recipe is None or not recipe.start:
        return [], []

    port = _find_free_port()
    ready_timeout = float(os.getenv("STATIC_TESTER_HTTP_TIMEOUT", "10"))
    result = run_verify(root, recipe, phases=(), ready_timeout=ready_timeout, port_override=port)

    readiness = result.readiness
    if readiness is None:
        return [], []
    if readiness.ready:
        note = (f"[http] Page servie : {readiness.url} → HTTP {readiness.status_code} "
                f"(recette {recipe.kind}/{source}, {readiness.duration:.1f}s).")
        return [], [note]
    if recipe.kind == "static-web":
        return [], [f"[http] Readiness KO ignorée (infrastructure locale) : "
                    f"{readiness.error or 'inconnue'}."]
    detail = (f"[http] Le serveur de l'application (recette {recipe.kind}, commande "
              f"« {recipe.start} ») n'a jamais répondu sur {readiness.url} en "
              f"{ready_timeout:.0f}s (erreur : {readiness.error or 'inconnue'} ; "
              f"sortie serveur : {readiness.output_tail[-300:]})")
    return [detail], []


def execute_static_tester_node(
    subtask: dict, settings
) -> Tuple[Optional[CoderOutput], Optional[NodeMetrics]]:
    """Nœud Static Tester : gatekeeper déterministe web AVANT le Tester LLM.

    Ne s'active QUE sur les fichiers HTML (web-only). Pour les autres technos
    (Python, etc.), retourne success immédiat (pass-through).

    Déterministe, 0 LLM. Retourne un CoderOutput dont le status est 'failure'
    si un bug web évident est détecté (court-circuit du Tester LLM, économie
    d'un cycle complet), avec les erreurs dans details (feedback actionnable
    pour le Coder à l'itération suivante).

    Pattern identique au Linter (F-30) : inséré dans process_subtask_loop
    (workflows.py) entre le Linter et le Tester. Si failure → réfutation en
    DuckDB + continue (skip Tester LLM).
    """
    import time

    start = time.time()
    task_id = subtask.get("id", "unknown")
    targets = subtask.get("target_files", []) or []

    # Opt-out global : STATIC_TESTER_ENABLED=0 désactive le nœud entièrement.
    if os.getenv("STATIC_TESTER_ENABLED", "1").strip().lower() in {"0", "false", "no", "off"}:
        return (
            CoderOutput(task_id=task_id, status="success", details="Static Tester désactivé."),
            NodeMetrics(node="static_tester", model="static-tester", duration_s=0.0,
                        input_tokens=0, output_tokens=0),
        )

    # Web-only : si aucun target HTML, pass-through (pas un échec).
    html_targets = [t for t in targets if _detect_html(t)]
    if not html_targets:
        return (
            CoderOutput(task_id=task_id, status="success",
                        details="Static Tester : pas de fichier HTML (web-only)."),
            NodeMetrics(node="static_tester", model="static-tester",
                        duration_s=time.time() - start, input_tokens=0, output_tokens=0),
        )

    # Tier 2 activé sauf si STATIC_TESTER_DEVTOOLS=0.
    run_devtools = os.getenv("STATIC_TESTER_DEVTOOLS", "1").strip().lower() not in {"0", "false", "no", "off"}
    # Tier 3 (animation temporelle) activé sauf si STATIC_TESTER_TEMPORAL=0.
    run_temporal = os.getenv("STATIC_TESTER_TEMPORAL", "1").strip().lower() not in {"0", "false", "no", "off"}

    all_errors: List[str] = []
    tiers_reached: List[str] = []
    for html_path in html_targets:
        res = static_check_html(html_path, run_devtools=run_devtools, run_temporal=run_temporal)
        if not res.is_valid and res.errors:
            all_errors.append(f"\nFichier {html_path} :")
            all_errors.extend(f"  - {e}" for e in res.errors)
        tiers_reached.append(res.tier_reached)

    # --- Tier HTTP (F-100) : « la page est servie et répond » ---------------
    # Ne tourne QUE si les tiers 1-4 sont propres (un bug détecté avant = le
    # Coder doit corriger d'abord, la preuve HTTP attendra). Opt-out
    # STATIC_TESTER_HTTP=0 ; dégradation gracieuse totale (cf. ADR-0002).
    http_notes: List[str] = []
    run_http = os.getenv("STATIC_TESTER_HTTP", "1").strip().lower() not in {"0", "false", "no", "off"}
    if run_http and not all_errors:
        try:
            http_errors, http_notes = _run_http_readiness_tier(html_targets)
            all_errors.extend(http_errors)
        except Exception as e:
            logger.debug("Static Tester Tier HTTP indisponible (%s).", e)
            http_notes = []

    if not all_errors:
        tier_summary = max(tiers_reached) if tiers_reached else "skipped"  # tier3 > tier2 > tier1
        details = f"OK — checks statiques web valides ({tier_summary})."
        if http_notes:
            details += " " + " ".join(http_notes)
        return (
            CoderOutput(task_id=task_id, status="success", details=details),
            NodeMetrics(node="static_tester", model="static-tester",
                        duration_s=time.time() - start, input_tokens=0, output_tokens=0),
        )

    details = ("BUGS WEB DÉTECTÉS (Static Tester déterministe, 0 LLM) :\n"
               + "\n".join(all_errors))
    return (
        CoderOutput(task_id=task_id, status="failure", details=details),
        NodeMetrics(node="static_tester", model="static-tester",
                    duration_s=time.time() - start, input_tokens=0, output_tokens=0),
    )
