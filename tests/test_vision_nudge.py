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
    _NAV_TIMEOUT_MARKER,
    _NUDGE_THRESHOLD,
    _READ_STALL_THRESHOLD,
    _ScreenshotCapturingTool,
    make_screenshot_callback,
    reset_browser_stall,
    reset_nav_freeze_nudge,
    reset_read_stall,
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
    reset_read_stall()
    yield
    tools.reset_visual_audit()
    reset_screenshot_nudge()
    reset_browser_stall()
    reset_read_stall()


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


class TestNavFreezeNudge:
    """F-129 (post-mortem run 2026-08-20_0901, Tetris) : gel AU CHARGEMENT.

    navigate_page répondait « Navigation timeout of 10000 ms exceeded » dès la
    1re navigation (JS bloquant le thread avant l'événement load — do...while
    de rejet jamais terminant). Le nudge F-125 ne détectait pas ce cas : marqueur
    "timed out" sans match + compteur remis à zéro par les commandes saines du
    browser-process. F-129 = directive immédiate dès la 1re occurrence.
    """

    # Message exact observé dans le run 2026-08-20_0901 (step 12).
    _NAV_TIMEOUT = (
        "Out: Unable to navigate in the selected page: Navigation timeout "
        "of 10000 ms exceeded."
    )

    def _make_callback(self, criteria: int = 0):
        holder: list = []
        cb = make_screenshot_callback(holder, visual_criteria_count=criteria)
        return cb, holder

    def _step(self, cb, holder, observations="Code output"):
        memory_step = SimpleNamespace(observations=observations, observations_images=None)
        cb(memory_step, agent=None)
        return memory_step

    def setup_method(self):
        reset_nav_freeze_nudge()
        reset_browser_stall()

    def test_nudge_immediat_premiere_occurrence(self):
        """Pas de seuil : un timeout de navigation locale est TOUJOURS pathologique."""
        cb, holder = self._make_callback()
        step = self._step(cb, holder, observations=self._NAV_TIMEOUT)
        assert "[GEL AU CHARGEMENT #1]" in step.observations

    def test_pas_de_nudge_sur_step_sain(self):
        cb, holder = self._make_callback()
        step = self._step(cb, holder, observations="Out: page chargée, 0 erreur console")
        assert "[GEL AU CHARGEMENT" not in (step.observations or "")

    def test_message_dirige_vers_le_code_pas_le_navigateur(self):
        cb, holder = self._make_callback()
        step = self._step(cb, holder, observations=self._NAV_TIMEOUT)
        obs = step.observations
        # Diagnostic : lire le code, chercher les boucles, corriger chirurgicalement.
        assert "read_file" in obs
        assert "while" in obs
        assert "search_replace" in obs
        assert "NE RETENTE PAS" in obs

    def test_message_mentionne_console_silencieuse(self):
        """Un gel ne produit AUCUNE erreur console — piège constaté step 15 du run."""
        cb, holder = self._make_callback()
        step = self._step(cb, holder, observations=self._NAV_TIMEOUT)
        assert "silencieux" in step.observations or "silencieuse" in step.observations

    def test_reset_repart_de_zero(self):
        cb, holder = self._make_callback()
        self._step(cb, holder, observations=self._NAV_TIMEOUT)
        reset_nav_freeze_nudge()
        step = self._step(cb, holder, observations="Out: sain")
        assert "[GEL AU CHARGEMENT" not in step.observations

    def test_occurrences_multiples_comptees(self):
        """Le compteur croît (observabilité) et le nudge se répète (pattern F-128)."""
        cb, holder = self._make_callback()
        step = self._step(cb, holder, observations=self._NAV_TIMEOUT)
        assert "[GEL AU CHARGEMENT #1]" in step.observations
        step = self._step(cb, holder, observations=self._NAV_TIMEOUT)
        assert "[GEL AU CHARGEMENT #2]" in step.observations

    def test_observations_existantes_preservees(self):
        cb, holder = self._make_callback()
        step = self._step(cb, holder, observations=f"Out: …\n{self._NAV_TIMEOUT}")
        assert step.observations.startswith("Out: …")
        assert "[GEL AU CHARGEMENT #1]" in step.observations

    def test_actif_aussi_pour_le_tester(self):
        """Callback sans critères visuels (chemin Tester) : nudge actif aussi."""
        cb, holder = self._make_callback(criteria=0)
        step = self._step(cb, holder, observations=self._NAV_TIMEOUT)
        assert "[GEL AU CHARGEMENT #1]" in step.observations

    def test_navigation_timeout_compte_dans_stall_f125(self):
        """Fix marqueur : « Navigation timeout » incrémente AUSSI le compteur F-125
        (avant, ce message ne matchait aucun marqueur → jamais compté)."""
        from graph_orchestrator.vision_callback import _BROWSER_STALL_STATE

        cb, holder = self._make_callback()
        # 1 timeout navigation + 2 erreurs protocole classiques = 3 marqueurs.
        self._step(cb, holder, observations=self._NAV_TIMEOUT)
        stalled = "Out: Error: Page.captureScreenshot timed out."
        self._step(cb, holder, observations=stalled)
        step = self._step(cb, holder, observations=stalled)
        assert "[NAVIGATEUR GELÉ]" in step.observations
        assert _NAV_TIMEOUT_MARKER == "Navigation timeout"
        assert _BROWSER_STALL_STATE["count"] >= _BROWSER_STALL_THRESHOLD


