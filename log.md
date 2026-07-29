# Journal d'Exécution (Append-Only)

## 🔧 INFOS À SAVOIR (infra & commandes)

### Serveurs Ollama
- **Distant** : `10.201.12.50:11434` — 16 cœurs physiques, 64 Go RAM. Héberge le
  modèle FAST (Coder). Peut être instable (l'inférence timeout intermittemment
  bien que `/api/tags` réponde toujours). Robustesse `LLM_TIMEOUT_S` ajoutée.
- **Localhost** : `127.0.0.1:11434` — héberge le modèle de RAISONNEMENT (Gemma4)
  + fallback stable pour le FAST si le distant est down.

### Qui gère quoi
- **Les pulls et créations de modèles sur le DISTANT sont gérés par l'utilisateur**
  (accès direct au serveur 10.201.12.50). L'agent n'a accès qu'à l'API Ollama.
  Pour viser le distant depuis la CLI ollama locale : `OLLAMA_HOST=10.201.12.50:11434`.

### Commandes de gestion des modèles (sur le distant, par l'utilisateur)
```bash
# Pull d'un modèle GGUF depuis HuggingFace
ollama pull hf.co/owao/Nanbeige4.2-3B-GGUF

# Créer un modèle optimisé (grand contexte + system prompt) depuis un Modelfile
ollama create nanbeige-bigctx -f docs/Modelfile.nanbeige-bigctx

# Lister / voir les modèles
ollama list
ollama ps   # modèles chargés en RAM + leur CONTEXT

# Voir les paramètres appliqués
curl http://10.201.12.50:11434/api/show -d '{"name":"nanbeige-bigctx"}'
```

### Modelfiles versionnés dans le repo (docs/)
- `docs/Modelfile.qwen-3.5-bigctx` — qwen3.5:4b + num_ctx 32768 (modèle FAST actuel)
- `docs/Modelfile.nanbeige-bigctx` — Nanbeige4.2-3B (candidat Coder, spécialisé code+agent)
- RÈGLE : ne PAS mettre `use_mlock` (provoque "unexpected EOF" sur Ollama 0.32).
  La syntaxe `mlock` moderne n'est pas reconnue non plus. Avec 64 Go RAM, inutile.

