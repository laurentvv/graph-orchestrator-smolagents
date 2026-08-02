# Contrat de Validation

## Critères d'Acceptation Automatisés
- [ ] Critère 1 : Le fichier `feature_list.json` existe et respecte le schéma JSON attendu.
- [ ] Critère 2 : Le fichier `contract.md` est présent à la racine.
- [ ] Critère 3 : Le fichier `progress.md` liste les jalons du sprint courant.
- [ ] Critère 4 : Le fichier `log.md` respecte le format d'ajout continu avec horodatage.
- [ ] Critère 5 : Les tests pytest s'exécutent sans erreur.

## Critères de Validation du Coding Workflow (objectif sprint)
- [ ] Critère 6 : Le Router classifie correctement la techno (HTML/JS pour une landing page).
- [ ] Critère 7 : L'Architect produit un plan avec 1 sous-tâche par fichier cible (2-4 max).
- [ ] Critère 8 : Le Coder crée des fichiers NON vides via write_file (garde anti-vide active).
- [ ] Critère 9 : Les 3 fichiers cibles sont créés : landing_page/{index.html, styles.css, script.js}.
- [ ] Critère 10 : Le HTML généré est valide (présence de `<!DOCTYPE html>`, `<html>`, `</html>`).
- [ ] Critère 11 : Le Coder termine par final_answer (pas de boucle de re-écriture infinie).
- [ ] Critère 12 : Le Judge émet un verdict (is_approved booléen) à la fin.
- [ ] Critère 13 : Le Knowledge Graph trace les observations/refutations du run.

## Critères de l'édition sécurisée SEARCH/REPLACE (cycle en cours)
- [ ] Critère 14 : Le Coder peut éditer un fichier existant via search_replace sans corruption (matching tolérant).
- [ ] Critère 15 : search_replace rejette les placeholders (TODO, '...') dans le bloc replace.
- [ ] Critère 16 : search_replace renvoie un feedback didactique (lignes proches) quand le bloc search n'est pas trouvé.
- [ ] Critère 17 : Le Mutex par fichier sérialise les écritures concurrentes (tests test_search_replace.py PASS).
- [ ] Critère 18 : La suite pytest complète passe (0 régression, 11 nouveaux tests inclus).

## Critères de la Persistance d'État (Checkpoints — Priorité 3)
- [ ] Critère 19 : Le `run_id` est stable (dérivé du hash du contenu de tâche) — relancer la même tâche reprend là où c'était arrêté ; deux contenus différents donnent deux run_id différents.
- [ ] Critère 20 : La reprise court-circuite l'Architect (plan rechargé depuis le checkpoint via `ArchitectOutput(**dict)`) et saute les sous-tâches déjà approuvées (résultat `replayed=True`).
- [ ] Critère 21 : La granularité "début d'itération" persiste un état cohérent avant chaque Coder (le checkpoint reflète `(current_subtask_idx, current_iteration)` + `architect_result` + `completed_subtasks`) ; à la reprise on rejoue l'itération complète (idempotent, jamais un état intermédiaire).
- [ ] Critère 22 : `FRESH_START=1` efface le checkpoint existant ; un run allant au bout efface son propre checkpoint (run "terminé"). `save_checkpoint`/`load_checkpoint`/`clear_checkpoint` validés sur DuckDB (upsert, round-trip, absence → None).
- [ ] Critère 23 : La suite pytest ciblée passe (0 régression, 12 nouveaux tests test_checkpoint.py inclus).

## Critères du Tester polyvalent multi-techno + Boucle d'auto-correction (Priorité 2)
- [ ] Critère 24 : `detect_tech` combine Router + extensions de `target_files` ; les extensions l'emportent en cas de conflit (déterministe > LLM) ; fallback `web` si rien de détectable.
- [ ] Critère 25 : `execute_tester_node` dispatche vers le bon runner selon la techno (`get_runner`) ; `task["tech"]` explicite prime sur la détection.
- [ ] Critère 26 : `PythonTestRunner` (subprocess) : exit 0 → `status="success"` ; exit≠0 → `"failure"` + stderr/stdout capturé et tronqué. Le subprocess utilise `sys.executable` (interpréteur du projet, qui a pytest).
- [ ] Critère 27 : Le `WebTestRunner` refactorisé conserve le comportement du bloc Puppeteer d'origine (MCP Chrome DevTools, calcul d'URL, skill web-tester) ; chargé via le loader centralisé.
- [ ] Critère 28 : `truncate_output` préserve head + tail + insère un marqueur transparent (`… [X lignes tronquées] …`) ; texte court retourné intact ; `None`/vide → `""`.
- [ ] Critère 29 : `truncate_history` plafonne l'historique cumulé des réfutations injecté au Coder (≤ `feedback_max_chars`), bugs récents prioritaires ; garde au moins le 1er item (tronqué) pour ne pas laisser le Coder sans info.
- [ ] Critère 30 : La troncature opère **à la lecture** (injection au Coder/Judge) — le contenu écrit en DuckDB reste intégral (pas de collision de `dedup_key`).
- [ ] Critère 31 : Le skill `web-tester` exige désormais un rapport structuré (section « ERREURS CONSOLE JS » = le « stderr » du web) ; le skill `python-tester` documente le verdict pytest (exit code) et la lecture d'un échec.
- [ ] Critère 32 : La suite pytest complète passe (0 régression, nouveaux tests inclus : feedback_utils, tech_detection, python_runner, tester_dispatch, feedback_integration).

