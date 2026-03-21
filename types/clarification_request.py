"""Shared clarification request contract for JARVIS MVP."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ClarificationRequest:
    """Minimal clarification payload used to unblock execution."""

    question: str
    options: list[str] | None = None

