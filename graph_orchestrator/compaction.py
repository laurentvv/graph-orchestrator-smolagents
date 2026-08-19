import json as _json
import re as _re
import time as _time
import uuid as _uuid
from pathlib import Path as _Path
from typing import List, Optional

from smolagents import CodeAgent, AgentMemory
from smolagents.agents import ActionStep
from smolagents.monitoring import Timing

# --- Seuils F-101 (port learn-claude-code s08_context_compact) ---
# Au-delà de LARGE_RESULT_CHAR_CHARS, un tool result est persisté sur disque
# et remplacé par un bloc <persisted-output> (preview réduite) au lieu d'une
# troncature destructive.
LARGE_RESULT_CHAR_LIMIT = 30_000
PREVIEW_CHARS = 2_000

# Marqueur d'archive s08 exact : "[N messages archived at <path>]".
ARCHIVE_MARKER_RE = _re.compile(r"\[(\d+) messages archived at ([^\]]+)\]")


def _synthetic_action_step(step_number: int) -> ActionStep:
    """Build a minimal ActionStep for compaction summaries.

    smolagents made ``timing`` a required positional argument of
    ``ActionStep.__init__`` (it used to default to None). The synthetic
    steps created during snip/branch summarization carry no real timing
    information, so we fabricate a zero-duration ``Timing`` to satisfy
    the contract and avoid:

        ActionStep.__init__() missing 1 required positional argument: 'timing'
    """
    now = _time.time()
    return ActionStep(step_number=step_number, timing=Timing(start_time=now, end_time=now))

def apply_image_purge(memory: AgentMemory):
    """Purge all visual memory except the very last step's image to prevent context explosion."""
    action_steps = [step for step in memory.steps if isinstance(step, ActionStep)]
    if not action_steps:
        return

    # Process older steps, keeping only the image of the last step
    for step in action_steps[:-1]:
        if hasattr(step, "observations_images") and step.observations_images:
            step.observations_images = []

    # As a secondary safety, if the last step has multiple images, only keep the last 1
    last_step = action_steps[-1]
    if hasattr(last_step, "observations_images") and last_step.observations_images and len(last_step.observations_images) > 1:
        last_step.observations_images = last_step.observations_images[-1:]

def _serialize_step(step) -> dict:
    """Sérialisation défensive d'un step pour l'archive JSONL (best-effort).

    L'archive doit rester tolérante : un champ non sérialisable est converti
    en chaîne, jamais une exception (l'archivage ne doit pas casser la
    compaction — ADR-0002 fail-open).
    """
    data: dict = {"step_type": type(step).__name__}
    for attr in (
        "step_number",
        "model_output",
        "code_action",
        "observations",
        "error",
        "is_final_answer",
        "task",
    ):
        value = getattr(step, attr, None)
        try:
            _json.dumps(value)
            data[attr] = value
        except (TypeError, ValueError):
            data[attr] = str(value)
    tool_calls = getattr(step, "tool_calls", None)
    if tool_calls:
        try:
            data["tool_calls"] = [
                {
                    "name": getattr(tc, "name", None) or (tc.get("name") if isinstance(tc, dict) else None),
                    "arguments": getattr(tc, "arguments", None) or (tc.get("arguments") if isinstance(tc, dict) else None),
                }
                for tc in tool_calls
            ]
        except Exception:
            data["tool_calls"] = str(tool_calls)
    return data


def archive_steps(steps: List[object], transcript_dir: Optional[_Path]) -> Optional[_Path]:
    """Archive les steps supprimés par le snip en JSONL perte-zéro (s08).

    Écrit ``transcript_<uuid4>.jsonl`` (création exclusive ``open("x")``),
    une ligne JSON par step. Le marqueur laissé dans le contexte pointe vers
    ce fichier : l'agent peut relire l'intégralité via read_file (mécanique
    de retrieval claude-science — « nothing archived is lost »).

    Retourne le chemin, ou None si archivage impossible (dir None, erreur
    disque) → l'appelant retombe sur le marqueur texte historique.
    """
    if transcript_dir is None or not steps:
        return None
    try:
        transcript_dir.mkdir(parents=True, exist_ok=True)
        path = transcript_dir / f"transcript_{_uuid.uuid4().hex}.jsonl"
        with path.open("x", encoding="utf-8") as fh:
            for step in steps:
                fh.write(_json.dumps(_serialize_step(step), ensure_ascii=False) + "\n")
        return path
    except Exception:
        return None


