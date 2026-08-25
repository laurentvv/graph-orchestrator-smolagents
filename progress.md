# État d'Avancement du Sprint

## Objectif Actuel : F-171 (vérificateurs déterministes du Coder) — branche feat/f-171-coder-verifier-hooks, puis run E2E v6 outillé
> **Mandat user (session 2026-08-25 PM, post-run v5 arrêté)** : « GO F-171 et
> relance un vrai run bien outillé ». Run v5 arrêté manuellement à T+71 min
> (DuckDB #3739) : F-170 validé en live (crash Coder iter1 → continuation +
> evt #3737), mais itération 2 en rituel visuel lent (40 pas, ctx 12,4 K)
> sans verdict ; script.js iter2 portait le bug `init()` (récursion infinie →
> `RangeError` au chargement — invisible au lint, prouvé en live via Chrome
> headless stderr) ; finding d'assertion du Tester lossy partout.
> **F-171 (GO user A+B après revue références)** : (A) capability
> pydantic-ai `Hooks` `after_tool_execute` sur les outils d'écriture →
> `lint_file`+`check_js_syntax` sur le seul fichier écrit, findings
> CONSULTATIFS au retour d'outil (pattern aider `lint_edited`, Hooks NATIFS
> confirmés dans pydantic-ai 2.33.0 installé) ; (B) smoke Chrome headless
> `--dump-dom --enable-logging=stderr` (file://, 0 serveur, 0 LLM) au chemin
> verdict F-170 : tour correctif borné 5 req (run réussi) + injection des
> findings réels dans le sauvetage post-budget. Settings
> `CODER_STATIC_VERIFY`/`CODER_SMOKE_VERDICT` (défaut on, fail-open).
> SUITE : PR + merge → **run E2E v6 outillé** (revalidation golden #19 §10
> toujours en attente — v5 n'a pas rendu de verdict).

## Jalons de l'Itération (cycle F-171 — vérif déterministe post-écriture + smoke verdict, 2026-08-25 soir)

- [x] F171-1 : Post-mortem v5 (base>log, DuckDB #3739) + revue références —
      pydantic-ai 2.33.0 a des Hooks NATIFS (`after_tool_execute` filtre
      `tools=`+`timeout=`, modifie le résultat) ; aider : `lint_edited`
      (auto-lint ON par défaut, fichiers édités seulement, erreurs
      réinjectées) + `auto_test=False` par défaut (coûteux) → design A+B
      validé ; open-swe/opencode : rien d'exploitable.
- [x] F171-2 : Validation LIVE du détecteur B avant de coder — Chrome
      headless stderr sur le livrable buggé v5 : `Uncaught RangeError …
      (script.js:25)` capté en 1,8 s ; page saine silencieuse (1,0 s) ;
      `file://` OK sans serveur HTTP.
- [x] F171-3 : `graph_orchestrator/coder_verifier.py` — (A) `build_verifier_hooks`
      (Hooks, filtre append_file/search_replace/multi_replace, timeout 15 s,
      sync=worker thread, DuckDB coder/verify, fail-open) + `run_static_verify`
      (lint_file + check_js_syntax, cap 5×220 c) ; (B) `run_smoke_check`
      (Chrome jetable user-data-dir temp, virtual-time-budget 4 s, parser
      console 2 formats CONSOLE:25/CONSOLE(0), familles critiques seules,
      dedup) + `resolve_smoke_targets` (même normalize_tool_path que les
      écritures).
- [x] F171-4 : Câblage — `build_coder_agent` appose la capability ;
      `_run_agent_with_budget_salvage` gère le smoke aux 2 chemins de verdict
      (tour correctif `_SMOKE_FEEDBACK_PROMPT` borné 5 req + injection
      `_BUDGET_SALVAGE_PROMPT`) ; `run_coder_pydantic` résout les cibles ;
      config `coder_static_verify`/`coder_smoke_verdict` + .env/.env.example.
- [x] F171-5 : Tests `tests/test_f171_coder_verifier.py` **24 PASS**
      (parser ×5 dont ligne EXACTE run v5, intégration RÉELLE FunctionModel
      advisory apposé/silencieux, live Chrome récursion flaggée, salvage ×6)
      + régression F-168/F-170/guards 62 PASS ; contract C549-C552 +
      feature_list F-171 + ce fichier.
- [ ] F171-6 : Suite complète 0 échec → commit + PR → merge (GO user direct)
      → **run E2E v6 outillé** (vigie : marqueurs `[F-171]`, verdict attendu
      <45 min, test navigateur livrable si approbation → MAJ §10).

## Jalons de l'Itération (cycle docs — refonte README + doc technique, 2026-08-25)

- [x] Docs-1 : Point d'avancement complet (167 features : 148 completed /
      17 cancelled / 2 pending F-87+F-119, 0 in_progress ; migration
      pydantic F-169 TERMINÉE = moteur unique ; run E2E v5 lancé 13:53 EN
      COURS en parallèle — non touché). README.md refondu (épuré : badges,
      highlights tableau, quick start, pipeline Mermaid, golden runs
      condensés + note d'honnêteté #19 invalidé/F-167, statut projet) ;
      profondeur technique déplacée vers docs/TECHNICAL_DOCS.md (13
      sections F-xxx : gardes, compaction v2/v3, F-170, MTP F-123, pool
      F-163, KG F-68, migration pydantic, isolation) ; info périmée
      CODER_ENGINE/TESTER_ENGINE retirée (moteur unique depuis F-169).
      Branche feat/readme-refresh → PR.

## Jalons de l'Itération (cycle F-170 — continuité graphe + verdict post-budget, 2026-08-25 après-midi)

- [x] F170-1 : Branches + DuckDB #3645 ; lecture doc pydantic-ai usage
      limits (règle F-157) : `capture_run_messages` capture même sur
      exception (état partiel), `message_history` + `UsageLimits` frais par
      appel — pattern sauvetage validé AVANT de coder.
- [x] F170-2 : (α) coder_pydantic.py — `_BUDGET_SALVAGE_PROMPT` +
      `_run_agent_with_budget_salvage` (helper testable) ; run_coder_pydantic
      délègue, None propre si sauvetage raté ; imports redondants purgés.
- [x] F170-3 : (ε) workflows.py — continuation sur mort Coder (synthèse
      CoderOutput honnête, plus de return) + journalisation DuckDB
      coder/error ; import CoderOutput en tête.
- [x] F170-4 : (budget) CODER_MAX_STEPS 40→60 (config défaut + load_settings
      + .env + .env.example, règle §7) ; test défaut mis au nouveau contrat.
- [x] F170-5 : Tests ×10 PASS (11 s) + suites voisines 86 PASS ; contract
      C545-C548 + feature_list F-170 + ce fichier.
- [x] F170-6 : Suite complète 2131 passed / 0 échec (580 s) → DuckDB #3733
      + commit 212f55d + PR #124 → **MERGÉE (197854c, feu vert user direct)**,
      branche supprimée, retour main. Revalidation E2E (run v5) : session
      suivante.

## Jalons de l'Itération (run de revalidation v4 + post-mortem, 2026-08-25 midi)

- [x] v4-1 : Lancement run E2E (DuckDB #3642) + vigie 5 min TOUT VERT :
      marqueurs `Coder (pydantic)` présent / `LoggedOpenAIServerModel` absent,
      draft 4 944 o gate F-91/F-167 PASS, caps F-168 jamais sollicités.
- [x] v4-2 : Run terminé T+30 — ÉCHEC technique `UsageLimitExceeded`
      (`CODER_MAX_STEPS=40` consommés en 27 min, 146 K tokens générés,
      40 tours, contexte borné 8-12 K — aucune pathologie des runs 24/08).
- [x] v4-3 : Post-mortem base>log (règle §8.2) — base MUETTE (0 evt),
      diagnostic via log llama-server (40 prompt evals ; cycles 8→12 K =
      rituel visuel ~5 tours répété) + lecture du livrable.
- [x] v4-4 : Test navigateur du livrable (Chrome MCP + `http.server 8791`,
      refermés — hygiène §7) : compteur 425 = comparaisons RÉELLES →
      F-167 validé au niveau livrable (1re fois que le bug golden #19 ne
      se reproduit pas) ; bug marquage `.sorted` confirmé en live.
- [x] v4-5 : Fixes F-170 FAITS (cf. cycle F-170 ci-dessus) : (α) budget
      Coder + verdict arraché ; (ε) continuation après mort Coder ;
      observabilité coder/error ; compaction F-159 priorité BAISSÉE
      (contexte borné naturellement sur chemin pydantic) ; run_id par
      exécution (backlog a) restant ouvert.

## Jalons de l'Itération (cycle F-169 — moteur unique pydantic + gardiens DSPy, 2026-08-24 nuit)

- [x] F169-1 : Vérification moteurs réels des runs du jour (marqueurs
      uniques `[T] Tester (pydantic)` / `Coder (pydantic)` vs
      `LoggedOpenAIServerModel`) : 1835 et 2223 = 100 % smolagents ; le
      print « Tester mode: » existait des deux côtés (faux signal corrigé).
- [x] F169-2 : `execute_coder_node` (nodes.py) → délégation unique
      `run_coder_pydantic` (branche smolagents CodeAgent SUPPRIMÉE, -408
      lignes) ; `WebTestRunner.run` (web_tester.py) → délégation unique
      `run_tester_pydantic` (409 → 32 lignes) ; settings `coder_engine`/
      `tester_engine` retirés de Settings + load_settings ; `.env`/
      `.env.example` purgés (ENGINE + CODER_PREFILL_CODE).
- [x] F169-3 : Gardiens DSPy (`dspy_nodes.py`) : `_last_raw_completion`
      (fenêtre `lm.history[hist_before:]` : parse-fail ≠ transport) +
      `_extract_dspy_section` + `_dspy_structure_rescue` (champ pydantic →
      cascade `extract_and_validate` F-168 ; champ str unique → section ou
      réponse entière — un draft Drafter non parsé reste un plan valide) ;
      câblés dans `_run_dspy_node` en except → rescued ou raise.
- [x] F169-4 : Tests — `tests/test_f169_engine_guards.py` ×13 (rescue ×6,
      sections ×2, history ×3, retrait moteur ×2) + classes dispatch
      réécrites (`TestCoderEnginePydanticOnly` ×3,
      `TestTesterEnginePydanticOnly` ×2) + 7 tests re-pointés vers les
      sources pydantic (web_tester_functional ×3, targeted_retest ×2,
      requirements ×1, plan_files ×1 — le prompt-building vit dans
      tester_pydantic/coder_pydantic).
- [x] F169-5 : Suite complète verte → DuckDB (#3594) + commit + PR #123 →
      MERGÉE (Kilo PASS, 2026-08-25) → run E2E relancé (cf. run v4 ci-dessus).

## Jalons de l'Itération (cycle F-168 — sauvetage borné + cap no-think, 2026-08-24)

- [x] F168-1 : Diagnostic post-mortem run 1835 — (a) rescue `models.py:311`
      sans max_tokens NI timeout (serveur accepte l'infini) → génération en
      fuite 7172+ tokens/25 min ; (b) règle « mets null si absent » viole les
      champs requis str/Literal → ValidationError string_type DANS le
      sauvetage ; (c) 2e mode d'échec JSONAdapter parse fail ; (d) Tester
      pydantic + ULTRA à `REASONING_MAX_TOKENS=16384` sur le 9B no-think 5,4
      t/s → pire cas ~50 min. DuckDB #3440 (post-mortem) + #3443 (feat).
- [x] F168-2 : `models.py` — `_fill_required_defaults` (Literal→"failure"
      fail-closed, str→"", int/float→0, bool→False ; optionnels et types
      inconnus intacts) + passe déterministe AVANT le sauvetage LLM + `dspy.LM`
      borné (1200/300 s/temp 0.0) + signature `fixed_json` texte brut avec
      extraction défensive `{...}` + remplissage post-parsing.
- [x] F168-3 : `config.py` setting `no_think_max_tokens` (défaut 4096) +
      `load_settings` NO_THINK_MAX_TOKENS + `.env.example`/`.env` synchronisés
      (règle §7) ; câblé `nodes.py:_select_coder_spec` (ULTRA) et
      `tester_pydantic.py:build_tester_agent` (ModelSettings).
- [x] F168-4 : Tests — 13 nouveaux (`tests/test_f168_rescue_bounds.py` :
      remplissage ×4, passe déterministe ×3 dont le verdict EXACT du run 1835,
      LM borné + fixed_json ×2 via fake dspy, cap ×4) + 2 historiques mis au
      nouveau contrat (`test_extract.py` absent→récupéré/incompatible→None ;
      `test_tester_pydantic.py` cap no_think).
- [x] F168-5 : Suite complète **2111 passed / 7 skipped / 0 échec** (passe
      finale, après mise au contrat du fixture ULTRA `test_coder_hardening` —
      SimpleNamespace sans `no_think_max_tokens`) → état disque + DuckDB
      (#3440, #3443, done) + commit + PR → review Kilo.

## Jalons de l'Itération (cycle F-167 — densité prescriptive du Drafter, 2026-08-24)

- [x] F167-1 : Diagnostic A/B isolation (`debug/run_drafter.py`, sous-tâche
      exacte du run 1448) : Ornith-1.5 (18,7 s) ET Ornith-1.0 (17,1 s) → draft
      creux IDENTIQUE 1231 o ; vérifié rétroactivement : TOUS les runs depuis
      2026-08-22 17:32 (Ornith-1.0, pré-1.5) clonent le même draft 1260 o.
      Cause racine : FORMAT DE SORTIE creux de `DrafterSignature` copié à la
      lettre par les 2 modèles. DuckDB #3247 (démarrage) + #3248 (diag).
- [x] F167-2 : Prompt `DrafterSignature` durci (dspy_nodes.py) : RÈGLE
      CRITIQUE n°4 « PRESCRIPTION PAR VALEURS EXACTES » (variables CSS
      `nom: valeur` — liste de noms = thème mort ; hauteur % ⇒ parent px ;
      hex/N/plages/délais ; sémantique d'incrément des compteurs), 2
      anti-pièges nouveaux (% sans référent ; compteur = comparaisons ≠
      échanges — encode le bug du golden #19 au niveau plan), FORMAT DE
      SORTIE réécrit DENSE (`:root` avec valeurs, `height 240px`, `N = 30`,
      `comparisons++` avant le test de swap). Docstring 73 lignes / 5228 c.
- [x] F167-3 : `draft_gate.py` — 2 checks de densité (0 LLM) :
      `css_vars_no_values` (ligne listant ≥2 `--var` dont une ni valuée sur la
      ligne ni définie ailleurs ; usages `var()` exclus ; références prose à
      des variables définies ailleurs tolérées) + `pct_height_no_parent`
      (contexte hauteur/% sans AUCUN px dans le plan) ; kinds retryables via
      `DENSITY_REJECT_KINDS` + `build_density_feedback`. Câblés dans
      `check_draft` (§2bis).
- [x] F167-4 : `workflows._drafter_with_density_retry` — un rejet de densité
      réexécute le Drafter AU PLUS 1 fois avec le feedback appendé à une COPIE
      de `sub_dict` (contenu du Coder jamais pollué) ; rejets structurels et
      crash = zéro direct F-91 historique ; call site du workflow allégé.
- [x] F167-5 : Faux positif `flex_column_bars` (F-124) corrigé — le draft
      dense du run C (body en colonne + `#board` row/flex-end) était rejeté à
      tort par le matching global (column + flex:1 + contexte barres n'importe
      où). Check par BLOC désormais : règle CSS (sélecteur → `}`) ou ligne
      prose ; la colonne doit partager le bloc du contexte barres.
- [x] F167-6 : Tests — **18 nouveaux 0-LLM PASS** (`tests/test_f167_drafter_
      density.py` ×16 : détection ×8 avec embeddings des drafts RÉELS 1448 +
      golden #19, feedback ×3, retry ×5 via fake `execute_drafter_node`
      (retry unique, non-pollution, crash, rejet structurel sans retry) ;
      `tests/test_draft_gate.py` +2 : faux positif body-column/board-row +
      variante prose du bug run #14). Suite complète verte (cf. DuckDB).
- [x] F167-7 : Validation A/B/C isolation : C = Ornith-1.5 × prompt durci →
      draft dense 4851 o / 56 lignes (`:root` complet hex, `#board height
      240px` « référent des % », `comparisons++` SYNCHRO avant sleep, init
      robuste) qui PASSE le gate. Artefacts : `debug/drafter_isolation_out/
      f167_ab_{A,B}_*` + `f167_runC_ornith15_hardened.md` (913 s think+gén).
- [x] F167-8 : État disque (contract C534-C537, feature_list F-167,
      NODES_AND_SKILLS §2.1 ligne Drafter + note F-167, ce fichier) + DuckDB
      + commit + PR → review Kilo.

## Jalons de l'Itération (cycle F-166 — auto-fixer au Coder, 2026-08-24)

- [x] F166-1 : État disque amorcé (feature_list F-166 in_progress, contract
      C530-C533) + branche `feat/f-166-autofixer-coder` + événement DuckDB
      #3168 (aucun run actif — vérifié process).
- [x] F166-2 : `search_replace_utils.py` — (a) `decode_literal_escapes` :
      décode `\n` en position séparateur de code + `\t` en tête de ligne ;
      `\n` légitime dans une chaîne affichée INTACT (regex séparateur ne
      matche pas). (b) **Regex F-132 unifiée** : elle vivait en 3 copies
      (tools.py garde + auto_fixer.py repair + …) → domicile canonique
      `CODE_SEPARATOR_NL_RE` ici, les 2 modules importent — l'outil ne peut
      pas rejeter ce que le décodeur décode. (c) **RelativeIndenter** (port
      fidèle aider :18-171, marqueur ←) : subtilité découverte au test — la
      dent de 1re ligne du bloc encode son indentation ABSOLUE, celle de la
      cible un DELTA → joker sur la 1re dent + préservation de la dent cible
      (ré-indentation correcte), fenêtres alignées sur les paires (index
      pair). (d) `_fuzzy_line_window_replace` : équivalent difflib stdlib de
      `dmp_lines_apply` (0 nouvelle dépendance), DERNIER recours gardé :
      ratio ≥ 0.75 (3 lignes identiques sur 4 = vrai cas valide, 0.8 trop
      strict), marge ≥ 0.05 sur le 2e meilleur, ≥ 4 lignes non vides ;
      `last_note` (attribut de fonction) signale les stratégies créatives au
      message de succès. Fuzzy SequenceMatcher caractères d'aider NON porté
      (désactivé en amont chez aider, piège documenté).
- [x] F166-3 : `tools.py` — `_f166_effective_args` : arguments EFFECTIFS par
      édition, brut prioritaire (pattern de réparation F-133 : old cite la
      séquence fautive du fichier corrompu — testé non-régressé), chaque arg
      décodé INDÉPENDAMMENT seulement si nécessaire (old absent du fichier,
      new fautif garde F-132), gardes réévaluées sur les effectifs (no-op
      décodé → rejet explicite « même après décodage … NO-OP »). Câblé sur
      search_replace/edit_file/multi_replace + write_file/append_file
      (content décodé si la garde le jugeait fautif ; rejet résiduel = double
      échappement). Directive P2 `_post_edit_syntax_directive` apposée au
      retour d'append_file (dernier outil d'écriture sans diagnostic — le
      pattern write_file(squelette)+append_file(JS) expose ses SyntaxError à
      la seconde ; testé avec l'erreur EXACTE du run 0857 : « Identifier
      'startBtn' has already been declared » détectée à l'append).
- [x] F166-4 : `fix_known_error` (F-133, ex-Tester-only) exposé au Coder des
      DEUX moteurs : liste `coder_tools` nodes.py + custom tools
      coder_pydantic.py + étape « MECHANICAL ERRORS » dans les prompts de
      validation (smolagents + pydantic). Effet de bord : numérotation des
      steps pydantic décalée d'une unité — test F-161 mis à jour (documenté).
- [x] F166-5 : Tests — **31 nouveaux 0-LLM PASS** (tests/
      test_f166_coder_autofix.py : decode ×5, RelativeIndenter ×4, fuzzy ×6,
      effective_args ×4, intégration outils ×8, exposition ×3) dont
      `test_run0857_trap_decoded_and_applied` = le cas EXACT du run 0857. **4
      tests F-132 mis à jour au nouveau contrat** (le littéral n'est plus
      rejeté mais décodé+appliqué — changement volontaire C530) + 2 tests
      no-op décodé ajoutés. Suite complète **2079 passed, 7 skipped, 0
      échec**. Gate F-103 : **1 erreur PRÉEXISTANTE** AG001 (AGENTS.md 19 614
      octets > limite 16 384 — apportée par la doc PR #119 §10 enrichie, NON
      touchée par F-166 ; à traiter par un condensé dédié).
- [x] F166-6 : **Validation isolation `debug/run_coder.py` GO** — exécution
      1 (génération from scratch, ~54 min GPU, 33+ steps : 3 fichiers
      index.html 1 866 o / styles.css 3 429 o / script.js 4 840 o, boucle de
      correction CSS saine, AUCUN rejet de garde ni activation auto-fix
      nécessaire — encodage propre cette fois, la non-régression est le
      point) + exécution 2 MODE CORRECTION it.2 (215 s, 2 steps, visual_check
      6/6, CoderOutput success natif, linter_ok/vision_ok True, stall
      detector tiré mais final_answer valide → succès conservé F-88) ;
      livrable vérifié : node --check OK, 0 var CSS orpheline ; pool
      navigateur + llama-server shutdown propres (0 résiduel).
- [x] F166-7 : État disque (contract C530-C533 cochés, feature_list F-166
      completed, NODES_AND_SKILLS §2.2 « Auto-fixers du Coder », README
      §guardrails, CODE_PUR_ROADMAP P2/P3 marqués PORTÉS) + DuckDB + commit +
      PR → review Kilo.

## Jalons de l'Itération (cycle F-165 — intégrité de l'enregistrement des verdicts)
> Né du post-mortem du run 021543 (F164-6) : le graphe a rejeté un livrable sur
> un échec Tester ARTEFACT et lancé une correction aveugle. Chaîne prouvée en
> base (règle base>log, AGENTS.md §8.2) : Tester step 5 code-mode →
> `write_file(probe1.js)` interdit par l'interpréteur pydantic
> (« InterpreterError: Forbidden function evaluation ») → max_steps sans verdict
> structuré (Pydantic + sauvetage DSPy échoués) → fallback dont le scan FAIL
> classait l'EN-TÊTE « Code execution failed… » comme assertion en échec de
> l'app (absent des marqueurs F-127) → snippet `[:300]` amputé avant
> l'exception → Judge fail-closed au feedback générique → wrapper workflows.py
> ré-empilait des blocs déjà embarqués → réfutation KG claim 255 dupliquée.

- [x] F165-1 : Fix A (nodes.py) — marqueur « code execution failed » ajouté à
      `_TESTER_TOOL_ERROR_MARKERS` + exclusion PAR BLOC des `step.error` (si
      une ligne du bloc porte une signature d'outil, tout le bloc sort du scan
      FAIL ; sémantique atomique : une erreur = un événement d'outil).
- [x] F165-2 : Fix B (nodes.py) — snippet du verdict failure = segment
      « due to: … » extrait dans une fenêtre de 4 lignes depuis la première
      ligne FAIL (même ligne ou lignes suivantes), sinon la ligne FAIL entière,
      cap 300 AVEC ellipsis explicite.
- [x] F165-3 : Fix C (feedback_utils.build_rejection_feedback + workflows.py)
      — si final_feedback contient déjà 🎯 CAUSE RACINE + 🛠️ INSTRUCTION
      (signature fail-closed dspy_nodes), passage tel quel ; sinon assemblage
      historique (Judge LLM normal) ; None → message historique inchangé.
- [x] F165-4 : Tests — **12 nouveaux 0-LLM PASS** (tests/
      test_f165_recording_fixes.py) dont `test_run21543_write_file_block_not_
      a_fail` reproduisant l'erreur EXACTE du run 021543 ; F-127 (16 tests) en
      régression verte.
- [x] F165-5 : État disque (contract C527-C529, feature_list F-165, ce
      fichier) + DuckDB (#3030 feat, done à suivre) + commit + PR.

## Jalons de l'Itération (cycle F-163 — pool navigateur run-scoped : un seul Chrome par run)
> Né de l'E2E F-162 (2026-08-23) : 4 serveurs MCP navigateur/itération, la
> fermeture stdio ne tuait JAMAIS l'arbre cmd→npx→node→Chrome sous Windows
> (2 Chromes orphelins, ~12 process fuis/run, tués à la main). Décision user
> 2026-08-23. Contrainte structurante découverte : stdio = 1 session par
> process → partager L'INSTANCE serveur entre mcpadapt (smolagents) et fastmcp
> (pydantic) est impossible → le pool porte le CHROME (le coût froid/leaky),
> tous les serveurs s'y connectent via `--browserUrl` (option officielle).

- [x] F163-1 : `graph_orchestrator/browser_pool.py` — singleton ancré au run
      (`configure_run` idempotent, supersède l'arbre précédent), Chrome unique
      (port libre + user-data-dir temporaire ≡ --isolated), health /json/version
      + respawn, PID racine au registre reaper F-140 (crash-safe), taskkill
      /T /F + sweep automation (marqueur `--remote-debugging-pipe` jamais sur
      le Chrome perso, baseline à la création, fail-safe PowerShell), shutdown
      auto au dernier release en standalone (debug F-89), repli historique
      exact si KO. 0 nouvelle dépendance.
- [x] F163-2 : Façades DEUX moteurs — `build_chrome_devtools_params(browser_url)`
      (--browserUrl ajouté, --isolated/--executable-path retirés),
      `chrome_devtools_tools` (Coder smolagents + Static Tester + Tester
      smolagents gratuits), `open_coder_mcp`/`open_tester_mcp` (lease spannant
      le nœud, appels sans kwargs si inactif — compat stubs), `watch_spawn`
      autour du repli puppeteer (lance son PROPRE Chrome → arbre capturé pour
      le kill final).
- [x] F163-3 : Câblage — `run_coding_workflow` wrapper try/finally (corps →
      `_run_coding_workflow_inner`, ancrage après run_id, shutdown garanti sur
      exception) ; config `BROWSER_POOL_ENABLED` (défaut 1) +
      `BROWSER_POOL_SPAWN_TIMEOUT_S` (30) + .env/.env.example.
- [x] F163-4 : Tests — **40 nouveaux 0-LLM/0-réseau PASS** (tests/
      test_browser_pool.py : état ×12, primitives Windows ×9, gating pytest/
      sweep ×3, params ×2, façades ×6, workflow ×2) ; 2 leçons de sûreté
      payées en direct : (a) détection pytest À L'APPEL (à l'import
      PYTEST_CURRENT_TEST n'existe pas → l'atexit sweep avait tué 3 arbres
      réels à la sortie de la première suite — corrigé : sweep INTERDIT sous
      pytest + baselines à la création) ; (b) bug réel trouvé par test :
      root_pid posé AVANT kill dans le chemin « Chrome pas prêt » (sinon
      fuite du spawn raté). Suite complète re-vérifiée post-compat (stubs
      mono-arg des tests existants préservés) ; gate F-103 29 surfaces
      0 erreur 0 warning.
- [x] F163-5 : **Validation live `debug/run_browser_pool.py` — 12/12 PASS** :
      spawn unique (port 53563) + health OK, façade smolagents 29 outils
      lisant la page témoin SUR le Chrome du pool, re-lease SANS respawn
      (Chrome chaud), façade pydantic --browserUrl lisant la MÊME page,
      shutdown → PID racine mort + zéro chrome automation résiduel.
- [x] F163-6 : État disque (contract C524-C526, feature_list F-163 completed,
      ce fichier) + DuckDB + commit + PR.

## Jalons de l'Itération (cycle F-158 — phase 3.1-3.2 : Coder pydantic en production)
> Premier incrément PRODUCTION du plan : le socle commun × profil Coder derrière un
> flag réversible (CODER_ENGINE), le moteur smolagents reste le défaut inchangé.

- [x] F158-1 : Module `graph_orchestrator/coder_pydantic.py` — FileSystem 8 tools
      (expected_hash ≡ ReadGate structurel, protected patterns ≡ io_guard) + 9 custom
      tools déléguant aux canoniques tools.py (gardes F-132/F-95/P2 conservées) +
      `output_type=CoderOutput` (fini extract_and_validate + sauvetage DSPy) +
      UsageLimits ≡ coder_max_steps + escalade Ultra F-111 conservée +
      ClearToolResults/ToolOutputLimits du spike.
- [x] F158-2 : Instructions système/user séparées (cache-friendly) — rôle + invariants
      + protocole tool-calls natifs + stratégies + mode correction + skills eager
      (budget F-103). Écart documenté : devtools-preview SUSPENDU sans outils
      navigateur (un skill qui documente des outils absents induit le modèle en
      erreur) — flip prévu phase 3.5/3.6.
- [x] F158-3 : Aiguillage `CODER_ENGINE=pydantic|smolagents` dans execute_coder_node
      (config + .env.example + .env ; valeur inconnue → warning + repli smolagents).
- [x] F158-4 : `debug/run_coder_pydantic.py` → appelle la VRAIE fonction production
      (convention F-89, 0 mock) — contrôles livrable 8/8 + CoderOutput natif.
- [x] F158-5 : Tests — 31 nouveaux 0-LLM/0-réseau PASS (instructions ×13, user
      prompt ×4, délégation tools ×6, assemblage Agent ×3, aiguillage ×4) ;
      suites voisines 85 passed ; py_compile OK ; gate F-103 29 surfaces 0 erreur
      (AGENTS.md préexistant > hard limit : condensé §4, warning soft uniquement).
- [x] F158-6 : Validation A/B isolation GPU (2026-08-23, run1) — **GO 8/8** :
      CoderOutput validé nativement (status=success, task_id exact, linter_ok=True),
      3 fichiers 22,4 Ko (strict mode + init robuste + câblage OK), **68,2k in /
      7,1k out / 583 s** — mieux que le spike (131,6k in) et -82 % vs baseline
      smolagents (384k in / 533 s). Caveat documenté : vision_ok=True non audité
      (gate vision = phase 3.3/3.6).
- [x] F158-7 : État disque final (contract C501-C504 cochés, feature_list F-158
      completed, README §Hands, ce fichier) + DuckDB + commit + PR.

## Jalons de l'Itération (cycle F-159 — phases 3.3-3.4 : gardes & contrôle + contexte/mémoire)
> Deuxième incrément PRODUCTION du plan de migration : le socle commun × profil
> Coder reçoit les gardes comportementales (boucles, stall, idle, preuves, retries)
> et la compaction contextuelle — sur les seams officiels du harness (hooks,
> SystemReminders, TieredCompaction), pas des répliques maison.

- [x] F159-1 : Module `graph_orchestrator/coder_pydantic_guards.py` —
      `ToolGuardsCapability` (LoopGuard v2 : fingerprint tool+args+RÉSULTAT vol
      crush, fenêtre 10, nudges 3/5, GuardAbort propre à 8 ; StallDetector F-88
      par réutilisation de compute_material_fingerprint + exemptions F-151 ;
      churn d'édition ; gels navigateur F-125/129 en détection générique),
      `IdleBreakerCapability` (F-61), `GoalGateCapability` (preuves autoritaires
      F-99, continuation ModelRetry native 1× puis waive), `ReviveRetryCapability`
      (F-104 : classify_llm_error maison + revive llama-server + échange
      request_context.model au changement de port).
- [x] F159-2 : Nudges → SystemReminders DYNAMIQUES (build_guard_reminders) :
      injection en queue derrière CachePoint, pop-once, JAMAIS dans
      message_history (finit la pollution memory_step.observations) ; GoalReanchor
      natif ; wind-down F-131 + checklist F-114 dérivés de run_step × audit
      visuel. F-130 remplacé par DeduplicateFileReads (plan §3.4) ; multifences/
      r-string F-150 obsolètes (tool-calls natifs).
- [x] F159-3 : Compaction (build_compaction_capabilities) : TieredCompaction
      ciblé 26k (parité preflight F-116) — Clamp 30k chars → ClearToolResults
      keep_pairs=3 → Summarizing (si COMPACTION_LLM_ENABLED) sinon SlidingWindow ;
      DeduplicateFileReads standalone chaque requête ; WarnNearLimits.
- [x] F159-4 : Câblage — `CODER_PYDANTIC_GUARDS` (défaut true ; false =
      comportement F-158 exact, ClearToolResults standalone) ; build_coder_
      capabilities ordonnée (ReviveRetry EN TÊTE = wrap externe) ; run_coder_
      pydantic capture GuardAbort → échec propre distinct d'un crash.
- [x] F159-5 : Tests — **39 nouveaux 0-LLM/0-réseau PASS** (loop ×6, stall ×3,
      churn/gels ×5, idle ×2, goal gate ×3 avec continuation ModelRetry PROUVÉE,
      revive ×5, reminders ×4, compaction ×3, assemblage ×3, intégration ×2 dont
      rejeu du scénario de gel : boucle d'édition stérile → nudges 3/5 injectés
      AVANT GuardAbort à 8 à travers le VRAI build_coder_agent) ; suites voisines
      139 passed ; **suite complète 1858 passed / 0 failed / 7 skipped** ; gate
      F-103 29 surfaces 0 erreur ; py_compile OK.
- [x] F159-6 : Validation GPU isolation ×3 runs (2026-08-23) — **non-régression
      PROUVÉE par A/B ON/OFF** : gardes ON run1 6/8 (52,2k in / 5,6k out /
      528 s) + run2 7/8 (50,1k / 4,7k / 441 s) vs gardes OFF run3 7/8 (50,3k /
      5,6k / 513 s) — CoderOutput success NATIF ×3, zéro GuardAbort parasite,
      zéro fausse continuation GoalGate, tokens/durées identiques. Les contrôles
      livrable échoués (JS strict mode 3/3, init robuste 1/3) échouent AUSSI
      sans gardes → variance du 4B (l'invariant est bien dans
      UNIVERSAL_INVARIANTS des deux moteurs ; F-158 run1 8/8 = tirage chanceux) ;
      livrables fonctionnellement valides (node --check OK, listeners câblés).
      Le barème 8/8 du script d'isolation mesure la qualité livrable du modèle,
      pas la non-régression des gardes — arbitrage réel = Static Tester/Judge.
- [x] F159-7 : État disque final (contract C505-C508, feature_list F-159
      completed, README §Hands, ce fichier) + DuckDB + commit + PR.

## Jalons de l'Itération (cycle F-164 — gardes d'écriture pydantic + design déterministe)
> Sixième incrément PRODUCTION, né du post-mortem E2E F-162 (3 gardes tools.py
> contournées par le write_file du FileSystem harness + livrable design
> défaillant) et de la demande user « boucle d'itération Coder jusqu'à ce que
> ça soit le mieux ». Doc consultée AVANT (règle §5) : le seam officiel est
> ToolGuardrail (harness/guardrails « Tool calls »).

- [x] F164-1 : `build_write_guardrail` (coder_pydantic_guards) câblé
      INCONDITIONNELLEMENT dans build_coder_capabilities — `guard` PRÉ-exécution
      (block : F-10 vide/placeholder, F-126 anti-réécriture >100 lignes avec
      orientation search_replace, F-164 remplissage data-viz : width fixe <40px
      sans flex/calc OU cap max-width <60px défaisant flex:1 ; min-width bénin) +
      `result_guard` POST-exécution (replace : directives var() CSS + remplissage
      apposées aux résultats d'écriture .css, logique canonique tools.py,
      find_undefined_css_vars/_find_narrow_fixed_widths extraites en pures).
- [x] F164-2 : Static Tester Tier 1 « [CSS VARS] » (agnostique moteur — le bug
      Times New Roman de l'E2E, var(--font-*) indéfinies, attrapé pour les DEUX
      moteurs ; anti-FP cross-fichiers <style>/setProperty) + skill
      frontend-design : règles COMPLÉTUDE var() (fallback DANS les parenthèses)
      et REMPLISSAGE (flex:1/calc, largeurs fixes étroites interdites).
- [x] F164-3 : Tests — **23 nouveaux 0-LLM PASS** (guard ×10 dont F-126/F-10/
      cap/fail-open, result_guard ×4 dont preuve transport directive, [CSS
      VARS] ×3 sans FP, câblage inconditionnel ×1, directive pure ×3, skill ×1,
      intégration in-process FunctionModel + VRAI FileSystem ×1) ; suite
      complète re-vérifiée post-changements ; gate F-103 29 surfaces 0 erreur ;
      contrat F-159 test_guards_off_exact_f158 mis à jour (précédent F-161).
- [x] F164-4 : **Boucle validation Coder ×6 runs GPU — CONVERGENCE prouvée** :
      run1 GO 10/10 → runs 2-4 `width:30px` récidive (42 % remplissage DOM) →
      garde largeur fixe → run5 loophole `flex:1+max-width:40px` (49 % mesuré,
      le modèle obéit à la lettre en gardant le cap) → garde anti-cap →
      **run6 : remplissage ✓ var() ✓ — 97 % de remplissage + Segoe UI MESURÉS
      DOM LIVE** (vs 42-49 % + Times New Roman avant gardes), success natif
      766 s / 226 k in ; restent strict mode + init robuste = variance 4B
      documentée F-159→F-161 (hors périmètre). Hiérarchie des leviers mesurée :
      skill 1/4 < directive soft 0/1 (ignorée alors que le canal est PROUVÉ
      in-process) < blocage pré-exécution 2/2. Contrôle design du script
      d'isolation unifié sur _find_narrow_fixed_widths (DRY).
- [x] F164-5 : État disque (contract C521-C523, feature_list F-164 completed,
      ce fichier) + DuckDB + commit + PR.
- [x] F164-6 : Validation E2E post-merge — **TENTÉE 2026-08-24 (runs 0209/021543)
      et INVALIDÉE** : essai 1 mort serveur mid-run (respawn OK côté serveur mais
      5 retries client « Connection error » < latence 1ʳᵉ réponse post-revive) ;
      essai 2 coupé sur décision user après découverte d'un run FAUSSÉ par le
      maillon d'enregistrement (réfutation KG dupliquée/tronquée/mensongère →
      correction aveugle) — voir F-165. Pool F-163 et garde CSS F-164 validés
      positivement au passage. **Re-validation requise sur main mergé F-165.**

## Jalons de l'Itération (cycle F-162 — phase 3.7 : runner web du Tester sur le socle pydantic)
> Cinquième incrément PRODUCTION du plan de migration : le runner web du Tester
> passe sur le MÊME socle que le Coder (F-158→F-161) par configuration fine —
> pas une seconde migration. Les 4 premiers runs GPU ont produit 3 leçons
> structurelles (budget requêtes ×2, AbstractCapability sous-classée,
> wind-down Tester) avant les 2 GO finaux.

- [x] F162-1 : Module `graph_orchestrator/tester_pydantic.py` — modèle
      `no_think_spec` (Ornith 9B multimodal) ; `open_tester_mcp` (chrome-devtools
      + 12 helpers DOM + **Puppeteer MCP** [repli documenté] + Context7,
      dégradation INDIVIDUELLE par serveur) ; custom tools lecture seule
      (read_file/list_directory) + fix_known_error F-133 déléguant aux
      canoniques — PAS de FileSystem en écriture (le Tester teste, il ne
      réécrit pas) ; prompt compacté F-152 en instructions natif tool-calls
      (skills devtools-preview PRÉ-COLLÉ garanti + web-tester toujours +
      budget F-103 + resources inlinées F-97 ; doc outils/vision/puppeteer
      conditionnées aux flags réels) ; user prompt variable (spec OU re-test
      ciblé F-47/F-52, checklist F-46 priorité critères Architect F-82, URLs
      file:/// exactes sur le PREMIER fichier cible) ; `output_type=CoderOutput`
      natif ; timeout wall-clock asyncio.wait_for + UsageLimitExceeded propre.
- [x] F162-2 : Socle paramétré sans casser F-159 — IdleBreaker
      `action_hint=` (vocabulaire Tester), WarnNearLimits ancré budget
      requêtes (param `max_steps=`), `build_tester_reminders` (GoalReanchor +
      4 nudges, SANS checklist/wind-down Coder ; wind-down TESTER ≤6 requêtes
      restantes : verdict honnête > timeout) ; PAS de GoalGate (preuves F-99
      sans objet pour un nœud qui ne produit pas de livrable) ; vision F-161
      et ToolGuards partagés ; `_ProgressPrintCapability` (AbstractCapability)
      imprime chaque tour (miroir verbosity smolagents).
- [x] F162-3 : Aiguillage `TESTER_ENGINE=pydantic|smolagents` (défaut
      smolagents) dans WebTestRunner.run + config + .env/.env.example ;
      `debug/run_tester.py` isolation F-89 sur le livrable PARFAIT run #19
      avec scénarios nommés `ok`/`bug` (mutation compteur figé = bug
      historique F-110, invisible des gates déterministes).
- [x] F162-4 : Tests — **39 nouveaux 0-LLM/0-réseau PASS** (instructions ×9,
      user prompt ×5, custom tools ×4, processor Puppeteer ×2 [strippage
      filePath des DEUX pilotes], open_tester_mcp ×2 [dégradation puppeteer
      isolée], capabilities ×7 [sans GoalGate/FileSystem, hint idle, wind-down
      budget], assembly ×5 dont EXÉCUTION réelle TestModel [leçon run 2 :
      l'enregistrement des capabilities n'est prouvable qu'en exécutant],
      aiguillage ×4, run ×3 [timeout propre, mode ciblé TARGETED_MAX_STEPS×2,
      spawn mort]) ; suites voisines 218 passed ; **suite complète 1972
      effectifs passed / 0 failed / 7 skipped** (baseline 1933, 0 régression ;
      flaky minute-boundary test_e2e_resume_reuses_same_run_dir reproduit
      PUIS repassé sur MAIN via worktree propre = préexistant, sans
      interaction F-162) ; gate F-103 29 surfaces 0 erreur 0 warning.
- [x] F162-5 : Validation GPU isolation ×6 (2026-08-23) — **run 5 `ok` GO
      4/4** : CoderOutput success NATIF, 6/6 critères PASS avec preuves runtime
      mesurées (elapsed=4501ms, comparingNow→sorted, steppedNotInstant,
      startBtn disabled), 0 erreur console, 253 924 in / 1 758 out / 624 s /
      tour 11 — pas de faux rejet ; **run 6 `bug` GO 4/4** : failure DÉTECTÉ
      (compteur figé), zone mutée localisée script.js ~L78 (le marqueur
      artificiel du scénario lu via read_file a guidé la localisation —
      écart documenté : récit 9B fusionne compteur/swap, verdict + zone
      corrects), fix_known_error exercé ×2 (no-fix, test continué), 444 529 in
      / 2 080 out / 789 s / tour 19. Runs 1-4 = leçons : budget 1:1 épuisé
      (→×2), TypeError capability duck-typée (→AbstractCapability + test
      TestModel), timeout 1800 s sur exploration 26-30 tours à ~65 s/requête
      (→wind-down + anti-about:blank + plafond VALIDATION 2700 s via env ;
      .env production reste 1800 s — arbitrage E2E : monter le plafond OU
      resserrer le rituel). Leçons consignées doc notes §3.
- [x] F162-6 : État disque final (contract C517-C520, feature_list F-162,
      README §Hands, doc notes §3 leçon F-162, ce fichier) + DuckDB + commit
      + PR.
- [x] F162-7 : Validation E2E Bubble Sort complet (2026-08-23, run
      2026-08-23_1959, LES DEUX moteurs pydantic, interrompu à l'entrée
      itération 3 sur budget temps user — 1h25 vs objectif 30 min) — **GO
      migration / NO-GO temps**. Chaîne parcourue ×2 itérations :
      PromptRefiner→Router→Architect→Drafter→**Coder pydantic** (it.1 success
      474 s / 317 k in ; it.2 correction 40/40 requêtes → garde UsageLimits →
      échec PROPRE)→Linter→Static OK ×2→**Tester pydantic COMPLET it.1 :
      failure avec VRAI bug** (`for (let i=0; i<i+1; i++)` ligne 99, valeurs
      non triées observées, 633 k in / 1 342 s / tour 26)→Security→Judge
      fail-closed→feedback→**Tester pydantic CIBLÉ it.2 : fix confirmé**
      (« targeted fix works », boucle corrigée `i < n - 1`, isSorted=true) +
      échec honnête sur violations restantes (393 k in / 1 099 s / tour 16).
      **ARBITRAGE C520 RÉSOLU : TESTER_TIMEOUT_S=1800 SUFFIT** (les deux
      verdicts ont convergé sous le plafond : 1 342 / 1 099 s — le 2 700 de
      l'isolation était superflu ; aucune modif .env requise). Goulots temps :
      Coder it.2 correction thrash 30 min (40 requêtes — problème rituel
      correction 4B connu F-116), Tester complet 22 min. Découvertes
      latérales consignées : **F-163** pool navigateur run-scoped (fuite
      Windows des arbres npx/node/Chrome à chaque fermeture MCP — 4 spawns/
      itération, 2 Chromes orphelins observés user, tués manuellement) ;
      **F-164** garde variables CSS cross-fichiers au Static Tester (livrable
      rendu en Times New Roman : var(--font-*) indéfinies, la garde tools.py
      post-édition ne voit pas le write_file du FileSystem pydantic) + règle
      de remplissage barres dans la skill frontend-design (board occupé à
      48 % vs flex:1 au golden #19 — frontend-design ÉTAIT injectée, budget
      3 k/16 k tokens : variance d'application 4B, pas un manque de skill).

## Jalons de l'Itération (cycle F-161 — phase 3.6 : vision multimodale des screenshots)
> Quatrième incrément PRODUCTION du plan de migration : take_screenshot retourne
> l'image DANS le contexte du Coder pydantic (le modèle VOIT ses livrables,
> parité F-50 smolagents) et la purge perte-zéro F-101/F-116 migre sur le seam
> officiel ProcessHistory. Découverte en route : le render texte F-160 produisait
> str(bytes) (bruit hexadécimal) sur un retour image — l'image était non
> seulement invisible mais polluante.

- [x] F161-1 : Module `graph_orchestrator/coder_pydantic_vision.py` —
      `split_tool_result` (texte/images séparés, JAMAIS str(bytes)),
      `make_image_tool_return` ([note_texte, BinaryImage] = ToolResult
      multimodal valide), `purge_history_images` (keep=N dernières images
      vivantes, archives .transcripts/images/ + placeholder « [Screenshot
      archivé: …] », parts reconstruites NEUVES via dataclasses.replace —
      dataclasses pydantic-ai, PAS des BaseModel), `build_vision_capabilities`
      (ProcessHistory officiel, avant CHAQUE requête modèle).
- [x] F161-2 : Câblage MCP — `process_tool_call` retourne la liste mixte pour
      tout résultat contenant des images (générique, pas seulement
      take_screenshot) ; strippage filePath F-50/F-90 inchangé et PROUVÉ sur le
      même chemin vision ; `render_mcp_result` délègue à split_tool_result
      (fix garbage hexa) ; OpenAIChatModel sérialise nativement en message tool
      (texte + « See file <id>. ») + message user (« This is file <id>: » +
      data-URI base64) — décodé par le mmproj llama-server, même format que
      le chemin smolagents F-50.
- [x] F161-3 : Instructions — étape VISUAL CHECK (« the screenshot is attached
      to your context AS AN IMAGE: LOOK at it ») insérée au workflow (fix
      d'erreurs conservé, numérotation automatique cohérente des deux modes),
      critères visuels jugés « by LOOKING at your latest screenshot » ;
      caveat « text confirmation only » retiré en nominal, conservé si
      CODER_PYDANTIC_VISION=false. Config CODER_PYDANTIC_VISION (défaut true)
      + CODER_PYDANTIC_VISION_KEEP (défaut 1 ≡ F-101 « very last step's
      image ») + .env/.env.example.
- [x] F161-4 : Purge INCONDITIONNELLE (guards on ET off — elle protège le
      contexte du NOUVEAU flux image ; l'A/B passe par CODER_PYDANTIC_VISION,
      pas par les gardes ; contrat test F-159 mis à jour en conséquence).
- [x] F161-5 : Tests — **31 nouveaux 0-LLM/0-réseau PASS** (split ×6 dont
      régression anti-garbage, retour image ×3, process_tool_call vision ×4
      dont filePath strippé sur chemin image, purge ×7 dont multi-images par
      part (l'image gardée survit à la reconstruction) + non-mutation +
      idempotence, capabilities ×5, instructions ×4, intégration in-process ×2 :
      FastMCP ImageContent → VRAI MCPToolset → ToolReturnPart multimodal dans
      l'historique de l'agent + sérialisation OpenAIChatModel data-URI prouvée
      sur le profil llama-server exact) ; suites voisines 155 passed ; **suite
      complète 1933 passed / 0 failed / 7 skipped** (baseline 1902, 0
      régression) ; gate F-103 29 surfaces 0 erreur ; py_compile OK.
- [x] F161-6 : Validation GPU isolation ×2 (2026-08-23) — **GO vision** :
      run 1 Bubble Sort (banner vision F-161) : CoderOutput **success natif,
      vision_ok=True**, 254 537 in / 5 521 out / 613,5 s, 7/8 contrôles (échec
      unique « JS strict mode » = variance 4B documentée) ; run 2 MINI-TÂCHE
      INSTRUMENTÉE (`debug/trace_vision_f161.py`, miroir F-160 run3) : le 4B
      exécute navigate → console → take_screenshot à travers le toolset,
      **l'image jpeg 11 941 octets est extraite et injectée dans le contexte,
      et le modèle DÉCRIT le visuel avec précision perceptive** (« dark theme,
      purple #6c8cff accent, centered card, counter showing "0", rounded blue
      button "+1" » — couleur hex + état RUNTIME du DOM : impossible sans
      vision réelle), success 155 s / 115 360 in ; confirmation croisée
      llama-server : requête post-screenshot 986 tokens (vs 554-640 tours
      texte) ≈ ~900 tokens vision mmproj ; purge non déclenchée ce run
      (1 screenshot ≤ keep=1, comportement correct — purge prouvée tests ×7).
- [x] F161-7 : État disque final (contract C513-C516, feature_list F-161,
      README §Hands, doc notes §3 leçon F-161, ce fichier) + DuckDB + commit
      + PR.

## Jalons de l'Itération (cycle F-160 — phase 3.5 : MCP navigateur & doc)
> Troisième incrément PRODUCTION du plan de migration : les serveurs MCP du
> Coder (chrome-devtools + Context7) passent sur les seams officiels du
> harness — MCPToolset/fastmcp remplace ToolCollection.from_mcp + le patch
> mcpadapt, process_tool_call remplace le sous-classage Tool.

- [x] F160-1 : Module `graph_orchestrator/coder_pydantic_mcp.py` —
      `build_devtools_mcp_toolset` (StdioTransport npx délégué à
      agent_server.mcp, init_timeout ≡ chrome_devtools_connect_timeout_s,
      tool_error_behavior=retry) ; `build_context7_mcp_toolset` (HTTP +
      header API + RenamedToolset tirets→underscores pour la parité
      prompts/skills) ; `open_coder_mcp` (AsyncExitStack, dégradation
      INDIVIDUELLE par serveur — miroir F-104).
- [x] F160-2 : Transformations per-tool via `process_tool_call` (doc
      mcp/client) — strip filePath/file_path de take_screenshot/take_snapshot
      (F-50/F-90), sanitisation enum types de list_console_messages (F-127),
      enrichissement console F-126 (stacks get_console_message bornées 4/8 +
      directive read_file ciblée + anti-réécriture + état F-128
      _update_console_pending réutilisé) — logique importée de
      vision_callback (0 duplication).
- [x] F160-3 : 12 helpers DOM (F-72/F-145/F-155) en FunctionToolset — corps
      JS importés À L'IDENTIQUE de devtools_dom_tools (clampage, rejets
      identifiants, interpolation __TOKEN__ F-155, défaut probe_sort 180000).
- [x] F160-4 : Câblage — build_coder_agent accepte `toolsets=` ;
      browser_tools_available DYNAMIQUE (skill devtools-preview re-précollé
      sur tâche web, bloc LIVE VERIFICATION console-centrique avec caveat
      « take_screenshot = confirmation texte, vision = 3.6 », URL file:///
      absolue, critères visuels via sondes DOM + visual_check).
- [x] F160-5 : **DÉCOUVERTE PROD** (isolation run1 NO-GO 400) : pydantic-ai
      force `tool_choice='required'` → llama-server l'encode en GRAMMAIRE
      GBNF d'union des tools, qui casse au-delà de ~45-60 outils (matrice
      mesurée sur body capturé : 62 outils+required=400, 62+auto=OK,
      45+required=OK — F-159 passait avec 17). Fix : `tool_choice='auto'`
      quand des toolsets sont attachés (forçage comportemental conservé via
      PROTOCOL + IdleBreaker F-159). Scripts diagnostic conservés
      (diag_grammar_f160, replay_request_f160).
- [x] F160-6 : Tests — **44 nouveaux 0-LLM/0-réseau PASS** (args ×5,
      enrich console ×4, process_tool_call ×3, render ×4, toolsets ×5,
      helpers ×11, instructions ×6, assemblage ×3 dont tool_choice auto
      conditionné ; +2 review Kilo #111 : intégration helpers via VRAI
      MCPToolset in-process + direction name_map RenamedToolset prouvée
      par exécution — la suggestion inversée de Kilo a été réfutée par
      source+test) ; suites voisines 197 passed ; **suite complète 1902
      passed / 0 failed / 7 skipped** (baseline 1858, 0 régression) ; gate
      F-103 29 surfaces 0 erreur (AGENTS.md sous hard limit, warning soft
      préexistant) ; py_compile OK ; dépendance `fastmcp-slim[client]`
      ajoutée (extra mcp absent du harness 0.24.0).
- [x] F160-7 : Validation GPU isolation ×3 : run1 NO-GO → découverte
      grammaire (400) → fix → run2 **CoderOutput success natif** (97,4k in /
      5,6k out / 670 s, chrome-devtools + Context7 connectés, 7/8 contrôles
      livrable — l'échec unique « JS strict mode » = variance 4B déjà
      documentée F-159) → run3 mini-tâche INSTRUMENTÉE
      (`debug/trace_mcp_calls_f160.py`) : le 4B exerce navigate_page →
      take_snapshot ×2 → click ×2 → list_console_messages À TRAVERS le
      toolset pydantic (success 157 s). Écart restant assumé : vision
      multimodale (screenshots → contexte image) = phase 3.6. Artefacts
      d'isolation détrackés de git (commit accidentel F-159). État disque
      final (contract C509-C512, feature_list F-160, README §Hands, doc
      notes §3, ce fichier) + DuckDB + commit + PR.

## Objectif Actuel : Sprint F-149 à F-155 (Élimination des frictions, allégement des rituels, sondes, initialisation robuste et déblocage du goulot Tester)
- [x] F149 : Pré-injection directe du Draft dans le prompt Coder (suppression du DraftGate, Step 1 direct écriture).
- [x] F150 : Épuration des prompts & invariants universels (suppression des micro-règles périmées, traduction intégrale en anglais).
- [x] F151 : Exemption des outils de validation visuelle du StallDetector.
- [x] F152 : Compaction du prompt Tester en mode ciblé (passage de ~22k à ~8k tokens).
- [x] F153 : Sonde déterministe de contrôles interactifs & fuzzing live dans le Static Tester.
- [x] F154 : Invariants d'initialisation DOM robuste (anti-readyState complete) et complétude :root.
- [x] F155 : Goulot n°1 « hang Chrome/DevTools du Tester » résolu — c'était le serveur llama (spill VRAM ngl=99), pas Chrome.
- [x] F156 : Barres invisibles du run 2149 — garde [CHARGEMENT] du Tier 2 réparée (parsing) + signature flat élargie.

## Jalons de l'Itération (cycle F-156 — Tier 2 aveugle : parsing v2 + barres atrophiées)
> Post-mortem run E2E 2026-08-22_2149 (validation F-155) : livrable 50 barres de
> 4 px (hauteur % non résolue sur conteneur flex sans height définie) VALIDÉ à tort
> par le Static Tester, boucle Coder de 20 steps sur la contradiction « capture
> vide vs DOM sain », leçon injectée à l'itération 2. Diagnostic user-poussé :
> « comment aider Coder/Tester à trouver cette erreur » (2026-08-22 soir).
>
> - [x] F156-1 : CAUSE LIVRABLE — `bar.style.height = (v/max)*100 + '%'` ne
>      résout pas (#board flex sans height définie) → toutes les barres au
>      `min-height: 4px` (h_min=h_max=4, plus haute barre = 2% du conteneur,
>      contraste OK, hit-test OK : VRAIMENT invisible, pas un artefact).
> - [x] F156-2 : CAUSE GATE — le Tier 2 mesurait JUSTE (probe : count=50,
>      visible:0) mais `_parse_devtools_json` enrobe le dict v2 {before,after}
>      en [dict] (contrat Tier 3) → branche « ancien format liste » → before
>      jeté → garde [CHARGEMENT] morte en prod (test live run15 = toujours
>      skippé sous pytest). Fix : désenrobage explicite avant détection.
> - [x] F156-3 : SIGNATURE FLAT ÉLARGIE — l'ancienne exigeait pleine largeur
>      (bandes run #14) ; nouvelle : hauteurs quasi-égales ET (pleine largeur
>      OU maxH ≤ 25% hauteur conteneur) → attrape les barres atrophiées.
> - [x] F156-4 : PREUVE LIVE — replay Static Tester sur le livrable fautif :
>      `success` avant le fix → `failure [CHARGEMENT] 50 éléments .bar présents
>      au chargement mais AUCUN visible` après. Le run aurait été rejeté dès
>      l'itération 1 avec feedback exact (pas de boucle Coder, pas de Tester LLM).
> - [x] F156-5 : Tests — 4 nouveaux 0-Chrome (contrat parse, unwrap→[CHARGEMENT],
>      ancien format préservé, signature source) ; suite 77 passed / 7 skipped
>      (live), 0 régression. État disque + DuckDB + PR.
> - [ ] F156-6 : Validation E2E post-merge — le run 2026-08-22_2149 (~1h20,
>      interrompu user à l'itération 2) a validé F-155 en prod (prefill no-think
>      538 t/s vs 66 hier ; Tester navigate 51 s vs 281-305 s ; règle reload 5-ter
>      appliquée ; Tester LLM verdict FAILURE correct sur le board vide — aucune
>      fausse approbation) et a fourni le cas F-156 (itération 1 : Static valide à
>      tort, boucle Coder). Relancer un run complet : le Tier 2 réparé doit
>      rejeter ce livrable dès l'itération 1.

## Jalons de l'Itération (cycle F-155 — goulot Tester : spill VRAM LLM, sonde tri, isolation sondes)
> Diagnostic des 4 goulots structurels consignés (focus n°1 demandé user), correctifs
> appliqués sur feu vert (2026-08-22, branche fix/tester-vram-autofit-probe-isolation).
>
> - [x] F155-1 : DIAGNOSTIC PRÉCIS — le « hang Chrome » du Tester = 100% temps LLM.
>      Correspondance 1:1 steps ↔ timings llama-server (run 1732 : navigate_page 281,7 s
>      = 274,2 s prefill 66 t/s ; read_file 86 s = 100% LLM, zéro navigateur). Chrome nu
>      (MCP production, 0 LLM, `debug/bench_devtools_naked.py`) : navigate 0,68 s /
>      reload 0,14-0,20 s / evaluate 0,21 s / connexion 2,7 s. AUCUN blocage Chrome.
> - [x] F155-2 : CAUSE RACINE VÉRIFIÉE par bench A/B (`debug/bench_tester_vram.py`,
>      spawn production exact) — ngl=99 forcé (F-127) annule l'auto-fit → 9B+mmproj
>      laissent ~180 MiB VRAM → spill buffers en mémoire partagée → prefill 83-242 t/s
>      INSTABLE d'un spawn à l'autre (le 1342 t/s du 21/08 = chance de fragmentation ;
>      Ornith-1.0 tout autant lent aujourd'hui → pas le modèle/mmproj/ctx). Auto-fit :
>      prefill 576-679 t/s STABLE (gen ~7 t/s, compromis assumé user : stabilité d'abord).
>      ULTRA (goulot n°4) = même cause (serveur mesuré 74 t/s).
> - [x] F155-3 : `REASONING_NO_THINK_NGL=0` (.env + .env.example, F-127 inversé) ;
>      REASONING_NGL=99 conservé + avertissement (Architect gen-heavy, trancher sur bench
>      dédié si régression). Goulots n°2/#3 : sonde `probe_sort_state` (12e helper
>      DevTools Coder+Tester) — attente in-page bornée jusqu'au VRAI tri complété +
>      mesure de mouvement post-timeout → verdicts SORTED / IN_PROGRESS (pas un défaut) /
>      STATIC_UNSORTED (cassé). Validation LIVE livrable 1732 : SORTED_AFTER_WAIT à
>      144 s (le run concluant « non trié » à 60 s). Règle 5-ter prompt Tester : reload
>      (~0,2 s) entre sondes indépendantes + jamais de « non trié » sans verdict sonde.
> - [x] F155-4 : BUG PROD découvert en validation live — le MCP chrome-devtools REJETTE
>      les kwargs (« Unknown argument », prouvé dans le log 1732) : les 5 helpers F-145
>      paramétrés étaient cassés en prod depuis leur création. Refactor : interpolation
>      __TOKEN__ côté Python (ints clampés, identifiants validés avant interpolation) +
>      garde node --check sur les 11 snippets JS + test anti-placeholder résiduel.
> - [x] F155-5 : Validation — 30/30 test_devtools_dom_tools, 228 tests voisins PASS
>      (prompts, f127, vision_nudge, skill_resolve, chrome_devtools_tool, mcp_connect ;
>      + fix d'un assert F-150 préexistant cassé sur tree propre), py_compile OK, gate
>      F-103 : 29 surfaces, 0 erreur, 0 warning. État disque synchronisé + DuckDB + PR.

## Jalons de l'Itération (cycle E2E du 2026-08-22 soir — boucle run/fix/run, 4 fixes usine)
> 5 runs E2E bubble-sort-multifile-v6 (12:37 pré-session, 15:24, 15:40, 16:31, 17:32). Aucun verdict Judge :
> chaque échec a produit un fix mécanique committé (branche `fix/search-replace-replace-all`), validé en
> production sur le run suivant. Rapports : `analysis_report.md` (run 17:32), `analysis_report_run1540.md`,
> `analysis_report_run1631.md`.
>
> - [x] RUN 12:37 (tué extérieurement) → `search_replace(replace_all=)` (le 4B le passe spontanément) + alignement des 6 tests cassés par F-150/F-152 (commit 7439253 : chaînes traduites non resynchronisées).
> - [x] RUN 15:24 → doublon `FRESH_START` dans `.env` (la 2e entrée `false` écrasait la 1re) → reprise involontaire du checkpoint 12:37 ; `.env` dédoublonné.
> - [x] RUN 15:40 → garde déterministe VARIABLES CSS INDÉFINIES post-édition (`tools.py`) : styles.css sans `:root` = barres transparentes = 2×40 min de galère Coder + audit visuel halluciné. Preuve en production au run 17:32 : tirée au Step 2, corrigée au Step 3.
> - [x] RUN 16:31 → F-110-bis (`static_tester.py`) : le check (c) exigeait `textContent =` littéral après `comparisons++` → faux positif sur rafraîchi via helper (`updateComparisonCounter()`), itérations 2-3 brûlées, escalation 9B prématurée. Runs suivants : Static Tester OK d'emblée (2×).
> - [x] RUN 17:32 (le plus loin : Coder→Static OK→Tester→Security ; bug réel trouvé it.1 « height=0 », hang Chrome it.2) → tué à 81 min sur itération 3 pendant que le 9B ULTRA (steps 4-7 min) chassait un état de sonde contaminé (`sorted:false` sur livrable correct à la lecture).
> - [ ] **Goulots structurels identifiés (prochain sprint)** : (1) escalade CODER ULTRA 9B = 60-90 min/itération 3 — à borner (max_steps dédié ou budget temps) ; (2) hang Chrome/DevTools du Tester = 30 min perdues (timeout nœud 1800 s) — à diagnostiquer/réduire ; (3) contamination d'état entre sondes `evaluate_script` successives — le 9B juge un état muté par ses propres tests (isolation par reload ou fresh tab par sonde) ; (4) artefact `sorted:false` : sonde sans attente du tri animé (~95 s) — sonde déterministe attendrie ou tri instantané en mode test.

## Jalons de l'Itération (cycle F-154 — initialisation DOM robuste & complétude :root)
> Imposition d'invariants de code stricts pour éliminer les écrans vides au chargement et les styles transparents (2026-08-22).
>
> - [x] F154-1 : Invariant #6 dans `skills/coding/SKILL.md` imposant le pattern d'initialisation vérifiant `document.readyState`.
> - [x] F154-2 : Ajout de la règle d'initialisation DOM dans `ROLE_BLOCKS["coder_frontend"]` (`prompts.py`).
> - [x] F154-3 : Mise à jour de `DrafterSignature` (`dspy_nodes.py`) imposant l'initialisation robuste et la complétude du bloc CSS `:root`.
> - [x] F154-4 : Synchronisation des fichiers de suivi et vérification du budget de guidance (29 surfaces, 0 erreur).

## Jalons de l'Itération (cycle F-149 à F-152 — élimination des frictions & allégement des prompts)
> Élimination des frictions Coder/Tester, suppression définitive du péage DraftGate et allégement des invites système (2026-08-22).
>
> - [x] F149 : Pré-injection directe du contenu complet du draft (`draft_*.md`) dans `draft_instruction`, permettant l'écriture directe au Step 1 sans passer par un appel `read_file`.
> - [x] F150 : Traduction intégrale en anglais des invariants universels (`UNIVERSAL_INVARIANTS`), des 9 blocs de rôles (`ROLE_BLOCKS`), des prompts Coder et Tester (`nodes.py`, `web_tester.py`), et des skills essentiels (`coding`, `devtools-preview`), avec élimination des micro-règles obsolètes.
> - [x] F151 : Immunité des outils de vérification visuelle (`visual_check`, `take_screenshot`, `list_console_messages`, `probe_canvas_activity`, etc.) dans `StallDetector` pour éviter les faux positifs en phase de test.
> - [x] F152 : Compaction du prompt du Web Tester en mode ciblé (omission des spécifications globales redondantes) pour réduire l'empreinte token de ~22k à ~8k tokens.
> - [x] F149-F152 : Tests unitaires et d'intégration validés à 100%, agent guidance check (29 surfaces, 0 erreur).

## Jalons de l'Itération (cycle F-153 — sonde déterministe de contrôles interactifs & fuzzing live)
> Validation de la détection déterministe 0 LLM des contrôles interactifs orphelins (2026-08-22).
>
> - [x] F153-1 : Tier 1b statique — Détection des contrôles interactifs avec ID orphelins (boutons non branchés sans handler comme `pauseBtn`, `resetBtn` et sliders sans écouteur dynamique `sizeRange`, `speedRange`).
> - [x] F153-2 : Tier 4 live — Fuzzing exhaustif des clics de tous les boutons et dispatch d'événements `input`/`change` sur tous les sliders en headless Chrome pour capturer les exceptions runtime.
> - [x] F153-3 : Validation sur le livrable réel (4 anomalies détectées en 1 ms) et suite de tests unitaires (78 passed, 0 régression).
> - [x] F153-4 : Synchronisation des fichiers de suivi et journalisation DuckDB.

## Jalons de l'Itération (cycle F-148 — vérification effective de la mémoire cross-run)
> Vérification en conditions réelles lors du run E2E Bubble Sort multi-fichiers :
>
> - [x] F148-1 : Extraction déterministe depuis DuckDB (`graph_orchestrator.db`) des 8 leçons durables (`insight` et `escalation`).
> - [x] F148-2 : Injection effective du bloc `### LEÇONS DE RUNS PRÉCÉDENTS (mémoire cross-run)` dans le prompt système du Coder.
> - [x] F148-3 : Exploitation immédiate par le Coder (initialisation du tableau à 20 barres pour éviter le timeout, synchronisation explicite des compteurs DOM).
> - [x] F148-4 : Synchronisation des fichiers de suivi (`feature_list.json`, `contract.md`, `progress.md`) et journalisation DuckDB.

## Jalons de l'Itération (cycle F-147 — suppression définitive du ReadGate et simplification Coder)
> Validation totale de la simplification Coder post-test isolation (2026-08-22).
> Le ReadGate (F-67) imposait un péage de lecture préalable (read-before-write) qui
> bloquait l'agent et provoquait des boucles de procrastination, alors que les fichiers
> cibles sont déjà pré-injectés dans le prompt en itération > 1 (current_files_block).
>
> - [x] F147-1 : Retrait du middleware `ReadGate` dans `nodes.py:execute_coder_node`.
> - [x] F147-2 : Simplification des `UNIVERSAL_INVARIANTS` dans `prompts.py` (utilisation directe du contexte, édition directe sans péage).
> - [x] F147-3 : Validation en isolation Coder complète (`debug/run_coder.py`) : 14 steps, 0 erreur de syntaxe, 0 erreur console, 5/5 visual checks PASS, tous livrables conformes.
> - [x] F147-4 : Synchronisation des fichiers de suivi (`feature_list.json`, `contract.md`, `progress.md`) et DuckDB.

## Jalons de l'Itération (cycle F-116 — compaction résiliente + chunks + ponytail)
> PRIORITÉ 1 du backlog (gouvernance 2026-08-18). Le mur démontré des runs
> #13/#16 : thrash 772k-990k tokens/step (~24k/step), ~40 min perdues. Plan
> approuvé user : 4 volets (A déterministe kilocode, B branchement nodes,
> C LLM opt-in ex-F-86, D ponytail fiche 48 à la source). Validation E2E
> prévue sur bubble-sort-multifile-v6 (étalon run #11).

- [x] F116-1 : Diagnostic affiné (vérifié code, pas hypothèse) — le trou n°1
  n'est PAS les images (apply_image_purge F-101 déjà active pendant #13/#16)
  mais le **model_output** des CodeAgents : pensée + bloc de code complet
  (fichiers entiers à write_file) envoyé à l'API à chaque step, JAMAIS compacté
  par les 5 couches F-101 (qui ne touchent que observations). + purge totale
  `steps=[]` au boundary de retry (rituel visuel rejoué ×3) + zéro preflight.
- [x] F116-2 (volet A, compaction.py v3, 0 LLM) : `apply_model_output_clip`
  (steps anciens > 2000 chars clippés head 600/tail 250, version intégrale
  persistée `.transcripts/mo_step_*.txt`) ; `apply_image_purge` v2 perte-zéro
  (archive `.transcripts/images/*.png` + placeholder `[Screenshot archivé: …]`) ;
  `render_transcript_block` (chunks kilocode : trace bornée 3000 chars dans le
  marqueur de snip) ; `collect_dead_ends` (tombstones « CULS-DE-SAC » ex-F-86
  sans LLM) ; `apply_soft_retry_reset` (archive tout l'évincé, step-synthèse,
  queue 4 conservée clippée ; `drop_task_steps` au boundary car smolagents
  ré-appose un TaskStep frais à chaque run — agents.py:488) ;
  `estimate_history_tokens` + preflight kilocode needed() ×1.3 (> 26000 →
  escalade AVANT l'envoi).
- [x] F116-3 (volet B, nodes.py) : overflow → `_f116_compact_memory` (LLM
  opt-in d'abord, repli soft reset) au lieu du wipe ; boundary
  `COMPACTION_RETRY_MODE=soft` (défaut) / `hard` (historique) ; flag
  anti double-compaction ; OverflowGuard failure_drain inchangé.
- [x] F116-4 (volet C, ex-F-86 opt-in désactivé) : `compaction_llm.py` —
  branche les dormants F-101 (build_summary_prompt + select_head_recent) ;
  **CompactionBudget hermes enfin branché** (verdict sur usage provider réel,
  remboursement, breaker). Pas de Mermaid L2 ni cascade par score (documenté).
- [x] F116-5 (volet D, ponytail) : `PONYTAIL_LADDER` (7 rungs YAGNI) injecté
  via build_role_header pour coder/coder_frontend SEULEMENT (Architect épargné
  — il garde son NIVEAU GRAPHIQUE MAXIMAL F-124) + clause anti-sous-livraison
  (« minimal décrit le CODE pas le PÉRIMÈTRE : sous-fonctionnalité = ÉCHEC »).
- [x] F116-6 : Config (6 settings COMPACTION_*) + .env + .env.example ; gate
  F-103 : **29 surfaces, 0 erreur, 0 warning** (prompts.py ~23.8 Ko < soft
  24 Ko) ; py_compile 4 fichiers.
- [x] F116-7 : Tests — **45 nouveaux PASS** (`tests/test_compaction_f116.py` :
  purge v2 ×6, clip ×6, transcript ×4, dead-ends ×4, soft reset ×7, estimate
  ×2, preflight pipeline ×2, wiring nodes ×3, LLM compact ×7, ponytail ×4) ;
  suite complète **1757 passed / 0 failed / 7 skipped** (baseline 1712 + 45,
  0 régression ; flaky minute-boundary PASSÉ cette exécution).
- [x] F116-8 : État disque (contract C473-C481, feature_list F-116 completed,
  ce fichier, README) + DuckDB + commit + PR.
- [x] F116-9a : Run E2E #1 (2026-08-21_1337) INTERROMPU user ~80 min (97 steps) :
  F-116 validé côté compaction (0 mur, 24-35k/appel stable, 0 erreur transport,
  archives mo_step_*) MAIS goulot de convergence global diagnostiqué — 58 % du
  temps = 21 steps vision (36 navigations), churn 71 sr / 92 reads / 28 writes,
  livrable cassé (var(--bg) sans :root, suspicion ponytail n=1), CODER_MAX_STEPS
  48 laissant thrasher. Correctifs P0-P3 appliqués : steps 24, toggle
  PONYTAIL_ENABLED, nudge churn d'édition (5 échecs consécutifs → failure
  honnête), nudge budget vision (8 cycles max). Tests 152 ciblés PASS, gate OK.
- [x] F116-9b : Session « trouver le goulot » (runs #1→#6, 2026-08-21) — 6 runs,
  6 causes racines corrigées sur la branche (PR #102, review Kilo adressée) :
  (1) CODER_MAX_STEPS 48→24 + P2 nudge churn d'édition + P3 nudge budget vision ;
  (2) toggle PONYTAIL_ENABLED (off pour validation, bug :root disparu n=2) ;
  (3) garantie déterministe skill devtools-preview Coder+Tester (décision user —
  perdu par la sélection LLM Architect : golden #19 l'avait, runs ratés non) ;
  (4) faux positif detect_unbounded_while_in_js (bubble sort canonique flaggué,
  logique inversée conservative + wrapper dur/heuristique séparé) ;
  (5) validate_html_monofile n'exige plus un livrable monofichier (<script src>
  local légal si cible existe — la golden task EST multifichier) ;
  (6) FRESH_START purge les réfutations DuckDB (bugs fantômes des runs
  précédents réinjectés au Coder). Contrat C482-C485, 197 tests ciblés PASS.
- [x] F116-9c : Run #6 = itinéraire COMPLET pour la 1re fois (Coder convergé
  11 min → Static OK + HTTP 200 → Tester LLM → Security → Judge) ; livrable
  3 fichiers VALIDÉ PAR L'USER (visuel + fonctionnel), intact (iter2 morte
  avant écriture). ÉCHEC au critère 30 min (47 min) : goulot restant = Web
  Tester 80 s/step (max 387 s) tué par TESTER_TIMEOUT_S=1200 sans verdict →
  Judge fail-closed → iter inutile. Leviers : tester sur fast 4B, timeout
  1800, investigation du step 387 s.
- [x] F116-9d : CAUSE RACINE PERFORMANCE (post-run #6) — MTP+ngl99 déborde la
  VRAM 6 Go (contexte draft) → offload CPU silencieux du 9B → prefill 84 t/s
  (vs 1300+ sans MTP, golden 550-700) → le Tester à 80 s/step et la régression
  « trop de features » depuis le golden venaient de LÀ (swap b10472+F-123).
  Matrice bench 6 combos (CUDA 12.4/13.3, FA, MTP, ngl éliminatoires). Fix :
  MTP OFF sur les 2 specs 9B (1342 t/s prefill + 41 t/s gen). llama.cpp
  b10517→b10549 appliqué (validation complète). Doc §2 réécrite. Contract C486.
- [x] F116-9e : Run #7 (config saine post-MTP-off, ~96 min, interrompu user) :
  chaîne amont VALIDÉE (Coder convergent 10 min, vrai bug `speed` détecté par le
  Static Tester et corrigé it.2 — l'usine fonctionne, plus aucun faux positif ;
  prefill réparé : steps tester 5-20 s vs 80 s). GOULOT FINAL identifié : le
  rituel visuel du Web Tester (~20-25 min d'aller-retours DevTools SÉRIELS —
  step 1 seul = 351 s) dépasse TESTER_TIMEOUT_S=1200 → Judge SKIPPÉ fail-closed
  → REJET ×3. Mesure : le tester avait son verdict à ~1 525 s →
  **TESTER_TIMEOUT_S=1800** (une ligne) est le fix suivant ; au-delà, réduire le
  rituel (7 critères → échantillonnage) pour tenir un budget 30 min.
- [ ] F116-9 : Validation E2E bubble-sort-multifile-v6 (relance P0-P3, deadline
  30 min — échec si dépassé ; étalon
  run #11 : ~23 min, 14,3 M tokens ; critères : livrable complet, PAS de
  croissance ~24k tokens/step, zéro exceed_context_size, archives
  .transcripts/ présentes, ponytail visible dans le prompt Coder).

## Jalons de l'Itération (cycle F-145 — sondes de preuve de mouvement, post-mortem run #8)
> Origine : bug ghostY du run #8 (pièce Tetris dessinée à `(ghostY+r)` au lieu de
> `(currentPiece.y+r)` + `drawGhost()` cassé — AUCUNE animation de chute, invisible
> sur screenshot) trouvé par debug manuel Chrome DevTools ; la sonde canvas v1
> (400 ms fixes) était disponible au Tester et ne pouvait pas le voir (une chute à
> 800ms/row ne change rien sous 800 ms de fenêtre, et le compte de pixels peints
> ne bouge pas quand une pièce tombe). Décision user : porter la méthode en outils.

- [x] F145-1 : `probe_canvas_activity` **v2** — `window_ms` paramétrable (défaut
  2400, bornes 800-10000), hash RGB échantillonné (1 pixel/3), liveness `raf_per_s`
  (1 s dédiée) + `visibility` (anti-faux-positif onglet caché), verdicts
  ANIMATING/STATIC_PAINTED/INERT_EMPTY/NON_2D + flag `suspect_animation_broken`
  (boucle active mais rendu figé — la signature exacte du bug ghostY).
- [x] F145-2 : 4 nouveaux outils (pattern F-72, délèguent à evaluate_script,
  identifiants JS nus validés côté Python, rejet sans IO) — `expose_game_state`
  (variables top-level ×2 à 1,5 s → changed_over_1500ms), `instrument_calls`
  (comptage d'appels réels draw/gameLoop/moveDown), `dump_function_source`
  (toString() capé 1200 chars — c'est ainsi que le bug a été LU), `force_advance`
  (N appels d'update + état avant/après + state_changed).
- [x] F145-3 : Factory 11 helpers (7+4), Coder ET Tester en bénéficient (câblage
  inchangé). Règle **5-bis** prompt Tester (preuve de mouvement OBLIGATOIRE avant
  tout PASS jeu/animation ; STATIC_PAINTED + raf>0 = défaut majeur ; diagnostic
  instrument_calls → dump_function_source) + étape 6 du rituel visuel Coder.
- [x] F145-4 : Tests — 12 nouveaux + 2 mis à jour → `test_devtools_dom_tools.py`
  **23/23 PASS** ; suites voisines (prompts, F-127, chrome_devtools, vision_nudge,
  validation_criteria) **170 passed** ; suite complète **1712 passed / 0 failed /
  7 skipped** (documentés) ; py_compile 3 fichiers ; gate F-103 : 29 surfaces,
  0 erreur, 0 warning.
- [x] F145-5 : État disque (contract C468-C472, feature_list F-145, ce fichier)
  + DuckDB + commit + PR.
- [ ] F145-6 : Validation E2E (run ultérieur — idéalement Tetris : la règle 5-bis
  doit faire FAIL le livrable sans animation de chute).

## Jalons de l'Itération (cycle F-146 — durcissement Coder correction & pré-injection)
> Origine : analyse des boucles de blocage Coder en itération 2 (2026-08-22). Le Coder
> s'épuisait en appels read_file stériles ou subissait des blocages de péage.

- [x] F146-1 : ReadGate séquentiel (`record_write` met à jour le hash SHA256 du contenu
  au lieu de supprimer la mark, autorisant des éditions successives sans RuntimeError).
- [x] F146-2 : Reset déterministe F-141 (`mark_write_done` et `reset_read_supply`
  réinitialisent le compteur de lectures identiques lors d'une écriture sur disque).
- [x] F146-3 : Pré-injection automatique du code des fichiers cibles existants en
  itération > 1 (`current_files_block` dans `nodes.py`), éliminant le besoin de read_file.
- [x] F146-4 : Désactivation du péage par défaut `READ_BEFORE_WRITE_ENABLED=false` dans
  `config.py` et `.env`.
- [x] F146-5 : Harmonisation des règles de prompt (Règle 6 et OUTILS DISPONIBLES
  déverrouillent l'écriture libre sans interdictions contradictoires ; Invariants 1 & 2
  assouplis).
- [x] F146-6 : Tests — `tests/test_coder_hardening.py` + `tests/test_read_gate.py` (58/58 PASS),
  gate F-103 OK (29 surfaces, 0 erreur).
- [x] F146-7 : État disque (contract C487, feature_list F-146, ce fichier) + DuckDB.

## Jalons de l'Itération (cycle F-130/131 — post-mortem run 2026-08-20_1028 Tetris, session « run de 0 »)
> Objectif utilisateur : run Tetris de 0 → analyser/corriger si problème →
> relancer → validé si 0 erreur dans les logs. Run 2026-08-20_1028 (~65 min,
> FRESH_START post-swap llama.cpp b10509) : **failure « Coder crash »** — les
> 3 tentatives Coder meurent à « Reached max steps » en boucle de lectures
> stériles : TypeError console réelle (bag numérique vs SHAPES lettré,
> `drawNextPiece:653` donné par la stack F-126) poursuivie sur les MAUVAISES
> lignes (406-411 hallucinées) via ~25 read_file sans modification ; step 41
> forcé = encore un read_file → Pydantic KO → sauvetage DSPy → checklist 6/6
> non audités ×3 → circuit-breaker idle. Le livrable final appelle bien
> createGrid() mais garde le TypeError (vérifié Chrome : stack exacte 653).

- [x] F130/131-1 : Diagnostic 3 couches — (a) read_file EXEMPT du LoopGuard
  F-36 ; (b) Stall Detector F-88 ne hashe que les écritures ; (c) nudge F-114
  exige un screenshot (2 seulement pris). Aucune garde ne voyait la boucle
  d'investigation.
- [x] F130-2 : Nudge lectures stériles (`vision_callback._build_read_stall_nudge`)
  — compteur PAR FICHIER (code_action + tool_calls, path nommé/positionnel),
  modification → ré-arme, seuil 5 → directive AGIS (search_replace / re-test
  page / checklist+final_answer) ; reset par nœud, traverse les retries ;
  actif Coder+Tester ; fail-open.
- [x] F131-2 : Nudge wind-down budget (`_build_wind_down_nudge`) — remaining
  ∈ [1,5] + checklist incomplète → directive convergence stricte à chaque
  dernier step (fix minimal → console → screenshot → visual_check ×N verdict
  False honnête PERMIS → final_answer) ; sans état ; Coder uniquement ;
  fail-open.
- [x] F130/131-3 : Branchement `make_screenshot_callback` AVANT l'early-return
  capture + resets nodes.py (même bloc lifecycle F-114/125/128/129).
- [x] F130/131-4 : Tests — **16 nouveaux PASS** (TestReadStallNudge 8 +
  TestWindDownNudge 8), fichier `test_vision_nudge.py` 46/46 ; py_compile OK.
- [x] F130/131-5 : État disque (contract C453-C456, feature_list F-130/F-131
  completed, ce fichier) + DuckDB + commit 9178dc9.
- [x] F130/131-6 : Run E2E validation #2 (2026-08-20_1203, ~2 h) : **échec
  « Coder crash » identique** — 3×40 steps, mais cause racine PLUS PROFONDE
  découverte : le livrable avait un SyntaxError JS PERMANENT causé par un
  `\n` LITTÉRAL (backslash-n texte) inséré par search_replace r-string
  (ligne 143 constatée dans Chrome), et la « correction » du 4B était un
  NO-OP (old == new) accepté avec « Successfully edited » → boucle de fix
  invincible qu'aucun nudge ne pouvait briser. Nudges F-130/131 validés en
  câblage réel (agent smolagents + CallbackRegistry : fired=True), mais sans
  effet sur une boucle d'édition — preuve d'observabilité console ajoutée
  (prints « Nudge F-130/131 injecté »).
- [x] F132-1 : Gardes outil anti-\n littéral + anti-no-op (tools.py) —
  `_noop_rejection` (old==new exact rejeté) + `_literal_newline_rejection`
  (\n littéral en séparateur de code dans le texte INSÉRÉ, fichiers code
  uniquement, old_string libre pour la réparation, légitimes épargnés) sur
  search_replace/edit_file/multi_replace/write_file. Tests +10 (72 PASS
  cumulés avec vision_nudge).
- [x] F132-2 : État disque (contract C457-C458, feature_list F-132, ce
  fichier) + DuckDB + commit.
- [x] F133-1 (proposition utilisateur) : Auto-fixer déterministe pluggé au
  Tester — module auto_fixer.py (const réassignée → let prouvé ; \n littéral
  → repair, même regex que F-132) ; outil fix_known_error branché au
  WebTestRunner + consigne prompt (fix → reload+console → CONTINUE le test ;
  sinon verdict normal) ; 10 tests PASS, gate F-103 OK. État disque (contract
  C459, feature_list F-133) + commit.
- [x] Focus « code pur » (décision utilisateur post-run #6 stoppé ~2h40) :
  minage references/ par 2 agents → docs/references-audit/CODE_PUR_ROADMAP.md
  (26 patterns, P1-P7). Ports P2+F-134 (diagnostics syntaxe déterministes
  injectés dans l'output des 4 outils d'édition — port kilocode, cœur
  refactoré de check_js_syntax F-72) et P4+F-135 (repair \n fence-aware —
  port deer-flow). 63 tests ciblés PASS, gate F-103 OK, contract C460-C461.
- [x] Ports P1-P7 COMPLETS (décision utilisateur « on fait tout d'un coup ») :
  F-136 valideur HTML Tier 0 (OpenKB), F-137 cascade lignes-vides (aider),
  F-138 moniteur Jaccard résultats (deer-flow, nudge), F-139 heal_selector
  (Scrapling, 7e helper DevTools), F-140 reaper process (qm, registre disque
  + taskkill arbre + boot workflow). 30 nouveaux tests (test_codepur_ports +
  màj compteurs), static tester 90 passed, gate F-103 OK, contract C462-C466.
- [x] Run #7 (1817, stoppe it.3 sur decision, ~2h20) : chaîne QA COMPLETE
  1re fois (Coder→Linter→Static→Tester→Security→Judge fail-closed), console
  livrable VIDE 1re fois, 0 erreur transport. P2 1 frappe (const paire fix
  instantane), F-130 x8 (9B les IGNORE), F-99 + priorite final_answer OK.
  Analyse profonde (analyzer 14,8M tokens in / 57 steps Coder ; 2 parsing
  unterminated recupere par F-33-2 ; Static passe SILENCIEUX ; Tester coupe
  a 10 steps/900s EN decouvrant le vrai bug pause-au-chargement ; ULTRA =
  14x le MEME read_file(offset=525)).
- [x] F-141 (4 correctifs code pur) : (A) print succes Static, (B) garde
  sanitte plan Architect (200x80/6000x2400 detectes deterministement + retry
  correctif unique, px vs cellules distingues), (C) TARGETED_MAX_STEPS 16 +
  TESTER_TIMEOUT_S 1200, (D) plafond lectures identiques (3e refus + directive,
  reset par noeud). 8 tests, gate F-103 OK, contract C467. Entré dans
  feature_list.json sous **F-144** (2026-08-20, décision user) : le numéro
  F-141 était pris par l'entrée références deepseek-harness (union PR #98/#99).
- [ ] Relance run E2E (après décision utilisateur) — validation : 0 erreur
  dans les logs.

## Jalons de l'Itération (gouvernance backlog — grooming post-run #19, décision user 2026-08-18)

- [x] GOV-1 : Arbitrage des 18 features pending sur les besoins réels démontrés
  (mono-GPU, runs séquentiels, livrables vanilla, humain dans la boucle) —
  **3 chantiers conservés** : F-116 (compaction, PRIORITÉ 1, intègre F-86),
  F-119 (diff Judge merge-base), F-87 (qualification skills, intègre F-96).
- [x] GOV-2 : **14 features annulées** (statut `cancelled` + raison par
  description) : F-18/25/34/74/77/78/79/94/107/117/118/121 + fusions F-86/F-96.
- [x] GOV-3 : **F-61 clos** en `completed` — rôle permanent du méta-analyste
  (§8) établi et démontré à chaud (7 runs le 2026-08-18).
- [x] GOV-4 : Note de gouvernance en tête de `plan_usine_logicielle.md` (les
  cases ouvertes = journal d'idées historique ; source de vérité =
  feature_list.json). Compteur final : **105 completed / 14 cancelled /
  3 pending**.

## Jalons de l'Itération (cycle F-120 — plan.md + task.md, transposition planning-with-files)
> Décision utilisateur après revue de la spécification kilocode (3 itérations de
> plan : ConfigProtection + matrice permissions → profil plan Architect/Drafter
> → minimal) : « simplement un plan.md et un task.md basé sur plan.md », sur le
> modèle du skill planning-with-files (OthmanAdi) montré par l'utilisateur.
> Volets ConfigProtection/mode plan NON PORTÉS : l'Architect et le Drafter sont
> des nœuds DSPy sans AUCUN outil FS (dspy_nodes.py:730/:848) — la restriction
> est déjà par construction, il n'y a rien à bridER (kilocode en a besoin car
> son agent de planification est un agent outillé interactif).

- [x] F120-1 : Module `graph_orchestrator/plan_files.py` (0 LLM) —
  `build_plan_markdown` miroir fidèle de TOUT l'ArchitectOutput (critères
  visuels/fonctionnels/rubric F-82 et skills F-57 inclus — rien de perdu,
  vérifié champ par champ), `build_task_markdown` (checklist vivante + journal
  daté des verdicts), `write_plan_files` best-effort, `build_coder_anchor`
  bloc court STABLE volontairement sans critères visuels (déjà injectés par
  le bloc F-82 — anti-redondance).
- [x] F120-2 : Config `plan_task_materialize` (défaut True, PLAN_TASK_MATERIALIZE)
  + `.env.example` + `.env` local.
- [x] F120-3 : Branchement `workflows.py` (helper `_sync_plan_files` à chaque
  transition : post-Architect/reprise, démarrage sous-tâche, coder KO, rejets
  linter/static, verdict juge, approbation, escalade, circuit breaker ; anchor
  dans `sub_dict` à chaque itération) + `{task.get('plan_anchor', '')}` dans le
  prompt Coder (`nodes.py`). Source de vérité INCHANGÉE (checkpoint F-24).
- [x] F120-4 : Tests — **24 nouveaux PASS** (23 test_plan_files + 1 config ;
  py_compile 4 fichiers ; gate F-103 : 29 surfaces, 0 erreur, 0 warning.
- [x] F120-5 : Suite complète (basetemp dédié F-95) — **1532 passed / 0 failed
  / 1 skipped** (flaky minute-boundary PASSÉ cette exécution) → 0 régression.
- [x] F120-6 : État disque (contract C443-C445, feature_list F-120 completed
  rescopé, ce fichier, README) + DuckDB + commit + PR #97.
- [x] F120-7 : **Run E2E #13 de validation exécuté (exigé user)** — run
  `2026-08-18_1130` (~80 min, 74,7 M tokens, 0/2, échec technique). **F-120
  VALIDÉ en prod** : plan.md miroir complet, task.md journal EXACT des 6
  transitions (démonstration post-mortem : c'est lui qui a reconstitué la
  chronologie), anchor 8× stable. Échec du run = 2 causes INDÉPENDANTES de
  F-120 (post-mortem complet `debug/POSTMORTEM_RUN13.md`) : (1) FAUX POSITIF
  Static Tester — sonde Tier 2 lit `backgroundColor` mais pas `background-image`
  → toute barre en linear-gradient sans texte = « invisible » (premier run E2E
  post-F-124 dont la validation avait été reportée) ; (2) TS-01 thrash rituel
  visuel 41 steps non convergé (pattern run #9) + timeouts 600 s finaux (10
  serveurs llama spawnés / 0 arrêt loggé — piste leak VRAM). Propositions P0-P3
  dans le post-mortem — **décision utilisateur attendue** (fix Static Tester
  en tête).
- [x] F120-8 : Fix Goal post-run #13 — `derive_goal` extrait la section
  `## Objective` de la spec F-115 (miroir parseur requirements_checklist F-51,
  rétrocompat `## Objectif`, repli texte brut) ; +5 tests → **28/28 PASS**.
- [x] F120-9 : **Session debug exigée user (« run final sans erreur et
  fonctionnel ») — 3 runs E2E le même jour** : #13 échec (faux positif
  gradient + thrash), #14 2/2 APPROUVÉES mais barres PLATES (géométrie du
  DRAFT column+flex:1, auto-approuvée par le rituel visuel), #15 **SUCCÈS
  COMPLET**. Fixes empilés : P0 sonde Tier 2 `backgroundImage` (preuve live
  livrable #13 : hidden AVANT=true/APRÈS=false) + print d'arrêt llama +
  CODER_MAX_STEPS 40→30 (f801716) ; puis 3 étages géométrie — draft_gate
  `flex_column_bars` REJECT, règle flex ROW prompt Architect (F-124 bis),
  sonde Tier 2 barres plates (preuve live #14 : flat_DETECTE=true) (b01fee4).
- [x] F120-10 : **Run #15 (2026-08-18_1717) = run final SANS ERREUR et
  FONCTIONNEL** : 1/1 approuvé itération 1 (24 min, 429k tokens, record),
  livrable 3 fichiers validé visuellement par chrome-devtools — 30 barres
  verticales proportionnelles (5,6→182px inline), gradient turquoise→violet,
  30/30 triées, compteur 225, dark theme. Post-mortem complet (épilogue
  #13→#15) : `debug/POSTMORTEM_RUN13.md`.
- [x] F120-11 : Suite complète post-fixes (basetemp dédié) — **1543 passed /
  0 failed / 5 skipped** (les 5 skips = tests live Tier 2 sans Chrome dans
  l'env pytest, documentés ; flaky minute-boundary PASSÉ cette exécution) →
  0 régression. Contract C446-C448 ajoutés. Cycle F-120 CLOS : PR #97
  contient feature + fixes de validation (F-120, F-49 sonde, F-91 gate,
  F-124-bis géométrie).
- [x] F120-12 : **Soirée de durcissement (runs #16→#19, feedback utilisateur
  en boucle visuelle)** : #16 échec propre (mur F-116, thrash 772k) ;
  #17/#18 succès graphe mais compteur FIGÉ en 2 nouvelles variantes F-110
  (littéraux purs, puis littéral avec mot) → checks (a-bis) v1+v2 « compteur
  statique » + (a) élargi aux concaténations (c5c2370, 2549d0f ; preuves sur
  les scripts réels, 70 passed). **#19 = RUN FINAL PARFAIT** : 1/1 APPROUVÉ
  it1 (~14 min) — validation visuelle complète : chargement 29/30 barres
  (4→250px), COMPTEUR VIVANT 0→249, tri 30/30 croissant, dark theme.
  Bilan du jour : 7 runs E2E, chaque défaut (gardes OU œil humain) a reçu
  son garde déterministe. Post-mortem épilogue complet :
  `debug/POSTMORTEM_RUN13.md`.

## Jalons de l'Itération (cycle F-122 — ULTRA restreint à l'itération ≥ 3)
> Décision utilisateur (proposition 2 du post-mortem run #10). Réactive
> l'escalade de modèle F-111 en la bornant : le 9B no-think trop lent ne
> s'active PLUS à l'itération 2 — uniquement à l'itération 3 (dernière chance
> avant escalade), au plus UNE activation par run.

- [x] F122-1 : `_select_coder_spec` — condition = `iteration >= 3` seule ;
  déclencheurs historiques retirés (docstring F-111/F-122) ; signaux
  `prev_*` conservés pour observabilité.
- [x] F122-2 : `CODER_ULTRA_CORRECTION=true` réactivé (`.env` +
  `.env.example`, commentaire F-122).
- [x] F122-3 : Tests — 2 cas historiques inversés (it.2 déterministe /
  coder-mort → fast), 22/22 `test_coder_hardening` PASS.
- [x] F122-4 : Suite complète pytest — **1497 passed / 1 failed / 1 skipped**
  (échec unique = flaky minute-boundary préexistant, sans interaction avec
  F-122, documenté) → 0 régression.
- [x] F122-5 : État disque (contract C440-C442, feature_list F-122, ce
  fichier) + DuckDB (#1220) + commit + PR. **Run E2E de validation reporté
  à une session ultérieure (décision utilisateur).**

## Jalons de l'Itération (runs #10 + #11 — validation E2E post-merges PR #90/#91)

## Jalons de l'Itération (runs #10 + #11 — validation E2E post-merges PR #90/#91)
> Run #10 (gardes actives) : F-114/F-115 VALIDÉS, F-112 partiel, F-113 non
> exercé. Run #11 (STATIC_TESTER_ENABLED=0, dédié) : **PREMIÈRE APPROBATION
> E2E COMPLÈTE** — F-113 validé, boucle Coder→Tester→Judge→APPROUVÉ de bout
> en bout. Post-mortems : `debug/POSTMORTEM_RUN10.md` + `POSTMORTEM_RUN11.md`.

- [x] Run #10 (~21 min, 9,5 M tokens) : Coder converge en 12 steps iter 1
  (60 visual_check vs 0 au run #9 ; fullPage capé → 1280×800) ; livrable
  rejeté 3× par Static Tester (bug compteur F-110) ; escalade propre.
  F-114 ✅ F-115 ✅ F-112 🟡 F-113 ❌ (Tester LLM jamais tourné).
- [x] Run #11 (~23 min, 14,3 M tokens, décision user prop. 1) : Web Tester
  LLM 2× ; 2 sauvetages Pydantic SANS Connection error ; F-108 fail-closed
  iter 1 ; **iter 2 le 4B corrige réellement** (feedback qualitatif précis) ;
  re-test ciblé F-52 ; Security ; **Juge APPROUVE** 🚀.
- [x] Découverte méta : le 4B sait corriger avec feedback LLM qualitatif —
  là où le feedback déterministe du run #10 ne déclenchait rien. Qualité du
  feedback = levier aussi fort que l'escalade de modèle (F-111), moins cher.
- [ ] Décision user en attente : (2) ULTRA itération ≥ 3 seule, (3) F-120
  plan.md/task.md, durcissement format sortie Tester (2/2 sauvetages).

## Objectif Actuel

## Jalons de l'Itération (cycle F-115 — Spec PromptRefiner en anglais)
> Décision utilisateur après démo du « Améliorer le prompt » de Kilo Code (fiche 47,
> la référence d'origine de F-39) : nos petits modèles locaux sont nettement plus
> forts sur l'anglais structuré → la spec raffinée passe en anglais, comme la
> sortie Kilo. Second commit de la PR #91 (même objectif : convergence petits modèles).

- [x] F115-1 : `PromptRefinerSignature` réécrite en anglais (règle LANGUAGE
  explicite + sections `## Objective` / `## Expected Features` / `## Technical
  Constraints` / `## Acceptance Criteria`).
- [x] F115-2 : `requirements_checklist.py` (F-51) bilingue — anglais prioritaire,
  français rétro-compat (checkpoints F-24 hérités) ; fallback inchangé.
- [x] F115-3 : Tests — 27 ciblés PASS (mock anglais + test doctrinal signature +
  3 parseur dont rétrocompat).
- [x] F115-4 : Suite complète pytest — **1498 passed / 0 failed / 1 skipped**
  (flaky minute-boundary passé cette exécution, 0 régression).
- [x] F115-5 : État disque (contract C437-C439, feature_list F-115, ce fichier)
  + DuckDB (#1172, #1206) + commit + push PR #91.

## Objectif Actuel
- [x] Valider le coding workflow de bout en bout sur un prompt "landing page premium"
      (Architect → Coder → Tester → Judge → verdict). ATTEINT (run #12 HTML propre,
      run #13 cycle complet + reprise après crash multi-crash).
- [x] Ajouter `browser-use` aux références et exécuter le workflow d'audit. TERMINÉ.
- [x] Cycle CHROME DEVTOOLS MCP + VALIDATION VISUELLE (F-45) : auto-validation visuelle
      du Coder (screenshot vu par gemma-4-E4B multimodal avant final_answer) + complément
      d'outils DevTools au WebTester (cumul avec Puppeteer, pas de suppression).
      Implémentation TERMINÉE (28 tests, 521 passed / 0 failed). Validation run à venir.
- [x] Cycle CHECKLIST FONCTIONNALITÉS + FIXES ROBUSTESSE GPU-LOCAL (F-46) : 3 runs de
      validation Bubble Sort ont révélé Security silencieux (VRAM saturée par parallélisme),
      Coder générant du TypeScript en vanilla, et Tester oubliant des fonctionnalités.
      Fixes (AUDIT_PARALLEL=false, max_steps 24→12, anti-TS, console obligatoire, règle 2
      essais) + checklist parsée forcée (1 assertion/fonctionnalité). Implémentation
      TERMINÉE (14 tests, 535 passed / 0 failed).
- [ ] Cycle TESTER POLYVALENT + AUTO-CORRECTION stderr (Priorité 2) : dispatch
      multi-techno (web+python) + troncature anti Context-Overflow. En cours.
- [ ] Cycle CONTEXT7 (doc libs à jour, anti-hallucination d'API) : intégration sur
      3 nœuds + skill stratégique. Implémentation TERMINÉE, validation runs à venir.
- [x] Cycle TESTER FONCTIONNEL (assertions comportementales, F-20) : le tester ne
      testait que l'absence de crash → bugs de logique validés à tort. Implémentation
      TERMINÉE (skill puppeteer_* + assertions, propagation spec, Judge équipé).
- [x] POST-MORTEM RUN 123955 (F-61 amélioration continue) : 3 bugs récurrents détectés
      par `run_analyzer.py` et corrigés sur la branche `fix/postmortem-run-123955` :
      (1) **Security fail-open CRITIQUE** — `security_res=None` (audit KO) était
      silencieusement transformé en "Aucune vulnérabilité" → le Judge approuvait à
      l'aveugle un code non audité (bs-001 APPROUVÉ juste après Error LLM). Fix :
      hard block fail-closed dans `execute_code_judge_node` (retour `is_approved=False`
      SANS appel LLM) + traçage KG de l'échec Security.
      (2) **Tester `click` forbidden (6×)** — l'allowlist DevTools filtrait `click`/`fill`
      alors que la doc les recommandait → smolagents rejetait l'appel. Fix : `click`/`fill`
      ajoutés à l'allowlist `chrome_devtools_tool.py`.
      (3) **Coder `}` au lieu de `)` (6×)** — quand `search_replace(new_string="<JS>")`
      contient des accolades, le modèle fermait l'appel Python par `}`. Fix : règle n°8
      dans le prompt Coder + section dédiée dans le skill coding (miroir du bloc IIFE
      web-tester). Implémentation TERMINÉE (42 tests sur les 3 zones, 692 passed / 7
      pré-existants non liés).

## Jalons de l'Itération (cycle F-114 — Cap fullPage + nudge checklist, post-mortem run #9)
> Feu vert utilisateur (propositions 1+2 du post-mortem). Deux fixes déterministes
> 0 LLM dans `vision_callback.py` pour débloquer la convergence du Coder :
> éliminer les images fullPage géantes (timeout 600 s) et rappeler la checklist
> `visual_check` AU MOMENT du comportement fautif (pas seulement au boundary).

- [x] F114-1 : Cap `fullPage` — force `fullPage=False` (et `full_page`) sur les
  clés uniquement déjà présentes ; config `VISION_FULLPAGE_CAP` (défaut true) +
  `.env`/`.env.example` ; strip filePath F-50/F-90 inchangé (test régression).
- [x] F114-2 : Nudge contextuel — `make_screenshot_callback(…,
  visual_criteria_count=0)` (Coder uniquement) ; au 3e screenshot avec critères
  manquants → rappel injonctif APPENDU à `memory_step.observations` (canal fiable :
  `_finalize_step` après assignation observations, smolagents agents.py:623) ;
  compteur traverse les retries ; `reset_screenshot_nudge()` au site de
  `reset_visual_audit()` ; fail-open total.
- [x] F114-3 : Tests — **14 nouveaux PASS** (`tests/test_vision_nudge.py` :
  cap 6 + nudge 8) ; py_compile 3 fichiers.
- [x] F114-4 : Suite complète pytest (basetemp dédié F-95) — **1493 passed /
  1 failed / 1 skipped** ; échec unique = flaky minute-boundary
  `test_e2e_resume_reuses_same_run_dir` PRÉEXISTANT (documenté F-53/F-95,
  vérifié identique SANS les changements F-114 via stash) → **0 régression**.
- [ ] F114-5 : État disque (contract C432-C436, feature_list F-114, ce fichier)
  + DuckDB + commit + PR.
- [ ] F114-6 : Re-run E2E validation F-112/F-113 (après merge).

> Note d'incident (sans perte) : bascule parallèle du working copy sur
> `docs/audit-kilocode` (travail fiche 47-kilocode de l'utilisateur) pendant le
> cycle — restauration sur `fix/f-114-screenshot-cap-nudge` via stash ; conflit
> binaire sur `data/event_stream.duckdb` résolu depuis le commit de stash
> (récupéré par blob SHA via `git ls-tree`/`git cat-file`) : 969 événements
> intacts au final, 0 perte.

## Jalons de l'Itération (run #9 — validation E2E post-merge F-112+F-113, ÉCHOUÉE en amont)
> Run FRESH_START `runs/2026-08-17_1439_bubble_sort_multifile_v6` (~1 h 28,
> exit 0, `failure/"Coder crash"`). Post-mortem complet :
> `debug/POSTMORTEM_RUN9.md` + `analysis_report.md`.

- [x] Run exécuté, analysé (`scripts/run_analyzer.py`), post-mortem rédigé +
  DuckDB (#1059).
- [x] Validations PASSANTES au passage (chemin négatif, en prod) : F-109 +
  F-109-bis (gate checklist : refus + rappel injecté), F-36 anti-loop, F-88
  stall detector, F-99 idle re-injection (cascade complète), F-95 (fs_tx/git
  run dir/allowlist) et F-101 (transcripts) actifs, échec définitif propre
  (exit 0, checkpoint effacé). Aucun `Connection error` au sauvetage Pydantic.
- [ ] **NON validés** : F-113 (Web Tester jamais atteint → parsage verdict
  post-fix api_base à prouver) et F-112 (Static Tester jamais atteint → sonde
  animation à prouver en chaîne).
- [ ] **Bloqueur identifié** : le Coder 4B fait 0 appel `visual_check` en
  3 tentatives (48 screenshots, conclusion en prose) + amplificateur
  `take_screenshot(fullPage=True)` (images 9 315 px → timeout 600 s, tentative
  2 tuée). 43,9 M tokens input, 0 livrable. Propositions 1/2/3 dans le
  post-mortem — **décision utilisateur attendue** (AGENTS.md §8).

## Jalons de l'Itération (cycle F-113 — Fixes P0 post-mortem run #8)
> Les deux causes racines prouvées par debug/POSTMORTEM_RUN8.md, corrigées :
> le sauvetage Pydantic qui tapait un port mort (LE bloqueur des approbations)
> et le prune qui détruisait les runs en silence depuis le 3 août.

- [x] F113-1 : Fix sauvetage — propriété `api_base` sur LoggedOpenAIServerModel
  + `_resolve_agent_api_base` (fallback client_kwargs) dans run_with_retry.
  smolagents n'expose PAS self.api_base → l'ancien getattr rendait toujours
  None → sauvetage sur port 8000 mort → Connection error 3/3 du run #8.
- [x] F113-2 : Fix prune — `_rmtree_verified` (retries + chmod read-only +
  vérification finale) ; « supprimé » seulement si disparu (sinon PRUNE
  PARTIEL bruyant) ; grâce 6h (un run frais ne peut plus être détruit à chaud).
- [x] F113-3 : Fix isolation — 6 helpers E2E → output_dir=tempfile.mkdtemp
  (avant : 8+ dossiers sous runs/ par exécution de suite → vrais runs poussés
  hors rétention → détruits).
- [x] F113-4 : 17 tests nouveaux PASS (dont la régression exacte du run #8,
  blob read-only supprimé, run récent protégé par grâce, jamais de succès
  mensonger, isolation des 6 helpers).
- [x] F113-5 : Suite complète **1407 passed / 0 failed / 1 skipped** (1390
  baseline, 0 régression) ; LIVE : 0 nouveau dossier sous runs/ post-suite.
- [x] F113-6 : État disque synchronisé + DuckDB + commit + PR.

## Jalons de l'Itération (cycle F-112 — Sonde animation instantanée multi-signal)
> Post-mortem run #8 (E2E FRESH_START 2026-08-16_2205, 1h47) : le livrable
> Bubble Sort avait un tri INSTANTANÉ (formule de délai négative + aucun
> repaint dans la boucle) sorti de 3 itérations sans qu'AUCUN nœud ne
> l'identifie. Demande utilisateur : « trouver un moyen pour, comme toi,
> trouver le problème ». Réponse : la sonde temporelle manuelle devient une
> brique déterministe de l'usine (2 voies indépendantes).

- [x] F112-1 : Diagnostic — Tier 3 cécité (découvreur de signal = PREMIER
  élément numérique du DOM = speedLabel CONSTANTE placée avant le compteur →
  t0=t1=t2 → skip silencieux) ; Tier 1c cécité (délai FORMULE non résolue) ;
  cause amont (le message Tier 1c suggérait LITTÉRALEMENT la formule que le
  Coder a greffée sur une variable en ms).
- [x] F112-2 : `_resolve_delay_ms` (Tier 1c) — résolution arithmétique sûre
  (substitution variables liées + éval whitelistée chiffres/opérateurs
  uniquement) ; `sleep(320 - speed*2)` avec speed=320 → −320 → flag
  « NÉGATIVE clampée à 0 » ; message rewordé : invariant d'UNITÉ, zéro
  formule copiable.
- [x] F112-3 : Tier 3 multi-signal — TOUS les éléments numériques (par id) +
  hash djb2 pixels du premier <canvas> + classes terminales ; `_temporal_verdict`
  pur (progressé-then-stable = instantané ; rien bougé = skip sans FP ; bouge
  encore = progressive) ; stabilisation 50→350 ms (anti-FP pas lents).
- [x] F112-4 : Tests — 19 nouveaux PASS (6 resolve + 3 behavioral + 8 verdict
  purs + 2 LIVE réplique exacte run #8 : réfutée / progressive passe).
- [x] F112-5 : Validation — LIVE sur le VRAI livrable `runs/2026-08-16_2205` :
  is_valid=False avec les DEUX réfutations (−320 ms statique + temporal
  « compteur counter 0→214 ; canvas (pixels) ») ; suite complète **1409
  passed / 0 failed / 1 skipped** (1390 baseline, 0 régression).
- [x] F112-6 : État disque synchronisé (feature_list F-112, contract
  C421-C426, plan case sous F-100, README) + DuckDB + PR.

## Jalons de l'Itération (cycle F-95 — Robustesse FS : transactions + verrous + cloisonnement IO)
> Priorité 8-bis (audit fiche 32-OpenKB, 2026-08-12). Complète l'idempotence F-43
> (replays) par l'ANNULATION des effets partiellement appliqués, durcit le Mutex
> F-20 vers du cross-process, et confine les IO du Coder par allowlist de chemins
> (allowlist > denylist sur le périmètre). 3 modules Python pur 0 LLM.

- [x] F95-1 : Exploration — lecture des 3 sources OpenKB (mutation.py 458 l.,
  locks.py 257 l., agent/tools.py) + fiche audit 32 ; points d'intégration
  identifiés (9 outils FS de tools.py, `with` workflows.py sans réindentation,
  config pattern singleton `from .config import settings`).
- [x] F95-2 : Module `fs_locks.py` — verrou OS advisory cross-process
  `.fs_tx/dir.lock` (fcntl POSIX / msvcrt Windows + retry borné 10 s puis
  FsLockTimeout), _LocalRwLock intra-process, réentrance par thread, upgrade
  read→write refusé, drain différé des journaux à la 1re acquisition exclusive,
  atomic_write_bytes/text/json (temp+replace+fsync). Écarts : pas de portalocker
  (stdlib pur) ; read lock exclusif OS sous Windows (documenté).
- [x] F95-3 : Module `fs_tx.py` — MutationSnapshot (journal active/committed/
  rolled_back + backup), snapshot_paths (hardlink_dirs optionnel, repli copy2
  sur EXDEV/EPERM/EACCES), track_new, rollback O(touched) par diff d'inode
  (_restore_hardlinked_dir), recover_pending_journals (corrompu → suppression
  bruyante ; rollback défaillant → retry borné 5 puis GAVE UP). Écarts :
  publish_staged_tree non porté ; prod hardlink_dirs=None (append_file in-place).
- [x] F95-4 : Module `io_guard.py` — allowlist scopée (pattern F-43), path_allowed
  (realpath anti-traversal, normcase Windows, frontière stricte run2∉run), messages
  pédagogiques, fail-open sans racine. Branché sur les 9 outils FS (write/append/
  edit/search_replace/multi_replace/read_file/skeleton/js_syntax/list_directory) ;
  bash_command non couvert (documenté).
- [x] F95-5 : Branchement `workflows.py` — `_scoped_run_guard` (verrou exclusif
  run dir + allowlist [run_output_dir]) composé dans le `with` existant ;
  transaction fs_tx autour de chaque appel Coder (normal→committed, exception→
  rollback+re-raise, crash→journal actif roulé back au run suivant, cohérent
  checkpoint F-24). `git_snapshot.init_run_git` exclut `.fs_tx/` via
  `.git/info/exclude` (PAS un .gitignore worktree — fix réactif : le .gitignore
  cassait le test de non-contamination F-102 en apparaissant dans git status).
  Config RUN_DIR_LOCK/FS_TRANSACTIONS/IO_ALLOWLIST_ENABLED + .env.example/.env.
- [x] F95-6 : Validation — **54 tests nouveaux PASS** (fs_locks 17 dont verrou
  cross-process réel parent/enfant subprocess ; fs_tx 16 dont inode partagé
  O(touched) et GAVE UP après retry borné ; io_guard 18 dont traversal et
  intégration des 9 outils ; git_snapshot +3 exclusion) ; suite complète
  **1441 passed / 0 failed / 1 skipped** (1390 baseline, 0 régression ; le
  1er run complet a réveillé le flaky minute-boundary `test_e2e_resume_reuses_
  same_run_dir` PRÉ-EXISTANT F-53, repassé isolément ET au run final) ;
  LIVE `debug/run_fs_safety.py` **3/3 démos** (crash-recovery end-to-end avec
  drain au verrou, verrou cross-process, cloisonnement IO + fail-open).
  Note env : symlink `pytest-current` mort (9 août) dans le temp pytest →
  PermissionError au sessionfinish (défaut pytest/Windows sur symlink dir) ;
  contourné via `--basetemp` (indépendant du projet).
- [x] F95-7 : État disque synchronisé (feature_list F-95 completed, contract
  C415-C420, plan P8-bis 3 sous-cases cochées + ligne d'état, progress, README)
  + DuckDB + PR.

## Jalons de l'Itération (cycle F-101 — Compaction v2 : petits modèles + anti-boucle)
> Priorité 9 (update références 2026-08-14, fiches opencode/learn-claude-code/pi/
> claude-science/hermes-agent). La compaction déterministe 5 couches reste la
> défaut ; ce cycle lui ajoute l'archive disque perte-zéro, la garde overflow
> à usage unique, et prépare (testé, dormant) le volet sémantique LLM opt-in.

- [x] F101-1 : Exploration (2 subagents parallèles) — opencode compaction.ts
  (SUMMARY_TEMPLATE 5 sections, UPDATE_INSTRUCTIONS verbatim, select() entrée
  entière, chaînage {summary,recent}), s08 (ordre tool_result_budget → snip
  archive .transcripts → micro réutilise les chemins → compact LLM, marqueur
  "[N messages archived at]", bloc <persisted-output>, retry réactif unique),
  pi §3.9 (overflowRecoveryUsed/failure_drain), claude-science (fold keys =
  search queries, never reconstruct, frame scratchpad), hermes (budget
  remboursé sur usage provider vérifié, latch verdict unique).
- [x] F101-2 : Module dormant `compaction_prompts.py` (0 LLM) — prompts
  opencode petits modèles + règles fold claude-science + build_summary_prompt
  (ordre fidèle) + select_head_recent (entrée ENTIÈRE jamais coupée).
- [x] F101-3 : Module `compaction_guards.py` (0 LLM) — OverflowGuard (pi :
  décision atomique armer/récupérer, drain au 2e overflow, réarmement par
  nouvel input uniquement) + CompactionBudget (hermes simplifié : verdict par
  usage provider réel, remboursement, breaker ; écarts DB/probation
  documentés) + is_context_overflow_error (patterns provider, tolérant).
- [x] F101-4 : `compaction.py` v2 — archive_steps (JSONL uuid, open("x"),
  sérialisation défensive) + apply_snip_compact (marqueur s08 exact,
  chaînage "Earlier archives kept:", FRAME) + persist_large_output
  (<persisted-output> + Full output/Preview, safe_id, jamais réécrit) +
  tool_result_budget persiste AVANT de tronquer (remplacement seulement s'il
  réduit) + micro_compact réutilise les chemins persistés + context_frame
  sur l'agent + snip déplacé EN TÊTE (archive aux contenus originaux).
- [x] F101-5 : Branchement `run_with_retry` — OverflowGuard par exécution de
  nœud : 1er overflow → récupération (purge mémoire + message d'action
  directe), 2e → failure_drain (return None immédiat, le graphe continue).
  Cohérent F-104 : l'overflow est fatal-4xx au transport → remonte au nœud.
- [x] F101-6 : Config COMPACTION_ARCHIVE_ENABLED / COMPACTION_OVERFLOW_GUARD
  (défauts true) + .env.example + .env local.
- [x] F101-7 : Validation — **63 tests nouveaux PASS** (test_compaction_v2.py)
  ; suite complète **1390 passed / 0 failed / 1 skipped** (1315 baseline +
  ~12 live, 0 régression ; flaky minute-boundary pré-existant documenté) ;
  py_compile 5 fichiers ; smoke live du snip archivé avant les tests. État
  disque synchronisé (feature_list F-101 completed, contract C409-C414, plan
  case P9 cochée, progress).

## Jalons de l'Itération (cycle F-104 — Retry LLM v2 + init MCP non bloquante)
> Priorité 8 (update références 2026-08-14, fiches openfox/opencode/crush/deer-flow).
> Diagnostic d'entrée : AUCUN retry transport n'existait — un « Connection error »
> transitoire remontait à run_with_retry qui purgeait TOUTE la mémoire du nœud
> pour relancer (très coûteux), ou tuait définitivement un nœud DSPy ; l'init
> MCP bloquait 30 s thread + event loop par défaut mcpadapt ; un serveur
> llama-server mort mid-run (VRAM, post-mortem run #4) n'était jamais détecté.

- [x] F104-1 : Exploration (2 subagents parallèles) — cartographie run_with_retry
  (retry niveau nœud, sans backoff, purge mémoire), LoggedOpenAIServerModel
  (log tokens seulement), _configure_dspy (0 num_retries), llama_server (aucune
  supervision mid-run), chrome_devtools/context7/web_tester (from_mcp nu),
  orphan_repair (aveugle à la forme top-level OpenAI).
- [x] F104-2 : Module `graph_orchestrator/llm_retry.py` (Python pur, 0 LLM) —
  RetryPolicy (5 essais, base 1s, cap 30s, jitter décorrelé 25%, retry-after
  prioritaire clampé), classify_llm_error (fatal 4xx AVANT retryable réseau,
  regex à frontières de mots : un code HTTP ne matche jamais un port ;
  inconnu = fatal fail-fast), extract_retry_after_ms (headers + message),
  with_llm_retry (sémantique openfox PRÉ-CONTENU : même requête rejouée,
  rien à l'historique, between_attempts best-effort).
- [x] F104-3 : Branchement smolagents — LoggedOpenAIServerModel.__call__ wrappé
  (kwarg revive= optionnel), _between_attempts = re-résolution du client
  (revive → NOUVEL api_base → create_client()) ; retry SDK openai désactivé
  (max_retries: 0 aux 4 sites de construction) → RetryPolicy autorité unique ;
  sites dynamiques Coder/Tester migrés vers LoggedOpenAIServerModel avec
  revive=srv.revive. DSPy : num_retries litellm natif dans _configure_dspy.
- [x] F104-4 : `model_lifecycle.revive()` + sonde _port_healthy 2s (llama_server.py)
  — serveur spawné mort/wedged mid-run → stop + respawn complet sous _spawn_lock
  (nouveau port), attrs mis à jour ; sain → no-op (blip) ; external → api_base.
- [x] F104-5 : Module `graph_orchestrator/mcp_connect.py` (crush : timeout PAR
  SERVEUR) — open_mcp_with_timeout : connexion en thread DAEMON bornée, retourne
  (cm, tools) déjà ouvert ou (None, []) au timeout (dégradation, thread zombie
  daemon documenté) ; branché chrome_devtools_tools (25s), context7_tools +
  fetch_context7_brief (15s), bloc Puppeteer web_tester (25s, ExitStack +
  callback __exit__ — DevTools prend le relais si Puppeteer pendu).
- [x] F104-6 : Leçon deer-flow dans orphan_repair.py — repair_orphan_tool_results
  voit la forme top-level message["tool_calls"] (réponse role=tool insérée après
  l'assistant, indices décroissants préservant l'ordre c1→c2) + réponses
  role=tool existantes collectées + dédup STRICTE par id entre les deux formes.
- [x] F104-7 : Config — LLM_RETRY_ENABLED/LLM_TRANSPORT_RETRIES/LLM_RETRY_BASE_
  DELAY_S/LLM_RETRY_MAX_DELAY_S/LLM_RETRY_JITTER + CHROME_DEVTOOLS_CONNECT_
  TIMEOUT_S/CONTEXT7_CONNECT_TIMEOUT_S/PUPPETEER_CONNECT_TIMEOUT_S (.env.example
  + .env local).
- [x] F104-8 : Validation — **43 tests nouveaux PASS** (test_llm_retry 23,
  test_mcp_connect 9, test_llm_model_retry 6, orphan_repair +5) ; suite complète
  **1315 passed / 0 régression** + 11 live test_web_tester_functional PASS ;
  1 flaky minute-boundary pré-existant documenté (passe isolément) ; py_compile
  10 fichiers. Tests MCP existants re-patchés vers mcp_connect.ToolCollection
  (le vrai point d'entrée réseau post-refactor). État disque synchronisé
  (feature_list F-104 completed, contract C401-C408, plan case P8 cochée).

## Jalons de l'Itération (cycle F-102 — Checkpoint git par itération pour le Judge)
> Priorité 8-bis (update références 2026-08-14, fiche 09-open-swe). Le Judge relit
> CE QUE GIT DIT de l'itération (diff structuré par fichier) au lieu de rejouer les
> tool-calls — complément de F-53 (git_snapshot) et F-70 (judge_diff), disponible
> DÈS l'itération 1 (le diff texte F-53 y est vide, <2 commits).

- [x] F102-1 : Module `graph_orchestrator/turn_checkpoint.py` (port Windows natif
      de `references/open-swe/agent/utils/turn_checkpoint.py`, 0 LLM, 0 shell
      POSIX) — `record_turn_checkpoint` : snapshot du worktree SANS contaminer
      HEAD/index/worktree (index scratch `GIT_INDEX_FILE` tempfile → read-tree →
      add -A → write-tree → commit-tree → update-ref
      `refs/graph-orchestrator/turns/<key>` ; une REF survit à un git gc mi-run) ;
      `read_turn_diff` : diff structuré `{status, files, truncated}` (numstat +
      name-status + contenus base/head via `cat-file --batch` natif, blob >400 Ko
      unrenderable, cap 200 fichiers) ; parseurs purs ports fidèles.
- [x] F102-2 : Écarts consciencieux documentés — invariant « earliest wins » de
      merge_checkpoint encodé au niveau de la REF (jamais avancée : une reprise
      après crash ne fait pas glisser la base du tour) ; garde d'isolation F-53
      réutilisée (refus de toute écriture de ref vers un repo parent) ; blobs
      octets bruts (pas de base64 sandbox) ; param `include_contents` ajouté
      (runtime Judge = résumé seul, saute cat-file).
- [x] F102-3 : Intégration `workflows.py` — snapshot `<task_id>-iter<N>` au DÉBUT
      de chaque itération (APRÈS le Drafter : le draft ne compte pas comme
      changement de code) ; post-Coder `read_turn_diff(include_contents=False)` →
      `summarize_turn_diff` → `sub_dict["turn_diff_summary"]` (best-effort).
- [x] F102-4 : Intégration `judge_diff.py` — `build_judge_code_block(...,
      turn_diff_files=)` préfixe « CE QUE GIT DIT (turn checkpoint F-102) » :
      manifeste par fichier (statut, +ajouts/-suppressions, binaire), devant le
      bloc diff texte IN-DIFF en iter >1 ; absent = comportement F-70 pur.
      Appel Judge (dspy_nodes.py) alimenté depuis `subtask["turn_diff_summary"]`.
- [x] F102-5 : Config `TURN_CHECKPOINT_ENABLED` (défaut true) + `.env.example` +
      `.env`. Script isolation `debug/run_turn_checkpoint.py` (convention F-89).
- [x] F102-6 : Validation — **34 tests nouveaux PASS** (29 module : non-
      contamination HEAD/index, reprise earliest-wins, anti-pollution parent,
      binaire/gros blob/truncated 201 fichiers, séquence prod exacte ; +4
      judge_diff ; +1 config) ; suite complète **1284 passed / 0 failed /
      1 skipped** (1250 baseline, 0 régression) ; LIVE isolation **8/8
      invariants** (résumé iter 1 = 2 fichiers added alors que diff texte F-53 =
      0 char). État disque synchronisé (feature_list F-102 completed, contract
      C396-C400, plan case P8-bis cochée, progress).

## Jalons de l'Itération (cycle F-100 — Recettes de vérification exécutable)
> Priorité 6 (update références 2026-08-14, fiche 25-hermes-agent). « La page est
> servie et répond » devient une preuve exécutable au lieu de `file://` + console
> seule (les scripts ES-module et fetch sont bloqués par CORS en file://).

- [x] F100-1 : Package `graph_orchestrator/verify/` (Python pur, 0 LLM) — port
      quasi 1:1 de `references/hermes-agent/agent/verify/` : `recipes.py`
      (détection grok ordre préservé : Node/frameworks/lockfiles, Python
      Django/FastAPI/Flask/générique, Go/Rust/Maven/Gradle/Make/compose),
      `runner.py` (phases → start arrière-plan → boucle readiness HTTP →
      teardown), `environment.py` (manifeste `.verify/environment.json` qui
      PRIME sur la détection, corrompu → détection fraîche).
- [x] F100-2 : Écarts consciencieux documentés — détecteur **static-web** en
      dernier recours (cas Prompt-Vault vanilla : `http.server {port} --bind
      127.0.0.1`, anti popup firewall Windows) ; `phases=None` vs `()` + start
      piloté par `skip_start` (référence rendait « start seul » inexprimable) ;
      substitution `{port}` (port libre dynamique) ; teardown Windows
      `taskkill /F /T` (kill de l'ARBRE — `terminate()` laisserait le serveur
      orphelin derrière cmd.exe) ; sonde readiness sans proxy (127.0.0.1 hors
      HTTP_PROXY).
- [x] F100-3 : Tier HTTP dans `execute_static_tester_node` — après Tiers 1-4
      PROPRES seulement ; recette au dossier du 1er target HTML ; preuve
      `[http] Page servie → HTTP 200 (kind/source, Xs)` dans le details
      success ; readiness KO = RÉFUTATION sauf recette static-web (notre
      infra, pas le code du modèle → note). Fail-open total (ADR-0002).
- [x] F100-4 : Config `STATIC_TESTER_HTTP` (défaut 1) + `STATIC_TESTER_HTTP_TIMEOUT`
      (défaut 10s) dans `.env.example` + `.env` local. Script isolation
      `debug/run_verify.py` (déterministe, convention F-89).
- [x] F100-5 : Validation — **52 tests PASS** (dont VRAI http.server servi +
      readiness 200 + port re-bindable après teardown) ; suite complète
      **1250 passed / 0 failed / 1 skipped** (1198 baseline, 0 régression) ;
      LIVE `debug/run_verify.py` sur golden run Bubble Sort : static-web
      détectée, servie HTTP 200 en 1.1s sur port libre, teardown propre.

## Jalons de l'Itération (cycle F-72 — Prompt Offloading)
> Priorité 10 du plan usine logicielle (volet Prompt Offloading). Encapsuler la complexité
> (snippets JS, algorithmes) dans des OUTILS Python dédiés au lieu de l'injecter en texte
> brut dans les prompts système. Modèle cité en réf : Web Tester (`puppeteer_clean_dom` /
> `puppeteer_add_visual_tags`). **Découverte clé : ce « modèle » était CASSÉ** — il wrappait
> `puppeteer_evaluate` (navigateur Puppeteer qui ne charge PAS les `file://` locaux → DevTools
> est devenu le pilote primaire). Le prompt du Tester disait même de NE PAS les utiliser. F-72
> recrée ces helpers en version DevTools, plus `check_js_syntax` et la centralisation de la doc.

- [x] F72-1 : Module `js_utils.py` — extraction DRY de `run_node_check` + `MAX_JS_CHARS` depuis
  `static_tester.py` (alias privés `_run_node_check`/`_MAX_JS_CHARS` préservent l'appelant, imports
  morts `subprocess`/`tempfile` retirés, 0 changement comportemental). Partagé Static Tester
  Tier 1a + futur outil Coder.
- [x] F72-2 : Outil `@tool check_js_syntax(path)` (tools.py, Coder) — auto-validation verify-after
  de la syntaxe JS via `node --check` ; détection `node` absent upfront (`shutil.which` → message
  informatif, n'affirme jamais 'valide' à tort) ; retrait de l'exemple subprocess `node --check`
  du prompt Coder (→ mention de l'outil).
- [x] F72-3 : Module `devtools_dom_tools.py` — 3 sous-classes `Tool` (`clean_dom`, `add_visual_tags`,
  `fuzz_click_all_buttons`) wrappent `evaluate_script` (DevTools) via `function=<JS>` ; snippets JS
  corps préservés EXACTS, adaptation `script=`→`function=` + retrait enveloppe IIFE (DevTools exige
  une fonction NON invoquée, une IIFE crasherait le CDP). Factory `build_devtools_helper_tools`
  fail-open. **Répare le modèle cassé.**
- [x] F72-4 : WebTester — retrait du bloc Puppeteer mort (`PuppeteerAddVisualTagsTool`/
  `PuppeteerCleanDomTool`) + branchement `build_devtools_helper_tools(cdt_tools)` ; prompt màj
  (les 3 outils désormais DevTools-based et OK à utiliser) ; 2 skills `web-tester/resources/` màj
  cohérence (`puppeteer_clean_dom`→`clean_dom` ; note « À ÉVITER » → « OK sur le navigateur actif »).
- [x] F72-5 : Coder — branchement `build_devtools_helper_tools(cdt_tools)` + retrait du snippet
  fuzzing inline du `preview_block` (étape 3 → `fuzz_click_all_buttons()`).
- [x] F72-6 : Centralisation doc DevTools — `DEVTOOLS_BASE_DOC` (chrome_devtools_tool.py, signatures
  communes `navigate_page`/`list_console_messages`/`evaluate_script` + anti-IIFE CRITIQUE, single
  source of truth) partagée Coder (`_DEVTOOLS_TOOLS_DOC`) + Tester (`devtools_hint`, ajoute
  `take_snapshot`/`click`/`fill`/`take_screenshot` + filePath/visual bug/python builtins). Couverture
  point-par-point vérifiée (0 marqueur perdu vs 6 points doc Coder + 13 points hint Tester).
- [x] F72-7 : Validation — py_compile OK (7 fichiers). **19 nouveaux tests PASS** (js_utils 5 +
  devtools_dom_tools 10 + tools +4). Suite complète **940 passed / 8 failed** (les 8 STRICTEMENT
  pré-existants `test_read_gate`×4 + `test_skill_lazy_loading`×3 + `test_guard`×1, documentés
  F-97/F-82, AUCUN lié à F-72). **0 régression.** État disque synchronisé (feature_list F-72
  completed, contract C337-C344, plan_usine case P10 cochée, progress).

## Jalons de l'Itération (cycle F-93 — Grounding des findings Judge, P6)
> Anti-hallucination de localisation. Le Judge exige « LOCALISATION OBLIGATOIRE » mais aucun garde
> logiciel ne vérifiait qu'elle existe dans le source → un critical inventé pouvait faire rejeter
> le code à tort. Décision utilisateur : **politique Option 1 non-destructive** (rétrograde+flag,
> is_approved inchangé) — calibrage d'abord, automation du verdict en cycle futur après mesure du
> taux de faux-positifs par le Meta-Analyste (P15).

- [x] Étape F93-1 : Exploration (2 subagents parallèles) — map précise : `Finding` schema
  (models.py:23, Pydantic mutable, `findings` JAMAIS persisté en DuckDB → liberté de mutation),
  point d'insertion `execute_code_judge_node` dspy_nodes.py (retournait `result.output` brut,
  aucun post-traitement ; fail-closed security=None retourne avant LLM = naturellement exclu),
  miroir F-70 (judge_metrics + judge_diff style), algorithme langextract (legacy sliding-window
  + LCS DP, pure stdlib). Décision design : porter le LEGACY `_fuzzy_align_extraction` (plus
  simple, bornage fenêtre implique densité) plutôt que le DP LCS.
- [x] Étape F93-2 : Module `graph_orchestrator/judge_grounding.py` (~330 lignes, 0 LLM) — port
  `_normalize_token` (lowercase+plural stem), `fragment_is_grounded` (sliding-window difflib,
  coverage 0.75, max_window 2·needle), `read_source_files`/`_resolve_file`/`extract_code_fragments`
  (spans backtick + chains a.b.c ONLY, PAS de prose ni filenames via `_looks_like_filename`),
  `_extract_file_line_refs`, `ground_finding` (line-range check + fragments), `ground_findings`,
  `apply_grounding` (Option 1 : rétrograde 1 cran + flag `[ungrounded]`, `model_copy` is_approved
  inchangé, no-op si 0 ungrounded). Data models locaux.
- [x] Étape F93-3 : Intégration `execute_code_judge_node` — post-LLM, gardé par
  `settings.judge_grounding_enabled`, `try/except` fail-open total, log observabilité.
- [x] Étape F93-4 : Config `judge_grounding_enabled` (défaut True) + `.env.example` + `.env`.
- [x] Étape F93-5 : Tests — `test_judge_grounding.py` (34 : normalize 4, fragment_grounded 8,
  extract 6 dont filename-exclu, read/resolve 7, ground_finding 6, ground_findings 2, apply 4) +
  2 intégration `test_dspy_nodes.py` (downgrade critical→high+flag / opt-out). **36 nouveaux PASS.**
- [x] Étape F93-6 : Bug trouvé + corrigé pendant les tests — `extract_code_fragments` extrayait
  les filenames (`index.html`) comme chains → false ungrounded (prose-only) OU faux grounded si
  un fichier du repo contenait `index`/`html`. Fix : `_looks_like_filename` + `_FILE_EXTS` exclut
  les filenames (gérés par line-range + _resolve_file). Test `test_filename_exclu_des_fragments`.
- [x] Étape F93-7 (Stade A) : py_compile OK + suite Judge ciblée **75/75 PASS**. Suite complète
  **979 passed / 9 failed** dont **8 STRICTEMENT pré-existants** confirmés identiques via `git stash`
  (read_gate×4 + skill_lazy×3 + guard×1, AUCUN lié au grounding) + 1 flaky non reproduit en
  isolation. **0 régression F-93.**
- [x] Étape F93-8 (Stade B) : `debug/run_judge_grounding.py` (déterministe 0 LLM) — valide les 4
  invariants politique Option 1 (ancré conservé, inventé rétrogradé critical→high+flagué,
  prose-only fail-open, is_approved invariant). `debug/run_judge.py` étendu (flag ungrounded).
- [ ] Étape F93-9 (Stade B live) : `debug/run_architect.py` (nœud Architect isolé GPU) produit un
  ArchitectOutput réaliste (vrais target_files + critères F-90) pour ancrer le test grounding.
- [x] Étape F93-10 (Stade C) : run E2E `FRESH_START=1 JUDGE_GROUNDING_ENABLED=1` Bubble Sort
  lancé (~57 min, **tué par décision utilisateur** — trajectoire estimée 1,5-2 h, F-93 étant
  par ailleurs validé). **Intégration tenue** : boot sain (Router=HTML, Architect plan 3-fichiers,
  Recall 8 leçons), 23 Coder steps, Judge iter 1 a rejeté normalement (`ts-html-structure REJETÉ`
  → DuckDB), **grounding silencieux = 0 ligne « ungrounded »/« grounding » dans le log → 0 faux
  flooding, 0 crash, fail-open confirmé en prod**. Les 2 exceptions sont des `Connection error`
  llama-server transitoires (infra, pas F-93). Le déclenchement positif (downgrade d'un finding
  halluciné) est probabiliste et n'a pas été observé sur la portion de run ; l'objectif d'intégration
  (« F-93 marche dans la vraie chaîne sans casser le Judge ») est atteint. Log : `logs/e2e_f93_run.log`.

> **Décision clé (politique)** : Option 1 (non-destructive)而非 Option 2/3 (recompute verdict).
> Le grounding ne peut JAMAIS approuver à tort (is_approved inchangé). La phase de calibrage
> collecte les flags `[ungrounded]` pour que le Meta-Analyste (P15) mesure le taux de faux-positifs
> avant toute automation. Complément orthogonal à F-70 (métriques quantitatives) : vérification
> d'intégrité qualitative en ligne.

## Jalons de l'Itération (cycle fix F-53 — isolation git du run dir anti-pollution repo principal)
> Bug signalé en bonus de la PR #61 : `git_snapshot` (F-53) avait créé un commit vide « Iteration 1 »
> dans le **repo principal** pendant un run E2E (reflog `9e860af`, droppé ensuite). Le `.git` du run
> est censé vivre dans `runs/<dated>/` (gitignoré), pas polluer le repo parent.

- [x] F53-1 : **Diagnostic**. Le code reposait sur `_run_git(cwd=None)` (hérite du cwd process) +
  garde Python `os.path.isdir(".git")` qui ne vérifie que le `.git` direct. Or **git remonte
  l'arborescence** pour découvrir un repo : si pour quelque raison que ce soit (cwd erroné, `.git`
  non créé, env `GIT_DIR`, etc.) le repo découvert n'est pas le run dir, le commit atterrit dans le
  parent. Preuve : `git show 9e860af` = commit vide (`--allow-empty`, signature exacte de
  `commit_iteration`) sur parent `81773e3` (état détaché droppé). Les run dirs ont bien un `.git`
  imbriqué → l'isolation marche *en principe*, mais aucun garde logiciel ne garantit l'isolation
  en cas de divergence cwd/decouverte.
- [x] F53-2 : **Fix de robustesse** (TDD). `git_snapshot.py` : (a) param `repo_path` optionnel sur
  les 4 fonctions publiques (`init_run_git`/`commit_iteration`/`get_last_diff`/`has_git_history`),
  rétrocompatible (défaut `None` = cwd process, les 12 tests existants inchangés) ; (b) toutes les
  commandes git passent `cwd=repo_path` (cwd-indépendant) ; (c) **garde défensive `_is_isolated`**
  qui compare `git rev-parse --show-toplevel` au run dir attendu (Windows-safe : `normcase`+`normpath`)
  et **REFUSE** toute opération si le repo découvert n'est pas le run dir. `workflows.py` passe
  `run_output_dir` explicitement aux 3 call sites (init/commit/get_diff).
- [x] F53-3 : **Tests** : 6 nouveaux tests `TestIsolationRobustesse` (init/commit/diff/history avec
  `repo_path` depuis un cwd ailleurs + **garde anti-pollution** : un run dir sans `.git` propre
  découvrant un parent ne crée AUCUN commit dans le parent + vérif toplevel après init). RED → GREEN.
  Fichier `test_git_snapshot.py` : 12 → 18 passed.
- [x] F53-4 : **Validation** : suite complète **908 passed / 8 failed** — les 8 échecs sont
  **pré-existants** (test_read_gate ×4 + test_skill_lazy_loading ×3 + test_guard ×1), confirmés sur
  main via `git stash` (test_guard échoue aussi sur main, non lié à F-53). **0 régression**.
  Note : `test_output_dir::test_e2e_resume_reuses_same_run_dir` est **flaky minute-boundary** par
  construction (run 1 clear le checkpoint ligne 966 + run_id diffère entre les 2 runs → run 2 ne
  reprend jamais via checkpoint, passe uniquement si les 2 runs tombent dans la même minute). À
  durcir dans un cycle dédié (hors scope F-53).

## Jalons de l'Itération (cycle F-61 Meta-Analyste — post-mortem run partiel 1h30)
> Rôle Meta-Analyste (AGENTS.md §8). Run E2E `bubble-sort-multifile-v6` lancé puis interrompu
> après 1h30 (trop long). `run_analyzer.py` sur le log partiel → diagnostic confirmé par lecture code.

- [x] F61-1 : Run E2E + `run_analyzer.py` → métriques brutes : **17,4M tokens input** (vs 7,5M
  pour run9 *complet*), 111 steps, 4 restarts Tester, 6 crashes « Pydantic→sauvetage DSPy→Connection error ».
- [x] F61-2 : **Diagnostic corrigé** (1ère hypothèse partiellement fausse). (a) P2 « compaction
  screenshots » était **DÉJÀ implémenté** (`apply_image_purge` compaction.py:22, appelé inconditionnellement
  dans `write_memory_to_messages`) — mon grep initial l'avait manqué. (b) Vraie cause des 5 retries :
  `_tester_max_steps_fallback` (nodes.py:189) **retournait `None` en l'absence de signal PASS/FAIL** →
  retry complet du Tester → qui re-thrash (`import os`, navigation sans assertion) → pas de signal →
  `None` → retry ×5. Le sauvetage DSPy crash en Connection error est un symptôme secondaire (payload
  énorme renvoyé au serveur surchargé), il rend `None` proprement et passe la main au fallback.
- [x] F61-3 : **Correctif P1 appliqué** (scope approuvé : « robustesse extraction verdict Tester ») :
  (1) `_tester_max_steps_fallback` ne retourne **PLUS None** — verdict `failure` « Tester n'a pas convergé »
  par défaut (tue la boucle de retries : un run max_steps sans conclusion est lui-même un signal).
  (2) `extract_and_validate` (models.py) tronque le `broken_text` du sauvetage à 6000 chars (défensif,
  anti Connection error sur payload énorme). P2 : rien (déjà fait). P3 droppé (snip threshold irrelevant
  à max_steps=8).
- [x] F61-4 : **Validation** : 5 tests `TestTesterMaxStepsFallback` PASS (dont 1 mis à jour
  `test_fallback_failure_si_aucun_signal`). Suite complète **902 passed / 8 failed** — les 8 échecs
  (test_read_gate ×4 + test_skill_lazy_loading ×3-4) sont **pré-existants**, confirmés strictement
  identiques via `git stash` (documentés F-82). **0 régression**. py_compile OK.

## Jalons de l'Itération (cycle Intégration formelle des fiches 30-44 — doc/cohérence)
> Fait suite au commit `dfcea24` (ajout brut des 15 dépôts fiches 30-44). Périmètre = travail
> documentaire uniquement (AUCUN code de production modifié, AUCUN test impacté). Miroir de F-66
> (qui avait intégré les fiches 19-23).

- [x] Étape IF30-1 : Lecture des 15 fiches 30-44 (en-têtes, notes globales, composants) + diagnostic
  — les bullets « Nouvelles Références d'Audit (Batch Août 2026) » en bas du plan étaient un DUMP
  BROUILLON avec numérotation incohérente (`fiche **19-Understand-Anything**`, `**XX-prime-agent**`,
  `**40-skills**`...) non distribué dans les priorités.
- [x] Étape IF30-2 : Distribution des bullets dans les sections de priorité cibles (P0-bis, P2, P3,
  P4, P6, P6-bis, P6-ter, P8, P8-bis, P9, P10, P11) en cases `[ ]` propres — numérotation corrigée
  (30-44 canonique), références `file:symbol` préservées, 12 nouvelles cases datées 2026-08-12.
- [x] Étape IF30-3 : Suppression du dump brut (120 lignes, anciennes lignes 427-548). Plan passé de
  549 à 468 lignes (vérifié : 0 marqueur `Nouvelles Références`, 0 numéro de fiche stale).
- [x] Étape IF30-4 : Création de 4 features formelles F-93..F-96 dans `feature_list.json` pour les
  workstreams les plus substantiels — F-93 grounding findings Judge (langextract, P6), F-94 capteur
  santé structurelle (sentrux, P6/P15), F-95 robustesse FS transactions/locks/IO allowlist (OpenKB,
  P8-bis), F-96 harnais évaluation skills (Anthropic skills, P10). **95 features total, JSON valide.**
- [x] Étape IF30-5 : Correction des en-têtes internes de 12 fiches sur 15 (mauvais numéros 19/XX/40/21
  → 30-44 canonique ; 3 fiches déjà correctes 30-Ix/31-Scrapling/34-brooklyn laissées intactes).
- [x] Étape IF30-6 : `INDEX.md` rendu cohérent — compteurs (29→44 projets, 494→569 entrées, date
  2026-08-12), tableau de navigation complété (15 lignes, 44 fiches), arbre du dossier complété
  (29-44). `references-audit/README.md` : 494→569.
- [x] Étape IF30-7 : Branche `docs/integration-fiches-30-44` + commit.

## Jalons de l'Itération (cycle Tester fonctionnel — F-20)
- [x] Étape TF-1 : Diagnostic (4 causes racines : skill aveugle logique, noms MCP faux, spec non propagée, Judge sans requirements).
- [x] Étape TF-2 : Skill web-tester réécrit (noms puppeteer_* + étape "Functional Logic Testing" via puppeteer_evaluate).
- [x] Étape TF-3 : Propagation spec complète (workflows seed_content → sub_dict original_content → tester prompt "CAHIER DES CHARGES").
- [x] Étape TF-4 : Judge équipé (CodeJudgeSignature + task_requirements).
- [x] Étape TF-5 : max_steps tester 20→24 (marge assertions).
- [x] Étape TF-6 : tests/test_web_tester_functional.py (11 tests). Suite 212 passed / 0 failed.
- [x] Étape TF-7 : Validation standalone (run_tester.py) — VALIDÉ ✅
  Le tester écrit de vraies assertions (puppeteer_evaluate + IIFE), détecte que le
  tableau n'est pas trié → FAIL documenté. Avant : "success" à tort. Itération skill
  via script standalone (~3 min) au lieu du workflow complet (~30 min).
- [x] Étape TF-8 : Corrections skill (syntaxe IIFE anti "Illegal return statement",
  résolution 1280×800, champ ASSERTIONS FONCTIONNELLES au rapport).
- [x] Étape TF-9 : Outil run_tester.py (tester isolé, itération rapide).

## Jalons de l'Itération (cycle Context7 — doc libs à jour)
- [x] Étape C7-1 : Exploration (API Context7, 3 nœuds, patterns de test) + plan approuvé.
- [x] Étape C7-2 : Module context7_tool.py (get_context7_tools + fetch_context7_brief, dégradation gracieuse).
- [x] Étape C7-3 : Skill context7-research (workflow stratégique : QUAND chercher = libs externes uniquement).
- [x] Étape C7-4 : Branchement skills_loader (socle Coder + règle dynamique libs).
- [x] Étape C7-5 : Coder (outils + prompt nuancé) + Architect (pré-fetch brief + garde-fou vanilla) + web-tester (outils).
- [x] Étape C7-6 : tests/test_context7_tool.py (13 tests, mock réseau, 0 dépendance réseau).
- [x] Étape C7-7 : Suite pytest → 201 passed / 0 failed (188 avant + 13 nouveaux).
- [ ] Étape C7-8 : Validation run Bubble Sort (Context7 dormant sur vanilla).
- [ ] Étape C7-9 : Validation run avec lib externe (Context7 en action).

## Jalons de l'Itération (cycle Tester polyvalent + stderr)
- [x] Étape A : Planification + exploration (détection techno, skills_loader, config).
- [x] Étape B : feedback_utils.py (troncature head+tail + truncate_history) + tests (15 PASS).
- [x] Étape C : config.py (settings test_timeout_s, stderr_head/tail_lines, feedback_max_chars).
- [x] Étape D : Package testers/ (base+detect_tech, web_tester refactor, python_tester subprocess).
- [x] Étape E : Nœud execute_tester_node refondu en dispatcher (nodes.py).
- [x] Étape F : skills_loader couche dynamique techno→skill pour le tester (select_skills_for_tester).
- [x] Étape G : Skills web-tester (enrichi) + python-tester (nouveau).
- [x] Étape H : Brancher troncature aux 3 points (dspy_nodes, workflows, tools/bash_command).
- [x] Étape I : Tests (tech_detection, python_runner, tester_dispatch, intégration troncature).
- [x] Étape J : uv run pytest tests/ → 185 passed, 2 failed (les 2 échecs sont PRÉ-EXISTANTS
  sur main dans test_extract.py, hors périmètre ce cycle). +45 tests vs base.
- [ ] Étape K : contract.md + feature_list + plan cochés + log/progress fin + PR.

## Jalons de l'Itération (test process complet)
- [x] Étape 1 : Prompt de test (tasks.json → landing page Nimbus) + reset KG.
- [x] Étape 2 : Corrections préventives (Context7, duplication router/judge, flushing).
- [x] Étape 3 : Réécriture du Coder (garde anti-vide, prompt anti-boucle, skills ciblés).
- [x] Étape 4 : Création skills file-creation + frontend-design + skills_loader (2 couches).
- [x] Étape 5 : Robustesse matérielle (FAST_MAX_TOKENS, LLM_TIMEOUT_S=600, Modelfile bigctx).
- [x] Étape 6 : Optimisations vitesse (Architect 3 sous-tâches, skills allégés, num_predict 4000).
- [x] Étape 7 : Étude références (crush/openfox/nanocode) + évaluation Nanbeige (abandonné).
- [x] Étape 7bis : Audit détaillé des projets (crush, nanocode, openfox) extrait dans references_audit.md.
- [x] Étape 8 : Run #11 → process multi-agent VALIDÉ de bout en bout (boucle Coder→Judge→feedback).
- [x] Étape 9 : PR #2 mergée (Kilo review SUCCESS). Stratégie modèles définie (Gemma4 GPU / distant CPU).
- [x] Étape 10 (cycle SEARCH/REPLACE) : outil search_replace tolérant (portage Aider) + Mutex par fichier.
  search_replace_utils.py + tools.py + Coder équipé + 11 tests unitaires PASS.
- [x] Étape 11 : Run validation (Coder utilise search_replace → HTML non corrompu) — Run #12 VALIDÉ.
- [x] Étape 11.5 : Mise à jour de l'architecture avec les principes de juillet 2026 (Ng, Anthropic, Google).
- [x] Étape 12 (cycle CHECKPOINTS) : Persistance d'État (Priorité 3). Table `checkpoint`
  dans DuckDB + run_id stable (hash du contenu de tâche) + branchement save/load dans
  run_coding_workflow (skip Architect + skip sous-tâches completed + reprise à l'itération).
  Granularité "début d'itération" (sûre/idempotente). Config FRESH_START. 12 tests PASS.
- [x] Étape 13 : Run validation reprise (interrompre un run CPU-only, relancer → reprise).
  Run #13 VALIDÉ en conditions réelles : cycle complet bout-en-bout avec crashs répétés,
  reprise automatique (skip Architect + skip sous-tâches validées), 3 fichiers générés
  (index.html 12 533 o, styles.css 14 033 o, script.js 7 285 o). Checkpoint effacé en fin.
- [ ] Étape 14 : Cycle suivant (Priorité 2 stderr / Nœud d'Escalade / Repo Map / CodeAgent).

## Jalons de l'Itération (cycle Nœud d'Escalade — F-23)
- [x] Étape ESC-1 : Planification approuvée (stratégie Diagnostic seul + persistance KG).
- [x] Étape ESC-2 : Modèle EscalationOutput (models.py).
- [x] Étape ESC-3 : Signature DSPy + execute_escalation_node (dspy_nodes.py).
- [x] Étape ESC-4 : Config escalation_enabled (config.py + .env.example).
- [x] Étape ESC-5 : Branchement workflows.py (remplacer max_iterations_reached).
- [x] Étape ESC-6 : Tests tests/test_escalation.py (8 tests, 0 LLM).
- [x] Étape ESC-7 : Suite pytest complète (220 passed / 0 failed).
- [x] Étape ESC-8 : Docs (contract.md, plan, README) + finalisation état disque.

## Jalons de l'Itération (cycle Auto-Dépendances — F-26)
- [x] Étape AD-1 : Planification approuvée (pip install non-persistant + validation regex + cap 1 retry).
- [x] Étape AD-2 : config.py + .env.example (auto_install_deps opt-out, valeur par défaut pour pas casser les helpers de test).
- [x] Étape AD-3 : python_tester.py (extract_missing_module + _install_module + branchement dans run()).
- [x] Étape AD-4 : tests/test_python_runner.py (extract unitaire + comportement auto-install + contrat _install_module).
- [x] Étape AD-5 : Suite pytest → 232 passed / 0 failed (220 avant + 12 nouveaux). 0 régression.
- [x] Étape AD-6 : Docs (contract.md +7 critères, plan, README) + finalisation état disque.

## Jalons de l'Itération (cycle Découpage incrémental — F-28, CodeAgent P0)
- [x] Étape DI-1 : 2e comparatif gros fichier inline INTERROMPU (1h, step 1 non fini) → gros
  write_file monolithique INEXPLOITABLE sur CPU-only. Le problème = le PATTERN, pas le type d'agent.
- [x] Étape DI-2 : 2 audits (references + web) — gap append_file confirmé (aucun projet ne l'a).
  Pattern n°1 recommandé pour petits modèles CPU = accumulateur incrémental.
- [x] Étape DI-3 : Plan approuvé (outil append_file + tests + prompt incrémental + branchement).
- [x] Étape DI-4 : append_file dans tools.py (mutex + gardes + feedback + anti-doublon léger).
- [x] Étape DI-5 : tests/test_append_file.py (8 tests, 0 LLM) — 8/8 PASS.
- [x] Étape DI-6 : Branchement append_file au Coder prod (nodes.py coder_tools) — additif non-cassant.
  Suite pytest 240 passed / 0 failed (232 avant + 8 nouveaux).
- [x] Étape DI-7 : prompts/dashboard_admin_incremental.md (workflow squelette + append section par section).
- [x] Étape DI-8 : Scripts comparatifs équipés (append_file dans tools des 2 scripts + prompt CodeAgent adapté).
- [x] Étape DI-9 : Runs comparatifs TCA vs CodeAgent sur le dashboard incrémental.
  RÉSULTAT : Le modèle (gemma-4-e4b) écrivait un squelette vide mais échouait à faire les `append_file` suivants.
  SOLUTION : Ajout d'une garde anti-squelette HTML dans `write_file` pour interdire la stratégie incrémentale sur ces fichiers et forcer l'écriture monolithique. Test validé : le CodeAgent a généré les 280 lignes d'un coup avec succès.
- [x] Étape DI-10 : Décision : Le garde-fou a été corrigé (regex DOTALL) et poussé en PR. L'utilisation du CodeAgent est confirmée car il génère correctement le fichier d'un bloc.

## 🗺️ Feuille de route Finalisation (P1-P3, décidée 2026-07-31)
Ce cycle (CodeAgent + append_file) a révélé 4 gaps qui s'emboîtent. Le workflow actuel
marche sur du simple (Bubble Sort) mais SOUFFRE sur le gros/multi-étapes (dashboard).
P1-P3 = finaliser (P4 = optimisations secondaires, hors périmètre immédiat).

### P1 — Migrer le Coder vers CodeAgent (IMMÉDIAT, ce cycle)
- [x] Preuves empiriques réunies (3 comparatifs convergent).
- [x] Migration execute_coder_node : ToolCallingAgent → CodeAgent + prompt Python (F-32).
- [x] Guard logiciel anti-déraillement (F-33 : idle step + parsing cassé).
- [ ] Validation run réel final (étape suivante).

### P2 — Architect évolué : stratégie de découpage adaptative (F-29, cycle suivant)
- [x] Enrichir ArchitectSignature : stratégie par sous-tâche (simple | incrémental | multi-fichier).
- [x] Décision techno-driven (HTML/CSS/JS=multifile par défaut, Python/TS=multifile, monolithe imposé=incremental).
- [x] L'Architect dicte au Coder COMMENT construire, pas juste QUOI (propagation sub_dict).
- [x] Tests (6 PASS).

### P3 — Linter Shift Left (F-30 = P7 plan usine logicielle, cycle d'après)
- [x] Nœud linter léger (tree-sitter multi-langue + py_compile) entre Coder et Tester.
- [x] Boucle fermée : syntaxe invalide → court-circuite le Tester coûteux → feedback Coder.
- [x] Couverture multi-langue : Python, HTML, CSS, JS, TS, TSX (17 tests PASS).
- [x] Branchement workflow (DuckDB réfutation source='linter' + continue).

### État validation
- [x] Suite pytest 271 passed / 0 failed (240 avant + 31 nouveaux). 0 régression.
- [x] Import workflow complet OK (pas de circularité).
- [ ] Run réel de validation (uv run python -m graph_orchestrator.workflows) — étape suivante.

### Hors finalisation (P4, à évaluer plus tard)
- F-31 : Tester en mode CodeAgent (2e candidat, optimisation potentielle, non urgent).
- F-34 : Nœud d'Audit Dette Technique (python-health-audit via uvx) en fin de workflow.
- File viewer fenêtré SWE-agent ACI (lourd, optionnel).
- 5 nœuds sans tools (Worker/Judge/Synth/Adversary) : CodeAgent inutile, ne pas migrer.
- **F-50 : Scripts d'isolation « l'agent joue le rôle du nœud » pour dépannage/validation rapide.**
  Idée : systématiser le pattern qui a si bien marché sur F-49 (l'agent injecte des
  entrées buggées et valide la sortie en <6s, au lieu de lancer le workflow complet de
  ~25 min). Un script d'isolation par nœud, qui fournit le contexte minimal et appelle
  la VRAIE fonction de production (zéro dérive de comportement). Bénéfices :
  - **Dépannage rapide** : itérer sur un nœud (prompt, skill, logique) sans relancer tout
    le graphe. Retour en secondes, pas en dizaines de minutes.
  - **Détection de régressions** : inputs buggés connus → assertion sur le verdict.
  - **Onboarding/debug** : comprendre le contrat entrée/sortie d'un nœud en l'exécutant
    isolément avec des données contrôlées.
  Nœuds candidats (par ordre de valeur) :
  1. **Tester** (`run_tester.py` existe déjà F-46) — étendre aux autres runners.
  2. **Coder** (`run_coder.py` / `prompts/bubble_sort_spec.md` existe déjà isolation) —
     formaliser en script réutilisable avec spec en entrée.
  3. **Static Tester** (`debug/validate_static_tester_live.py` existe déjà F-49) — garder.
  4. **Linter** — injecter fichiers buggés (TS, Python IndentationError, contenu après
     </html>) et valider le court-circuit.
  5. **Architect / Router / Judge** — injecter specs/prompt et valider le JSON de sortie
     (DSPy, moins évident à isoler mais faisable via signature directe).
  6. **Security Reviewer** — injecter code vulnérable (XSS, eval) et valider le verdict.
  Convention : un dossier `debug/isolation/` avec un script par nœud, documentation du
  contrat d'entrée (quoi fournir) et d'attentes (quoi vérifier). Réutilise les fixtures
  déjà écrites dans les tests unitaires.

## Jalons bootstrap (faits)
- [x] Création agent.md (specs gestion d'état).
- [x] Initialisation feature_list.json, contract.md, progress.md.

## Jalons de l'Itération (cycle CodeAgent — Priorité 0, transition ToolCallingAgent→CodeAgent)
- [x] Étape CA-1 : Analyse codebase (7 ToolCallingAgent + 1 CodeAgent mort). Seul le
  Coder est un vrai candidat (5 agents sans tools = pas de bénéfice, Security en DSPy).
- [x] Étape CA-2 : Plan approuvé (2 scripts séparés, mode TCA import direct prod,
  mode CodeAgent expérimental, isolation stricte des répertoires).
- [x] Étape CA-3 : run_coder_tca.py (import execute_coder_node, OUT_DIR=tca/ isolé+nettoyé).
- [x] Étape CA-4 : run_coder_codeagent.py (CodeAgent, prompt final_answer Python,
  extraction maison, OUT_DIR=codeagent/ isolé+nettoyé).
- [x] Étape CA-5 : .gitignore + codeagent_compare/ (artefacts jetables).
- [ ] Étape CA-6 : Vérification imports + syntaxe (py_compile).
- [x] Étape CA-7 : Runs comparatifs (TCA puis CodeAgent) — TERMINÉ. Les 2 réussissent
  sur Bubble Sort (borné). CodeAgent gagne sur tokens IN (-63%) et durée (-19%).
  Résultats consignés dans le journal d'événements (migré DuckDB).
- [ ] Étape CA-8 : Décision : migrer execute_coder_node vers CodeAgent (si gain prouvé)
  OU garder TCA (si CodeAgent n'apporte rien). Création feature F-XX le cas échéant.
  → EN ATTENTE : un 2e test sur contenu plus lourd (multi-fichiers / HTML 3000+
  lignes) confirmerait le gain sur le scénario-douleur (corruption JSON du TCA).


## Jalons de l'Itération (Amélioration Plan Usine Logicielle)
- [x] Étape 1 : Analyse des audits LlamaBot, Deer Flow, Crush, OpenCode, Aider.
- [x] Étape 2 : Création de l'artefact Implementation Plan soumis pour validation.
- [x] Étape 3 : Application des modifications au plan_usine_logicielle.md.
- [x] Étape 4 : Mise à jour de progress.md et feature_list.json.

## Jalons de l'Itération (Output daté par run — F-40, Priorité 13)
- [x] Étape OD-1 : Exploration points d'insertion (KG instantiation, checkpoint, run_id critique,
  load_tasks_from_json relatif) + décision design (date + persistance checkpoint pour préserver
  la reprise — le timestamp seul l'aurait cassée).
- [x] Étape OD-2 : config.py + .env.example — output_dir (défaut runs).
- [x] Étape OD-3 : workflows.py — _slugify + _resolve_run_output_dir + _scoped_chdir (context
  manager finally) + branchement (KG avant chdir, corps wrappé dans with) + persistance checkpoint.
- [x] Étape OD-4 : Refactor indentation corps 350 lignes (script Python + py_compile + suite
  381 passed = 0 cassé).
- [x] Étape OD-5 : tests/test_output_dir.py (13 PASS) — slugify, resolve, scoped_chdir, E2E
  (Coder écrit dans run dir + reprise même dossier + kg_path stable). Correctif mock linter
  (module source, pas workflows).
- [x] Étape OD-6 : Suite pytest complète → 394 passed / 0 failed (381 + 13). 0 régression.
- [x] Étape OD-7 : État disque synchronisé (contract.md +9 critères 105-113, feature_list.json
  +F-40, progress.md, plan_usine_logicielle.md case P13 cochée, .gitignore runs/).

## Jalons de l'Itération (nœud PromptRefiner — F-39, meta-prompt avant l'Architect)
- [x] Étape PR-1 : Exploration (Router/Architect DSPy, checkpoint, test patterns) + recherche web
  Kilo Code/Cline "Enhance Prompt" (sources consignées). Plan approuvé (Phase 1 seule ;
  Phase 2 MIPROv2 écartée — signal biaisé mono-modèle 6 Go VRAM).
- [x] Étape PR-2 : models.py PromptRefinerOutput (refined_prompt + ambiguities_detected).
- [x] Étape PR-3 : dspy_nodes.py — PromptRefinerSignature (2 inputs, docstring pipeline aligné
  Kilo/Cline/open-swe) + _build_capabilities_summary (catalogue complet via list_skills, repli
  défensif dossier skills/, statut Context7, testers statiques) + execute_prompt_refiner_node
  (clone execute_router_node, gemma REASONING, dégradation None,None).
- [x] Étape PR-4 : config.py + .env.example — prompt_refiner_enabled (défaut True).
- [x] Étape PR-5 : workflows.py — branchement APRÈS run_id (critique : hash stable) AVANT Router +
  checkpoint refined_prompt (skip LLM à la reprise).
- [x] Étape PR-6 : tests/test_prompt_refiner.py (8 tests). BUG DÉCOUVERT + CORRIGÉ : les 3 helpers
  E2E existants (test_escalation/test_checkpoint/test_feedback_integration) ne mockaient pas
  execute_prompt_refiner_node → le workflow appelait le VRAI LLM en test → hang. Correctif :
  ajout d'un mock passe-through (None → repli prompt brut) dans les 3 helpers.
- [x] Étape PR-7 : Suite pytest complète → 379 passed / 0 failed (371 avant + 8 nouveaux). 0 régression.
- [x] Étape PR-8 : État disque synchronisé (contract.md +9 critères 96-104, feature_list.json
  +F-39, progress.md, plan_usine_logicielle.md +Priorité 12 +Phase 2 chantier futur, README.md,
  .env.example). Commit + push + PR.

## Jalons de l'Itération (cycle 3 tâches rapides : Anti-Loop P3 + Nettoyage DOM P6 + Guard bash P8-bis)
- [x] Étape TR-1 : Sélection des 2 tâches les plus rapides et isolées du plan (P3 ligne 73
  + P6 ligne 108). Écart de l'Anti-Loop SHA256 (nodes.py) et du Nettoyage DOM (web_tester.py).
  Note archi : dépôt sans LangGraph (pas de GraphState), checkpoints ne rechargent pas la
  mémoire smolagents → "Orphan Repair" (P8) écarté (N/A).
- [x] Étape TR-2 (Tâche 1 — Anti-Loop, F-36) : loop_guard.py (compute_tool_call_fingerprint
  SHA256 + LoopGuard.record/repeated_action/reset + extract_tool_calls_from_step pour
  ToolCallingAgent ET CodeAgent). Config LOOP_GUARD_ENABLED/THRESHOLD. Branché dans
  run_with_retry (param optionnel non-cassant) via execute_coder_node.
- [x] Étape TR-3 (Tâche 2 — Nettoyage DOM, F-37) : dom_filter.py (clean_dom_for_llm,
  regex précompilées, sans dépendance). Branché dans web_tester.py (directive prompt +
  snippet JS côté navigateur).
- [x] Étape TR-4 : Tests (test_loop_guard.py 16 tests + test_dom_filter.py 18 tests).
  Correction marqueur async (@pytest.mark.anyio, pas asyncio — projet utilise anyio).
- [x] Étape TR-5 : Suite pytest complète → 305 passed / 0 failed (271 avant + 34 nouveaux).
  0 régression. Seuls warnings = DeprecationWarning DSPy (préexistants, hors périmètre).
- [x] Étape TR-6 : État disque synchronisé (contract.md +16 critères 72-87, feature_list.json
  +F-36/F-37, progress.md, plan_usine_logicielle.md, .env.example).
- [x] Étape TR-7 (Tâche 3 — Guard bash denylist, F-38, P8-bis) : bash_guard.py
  (check_bash_command, denylist regex case-insensitive Unix+Windows+cross, message
  pédagogique jamais d'exception). Branché dans tools.py bash_command AVANT subprocess.run.
  Config BASH_GUARD_ENABLED. Patterns debuggés via fichier temp (lookbehind/lookahead pour
  flags /s /q /f, `-[rRfF]{1,3}` pour rm). 66 tests PASS.
- [x] Étape TR-8 : Suite pytest complète → 371 passed / 0 failed (305 avant + 66 nouveaux).
  0 régression.
- [x] Étape TR-9 : État disque synchronisé (contract.md +8 critères 88-95, feature_list.json
  +F-38, progress.md, plan_usine_logicielle.md P8-bis ❌→🟡 + sous-case guard, README.md,
  .env.example). Commit + push + PR.

## Jalons de l'Itération (cycle 2 tâches rapides : Anti-Loop P3 + Nettoyage DOM P6)
- [x] Étape TR-1 : Sélection des 2 tâches les plus rapides et isolées du plan (P3 ligne 73
  + P6 ligne 108). Écart de l'Anti-Loop SHA256 (nodes.py) et du Nettoyage DOM (web_tester.py).
  Note archi : dépôt sans LangGraph (pas de GraphState), checkpoints ne rechargent pas la
  mémoire smolagents → "Orphan Repair" (P8) écarté (N/A).
- [x] Étape TR-2 (Tâche 1 — Anti-Loop, F-36) : loop_guard.py (compute_tool_call_fingerprint
  SHA256 + LoopGuard.record/repeated_action/reset + extract_tool_calls_from_step pour
  ToolCallingAgent ET CodeAgent). Config LOOP_GUARD_ENABLED/THRESHOLD. Branché dans
  run_with_retry (param optionnel non-cassant) via execute_coder_node.
- [x] Étape TR-3 (Tâche 2 — Nettoyage DOM, F-37) : dom_filter.py (clean_dom_for_llm,
  regex précompilées, sans dépendance). Branché dans web_tester.py (directive prompt +
  snippet JS côté navigateur).
- [x] Étape TR-4 : Tests (test_loop_guard.py 16 tests + test_dom_filter.py 18 tests).
  Correction marqueur async (@pytest.mark.anyio, pas asyncio — projet utilise anyio).
- [x] Étape TR-5 : Suite pytest complète → 305 passed / 0 failed (271 avant + 34 nouveaux).
  0 régression. Seuls warnings = DeprecationWarning DSPy (préexistants, hors périmètre).
- [x] Étape TR-6 : État disque synchronisé (contract.md +16 critères 72-87, feature_list.json
  +F-36/F-37, progress.md, plan_usine_logicielle.md, .env.example).

## Jalons de l'Itération (P8 — Orphan Repair, anti-corruption d'historique, F-41)
- [x] Étape OP-1 : Contexte — P8 du plan (ligne 129), blueprint s08_context_compact, structure smolagents memory.steps/ActionStep lue.
- [x] Étape OP-2 : `orphan_repair.py` — niveau messages (`repair_orphan_tool_results`, FAKE_INTERRUPTED={{status:error,error:Interrompu}}) gérant tool_use + forme sérialisée type=function/function.name, réponse via tool_use_id/tool_call_id/id.
- [x] Étape OP-3 : `orphan_repair.py` — niveau steps (`repair_orphan_steps` : ActionStep avec tool_calls sans observations/error/is_final_answer → observations=FAKE_INTERRUPTED).
- [x] Étape OP-4 : Intégration défensive (`try/except Exception: pass`) dans `nodes.run_with_retry` (bloc P8, ~lignes 174-189) AVANT chaque `agent.run`.
- [x] Étape OP-5 : Tests — `tests/test_orphan_repair.py` 11 tests ; vérif `orphan+guard+loop_guard` = 35 passed ; suite complète = 405 passed / 0 failed (0 régression).
- [x] Étape OP-6 : État disque synchronisé — feature_list.json +F-41, contract.md +critères 114-121, plan_usine_logicielle.md P8 [x], progress.md, README.md.

## Jalons de l'Itération (P8 — Sanitizer, Auto-typage des arguments d'outil, F-42)
- [x] Étape SZ-1 : Contexte — petit LLM émet des args malformés (offset="1, 80", replace_all="true") → TypeError validation smolagents → retries gaspillés. Flux de validation tracé (agents.py:1476 validate_tool_arguments). Chemin CodeAgent confirmé : executor local expose les outils et les appelle via `__call__` directement (PAS execute_tool_call/validate_tool_arguments) → proxy `__call__` intercepte avant `forward`.
- [x] Étape SZ-2 : `sanitizer.py` niveau coercition — `_parse_string_to_structure` (json.loads→ast.literal_eval fallback), `_coerce_integer` (dernier entier d'une chaîne), `_coerce_number`, `_coerce_boolean` (true/1/yes/on→True), `coerce_value` (array/object/string/None respecté, best-effort), `sanitize_tool_arguments` (clés connues seulement, non-dict intact).
- [x] Étape SZ-3 : `sanitizer.py` niveau proxy — `SanitizedTool(BaseTool)` copie name/description/inputs/output_type, intercepte `__call__` pour coerçer kwargs avant de déléguer à l'outil réel ; `wrap_tool` + `sanitize_tools(enabled)` no-op quand disabled.
- [x] Étape SZ-4 : Config `sanitizer_enabled` (env `SANITIZER_ENABLED`, défaut True) dans `config.py` (champ dataclass + load_settings).
- [x] Étape SZ-5 : Branchement `nodes.execute_coder_node` + `execute_architect_node` via `sanitize_tools(..., enabled=settings.sanitizer_enabled)`.
- [x] Étape SZ-6 : Tests — `tests/test_sanitizer.py` 23 tests (coercion 13 + sanitize 4 + proxy 3 + wrap 3) ; 23/23 PASS.
- [x] Étape SZ-7 : Suite pytest complète → 417 passed / 0 failed (394 baseline + 23 nouveaux), 0 régression. web_tester_functional désélectionné (nécessite Chrome/npx).
- [x] Étape SZ-8 : État disque synchronisé — feature_list.json +F-42, contract.md +critères 122-129, progress.md, README.md.

## Jalons de l'Itération (P8-bis — Idempotence des effets de bord, F-43)
- [x] Étape ID-1 : Contexte — replays de checkpoint réappliquent les effets de bord non-idempotents (append_file, pip install). Référence qm idempotency-store.ts (once(key, fn), inflight + done + backing + rétention 14j). Mécanisme de replay tracé (save_coding_state granularité début d'itération → Coder rejoue).
- [x] Étape ID-2 : `idempotency.py` — `IdempotencyStore` (once/committed/reset/_prune_if_due, threading.Lock, backing DuckDB) + `make_op_key` + contexte module-level (`_scoped_idempotency`/`get_current_store`/`set_current_store`/`clear_current_store`). Port Python fidèle de qm.
- [x] Étape ID-3 : `knowledge_graph.py` — table `idempotency_record(run_id, op_key, created_at, PK)` + `save_idempotency` (INSERT OR IGNORE) / `is_idempotency_committed` / `prune_idempotency` / `clear_idempotency`. Import `datetime`/`timedelta` ajouté.
- [x] Étape ID-4 : `config.py` + `.env.example` — `idempotence_enabled` (défaut True) + `idempotency_retention_days` (défaut 14).
- [x] Étape ID-5 : Branchement `workflows.py` — store créé après kg+run_id+checkpoint, corps wrappé `with _scoped_chdir(...), _scoped_idempotency(_idem_store):` (composition sans réindentation). `clear_idempotency(run_id)` aux 2 sites `clear_checkpoint` (FRESH_START + fin de run).
- [x] Étape ID-6 : Branchement `tools.py` (`append_file` via `once` + `_do_append` closure, write_file NON wrappé) + `python_tester.py` (`_install_module` via `_install_module_or_raise`/`_InstallFailed`, échec non marqué done).
- [x] Étape ID-7 : Tests — `tests/test_idempotency.py` 25 tests (store 10 + KG 4 + scoped 3 + make_op_key 4 + intégration append 2 + intégration pip 2) ; 25/25 PASS.
- [x] Étape ID-8 : Suite pytest complète → 442 passed / 0 failed (417 baseline + 25 nouveaux), 0 régression. web_tester_functional désélectionné (nécessite Chrome/npx). État disque synchronisé (feature_list.json +F-43, contract.md +critères 130-140, plan_usine_logicielle.md P8-bis [x], progress.md, README.md).

## Jalons de l'Itération (cycle Refonte Prompts — P0 + P0-bis + P6, F-44)
- [x] Étape RP-1 : Cartographie prompts actuels (6 nœuds DSPy docstring + 2 smolagents f-string + 1 déterministe sans prompt ; aucun préfixe commun). Lecture fiches audit 15/16/17 (invariants universels, prompts purs par rôle, prompts open-source citables).
- [x] Étape RP-2 : Création `graph_orchestrator/prompts.py` — fondation partagée (UNIVERSAL_INVARIANTS 10 patterns + ROLE_BLOCKS 9 rôles + build_role_header/with_invariants helpers + build_invariants_header standalone).
- [x] Étape RP-3 : Injection des invariants dans les 6 Signatures DSPy (`dspy_nodes.py`) via `__doc__ = with_invariants(role, doc_métier)`. Mécanisme validé empiriquement (DSPy lit `__doc__` via metaclass — test probe `SigB.instructions` contient rôle+invariants+métier).
- [x] Étape RP-4 : Durcissement Judge (CodeJudgeSignature + docstring enrichi : rubric critical/high/medium/low, in-diff only, anti-nits, professional objectivity, vérification comportementale via task_requirements) + extension additive `CodeJudgeOutput.findings: List[Finding] = []`.
- [x] Étape RP-5 : Durcissement Security (SecuritySignature + docstring enrichi : OWASP Top 10, scores CVSS, defensive-only) + extension additive `SecurityOutput.findings: List[Finding] = []`. Schéma `Finding` (`severity/category/location/description/suggestion`) + `Severity` Literal définis dans models.py.
- [x] Étape RP-6 : Spécialisation prompts smolagents — Coder (`nodes.py`) préfixé par `build_role_header("coder")` (rôle + 10 invariants dont verify-after, type hints, anti-laziness) ; WebTester (`testers/web_tester.py`) préfixé par `build_role_header("web_tester")` (pyramide 70/20/10, pattern AAA, indépendance des tests).
- [x] Étape RP-7 : Suppression ~180 lignes de nœuds smolagents DÉPRÉCIÉS dans `nodes.py` (versions mortes execute_router_node/execute_architect_node/execute_security_reviewer_node/execute_code_judge_node — jamais appelées par run_coding_workflow qui importe les versions DSPy) + imports morts nettoyés (RouterOutput/ArchitectOutput/SecurityOutput/CodeJudgeOutput retirés de l'import nodes.py). Préalable requis par le plan (ligne 42).
- [x] Étape RP-8 : Tests — `tests/test_prompts.py` 40 tests (invariants 2 + rôles paramétrés 17 + build_role_header 3 + with_invariants 2 + signatures DSPy paramétrées 6 + rubric markers 3 + Finding/models 7) ; 40/40 PASS.
- [x] Étape RP-9 : Suite pytest complète → 482 passed / 0 failed (442 baseline + 40 nouveaux), 0 régression. web_tester_functional désélectionné (nécessite Chrome/npx).
- [x] Étape RP-10 : État disque synchronisé (feature_list.json +F-44, contract.md +critères 141-149, plan_usine_logicielle.md P0+P0-bis+P6 cochés, progress.md, README.md).

## Jalons de l'Itération (requête utilisateur)
- [x] Clonage du dépôt awesome-claude-skills dans references/.

## Jalons de l'Itération (cycle Validation Coder — 6 fixes + Architect + timings)
- [x] Étape VC-1 : Fix SanitizedTool.__getattr__ (to_code_prompt délégation — bug CodeAgent crash).
- [x] Étape VC-2 : Fix search_replace arg names (search→old_string, replace→new_string, convention canonique aider/Cline).
- [x] Étape VC-3 : Fix Coder mode CORRECTION (iteration>1 = read_file+search_replace, pas rewrite).
- [x] Étape VC-4 : Fix auto-réparation HTML append_file (déplace </body></html> à la fin, 0 LLM).
- [x] Étape VC-5 : Fix Linter HTML (ignore faux positifs tree-sitter sur CSS/JS inline).
- [x] Étape VC-6 : Fix Architect découpage (règle "1 livrable testable = 1 sous-tâche" + simple par défaut).
- [x] Étape VC-7 : Run GPU validation — Coder one-shot (2 steps/77s, 9726 octets, HTML+BubbleSort complets).
- [x] Étape VC-8 : Analyse timings (debug/TIMINGS_ANALYSE.md) — Tester identifié comme goulot (querySelector, ~30 min).
- [x] Étape VC-9 : Audit utilisateur intégré (audit_coder/ — 7 tests + screenshots, confirme Coder one-shot).
- [x] Étape VC-10 : Suite pytest 482 passed / 0 failed après tous les fixes. Commit.
- [x] Étape VC-11 (cycle suivant) : Fix Tester querySelector (ACTION IMMÉDIATE documentée).

## Jalons de l'Itération (cycle Fix Tester querySelector — F-45)
- [x] Étape F45-1 : Diagnostic empirique (lecture log GPU) — racine corrigée vs hypothèse
  initiale du doc : le modèle écrit `document.querySelector='...'` (assignation `=`) au lieu
  de `document.querySelector('...')` (appel `()`) → écrase la fonction native → boucle fatale.
  Ce n'est PAS "Puppeteer n'expose pas querySelector". Le HTML généré utilise getElementById.
- [x] Étape F45-2 (Axe 1 — Skill web-tester) : directive ciblée anti "querySelector assigné
  vs appelé" (= fatal vs ()) + garde anti-pollution du contexte (jamais réassigner une méthode
  native) + replis robustes getElementById/getElementsByTagName + pattern DOMContentLoaded.
- [x] Étape F45-3 (Axe 2 — Cap steps) : config.py `tester_max_steps` (défaut 12, avant 24
  hardcoded) + .env.example + web_tester.py (max_steps=settings.tester_max_steps).
- [x] Étape F45-4 (Axe 3 — Guard contextuel) : LoopGuard instancié et passé au WebTestRunner
  via run_with_retry + _detect_idle_step contextuel (node_kind='tester' → message puppeteer_*
  /final_answer, pas write_file) ; run_with_retry accepte node_kind (défaut 'coder').
- [x] Étape F45-5 (Tests) : test_guard.py +3 (message contextuel tester/coder, productif
  no-message, run_with_retry node_kind='tester' émet le log idle) + test_config.py +1
  (tester_max_steps défaut+override).
- [x] Étape F45-6 (Suite) : pytest 487 passed / 0 failed (482 baseline + 5 nouveaux).
- [x] Étape F45-7 (État disque) : debug/TIMINGS_ANALYSE.md (ACTION CORRIGÉE + recommandations
  statutées), feature_list.json +F-45, contract.md +critères 150-155, progress.md.

## Jalons de l'Itération (cycle Fix bug visuel Coder + Judge hang — F-46/F-47)
- [x] Étape F46-1 : Diagnostic bug visuel — lecture log F-45 prouve que le Coder applique
  LITTÉRALEMENT 'hero 3.5rem' du skill frontend-design (log lignes 403-405 + 482). Le skill
  était conçu pour landing pages, inadapté à un visualiseur (app/tool).
- [x] Étape F46-2 : Skill frontend-design réécrit — ÉTAPE 0 (APP/TOOL vs LANDING/PAGE),
  fourchettes conditionnelles (remplacent 'hero 3.5rem'), garde anti-titre-géant, directive
  layout APP (pas de row à 1024px, une colonne).
- [x] Étape F46-3 : Bug FRESH_START corrigé — load_dotenv(override=True) écrasait l'env shell
  → FRESH_START=1 au shell inopérant. Passé à override=False (défaut). Validé.
- [x] Étape F47-1 : Diagnostic Gap 2 (Judge hang) — analyse log + tests exhaustifs. Prompt
  Judge PETIT (~4k tokens, déjà tronqué). Température 0.3 CORRECTE (ne pas changer). VRAIE
  cause : thinking Gemma 4 FORCÉ sur /v1 (Ollama 0.32.5 = dernière version). Non désactivable
  via /v1 (think/chat_template_kwargs/Modelfile testés, tous ignorés).
- [x] Étape F47-2 : Percée technique — provider litellm 'ollama/' parle /api/chat natif +
  paramètre think. Testé : think=false → 3.8s, réponse directe (vs 23min thinking).
- [x] Étape F47-3 : _configure_dspy migre vers ollama/ + retrait /v1 + paramètre think.
  Décision utilisateur : think=True uniquement Architect, think=False pour les 5 autres
  nœuds DSPy (Router/PromptRefiner/Security/Judge/Escalation).
- [x] Étape F47-4 : Tests — 2 tests test_prompt_refiner.py mis à jour (assertions think=False).
  Suite pytest 487 passed / 0 failed.
- [x] Étape F4647-5 : debug/GAPS_TESTER_JUDGE.md — 2 gaps consignés avec DONNÉES RÉELLES
  (Gap 1 screenshot jetté par smolagents, Gap 2 thinking résolu par F-47).

## [ARCHIVE — F-48 fermée sans cycle dédié (2026-08-11)]
> F-48 « Vision Coder » était planifiée quand le backend était Ollama /v1 et avant que
> F-50/F-58/F-90 n'existent. Les 4 étapes ci-dessous sont devenues OBSOLÈTES ou furent
> livrées autrement. La description de F-48 décrivait comme « à faire » ce qui était déjà
> en prod. Feature marquée `completed` (livrée par étapes) lors du nettoyage de cohérence.
> - F48-1 (think=false Coder) → résolu par **F-58** (migration llama-server spawn +
>   `FAST_REASONING=off` au spawn via ModelSpec, `llama_server.py:198`). Le contournement
>   litellm `/api/chat` de F-47 (spécifique Ollama /v1) n'a plus de raison d'être.
> - F48-2 (screenshot tool) + F48-3 (verify-after skill) → livrés par **F-50** (ex-F-45) :
>   `vision_callback.py` + `chrome_devtools_tool.py` + skill `devtools-preview` + bloc
>   VALIDATION VISUELLE dans le prompt Coder + enforcement programmatique. **F-90** a
>   ajouté `visual_success_criteria` générés par l'Architect (checklist OUI/NON vs screenshot).
> - F48-4 (comparatif A/B) → non essentiel, non fait.
>
> Le Coder a DONC déjà la vision en prod. Cette section est conservée pour la traçabilité
> historique mais ne décrit plus un « prochain cycle ».

## Jalons de l'Itération (cycle Chrome DevTools MCP + validation visuelle — F-45)
- [x] Étape CD-0 : Vérification runtime fast_model (gemma-4-E4B) multimodal — VALIDÉ
      (image rouge 4x4 envoyée via /v1/chat/completions → réponse "Roux... rouge").
- [x] Étape CD-1 : Config MCP build_chrome_devtools_params() (agent_server/mcp.py) —
      source unique stdio (npx chrome-devtools-mcp@latest --isolated --viewport 1280x800
      --screenshot-format jpeg), opt-out CHROME_DEVTOOLS_ENABLED, CHROME_PATH, HEADLESS.
- [x] Étape CD-2 : Context manager chrome_devtools_tool.py (yield [] si KO, dégradation
      gracieuse pattern Context7).
- [x] Étape CD-3 : Module vision_callback.py — wrapper _ScreenshotCapturingTool (capture
      PIL image) + make_screenshot_callback (step_callback peuple observations_images).
      Nécessaire car smolagents v1.26.0 ne pousse pas auto les images MCP en multimodal.
- [x] Étape CD-4 : Branchement Coder (CodeAgent) — outils DevTools + step_callback +
      prompt section VALIDATION VISUELLE (conditionnelle web), max_steps 12→14.
- [x] Étape CD-5 : Branchement WebTester — cumul Puppeteer + Chrome DevTools,
      step_callback vision actif, doc outils complémentaires dans le prompt.
- [x] Étape CD-6 : Skill devtools-preview/SKILL.md + skills_loader (routage dynamique web).
- [x] Étape CD-7 : Config .env + .env.example (CHROME_DEVTOOLS_ENABLED, CHROME_PATH,
      CHROME_DEVTOOLS_HEADLESS). Reporté dans .env local (AGENTS.md §7).
- [x] Étape CD-8 : tests/test_chrome_devtools_tool.py (28 tests : params, dégradation,
      callback, helpers Coder, skills). Suite pytest 521 passed / 0 failed (+28 vs baseline).
- [x] Étape CD-9 : Fichiers état (feature_list F-45, contract C150-C160, progress, log).
- [ ] Étape CD-10 : Validation run Bubble_Sort_Visualizer (borné, WORKFLOW_MODE=coding).

## Jalons de l'Itération (cycle Checklist fonctionnalités + fixes robustesse — F-46)
- [x] Étape CD-11 : 3 runs de validation Bubble Sort (diagnostic des failure modes).
- [x] Étape CD-12 : Fix AUDIT_PARALLEL=false (séquentialise Tester PUIS Security, GPU-local).
- [x] Étape CD-13 : Fix max_steps Tester 24→12 (anti-explosion contexte 405k→233k tokens).
- [x] Étape CD-14 : Skill coding anti-TypeScript (tableau syntaxes interdites en vanilla).
- [x] Étape CD-15 : Skill devtools-preview — list_console_messages OBLIGATOIRE avant screenshot.
- [x] Étape CD-16 : Skill web-tester — règle des 2 essais (conclure FAILURE vite).
- [x] Étape CD-17 : requirements_checklist.py (parser regex + build_checklist_block).
- [x] Étape CD-18 : Injection checklist dans web_tester.py (checklist_block après cahier charges).
- [x] Étape CD-19 : tests/test_requirements_checklist.py (14 tests). Suite 535 passed / 0 failed.
- [x] Étape CD-20 : Doc — README.md §"Node Graph & Data Flow" (diagramme ASCII complet
      avec tiering modèles + flux données) + AGENTS.md (séquence + référence).
- [x] Étape CD-21 : Fichiers état (feature_list F-46, contract C161-C170, log, progress).
- [ ] Étape CD-22 : Validation run Bubble Sort avec checklist F-46 active (cycle suivant).

## Jalons de l'Itération (cycle Static Tester déterministe — F-49)
- [x] Étape ST-1 : Module `graph_orchestrator/static_tester.py` — Tier 1a (`node --check`
      sur JS inline → TS-in-vanilla, bug n°1 = page blanche), Tier 1b (wiring
      `addEventListener` → slider non branché, piège n°1 indétectable par screenshot),
      Tier 2 (visibilité DOM DevTools `getBoundingClientRect().height` → barres invisibles,
      le bug CSS height:% que le LLM a raté par biais de confirmation). Déclenchement de
      l'action primaire (clic start) combiné au probe en UN appel synchrone (éléments créés
      au clic, pas au load). Générique (découvre sélecteurs + ids depuis le HTML, ne hardcode rien).
- [x] Étape ST-2 : Intégration `workflows.py` — inséré entre Linter et Tester LLM, même
      pattern de court-circuit (réfutation DuckDB source='static_tester' + continue).
- [x] Étape ST-3 : Tests `tests/test_static_tester.py` — 29 tests (l'agent joue le Coder
      avec des HTML bubble-sort buggés). 29/29 PASS. Bug barres invisibles ATTRAPÉ.
- [x] Étape ST-4 : Config `.env` + `.env.example` — STATIC_TESTER_ENABLED, STATIC_TESTER_DEVTOOLS.
- [x] Étape ST-5 : Fichiers état synchronisés (feature_list F-49, contract C180-C189, README,
      AGENTS.md, log, progress).
- [x] Étape ST-6 : Suite pytest complète → 592 passed / 0 failed (563 baseline + 29 nouveaux).
      0 régression. web_tester_functional désélectionné (nécessite Chrome/npx live).
- [ ] Étape ST-7 : Validation run live (HTML corrompu → FAILURE ciblé, HTML correct → SUCCESS).

## Jalons de l'Itération (cycle Scripts isolation « l'agent joue le nœud » — F-55)
- [x] Étape ISO-1 : Plan approuvé (périmètre = Linter + 4 DSPy Router/Architect/Judge/Security ;
  PromptRefiner/Escalation hors périmètre). Convention debug/isolation/ (conforme F-55).
  Exploration (3 agents parallèles) : signatures exactes nœuds, clés dict task lues, sites
  d'appel workflows.py, tests mockés, config. Leçon clé : nœuds DSPy instancient eux-mêmes
  leur LLM via _configure_dspy (param *_model reçu IGNORÉ, relicat d'API).
- [x] Étape ISO-2 (première version, CORRIGÉE ensuite) : 5 scripts Python appelant le LLM du
  graphe (run_router.py etc.). VALIDÉS par py_compile + 1 exécution Router réelle (18.9s).
- [x] Étape ISO-2b (CORRECTION MAJEURE après feedback user) : « l'agent joue le nœud » =
  MOI (ZCode) qui joue le nœud à la main, PAS un script qui appelle le LLM du graphe.
  Pattern découvert : debug/MANUAL_TESTER_METHODOLOGY.md (le Tester joué à la main, doc
  d'étapes fail-fast + biais) + audit_coder/ (le Coder joué avec screenshots). Les 4 scripts
  DSPy (router/architect/judge/security) SUPPRIMÉS — design mauvais. run_linter.py GARDÉ
  (déterministe, valide la vraie fct prod, 7/7 ✅).
- [x] Étape ISO-3 : MANUAL_ROUTER_METHODOLOGY.md — étapes fail-fast (mots-clés → extensions
  → résolution multi-techno → décision), tableau de décision par langage, 3 biais.
- [x] Étape ISO-4 : MANUAL_ARCHITECT_METHODOLOGY.md — 3 stratégies F-29 (techno-driven),
  5 étapes (livrables/stratégie/sections/description/assemblage), 4 biais.
- [x] Étape ISO-5 : MANUAL_JUDGE_METHODOLOGY.md — rubric sévérité F-44, 6 étapes (Read
  in-diff/couverture/test_res/security_res/décision/feedback), 5 biais.
- [x] Étape ISO-6 : MANUAL_SECURITY_METHODOLOGY.md — grille OWASP Top 10, 6 étapes
  (Read/grep OWASP/contexte input/CVSS/findings defensive/is_secure), 5 biais.
- [x] Étape ISO-7 : MANUAL_LINTER_METHODOLOGY.md (compléter le set, cohérence).
- [x] Étape ISO-8 : README isolation réécrit (convention doc méthodologie + run_linter.py
  seul script). README racine corrigé. État disque synchronisé (feature_list F-55,
  contract C196-C204, progress, log). Suite pytest 586 passed / 0 failed (0 régression).
  Commit + PR.

## Jalons de l'Itération (cycle F-56 durcissement prompts nœuds — P14)
- [x] Étape P14-1 : Plan approuvé (2 décisions user : P14-E=warning non bloquant, F-57=planifié
  après F-56). Exploration clé : seul test_prompts.py asserte le contenu des docstrings (tests
  de présence de marqueurs) → durcir les docstrings ne casse aucun test si marqueurs préservés.
- [x] Étape P14-E : Linter warning fichier absent (linter.py + execute_linter_node + 2 tests).
  Défense is_valid=True conservée + avertissement remonté dans details pour observabilité.
- [x] Étape P14-A : Router — MOTS-CLÉS CANONIQUES + RÈGLE DE PRIORITÉ + ANTI-BIAIS.
- [x] Étape P14-B : Architect — RÈGLES sections incremental + BIAIS incremental/multifile.
- [x] Étape P14-D : Security — PATTERNS OWASP concrets + DISCRIMINATION INPUT + A09 + FP.
- [x] Étape P14-C : Judge — PROCÉDURE OBLIGATOIRE 5 étapes + croisement défiant + localisation.
- [x] Étape P14-F : Validation — pytest 587 passed / 0 failed. Marqueurs préservés (grep 3/3).
  run_linter 7/7 ✅. Correspondance 1:1 audit→implémentation vérifiée.
- [x] Étape F-57 : PLANIFIÉ (feature_list pending + plan_usine §P10) — lazy loading cycle suivant.
- [x] Étape P14-9 : État disque synchronisé (feature_list F-56 completed + F-57 pending,
  contract, progress, log, plan_usine P14 coché).

## Jalons de l'Itération (cycle Intégration llama.cpp dynamique — F-58)
- [x] Étape LCP-1 : `llama_server.py` créé avec le context manager `model_lifecycle`.
- [x] Étape LCP-2 : `_configure_dspy` (dspy_nodes.py) et les runners (`CodeAgent` / `WebTester`) adaptés pour accepter l'API base issue du `model_lifecycle` spawn.
- [x] Étape LCP-3 : Configurations .env et config.py adaptées (backends `spawn`, `FAST_MODEL` etc.)
- [x] Étape LCP-4 : Ajustements mock tests pour respecter les `_SpawnedServer`.
- [x] Étape LCP-5 : Tests unitaires (598 passed).
- [x] Étape LCP-6 : Run E2E (Bubble Sort validé avec crash DSPy et régression Coder capturés pour F-59).
- [x] Étape LCP-7 : Fix DSPy Rescue (ajout de l'alias dans llama_server) et Warning top-level await Web Tester.
- [x] Étape LCP-8 : Implémentation outil multi_replace (F-59) pour le Coder et modification de nodes.py.


## Jalons de l'Itération (cycle Analyse des Runs & Amélioration Continue — F-60 / F-61)
- [x] Étape RAA-1 : Création de 
un_analyzer.py (F-60) pour parser les logs 	ask-*.log et extraire les métriques de graph_orchestrator.db. Filtres robustes contre les bordures de logs (Rich).
- [x] Étape RAA-2 : Validation en direct du rôle de Meta-Analyste de l'assistant IA (F-61). Diagnostic des crashes InterpreterError et injection dynamique de la règle import time dans 
odes.py et web_tester.py.
- [x] Étape RAA-3 : Remplacement du write_file par multi_replace_file_content validé et acté (F-59) pour le Coder.
- [x] Étape RAA-4 : Application en direct (F-61) d'un deuxième correctif : le run E2E a crashé sur le Web Tester à cause de la règle "IIFE" passée au MCP chrome-devtools. Analyse + correction de 
odes.py et web_tester.py pour exiger une DÉCLARATION de fonction asynchrone non invoquée (sync () => { await ... }) à la place de l'IIFE.
- [x] Étape RAA-5 : Mise à jour exhaustive des documents de suivi (eature_list.json, plan_usine_logicielle.md, README.md, progress.md).
- [ ] Étape RAA-6 : Attente de la fin du run E2E, analyse post-mortem finale avec un_analyzer.py, rapport de validation, et préparation pour commit/PR.

## Jalons de l'Itération (cycle Audit cohérence INDEX références — enrichissement plan)
- [x] Étape ACI-1 : Constat initial — fiches 19-23 déjà intégrées via F-66 (completed). INDEX.md + inventory.json = commit 9dc59c0.
- [x] Étape ACI-2 : Audit de cohérence exhaustif (agent Explore) — Hall of Fame INDEX croisé contre plan_usine_logicielle.md. 18 écarts identifiés, gisement principal = qm (4 briques 🟢 Haute sur 9 oubliées).
- [x] Étape ACI-3 : Enrichissement plan_usine_logicielle.md (cases `[ ]` uniquement, 0 code modifié) — P3-bis (+2), P6-bis (+2), P6-ter NOUVELLE sous-section (+1 bloc), P9 (+1 case + garde), P1 (+1 case + précision source), P2 (+1 case), P10 (+2 cases), tableau état avancement mis à jour.
- [x] Étape ACI-4 : feature_list.json +4 features pending (F-68 mémoire KG qm, F-69 budget+queue qm, F-70 diff+métriques Judge, F-71 skeleton libcst). 72 features total. JSON validé.
- [x] Étape ACI-5 : progress.md synchronisé (journal migré DuckDB). Périmètre = travail documentaire uniquement (aucun code de production modifié, aucun test impacté).

## Jalons de l'Itération (cycle Read-Before-Write Gate — F-67, Priorité 1)
- [x] Étape RBW-1 : Exploration (2 agents parallèles) — design Deer Flow lu (issue #3857,
  middleware read_before_write_middleware.py 269 lignes) : hash SHA256 contenu complet,
  stamp après read_file, « newest mark wins », fail-open, gate write_file+str_replace,
  un write réussi invalide la mark (Strict). Archi smolagents cartographiée (SanitizedTool
  = template parfait à copier, step_callbacks existants, read_file non tracé).
- [x] Étape RBW-2 : Décision design (AskUserQuestion) — mode STRICT (fidèle Deer Flow) :
  un write réussi n'auto-stamp PAS la mark → force re-read avant chaque édition.
- [x] Étape RBW-3 : `graph_orchestrator/read_gate.py` (~310 lignes) — compute_content_hash,
  _normalize_path (Windows-safe), ReadGate (dict thread-safe), _GatedWriteTool,
  _ReadTrackingTool, wrap_tools_with_read_gate. 0 LLM, 100% déterministe.
- [x] Étape RBW-4 : Branchement `nodes.py execute_coder_node` (~10 lignes) — gate inséré
  ENTRE wrap_screenshot_tools et sanitize_tools (ordre : gate AVANT sanitizer).
- [x] Étape RBW-5 : Config `read_before_write_enabled` (défaut True) dans config.py +
  .env.example + .env local (AGENTS.md §7). Opt-out READ_BEFORE_WRITE_ENABLED=false.
- [x] Étape RBW-6 : `tests/test_read_gate.py` — 35 tests (helpers 5, ReadGate logic 4,
  fail-open 6, Strict mode 3, newest-wins 1, thread-safety 1, _GatedWriteTool 5,
  _ReadTrackingTool 3, wrap 3, E2E 4). 35/35 PASS.
- [x] Étape RBW-7 : Validation — py_compile OK (3 fichiers) + suite pytest complète
  651 passed / 0 failed (616 baseline + 35 nouveaux), 0 régression.
- [x] Étape RBW-8 : État disque synchronisé (feature_list.json +F-67, contract.md
  +critères 215-227, plan_usine_logicielle.md P1 case cochée, progress.md, README.md).
  Commit + push + PR.

## Jalons de l'Itération (cycle Skills à la demande / Coder — F-57 Phase 1, Priorité 10)
> **Note de pivot (v3)** : le design initial v1 (lazy loading via tool `load_skill`
> + flag `SKILL_LAZY_LOADING_ENABLED`) a **échoué en run de validation** : le Coder
> 9B n'appelait pas l'outil, perdant les skills conditionnels. Pivot vers v3 =
> **sélection par l'Architect** (injection directe fiable à 100%) + budget tokens.
> Le tool `load_skill` reste disponible pour la flexibilité (re-consulter un skill),
> mais n'est plus le mécanisme principal.
- [x] Étape F57-1 : Plan approuvé (2 phases : Phase 1 = Coder pour prouver le gain
  tokens ; Phase 2 = généralisation aux nœuds DSPy UNIQUEMENT si Phase 1 performante).
  Baseline = run 2026-08-04_1816_bubble_sort (index.html 255 lignes one-shot).
  Décisions : mécanisme input field methodology_context pour DSPy (Phase 2),
  socle ALWAYS (3 skills critiques) vs skills conditionnels (sélection regex).
- [x] Étape F57-2 : `graph_orchestrator/skills_loader.py` — API additive :
  ALWAYS_SKILLS_CODER (set de 3, ex-EAGER_SKILLS_CODER renommé), _parse_frontmatter_yaml
  (défensif, jamais lève), parse_skill_meta (tuple name+desc, None si absent, pour
  nœuds DSPy), count_skill_tokens (tiktoken cl100k_base + mémo + repli chars/4),
  enforce_skill_budget (rogne « petits d'abord », socle ALWAYS toujours conservé),
  build_conditional_skills_block (repli regex si Architect n'a rien sélectionné).
  build_skills_catalog / build_eager_skills_block / EAGER_SKILLS_CODER CONSERVÉS
  en alias dépréciés (rétrocompat tests). build_skills_block + select_skills_for_coder
  CONSERVÉS (WebTester en dépend).
- [x] Étape F57-3 : `graph_orchestrator/skill_loader_tool.py` — @tool
  load_skill(skill_name) retourne corps complet (load_skill_body) ou message si
  introuvable, fail-open jamais ne lève. Déterministe, 0 LLM, 0 réseau. Rôle v3 =
  flexibilité (re-consulter un skill), PAS mécanisme principal d'injection.
- [x] Étape F57-4 : `graph_orchestrator/nodes.py execute_coder_node` — branchement v3 :
  l'Architect sélectionne `subtask.skills` → `enforce_skill_budget(budget=skill_budget_tokens)`
  → injection corps complet directe. Repli `build_conditional_skills_block` (regex) si
  l'Architect n'a rien sélectionné. Outil `load_skill` ajouté à coder_tools pour la
  flexibilité. ArchitectOutput/SubTask gagnent les champs `skills`/`tester_skills`/
  `judge_skills` (models.py l.76-81).
- [x] Étape F57-5 : **Pivot F-57 v3** (le lazy loading via tool a échoué en run :
  le Coder 9B n'appelait pas `load_skill`, cf. commentaire skills_loader.py l.166-179).
  Nouveau design = **sélection par l'Architect** (`subtask.skills` dans ArchitectOutput,
  models.py l.76-81) + budget tokens anti-saturation. `config.py` + `.env.example` +
  `.env` local — `skill_budget_tokens: int = 8000` (défaut, ~24% du contexte Qwen 9B)
  + `_get_int("SKILL_BUDGET_TOKENS", 8000)`. AUCUN flag `skill_lazy_loading_enabled`
  (abandonné : le mécanisme n'est plus conditionnel à un opt-out).
- [x] Étape F57-6 : `tests/test_skill_lazy_loading.py` — 33 tests / 8 classes v3
  (AlwaysSkillsCoder 3, CountSkillTokens 6, EnforceSkillBudget 6, BuildConditional-
  SkillsBlock 4, LoadSkillTool 3, ArchitectTaskSkillsField 3, CatalogueEtendu 4,
  NonRegression 4). 33/33 PASS.
- [x] Étape F57-7 : Validation — py_compile OK (5 fichiers) + smoke test (system prompt
  -36.8% par step : 17386→10988 chars sur tâche web) + suite pytest complète 678 passed
  / 0 failed hors 3 pré-existants test_run_logging.py (non liés, confirmés par git stash),
  11 deselected (test_web_tester_functional). 0 régression.
- [x] Étape F57-8 : État disque synchronisé (feature_list.json F-57 pending→completed,
  contract.md +critères 228-237, plan_usine_logicielle.md P10 PARTIEL + case cochée,
  progress.md, README.md section Coder). ATTENTE commit/PR.
- [ ] Étape F57-9 : Run de validation Bubble Sort. Critères v3 : HTML complet +
  l'Architect sélectionne `subtask.skills` + `enforce_skill_budget` plafonne la
  sélection + le Coder reçoit les corps complets (plus de dépendance à un appel
  `load_skill` du modèle). SI réussite → déclenche Phase 2 (nœuds DSPy via
  `methodology_context`).

## Jalons de l'Itération (cycle Static Tester Tier 3 — détection animations instantanées, F-81)
- [x] Étape T3-1 : Diagnostic du bug réel (runs/2026-08-05_1602_bubble_sort/index.html) —
  `performStep()` appelée par `requestAnimationFrame` contient les deux boucles imbriquées
  complètes du bubble sort → tout le tri en 1 tick JS → animation instantanée invisible.
  Tier 1 (JS valide, wiring OK) et Tier 2 (barres visibles) PASS ce fichier ; Tester LLM
  aussi (son pattern animation = wait 2s puis check état final, qui passe même si
  l'animation a duré 0 ms). Zone aveugle confirmée.
- [x] Étape T3-2 : Prévention Coder (Partie A) — règle 9 (nodes.py RÈGLES CRITIQUES :
  une itération par frame, jamais l'algorithme complet, ❌ FAUX/✅ JUSTE) + paragraphe
  granularité step (skills/coding/SKILL.md, complément de la règle threading existante).
- [x] Étape T3-3 : Détection LLM Tester (Partie C) — règle 4 (web_tester.py : test
  temporel pas état final) + recette temporelle (skills/web-tester/SKILL.md : snapshot
  T0/clic/wait 400ms/snapshot T1 au lieu du pattern wait-2s-check-final qui rate le bug).
- [x] Étape T3-4 : Détection déterministe Static Tester Tier 3 (Partie B) —
  `static_tester.py _evaluate_temporal()` : sonde DevTools en UN seul evaluate_script
  async (snapshot progression T0 → clic bouton primaire → await 400ms → snapshot T1 ;
  verdict : état terminal atteint pendant la fenêtre = animation instantanée).
  Terminaison générique (hauteurs .bar ordonnées OU toutes .sorted — ne compare PAS le
  compteur au nombre de barres). Opt-out STATIC_TESTER_TEMPORAL=0. Branché après Tier 2
  (même session Chrome) → court-circuite le Tester LLM via l'existing failure path
  (aucune modif workflows.py). `_parse_devtools_json` corrigé (gère les dicts stringifiés,
  pas seulement les arrays).
- [x] Étape T3-5 : Tests — `tests/test_static_tester.py` +5 tests Tier 3 (instant détecté,
  progressive non-flaggué, opt-out env-var ×2, no-signal skip). Suite complète 33 passed /
  1 skipped (le skip = test Tier 2 pré-existant, Chrome timing entre tests).
- [x] Étape T3-6 : Validation V1 (harness standalone sur le VRAI fichier bugué) —
  `debug/validate_tier3_temporal.py` : Scénario 1 (runs/.../index.html bugué) → FAILURE
  en 4.5s (signal 0→435 comparaisons = tout le tri en 1 tick), Scénario 2 (animation
  légitime ~2s) → SUCCESS (pas de faux positif). 🎉 VALIDATION RÉUSSIE.
- [ ] Étape T3-7 (V2, optionnel, ~3-5 min GPU) : Coder corrige le fichier bugué —
  `debug/test_gate_live_bubble.py` adapté, iteration=2 (mode correction), la règle 9
  doit pousser le modèle à corriger performStep en une iteration par frame. Re-run V1
  sur le corrigé doit passer.
- [ ] Étape T3-8 (V3, optionnel, ~10-25 min GPU) : Tester LLM valide le fichier corrigé —
  `debug/run_web_tester_standalone.py` corrigé (lit REASONING_NO_THINK_* au lieu de
  FAST_BACKEND_URL). La règle 4 + recette temporelle doivent faire écrire une assertion
  temporelle. Bonus : Tester LLM sur le fichier bugué non corrigé doit maintenant FAIL.

### Résultats V2 + V3 (validations standalone GPU, 2026-08-05)
- [x] **V2 — Coder corrige le fichier bugué** (`debug/validate_tier3_coder_fix.py`) :
  iteration=2 (mode correction read_file + search_replace), feedback Tier 3 injecté +
  règle 9 du prompt. **13 steps, 816s (~13.6 min), Qwen3.5-9B.** SUCCÈS : le Coder a
  correctement transformé performStep (double boucle → if/else une itération par frame,
  variables i/j persistées hors fonction), puis auto-validation visuelle complète
  (navigate, console OK, screenshot avant/après clic). `final_answer: success`.
- [x] **V2-4 — Static Tester Tier 3 sur le corrigé** : `success` (tier3 atteint, 7.9s,
  0 LLM). Le Tier 3 ne flaggue PLUS l'animation → la correction est prouvée déterministe.
- [x] **V3 — Tester LLM (Ornith-9B) sur le corrigé** (`debug/validate_tier3_tester_llm.py`) :
  **timeout à 600s (step 25)** — MAIS valide Parts C1+C2 : le Tester a explicitement
  annoncé "Now let me do the temporal test - click Start and measure progression over
  400ms" (step 15) → la règle 4 + recette temporelle guident le LLM. Il a détecté un
  bug réel (régression Coder : `i`/`j` non resetés dans `init()` → 2e clic inopérant,
  counter=0). Le timeout vient de l'over-exploration du Tester (failure mode pré-existant
  documenté TIMINGS_ANALYSE, pas lié au Tier 3).
- [x] **V3-3 — Fix manuel i/j + runtime probe** : ajout de `i=0; j=0; isSorting=false;`
  dans `init()`. Static Tester re-passé (`success`, tier3). Runtime probe manuelle :
  `c0=0 → c1=10` en 600ms, `progressed=True`, `finished=False` (animation progressive,
  non terminale). **L'animation marche pour de vrai maintenant.**

Bilan global V1+V2+V3 : les 3 couches (Coder prévient, Static Tester rattrape, Tester
LLM confirme) fonctionnent. Le Tier 3 déterministe est validé end-to-end (détecte le
bug en 4.5s, ne flaggue pas le corrigé, 0 faux positif). Le Tester LLM applique bien
le test temporel mais reste limité par son over-exploration (pré-existant). La règle 9
Coder est appliquée correctement par Qwen3.5-9B.
- [x] Étape T3-9 : État disque synchronisé (feature_list.json +F-81, progress.md, README.md).
  Branche `feat/static-tester-tier3-temporal`. Commit.

## Jalons de l'Itération (cycle Diff + métriques Judge — F-70, P6-bis)
- [x] Étape F70-1 : Reconnaissance (2 agents Explore parallèles) — Judge plumbing
  cartographié (`execute_code_judge_node` dspy_nodes.py:777 recevait le full-file
  concaténé `:799-805` passé au champ `code` `:858`, alors que le docstring + rôle
  exigent IN-DIFF ONLY), F-53 git_snapshot fournit `get_last_diff` (déjà propagé dans
  `sub_dict["git_diff"]` workflows.py:583, consommé seulement par le web_tester),
  pattern d'injection `build_targeted_retest_block` identifié. Références localisées
  (scorer.py, pr_diff.py, SKILL.md) — `compute_risk_score` (KG structural) et
  `build_pr_diff_files` (fetcher GitHub UI) écartés justifiés.
- [x] Étape F70-2 : `graph_orchestrator/judge_diff.py` — `build_judge_code_block`
  (0 LLM). Iter 1 (diff vide) = full-file rétrocompat ; iter >1 = bloc diff annoté
  IN-DIFF ONLY en tête + full-file tronqué (`truncate_output`, contexte vérif
  exigences). Fail-open (fichier absent sauté). Miroir `targeted_retest`.
- [x] Étape F70-3 : Branchement `dspy_nodes.py execute_code_judge_node` — boucle
  full-file remplacée par `build_judge_code_block(...)`, import ajouté. Aucune
  modif workflows.py (git_diff déjà propagé).
- [x] Étape F70-4 : `graph_orchestrator/judge_metrics.py` (offline, 0 LLM) —
  `canonicalize_finding` (ID stable `location|category|severity`, insensible
  paraphrase), `compute_precision_recall`, `compute_mrr`, `judge_verdict_accuracy`
  (TP/FP/FN). Ports typés de code-review-graph/eval/scorer.py.
- [x] Étape F70-5 : Tests — `test_judge_diff.py` (12, miroir test_targeted_retest)
  + `test_judge_metrics.py` (18, pure logique) + `test_dspy_nodes.py` +2 Judge
  (git_diff non vide → mock reçoit bloc diff ; iter1 full-file pas de bloc).
  32/32 PASS. Correctifs : Literal severity Pydantic stricte, marqueur troncature
  "tronqu" matchait tmp_path → "lignes tronquées".
- [x] Étape F70-6 : Validation — 0 régression confirmée par `git stash` (25 échecs
  préexistants sur HEAD strictement identiques avant/après, tous E2E workflow +
  guard + read_gate + skill_lazy_loading, AUCUN lié au Judge). `test_judge_diff` +
  `test_judge_metrics` + Judge `test_dspy_nodes` tous PASS.
- [x] Étape F70-7 : État disque synchronisé (feature_list.json F-70 completed,
  contract +critères 238-244, plan P6-bis 2 cases cochées, progress, log).

## Jalons de l'Itération (cycle F-61 Meta-Analyste — post-mortem run coding_d72dc8e36445c4b6)
> Run Bubble Sort du 2026-08-06 17:16 : verdict `failure` (Coder crash). Post-mortem
> via `run_analyzer.py` → 3 failure modes Coder récurrents identifiés (F-70 non impliqué,
> Judge iter 1 OK). Correctifs appliqués (AGENTS.md §8 : diagnostiquer → proposer → valider
> → appliquer).

- [x] Étape F61-1 : Diagnostic (run_analyzer.py + lecture log) — 3 causes racines :
  (1) `}` au lieu de `)` fermant search_replace (failure mode historique, règle prompt n°8
  insuffisante) ; (2) Coder boucle 87 steps / 80 min / 18M tokens (max_steps=25 trop permissif
  × worker_max_retries=3 × retries internes) ; (3) tours idle répétés sans tool call
  (_detect_idle_step F-33 réinjecte un message mais ne coupe JAMAIS → boucle jusqu'à
  épuisement). Crash final : litellm.InternalServerError Connection error (serveur llama.cpp
  saturé sous charge).
- [x] Étape F61-2 : Correctif 1 (Guard anti-`}`) — hook dans run_with_retry except Exception.
  Détection INDEPENDANTE de la condition Syntax/parse (le message smolagents "Code parsing
  failed" ne contient ni "Syntax" ni "parse" mais "parsing" — bug de condition corrigé :
  la branche `}` est testée en PREMIER). Message SPÉCIFIQUE actionnable (Règle n°8 + exemple
  correct) au lieu du générique "découpe".
- [x] Étape F61-3 : Correctif 2 (CODER_MAX_STEPS configurable) — config coder_max_steps
  (défaut 18, avant 25 hardcoded) + .env.example. Choix : Coder produit en 6-14 steps nominal,
  18 laisse une marge sans brider.
- [x] Étape F61-4 : Correctif 3 (Circuit-breaker idle consécutifs) — compteur consecutive_idle
  dans run_with_retry, param idle_breaker_threshold (défaut 3). N idles consécutifs → échec
  définitif propre. Reset sur run productif. Nœuds non-Coder (Judge/Synth/Adversary/Worker)
  reçoivent threshold=10**9 (jamais coupés — le Judge réfléchit légitimement).
- [x] Étape F61-5 : Tests tests/test_coder_hardening.py — 8 tests (config 3, hook `}` 2, idle
  breaker 3). Découvertes de mock : type(agent).__name__ nécessite une vraie sous-classe
  dynamique (MagicMock.__class__ assign + spec= ne changent pas type()) ; agent.memory.steps
  purgé en fin d'attempt → repeupler dans le mock pour simuler N idles consécutifs.
- [x] Étape F61-6 : Validation — 8/8 nouveaux tests PASS. Suite pytest complète 673 passed
  (+8 vs baseline 665) / 25 échecs préexistants strictement identiques (confirmés via la
  baseline F-70), 0 régression. py_compile OK (nodes.py + config.py).
- [x] Étape F61-7 : État disque synchronisé (feature_list.json F-61 description + cycle,
  contract +critères 245-250, progress, log).

## Jalons de l'Itération (cycle F-61 itération 3 — final_answer valide vs LoopGuard)
> Run E2E Bubble Sort multi-fichier du 2026-08-06 20:16 : verdict `failure` (Coder crash),
> mais les 3 fichiers générés étaient fonctionnels. Post-mortem via `run_analyzer.py` →
> bug logiciel `run_with_retry` identifié (un final_answer valide éjecté par le LoopGuard).

- [x] Étape F61-8 : Run E2E Bubble Sort multi-fichier (WORKFLOW_MODE=coding, FRESH_START=true)
  — 2390s (~40 min), 294k tokens. Validations E2E réussies : F-58 (llama.cpp dyn.), F-59
  (multi_replace en mode correction), F-67 (Read-Before-Write Gate a BLOCKÉ une édition
  sans relecture), F-61 (max_steps 18 + idle breaker), F-33 (rattrapage parsing triple-quote),
  F-50 (auto-validation visuelle Coder). Verdict failure (cause logicielle, pas code produit).
- [x] Étape F61-9 : Post-mortem `run_analyzer.py` — cause racine : `run_with_retry` lignes
  296-297 `if loop_msg: pass`. Le LoopGuard (F-36) scanne tout l'historique et comptabilise
  comme "répétition" l'itération de correction légitime, puis le bloc `if validated:` jette
  silencieusement le final_answer valide (`pass` au lieu de `return`). 3 retries reproduisent
  → échec définitif. Diagnostic confirmé par agent Explore (lecture code nodes.py + loop_guard).
- [x] Étape F61-10 : Correctif — bloc `if validated:` inversé. Un `validated` réussi prime
  TOUJOURS sur `loop_msg`. Le `if loop_msg: pass` supprimé. `loop_msg` reste dans le prompt
  de retry (ligne 279) pour guider le retry UNIQUEMENT quand `validated is None`. Message
  d'observabilité ajouté pour tracer le chemin. Branche `fix/coder-final-answer-loopguard-priority`.
- [x] Étape F61-11 : Test de non-régression `test_valid_final_answer_wins_over_loop_guard`
  (test_coder_hardening.py) — agent avec 3× write_file identique (déclenche loop_guard) +
  final_answer valide → assert succès retourné (pas None), 0 retry consommé. 9/9 PASS.
- [x] Étape F61-12 : Validation — suite pytest 674 passed (+1 vs baseline 673) / 26 échecs
  préexistants strictement identiques (confirmés via `git stash` : 26 failed avant ET après,
  aucun lié au LoopGuard). py_compile OK. 0 régression.
- [x] Étape F61-13 : État disque synchronisé (feature_list.json F-61 description + itération 3,
  contract +critères 251-254, progress, log).

## Jalons de l'Itération (audit approfondi TencentDB-Agent-Memory — fiche 28 enrichie)
> Re-analyse de `references/TencentDB-Agent-Memory` (audit F-83 initial superficiel : 4
> briques seulement, noté 🟡 Moyenne). Objectif : récupérer les infos pour enrichir les
> prompts actuels et la roadmap (plan_usine_logicielle.md / feature_list.json).

- [x] Étape AUDIT-1 : Exploration exhaustive (2 subagents parallèles) — carte complète des
  prompts/méthodologie de TencentDB (7 modules : l1-extraction, l1-dedup, scene-extraction,
  persona-generation, offload L1/L1.5/L2, skill-review) + map de nos prompts actuels
  (prompts.py, dspy_nodes.py, nodes.py, web_tester.py) et de l'existant mémoire (F-68, F-83).
- [x] Étape AUDIT-2 : Enrichissement fiche 28 (`docs/references-audit/projects/28-TencentDB-Agent-Memory.md`)
  — table "Documentation pertinente" (4→14 lignes) + table "Code réutilisable" (4→13 lignes)
  + synthèse + correspondance plan. Renotée 🟡 Moyenne → 🟢 Haute.
- [x] Étape AUDIT-3 : Enrichissement `plan_usine_logicielle.md` — 2 items sous P6-ter (pipeline
  L0→L3 extraction+dédup+oubli par chaleur ; recall hybride + split stable/dynamic), 1 item
  sous P9 (context-offload Mermaid scoré + cognitive tombstones), 1 item sous P10 (Skill
  Review gate 5-critères + 4-dim/100pts). En-tête P6-ter + dashboard P6 mis à jour.
- [x] Étape AUDIT-4 : Enrichissement `feature_list.json` — F-68 étoffée (pipeline L0-L3 complet,
  2 références qm+TencentDB nécessaires ensemble), +2 nouveaux IDs F-86 (context-offload P9,
  pending) et F-87 (Skill Review gate P10, pending). Total 85→87 features. JSON validé.
- [x] Étape AUDIT-5 : Analyse prompts runtime (3 candidats) — VERDICT : les 3 sont soit
  redondants (Coder règle 4+5 couvre déjà "独立完整"), soit prématurés (Skill Review gate =
  dépend F-65/F-80/F-87 pending, pas de pipeline génération aujourd'hui), soit contre
  l'architecture (compaction 0-LLM par design = tombstones LLM régresserait). Décision
  VALIDÉE par l'utilisateur : ne pas toucher aux prompts runtime (AGENTS.md §8 respecté).
- [x] Étape AUDIT-6 : Mise à jour INDEX (`docs/references-audit/INDEX.md`) — résumé fiche 28,
  compteur (1H/3M → 8H/5M), totaux (217/186/84 → 224/188/84), constat dédié.
- [x] Étape AUDIT-7 : Branche `feat/tencent-memory-prompts-enrichment` créée (règle d'or Git).

> **Décision clé** : la valeur de l'audit TencentDB se situe dans la **roadmap** (mémoire
> durable F-68 complétée, F-86/F-87 ajoutés), PAS dans des modifications spéculatives du
> runtime aujourd'hui. Les 3 changements de prompts envisagés auraient été contre-productifs
> ou redondants — la validation humaine (AGENTS.md §8) a protégé d'un changement inutile.

## Jalons de l'Itération (cycle F-65 — pépites prompts différenciantes, scope A)
> Successeur direct de F-85 (lignée F-44 → F-56 → F-85 → F-65). F-85 n'avait ingéré que les
> quick wins de la fiche 29. F-65 porte les 5 mécanismes différenciants prioritaires + 3
> quick wins, **en enrichissement de prompts uniquement** (scope A validé utilisateur).

- [x] Étape F65-1 : Branche `feat/prompt-pepites-f65` créée (règle d'or Git).
- [x] Étape F65-2 : Exploration code (3 subagents parallèles) — map précis des attach points
  (prompts.py invariants/rôles, dspy_nodes.py signatures, models.py Finding, workflows.py
  fan-out, testers/ contrat) + extraction fidèle des 5 mécanismes avec attributions exactes
  (corrections d'erreurs initiales du plan confirmées par grep indépendant).
- [x] Étape F65-3 : `prompts.py` — invariant n°5 enrichi (grille réversibilité/blast-radius,
  Codex 4-tier + Claude Code 3-tier fiche 29) + nouvel invariant n°12 (self-correction
  vérifiable « don't end with a promise », Claude Code fiche 29 + Cursor fiche 17) + 7 role
  blocks enrichis (router write-lock policy, architect EARS, coder/coder_frontend engineering
  mindset, web_tester deltas+requirements coverage, judge self-correction+citation file:start-end,
  security réversibilité+`{{secret_name}}` canary) + commentaires stale corrigés (10→12).
- [x] Étape F65-4 : `tests/test_prompts.py` — 28 cas paramétrés (11 nouveaux marqueurs
  doctrinaux) + test compte invariants mis à jour (10→12) + test grille réversibilité.
- [x] Étape F65-5 : `uv run pytest tests/test_prompts.py` → **52 passed / 0 failed**.
- [x] Étape F65-6 : Suite complète `uv run pytest tests/ --ignore=tests/test_static_tester.py`
  → **711 passed / 12 failed**. Comparatif sur `main` : **mêmes 12 échecs pré-existants**
  (test_static_tester collection error, test_read_gate, test_skill_lazy_loading, etc. —
  tests appelant vrais modèles/env, non mockés). **0 régression F-65.**
- [x] Étape F65-7 : `docs/NODES_AND_SKILLS.md` — passage de 11 à 12 invariants + nouvelle
  section F-65 (tableau attributions exactes + corrections d'erreurs d'attribution).
- [x] Étape F65-8 : État disque finalisé (`plan_usine_logicielle.md` items F-65 cochés + stub
  corrigé, `feature_list.json` F-65 → completed, `progress.md` ce bloc).

> **Hors scope (cycles futurs)** : gate logicielle `requires_approval` réelle sur bash_command
> (scope B, étend bash_guard F-38) ; modèle `TestResult` structuré PASS/FAIL delta (scope B,
> touche contrat runners + extraction Judge) ; parallélisation réelle fan-out Coder (scope C,
> risky sur VRAM 6 Go, ReadGate à durcir) ; compatibilité Synth/Drafter avec système
> d'invariants ; autres secondaires F-65 (notify vs ask Manus, 8 templates Qoder).

## Jalons de l'Itération (cycle Anti-loop v2 — F-88, P3-bis)
> Le plan P3-bis (lignes 109-114) demande 3 patterns anti-loop de la référence loopx
> (fiche 19) : stall detector + hash d'output matériel + vocabulaire delivery_outcome.
> F-36 (LoopGuard) ne hashe que ToolName + Input → aveugle à 2 failure modes :
> (a) même contenu réécrit avec input cosmétiquement différent, (b) série de turns
> sans livrable matériel nouveau.

- [x] Étape SD-1 : Exploration (3 agents parallèles) — contrat F-36 exhaustif (LoopGuard,
  run_with_retry, _detect_idle_step, breaker idle, test_valid_final_answer_wins_over_loop_guard),
  patterns loopx vérifiés en Python pur stdlib (recent_runs.py, pr_monitor_materialization.py,
  delivery_outcome.py + transaction.py), conventions projet (modules/tests/config/contract).
- [x] Étape SD-2 : Plan approuvé (décision design clé : module ORTHOGONAL, LoopGuard intact —
  préserve la cohérence F-36 et le test fragile test_valid_final_answer_wins_over_loop_guard).
- [x] Étape SD-3 : Module `graph_orchestrator/stall_detector.py` (~210 lignes, 0 LLM, 100%
  Python natif, thread-safe) — DeliveryOutcome enum (3 valeurs) + ACCOUNTABLE_OUTCOMES +
  WRITE_TOOLS + classify_turn + compute_material_fingerprint (port _group_fingerprint, hash
  contenu tronqué 16 hex) + _dominant_material_hash + StallDetector (threshold=2, table de
  vérité ACCOUNTABLE-différent→reset / ACCOUNTABLE-identique→incrément / PROGRESS-IDLE→incrément).
- [x] Étape SD-4 : Tests `tests/test_stall_detector.py` — 26 tests (enum 2, classify_turn 4,
  compute_material_fingerprint 6, StallDetector 8, thread-safety 1, intégration run_with_retry 3,
  non-régression F-36 2). Style test_loop_guard.py (une fonction par cas, @pytest.mark.anyio,
  SimpleNamespace, bannières # ===).
- [x] Étape SD-5 : Branchement `nodes.py run_with_retry` — nouveau param optionnel
  `stall_detector=None` (non-cassant). Pour chaque step de agent.memory.steps : classify_turn +
  compute_material_fingerprint + record. Si is_stalled() ET validated is None → message au prompt.
  reset() aligné sur loop_guard.reset(). Priorité validated conservée (log informatif dédié).
  Correctif pendant dev : record par STEP (pas par attempt) — sinon un run multi-steps ne déclenche
  qu'1 incrément et le stall n'est jamais atteint.
- [x] Étape SD-6 : Branchement production `execute_coder_node` — instancie StallDetector à côté
  du LoopGuard et le passe à run_with_retry. WebTester hérite du défaut (actif). Judge/Synth/
  Adversary ne le passent pas (nœuds de raisonnement, idle_breaker_threshold=10**9).
- [x] Étape SD-7 : Config — config.py (stall_detector_enabled défaut True + stall_detector_threshold
  défaut 2, bloc commenté style loop_guard) + load_settings (_get_bool/_get_int) + .env.example
  (bloc # --- Stall Detector ---) + .env local (AGENTS.md §7).
- [x] Étape SD-8 : Validation — 26/26 tests stall_detector PASS. Suite pytest complète 714 passed
  / 12 failed (les 12 échecs PRÉ-EXISTANTS confirmés via git stash : architect/escalation/guard-
  timeout/prompt_refiner(3)/read_gate(4)/skill_lazy_loading(2), AUCUN lié au stall detector),
  1 error collection test_static_tester (pré-existant sur main, import extract_inline_js manquant).
  0 régression. py_compile OK (stall_detector.py + nodes.py + config.py).
- [x] Étape SD-9 : État disque synchronisé (feature_list.json +F-88 completed deps [F-36],
  contract.md +critères 255-267, plan_usine_logicielle.md P3-bis 3 cases cochées + écarts
  justifiés, progress.md). Branche `feat/stall-detector-p3bis`.

> **Décision clé** : module orthogonal (LoopGuard intact) plutôt qu'extension de LoopGuard.
> La case P3-bis "Hash d'output matériel" disait "Étendre notre LoopGuard (F-36)" — décision
> contraire justifiée : le docstring loop_guard.py:10-12 dit "on n'inclut pas l'Output" (inverser
> casserait la cohérence F-36) ET le test test_valid_final_answer_wins_over_loop_guard est fragile
> (asserte guard.repeated_action() is not None après return validated). Le stall detector opère à
> un autre niveau (step/turn) que le LoopGuard (tool call isolé) — gardes complémentaires.

## Jalons de l'Itération (cycle Hotfix F-88 — hash CodeAgent vide, post-run E2E 2026-08-08)
> Run E2E Bubble Sort multi-fichier (FRESH_START=true) : verdict FAILURE après 1h10. Le stall
> detector s'est déclenché 8 fois à tort (jusqu'à "17 turns consécutifs sans changement matériel")
> sur du debug légitime du Coder, polluant son prompt avec des messages "CHANGE D'APPROCHE" →
> confusion → max_steps atteint sans final_answer valide. Régression réelle vs main (sans F-88).
> Leçon : un test unitaire mocké ne suffit pas — il faut un run réel (ou isolé) pour valider une
> feature qui touche au chemin chaud du Coder.

- [x] Étape HF-1 : Diagnostic — grep du log E2E révèle 8 déclenchements stall + "CIRCUIT BREAKER
  (Stall Detector) : 17 turns". 0 LoopGuard (le Coder ne bouclait pas — il debuguait). Le compteur
  stall ne resetait JAMAIS sur matériel nouveau (write_file répétés en phase de debug).
- [x] Étape HF-2 : Reproduction isolée sur le VRAI parseur (pas un mock) — `extract_tool_calls_from_step`
  CodeAgent retourne args = ligne source Python strippée (ex: 'write_file(path="a", content="x")'),
  PAS un dict. Or `_extract_str` ne gérait que dict + JSON-string. Pour une ligne source Python,
  retournait "" → tous les writes CodeAgent avaient le même hash SHA256("") → jamais de reset.
  BUG CONFIRMÉ : deux writes au contenu totalement différent (AAA vs BBB) → même hash e3b0c44298fc1c14.
- [x] Étape HF-3 : Fix `stall_detector.py _extract_str` — 3e cas ajouté (ligne source Python CodeAgent)
  via regex qui extrait la valeur après `key=` (guillemets doubles/simples, DOTALL). Best-effort :
  suffisant pour distinguer deux writes au contenu différent (le but du stall detector).
- [x] Étape HF-4 : Validation sur le vrai parseur — write(content=AAA) → hash X ; write(content=BBB)
  → hash Y (différent → reset) ; write(content=AAA) → hash X (identique → reproduction = stall).
  search_replace → hash non vide. CORRECT.
- [x] Étape HF-5 : 2 tests de non-régression ajoutés (test_stall_detector.py) :
  `test_material_fingerprint_codeagent_source_line_differs_on_content` (unitaire) +
  `test_stall_detector_resets_on_codeagent_write_with_new_content` (end-to-end sur la vraie chaîne
  extract_tool_calls_from_step → classify_turn → record). 28 tests PASS (26 + 2 nouveaux).
- [x] Étape HF-6 : Script d'isolation `debug/run_coder.py` créé (multi-fichier + draft injecté
  optionnel + vrai execute_coder_node). Convention F-55 étendue aux nœuds LLM. Permet la boucle
  de debug "couper si erreur, corriger, relancer" en minutes au lieu de 30-40 min.
- [x] Étape HF-7 : Validation run Coder isolé multi-fichier + draft (F-88 activé, STALL_DETECTOR=true
  seuil 2) : 0 stall sur 8 steps avec 43 tool calls d'écriture. Le fix tient en conditions E2E réelles.
- [x] Étape HF-8 : État disque synchronisé — hotfix commit + push PR #47. contract.md +critère 268.
  feature_list.json +F-89 (jeux de tests par nœud P17 MAX). plan_usine_logicielle.md +Priorité 17
  (Jeux de tests par nœud, priorité MAX) + dashboard P17 🟡 PARTIEL.

> **Leçon structurante (alimente P17/F-89)** : le bug du hash CodeAgent vide était reproductible
> en <1s sur le vrai parseur, mais a mis 1h10 de run E2E + post-mortem manuel à diagnostiquer.
> C'est la preuve que les scripts d'isolation par nœud + jeux de fixtures sont INDISPENSABLES —
> pas un nice-to-have. Placé en priorité MAX (P17) pour le cycle suivant.

## Jalons de l'Itération (cycle Jeux de tests par nœud — F-89, P17 MAX)
> Priorité MAX du plan usine logicielle. 6 scripts d'isolation LLM créés — chacun appelle la
> VRAIE fonction de production (0 mock, 0 duplication) avec fixtures figées. Permet d'itérer
> en secondes/minutes sur un nœud sans relancer le workflow E2E de 30-40 min.

- [x] Étape F89-1 : Exploration (2 agents parallèles) — signatures exactes des 6 nœuds LLM
  cartographiées (Router/PromptRefiner/Architect/Drafter/Security/Judge), clés dict lues,
  modèles utilisés (tous ignorent le param *_model → _run_dspy_node → model_lifecycle(spec)),
  config settings + 3 backends spawn. Modèles Pydantic output listés. Pattern run_coder.py
  (existant fix F-88) = référence pour la convention.
- [x] Étape F89-2 : `debug/run_router.py` — 5 prompts figés (Python mots-clés web piège /
  React JSX / HTML-CSS-JS vanilla / Rust / ambigu). Valide bug F-56a (débordement JS).
- [x] Étape F89-3 : `debug/run_prompt_refiner.py` — 3 prompts figés (vagues / déjà structuré /
  minimaliste). Affiche ambiguities_detected + refined_prompt.
- [x] Étape F89-4 : `debug/run_architect.py` — spec Bubble Sort figée. Affiche ArchitectOutput
  (plan_id, global_architecture, sous-tâches + stratégie + skills).
- [x] Étape F89-5 : `debug/run_drafter.py` — sub_dict Bubble Sort figé (configurable). Sauvegarde
  draft_markdown dans debug/drafter_isolation_out/ pour réinjection run_coder.py --draft.
- [x] Étape F89-6 : `debug/run_security.py` — 4 codes figés (propre/XSS-innerHTML/eval-URL/
  pickle.loads). Fixtures en tempfile (le nœud lit target_files depuis disque).
- [x] Étape F89-7 : `debug/run_judge.py` — 4 scénarios figés (correct+PASS / bug+FAIL / nit+PASS /
  fail-closed security=None). SecurityOutput Pydantic + test_res dict construits. Le fail-closed
  valide le hard block SANS LLM (post-mortem run 123955).
- [x] Étape F89-8 : `debug/fixtures/golden/README.md` — convention golden files (déterministe =
  golden possible ; LLM = non-golden, entrées figées seulement).
- [x] Étape F89-9 : `debug/isolation/README.md` mis à jour — 2 familles (méthodologies manuelles
  F-55 + scripts d'isolation LLM F-89) + tableau des 8 scripts.
- [x] Étape F89-10 : `debug/` retiré du `.gitignore` — 37 fichiers d'outillage versionnés
  (F-55 croyait l'avoir fait, ne l'était pas). Artefacts régénérables gardés ignorés
  (coder_isolation_out, drafter_isolation_out, run dirs, __pycache__).
- [x] Étape F89-11 : Validation — py_compile OK (6 scripts), imports OK (3 backends spawn
  validés), suite pytest 729 passed / 12 échecs pré-existants (confirmés identiques, AUCUN
  lié à F-89). 0 code de production modifié. 0 régression.
- [x] Étape F89-12 : État disque synchronisé (feature_list.json F-89 pending→completed,
  contract.md +critères 280-293, plan_usine_logicielle.md P17 🟡→🟢 + cases cochées,
  progress.md, README.md). Commit + push + PR.

## Jalons de l'Itération (cycle Consolidation mémoire KG — F-68 Phase 1, P6-ter)
> Priorité HAUTE (gisement d'écarts le plus massif de l'audit de cohérence INDEX qm).
> Le KG DuckDB grossit indéfiniment : dedup_key ne capte que les doublons EXACTS (case/
> espace), le nœud d'escalade F-23 concatène toutes les réfutations sans réduction, et
> rien n'oublie jamais. Découpage en 3 phases (décision utilisateur : Phase 1 seule ce
> cycle). Phase 1 = socle directement actionnable : consolidation LLM-juge (format qm
> UPDATE/DELETE/ADD en JSON typé) + oubli par rétention temporelle. Phase 2 (scratch/
> notebook cross-run) et Phase 3 (extraction sémantique L0-L3 TencentDB + heat) reportées.

- [x] Étape F68-1 : Exploration (3 agents parallèles) — KG actuel cartographié (6 tables,
  dedup_key = SHA1 lower/strip, add_claim dedup seulement si status='open', AUCUNE
  consolidation aujourd'hui), références qm + TencentDB analysées (qm = contrat stockage
  + consolidation UPDATE/DELETE/ADD line-oriented + oubli FIFO ; TencentDB = sémantique
  riche store/skip/update/merge + heat + L0-L3 + recall hybride), points d'intégration
  identifiés (fin de run workflows.py:858, miroir pattern escalation F-23).
- [x] Étape F68-2 : Modèles Pydantic `models.py` — ConsolidationAction (kind update/delete/
  add, index 1-based, text) + ConsolidationOutput (entity_id, actions, summary). Convention
  additive (défauts []) — non-cassant.
- [x] Étape F68-3 : Méthodes KG `knowledge_graph.py` — get_claims_by_run (JOIN provenance),
  get_entities_by_run (distinct, fidèle qm ScopeId), update_claim_content (UPDATE + recalcul
  dedup_key), delete_claim (CASCADE manuelle provenance+edges, jamais d'exception),
  prune_old_claims (miroir prune_idempotency, preserve_kinds escalation+insight par défaut).
  AUCUNE migration schéma (created_at/kind/status existent déjà).
- [x] Étape F68-4 : Applier déterministe `apply_consolidation_actions` (module-level, 0 LLM,
  port qm applyConsolidationActions) — ordre DELETE-d'abord puis UPDATE puis ADD, index
  1-based, invalide → skip fail-open, ADD via add_claim kind='insight' source='consolidation'.
- [x] Étape F68-5 : Config `config.py` + `.env.example` + `.env` — memory_consolidation_enabled
  (défaut True), memory_consolidation_after (défaut 10 = qm DEFAULT_CONSOLIDATE_AFTER),
  memory_retention_days (défaut 30). Opt-out MEMORY_CONSOLIDATION_ENABLED=false.
- [x] Étape F68-6 : Nœud DSPy `dspy_nodes.py` — ConsolidationSignature (rôle judge + invariants
  F-44 + procédure obligatoire 5 étapes + anti-nits + index 1-based) + execute_consolidation_node
  (parcourt entités par run, skip si < seuil, numérote 1-based, truncate_output, _run_dspy_node
  spec=no_think_spec think=False, applique via apply_consolidation_actions, NodeMetrics par
  entité, dégradation gracieuse None/None si LLM down).
- [x] Étape F68-7 : Branchement `workflows.py` fin de run — execute_consolidation_node si
  enabled + prune_old_claims TOUJOURS (indépendant du flag). Dégradation gracieuse try/except.
  Import execute_consolidation_node ajouté au bloc différé dspy_nodes.
- [x] Étape F68-8 : Tests `tests/test_consolidation.py` — 24 tests (Tier 1 applier+KG 17,
  Tier 2 nœud DSPy mocké 5, Tier 3 E2E workflow 3). Miroir test_escalation.py (mock
  _configure_dspy + dspy.ChainOfThought, _setup_workflow_mocks avec fake_consolidation).
- [x] Étape F68-9 : Script d'isolation `debug/run_consolidation.py` (convention F-89) — 3
  scénarios figés (doublons/mixed/clean), KG temporaire isolé (ne pollue pas data/), affiche
  claims avant/après + actions émises + vérif leçons préservées.
- [x] Étape F68-10 : Validation — py_compile OK (7 fichiers), suite pytest 763 passed / 13
  failed (12 pré-existants + 1 flaky `test_e2e_resume_reuses_same_run_dir` confirmé passant
  en isolation). 0 régression F-68. 24/24 tests consolidation PASS.
- [x] Étape F68-11 : État disque synchronisé (feature_list.json F-68 pending→in_progress,
  contract.md +critères 294-303, plan_usine_logicielle.md P6-ter case consolidation cochée +
  dashboard P6 mis à jour, progress.md, .env.example). Branche `feat/kg-memory-consolidation-f68`.

> **Décision clé** : Phase 1 seule ce cycle (consolidation + oubli). Le plan original F-68
> combinait 4 briques de 2 références (consolidation + scratch/notebook + extraction L0-L3 +
> recall hybride) — trop pour un cycle unique. Le format JSON typé (OutputField DSPy) a été
> préféré au format line-oriented pur qm car la convention projet (Judge/Security/Escalation)
> émet du JSON structuré, plus fiable sur 9B. L'oubli par rétention temporelle a été préféré
> au heat TencentDB (plus simple, miroir prune_idempotency, Pas de migration schéma).
> Phases 2+3 = cycles futurs conditionnels.

## Jalons de l'Itération (cycle F-68 Phase 2 — Recall cross-run scratch/notebook)
> Deux-tier DÉJÀ IMPLICITE après Phase 1 : scratch = observation/refutation (éphémère,
> pruné 30j), notebook = insight/escalation (durable, préservé cross-run par
> prune_old_claims). Promotion = consolidation Phase 1 (déjà câblée). Ce qui manquait =
> le RECALL (qm memory-service.ts:recall = 0 LLM). Décision utilisateur : Recall-centric +
> Global unique (top-N par récence, note « ignore si non pertinent »).

- [x] Étape P2-1 : `graph_orchestrator/knowledge_graph.py` — méthode `recall_lessons(kinds,
  limit)` (query SQL globale : SELECT content,kind,created_at WHERE kind IN (insight,
  escalation) AND status='open' ORDER BY created_at DESC LIMIT N, PAS de filtre entity_id
  ni run_id = global). Kinds défaut {insight,escalation} cohérent avec preserve_kinds.
- [x] Étape P2-2 : `graph_orchestrator/lesson_recall.py` (nouveau module, 0 LLM, miroir
  targeted_retest.py/judge_diff.py) — `recall_lessons` (wrapper) + `build_lessons_block`
  (formatage markdown numéroté + badges [LEÇON]/[ESCALATION] + note explicite + troncature
  truncate_output) + `DEFAULT_LESSON_KINDS`.
- [x] Étape P2-3 : `config.py` + `load_settings()` — memory_recall_enabled (défaut True),
  memory_recall_limit (défaut 8), memory_recall_max_chars (défaut 1500). `.env.example`
  + `.env` local (AGENTS.md §7). Opt-out MEMORY_RECALL_ENABLED=false.
- [x] Étape P2-4 : `workflows.py` — recall DÉBUT de run (après Router, avant boucle sous-
  tâches) → lessons_block → sub_dict['lessons']. Dégradation gracieuse try/except. Pas de
  checkpoint (cheap, refait pour fraîcheur).
- [x] Étape P2-5 : `nodes.py` — injection prompt Coder (pattern conditionnel original_content
  étendu, task.get('lessons') après original_content avant RAPPEL récence).
- [x] Étape P2-6 : `tests/test_lesson_recall.py` — 31 tests / 6 classes (recall_lessons KG
  10 + wrapper 2 + build_lessons_block 8 + prompt injection 4 + E2E workflow 4 + config 3).
  Migration tempfile.mkdtemp() → tmp_path fixture (review Kilo, anti-fuite disque).
- [x] Étape P2-7 : Script isolation `debug/run_lesson_recall.py` (convention F-89) — 3
  scénarios default/empty/scratch, KG temporaire isolé, vérif d'invariance (scratch non
  rappelé). `debug/print_lessons.py` corrigé (table 'claims' → 'claim', review Kilo CRITICAL).
- [x] Étape P2-8 : Validation — py_compile OK (7 fichiers), 31 tests PASS, suite pytest main
  final 785 passed / 11 failed (pré-existants confirmés identiques). Smoke recall : 4 leçons
  durables rappelées, scratch ignoré. 0 régression.

## Jalons de l'Itération (cycle F-76 — Contextualisation par package AGENTS.md localisés)
- [x] Étape F76-1 : `nodes.py execute_coder_node` — lecture `AGENTS.md` au commonpath des
  dirname des target_files, injection sous `### DIRECTIVES SPÉCIFIQUES AU COMPOSANT`.
- [x] Étape F76-2 : Défense path traversal (review Kilo WARNING) — containment realpath,
  workspace_root = os.path.realpath(os.getcwd()), fail-open silencieux.
- [x] Étape F76-3 : feature_list.json F-76 completed + plan_usine_logicielle.md case cochée.

## Synthèse merge (#50 + #51)
- [x] PR #50 (F-76) squash-merged → main (37e6ec0). Branche supprimée.
- [x] PR #51 (F-68 Phase 2) squash-merged → main (0694fac) après rebase (skip commit F-76
  base déjà mergé). Branche supprimée.
- [x] 3 retours Kilo adressés : CRITICAL print_lessons.py table + WARNING ×2 tempfile leaks
  + WARNING path traversal F-76.
- [x] Validation main final : py_compile OK, 785 passed / 11 pré-existants (0 régression),
  smoke recall OK, branches nettoyées.

## Jalons de l'Itération (cycle F-82 — Skill Finder, durcissement du scaffold)
> Constat initial : F-82 était **déjà scaffoldé et commité sur main** (`tools.py:586`
> + ReAct Architect `dspy_nodes.py:759`) mais marqué `pending` — sans tests, sans flag
> config, avec `shell=True` interpolé (injection), une regex dégénérée `\b(query)\b`,
> et une **réécriture du fichier source skills_loader.py** à l'exécution (salissait
> git, fragile). Décisions utilisateur : (1) durcir le scaffold ; (2) sécurité par
> **marqueurs skills.sh** (safe/verified) + allowlist configurable (pas d'API Socket) ;
> (3) **persistance durable** par manifeste (pas de mutation de source) ; (4) **toujours
> ON** + flag ; (5) **ligne regex dédiée multi-mots-clés** par skill installé.
- [x] Étape F82-1 : Branche `feat/f-82-skill-finder` + exploration (3 agents parallèles)
  cartographiant Architect/ReAct, skills_loader API, skills/ + config + patterns HTTP.
- [x] Étape F82-2 : `graph_orchestrator/skill_finder.py` (logique pure, standalone à
  l'import) — parse_skills_find_output (ANSI + marqueurs safe/unsafe), is_trusted
  (allowlist + blocage marqueur négatif), extract_trigger_keywords + build_trigger_regex
  (regex dédiée multi-mots-clés), install_skill (subprocess shell=False + validation
  regex composants + cmd.exe /c npx cross-plateforme), manifeste durable (register/
  load/refresh), search_and_install (orchestrateur fail-open).
- [x] Étape F82-3 : `tools.py` — `search_and_install_skill` devient wrapper mince (+
  param `triggers` hints). **Suppression** de `shell=True` et de la réécriture de
  `skills_loader.py` (→ manifeste).
- [x] Étape F82-4 : `skills_loader.py` — `DYNAMIC_SKILL_RULES.extend(load_dynamic_manifest())`
  au démarrage + helper `register_dynamic_rule` (no-op en fresh checkout → 0 régression).
- [x] Étape F82-5 : `dspy_nodes.py` — bloc ReAct F-82 gate par `if settings.skill_finder_enabled:`
  + wrapper propage `triggers`. ReAct + injection `research_summary` conservés.
- [x] Étape F82-6 : `config.py` — `skill_finder_enabled` (défaut True) +
  `skill_finder_trusted_authors` (CSV) + `.env.example` + `.env` local + `.gitignore`
  (`skills/installed-skills.json`).
- [x] Étape F82-7 : `tests/test_skill_finder.py` — 37 tests (parsing, trust, keywords/regex,
  install shell=False, manifeste, search_and_install E2E mocké, intégration skills_loader,
  @tool wrapper, config+gate source guard). 37/37 PASS.
- [x] Étape F82-8 : Validation — py_compile OK (6 fichiers) + suite complète 883 passed /
  7 failed / 1 skipped / 11 deselected. **0 régression confirmée** : les 7 échecs
  (test_read_gate ×4 + test_skill_lazy_loading ×3) sont pré-existants, strictement
  identiques au baseline via `git stash` (AUCUN lié au Skill Finder).
- [x] Étape F82-9 : État disque synchronisé (feature_list F-82 completed, contract
  critères 315-326, progress, README section 6). Branche `feat/f-82-skill-finder`. Commit + PR.
- [x] Étape F82-9b : Persistance des prompts de validation (retour user « ne pas perdre
  les prompts des bulles ») — `prompts/validation/` versionné (bubble_sort.md snapshot
  du prompt canonique + skill_finder_ai_sdk.md + skill_finder_react.md forceurs F-82) +
  README de convention + `scripts/load_prompt.py` (charge un .md → tasks.json coding[0],
  parse frontmatter id/target_files/expected_skill_finder). Le Prompt-Vault
  (references/, gitignoré) reste la banque externe ; prompts/validation/ est l'instantané
  minimal versionné. Loader smoke-testé (round-trip OK, cible temp, 0 modif tasks.json).
- [x] Étape F82-10 : Validation live (pipeline direct `search_and_install("react")`) —
  RÉUSSIE. `vercel-labs/agent-skills@vercel-react-best-practices` (auteur de confiance)
  installé dans `skills/`, manifeste `skills/installed-skills.json` écrit avec **regex
  dédiée** `\b(react|next|performance|optimization|...)\b`, `select_skills_for_coder`
  l'inclut (`[file-creation, coding, context7-research, vercel-react-best-practices]`).
  ⚠️ Bug trouvé + corrigé en live : `install_skill` n'injectait pas `-y --copy` → la CLI
  skills demandait une confirmation en subprocess non-tty (hang/timeout). Fix appliqué
  + test `assert "-y" in cmd and "--copy" in cmd`. Stopwords enrichis (should/shall/must).
  ⚠️ Finding production (suivi requis) : `npx skills add --copy` reproduit le skill dans
  ~27 dossiers d'agents (`.augment/`, `.codebuddy/`, `.continue/`...) — seul `skills/`
  nous intéresse. Nettoyage post-install (parse sortie CLI → rm agent dirs ≠ skills/) ou
  gitignore des patterns d'agents à ajouter dans un cycle futur. Working tree nettoyé
  post-démo (skill non bundlé — réinstallable en 1 commande).
- [x] Étape F82-11 : Validation **ReAct Architect LLM** — RÉUSSIE (Ornith-9B, GPU).
  `debug/run_architect.py @prompts/validation/skill_finder_ai_sdk.md` (corps seul) → le
  ReAct `SkillResearchSignature` a **appelé `search_and_install_skill`** et installé
  `vercel-labs/ai@ai-sdk` (auteur de confiance). Manifeste écrit avec **regex dédiée**
  `\b(ai-sdk|ai|streamtext|usechat|...)\b` (mots-clés extraits de la vraie description),
  `skills/ai-sdk/` créé, refresh_dynamic_rules in-memory, Architect terminé (exit 0,
  177.9s, plan 2 sous-tâches multifile). Le 9B décide donc bien d'invoquer l'outil.
  2 corrections appliquées lors de la validation :
  (1) ReAct `think=False` (avant `think=True` → hang 580s en thinking sur 9B, miroir F-47) ;
  (2) prompt `SkillResearchSignature` directif (« tu DOIS appeler l'outil si une techno est
  nommée ») — avant, le 9B répondait « Aucun » par défaut (décision paresseuse).
  ⚠️ Trouvaille wiring (suivi) : si le résumé ReAct finit en « Aucun » malgré l'install
  (incohérence petit modèle), l'Architect ne sélectionne pas le skill dans `subtask.skills`
  → le Coder (voie F-57 prioritaire sur subtask.skills) ne le voit pas au run courant ;
  en revanche les runs futurs le voient via le manifeste (catalogue Architect). À durcir si
  besoin (propager le nom installé au-delà du seul résumé LLM). Working tree nettoyé
  post-démo (skill non bundlé). Témoin négatif `bubble_sort.md` → « Aucun skill ajouté »
  (vanilla, pas de techno nommée) reste à confirmer en run.

## Jalons de l'Itération (cycle F-90 validation run + 7 hardening fixes, 2026-08-11)
> Objectif utilisateur : « faire un run complet sans erreur, si erreur corriger puis
> relancer jusqu'à un run réussi ». 9 runs E2E Bubble Sort pour diagnostiquer et fixer
> toute la chaîne. SUCCÈS au run #9 : sous-tâche 1 APPROUVÉE par le Judge au 1er cycle
> (1ère approbation en 9 runs). F-90 marquée completed.

- [x] F-90 : Architecte produit les 3 champs (visual/functional/rubric), injectés aux 3
  nœuds. Validé en isolation (debug/run_architect.py affiche les critères) + E2E (run #9).
- [x] Fix screenshot `filePath` : `_ScreenshotCapturingTool.forward()` (vision_callback.py)
  strippe le kwarg `filePath` avant délégation. Le mode `--isolated` de chrome-devtools-mcp
  rejette toute écriture disque → l'outil échouait AVANT de retourner l'image → la callback
  vision ne capturait rien → boucle de 25 steps (run #1). Règle anti-filePath dans
  devtools-preview/SKILL.md. Test test_strip_filepath_avant_delegation. Documenté AGENTS.md §7.
- [x] Fix Tester convergence : tester_max_steps 25→8, tester_timeout_s 600→480, règle 6
  « budget steps » (web_tester.py). 8 steps × ~55s pire cas = 440s < 480s → le Tester
  converge (max_steps gagne la course contre le wall-clock) au lieu de timeout.
- [x] Fix Tester fallback verdict : `_tester_max_steps_fallback` (nodes.py) scanne le step
  history et dérive un verdict comportemental (FAIL observé → failure, assertions PASS sans
  FAIL → success) quand l'auto-final-answer à max_steps ne parse pas. Évite la boucle de
  3 retries (~15 min) puis None. 6 tests (test_coder_hardening.py). Validé E2E run #5/#9.
- [x] Fix Judge vue deliverable complet : `_judge_deliverable_files` (dspy_nodes.py) UNION de
  target_files avec TOUS les fichiers source du run dir. Cause racine escalade run #5 :
  l'Architect split un app 3-fichiers en 3 sous-tâches → le Judge ne voyait qu'1 fichier
  → « css/js manquants » → rejet systématique ×3. 3 tests (test_judge_diff.py).
- [x] Fix règle CSS height inline : `coding/SKILL.md` section « RÈGLES CRITIQUES » eager-loaded
  (pas derrière une resource lazy). Pattern EXACT : ❌ `bar.style.height='0px'` à la création
  = BUG n°1 (barres invisibles au load), ✅ `(value*SCALE)+'px'` dès le createElement. Le 4B
  l'applique dès le run #9 (`Math.max(10, value*2)px`). C'était LE failure mode persistant
  (Static Tester catchait « height=0 » à chaque run).
- [x] Fix Static Tester settle wait : `_evaluate_visibility` (static_tester.py) probe maintenant
  `async () => { click; await setTimeout(150); probe; }` au lieu de `() => { click; probe; }`
  synchrone. Laisse les handlers async/re-render se stabiliser (réduit faux-positifs).
- [x] debug/run_architect.py : affiche les 3 champs F-90 (visual/functional/rubric) dans la
  sortie isolation (était manquant).
- [x] Validation run #9 : sous-tâche ts-html-structure APPROUVÉE par le Judge au 1er cycle.
  Tous les fixes actifs simultanément : barres visibles (height rule) → Static Tester PASS →
  Tester fallback=success → Judge deliverable view (3 fichiers) → APPROUVÉ. 52+ tests unitaires
  PASS (chrome_devtools + coder_hardening + config + judge_diff), 0 régression confirmée.

## Jalons de l'Itération (Meta-Analyste — post-mortem run9 F-90, 2026-08-12)
> Rôle Meta-Analyste (AGENTS.md §8) : `uv run python scripts/run_analyzer.py --log
> logs/e2e_f90_validation_run9.log`. Run9 = SUCCÈS (2 Judge APPROUVED) mais coûteux
> (7.59M tokens input, ~41 min). 3 problèmes récurrents identifiés, 1 traité ce cycle.

- [x] **MA-1 Diagnostic** : 3 signaux — (1) explosion contexte Coder (6.39M tokens / 43 steps,
  ~84% du budget, chantier lourd Context Epochs laissé hors périmètre) ; (2) `InterpreterError:
  Import of os is not allowed` côté Tester (log lignes 2771/2789) — le Tester (CodeAgent) a
  généré `import os` pour lire ses ressources de skill, la sandbox n'autorise que
  ['unicodedata','collections','re','math','time','random','statistics','itertools','queue',
  'datetime','stat'] → crash + code fragmenté (variable `resource_files` perdue entre steps) ;
  (3) saturation llama-server (2× Pydantic→DSPy rescue→Connection error, déjà atténué par
  AUDIT_PARALLEL=false, infra).
- [x] **MA-2 Fix `import os` Tester** (jumeau du fix `import time` F-61/RAA-2, même failure
  mode) : (a) règle n°4 `web_tester.py` réécrite — OUTILS `read_file`/`list_directory` préférés
  pour LIRE, built-ins `open()`/`read()` restent interdits par la sandbox ; (b) safety net
  `additional_authorized_imports=["os", "subprocess"]` sur le `CompactingCodeAgent` du Tester.
  **DÉCISION UTILISATEUR (principe TESTER = CODER)** : le Tester écrit des scripts de test et
  doit pouvoir coder comme le Coder → même set d'imports que `nodes.py:1071` (os + subprocess,
  1:1). Premiere version du fix n'avait mis que `["os"]` (subprocess écarté par « frontière de
  périmètre » — sur-prudent, corrigé). Doctrine F-33 « un prompt seul ne suffit jamais » :
  la règle steer vers les outils, le safety net rattrape le slip sans crash. Validation :
  py_compile OK + sous-ensemble pytest (test_tester_dispatch + test_config + test_static_tester)
  47 passed / 1 skipped / 0 failed. Branche `fix/tester-import-os-guard`.
- [ ] **MA-3 (à évaluer, hors petite tâche)** : explosion contexte Coder (compaction L4
  existante via CompactingCodeAgent mais insuffisante — envisager Context Epochs / budget
  par step plus strict). Cycle lourd, reporté.
- [x] **MA-4 Validation live GPU** (`debug/run_web_tester_standalone.py` retargeté vers
  `runs/2026-08-11_2109_bubble_sort_multifile_v6/index.html`, Ornith-9B reasoning off, 8 steps).
  **RÉSULTAT : bug `import os` ÉLIMINÉ.** Sur les 8 steps, le Tester n'a JAMAIS tenté `import os`
  — il a utilisé l'outil `read_file` (steering règle n°4). Zéro `InterpreterError: Import of os`.
  Le safety net `additional_authorized_imports=["os","subprocess"]` n'a même pas eu à agir (cas
  idéal : la règle a suffi). Le fix MA-2 est donc VALIDÉ en run réel.
- [ ] **MA-5 (révélé par la validation, AUTRE cycle, hors périmètre MA)** : le run s'est terminé
  en `failure` non à cause d'`import os` mais d'un failure mode DISTINCT pré-existant — (a) le
  Tester a brûlé ses 8 steps à lire les 5 `resources/` F-92 de la skill (progressive disclosure)
  sans jamais atteindre le test réel (0 navigate_page, 0 assertion, 0 screenshot) ; (b) 3 steps
  perdus sur des erreurs de format de chemin Windows (`file:///...` → [Errno 22], `/D:/GIT/...`
  (préfixe MSYS) → WinError 123) avant de trouver `D:/GIT/...`. Le fallback F-90 a dérivé un
  verdict `failure` correct. Pistes cycle futur : plafonner/réduire le nb de resources lues par
  le Tester (ou injecter leur contenu en eager plutôt que lazy), et durcir le prompt chemin
  Windows (la directive existante n'a pas empêché le modèle d'utiliser `file:///` depuis les
  liens markdown de la skill).

## Jalons de l'Itération (cycle MA-5 — durcir le Tester : resources skill + chemins Windows, F-97)
> Reprise du thread MA-5 laissé ouvert ci-dessus. Périmètre = les 2 failure modes révélés par la
> validation live du fix MA-2. Investigation approfondie (2 subagents Explore) → les racines
> réelles étaient PLUS PRÉCISES que le framing MA-5 initial (bug générateur `view_file` n'existe
> pas + piège `file:///` correct pour un outil, fatal pour l'autre).

- [x] Étape MA5-1 : Plan approuvé (EnterPlanMode → ExitPlanMode). Décisions clés : (a) résoudre
  la progressive disclosure F-92 **côté serveur** pour le Tester (inline) plutôt que compter sur
  le prompt — l'inline est strictement meilleur pour un agent one-shot qui a besoin de TOUT le
  contenu ; (b) garde logiciel de normalisation en tête des outils fichier (doctrine F-33) + prompt
  réécrit, pas prompt seul.
- [x] Étape MA5-2 : `graph_orchestrator/path_utils.py` (NEW) — `normalize_tool_path` (pur chaîne,
  SANS abspath pour préserver relatifs + hashing read_gate ; strippe `file:///` variantes + MSYS
  `/d/` ; fail-open). Aucune règle `^([a-zA-Z])/` sans slash initial (sinon `src/a.js` → `S:/rc/a.js`).
- [x] Étape MA5-3 : `tests/test_path_utils.py` (NEW, 19 tests) — 3 variantes de slashes, `/X:/`,
  MSYS `/x/`, anti-corruption relatifs, backslash inchangé, déjà-correct, vide/non-str, idempotence.
  19/19 PASS.
- [x] Étape MA5-4 : `tools.py` — `read_file` + `list_directory` appliquent `normalize_tool_path`
  en tête (défense en profondeur, bénéficie au Coder). Import ajouté. +2 tests d'intégration
  dans `test_tools.py` (read_file/list_directory acceptent un `file:///` sur tmp_file/tmp_dir).
- [x] Étape MA5-5 : `skills_loader.py` — `load_skill_body_resolved(name)` : inline les
  `resources/*.md` sous `### <title>` (tri déterministe) + RETIRE la section pointeur
  « ## Dynamic Resources » (sinon l'instruction `view_file` reste, contradictoire) + bannière
  anti-re-read. Fallback corps brut si pas de `resources/`. Skill absent → `""`.
- [x] Étape MA5-6 : `tests/test_skill_resolve.py` (NEW, 7 tests) — mécaniques (tmp skills via
  monkeypatch SKILLS_DIR) + intégration sur la VRAIE skill `web-tester` (resources inlinées, plus
  de `view_file`, plus de liens `file:///.../resources/`). 7/7 PASS.
- [x] Étape MA5-7 : `web_tester.py` — `:150` utilise `load_skill_body_resolved` (gated flag,
  défaut ON) ; `:250` règle chemins réécrite (`file:///` RÉSERVÉ à `navigate_page` ;
  `read_file`/`list_directory` attendent un chemin simple, note que la normalisation auto rattrape).
- [x] Étape MA5-8 : `config.py` + `.env.example` + `.env` — `tester_inline_skill_resources: bool
  = True` + `_get_bool("TESTER_INLINE_SKILL_RESOURCES", True)` + report local.
- [x] Étape MA5-9 : Racine générateur — `scripts/refactor_skills.py` `view_file` → `read_file` +
  « read on-demand, NOT all upfront ». Hygiène ressource `evaluation_criteria` : « 12 max steps »
  (stale, cap réel 8) → « TESTER_MAX_STEPS, par défaut 8 ».
- [x] Étape MA5-10 : Validation — py_compile OK (9 fichiers). 28 nouveaux tests PASS. Suite
  complète **892 passed / 8 failed** (les 8 STRICTEMENT pré-existants `test_read_gate` ×4 +
  `test_skill_lazy_loading` ×3 + `test_guard` ×1, confirmés identiques via `git stash`). **0 régression.**
- [x] Étape MA5-11 : État disque synchronisé — feature_list.json +F-97 (completed), contract.md
  +critères 327-336, progress.md (ce bloc), .gitignore (.pytest_tmp/). Branche
  `fix/tester-resources-paths-ma5`. Commit + push + PR.

> **Décision clé (a)** : résoudre la progressive disclosure côté serveur plutôt que durcir le stub.
> Le Tester (one-shot, 8 steps) a besoin de TOUT le contenu de la skill — lire 5 resources
> dynamiquement = 5 steps + 5× tokens en contexte dynamique, alors que l'inline = 1× tokens en
> system prompt (cached). La progressive disclosure F-92 n'est bénéfique QUE pour les agents qui
> lisent à la demande ; le Tester non. Le bug générateur `view_file` (qui n'existe pas dans le
> projet) rendait en plus la consigne inapplicable. Le loader `load_skill_body_resolved` est
> générique (réutilisable par d'autres nœuds si besoin) et préserve F-92 sur disque.
> **Décision clé (b)** : un garde logiciel de normalisation (et pas seulement un prompt) —
> `file:///` est un token correct pour `navigate_page` et fatal pour `read_file`/`list_directory` ;
> aucun prompt ne peut rendre ce dualisme infaillible. `normalize_tool_path` rend le bug impossible
> quel que soit le comportement du modèle, SANS corrompre les chemins relatifs (pas d'abspath).

## Jalons de l'Itération (cycle Coder Stop Condition & Navigation HTML-only — PR #70)
- [x] Étape CSC-1 : Diagnostic empirique du run de 2 heures — le Coder naviguait sur `styles.css` avec DevTools MCP, générant un DOM vide (`<pre>`), entraînant des assertions JS fausses et une boucle de 35 steps de tests redondants.
- [x] Étape CSC-2 : Ajout de l'Invariant universel 13 (Deterministic Stop Condition) dans `graph_orchestrator/prompts.py` (obligation d'appeler `final_answer` dès les tests initiaux validés).
- [x] Étape CSC-3 : Interdiction formelle de naviguer sur des fichiers non-HTML (`.css`, `.js`, etc.) dans `skills/devtools-preview/SKILL.md` et dans le prompt du `coder_frontend`.
- [x] Étape CSC-4 : Validation en isolation via `debug/run_coder.py` (Qwen 4B) : 3 fichiers générés (`index.html`, `styles.css`, `script.js`), 0 erreur console, rendu visuel validé, fuzzing boutons réussi, sortie propre via `final_answer` à l'étape 14 (sans boucle).
- [x] Étape CSC-5 : Revue Kilo validée sans réserve ("No Issues Found | Recommendation: Merge"), PR #70 squash-mergée et branche supprimée.

## Jalons de l'Itération (cycle Update References — pull amont 2026-08-14)
> Workflow `references/PROCEDURE-UPDATE-REFERENCES.md` (5 étapes). Synchronisation périodique
> des dépôts amont + veille + backlog. AUCUN code de production modifié.

- [x] Étape UR1 : `update_references.py` exécuté — **25 dépôts mis à jour / 19 à jour /
      1 erreur** (LlamaBot : historique réécrit en amont « forced update » → resynchronisé
      `git reset --hard origin/main` @884cd2a, fix SSRF page-clone). Rapport
      `references/update_report.md` régénéré (25 sections, ~5 700 fichiers changés).
- [x] Étape UR2 : analyse des nouveautés par **3 subagents Explore parallèles** (7 dépôts
      harness cœur + 7 skills/prompts + 12 frameworks). Faits saillants : qm `goal.ts`
      (enforcement de but anti faux-« fini »), hermes `verify/` (recettes d'exécution +
      readiness HTTP), opencode compaction réécrite POUR PETITS MODÈLES, learn-claude-code
      s08 réordonné (archive disque .transcripts), pi §3.9 `overflowRecoveryUsed`, open-swe
      `turn_checkpoint.py` (snapshot git PAR TOUR), Anthropic `prompt-audit` (signaux
      greppables), Claude Code v2.1.224→v2.1.232 (WaitForMcpServers + anti
      permission-laundering + safety=frontière non retryable), `claude-science.md` (folds =
      search queries + frame), davidondrej groupe 10 password managers, brooklyn `babysit`,
      deer-flow budgets AGENTS.md + fix dangling tool calls, crush MCP init gate, openfox
      retry pré/mid-stream. Fiches déjà auditées : fichiers clés inchangés ou évolutions
      sans changement de design (qm context-compaction, hermes trajectory_compressor,
      loopx event_sourced_state).
- [x] Étape UR3 : `feature_list.json` + **7 features F-99..F-105** (toutes `pending` ;
      invariant respecté : AUCUNE feature `completed` modifiée). 104 features au total
      (84 completed / 19 pending / 1 in_progress).
- [x] Étape UR4 : `plan_usine_logicielle.md` + **10 cases `[ ]` datées « update références
      2026-08-14 »** (P3 enforcement de but, P6 recettes verify, P8 retry v2, P8-bis
      checkpoint git/tour + sécurité groupe 10, P9 compaction v2, P0-bis prompt-audit +
      budgets guidance + invariants CC, P10 routeur skills + skills écrites par l'agent,
      P11 prompt envelopes + event bus). Invariant respecté : 0 case cochée modifiée
      (10 insertions pures, vérifiées par `git diff`).
- [x] Étape UR5 : état disque synchronisé (progress.md ce bloc) + commit et push
      sur main via cherry-pick (procédure « branche feature active » — la session était sur
      `fix/update-llamacpp-asset-matching`).

## Jalons de l'Itération (cycle F-106 — clôture du journal plat, 2026-08-14)
> Décision utilisateur : « toute mention du journal plat doit disparaître, ainsi que le
> fichier à la fin, pour ne plus jamais l'utiliser ». Diagnostic préalable (réponse à la
> question « pourquoi écrit-on encore dedans ? ») : l'écrivain était l'ASSISTANT en fin
> de cycle (convention héritée), pas le code de production ; et la migration F-75 avait
> perdu les dates historiques (194 événements tous horodatés à la date de migration —
> bug migrate_log.py : la date d'en-tête était capturée mais jamais utilisée) avant que
> le fichier ne soit supprimé PUIS re-créé à la main le 2026-08-12.

- [x] Étape F106-1 : Diagnostic — base event_stream.duckdb dormante (dernier write
  2026-08-05 : seul le Coder 4B pouvait l'alimenter de sa propre initiative via l'outil
  log_event ; aucun nœud du graphe n'émet d'événement lifecycle) tandis que le fichier
  plat reprenait sa croissance à chaque cycle docs.
- [x] Étape F106-2 : `scripts/recover_log_history.py` — récupération depuis git (47
  versions, les deux ères du fichier via --follow, pic 198 entrées avant la suppression
  F-75), parsing `## [date] type | titre` (regex `[\w-]+` corrigeant l'absorption de
  `P8-bis` par l'ancienne regex), union dédupliquée par (date, type, titre), sous-titres
  non datés rattachés au corps, import DATÉ (created_at = date d'en-tête, fallback date
  du commit de première apparition), idempotent (clé event_type+titre), backup base +
  remplacement documenté des 194 lignes 'legacy' non datées.
- [x] Étape F106-3 : Migration exécutée — base finale 199 événements datés
  (2026-07-29 → 2026-08-14, run_id legacy_md) ; 3 coquilles source corrigées
  ([2026-01-08] → 2026-08-01 pour F-41/F-42/F-43) ; entrée P8-bis F-43 récupérée ;
  préambule « 🔧 INFOS À SAVOIR » préservé.
- [x] Étape F106-4 : `scripts/log_event.py` — CLI d'historisation pour l'ASSISTANT
  (même table/canal que l'outil du graphe ; options --run-id/--node/--date). Dogfoodé
  immédiatement (événements #394 diag + #395 done, run_id f-106).
- [x] Étape F106-5 : Suppression définitive (git rm) du fichier journal et de
  `scripts/migrate_log.py` (obsolète). Purge de TOUTES les mentions : AGENTS.md §2D
  réécrit (règle critique « AUCUN JOURNAL PLAT », interdiction de recréation, deux
  canaux runtime/assistant documentés), progress.md 21→0, contract.md (Critère 4
  réécrit + section F-106 critères 354-358), feature_list.json (F-04/F-74 réécrits,
  +F-106), plan_usine §P11 annoté FAIT-partie-plate, references_audit.md, commentaire
  nodes.py, docstrings log_event.py. Tombstones assumées (3) : la règle d'interdiction
  AGENTS.md, le script de récupération (qui doit nommer le chemin git), l'audit du
  dépôt externe opencode (fichiers du tiers).
- [x] Étape F106-6 : Validation — 13 tests PASS (`tests/test_log_recovery.py` : parser
  6, created_at fallbacks 1, dedup multi-versions 1, insertion remplacement legacy +
  idempotence + dry-run 3, git-walk réel sur repo tmp 1, CLI 2). py_compile OK.
  Sanity 43/43 (test_guard + test_stall_detector, import nodes.py). Sweep grep final
  vérifié. F-74 reste pending pour la part runtime (instrumentation workflows +
  runs_history + rétention).

## Jalons de l'Itération (cycle F-99 — Goal Enforcement, P3, 2026-08-14)
> 1re feature du backlog F-99..F-105 (update références 2026-08-14). Prolonge le fil
> anti-loop signature (F-36 LoopGuard → F-88 StallDetector → F-99 garde comportementale
> du faux « j'ai fini »). Rebasée sur main post-merge F-106 (4227b55).

- [x] Étape F99-1 : Exploration qm (`src/harness/goal.ts` + `grind.ts`) + points
  d'insertion (`run_with_retry` où F-36/F-88 sont déjà branchés, `execute_coder_node`,
  config). Design : audit de complétion DÉTERMINISTE (le disque = état autoritaire)
  + prompt de continuation qm + bornes (impasse/deadlock/cap).
- [x] Étape F99-2 : Module `graph_orchestrator/goal_enforcer.py` — 4 mécanismes qm
  (continuation prompt « NON PROUVÉE » avec preuves manquantes concrètes, blocked
  après 3 MÊME impasse, auto-waiver après 5 rounds sans tool call, token cap 2M =
  wind-down unique). Audit mode-aware (création stricte / correction allégée).
  Objectif échappé HTML + encapsulé <objectif> (anti-injection, miroir qm).
- [x] Étape F99-3 : Branchement — `run_with_retry` (param `goal_enforcer`, metering
  par attempt, RAPPEL générique supprimé sur les rounds de continuation) +
  `execute_coder_node` (GoalEnforcer depuis task content/target_files/iteration/
  _is_web_task) + config (4 settings) + .env.example + .env.
- [x] Étape F99-4 : Tests — 22 PASS. BUG D'INTÉGRATION découvert et corrigé :
  `loop_guard.known_tools` (F-36) ignorait multi_replace/check_js_syntax/outils
  DevTools → aucune preuve verify-after visible en chemin CodeAgent (l'audit
  web échouait systématiquement). Liste étendue (13 outils), exemptés
  observationnels préservés dans record().
- [x] Étape F99-5 : Validation — suite complète **1035 passed / 0 failed / 1 skipped**
  (+22 vs baseline 1013), py_compile OK. Écarts consciencieux vs qm documentés
  (boucle bornée max_retries, delta tool calls adapté à la purge mémoire, pas
  d'outil update_goal, objectif tronqué 4000).
- [x] Étape F99-6 : État disque synchronisé (feature_list F-99 completed, contract
  critères 359-364, plan case P3 cochée, progress ce bloc, événements journalisés
  via scripts/log_event.py run_id f-99 — convention F-106).

## Jalons de l'Itération (runs E2E de validation F-99/F-97/PR#70 — 2026-08-14)
> Objectif : valider en live les 5 changements comportementaux accumulés depuis le run #9
> (F-72, F-97, PR #70, F-99, F-106). Prompt canonique Bubble Sort (multifile-v6),
> WORKFLOW_MODE=coding, spawn backends. 3 runs, dont l'analyse a produit 2 durcissements (PR #74).

- [x] Run #1 (échec infra) : Coder 3/3 tentatives en `exceed_context_size_error` — requests
  33-39k tokens > n_ctx 32768 du llama-server Qwen. Correctif : FAST_CONTEXT 32768 → 49152
  (local .env + défaut .env.example). F-99 non en cause (0 déclenchement, mort par 400 serveur).
- [x] Run #2 (échec révélateur) : final_answer VALIDE + 3 fichiers sur disque au 3e attempt,
  mais (a) continuation F-99 sur le DERNIER attempt (budget épuisé → échec technique au lieu
  du Judge) et (b) audit sur mémoire purgée (preuves des tentatives précédentes invisibles).
  Correctifs PR #74 : waiver dernier attempt + preuves cumulées cross-attempts + reason
  listant les preuves manquantes.
- [~] Run #3 (approbation Judge = **FAUX POSITIF** — REJETÉ par l'utilisateur en validation manuelle) :
  F-82-ts-01 APPROUVÉ par le Judge 🚀 (2e approbation du projet).
  F-99 en action : T1/T2 défiées (le 4B voulait finir SANS AUCUN write — « Je peux maintenant
  appeler final_answer ») → le modèle a produit les 3 fichiers au fil des tentatives (styles
  21:57, script 22:05, index 22:08) → T3 même impasse → blocked-waive → Judge a arbitré et
  approuvé. Chaîne complète : Linter → Static Tester (4.1s) → Tester (fallback verdict) →
  Security → Judge → consolidation. Métriques attempt réussie : Coder 130.7s/184k tokens,
  Tester 286s/180k. Signaux validés : PR #70 (0 navigation non-HTML), F-97 (0 erreur de
  chemin réelle — l'unique grep = le texte du prompt), F-90 (critères présents), F-68
  (8 leçons rappelées), F-106 (event stream + consolidation OK).
- [ ] **Requalification (2026-08-14 soir, validation manuelle utilisateur)** : le run #3 NE
  compte PAS comme golden. Bugs constatés à la main dans le livrable : animation instantanée
  (`await sleep(speed)` avec speed=1-10 **millisecondes**/étape au lieu de ~100-300ms attendus),
  compteur de comparaisons **jamais incrémenté** (reste 0 à vie — initialisé/affiché mais pas
  d'incrément dans bubbleSort), rendu buggé (`updateBar` dessine sans effacer → traînées +
  barres qui restent orange au lieu de restaurer leur couleur). Faits méta : (1) le Tester
  (fallback max_steps) avait DÉRIVÉ `failure` — BON verdict — et le Judge l'a OUTREPASSE sans
  persister son raisonnement dans le KG (gap d'observabilité : aucun claim 22:18-22:24) ;
  (2) F-99 reste valide côté mécanique (continuations/waive ont fonctionné comme conçus) ;
  (3) pistes de correction proposées à l'utilisateur (AGENTS.md §8, en attente de feu vert) :
  gate fail-closed du Judge sur test_results=failure, durcissement de l'échelle de vitesse
  dans le prompt Coder/skill (règle 9 : exiger un delay explicite 50-300ms par étape + test
  du compteur), persistance du verdict Judge (findings + justification) dans le KG.
- [x] Durcissement final (run #3 a révélé le dernier angle mort : la COMPACTION ampute
  memory.steps — « AUCUN appel d'écriture » alors qu'index.html venait d'être écrit) :
  preuve par le DISQUE d'abord (création), git status des cibles (correction, source
  autoritaire F-53), verify-after retiré des bloqueurs (redondant F-50 + Static Tester).
  28 tests F-99 PASS, 87 guards, py_compile OK.
- [x] État disque synchronisé : feature_list F-99 (validation E2E consignée), contract
  critères 365-367, progress ce bloc, événements #398-#402 (run_id e2e-f99-validation),
  analysis_report.md régénéré.

## Jalons de l'Itération (post-mortem run #3 — fail-closed Judge + Tier 1c, F-108, 2026-08-14)
> Suite au REJET utilisateur du run #3. Diagnostic complet depuis les logs + le code généré,
> puis correctifs (feu vert utilisateur « corrige le juge ou tester pour trouver le bug »).

- [x] PM-1 Diagnostic (logs en détail) : le Tester a BIEN travaillé (9 steps : navigation,
  console, 4 clics, 10 evaluate_script) et son fallback a correctement dérivé `failure` ;
  mais (a) le statut n'était PAS transmis au LLM Judge (seuls les details), (b) le prompt
  Judge « SANCTIONNE LES ÉCHECS » a été ignoré par le 9B, (c) le Static Tester Tier 3 exigait
  t1>t0 — le compteur MORT (0→0) rendait l'instantané indétectable (les 2 bugs se camouflaient
  mutuellement), (d) le verdict Judge n'était persisté nulle part. Bugs du livrable : sleep 5ms
  (l.89 script.js), comparisons jamais incrémenté (l.18/36), updateBar sans effacement (traînées
  orange). VERDICT : pas une régression — angle mort latent (Coder 4B + Tier 3 depuis F-54 +
  Judge jamais gated), révélé par les signaux améliorés F-61/F-99.
- [x] PM-2 Gate fail-closed TEST (mirror Security F-61) : failure/timeout/absent →
  is_approved=False SANS appel LLM + finding critical/testing + feedback propagé. Opt-out
  JUDGE_RESPECT_TEST_FAILURE. + transmission du statut dans test_results.
- [x] PM-3 Static Tester Tier 1c (_check_behavioral_smells, 0 LLM) : compteur mort + délai
  < 20ms (garde anti-FP setTimeout). Validé sur le script.js EXACT du run #3 : 2 bugs attrapés,
  version corrigée 0, cas légitimes 0 FP.
- [x] PM-4 Persistance verdict Judge dans l'event stream (node=judge, type=verdict) —
  auditable.
- [x] PM-5 Validation : 12 tests judge + 8 Tier 1c + suite complète **1052 passed / 0 failed /
  1 skipped**. py_compile OK. État disque synchronisé (F-108, contract 368-371, ce bloc).

## Jalons de l'Itération (F-109 — audit visuel matérialisé + Tier 4 console, boucle Coder, 2026-08-15)
> Objectif utilisateur : le Coder doit VOIR ses erreurs et corriger — boucle sur le Coder seul
> (debug/run_coder.py) avec les 6 critères exacts du run #5. Coupe/fix/relance en cas d'erreur.

- [x] B1 : boucle 1 (constat) — 60 steps : 4 screenshots, 2 fuzz, 6 console, 4 edits, MAIS 0 visual_check
  et 0 final_answer (tentative 1 morte à max_steps 40). Diagnostic : l'exigence de checklist n'est que
  dans le prompt initial + au final_answer jamais atteint → le modèle ne la voit jamais réaffirmée.
- [x] B2 : correctifs (commit fa4c8d9) — outil visual_check (audit matérialisé, pattern evidence exigée),
  enforcement final_answer (_visual_checklist_error : incomplet/False/creux = blocage), CHECKLIST
  OBLIGATOIRE dans le prompt critères, injection RAPPEL au boundary d'attempt (F-109-bis, décompte exact),
  Static Tester TIER 4 console (crash runtime : validé LIVE sur run #4 « Uncaught TypeError reading
  'sorted' » → False ; vrai négatif run #5), config VISUAL_AUDIT_ENABLED.
- [x] B3 : boucle 2 (preuve) — **6/6 visual_check matérialisés avec observations** + final_answer
  success en UNE tentative (13 steps, 503 s, 303k tokens — vs 2×40 steps sans conclusion).
- [x] B4 : vérification DIRECTE du livrable par l'assistant : 0 erreur console, compteur de
  comparaisons incrémenté (0→15 à ~2/s = 500 ms/step conformes au slider 100-2000ms), 50 barres
  proportionnelles (DOM), permutations visibles, thème sombre, boutons fonctionnels (capture prise).
- [x] B5 : état disque synchronisé (F-109, contract 372-377, événements run_id f-109).

## Jalons de l'Itération (F-110 + runs E2E #6/#7 — clôture 2026-08-15 soir)
> Objectif : run E2E complet jusqu'à Judge APPROUVÉ avec toute la chaîne (F-108/F-109/Tier 4).

- [x] Run #6 : chaîne complète OBSERVÉE pour la 1re fois — it.1 : 6/6 visual_check MAIS Tier 1c attrape le
  compteur non incrémenté → court-circuit Tester LLM → gate F-108 APPROBATION BLOQUÉE → rejet → it.2 corrige
  (comparisons++ ajouté) → Judge APPROUVÉ. Apparence de succès MAIS vérification directe = FAUX POSITIF
  résiduel : animation INVISIBLE (draw() jamais rappelé, 30 divs DANS le canvas) + compteur incrémenté mais
  jamais réaffiché. Compteur figé à 0 à l'écran, canvas statique — 0 erreur console (bug d'omission, pas de crash).
- [x] F-110 (commit 532b255) : gardes (c) compteur-rafraîchi (seulement si affiché ; rafraîchi requis dans les
  400 chars après l'incrément) + `_check_canvas_children` (appendChild dans <canvas> = jamais rendu) + skill
  coding règle 5 (boucle d'animation canonique avec exemple complet). Validation : run6 → 2 flags exacts,
  loop2 sain → 0, suite 1065/0.
- [x] Run #7 : le système a fonctionné EXACTEMENT comme conçu — 3 itérations toutes REJETÉES (le 4B a
  reproduit le bug du compteur mort à chaque itération ; injection boundary F-109-bis a joué 2×), escalade
  finale avec diagnostic correct (« comparisons initialisé à 0 mais jamais incrémenté »). PLUS AUCUN faux
  positif d'approbation ne passe. En contrepartie : pas d'approbation ce run — goulot = convergence du 4B
  (variance : run #6 avait convergé en 13 steps, run #7 a thrashé à max_steps sur toutes les tentatives).
- [x] Décision ouverte (utilisateur) : relancer plus tard (variance du 4B), ou basculer le Coder sur le
  modèle 9B (REASONING en FAST — plus lent/step, convergence bien plus fiable), ou stopper.

## Verdict Coder Ultra après test live (run #8, 2026-08-15 nuit — coupé sur décision utilisateur)
- Run #8 : l'escalade à signaux a fonctionné à la lettre (it.1 4B → rejet statique → it.2 [⚡ULTRA] →
  rejet statique 5ms+console → it.3 [⚡ULTRA] dernière chance).
- L'Ultra (Ornith-9B no-think) a corrigé 3 classes de bugs en it.2 (compteur rafraîchi DANS la boucle,
  draw() rappelé, canvas pur sans divs) — mais a laissé le délai 5 ms et son rythme est rédhibitoire :
  3,8 t/s (5x le 4B), méga-blocs de 1800+ tokens qui dépassent le timeout client 600 s → 2 tentatives
  mortes en boucle, ~67 min sur la seule itération 3, run coupé à ~2 h sans conclusion.
- DÉCISION UTILISATEUR : « pas convaincu de l'ultra codeur (trop lourd pour cette tâche) » →
  CODER_ULTRA_CORRECTION=false par défaut (feature conservée en opt-in pour tâches lourdes).
- Leçon consolidée : sur cette classe de tâches, la voie gagnante = 4B + gardes déterministes aux
  feedbacks EXACTS (runs #6 it.2 et boucle Coder 2 ont convergé en 8-13 min ainsi).

## Jalons de l'Itération (cycle F-103 — budgets de guidance + signaux prompt-audit, 2026-08-16)
> P0-bis du plan (case « Linter de prompts + budgets de guidance »). Rationale : la leçon
> consolidée des runs #1 (exceed_context_size_error) / F-57 (15k chars de skills eager par step)
> / #7 (thrash du 4B) désigne la discipline de contexte comme goulot — or RIEN ne bornait la
> taille de la guidance (cliquet additif F-44/F-56/F-65/F-109). Gate déterministe 0-LLM, port
> du CI check deer-flow (production ByteDance).

- [x] F103-1 : Exploration — lecture intégrale de la référence deer-flow
      (scripts/check_agent_guidance.py : tiers root/module/local + chaîne cumulée, sémantique
      incrémentale base/head « au-dessus du hard sans croissance = warning », annotations
      GitHub, exit codes) + du framework prompt-audit Anthropic (~220 l : signaux greppables
      groupe 1a/1c, règle « could the model already know this? », keep-list explicite).
- [x] F103-2 : Mesure à chaud des surfaces réelles — AGENTS.md 20.1 Ko, prompts.py 17.3 Ko,
      skills ≤ 8.3 Ko (max frontend-design-anthropic), chaîne Coder (prompts.py + 4 eager)
      30.7 Ko, densité de pression max 1.6 occ/Ko (coding, devtools-preview).
- [x] F103-3 : scripts/check_agent_guidance.py — port fidèle ADAPTÉ aux surfaces du repo :
      racine AGENTS.md (12/16 Ko soft/hard), module graph_orchestrator/prompts.py (24/32),
      local skills/*/SKILL.md (40/48), CHAÎNE CODER cumulée (80/96) composée dynamiquement
      depuis ALWAYS_SKILLS_CODER (import skills_loader = source de vérité unique, PAS une
      copie — la chaîne suit les futures évolutions du socle eager). Limitation documentée :
      le bloc prompt inline de nodes.py n'est pas mesurable statiquement, hors chaîne.
      Durcissement vs référence : repo sans commit → repli sur non-trackés (deer-flow
      planterait sur `git diff HEAD`).
- [x] F103-4 : Volet prompt-audit (a) en opt-in --audit-signals — AG101 densité de pression
      (seuil 4 occ/Ko, calibré sur l'état réel max ~1.6 = silencieux aujourd'hui, attrape le
      bloat futur) + AG102 hedges agrégés par fichier. CAVEAT systématique dans chaque
      message : la pression est LÉGITIME pour nos 4B/9B sous-déclencheurs — signaux pensés
      pour modèles très littéraux, jugement requis. Décision de cadrage : le volet LLM-jugé
      complet (audit/suppression) est REPORTÉ — la pression est load-bearing sur petits
      modèles, un audit de suppression prématuré ferait des dégâts (le doc Anthropic
      lui-même : « Older, less steerable models genuinely needed forcefulness »).
- [x] F103-5 : tests/test_agent_guidance.py — 37 tests (normalisation CRLF 3, tiers 4,
      guidance_paths 1, sémantique budget 7 branches, chaîne 3, analyze 8, signaux 5,
      exit codes 4 avec git init réel en basetemp, intégration repo réel read-only 2).
      2 bugs d'implémentation attrapés pendant le dev : budget chaîne mathématiquement
      impossible (chaque fichier sous son soft → somme max 64 Ko < hard 96 : recomposé
      2 skills + module) + mkdir .git factice (git ls-files échoue sans vrai init).
- [x] F103-6 : Validation — 37/37 PASS, py_compile OK, suite complète **1110 passed /
      0 failed / 1 skipped** (0 régression). Run LIVE : mode local = 29 surfaces,
      1 error AG001 AGENTS.md 20 433 o > hard 16 384 (VRAI SIGNAL — croissance continue
      du fichier plat, candidate F-107 ; réduction NON exécutée, décision utilisateur) ;
      mode incrémental --base-ref origin/main = 0 error 0 warning exit 0 (sémantique
      d'adoption prouvée : la gate ne bloque pas les PR qui ne font pas grossir) ;
      --audit-signals = 1 warning hedge (frontend-design-anthropic, « try to »).
- [x] F103-7 : État disque synchronisé (feature_list F-103 completed, contract critères
      381-385, plan case cochée + note FAIT, README §Guardrails, ce bloc, événements
      DuckDB run_id f-103).
- [x] F103-8 (follow-up user, même PR) : **AGENTS.md réduit sous budget** — 22 308 → 13 583
      octets normalisés (13,3 Ko < hard 16 384 ; ~1,3 Ko au-dessus du soft 12 288 = warning
      non bloquant assumé, marge de croissance ~2,7 Ko). Méthode : TOUTES les règles et
      interdictions conservées (INTERDICTION DE SUPPRESSION, or git, bootstrap/sync/erreurs,
      canaux DuckDB, piège filePath, tiering) ; compressés les récits historiques et détails
      dupliqués ailleurs (métriques Golden Run, descriptions Static Tester/vision_callback →
      couvertes par README §Node Graph + feature_list) ; blocs de format JSON/MD → signatures
      compactes ; numérotation §1-11 préservée (références croisées §7/§8 intactes).
      + section 1-bis AJOUTÉE (demande user) : anti-confusion Usine (ce dépôt) ≠ Produits
      de l'Usine (runs/) + distinction de contexte AGENTS.md (assistant dev) vs prompts.py+skills
      (runtime nœuds). Gate mode local APRÈS réduction : 0 error, 1 warning soft, exit 0.

## Jalons de l'Itération (cycle F-105 — password managers + redaction secrets, 2026-08-16)
> P8-bis du plan (case « Durcissement sécurité : groupe 10 password managers + redaction
> secrets »). Suite directe du merge PR #80 (F-103). Sécurité défensive déterministe :
> l'agent ne doit JAMAIS lire un coffre de mots de passe, ni exfiltrer un secret dans une
> trace. Miroir du pattern F-38 (denylist + tests paramétrés), 0 LLM, 0 risque runtime.

- [x] F105-1 : Exploration — lecture du groupe 10 davidondrej (dangerous-patterns.txt
      l.54-65 : doctrine « op/pass = mots courants → vrais subcommands seulement »),
      test-guard.sh (~42 block PM + ~19 allow), section Redact mattpocock, bash_guard.py
      F-38 (66 tests), feedback_utils.py (point unique de passage vers le LLM F-21).
- [x] F105-2 : (a) bash_guard.py +9 patterns transpilés — CLIs distinctifs d'office ;
      `pass` en position de commande STRICTE (`_SEP_CMD` début/;&| + re.M multiligne) ;
      `op` avec ses 10 vrais subcommands ; security keychain (flags gérés) ; .app ;
      ~/.password-store (~/$HOME/${HOME}//Users/x) ; open -a PM ; brew uninstall PM ;
      gpg --export-secret-key(s|subkeys). Message pédagogique étendu aux coffres.
- [x] F105-3 : (b) module redaction.py — redact_secrets() : blocs PEM privés (entier),
      URL creds (user conservé), préfixes réservés (sk-/ghp-/github_pat_/xox[baprs]-/
      AKIA/AIza/JWT eyJ), Bearer/Authorization, affectations nommées (nom SUFFIXE
      d'identifiant OK : PGPASSWORD/OS_PASSWORD ; nom + séparateur + quotes conservés).
      POLITIQUE ANTI-CORRUPTION fail-open : valeurs code-like (a.b, f(), [0], ${x},
      $VAR, %VAR%, <...>, <8 chars) JAMAIS redactées ; idempotent.
- [x] F105-4 : Branchement feedback_utils.truncate_output (Testeur→Judge, Judge→Coder,
      bash_command) AVANT l'early-return court ; doctrine F-21 (lecture seule, DuckDB
      intégral pour audit). Config redaction_enabled + REDACTION_ENABLED dans
      .env.example ET .env local (règle AGENTS.md §7).
- [x] F105-5 : Tests — test_bash_guard.py étendu (66 → 135 : 69 nouveaux groupe 10,
      tous les faux positifs de la réf couverts) + test_redaction.py (19). 2 bugs de
      design attrapés à la relecture : \bpassword ne matchait pas PGPASSWORD (préfixe
      identifiant ajouté) et valeur dotted ya29.* exclue par l'anti-corruption (test
      corrigé sur valeur dotless — fail-open assumé).
- [x] F105-6 : Validation — py_compile OK, suite complète **1198 passed / 0 failed /
      1 skipped** (1110 baseline + 88 nouveaux, 0 régression). État disque synchronisé
      (feature_list F-105 completed, contract critères 386-390, plan case cochée, ce
      bloc, README §Guardrails, événements DuckDB run_id f-105).

## Jalons de l'Itération (F-126 — durcissements Coder post-mortem run 1552)

> Post-mortem run 2026-08-19_1552 (Tetris) : « Coder crash » après 3 retries
> (~93 min, 98 steps). Bug local `merge()` (ROWS itéré sur matrice shape 2-4
> lignes → TypeError au 1er posage) jamais trouvé : le 4B réécrivait TOUT
> index.html (3 réécritures ~15 min/passe) → contexte inondé → 400
> exceed_context_size (54 115 > n_ctx 49 152) ; gate screenshot F-109 faux
> négatif (scan mémoire purgée) ; erreurs console sans localisation. Décision
> utilisateur : « Go » sur les 4 recommandations R1-R4 (branche
> fix/coder-hardening-run1552, base fix/architect-skillfinder-failopen).

- [x] F126-1 (R1) : garde anti-réécriture totale dans `tools.write_file` — REFUS
      d'écraser un fichier EXISTANT de >100 lignes (message pédagogique →
      read_file ciblé + search_replace/multi_replace ; création libre ; seuil
      CODER_WRITEFILE_MAX_LINES, 0=off ; fail-open OSError). Settings
      `coder_writefile_max_lines` (config.py). Prompt : description write_file
      mise à jour (OUTILS DISPONIBLES) + règle « erreur console = bug LOCAL »
      dans le RAPPEL récence.
- [x] F126-2 (R2) : FAST_CONTEXT 49152→65536 + FAST_KV_QUANT=q8_0 dans .env et
      .env.example (65536@q8_0 = MOINS de VRAM KV que 49152@f16 sur RTX 3060
      6 Go) + docs/LLAMA_SERVER_FLAGS.md §3.5 mis à jour (leçon run 1552).
- [x] F126-3 (R3) : preuve durable de screenshot — `tools._SCREENSHOT_PROOF`
      (mark_screenshot_taken/screenshot_was_taken/reset_screenshot_proof),
      marquée à l'EXÉCUTION réelle par vision_callback (_mark_screenshot_proof :
      image PIL ou texte sans signature d'échec ; take_snapshot exclu). Gate
      nodes.py : flag durable PRIMAIRE, scan agent.memory.steps conservé en
      fallback. Reset au même endroit que reset_visual_audit (traverse les
      retries).
- [x] F126-4 (R4) : enrichissement console — wrapper _ConsoleEnrichingTool +
      wrap_console_enrichment (vision_callback) : après list_console_messages,
      chaque [error] msgid (max 4) est détaillé via get_console_message →
      stack frames (max 8) + directive read_file(path, offset=ligne-8,
      limit=20) + search_replace chirurgical + avertissement anti-réécriture.
      Branché dans execute_coder_node. Fail-open total.
- [x] F126-5 : Tests — nouveau tests/test_f126_run1552_hardening.py (23 verts :
      garde write_file 5, config 3, preuve screenshot 6 dont 2 via
      run_with_retry en conditions purgées, enrichment console 8) + entrées
      feature_list F-125 (rattrapage session précédente) et F-126 +
      check_agent_guidance 0 erreur. Validation E2E : à confirmer au prochain
      run Tetris.

## Jalons de l'Itération (post-mortem run 2026-08-19_2104 — validation F-126 à chaud)

> Run Tetris FRESH_START interrompu à ~72 min sur décision utilisateur (dernière
> tentative CODER ULTRA stérile). Verdict central : **livrable sain, Testers
> fautifs** — 2 rejets sur verdicts fantômes (max-steps → prose → rescue →
> « failure ») alors que le jeu tourne (0 erreur console, vérifié en direct).

- [x] F-126 VALIDÉ en production : R1 zéro réécriture totale (itération 2 =
      read_file + search_replace chirurgical, 7 steps/5 min) ; R2 ctx 65536 +
      KV q8_0 sans overflow (10,9 M tokens in vs 39 M au run 1552) ; R3/R4
      sans stress (checklists passées, 0 erreur console à enrichir).
- [x] Constat Tester (cause racine des 2 rejets) : budget 8/6 steps brûlé en
      découverte d'UI (ID canvas) + erreurs d'outils propres (-32602 enum,
      NameError evaluate_script) → final_answer en prose au max-steps →
      verdict « failure » générique → fail-closed. AUCUN bug réel identifié.
- [x] Correctif immédiat appliqué : TESTER_MAX_STEPS 8 → 16 (.env + .env.example,
      prompt tester auto-adaptatif via settings).
- [x] F-127 appliqué (feu vert utilisateur « go ») : TARGETED_MAX_STEPS 6 → 10 ;
      REASONING_NO_THINK_NGL=99 dans .env + .env.example (serveur Tester/Ultra en
      full offload, était bridé à 7,7 t/s en auto-fit) ; `_tester_max_steps_fallback`
      n'attribute plus les erreurs d'OUTILS du Tester (MCP -32602, NameError sandbox,
      probe null) à l'app — les « Uncaught » de l'app restent des FAIL (règle ancrée,
      testée) ; helper `discover_ui()` (inventaire canvas/boutons/inputs en 1 appel,
      en tête des helpers DevTools, Coder + Tester) ; `_sanitize_console_kwargs` filtre
      l'enum `types` avant l'appel MCP ; wrapper console enrichi branché aussi sur le
      Tester. CODER ULTRA : maintenu + accéléré par NGL=99, statut à réévaluer au
      prochain E2E. Tests : tests/test_f127_tester_hardening.py (16 verts) +
      factory devtools 5→6 helpers.
- [x] CODER ULTRA (footnote) : modèle trop lourd à 7,7 t/s — 3 tentatives mortes
      (cap 1200 s, stall step 26, tuée). Décision modèle à revoir à froid.

## Jalons de l'Itération (run 2026-08-20_0901 — gel au chargement, F-128 rattrapé + F-129)

> Relance E2E Tetris (suite note fin de session 02h : « tout est prêt, rien
> d'autre à faire avant »). FRESH_START=1 — pas de reprise iter 2 du run coupé
> 000845 (livrable iter 1 déjà sain ; reprendre = nourrir le failure mode
> connu des gros search_replace sur du déjà-fixé). Run en cours PENDANT ce
> cycle : les fixes ci-dessous s'appliquent au PROCHAIN run (code chargé en
> mémoire au démarrage du process).

- [x] Diagnostic en direct (question utilisateur « pas d'affichage dans le
      chrome, ça mouline ») : reproduction indépendante (Chrome session
      assistant : Navigation timeout) + exécution du JS extrait sous watchdog
      Node `vm` (debug/repro_freeze_tetris.js) + instrumentation des boucles
      (repro_freeze_tetris2.js) → **BOUCLE INFINIE ligne 299** :
      `do { piece = random } while (bag.includes(piece))` dans
      `getRandomPiece()` — le sac 7-bag rechargé à 14 pièces (2×7 types)
      contient TOUS les types après 2 pops → le rejet est éternel → le thread
      principal gèle avant l'événement load (spinner infini, 0 erreur console
      car un gel est SILENCIEUX, tous les appels CDP renderer timeout).
- [x] Constat pipeline : le nudge F-125 n'a PAS détecté ce cas — (a) marqueur
      "timed out" ne matche pas « Navigation timeout », (b) les commandes
      saines du browser-process (console vide) remettent son compteur à zéro
      → jamais 3 erreurs consécutives. Le Coder a brûlé ~15 steps (10→190 s
      chacune) à retenter navigate/new_page/screenshot sans jamais relire son
      code. Gate F-109 (preuve screenshot) = fail-closed garanti : aucune
      fausse approbation possible sur une page gelée.
- [x] F-128 RATTRAPAGE (implémenté hier 00h08, validé en prod au run 000845,
      jamais synchronisé sur disque — fin de session 02h) : feature_list
      F-128 + contract C450 ajoutés.
- [x] F-129 NOUVEAU (proposition utilisateur « un prompt qui dit que si une
      page html timeout risque de boucle dans un js ? » — doctrine F-33 :
      prompt + garde logicielle) : (1) nudge `_build_nav_freeze_nudge` —
      directive IMMÉDIATE dès « Navigation timeout » (un timeout de
      navigation sur fichier LOCAL est TOUJOURS pathologique) : diagnostic
      boucle while/do-while jamais fausse + read_file + search_replace +
      re-navigate pour CONFIRMER ; actif Coder ET Tester ; (2) fix marqueur
      F-125 (« Navigation timeout » compte désormais dans les erreurs
      protocole) ; (3) ligne ⚠️ prompt Coder + règle 4-bis prompt Tester
      (conclure failure « page gelée » immédiatement). Tests : 9 nouveaux
      TestNavFreezeNudge (30/30 fichier, 92 passed suites voisines basetemp
      dédié) ; gate F-103 : 29 surfaces, 0 erreur, 0 warning. Contract C451-
      C452, feature_list F-129.
- [ ] Issue du run en cours : verdict final (Coder era pre-F-129 sur page
      gelée → issue attendue entre correction par relecture fortuite,
      échec propre fail-closed, ou burn-out des tentatives) → post-mortem.

## Jalons de l'Itération (update références 2026-08-20)

- [x] Exécution de `update_references.py` sur les 51 dépôts de références.
- [x] Analyse de `update_report.md` et extraction des nouveautés majeures (Agent Teams, FD3 Protocol, Claude Design Skills, Token Budget, Gatekeeper Context).
- [x] Mise à jour de `feature_list.json` avec les nouvelles fonctionnalités (F-141 à F-143).
- [x] Mise à jour de `plan_usine_logicielle.md` (ajout de la priorité P17 avec les 5 références principales).

## Jalons de l'Itération (cycle F-157 — spike migration Coder pydantic-ai-harness, 2026-08-23)

> Décision user post-analyse (docs/ANALYSE_MIGRATION_HARNESS_CODAGE.md) : « Ok go pour
> pydantic-ai-harness ». Branched `feat/pydantic-harness-coder-spike`. Doc complète en
> local + règle de lecture ajoutée à AGENTS.md ; synthèse liens :
> docs/PYDANTIC_AI_HARNESS_DOC_NOTES.md.

- [x] F157-1 : Phase 1 smoke test provider (debug/pydantic_smoke_provider.py) — 100 %
      PASS (chat, tool-calling Hermes, output_type Pydantic ; même profil OpenAI défaut).
- [x] F157-2 : Phase 2 round 1-2 CodeMode — NO-GO documenté : le 4B écrit
      `with open(...)` au lieu des tools Monty, régénère à l'identique (6 retries,
      logs/spike_pydantic_round2.log) → variante tools natifs.
- [x] F157-3 : Phase 2 round 3 tools natifs — VERDICT GO : Bubble Sort 3 fichiers
      8/8 contrôles, 14 tool calls / 0 retry, 131.6k/7.4k tokens, 593 s
      (logs/spike_pydantic_round3.log, debug/run_coder_pydantic.py).
- [x] F157-4 : Bug préexistant main découvert par l'A/B (`select_skills` NameError,
      nodes.py repli skills — invisible E2E) : corrigé (`build_skills_block` + import).
- [x] F157-5 : Baseline A/B smolagents (logs/spike_smolagents_baseline2.log) — GO
      en cours au moment de l'écriture ; reporter les métriques dans
      ANALYSE_MIGRATION_HARNESS_CODAGE.md §9.3.
- [ ] F157-6 : PR du spike (scripts + fix + docs + AGENTS.md) → review Kilo.
- [ ] F157-7 (phase 3, après merge) : portage gardes (hooks/capabilities), MCP
      vision (PlaywrightBrowser vs DevTools MCP), CoderOutput output_type, Web Tester.

## Jalons de l'Itération (cycle maintenance F-98/F-123 — llama.cpp + paquets Python, 2026-08-23)

> Branche `chore/dep-upgrade-2026-08-23`. Événement DuckDB #2392. Rapport versions :
> `logs/upgrade_report_20260823_120602.md` (gitignoré, régénérable).

- [x] llama.cpp nightly b10586 → b10590 (vendor CUDA 13.3, ~537 Mo téléchargés,
      backup `llamacpp-cuda13-b10586.bak` conservé, flags critiques vérifiés au swap).
- [x] Montée paquets Python latest : 16 MAJ + 5 ajouts (stack boto3, nouvelle
      dépendance de litellm 1.98.0). 0 suppression.
- [x] Validation non-régression : MTP baseline 20,85 tok/s ; tests cmd serveur
      8/8 ; pytest complet **1819 passed / 7 skipped, exit 0** (9 min 40).
- [x] Diagnostic spec-mtp ❌ : PRÉ-EXISTANT (log b10586 du 2026-08-22 identique) —
      le GGUF Ornith-1.5 n'embarque pas de couches MTP (`nextn` absentes, contrairement
      à Ornith-1.0-9B-MTP) et `REASONING_SPEC_MTP=false` en prod (VRAM 6 Go). Pas une
      régression b10590 ; action optionnelle : repérer une variante -MTP d'Ornith-1.5.

## Jalons de l'Itération (re-validation E2E F164-6 — intégrité enregistrement verdicts, 2026-08-24)

> Post-merge PR #117 (F-165). Run E2E `bubble-sort-multifile-v6` démarré 08:57:05
> (`logs/run-20260824_085705-coding-f165-revalidation.log`,
> `runs/2026-08-24_0857_bubble_sort_multifile_v6/`). Branche doc :
> `docs/golden-run-revalidation`. Monitoring 10 min : log + livrables + bases.

- [x] Prérequis : GGUF Ornith-1.5 remplacé (téléchargement 08:49→08:56, ancien en
      backup `_Ornith-1.5-9B-Q4_K_M.gguf`) ; premier run AVEC Ornith-1.5.
- [x] Pipeline amont sain : Routeur HTML, 8 leçons injectées, plan Architect reçu.
- [x] **GOLDEN RUN #19 INVALIDÉ (double constat, 2026-08-24)** :
      (a) non-reproductible — retest même tâche : itération 1 en ÉCHEC (40 steps
      `coder_max_steps`, 7 audits visuels KO « board vide », garde fail-closed,
      itération 2 lancée ~09:37) vs 21 steps/approbation du 18/08. Cause candidate :
      draft Ornith-1.5 3× plus court (intentions sans valeurs) → bugs mécaniques
      du 4B : hauteur `(v/100)*100%` sans hauteur parent → board vide ;
      `var(--*)` consommées sans `:root` → thème sombre mort.
      (b) **bug intrinsèque du livrable golden** (test navigateur 2026-08-24,
      serveur 8798 + mesure) : le compteur « comparaisons » compte les ÉCHANGES —
      `comparisonCount++` dans le `if (arr[i] > arr[i+1])` (`script.js:77`) ;
      tableau 30 éléments : compteur final **228** (= swaps) vs **551
      comparaisons réelles**. Cahier des charges violé ; Judge du 18/08 avait
      approuvé → **fausse approbation historique** (famille F164-6). Écart
      secondaire : `.sorted` appliqué seulement à la fin (pas de vert progressif).
      Le reste tient : 30 barres au chargement, tri croissant, thème sombre réel.
      Noté dans AGENTS.md §10.
- [x] Incident DuckDB pendant le run : `run_event` régressé 2972→2970 à 09:23
      (WAL consommé sans rejeu) — perte de 2 événements assistant (#3165 `run_start`
      08:51 + `rch` 09:18). Lecture fiable = copie+rejeu WAL ; **règle : aucune
      écriture assistant dans event_stream.duckdb pendant un run**.
- [x] KG `graph_orchestrator.db` = DuckDB, connexion rw longue tenue par le run
      (`knowledge_graph.py:55`) → verrou exclusif, illisible de l'extérieur pendant
      le run (analyse claims/réfutations/verdicts reportée à la fin).
- [x] Fin de run (12:57, ~4 h) : **ÉCHEC PROPRE fail-closed** — `"status":
      "failure", "reason": "Coder crash"`, checkpoint CONSERVÉ pour reprise,
      pool navigateur shutdown, exit 0. 3 itérations Coder épuisées sur le
      même piège (`\n` littéraux search_replace + doublon startBtn).
- [x] **VERDICT RE-VALIDATION F164-6 (partiel)** :
      ✅ TIENT — verdicts Judge intègres quand le Judge tourne (25 verdicts
      historiques sous run_id `coding_d72dc8e…` : zéro doublon, feedbacks
      complets non tronqués, format fidèle) ; claim #256 non dupliqué
      (dedup_key unique), contenu complet ; checkpoint riche et fidèle.
      ❌ RESTE À CORRIGER — (1) **claim #256 du 24/08 10:46 MENSONGER** :
      décrit « DOM not updated after each swap, internal sort correct »
      alors que la preuve (console lue par le graphe) est une SyntaxError
      fatale → script jamais exécuté. Ticket fantôme relisable par les
      runs suivants = famille exacte F164-6 (non-ancrage sur preuve).
      (2) **run_id = hash de la TÂCHE, pas de l'exécution** : les 25
      verdicts mélangent 9 jours de runs — impossible d'isoler une
      exécution en base. (3) **Trou d'observabilité Coder** : 4 h de run
      terminé en « Coder crash » → **0 événement** dans `run_event`
      (canal muet tant que Judge/Tester ne passent pas ; échecs d'itération,
      circuit breaker et crash non journalisés).
- [ ] Événement DuckDB de clôture (run terminé, verrous libérés) + PR doc.

### Décision utilisateur validée (2026-08-24, ~10:00) — future F-166

> « Il faut donner l'auto-fixer au Coder et à tous les nœuds qui codent de la
> logique » — doctrine §8.3 « code pur d'abord » confirmée par ce run :
> ~80 steps LLM brûlés sur un fix mécanique (doublon `startBtn` + `\n`
> littéraux dans `search_replace`) qu'un fixer déterministe fait en <1 s.

Périmètre F-166 proposé (à planifier proprement après le run) :
1. **Auto-décodage `\n` dans `search_replace`** (tools.py, garde F-132) :
   l'outil décode lui-même `\n`/`\t` littéraux des old/new_string, réessaie
   le match décodé avant de rejeter — sûreté par recherche de chaîne. Fix
   immédiat du piège observé ×15 dans ce run (step 22 it2 : diagnostic bon,
   encodage seul en cause).
2. **Classe 3 auto-fixer** : `SyntaxError: Identifier 'X' has already been
   declared` (redéclaration même scope) — nécessite parsing de scope (pas
   regex pure), à évaluer.
3. **Branchement F-133 au-delà du Tester** : rendre `apply_known_fixes`
   appelable par le Coder (post-rejet F-132) et tout nœud qui écrit du code
   (Drafter/Architect en durcissement amont du draft).

Pépites déjà minées (vérifiées 2026-08-24 dans `docs/references-audit/
CODE_PUR_ROADMAP.md` — minage 2026-08-20 des 44 projets, clones locaux) :
- **P3-aider** `references/aider/aider/coders/search_replace.py:565`
  `flexible_search_and_replace` — cascade de strategies (exact → strip
  lignes vides → indentation relative `RelativeIndenter` → whitespace-
  tolerant → élision `...` → diff-match-patch par lignes) À BRANCHER EN
  AVAL de F-132 : edit raté pour raison d'encodage/indentation appliqué
  mécaniquement au lieu de coûter un tour LLM. ⚠️ fuzzy SequenceMatcher
  désactivé chez aider (:296) — à ne PAS porter sans garde. Notre
  auto-décodage `\n` (point 1) = préprocesseur de tête de cette cascade.
- **P2-kilocode** `apply_patch.ts:276-323` — après chaque édition : formatage
  + diagnostics de parse INJECTÉS dans l'output de l'outil. Port : check
  syntaxe JS déterministe (`node --check`) après write_file/search_replace
  → la SyntaxError `startBtn` de ce run aurait été détectée à l'écriture
  (09:03), pas 80 steps plus tard.
- **P1-OpenKB** `deck/validator.py:128` — valideur HTML stdlib shift-left
  (self-contained, ids dupliqués, `getElementById('x')` sans `id="x"`).
- P4-deer-flow (repair `\n` fence-aware) : DÉJÀ porté dans F-133 (fichier) ;
  F-166 l'étend aux ARGUMENTS d'outil.
- Bonus second rang : coercition d'args par schéma (open-swe
  `sanitize_tool_inputs.py:24`), repair nom d'outil (kilocode `llm.ts:371`),
  `json_repair` (OpenKB `agent/compiler.py:540`).
