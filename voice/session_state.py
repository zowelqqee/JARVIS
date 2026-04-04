"""Current-session voice event helpers for the CLI shell."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VoiceSessionEvent:
    """One current-session voice event for operator-facing inspection."""

    event_kind: str
    raw_transcript: str
    normalized_transcript: str
    detected_locale: str | None
    interaction_kind: str | None = None
    lifecycle_state: str | None = None
    follow_up_reason: str | None = None
    interaction_summary: str | None = None
    spoken_response: str | None = None
    control_action: str | None = None
    interruption_reason: str | None = None


class VoiceSessionState:
    """Track the last voice event observed in the current CLI session."""

    def __init__(self) -> None:
        self._last_event: VoiceSessionEvent | None = None

    @property
    def last_event(self) -> VoiceSessionEvent | None:
        """Return the most recent voice event when present."""
        return self._last_event

    def clear(self) -> None:
        """Forget the current-session last voice event."""
        self._last_event = None

    def record_dispatch(self, voice_turn: object) -> None:
        """Store the last dispatched voice turn for operator inspection."""
        self._last_event = VoiceSessionEvent(
            event_kind="dispatch",
            raw_transcript=str(getattr(voice_turn, "raw_transcript", "") or ""),
            normalized_transcript=str(
                getattr(voice_turn, "normalized_text", None)
                or getattr(voice_turn, "normalized_transcript", "")
                or ""
            ),
            detected_locale=_voice_locale(voice_turn),
            interaction_kind=str(getattr(voice_turn, "interaction_kind", "") or "").strip() or None,
            lifecycle_state=str(getattr(voice_turn, "lifecycle_state", "") or "").strip() or None,
            follow_up_reason=str(getattr(voice_turn, "follow_up_reason", "") or "").strip() or None,
            interaction_summary=str(getattr(voice_turn, "interaction_summary", "") or "").strip() or None,
            spoken_response=str(getattr(voice_turn, "spoken_response", "") or "").strip() or None,
        )

    def record_control(self, prior_turn: object, follow_up_turn: object, *, action: str) -> None:
        """Store the last shell-level follow-up control event."""
        self._last_event = VoiceSessionEvent(
            event_kind="control",
            raw_transcript=str(getattr(follow_up_turn, "raw_transcript", "") or ""),
            normalized_transcript=str(
                getattr(follow_up_turn, "normalized_text", None)
                or getattr(follow_up_turn, "normalized_transcript", "")
                or ""
            ),
            detected_locale=_voice_locale(follow_up_turn),
            lifecycle_state=str(getattr(prior_turn, "lifecycle_state", "") or "").strip() or None,
            follow_up_reason=str(getattr(prior_turn, "follow_up_reason", "") or "").strip() or None,
            interaction_summary=str(getattr(prior_turn, "interaction_summary", "") or "").strip() or None,
            spoken_response=str(getattr(prior_turn, "spoken_response", "") or "").strip() or None,
            control_action=str(action or "").strip() or None,
        )

    def record_interruption(self, *, reason: str, locale: str | None = None) -> None:
        """Store the last speech interruption event observed before a new capture."""
        self._last_event = VoiceSessionEvent(
            event_kind="interruption",
            raw_transcript="",
            normalized_transcript="",
            detected_locale=str(locale or "").strip() or None,
            interruption_reason=str(reason or "").strip() or None,
        )


def build_default_voice_session_state() -> VoiceSessionState:
    """Build the default current-session voice event tracker."""
    return VoiceSessionState()


def format_voice_last_event(voice_session_state: VoiceSessionState | None) -> str:
    """Render the last current-session voice event for operators."""
    last_event = None if voice_session_state is None else voice_session_state.last_event
    if last_event is None:
        return "JARVIS Voice Last\nlast event: none"
    lines = [
        "JARVIS Voice Last",
        f"event kind: {last_event.event_kind}",
        f'raw transcript: "{last_event.raw_transcript}"',
        f'normalized transcript: "{last_event.normalized_transcript}"',
        f"detected locale: {last_event.detected_locale or 'n/a'}",
        f"interaction kind: {last_event.interaction_kind or 'n/a'}",
        f"lifecycle state: {last_event.lifecycle_state or 'n/a'}",
        f"follow-up reason: {last_event.follow_up_reason or 'n/a'}",
    ]
    if last_event.control_action:
        lines.append(f"control action: {last_event.control_action}")
    if last_event.interruption_reason:
        lines.append(f"interruption reason: {last_event.interruption_reason}")
    if last_event.interaction_summary:
        lines.append(f"interaction summary: {last_event.interaction_summary}")
    if last_event.spoken_response:
        lines.append(f"spoken response: {last_event.spoken_response}")
    return "\n".join(lines)


def _voice_locale(voice_turn: object | None) -> str | None:
    if voice_turn is None:
        return None
    locale = str(
        getattr(voice_turn, "locale_hint", None)
        or getattr(voice_turn, "detected_locale", None)
        or ""
    ).strip()
    return locale or None
