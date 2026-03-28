"""Unit coverage for the thin single-turn voice-session layer."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from input.voice_input import VoiceInputError
from voice.asr_service import VoiceCaptureTurn
from voice.session import SingleTurnVoiceSession, VoiceTurn, capture_cli_voice_turn


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


if __name__ == "__main__":
    unittest.main()
