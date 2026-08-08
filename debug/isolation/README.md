# Scripts d'isolation (F-55 + F-89)

Deux familles complémentaires pour **itérer sur un nœud en secondes/minutes** sans relancer
le workflow complet (~30-40 min : Architect → Coder → Tester → Judge) :

1. **Méthodologies manuelles** (F-55) — *l'agent ZCode joue le nœud à la main* (Read, grep,
   `node --check`, DevTools, jugement). 0 LLM, 0 réseau. La doc sert de spec du nœud idéal.
2. **Scripts d'isolation LLM** (F-89, ce paragraphe) — *la VRAIE fonction de production est
   appelée* avec des fixtures figées. Reproduit fidèlement le comportement réel (prompts
   F-44/F-56/F-65, model_lifecycle, DSPy, smolagents) mais saute tout le reste du graphe.

## Convention

Chaque nœud a une **méthodologie** (`MANUAL_<NODE>_METHODOLOGY.md`) qui décrit **exactement
ce que JE fais** quand je joue ce nœud à la main :

1. **Les étapes dans l'ordre** (fail-fast) — ce que je fais, avec quel outil (`Read`, `grep`,
   `node --check`, DevTools, mon propre jugement), à quel coût (0 LLM la plupart du temps).
2. **Les échecs types détectés** — les bugs précis que chaque étape attrape (issus des runs
   réels, pas théoriques).
3. **Les biais de confirmation** — les pièges que j'ai vécus en jouant le nœud et leurs
   contre-mesures.
4. **Pourquoi cette méthode vs le LLM du graphe** — un comparatif (temps, fiabilité, tokens).

Ces docs sont la **spec du nœud idéal** : la source de vérité sur ce que le nœud *devrait*
faire, que je suis quand on me demande de le jouer, et qui sert de référence pour itérer sur
les prompts/skills/logique du nœud de production correspondant.

## Contenu du dossier

### Méthodologies manuelles (F-55 — l'agent joue le nœud)

| Fichier | Nœud joué | Type | Sortie attendue |
|---|---|---|---|
| `MANUAL_ROUTER_METHODOLOGY.md` | Router (F-01) | Classification | `RouterOutput(language)` |
| `MANUAL_ARCHITECT_METHODOLOGY.md` | Architect (F-15/F-29) | Découpage + stratégie | `ArchitectOutput(subtasks[strategy])` |
| `MANUAL_LINTER_METHODOLOGY.md` | Linter (F-30) | Gatekeeper syntaxe (déterministe) | `CoderOutput(status)` |
| `MANUAL_SECURITY_METHODOLOGY.md` | Security (F-44 OWASP) | Audit vulnérabilités | `SecurityOutput(is_secure, findings)` |
| `MANUAL_JUDGE_METHODOLOGY.md` | Judge (F-44 rubric) | Verdict final | `CodeJudgeOutput(is_approved, findings)` |
| `run_linter.py` | Linter (validation automatisée) | Script Python | `CoderOutput(status)` — valide la doc ci-dessus en exécution |
| `COMPARISON_AUDIT.md` | — (transverse) | Audit | Compare les 5 docs méthodologiques vs nœuds de production (prompt + skills + MCP + ajouts) → gaps + recommandations |

### Scripts d'isolation LLM (F-89 — la vraie fonction de production)

Tous dans `debug/` (sauf `run_linter.py` déjà ici). Chaque script appelle la **vraie**
fonction `execute_*_node` (0 mock, 0 duplication), avec des fixtures figées (entrées
reproductibles). Affiche le contrat entrée/sortie + métriques (modèle, durée).

| Script | Nœud | Entrée figée | Vérifie |
|---|---|---|---|
| `debug/run_router.py` | Router | 5 prompts (Python/React/HTML/Rust/ambigu) | Pas de débordement vers JS (bug F-56a) |
| `debug/run_prompt_refiner.py` | PromptRefiner | 3 prompts (vagues/déjà structuré/minimaliste) | Détection termes vagues sans inventer du scope |
| `debug/run_architect.py` | Architect | Spec Bubble Sort | 1 fichier = 1 sous-tâche, stratégie techno-driven |
| `debug/run_drafter.py` | Drafter | Sous-tâche Bubble Sort JS | Qualité du draft de logique (réinjectable dans Coder) |
| `debug/run_security.py` | Security | 4 codes (propre/XSS/eval/pickle) | Détection OWASP sans faux positifs |
| `debug/run_judge.py` | Judge | 4 scénarios (correct/bug/nit/fail-closed) | Verdict conforme + fail-closed sans LLM |
| `debug/run_coder.py` | Coder | Spec Bubble Sort 3 fichiers (+ draft optionnel) | Code produit complet (existant, créé fix F-88) |
| `debug/run_web_tester_standalone.py` | Web Tester | HTML correct/buggé | Assertions fonctionnelles (existant F-45) |

