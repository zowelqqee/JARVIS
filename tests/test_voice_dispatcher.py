"""Unit coverage for the thin voice-aware dispatcher layer."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from voice.audio_policy import HalfDuplexAudioPolicy
from voice.asr_service import VoiceCaptureTurn
from voice.dispatcher import dispatch_interaction_input, dispatch_voice_turn, render_interaction_dispatch
from voice.session import VoiceTurn
from voice.tts_provider import SpeechUtterance, TTSResult


class VoiceDispatcherTests(unittest.TestCase):
    """Keep CLI dispatch packaging stable as voice-specific layers move out of CLI."""

    def test_dispatch_interaction_input_collects_visible_lines_and_speech(self) -> None:
        interaction_manager = MagicMock()
        interaction_manager.handle_input.return_value = SimpleNamespace(
            interaction_mode="question",
            answer_result=SimpleNamespace(
                answer_text="I can open apps and answer grounded questions. I stay read-only.",
                sources=[],
                warning="Answer is limited to grounded local sources.",
            ),
            clarification_request=None,
            runtime_result=None,
            error=None,
        )

        dispatch_result = dispatch_interaction_input(
            "What can you do?",
            interaction_manager=interaction_manager,
            session_context=None,
            speak_enabled=True,
        )

        self.assertEqual(dispatch_result.raw_input, "What can you do?")
        self.assertIn("mode: question", dispatch_result.visible_lines)
        self.assertEqual(
            dispatch_result.speech_utterance,
            SpeechUtterance(
                text=(
                    "I can open apps and answer grounded questions. "
                    "I stay read-only. "
                    "Warning: Answer is limited to grounded local sources."
                ),
                locale="en-US",
            ),
        )

    def test_dispatch_voice_turn_uses_voice_turn_locale_hint_for_spoken_output(self) -> None:
        interaction_manager = MagicMock()
        interaction_manager.handle_input.return_value = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "completed",
                "command_summary": "open_app: Telegram",
                "completion_result": "Completed open_app with 1 step(s).",
            },
            answer_result=None,
            clarification_request=None,
            runtime_result=None,
            error=None,
        )
        voice_turn = VoiceTurn(
            raw_transcript="Джарвис, открой телеграм",
            normalized_transcript="open telegram",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )

        dispatch_result = dispatch_voice_turn(
            voice_turn,
            interaction_manager=interaction_manager,
            session_context=None,
            speak_enabled=True,
        )

        self.assertEqual(dispatch_result.voice_turn.raw_transcript, voice_turn.raw_transcript)
        self.assertEqual(dispatch_result.voice_turn.interaction_kind, "command")
        self.assertEqual(dispatch_result.voice_turn.lifecycle_state, "executing")
        self.assertEqual(dispatch_result.voice_turn.interaction_summary, "Открыл Telegram.")
        self.assertEqual(dispatch_result.voice_turn.spoken_response, "Открыл Telegram.")
        self.assertIsNone(dispatch_result.voice_turn.follow_up_reason)
        self.assertEqual(
            dispatch_result.interaction.speech_utterance,
            SpeechUtterance(text="Открыл Telegram.", locale="ru-RU"),
        )

    def test_dispatch_voice_turn_accepts_legacy_voice_capture_turn_contract(self) -> None:
        interaction_manager = MagicMock()
        interaction_manager.handle_input.return_value = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "completed",
                "command_summary": "open_app: Telegram",
                "completion_result": "Completed open_app with 1 step(s).",
            },
            answer_result=None,
            clarification_request=None,
            runtime_result=None,
            error=None,
        )
        legacy_turn = VoiceCaptureTurn(
            raw_transcript="Джарвис, открой телеграм",
            normalized_text="open telegram",
            locale_hint="ru-RU",
        )

        dispatch_result = dispatch_voice_turn(
            legacy_turn,
            interaction_manager=interaction_manager,
            session_context=None,
            speak_enabled=True,
        )

        interaction_manager.handle_input.assert_called_once_with("open telegram", session_context=None)
        self.assertEqual(
            dispatch_result.interaction.speech_utterance,
            SpeechUtterance(text="Открыл Telegram.", locale="ru-RU"),
        )
        self.assertEqual(dispatch_result.voice_turn.lifecycle_state, "executing")

    def test_dispatch_voice_turn_marks_confirmation_follow_up_window(self) -> None:
        interaction_manager = MagicMock()
        interaction_manager.handle_input.return_value = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "awaiting_confirmation",
                "command_summary": "close_app: Telegram",
                "confirmation_request": {
                    "message": "Approve close_app for Telegram before execution.",
                    "intent": "close_app",
                    "targets": ["Telegram"],
                },
            },
            answer_result=None,
            clarification_request=None,
            runtime_result=None,
            error=None,
        )
        voice_turn = VoiceTurn(
            raw_transcript="Джарвис, закрой телеграм",
            normalized_transcript="close telegram",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )

        dispatch_result = dispatch_voice_turn(
            voice_turn,
            interaction_manager=interaction_manager,
            session_context=None,
            speak_enabled=True,
        )

        self.assertEqual(dispatch_result.interaction.follow_up_reason, "confirmation")
        self.assertEqual(dispatch_result.interaction.follow_up_window_seconds, 8.0)
        self.assertEqual(dispatch_result.voice_turn.lifecycle_state, "awaiting_follow_up")
        self.assertEqual(dispatch_result.voice_turn.follow_up_reason, "confirmation")
        self.assertEqual(dispatch_result.voice_turn.follow_up_window_seconds, 8.0)
        self.assertEqual(
            dispatch_result.voice_turn.interaction_summary,
            "Закрыть Telegram? Скажи да или нет.",
        )

    def test_dispatch_interaction_input_marks_short_answer_follow_up_window(self) -> None:
        interaction_manager = MagicMock()
        interaction_manager.handle_input.return_value = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": "Use voice for one-shot commands.",
                "answer_summary": "Use voice for one-shot commands.",
                "answer_source_attributions": [],
            },
            answer_result=SimpleNamespace(
                answer_text="Use voice for one-shot commands.",
                sources=[],
                warning="",
            ),
            clarification_request=None,
            runtime_result=None,
            error=None,
        )

        dispatch_result = dispatch_interaction_input(
            "How should I use voice?",
            interaction_manager=interaction_manager,
            session_context=None,
            speak_enabled=True,
        )

        self.assertEqual(dispatch_result.follow_up_reason, "short_answer")
        self.assertEqual(dispatch_result.follow_up_window_seconds, 6.0)
        self.assertEqual(
            dispatch_result.speech_utterance,
            SpeechUtterance(text="Use voice for one-shot commands.", locale="en-US"),
        )

    def test_render_interaction_dispatch_uses_audio_policy_for_tts(self) -> None:
        lines: list[str] = []
        tts_provider = MagicMock()
        tts_provider.speak.return_value = TTSResult(ok=True)
        policy = HalfDuplexAudioPolicy()
        dispatch_result = SimpleNamespace(
            visible_lines=("mode: question",),
            speech_utterance=SpeechUtterance(text="Hello there.", locale="en-US"),
        )

        render_interaction_dispatch(
            dispatch_result,
            emit_line=lines.append,
            tts_provider=tts_provider,
            audio_policy=policy,
        )

        self.assertEqual(lines, ["mode: question"])
        self.assertEqual(policy.current_state, "idle")
        tts_provider.speak.assert_called_once_with(SpeechUtterance(text="Hello there.", locale="en-US"))

    def test_render_interaction_dispatch_reports_failed_speech_attempt(self) -> None:
        lines: list[str] = []
        tts_provider = MagicMock()
        tts_provider.speak.return_value = TTSResult(ok=False, attempted=True, error_code="TTS_FAILED")
        dispatch_result = SimpleNamespace(
            visible_lines=("state: completed",),
            speech_utterance=SpeechUtterance(text="Hello there.", locale="en-US"),
        )

        render_interaction_dispatch(
            dispatch_result,
            emit_line=lines.append,
            tts_provider=tts_provider,
        )

        self.assertEqual(lines, ["state: completed", "speech: unavailable."])

    def test_render_interaction_dispatch_plays_speaking_start_earcon_before_tts(self) -> None:
        lines: list[str] = []
        tts_provider = MagicMock()
        tts_provider.speak.return_value = TTSResult(ok=True)
        earcon_provider = MagicMock()
        dispatch_result = SimpleNamespace(
            visible_lines=("state: completed",),
            speech_utterance=SpeechUtterance(text="Hello there.", locale="en-US"),
        )

        render_interaction_dispatch(
            dispatch_result,
            emit_line=lines.append,
            tts_provider=tts_provider,
            earcon_provider=earcon_provider,
        )

        self.assertEqual(lines, ["state: completed"])
        earcon_provider.play.assert_called_once_with("speaking_start")
        tts_provider.speak.assert_called_once_with(SpeechUtterance(text="Hello there.", locale="en-US"))


if __name__ == "__main__":
    unittest.main()
