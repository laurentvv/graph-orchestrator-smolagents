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
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .logging_utils import NodeMetrics
from .models import CoderOutput

logger = logging.getLogger(__name__)

# Limite de JS extrait soumis à node --check (un HTML monstrueux pourrait
# dépasser la ligne de commande OS ; on tronque par sécurité).
_MAX_JS_CHARS = 200_000


# ==========================================
# Utilitaire subprocess Node — miroir de git_snapshot._run_git
# ==========================================
def _run_node_check(js_source: str) -> Tuple[int, str]:
    """Lance `node --check` sur le JS, retourne (exit_code, stderr).

    Tolérant : jamais d'exception (subprocess peut échouer si node absent).
    Copie carbone de git_snapshot._run_git : arg-list, capture_output,
    timeout, encoding utf-8, errors replace, catch FileNotFoundError.
    """
    # node --check lit le fichier (pas stdin) — on écrit en tmp.
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False, encoding="utf-8"
        ) as f:
            f.write(js_source)
            tmp_path = f.name
    except OSError as e:
        logger.debug("Static Tester : écriture tmp JS échouée (%s).", e)
        return 1, ""

    try:
        result = subprocess.run(
            ["node", "--check", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode, result.stderr
    except FileNotFoundError:
        # node absent du PATH — dégradation gracieuse (le LLM Tester prend le relais).
        logger.debug("Static Tester : `node` absent du PATH — skip node --check.")
        return 0, ""
    except subprocess.SubprocessError as e:
        logger.debug("Static Tester : node --check échoué (%s).", e)
        return 1, ""
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


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


def extract_inline_js(html: str) -> str:
    """Extrait et concatène le JS des balises <script> inline (sans src).

    Exclut explicitement les scripts externes (<script src="...">) car on ne
    dispose pas de leur code ici. Retourne le JS concaténé (séparé par \\n\\n
    pour que les erreurs de l'un ne cascade pas sur l'autre).

    Exemples:
        >>> extract_inline_js('<script>let x = 1;</script>')
        'let x = 1;'
        >>> extract_inline_js('<script src="app.js"></script>')
        ''
        >>> extract_inline_js('<script type="module">const y: number = 2;</script>')
        'const y: number = 2;'
    """
    if not html:
        return ""
    blocks = _SCRIPT_INLINE_RE.findall(html)
    return "\n\n".join(b.strip() for b in blocks if b.strip())


def _check_js_syntax(html: str) -> List[str]:
    """Tier 1a : valide la syntaxe du JS inline via `node --check`.

    Déterministe, 0 LLM, <1s. Attrape le bug n°1 du Coder : TypeScript dans
    du vanilla JS (`: type`, `as Cast`) → SyntaxError → page blanche. Un
    screenshot ne le détecte PAS (la page est juste vide).

    Returns:
        Liste de messages d'erreur (vide si OK ou node absent). On garde le
        premier message de stderr de node (le plus pertinent = la cause).
    """
    js = extract_inline_js(html)
    if not js.strip():
        return []  # rien à valider (HTML statique sans JS, ou JS externe uniquement)

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


def _check_event_wiring(html: str) -> List[str]:
    """Tier 1b : vérifie que chaque contrôle interactif est branché au JS.

    Déterministe, 0 LLM, <1s. Attrape le piège n°1 du Coder : un élément HTML
    présent visuellement mais INACTIF car non connecté au JS. Bug concret :
    `<input id="speedSlider" type="range">` sans `speedSlider.addEventListener(...)`
    → slider visible mais qui ne fait rien.

    GÉNÉRIQUE : scanne TOUS les contrôles du HTML. Ne connaît pas « speedSlider ».

    Tolère les patterns légitimes :
      - onclick/onchange/... inline (attributs on*)
      - <button type="submit"> dans un <form> (submit natif)
      - <a href> (navigation native, pas besoin de JS)
      - <input type="hidden"> (pas interactif)

    Returns:
        Liste de messages (vide si OK). Un message par contrôle non-wiré.
    """
    errors: List[str] = []

    # Rassemble tous les ids référencés en JS (via getElementById/querySelector)
    # pour tolérer le pattern `document.getElementById('x').addEventListener(...)`.
    referenced_ids: set = set()
    for m in _GETBY_RE.finditer(html):
        referenced_ids.add(m.group(1) or m.group(2))
    # De même : si au moins un addEventListener existe globalement, on est
    # indulgent (le Coder peut brancher via querySelectorAll('.class') — on ne
    # peut pas tout matcher). On ne flag QUE s'il n'y a AUCUN handler OU
    # l'id n'est référencé nulle part.
    has_any_handler = bool(_ADD_EVENT_RE.search(html)) or bool(_ONCLICK_RE.search(html))

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
    r'id\s*=\s*["\']?(start|go|run|play|generate|init|launch|submit)\w*',
    re.IGNORECASE,
)


def _discover_visibility_targets(html: str) -> List[str]:
    """Découvre les sélecteurs CSS candidats à vérifier pour la visibilité.

    GÉNÉRIQUE : on ne hardcode pas `.bar`. Deux sources de candidats :
      1. Classes assignées en JS (b.className = "bar", classList.add("bar")) —
         ces éléments sont CRÉÉS dynamiquement (ils n'existent pas au load,
         donc on ne peut pas les voir dans le HTML statique).
      2. Classes présentes dans le HTML + citées dans un appendChild/innerHTML.

    La source 1 est cruciale : c'est elle qui détecte les éléments créés au clic
    (le bug des barres invisibles : .bar est créé via createElement + className,
    jamais présent dans le HTML au load).
    """
    targets: List[str] = []
    seen = set()
    js = extract_inline_js(html)

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
        if isinstance(parsed, str):
            # parsed est encore une string (contenu doublement stringifié) → reloop.
            text = parsed
            continue
        return []  # dict ou scalar → pas ce qu'on cherche
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
            )
        js_probe = (
            "() => {" + click_clause +
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
            "    const hidden = (r.height === 0 "
            "                     || cs.display === 'none' || cs.visibility === 'hidden');"
            "    out.push({sel, count: els.length, h: r.height, hidden});"
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
                    f"INVISIBLE(s) (height={h}, display:none ou visibility:hidden). "
                    f"Bug CSS probable : `height` en pourcentage sur un conteneur "
                    f"parent sans `height` explicite (le % se résout à 0), ou "
                    f"élément en `position:absolute` hors écran. Vérifie le CSS."
                )
        return errors
    except Exception as e:
        # Tier 2 est fragile (API DevTools, Chrome qui ne lance pas, etc.).
        # On ne fait JAMAIS échouer le nœud sur une erreur Tier 2 — on skip.
        logger.debug("Static Tester Tier 2 skip (%s).", e)
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
    tier_reached: str = "skipped"  # "tier1" | "tier2" | "skipped"


