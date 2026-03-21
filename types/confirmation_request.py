"""Shared confirmation contracts for JARVIS MVP."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types.target import Target


class ConfirmationBoundary(str, Enum):
    """Supported confirmation boundary types."""

    COMMAND = "command"
    STEP = "step"


class ConfirmationResult(str, Enum):
    """Confirmation outcomes allowed by MVP."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


@dataclass(slots=True)
class ConfirmationRequest:
    """Minimal confirmation payload for command-level or step-level gates."""

    boundary: ConfirmationBoundary
    message: str
    targets: list[Target] = field(default_factory=list)
    step_id: str | None = None
    status: ConfirmationResult = ConfirmationResult.PENDING

