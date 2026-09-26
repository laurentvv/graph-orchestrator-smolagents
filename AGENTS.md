# AGENTS.md — graph-orchestrator-smolagents

> Instructions pour tout agent IA de codage travaillant dans ce dépôt.
> Structure : **bloc commun** (délimité, resynchronisable) + **spécifique projet** (libre).

<!-- BEGIN:agents-commun v1.0 — bloc partagé entre dépôts (agents-kit). Ne pas éditer à la main : resynchroniser via scripts/sync_agents.py -->
<!-- Le script remplace uniquement ce qui se trouve entre les marqueurs BEGIN/END ; tout le contenu spécifique du dépôt est préservé -->

## §1 Environnement

- Machine : **Windows 11**. Shell du dépôt : **Git Bash** *(adapter au §7 si PowerShell 7 — n'utiliser QUE les commandes du shell déclaré)*.
- Python : **`uv` uniquement** — jamais `pip install`, jamais `requirements.txt` (`uv add` / `uv run`).
- Chemins machine : jamais en dur dans le code — passer par la configuration du projet (config.py / .env / section dédiée).
- Contexte long (architecture, leçons détaillées, écosystème) : voir `PROJECT_MEMORY.md` ou `docs/` du dépôt — AGENTS.md reste volontairement court.

## §2 État sur disque = source de vérité

Ne jamais se fier à la seule fenêtre de contexte : elle s'altère, se compresse, s'efface. L'état du travail vit dans **quatre fichiers** (défaut : racine du dépôt ; variantes admises si déclarées au §7 : `.agents/`, `memory-bank/`). À chaque initialisation, plantage ou redémarrage : les lire pour reconstruire son état de façon déterministe.

| Fichier | Rôle | Cycle de vie |
|---|---|---|
| `feature_list.json` | Fonctionnalités **actives** (pending / in_progress) uniquement. | Mis à jour à chaque changement de statut ; les `completed` partent en `feature_list_archive.json` (garder court — lu chaque session). |
| `contract.md` | Contrat de validation : assertions strictes et testables (15-30 critères). | **Figé** avant la première ligne de code ; plus modifiable par le générateur. |
| `progress.md` | Tableau de bord du sprint en cours (objectif + jalons). | Mis à jour à la fin de chaque itération. |
| `log.md` | Journal chronologique **append-only**. | Une entrée au début et à la fin de chaque action. |

**Formats** :

`feature_list.json` — `"status"` ∈ `pending | in_progress | completed` (+ extensions projet autorisées, ex. `awaiting_playtest` — les déclarer au §7) :

```json
{ "features": [ { "id": "F-01", "name": "…", "description": "périmètre technique",
  "status": "pending | in_progress | completed", "dependencies": [] } ] }
```

`log.md` — **budget ~200 caractères par entrée** (le détail va dans le commit) :

```markdown
## [AAAA-MM-JJ] init | Initialisation du workspace et négociation du contrat.md
## [AAAA-MM-JJ] gen  | Écriture du script principal et génération des structures JSON.
## [AAAA-MM-JJ] eval | Échec de la validation du contrat sur le critère 2.
```

`type` ∈ `init | gen | eval | fix | sync | done | err` (+ extensions projet).

**Rotation du log** (budget contexte) : `log.md` ne contient que le mois courant. Au changement de mois (ou au-delà de ~150 Ko), déplacer l'historique vers `docs/journal/log_AAAA-MM[_JJ-JJ].md` — rien n'est effacé, l'archive reste grepable. **Au bootstrap : ne lire que `log.md` (court) ; les archives uniquement par `grep` ciblé.** *Variante B (à déclarer au §7) : historisation événementielle en base (DuckDB/SQLite) à la place du fichier plat — même discipline, zéro journal .md.*

## §3 Boucle d'exécution

1. **Bootstrap** — vérifier les 4 fichiers ; absents → les créer ; présents → les lire (budget : actives de `feature_list.json`, `progress.md`, `contract.md`, `log.md` en entier). Ne PAS lire les archives sauf `grep` ciblé.
2. **Action** — avant d'exécuter une tâche, écrire la ligne dans `log.md`.
3. **Gate** — une vérification statique en échec **interdit** la synchronisation du ledger (compiler/linter au vert d'abord — ne jamais annoncer « check OK » sans l'avoir lancé).
4. **Synchronisation** — après chaque écriture ou test, mettre à jour le fichier de statut associé.
5. **Erreurs** — en cas d'exception ou d'interruption, l'état valide = dernière entrée du `log.md` + assertions de `progress.md`.

## §4 Git & livraison

- **Jamais de travail ni de push direct sur `main`** : branche `feat/…` ou `fix/…` avant toute modification.
- Une fois la PR soumise : **s'arrêter** (pas de boucle d'attente) ; merge uniquement sur instruction explicite.
- **Jamais `git reset --hard` sur un working tree vivant** — annulation d'un commit de test : `git reset --soft HEAD~1` puis purge ciblée.
- Push uniquement sur demande explicite de l'utilisateur.
- **Checklist avant commit** : tests/linters au vert · aucun secret dans le diff · doc maintenue à jour · ledger synchronisé.