### Paramètres modèle FAST recommandés
- `num_ctx 32768` (le Coder accumule l'historique des tools ; trop petit = corruption)
- `num_predict 12000` (un fichier complet = 2-4k tokens ; aussi piloté par FAST_MAX_TOKENS)
- `num_thread 16` (cœurs physiques)
- System prompt "développeur expert et concis" (dans le Modelfile)

## [2026-07-29] init | Initialisation du workspace et création de agent.md
## [2026-07-29] gen  | Création des fichiers feature_list.json, contract.md, progress.md et log.md
## [2026-07-29] init | Exploration du codebase (tasks.json, .env, config, workflows, nodes, dspy_nodes, models, tools, knowledge_graph, skills)
## [2026-07-29] cfg  | tasks.json : prompt T004 → landing page premium "Nimbus" (HTML5/CSS3/JS vanilla, responsive, landing_page/). Backup KG + reset.
## [2026-07-29] fix  | test_context7.py : @context7/mcp (404 npm) → @upstash/context7-mcp
## [2026-07-29] fix  | nodes.py : marquage # DEPRECATED des doublons router/judge (versions dspy_nodes utilisées par le workflow coding)
## [2026-07-29] fix  | workflows.py : flushing stdout temps-réel (line_buffering) pour observabilité en contexte non-TTY
## [2026-07-29] run1 | Run #1 bloqué : Router figé (endpoint distant 10.201.12.50 sans inférence). FAST basculé sur localhost.
## [2026-07-29] run2 | Run #2 (qwen3.5:4b local) : Router+Architect OK, Coder échoue (0 fichier écrit, boucle list_directory, max_steps=10 trop bas, parsing échoué)
## [2026-07-29] fix  | nodes.py : réécriture execute_coder_node (max_steps 24, prompt structuré write_file prioritaire, suppression pollution chemins SKILL.md)
## [2026-07-29] rch  | Étude références (crush/openfox/nanocode) : garde anti-vide = gap à inventer, loop detection crush, séparation planner/builder openfox
## [2026-07-29] feat | skills/file-creation/SKILL.md (nouveau) : enseigne le bon usage de write_file
## [2026-07-29] feat | skills/frontend-design/SKILL.md (nouveau) : design pro HTML5/CSS3
## [2026-07-29] fix  | tools.py : write_file garde anti-contenu-vide + anti-placeholder (feedback pédagogique au modèle)
## [2026-07-29] feat | skills_loader.py : routage nœud→skills en 2 couches (socle statique + détection dynamique). Coder injecte le contenu des skills ciblés.
## [2026-07-29] run3 | Run #3 : Coder écrit du vrai contenu MAIS HTML corrompu (garbage JSON échappé, petit modèle + contenu long). Contexte explose (45k tokens).
## [2026-07-29] run4 | Run #4 : HTML écrit (2588 chars) MAIS tronqué en plein CSS (pas de </html>). Cause : build_fast_model sans max_tokens.
## [2026-07-29] fix  | config.py + nodes.py : FAST_MAX_TOKENS=12000 (anti-troncature génération)
## [2026-07-29] cfg  | Distant rétabli + Modelfile qwen-3.5-bigctx créé (num_ctx 32768, num_predict 12000, num_thread 16, system prompt dev). use_mlock retiré (EOF error).
## [2026-07-29] fix  | robustesse : LLM_TIMEOUT_S=180 (timeout appel LLM sur smolagents + DSPy) — un endpoint muet échoue proprement au lieu de figer
## [2026-07-29] run5 | Run #5 (distant bigctx) : Router figé (distant re-planté après ~3min)
## [2026-07-29] run6 | Run #6 (localhost) : interrompu pour recréer modèle optimisé sur distant
## [2026-07-29] run7 | Run #7 (qwen-3.5-bigctx distant optimisé) : Coder boucle
- Router→HTML ✅. Architect→4 sous-tâches ✅. Skills bien injectés ✅.
- Coder écrit du vrai contenu (non corrompu cette fois — début HTML propre).
- BUG : re-écrit index.html en boucle (1332→3264→1271 chars) sans jamais final_answer.
  Chaque step ~140s (thinking Qwen3.5 + contexte qui gonfle). max_steps=24 = ~56min !
- Run arrêté.

## [2026-07-29] fix | nodes.py : prompt Coder anti-boucle + max_steps 24→12
- Nouveau plan d'action "UNE PASSE UNIQUE" : un write_file par fichier puis final_answer.
- Règle anti-boucle explicite : "NE RE-ÉCRIS JAMAIS un fichier déjà créé", "ne relis pas après write".
- max_steps 24→12 (borne le temps ; 12 couvrent 3-5 fichiers + final_answer).

## [2026-07-29] cfg | Pull Nanbeige4.2-3B-GGUF (candidat Coder spécialisé code+agent)
- owao/Nanbeige4.2-3B-GGUF pullé sur distant (2.6 GB) + Modelfile nanbeige-bigctx créé.
- Profil : tool-calling natif, 63.6 SWE-Bench, spécialisé code+agent au SFT, 256K ctx, EN/ZH.
- docs/Modelfile.nanbeige-bigctx versionné.
- BLOQUANT : Ollama 0.32.5 sur le distant ne supporte PAS l'architecture 'nanbeige'
  (error: unknown model architecture: 'nanbeige'). Nécessite MAJ Ollama >= 0.11.
- DÉCISION : utilisateur met à jour Ollama sur le distant (curl install.sh), puis
  on bascule FAST_MODEL_ID=nanbeige-bigctx après test d'inférence réussi.
- Commande MAJ (Linux distant) : curl -fsSL https://ollama.com/install.sh | sh

## [2026-07-29] cfg | Nanbeige abandonné (prématuré pour stack Ollama)
- Discussion HF #17 : Nanbeige4.2 génère bien des tool calls MAIS llama.cpp (base
  d'Ollama) a un bug de parser qui droppe les <tool_call> avec espace trailing.
- Bilan Nanbeige : 2 problèmes empilés (architecture inconnue Ollama 0.32 + bug
  parser tool-call). Trop prématuré. Garé pour plus tard.
- DÉCISION FINALE : on reste sur qwen-3.5-bigctx (qui marche).

## [2026-07-29] fix | ROOT CAANCE trouvé : distant CPU-only = génération LENTE, pas plantée
- Diagnostic utilisateur via htop : pendant un "timeout", le modèle tourne à 100%
  CPU (génération en cours) — ce n'est PAS une panne, c'est juste long (CPU only).
- Le test calculator répondait en 12-21s car prompt minuscule. Le Coder (gros prompt
  + skills + fichier complet + thinking) prend PLUSIEURS MINUTES légitimement.
- BUG : LLM_TIMEOUT_S=180 coupait la génération en plein milieu → échec (run #8).
- FIX : LLM_TIMEOUT_S 180 → 600 (10 min par appel, tolère une vraie génération CPU).
- Défaut config.py aussi relevé à 600.

## [2026-07-29] run9 | Run #9 (timeout 600s) : figé 10min sur sous-tâche 1/5, 0 fichier
- Timeout corrigé (600s) = plus de coupure. MAIS qwen3.5:4b + thinking + gros prompt
  = génération de 5-10 MIN par fichier en CPU-only. 5 sous-tâches = 30-60min. Inhabitable.
- DÉCOUVERTE : serveur distant MONO-TÂCHE. Pendant la génération du Coder (100% CPU),
  tout autre appel inférence timeout (test "OK" → vide). Pas de parallélisme possible.
- /no_think testé : NE DÉSACTIVE PAS le thinking (Qwen3.5 chat template). Pas un levier.
- Run arrêté.

## [2026-07-29] opt | 3 leviers de vitesse appliqués (rendre le Coder viable)
1. ArchitectSignature : contrainte "1 fichier = 1 sous-tâche, 2-4 MAX" (avant : 5 sous-tâches).
2. skills_loader : socle coder réduit à [file-creation, coding] (avant : +windows-file-mgmt).
   frontend-design condensé (3167→~1500 chars). Moins de tokens injectés à chaque step.
3. FAST_MAX_TOKENS 12000 → 4000 (un fichier ~2000 tok + marge thinking ; avant, le thinking
   divergeait sur 8000 tok = 5-10min/step). Compromis vitesse/qualité.

## [2026-07-29] run10 | Run #10 (3 optims) : Architect→3 sous-tâches ✅, Coder tjrs trop lent
- Architect a bien généré 3 sous-tâches (1/fichier) — optims OK.
- MAIS Coder figé 9min sur sous-tâche 1, 0 fichier. qwen3.5:4b CPU-only tjrs trop lent.
- Le process logiciel est VALIDÉ (tous les nœuds s'enchaînent, directives correctes).
  Le bloquant est purement MATÉRIEL (CPU-only + mono-tâche).

## [2026-07-29] test | Comparatif modèles Coder locaux (tool-calling génération fichier)
- qwen2.5-coder:3b : PAS de tool-calling natif (met l'appel dans content). ❌
- lfm2.5:latest : tool-calling simple OK, MAIS échoue génération fichier (reasoning vide). ❌
- lfm2.5:8b-a1b : idem, 1570 tok de reasoning sans tool_call. ❌
- CONCLUSION : seul qwen3.5:4b fait le tool-calling de génération de fichier correctement
  (prouvé runs #3/#4/#7), mais il est lent en CPU-only. Compromis inévitable.

## [2026-07-29] run11 | Run #11 (localhost qwen-3.5-bigctx) : PROCESS VALIDÉ DE BOUT EN BOUT 🎉
- ✅ Router → HTML. Architect → 3 sous-tâches (1/fichier).
- ✅ Coder écrit index.html (9734 chars) puis appelle final_answer (anti-boucle OK).
- ✅ Tester + Security Reviewer lancés en parallèle (1ère fois qu'on atteint cette phase !).
- ✅ Judge émet un verdict : REJETÉ (HTML tronqué, détecté). Bug sauvé dans DuckDB.
- ✅ Itération 2/3 lancée (Coder corrige en relisant le bug depuis le Knowledge Graph).
- ➡️ LE PLAYBOOK MULTI-AGENT FONCTIONNE : Coder→Audit→Judge→feedback→retry.
- Note qualité : HTML tronqué en fin (FAST_MAX_TOKENS=4000 trop juste pour cette page).
  Compromis vitesse/qualité à ajuster (remonter à 6000 pour la complétude du fichier).
- Process démontré de bout en bout. L'objectif de validation est ATTEINT.

## [2026-07-29] run11 | FIN du run #11 : process OK, mais qualité HTML insuffisante
- Sous-tâche 1 (html-structure-nimbus) rejetée 3x (itérations 1/2/3) → max_iterations.
- DIAGNOSTIC FINAL : le HTML généré est GRAVEMENT corrompu (classes CSS dans attributs
  HTML, balises cassées h2class/p class', SVG illisible, guillemets incohérents).
  Step 4 : "Error parsing tool call: does not contain any JSON blob".
- CAUSE RACINE = CAPACITÉ DU MODÈLE : qwen3.5:4b en mode tool-calling n'arrive pas à
  générer proprement un GROS contenu HTML dans un argument JSON. Plus le contenu grandit,
  plus le modèle s'emmêle avec l'échappement JSON → corruption. C'est une limite du 4B.
- EFFET PERVERS observé : le fichier RÉTRÉCIT à chaque retry (9734→8347→3502 chars) car
  le Coder tente de "finir avant le cutoff" au lieu de compléter.
- CONCLUSION : l'ARCHITECTURE multi-agent fonctionne (boucle complète démontrée). Le
  problème de qualité est un problème de MODÈLE (4B trop petit pour du gros contenu
  JSON inline). Solution = modèle plus gros, OU format de génération alternatif.

## 🎯 BILAN FINAL DE VALIDATION
### ✅ Process logiciel VALIDÉ (architecture multi-agent démontrée)
- Router (DSPy) → classification correcte.
- Architect (DSPy) → plan propre (3 sous-tâches = 1/fichier).
- Coder (smolagents) → appelle write_file puis final_answer (anti-boucle OK).
- Tester (MCP Puppeteer) + Security (DSPy) → audits parallèles déclenchés.
- Judge (DSPy) → verdict booléen, feedback structuré.
- Knowledge Graph (DuckDB) → bugs/refutations tracés avec provenance.
- Boucle de feedback → retry sur rejet, max_iterations=3 anti-boucle-infinie.

### 🔴 Problème de qualité = capacité du modèle (pas du process)
- qwen3.5:4b corrompt les gros contenus JSON inline. Options :
  1. Modèle plus gros (8B+) qui gère mieux le JSON long — mais plus lent en CPU.
  2. Format de génération alternatif : écrire le fichier via plusieurs edit_file
     incrémentaux plutôt qu'un seul write_file massif.
  3. Modèle spécialisé tool-calling + code (Nanbeige4.2 idéal MAIS bloqué par
     Ollama 0.32 — à retester après MAJ Ollama).

### Améliorations code apportées (10+, cf. ce journal)
- Garde anti-contenu-vide write_file, skills ciblés (2 couches), prompt anti-boucle,
  FAST_MAX_TOKENS, LLM_TIMEOUT_S, Architect 1-fichier-1-sous-tâche, flushing stdout,
  Context7 corrigé, doublons router/judge clarifiés, Modelfiles versionnés.

## [2026-07-29] pr | PR #2 créée → Kilo Code Review SUCCESS → MERGED dans main
- Branche feat/coding-workflow-validation → squash merge → main (commit 1ca7a88).
- Kilo Code Review : SUCCESS, merge state CLEAN.
- Branche locale + remote supprimées après merge.

## [2026-07-29] strat | NOUVEAU CAP : résoudre la qualité via GPU + stratégie modèles
- DIAGNOSTIC CONFIRMÉ : le blocage qualité est le modèle Coder (qwen3.5:4b corrompt
  le JSON long), pas le process (validé).
- INFRA DÉCOUVERTE : localhost a un GPU (RTX 3060 Laptop, 6 Go VRAM). Le distant
  est CPU-only (16 cœurs, 64 Go RAM).
- NOUVELLE STRATÉGIE :
  * Coder (besoin lourd, gros contenus) → Gemma4 E4B sur localhost GPU (rapide, costaud).
  * Distant CPU → multi-petits-modèles spécialisés (rôles légers : router, security, etc.).
- Sources à explorer : huggingface.co/models (gguf, <6B, trending) + ollama.com/search?c=tools



## [2026-07-29] audit | Audit des projets references (crush, nanocode, openfox) pour idées Graph Engineering
## [2026-07-29] audit | Lecture approfondie du code source (crush/internal, openfox/src, nanocode)
## [2026-07-29] audit | Ajout des stratégies d'outillage internes d'Antigravity (mes propres capacités) à references_audit.md
## [2026-07-29] audit | Clone du dépôt Aider depuis GitHub et analyse des implémentations de tools (crush, openfox, aider)
## [2026-07-29] audit | Recherche web sur les architectures d'agents open source basées sur les graphes (LangGraph, Code Knowledge Graph) et mise à jour de l'audit
## [2026-07-29] arch | Rédaction de l'architecture Circuit Breaker pour graphes d'états dans circuit_breaker_architecture.md

## [2026-07-29] plan | Planification usine logicielle (cycle SEARCH/REPLACE)
- Étude des docs plan_usine_logicielle.md / circuit_breaker_architecture.md / references_audit.md.
- DÉCISION : cycle focalisé SEARCH/REPLACE (Priorité 1) — résout DIRECTEMENT la
  corruption JSON sans changer le type d'agent. CodeAgent/repo-map = cycles suivants.
  Architect DSPy conservé (la version CodeAgent de nodes.py est du code mort).
- Aider trouvé dans references/aider/ : parser SEARCH/REPLACE + logique tolérante
  (match exact → indentation → ellipses) directement portable.

## [2026-07-29] feat | Outil search_replace tolérant + Mutex par fichier (Priorité 1)
- Nouveau module search_replace_utils.py : portage allégé d'Aider.
  replace_most_similar_chunk (match exact → tolérant indentation → ellipses),
  find_similar_lines (feedback didactique "Did you mean..." en cas d'échec).
- Nouvel outil @tool search_replace dans tools.py : (path, search, replace),
  matching tolérant, garde anti-placeholder, garde anti-effacement, feedback avec
  lignes proches si non trouvé.
- Mutex par fichier (threading.Lock, inspiré openfox) : sérialise les écritures
  concurrentes sur un même fichier (défense ceinture+bretelles).
- Coder équipé (nodes.py) : search_replace ajouté aux tools + prompt adapté
  ("préfère search_replace pour modifier un fichier existant").
- 11 tests unitaires (tests/test_search_replace.py) : 11/11 PASS, y compris le cas
  critique d'indentation tolérante de bout en bout.
- Objectif : éliminer la corruption des gros contenus JSON (le Coder ne génère plus
  qu'un fragment, pas tout le fichier).

## [2026-07-29] fix | Température du Coder : 1.0 (chat créatif) → 0.2 (code)
- DÉCOUVERTE CRITIQUE : le modèle distant qwen-3.5-bigctx héritait de temperature=1.0
  (défaut qwen3.5:4b) + top_p 0.95. Le Coder (smolagents) ne fixait aucune température
  → héritait du 1.0 serveur → choix de tokens aléatoires = cause MAJEURE de corruption
  de la syntaxe HTML/JSON.
- FIX double couche : (1) Modelfile PARAMETER temperature 0.2 (le plus sûr, tous les appels),
  (2) config CODER_TEMPERATURE=0.2 appliqué dans build_fast_model (prioritaire serveur).
- Router/Judge (API native) déjà à 0.0. DSPy déjà à 0.3. Le Coder était le seul orphelin.
- Suite complète : 127 PASS.

## [2026-07-29] pr | PR #3 créée → Kilo review (crash puis relance SUCCESS) → MERGED
- Branche feat/search-replace-edit → squash merge → main (commit e295919).
- Contenu : search_replace + Mutex + température 0.2 + tests (127 PASS) + docs plan.
- Kilo Code Review : 1er run FAILURE (crash Kilo, pas lié à la PR), relance SUCCESS.
- Branche locale + remote supprimées après merge.

## 🎯 RÉPARTITION MODÈLES PAR NŒUD (workflow coding, état actuel)
- Coder/Router/Judge → qwen-3.5-bigctx sur DISTANT CPU (10.201.12.50). temp 0.2.
- Architect/Tester/Security → gemma-4-E4B sur LOCALHOST GPU. temp 0.3 (DSPy).
- Décision : garder cette config pour valider search_replace + température à conditions
  égales. Coder → Gemma4 GPU = évolution future (1 seul modèle en VRAM 6 Go, séquentiel OK).

## [2026-07-30] run12 | RUN FINAL VALIDÉ : HTML PROPRE ET COMPLET 🎉🎉
- Modèle distant recréé avec température 0.2 (vérifié via /api/show).
- Run avec search_replace + température 0.2 sur qwen-3.5-bigctx distant CPU.
- RÉSULTAT DÉCISIF : index.html = 10248 chars / 203 lignes, HTML5 PROPRE ET COMPLET.
  * 0 séquence corrompue \u003c (vs garbage total au run #11).
  * Toutes balises équilibrées : <!DOCTYPE>×1, <html></html>, <head></head>,
    <body></body>, <header></header>, <nav></nav>×2, <main></main>,
    <footer></footer>, <section></section>×5, <div></div>×12.
  * Liens CSS/JS corrects, texte français réel ("Nimbus", "Comment ça marche").
  * Coder finalise par final_answer (anti-boucle OK).
- LE BLOCAGE QUALITÉ EST RÉSOLU. Les 2 leviers combinés (température 0.2 +
  search_replace) ont éliminé la corruption des gros contenus.
- Process complet de bout en bout : Router→Architect→Coder(write_file propre)→
  Tester(MCP)→Judge, avec index.html complet. Validation ATTEINTE.



