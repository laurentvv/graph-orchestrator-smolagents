"""Auto-fixer déterministe pour erreurs mécaniques connues (F-133).

Post-mortem runs 2026-08-20 (Tetris) : certaines erreurs console ont un fix
MÉCANIQUE prouvé par l'erreur elle-même — p.ex. `Assignment to constant
variable 'X'` prouve que X est réassignée, donc `const X` → `let X` est
sémantiquement garanti. Le Coder 4B a mis plusieurs steps (voire des runs
entiers, cf no-ops F-132) à appliquer ce genre de correctif.

Design (proposition utilisateur, session 2026-08-20) : l'outil est PLUGGÉ AU
TESTER — il trouve l'erreur mécanique pendant son audit, demande à l'outil de
l'appliquer, puis CONTINUE son test (reload + console) au lieu d'échouer
l'itération entière → cycle Coder complet économisé (~30 min GPU).

Périmètre STRICT (fail-closed) : seules les classes de fix dont la sûreté est
DÉMONTRABLE mécaniquement. Tout le reste (X is not defined, propriété d'un
undefined, logique métier) reste au diagnostic LLM — aucun fix ici.

Classes couvertes (v1) :
  1. `Uncaught TypeError: Assignment to constant variable 'X'`
     → convertir toutes les déclarations `const X =` du fichier en `let X =`
       (l'erreur PROUVE la réassignation : let est l'intention d'origine).
  2. `\n` littéral en séparateur de code (mêmes signatures que la garde F-132
     dans tools.py, en mode RÉPARATION cette fois) → remplacer par un vrai
     saut de ligne. C'est le fix que le 4B a échoué à poser 3 fois (no-ops).

Tout est best-effort : jamais d'exception vers l'appelant, journalisation
DuckDB des applications réelles (traçabilité Judge/post-mortem).
"""

from __future__ import annotations

import re
from typing import List, Optional

# ---------------------------------------------------------------------------
# Signatures d'erreurs → fix mécanique. Chaque entrée : regex sur le message
# d'erreur + fonction de patch qui retourne la liste des corrections.
# ---------------------------------------------------------------------------

# « Uncaught TypeError: Assignment to constant variable 'ghostY' » (Chrome/edge)
_CONST_ASSIGN_RE = re.compile(r"Assignment to constant variable ['\"]([A-Za-z_$][\w$]*)['\"]")

# Déclaration `const X =` (insensible à l'indentation ; PAS const X; seul ni
# `const X` sans initialisateur — on ne touche qu'à la forme avec affectation,
# qui est celle que le runtime a rencontrée).
def _fix_const_reassignment(source: str, var: str) -> tuple[str, List[str]]:
    decl = re.compile(r"\bconst\s+" + re.escape(var) + r"(\s*=)")
    changes: List[str] = []

    def _sub(m: re.Match) -> str:
        changes.append(f"const {var} = -> let {var} =")
        return f"let {var}{m.group(1)}"

    return decl.sub(_sub, source), changes


# `\n` littéral en séparateur de code — MÊME regex que la garde F-132
# (tools._CODE_SEPARATOR_NL_RE), recopiée ici pour éviter un import privé
# croisé ; toute évolution doit rester synchronisée des deux côtés.
_NL_KEYWORDS = (
    "const|let|var|function|return|if|else|for|while|switch|case|class|"
    r"new\b|document\.|window\.|addEventListener|try|catch|import|export|"
    r"async|await|def\b|print\("
)
_CODE_SEPARATOR_NL_RE = re.compile(
    r"(?:(?<=[;{}()\[\]])\\n|\\n(?=\s*(?:" + _NL_KEYWORDS + r")))"
)

# Blocs de code fence (```…``` y compris dans <pre>) : leur contenu est
# préservé tel quel par le repair \n (P4, port deer-flow).
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)

# Fichiers où les fixes s'appliquent (périmètre Prompt-Vault : web vanilla + py).
_CODE_FILE_SUFFIXES = (
    ".html", ".htm", ".js", ".mjs", ".cjs", ".css", ".ts", ".tsx", ".jsx",
    ".py", ".vue", ".svelte",
)


