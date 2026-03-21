"""Shared clarification request contract for JARVIS MVP."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ClarificationRequest:
    """Minimal clarification payload used to unblock execution."""

    message: str
    code: str
    options: list[str] | None = None