## Critères de l'Édition Incrémentale (append_file — F-28)
- [ ] Critère 46 : `append_file(path, content)` AJOUTE `content` à la fin d'un fichier sans réécrire l'existant (contenu préservé) ; crée le fichier s'il n'existe pas (mode `'a'`).
- [ ] Critère 47 : Le mutex par fichier (`_file_lock`) sérialise les écritures concurrentes — 2 appends parallèles ne se corrompent pas (test `test_append_concurrent_does_not_corrupt` : 40 lignes attendues, 0 perdue).
- [ ] Critère 48 : Garde anti-contenu-vide + anti-placeholder — `content=""` ou `"TODO"` est rejeté avec message pédagogique, le fichier N'EST PAS modifié.
- [ ] Critère 49 : Garde anti-doublon légère — si `content` est déjà la fin exacte du fichier, l'opération est signalée (`NOTICE ... duplicate`) SANS réécrire (défense contre le bug "section appendée N fois").
- [ ] Critère 50 : Feedback riche (SWE-agent ACI) — le retour contient le nb de chars ajoutés ET la nouvelle taille totale (chars + lignes), pour que le modèle suive sa progression.
- [ ] Critère 51 : Les sous-dossiers parents sont créés automatiquement (`os.makedirs(exist_ok=True)`), cohérent avec `write_file`.
- [ ] Critère 52 : La suite pytest complète passe (0 régression, nouveaux tests `test_append_file.py` inclus : création, préservation, gardes, anti-doublon, sous-dossiers, concurrence).

## Critères du Cycle P1-P3 (finalisation)
### Linter Shift Left (F-30)
- [ ] Critère 53 : `lint_file(path)` détecte la langue par extension (Python/HTML/CSS/JS/TS/TSX) ; extension inconnue/fichier absent → valide (pas de faux positif, dégradation gracieuse).
- [ ] Critère 54 : Back-end double complémentaire — tree-sitter (SyntaxError, strings non fermées, structures cassées) + py_compile (IndentationError Python — le point noir que tree-sitter tolérant ne voit PAS) + vérifs structurelles HTML (contenu après `</html>`, équilibrage balises).
- [ ] Critère 55 : `execute_linter_node` (déterministe, 0 LLM, `model='tree-sitter-linter'`) retourne `CoderOutput(status, details)` avec status='failure' si AU MOINS un fichier invalide + détails exploitables par le Coder (nom du fichier + erreur).
- [ ] Critère 56 : Branchement workflow — inséré ENTRE le Coder et le Tester ; si invalide → court-circuite le Tester coûteux (écrit réfutation `source='linter'` en DuckDB, relance le Coder à l'itération suivante via `continue`).

### Architect adaptatif (F-29)
- [ ] Critère 57 : `ArchitectTask` expose `strategy` (`Literal['simple','incremental','multifile']`, défaut `'simple'` pour rétro-compat) + `sections` (`List[str]`, vide sauf si `incremental`).
- [ ] Critère 58 : `ArchitectSignature` docstring explique les 3 stratégies + quand utiliser laquelle (HTML/CSS/JS → multifile par défaut, Python/TS → multifile, monolithe imposé → incremental).
- [ ] Critère 59 : `strategy` + `sections` propagés dans `sub_dict` (workflows.py) via `getattr(subtask, 'strategy', 'simple')` → consommés par le prompt Coder (F-32).
- [ ] Critère 60 : Round-trip `ArchitectOutput.model_dump()` → `ArchitectOutput(**dict)` préserve strategy/sections (compatible checkpoint) ; sous-tâche historique sans stratégie → défaut `'simple'`.

### Migration Coder → CodeAgent (P1/F-29a)
- [ ] Critère 61 : `execute_coder_node` instancie un `CodeAgent` (pas un `ToolCallingAgent`) ; `final_answer` attendu en syntaxe Python (`final_answer({...})`), pas en JSON.
- [ ] Critère 62 : `run_with_retry` RÉUTILISÉ (compatible CodeAgent, hérite de MultiStepAgent) ; `extract_and_validate` gère le dict renvoyé par `final_answer` (models.py gère déjà les dicts).

### Prompt Coder réécrit (F-32)
- [ ] Critère 63 : Structure canonique (Rôle → Règles critiques → Format sortie → One-shot → Workflow adapté stratégie → Rappels) ; double-marquage primacy/recency.
- [ ] Critère 64 : Anti "reasoning sans action" — "AGIS, ne raconte pas" + "Une réponse sans appel d'outil = tâche terminée".
- [ ] Critère 65 : Anti triple-quote — "≤60 lignes/appel, chaque bloc syntaxiquement complet, jamais de string/brace ouverte entre 2 appels".
- [ ] Critère 66 : Workflow adapté à la stratégie — `incremental` impose squelette avec marqueurs d'insertion ouverts + append par section (corrige le bug dashboard : on n'append PAS après `</html>` fermé).

### Guard logiciel anti-déraillement (F-33)
- [ ] Critère 67 : `_detect_idle_step` détecte un tour SANS tool call exécuté (inspecte dernier `ActionStep` : `tool_calls`/`code_action`/`observations` tous vides) → message anti-idle ré-injecté (openfox style).
- [ ] Critère 68 : Exception parsing CodeAgent (triple-quote non fermée) → message "découpe au lieu de recommancer le même gros payload" (deer-flow style).
- [ ] Critère 69 : Message de retry adapté au type d'agent — Python (`final_answer(...)`) pour CodeAgent, JSON (`model_json_schema()`) pour ToolCallingAgent.

### Validation globale
- [ ] Critère 70 : La suite pytest complète passe (0 régression, 271 tests : 240 avant + 17 linter + 6 architect strategy + 8 guard).
- [ ] Critère 71 : Import du workflow complet OK — pas de circularité avec `linter.py` + CodeAgent + signatures Architect modifiées.

