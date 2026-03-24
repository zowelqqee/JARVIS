"""Shared interaction-kind vocabulary for top-level dual-mode handling."""

from __future__ import annotations

from enum import Enum


class InteractionKind(str, Enum):
    """Stable interaction vocabulary shared across routing, runtime, and UI."""

    COMMAND = "command"
    QUESTION = "question"
    CLARIFICATION = "clarification"

    def __str__(self) -> str:
        return self.value


def interaction_kind_value(kind: InteractionKind | str) -> str:
    """Return the stable string value for an interaction kind."""
    return str(getattr(kind, "value", kind))
