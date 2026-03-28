"""Text-to-speech provider contracts for JARVIS voice output."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SpeechUtterance:
    """Structured spoken payload prepared by the speech presenter."""

    text: str
    locale: str | None = None


@dataclass(frozen=True, slots=True)
class TTSResult:
    """Outcome of one text-to-speech attempt."""

    ok: bool
    attempted: bool = True
    error_code: str | None = None
    error_message: str | None = None


@runtime_checkable
class TTSProvider(Protocol):
    """Minimal provider interface for speaking a prepared utterance."""

    def speak(self, utterance: SpeechUtterance | None) -> TTSResult:
        """Speak one prepared utterance."""


def build_default_tts_provider() -> TTSProvider:
    """Build the default local TTS backend for the current CLI."""
    from voice.tts_macos import MacOSTTSProvider

    return MacOSTTSProvider()
