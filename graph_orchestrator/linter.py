"""Nœud Linter (F-30, Priorité 3 — Shift Left).

Intercepte les erreurs de syntaxe triviales JUSTE APRÈS le Coder, AVANT le Tester
coûteux (LLM). C'est l'économie massive visée par P3/P7 du plan usine logicielle :
un bug de syntaxe (IndentationError Python, contenu après </html>, string non fermée)
ne doit pas gaspiller un cycle LLM complet (Tester + Judge) pour être détecté.

Couverture linguistique : Python, HTML, CSS, JavaScript, TypeScript, TSX.

Back-end double (complémentaire, pas redondant) :
- **tree-sitter** (universel, tolérant) : détecte SyntaxError (parenthèse non fermée),
  strings non fermées (le bug "triple-quote" observé au step 6 du run CodeAgent),
  structures cassées en Python/HTML/CSS/JS/TS/TSX. Voir references_audit.md (pattern n°2).
- **py_compile** (Python seulement) : détecte IndentationError — le POINT NOIR reconnu
  par tous les audits (Copilot, Cursor, aider le documentent). tree-sitter NE le détecte
  PAS (c'est un parser grammatical tolérant, pas un vérificateur sémantique Python).
  py_compile est la contre-mesure canonique (SWE-agent ACI).
- **Vérifs structurelles HTML** : tree-sitter-html est TOLÉRANT (parse du contenu orphelin
  après </html> sans flagger). On ajoute donc des checks explicites : équilibrage
  DOCTYPE/html/head/body, pas de contenu significatif après </html> (le bug EXACT du
  dashboard cassé observé au run CodeAgent incrémental).

Déterministe, 0 LLM, 0 réseau : millisecondes. Inspiré du pattern PythonTestRunner
(subprocess déterministe + verdict binaire + détails exploitables par le Coder).
"""
from __future__ import annotations

import os
import py_compile
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .logging_utils import NodeMetrics
from .models import CoderOutput


# ==========================================
# Détection tree-sitter (lazy import — heavy)
# ==========================================
# Les grammars tree-sitter sont importés paresseusement (et une seule fois) car
# l'import initial est coûteux (~100ms). On cache les parsers par language key.
_PARSERS: dict = {}
_LANGUAGE_MODULES: dict = {}


def _get_parser(lang_key: str):
    """Retourne un Parser tree-sitter pour la langue, avec cache. None si non dispo."""
    if lang_key in _PARSERS:
        return _PARSERS[lang_key]
    try:
        if lang_key == "python":
            import tree_sitter_python as tsmodule
            language_factory = tsmodule.language
        elif lang_key == "javascript":
            import tree_sitter_javascript as tsmodule
            language_factory = tsmodule.language
        elif lang_key == "html":
            import tree_sitter_html as tsmodule
            language_factory = tsmodule.language
        elif lang_key == "css":
            import tree_sitter_css as tsmodule
            language_factory = tsmodule.language
        elif lang_key in ("typescript", "tsx"):
            # Particularité : tree-sitter-typescript expose 2 langues (typescript + tsx)
            # via language_typescript() / language_tsx(), PAS une fonction language() unique.
            import tree_sitter_typescript as tsmodule
            language_factory = tsmodule.language_tsx if lang_key == "tsx" else tsmodule.language_typescript
        else:
            return None
        from tree_sitter import Language, Parser
        lang = Language(language_factory())
        parser = Parser(lang)
        _PARSERS[lang_key] = parser
        return parser
    except Exception:
        # tree-sitter ou le grammar absent (dépendance non installée) → dégradation gracieuse
        return None


def _count_tree_sitter_errors(parser, source_bytes: bytes) -> Tuple[int, int]:
    """Compte les nœuds ERROR et MISSING dans l'arbre de parsing tree-sitter.

    tree-sitter est tolérant : il ne lève jamais d'exception sur du code invalide,
    il insère des nœuds ERROR (texte non reconnu) ou MISSING (token attendu absent).
    On traverse tout l'arbre (DFS) pour les compter.
    """
    tree = parser.parse(source_bytes)
    root = tree.root_node
    errors = 0
    missing = 0
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "ERROR":
            errors += 1
        if node.is_missing:
            missing += 1
        for child in node.children:
            stack.append(child)
    return errors, missing


# ==========================================
# Détection py_compile (IndentationError Python — le point noir)
# ==========================================
def _lint_python_py_compile(path: str) -> List[str]:
    """Détecte IndentationError + SyntaxError Python via py_compile.

    py_compile est LE contre-mesure canonique de l'IndentationError (point noir
    reconnu). tree-sitter ne le voit pas (parser grammatical tolérant), py_compile oui.
    Retourne une liste de messages d'erreur (vide si OK).
    """
    errors: List[str] = []
    try:
        # py_compile.compile lève py_compile.PyCompileError (qui wrap SyntaxError /
        # IndentationError / TabError) si le fichier est invalide.
        py_compile.compile(path, doraise=True)
    except py_compile.PyCompileError as e:
        # Le message contient déjà le nom du fichier + ligne + type d'erreur.
        # On nettoie pour garder l'essentiel (sans le traceback interne de py_compile).
        msg = str(e)
        # Extraction de la première ligne significative (file "path", line N)
        first_line = msg.strip().splitlines()[0] if msg.strip() else str(e)
        errors.append(f"[py_compile] {first_line}")
    except Exception:
        # Fichier non lisible, encoding, etc. — pas une erreur de syntaxe, on ignore
        # (le Linter ne doit pas planter sur un fichier qu'il ne sait pas lire).
        pass
    return errors


