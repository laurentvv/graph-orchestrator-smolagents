"""Tests F-114 (post-mortem run #9) : cap fullPage + nudge checklist visual_check.

Run #9 (`logs/e2e_f113_run.log`) : le Coder 4B a pris 48 screenshots dont des
fullPage jusqu'à 1265×9315 px (timeout LLM 600 s → tentative tuée), et n'a
JAMAIS appelé visual_check (0 appel en 3 tentatives) → la gate F-109 refusait
final_answer → échec définitif. Deux fixes déterministes dans vision_callback :
(1) force fullPage=False sur les clés présentes ; (2) au 3e screenshot sans
audit complet, rappel injecté dans memory_step.observations.
"""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from graph_orchestrator import tools
from graph_orchestrator.config import settings
from graph_orchestrator.vision_callback import (
    _BROWSER_STALL_THRESHOLD,
    _NUDGE_THRESHOLD,
    _ScreenshotCapturingTool,
    make_screenshot_callback,
    reset_browser_stall,
    reset_screenshot_nudge,
)


class _FakeImg:
    """Faux objet image (seul .copy() est requis par le callback)."""

    def copy(self):
        return self


class _FakeScreenshotTool:
    """Faux outil MCP take_screenshot qui enregistre les kwargs reçus."""

    name = "take_screenshot"
    description = "fake"
    inputs = {
        "filePath": {"type": "string", "description": "chemin"},
        "fullPage": {"type": "boolean", "description": "page entière"},
    }
    output_type = "object"

    def __init__(self):
        self.received_kwargs = None

    def forward(self, *args, **kwargs):
        self.received_kwargs = dict(kwargs)
        return "Took a screenshot."


@pytest.fixture(autouse=True)
def _clean_state():
    tools.reset_visual_audit()
    reset_screenshot_nudge()
    reset_browser_stall()
    yield
    tools.reset_visual_audit()
    reset_screenshot_nudge()
    reset_browser_stall()


def _make_wrapper():
    fake = _FakeScreenshotTool()
    holder: list = []
    return _ScreenshotCapturingTool(fake, holder), fake, holder


class TestFullPageCap:
    def test_fullpage_true_force_false(self):
        wrapper, fake, _ = _make_wrapper()
        wrapper.forward(fullPage=True)
        assert fake.received_kwargs["fullPage"] is False

    def test_fullpage_false_unchanged(self):
        wrapper, fake, _ = _make_wrapper()
        wrapper.forward(fullPage=False)
        assert fake.received_kwargs["fullPage"] is False

    def test_cle_absente_jamais_injectee(self):
        wrapper, fake, _ = _make_wrapper()
        wrapper.forward(format="jpeg")
        assert "fullPage" not in fake.received_kwargs
        assert "full_page" not in fake.received_kwargs

    def test_snake_case_full_page_couvert(self):
        wrapper, fake, _ = _make_wrapper()
        wrapper.forward(full_page=True)
        assert fake.received_kwargs["full_page"] is False

    def test_opt_out_respecte_fullpage(self):
        # Settings est frozen : on patch la référence du module sous test
        # (convention test_bash_guard — « patch à la source »).
        relaxed = replace(settings, vision_fullpage_cap=False)
        with patch("graph_orchestrator.vision_callback.settings", relaxed):
            wrapper, fake, _ = _make_wrapper()
            wrapper.forward(fullPage=True)
        assert fake.received_kwargs["fullPage"] is True

    def test_filepath_toujours_stripe(self):
        """Régression F-50/F-90 : le cap ne doit pas masquer le strip filePath."""
        wrapper, fake, _ = _make_wrapper()
        wrapper.forward(filePath="screenshot.png", fullPage=True)
        assert "filePath" not in fake.received_kwargs
        assert fake.received_kwargs["fullPage"] is False