class TestReadStallNudge:
    """F-130 (post-mortem run 2026-08-20_1028) : lectures stériles du même fichier.

    Le Coder 4B a relu index.html ~10 fois sans le modifier (mauvaise piste sur
    un TypeError console) jusqu'au plafond de steps. Le nudge doit déclencher au
    seuil de lectures SANS modification, être ré-armé par une édition, et rester
    inactif pour des fichiers différents.
    """

    def _cb(self, criteria: int = 0):
        return make_screenshot_callback([], visual_criteria_count=criteria)

    def _step(self, cb, code: str = "", observations: str = "Out: …"):
        memory_step = SimpleNamespace(
            observations=observations,
            observations_images=None,
            code_action=code,
            tool_calls=None,
            step_number=1,
        )
        cb(memory_step, agent=SimpleNamespace(max_steps=40))
        return memory_step

    def test_pas_de_nudge_sous_le_seuil(self):
        cb = self._cb()
        for _ in range(_READ_STALL_THRESHOLD - 1):
            step = self._step(cb, code='c = read_file(path="index.html")')
            assert "[LECTURES STÉRILES]" not in (step.observations or "")

    def test_nudge_au_seuil(self):
        cb = self._cb()
        for _ in range(_READ_STALL_THRESHOLD - 1):
            self._step(cb, code='c = read_file(path="index.html")')
        step = self._step(cb, code='c = read_file(path="index.html")')
        assert "[LECTURES STÉRILES]" in step.observations
        assert "index.html" in step.observations
        assert "search_replace" in step.observations
        assert "list_console_messages" in step.observations

    def test_fichiers_differents_non_sommes(self):
        cb = self._cb()
        for i in range(_READ_STALL_THRESHOLD - 1):
            path = "a.js" if i % 2 else "b.js"
            step = self._step(cb, code=f'c = read_file(path="{path}")')
            assert "[LECTURES STÉRILES]" not in (step.observations or "")

    def test_edit_rearme_le_compteur_du_fichier(self):
        cb = self._cb()
        for _ in range(_READ_STALL_THRESHOLD - 1):
            self._step(cb, code='c = read_file(path="index.html")')
        # Une modification ré-arme le droit de lecture (pattern read→edit légitime
        # imposé par la garde Read-Before-Write).
        self._step(
            cb,
            code='search_replace(path="index.html", old_string=r"""a""", new_string=r"""b""")',
        )
        step = self._step(cb, code='c = read_file(path="index.html")')
        assert "[LECTURES STÉRILES]" not in (step.observations or "")

    def test_forme_positionnelle_codeagent(self):
        cb = self._cb()
        step = self._step(cb, code='read_file("styles.css")')
        assert "[LECTURES STÉRILES]" not in (step.observations or "")

    def test_forme_tool_calls_tca(self):
        cb = self._cb()
        memory_step = SimpleNamespace(
            observations="Out: …",
            observations_images=None,
            code_action="",
            tool_calls=[
                SimpleNamespace(name="read_file", arguments={"path": "styles.css"}),
                SimpleNamespace(name="read_file", arguments={"path": "styles.css"}),
            ],
            step_number=1,
        )
        cb(memory_step, agent=SimpleNamespace(max_steps=40))
        # 2 lectures d'un coup : comptées, mais sous le seuil.
        assert "[LECTURES STÉRILES]" not in (memory_step.observations or "")

    def test_reset_repart_de_zero(self):
        cb = self._cb()
        for _ in range(_READ_STALL_THRESHOLD):
            self._step(cb, code='c = read_file(path="x.py")')
        reset_read_stall()
        for _ in range(_READ_STALL_THRESHOLD - 1):
            step = self._step(cb, code='c = read_file(path="x.py")')
            assert "[LECTURES STÉRILES]" not in (step.observations or "")

    def test_actif_aussi_pour_le_tester(self):
        """Callback sans critères visuels (chemin Tester) : nudge actif aussi —
        le stall de lectures est du gaspillage pour tout agent outillé."""
        cb = self._cb(criteria=0)
        for _ in range(_READ_STALL_THRESHOLD - 1):
            self._step(cb, code='c = read_file(path="script.js")')
        step = self._step(cb, code='c = read_file(path="script.js")')
        assert "[LECTURES STÉRILES]" in step.observations