# ==========================================
# Vérifs structurelles HTML (le bug dashboard)
# ==========================================
# tree-sitter-html est TOLÉRANT : il parse du contenu orphelin après </html> sans
# flagger. On ajoute donc des vérifications structurelles explicites, calées sur les
# bugs réels observés (run CodeAgent incrémental : CSS/JS appendés après </html>).
_DOCTYPE_RE = re.compile(r"<!DOCTYPE\s+html", re.IGNORECASE)
_TAG_RE = re.compile(r"<(/?)(\w+)[^>]*?(/?)>", re.IGNORECASE)
# Balises structurelles qu'on veut voir équilibrées dans un document HTML complet.
_STRUCTURAL_TAGS = {"html", "head", "body"}


def _lint_html_structure(source: str) -> List[str]:
    """Vérifs structurelles HTML que tree-sitter-html tolérant ne voit pas.

    Détecte notamment : contenu significatif après </html> (le bug exact du dashboard
    cassé : CSS/JS appendés après la fermeture du document → rendu texte brut).
    """
    errors: List[str] = []
    if not source.strip():
        return errors

    # 1. Pas de contenu significatif après </html>
    close_html_idx = source.rfind("</html>")
    if close_html_idx != -1:
        trailing = source[close_html_idx + len("</html>"):].strip()
        # On tolère un whitespace pur, mais PAS du contenu (texte, balises, CSS, JS).
        if trailing:
            # Aperçu pour le feedback (très utile pour que le Coder comprenne le bug)
            preview = trailing[:80].replace("\n", " ")
            errors.append(
                f"[structure] Contenu trouvé APRÈS </html> (ligne ~"
                f"{source[:close_html_idx].count(chr(10)) + 1}). Le navigateur "
                f"affichera ce contenu en texte brut. Aperçu : {preview!r}"
            )

    # 2. Équilibrage des balises structurelles (html/head/body)
    open_counts = {t: 0 for t in _STRUCTURAL_TAGS}
    close_counts = {t: 0 for t in _STRUCTURAL_TAGS}
    for slash, name, _selfclose in _TAG_RE.findall(source):
        name_lower = name.lower()
        if name_lower in _STRUCTURAL_TAGS:
            if slash == "/":
                close_counts[name_lower] += 1
            else:
                open_counts[name_lower] += 1
    for tag in _STRUCTURAL_TAGS:
        if open_counts[tag] != close_counts[tag]:
            errors.append(
                f"[structure] Balise <{tag}> déséquilibrée : "
                f"{open_counts[tag]} ouvrante(s) vs {close_counts[tag]} fermante(s)."
            )

    # 3. DOCTYPE présent (recommandé pour un document HTML complet)
    if not _DOCTYPE_RE.search(source):
        errors.append("[structure] Aucun <!DOCTYPE html> trouvé (recommandé).")

    return errors


# ==========================================
# API publique
# ==========================================
@dataclass
class LintResult:
    """Résultat du lint d'un fichier."""
    path: str
    language: str  # 'python', 'html', 'javascript', 'css', 'unknown', 'missing'
    is_valid: bool
    errors: List[str] = field(default_factory=list)


def _detect_language(path: str) -> str:
    """Détection de la langue par extension (déterministe, fiable)."""
    ext = os.path.splitext(path)[1].lower()
    return {
        ".py": "python",
        ".html": "html", ".htm": "html",
        ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".css": "css",
    }.get(ext, "unknown")


