"""Feature flags for staged voice-rollout behavior."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping

_ENV_CONTINUOUS_MODE = "JARVIS_VOICE_CONTINUOUS_MODE"
_ENV_EARCONS = "JARVIS_VOICE_EARCONS"
_AUTO_FOLLOW_UP_TURN_LIMIT = 2


@dataclass(frozen=True, slots=True)
class VoiceModeStatus:
    """Operator-facing summary of the current bounded voice-conversation mode."""

    advanced_follow_up_flag: str
    continuous_mode_enabled: bool
    earcons_flag: str
    earcons_enabled: bool
    advanced_follow_up_default_off: bool
    max_auto_follow_up_turns: int
    short_answer_follow_up_requires_speech: bool


def continuous_voice_mode_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether advanced multi-turn voice follow-up is enabled."""
    env = os.environ if environ is None else environ
    return _parse_bool(env.get(_ENV_CONTINUOUS_MODE), default=False)


def max_auto_follow_up_turns(environ: Mapping[str, str] | None = None) -> int:
    """Return the current bounded follow-up budget for the explicit voice shell path."""
    return _AUTO_FOLLOW_UP_TURN_LIMIT if continuous_voice_mode_enabled(environ=environ) else 0


def voice_earcons_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether optional voice earcons are enabled for the current CLI session."""
    env = os.environ if environ is None else environ
    return _parse_bool(env.get(_ENV_EARCONS), default=False)


def build_voice_mode_status(environ: Mapping[str, str] | None = None) -> VoiceModeStatus:
    """Build a concise summary of the current bounded voice-conversation mode."""
    return VoiceModeStatus(
        advanced_follow_up_flag=_ENV_CONTINUOUS_MODE,
        continuous_mode_enabled=continuous_voice_mode_enabled(environ=environ),
        earcons_flag=_ENV_EARCONS,
        earcons_enabled=voice_earcons_enabled(environ=environ),
        advanced_follow_up_default_off=not continuous_voice_mode_enabled(environ={}),
        max_auto_follow_up_turns=max_auto_follow_up_turns(environ=environ),
        short_answer_follow_up_requires_speech=True,
    )


def format_voice_mode_status(status: VoiceModeStatus) -> str:
    """Render one compact operator-facing summary of the current voice mode."""
    return "\n".join(
        [
            "JARVIS Voice Mode",
            f"advanced follow-up flag: {status.advanced_follow_up_flag}",
            f"continuous mode enabled: {'yes' if status.continuous_mode_enabled else 'no'}",
            f"earcons flag: {status.earcons_flag}",
            f"earcons enabled: {'yes' if status.earcons_enabled else 'no'}",
            f"advanced follow-up default off: {'yes' if status.advanced_follow_up_default_off else 'no'}",
            f"max auto follow-up turns: {status.max_auto_follow_up_turns}",
            f"short-answer follow-up requires speech: {'yes' if status.short_answer_follow_up_requires_speech else 'no'}",
        ]
    )


def _parse_bool(raw_value: str | None, *, default: bool) -> bool:
    if raw_value is None:
        return default
    normalized = str(raw_value or "").strip().lower()
    if not normalized:
        return default
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default
