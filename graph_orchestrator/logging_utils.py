"""Utilitaires d'affichage : niveau de log, table d'observabilité.

- `resolve_verbosity` : traduit LOG_LEVEL (env) en LogLevel smolagents pour calmer
  le bruit des workers en parallèle.
- `NodeMetrics` : dataclass pour collecter tokens/durée par nœud.
- `render_observability_table` : table rich récapitulative en fin de run.
"""

from dataclasses import dataclass
from typing import List, Optional

from rich.console import Console
from rich.table import Table
from smolagents.monitoring import LogLevel


def resolve_verbosity(level: str) -> LogLevel:
    """Convertit une chaîne LOG_LEVEL en LogLevel smolagents.

    smolagents expose : OFF (-1), ERROR (0), INFO (1), DEBUG (2).
    - LOW    → ERROR : workers parallèles, n'affiche que les erreurs (Fan-out lisible)
    - MEDIUM → INFO  : affiche les étapes
    - HIGH   → DEBUG : verbose complet (juge/synthèse séquentiels)
    """
    mapping = {
        "LOW": LogLevel.ERROR,
        "MEDIUM": LogLevel.INFO,
        "HIGH": LogLevel.DEBUG,
        "INFO": LogLevel.INFO,
        "DEBUG": LogLevel.DEBUG,
    }
    return mapping.get(level.strip().upper(), LogLevel.ERROR)


@dataclass
class NodeMetrics:
    """Métriques d'un nœud exécuté (collectées via return_full_result=True)."""
    node: str  # ex. "worker[t1]", "judge", "synth"
    model: str
    duration_s: Optional[float]  # None si indisponible
    input_tokens: Optional[int]
    output_tokens: Optional[int]

    @property
    def total_tokens(self) -> Optional[int]:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens


def render_observability_table(metrics: List[NodeMetrics], console: Optional[Console] = None) -> None:
    """Affiche une table récapitulative des tokens et durées par nœud."""
    console = console or Console()

    table = Table(title="Observabilité du run", show_lines=False, header_style="bold cyan")
    table.add_column("Nœud", style="white", no_wrap=True)
    table.add_column("Modèle", style="dim")
    table.add_column("Durée", justify="right")
    table.add_column("Tokens (in/out)", justify="right")
    table.add_column("Total", justify="right", style="bold")

    total_duration = 0.0
    total_in = 0
    total_out = 0
    has_token_data = False
    has_duration_data = False

    for m in metrics:
        dur = f"{m.duration_s:.1f}s" if m.duration_s is not None else "—"
        tokens = (
            f"{m.input_tokens:,} / {m.output_tokens:,}".replace(",", " ")
            if m.total_tokens is not None
            else "—"
        )
        total = f"{m.total_tokens:,}".replace(",", " ") if m.total_tokens is not None else "—"
        table.add_row(m.node, _short_model(m.model), dur, tokens, total)

        if m.duration_s is not None:
            total_duration += m.duration_s
            has_duration_data = True
        if m.total_tokens is not None:
            total_in += m.input_tokens
            total_out += m.output_tokens
            has_token_data = True

    # Ligne TOTAL
    total_dur = f"{total_duration:.1f}s" if has_duration_data else "—"
    total_tok = (
        f"{(total_in + total_out):,}".replace(",", " ") if has_token_data else "—"
    )
    table.add_row(
        "[bold]TOTAL[/bold]", "", f"[bold]{total_dur}[/bold]",
        "", f"[bold]{total_tok}[/bold]",
    )

    console.print()
    console.print(table)


def _short_model(model_id: str) -> str:
    """Raccourcit l'affichage d'un model_id pour la table."""
    # hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL -> gemma-4-E4B-it-qat
    if "/" in model_id:
        model_id = model_id.rsplit("/", 1)[-1]
    if ":" in model_id:
        model_id = model_id.split(":", 1)[0]
    # tronque les GGUF suffixes verbeux
    model_id = model_id.replace("-GGUF", "").replace("-qat", "")
    return model_id
