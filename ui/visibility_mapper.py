"""Visibility mapping interfaces for JARVIS MVP runtime state."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from types.clarification_request import ClarificationRequest
    from types.command import Command
    from types.confirmation_request import ConfirmationRequest
    from types.jarvis_error import JarvisError
    from types.runtime_state import RuntimeState
    from types.step import Step


class VisibilityPayload(TypedDict, total=False):
    """Minimal user-visible runtime payload shape."""

    command_summary: str
    runtime_state: str
    current_step: str
    completed_steps: list[str]
    blocked_reason: str
    confirmation_prompt: str
    failure_message: str
    completion_result: str
    can_cancel: bool


_CANCEL_ENABLED_STATES: set[str] = {
    "parsing",
    "validating",
    "planning",
    "executing",
    "awaiting_clarification",
    "awaiting_confirmation",
}


def can_show_cancel(state: RuntimeState) -> bool:
    """Return whether cancel control should be visible for the runtime state."""
    state_value = getattr(state, "value", str(state))
    return state_value in _CANCEL_ENABLED_STATES


def map_visibility(
    state: RuntimeState,
    command: Command | None = None,
    current_step: Step | None = None,
    clarification: ClarificationRequest | None = None,
    confirmation: ConfirmationRequest | None = None,
    error: JarvisError | None = None,
) -> VisibilityPayload:
    """Map runtime truth into a minimal user-visible payload."""
    raise NotImplementedError("Visibility mapping is not implemented in MVP skeleton.")

