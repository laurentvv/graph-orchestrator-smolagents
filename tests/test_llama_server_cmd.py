"""Tests des flags llama-server MTP/KV-quant (ModelSpec env + construction de commande).

Bench de référence debug/test_mtp_spec.py (2026-08-17) : +29% sur Ornith-9B @ctx32k
avec spec-mtp + KV q8_0, régression -42% sur Qwen-4B → les flags sont opt-in par rôle.
"""

from graph_orchestrator.config import _model_spec_from_env
from graph_orchestrator.llama_server import _build_cmd


def _spec(**kwargs):
    """ModelSpec minimal de rôle spawn pour les tests de _build_cmd."""
    from graph_orchestrator.config import ModelSpec
    defaults = dict(backend="spawn", model="fake.gguf", reasoning="on",
                    context=32768, gpu_layers=99)
    defaults.update(kwargs)
    return ModelSpec(**defaults)


class TestModelSpecEnv:
    """Parsing <PREFIX>_SPEC_MTP / <PREFIX>_KV_QUANT (défauts opt-in)."""

    def test_defauts_desactives(self, monkeypatch):
        monkeypatch.delenv("REASONING_SPEC_MTP", raising=False)
        monkeypatch.delenv("REASONING_KV_QUANT", raising=False)
        spec = _model_spec_from_env("REASONING")
        assert spec.spec_mtp is False
        assert spec.kv_quant == ""

    def test_activation_env(self, monkeypatch):
        monkeypatch.setenv("REASONING_SPEC_MTP", "true")
        monkeypatch.setenv("REASONING_KV_QUANT", "Q8_0")  # normalisé lowercase
        spec = _model_spec_from_env("REASONING")
        assert spec.spec_mtp is True
        assert spec.kv_quant == "q8_0"


class TestBuildCmd:
    """_build_cmd : flags production de base + flags MTP/KV conditionnels."""

    def test_base_sans_mtp(self):
        cmd = _build_cmd(_spec(), port=1234)
        assert "--parallel" in cmd and cmd[cmd.index("--parallel") + 1] == "1"
        # -ngl : flag court (un seul tiret), pas --ngl.
        assert "-ngl" in cmd and cmd[cmd.index("-ngl") + 1] == "99"
        assert "--spec-type" not in cmd
        assert "--cache-type-k" not in cmd

    def test_mtp_seul_defaut_q8_draft(self):
        cmd = _build_cmd(_spec(spec_mtp=True), port=1234)
        # --spec-default (ngram-mod) VOLONTAIREMENT exclu : bench dégradé (24,1 vs
        # 25,6 t/s) + issue #24266. n-max 2 optimal sur le 9B dense (27,5 t/s).
        assert "--spec-default" not in cmd
        assert cmd[cmd.index("--spec-type") + 1] == "draft-mtp"
        assert cmd[cmd.index("--spec-draft-n-max") + 1] == "2"
        # Sans kv_quant, le KV du draft quantize quand même en q8_0 (défaut bench).
        assert cmd[cmd.index("--spec-draft-type-k") + 1] == "q8_0"
        # Le KV principal reste f16 si kv_quant vide.
        assert "--cache-type-k" not in cmd

    def test_mtp_plus_kv_quant(self):
        cmd = _build_cmd(_spec(spec_mtp=True, kv_quant="q8_0"), port=1234)
        assert cmd[cmd.index("--cache-type-k") + 1] == "q8_0"
        assert cmd[cmd.index("--cache-type-v") + 1] == "q8_0"

    def test_kv_quant_seul(self):
        cmd = _build_cmd(_spec(kv_quant="q8_0"), port=1234)
        assert "--spec-type" not in cmd
        assert cmd[cmd.index("--cache-type-k") + 1] == "q8_0"

    def test_cache_reuse(self):
        cmd = _build_cmd(_spec(cache_reuse=256), port=1234)
        assert cmd[cmd.index("--cache-reuse") + 1] == "256"
        assert "--cache-reuse" not in _build_cmd(_spec(), port=1234)

    def test_sampling_qwen(self):
        cmd = _build_cmd(_spec(top_k=20, min_p=0.0), port=1234)
        assert cmd[cmd.index("--top-k") + 1] == "20"
        assert cmd[cmd.index("--min-p") + 1] == "0.0"
        # Défauts : aucun flag sampling passé (défauts serveur).
        cmd0 = _build_cmd(_spec(), port=1234)
        assert "--top-k" not in cmd0 and "--min-p" not in cmd0
