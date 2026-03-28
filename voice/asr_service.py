"""High-level one-shot ASR orchestration for CLI voice turns."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from input import voice_normalization
from input.voice_input import capture_voice_input
from voice.language import detect_spoken_locale


@dataclass(frozen=True, slots=True)
class VoiceCaptureTurn:
    """Structured result for one captured voice turn."""

    raw_transcript: str
    normalized_text: str
    locale_hint: str | None = None


def capture_voice_turn(
    *,
    timeout_seconds: float,
    preferred_locales: Sequence[str] | None = None,
) -> VoiceCaptureTurn:
    """Capture one spoken turn and attach normalization plus coarse locale hint."""
    raw_transcript = capture_voice_input(
        timeout_seconds=timeout_seconds,
        preferred_locales=preferred_locales,
    )
    normalized_text = voice_normalization.normalize_voice_command(raw_transcript)
    return VoiceCaptureTurn(
        raw_transcript=raw_transcript,
        normalized_text=normalized_text,
        locale_hint=_voice_locale_hint(raw_transcript),
    )


def _voice_locale_hint(raw_transcript: str) -> str | None:
    """Keep locale hints only for non-default spoken rendering paths."""
    detected_locale = detect_spoken_locale(raw_transcript)
    if detected_locale.startswith("ru"):
        return detected_locale
    return None
