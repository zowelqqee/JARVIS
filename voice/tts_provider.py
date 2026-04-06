"""Text-to-speech provider contracts for JARVIS voice output."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable

from voice.tts_models import BackendCapabilities, VoiceDescriptor


@dataclass(frozen=True, slots=True)
class SpeechUtterance:
    """Structured spoken payload prepared by the speech presenter."""

    text: str
    locale: str | None = None
    voice_profile: str | None = None
    voice_id: str | None = None
    rate: float | None = None
    pitch: float | None = None
    volume: float | None = None
    style_hint: str | None = None
    interruptible: bool = True


@dataclass(frozen=True, slots=True)
class TTSResult:
    """Outcome of one text-to-speech attempt."""

    ok: bool
    attempted: bool = True
    error_code: str | None = None
    error_message: str | None = None
    backend_name: str | None = None
    voice_id: str | None = None


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


@runtime_checkable
class TTSBackend(InterruptibleTTSProvider, Protocol):
    """Expanded backend contract used by the cross-platform manager."""

    def list_voices(self, locale_hint: str | None = None) -> list[VoiceDescriptor]:
        """Return native voices visible to this backend."""

    def resolve_voice(self, profile: str | None, locale: str | None = None) -> VoiceDescriptor | None:
        """Resolve one product profile to a backend-native voice."""

    def is_available(self) -> bool:
        """Return whether the backend is available in the current runtime."""

    def capabilities(self) -> BackendCapabilities:
        """Return structured capability metadata for the backend."""


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


def build_default_tts_provider(*, environ: Mapping[str, str] | None = None) -> TTSProvider:
    """Build the default local TTS backend for the current CLI."""
    from voice.tts_manager import build_default_tts_manager

    return build_default_tts_manager(environ=environ)
