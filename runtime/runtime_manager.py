"""Runtime manager interface for JARVIS MVP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from context.session_context import SessionContext
    from types.command import Command
    from types.runtime_state import RuntimeState


@dataclass(slots=True)
class RuntimeManager:
    """Minimal runtime manager shape for supervised command lifecycle."""

    current_state: RuntimeState | None = None
    active_command: Command | None = None
    session_context: SessionContext | None = None

    def handle_event(self, event: str) -> RuntimeState:
        """Apply one runtime event to the active state machine."""
        raise NotImplementedError("Runtime management is not implemented in MVP skeleton.")

