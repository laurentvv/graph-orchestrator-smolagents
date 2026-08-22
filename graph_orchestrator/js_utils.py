"""Utilitaires partagés de validation JavaScript (DRY Coder / Static Tester).

Centralise le lancement de ``node --check`` pour la validation syntaxique du JS.
Extrait de ``static_tester.py`` dans le cadre de F-72 (Prompt Offloading) afin
d'être réutilisé par l'outil ``check_js_syntax`` exposé au Coder pour son
auto-validation verify-after, sans dupliquer la logique subprocess.

Fidèle au comportement historique (Static Tester Tier 1a) : tolérant par défaut
(jamais d'exception), dégradation gracieuse si ``node`` est absent du PATH.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from typing import Tuple

logger = logging.getLogger(__name__)

# Limite de JS soumis à node --check (un HTML monstrueux pourrait dépasser la
# ligne de commande OS ; l'appelant tronque par sécurité avant l'appel).
MAX_JS_CHARS = 200_000


def run_node_check(js_source: str) -> Tuple[int, str]:
    """Lance ``node --check`` sur le JS, retourne ``(exit_code, stderr)``.

    Tolérant : jamais d'exception (subprocess peut échouer si node absent).
    Copie carbone de ``git_snapshot._run_git`` : arg-list, capture_output,
    timeout, encoding utf-8, errors replace, catch FileNotFoundError.

    Consommé par :
      - le Static Tester (validation Tier 1a du JS inline du HTML généré),
      - l'outil ``check_js_syntax`` exposé au Coder (auto-validation verify-after).
    """
    # node --check lit le fichier (pas stdin) — on écrit en tmp.
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False, encoding="utf-8"
        ) as f:
            f.write(js_source)
            tmp_path = f.name
    except OSError as e:
        logger.debug("js_utils : écriture tmp JS échouée (%s).", e)
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
        logger.debug("js_utils : `node` absent du PATH — skip node --check.")
        return 0, ""
    except subprocess.SubprocessError as e:
        logger.debug("js_utils : node --check échoue (%s).", e)
        return 1, ""
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# =============================================================================
# Extraction de blocs inline HTML (<script> et <style>)
# =============================================================================
_SCRIPT_BLOCK_RE = re.compile(
    r"<script(?:\s+[^>]*)?>(.*?)</script>", re.IGNORECASE | re.DOTALL
)
_STYLE_BLOCK_RE = re.compile(
    r"<style(?:\s+[^>]*)?>(.*?)</style>", re.IGNORECASE | re.DOTALL
)
_SCRIPT_TYPE_IGNORE_RE = re.compile(
    r"""type\s*=\s*['"](?:application/json|text/template|text/plain|text/html|importmap)['"]""",
    re.IGNORECASE,
)


def extract_script_blocks(html_source: str) -> list[dict]:
    """Extrait le contenu et la position de chaque balise <script> dans du HTML.

    Ignore les scripts de données (type='application/json', importmap, etc.).
    Retourne une liste de dicts : [{'code': str, 'start_line': int, 'tag': str}].
    """
    blocks: list[dict] = []
    if not html_source:
        return blocks

    for match in _SCRIPT_BLOCK_RE.finditer(html_source):
        full_match = match.group(0)
        tag_header = full_match[: full_match.find(">") + 1]
        # Ignore les scripts JSON / templates
        if _SCRIPT_TYPE_IGNORE_RE.search(tag_header):
            continue
        code = match.group(1)
        if not code.strip():
            continue
        start_line = html_source[: match.start(1)].count("\n") + 1
        blocks.append(
            {
                "code": code,
                "start_line": start_line,
                "tag": tag_header,
            }
        )
    return blocks


def extract_style_blocks(html_source: str) -> list[dict]:
    """Extrait le contenu et la position de chaque balise <style> dans du HTML.

    Retourne une liste de dicts : [{'code': str, 'start_line': int}].
    """
    blocks: list[dict] = []
    if not html_source:
        return blocks

    for match in _STYLE_BLOCK_RE.finditer(html_source):
        code = match.group(1)
        if not code.strip():
            continue
        start_line = html_source[: match.start(1)].count("\n") + 1
        blocks.append(
            {
                "code": code,
                "start_line": start_line,
            }
        )
    return blocks


# =============================================================================
# Détection de fuites de syntaxe Python dans le JS (Nanocode / DeepSeek Harness)
# =============================================================================
_JS_STRING_OR_COMMENT_RE = re.compile(
    r"""/\*[\s\S]*?\*/|//[^\r\n]*|`(?:\\.|[^`\\])*`|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'"""
)


def strip_js_comments_and_strings(js_source: str) -> str:
    """Remplace les chaînes et commentaires JS par des espaces pour analyse statique.

    Conserve les sauts de ligne pour préserver la correspondance des numéros de ligne.
    """
    def _replacer(match):
        text = match.group(0)
        newlines = text.count("\n")
        return "\n" * newlines if newlines else " "

    return _JS_STRING_OR_COMMENT_RE.sub(_replacer, js_source)


