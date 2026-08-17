# Post-mortem run #10 — E2E validation FRESH_START (2026-08-17, main 018a5b6)

> Run de validation post-merges PR #90 (fiche 47-kilocode) + PR #91 (F-114/F-115),
> tâche `bubble-sort-multifile-v6`, ~21 min d'inférence (1 248 s), exit 0.
> Résultat final : `escalated` (3 itérations rejetées par le Static Tester,
> diagnostic d'escalade de qualité). Log : `logs/e2e_f114_run.log` — rapport :
> `analysis_report.md`.

## TL;DR

**F-114 est une transformation radicale du comportement du Coder** : là où le
run #9 faisait 48 screenshots pour 0 appel `visual_check` et mourait 3× à
max_steps (43,9 M tokens, 0 livrable), le run #10 converge en **12 steps à la
itération 1** avec **60 appels `visual_check`** et un `final_answer` valide du
premier coup. Le livrable reste néanmoins rejeté (bug compteur F-110 reproduit
par le 4B) — mais cette fois par les gardes déterministes, en 4× moins de temps
et 4,6× moins de tokens, avec escalade propre et diagnostic exact.

## Verdicts par feature

| Feature | Verdict | Preuve |
|---|---|---|
| **F-114** (cap + nudge) | ✅ **VALIDÉ E2E** | 60 appels `visual_check` avec observations factuelles (vs 0 au run #9) ; 17 screenshots demandés dont 8 `fullPage=True` **tous convertis** — 3 images capturées toutes en 1280×800 (vs images 9 315 px au run #9 : plus aucun timeout) ; convergence 12 steps iter 1 |
| **F-115** (spec anglaise) | ✅ **VALIDÉ E2E** | sections `## Objective` / `## Expected Features` / `## Acceptance Criteria` présentes ×4 dans la chaîne (spec → Architect → Coder) ; 5 ambiguïtés détectées sur le prompt français |
| **F-112** (sonde animation) | 🟡 PARTIEL | le Static Tester a réfuté via le Tier 1c-(c) **F-110** (compteur incrémenté jamais propagé à `counterEl.textContent`) — les gardes AMONT ont court-circuité avant que la sonde temporelle ne soit l'arbitre. À valider sur un livrable passant les Tiers 1-3 |
| **F-113** (sauvetage api_base) | ❌ NON VALIDÉ | le Web Tester LLM n'a **jamais tourné** : court-circuité 3× par le Static Tester (by design, économie de cycle). Le chemin du sauvetage ne s'exerce que si les gardes déterministes passent |

## Métriques (vs run #9)

| Métrique | Run #9 | Run #10 |
|---|---|---|
| Durée inférence | 2 980 s | **1 248 s (−58 %)** |
| Tokens input | 43,9 M | **9,5 M (−78 %)** |
| Appels visual_check | 0 | **60** |
| Screenshots (capturés) | 48 (dont 9 315 px) | 3 (tous 1280×800) |
| Verdict | failure « Coder crash » | **escalated** (diagnostic exploitable) |

## Déroulé

- Boot sain ; spec PromptRefiner EN 2 060 c. (5 ambiguïtés) ; Router HTML ;
  Architect 3 fichiers.
- **Itération 1** : Coder 4B converge en 12 steps — checklist 5/5 visual_check
  honorée AVANT final_answer (le nudge F-114 n'a même pas eu à tirer) ;
  Stall Detector signalé mais priorité au final_answer valide (règle F-88) ✓.
- Static Tester réfute : Tier 1c-(c) F-110 — `comparisons++` jamais propagé à
  `counterEl.textContent` (le bug compteur historique du 4B) → court-circuit
  du Tester LLM.
- **Itérations 2-3** : le 4B ne corrige PAS (« aucune édition matérielle » —
  Goal enforcement F-99 l'a détecté à la ronde 1). 3 rejets déterministes →
  escalade F-23 avec cause racine + leçon EXACTES.
- `CODER_ULTRA_CORRECTION=false` dans `.env` (décision post-run #8 : Ornith 9B
  no-think trop lent, 3,8 t/s, mega-blocs > timeout 600 s) — l'escalade de
  modèle prévue par F-111 aux itérations déterministes était donc désactivée
  PAR CONFIG. Pas une anomalie : comportement conforme.

## Lecture d'ensemble

1. **L'usine tient sa promesse de refus** : 2 runs d'affilée sans aucun faux
   positif d'approbation — les livrables défectueux sont rejetés par les gardes
   déterministes avec feedback pédagogique, escalade documentée, exit propre.
2. **Le problème de convergence processuel du 4B est RÉSOLU** (F-114) ; il
   reste le problème de **correction** : face au bug compteur identifié 3× avec
   feedback précis, le 4B n'édite pas. C'était précisément la cible de F-111
   (ULTRA sur rejet déterministe), désactivée pour cause de lenteur.
3. **F-113 ne peut être validé que sur un livrable propre** : les gardes
   déterministes (F-54/F-100/F-108/F-110/F-112) court-circuitent le Tester LLM
   tant que le code a des bugs détectables statiquement. Options : (a) run
   dédié `STATIC_TESTER_ENABLED=0` (exercer uniquement Tester LLM → verdict →
   Judge → approbation) ; (b) attendre un run où le 4B/ULTRA livre du code
   passant les tiers.

## Propositions (décision utilisateur)

1. **Run dédié F-113** : `FRESH_START=1 STATIC_TESTER_ENABLED=0` (~30-40 min)
   — le Web Tester LLM tourne enfin, son verdict est parsé (ou le sauvetage
   F-113 s'exerce), le Judge arbitre : on valide le dernier fix non prouvé.
2. **Réactiver ULTRA au seul cas « itération ≥ 3 »** (dernière chance avant
   escalade) au lieu de tous les rejets déterministes — mitige la lenteur du
   9B (une seule activation par run maximum) tout en donnant une vraie
   dernière chance de correction. Petit cycle config/logique.
3. (à inscrire kilocode) le plan.md/task.md materialisé (F-120) : ancrage
   stable pour la correction — le Coder des itérations 2-3 n'avait pas de
   référence courte du bug à corriger.
