"""Half-duplex audio policy helpers for the current CLI voice layer."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator

_VALID_AUDIO_TRANSITIONS = {
    "idle": frozenset({"listening", "speaking"}),
    "listening": frozenset({"idle"}),
    "speaking": frozenset({"idle"}),
}


class AudioPolicyError(RuntimeError):
    """Raised when the current voice layer tries to overlap listen/speak phases."""


class HalfDuplexAudioPolicy:
    """Prevent simultaneous listening and speaking in the current MVP."""

    def __init__(self) -> None:
        self.current_state = "idle"

    @contextmanager
    def capture_phase(self) -> Iterator[None]:
        self._transition_to("listening")
        try:
            yield
        finally:
            if self.current_state == "listening":
                self._transition_to("idle")

    @contextmanager
    def speaking_phase(self) -> Iterator[None]:
        self._transition_to("speaking")
        try:
            yield
        finally:
            if self.current_state == "speaking":
                self._transition_to("idle")

    def stop_speaking_for_capture(self, *, stop_active_speech: Callable[[], bool] | None = None) -> bool:
        """Interrupt active speech before a new capture phase begins."""
        if self.current_state != "speaking":
            return False
        if stop_active_speech is None:
            raise AudioPolicyError("Cannot start capture while speaking.")
        if not bool(stop_active_speech()):
            raise AudioPolicyError("Cannot interrupt active speech for capture.")
        self.current_state = "idle"
        return True

    def _transition_to(self, next_state: str) -> None:
        allowed_states = _VALID_AUDIO_TRANSITIONS.get(self.current_state, frozenset())
        if next_state not in allowed_states:
            raise AudioPolicyError(f"Invalid audio transition: {self.current_state} -> {next_state}")
        self.current_state = next_state


def build_default_audio_policy() -> HalfDuplexAudioPolicy:
    """Build the default local half-duplex policy for CLI voice I/O."""
    return HalfDuplexAudioPolicy()
