"""Smoke test provider pydantic-ai × llama-server (phase 1 du spike F-157).

Valide le chemin critique identifié dans l'analyse de migration
(docs/ANALYSE_MIGRATION_HARNESS_CODAGE.md §4.4) AVANT tout portage :
l'endpoint OpenAI-compatible de llama-server (spawné par model_lifecycle,
comme en production) est-il consommable par pydantic-ai OpenAIChatModel,
avec tool-calling natif (templates Hermes de Qwen 3.5, flag --jinja) ?

Tests (chacun PASS/FAIL, coupe au premier échec bloquant) :
  A. Chat simple, profil OpenAI par défaut      → détecte les params rejetés
     (max_completion_tokens, strict tool defs, etc. — cf. issue pydantic#4878).
  B. Chat simple, profil conservateur llama.cpp → flags OpenAIModelProfile.
  C. Tool-calling natif (1 tool trivial)        → le protocole JSON passe-t-il ?
  D. Tool-calling + sortie structurée Pydantic  → output_type validé.

Usage :
    uv run python debug/pydantic_smoke_provider.py

0 LLM de raisonnement, 0 MCP — juste le fast model spawné (~30 s de démarrage
llama-server). Écrit uniquement dans les logs console.
"""
import sys

from dotenv import load_dotenv

load_dotenv()


def _utf8() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass


def build_model(api_base: str, api_key: str, model_id: str, conservative: bool):
    """OpenAIChatModel vers llama-server ; conservative=True applique les flags
    de compat documentés pour les endpoints OpenAI-compatibles exotiques."""
    from pydantic_ai.models.openai import OpenAIChatModel, OpenAIModelProfile
    from pydantic_ai.providers.openai import OpenAIProvider

    provider = OpenAIProvider(base_url=api_base, api_key=api_key)
    if not conservative:
        return OpenAIChatModel(model_id, provider=provider)
    profile = OpenAIModelProfile(
        # llama-server : schémas d'outils non stricts, pas de param Responses,
        # un seul message système (chat template appliqué côté serveur),
        # max_tokens (pas max_completion_tokens).
        openai_supports_strict_tool_definition=False,
        openai_chat_supports_multiple_system_messages=False,
        openai_chat_supports_max_completion_tokens=False,
    )
    return OpenAIChatModel(model_id, provider=provider, profile=profile)


def main() -> int:
    _utf8()
    from graph_orchestrator.config import settings
    from graph_orchestrator.llama_server import model_lifecycle

    results: list[tuple[str, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, "PASS" if ok else "FAIL"))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    print("[*] Smoke test provider pydantic-ai × llama-server (F-157 phase 1)")
    print(f"    fast_spec : {settings.fast_spec.model} (backend={settings.fast_spec.backend})")
    print()

    with model_lifecycle(settings.fast_spec) as srv:
        if not srv.api_base:
            print("[!] Échec du spawn llama-server — abandon.")
            return 2
        print(f"[*] llama-server prêt : {srv.api_base} (model={srv.model_id})")
        base, key, mid = srv.api_base, srv.api_key, srv.model_id

        # --- Test A : chat simple, profil par défaut -------------------------
        from pydantic_ai import Agent

        print("[Test A] Chat simple — profil OpenAI par défaut")
        try:
            agent = Agent(build_model(base, key, mid, conservative=False),
                          instructions="Réponds en français, de façon très brève.")
            result = agent.run_sync("Réponds exactement : OK")
            out = result.output
            record("A. chat round-trip (profil défaut)", bool(out and str(out).strip()),
                   f"output={str(out)[:60]!r} usage={result.usage.input_tokens}/"
                   f"{result.usage.output_tokens} tok")
        except Exception as exc:  # noqa: BLE001 — diagnostic volontairement large
            record("A. chat round-trip (profil défaut)", False, f"{type(exc).__name__}: {exc}")
            print("    → bascule immédiate sur le profil conservateur (tests B-D).")

        # --- Test B : chat simple, profil conservateur llama.cpp -------------
        print("[Test B] Chat simple — profil conservateur (flags llama.cpp)")
        conservative_works = False
        try:
            agent = Agent(build_model(base, key, mid, conservative=True),
                          instructions="Réponds en français, de façon très brève.")
            result = agent.run_sync("Réponds exactement : OK")
            conservative_works = bool(result.output and str(result.output).strip())
            record("B. chat round-trip (profil conservateur)", conservative_works,
                   f"output={str(result.output)[:60]!r}")
        except Exception as exc:  # noqa: BLE001
            record("B. chat round-trip (profil conservateur)", False,
                   f"{type(exc).__name__}: {exc}")

        # --- Test C : tool-calling natif --------------------------------------
        print("[Test C] Tool-calling natif (tool_plain, JSON Hermes)")
        try:
            agent = Agent(build_model(base, key, mid, conservative=True),
                          instructions="Utilise TOUJOURS l'outil disponible pour répondre.")

            @agent.tool_plain
            def get_weather(city: str) -> str:
                """Retourne la météo fictive d'une ville."""
                return f"{city}: 21°C, ensoleillé"

            result = agent.run_sync("Quelle est la météo à Lyon ? (utilise l'outil)")
            ok = "21" in str(result.output)
            record("C. tool-calling + résultat", ok,
                   f"output={str(result.output)[:60]!r} requests={result.usage.requests}")
        except Exception as exc:  # noqa: BLE001
            record("C. tool-calling + résultat", False, f"{type(exc).__name__}: {exc}")

        # --- Test D : sortie structurée Pydantic ------------------------------
        print("[Test D] Sortie structurée output_type (validation + retry)")
        try:
            from pydantic import BaseModel

            class Verdict(BaseModel):
                city: str
                temperature_c: int

            agent = Agent(build_model(base, key, mid, conservative=True),
                          instructions="Utilise l'outil puis réponds via le format de sortie.",
                          output_type=Verdict)

            @agent.tool_plain
            def get_weather2(city: str) -> str:
                """Retourne la météo fictive d'une ville (température en chiffres)."""
                return f"{city}: 21°C, ensoleillé"

            result = agent.run_sync("Météo à Lyon ? (utilise l'outil)")
            ok = isinstance(result.output, Verdict) and result.output.temperature_c == 21
            record("D. output_type Pydantic", ok, f"output={result.output!r}")
        except Exception as exc:  # noqa: BLE001
            record("D. output_type Pydantic", False, f"{type(exc).__name__}: {exc}")

    # --- Bilan ---------------------------------------------------------------
    print()
    fails = [n for n, s in results if s == "FAIL"]
    print("=" * 60)
    if not fails:
        print("SMOKE TEST : 100% PASS — le chemin critique llama-server × pydantic-ai")
        print("est OUVERT. Phase 2 (spike Coder) débloquée.")
        rc = 0
    elif all(s == "FAIL" for _, s in results):
        print("SMOKE TEST : 100% FAIL — chemin critique BLOQUUÉ (issue pydantic#4878 ?).")
        print("→ Basculer sur le plan B (boucle waku-agent, analyse §7-S2).")
        rc = 2
    else:
        print(f"SMOKE TEST : {len(fails)} échec(s) partiel(s) : {fails}")
        print("→ Diagnostiquer les cas FAIL avant la phase 2 (flags profil, timeout…).")
        rc = 1
    print("=" * 60)
    return rc


if __name__ == "__main__":
    sys.exit(main())