_JS_COMMENT_ONLY_RE = re.compile(r"""/\*[\s\S]*?\*/|//[^\r\n]*""")


def has_use_strict(js_source: str) -> bool:
    """Vérifie si 'use strict' est présent dans le code JS (Nanocode invariant)."""
    if not js_source:
        return False
    # Supprime uniquement les commentaires pour chercher la directive au début
    without_comments = _JS_COMMENT_ONLY_RE.sub("", js_source).strip()
    return bool(re.search(r"""^\s*['"]use strict['"]\s*;?""", without_comments, re.MULTILINE))


def detect_python_syntax_in_js(js_source: str, start_line: int = 1) -> list[str]:
    """Détecte les fuites de syntaxe Python dans du code JavaScript.

    Cas récurrents chez les modèles 4B/9B :
    1. Tuples Python dans les arrays : [(0,0), (1,0)] au lieu de [[0,0], [1,0]].
       (En JS, `(0,0)` est l'opérateur virgule qui évalue à 0, produisant [0, 0] et
       cassant silencieusement l'indexation kick[0] -> undefined à l'exécution).
    2. Booléens / valeurs Python : None, True, False (hors chaînes de caractères).
    3. Mots-clés Python : def, elif, print(, not in.

    Retourne une liste de messages d'erreur explicites (vide si OK).
    """
    errors: list[str] = []
    if not js_source:
        return errors

    # 1. Détection des tuples dans les tableaux : [(x, y), ...]
    tuple_in_array_matches = list(
        re.finditer(
            r"""\[\s*\(\s*(-?\d+|[a-zA-Z_$][\w$]*)\s*,\s*(-?\d+|[a-zA-Z_$][\w$]*)\s*\)""",
            js_source,
        )
    )
    for m in tuple_in_array_matches:
        line_no = start_line + js_source[: m.start()].count("\n")
        snippet = m.group(0)
        errors.append(
            f"[Syntaxe JS - Ligne {line_no}] Tuples Python détectés dans un tableau : `{snippet}...`. "
            f"En JavaScript, utilise des tableaux imbriqués `[[x, y], ...]` et non `[(x, y), ...]`."
        )

    # 2. Nettoyage des commentaires et chaînes pour analyse des mots-clés
    cleaned = strip_js_comments_and_strings(js_source)

    # 3. Mots-clés Python interdits en JS
    py_keywords = [
        ("None", "null"),
        ("True", "true"),
        ("False", "false"),
        ("elif", "else if"),
        ("def ", "function "),
        ("print(", "console.log("),
    ]

    for py_kw, js_equiv in py_keywords:
        pattern = rf"\b{re.escape(py_kw.strip())}\b" if not py_kw.endswith((" ", "(")) else rf"\b{re.escape(py_kw)}"
        for m in re.finditer(pattern, cleaned):
            line_no = start_line + cleaned[: m.start()].count("\n")
            errors.append(
                f"[Syntaxe JS - Ligne {line_no}] Mot-clé Python `{py_kw.strip()}` détecté en JavaScript. "
                f"Remplace par `{js_equiv.strip()}`."
            )

    return errors


def detect_const_mutation_in_js(js_source: str, start_line: int = 1) -> list[str]:
    """Détecte les variables déclarées avec `const` puis mutées (++, --, +=, -=, =).

    Empêche les erreurs bloquantes `TypeError: Assignment to constant variable` à l'exécution.
    """
    errors: list[str] = []
    if not js_source:
        return errors

    cleaned = strip_js_comments_and_strings(js_source)

    # Déclarations const : `const varName = ...`
    const_matches = list(re.finditer(r"\bconst\s+([a-zA-Z_$][\w$]*)\s*=", cleaned))

    for m in const_matches:
        var_name = m.group(1)
        decl_pos = m.end()
        decl_line = start_line + cleaned[: m.start()].count("\n")

        # Scope d'analyse : ~80 lignes suivantes
        scope_text = cleaned[decl_pos : decl_pos + 4000]

        # 1. Incrément / Décrément : var++, ++var, var--, --var
        inc_match = re.search(
            rf"(?:\+\+\s*{re.escape(var_name)}|--\s*{re.escape(var_name)}|\b{re.escape(var_name)}\s*\+\+|\b{re.escape(var_name)}\s*--)",
            scope_text,
        )
        if inc_match:
            mutation_line = decl_line + scope_text[: inc_match.start()].count("\n")
            errors.append(
                f"[Crash JS - Ligne {mutation_line}] Variable `{var_name}` déclarée avec `const` ligne {decl_line} "
                f"mais modifiée par `{inc_match.group(0).strip()}`. "
                f"Utilise `let` au lieu de `const` pour toute variable réassignée ou incrémentée "
                f"(évite `TypeError: Assignment to constant variable`)."
            )
            continue

        # 2. Assignation composée : var +=, var -=, var *=, var /=
        assign_match = re.search(
            rf"\b{re.escape(var_name)}\s*(?:\+=|-=|\*=|/=|%=)",
            scope_text,
        )
        if assign_match:
            mutation_line = decl_line + scope_text[: assign_match.start()].count("\n")
            errors.append(
                f"[Crash JS - Ligne {mutation_line}] Variable `{var_name}` déclarée avec `const` ligne {decl_line} "
                f"mais réassignée par `{assign_match.group(0).strip()}`. "
                f"Utilise `let` au lieu de `const` pour toute variable réassignée."
            )

    return errors


