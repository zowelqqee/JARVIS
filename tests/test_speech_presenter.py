"""Speech presenter contract tests for spoken output."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from voice.speech_presenter import interaction_speech_message, interaction_speech_utterance
from voice.tts_provider import SpeechUtterance


class SpeechPresenterTests(unittest.TestCase):
    """Protect the voice-facing speech rendering contract."""

    def test_question_warning_uses_russian_prefix_for_russian_answer(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_summary": "Я могу отвечать на вопросы по репозиторию.",
                "answer_warning": "Ответ ограничен локальными источниками.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result),
            "Я могу отвечать на вопросы по репозиторию. Предупреждение: Ответ ограничен локальными источниками.",
        )
        self.assertEqual(
            interaction_speech_utterance(result),
            SpeechUtterance(
                text="Я могу отвечать на вопросы по репозиторию. Предупреждение: Ответ ограничен локальными источниками.",
                locale="ru-RU",
            ),
        )

    def test_known_question_warning_is_localized_for_russian_voice(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_summary": "Рэйлиевское рассеяние объясняет голубой цвет неба.",
                "answer_warning": "This answer may be out of date for changing public facts.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            (
                "Рэйлиевское рассеяние объясняет голубой цвет неба. "
                "Предупреждение: Этот ответ может быть неактуален для меняющихся публичных фактов."
            ),
        )

    def test_generic_refusal_answer_is_localized_for_russian_voice(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": "I can't help with that request.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Я не могу помочь с этой просьбой.",
        )

    def test_known_question_failure_is_localized_for_russian_voice(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "failure_message": "UNSUPPORTED_QUESTION: Question is outside the supported v1 grounded QA scope.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Я не могу ответить на этот вопрос в текущем режиме.",
        )

    def test_command_completion_uses_command_summary_instead_of_internal_log(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "completed",
                "command_summary": "prepare_workspace: Visual Studio Code, JARVIS, Google Chrome",
                "completion_result": "Completed prepare_workspace with 3 step(s).",
            },
        )

        self.assertEqual(
            interaction_speech_message(result),
            "Prepared workspace: Visual Studio Code, JARVIS, Google Chrome.",
        )

    def test_command_completion_uses_russian_phrase_when_locale_prefers_russian(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "completed",
                "command_summary": "open_app: Telegram",
                "completion_result": "Completed open_app with 1 step(s).",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Открыл Telegram.",
        )

    def test_open_file_completion_sanitizes_spoken_path(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "completed",
                "command_summary": "open_file: roadmap.md",
                "completion_result": "Opened file: /tmp/demo/roadmap.md",
            },
        )

        self.assertEqual(interaction_speech_message(result), "Opened file roadmap.md.")

    def test_confirmation_prompt_uses_friendlier_spoken_phrase(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "awaiting_confirmation",
                "command_summary": "close_app: Telegram",
                "confirmation_request": {
                    "message": "Approve close_app for Telegram before execution.",
                    "affected_targets": ["Telegram"],
                },
            },
        )

        self.assertEqual(interaction_speech_message(result), "Do you want me to close Telegram?")

    def test_confirmation_prompt_uses_russian_phrase_when_locale_prefers_russian(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "awaiting_confirmation",
                "command_summary": "close_app: Telegram",
                "confirmation_request": {
                    "message": "Approve close_app for Telegram before execution.",
                    "affected_targets": ["Telegram"],
                },
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Закрыть Telegram?",
        )

    def test_mixed_interaction_clarification_is_localized_for_russian_voice(self) -> None:
        result = SimpleNamespace(
            interaction_mode="clarification",
            visibility={
                "interaction_mode": "clarification",
                "clarification_question": "Do you want an answer first or should I open Safari?",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Сначала ответить или открыть Safari?",
        )

    def test_runtime_clarification_target_prompt_is_localized_for_russian_voice(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "awaiting_clarification",
                "clarification_question": "Which previous target are you referring to?",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Какую предыдущую цель ты имеешь в виду?",
        )

    def test_failure_message_can_include_localized_spoken_next_step_hint(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "failed",
                "failure_message": "Could not list windows: Window inspection unavailable",
                "next_step_hint": "Try again in an active macOS desktop session.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Не удалось показать окна: Window inspection unavailable. Попробуй ещё раз в активной сессии macOS.",
        )

    def test_search_completion_is_localized_for_russian_voice(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "completed",
                "completion_result": "Found 7 matches in demo.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Нашёл 7 совпадений в demo.",
        )

    def test_window_completion_is_localized_for_russian_voice(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "completed",
                "completion_result": "Found 7 visible windows.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Сейчас видно 7 окон.",
        )

    def test_filtered_window_empty_completion_is_localized_for_russian_voice(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "completed",
                "completion_result": "No visible Telegram windows found.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Окон Telegram не найдено.",
        )

    def test_failure_path_is_sanitized_for_spoken_russian_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "failed",
                "failure_message": (
                    "Found a matching file, but could not open it: "
                    "/tmp/demo/roadmap.md. simulated open failure"
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Нашёл подходящий файл, но не смог открыть roadmap.md. simulated open failure",
        )

    def test_clarification_path_options_are_sanitized_for_spoken_russian_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="clarification",
            visibility={
                "interaction_mode": "clarification",
                "clarification_question": (
                    "I could not find /tmp/demo/roadmap.md; did you mean "
                    "/tmp/demo/notes.md, /tmp/demo/plan.md?"
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Не нашёл roadmap.md. Ты имел в виду notes.md, plan.md?",
        )


if __name__ == "__main__":
    unittest.main()
