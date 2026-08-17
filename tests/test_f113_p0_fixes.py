"""Tests des fixes P0 du post-mortem run #8 (F-113).

Deux causes racines prouvées par debug/POSTMORTEM_RUN8.md :

1. **Sauvetage Pydantic → port mort** : ``run_with_retry`` lisait
   ``getattr(agent_model, "api_base", None)`` — or
   ``smolagents.OpenAIServerModel`` n'assigne PAS ``self.api_base`` (seulement
   ``client_kwargs["base_url"]``) → None à chaque fois → le sauvetage tapait
   ``settings.local_api_base`` (port 8000, rien n'écoute en mode spawn) →
   ``Connection error`` déterministe 3/3 (serveurs dynamiques sains).
   Fix : propriété ``api_base`` sur ``LoggedOpenAIServerModel`` +
   ``_resolve_agent_api_base`` (fallback client_kwargs).

2. **Prune destructeur** : ``_prune_old_runs`` faisait
   ``shutil.rmtree(ignore_errors=True)`` → suppression PARTIELLE silencieuse
   multi-passes sous Windows (~290 runs/ éviscérés depuis le 3 août ; le run #8
   détruit 20 min après sa fin) + message « supprimé » imprimé sans vérifier.
   Fix : ``_rmtree_verified`` (retries + chmod read-only + vérification) +
   période de grâce + messages conditionnels.

3. **Pollution runs/ par les tests E2E** : 6 helpers construisaient
   ``Settings(...)`` sans ``output_dir`` → vrais dossiers sous ``runs/`` qui
   poussent les runs récents hors top-N de la rétention. Fix : output_dir
   isolé (tempfile.mkdtemp).
"""

import os
import time
from pathlib import Path

import pytest

from graph_orchestrator.nodes import LoggedOpenAIServerModel, _resolve_agent_api_base
from graph_orchestrator.workflows import _prune_old_runs, _rmtree_verified


# ==========================================
# Fix 1 — résolution api_base du sauvetage
# ==========================================
class TestResolveApiBase:
    def test_propriete_api_base_logged_model(self):
        """LA régression du run #8 : LoggedOpenAIServerModel DOIT exposer son
        vrai endpoint (le sauvetage Pydagnostic en dépend)."""
        m = LoggedOpenAIServerModel(
            model_id="test-m",
            api_base="http://127.0.0.1:61585/v1",
            api_key="k",
        )
        assert m.api_base == "http://127.0.0.1:61585/v1"

    def test_propriete_suivie_par_revive(self):
        """_between_attempts met client_kwargs['base_url'] à jour lors d'un
        revive — la propriété lit TOUJOURS la valeur courante (pas une copie)."""
        m = LoggedOpenAIServerModel(
            model_id="test-m", api_base="http://127.0.0.1:1/v1", api_key="k"
        )
        m.client_kwargs["base_url"] = "http://127.0.0.1:2/v1"
        assert m.api_base == "http://127.0.0.1:2/v1"

    def test_resolve_fallback_client_kwargs(self):
        """Un modèle NON-Logged (OpenAIServerModel nu) : pas d'attribut api_base
        mais client_kwargs['base_url'] → résolu (le fallback du run #8)."""

        class _BareModel:
            model_id = "m"
            client_kwargs = {"base_url": "http://127.0.0.1:9/v1", "max_retries": 0}

        assert _resolve_agent_api_base(_BareModel()) == "http://127.0.0.1:9/v1"

    def test_resolve_attribut_direct_prioritaire(self):
        class _AttrModel:
            api_base = "http://attr/v1"
            client_kwargs = {"base_url": "http://kwargs/v1"}

        assert _resolve_agent_api_base(_AttrModel()) == "http://attr/v1"

    def test_resolve_none_sans_rien(self):
        class _Empty:
            pass

        assert _resolve_agent_api_base(_Empty()) is None
        assert _resolve_agent_api_base(None) is None


