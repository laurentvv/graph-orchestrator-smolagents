# Tests Rapides par Nœud — Scripts d'Isolation (F-89)

> Extrait d'`AGENTS.md` §9 le 2026-09-01 (allègement du contexte de session : le tableau de
> correspondance script → nœud vit ICI, AGENTS.md ne garde que le principe et le renvoi).

Un run E2E complet dure 30-40 min GPU-local ; valider la modif d'UN seul nœud (prompt, skill, config, logique) se fait en **secondes/minutes** via le script d'isolation du dossier `debug/` : chacun appelle la VRAIE fonction de production (0 mock) avec des entrées figées. C'est la boucle de debug itérative recommandée, AVANT tout run E2E. Convention complète : `debug/isolation/README.md`.

| Script | Nœud testé | Commande |
|---|---|---|
| `debug/run_router.py` | Router (classification langage) | `uv run python debug/run_router.py` |
| `debug/run_prompt_refiner.py` | PromptRefiner (meta-prompt) | `uv run python debug/run_prompt_refiner.py` |
| `debug/run_architect.py` | Architect (découpage + stratégie) | `uv run python debug/run_architect.py` |
| `debug/run_drafter.py` | Drafter (logique pure) | `uv run python debug/run_drafter.py` |
| `debug/run_security.py` | Security (audit OWASP) | `uv run python debug/run_security.py` |
| `debug/run_judge.py` | Judge (verdict final) | `uv run python debug/run_judge.py` |
| `debug/run_coder.py` | Coder (génération code) | `uv run python debug/run_coder.py` |
| `debug/run_web_tester_standalone.py` | Web Tester (assertions) | `uv run python debug/run_web_tester_standalone.py` |
| `debug/isolation/run_linter.py` | Linter (déterministe, 0 LLM) | `uv run python debug/isolation/run_linter.py` |
| `debug/validate_static_tester_live.py` | Static Tester (déterministe) | `uv run python debug/validate_static_tester_live.py` |
| `debug/run_verify.py` | Vérif exécutable F-100 (recette + readiness HTTP, 0 LLM) | `uv run python debug/run_verify.py [dossier]` |
| `debug/run_turn_checkpoint.py` | Checkpoint git par itération F-102 (0 LLM) | `uv run python debug/run_turn_checkpoint.py` |
| `debug/run_fs_safety.py` | Robustesse FS F-95 (transaction+crash-recovery, verrou cross-process, 0 LLM) | `uv run python debug/run_fs_safety.py` |
| `debug/test_mtp_spec.py` | Compat/bench MTP spéculatif llama-server (A/B `--spec-type draft-mtp`, 0 LLM) | `uv run python debug/test_mtp_spec.py [--only fast\|reasoning\|no_think] [--ctx N]` |
| `debug/bench_prefill_flags.py` | Bench préfill flags FAST (`--cache-reuse`, `-ub`), multi-tours simulé (0 LLM) | `uv run python debug/bench_prefill_flags.py [--ctx N] [--turns N]` |
| `debug/diag_grammar_f160.py` / `replay_request_f160.py` / `trace_mcp_calls_f160.py` | F-160 : grammaire llama-server vs `tool_choice`, rejeu variants, trace appels MCP | `uv run python debug/<script>.py` |
| `debug/run_browser_pool.py` | Pool navigateur F-163 (Chrome unique/run, 0 LLM) | `uv run python debug/run_browser_pool.py` |

Boucle : identifier le nœud impacté → lancer son script → observer le verdict → couper si erreur, corriger, relancer. Input ad hoc : scénario nommé (`debug/run_judge.py bug`), prompt en CLI (`debug/run_router.py "ma description"`), ou `@fichier`. Une fois le nœud validé isolément, relancer l'E2E complet (AGENTS.md §7).

Détail technique : les nœuds DSPy ignorent le paramètre `*_model` — le vrai modèle vient de `_run_dspy_node → model_lifecycle(spec)` qui spawn son propre llama-server ; les scripts reproduisent fidèlement ce comportement.
