"""Runner de tests PYTHON (subprocess pytest) — Nouveau (Priorité 2).

Contrairement au runner web (piloté par LLM via MCP Puppeteer), le runner Python
est DÉTERMINISTE : il lance `pytest` en sous-processus isolé, capture
stdout/stderr/code de sortie, et en déduit un verdict binaire sans appel LLM.
C'est plus rapide, plus fiable et gratuit (pas de tokens).

Capture robuste + troncature anti "Context Overflow" :
- Le stderr d'un échec pytest peut faire des centaines de lignes (traceback complet).
- On le tronque (head + tail) via `feedback_utils` avant de l'injecter au Coder,
  sinon le contexte explose au bout du 3ème essai → oubli des directives.
- Le stdout (résumé pytest "X passed, Y failed") est conservé en tête.

Auto-Résolution des Dépendances (F-26) : si le stderr contient un
`ModuleNotFoundError`, le runner installe lui-même le module manquant
(`pip install` non-persistant) puis relance les tests (1 retry max). Cela
évite de gaspiller un cycle LLM pour une simple dépendance absente. Opt-out
via AUTO_INSTALL_DEPS=false.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Optional, Tuple

from ..config import Settings
from ..feedback_utils import truncate_output
from ..logging_utils import NodeMetrics
from ..models import CoderOutput

# Regex du nom de module capturé dans un ModuleNotFoundError (ex: 'requests',
# 'requests.auth'). On accepte les points (sous-modules) puis on garde le top-level.
_MISSING_MODULE_RE = re.compile(r"No module named ['\"]([\w.]+)['\"]")
# Un identifiant Python top-level valide (anti-injection dans la commande pip) :
# on n'injecte jamais une chaîne arbitraire issue du stderr dans un subprocess.
_VALID_MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def extract_missing_module(stderr: str) -> Optional[str]:
    """Extrait le nom de module top-level d'un `ModuleNotFoundError` dans le stderr.

    `ModuleNotFoundError: No module named 'requests'` → "requests".
    `... 'requests.auth'` → "requests" (on garde le top-level, ce que pip attend).

    Retourne None si :
      - aucun `ModuleNotFoundError` détecté (autre type d'erreur) ;
      - le nom extrait n'est pas un identifiant Python valide (défense en profondeur :
        on n'injecte jamais une chaîne arbitraire issue du stderr dans la commande pip).

    Le stderr vient du test de code utilisateur ; risque d'injection faible, mais on
    valide quand même — ceinture + bretelles.
    """
    match = _MISSING_MODULE_RE.search(stderr or "")
    if not match:
        return None
    # Top-level uniquement : pip installe 'requests', pas 'requests.auth'.
    top_level = match.group(1).split(".", 1)[0]
    if not _VALID_MODULE_RE.match(top_level):
        return None
    return top_level


def _install_module(module: str, timeout_s: float = 120.0) -> bool:
    """Installe un module Python manquant via `pip install` (non-persistant).

    Non-persistant : le package est dispo pour ce run (donc pour la relance des
    tests), mais n'est PAS ajouté à pyproject.toml/uv.lock — non-intrusif pour le
    projet de l'utilisateur (aucun fichier modifié, aucun effet de bord visible en git).

    Args:
        module: Nom du module top-level validé (ex: "requests"). Issu d'extract_missing_module,
            donc déjà passé par la regex anti-injection.
        timeout_s: Timeout d'installation. Par défaut 120s (un gros package peut être long).

    Returns:
        True si l'installation a réussi (exit 0), False sinon (timeout, réseau, PyPI down,
        package introuvable). Jamais d'exception : un échec d'install ne fait pas planter le run.

    Sécurité : liste d'args (pas `shell=True`) — le nom du module vient du stderr mais
    est déjà validé par extract_missing_module. Double défense.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", module],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode == 0
    except Exception:
        # Timeout réseau, pip absent, PyPI down, etc. — l'auto-install échoue
        # gracieusement ; le test ressort en failure comme avant.
        return False


