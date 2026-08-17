# Run de référence #11 — Première approbation E2E complète (2026-08-17)

> **Pourquoi ce dossier existe** : `runs/` est vidé cycliquement par la rétention
> (OUTPUT_RETENTION). Ce run est le **premier livrable APPROUVÉ de bout en bout**
> par la pile de gardes moderne (Coder → LLM Web Tester → fail-closed → correction
> chirurgicale → re-test ciblé → Security → Judge ✓) — il est préservé ici comme
> **étalon de la validation 2026-08-17**, aux côtés du Golden Run historique
> (`debug/reference_run_qwen4b_bubble_sort/`).

## Où tout se trouve

| Fichier | Contenu |
|---|---|
| `index.html` / `styles.css` / `script.js` | **Le livrable approuvé** (3 fichiers, vanilla JS, thème sombre) — `script.js` contient la correction d'itération 2 (compteur propagé au DOM) |
| `draft_F_82_T1.md` | Le draft de l'Architecte (Ornith-9B) |
| `run_git_history.txt` | Historique git du run (F-53) : `Iteration 1` puis `Iteration 2 — script.js +2 insertions` = la correction chirurgicale du 4B, preuve matérielle |
| `run_full.log` | Journal d'exécution complet (6 743 lignes) — le film du run : checklist `visual_check` 5/5 aux 2 itérations, verdicts Tester, 2 sauvetages Pydantic SANS `Connection error`, fail-closed F-108, APPROBATION finale |
| `.transcripts/` | Archives de compaction F-101 (JSONL des steps snippés) |

## Contexte de reproduction

- Commande : `FRESH_START=1 STATIC_TESTER_ENABLED=0 uv run agent_graph.py`
  (run dédié F-113, post-mortem run #10 proposition 1 — Static Tester désactivé
  pour laisser le Web Tester LLM s'exercer)
- Tâche : `bubble-sort-multifile-v6` (`tasks.json`, coding)
- Modèles : Qwen3.5-4B (Coder), Ornith-1.0-9B (Architect/Security/Judge)
- Main : `018a5b6` (post-merges PR #90 + #91)
- Durée : ~23 min d'inférence (1 352 s), 14,3 M tokens input, exit 0

## Lectures

- Post-mortem complet : `debug/POSTMORTEM_RUN11.md`
- Leçon méta : le 4B sait CORRIGER avec un feedback qualitatif précis (Tester
  LLM) — qualité du feedback > escalade de modèle. Voir aussi le run #10
  (gardes actives, `debug/POSTMORTEM_RUN10.md`) pour la contre-preuve.
