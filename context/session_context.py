"""Short-lived session context contract for JARVIS MVP."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types.command import Command
    from types.confirmation_request import ConfirmationResult
    from types.runtime_state import RuntimeState
    from types.step import StepStatus
    from types.target import Target


@dataclass(slots=True)
class SessionContext:
    """In-memory context used only for the active supervised session."""

    active_command: Command | None = None
    current_step_index: int | None = None
    step_statuses: dict[str, StepStatus] = field(default_factory=dict)
    runtime_state: RuntimeState | None = None
    last_resolved_targets: list[Target] = field(default_factory=list)
    recent_clarification_answer: str | None = None
    recent_confirmation_state: ConfirmationResult | None = None
    recent_workspace_context: str | None = None

