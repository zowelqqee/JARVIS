"""Speech presenter contract tests for spoken output."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from voice.speech_presenter import (
    interaction_speech_message,
    interaction_speech_utterance,
    latency_filler_utterance,
)
from voice.tts_provider import SpeechUtterance


class SpeechPresenterTests(unittest.TestCase):
    """Protect the voice-facing speech rendering contract."""

    def test_latency_filler_utterance_defaults_to_english(self) -> None:
        self.assertEqual(
            latency_filler_utterance(),
            SpeechUtterance(text="One moment.", locale="en-US"),
        )

    def test_latency_filler_utterance_uses_russian_locale_hint(self) -> None:
        self.assertEqual(
            latency_filler_utterance(preferred_locale="ru-RU"),
            SpeechUtterance(text="Одну секунду.", locale="ru-RU"),
        )

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

    def test_utterance_uses_explicit_russian_locale_for_english_heavy_message(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": "Relevant sources: docs/clarification_rules.md.",
            },
        )

        self.assertEqual(
            interaction_speech_utterance(result, preferred_locale="ru-RU"),
            SpeechUtterance(
                text="Источник: clarification_rules.md.",
                locale="ru-RU",
            ),
        )

    def test_utterance_preserves_explicit_english_locale_variant(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": "Relevant sources: docs/clarification_rules.md.",
            },
        )

        self.assertEqual(
            interaction_speech_utterance(result, preferred_locale="en-GB"),
            SpeechUtterance(
                text="Relevant sources: clarification_rules.md.",
                locale="en-GB",
            ),
        )

    def test_explicit_english_locale_wins_over_cyrillic_message_detection(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": "Сейчас используется папка /tmp/demo.",
            },
        )

        self.assertEqual(
            interaction_speech_utterance(result, preferred_locale="en-US"),
            SpeechUtterance(
                text="Сейчас используется папка demo.",
                locale="en-US",
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

    def test_unsafe_refusal_answer_is_shortened_for_english_voice(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": "I can't help with instructions for stealing a car.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "I can't help with that request.",
        )

    def test_self_harm_refusal_answer_mentions_988_briefly_for_english_voice(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "I'm sorry you're going through this, but I can't help with self-harm. "
                    "You deserve support and can call or text 988 for immediate help."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "I can't help with that. If you're in immediate danger, call or text 988 now.",
        )

    def test_self_harm_refusal_answer_is_localized_for_russian_voice(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "I'm sorry you're going through this, but I can't help with self-harm. "
                    "You deserve support and can call or text 988 for immediate help."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Я не могу помочь с этим. Если тебе угрожает немедленная опасность, позвони или напиши на 988 прямо сейчас.",
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

    def test_known_question_failure_is_shortened_for_english_voice(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "failure_message": "UNSUPPORTED_QUESTION: Question is outside the supported v1 grounded QA scope.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "I can't answer that in the current mode.",
        )

    def test_insufficient_context_failure_is_shortened_for_english_voice(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "failure_message": "INSUFFICIENT_CONTEXT: No recent answer context is available for that follow-up.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "I need more recent context for that follow-up.",
        )

    def test_source_answer_paths_are_sanitized_for_spoken_english_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "The relevant source is "
                    "/Users/arseniyabramidze/JARVIS/docs/clarification_rules.md."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "The relevant source is clarification_rules.md.",
        )

    def test_repo_relative_source_paths_are_sanitized_for_spoken_english_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": "Relevant sources: docs/clarification_rules.md, docs/runtime_flow.md.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Relevant sources: clarification_rules.md, runtime_flow.md.",
        )

    def test_single_source_phrase_is_localized_for_spoken_russian_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "The relevant source is "
                    "/Users/arseniyabramidze/JARVIS/docs/clarification_rules.md."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Источник: clarification_rules.md.",
        )

    def test_two_source_phrase_is_localized_for_spoken_russian_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": "Relevant sources: docs/clarification_rules.md, docs/runtime_flow.md.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Источники: clarification_rules.md, runtime_flow.md.",
        )

    def test_mixed_two_source_phrase_uses_natural_english_conjunction(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Relevant sources: docs/clarification_rules.md, "
                    "https://docs.python.org/3/library/pathlib.html."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Relevant sources: clarification_rules.md and docs.python.org.",
        )

    def test_mixed_two_source_phrase_uses_natural_russian_conjunction(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Relevant sources: docs/clarification_rules.md, "
                    "https://docs.python.org/3/library/pathlib.html."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Источники: clarification_rules.md и docs.python.org.",
        )

    def test_long_source_list_is_summarized_for_spoken_english_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Relevant sources: docs/clarification_rules.md, docs/runtime_flow.md, "
                    "docs/manual_voice_verification.md, docs/voiceover_plan.md."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Relevant sources: clarification_rules.md, runtime_flow.md, and 2 more.",
        )

    def test_long_source_list_is_summarized_for_spoken_russian_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Relevant sources: docs/clarification_rules.md, docs/runtime_flow.md, "
                    "docs/manual_voice_verification.md, docs/voiceover_plan.md."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Источники: clarification_rules.md, runtime_flow.md и ещё 2 источника.",
        )

    def test_mixed_file_and_host_source_list_handles_oxford_comma_for_english_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Relevant sources: docs/clarification_rules.md, https://docs.python.org/3/library/pathlib.html, "
                    "and docs/runtime_flow.md."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Relevant sources: clarification_rules.md, docs.python.org, and 1 more.",
        )

    def test_mixed_file_and_host_source_list_handles_oxford_comma_for_russian_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Relevant sources: docs/clarification_rules.md, https://docs.python.org/3/library/pathlib.html, "
                    "and docs/runtime_flow.md."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Источники: clarification_rules.md, docs.python.org и ещё 1 источник.",
        )

    def test_embedded_source_cue_is_appended_to_spoken_english_answer_summary(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Use pathlib for file-system paths. Relevant sources: "
                    "docs/clarification_rules.md, https://docs.python.org/3/library/pathlib.html."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Use pathlib for file-system paths. Sources: clarification_rules.md and docs.python.org.",
        )

    def test_embedded_source_cue_is_appended_to_spoken_russian_answer_summary(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_summary": "Используй pathlib для работы с путями.",
                "answer_text": (
                    "Используй pathlib для работы с путями. Relevant sources: "
                    "docs/clarification_rules.md, https://docs.python.org/3/library/pathlib.html."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Используй pathlib для работы с путями. Источники: clarification_rules.md и docs.python.org.",
        )

    def test_summary_drops_embedded_source_marker_before_appending_english_source_cue(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Use pathlib for file-system paths; Relevant sources: "
                    "docs/clarification_rules.md, https://docs.python.org/3/library/pathlib.html."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Use pathlib for file-system paths. Sources: clarification_rules.md and docs.python.org.",
        )

    def test_summary_drops_embedded_source_marker_before_appending_russian_source_cue(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Используй pathlib для работы с путями; Relevant sources: "
                    "docs/clarification_rules.md, https://docs.python.org/3/library/pathlib.html."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Используй pathlib для работы с путями. Источники: clarification_rules.md и docs.python.org.",
        )

    def test_summary_drops_parenthesized_source_marker_before_appending_english_source_cue(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Use pathlib for file-system paths (Relevant sources: "
                    "docs/clarification_rules.md, https://docs.python.org/3/library/pathlib.html)."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Use pathlib for file-system paths. Sources: clarification_rules.md and docs.python.org.",
        )

    def test_summary_drops_em_dash_source_marker_before_appending_russian_source_cue(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Используй pathlib для работы с путями — Relevant sources: "
                    "docs/clarification_rules.md, https://docs.python.org/3/library/pathlib.html."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Используй pathlib для работы с путями. Источники: clarification_rules.md и docs.python.org.",
        )

    def test_summary_drops_quoted_source_marker_before_appending_english_source_cue(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    'Use pathlib for file-system paths "Relevant sources: '
                    'docs/clarification_rules.md, <https://docs.python.org/3/library/pathlib.html>".'
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Use pathlib for file-system paths. Sources: clarification_rules.md and docs.python.org.",
        )

    def test_summary_drops_guillemet_source_marker_before_appending_russian_source_cue(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Используй pathlib для работы с путями «Relevant sources: "
                    "docs/clarification_rules.md, <https://docs.python.org/3/library/pathlib.html>»."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Используй pathlib для работы с путями. Источники: clarification_rules.md и docs.python.org.",
        )

    def test_russian_source_prefix_is_supported_for_source_only_answer(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": "Источники: docs/clarification_rules.md, https://docs.python.org/3/library/pathlib.html.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Источники: clarification_rules.md и docs.python.org.",
        )

    def test_russian_source_prefix_is_supported_for_embedded_source_cue(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Используй pathlib для работы с путями. Источники: "
                    "docs/clarification_rules.md, https://docs.python.org/3/library/pathlib.html."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Используй pathlib для работы с путями. Источники: clarification_rules.md и docs.python.org.",
        )

    def test_english_sources_dash_prefix_is_supported_for_embedded_source_cue(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Use pathlib for file-system paths. Sources - "
                    "docs/clarification_rules.md, https://docs.python.org/3/library/pathlib.html."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Use pathlib for file-system paths. Sources: clarification_rules.md and docs.python.org.",
        )

    def test_russian_sources_em_dash_prefix_is_supported_for_embedded_source_cue(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Используй pathlib для работы с путями. Источники — "
                    "docs/clarification_rules.md, https://docs.python.org/3/library/pathlib.html."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Используй pathlib для работы с путями. Источники: clarification_rules.md и docs.python.org.",
        )

    def test_russian_single_source_dash_prefix_is_supported_for_source_only_answer(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": "Источник - docs/clarification_rules.md.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Источник: clarification_rules.md.",
        )

    def test_warning_follows_embedded_source_cue_for_spoken_english_answer(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Use pathlib for file-system paths. Relevant sources: "
                    "docs/clarification_rules.md, https://docs.python.org/3/library/pathlib.html."
                ),
                "answer_warning": "This answer may be out of date for changing public facts.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            (
                "Use pathlib for file-system paths. Sources: clarification_rules.md and docs.python.org. "
                "Warning: May be out of date."
            ),
        )

    def test_warning_follows_embedded_source_cue_for_spoken_russian_answer(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_summary": "Используй pathlib для работы с путями.",
                "answer_text": (
                    "Используй pathlib для работы с путями. Relevant sources: "
                    "docs/clarification_rules.md, https://docs.python.org/3/library/pathlib.html."
                ),
                "answer_warning": "This answer may be out of date for changing public facts.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            (
                "Используй pathlib для работы с путями. Источники: clarification_rules.md и docs.python.org. "
                "Предупреждение: Ответ может быть неактуален."
            ),
        )

    def test_long_answer_with_source_and_warning_drops_more_detail_prompt_in_english(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_summary": "Pathlib helps with cross-platform path handling.",
                "answer_text": (
                    "Pathlib helps with cross-platform path handling. "
                    "It gives you higher-level path operations, cleaner path joins, and safer file-name handling in Python projects. "
                    "It also makes it easier to work with files, folders, and path normalization across operating systems. "
                    "Relevant sources: docs/clarification_rules.md, https://docs.python.org/3/library/pathlib.html."
                ),
                "answer_warning": "This answer may be out of date for changing public facts.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            (
                "Pathlib helps with cross-platform path handling. "
                "Sources: clarification_rules.md and docs.python.org. "
                "Warning: May be out of date."
            ),
        )

    def test_long_answer_with_source_and_warning_drops_more_detail_prompt_in_russian(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_summary": "Pathlib помогает работать с путями в разных системах.",
                "answer_text": (
                    "Pathlib помогает работать с путями в разных системах. "
                    "Он даёт более высокий уровень абстракции для путей, упрощает соединение сегментов и делает код с файлами чище. "
                    "Также с ним удобнее работать с файлами, папками и нормализацией путей в проектах на Python. "
                    "Relevant sources: docs/clarification_rules.md, https://docs.python.org/3/library/pathlib.html."
                ),
                "answer_warning": "This answer may be out of date for changing public facts.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            (
                "Pathlib помогает работать с путями в разных системах. "
                "Источники: clarification_rules.md и docs.python.org. "
                "Предупреждение: Ответ может быть неактуален."
            ),
        )

    def test_compact_local_sources_warning_uses_note_prefix_for_spoken_english_answer(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Use pathlib for file-system paths. Relevant sources: "
                    "docs/clarification_rules.md, https://docs.python.org/3/library/pathlib.html."
                ),
                "answer_warning": "Answer is limited to grounded local sources.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            (
                "Use pathlib for file-system paths. Sources: clarification_rules.md and docs.python.org. "
                "Note: Local sources only."
            ),
        )

    def test_compact_model_knowledge_warning_uses_note_prefix_for_spoken_russian_answer(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_summary": "Это общий ответ про тему.",
                "answer_text": (
                    "Это общий ответ про тему. "
                    "Он даёт обзор и дополнительные детали по теме, чтобы можно было продолжить вопрос следующим уточнением. "
                    "Он также остаётся достаточно длинным, чтобы speech layer предложил короткий follow-up prompt."
                ),
                "answer_warning": "This answer is based on model knowledge, not local sources.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            (
                "Это общий ответ про тему. "
                "Предупреждение: Этот ответ основан на знаниях модели, а не на локальных источниках."
            ),
        )

    def test_markdown_formatting_is_removed_from_spoken_question_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": "**Clarification** happens in `docs/clarification_rules.md`.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Clarification happens in clarification_rules.md.",
        )

    def test_urls_are_shortened_to_host_for_spoken_question_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": "You can read more at https://docs.python.org/3/library/pathlib.html.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "You can read more at docs.python.org.",
        )

    def test_debug_suffix_is_removed_from_spoken_question_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": "Clarification happens before execution Debug: request_id=req_123 latency_ms=42",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Clarification happens before execution",
        )

    def test_traceback_suffix_is_removed_from_spoken_question_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Relevant source docs/clarification_rules.md "
                    "Traceback (most recent call last): File \"demo.py\", line 1"
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Relevant source clarification_rules.md",
        )

    def test_long_english_question_answer_speaks_first_two_sentences(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Rayleigh scattering makes shorter wavelengths of sunlight scatter more strongly in the atmosphere. "
                    "That is why blue light spreads across the sky more than red light during the day. "
                    "The exact color still depends on air composition, dust, humidity, and the position of the sun."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            (
                "Rayleigh scattering makes shorter wavelengths of sunlight scatter more strongly in the atmosphere. "
                "That is why blue light spreads across the sky more than red light during the day."
            ),
        )

    def test_long_capability_answer_speaks_two_sentence_summary_without_underscores(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "I support command intents for open_app, open_file, open_folder, open_website, "
                    "list_windows, search_local, prepare_workspace, close_app, close_window. "
                    "Safe command families include open_app, open_file, open_folder, open_website, "
                    "list_windows, search_local, prepare_workspace. Sensitive actions that stay behind "
                    "confirmation are close_app, close_window. Question mode currently covers "
                    "blocked_state, recent_runtime, capabilities, runtime_status, docs_rules, "
                    "repo_structure, safety_explanations. Short answer follow-ups such as explain-more "
                    "and source questions stay grounded only to the most recent answer."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            (
                "I support command intents for open app, open file, open folder, open website, "
                "list windows, search local, prepare workspace, close app, close window. "
                "Safe command families include open app, open file, open folder, open website, "
                "list windows, search local, prepare workspace."
            ),
        )

    def test_long_russian_question_answer_speaks_first_two_sentences(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": (
                    "Рэйлиевское рассеяние объясняет, почему небо выглядит голубым. "
                    "Короткие волны синего света рассеиваются в атмосфере сильнее, чем длинные волны красного света. "
                    "На оттенок неба также влияют пыль, влажность, высота солнца и общее состояние атмосферы."
                ),
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            (
                "Рэйлиевское рассеяние объясняет, почему небо выглядит голубым. "
                "Короткие волны синего света рассеиваются в атмосфере сильнее, чем длинные волны красного света."
            ),
        )

    def test_short_question_answer_does_not_add_more_detail_prompt(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": "The sky looks blue because shorter wavelengths scatter more strongly.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "The sky looks blue because shorter wavelengths scatter more strongly.",
        )

    def test_folder_answer_paths_are_sanitized_for_spoken_russian_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": "Сейчас используется папка /tmp/demo.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="ru-RU"),
            "Сейчас используется папка demo.",
        )

    def test_file_names_with_underscores_keep_extensions_in_spoken_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": "Relevant sources: docs/question_answer_mode.md.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Relevant sources: question_answer_mode.md.",
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

        self.assertEqual(interaction_speech_message(result), "Do you want me to close Telegram? Say yes or no.")

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
            "Закрыть Telegram? Скажи да или нет.",
        )

    def test_non_destructive_confirmation_prompt_stays_brief(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "awaiting_confirmation",
                "command_summary": "open_app: Safari",
                "confirmation_request": {
                    "message": "Approve open_app for Safari before execution.",
                    "affected_targets": ["Safari"],
                },
            },
        )

        self.assertEqual(interaction_speech_message(result), "Do you want me to open Safari?")

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

    def test_runtime_clarification_target_prompt_is_shortened_for_english_voice(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "awaiting_clarification",
                "clarification_question": "Which previous target are you referring to?",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Which target do you mean?",
        )

    def test_command_clarification_drops_debug_suffix_before_spoken_mapping(self) -> None:
        result = SimpleNamespace(
            interaction_mode="clarification",
            visibility={
                "interaction_mode": "clarification",
                "clarification_question": "Please reply with confirm or cancel. Debug: request_id=req_123",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Say confirm or cancel.",
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

    def test_command_failure_drops_debug_suffix_for_spoken_english_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "failed",
                "failure_message": "Could not list windows: Window inspection unavailable Debug: request_id=req_123",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Could not list windows: Window inspection unavailable",
        )

    def test_failure_message_can_include_spoken_next_step_hint_for_english_voice(self) -> None:
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
            interaction_speech_message(result, preferred_locale="en-US"),
            "Could not list windows: Window inspection unavailable. Try again in an active macOS desktop session.",
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

    def test_open_file_completion_drops_debug_suffix_for_spoken_output(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "completed",
                "completion_result": "Opened file: docs/clarification_rules.md Debug: request_id=req_123",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Opened file clarification_rules.md.",
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

    def test_clarification_path_options_are_sanitized_for_spoken_english_output(self) -> None:
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
            interaction_speech_message(result, preferred_locale="en-US"),
            "I couldn't find roadmap.md. Did you mean notes.md or plan.md?",
        )

    def test_confirmation_reply_clarification_is_shortened_for_english_voice(self) -> None:
        result = SimpleNamespace(
            interaction_mode="clarification",
            visibility={
                "interaction_mode": "clarification",
                "clarification_question": "Please reply with confirm or cancel.",
            },
        )

        self.assertEqual(
            interaction_speech_message(result, preferred_locale="en-US"),
            "Say confirm or cancel.",
        )


if __name__ == "__main__":
    unittest.main()
