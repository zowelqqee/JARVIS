"""Runtime transition legality rules for JARVIS MVP."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types.runtime_state import RuntimeState


STATE_VALUES: frozenset[str] = frozenset(
    {
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
    }
)


ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "idle": frozenset({"parsing"}),
    "parsing": frozenset({"validating", "awaiting_clarification", "failed"}),
    "validating": frozenset({"planning", "awaiting_clarification", "failed"}),
    "awaiting_clarification": frozenset({"validating", "cancelled"}),
    "planning": frozenset({"executing", "failed"}),
    "executing": frozenset(
        {
            "executing",
            "awaiting_confirmation",
            "completed",
            "failed",
            "awaiting_clarification",
            "cancelled",
        }
    ),
    "awaiting_confirmation": frozenset({"executing", "cancelled", "failed"}),
    "completed": frozenset({"idle"}),
    "failed": frozenset({"idle"}),
    "cancelled": frozenset({"idle"}),
}


def normalize_state_value(state: RuntimeState | str) -> str:
    """Normalize enum-or-string runtime state input to a validated state value."""
    value = getattr(state, "value", state)
    if value not in STATE_VALUES:
        raise ValueError(f"Unknown runtime state: {value!r}")
    return value


def is_valid_transition(from_state: RuntimeState | str, to_state: RuntimeState | str) -> bool:
    """Return whether a runtime transition is allowed by the MVP state model."""
    current = normalize_state_value(from_state)
    next_state = normalize_state_value(to_state)
    return next_state in ALLOWED_TRANSITIONS[current]


def assert_valid_transition(from_state: RuntimeState | str, to_state: RuntimeState | str) -> None:
    """Raise an error when a runtime transition is not legal."""
    current = normalize_state_value(from_state)
    next_state = normalize_state_value(to_state)
    if next_state not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"Invalid runtime transition: {current!r} -> {next_state!r}")


def transition_runtime(state: RuntimeState | str, event: RuntimeState | str) -> str:
    """Return the next runtime state value when the transition is legal."""
    assert_valid_transition(state, event)
    return normalize_state_value(event)

