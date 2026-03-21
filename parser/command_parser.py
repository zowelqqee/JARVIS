"""Command parser interface for JARVIS MVP."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from context.session_context import SessionContext
    from types.command import Command


def parse_command(raw_input: str, session_context: SessionContext | None) -> Command:
    """Parse normalized raw input into a preliminary Command."""
    raise NotImplementedError("Command parsing is not implemented in MVP skeleton.")

