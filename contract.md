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

## Protocole d'Évaluation
* Tests unitaires : `uv run pytest tests/ -v` → zéro échec.
* Validation process : `uv run python -m graph_orchestrator.workflows` (WORKFLOW_MODE=coding) →
  vérifier que le workflow aboutit (Architect→Coder→Tester→Judge) et produit les 3 fichiers.
* Vérification livrable : `ls landing_page/` (3 fichiers) + inspection HTML (non corrompu).