class TestWindDownNudge:
    """F-131 (post-mortem run 2026-08-20_1028) : convergence au plafond de steps.

    Les 3 tentatives Coder sont mortes à « Reached max steps » en exploration.
    À ≤5 steps du plafond avec checklist incomplète → directive de convergence.
    """

    def _step(self, criteria: int, step_number: int, max_steps: int = 40, audited=()):
        for n in audited:
            tools._VISUAL_AUDIT.append(
                {"criterion_number": n, "verdict": True, "observation": "ok"}
            )
        cb = make_screenshot_callback([], visual_criteria_count=criteria)
        memory_step = SimpleNamespace(
            observations="Out: …",
            observations_images=None,
            code_action="",
            tool_calls=None,
            step_number=step_number,
        )
        cb(memory_step, agent=SimpleNamespace(max_steps=max_steps))
        return memory_step

    def test_nudge_dans_les_5_derniers_steps(self):
        step = self._step(criteria=6, step_number=36)  # 4 restants
        assert "[BUDGET" in step.observations
        assert "4 step(s) restant(s)" in step.observations
        assert "final_answer" in step.observations

    def test_nudge_au_dernier_step(self):
        step = self._step(criteria=6, step_number=39)  # 1 restant
        assert "[BUDGET" in step.observations
        assert "1 step(s) restant(s)" in step.observations

    def test_pas_de_nudge_loin_du_plafond(self):
        step = self._step(criteria=6, step_number=30)  # 10 restants
        assert "[BUDGET" not in (step.observations or "")

    def test_pas_de_nudge_step_fatal(self):
        """Au step ATTEIGNANT le plafond (0 restant), il est trop tard : pas de bruit."""
        step = self._step(criteria=6, step_number=40)
        assert "[BUDGET" not in (step.observations or "")

    def test_inactif_sans_critères(self):
        """Tester (criteria=0) : pas de wind-down (le fallback max-steps F-61
        couvre déjà la sortie du Tester)."""
        step = self._step(criteria=0, step_number=38)
        assert "[BUDGET" not in (step.observations or "")

    def test_pas_de_nudge_checklist_complete(self):
        step = self._step(criteria=6, step_number=38, audited=range(1, 7))
        assert "[BUDGET" not in (step.observations or "")

    def test_message_liste_les_manquants(self):
        step = self._step(criteria=6, step_number=37, audited=(1, 2))
        assert "[3, 4, 5, 6]" in step.observations
        assert "CONVERGENCE" in step.observations

    def test_verdict_false_explicitement_permis(self):
        """Le message doit ACCEPTER un verdict honnête False (échec prouvé > run brûlé)."""
        step = self._step(criteria=6, step_number=38)
        assert "verdict" in step.observations.lower()


# ===========================================================================
# Goulot run 2026-08-21_1337 : churn d'édition (P2) + budget vision (P3)
# ===========================================================================

