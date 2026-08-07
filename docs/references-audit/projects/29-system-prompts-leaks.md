# 29 - System Prompts Leaks

## 📝 Synthèse
* **Date d'audit** : 2026-08-07 (extraction approfondie : 2026-08-07)
* **Dépôt** : [asgeirtj/system_prompts_leaks](https://github.com/asgeirtj/system_prompts_leaks) (sous-module git)
* **Description** : Collection massive (~300+ fichiers) de prompts système "fuités" (leaked) provenant des principaux modèles d'IA du marché (OpenAI, Anthropic, Google, xAI, Perplexity, Microsoft, etc.), 19 dossiers vendeurs.
* **Utilité** : Aperçu non censuré des instructions système en production pour des modèles de pointe et des agents complexes (Claude Code/Design/Cowork, Codex GPT-5.x, Antigravity CLI, Cursor, Devin, Amp, Copilot CLI, Grok Build).

## 🎯 Points Forts / Architecture
* **Diversité et Couverture** : Modèles jusqu'à juillet 2026 (Claude Opus 5/Fable 5, ChatGPT 5.6 Sol, Gemini 3.5 Flash, Grok 4.5, Codex gpt-5.6).
* **Architecture d'Agents** : Claude Code (10 subagents avec YAML frontmatter `name`/`whenToUse`/`tools`/`disallowedTools`/`model`/`permissionMode`/`maxTurns`), Claude Cowork (dispatch multi-agent), Codex (`spawn_agent` + write sets disjoints), Amp (Oracle/Task/Search taxonomie 3 subagents).
* **Anti-injection (la pépite n°1)** : Claude Cowork a le bloc `<critical_injection_defense>` le plus complet du corpus — 6 tags XML imbriqués, défense récursive, détection social engineering, immutabilité des règles (`claude-cowork.md:1384-1554`). Comble notre gap n°1 (aucune directive anti-injection dans nos prompts actuels).
* **Garde-fous (Guardrails)** : Taxonomie de confirmation Codex Computer Use (4 tiers, `computer-use.md:32-101`), matrice 3 tiers Claude Code, shell-injection detector Copilot-CLI (`${var@P}`/`eval`).

## 🚫 Points d'Exclusion
* **Prompts obsolètes** : Sous-dossiers "Old"/"raw" (dépréciés).
* **Personas non techniques** : "Personalities"/"Voice Assistant" non pertinents.
* **bundled-skills/** : Documentation Anthropic livrée (pas des leaks) — utile comme référence seulement.
* **Gap notables (absents de CE corpus)** : v0, Lovable, Replit Agent, Aider, Cline, Roo, Windsurf, Bolt, Qoder, Kiro, Traycer, Manus — ces prompts sont dans l'AUTRE corpus (`system-prompts-and-models-of-ai-tools`, fiche 17/F-64).

## ⚠️ Correction d'attribution (extraction 2026-08-07)
Le minage approfondi révèle que plusieurs mécanismes cités dans F-65/F-64 en attribuant la source à ce corpus **ne s'y trouvent pas** — ils viennent de la fiche 17 :
- `<think>` tool 13 triggers (Devin) → absent ici.
- `report_environment_issue` (Devin) → absent.
- Balise `<cite>` (Devin DeepWiki) → absent ; Devin utilise `<ref_file>`/`<ref_snippet>`.
- Cursor "same turn / update_emitted" → absent ; le plus proche est Claude Code "don't end with a promise" (`claude-code-desktop-fable-5.md:105`).
- apply_patch `@@` hiérarchique / quality gates triage / response-mode escalation (VSCode gpt-5) → absents des fichiers Microsoft.

## 📦 Composants Pertinents (extraction détaillée)
→ **Livrable complet** : [`docs/system_prompts_leaks_extraction.md`](../../system_prompts_leaks_extraction.md) (12 sections, citations verbatim `file:line`).

Top 3 découvertes :
1. **Anti-injection Claude Cowork** (`claude-cowork.md:1384-1554`) — 6 tags imbriqués, défense récursive. Notre gap n°1.
2. **Taxo confirmation Codex** (`computer-use.md:32-101`) — base la plus concrète pour F-65 gates bloquantes.
3. **Write-lock parallel policy Amp** (`amp-code.md:466-480`) — parallèle ssi cibles disjointes, serialize si contrat partagé. Confirmé par Codex (`codex-full.md:1295-1310`).

Autres mécanismes actionnables : `{{secret_name}}` redaction (Warp), PII exfiltration defense (Cowork), failure tokens `result:`/`needs input:`/`failed:` (Claude Code agent), honest-reporting anti-faux-vert (Amp), shell-injection detector (Copilot-CLI).

## 🚀 Recommandations pour l'Usine Logicielle
* **Anti-injection (NOUVEAU, priorité max)** : Ajouter un invariant n°11 + bloc spécifique Coder/Testeur inspiré de Claude Cowork. Gap comblé à ~15 lignes denses.
* **F-65 (ingestion pépites)** : Les 5 pépites restent valides mais avec **sources corrigées** (cf. extraction §10). Pépite anti-injection ajoutée en tête (ROI max).
* **Quick wins prompts faibles** : `JSONFixSignature`, `SkillResearchSignature`, `Drafter`, `Synth` — cf. extraction §9.
* **Correction plan** : Éditer `plan_usine_logicielle.md` F-65 pour distinguer sources fiche 17 vs fiche 29.
