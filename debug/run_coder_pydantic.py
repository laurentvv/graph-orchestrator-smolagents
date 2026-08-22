"""Spike F-157 phase 2 : nœud Coder pydantic-ai-harness en isolation (A/B vs run_coder.py).

Valide le scénario S1 de la migration (docs/ANALYSE_MIGRATION_HARNESS_CODAGE.md §7) :
un Coder minimal monté sur pydantic-ai-harness (FileSystem + CodeMode + limites de
contexte) produit-il le livrable Bubble Sort multi-fichiers avec le Qwen 3.5 4B local ?

Différences assumées vs le Coder production (smolagents) — périmètre SPIKE :
  - pas de MCP chrome-devtools (pas de screenshots/visual_check)  → phase 3 si GO ;
  - pas de gardes LoopGuard/StallDetector/GoalEnforcer            → phase 3 si GO ;
  - pas de prefill assistant (protocole différent : CodeMode = code dans un
    tool-call run_code, le prefill markdown ```python n'a pas de sens ici) ;
  - sortie = fichiers sur disque (pas de CoderOutput structuré)   → mesuré en phase 3.

Mesures GO/NO-GO (analyse §7-S1) :
  - tool-calls run_code bien formés (échecs/parse errors comptés dans l'historique) ;
  - livrable conforme : 3 fichiers non vides + câblage index.html → styles.css/script.js ;
  - pas de boucle d'édition stérile (nombre de run_code borné) ;
  - tokens & durée vs baseline smolagents (coder_isolation_out / runs de référence).

Usage :
    uv run python debug/run_coder_pydantic.py            # tâche Bubble Sort par défaut
    uv run python debug/run_coder_pydantic.py @spec.md   # spec personnalisée
"""
import argparse
import os
import shutil
import sys
import time

from dotenv import load_dotenv

load_dotenv()

# 🔒 DOSSIER DE SORTIE HARDCODÉ — isolation stricte (nettoyé à chaque run).
OUT_DIR = "debug/coder_pydantic_out"

DEFAULT_TARGET_FILES = ["index.html", "styles.css", "script.js"]

# Même tâche que debug/run_coder.py (comparaison A/B honnête).
DEFAULT_TASK = (
    "Crée un visualiseur d'algorithme Bubble Sort (tri à bulles) interactif en "
    "HTML/CSS/JS vanilla, réparti sur TROIS fichiers séparés : index.html (structure "
    "+ lien vers le CSS et le JS), styles.css (tout le style), script.js (toute la "
    "logique). Pas de framework ni de CDN externe.\n\n"
    "L'interface doit montrer un tableau de barres verticales (hauteurs proportionnelles "
    "aux valeurs) qui s'animent pendant le tri. Fonctionnalités attendues :\n"
    "- un bouton « Démarrer le tri » qui lance l'animation pas-à-pas de Bubble Sort "
    "avec un délai visible entre chaque comparaison/échange ;\n"
    "- un bouton « Réinitialiser » qui génère un nouveau tableau aléatoire ;\n"
    "- un curseur/slidebar pour régler la vitesse d'animation ;\n"
    "- un compteur affichant le nombre de comparaisons effectuées ;\n"
    "- un code couleur clair : barre en cours de comparaison = une couleur, barre déjà "
    "triée = une autre couleur, barres non encore traitées = couleur par défaut.\n\n"
    "Contraintes techniques : index.html doit référencer styles.css via <link> et "
    "script.js via <script src>. Le JS accède au DOM via les ids définis dans le HTML. "
    "Design soigné, responsive, avec un thème sombre (dark mode)."
)

# Round 3 (défaut) : TOOLS NATIFS — le 4B appelle write_file/edit_file directement
# comme tool-calls (prouvé OK par debug/pydantic_smoke_provider.py tests C/D).
# Round 2 (--codemode) : CodeMode — NO-GO constaté : le 4B écrit `with open(...)`
# au lieu d'appeler les tools pliés dans le sandbox Monty, et régénère le même
# programme à l'identique malgré 6 retries (log spike_pydantic_round2.log).
PROTOCOL_NATIVE = """### SPIKE PROTOCOL (native tool calls)
- Call your tools DIRECTLY as tool calls: read_file, write_file, edit_file,
  list_directory, search_files, find_files, create_directory, file_info.
  Exact signatures are in each tool's description — do NOT invent parameters.
- For each new file: ONE write_file call with the COMPLETE final content
  (never elide, never placeholders, no comments like "rest of the code here").
- Batch independent tool calls in the same turn when possible.
- NEVER try to write files via Python code (no open(), no os.) — only the tools.
- STOP CONDITION: as soon as the target files are written, answer with a SHORT
  final summary (files written, key choices) and NO more tool calls. Do not loop."""

