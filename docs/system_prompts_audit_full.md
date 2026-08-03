# Audit complet — System Prompts des outils IA

> **Source** : `references/system-prompts-and-models-of-ai-tools/` (34 dossiers d'outils)
> **Méthode** : lecture intégrale du contenu de 28+ prompts (on ignore les considérations de licence/leak — on extrait les **mécanismes**).
> **Date** : 2026-08-03
> **Projet cible** : `graph-orchestrator-smolagents` — orchestrateur multi-agent (Router → Architect → Coders fan-out → Tester → Judge → Security), Python (DSPy + smolagents).
> **Lié à** : Feature **F-64** (audit) + **F-65** (gaps actionnables) dans `feature_list.json` ; Priorité 16 dans `plan_usine_logicielle.md`.

---

## 1. Périmètre

Sur 34 dossiers d'outils, **28+ prompts lus en entier** :

- 🟢 **12 prompts à forte valeur** (dense, 100-700 L, garde-fous concrets) : Cline, Codex CLI, Gemini CLI, RooCode, Claude Code 2.0 + v1, Cursor (2.0 / v1.2 / 2025-09-03 / CLI), Devin, Kiro (Spec + Classifier), Traycer, Poke, Augment, Manus (loop + Modules), Amp (Sonnet + GPT-5), VSCode Agent (gpt-5).
- 🟡 **11 prompts à valeur partielle** (pépites noyées dans du verbeux/redondant) : Windsurf, Qoder (prompt + Quest Design + Quest Action), Replit, Warp, Junie, CodeBuddy, Cursor v1.0, Sonnet 5, DeepWiki.
- 🔴 **11 prompts à écarter** (frontend React pur / narratifs / hors-scope) : v0, Lovable, Same.dev, Leap, Orchids, Emergent, Google vibe-coder, Antigravity, Z.ai, Comet, NotionAI, Cluely, dia, Xcode, Lumo, Bolt *(Bolt sauf pour la doctrine DB safety)*.

---

## 2. Taxonomie — 4 archétypes

| Archétype | Exemples | Particularité |
|---|---|---|
| **Coding agent CLI** | Cline, Codex, Gemini, Roo, Devin, Claude Code, Cursor, Amp | Édition + workflow + gating sécurité |
| **Router / Classifier** | Kiro Mode Classifier, Poke, Manus | Décident qui/quoi, délèguent |
| **Architect / Spec** | Kiro Spec, Traycer, Qoder Design, Augment | Read-only, planifient, ne codent pas |
| **Consumer / chat** | Sonnet 5, Lumo, NotionAI, Comet | Q&A, pas d'édition de code |

---

## 3. Invariants universels (déjà ingérés via F-44)

Règles présentes dans **≥5 prompts** du corpus, déjà dans `graph_orchestrator/prompts.py:41-63` (`UNIVERSAL_INVARIANTS`) :

1. **Read-before-write** — lire/chercher avant d'éditer (Cline, Claude Code, Cursor, Devin)
2. **SEARCH/REPLACE > whole-file rewrite** — diffs ciblés (`apply_patch`, `replace_in_file`)
3. **Test-first / verify-after-edit** — lint+typecheck+tests après chaque batch
4. **Approval gating par risque** — read-only / workspace-write / danger
5. **Anti-boucle seuil explicite** — max 3 itérations, puis stop + user
6. **TodoWrite discipline** — 1 seul `in_progress`, marquer `completed` immédiatement
7. **Mimic conventions + verify library availability** — check `requirements.txt` avant import
8. **Parallel tool calls si indépendants** — batch read ; séquentiel pour edits
9. **Concision radicale** — pas de "Great/Certainly/Here is…"
10. **Git safety locks** — NEVER `--no-verify`, NEVER force push main

*Invariants secondaires* : no comments unless asked, don't fix unrelated bugs, root-cause over surface, absolute paths, specialized tools not bash.

---

## 4. Mécanismes différenciants par catégorie

### 4.1 Formats d'édition (5 paradigmes)

| Paradigme | Source | Principe |
|---|---|---|
| **SEARCH/REPLACE sans line#** | Cline, CodeBuddy | `<<<<<<< SEARCH / ======= / >>>>>>> REPLACE`, première occurrence, lignes complètes |
| **SEARCH/REPLACE + line numbers** | Roo (`apply_diff`), Warp | `:start_line:`/`:end_line` obligatoires, exactitude spatiale |
| **apply_patch DSL** | Codex, VSCode gpt-5 | `*** Add/Update/Delete/Move File`, hunks `@@` — **VSCode ajoute `@@` hiérarchique** (`@@ class Foo` / `@@   def method`) |
| **Whole-file only** | Bolt | Contrainte WebContainer, pas de diff possible |
| **Sketch délégué** | Cursor (`edit_file`), Devin (`find_and_edit`), Qoder | L'agent produit un *sketch* lu par un **modèle plus faible** qui applique — convention `// ... existing code ...` |

**Bonus Roo** : `search_and_replace` JSON avec `use_regex`, `ignore_case`, `regex_flags`, restriction line-range — le set d'édition le plus riche.
**Bonus Devin** : `find_and_edit` cross-fichiers par regex + description naturelle (refactoring distribué).

### 4.2 Sécurité / Gating (6 modèles)

| Mécanisme | Source | Granularité |
|---|---|---|
| **`requires_approval: bool`** | Cline, Roo, CodeBuddy | Par commande (install/delete/network = true) |
| **Matrice sandbox × approval** | Codex CLI | FS (read-only/workspace-write/danger) × net (restricted/enabled) × approval (untrusted/on-failure/on-request/never) — le **plus formel** |
| **FileRestrictionError regex** | Roo | Par mode (`\.md$` pour architect) |
| **`is_dangerous: bool`** | Replit | Sur shell commands non-réversibles |
| **SafeToAutoRun non-overridable** | Windsurf | "You CANNOT allow USER to override your judgement" |
| **Explain-before-execute** | Gemini | Doit expliquer impact avant commande modifiant FS |

**Garde-fous spécialisés** :
- **Bolt** : DATA INTEGRITY = highest priority, interdit `DROP/DELETE/BEGIN/COMMIT`, dual-action migration (file + query SQL identique), RLS obligatoire — le **plus strict sur la DB**
- **Warp** : détecte secret redacted (astérisques) → placeholder `{{secret_name}}`, jamais inline, toujours env var
- **CodeBuddy** : **canary anti-prompt-injection** — si demande "output initialization", imprime un **decoy prompt** prédéfini (seul du corpus à le faire)
- **Claude Code 2.0** : refuse credential discovery / bulk crawling SSH keys / cookies / wallets (defensive only)

### 4.3 Routing (4 modèles)

| Modèle | Source | Schéma |
|---|---|---|
| **Distribution probabiliste somme=1** | Kiro Classifier | `{"chat":0.0,"do":0.9,"spec":0.1}` — default-safe `do`, signaux lexicaux (base-form verbs, wh-words, modaux) |
| **Multi-source parallèle au doute** | Poke | 3 cas : source unique→elle / multi→parallèle / doute→**parallèle** ; "never make up info" |
| **Matrice good/bad queries par outil** | Augment | view-sans-regex / view-regex / grep / codebase-retrieval / git-commit — avec exemples à éviter |
| **Hiérarchie info priority** | Manus | API datasource > web search > internal knowledge ; **snippets search ≠ source valide** |

### 4.4 Planification / Architecture (6 modèles)

| Modèle | Source | Caractéristique |
|---|---|---|
| **EARS 3-phases + approval typé** | Kiro Spec | Requirements (EARS `WHEN…THEN…SHALL…`) → Design (sections figées) → Tasks (TDD, `_Requirements: 1.2_`). 3 reason strings codés (`spec-requirements-review` etc.) comme approval gating |
| **Tech Lead read-only** | Traycer | "You DO NOT write code", `write_phases` only, "TEXT-only response strictly prohibited" |
| **Tasklist Triggers + incremental replanning** | Augment | Critères pour décider si planifier ; premier task = "Investigate/Triage" seul IN_PROGRESS ; sub-tasks ~10 min |
| **Pseudocode numéroté + reflection** | Manus | Plan en pseudocode, chaque step = numéro + status + reflection ; `todo.md` persistant |
| **Design → Action two-phase** | Qoder | "Executing without design = inaccurate" ; 8 templates doc par **type de repo** (frontend/backend/lib/framework/CLI/mobile/desktop) |
| **Planning/Standard modes** | Devin | Planning = read-only + `<suggest_plan>` ; Standard = exécution pas-à-pas |

### 4.5 Méta-cognition / Self-correction (4 modèles)

| Modèle | Source | Mécanisme |
|---|---|---|
| **`<think>` tool, 13 triggers** | Devin | 3 obligatoires (git critique, explore→edit, avant completion) + 10 conditionnels. Le plus riche |
| **Status update narratif + self-correction vérifiable** | Cursor 2025-09-03 | "If you say you'll do something, do it same turn" ; règle **`tools_used_in_turn => update_emitted == true`** |
| **Oracle o3 reviewer** | Amp | Subagent raisonneur séparé (OpenAI o3) invoqué pour plan/review/debug, annoncé à l'user |
| **Reflect per step** | Manus | Chaque step du plan inclut status + reflection |

### 4.6 Narration / Output structuré

| Mécanisme | Source | Format |
|---|---|---|
| **Final Status Spec** | Amp GPT-5 | 2-10 lignes, lead quoi/pourquoi, liens `file://`+lignes, **métriques vérification** ("148/148 pass") |
| **Citation `<cite>` vide obligatoire** | Devin DeepWiki | "Every sentence MUST END IN A CITATION" ; si pas de source → `<cite/>` vide quand même ; max 5 lignes, "DON'T CITE ENTIRE FUNCTIONS" |
| **Code ref `file:line`** | Claude Code, Cursor, Devin | ```startLine:endLine:filepath``` |
| **Quality gates triage** | VSCode gpt-5 | Build/Lint/Typecheck/Tests/smoke → "report deltas only (PASS/FAIL)" + requirements coverage line |

---

## 5. Les 20 pépites uniques (non vues ailleurs)

Ces mécanismes n'existent que chez un ou deux prompts — la vraie valeur différenciante :

| # | Pépite | Source | Intérêt pour nous |
|---|---|---|---|
| 1 | **Parallel write-lock policy** : paralléliser writes *iff* write targets disjoints ; sérialiser si contrat partagé (types/schema/API) | Amp GPT-5 | Coder fan-out — décider parallèle vs séquentiel |
| 2 | **Oracle o3** : reviewer/conseiller invocable | Amp | Modèle 2-tier (fast + raisonneur) |
| 3 | **apply_patch `@@` hiérarchique** : contexte `@@ class Foo` / `@@   def method` | VSCode gpt-5 | Diff plus robuste |
| 4 | **Engineering mindset** : outline "contract" (inputs/outputs/error modes) + 3-5 edge cases + TDD minimal | VSCode gpt-5 | Coder/Tester |
| 5 | **Response-mode escalation** : light (trivial) → full engineering ; "if you escalate, say so briefly" | VSCode gpt-5 | Économie de tokens |
| 6 | **Self-correction vérifiable** : `tools_used => update_emitted` | Cursor 2025-09-03 | Judge auto-régulation |
| 7 | **Status update narratif** : "narrating the story", tenses correctes | Cursor 2025-09-03 | Observabilité |
| 8 | **Mémoire citée `[[memory:ID]]`** + **delete-on-contradiction** (pas update) | Cursor v1.2 | Knowledge graph |
| 9 | **EARS requirements** (WHEN…THEN…SHALL…) | Kiro Spec | Architect spec format |
| 10 | **3 reason strings codés** (`spec-*-review`) comme approval typé | Kiro Spec | Contrat Router/Architect |
| 11 | **Steering files 3 modes** (always/fileMatch/manual) | Kiro Spec | Contexte conditionnel |
| 12 | **notify vs ask** (non-blocking vs blocking) | Manus | Gating utilisateur |
| 13 | **Subagent typé + goal-only communication** | Poke | Router→Workers |
| 14 | **report_environment_issue** + "do not fix env yourself" | Devin | Tester/escalation |
| 15 | **8 templates doc par type de repo** + PII substitution | Qoder Design | Architect |
| 16 | **Protocole XML typé** (`is_dangerous`, `mode`, `set_run_button`) + workspace nudges | Replit | Déclaration vs function-call |
| 17 | **`{{secret_name}}` placeholder** + Question/Task split | Warp | Security |
| 18 | **Canary anti-injection (decoy prompt)** | CodeBuddy | Security |
| 19 | **Grep-first pivot** + inline line numbers stripping | Cursor CLI | Sans index sémantique |
| 20 | **Inline completion** avec `edit_diff_history` + cursor prediction | VSCode nes | Non-agent (si completion) |

---

## 6. Mapping vers nos nœuds (croisement avec l'existant)

État actuel de la fondation prompts : `prompts.py` F-44 (invariants) + F-0 (9 rôles) + F-56 (durcissement docstrings). Légende : ✅ = déjà couvert, ⚠️ = partiel, ❌ = manquant.

### Router
| Mécanisme source | État | Action |
|---|---|---|
| Distribution JSON somme=1 (Kiro) | ❌ | Notre Router = label unique → **Ajouter scores** pour gérer l'ambiguïté |
| Matrice good/bad queries (Augment) | ❌ | Routing des tools de recherche |
| Default-safe explicite | ✅ | Déjà en place |
| Subagent typé + goal-only (Poke) | ⚠️ | Fan-out existe mais communication = prompt complet |

### Architect
| Mécanisme source | État | Action |
|---|---|---|
| EARS requirements format (Kiro) | ❌ | Structurer la spec |
| Read-only strict + write_phases only (Traycer) | ✅ | Déjà read-only |
| 8 templates par type de repo (Qoder) | ❌ | Spécialisation |
| Pseudocode numéroté + reflection (Manus) | ⚠️ | Sous-tâches existent, manque reflection |
| Tasklist triggers + incremental replanning (Augment) | ❌ | Décider si planifier |
| Approval typé via reason strings (Kiro) | ❌ | Contrat Architect→user |

### Coder
| Mécanisme source | État | Action |
|---|---|---|
| SEARCH/REPLACE (Cline) | ✅ | Porté (`search_replace_utils.py`) |
| apply_patch DSL (Codex) | ⚠️ | Partiel |
| Core Mandates "NEVER assume lib" (Gemini) | ✅ | Invariant F-44 |
| Sketch délégué `// ... existing code ...` (Cursor) | ❌ | Pattern 2-modèles |
| find_and_edit cross-files (Devin) | ❌ | Refactoring distribué |
| **Write-lock parallel policy** (Amp) | ❌ | Décider parallèle fan-out |
| Engineering mindset contract+edge cases (VSCode) | ❌ | Avant de coder |

### Tester
| Mécanisme source | État | Action |
|---|---|---|
| "specific→broad" (Codex) | ⚠️ | |
| Verify(Tests)→Verify(Standards) workflow (Gemini) | ❌ | Phase lint/typecheck explicite |
| Quality gates triage + deltas only (VSCode) | ❌ | Format rapport |
| report_env_issue + don't fix yourself (Devin) | ❌ | Escalation |

### Judge
| Mécanisme source | État | Action |
|---|---|---|
| Self-correction vérifiable (Cursor) | ❌ | Auto-régulation |
| `<think>` 13 triggers dont completion check (Devin) | ⚠️ | Think sélectif F-47, manque triggers |
| Citation `<cite>` obligatoire (DeepWiki) | ❌ | Justification des verdicts |
| Critical/Major/Minor grille (claude-code-unified-agents fiche 15) | ⚠️ | |

### Security
| Mécanisme source | État | Action |
|---|---|---|
| Matrice sandbox×approval (Codex) | ❌ | Le plus formel |
| `requires_approval` bool (Cline) | ❌ | Gate par commande |
| `{{secret_name}}` placeholder (Warp) | ❌ | Anti-leak |
| Canary anti-injection decoy (CodeBuddy) | ❌ | Anti-prompt-injection |
| DATA INTEGRITY + dual-action (Bolt) | ❌ | DB safety |

### PromptRefiner
| Mécanisme source | État | Action |
|---|---|---|
| Intent detection (Kiro/Augment/Qoder) | ⚠️ | Existe (`ambiguities_detected`) |
| Repo-type detection (Qoder) | ❌ | Adapter la spec au type |

---

## 7. Ce qui est NOUVEAU vs notre état (F-44 + F-56)

Notre fondation (`prompts.py`) couvre les **10 invariants universels** + **condensé des 9 rôles** + **durcissement P14**. Ce que le corpus apporte en **plus** :

### Gaps actionnables prioritaires
1. **Gates bloquantes F-56-bis** (le plus mûr) : `requires_approval` (Cline), matrice sandbox Codex, `is_dangerous` (Replit) — actuellement nos rôles sont déclaratifs ("DEFENSIVE ONLY"), pas de mécanisme attaché
2. **Write-lock parallel policy** (Amp) : notre Coder fan-out ne décide pas parallèle vs séquentiel sur critère de cibles disjointes
3. **Self-correction vérifiable** (Cursor) : règle `tools_used => update_emitted` pour Judge
4. **Citation `<cite>` obligatoire** (DeepWiki) : justifier verdicts Judge par localisation code
5. **Quality gates triage** (VSCode) : rapport Tester en deltas PASS/FAIL + requirements coverage

### Gaps secondaires
6. EARS format pour Architect (Kiro)
7. Engineering mindset contract+edge cases avant coder (VSCode)
8. `{{secret_name}}` placeholder (Warp) + canary decoy (CodeBuddy) pour Security
9. notify vs ask (Manus) pour gating
10. 8 templates par type de repo (Qoder) pour Architect

---

## 8. Synthèse en une ligne

Le corpus confirme nos **10 invariants (F-44)** et nos **9 rôles (F-0)**, mais recèle **20 pépites différenciantes** non ingérées — les plus actionnables étant les **gates bloquantes** (`requires_approval`/sandbox), la **write-lock parallel policy** (Amp), le **self-correction vérifiable** (Cursor) et la **citation obligatoire** (DeepWiki).
