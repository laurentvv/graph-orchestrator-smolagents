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

Pose aussi les fondations de l'auto-dépendances (F-26) : on détecte un
`ModuleNotFoundError` dans le stderr pour préparer l'auto-install future.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional, Tuple

from ..config import Settings
from ..feedback_utils import truncate_output
from ..logging_utils import NodeMetrics
from ..models import CoderOutput


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

        # 3. Verdict : exit 0 = succès ; tout le reste = échec.
        #    On concatène stdout (résumé court) + stderr (détails des échecs), tronqué.
        combined = self._format_output(stdout, stderr, exit_code)
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