## Critères de l'Auto-Résolution des Dépendances (Priorité 5 — F-26)
- [ ] Critère 39 : `extract_missing_module(stderr)` extrait le nom de module top-level d'un `ModuleNotFoundError` (`'requests'`, `'requests.auth'` → `'requests'`) ; retourne `None` si pas de `ModuleNotFoundError` ou si le nom extrait n'est pas un identifiant Python valide (regex `^[A-Za-z_][A-Za-z0-9_]*$` — défense en profondeur anti-injection).
- [ ] Critère 40 : Le déclenchement est conditionnel — `extract_missing_module` n'est appelé QUE si `exit_code != 0` ET `settings.auto_install_deps` est vrai ; un AssertionError/SyntaxError/etc. ne déclenche JAMAIS l'install (comportement historique préservé).
- [ ] Critère 41 : `auto_install_deps=False` (opt-out via `AUTO_INSTALL_DEPS=false`) désactive totalement la feature — aucune install tentée, aucune relance, failure normal (comportement historique).
- [ ] Critère 42 : L'installation est **non-persistante** (`pip install` via `sys.executable`, liste d'args sans `shell=True`) — n'écrit ni dans `pyproject.toml` ni dans `uv.lock` (aucun fichier du projet modifié, aucun effet de bord visible en git).
- [ ] Critère 43 : Cap **1 retry** — si l'install réussit, les tests sont relancés une seule fois ; si l'install échoue (PyPI down), aucune relance (pas de boucle infinie).
- [ ] Critère 44 : Dégradation gracieuse — `_install_module` n'élève JAMAIS d'exception (timeout/réseau/pip absent → retourne `False`) ; un échec d'install ne fait jamais planter le run (le test ressort en failure comme avant). L'action est tracée dans `details` pour l'observabilité (ex : `[auto-install] 'requests' installé puis tests relancés`).
- [ ] Critère 45 : La suite pytest complète passe (0 régression, nouveaux tests `test_python_runner.py` inclus : `extract_missing_module` unitaire, comportement auto-install retry/opt-out/non-ModuleNotFoundError/cap, contrat `_install_module` succès/échec/exception).

## Critères de l'Anti-Loop Cryptographique (Priorité 3 — P3 plan usine logicielle)
- [ ] Critère 72 : `compute_tool_call_fingerprint(tool_name, arguments)` produit un hash SHA256 stable — `(tool, args)` identiques → même empreinte, indépendamment de l'ordre des clés du dict (`sort_keys=True`) ; le whitespace de tête/queue des valeurs string est normalisé (les petits LLM ajoutent/suppriment des espaces au hasard).
- [ ] Critère 73 : Deux outils différents appelés avec les mêmes arguments ne sont PAS considérés comme une boucle (le nom de l'outil préfixe le hash) ; deux appels du même outil avec des arguments différents non plus.
- [ ] Critère 74 : `LoopGuard.repeated_action()` renvoie un message pédagogique (`"CIRCUIT BREAKER (Anti-Loop)..."`) uniquement quand une même empreinte atteint le seuil (`threshold`) ; `None` sinon. Seuil `< 2` rejeté (`ValueError`).
- [ ] Critère 75 : Opt-out `LOOP_GUARD_ENABLED=false` désactive totalement la détection (jamais de déclenchement, `record()` no-op) ; seuil configurable via `LOOP_GUARD_THRESHOLD` (défaut 3).
- [ ] Critère 76 : `reset()` vide le compteur entre deux retries (aligné sur la purge de `agent.memory.steps` dans `run_with_retry` — un bug d'une tentative précédente ne fait pas déclencher la suivante).
- [ ] Critère 77 : `extract_tool_calls_from_step` lit les tool calls des deux familles d'agents — ToolCallingAgent (`step.tool_calls`, liste structurée `.name/.arguments`) ET CodeAgent (`step.code_action`, source Python scannée pour les noms d'`@tool` connus) ; step vide → liste vide.
- [ ] Critère 78 : Le guard n'est instancié QUE dans `execute_coder_node` (seul nœud appelant des outils d'écriture — un agent sans outils ne peut pas boucler sur des tool calls) et passé à `run_with_retry` via le paramètre optionnel `loop_guard=None` (non-cassant : les autres nœuds appellent `run_with_retry` sans guard, comportement inchangé).
- [ ] Critère 79 : La suite pytest complète passe (0 régression, nouveaux tests `test_loop_guard.py` inclus : empreinte stable/order/whitespace, détection seuil/opt-out/reset, extraction ToolCallingAgent+CodeAgent, intégration `run_with_retry`).

