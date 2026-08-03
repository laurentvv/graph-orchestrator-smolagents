# 21 — davidondrej-skills

## En-tête
- **Nom** : davidondrej-skills (Agent Skills de David Ondrej, standard agentskills.io)
- **Chemin** : `references/davidondrej-skills/`
- **Type** : Collection de ~49 « Agent Skills » (standard agentskills.io) **+ un sous-système de hooks de sécurité cross-agent** (la partie intéressante pour P8)
- **Langage principal** : Markdown (`SKILL.md` + YAML frontmatter) + `.yaml` (`agents/openai.yaml` pour Codex) + `.sh` (hooks POSIX bash). **Aucun Python, aucun JS applicatif.**
- **Statistiques** : 75 fichiers hors `.git/` (52 `.md`, 17 `.yaml`, 3 `.sh`, 1 `.txt`). Cible native : Claude Code / Codex / Cursor / Pi / Hermes / Grok / Droid / Devin (écosystème multi-agent).
- **Organisation** : 5 catégories sous `skills/` — `agent-orchestration/` (13 skills), `ops-and-setup/` (10), `research-and-web/` (8), `skill-authoring/` (4), `thinking-and-docs/` (14) ; plus `hooks/` (3 fichiers).

## Synthèse
La valeur réelle pour le projet cible est **concentrée sur P8** (middlewares anti-crash). Le dossier `hooks/` est un cas d'école de **denylist anti-crash bien conçue** : POSIX-ERE, fail-open propre, tests exhaustifs (~115 cas). Le reste est une bibliothèque de prompts/procédures en anglais, fortement orientée macOS et outils SaaS commerciaux (OpenAI Codex, Cursor, Fable, ChatGPT subscription) — peu réutilisable tel quel dans un orchestrateur Python.

