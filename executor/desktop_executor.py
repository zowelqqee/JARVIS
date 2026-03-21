"""Desktop executor interface for JARVIS MVP."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types.action_result import ActionResult
    from types.step import Step


def execute_step(step: Step) -> ActionResult:
    """Execute one validated step and return a strict action result."""
    raise NotImplementedError("Step execution is not implemented in MVP skeleton.")

