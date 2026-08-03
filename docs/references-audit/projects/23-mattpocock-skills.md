# 23 — mattpocock-skills

## En-tête
- **Nom** : mattpocock-skills (« Skills For Real Engineers » de Matt Pocock)
- **Chemin** : `references/mattpocock-skills/`
- **Type** : Collection de ~41 skills agent (slash-commands / behaviors) pour coding-agents réels (Claude Code, Codex), avec une **doctrine d'authoring formelle**. Distribuée via 3 canaux : plugin Claude Code natif (`.claude-plugin/`), marketplace `skills.sh` (`npx skills add`), symlinks locaux (`scripts/link-skills.sh`).
- **Langage principal** : pur Markdown + YAML frontmatter + bash. **Zéro Python, zéro code applicatif** — doctrine textuelle pure.
- **Statistiques** : 166 fichiers hors `.git/` (111 `.md`, 41 `.yaml` (un `agents/openai.yaml` par skill), 5 `.sh`, 5 `.json`, 1 `.cjs`).
- **Organisation** : 6 buckets sous `skills/` — `engineering` (17, le cœur), `productivity` (5), `in-progress` (9), `deprecated` (4), `misc` (4), `personal` (2). **Promoted set** = `engineering` + `productivity` (22 skills), seuls exposés dans le plugin Claude ; chacun a un `SKILL.md` + une doc longue miroir sous `docs/<bucket>/<name>.md`.
- **ADR** : `.agents/adr/` (2 décisions d'architecture) ; conventions dans `.agents/` (`invocation.md`, `writing-docs.md`).

## Synthèse
Ce que mattpocock apporte d'unique vs awesome-claude-skills (18) et davidondrej (21) : ce n'est pas une liste de prompts, c'est une **doctrine d'authoring formelle**. `writing-great-skills` + son `GLOSSARY.md` définissent un **modèle conceptuel cohérent** (Predictability comme racine, deux charges cognitive/contextuelle, hiérarchie de l'information à 3 rungs, modes d'échec nommés). C'est exactement la matière que la procédure (Annexe B) cherche à fusionner en une fiche doctrine enrichie pour P10 — mattpocock en est le **socle conceptuel dominant**.

Valeur secondaire : `code-review` (deux axes parallèles en sub-agents, jamais fusionnés) et `tdd` (vertical slices, anti-patterns nommés) sont des briques concrètes pour P6 (judge/review) et P0 (spécialisation coding). Le pattern de composition « user-invoked orchestre → model-invoked exécute » est directement transposable à un orchestrateur multi-agent.

**Réserves pour le projet cible** :
- Philosophie **« small, easy to adapt, composable »** + **« any model »** (README l.19) — la doctrine mattpocock est pensée pour des skills **isolés, agent-agnostiques, sans état**. Notre orchestrateur est Python/DSPy/smolagents avec persistance DuckDB et workflow structuré : la doctrine de *pruning* et de *cognitive/context load* s'applique, mais la mécanique de *skill routing* par frontmatter Claude/Codex ne se transpose pas telle quelle.
- 100% orienté **TypeScript/web** dans les exemples (`processOrder`, StripeGateway, Postgres repo) — l'adaptation à Python demande reformulation.
- Le plugin Claude (`disable-model-invocation`, `policy.allow_implicit_invocation`) est **spécifique à l'écosystème Claude Code/Codex**, pas portable vers smolagents.

Note globale : **🟢 Haute** pour la doctrine P10 (le plus formel des 3 sources), 🟡 pour les engineering skills concrets (TS-biaisés). Pivot de la fusion doctrine P10.

## Documentation pertinente
| Chemin | Description | Réutilisabilité |
|---|---|---|
| `references/mattpocock-skills/docs/productivity/writing-great-skills.md` (+ `GLOSSARY.md` 202 L) | **LE FICHIER P10.** Doctrine d'authoring de skills la plus aboutie des 3 refs. Racine = Predictability ; deux charges (cognitive/context) ; hiérarchie 3 rungs ; 5 failure modes ; leading words ; completion criterion. | Haute |
| `references/mattpocock-skills/.agents/adr/0001-explicit-setup-pointer-only-for-hard-dependencies.md` | Décision : hard-dependency (→ setup pointer) vs soft-dependency (→ degrade gracefully). Pattern fail-loud vs degrade-gracefully. | Haute |
| `references/mattpocock-skills/.agents/adr/0002-ship-as-a-claude-code-plugin.md` | Décision packaging multi-harness (plugin Claude array vs path string Codex). Leçon de distribution. | Moyenne |
| `references/mattpocock-skills/docs/engineering/code-review.md` | Doc longue : two axes (Standards/Spec) en sub-agents parallèles, Fowler smell baseline (12). | Haute |
| `references/mattpocock-skills/docs/engineering/tdd.md` (+ `mocking.md`, `tests.md`) | Doc longue : red→green en vertical slices, seam (Michael Feathers), tracer bullet, 3 anti-patterns. | Haute |
| `references/mattpocock-skills/docs/engineering/diagnosing-bugs.md` | Doc longue : 6 phases, tight feedback loop red-capable, hypothèses falsifiables, bisection. | Moyenne |
| `references/mattpocock-skills/CONTEXT.md` | Exemple de ubiquitous-language minimal (Issue tracker / Issue / Triage role, section Flagged ambiguities). | Moyenne |
| `references/mattpocock-skills/README.md` | Marketing moitié newsletter/promo — ignorer pour la doctrine | Faible |

## Code réutilisable
| Chemin | Symbole(s) clé(s) | Description | Réutilisabilité | Justification |
|---|---|---|---|---|
| `references/mattpocock-skills/skills/productivity/writing-great-skills/SKILL.md` (+ `GLOSSARY.md`) | **Predictability**, **context load** vs **cognitive load**, **model-invoked** vs **user-invoked**, **router skill**, **information hierarchy** (3 rungs : in-skill step / in-skill reference / external reference), **progressive disclosure**, **context pointer**, **leading word** (Leitwort), **completion criterion** (checkable + exhaustive), **legwork**, **post-completion steps**, **single source of truth**, **co-location**, **negation** (elephant) | **Doctrine P10.** Règles verbatim plus bas. La plus aboutie des 3 sources (awesome-claude-skills + davidondrej + mattpocock). | **Haute** | Importer la structure conceptuelle comme armature de la fiche doctrine P10 fusionnée. Concepts agnostiques du runtime, applicables à nos skills smolagents |
| `references/mattpocock-skills/scripts/list-skills.sh` | `find -name SKILL.md` trié (filtre `node_modules`) | 7 L : discovery des skills par convention `SKILL.md`. Mécanique de registry implicite. | **Haute** | Outillage P10 — patron simple de discovery (complémentaire de `init_skill.py`/`quick_validate.py` de awesome-claude-skills 18) |
| `references/mattpocock-skills/scripts/link-skills.sh` | symlink vers `~/.claude/skills` + `~/.agents/skills`, exclusion `deprecated/`, garde-fou anti-self-pollution (détection symlink circulaire l.31-40) | 57 L : installe chaque skill comme symlink dans 2 harness dirs, `git pull` suffit pour MAJ. | Moyenne | Spécifique Unix/Claude — concept utile (symlink = MAJ automatique) mais à adapter |
| `references/mattpocock-skills/.agents/adr/0001-explicit-setup-pointer-only-for-hard-dependencies.md` | **hard-dependency** vs **soft-dependency** skill, setup pointer | Décision : seuls les skills à dépendance dure pointent vers setup ; les skills à dépendance molle dégradent gracieusement. | **Haute** | P10/P0 conception — pattern fail-loud vs degrade-gracefully (notre Context7/devtools font déjà du degrade-gracefully) |
| `references/mattpocock-skills/skills/engineering/code-review/SKILL.md` (+ `docs/engineering/code-review.md`) | **two axes** (Standards / Spec), **parallel sub-agents**, **Fowler smell baseline** (12 smells), `git diff <fixed-point>...HEAD`, merge-base three-dot, hard violation vs judgement call | Review du diff depuis un point fixe sur 2 axes en **sub-agents parallèles** (jamais fusionnés ni re-rankés). Standards = conventions repo + base Fowler ; Spec = conformité à l'issue/PRD. Chaîne : `grill-with-docs → to-spec → to-tickets → implement → code-review`. | **Haute** | P6 — pattern de judge agent à deux axes (Standards axis → lint/coding-standards, Spec axis → conformité PRD). Complémentaire d'open-swe (09) et code-review-graph (20) |
| `references/mattpocock-skills/skills/engineering/tdd/SKILL.md` (+ `mocking.md`, `tests.md`, `docs/engineering/tdd.md`) | **red → green**, **seam** (Michael Feathers), **pre-agreed seams**, **tracer bullet**, **vertical slices** vs **horizontal slicing**, **tautological** test, **implementation-coupled** | Boucle red-green en **vertical slices** (1 test → 1 impl → repeat), tests seulement aux seams pré-agréés, refactoring hors-boucle (délégué à code-review). 3 anti-patterns nommés. | **Haute** | P6/P0 — doctrine TDD pour le nœud Tester (complémentaire de LlamaBot 07 et fiche 17 invariants) |
| `references/mattpocock-skills/skills/engineering/diagnosing-bugs/SKILL.md` | **tight feedback loop**, **red-capable**, **minimise**, **falsifiable hypothesis** (3-5 ranked), `[DEBUG-a4f2]` tagging, bisection harness | 6 phases : construire une loop tight qui passe au rouge → reproduire/minimiser → 3-5 hypothèses falsifiables → instrumenter (1 var/time) → fix + regression test → cleanup. Phase 1 = "the skill". | Moyenne | P0 (debug) — doctrine de diagnostic pour le nœud Tester/Escalation |
| `references/mattpocock-skills/skills/engineering/codebase-design/SKILL.md` | **deep modules** (Ousterhout révisé : depth = leverage pas ratio de lignes), deletion test, "1 adapter = seam hypothétique, 2 = seam réel" | Vocabulaire de design de codebase. | Faible | Conceptuel, hors priorités cœur |

### Doctrine P10 — règles principales verbatim
Depuis `writing-great-skills/SKILL.md` + `GLOSSARY.md` :
- **Racine** : « A skill exists to wrangle determinism out of a stochastic system. **Predictability** — the agent taking the same _process_ every run, not producing the same output — is the root virtue; every lever below serves it. »
- **Deux charges** : model-invoked paie **context load** (description toujours en fenêtre) ; user-invoked paie **cognitive load** (« _you_ are the index that must remember it exists »).
- **Router skill** : « when user-invoked skills multiply past what you can remember, that piled-up cognitive load is cured by a **router skill**: one user-invoked skill that names the others and when to reach for each. »
- **Hiérarchie** (3 rungs) : in-skill step (avec **completion criterion** checkable + exhaustive) > in-skill reference > external reference derrière **context pointer**.
- **Split** : « split only when the cut earns it » — *by invocation* (nouveau leading word + indépend reach) ou *by sequence* (cacher les **post-completion steps** pour freiner la **premature completion**).
- **Pruning** : **single source of truth** + test du **no-op** (« does it change behaviour versus the default? ») appliqué **phrase par phrase** + **relevance** contre **sediment**.
- **Leading word** : « a compact concept already living in the model's pretraining » (_tight_, _red_, _tracer bullet_, _fog of war_) — sert l'invocation ET l'exécution.
- **5 failure modes** : **premature completion**, **duplication**, **sediment**, **sprawl**, **no-op**, **negation** (elephant — « prompt the positive »).

## Contrats / Specs / Config
| Chemin | Type | Description |
|---|---|---|
| `references/mattpocock-skills/.agents/adr/0001-*.md` | ADR | Décision hard-dependency vs soft-dependency — pattern architectural réutilisable |
| `references/mattpocock-skills/.agents/adr/0002-*.md` | ADR | Décision packaging multi-harness — leçon de distribution |
| `references/mattpocock-skills/CONTEXT.md` | spec (ubiquitous-language) | Exemple de vocabulaire partagé minimal avec section Flagged ambiguities |

## Exclusions conscientes
- `references/mattpocock-skills/skills/personal/` (2), `in-progress/` (9), `deprecated/` (4), `misc/` (4) — buckets non-promoted, hors scope.
- `references/mattpocock-skills/skills/productivity/` hors coding : `grill-me`, `grilling`, `handoff`, `teach` — intéressants conceptuellement (pattern *grilling* transposable) mais pas cœur du scope coding-agent.
- README marketing (liens `aihero.dev`, ~60k subs) — ignorer pour la doctrine.
- Mécanismes frontmatter Claude / `agents/openai.yaml` / plugin manifest — spécifiques écosystème Claude/Codex, ne portent pas vers smolagents/DuckDB.
- Snippets code TypeScript/web (Stripe, Postgres, Playwright) — besoin reformulation Python.

## Correspondance avec `plan_usine_logicielle.md`
- **P10 (Skill loading)** : `writing-great-skills/SKILL.md` + `GLOSSARY.md` (doctrine : Predictability, deux charges, hiérarchie 3-rungs, 5 failure modes, leading words) + `list-skills.sh`/`link-skills.sh` (outillage discovery) + ADR 0001 (hard vs soft dependency). **Pivot de la fusion doctrine P10** (Annexe B de la procédure) avec awesome-claude-skills (18, modèle 3-niveaux + init/validate) et davidondrej (21, effective-agent-skills). mattpocock = socle conceptuel dominant (le seul des 3 qui formalise une *théorie* plutôt qu'une *collection*). La distinction model-invoked/user-invoked + router skill se traduit en rôles d'agents (orchestrator = user-invoked router ; workers = model-invoked).
- **P6 (Judge / Findings)** : `code-review/SKILL.md` (two axes en sub-agents parallèles jamais fusionnés : Standards → lint/coding-standards, Spec → conformité PRD) + `tdd/SKILL.md` (vertical slices, seams pré-agréés, 3 anti-patterns). Complémentaire d'open-swe (09, findings), code-review-graph (20, risk score), llm-council (22, council), system-prompts (17, invariants).
- **P0 (Spécialisation)** : `diagnosing-bugs/SKILL.md` (doctrine diagnostic, tight feedback loop red-capable) pour le nœud Tester/Escalation.
