"""Shared runtime state contract for JARVIS MVP."""

from __future__ import annotations

from enum import Enum


class RuntimeState(str, Enum):
    """Allowed runtime lifecycle states."""

    IDLE = "idle"
    PARSING = "parsing"
    VALIDATING = "validating"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    PLANNING = "planning"
    EXECUTING = "executing"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

