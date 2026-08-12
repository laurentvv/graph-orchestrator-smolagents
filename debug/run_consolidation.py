"""Lance le nœud de Consolidation mémoire (production) en isolation — F-68 Phase 1.

Usage :
    uv run python debug/run_consolidation.py             # scénario par défaut (doublons)
    uv run python debug/run_consolidation.py mixed        # mix doublons + bruit + insight
    uv run python debug/run_consolidation.py clean        # peu de claims (skip attendu)

Le nœud execute_consolidation_node (F-68, P6-ter) déduplique/fusionne les claims
rabâchés du KG via un LLM-juge (format qm UPDATE/DELETE/ADD). Le LLM DÉCIDE, l'applier
déterministe apply_consolidation_actions (0 LLM) APPLIQUE.

Appelle DIRECTEMENT execute_consolidation_node de dspy_nodes.py (0 duplication) →
comportement réel : ConsolidationSignature (rôles + invariants F-44), model_lifecycle
(spawn REASONING_NO_THINK spec), apply_consolidation_actions (port qm).

But : valider que la consolidation réduit les doublons, préserve les leçons, et
dégrade gracieusement — sans relancer le workflow complet de 30-40 min.
"""
import argparse
import asyncio
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


# ─── FIXTURES FIGÉES — claims redondants simulés (ce que le KG accumule) ───────
# Chaque scénario peuple un KG isolé puis appelle le VRAI nœud de production.

ENTITY = "file:bubble_sort_index"
RUN_ID = "isolation_consolidation"

SCENARIOS = {
    "doublons": [
        ("Bug: SyntaxError ligne 5 — deux-points manquants après if", "refutation"),
        ("SyntaxError à la ligne 5 (deux-points manquants)", "refutation"),
        ("Erreur de syntaxe ligne 5 (if sans :)", "refutation"),
        ("Le tri ne s'exécute pas — performStep vide", "refutation"),
        ("Bubble sort ne trie pas — animation instantanée", "refutation"),
        ("requestAnimationFrame exécute tout en 1 tick", "refutation"),
        ("Le slider de vitesse n'a aucun effet", "refutation"),
        ("Les barres restent invisibles (height:100% sans parent heighté)", "refutation"),
        ("Container sans hauteur → barres height:% résolues à 0", "refutation"),
        ("Counter de comparaisons manquant", "refutation"),
        ("Compteur de comparaisons non affiché", "refutation"),
    ],
    "mixed": [
        ("Bug: SyntaxError ligne 5 — deux-points manquants", "refutation"),
        ("SyntaxError à la ligne 5", "refutation"),
        ("Chemins de fichiers : ./runs/2026-08-05/index.html", "observation"),
        ("Détail API : getElementById('startBtn') retourne un HTMLElement", "observation"),
        ("Timestamp du run : 2026-08-05T16:02:00Z", "observation"),
        ("Le tri ne s'exécute pas — performStep fait tout en 1 frame", "refutation"),
        ("Animation instantanée — requestAnimationFrame loop imbriquée", "refutation"),
        ("Leçon : une itération par frame, jamais l'algorithme complet", "escalation"),
    ],
    "clean": [
        ("Bug mineur : couleur du bouton", "refutation"),
        ("Le bouton start est bleu mais devrait être vert", "refutation"),
    ],
}


def _populate_kg(kg: KnowledgeGraph, scenario_name: str):
    """Peuple le KG avec les claims du scénario choisi."""
    kg.add_entity(ENTITY, kind="file")
    claims = SCENARIOS[scenario_name]
    for i, (content, kind) in enumerate(claims):
        cid = kg.add_claim(
            entity_id=ENTITY,
            content=content,
            kind=kind,
            confidence=0.6 if kind == "refutation" else 0.8,
            source="judge_panel" if kind == "refutation" else "coder",
            run_id=RUN_ID,
        )
        if cid is None:
            print(f"  (claim {i+1} ignorée — doublon exact)")
    return len(claims)