class TestChecklistNudge:
    def _make_callback(self, criteria: int):
        holder: list = []
        cb = make_screenshot_callback(holder, visual_criteria_count=criteria)
        return cb, holder

    def _step(self, cb, holder, observations="Code output"):
        holder.append(_FakeImg())
        memory_step = SimpleNamespace(observations=observations, observations_images=None)
        cb(memory_step, agent=None)
        return memory_step

    def test_pas_de_nudge_sous_le_seuil(self):
        cb, holder = self._make_callback(criteria=6)
        for _ in range(_NUDGE_THRESHOLD - 1):
            step = self._step(cb, holder)
            assert "[CHECKLIST VISUELLE]" not in (step.observations or "")

    def test_nudge_au_3e_screenshot(self):
        cb, holder = self._make_callback(criteria=6)
        for _ in range(_NUDGE_THRESHOLD - 1):
            self._step(cb, holder)
        step = self._step(cb, holder)
        assert "[CHECKLIST VISUELLE]" in step.observations
        assert "Screenshot #3" in step.observations
        assert "6/6" in step.observations
        assert "[1, 2, 3, 4, 5, 6]" in step.observations
        assert "visual_check" in step.observations

    def test_nudge_liste_les_manquants_seulement(self):
        for n in (1, 2):
            tools._VISUAL_AUDIT.append(
                {"criterion_number": n, "verdict": True, "observation": "ok"}
            )
        cb, holder = self._make_callback(criteria=6)
        for _ in range(_NUDGE_THRESHOLD):
            self._step(cb, holder)
        step = self._step(cb, holder)
        assert "4/6" in step.observations
        assert "[3, 4, 5, 6]" in step.observations

    def test_pas_de_nudge_checklist_complete(self):
        for n in range(1, 7):
            tools._VISUAL_AUDIT.append(
                {"criterion_number": n, "verdict": True, "observation": "ok"}
            )
        cb, holder = self._make_callback(criteria=6)
        for _ in range(_NUDGE_THRESHOLD + 5):
            step = self._step(cb, holder)
            assert "[CHECKLIST VISUELLE]" not in step.observations

    def test_pas_de_nudge_sans_critères_chemin_tester(self):
        """Le Tester fabrique le callback sans critères → nudge inactif."""
        cb, holder = self._make_callback(criteria=0)
        for _ in range(_NUDGE_THRESHOLD + 3):
            step = self._step(cb, holder)
            assert "[CHECKLIST VISUELLE]" not in step.observations

    def test_reset_repart_de_zero(self):
        cb, holder = self._make_callback(criteria=6)
        for _ in range(_NUDGE_THRESHOLD):
            self._step(cb, holder)
        reset_screenshot_nudge()
        for _ in range(_NUDGE_THRESHOLD - 1):
            step = self._step(cb, holder)
            assert "[CHECKLIST VISUELLE]" not in step.observations
        step = self._step(cb, holder)
        assert "Screenshot #3" in step.observations

    def test_observations_existantes_preservees(self):
        cb, holder = self._make_callback(criteria=2)
        for _ in range(_NUDGE_THRESHOLD):
            self._step(cb, holder, observations="Résultat du code")
        step = self._step(cb, holder, observations="Résultat du code")
        assert step.observations.startswith("Résultat du code")
        assert "[CHECKLIST VISUELLE]" in step.observations

    def test_compteur_ignore_les_steps_sans_screenshot(self):
        """Holder vide → early-return : le compteur ne doit pas avancer."""
        cb, holder = self._make_callback(criteria=6)
        memory_step = SimpleNamespace(observations="pas d'image", observations_images=None)
        cb(memory_step, agent=None)  # holder vide → rien
        for _ in range(_NUDGE_THRESHOLD - 1):
            self._step(cb, holder)
        step = self._step(cb, holder)  # 3e screenshot RÉEL
        assert "Screenshot #3" in step.observations


