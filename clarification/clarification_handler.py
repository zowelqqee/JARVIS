"""Clarification interfaces for JARVIS MVP."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types.clarification_request import ClarificationRequest
    from types.command import Command
    from types.jarvis_error import JarvisError


def build_clarification(validation_issue: JarvisError, command: Command) -> ClarificationRequest:
    """Create one minimal clarification request for a blocked command."""
    raise NotImplementedError("Clarification building is not implemented in MVP skeleton.")


def apply_clarification(command: Command, user_reply: str) -> Command:
    """Apply a user clarification reply to blocked command fields."""
    raise NotImplementedError("Clarification application is not implemented in MVP skeleton.")

