"""Unit coverage for the thin voice ASR orchestration layer."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from voice import asr_service


class ASRServiceTests(unittest.TestCase):
    """Keep the CLI-facing ASR service contract stable."""

    def test_capture_voice_turn_normalizes_russian_command_and_keeps_locale_hint(self) -> None:
        with patch("voice.asr_service.capture_voice_input", return_value="Джарвис, открой телеграм") as capture_mock:
            turn = asr_service.capture_voice_turn(timeout_seconds=7.0)

        self.assertEqual(
            turn,
            asr_service.VoiceCaptureTurn(
                raw_transcript="Джарвис, открой телеграм",
                normalized_text="open telegram",
                locale_hint="ru-RU",
            ),
        )
        capture_mock.assert_called_once_with(timeout_seconds=7.0, preferred_locales=None)

    def test_capture_voice_turn_keeps_english_default_without_locale_hint(self) -> None:
        with patch("voice.asr_service.capture_voice_input", return_value="What can you do what can you do"):
            turn = asr_service.capture_voice_turn(timeout_seconds=5.0)

        self.assertEqual(
            turn,
            asr_service.VoiceCaptureTurn(
                raw_transcript="What can you do what can you do",
                normalized_text="What can you do",
                locale_hint=None,
            ),
        )

    def test_capture_voice_turn_forwards_locale_chain_override(self) -> None:
        with patch("voice.asr_service.capture_voice_input", return_value="hello") as capture_mock:
            asr_service.capture_voice_turn(timeout_seconds=3.0, preferred_locales=("en-US", "ru-RU"))

        capture_mock.assert_called_once_with(
            timeout_seconds=3.0,
            preferred_locales=("en-US", "ru-RU"),
        )

    def test_capture_voice_turn_normalizes_russian_confirmation_followup(self) -> None:
        with patch("voice.asr_service.capture_voice_input", return_value="да, подтверждаю"):
            turn = asr_service.capture_voice_turn(timeout_seconds=4.0)

        self.assertEqual(
            turn,
            asr_service.VoiceCaptureTurn(
                raw_transcript="да, подтверждаю",
                normalized_text="confirm",
                locale_hint="ru-RU",
            ),
        )


if __name__ == "__main__":
    unittest.main()
