"""Shared validator output contract for JARVIS MVP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types.command import Command
    from types.jarvis_error import JarvisError


@dataclass(slots=True)
class ValidationResult:
    """Validation outcome with either validated command data or a blocking issue."""

    is_valid: bool
    validated_command: Command | None = None
    issue: JarvisError | None = None

