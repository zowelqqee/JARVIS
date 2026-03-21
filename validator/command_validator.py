"""Command validator interface for JARVIS MVP."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types.command import Command
    from types.validation_result import ValidationResult


def validate_command(command: Command) -> ValidationResult:
    """Validate a preliminary command against MVP runtime rules."""
    raise NotImplementedError("Command validation is not implemented in MVP skeleton.")

