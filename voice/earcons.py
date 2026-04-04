"""Minimal earcon provider contracts for staged CLI voice UX."""

from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class EarconResult:
    """Outcome of one earcon playback attempt."""

    ok: bool
    attempted: bool = True
    error_code: str | None = None
    error_message: str | None = None


@runtime_checkable
class EarconProvider(Protocol):
    """Minimal provider interface for short non-verbal voice cues."""

    def play(self, event: str | None) -> EarconResult:
        """Play one earcon cue for the requested event."""


class TerminalBellEarconProvider:
    """Best-effort local earcon provider using the terminal bell character."""

    def play(self, event: str | None) -> EarconResult:
        del event
        try:
            sys.stdout.write("\a")
            sys.stdout.flush()
        except Exception as exc:
            return EarconResult(ok=False, error_code="EARCON_FAILED", error_message=str(exc))
        return EarconResult(ok=True)


def build_default_earcon_provider() -> EarconProvider:
    """Build the default local earcon backend for CLI voice UX."""
    return TerminalBellEarconProvider()