class TestBrowserStallNudge:
    """F-125 (post-mortem run 2026-08-19 12:02, Tetris) : onglet gelé.

    Le renderer ne répondait plus (timeout CDP ~190 s sur screenshots/evaluate/
    input) alors que list_pages répondait : le Coder a brûlé ~15 steps à retenter
    au lieu de récupérer → « Coder crash ». Le nudge injecte une directive de
    récupération à partir de 3 observations d'erreur protocole consécutives.
    """

    _STALLED = (
        "Out: Error: Runtime.evaluate timed out. Increase the 'protocolTimeout' "
        "setting in launch/connect calls for a higher timeout if needed."
    )

    def _make_callback(self, criteria: int = 0):
        holder: list = []
        cb = make_screenshot_callback(holder, visual_criteria_count=criteria)
        return cb, holder

    def _step(self, cb, holder, observations="Code output"):
        # Un step gelé ne produit AUCUNE image : holder laissé vide exprès.
        memory_step = SimpleNamespace(observations=observations, observations_images=None)
        cb(memory_step, agent=None)
        return memory_step

    def test_pas_de_nudge_sous_le_seuil(self):
        cb, holder = self._make_callback()
        for _ in range(_BROWSER_STALL_THRESHOLD - 1):
            step = self._step(cb, holder, observations=self._STALLED)
            assert "[NAVIGATEUR GELÉ]" not in (step.observations or "")

    def test_nudge_au_3e_step_gele_sans_screenshot(self):
        """Le nudge doit agir même AUCUNE image capturée (c'est le signal même)."""
        cb, holder = self._make_callback()
        for _ in range(_BROWSER_STALL_THRESHOLD):
            step = self._step(cb, holder, observations=self._STALLED)
        assert "[NAVIGATEUR GELÉ]" in step.observations
        assert "navigate_page" in step.observations
        assert "final_answer" in step.observations
        assert "3 erreurs de protocole" in step.observations

    def test_page_detachee_comptee(self):
        """Signature « Not attached to an active page » (run Tetris, step 12+)."""
        cb, holder = self._make_callback()
        stalled = (
            "Out: Error: Protocol error (Page.captureScreenshot): "
            "Not attached to an active page"
        )
        for _ in range(_BROWSER_STALL_THRESHOLD):
            step = self._step(cb, holder, observations=stalled)
        assert "[NAVIGATEUR GELÉ]" in step.observations

    def test_step_sain_reset_le_compteur(self):
        cb, holder = self._make_callback()
        for _ in range(_BROWSER_STALL_THRESHOLD - 1):
            self._step(cb, holder, observations=self._STALLED)
        self._step(cb, holder, observations="Out: OK, canvas rendu")  # step sain
        step = self._step(cb, holder, observations=self._STALLED)
        assert "[NAVIGATEUR GELÉ]" not in step.observations  # recompté à 1

    def test_reset_repart_de_zero(self):
        cb, holder = self._make_callback()
        for _ in range(_BROWSER_STALL_THRESHOLD):
            self._step(cb, holder, observations=self._STALLED)
        reset_browser_stall()
        for _ in range(_BROWSER_STALL_THRESHOLD - 1):
            step = self._step(cb, holder, observations=self._STALLED)
            assert "[NAVIGATEUR GELÉ]" not in step.observations

    def test_actif_aussi_pour_le_tester(self):
        """Callback sans critères visuels (chemin Tester) : nudge anti-gel actif."""
        cb, holder = self._make_callback(criteria=0)
        for _ in range(_BROWSER_STALL_THRESHOLD):
            step = self._step(cb, holder, observations=self._STALLED)
        assert "[NAVIGATEUR GELÉ]" in step.observations

    def test_observations_existantes_preservees(self):
        cb, holder = self._make_callback()
        for _ in range(_BROWSER_STALL_THRESHOLD):
            step = self._step(cb, holder, observations=f"Out: …\n{self._STALLED}")
        assert step.observations.startswith("Out: …")
        assert "[NAVIGATEUR GELÉ]" in step.observations
