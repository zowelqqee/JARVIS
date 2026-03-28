"""Voice-aware interaction dispatch helpers for CLI rendering."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ui.interaction_presenter import interaction_output_lines
from voice.audio_policy import HalfDuplexAudioPolicy
from voice.session import VoiceTurn, finalize_voice_turn
from voice.speech_presenter import interaction_speech_utterance
from voice.tts_provider import SpeechUtterance, TTSProvider

if TYPE_CHECKING:
    from context.session_context import SessionContext
    from interaction.interaction_manager import InteractionManager


_FOLLOW_UP_WINDOW_SECONDS = {
    "clarification": 8.0,
    "confirmation": 8.0,
    "short_answer": 6.0,
}
_SHORT_ANSWER_MAX_CHARS = 160


@dataclass(frozen=True, slots=True)
class InteractionDispatchResult:
    """Prepared visible and spoken output for one interaction input."""

    raw_input: str
    interaction_result: object
    visible_lines: tuple[str, ...]
    speech_utterance: SpeechUtterance | None = None
    follow_up_reason: str | None = None
    follow_up_window_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class VoiceDispatchResult:
    """Dispatch metadata bound back to the originating voice turn."""

    voice_turn: VoiceTurn
    interaction: InteractionDispatchResult


def dispatch_interaction_input(
    raw_input: str,
    *,
    interaction_manager: InteractionManager,
    session_context: SessionContext | None,
    speak_enabled: bool,
    speech_locale_hint: str | None = None,
) -> InteractionDispatchResult:
    """Resolve one interaction input into visible lines plus optional speech."""
    interaction_result = interaction_manager.handle_input(raw_input, session_context=session_context)
    visibility = _interaction_visibility(interaction_result)
    speech_utterance = None
    if speak_enabled:
        speech_utterance = interaction_speech_utterance(
            interaction_result,
            preferred_locale=speech_locale_hint,
        )
    follow_up_reason = _follow_up_reason(
        interaction_result,
        visibility=visibility,
        speech_utterance=speech_utterance,
    )
    return InteractionDispatchResult(
        raw_input=raw_input,
        interaction_result=interaction_result,
        visible_lines=tuple(interaction_output_lines(interaction_result)),
        speech_utterance=speech_utterance,
        follow_up_reason=follow_up_reason,
        follow_up_window_seconds=(
            _FOLLOW_UP_WINDOW_SECONDS.get(follow_up_reason) if follow_up_reason is not None else None
        ),
    )


def dispatch_voice_turn(
    voice_turn: VoiceTurn | object,
    *,
    interaction_manager: InteractionManager,
    session_context: SessionContext | None,
    speak_enabled: bool,
) -> VoiceDispatchResult:
    """Bind one prepared voice turn to the downstream interaction result."""
    prepared_turn = _coerce_voice_turn(voice_turn)
    interaction_input = str(
        getattr(prepared_turn, "interaction_input", None)
        or getattr(voice_turn, "normalized_text", None)
        or getattr(voice_turn, "normalized_transcript", "")
        or ""
    ).strip()
    locale_hint = getattr(prepared_turn, "locale_hint", None)
    interaction = dispatch_interaction_input(
        interaction_input,
        interaction_manager=interaction_manager,
        session_context=session_context,
        speak_enabled=speak_enabled,
        speech_locale_hint=locale_hint if speak_enabled else None,
    )
    enriched_turn = finalize_voice_turn(
        prepared_turn,
        interaction_kind=_interaction_mode_value(interaction.interaction_result),
        interaction_summary=_interaction_summary(interaction),
        spoken_response=getattr(interaction.speech_utterance, "text", None),
        follow_up_reason=interaction.follow_up_reason,
        follow_up_window_seconds=interaction.follow_up_window_seconds,
    )
    return VoiceDispatchResult(voice_turn=enriched_turn, interaction=interaction)


def render_interaction_dispatch(
    dispatch_result: InteractionDispatchResult,
    *,
    emit_line: Callable[[str], None],
    tts_provider: TTSProvider | None = None,
    audio_policy: HalfDuplexAudioPolicy | None = None,
    on_speech_result: Callable[[SpeechUtterance, object], None] | None = None,
) -> None:
    """Emit visible lines and optional spoken output for one prepared dispatch."""
    for line in dispatch_result.visible_lines:
        emit_line(line)

    utterance = dispatch_result.speech_utterance
    if utterance is None or tts_provider is None:
        return

    if audio_policy is None:
        speech_result = tts_provider.speak(utterance)
    else:
        with audio_policy.speaking_phase():
            speech_result = tts_provider.speak(utterance)

    if on_speech_result is not None:
        on_speech_result(utterance, speech_result)

    if speech_result.attempted and not speech_result.ok:
        emit_line("speech: unavailable.")


def _coerce_voice_turn(voice_turn: VoiceTurn | object) -> VoiceTurn:
    if isinstance(voice_turn, VoiceTurn):
        return voice_turn
    return VoiceTurn(
        raw_transcript=str(getattr(voice_turn, "raw_transcript", "") or ""),
        normalized_transcript=str(
            getattr(voice_turn, "normalized_text", None)
            or getattr(voice_turn, "normalized_transcript", "")
            or ""
        ),
        detected_locale=str(getattr(voice_turn, "locale_hint", "") or "") or "en-US",
        locale_hint=getattr(voice_turn, "locale_hint", None),
        recognition_status=str(getattr(voice_turn, "recognition_status", "recognized") or "recognized"),
        interaction_input=getattr(voice_turn, "interaction_input", None),
        retryable=bool(getattr(voice_turn, "retryable", True)),
    )


def _interaction_mode_value(result: object) -> str | None:
    mode = getattr(result, "interaction_mode", None)
    if mode is None:
        visibility = _interaction_visibility(result)
        mode = visibility.get("interaction_mode")
    mode_text = str(getattr(mode, "value", mode) or "").strip()
    return mode_text or None


def _interaction_visibility(result: object) -> dict[str, object]:
    return dict(getattr(result, "visibility", {}) or {})


def _interaction_summary(dispatch_result: InteractionDispatchResult) -> str | None:
    visibility = _interaction_visibility(dispatch_result.interaction_result)

    summary_candidates = (
        getattr(dispatch_result.speech_utterance, "text", None),
        visibility.get("answer_summary"),
        visibility.get("command_summary"),
        visibility.get("clarification_question"),
        (
            visibility.get("confirmation_request", {}).get("message")
            if isinstance(visibility.get("confirmation_request"), dict)
            else None
        ),
        visibility.get("failure_message"),
        visibility.get("completion_result"),
    )
    for candidate in summary_candidates:
        text = str(candidate or "").strip()
        if text:
            return text
    return None


def _follow_up_reason(
    result: object,
    *,
    visibility: dict[str, object],
    speech_utterance: SpeechUtterance | None,
) -> str | None:
    mode = _interaction_mode_value(result)
    clarification_question = str(visibility.get("clarification_question", "") or "").strip()
    confirmation_request = visibility.get("confirmation_request")
    answer_summary = str(visibility.get("answer_summary", "") or "").strip()
    failure_message = str(visibility.get("failure_message", "") or "").strip()

    if mode == "clarification" or clarification_question:
        return "clarification"
    if isinstance(confirmation_request, dict) and str(confirmation_request.get("message", "") or "").strip():
        return "confirmation"
    if mode == "question" and not failure_message and _is_short_spoken_answer(
        speech_utterance=speech_utterance,
        answer_summary=answer_summary,
    ):
        return "short_answer"
    return None


def _is_short_spoken_answer(
    *,
    speech_utterance: SpeechUtterance | None,
    answer_summary: str,
) -> bool:
    spoken_text = str(getattr(speech_utterance, "text", "") or "").strip()
    if spoken_text:
        return len(spoken_text) <= _SHORT_ANSWER_MAX_CHARS
    return bool(answer_summary) and len(answer_summary) <= _SHORT_ANSWER_MAX_CHARS
