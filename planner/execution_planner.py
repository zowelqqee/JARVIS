"""Execution planner interface for JARVIS MVP."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types.command import Command
    from types.planned_command import PlannedCommand


def build_execution_plan(command: Command) -> PlannedCommand:
    """Build an ordered execution plan from a validated command."""
    raise NotImplementedError("Execution planning is not implemented in MVP skeleton.")

