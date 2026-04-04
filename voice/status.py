"""Session-aware status helpers for the current CLI voice path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from voice.flags import build_voice_mode_status
from voice.telemetry import VoiceTelemetrySnapshot


@dataclass(frozen=True, slots=True)
class VoiceSessionStatus:
    """Compact operator-facing view of the current CLI voice session."""

    speak_enabled: bool
    continuous_mode_enabled: bool
    advanced_follow_up_default_off: bool
    max_auto_follow_up_turns: int
    short_answer_follow_up_requires_speech: bool
    telemetry_capture_attempts: int
    telemetry_dispatch_count: int
    telemetry_tts_attempts: int
    telemetry_max_follow_up_chain_length: int
    telemetry_follow_up_limit_hit_count: int
    telemetry_follow_up_relisten_count: int
    telemetry_follow_up_dismiss_count: int
    telemetry_speech_interrupt_count: int
    telemetry_speech_interrupt_for_capture_count: int


def build_voice_session_status(
    *,
    speak_enabled: bool,
    telemetry_snapshot: VoiceTelemetrySnapshot | None,
    environ: Mapping[str, str] | None = None,
) -> VoiceSessionStatus:
    """Build one current-session voice status summary for CLI helpers."""
    mode_status = build_voice_mode_status(environ=environ)
    snapshot = telemetry_snapshot or _empty_telemetry_snapshot()
    return VoiceSessionStatus(
        speak_enabled=bool(speak_enabled),
        continuous_mode_enabled=mode_status.continuous_mode_enabled,
        advanced_follow_up_default_off=mode_status.advanced_follow_up_default_off,
        max_auto_follow_up_turns=mode_status.max_auto_follow_up_turns,
        short_answer_follow_up_requires_speech=mode_status.short_answer_follow_up_requires_speech,
        telemetry_capture_attempts=snapshot.capture_attempts,
        telemetry_dispatch_count=snapshot.dispatch_count,
        telemetry_tts_attempts=snapshot.tts_attempts,
        telemetry_max_follow_up_chain_length=snapshot.max_follow_up_chain_length,
        telemetry_follow_up_limit_hit_count=snapshot.follow_up_limit_hit_count,
        telemetry_follow_up_relisten_count=snapshot.follow_up_relisten_count,
        telemetry_follow_up_dismiss_count=snapshot.follow_up_dismiss_count,
        telemetry_speech_interrupt_count=snapshot.speech_interrupt_count,
        telemetry_speech_interrupt_for_capture_count=snapshot.speech_interrupt_for_capture_count,
    )


def format_voice_session_status(status: VoiceSessionStatus) -> str:
    """Render one current-session voice status summary for operators."""
    return "\n".join(
        [
            "JARVIS Voice Status",
            f"speech output enabled: {'yes' if status.speak_enabled else 'no'}",
            f"continuous mode enabled: {'yes' if status.continuous_mode_enabled else 'no'}",
            f"advanced follow-up default off: {'yes' if status.advanced_follow_up_default_off else 'no'}",
            f"max auto follow-up turns: {status.max_auto_follow_up_turns}",
            f"short-answer follow-up requires speech: {'yes' if status.short_answer_follow_up_requires_speech else 'no'}",
            f"telemetry capture attempts: {status.telemetry_capture_attempts}",
            f"telemetry dispatch count: {status.telemetry_dispatch_count}",
            f"telemetry tts attempts: {status.telemetry_tts_attempts}",
            f"telemetry max follow-up chain length: {status.telemetry_max_follow_up_chain_length}",
            f"telemetry follow-up limit hit count: {status.telemetry_follow_up_limit_hit_count}",
            f"telemetry follow-up relisten count: {status.telemetry_follow_up_relisten_count}",
            f"telemetry follow-up dismiss count: {status.telemetry_follow_up_dismiss_count}",
            f"telemetry speech interrupt count: {status.telemetry_speech_interrupt_count}",
            f"telemetry speech interrupt for capture count: {status.telemetry_speech_interrupt_for_capture_count}",
        ]
    )


def _empty_telemetry_snapshot() -> VoiceTelemetrySnapshot:
    return VoiceTelemetrySnapshot(
        capture_attempts=0,
        dispatch_count=0,
        tts_attempts=0,
        recognition_latency_ms=None,
        empty_recognition_rate=0.0,
        clarification_rate=0.0,
        confirmation_completion_rate=0.0,
        retry_rate=0.0,
        tts_failure_rate=0.0,
        average_spoken_response_length=0.0,
        follow_up_relisten_count=0,
        follow_up_dismiss_count=0,
        max_follow_up_chain_length=0,
        follow_up_limit_hit_count=0,
        speech_interrupt_count=0,
        speech_interrupt_for_capture_count=0,
    )
