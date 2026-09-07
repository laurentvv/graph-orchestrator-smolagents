"""F-171 — Vérificateurs déterministes autour du Coder (0 LLM).

Mandat run v5 (2026-08-25, logs/run_coding_20260825_135356) : les vérifications
existantes sont soit *opt-in* (outils ``check_js_syntax``/``visual_check`` que le
modèle peut oublier d'appeler) soit *a posteriori* (nœuds Linter/Static/Tester
après toute la session Coder, ~10 min d'audit LLM par itération). Deux briques
comblent le vide, pattern aider ``lint_edited`` (auto-lint ON, auto-test OFF) :

- **A — vérif statique post-écriture** : capability pydantic-ai ``Hooks``
  (``after_tool_execute`` filtré sur les outils d'écriture) qui lance
  ``linter.lint_file`` + ``check_js_syntax`` sur le SEUL fichier écrit et
  appose le résultat CONSULTATIF au retour d'outil — le modèle se corrige au
  tour suivant. Zéro requête LLM ajoutée, timeout dur.
- **B — smoke navigateur au verdict** : Chrome headless ``--dump-dom
  --enable-logging=stderr`` sur les cibles HTML (``file://``, 0 serveur, 0
  LLM) — attrape les erreurs JS AU CHARGEMENT (famille ``RangeError``
  récursion ``init()`` du run v5, validée en live) que la syntaxe ne voit
  pas. Injectée au chemin verdict F-170 : tour correctif borné après un run
  réussi, findings réels dans le prompt de sauvetage post-budget.

Règles de sécurité (leçons F164-6 / §8.3 AGENTS.md) : toujours CONSULTATIF
sauf échec mécanique prouvable, fail-open (vérif indisponible = silence,
jamais de blocage), budgets bornés partout.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

# Outils d'écriture du Coder (coder_pydantic.py) — le hook ne se déclenche
# QUE sur ceux-ci : lecture/screenshot/log restent intouchés.
WRITE_TOOL_NAMES = ("append_file", "search_replace", "multi_replace")

# Bornes : jamais plus de N lignes de feedback par écriture (contexte Coder
# borné 8-12 K tokens/tour — le warning doit rester marginal).
_MAX_FINDINGS = 5
_MAX_FINDING_LEN = 220

_HOOK_TIMEOUT_S = 15.0
_SMOKE_TIMEOUT_S = 25.0
_SMOKE_VIRTUAL_BUDGET_MS = 4000

# Lignes console Chrome stderr : `...INFO:CONSOLE:25] "Uncaught RangeError:
# Maximum call stack size exceeded", source: file:///.../script.js (25)`
# Deux formes de niveau selon la version/le canal : `CONSOLE:25]` et
# `CONSOLE(0)]` — on accepte les deux.
_CONSOLE_LINE_RE = re.compile(
    r':CONSOLE(?::|\()(\d*)\)?\]\s*"([^"]+)"(?:,\s*source:\s*(\S+?)\s+\((\d+)\))?'
)
# Familles d'erreurs critiques uniquement — pas de false positive sur les
# console.log/warn bénins.
_CRITICAL_JS_RE = re.compile(
    r"\bUncaught\b|SyntaxError|ReferenceError|TypeError|RangeError|EvalError|URIError"
)


# ============================================================
# A — Vérification statique post-écriture (capability Hooks)
# ============================================================

def _classify_check_js_syntax(message: str) -> List[str]:
    """Extrait les findings du message de check_js_syntax ('❌ …' = erreur)."""
    if not message:
        return []
    if "❌" in message:
        return [line.strip("- \n") for line in message.splitlines()
                if line.strip().startswith("- ")] or [message]
    return []


def run_static_verify(path: str) -> List[str]:
    """Vérifications statiques déterministes sur UN fichier écrit.

    Réutilise les canons existants (linter.py tree-sitter/py_compile/HTML,
    check_js_syntax node --check + var(--x) sans :root + fuites Python).
    Fail-open : toute exception interne → liste vide (jamais de blocage).
    """
    try:
        from .linter import lint_file
        from .path_utils import normalize_tool_path

        abs_path = normalize_tool_path(path)
        findings: List[str] = []

        lint = lint_file(abs_path)
        # Les [avertissement] (fichier attendu absent) ne sont PAS des
        # findings bloquants — fail-open par design.
        findings.extend(
            e for e in (lint.errors or []) if not e.startswith("[avertissement]")
        )

        if abs_path.lower().endswith((".js", ".html", ".htm")):
            from . import tools as _tools
            findings.extend(_classify_check_js_syntax(_tools.check_js_syntax(path=path)))

        findings = [f[:_MAX_FINDING_LEN] for f in findings if f][:_MAX_FINDINGS]
        return findings
    except Exception:  # noqa: BLE001 — fail-open absolu
        return []


def _log_verify_event(event_type: str, message: str) -> None:
    """Observabilité DuckDB (canal agent du run courant) — best effort."""
    try:
        from .event_stream import get_event_db
        from .idempotency import get_current_store

        store = get_current_store()
        run_id = store.run_id if (store and store.run_id) else "unknown_run"
        get_event_db().log_event(run_id, "coder", event_type, message)
    except Exception:  # noqa: BLE001 — l'observabilité ne doit jamais casser le run
        pass


def build_verifier_hooks(settings: Any = None) -> Optional[Any]:
    """Capability pydantic-ai « vérif statique post-écriture » (F-171 A).

    Retourne un ``Hooks`` à passer à ``Agent(capabilities=[...])`` ou None si
    désactivé (``CODER_STATIC_VERIFY=false``). Le hook est SYNCHRONE : la doc
    pydantic-ai exécute les hooks sync dans un worker thread — parfait pour
    du subprocess (node --check) sans bloquer l'event loop.
    """
    if settings is not None and not getattr(settings, "coder_static_verify", True):
        return None

    from pydantic_ai.capabilities import Hooks

    hooks = Hooks()

    @hooks.on.after_tool_execute(tools=list(WRITE_TOOL_NAMES), timeout=_HOOK_TIMEOUT_S)
    def verify_write(ctx, *, call, tool_def, args, result):  # noqa: ANN001, ARG001
        """Appose les findings statiques au retour d'outil (consultatif)."""
        path = str((args or {}).get("path", ""))
        if not path:
            return result
        findings = run_static_verify(path)
        if not findings:
            return result
        _log_verify_event(
            "verify",
            f"F-171 statique : {len(findings)} finding(s) sur {path} — "
            + " | ".join(findings[:3]),
        )
        block = (
            f"\n\n⚠ [F-171 vérificateur déterministe — CONSULTATIF] "
            f"{len(findings)} problème(s) statique(s) détecté(s) sur {path} :\n"
            + "\n".join(f"- {f}" for f in findings)
            + "\nSi ce sont de vrais problèmes, corrige-les via search_replace "
              "AVANT de continuer. (Vérif automatique : faux positifs possibles, "
              "juge par toi-même.)"
        )
        if isinstance(result, str):
            return result + block
        return result  # type non-chaîne (improbable pour ces tools) : intact

    return hooks


