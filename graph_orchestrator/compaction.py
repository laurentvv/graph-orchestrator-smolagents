import os
from pathlib import Path
from typing import Any

from smolagents import CodeAgent, AgentMemory
from smolagents.agents import ActionStep, TaskStep

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
    snip_step = ActionStep(step_number=head_steps[-1].step_number + 1)
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
        
        # 2. Micro: trim old tool outputs (keeps the command, drops the big output)
        apply_micro_compact(self.memory)
        
        # 3. Snip: trim the middle of the conversation if > 15 steps
        apply_snip_compact(self.memory)
        
        # Proceed with standard message building
        return super().write_memory_to_messages(summary_mode)