def _detect_html(path: str) -> bool:
    """True si le fichier est du HTML (extension). Déterministe, fiable."""
    ext = os.path.splitext(path)[1].lower()
    return ext in (".html", ".htm")


def static_check_html(path: str, run_devtools: bool = True, devtools_url: Optional[str] = None) -> StaticCheckResult:
    """Check statique complet d'un fichier HTML : Tier 1 (+ Tier 2 si activé).

    Args:
        path: Chemin du fichier HTML à valider.
        run_devtools: True pour lancer le Tier 2 (visibilité DOM via Chrome).
            False = Tier 1 seul (plus rapide, 0 dépendance Chrome).
        devtools_url: URL file:/// à passer à navigate_page pour le Tier 2.
            Si None, déduite du path.

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

    # --- Tier 1 (toujours, statique pur) ---
    errors.extend(_check_js_syntax(html))
    errors.extend(_check_event_wiring(html))
    tier = "tier1" if not errors else "tier1"  # on continue vers Tier 2 même si Tier 1 FAIL ?

    # Décision : si Tier 1 a déjà trouvé un bug SYNTAXE (page blanche garantie),
    # on NE lance pas le Tier 2 (Chrome afficherait juste une page blanche —
    # gaspillage de ~5s). On ne court-circuite que sur node --check FAIL.
    syntax_failed = any(e.startswith("[node --check]") for e in errors)
    if syntax_failed:
        # Page blanche garantie → Tier 2 inutile.
        return StaticCheckResult(path=path, is_valid=False, errors=errors, tier_reached="tier1")

    # --- Tier 2 (optionnel, runtime DevTools) ---
    if run_devtools:
        from .chrome_devtools_tool import chrome_devtools_tools
        try:
            with chrome_devtools_tools() as cdt:
                if cdt:  # Chrome dispo
                    url = devtools_url or ("file:///" + os.path.abspath(path).replace("\\", "/"))
                    selectors = _discover_visibility_targets(html)
                    # Étape 7 : déclenche l'action primaire (start/generate) pour
                    # créer les éléments dynamiques avant de vérifier leur visibilité.
                    primary_id = _find_primary_action_id(html)
                    tier2_errors = _evaluate_visibility(cdt, url, selectors, primary_id)
                    errors.extend(tier2_errors)
                    tier = "tier2"
                else:
                    tier = "tier1"  # Chrome absent → on reste au Tier 1
        except Exception as e:
            logger.debug("Static Tester Tier 2 indisponible (%s).", e)
            tier = "tier1"

    return StaticCheckResult(
        path=path,
        is_valid=(len(errors) == 0),
        errors=errors,
        tier_reached=tier,
    )


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

    all_errors: List[str] = []
    tiers_reached: List[str] = []
    for html_path in html_targets:
        res = static_check_html(html_path, run_devtools=run_devtools)
        if not res.is_valid and res.errors:
            all_errors.append(f"\nFichier {html_path} :")
            all_errors.extend(f"  - {e}" for e in res.errors)
        tiers_reached.append(res.tier_reached)

    if not all_errors:
        tier_summary = max(tiers_reached) if tiers_reached else "skipped"  # tier2 > tier1
        return (
            CoderOutput(task_id=task_id, status="success",
                        details=f"OK — checks statiques web valides ({tier_summary})."),
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
