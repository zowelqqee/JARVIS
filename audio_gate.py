from __future__ import annotations

from dataclasses import dataclass
import time


@dataclass
class AudioTurnGate:
    reopen_grace_seconds: float = 0.35
    drain_grace_seconds: float = 0.45
    assistant_turn_active: bool = False
    mic_resume_after: float = 0.0
    last_audio_chunk_at: float = 0.0

    def note_output_audio(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self.assistant_turn_active = True
        self.last_audio_chunk_at = now
        self.mic_resume_after = max(self.mic_resume_after, now + self.reopen_grace_seconds)

    def finish_output_turn(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self.assistant_turn_active = False
        self.mic_resume_after = now + self.reopen_grace_seconds

    def reset(self) -> None:
        self.assistant_turn_active = False
        self.mic_resume_after = 0.0
        self.last_audio_chunk_at = 0.0

    def mic_input_blocked(self, is_speaking: bool, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        return is_speaking or self.assistant_turn_active or now < self.mic_resume_after

    def playback_drain_elapsed(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        if self.last_audio_chunk_at <= 0:
            return True
        return (now - self.last_audio_chunk_at) >= self.drain_grace_seconds