Usage type : `uv run python debug/run_<node>.py` (jeu de fixtures par défaut) ou
`uv run python debug/run_<node>.py "<input>"` (input unique).

Le nœud **Tester** a déjà sa méthodologie dans `debug/MANUAL_TESTER_METHODOLOGY.md` (le
pattern original, non dupliqué ici). Le nœud **Static Tester** (F-54) est validé par
`debug/validate_static_tester_live.py`. Les nœuds **Coder** sont illustrés par
`audit_coder/audit_coder_report.md` + les scripts racine `run_coder_tca.py` /
`run_coder_codeagent.py`.

## Comment jouer un nœud

1. **Lire la méthodologie** du nœud cible (`MANUAL_<NODE>_METHODOLOGY.md`).
2. **Préparer l'entrée** minimale que le nœud reçoit en production (dict `task`/`subtask`
   ou `str` — voir le contrat ci-dessous).
3. **Suivre les étapes** de la doc, en mode fail-fast (s'arrêter au premier échec détecté).
4. **Produire la sortie** au format Pydantic attendu (`RouterOutput`, etc.) + une
   justification courte.
5. **Documenter** le résultat si c'est une session d'audit (cf. `audit_coder/`).

## Contrat entrée/sortie par nœud (ce que le nœud reçoit en prod)

| Nœud | Entrée | Clés lues | Sortie |
|---|---|---|---|
| Router | `str` (prompt) | (pas un dict) | `RouterOutput(language)` |
| Architect | `dict` | `content` | `ArchitectOutput(subtasks[])` |
| Linter | `dict` | `id`, `target_files` | `CoderOutput(status, details)` |
| Security | `dict` | `id`, `target_files` | `SecurityOutput(is_secure, vulnerabilities, findings)` |
| Judge | `dict` + `Any` + `SecurityOutput?` | `id`, `target_files`, `original_content` (+ `test_res`, `security_res`) | `CodeJudgeOutput(is_approved, final_feedback, findings)` |

## Bénéfices

- **Dépannage rapide** : jouer un nœud à la main (secondes) ou via script d'isolation
  (minutes) sans relancer le graphe (~30-40 min) ni dépendre des autres nœuds.
- **Spé du nœud idéal** (méthodologies F-55) : la doc sert de référence pour itérer sur le
  prompt/skill/logique du nœud de production (ex: la grille de sévérité du Judge, la grille
  OWASP du Security).
- **Reproduction fidèle** (scripts F-89) : la vraie fonction de production est appelée → on
  valide le comportement réel (prompts, DSPy, model_lifecycle), pas un mock qui dérive.
- **Détection de régression** (nœuds déterministes) : entrées buggées connues → assertion
  sur le verdict. Voir `debug/fixtures/golden/` pour la convention golden files.
- **Onboarding / debug** : comprendre le contrat entrée/sortie d'un nœud en le jouant
  soi-même (à la main ou via script) avec des données contrôlées.

## Leçon structurante (post-mortem F-88)

Le bug du hash CodeAgent vide (F-88) a mis **1h10 de run E2E + post-mortem manuel** à
diagnostiquer, alors qu'il était reproductible en **<1s** sur le vrai parseur
(`extract_tool_calls_from_step` → `compute_material_fingerprint`). Si un script d'isolation
du Stall Detector avait existé, le bug aurait été attrapé **avant** la PR. C'est la leçon
qui place F-89 (jeux de tests par nœud) en priorité MAX : **chaque nœud doit avoir un
script d'isolation pour itérer en secondes, pas en dizaines de minutes.**

## Validation automatisée (nœuds déterministes uniquement)

Les nœuds **déterministes** (Linter, Static Tester) peuvent être validés par un script qui
appelle la vraie fonction de production (0 LLM, assertion binaire possible) :
- `run_linter.py` (ce dossier) — 7 scénarios buggés/corrects, validé 7/7 ✅ en millisecondes.
- `debug/validate_static_tester_live.py` (F-54) — pattern original.

Les nœuds **LLM** (Router, Architect, Drafter, Security, Judge, Coder, Tester) ont un
script d'isolation F-89 qui appelle la vraie fonction (comportement réel) mais sans
assertion binaire stricte — le verdict dépend de la réflexion, pas d'un pattern fixe.
On compare visuellement / heuristiquement la qualité de la sortie.
