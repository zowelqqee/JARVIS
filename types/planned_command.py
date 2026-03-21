"""Shared planned command contract for JARVIS MVP."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types.command import Command
    from types.confirmation_request import ConfirmationRequest
    from types.step import Step


@dataclass(slots=True)
class PlannedCommand:
    """Validated command plus ordered execution plan metadata."""

    command: Command
    execution_steps: list[Step] = field(default_factory=list)
    status_message: str = ""
    confirmation_boundaries: list[ConfirmationRequest] | None = None