class PythonTestRunner:
    """Teste du code Python en lançant pytest dans un sous-processus isolé."""

    async def run(self, task: dict, model, settings: Settings) -> Tuple[Optional[CoderOutput], Optional[NodeMetrics]]:
        import time

        start = time.time()
        task_id = task.get("id", "unknown")

        # 1. Cible : fichiers .py / dossier / à défaut le cwd.
        targets = [f for f in (task.get("target_files") or []) if isinstance(f, str) and f.endswith(".py")]
        if not targets:
            # Pas de .py → on tente le dossier courant (pytest découvre les tests).
            test_args = ["."]
        else:
            # pytest accepte une liste de fichiers. On garde la forme simple.
            test_args = list(targets)

        # 2. Construction de la commande. `python -m pytest` est plus portable
        #    que l'appel direct `pytest` (fonctionne en l'absence du binaire sur PATH,
        #    tant que l'interpréteur du projet — uv/venv — est actif).
        #    On désactive le cache (-p no:cacheprovider) pour des runs reproductibles
        #    et on force le mode "court" (-q) : un échec = un bloc concis, pas un
        #    pavé de context lines. Le détail est dans le stderr capturé.
        #    CRITIQUE : on utilise sys.executable (interpréteur du process courant)
        #    et non le littéral "python" — sinon le subprocess hérite de l'interpréteur
        #    système (sans pytest) au lieu de celui du venv/uv où pytest est installé.
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *test_args]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.test_timeout_s,
                cwd=os.getcwd(),
                # encoding pour éviter les UnicodeDecodeError sur Windows (accents,
                # chemins). errors="replace" plutôt que crash sur octet inattendu.
                encoding="utf-8",
                errors="replace",
            )
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            # Un test qui boucle (ex: while True) ne doit pas figer l'usine.
            return self._failure(
                task_id,
                f"DÉLAI DÉPASSÉ : pytest n'a pas terminé après {settings.test_timeout_s}s.",
                start,
                settings,
            ), None
        except FileNotFoundError:
            # pytest absent de l'environnement → feedback actionnable, pas un crash.
            return self._failure(
                task_id,
                "pytest est introuvable dans l'environnement. "
                "Installez-le (`uv add pytest` ou `pip install pytest`).",
                start,
                settings,
            ), None

        # 3. Auto-Résolution des Dépendances (F-26) : si l'échec est un
        #    ModuleNotFoundError et que l'opt-in est actif, on installe le module
        #    manquant puis on relance les tests (1 SEUL retry — anti-boucle). Cela
        #    économise un cycle LLM (sinon le Coder tenterait de résoudre ça en
        #    réécrivant le code, sans savoir que c'est juste un package absent).
        auto_install_note = ""
        if exit_code != 0 and settings.auto_install_deps:
            module = extract_missing_module(stderr)
            if module:
                print(f"[auto-install] Module manquant détecté : '{module}' — installation...")
                if _install_module(module, timeout_s=settings.test_timeout_s):
                    try:
                        result2 = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            timeout=settings.test_timeout_s,
                            cwd=os.getcwd(),
                            encoding="utf-8",
                            errors="replace",
                        )
                        stdout = result2.stdout or ""
                        stderr = result2.stderr or ""
                        exit_code = result2.returncode
                        auto_install_note = f"[auto-install] '{module}' installé puis tests relancés."
                        print(f"[auto-install] '{module}' installé — tests relancés (exit_code={exit_code}).")
                    except subprocess.TimeoutExpired:
                        auto_install_note = f"[auto-install] '{module}' installé, mais les tests ont dépassé le délai à la relance."
                    except FileNotFoundError:
                        auto_install_note = f"[auto-install] '{module}' installé, mais pytest introuvable à la relance."
                else:
                    auto_install_note = f"[auto-install] Échec d'installation de '{module}' (réseau/PyPI down ?)."
                    print(f"[auto-install] Échec d'installation de '{module}'.")

        # 4. Verdict : exit 0 = succès ; tout le reste = échec.
        #    On concatène stdout (résumé court) + stderr (détails des échecs), tronqué.
        combined = self._format_output(stdout, stderr, exit_code)
        if auto_install_note:
            # L'auto-install peut transformer un failure en success : on garde la
            # trace de l'action pour l'observabilité (utile au débogage).
            combined = f"{auto_install_note}\n\n{combined}"
        details = truncate_output(
            combined,
            head_lines=settings.stderr_head_lines,
            tail_lines=settings.stderr_tail_lines,
            max_chars=settings.feedback_max_chars,
        )

        status = "success" if exit_code == 0 else "failure"
        metrics = NodeMetrics(
            node="python_tester",
            model="pytest-subprocess",  # pas de LLM : on le signale explicitement
            duration_s=time.time() - start,
            input_tokens=0,
            output_tokens=0,
        )
        return CoderOutput(task_id=task_id, status=status, details=details), metrics

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_output(stdout: str, stderr: str, exit_code: int) -> str:
        """Assemble une sortie lisible pour le Coder, sans escaping surprising."""
        parts = [f"[pytest] exit_code={exit_code}"]
        if stdout.strip():
            parts.append("=== STDOUT ===\n" + stdout.strip())
        if stderr.strip():
            parts.append("=== STDERR ===\n" + stderr.strip())
        return "\n\n".join(parts)

    @staticmethod
    def _failure(task_id: str, message: str, start: float, settings: Settings) -> CoderOutput:
        return CoderOutput(
            task_id=task_id,
            status="failure",
            details=truncate_output(
                message,
                head_lines=settings.stderr_head_lines,
                tail_lines=settings.stderr_tail_lines,
                max_chars=settings.feedback_max_chars,
            ),
        )