def lint_file(path: str) -> LintResult:
    """Lint un fichier : syntaxe (tree-sitter + py_compile) + structure (HTML).

    Déterministe, 0 LLM, 0 réseau. Dégradation gracieuse : si la dépendance
    tree-sitter n'est pas installée, on retombe sur py_compile (Python) et les
    vérifs structurelles (HTML) — le Linter reste utile même partiellement outillé.
    """
    if not os.path.exists(path):
        # F-56/P14-E : fichier absent reste is_valid=True (défense contre échec silencieux
        # du Coder — ne pas court-circuiter, le Tester/Judge détecteront l'absence de façon
        # plus contextuelle ; et en mode correction le Coder est en read_file+search_replace
        # sur un fichier qu'il croit créé, le bloquer ici causerait une boucle). MAIS on
        # remonte un AVERTISSEMENT non bloquant dans errors pour l'observabilité (ex: le Coder
        # a déclaré success sans write_file, ou a écrit dans un autre chemin).
        return LintResult(
            path=path,
            language="missing",
            is_valid=True,
            errors=["[avertissement] Fichier attendu non trouvé — le Coder ne l'a "
                    "peut-être pas créé (ou l'a écrit sous un autre chemin)."],
        )

    lang = _detect_language(path)
    if lang == "unknown":
        # Extension non supportée → on ne valide pas négativement (pas de faux positif),
        # on laisse le Tester/Judge juger. Le Linter ne sait pas tout faire.
        return LintResult(path=path, language="unknown", is_valid=True, errors=[])

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except Exception:
        return LintResult(path=path, language=lang, is_valid=True, errors=[])

    errors: List[str] = []

    # --- tree-sitter (SyntaxError génériques, strings non fermées, structures cassées)
    # EXCEPTION HTML : tree-sitter-html parse le CSS/JS inline comme du texte HTML →
    # des dizaines de nœuds ERROR sur du code parfaitement valide (les #, {}, let, ; du
    # <style>/<script> sont incompréhensibles pour le parser HTML). C'était la cause de
    # la boucle Linter infinie sur Bubble Sort (77 faux positifs sur un HTML correct).
    # Pour le HTML, on se fie UNIQUEMENT aux vérifs structurelles (_lint_html_structure)
    # qui sont précises (équilibrage balises, contenu après </html>, DOCTYPE).
    parser = _get_parser(lang)
    if parser is not None and lang != "html":
        err_count, miss_count = _count_tree_sitter_errors(parser, source.encode("utf-8"))
        if err_count > 0:
            errors.append(f"[tree-sitter] {err_count} erreur(s) de syntaxe détectée(s).")
        if miss_count > 0:
            errors.append(f"[tree-sitter] {miss_count} token(s) manquant(s) (MISSING).")

    # --- py_compile (IndentationError Python — le point noir, tree-sitter l'ignore)
    if lang == "python":
        errors.extend(_lint_python_py_compile(path))

    # --- Vérifs structurelles HTML (tree-sitter-html tolérant ne suffit pas)
    if lang == "html":
        errors.extend(_lint_html_structure(source))

    return LintResult(
        path=path,
        language=lang,
        is_valid=(len(errors) == 0),
        errors=errors,
    )


def lint_subtask(target_files: List[str]) -> List[LintResult]:
    """Lint tous les fichiers cibles d'une sous-tâche. Retourne un résultat par fichier."""
    return [lint_file(f) for f in (target_files or [])]


def execute_linter_node(subtask: dict, settings) -> Tuple[Optional[CoderOutput], Optional[NodeMetrics]]:
    """Nœud Linter : valide la syntaxe des fichiers générés par le Coder.

    Déterministe, 0 LLM (model='tree-sitter-linter'). Retourne un CoderOutput dont le
    status est 'success' si TOUS les fichiers sont valides, 'failure' sinon, avec les
    erreurs dans details (exploitables comme feedback pour une nouvelle itération Coder).

    Conçu pour s'insérer entre le Coder et le Tester dans process_subtask_loop
    (workflows.py) : si invalide, on court-circuite le Tester coûteux et on relance le
    Coder avec le feedback (écrit en DuckDB comme une réfutation, kind='linter_error').
    """
    import time
    start = time.time()
    task_id = subtask.get("id", "unknown")
    targets = subtask.get("target_files", []) or []

    results = lint_subtask(targets)
    all_valid = all(r.is_valid for r in results)
    linted = [r for r in results if r.language not in ("unknown", "missing")]

    if all_valid:
        details = "OK — syntaxe valide"
        if linted:
            details += " (" + ", ".join(f"{r.path}:{r.language}" for r in linted) + ")"
        # F-56/P14-E : avertissements non bloquants (fichiers attendus absents). On les
        # remonte dans details pour l'observabilité SANS changer le statut (la défense
        # is_valid=True sur fichier absent est conservée — cf. lint_file commentaire).
        warnings = [r for r in results if r.is_valid and r.errors and r.language == "missing"]
        if warnings:
            details += "\n\nAVERTISSEMENTS (non bloquants) :"
            for r in warnings:
                for e in r.errors:
                    details += f"\n  - {r.path}: {e}"
        status = "success"
    else:
        # Agrège les erreurs : chaque fichier + ses erreurs, lisible par le Coder.
        lines = ["ERREURS DE SYNTAXE DÉTECTÉES (à corriger avant de continuer) :"]
        for r in results:
            if not r.is_valid and r.errors:
                lines.append(f"\nFichier {r.path} ({r.language}) :")
                for e in r.errors:
                    lines.append(f"  - {e}")
        details = "\n".join(lines)
        status = "failure"

    metrics = NodeMetrics(
        node="linter",
        model="tree-sitter-linter",
        duration_s=time.time() - start,
        input_tokens=0,
        output_tokens=0,
    )
    return CoderOutput(task_id=task_id, status=status, details=details), metrics
