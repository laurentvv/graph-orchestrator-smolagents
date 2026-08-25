"""Runner de tests WEB — moteur UNIQUE pydantic-ai-harness (F-169).

F-169 (décision user 2026-08-24, « enlève le CodeAgent de smolagents ») :
l'exécution smolagents (CompactingCodeAgent + MCP Puppeteer + run_with_retry)
est RETIRÉE — le Web Tester tourne sur le harness pydantic-ai
(``tester_pydantic.run_tester_pydantic``), chaîne validée E2E (F-162).
L'interface ``TestRunner`` (dispatch par techno) est conservée : ce runner
reste le fallback par défaut quand aucune techno n'est détectée.

Le nettoyage DOM s'opère côté navigateur (JS injecté dans le prompt du moteur
pydantic, plus efficace : pas de round-trip du HTML brut).
"""

from __future__ import annotations

from typing import Optional, Tuple

# clean_dom_for_llm est importé côté tests (tests/test_dom_filter.py) et utilisé
# à terme pour post-traiter tout HTML rapatrié côté Python. On garde l'import
# symbolique pour documenter la dépendance et faciliter son utilisation future.
from ..dom_filter import clean_dom_for_llm  # noqa: F401
from ..logging_utils import NodeMetrics
from ..models import CoderOutput


class WebTestRunner:
    """Teste une application web (HTML/CSS/JS) via le harness pydantic-ai."""

    async def run(self, task: dict, model, settings) -> Tuple[Optional[CoderOutput], Optional[NodeMetrics]]:
        from ..tester_pydantic import run_tester_pydantic

        return await run_tester_pydantic(task, settings)