PROTOCOL_CODEMODE = """### SPIKE PROTOCOL (pydantic-ai-harness CodeMode)
- Your tools are available INSIDE the `run_code` sandbox: write ONE Python program per
  turn that calls them with the EXACT names and signatures from your run_code tool
  catalog (do NOT invent tool names). Batch ALL file creations in a single program.
- Inside the sandbox: PLAIN simple Python only — no imports, no f-strings, no
  try/except, no fancy comprehensions, and NEVER open()/file I/O: ALWAYS call the
  provided tool functions (write_file(...), edit_file(...)) instead.
- For a full new file, use the write tool with the COMPLETE content (never elide,
  never placeholders). To modify a fragment, use the edit tool.
- STOP CONDITION: as soon as the target files are written, answer with a SHORT final
  summary (files written, key choices) and NO more tool calls. Do not loop."""


def _resolve_arg(arg: str) -> str:
    if not arg:
        return arg
    if arg.startswith("@"):
        with open(arg[1:], "r", encoding="utf-8") as f:
            return f.read().strip()
    if os.path.isfile(arg):
        with open(arg, "r", encoding="utf-8") as f:
            return f.read().strip()
    return arg


def _reset_out_dir() -> None:
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.makedirs(OUT_DIR, exist_ok=True)


def _build_instructions(target_files: list[str], codemode: bool = False) -> str:
    from graph_orchestrator.prompts import ROLE_BLOCKS, UNIVERSAL_INVARIANTS

    files_block = (
        "### TARGET FILES (exact deliverable)\n"
        + "\n".join(f"- `{f}`" for f in target_files)
        + "\nAll paths are RELATIVE to the current working directory (your workspace root)."
    )
    return "\n\n".join([
        ROLE_BLOCKS["coder"],
        ROLE_BLOCKS.get("coder_frontend", ""),
        UNIVERSAL_INVARIANTS,
        PROTOCOL_CODEMODE if codemode else PROTOCOL_NATIVE,
        files_block,
    ])


def _message_metrics(messages) -> dict:
    """Compte tool-calls run_code, retours et erreurs de parse/validate dans l'historique."""
    from pydantic_ai.messages import RetryPromptPart, ToolCallPart, ToolReturnPart

    run_calls, other_calls, returns, retry_prompts = 0, 0, 0, 0
    first_call_args = None
    for msg in messages:
        for part in getattr(msg, "parts", []):
            if isinstance(part, ToolCallPart):
                if part.tool_name == "run_code":
                    run_calls += 1
                    if first_call_args is None:
                        first_call_args = str(part.args)[:400]
                else:
                    other_calls += 1
            elif isinstance(part, ToolReturnPart):
                returns += 1
            elif isinstance(part, RetryPromptPart):
                retry_prompts += 1
    return {
        "run_code_calls": run_calls,
        "other_tool_calls": other_calls,
        "total_calls": run_calls + other_calls,
        "tool_returns": returns,
        "retry_prompts": retry_prompts,
        "first_call_args": first_call_args,
    }


