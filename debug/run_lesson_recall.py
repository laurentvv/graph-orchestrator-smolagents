"""Lance le recall mémoire cross-run (production) en isolation — F-68 Phase 2.

Usage :
    uv run python debug/run_lesson_recall.py            # scénario par défaut (notebook riche)
    uv run python debug/run_lesson_recall.py empty       # KG vierge (bloc vide attendu)
    uv run python debug/run_lesson_recall.py scratch     # que du scratch (bloc vide attendu)

Le recall (lesson_recall.py, 0 LLM, déterministe) récupère les N leçons durables
(insight+escalation) les plus récentes de TOUS les runs passés et les formate en
bloc markdown injectable au prompt Coder. C'est la boucle fermée d'apprentissage :
un run qui a appris une leçon (ex: « une itération par requestAnimationFrame »)
la transmet aux runs suivants.

Two-tier implicite :
  - scratch  = observation/refutation (éphémère, pruné 30j — JAMAIS rappelé).
  - notebook = insight/escalation (durable, préservé cross-run — RAPPELÉ ici).

Appelle DIRECTEMENT recall_lessons + build_lessons_block de lesson_recall.py
(0 duplication) → comportement réel. KG temporaire isolé (tempfile) pour ne pas
polluer data/graph_orchestrator.db.

But : valider que le recall récupère les bonnes leçons, ignore le scratch, et
formate un bloc lisible — sans relancer le workflow complet de 30-40 min.
"""
import argparse
import os
import sys
import tempfile

from dotenv import load_dotenv

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from graph_orchestrator.config import load_settings
from graph_orchestrator.knowledge_graph import KnowledgeGraph
from graph_orchestrator.lesson_recall import build_lessons_block, recall_lessons


# ─── FIXTURES FIGÉES — leçons durables simulées (ce que le notebook accumule) ──

RUN_PRIOR_A = "prior_bubble_sort_run_abc123"
RUN_PRIOR_B = "prior_dashboard_run_def456"


SCENARIOS = {
    # Notebook riche : insights + escalations de plusieurs runs passés.
    "default": [
        ("file:bubble_sort_index", "Une itération par requestAnimationFrame évite l'animation instantanée (bug F-81).", "insight", RUN_PRIOR_A),
        ("file:bubble_sort_index", "Toujours reset i=0; j=0; isSorting=false dans init() sinon le 2e clic est inopérant.", "insight", RUN_PRIOR_A),
        ("file:dashboard_admin", "Le pattern incrémental (squelette + append_file sections) reste ingérable sur gemma-4 — préférer write_file monolithique.", "escalation", RUN_PRIOR_B),
        ("file:landing_nimbus", "h1 > 3rem est interdit sauf hero unique de landing page (skill frontend-design ÉTAPE 0).", "insight", RUN_PRIOR_B),
    ],
    # KG vierge : aucune leçon durable.
    "empty": [],
    # Que du scratch : observations + réfutations (éphémères, JAMAIS rappelées).
    "scratch": [
        ("file:t1", "Code généré (Itération 1): HTML bubble sort créé.", "observation", RUN_PRIOR_A),
        ("file:t1", "Bug: les barres sont invisibles car height:% sans parent heighté.", "refutation", RUN_PRIOR_A),
        ("file:t2", "TypeError: document.querySelector is not a function.", "refutation", RUN_PRIOR_A),
    ],
}


def _populate_kg(kg: KnowledgeGraph, scenario_name: str) -> int:
    """Peuple le KG isolé avec le scénario choisi. Retourne le nb de claims ajoutées."""
    scenario = SCENARIOS.get(scenario_name, SCENARIOS["default"])
    n = 0
    for entity_id, content, kind, run_id in scenario:
        kg.add_entity(entity_id, kind="file")
        cid = kg.add_claim(
            entity_id=entity_id,
            content=content,
            kind=kind,
            confidence=0.9 if kind in ("insight", "escalation") else 0.5,
            source="isolation_script",
            run_id=run_id,
        )
        if cid is not None:
            n += 1
        else:
            print(f"    (doublon ignoré: {content[:50]}...)")
    return n


