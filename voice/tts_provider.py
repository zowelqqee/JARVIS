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


@runtime_checkable
class InterruptibleTTSProvider(TTSProvider, Protocol):
    """Optional contract for local TTS backends that can stop active speech."""

    def stop(self) -> bool:
        """Stop the current speech attempt, if one is active."""


def stop_speech_if_supported(tts_provider: TTSProvider | None) -> bool:
    """Stop active speech only when the concrete provider exposes a real stop hook."""
    if tts_provider is None:
        return False
    stop_method = getattr(type(tts_provider), "stop", None)
    if not callable(stop_method):
        return False
    try:
        return bool(stop_method(tts_provider))
    except Exception:
        return False


def build_default_tts_provider() -> TTSProvider:
    """Build the default local TTS backend for the current CLI."""
    from voice.tts_macos import MacOSTTSProvider

    return MacOSTTSProvider()