def _check_deliverable(out_dir: str) -> list[tuple[str, bool, str]]:
    """Contrôles livrable : existence, taille, câblage index.html, invariants JS clés."""
    checks: list[tuple[str, bool, str]] = []
    contents: dict[str, str] = {}
    for fname in DEFAULT_TARGET_FILES:
        path = os.path.join(out_dir, fname)
        ok = os.path.isfile(path) and os.path.getsize(path) > 100
        checks.append((f"fichier {fname}", ok, f"{os.path.getsize(path) if os.path.exists(path) else 0} octets"))
        if ok:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                contents[fname] = f.read()
    idx = contents.get("index.html", "")
    js = contents.get("script.js", "")
    checks.append(("index.html référence styles.css", "styles.css" in idx, ""))
    checks.append(("index.html référence script.js", "script.js" in idx, ""))
    checks.append(("JS init robuste (readyState/DOMContentLoaded)",
                   ("readyState" in js or "DOMContentLoaded" in js), ""))
    checks.append(("JS strict mode", "'use strict'" in js or '"use strict"' in js, ""))
    checks.append(("aucun placeholder TODO/…", not any(
        m in c for c in contents.values() for m in ("TODO", "...:</", "PLACEHOLDER")), ""))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Spike Coder pydantic-ai-harness (F-157 ph.2)")
    parser.add_argument("task", nargs="?", default=None, help="Tâche (ou @fichier)")
    parser.add_argument("--codemode", action="store_true",
                        help="Force CodeMode (round 2, NO-GO) au lieu des tools natifs (round 3)")
    args = parser.parse_args()
    task_desc = _resolve_arg(args.task) if args.task else DEFAULT_TASK

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    _reset_out_dir()

    from graph_orchestrator.config import settings
    from graph_orchestrator.llama_server import model_lifecycle

    print("[*] Spike Coder pydantic-ai-harness — F-157 phase 2")
    print(f"    Sortie isolée  : {os.path.abspath(OUT_DIR)}")
    print(f"    Modèle FAST    : {settings.fast_spec.model}")
    print(f"    tempér.        : {settings.coder_temperature} | max_tokens : {settings.fast_max_tokens}")
    print()

    from pydantic_ai import Agent, ModelSettings
    from pydantic_ai.models.openai import OpenAIChatModel, OpenAIModelProfile
    from pydantic_ai.providers.openai import OpenAIProvider
    from pydantic_ai.usage import UsageLimits
    from pydantic_ai_harness import ClearToolResults, CodeMode, FileSystem, ToolOutputLimits

    original_cwd = os.getcwd()
    os.chdir(OUT_DIR)
    t0 = time.time()
    result = None
    crash: Exception | None = None
    try:
        with model_lifecycle(settings.fast_spec) as srv:
            if not srv.api_base:
                print("[!] Échec du spawn llama-server — abandon.")
                return 2

            profile = OpenAIModelProfile(
                openai_supports_strict_tool_definition=False,
                openai_chat_supports_multiple_system_messages=False,
                openai_chat_supports_max_completion_tokens=False,
            )
            model = OpenAIChatModel(
                srv.model_id,
                provider=OpenAIProvider(base_url=srv.api_base, api_key=srv.api_key),
                profile=profile,
            )
            agent = Agent(
                model,
                instructions=_build_instructions(DEFAULT_TARGET_FILES, codemode=args.codemode),
                capabilities=[
                    FileSystem("."),
                    # Round 3 (défaut) : tools natifs, pas de CodeMode. Round 2
                    # (--codemode) : 6 retries conservés pour reproduction.
                    *([CodeMode(max_retries=6)] if args.codemode else []),
                    ToolOutputLimits(),
                    ClearToolResults(max_fraction=0.7),
                ],
                model_settings=ModelSettings(
                    temperature=settings.coder_temperature,
                    max_tokens=settings.fast_max_tokens,
                    timeout=settings.llm_timeout_s,
                ),
            )
            print(f"[*] llama-server prêt : {srv.api_base} — run du Coder…\n")

            # Itération instrumentée : chaque node → dump live des tool calls /
            # retours / retries (diagnostic round 1 : les détails étaient perdus).
            import asyncio

            async def _run() -> None:
                nonlocal result
                from pydantic_ai.messages import RetryPromptPart, ToolCallPart, ToolReturnPart

                async with agent.iter(
                    task_desc,
                    usage_limits=UsageLimits(request_limit=40, tool_calls_limit=120),
                ) as run:
                    async for node in run:
                        if not agent.is_call_tools_node(node):
                            continue
                        for msg in run.new_messages():
                            for part in getattr(msg, "parts", []):
                                if isinstance(part, ToolCallPart):
                                    print(f"\n[CALL] {part.tool_name} args={str(part.args)[:700]}")
                                elif isinstance(part, ToolReturnPart):
                                    print(f"[RET ] {part.tool_name} -> {str(part.content)[:400]}")
                                elif isinstance(part, RetryPromptPart):
                                    print(f"[RETRY] {str(part.content)[:400]}")
                        sys.stdout.flush()
                    result = run.result

            try:
                asyncio.run(_run())
            except Exception as exc:  # noqa: BLE001 — diagnostic du spike
                crash = exc
                print(f"\n[!] CRASH du run : {type(exc).__name__}: {exc}")
    finally:
        os.chdir(original_cwd)
    duration = time.time() - t0

    # ---- Métriques -----------------------------------------------------------
    if result is not None:
        metrics = _message_metrics(result.all_messages())
        usage = result.usage
    else:
        metrics = {"run_code_calls": -1, "other_tool_calls": -1, "total_calls": -1,
                   "tool_returns": -1, "retry_prompts": -1, "first_call_args": None}
        usage = None

    print("\n" + "=" * 60)
    print("RÉSULTAT DU SPIKE — pydantic-ai-harness Coder")
    print("=" * 60)
    if result is not None:
        print(f"Réponse finale (600 c.) : {str(result.output)[:600]}")
    else:
        print(f"Run terminé sur exception : {type(crash).__name__}")
    print("-" * 60)
    print("Métriques protocole :")
    print(f"  run_code calls      : {metrics['run_code_calls']}")
    print(f"  other tool calls    : {metrics['other_tool_calls']}")
    print(f"  tool returns        : {metrics['tool_returns']}")
    print(f"  retry prompts       : {metrics['retry_prompts']}  (parse/validate échoués)")
    if metrics["first_call_args"]:
        print(f"  1er run_code (400 c.): {metrics['first_call_args']}")
    if usage is not None:
        print(f"  requests LLM        : {usage.requests}")
        print(f"  tokens in/out       : {usage.input_tokens} / {usage.output_tokens}")
    print(f"  durée               : {duration:.1f}s")
    print("-" * 60)
    print("Livrable :")
    ok_count = 0
    for name, ok, detail in _check_deliverable(OUT_DIR):
        print(f"  [{'✓' if ok else '✗'}] {name} {detail}")
        ok_count += ok
    total = len(DEFAULT_TARGET_FILES) + 5
    print("-" * 60)
    verdict = (
        "GO"
        if result is not None
        and ok_count == total
        and metrics["total_calls"] <= 25
        and metrics["retry_prompts"] <= 4
        else "NO-GO"
    )
    print(f"VERDICT SPIKE : {verdict} ({ok_count}/{total} contrôles livrable, "
          f"{metrics['total_calls']} tool calls, {metrics['retry_prompts']} retries)")
    print("=" * 60)
    return 0 if verdict == "GO" else 1


if __name__ == "__main__":
    sys.exit(main())