def persist_large_output(
    identifier: str,
    output: str,
    outputs_dir: Optional[_Path],
    limit_chars: int = LARGE_RESULT_CHAR_LIMIT,
    preview_chars: int = PREVIEW_CHARS,
) -> str:
    """Persiste un gros tool result sur disque et retourne le bloc
    ``<persisted-output>`` avec preview (s08 persist_large_output).

    Sous le seuil : output inchangé. Sans ``outputs_dir`` ou sur erreur
    disque : output inchangé (fail-open, la troncature budget reste le
    filet de sécurité en aval).
    """
    if outputs_dir is None or len(output) <= limit_chars:
        return output
    try:
        outputs_dir.mkdir(parents=True, exist_ok=True)
        safe_id = _re.sub(r"[^A-Za-z0-9._-]", "_", str(identifier))[:120] or "unknown"
        path = outputs_dir / f"{safe_id}.txt"
        if not path.exists():
            path.write_text(output, encoding="utf-8")
        return (
            "<persisted-output>\n"
            f"Full output: {path}\n"
            "Preview:\n"
            f"{output[:preview_chars]}\n"
            "</persisted-output>"
        )
    except Exception:
        return output


def apply_micro_compact(memory: AgentMemory, keep_recent: int = 2, threshold: int = 250):
    """L2: Compaction Payload Recovery (Kilo Code / OpenCode — fiche 47).

    Purge agressivement les anciens outputs verbeux (snapshots DOM, dumps de code,
    grosses traces) des étapes antérieures pour éviter la saturation du contexte du 4B
    et maintenir une vitesse de génération maximale (> 15 t/s).
    Si l'observation contient un chemin persisté, le remplacement pointe vers ce chemin.
    """
    action_steps = [step for step in memory.steps if isinstance(step, ActionStep)]
    if len(action_steps) <= keep_recent:
        return

    # Process older steps
    for step in action_steps[:-keep_recent]:
        obs_str = str(getattr(step, "observations", "") or "")
        if len(obs_str) > threshold:
            saved_path = None
            for line in obs_str.splitlines():
                if line.startswith("Full output: "):
                    saved_path = line.removeprefix("Full output: ").strip()
                    break

            if saved_path:
                step.observations = f"[Earlier tool result saved at {saved_path}]"
            elif "RootWebArea" in obs_str or "## Latest page snapshot" in obs_str:
                step.observations = "[Compacted: DOM tree snapshot inspected and verified]"
            elif "<!DOCTYPE html" in obs_str or "<html" in obs_str:
                step.observations = f"[Compacted: HTML/JS source code ({len(obs_str)} chars) read]"
            elif "Console messages" in obs_str:
                if any(k in obs_str for k in ("[error]", "TypeError", "ReferenceError", "SyntaxError", "Uncaught")):
                    err_lines = [
                        l.strip()
                        for l in obs_str.splitlines()
                        if any(k in l for k in ("[error]", "TypeError", "ReferenceError", "SyntaxError", "Uncaught"))
                    ]
                    step.observations = "[Compacted: Console errors observed:\n" + "\n".join(err_lines[:5]) + "]"
                else:
                    step.observations = "[Compacted: 0 console errors observed]"
            else:
                step.observations = f"[Compacted: Earlier tool output ({len(obs_str)} chars) truncated. Re-run if needed.]"

def apply_snip_compact(
    memory: AgentMemory,
    max_steps: int = 15,
    transcript_dir: Optional[_Path] = None,
    frame: Optional[List[str]] = None,
):
    """L1: Trim middle steps if the history is getting too long.

    F-101 — deux évolutions (learn-claude-code s08 + opencode/claude-science) :
    (1) Archive disque : les steps supprimés sont archivés en JSONL perte-zéro
    (``transcript_dir``) et le marqueur devient ``[N messages archived at
    <path>]`` (s08 exact) — sans ``transcript_dir``, marqueur historique.
    (2) Chaînage + frame : les chemins d'archives PRÉCÉDENTS snippés à leur
    tour sont reportés dans le nouveau marqueur (opencode : le résumé
    précédent est réinjecté — rien n'échappe aux compactions successives) ;
    le frame scratchpad (claude-science) survit à chaque snip.
    """
    # steps typically start with TaskStep, followed by ActionSteps
    if len(memory.steps) <= max_steps:
        return

    keep_head = 3  # Keep TaskStep + first few ActionSteps to remember context
    keep_tail = max_steps - keep_head

    if keep_head >= len(memory.steps) - keep_tail:
        return

    head_steps = memory.steps[:keep_head]
    tail_steps = memory.steps[-keep_tail:]
    snipped = memory.steps[keep_head:-keep_tail]
    snipped_count = len(snipped)

    archive_path = archive_steps(snipped, transcript_dir)

    # Report des archives précédentes (chaînage) : un snip antérieur peut
    # vivre dans les steps snippés — son chemin doit survivre.
    prior_archives: List[str] = []
    for step in snipped:
        for match in ARCHIVE_MARKER_RE.finditer(str(getattr(step, "model_output", "") or "")):
            prior = match.group(2).strip()
            if prior not in prior_archives:
                prior_archives.append(prior)

    # Create a synthetic ActionStep that holds the "snipped" notice
    snip_step = _synthetic_action_step(head_steps[-1].step_number + 1)
    if archive_path is not None:
        marker = f"[{snipped_count} messages archived at {archive_path}]"
        if prior_archives:
            marker += f"\nEarlier archives kept: {', '.join(prior_archives)}"
    else:
        marker = f"[Snipped {snipped_count} intermediate steps to preserve context window]"
        if prior_archives:
            marker += f"\nEarlier archives kept: {', '.join(prior_archives)}"
    if frame:
        marker += "\nFRAME (survit à la compaction — notes de travail):\n" + "\n".join(
            f"- {note}" for note in frame
        )
    snip_step.model_output = marker

    memory.steps = head_steps + [snip_step] + tail_steps

