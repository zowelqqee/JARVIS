"""Unit coverage for current-session voice event tracking."""

from __future__ import annotations

import unittest

from voice.session import VoiceTurn
from voice.session_state import (
    VoiceSessionState,
    format_voice_last_event,
    format_voice_tts_last_result,
)
from voice.tts_provider import SpeechUtterance, TTSResult


class VoiceSessionStateTests(unittest.TestCase):
    """Keep the last voice event helper stable and operator-friendly."""

    def test_format_voice_last_event_reports_empty_state(self) -> None:
        rendered = format_voice_last_event(VoiceSessionState())

        self.assertIn("JARVIS Voice Last", rendered)
        self.assertIn("last event: none", rendered)

    def test_record_dispatch_captures_last_voice_turn_fields(self) -> None:
        state = VoiceSessionState()
        state.record_dispatch(
            VoiceTurn(
                raw_transcript="Что ты умеешь?",
                normalized_transcript="what can you do",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                interaction_kind="question",
                interaction_summary="Я могу открывать приложения и отвечать на вопросы.",
                spoken_response="Я могу открывать приложения и отвечать на вопросы.",
                follow_up_reason="short_answer",
            )
        )

        rendered = format_voice_last_event(state)

        self.assertIn("event kind: dispatch", rendered)
        self.assertIn('raw transcript: "Что ты умеешь?"', rendered)
        self.assertIn('normalized transcript: "what can you do"', rendered)
        self.assertIn("interaction kind: question", rendered)
        self.assertIn("follow-up reason: short_answer", rendered)

    def test_record_control_overwrites_last_event_with_control_surface(self) -> None:
        state = VoiceSessionState()
        prior_turn = VoiceTurn(
            raw_transcript="Закрой телеграм",
            normalized_transcript="close telegram",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
            lifecycle_state="awaiting_follow_up",
            interaction_summary="Закрыть Telegram?",
            spoken_response="Закрыть Telegram?",
            follow_up_reason="confirmation",
        )
        control_turn = VoiceTurn(
            raw_transcript="слушай снова",
            normalized_transcript="listen again",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )

        state.record_control(prior_turn, control_turn, action="listen_again")
        rendered = format_voice_last_event(state)

        self.assertIn("event kind: control", rendered)
        self.assertIn('normalized transcript: "listen again"', rendered)
        self.assertIn("control action: listen_again", rendered)
        self.assertIn("follow-up reason: confirmation", rendered)

    def test_record_interruption_reports_last_interruption_event(self) -> None:
        state = VoiceSessionState()

        state.record_interruption(
            reason="follow_up_capture_start",
            locale="ru-RU",
        )
        rendered = format_voice_last_event(state)

        self.assertIn("event kind: interruption", rendered)
        self.assertIn('raw transcript: ""', rendered)
        self.assertIn("detected locale: ru-RU", rendered)
        self.assertIn("interruption reason: follow_up_capture_start", rendered)

    def test_record_interruption_conflict_reports_last_failed_interruption_event(self) -> None:
        state = VoiceSessionState()

        state.record_interruption_conflict(
            reason="initial_capture_start",
            locale="en-US",
            error_message="Cannot interrupt active speech for capture.",
        )
        rendered = format_voice_last_event(state)

        self.assertIn("event kind: interruption_conflict", rendered)
        self.assertIn('raw transcript: ""', rendered)
        self.assertIn("detected locale: en-US", rendered)
        self.assertIn("interruption reason: initial_capture_start", rendered)
        self.assertIn("interruption error: Cannot interrupt active speech for capture.", rendered)

    def test_record_tts_result_reports_last_spoken_backend_and_voice(self) -> None:
        state = VoiceSessionState()

        state.record_tts_result(
            SpeechUtterance(text="Привет, мир.", locale="ru-RU"),
            TTSResult(ok=True, backend_name="yandex_speechkit", voice_id="yandex:ermil:good"),
        )
        rendered = format_voice_tts_last_result(state)

        self.assertIn("JARVIS TTS Last", rendered)
        self.assertIn("ok: yes", rendered)
        self.assertIn("locale: ru-RU", rendered)
        self.assertIn("backend: yandex_speechkit", rendered)
        self.assertIn("voice id: yandex:ermil:good", rendered)

    def test_format_voice_tts_last_result_reports_empty_state(self) -> None:
        rendered = format_voice_tts_last_result(VoiceSessionState())

        self.assertIn("JARVIS TTS Last", rendered)
        self.assertIn("last tts result: none", rendered)


if __name__ == "__main__":
    unittest.main()