def detect_unbounded_while_in_js(js_source: str, start_line: int = 1) -> list[str]:
    """Détecte les boucles while potentiellement infinies en JS.

    Cas classique en jeu Canvas / Tetris :
    `while (!collide({ x: 0, y: 1 })) { ghostY++; }`
    où `ghostY` est incrémenté dans le corps de la boucle mais n'apparaît PAS dans la condition du while,
    et la fonction appelée ignore son argument ou ne dépend pas de l'incrément -> boucle infinie bloquante.

    Goulot run 2026-08-21_1531 (review post-mortem) : l'ancienne logique flaggait
    TOUTE variable incrémentée dans le corps absente de la condition — faux
    positif sur le bubble sort canonique (`while (swapped && …)` avec `i++` de
    passe externe) que le Coder a réécrit 6+ fois sans jamais satisfaire le
    checker (boucle de fix invincible). Logique INVERSÉE, conservative : on
    flaggue uniquement si AUCUNE variable de la condition n'est mutée dans le
    corps (assignation `=` OU incrément) — la condition ne peut alors jamais
    changer ; ou si la condition est constante vraie (`while (true)`, `while (1)`).
    """
    errors: list[str] = []
    if not js_source:
        return errors

    cleaned = strip_js_comments_and_strings(js_source)

    for m in re.finditer(r"\bwhile\s*\(", cleaned):
        pos = m.end()
        # Parse parenthèses équilibrées pour la condition
        paren_depth = 1
        cond_start = pos
        while pos < len(cleaned) and paren_depth > 0:
            if cleaned[pos] == "(":
                paren_depth += 1
            elif cleaned[pos] == ")":
                paren_depth -= 1
            pos += 1
        if paren_depth != 0:
            continue
        cond = cleaned[cond_start : pos - 1].strip()

        # Parse accolades équilibrées pour le corps de boucle
        brace_m = re.search(r"^\s*\{", cleaned[pos:])
        if not brace_m:
            continue
        body_start = pos + brace_m.end()
        brace_depth = 1
        bpos = body_start
        while bpos < len(cleaned) and brace_depth > 0 and (bpos - body_start) < 2000:
            if cleaned[bpos] == "{":
                brace_depth += 1
            elif cleaned[bpos] == "}":
                brace_depth -= 1
            bpos += 1
        if brace_depth != 0:
            continue
        body = cleaned[body_start : bpos - 1].strip()

        while_line = start_line + cleaned[: m.start()].count("\n")

        # Variables LUES dans la condition (identifiants nus, hors littéraux).
        cond_vars = set(re.findall(r"\b([a-zA-Z_$][\w$]*)\b", cond)) - {
            "true", "false", "null", "undefined", "length", "not", "&&", "||", "!"
        }
        # Constante vraie : aucune variable lue → while(true) & co.
        if not cond_vars:
            mutated_in_body = re.findall(
                r"\b([a-zA-Z_$][\w$]*)\s*(?:\+\+|--|\+=|-=|\*=|/=|=(?!=))", body
            )
            if mutated_in_body or cond in ("true", "1"):
                errors.append(
                    f"[Boucle infinie JS - Ligne {while_line}] La boucle `while ({cond})` "
                    f"ne teste AUCUNE variable mutée dans son corps (`while (true)` ou "
                    f"condition constante) — elle ne peut jamais devenir fausse. "
                    f"Risque critique de blocage du navigateur. Fais tester une variable "
                    f"réellement mutée dans le corps (ex: `while (i < ROWS && !done)`)."
                )
            continue

        # Variables MUTÉES dans le corps : incrément OU assignation simple
        # (`swapped = false` fait bien sortir un bubble sort — l'ancienne version
        # ne comptait que ++/-- et flaggait à tort, run 2026-08-21_1531).
        mutated = set(
            re.findall(r"\b([a-zA-Z_$][\w$]*)\s*(?:\+\+|--|\+=|-=|\*=|/=|=(?!=))", body)
        )
        # Conservative : au moins UNE variable de condition mutée → pas de flag
        # (les sorties via fonctions/break restent invisibles, on ne devine pas).
        if cond_vars & mutated:
            continue
        errors.append(
            f"[Boucle infinie JS - Ligne {while_line}] La condition `while ({cond})` "
            f"teste {sorted(cond_vars)} mais AUCUNE de ces variables n'est modifiée "
            f"dans le corps de la boucle — la condition ne peut jamais changer. "
            f"Risque critique de blocage du navigateur. Assure-toi qu'au moins une "
            f"variable testée est mutée dans le corps (assignation ou incrément)."
        )
    return errors

