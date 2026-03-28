"""Single-turn voice-session helpers for the current CLI MVP."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from input.voice_input import VoiceInputError
from voice.asr_service import capture_voice_turn
from voice.language import detect_spoken_locale

_VALID_SESSION_TRANSITIONS = {
    "idle": frozenset({"listening"}),
    "listening": frozenset({"transcribing", "error"}),
    "transcribing": frozenset({"routing", "error"}),
    "routing": frozenset(),
    "error": frozenset(),
}


@dataclass(frozen=True, slots=True)
class VoiceTurn:
    """Prepared single-turn voice payload for CLI routing."""

    raw_transcript: str
    normalized_transcript: str
    detected_locale: str
    locale_hint: str | None = None
    recognition_status: str = "recognized"
    lifecycle_state: str = "routing"
    interaction_input: str | None = None
    retryable: bool = True

    def __post_init__(self) -> None:
        if self.interaction_input is None:
            object.__setattr__(self, "interaction_input", self.normalized_transcript)

    @property
    def normalized_text(self) -> str:
        """Keep compatibility with the earlier voice-capture contract."""
        return self.normalized_transcript


class SingleTurnVoiceSession:
    """Track one explicit CLI voice turn through a tiny lifecycle."""

    def __init__(self) -> None:
        self.current_state = "idle"

    def capture_turn(
        self,
        *,
        timeout_seconds: float,
        preferred_locales: Sequence[str] | None = None,
    ) -> VoiceTurn:
        self._transition_to("listening")
        try:
            captured_turn = capture_voice_turn(
                timeout_seconds=timeout_seconds,
                preferred_locales=preferred_locales,
            )
        except VoiceInputError:
            self._transition_to("error")
            raise

        self._transition_to("transcribing")
        detected_locale = captured_turn.locale_hint or detect_spoken_locale(captured_turn.raw_transcript)
        self._transition_to("routing")
        return VoiceTurn(
            raw_transcript=captured_turn.raw_transcript,
            normalized_transcript=captured_turn.normalized_text,
            detected_locale=detected_locale,
            locale_hint=captured_turn.locale_hint,
        )

    def _transition_to(self, next_state: str) -> None:
        allowed_states = _VALID_SESSION_TRANSITIONS.get(self.current_state, frozenset())
        if next_state not in allowed_states:
            raise ValueError(f"Invalid voice session transition: {self.current_state} -> {next_state}")
        self.current_state = next_state


def capture_cli_voice_turn(
    *,
    timeout_seconds: float,
    preferred_locales: Sequence[str] | None = None,
) -> VoiceTurn:
    """Capture one prepared voice turn for the current CLI shell layer."""
    return SingleTurnVoiceSession().capture_turn(
        timeout_seconds=timeout_seconds,
        preferred_locales=preferred_locales,
    )
