"""Runtime state machine contracts for JARVIS MVP."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types.runtime_state import RuntimeState


ALLOWED_RUNTIME_STATES: tuple[str, ...] = (
    "idle",
    "parsing",
    "validating",
    "awaiting_clarification",
    "planning",
    "executing",
    "awaiting_confirmation",
    "completed",
    "failed",
    "cancelled",
)


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "idle": {"parsing"},
    "parsing": {"validating", "awaiting_clarification", "failed"},
    "validating": {"planning", "awaiting_clarification", "failed"},
    "awaiting_clarification": {"validating", "cancelled"},
    "planning": {"executing", "failed"},
    "executing": {
        "executing",
        "awaiting_confirmation",
        "completed",
        "failed",
        "awaiting_clarification",
        "cancelled",
    },
    "awaiting_confirmation": {"executing", "cancelled", "failed"},
    "completed": {"idle"},
    "failed": {"idle"},
    "cancelled": {"idle"},
}


def is_allowed_transition(current_state: str, next_state: str) -> bool:
    """Return whether the given runtime transition is permitted by MVP rules."""
    return next_state in ALLOWED_TRANSITIONS.get(current_state, set())


def transition_runtime(state: RuntimeState, event: str) -> RuntimeState:
    """Transition runtime state from one event token."""
    raise NotImplementedError("Runtime transition handling is not implemented in MVP skeleton.")

