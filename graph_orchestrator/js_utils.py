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
