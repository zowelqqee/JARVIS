"""Shared execution step contract for JARVIS MVP."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types.target import Target


class StepStatus(str, Enum):
    """Allowed step lifecycle statuses."""

    PENDING = "pending"
    EXECUTING = "executing"
    DONE = "done"
    FAILED = "failed"


@dataclass(slots=True)
class Step:
    """One executable desktop step in ordered command flow."""

    id: str
    action: str
    target: Target
    parameters: dict[str, Any] | None = None
    status: StepStatus = StepStatus.PENDING
    requires_confirmation: bool = False