**Réserves importantes** :
- ⚠️ **Correction de la procédure** (Annexe D cite « 52 regex ») : c'est **faux**. Le fichier `dangerous-patterns.txt` fait **52 lignes au total** mais ne contient que **27 patterns regex effectifs** (15 lignes de commentaires `#` + 10 lignes vides + 27 regex = 52 lignes). La procédure a confondu « lignes du fichier » et « nombre de regex ». À corriger dans le plan P8.
- **Aucune logique en Python** : tout est bash + `jq` + JSON. Pour smolagents/DSPy, il faut **réimplémenter** le moteur (lire les patterns, les compiler en `re`, matcher la commande de l'outil `Bash`). Le fichier `.txt` est portable ; les scripts `.sh` ne le sont pas directement.
- **Couverture limitée à bash/macOS** : rien pour `Write`/`Edit` sur fichiers système, rien pour les commandes Windows, rien pour l'injection via Python (`python -c "shutil.rmtree(...)"` est explicitement reconnu comme échappatoire dans `global-agent-guardrails`).
- Nous avons déjà un `bash_guard.py` (F-38) ; davidondrej l'**enrichit** (patterns supplémentaires + doctrine fail-open) plutôt qu'il ne le remplace.

Note globale : **🟡 Moyenne**. Excellent sur le périmètre P8 (denylist + doctrine), faible ailleurs pour ce projet. Le complément parfait de notre F-38 (`bash_guard.py`) : 27 patterns POSIX-ERE testés + doctrine fail-open + suite de tests déjà écrite.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/davidondrej-skills/skills/ops-and-setup/global-agent-guardrails/SKILL.md` | **Doctrine companion de la denylist** : « block only irreversible/catastrophic commands, allow local-destructive-but-recoverable ». Table de wiring par agent (9 agents). Recette E2E de vérification. Contient les gotchas (Codex hash-pinning, Cursor `failClosed=false`, classes de faux positifs). | Haute |
| `references/davidondrej-skills/README.md` | Présentation des 5 catégories de skills + hooks | Faible |
| `references/davidondrej-skills/skills/skill-authoring/effective-agent-skills/SKILL.md` | Doctrine d'authoring de skills (13 sections : progressive disclosure, anatomy SKILL.md, Pattern A/B, anti-patterns, ship/security checklist). Référence P10 (cf. fiche 23 fusion doctrine). | Moyenne |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/davidondrej-skills/hooks/dangerous-patterns.txt` | **27 regex POSIX-ERE** (une par ligne ; commentaires `#` et lignes vides ignorés). Format documenté en header du fichier. 9 catégories numérotées. | **Denylist de commandes bash destructrices** : `rm -rf /`/`~`/`/Users` (6 patterns), `--no-preserve-root`, `dd … of=/dev/`, `mkfs`, `diskutil erase*`, `sudo rm`, fork bomb `:(){ :\|:& };:`, `curl\|sh`, `git push --force`/`--delete`/`+branch`/`:branch`, `chmod 777 /`, `chown -R /`, `git reflog expire --expire=now`, `git gc --prune=now\|all`, `gh repo/release/secret/ssh-key/gpg-key delete`, `gh api -X DELETE`, `gh repo edit --visibility public`, `gh auth token`. | **Haute** | Réutiliser le fichier `.txt` tel quel (portable). Pour Python : transpiler `[:space:]`→`\s` (`.replace("[:space:]", r"\s")`), compiler en `re`. Enrichit notre F-38 (`bash_guard.py`) de patterns manquants (gh delete, fork bomb, curl\|sh, reflog expire) |
| `references/davidondrej-skills/hooks/deny-dangerous.sh` | `jq` extrait la commande depuis `.tool_input.command` / `.toolInput.command` / `.command`. Boucle `while read` + `grep -qE`. **Fail-open** si `jq` absent ou patterns manquants. Modes `exitcode` (exit 2 + stderr) ou `cursor` (JSON `{"permission":"deny"}` stdout, exit 0). | **Moteur de garde PreToolUse.** Design sane : fail-open pour ne pas casser les agents, mais rejet explicite avec explication citant le pattern matché. | **Haute** | Réimplémenter en middleware Python (notre `bash_guard.py` fait déjà le `check_bash_command` ; s'inspirer du **fail-open** + **message explicite citant le pattern**). Le contrat exit-2/JSON-Cursor n'a pas d'équivalent smolagents — adapter |
| `references/davidondrej-skills/hooks/test-guard.sh` | 2× ~75 cas `check block\|allow <cmd>`, exécutés sur les deux shapes de payload (Claude/Codex exit-code + Cursor JSON). Affiche `passed: N, failed: M`, exit 1 si échec. | **Suite de tests** (~115 cas au total : ~75 block + ~40 allow). Très bien couverte : tous les patterns + faux positifs (`rm -rf node_modules` doit passer, `git push --force-with-lease` doit passer). | **Haute** | Porter en tests pytest paramétrés (~115 cas déjà écrits verbatim dans le fichier — gain net). À merger dans `tests/test_bash_guard.py` existant |
| `references/davidondrej-skills/skills/skill-authoring/effective-agent-skills/SKILL.md` | Sections 1-13 : progressive disclosure (3 niveaux), anatomy SKILL.md, Pattern A (capability primitives / wrappers CLI) vs Pattern B (process primitives / disciplines), anti-patterns, ship checklist, security checklist. | Doctrine d'authoring de skills — LE guide pour écrire un `SKILL.md`. | Moyenne | P10 (cf. fiche 23 fusion doctrine avec awesome-claude-skills + mattpocock) |
| `references/davidondrej-skills/skills/agent-orchestration/goal-loop/SKILL.md` | 5-part contract : Objective / Constraints / Validation command / Stop condition / Documentation. États lifecycle `pursuing/paused/achieved/unmet/budget-limited`. Interdiction explicite du reward-hacking (« Do not delete, skip, weaken tests »). | Doctrine de boucle auto-contrôlée avec stop condition vérifiable. Alignée avec l'idée d'un orchestrateur qui boucle. | Moyenne | P3 connexe (stop condition vérifiable) + anti-reward-hacking |
| `references/davidondrej-skills/skills/agent-orchestration/handoff/SKILL.md` | `disable-model-invocation: true`. Template de handoff structuré (Goal / Current State / Decisions / Traps & Dead Ends / Files & Pointers / Open Work / Prompt for Fresh Agent). Principes : « State, not instructions », « Capture the why », « Trust nothing blindly ». | Procédure de transmission de contexte entre sessions/agents. | Faible | Conceptuellement utile (persistance inter-agent DuckDB) mais le format « fenced code block à copier-coller » ne se porte pas |

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/davidondrej-skills/hooks/dangerous-patterns.txt` | spec (regex) | **Les 27 regex POSIX-ERE** — la matière première portable. Format : une regex par ligne, `#` = commentaire, lignes vides ignorées, header documente les 9 catégories |

### Exemples verbatim de patterns (sur 27)
Pour donner la saveur du format (POSIX-ERE avec `[:space:]`, jamais `\s` car les adaptateurs convertissent) :
```
(^|[;&|[:space:]])rm[[:space:]]+((-[a-zA-Z]+|--[a-z-]+)[[:space:]]+)*["']?/["']?[[:space:]]*($|[;&|])
--no-preserve-root
(^|[;&|[:space:]])dd[[:space:]][^;&|]*of=["']?/dev/
(^|[;&|[:space:]])sudo[[:space:]]+(-[a-zA-Z]+[[:space:]]+)*rm([[:space:]]|$)
:\(\)[[:space:]]*\{[[:space:]]*:[[:space:]]*\|[[:space:]]*:[[:space:]]*&[[:space:]]*\}[[:space:]]*;[[:space:]]*:
(^|[;&|[:space:]])(curl|wget)[[:space:]][^;&|]*\|[[:space:]]*(sudo[[:space:]]+)?(ba|z|da)?sh([[:space:]]|$)
(^|[;&|[:space:]])git[[:space:]]+push[^;&|]*[[:space:]](-f|--force)([[:space:]]|$)
(^|[;&|[:space:]])gh[[:space:]]+repo[[:space:]]+delete([[:space:]]|$)
(^|[;&|[:space:]])gh[[:space:]]+auth[[:space:]]+token([[:space:]]|$)
```

## Exclusions conscientes
- `references/davidondrej-skills/skills/research-and-web/` (8 skills : DeepAPI, YouTube transcript, Fireflies transcript, online-shopping, pi-web-search) — trop spécifiques au workflow personnel de l'auteur.
- `references/davidondrej-skills/skills/ops-and-setup/` (macbook-metrics-setup, nuke-cursor-app, anti-sleep, pi-custom-model) — setup hardware/commercial spécifique macOS.
- `references/davidondrej-skills/skills/agent-orchestration/` (gpt-review / fable-review) — délèguent à un sous-agent commercial (GPT 5.6 Sol Max / Fable 5 Max 1M). Le pattern de prompt (neutre, « report verbatim ») est reprisable mais l'implémentation est liée à des modèles/abonnements.
- `references/davidondrej-skills/skills/agent-orchestration/` (codex-subagent, launch-subagent, run-deep-swe, cmux) — wrappers CLI autour de Codex/Cursor, non portables vers smolagents.
- `references/davidondrej-skills/skills/thinking-and-docs/` (before-building, decisions, level-up, remind, save-idea, short, teach, read-all-adrs…) — disciplines cognitives en prompts purs, style « coach personnel », pertinence faible pour un orchestrateur programmatique.

## Correspondance avec `plan_usine_logicielle.md`
- **P8 (Middlewares anti-crash)** : `dangerous-patterns.txt` (27 regex POSIX-ERE) + `deny-dangerous.sh` (moteur fail-open + message explicite citant le pattern) + `test-guard.sh` (~115 cas block+allow déjà écrits) + `global-agent-guardrails/SKILL.md` (doctrine « block catastrophic-only, allow recoverable »). **Enrichit directement notre F-38 (`bash_guard.py`)** de patterns manquants (gh delete, fork bomb, `curl|sh`, reflog expire) + la doctrine **fail-open** + une suite de tests prête à porter. **⚠️ Correction à reporter dans le plan** : « 52 regex » → « 27 regex (fichier de 52 lignes dont 15 commentaires + 10 vides) ». Complémentaire de learn-claude-code s04 (16, hooks) et qm (14, idempotence) — pas en concurrence.
- **P10 (Skill loading)** : `effective-agent-skills/SKILL.md` (doctrine authoring). Citée dans la fusion doctrine P10 (cf. fiche 23-mattpocock) avec awesome-claude-skills (18) — les 3 sources fusionnent en une doctrine enrichie plutôt qu'en 3 fiches séparées (Annexe B de la procédure).
- **P3 connexe** : `goal-loop/SKILL.md` (stop condition vérifiable + anti-reward-hacking).
