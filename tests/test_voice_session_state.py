"""Unit coverage for current-session voice event tracking."""

from __future__ import annotations

import unittest

from voice.session import VoiceTurn
from voice.session_state import (
    VoiceSessionState,
    format_voice_last_event,
)


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


if __name__ == "__main__":
    unittest.main()