## §5 Sécurité & intégrité

- **Aucun secret** dans le code, les commits, les logs ni l'écran (chemins utilisateur, e-mails, jetons) → env vars / figurants fictifs.
- **Jamais supprimer** les fichiers d'état, bases, archives ou données métier. Toute suppression ambiguë : **reformuler la liste** à l'utilisateur et faire confirmer AVANT d'exécuter.
- **Jamais éteindre/redémarrer/mettre en veille la machine** sans demande formelle explicite.
- **Actions irréversibles ou externes** (publication, upload, écriture PROD, envoi de messages) : générer d'abord les artefacts de contrôle, puis attendre l'accord explicite dans le chat.

## §6 Vérité & validation

- « Vérifié » = **exécuté réellement** (exit 0) ou **inspecté visuellement** (capture/rendu regardés) — jamais déduit du code, des intentions ou des logs.
- Toute affirmation factuelle (chiffre, couleur, présence d'un asset) est étayée par une mesure ou une capture conservée en preuve.
- Après une correction : re-valider par le **chemin complet réel**, pas par un harnais qui le court-circuite.
- Documentation : toute évolution de comportement → mettre à jour la doc maintenue du dépôt avant de clore la tâche.

<!-- END:agents-commun -->

---

## §7 Spécifique projet

### Mission / périmètre

**L'Usine** : graphe multi-agents LLM **GPU-local** qui fabrique des livrables de code (`uv run agent_graph.py`, chaîne PromptRefiner → Router → Architect → Coder → Linter → Static Tester → Tester+Security → Judge, max 3 itérations, Escalation si circuit breaker). GGUF via llama-server spawné (DSPy) : `fast_model` Qwen3.5-4B (Coder, Router) / `reasoning_model` Ornith-1.0-9B (le reste), tous multimodaux.

### Emplacements déclarés (écarts au commun)

- **Variante B (historisation événementielle)** — déclarée : le journal vit en **DuckDB** (`data/event_stream.duckdb`, table `run_event`), PAS dans un fichier plat. L'ancien log.md a été supprimé le 2026-08-14 (F-106), 199 événements récupérés en base. **Ne jamais recréer un journal `.md` ni y appender d'événement.** Écriture : outil `log_event(event_type, details)` côté graphe, CLI `uv run python scripts/log_event.py <type> "<msg>"` côté assistant — LE geste de fin de cycle. Lecture post-mortem : requêtes DuckDB directes.
- Ledger : racine (`feature_list.json`, `contract.md`, `progress.md`). Bases `data/` (DuckDB, SQLite) intangibles.
- Shell : Git Bash · `uv` · modèles dans `models/` (`powershell .\scripts\download_models.ps1`).

### Périmètre usine ≠ produits (NE JAMAIS confondre)

1. **L'usine** (ce que TU maintiens) : `graph_orchestrator/`, `testers/`, `tests/`, `scripts/`, `skills/`, `debug/`, `prompts/`, fichiers d'état, `data/` — tout cycle dev s'applique À CE NIVEAU.
2. **Les livrables** (ce que l'usine fabrique) : `runs/<dated>_<slug>/` (gitignorés). Un bug dans un livrable = **symptôme du comportement d'un nœud** : diagnostiquer et corriger L'USINE, jamais « réparer » un livrable en place (sauf validation/debug explicite). Les commits ne concernent JAMAIS `runs/`.
- **Contexte** : ce fichier guide l'assistant de dev ; il n'est PAS injecté aux nœuds LLM pendant les runs (la guidance runtime vit dans `graph_orchestrator/prompts.py` + `skills/`, budgétée par le gate F-103 `scripts/check_agent_guidance.py`).

### Commandes clés

```bash
uv run python scripts/log_event.py <type> "<msg>"     # journal d'événement (fin de cycle)
uv run python debug/run_<noeud>.py                    # isolation d'un nœud (0 mock, secondes) AVANT tout E2E
uv run python scripts/run_analyzer.py                 # meta-analyste après un run E2E
uv run python scripts/refactor_skills.py              # découpe les SKILL.md > 80 lignes (F-92)
uv run python scripts/update_llamacpp.py              # veille llama.cpp (check seul ; --apply = swap + backup .bak)
```

### Workflow de test & amélioration

- **E2E** : prompt de `references/Prompt-Vault/` (clone externe `laurentvv/Prompt-Vault` gitignoré — tout ajout : commité dans le clone ET reporté en copie trackée `prompts/`) → `tasks.json` (`coding.content`) → `WORKFLOW_MODE=coding` → `uv run agent_graph.py` (30-40 min GPU : valider d'abord en isolation). Valider le graphe avec **Bubble_Sort_Visualizer**. Toute modif de `.env.example` → reporter dans `.env` local.
- **Audits séquentiels** : `AUDIT_PARALLEL=false` (Tester PUIS Security, sinon saturation VRAM).
- **Piège `filePath` screenshots (F-50/F-90)** : le Coder appelle `take_screenshot(filePath=…)` → rejeté par chrome-devtools-mcp `--isolated` → boucle. `vision_callback.py` strippe `filePath`. Si la boucle revient : grep `Access denied`.
- **Meta-analyste (F-61)** : exécution autonome par l'assistant, analyse, **validation humaine obligatoire** avant de durcir prompts/skills.
- **Golden runs** : `debug/reference_run_*` (runs historiques de référence). **Maintenance deps (F-98)** : `uv lock --upgrade && uv sync` → pytest → run d'isolation → PR dédiée ; jamais `--apply` llama.cpp sans validation post-swap (`debug/test_mtp_spec.py --only reasoning`).

### Invariants métier (à ne jamais casser)

- **INTERDICTION DE SUPPRESSION** : jamais supprimer/vider `progress.md`, `feature_list.json`, `contract.md`, ni altérer les bases `data/` — même si l'utilisateur demande un « full run de 0 » : ce sont la mémoire d'agent et l'historique d'exécution.
- README mis à jour à chaque nouvelle fonctionnalité importante, avant de clore la tâche.
- Kilo Code Review retirée côté projet jumeau (2026-09-03, parsing GDScript impossible) — ici la revue d'agent reste applicable : PR soumise → on s'arrête (cf. commun §4).

### Pièges & leçons (format daté)

- **[2026-08-14] zéro journal plat** — F-106 : la suppression de l'ancien log.md s'est accompagnée d'une récupération INTÉGRALE en base : historique consultable (`git log -p --follow -- log.md`), ré-importable (`scripts/recover_log_history.py`).
- **[2026-08-18] leçon des golden runs** — le 4B suit le plan à la lettre : un prompt/draft sain vaut mieux que des corrections aval (run #19 : 100 % conforme en 1 itération).
- **Amélioration continue** — jamais modifier les règles à l'aveugle : résumé + solution proposée, feu vert humain d'abord.

### Renvois

- `README.md` (§ Node Graph & Data Flow) · `docs/NODES_AND_SKILLS.md` (ce que voit chaque agent) · `docs/LLAMA_SERVER_FLAGS.md` (AVANT de changer `<PREFIX>_*` du `.env`) · `debug/isolation/README.md` (convention d'isolation).
