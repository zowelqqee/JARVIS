"""Shared action execution result contract for JARVIS MVP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types.target import Target


@dataclass(slots=True)
class ActionError:
    """Error payload for failed desktop actions."""

    code: str
    message: str


@dataclass(slots=True)
class ActionResult:
    """Strict result shape produced by step execution."""

    action: str
    success: bool
    target: Target
    details: dict[str, Any] | None = None
    error: ActionError | None = None