def apply_tool_result_budget(
    memory: AgentMemory,
    max_bytes: int = 80000,
    outputs_dir: Optional[_Path] = None,
):
    """L3: Truncate extremely large tool outputs in the most recent steps.

    F-101 (s08) : avant de tronquer, le contenu intégral est PERSISTÉ sur
    disque (``outputs_dir``) sous forme de bloc ``<persisted-output>`` — la
    troncature n'est plus une perte, juste un déplacement. Sans
    ``outputs_dir``, comportement historique (preview tronquée).
    """
    action_steps = [step for step in memory.steps if isinstance(step, ActionStep) and step.observations]

    total_bytes = sum(len(str(step.observations)) for step in action_steps)
    if total_bytes <= max_bytes:
        return

    # Sort steps by observation size, largest first
    ranked = sorted(action_steps, key=lambda s: len(str(s.observations)), reverse=True)

    for step in ranked:
        if total_bytes <= max_bytes:
            break
        obs = str(step.observations)
        obs_len = len(obs)
        if obs_len <= 1000:
            continue

        if outputs_dir is not None:
            persisted = persist_large_output(
                identifier=f"step_{getattr(step, 'step_number', 'x')}",
                output=obs,
                outputs_dir=outputs_dir,
                # Seuil abaissé au seuil de troncature : ici on sait déjà
                # qu'il faut réduire ; persister dès qu'on touche le step.
                # Preview alignée sur le budget (~1000) pour que le bloc
                # persisted soit TOUJOURS plus court que l'original réduit.
                limit_chars=1000,
                preview_chars=1000,
            )
            # Le bloc persisted ne remplace l'original que s'il réduit
            # réellement (petits outputs : l'en-tête du bloc pourrait
            # dépasser le gain).
            if persisted != obs and len(persisted) < obs_len:
                step.observations = persisted
                total_bytes -= obs_len - len(persisted)
                continue

        # Truncate to a preview
        preview = obs[:1000] + "\n... [Output truncated due to context budget] ..."

        step.observations = preview
        total_bytes -= (obs_len - len(preview))


