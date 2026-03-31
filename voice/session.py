"""Single-turn voice-session helpers for the current CLI MVP."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from input.voice_input import VoiceInputError
from voice.audio_policy import AudioPolicyError, HalfDuplexAudioPolicy
from voice.asr_service import capture_voice_turn
from voice.language import detect_spoken_locale

_VALID_SESSION_TRANSITIONS = {
    "idle": frozenset({"listening"}),
    "listening": frozenset({"transcribing", "error"}),
    "transcribing": frozenset({"routing", "error"}),
    "routing": frozenset({"executing", "answering", "awaiting_follow_up", "error"}),
    "executing": frozenset({"speaking", "error"}),
    "answering": frozenset({"speaking", "awaiting_follow_up", "error"}),
    "speaking": frozenset({"awaiting_follow_up", "error"}),
    "awaiting_follow_up": frozenset(),
    "error": frozenset(),
}
_FOLLOW_UP_REASONS = frozenset({"clarification", "confirmation", "short_answer"})
_FOLLOW_UP_CONTROL_ACTIONS = {
    "listen again": "listen_again",
    "stop speaking": "dismiss_follow_up",
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
    interaction_kind: str | None = None
    interaction_summary: str | None = None
    spoken_response: str | None = None
    follow_up_reason: str | None = None
    follow_up_window_seconds: float | None = None
    retryable: bool = True

    def __post_init__(self) -> None:
        if self.interaction_input is None:
            object.__setattr__(self, "interaction_input", self.normalized_transcript)

    @property
    def normalized_text(self) -> str:
        """Keep compatibility with the earlier voice-capture contract."""
        return self.normalized_transcript


@dataclass(frozen=True, slots=True)
class FollowUpCaptureRequest:
    """Prepared one-shot follow-up capture request for the next voice reply."""

    reason: str
    timeout_seconds: float
    preferred_locales: tuple[str, ...]
    prompt: str | None = None


class SingleTurnVoiceSession:
    """Track one explicit CLI voice turn through a tiny lifecycle."""

    def __init__(self, *, audio_policy: HalfDuplexAudioPolicy | None = None) -> None:
        self.audio_policy = audio_policy
        self.current_state = "idle"

    def capture_turn(
        self,
        *,
        timeout_seconds: float,
        preferred_locales: Sequence[str] | None = None,
    ) -> VoiceTurn:
        self._transition_to("listening")
        try:
            if self.audio_policy is None:
                captured_turn = capture_voice_turn(
                    timeout_seconds=timeout_seconds,
                    preferred_locales=preferred_locales,
                )
            else:
                with self.audio_policy.capture_phase():
                    captured_turn = capture_voice_turn(
                        timeout_seconds=timeout_seconds,
                        preferred_locales=preferred_locales,
                    )
        except AudioPolicyError as exc:
            self._transition_to("error")
            raise VoiceInputError("AUDIO_POLICY_CONFLICT", str(exc)) from exc
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


def finalize_voice_turn(
    voice_turn: VoiceTurn,
    *,
    interaction_kind: str | None = None,
    interaction_summary: str | None = None,
    spoken_response: str | None = None,
    follow_up_reason: str | None = None,
    follow_up_window_seconds: float | None = None,
) -> VoiceTurn:
    """Attach post-routing metadata to a prepared turn with lifecycle validation."""
    next_state = _post_routing_state(
        interaction_kind=interaction_kind,
        follow_up_reason=follow_up_reason,
    )
    _validate_voice_turn_transition(voice_turn.lifecycle_state, next_state)
    return replace(
        voice_turn,
        interaction_kind=interaction_kind,
        interaction_summary=interaction_summary,
        spoken_response=spoken_response,
        follow_up_reason=follow_up_reason,
        follow_up_window_seconds=follow_up_window_seconds,
        lifecycle_state=next_state,
    )


def _post_routing_state(*, interaction_kind: str | None, follow_up_reason: str | None) -> str:
    if follow_up_reason:
        return "awaiting_follow_up"
    if str(interaction_kind or "").strip() == "question":
        return "answering"
    return "executing"


def _validate_voice_turn_transition(current_state: str, next_state: str) -> None:
    allowed_states = _VALID_SESSION_TRANSITIONS.get(current_state, frozenset())
    if next_state not in allowed_states:
        raise ValueError(f"Invalid voice turn transition: {current_state} -> {next_state}")


def build_follow_up_capture_request(voice_turn: VoiceTurn) -> FollowUpCaptureRequest | None:
    """Return one optional follow-up capture request for an eligible finished turn."""
    reason = str(voice_turn.follow_up_reason or "").strip()
    timeout_seconds = float(voice_turn.follow_up_window_seconds or 0.0)
    if voice_turn.lifecycle_state != "awaiting_follow_up":
        return None
    if reason not in _FOLLOW_UP_REASONS or timeout_seconds <= 0.0:
        return None
    prompt = str(voice_turn.spoken_response or voice_turn.interaction_summary or "").strip() or None
    return FollowUpCaptureRequest(
        reason=reason,
        timeout_seconds=timeout_seconds,
        preferred_locales=_follow_up_locales(voice_turn),
        prompt=prompt,
    )


def capture_follow_up_voice_turn(
    voice_turn: VoiceTurn,
    *,
    timeout_seconds: float | None = None,
    preferred_locales: Sequence[str] | None = None,
    audio_policy: HalfDuplexAudioPolicy | None = None,
) -> VoiceTurn:
    """Capture one optional follow-up reply after clarification/confirmation/short answer."""
    request = build_follow_up_capture_request(voice_turn)
    if request is None:
        raise ValueError("Voice turn is not awaiting an eligible follow-up reply.")

    effective_timeout = float(timeout_seconds if timeout_seconds is not None else request.timeout_seconds)
    if effective_timeout <= 0.0:
        raise ValueError("Follow-up timeout must be positive.")

    return capture_cli_voice_turn(
        timeout_seconds=effective_timeout,
        preferred_locales=preferred_locales or request.preferred_locales,
        audio_policy=audio_policy,
    )


def follow_up_control_action(voice_turn: VoiceTurn | object, *, prior_reason: str | None = None) -> str | None:
    """Return a shell-level follow-up control action without routing it downstream."""
    normalized_text = str(
        getattr(voice_turn, "normalized_text", None)
        or getattr(voice_turn, "normalized_transcript", "")
        or ""
    ).strip().lower().rstrip("?.! ")
    if not normalized_text:
        return None
    direct_action = _FOLLOW_UP_CONTROL_ACTIONS.get(normalized_text)
    if direct_action is not None:
        return direct_action
    if str(prior_reason or "").strip() == "short_answer" and normalized_text in {"cancel", "stop"}:
        return "dismiss_follow_up"
    return None


def _follow_up_locales(voice_turn: VoiceTurn) -> tuple[str, ...]:
    primary_locale = str(voice_turn.locale_hint or voice_turn.detected_locale or "").strip() or "en-US"
    if primary_locale.startswith("ru"):
        fallback_locale = "en-US"
    else:
        fallback_locale = "ru-RU"
    if primary_locale == fallback_locale:
        return (primary_locale,)
    return (primary_locale, fallback_locale)


def capture_cli_voice_turn(
    *,
    timeout_seconds: float,
    preferred_locales: Sequence[str] | None = None,
    audio_policy: HalfDuplexAudioPolicy | None = None,
) -> VoiceTurn:
    """Capture one prepared voice turn for the current CLI shell layer."""
    return SingleTurnVoiceSession(audio_policy=audio_policy).capture_turn(
        timeout_seconds=timeout_seconds,
        preferred_locales=preferred_locales,
    )