## Critères du Nettoyage DOM (Priorité 6 — P6 plan usine logicielle, LlamaBot)
- [ ] Critère 80 : `clean_dom_for_llm(html)` supprime ENTIÈREMENT (contenu inclus) les balises bruyantes : `<script>`, `<style>`, `<svg>`, `<canvas>`, `<iframe>`, `<noscript>`, `<template>`, `<head>` — case-insensitive (HTML tolère `<SCRIPT>`), variants auto-fermants (XHTML) inclus.
- [ ] Critère 81 : Les commentaires HTML `<!-- ... -->` sont supprimés (y compris gros contenu conditionnel type `<!--[if IE]>`).
- [ ] Critère 82 : Le contenu sémantique est PRÉSERVÉ — texte, `<div>`/`<table>`/`<p>`, attributs `id`, `class`, `aria-*`, `role` (utiles aux assertions fonctionnelles du Web Tester).
- [ ] Critère 83 : Compactage whitespace — espaces en fin de ligne supprimés, series de ≥3 newlines réduites à 2 ; troncature finale à `max_chars` (défaut 8000, cohérent avec `FEEDBACK_MAX_CHARS`) avec marqueur `[tronqué par dom_filter]`.
- [ ] Critère 84 : Cas limites — `None`/chaîne vide → `""` ; HTML déjà propre → contenu sémantique inchangé.
- [ ] Critère 85 : Gain effectif — sur un HTML réaliste (80% de bruit script+style+svg), la taille est divisée par au moins 3 (justification ROI du plan : "économise massivement les tokens sur le Web Tester").
- [ ] Critère 86 : Branchement `web_tester.py` — le prompt du Web Tester contient une directive "NETTOYAGE DOM" qui fournit un snippet JS (exécuté côté navigateur via `puppeteer_evaluate`, plus efficace qu'un round-trip Python) appliquant le même nettoyage avant analyse/citation du DOM dans le rapport.
- [ ] Critère 87 : La suite pytest complète passe (0 régression, nouveaux tests `test_dom_filter.py` inclus : suppression de chaque famille de balises, casse/XHTML, commentaires, préservation sémantique, compactage, troncature, cas limites, gain effectif).

## Critères du Guard bash denylist (Priorité 8-bis — robustesse runtime)
- [ ] Critère 88 : `check_bash_command(cmd)` renvoie `(allowed, reason)` — ne lève JAMAIS d'exception ; `allowed=True, reason=""` si la commande passe, `allowed=False, reason="<message pédagogique>"` si bloquée.
- [ ] Critère 89 : Blocage des commandes destructrices Unix — `rm -rf /` (+ `/usr`, `/etc`, `/home`...), `rm -rf ~`/`$HOME`, `rm -rf *` non borné, `mkfs`, `dd of=/dev/sd*`, redirection `> /dev/sd*`, fork bomb `:(){ :|:& };:`, `chmod -R 777 /`.
- [ ] Critère 90 : Blocage des commandes destructrices Windows — `format X:`, `rmdir/rd /s /q` sur `C:\`/`%SystemRoot%`/`%Windir%`/`%ProgramFiles%`, `del /f /s /q` idem, `diskpart`, `reg delete HKLM\...`.
- [ ] Critère 91 : Blocage cross-plateforme — `shutdown`/`halt`/`poweroff`/`reboot`, `git push --force`/`-f`, `curl|sh`/`wget|bash` (exécution code distant non inspecté).
- [ ] Critère 92 : Préservation des usages légitimes (anti faux positifs) — `rm -rf ./build`, `rm fichier`, `git push origin main`, `git commit`, `pytest`, `mkdir`, `cat /etc/hostname`, ET un chemin contenant un mot-clé anodin (`cat /format/rapport.txt` n'est PAS bloqué par le pattern `format X:`).
- [ ] Critère 93 : Insensibilité à la casse (`FORMAT C:`, `RM -RF /`) + normalisation whitespace (espaces multiples ne cassent pas la détection) ; commande vide/None → autorisée (no-op laissé à subprocess).
- [ ] Critère 94 : Branchement dans `bash_command` (`tools.py`) — le guard s'exécute AVANT `subprocess.run(shell=True)` ; une commande bloquée ne lance JAMAIS le subprocess (vérifié par test d'intégration). Opt-out `BASH_GUARD_ENABLED=false` contourne le guard (utile pour les envs de confiance).
- [ ] Critère 95 : La suite pytest complète passe (0 régression, nouveaux tests `test_bash_guard.py` inclus : 66 tests paramétrés couvrant blocages Unix/Windows/cross, légitimes préservés, casse/whitespace, message pédagogique, intégration subprocess + opt-out).

## Critères du nœud PromptRefiner (F-39, meta-prompt avant l'Architect)
- [ ] Critère 96 : `PromptRefinerSignature` (DSPy, `ChainOfThought`) prend 2 inputs (`raw_prompt` + `available_capabilities`) et renvoie un `PromptRefinerOutput` Pydantic (`refined_prompt: str` + `ambiguities_detected: List[str]`).
- [ ] Critère 97 : L'instruction (docstring) impose 4 étapes — (1) détection termes vagues (fast/easy/user-friendly/flexible...) → `ambiguities_detected` ; (2) orientation selon capacités dispo (web-tester/python-tester/context7) ; (3) structuration en sections fixes `## Objectif / ## Fonctionnalités attendues / ## Contraintes techniques / ## Critères de validation` (Given/When/Then quand pertinent) ; (4) complétion légère SANS inventer de scope. Règle "Tu STRUCTURES, tu n'INVENTES PAS" + concision ~30 lignes + préservation des exigences explicites.
- [ ] Critère 98 : `_build_capabilities_summary(settings)` produit un résumé compact contenant — le catalogue COMPLET des skills (via `agent_server.skills.list_skills()`, repli lecture dossier `skills/` si import échoue, chaîne vide si tout échoue), le statut Context7 (`bool(CONTEXT7_API_KEY)`, sans connexion réseau), et les testers statiques (Puppeteer/pytest). Dégradation gracieuse à 3 niveaux.
- [ ] Critère 99 : `execute_prompt_refiner_node` clone le pattern `execute_router_node` (`_configure_dspy` + `dspy.ChainOfThought` + `asyncio.to_thread`), utilise le modèle REASONING (gemma), `node="prompt_refiner_dspy"`, dégradation `(None, None)` sur exception (l'appelant replie sur prompt brut).
- [ ] Critère 100 : Branchement dans `run_coding_workflow` — le nœud s'exécute APRÈS le calcul du `run_id` (l.221, hash du prompt BRUT → stable) et AVANT le Router. Si succès → `task_content = refined.refined_prompt` muté dans `seed_tasks[0]['content']` (propagé à Router/Architect/Tester/Judge) ; si échec/None → repli prompt brut.
- [ ] Critère 101 : Persistance checkpoint — `refined_prompt` est sauvegardé dans le payload (`save_coding_state`) et hydraté à la reprise : si `checkpoint["refined_prompt"]` existe, le nœud LLM est SKIPPÉ (économie, même logique que `architect_result`).
- [ ] Critère 102 : Opt-out `PROMPT_REFINER_ENABLED=false` → le nœud n'est jamais appelé, l'Architect reçoit le prompt brut (comportement historique). Défaut `True` dans la dataclass (ne casse pas les `Settings(...)` positionnels en test).
- [ ] Critère 102-bis : Setting `PROMPT_REFINER_MODEL_ID` — si vide (défaut), le nœud utilise `reasoning_model_id` (gemma-12B, ~5min/prompt) ; si setté, il utilise ce modèle dédié (recommandation : gemma-4-E4B, ~8× plus rapide pour qualité équivalente — test comparatif réel dans log.md). `_configure_dspy` reçoit le modèle dédié et la métrique `model` reflète le modèle réellement utilisé. Fallback transparent sur `reasoning_model_id` si vide (rétro-compatibilité).
- [ ] Critère 103 : Context7 est CITÉ seulement dans le catalogue (statut dispo), JAMAIS consommé par le PromptRefiner — l'Architect fait déjà le pré-fetch en `dspy_nodes.py:225` (pas de duplication d'appel).
- [ ] Critère 104 : La suite pytest complète passe (0 régression, nouveaux tests `test_prompt_refiner.py` inclus : exécuteur mock LLM + available_capabilities propagé, dégradation gracieuse, helper capabilities avec/sans clé/repli, E2E toggle off, E2E toggle on + propagation Architect, E2E checkpoint skip). Les 3 helpers E2E existants (`test_escalation`/`test_checkpoint`/`test_feedback_integration`) mockent `execute_prompt_refiner_node` pour éviter un appel LLM réel en test.

## Critères de l'Output daté par run (Priorité 13 — isolation des artefacts)
- [ ] Critère 105 : `_slugify(text)` produit un slug sûr cross-plateforme (lowercase, `[^a-z0-9]→_`, collapse `__+`, strip bord, truncate `max_len=24`) ; fallback `'run'` si texte vide/nul ; aucun caractère interdit Windows (`:`/`?`/`*`/`<>`/`|`).
- [ ] Critère 106 : `_resolve_run_output_dir` renvoie un chemin **absolu** — si `checkpoint["output_dir"]` existe → REPRED ce dossier (reprise après crash, fichiers préservés) ; sinon → nouveau dossier daté `{output_dir}/{YYYY-MM-DD}_{HHMM}_{slug}/` résolu en absolu.
- [ ] Critère 107 : `_scoped_chdir(target_dir)` est un context manager qui restore **TOUJOURS** le cwd original à la sortie (y compris en cas d'exception mid-bloc — `try/finally`). Critical pour les tests E2E qui enchaînent plusieurs runs.
- [ ] Critère 108 : Branchement dans `run_coding_workflow` — ORDRE CRITIQUE respecté : (1) KG instancié AVANT le chdir → DuckDB reste à `kg_path` stable ; (2) checkpoint chargé AVANT la décision reprise/nouveau ; (3) `run_id` (hash du contenu brut, PAS du cwd) calculé avant et inchangé.
- [ ] Critère 109 : Le `output_dir` est persisté dans le checkpoint (`save_coding_state` payload clé `"output_dir"`) pour que la reprise après crash reprenne dans le MÊME dossier.
- [ ] Critère 110 : Les fichiers générés par le Coder atterrissent dans `runs/.../`, PAS à la racine du projet (validé par test E2E qui écrit un fichier relatif et vérifie son emplacement).
- [ ] Critère 111 : `kg_path` ne suit PAS le chdir — la DB DuckDB reste à sa place d'origine (testé `test_e2e_kg_path_stable_after_chdir` : la DB existe à `kg_path`, pas dans `runs/`).
- [ ] Critère 112 : Cas `kg_path=":memory:"` (tests) — ne crash pas (dossier neuf créé, pas de persistance checkpoint).
- [ ] Critère 113 : La suite pytest complète passe (0 régression, nouveaux tests `test_output_dir.py` inclus : slugify 5 cas, resolve 3 cas, scoped_chdir 2 cas, E2E 3 cas — écriture run dir, reprise même dossier, kg_path stable).
- [ ] Critère 114 : `repair_orphan_tool_results` détecte un `tool_use` orphelin (sans `tool_result` associé) et injecte une fausse réponse `FAKE_INTERRUPTED` (`{"status": "error", "error": "Interrompu"}`) — testé `test_single_orphan_repaired` (1 réparation, temoin id+content).
- [ ] Critère 115 : `repair_orphan_tool_results` ignore les appels d'outil déjà répondus (idempotence complète) — testé `test_already_answered_untouched` (0 réparation, liste strictement égale) + `test_reapply_is_noop` (0 réparation au second passage).
- [ ] Critère 116 : `repair_orphan_tool_results` gère les orphelins multiples sur plusieurs messages (réparation = somme) et détecte les blocs sérialisés `type="function"` + `function.name` (OpenAI/smolagents ToolCall.dict) via `id` — testé `test_multiple_orphans_repaired` (3 réparations) et `test_block_with_id_and_name_is_tool_use`.
- [ ] Critère 117 : `repair_orphan_tool_results` résiste aux cas dégénérés — appel sans id, string `content`, content non-liste — sans crasher (testé `test_call_without_id_skipped`, `test_string_content_skipped`, `test_non_list_content_skipped`).
- [ ] Critère 118 : `repair_orphan_steps` répares un ActionStep smolagents avec `tool_calls` mais sans `observations`/`error` en injectant `observations=FAKE_INTERRUPTED` — testé `test_steps_level_uses_observations` (1 étape réparée, `.observations == FAKE_INTERRUPTED`).
- [ ] Critère 119 : `repair_orphan_steps` ignore les étapes non-orphelines : avec observations, avec erreur, réponse finale, sans tool_calls (0 réparation) — testé `test_steps_status_nodes` + `test_final_answer_respected`.
- [ ] Critère 120 : L'intégration dans `nodes.run_with_retry` est défensive (bloc `try/except Exception`) et répare la mémoire avant chaque exécution d'agent — vérifié par lecture du code (P8 block, lignes ~174-189).
- [ ] Critère 121 : La suite pytest complète passe toujours (0 régression ; `tests/test_orphan_repair.py` 11 tests + `test_guard.py` + `test_loop_guard.py`, total 405 passed / 0 failed).

## Critères du Sanitizer (Auto-typage des arguments d'outil — F-42)
- [ ] Critère 122 : `coerce_value("1, 80", {"type": "integer"})` renvoie `80` (dernier entier de la chaîne) — le cas cible F-42, testé `test_coerce_integer_extracts_last_number`.
- [ ] Critère 123 : `coerce_value` préserve les valeurs déjà typées (int→int, float→int tronqué, bool→bool) et laisse les valeurs non coercibles inchangées (`"abc"`→`"abc"`) — testé `test_coerce_integer_already_int_and_float` + `test_coerce_integer_uncoercible_left_intact` + `test_coerce_integer_bool_preserved`.
- [ ] Critère 124 : `coerce_value` gère `number` (string→float), `boolean` (`"true"`/`"1"`/`"yes"`/`"on"`→True ; `"false"`/`"0"`/`"no"`/`"off"`→False ; non reconnu→inchangé), `string` (non-str→str()) — testé `test_coerce_number` + `test_coerce_boolean` + `test_coerce_string`.
- [ ] Critère 125 : `coerce_value` parse les structures `array`/`object` depuis une string JSON (`json.loads`→`ast.literal_eval` fallback) et laisse une string non parsable inchangée ; `None` respecté (nullable) — testé `test_coerce_array_from_json_string` + `test_coerce_object_from_json_string` + `test_coerce_unparseable_structure_left_intact` + `test_coerce_none_respected`.
- [ ] Critère 126 : `sanitize_tool_arguments` coerce uniquement les clés connues du schéma `inputs` ; les clés inconnues restent inchangées ; les arguments non-dict et les `inputs` non-dict sont renvoyés inchangés — testé `test_sanitize_known_keys_only` + `test_sanitize_unknown_keys_untouched` + `test_sanitize_non_dict_arguments_untouched` + `test_sanitize_non_dict_inputs_noop`.
- [ ] Critère 127 : `SanitizedTool` copie `name`/`description`/`inputs`/`output_type` de l'outil sous-jacent et délègue à son `__call__` en coerçant les kwargs (l'outil réel reçoit des arguments typés, pas les strings) — testé `test_sanitized_tool_copies_metadata` + `test_sanitized_tool_coerces_and_delegates`.
- [ ] Critère 128 : `SanitizedTool` reste un `BaseTool` (satisfait les `isinstance` du framework) ; `wrap_tool` enveloppe un `BaseTool` ; `sanitize_tools(enabled=True)` enveloppe tous, `sanitize_tools(enabled=False)` est no-op (même objet liste) — testé `test_sanitized_tool_valid_callable_isinstance` + `test_wrap_tool_wraps_base_tool` + `test_sanitize_tools_enabled_wraps_all` + `test_sanitize_tools_disabled_is_noop`.
- [ ] Critère 129 : Le branchement dans `nodes.execute_coder_node` et `execute_architect_node` enveloppe les tool sets via `sanitize_tools(..., enabled=settings.sanitizer_enabled)` ; config `sanitizer_enabled` (env `SANITIZER_ENABLED`, défaut True) ajoutée à `config.py` — vérifié par lecture du code (lignes ~424-427 Architect, ~488-491 Coder ; config.py champ + load_settings).

## Critères de l'Idempotence des effets de bord (Priorité 8-bis — F-43)
- [ ] Critère 130 : `IdempotencyStore.once(key, fn)` retourne `True` la 1re fois (fn exécutée), `False` la 2e (skippée) — testé `test_once_runs_fn_first_time_skips_second` ; `committed` reflète l'état — testé `test_committed_reflects_state`.
- [ ] Critère 131 : Inflight set bloque un 2e appel concurrent sur la même clé (fn tourne 1 fois) ; 20 threads concurrents → fn exécutée exactement 1 fois — testé `test_inflight_blocks_concurrent_same_key` + `test_concurrent_once_runs_fn_exactly_once`.
- [ ] Critère 132 : Si `fn` lève, `once` propage l'exception et ne marque PAS done (retryable au prochain replay) — testé `test_fn_raises_not_marked_done_retryable`.
- [ ] Critère 133 : Backing durable DuckDB — un nouveau `IdempotencyStore` (même `kg`+`run_id`, RAM fraîche simulant un crash/nouveau process) voit `committed` True via le backing et `once` skip — testé `test_durable_backing_survives_new_store`.
- [ ] Critère 134 : Isolation par `run_id` — un `run_id` différent ne voit pas les records d'un autre run — testé `test_durable_different_run_id_not_committed`.
- [ ] Critère 135 : Rétention — une key expirée (au-delà de `retention_s`) est re-runnable ; `prune_idempotency` supprime les records expirés — testé `test_retention_expired_key_rerunnable` + `test_prune_removes_old_records`.
- [ ] Critère 136 : `make_op_key(run_id, kind, *parts)` est stable (mêmes inputs → même clé), différenciée par `kind` et par `parts`, et bornée (hash SHA256, pas de clé arbitrairement longue) — testé `test_make_op_key_stable` + `test_make_op_key_differentiated_by_kind` + `test_make_op_key_differentiated_by_parts` + `test_make_op_key_bounded_for_large_content`.
- [ ] Critère 137 : `_scoped_idempotency(store)` set le store courant, le clear TOUJOURS à la sortie (y compris sur exception) ; `store=None` → no-op — testé `test_scoped_idempotency_sets_and_clears` + `test_scoped_idempotency_clears_on_exception` + `test_scoped_idempotency_none_store`.
- [ ] Critère 138 : `KnowledgeGraph` — `save_idempotency` (INSERT OR IGNORE, idempotent) + `is_idempotency_committed` + `prune_idempotency` + `clear_idempotency(run_id)` (efface CE run seulement) — testé `TestKnowledgeGraphIdempotency` (4 tests). `clear_idempotency(run_id)` est appelé aux MÊMES sites que `clear_checkpoint` (FRESH_START l.309 + fin de run l.706 de workflows.py) — vérifié par lecture du code.
- [ ] Critère 139 : Intégration `append_file` — un 2e append identique (même path+content) CE RUN est skippé par le store (au-delà de l'anti-doublon textuel qui échoue si un append ultérieur a déplacé la fin du fichier) ; sans store (opt-out) → comportement historique — testé `test_append_file_idempotent_on_replay` + `test_append_file_no_store_historical_behavior`. `write_file` n'est PAS wrappé (idempotent par écrasement par design).
- [ ] Critère 140 : Intégration `_install_module` (pip) — un 2e appel pour le même module CE RUN est skippé (backing DuckDB) ; un échec n'est PAS marqué done (retryable via `_InstallFailed`) — testé `test_install_module_skipped_on_second_call` + `test_install_module_failure_not_marked_done_retryable`. Suite pytest complète → 442 passed / 0 failed (417 baseline + 25 nouveaux), 0 régression.

## Critères de la Refonte Prompts (Priorités 0 + 0-bis + 6 — F-44)
- [ ] Critère 141 : `UNIVERSAL_INVARIANTS` contient les 10 patterns universels numérotés (read-before-write, no whole-file rewrite, format d'édition formel, never assume library available, verify-after, approval gating, anti-boucle, concision, todo tracking, parallel tool calls) — testé `test_all_10_patterns_present`.
- [ ] Critère 142 : Les 2 marqueurs doctrinaux bonus sont présents dans les invariants — professional objectivity (`FACTUEL ET OBJECTIF`) ET defensive security (`SÉCURITÉ DÉFENSIVE`) — testé `test_key_doctrinal_markers_present`.
- [ ] Critère 143 : `ROLE_BLOCKS` définit les 9 rôles du graphe (router, architect, prompt_refiner, coder, coder_frontend, web_tester, judge, security, escalation) — testé `test_all_9_roles_defined`.
- [ ] Critère 144 : Chaque rôle porte ses marqueurs doctrinaux spécifiques (Judge : in-diff only + anti-nits + professional objectivity ; Security : OWASP + CVSS + defensive-only ; Architect : read-only + 5 axes ; Coder : type hints + verify-after ; WebTester : pyramide + AAA) — testé paramétré `test_role_contains_doctrinal_marker` (17 cas).
- [ ] Critère 145 : `build_role_header(role)` assemble rôle + invariants pour les prompts smolagents ; rôle inconnu → invariants seuls (robustesse, pas de crash) ; `with_invariants(role, doc)` assemble rôle + invariants + métier dans le bon ordre pour DSPy — testé `TestBuildRoleHeader` + `TestWithInvariants`.
- [ ] Critère 146 : Les 6 Signatures DSPy (Router/Architect/PromptRefiner/Security/Judge/Escalation) ont les invariants injectés dans leur `__doc__` via `__doc__ = with_invariants(...)` — mécanisme validé empiriquement (DSPy lit `__doc__` via metaclass, non écrasé) — testé paramétré `test_signature_has_invariants`.
- [ ] Critère 147 : `Finding` (models.py) est le schéma Pydantic de sévérité partagé par Judge et Security (`severity` critical/high/medium/low + `category` + `location` + `description` + `suggestion`) ; `CodeJudgeOutput` et `SecurityOutput` ont un champ `findings: List[Finding] = []` ADDITIF (défaut `[]` = rétro-compatible checkpoints + tests existants) — round-trip Pydantic validé — testé `TestFindingAndAdditiveModels`.
- [ ] Critère 148 : Suppression des ~180 lignes de nœuds smolagents DÉPRÉCIÉS (versions mortes de `execute_router_node`/`execute_architect_node`/`execute_security_reviewer_node`/`execute_code_judge_node` dans `nodes.py`, jamais appelées par `run_coding_workflow`) + imports morts nettoyés (`RouterOutput`/`ArchitectOutput`/`SecurityOutput`/`CodeJudgeOutput` retirés de l'import `nodes.py`) — vérifié par import (4 fonctions absentes, fonctions actives Coder/Tester/Worker/Reduce/Judge/Synth/Adversary préservées).
- [ ] Critère 149 : La suite pytest complète passe (0 régression, 482 passed = 442 baseline + 40 nouveaux `test_prompts.py`).

## Critères de Chrome DevTools MCP + validation visuelle (Priorité 14 — F-45)
- [ ] Critère 150 : `build_chrome_devtools_params()` retourne `StdioServerParameters` (command="npx", args contient "chrome-devtools-mcp@latest", "--isolated", "1280x800", "jpeg") si `CHROME_DEVTOOLS_ENABLED=1` ; `None` si `CHROME_DEVTOOLS_ENABLED=0` — testé `TestBuildParams`.
- [ ] Critère 151 : `CHROME_PATH` set → ajoute `--executable-path <path>` aux args ; `CHROME_DEVTOOLS_HEADLESS=1` → ajoute `--headless` ; absent par défaut (visible pour debug) — testé `test_chrome_path_ajoute_executable_path` + `test_headless_*`.
- [ ] Critère 152 : `chrome_devtools_tools()` yield `[]` si params None (désactivé) OU si `ToolCollection.from_mcp` lève (Chrome absent/réseau down) — pas de crash, dégradation gracieuse — testé `TestChromeDevtoolsToolsDegration`.
- [ ] Critère 153 : `chrome_devtools_tools()` yield la liste des outils MCP si connexion OK — testé `TestChromeDevtoolsToolsMocked::test_connexion_ok_yield_outils`.
- [ ] Critère 154 : `wrap_screenshot_tools()` wrap UNIQUEMENT les outils `take_screenshot`/`puppeteer_screenshot` (pas les autres), capture l'image PIL retournée dans le holder, préserve le comportement original (retourne quand même l'image) — testé `TestWrapScreenshotTools` + `TestScreenshotCapture`.
- [ ] Critère 155 : `make_screenshot_callback()` peuple `memory_step.observations_images` avec le dernier screenshot, reset le holder après push, noop si holder vide — testé `TestScreenshotCallback`.
- [ ] Critère 156 : `list_mcp_servers_status()` inclut l'entrée `chrome-devtools` (name + transport="stdio" + configured reflète l'état) — testé `TestMcpStatusDiagnostic`.
- [ ] Critère 157 : `_is_web_task()` détecte le web via `router_lang` OU extensions des `target_files` (.html/.htm/.css/.js) ; false pour Python — testé `TestCoderWebDetection`.
- [ ] Critère 158 : `_build_devtools_blocks()` retourne ("","") si pas d'outils DevTools (backward-compat) ; block preview + doc outils si web+outils dispos ; doc seule si non-web+outils — testé `test_build_devtools_blocks_*`.
- [ ] Critère 159 : Skill `devtools-preview` routé pour les tâches web (regex frontend-design), absent pour Python ; son body se charge depuis `skills/devtools-preview/SKILL.md` — testé `TestSkillRouting`.
- [ ] Critère 160 : Suite pytest complète passe (0 régression, 521 passed = 493 baseline + 28 nouveaux test_chrome_devtools_tool + 1 mis à jour test_skills_and_mcp).

## Critères de la Checklist de fonctionnalités + Fixes robustesse GPU-local (F-46)
- [ ] Critère 161 : `extract_functionalities(spec)` parse la section `## Fonctionnalités attendues` en liste Python (regex), s'arrête à la prochaine section `##`, dédoublonne — testé `TestExtractFunctionalities`.
- [ ] Critère 162 : Robustesse — spec vide/prompt brut/section sans puces → `[]` (fallback historique, pas de crash) — testé `TestExtractRobustesse`. Insensible casse/accents (Fonctionnalité/Fonctionnalités).
- [ ] Critère 163 : `build_checklist_block(funcs)` produit un bloc qui compte les N exigences, numérote 1..N, impose un tableau verdict (PASS/FAIL/N-A), et rappelle « 1 FAIL = failure » — testé `TestBuildChecklistBlock`.
- [ ] Critère 164 : Le WebTester importe et injecte `checklist_block` dans son prompt après le cahier des charges — testé `TestTesterInjection::test_web_tester_importe_le_module`.
- [ ] Critère 165 : `AUDIT_PARALLEL=false` (défaut) séquentialise Tester PUIS Security ; `AUDIT_PARALLEL=true` restaure le `asyncio.gather` — vérifié par lecture code workflows.py:554-575.
- [ ] Critère 166 : `max_steps` Tester = 12 (GPU-local, anti-explosion contexte observée à 24 steps/405k tokens) — testé `test_run_max_steps_12`.
- [ ] Critère 167 : Skill `coding` contient la règle anti-TypeScript (tableau syntaxes interdites : `: type`, `as`, `: void`, `interface`) avec exemples — vérifié par lecture skill.
- [ ] Critère 168 : Skill `devtools-preview` met `list_console_messages` OBLIGATOIRE AVANT `take_screenshot` (le screenshot seul ne révèle pas un JS cassé) — vérifié par lecture skill.
- [ ] Critère 169 : Skill `web-tester` contient la règle des 2 essais (conclure FAILURE vite sur bug réel, ne pas explorer 15 sélecteurs) — vérifié par lecture skill.
- [ ] Critère 170 : Suite pytest complète passe (0 régression, 535 passed = 521 baseline + 14 nouveaux test_requirements_checklist).

## Critères du Re-test ciblé + Git diff (F-47, F-48)
- [ ] Critère 171 : `should_use_targeted_retest(iter, refs)` active le mode ciblé si iter>1 ET refs non vides ; sinon mode complet — testé `TestShouldUseTargeted`.
- [ ] Critère 172 : `extract_bug_points(refs)` extrait les réfutations (plus récentes d'abord, tronquées à max_chars) ou None si vide — testé `TestExtractBugPoints`.
- [ ] Critère 173 : `build_targeted_retest_block(bugs, iter, git_diff)` produit un prompt ciblé (max_steps 6, assertions par bug, smoke-test, section diff si fourni) — testé `TestBuildTargetedRetestBlock` + `TestTargetedRetestWithDiff`.
- [ ] Critère 174 : Le web_tester a un max_steps ADAPTATIF (TARGETED_MAX_STEPS=6 ciblé, 12 complet) et remplace checklist_block par targeted_block en mode ciblé — testé `TestWebTesterIntegration`.
- [ ] Critère 175 : Le workflow propage `refutations` (brutes) et `git_diff` dans sub_dict pour le Tester — testé `TestWorkflowPropagation`.
- [ ] Critère 176 : `init_run_git()` crée un .git local (idempotent) ; `commit_iteration()` commit après Coder — testé `TestInitRunGit` + `TestCommitAndGetDiff`.
- [ ] Critère 177 : `get_last_diff()` retourne git diff HEAD~1..HEAD (vides si <2 commits ou git absent) ; tronque au-delà de max_chars avec marqueur — testé `TestDiffTruncation` + `TestRobustesse`.
- [ ] Critère 178 : Skill coding contient la règle CSS `height: %` (failure mode isolation #1 : barres invisibles) — vérifié par lecture skill.
- [ ] Critère 179 : Suite pytest complète passe (0 régression, 563 passed = 551 + 12 nouveaux test_git_snapshot).

## Critères du Static Tester déterministe (F-49)
- [ ] Critère 180 : `extract_inline_js(html)` extrait le JS des `<script>` SANS `src` (ignore les externes) — testé `test_extract_inline_js_*`.
- [ ] Critère 181 : `_check_js_syntax` lance `node --check` et détecte TS-in-vanilla (`: type`, `as Cast`) → SyntaxError — testé `test_ts_annotation_in_script` + `test_ts_as_cast_in_script`.
- [ ] Critère 182 : `_check_event_wiring` flagge un contrôle interactif (button/input/select) avec id mais AUCUN handler (le piège n°1 : slider non branché, indétectable par screenshot) — testé `test_slider_not_wired`.
- [ ] Critère 183 : Tolérances wiring légitimes : onclick inline, `<button type=submit>` en form, `<a href>`, `<input type=hidden>` — testés `test_*_not_flagged`.
- [ ] Critère 184 : Tier 2 DevTools détecte les éléments créés en JS mais INVISIBLES (height=0 = bug CSS height:% sur conteneur sans hauteur), APRES déclenchement de l'action primaire (clic bouton start) — testé `test_invisible_bars_height_percent`.
- [ ] Critère 185 : Dégradation `node` absent → Tier 1a skip silencieux (pas d'échec faux, le LLM Tester prend le relais) — testé `test_node_absent_degrades`.
- [ ] Critère 186 : Dégradation Chrome absent/opt-out → tier_reached="tier1" (Tier 2 skip, Tier 1 reste actif) — testé `test_tier2_skipped_when_devtools_off`.
- [ ] Critère 187 : Non-HTML pass-through (target `.py` → success immédiat, le Static Tester est web-only) — testé `test_non_html_passthrough`.
- [ ] Critère 188 : Opt-out `STATIC_TESTER_ENABLED=0` désactive le nœud (pass-through) ; `STATIC_TESTER_DEVTOOLS=0` désactive le Tier 2 seul — testés `test_opt_out_flag_disables` + `test_devtools_disabled_still_runs_tier1`.
- [ ] Critère 189 : Le workflow intègre le Static Tester entre le Linter et le Tester LLM, avec court-circuit (réfutation DuckDB + continue) sur failure — vérifié par lecture workflows.py.

## Protocole d'Évaluation
* Tests unitaires : `uv run pytest tests/ -v` → zéro échec.
* Validation process : `uv run python -m graph_orchestrator.workflows` (WORKFLOW_MODE=coding) →
  vérifier que le workflow aboutit (Architect→Coder→Tester→Judge) et produit les 3 fichiers.
* Vérification livrable : `ls landing_page/` (3 fichiers) + inspection HTML (non corrompu).

