"""Unit coverage for the thin single-turn voice-session layer."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from input.voice_input import VoiceInputError
from voice.audio_policy import HalfDuplexAudioPolicy
from voice.asr_service import VoiceCaptureTurn
from voice.session import (
    FollowUpCaptureRequest,
    SingleTurnVoiceSession,
    VoiceTurn,
    build_follow_up_capture_request,
    capture_cli_voice_turn,
    capture_follow_up_voice_turn,
    finalize_voice_turn,
)


class VoiceSessionTests(unittest.TestCase):
    """Keep the CLI-facing voice-session boundary stable."""

    def test_capture_cli_voice_turn_returns_routing_turn_with_locale_metadata(self) -> None:
        with patch(
            "voice.session.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Джарвис, открой телеграм",
                normalized_text="open telegram",
                locale_hint="ru-RU",
            ),
        ) as capture_mock:
            turn = capture_cli_voice_turn(timeout_seconds=7.0)

        self.assertEqual(
            turn,
            VoiceTurn(
                raw_transcript="Джарвис, открой телеграм",
                normalized_transcript="open telegram",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
            ),
        )
        capture_mock.assert_called_once_with(timeout_seconds=7.0, preferred_locales=None)

    def test_single_turn_session_tracks_routing_state_after_success(self) -> None:
        session = SingleTurnVoiceSession()

        with patch(
            "voice.session.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="What can you do?",
                normalized_text="What can you do?",
                locale_hint=None,
            ),
        ):
            turn = session.capture_turn(timeout_seconds=5.0)

        self.assertEqual(session.current_state, "routing")
        self.assertEqual(turn.detected_locale, "en-US")
        self.assertEqual(turn.interaction_input, "What can you do?")
        self.assertEqual(turn.recognition_status, "recognized")
        self.assertTrue(turn.retryable)

    def test_single_turn_session_marks_error_state_on_capture_failure(self) -> None:
        session = SingleTurnVoiceSession()
        error = VoiceInputError("PERMISSION_DENIED", "Speech recognition access was denied.")

        with patch("voice.session.capture_voice_turn", side_effect=error):
            with self.assertRaises(VoiceInputError):
                session.capture_turn(timeout_seconds=5.0)

        self.assertEqual(session.current_state, "error")

    def test_single_turn_session_maps_audio_policy_conflict_to_voice_input_error(self) -> None:
        policy = HalfDuplexAudioPolicy()
        session = SingleTurnVoiceSession(audio_policy=policy)

        with policy.speaking_phase():
            with self.assertRaises(VoiceInputError) as context:
                session.capture_turn(timeout_seconds=5.0)

        self.assertEqual(getattr(context.exception, "code", ""), "AUDIO_POLICY_CONFLICT")
        self.assertEqual(session.current_state, "error")

    def test_finalize_voice_turn_marks_question_answering_state(self) -> None:
        turn = VoiceTurn(
            raw_transcript="Что ты умеешь?",
            normalized_transcript="What can you do?",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )

        finalized_turn = finalize_voice_turn(
            turn,
            interaction_kind="question",
            interaction_summary="I can open apps and answer questions.",
            spoken_response="Я могу открывать приложения и отвечать на вопросы.",
        )

        self.assertEqual(finalized_turn.lifecycle_state, "answering")
        self.assertEqual(finalized_turn.interaction_kind, "question")
        self.assertEqual(
            finalized_turn.interaction_summary,
            "I can open apps and answer questions.",
        )
        self.assertEqual(
            finalized_turn.spoken_response,
            "Я могу открывать приложения и отвечать на вопросы.",
        )

    def test_finalize_voice_turn_marks_follow_up_ready_state(self) -> None:
        turn = VoiceTurn(
            raw_transcript="Закрой телеграм",
            normalized_transcript="close telegram",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )

        finalized_turn = finalize_voice_turn(
            turn,
            interaction_kind="command",
            interaction_summary="Закрыть Telegram?",
            spoken_response="Закрыть Telegram?",
            follow_up_reason="confirmation",
            follow_up_window_seconds=8.0,
        )

        self.assertEqual(finalized_turn.lifecycle_state, "awaiting_follow_up")
        self.assertEqual(finalized_turn.follow_up_reason, "confirmation")
        self.assertEqual(finalized_turn.follow_up_window_seconds, 8.0)

    def test_build_follow_up_capture_request_uses_turn_prompt_and_locale_chain(self) -> None:
        voice_turn = VoiceTurn(
            raw_transcript="Закрой телеграм",
            normalized_transcript="close telegram",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
            lifecycle_state="awaiting_follow_up",
            interaction_summary="Закрыть Telegram?",
            spoken_response="Закрыть Telegram?",
            follow_up_reason="confirmation",
            follow_up_window_seconds=8.0,
        )

        request = build_follow_up_capture_request(voice_turn)

        self.assertEqual(
            request,
            FollowUpCaptureRequest(
                reason="confirmation",
                timeout_seconds=8.0,
                preferred_locales=("ru-RU", "en-US"),
                prompt="Закрыть Telegram?",
            ),
        )

    def test_build_follow_up_capture_request_returns_none_for_non_follow_up_turn(self) -> None:
        voice_turn = VoiceTurn(
            raw_transcript="Открой телеграм",
            normalized_transcript="open telegram",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
            lifecycle_state="executing",
        )

        self.assertIsNone(build_follow_up_capture_request(voice_turn))

    def test_capture_follow_up_voice_turn_uses_derived_request_defaults(self) -> None:
        policy = HalfDuplexAudioPolicy()
        voice_turn = VoiceTurn(
            raw_transcript="Закрой телеграм",
            normalized_transcript="close telegram",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
            lifecycle_state="awaiting_follow_up",
            spoken_response="Закрыть Telegram?",
            follow_up_reason="confirmation",
            follow_up_window_seconds=8.0,
        )
        captured_follow_up = VoiceTurn(
            raw_transcript="Да",
            normalized_transcript="confirm",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )

        with patch(
            "voice.session.capture_cli_voice_turn",
            return_value=captured_follow_up,
        ) as capture_mock:
            next_turn = capture_follow_up_voice_turn(voice_turn, audio_policy=policy)

        self.assertEqual(next_turn, captured_follow_up)
        capture_mock.assert_called_once_with(
            timeout_seconds=8.0,
            preferred_locales=("ru-RU", "en-US"),
            audio_policy=policy,
        )

    def test_capture_follow_up_voice_turn_rejects_non_follow_up_turn(self) -> None:
        voice_turn = VoiceTurn(
            raw_transcript="Открой телеграм",
            normalized_transcript="open telegram",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
            lifecycle_state="executing",
        )

        with self.assertRaises(ValueError):
            capture_follow_up_voice_turn(voice_turn)


if __name__ == "__main__":
    unittest.main()