# ==========================================
# Fix 2 — prune vérifié + grâce
# ==========================================
class TestRmtreeVerified:
    def test_suppression_normale(self, tmp_path: Path):
        d = tmp_path / "run_x"
        (d / ".git" / "objects").mkdir(parents=True)
        (d / ".git" / "objects" / "ab").mkdir()
        (d / ".git" / "objects" / "ab" / "cdef").write_bytes(b"x")
        (d / "index.html").write_text("<html></html>")
        assert _rmtree_verified(str(d)) is True
        assert not d.exists()

    def test_fichier_read_only_supprime(self, tmp_path: Path):
        """Pattern Windows du run #8 : blobs git en read-only → l'ancien
        rmtree(ignore_errors=True) abandonnait en silence ; le handler chmod
        doit permettre la suppression complète."""
        import stat

        d = tmp_path / "run_ro"
        (d / ".git" / "objects" / "ab").mkdir(parents=True)
        blob = d / ".git" / "objects" / "ab" / "cdef"
        blob.write_bytes(b"x")
        os.chmod(blob, stat.S_IREAD)
        assert _rmtree_verified(str(d)) is True
        assert not d.exists()

    def test_echec_avoue(self, tmp_path: Path, monkeypatch, capsys):
        """rmtree qui échoue obstinément → False (jamais 'vrai' par défaut),
        le dossier survit et l'appelant SAURA ne pas loguer 'supprimé'."""
        import shutil as _shutil

        d = tmp_path / "run_locked"
        d.mkdir()
        (d / "f.txt").write_text("x")

        def _always_fail(*a, **k):
            raise OSError("fichier verrouillé")

        monkeypatch.setattr(_shutil, "rmtree", _always_fail)
        assert _rmtree_verified(str(d), attempts=1) is False
        assert d.exists()  # survécu — et le retour le DIT


class TestPruneGrace:
    def _mk(self, root: Path, name: str, age_hours: float) -> Path:
        d = root / name
        d.mkdir(parents=True)
        (d / "f.txt").write_text("x")
        stamp = time.time() - age_hours * 3600
        os.utime(d, (stamp, stamp))
        return d

    def test_run_recent_protege_par_grace(self, tmp_path: Path, capsys):
        """Le run #8 : un dir RÉCENT hors top-N (poussé par des dirs de tests)
        ne doit PAS être supprimé — c'est la période de grâce."""
        # Le plus ancien (72h) sera hors top-N et éligible ; le récent (0.1h)
        # aussi hors top-N mais PROTÉGÉ par la grâce.
        for i in range(10):
            self._mk(tmp_path, f"old_{i:02d}", age_hours=48)
        self._mk(tmp_path, "ancien_hors_top", age_hours=72)
        recent = self._mk(tmp_path, "recent_hors_top", age_hours=0.1)

        _prune_old_runs(str(tmp_path), retention=10, grace_hours=6.0)
        out = capsys.readouterr().out
        assert recent.exists()  # protégé par la grâce
        assert "recent_hors_top" not in out  # jamais candidat → jamais logué
        assert "ancien_hors_top" in out  # le plus ancien, lui, est traité
        assert (tmp_path / "ancien_hors_top").exists() is False

    def test_message_supprime_seulement_si_disparu(self, tmp_path: Path, capsys, monkeypatch):
        """Jamais plus de « 🗑️ supprimé » pour un dir qui survit — le warning
        PRUNE PARTIEL remplace le mensonge silencieux du run #8."""
        import shutil as _shutil

        for i in range(12):
            self._mk(tmp_path, f"r_{i:02d}", age_hours=48)

        def _partial(path, onerror=None):
            # Simule l'échec verrouillé : ne supprime rien.
            raise OSError("verrou")

        monkeypatch.setattr(_shutil, "rmtree", _partial)
        _prune_old_runs(str(tmp_path), retention=10, grace_hours=6.0)
        out = capsys.readouterr().out
        assert "[🗑️]" not in out  # jamais de message de succès mensonger
        assert "PRUNE PARTIEL" in out

    def test_retention_zero_noop(self, tmp_path: Path):
        self._mk(tmp_path, "a", age_hours=48)
        _prune_old_runs(str(tmp_path), retention=0)
        assert (tmp_path / "a").exists()


# ==========================================
# Fix 3 — isolation output_dir des helpers E2E
# ==========================================
class TestE2EHelpersIsoles:
    """Les 6 helpers E2E qui polluaient le vrai runs/ (dirs _t1/_task1 par
    dizaines, poussant les runs récents hors rétention → destruction par
    prune). Chacun doit maintenant construire un output_dir TEMPORAIRE."""

    @pytest.mark.parametrize("module_name,helper", [
        ("tests.test_escalation", "_settings"),
        ("tests.test_checkpoint", "_settings"),
        ("tests.test_consolidation", "_settings"),
        ("tests.test_lesson_recall", "_settings"),
        ("tests.test_prompt_refiner", "_settings_full"),
        ("tests.test_feedback_integration", "_settings"),
    ])
    def test_output_dir_isole(self, module_name, helper):
        import importlib

        mod = importlib.import_module(module_name)
        settings = getattr(mod, helper)()
        assert settings.output_dir not in ("runs", "", None), (
            f"{module_name}.{helper} écrit dans le vrai runs/ ! "
            f"(output_dir={settings.output_dir!r})"
        )
        assert "e2e_runs_" in str(settings.output_dir)