def _print_claims(kg: KnowledgeGraph, label: str) -> None:
    """Affiche toutes les claims du KG (tous kinds confondus) pour comparaison."""
    rows = kg.conn.execute(
        "SELECT content, kind, created_at FROM claim ORDER BY created_at DESC"
    ).fetchall()
    badge = {"insight": "💡", "escalation": "🚨", "observation": "👁️", "refutation": "🐞"}
    print(f"\n{'─' * 70}\n{label} ({len(rows)} claims total)")
    print(f"{'─' * 70}")
    for content, kind, created_at in rows:
        icon = badge.get(kind, "❓")
        durable = "✓ RAPPELÉ" if kind in ("insight", "escalation") else "✗ ignoré (scratch)"
        print(f"  {icon} [{kind}] {durable}")
        print(f"      {content[:90]}{'...' if len(content) > 90 else ''}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Isolation du recall mémoire cross-run (F-68 Phase 2).")
    parser.add_argument(
        "scenario", nargs="?", default="default",
        choices=list(SCENARIOS.keys()),
        help="Scénario de fixtures (default: notebook riche).",
    )
    args = parser.parse_args()

    settings = load_settings()
    print("=" * 70)
    print("  F-68 Phase 2 — RECALL MÉMOIRE CROSS-RUN (isolation, 0 LLM)")
    print("=" * 70)
    print(f"  Scénario      : {args.scenario}")
    print(f"  recall_limit  : {settings.memory_recall_limit}")
    print(f"  recall_max    : {settings.memory_recall_max_chars} chars")
    print("  kinds durables: insight, escalation (préservés par prune_old_claims)")

    # KG temporaire isolé — ne pollue JAMAIS data/graph_orchestrator.db.
    tmp_dir = tempfile.mkdtemp(prefix="lesson_recall_iso_")
    db_path = os.path.join(tmp_dir, "kg_recall_isolation.db")
    kg = KnowledgeGraph(db_path)
    try:
        added = _populate_kg(kg, args.scenario)
        print(f"\n[*] {added} claim(s) ajoutée(s) au KG isolé.")
        _print_claims(kg, "KG AVANT RECALL")

        # ─── LE RECALL (0 LLM, déterministe) ───────────────────────────────
        print(f"\n{'═' * 70}\n  RECALL — recall_lessons(kg, limit={settings.memory_recall_limit})")
        print(f"{'═' * 70}")
        recalled = recall_lessons(kg, limit=settings.memory_recall_limit)
        print(f"  → {len(recalled)} leçon(s) durable(s) récupérée(s) cross-run.")

        # ─── FORMATAGE (build_lessons_block) ───────────────────────────────
        block = build_lessons_block(recalled, max_chars=settings.memory_recall_max_chars)
        if block:
            print(f"\n{'─' * 70}\n  BLOC INJECTÉ AU PROMPT CODER (build_lessons_block)")
            print(f"{'─' * 70}")
            print(block)
            print(f"{'─' * 70}")
            print(f"  Taille: {len(block)} chars")
        else:
            print("\n  ⚠️  Bloc vide (aucune leçon durable à rappeler).")

        # ─── VÉRIFICATION D'INVARIANCE ─────────────────────────────────────
        print(f"\n{'─' * 70}\n  VÉRIFICATION D'INVARIANCE")
        print(f"{'─' * 70}")
        kinds_recalled = {r["kind"] for r in recalled}
        scratch_leaked = kinds_recalled & {"observation", "refutation"}
        if scratch_leaked:
            print(f"  ❌ ÉCHEC : le scratch a fuité dans le recall : {scratch_leaked}")
        elif recalled:
            print(f"  ✅ OK : seules les leçons durables sont rappelées ({kinds_recalled}).")
        else:
            print(f"  ✅ OK : aucune leçon à rappeler (scénario '{args.scenario}' = vide/scratch).")

    finally:
        kg.close()
        try:
            os.remove(db_path)
            os.rmdir(tmp_dir)
        except OSError:
            pass

    print("\n[*] Isolation terminée — KG temporaire nettoyé.")


if __name__ == "__main__":
    main()