def _print_claims(kg: KnowledgeGraph, label: str):
    """Affiche les claims actuelles de l'entité."""
    claims = kg.get_claims(ENTITY)
    print(f"\n{'=' * 60}")
    print(f"📋 {label} : {len(claims)} claim(s) sur {ENTITY}")
    print(f"{'=' * 60}")
    for i, c in enumerate(claims, start=1):
        kind_badge = {
            "refutation": "🔴 REFUTATION",
            "observation": "🔵 OBSERVATION",
            "escalation": "🟣 ESCALATION",
            "insight": "🟢 INSIGHT",
        }.get(c["kind"], c["kind"])
        print(f"  {i:>2}. [{kind_badge}] {c['content'][:80]}")


async def main():
    parser = argparse.ArgumentParser(description="Isolation du nœud Consolidation mémoire (F-68).")
    parser.add_argument(
        "scenario", nargs="?", default="doublons",
        choices=list(SCENARIOS.keys()),
        help="Scénario de claims à charger (défaut: doublons).",
    )
    args = parser.parse_args()

    print("╔══════════════════════════════════════════════════════════╗")
    print("║  NŒUD DE CONSOLIDATION MÉMOIRE (F-68 Phase 1, P6-ter)   ║")
    print(f"║  Scénario : {args.scenario:<44s}║")
    print("╚══════════════════════════════════════════════════════════╝")

    settings = load_settings()
    print(f"\n⚙️  Config : seuil={settings.memory_consolidation_after} claims, "
          f"rétention={settings.memory_retention_days}j")
    print(f"⚙️  Modèle : {settings.no_think_spec.model} (think=False, classification)")

    # KG isolé (fichier temporaire — ne pollue pas data/graph_orchestrator.db).
    tmp_dir = tempfile.mkdtemp(prefix="consolidation_iso_")
    db_path = os.path.join(tmp_dir, "kg_iso.db")
    kg = KnowledgeGraph(db_path)

    try:
        _populate_kg(kg, args.scenario)
        _print_claims(kg, "AVANT consolidation")

        print("\n🚀 Appel à execute_consolidation_node (vrai nœud de production)...")
        from graph_orchestrator.dspy_nodes import execute_consolidation_node

        summary, metrics = await execute_consolidation_node(kg, RUN_ID, settings)

        _print_claims(kg, "APRÈS consolidation")

        print(f"\n{'─' * 60}")
        if summary is None:
            print("📊 Résultat : AUCUNE consolidation (pas assez de claims ou LLM down).")
        else:
            print("📊 Résultat de la consolidation :")
            for entity_id, result in summary.items():
                print(f"  • {entity_id} :")
                print(f"      - {result['updated']} claim(s) mise(s) à jour (fusion)")
                print(f"      - {result['deleted']} claim(s) supprimée(s) (doublons/bruit)")
                print(f"      - {result['added']} insight(s) ajouté(s) (patrons transversaux)")
                print(f"      - {result['skipped']} action(s) ignorée(s) (index invalide/doublon)")
            if metrics:
                for m in metrics:
                    print(f"  ⏱️  {m.node} : {m.duration_s:.1f}s ({m.model})")

        # Vérification manuelle : les kinds préservés (escalation/insight) doivent survivre.
        final_claims = kg.get_claims(ENTITY)
        preserved = [c for c in final_claims if c["kind"] in ("escalation", "insight")]
        original_preserved = [
            content for content, kind in SCENARIOS[args.scenario]
            if kind in ("escalation", "insight")
        ]
        print(f"\n🔒 Leçons préservées : {len(preserved)} (original : {len(original_preserved)})")
        if len(preserved) < len(original_preserved):
            print("  ⚠️  ATTENTION : une leçon durable a été supprimée — vérifier le LLM.")
        else:
            print("  ✅ Toutes les leçons durables (escalation/insight) sont préservées.")

    finally:
        kg.close()
        # Nettoyage du KG temporaire.
        try:
            os.remove(db_path)
            os.rmdir(tmp_dir)
        except OSError:
            pass

    print("\n✅ Isolation terminée.")


if __name__ == "__main__":
    asyncio.run(main())