# ============================================================
# B — Smoke navigateur déterministe (Chrome headless, 0 LLM)
# ============================================================

@dataclass
class SmokeResult:
    """Résultat du smoke : ``skipped`` non vide = pas de vérif possible."""

    skipped: str = ""
    checked: List[str] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)


def parse_console_errors(stderr_text: str, max_findings: int = _MAX_FINDINGS) -> List[str]:
    """Extrait les erreurs JS critiques des lignes CONSOLE du stderr Chrome."""
    seen: List[str] = []
    for match in _CONSOLE_LINE_RE.finditer(stderr_text or ""):
        message = match.group(2) or ""
        if not _CRITICAL_JS_RE.search(message):
            continue
        source = match.group(3) or "?"
        line = match.group(4) or "?"
        short_src = os.path.basename(source.split("/")[-1]) or source
        entry = f'"{message}" ({short_src}:{line})'
        if entry not in seen:
            seen.append(entry)
    return seen[:max_findings]


def run_smoke_check(html_paths: List[str],
                    timeout_s: float = _SMOKE_TIMEOUT_S) -> SmokeResult:
    """Charge chaque page HTML dans un Chrome headless jetable et collecte
    les erreurs JS critiques au chargement (console stderr).

    Déterministe, 0 LLM, 0 serveur HTTP (``file://``). Fail-open : Chrome
    absent / cible absente / timeout interne → skip ou finding consultatif,
    jamais d'exception vers l'appelant.
    """
    from .browser_pool import find_chrome_executable

    chrome = find_chrome_executable()
    if not chrome:
        return SmokeResult(skipped="chrome introuvable")

    targets = [p for p in (html_paths or []) if os.path.isfile(p)]
    if not targets:
        return SmokeResult(skipped="aucune cible HTML sur disque")

    result = SmokeResult(checked=[os.path.basename(p) for p in targets])
    tmp_profile = tempfile.mkdtemp(prefix="f171_smoke_")
    try:
        for path in targets:
            name = os.path.basename(path)
            cmd = [
                chrome, "--headless=new", "--disable-gpu", "--no-first-run",
                "--no-default-browser-check", f"--user-data-dir={tmp_profile}",
                "--enable-logging=stderr", "--v=0",
                f"--virtual-time-budget={_SMOKE_VIRTUAL_BUDGET_MS}",
                "--dump-dom", Path(path).resolve().as_uri(),
            ]
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, timeout=timeout_s,
                    encoding="utf-8", errors="replace",
                )
            except subprocess.TimeoutExpired:
                result.findings.append(
                    f"{name} : smoke interrompu (timeout {timeout_s:.0f}s) — "
                    "chargement très lent ou boucle bloquante, vérifie manuellement"
                )
                continue
            except Exception as exc:  # noqa: BLE001 — fail-open par cible
                result.findings.append(f"{name} : smoke impossible ({exc})")
                continue
            result.findings.extend(
                f"{name} → {m}" for m in parse_console_errors(proc.stderr or "")
            )
    finally:
        shutil.rmtree(tmp_profile, ignore_errors=True)
    return result


def resolve_smoke_targets(task: dict) -> List[str]:
    """Cibles HTML du smoke = target_files *.html résolues comme les écritures
    du Coder (même normalize_tool_path → même workspace, par construction)."""
    try:
        from .path_utils import normalize_tool_path

        return [
            normalize_tool_path(str(f))
            for f in (task.get("target_files") or [])
            if str(f).lower().endswith((".html", ".htm"))
        ]
    except Exception:  # noqa: BLE001 — fail-open
        return []


def format_smoke_findings(findings: List[str]) -> str:
    """Bloc findings pour prompt (tour correctif ou sauvetage post-budget)."""
    return "\n".join(f"- {f}" for f in findings[:_MAX_FINDINGS * 2])
