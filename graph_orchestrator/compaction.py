import os
import time as _time
from pathlib import Path
from typing import Any

from smolagents import CodeAgent, AgentMemory
from smolagents.agents import ActionStep, TaskStep
from smolagents.monitoring import Timing


def _synthetic_action_step(step_number: int) -> ActionStep:
    """Build a minimal ActionStep for compaction summaries.

    smolagents made ``timing`` a required positional argument of
    ``ActionStep.__init__`` (it used to default to None). The synthetic
    steps created during snip/branch summarization carry no real timing
    information, so we fabricate a zero-duration ``Timing`` to satisfy the
    contract and avoid:

        ActionStep.__init__() missing 1 required positional argument: 'timing'
    """
    now = _time.time()
    return ActionStep(step_number=step_number, timing=Timing(start_time=now, end_time=now))

def apply_micro_compact(memory: AgentMemory, keep_recent: int = 3, threshold: int = 150):
    """L2: Replace old large tool results with a placeholder."""
    action_steps = [step for step in memory.steps if isinstance(step, ActionStep)]
    if len(action_steps) <= keep_recent:
        return
    
    # Process older steps
    for step in action_steps[:-keep_recent]:
        if step.observations and len(str(step.observations)) > threshold:
            step.observations = "[Compacted: Earlier tool result truncated. Re-run if needed.]"
        # Also clear images if any to save token space
        if hasattr(step, "observations_images") and step.observations_images:
            step.observations_images = []

def apply_snip_compact(memory: AgentMemory, max_steps: int = 15):
    """L1: Trim middle steps if the history is getting too long."""
    # steps typically start with TaskStep, followed by ActionSteps
    if len(memory.steps) <= max_steps:
        return
    
    keep_head = 3  # Keep TaskStep + first few ActionSteps to remember context
    keep_tail = max_steps - keep_head
    
    if keep_head >= len(memory.steps) - keep_tail:
        return
    
    head_steps = memory.steps[:keep_head]
    tail_steps = memory.steps[-keep_tail:]
    
    snipped_count = len(memory.steps) - (keep_head + keep_tail)
    
    # Create a synthetic ActionStep that holds the "snipped" notice
    snip_step = _synthetic_action_step(head_steps[-1].step_number + 1)
    snip_step.model_output = f"[Snipped {snipped_count} intermediate steps to preserve context window]"
    
    memory.steps = head_steps + [snip_step] + tail_steps

def apply_tool_result_budget(memory: AgentMemory, max_bytes: int = 80000):
    """L3: Truncate extremely large tool outputs in the most recent steps."""
    action_steps = [step for step in memory.steps if isinstance(step, ActionStep) and step.observations]
    
    total_bytes = sum(len(str(step.observations)) for step in action_steps)
    if total_bytes <= max_bytes:
        return
        
    # Sort steps by observation size, largest first
    ranked = sorted(action_steps, key=lambda s: len(str(s.observations)), reverse=True)
    
    for step in ranked:
        if total_bytes <= max_bytes:
            break
        obs_len = len(str(step.observations))
        if obs_len <= 1000:
            continue
            
        # Truncate to a preview
        preview = str(step.observations)[:1000] + "\n... [Output truncated due to context budget] ..."
        
        step.observations = preview
        total_bytes -= (obs_len - len(preview))


class CompactingCodeAgent(CodeAgent):
    """CodeAgent with dual-layer compaction to prevent context overflow.
    
    Implements the Event-Sourcing & Reducers patterns from qm and learn-claude-code.
    """
    def write_memory_to_messages(self, summary_mode: bool = False):
        # 1. Budget: truncate massive single outputs (protects the current turn)
        apply_tool_result_budget(self.memory)
        
        # 2. Branch Summarization: summarize consecutive failed attempts
        self._apply_branch_summarization()
        
        # 3. File-State Compaction: prune obsolete reads if a file was modified
        self._apply_file_state_compact()
        
        # 4. Micro: trim old tool outputs (keeps the command, drops the big output)
        apply_micro_compact(self.memory)
        
        # 5. Snip: trim the middle of the conversation if > 15 steps
        apply_snip_compact(self.memory)
        
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
                summary_step.model_output = f"[Branch Summarization] Attempted {len(failed_branch)} actions which all resulted in errors. Learning: the previous approaches are invalid and must not be repeated."
                errors = []
                for s in failed_branch:
                    err = str(getattr(s, "error", "")) or str(s.observations)
                    # Keep only the first line of the error to save tokens
                    errors.append(err.split("\\n")[0][:100])
                summary_step.observations = "Errors encountered: " + ", ".join(errors)
                new_steps.append(summary_step)
            elif len(failed_branch) == 1:
                new_steps.append(failed_branch[0])
                
            failed_branch = []
            new_steps.append(step)
            
        if len(failed_branch) > 1:
            summary_step = _synthetic_action_step(failed_branch[0].step_number)
            summary_step.model_output = f"[Branch Summarization] Attempted {len(failed_branch)} actions which all resulted in errors. Learning: the previous approaches are invalid and must not be repeated."
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