class CompactingCodeAgent(CodeAgent):
    """CodeAgent with dual-layer compaction to prevent context overflow.

    Implements the Event-Sourcing & Reducers patterns from qm and learn-claude-code.

    F-101 (Compaction v2) : le snip archive désormais les steps supprimés sur
    disque (``.transcripts/`` du run dir, cwd grâce à F-40) et les gros tool
    outputs sont persistés (``.task_outputs/tool-results/``) avant troncature.
    ``context_frame`` est le scratchpad claude-science : des notes de travail
    qui survivent à toutes les compactions (réinjectées dans le marqueur de
    snip, jamais snippées elles-mêmes).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Scratchpad frame (claude-science) : privé à ce nœud, survit au snip.
        self.context_frame: List[str] = []

    def write_memory_to_messages(self, summary_mode: bool = False):
        # Résolution des dossier d'archive (opt-out COMPACTION_ARCHIVE_ENABLED).
        # cwd = dossier du run (chdir F-40) → archives colocalisées avec les
        # livrables. Fail-open total : settings indisponible → pas d'archive.
        transcript_dir = None
        outputs_dir = None
        try:
            from .config import settings

            if settings.compaction_archive_enabled:
                base = _Path.cwd()
                transcript_dir = base / ".transcripts"
                outputs_dir = base / ".task_outputs" / "tool-results"
        except Exception:
            pass

        # 0. Visual Memory Purge: aggressively remove old images (1 image = ~5k tokens)
        apply_image_purge(self.memory)

        # 1. Snip (EN TÊTE, F-101) : archive les steps supprimés AVANT toute
        # réduction — l'archive JSONL contient les contenus originaux
        # (perte-zéro), pas des versions déjà tronquées.
        apply_snip_compact(
            self.memory, transcript_dir=transcript_dir, frame=self.context_frame
        )

        # 2. Budget: persist massive single outputs to disk, then truncate
        # (protects the current turn)
        apply_tool_result_budget(self.memory, outputs_dir=outputs_dir)

        # 3. Branch Summarization: summarize consecutive failed attempts
        self._apply_branch_summarization()

        # 4. File-State Compaction: prune obsolete reads if a file was modified
        self._apply_file_state_compact()

        # 5. Micro: trim old tool outputs (keeps the command, drops the big
        # output — réutilise les chemins persistés de la couche budget)
        apply_micro_compact(self.memory)

        # Proceed with standard message building
        return super().write_memory_to_messages(summary_mode)

    def _apply_branch_summarization(self):
        """L4: Branch Summarization for failed attempts.

        Groups consecutive failed ActionSteps into a single summarized step to preserve
        the learning ('I tried this and it failed') without the token cost of the full trace.
        """
        if not self.memory.steps:
            return

        new_steps = []
        failed_branch = []

        for step in self.memory.steps:
            if isinstance(step, ActionStep):
                # Detect errors (InterpreterError, AssertionError, etc.)
                is_error = getattr(step, "error", None) is not None or (
                    step.observations and "InterpreterError:" in str(step.observations)
                )

                if is_error:
                    failed_branch.append(step)
                    continue

            # If we reach a non-error step, flush the failed branch
            if len(failed_branch) > 1:
                summary_step = _synthetic_action_step(failed_branch[0].step_number)
                errors = []
                actions = []
                for s in failed_branch:
                    err = str(getattr(s, "error", "")) or str(s.observations)
                    errors.append(err.split("\\n")[0][:100])
                    code = str(getattr(s, "model_output", "") or getattr(s, "code_action", ""))
                    # Extract the python code block if it exists
                    import re
                    match = re.search(r"```python\\s*(.*?)\\s*```", code, re.DOTALL)
                    if match:
                        code_snippet = match.group(1).strip().replace("\\n", " ")[:150]
                    else:
                        code_snippet = code.replace("\\n", " ")[:150]
                    actions.append(f"`{code_snippet}`")

                actions_str = ", ".join(actions)
                summary_step.model_output = f"[Branch Summarization] Attempted {len(failed_branch)} actions which all resulted in errors. Failed code: {actions_str}. Learning: the previous approaches are invalid and must not be repeated."
                summary_step.observations = "Errors encountered: " + " | ".join(errors)
                new_steps.append(summary_step)
            elif len(failed_branch) == 1:
                new_steps.append(failed_branch[0])

            failed_branch = []
            new_steps.append(step)

        if len(failed_branch) > 1:
            summary_step = _synthetic_action_step(failed_branch[0].step_number)
            errors = []
            actions = []
            for s in failed_branch:
                err = str(getattr(s, "error", "")) or str(s.observations)
                errors.append(err.split("\\n")[0][:100])
                code = str(getattr(s, "model_output", "") or getattr(s, "code_action", ""))
                import re
                match = re.search(r"```python\\s*(.*?)\\s*```", code, re.DOTALL)
                if match:
                    code_snippet = match.group(1).strip().replace("\\n", " ")[:150]
                else:
                    code_snippet = code.replace("\\n", " ")[:150]
                actions.append(f"`{code_snippet}`")

            actions_str = ", ".join(actions)
            summary_step.model_output = f"[Branch Summarization] Attempted {len(failed_branch)} actions which all resulted in errors. Failed code: {actions_str}. Learning: the previous approaches are invalid and must not be repeated."
            summary_step.observations = "Errors encountered: " + " | ".join(errors)
            new_steps.append(summary_step)
        elif len(failed_branch) == 1:
            new_steps.append(failed_branch[0])

        self.memory.steps = new_steps

    def _apply_file_state_compact(self):
        """L5: File-State Compaction.

        Uses file state logic rather than purely chronological truncation.
        If we see a state mutation (write_file) or a terminal read (visit_webpage),
        older exploratory reads are considered obsolete context and are aggressively compacted.
        """
        mutation_seen = False

        # Traverse from newest to oldest
        for step in reversed(self.memory.steps):
            if not isinstance(step, ActionStep):
                continue

            code = getattr(step, "model_output", "") or getattr(step, "code_action", "")
            code = str(code)

            # If we see a mutation or major state capture, mark it
            if "write_file(" in code or "replace_file_content(" in code or "puppeteer_screenshot(" in code:
                mutation_seen = True
                continue

            # If a mutation was seen after this step, older reads are obsolete
            if mutation_seen and ("read_file(" in code or "visit_webpage(" in code or "list_console_messages(" in code):
                if step.observations and len(str(step.observations)) > 300:
                    step.observations = "[File-State Compaction: Output dropped. File state was mutated in a subsequent step.]"
