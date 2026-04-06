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

    def test_russian_notes_command_normalizes_to_notes_alias(self) -> None:
        self.assertEqual(normalize_voice_command("Джарвис, открой заметки"), "open notes")

    def test_russian_greeting_before_wake_word_is_stripped(self) -> None:
        self.assertEqual(normalize_voice_command("Привет Джарвис открой Telegram"), "open Telegram")

    def test_russian_greeting_with_punctuation_before_wake_word_is_stripped(self) -> None:
        self.assertEqual(normalize_voice_command("Привет, Джарвис, открой телеграм"), "open telegram")

    def test_leading_greeting_before_russian_question_is_stripped(self) -> None:
        self.assertEqual(normalize_voice_command("привет почему небо зелёное"), "почему небо зелёное")

    def test_conversational_fillers_before_russian_question_are_stripped(self) -> None:
        self.assertEqual(
            normalize_voice_command("привет слушай а почему Lego так называется"),
            "почему Lego так называется",
        )

    def test_conversational_fillers_before_wake_word_are_stripped(self) -> None:
        self.assertEqual(normalize_voice_command("ну слушай Джарвис открой заметки"), "open notes")

    def test_plain_greeting_is_not_rewritten_when_no_voice_payload_follows(self) -> None:
        self.assertEqual(normalize_voice_command("привет"), "привет")

    def test_general_russian_open_domain_question_is_left_as_is(self) -> None:
        self.assertEqual(normalize_voice_command("Кто президент Франции"), "Кто президент Франции")

    def test_russian_answer_follow_up_phrases_map_to_existing_text_surface(self) -> None:
        cases = {
            "скажи подробнее": "Explain more",
            "объясни подробнее": "Explain more",
            "какой источник": "Which source?",
            "где это написано": "Where is that written",
            "почему": "Why is that",
            "повтори": "Repeat that",
            "скажи ещё раз": "Repeat that",
        }

        for raw_text, expected in cases.items():
            with self.subTest(raw_text=raw_text):
                self.assertEqual(normalize_voice_command(raw_text), expected)

    def test_bare_podrobnee_is_no_longer_canonicalized(self) -> None:
        self.assertEqual(normalize_voice_command("подробнее"), "подробнее")

    def test_russian_listen_again_control_phrases_map_to_shell_control_surface(self) -> None:
        cases = {
            "слушай снова": "listen again",
            "послушай снова": "listen again",
            "послушай ещё раз": "listen again",
        }

        for raw_text, expected in cases.items():
            with self.subTest(raw_text=raw_text):
                self.assertEqual(normalize_voice_command(raw_text), expected)

    def test_russian_stop_speaking_control_phrases_map_to_shell_control_surface(self) -> None:
        cases = {
            "замолчи": "stop speaking",
            "прекрати говорить": "stop speaking",
            "перестань говорить": "stop speaking",
        }

        for raw_text, expected in cases.items():
            with self.subTest(raw_text=raw_text):
                self.assertEqual(normalize_voice_command(raw_text), expected)

    def test_english_repeat_follow_up_maps_to_existing_text_surface(self) -> None:
        self.assertEqual(normalize_voice_command("repeat"), "Repeat that")

    def test_english_answer_follow_up_phrases_map_to_existing_text_surface(self) -> None:
        cases = {
            "say more": "Explain more",
            "tell me more": "Explain more",
            "which source": "Which source?",
            "where is that from": "Where is that written",
            "why is that": "Why is that",
            "say that again": "Repeat that",
        }

        for raw_text, expected in cases.items():
            with self.subTest(raw_text=raw_text):
                self.assertEqual(normalize_voice_command(raw_text), expected)


if __name__ == "__main__":
    unittest.main()