def _fix_literal_newline(source: str) -> tuple[str, List[str]]:
    """Remplace chaque `\\n` littéral en séparateur de code par un vrai saut.

    FENCE-AWARE (P4, port deer-flow `mindie_provider.py:154`
    `_decode_escaped_newlines_outside_fences`) : la transformation ne
    s'applique QUE hors des blocs de code fence (```…``` — typiquement les
    échantillons de code dans <pre>). À l'intérieur, `\\n` peut être du
    contenu légitime (chaînes affichées) : on ne touche à rien.
    """
    fences = _FENCE_RE.findall(source)
    segments = _FENCE_RE.split(source)
    total = 0
    out: List[str] = []
    for i, seg in enumerate(segments):
        total += len(_CODE_SEPARATOR_NL_RE.findall(seg))
        out.append(_CODE_SEPARATOR_NL_RE.sub("\n", seg))
        if i < len(fences):
            out.append(fences[i])  # fences intactes
    changes: List[str] = []
    if total:
        changes.append(f"{total} séquence(s) '\\n' littérale(s) -> vrai saut de ligne (hors fences)")
    return "".join(out), changes


def apply_known_fixes(path: str, error_message: str) -> str:
    """Applique les fixes mécaniques connus correspondant au message d'erreur.

    Retourne TOUJOURS un rapport textuel (jamais d'exception) :
      - fixes appliqués (avec détails) → le caller doit RE-TESTER (reload +
        console) pour confirmer ;
      - aucun pattern connu / fichier non-code / rien trouvé → dit explicitement
        qu'aucun fix automatique n'existe et qu'il faut rapporter le bug au
        Coder via le verdict normal.
    """
    try:
        if not path or not str(path).lower().endswith(_CODE_FILE_SUFFIXES):
            return (
                f"PAS DE FIX AUTO : '{path}' n'est pas un fichier code couvert "
                f"(html/js/css/ts/py/vue/svelte). Rapporte le bug normalement."
            )

        # Lecture défensive.
        try:
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
        except OSError as e:
            return f"PAS DE FIX AUTO : lecture impossible ({e}). Rapporte le bug normalement."

        changes: List[str] = []
        new_source = source

        # Classe 1 : const réassignée.
        m = _CONST_ASSIGN_RE.search(error_message or "")
        if m:
            var = m.group(1)
            new_source, ch = _fix_const_reassignment(new_source, var)
            if ch:
                changes.append(f"[const→let] variable '{var}' : " + "; ".join(ch))

        # Classe 2 : \n littéral (systématique — pas besoin du message d'erreur,
        # la signature est auto-suffisante ; mais on ne l'active que si le
        # message évoque une SyntaxError/Unexpected token pour éviter les
        # faux positifs sur fichiers sains).
        if error_message and re.search(r"SyntaxError|Unexpected (token|identifier|end)", error_message, re.IGNORECASE):
            new_source, ch = _fix_literal_newline(new_source)
            if ch:
                changes.extend(ch)

        if not changes:
            return (
                "PAS DE FIX AUTO : aucune classe de fix mécanique connue ne "
                "correspond à cette erreur (diagnostic LLM requis). Rapporte le "
                "bug via ton verdict normal — NE tente pas de patch manuel hasardeux."
            )

        if new_source == source:
            return (
                "PAS DE FIX AUTO : pattern reconnu mais AUCUNE occurrence "
                "trouvée dans le fichier (déjà corrigé ?). Re-teste pour vérifier."
            )

        # Écriture + traçabilité.
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_source)
        _log_fix(path, changes)
        report = "FIX AUTO APPLIQUÉ sur " + str(path) + " :\n- " + "\n- ".join(changes)
        report += (
            "\nPROCHAINE ACTION OBLIGATOIRE : navigate_page(reload) puis "
            "list_console_messages pour CONFIRMER que l'erreur a disparu, puis "
            "CONTINUE ton test plan."
        )
        return report
    except Exception as e:  # pragma: no cover - fail-open garanti
        return f"PAS DE FIX AUTO : erreur interne ({e}). Rapporte le bug normalement."


def _log_fix(path: str, changes: List[str]) -> None:
    """Journalise l'application en DuckDB (best-effort, jamais bloquant)."""
    try:
        from .event_stream import get_event_db
        from .idempotency import get_current_store

        store = get_current_store()
        run_id = store.run_id if (store and store.run_id) else "unknown_run"
        db = get_event_db()
        db.log_event(run_id, "tester", "fix", f"auto_fixer {path} : {'; '.join(changes)}")
    except Exception:
        pass
