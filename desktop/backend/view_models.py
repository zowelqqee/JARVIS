from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class PendingPrompt:
    """Represents a pending clarification or confirmation request."""
    kind: str           # "confirmation" | "clarification"
    message: str
    options: list[str] = field(default_factory=list)


@dataclass
class PanelState:
    """
    Single flat state object consumed by all panel sections.

    Section mapping:
      Section 2 (State Row)      : mode + runtime_state
      Section 3 (Current Action) : current_action_text
      Section 4 (Prompt Zone)    : pending_prompt (None = hidden)
      Section 5 (Last Exchange)  : last_user + last_vector
      Section 6 (Input Bar)      : runtime_state (for disabled/placeholder logic)
    """

    # State Row chips
    mode: str = "IDLE"               # COMMAND | QUESTION | VOICE | IDLE
    runtime_state: str = "idle"      # idle | listening | thinking | executing |
                                     # answering | awaiting_clarification |
                                     # awaiting_confirmation | failed

    # Current Action text (always shown, content depends on runtime_state)
    current_action_text: str = "Ready."

    # Prompt Zone — None means the zone is not rendered
    pending_prompt: PendingPrompt | None = None

    # Last Exchange Strip
    last_user: str | None = None
    last_vector: str | None = None

    # Auxiliary
    speaking: bool = False
    command_summary: str | None = None
