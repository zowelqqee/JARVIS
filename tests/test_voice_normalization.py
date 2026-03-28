"""Unit coverage for voice-specific transcript normalization."""

from __future__ import annotations

import unittest

from input.voice_normalization import normalize_voice_command


class VoiceNormalizationTests(unittest.TestCase):
    """Keep the spoken normalization surface stable for the CLI voice layer."""

    def test_russian_confirmation_followups_map_to_canonical_replies(self) -> None:
        cases = {
            "да": "yes",
            "да да": "yes",
            "подтверждаю": "confirm",
            "да, подтверждаю": "confirm",
            "нет": "no",
            "нет, отмена": "cancel",
            "стоп": "cancel",
        }

        for raw_text, expected in cases.items():
            with self.subTest(raw_text=raw_text):
                self.assertEqual(normalize_voice_command(raw_text), expected)

    def test_russian_command_path_still_normalizes_application_alias(self) -> None:
        self.assertEqual(normalize_voice_command("Джарвис, открой телеграм"), "open telegram")

    def test_general_russian_open_domain_question_is_left_as_is(self) -> None:
        self.assertEqual(normalize_voice_command("Кто президент Франции"), "Кто президент Франции")


if __name__ == "__main__":
    unittest.main()