class TestEditChurnNudge:
    """5 edits chirurgicaux consécutifs sans effet → sortie d'auto-fix honnête."""

    def _nudge(self, code: str, observations: str):
        from graph_orchestrator.vision_callback import (
            _build_edit_churn_nudge,
            reset_edit_churn,
        )

        reset_edit_churn()
        step = SimpleNamespace(code_action=code, observations=observations, tool_calls=None)
        return _build_edit_churn_nudge(step)

    def test_aucun_edit_pas_de_nudge(self):
        assert self._nudge("read_file('a')", "Out: contenu") is None

    def test_edit_reussit_reset(self):
        assert (
            self._nudge(
                "search_replace(path='a', old_string='x', new_string='y')",
                "Successfully updated a (1 occurrences replaced).",
            )
            is None
        )

    def test_cinq_edits_rates_declenchent(self):
        from graph_orchestrator.vision_callback import reset_edit_churn, _EDIT_CHURN_STATE

        reset_edit_churn()
        step = SimpleNamespace(
            code_action="search_replace(path='a', old_string='x', new_string='y')",
            observations="Ancien et nouveau IDENTIQUES : edit refusé.",
            tool_calls=None,
        )
        from graph_orchestrator.vision_callback import _build_edit_churn_nudge

        results = [_build_edit_churn_nudge(step) for _ in range(5)]
        assert results[:4] == [None, None, None, None]
        assert results[4] is not None and "CHURN D'ÉDITION" in results[4]
        assert 'status="failure"' in results[4]

    def test_edit_ambigu_non_compte(self):
        from graph_orchestrator.vision_callback import reset_edit_churn, _build_edit_churn_nudge

        reset_edit_churn()
        step = SimpleNamespace(
            code_action="search_replace(path='a', old_string='x', new_string='y')",
            observations="Out: quelque chose sans marqueur",
            tool_calls=None,
        )
        assert all(_build_edit_churn_nudge(step) is None for _ in range(10))

    def test_reset_par_noeud(self):
        from graph_orchestrator.vision_callback import reset_edit_churn, _build_edit_churn_nudge, _EDIT_CHURN_STATE

        reset_edit_churn()
        step = SimpleNamespace(
            code_action="multi_replace(path='a', replacements=[])",
            observations="chaîne introuvable — n'a pas été modifié.",
            tool_calls=None,
        )
        for _ in range(4):
            _build_edit_churn_nudge(step)
        reset_edit_churn()
        assert _build_edit_churn_nudge(step) is None  # repart de zéro


class TestVisionBudgetNudge:
    """8 cycles navigate/screenshot par tentative → conclus sur les preuves."""

    def _nudge(self, code: str):
        from graph_orchestrator.vision_callback import (
            _build_vision_budget_nudge,
            reset_vision_budget,
        )

        reset_vision_budget()
        step = SimpleNamespace(code_action=code, observations="img", tool_calls=None)
        return _build_vision_budget_nudge(step)

    def test_sans_outil_vision_pas_de_comptage(self):
        assert self._nudge("write_file('a', 'x')") is None

    def test_seuil_huit_declenche(self):
        from graph_orchestrator.vision_callback import reset_vision_budget, _build_vision_budget_nudge

        reset_vision_budget()
        step = SimpleNamespace(
            code_action="navigate_page(url='file://x.html')", observations="", tool_calls=None
        )
        results = [_build_vision_budget_nudge(step) for _ in range(13)]
        assert results[:7] == [None] * 7
        assert results[7] is not None and "BUDGET VISION ÉPUISÉ" in results[7]
        # pression graduée : re-fire à 12, pas à chaque step
        assert results[8:11] == [None] * 3
        assert results[11] is not None

    def test_comptage_via_code_action_multiple_appels(self):
        """Plusieurs appels vision dans UN step comptent chacun (via code_action —
        nos agents sont CodeAgent, tool_calls vaut python_interpreter : review
        Kilo PR #102)."""
        from graph_orchestrator.vision_callback import reset_vision_budget, _build_vision_budget_nudge

        reset_vision_budget()
        code = (
            "navigate_page(url='file://x.html')\n"
            "take_screenshot(format='jpeg')\n"
            "navigate_page(url='file://x.html')"
        )
        step = SimpleNamespace(code_action=code, observations="", tool_calls=None)
        # 3 appels/step : cumul 3, 6, 9 (muet), 12 → déclenche (n≥8, (n-8)%4==0)
        assert all(_build_vision_budget_nudge(step) is None for _ in range(3))
        nudge = _build_vision_budget_nudge(step)
        assert nudge is not None and "12 navigations/screenshots" in nudge
