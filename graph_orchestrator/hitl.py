"""Human-in-the-loop stratégique (Phase 6).

Différence avec le hitl_checkpoint précédent : le déclenchement est CONDITIONNEL
(routage par nœud), pas global. Le checkpoint n'apparaît qu'aux nœuds "à enjeu"
(configurables via HITL_NODES), et affiche le contexte du Knowledge Graph
(provenance) pour que l'humain décide en connaissance de cause.
"""

from typing import List, Optional

from rich.console import Console
from rich.panel import Panel

from .config import Settings
from .models import WorkerOutput

console = Console()


def should_trigger_hitl(node_name: str, settings: Settings) -> bool:
    """Logique pure de routage stratégique.

    Le HITL se déclenche seulement si :
      1. settings.hitl_enabled est True (master switch)
      2. node_name fait partie des nœuds configurés (HITL_NODES, CSV)
    """
    if not settings.hitl_enabled:
        return False
    target_nodes = {n.strip() for n in settings.hitl_nodes.split(",") if n.strip()}
    return node_name in target_nodes


def hitl_checkpoint(
    approved_data: List[WorkerOutput],
    node_name: str = "synth",
    provenance: Optional[List[dict]] = None,
) -> bool:
    """Point d'approbation humaine. Retourne True si validé.

    Affiche les tâches approuvées ET, si fournie, leur provenance (qui a dit quoi,
    à partir de quel modèle) — l'humain voit la traçabilité avant de décider.
    """
    console.print(Panel(
        f"Nœud : [bold]{node_name}[/bold]\n{len(approved_data)} tâche(s) approuvée(s) par les adversaires.",
        title="[bold yellow]HUMAN-IN-THE-LOOP : validation requise[/bold yellow]",
        border_style="yellow",
    ))
    for w in approved_data:
        console.print(
            f"  • [bold]{w.task_id}[/bold] (conf={w.confidence_score:.2f})  {w.summary}"
        )

    if provenance:
        console.print("\n  [dim]Provenance (qui a produit chaque claim) :[/dim]")
        for p in provenance[:10]:  # plafonne l'affichage
            src = p.get("source", "?")
            model = p.get("model_id", "?")
            console.print(f"    [dim]via {src} ({model})[/dim]")

    try:
        answer = console.input(
            "\n[bold]Approuver la synthèse de ces tâches ? [y/N] : [/bold]"
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in {"y", "yes", "o", "oui"}
