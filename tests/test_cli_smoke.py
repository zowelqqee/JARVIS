"""Minimal smoke coverage for JARVIS CLI shell behavior."""

from __future__ import annotations

import io
import hashlib
import json
import tempfile
from threading import Event, Thread
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from time import sleep
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, call, patch

import cli
from input.voice_input import VoiceInputError
from voice.audio_policy import HalfDuplexAudioPolicy
from voice.asr_service import VoiceCaptureTurn
from voice.session_state import VoiceSessionState
from voice.telemetry import VoiceTelemetryCollector
from voice.tts_provider import SpeechUtterance, TTSResult


class CliSmokeTests(unittest.TestCase):
    """Protect the current CLI shell command behavior with small smoke tests."""

    def setUp(self) -> None:
        self.runtime_manager = MagicMock()
        self.session_context = MagicMock()

    def test_cli_question_defaults_enable_hybrid_open_domain_when_unset(self) -> None:
        env: dict[str, str] = {}

        cli._apply_cli_question_defaults(env)
        config = cli.load_answer_backend_config(environ=env)

        self.assertEqual(getattr(config.backend_kind, "value", ""), "deterministic")
        self.assertTrue(config.llm.enabled)
        self.assertTrue(config.llm.open_domain_enabled)
        self.assertEqual(getattr(config.llm.provider, "value", ""), "openai_responses")
        self.assertTrue(config.llm.strict_mode)

    def test_cli_question_defaults_preserve_explicit_user_overrides(self) -> None:
        env = {
            "JARVIS_QA_LLM_ENABLED": "false",
            "JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED": "false",
            "JARVIS_QA_LLM_PROVIDER": "openai_responses",
            "JARVIS_QA_LLM_STRICT_MODE": "false",
        }

        cli._apply_cli_question_defaults(env)
        config = cli.load_answer_backend_config(environ=env)

        self.assertFalse(config.llm.enabled)
        self.assertFalse(config.llm.open_domain_enabled)
        self.assertFalse(config.llm.strict_mode)

    def test_voice_aliases_capture_speech_before_runtime_dispatch(self) -> None:
        for command in ("voice", "/voice", "voice on", "/voice on"):
            with self.subTest(command=command):
                with patch(
                    "cli.capture_voice_turn",
                    return_value=VoiceCaptureTurn(
                        raw_transcript="open browser",
                        normalized_text="open browser",
                        locale_hint=None,
                    ),
                ) as capture_mock, patch(
                    "cli.dispatch_voice_turn",
                    return_value=SimpleNamespace(interaction=SimpleNamespace(visible_lines=(), speech_utterance=None)),
                ) as dispatch_mock, patch("cli.render_interaction_dispatch") as render_mock:
                    should_exit, speak_enabled, output = self._run_command(command, speak_enabled=False)

                self.assertFalse(should_exit)
                self.assertFalse(speak_enabled)
                self.assertIn("voice: listening... speak now.", output)
                self.assertIn('recognized: "open browser"', output)
                capture_mock.assert_called_once_with(
                    timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
                    audio_policy=ANY,
                )
                dispatch_mock.assert_called_once_with(
                    capture_mock.return_value,
                    interaction_manager=ANY,
                    session_context=self.session_context,
                    speak_enabled=False,
                )
                render_mock.assert_called_once()

    def test_generic_question_escapes_clarification_state_after_invalid_command(self) -> None:
        from context.session_context import SessionContext
        from runtime.runtime_manager import RuntimeManager

        runtime_manager = RuntimeManager()
        session_context = SessionContext()
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            should_exit, speak_enabled = cli._handle_cli_command(
                "htlp",
                runtime_manager=runtime_manager,
                session_context=session_context,
                speak_enabled=False,
            )
            self.assertFalse(should_exit)
            self.assertFalse(speak_enabled)

            should_exit, speak_enabled = cli._handle_cli_command(
                "What can you do?",
                runtime_manager=runtime_manager,
                session_context=session_context,
                speak_enabled=False,
            )

        output = buffer.getvalue()
        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertNotIn("Speech output enabled.", output)
        self.assertIn("command: clarify: htlp", output)
        self.assertIn("mode: question", output)
        self.assertIn("answer:", output)

    def test_russian_text_follow_up_escapes_command_clarify_after_answer(self) -> None:
        from context.session_context import SessionContext
        from runtime.runtime_manager import RuntimeManager

        runtime_manager = RuntimeManager()
        session_context = SessionContext()
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            should_exit, speak_enabled = cli._handle_cli_command(
                "Что ты умеешь?",
                runtime_manager=runtime_manager,
                session_context=session_context,
                speak_enabled=False,
            )
            self.assertFalse(should_exit)
            self.assertFalse(speak_enabled)

            should_exit, speak_enabled = cli._handle_cli_command(
                "скажи подробнее",
                runtime_manager=runtime_manager,
                session_context=session_context,
                speak_enabled=False,
            )

        output = buffer.getvalue()
        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertEqual(output.count("mode: question"), 2)
        self.assertNotIn("command: clarify: скажи подробнее", output)
        self.assertIn("answer:", output)

    def test_voice_retries_initial_capture_with_alternate_locales_after_gibberish_fallback(self) -> None:
        interaction_manager = MagicMock()
        dispatch_result = SimpleNamespace(interaction=SimpleNamespace(visible_lines=(), speech_utterance=None))

        with patch(
            "cli.capture_voice_turn",
            side_effect=[
                VoiceCaptureTurn(
                    raw_transcript="Войска из Blue Cristian",
                    normalized_text="Войска из Blue Cristian",
                    locale_hint="ru-RU",
                    preferred_locales=("ru-RU", "en-US"),
                ),
                VoiceCaptureTurn(
                    raw_transcript="Why sky is blue",
                    normalized_text="Why sky is blue",
                    locale_hint=None,
                    preferred_locales=("en-US", "ru-RU"),
                ),
            ],
        ) as capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=dispatch_result,
        ) as dispatch_mock, patch(
            "cli.render_interaction_dispatch"
        ) as render_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ):
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice: didn't catch that clearly. speak again.", output)
        self.assertIn("voice: listening again... speak now.", output)
        self.assertIn('recognized: "Why sky is blue"', output)
        self.assertNotIn('recognized: "Войска из Blue Cristian"', output)
        self.assertEqual(
            capture_mock.call_args_list,
            [
                call(timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS, audio_policy=ANY),
                call(
                    timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
                    preferred_locales=("en-US", "ru-RU"),
                    audio_policy=ANY,
                ),
            ],
        )
        dispatch_mock.assert_called_once()
        render_mock.assert_called_once()

    def test_voice_does_not_retry_blocked_state_confirmation_reply(self) -> None:
        interaction_manager = MagicMock()
        interaction_manager.runtime_manager.current_state = "awaiting_confirmation"
        dispatch_result = SimpleNamespace(interaction=SimpleNamespace(visible_lines=(), speech_utterance=None))

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="да",
                normalized_text="yes",
                locale_hint="ru-RU",
                preferred_locales=("ru-RU", "en-US"),
            ),
        ) as capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=dispatch_result,
        ) as dispatch_mock, patch(
            "cli.render_interaction_dispatch"
        ) as render_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ):
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn('recognized: "yes"', output)
        self.assertNotIn("voice: didn't catch that clearly. speak again.", output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        dispatch_mock.assert_called_once()
        render_mock.assert_called_once()

    def test_voice_question_emits_latency_filler_when_dispatch_is_slow_and_speech_is_enabled(self) -> None:
        interaction_manager = MagicMock()
        tts_provider = MagicMock()
        dispatch_result = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Why is the sky blue?",
                normalized_transcript="Why is the sky blue?",
                detected_locale="en-US",
                locale_hint="en-US",
                lifecycle_state="answering",
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=SpeechUtterance(
                    text="Rayleigh scattering explains why the sky looks blue.",
                    locale="en-US",
                ),
                follow_up_reason="short_answer",
            ),
        )

        def slow_dispatch(*args, **kwargs):
            del args, kwargs
            sleep(0.02)
            return dispatch_result

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Why is the sky blue?",
                normalized_text="Why is the sky blue?",
                locale_hint="en-US",
            ),
        ) as capture_mock, patch(
            "cli.dispatch_voice_turn",
            side_effect=slow_dispatch,
        ) as dispatch_mock, patch(
            "cli.render_interaction_dispatch"
        ) as render_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch(
            "cli.build_default_tts_provider",
            return_value=tts_provider,
        ), patch(
            "cli._VOICE_LATENCY_FILLER_DELAY_SECONDS",
            0.0,
        ):
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=True)

        self.assertFalse(should_exit)
        self.assertTrue(speak_enabled)
        self.assertIn('recognized: "Why is the sky blue?"', output)
        self.assertIn("voice: thinking...", output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        dispatch_mock.assert_called_once()
        render_mock.assert_called_once()
        tts_provider.speak.assert_called_once_with(
            SpeechUtterance(text="One moment.", locale="en-US"),
        )

    def test_voice_answer_follow_up_emits_latency_filler_when_dispatch_is_slow_and_speech_is_enabled(self) -> None:
        interaction_manager = MagicMock()
        tts_provider = MagicMock()
        self.session_context.get_recent_answer_context.return_value = {"topic": "sky"}
        dispatch_result = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Explain more",
                normalized_transcript="Explain more",
                detected_locale="en-US",
                locale_hint="en-US",
                lifecycle_state="answering",
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=SpeechUtterance(
                    text="Blue light scatters more strongly because it has a shorter wavelength.",
                    locale="en-US",
                ),
                follow_up_reason="short_answer",
            ),
        )

        def slow_dispatch(*args, **kwargs):
            del args, kwargs
            sleep(0.02)
            return dispatch_result

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Explain more",
                normalized_text="Explain more",
                locale_hint="en-US",
            ),
        ), patch(
            "cli.dispatch_voice_turn",
            side_effect=slow_dispatch,
        ) as dispatch_mock, patch(
            "cli.render_interaction_dispatch"
        ) as render_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch(
            "cli.build_default_tts_provider",
            return_value=tts_provider,
        ), patch(
            "cli._VOICE_LATENCY_FILLER_DELAY_SECONDS",
            0.0,
        ):
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=True)

        self.assertFalse(should_exit)
        self.assertTrue(speak_enabled)
        self.assertIn('recognized: "Explain more"', output)
        self.assertIn("voice: thinking...", output)
        dispatch_mock.assert_called_once()
        render_mock.assert_called_once()
        tts_provider.speak.assert_called_once_with(
            SpeechUtterance(text="One moment.", locale="en-US"),
        )

    def test_voice_command_does_not_emit_latency_filler_when_dispatch_is_slow(self) -> None:
        interaction_manager = MagicMock()
        tts_provider = MagicMock()
        dispatch_result = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="open Safari",
                normalized_transcript="open Safari",
                detected_locale="en-US",
                locale_hint="en-US",
                lifecycle_state="executing",
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=SpeechUtterance(
                    text="Opened Safari.",
                    locale="en-US",
                ),
                follow_up_reason=None,
            ),
        )

        def slow_dispatch(*args, **kwargs):
            del args, kwargs
            sleep(0.02)
            return dispatch_result

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="open Safari",
                normalized_text="open Safari",
                locale_hint="en-US",
            ),
        ), patch(
            "cli.dispatch_voice_turn",
            side_effect=slow_dispatch,
        ) as dispatch_mock, patch(
            "cli.render_interaction_dispatch"
        ) as render_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch(
            "cli.build_default_tts_provider",
            return_value=tts_provider,
        ), patch(
            "cli._VOICE_LATENCY_FILLER_DELAY_SECONDS",
            0.0,
        ):
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=True)

        self.assertFalse(should_exit)
        self.assertTrue(speak_enabled)
        self.assertNotIn("voice: thinking...", output)
        dispatch_mock.assert_called_once()
        render_mock.assert_called_once()
        tts_provider.speak.assert_not_called()

    def test_voice_command_plays_earcons_for_listen_and_speech_when_enabled(self) -> None:
        interaction_manager = MagicMock()
        tts_provider = MagicMock()
        tts_provider.speak.return_value = TTSResult(ok=True)
        earcon_provider = MagicMock()
        dispatch_result = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="open Safari",
                normalized_transcript="open Safari",
                detected_locale="en-US",
                locale_hint="en-US",
                lifecycle_state="executing",
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=SpeechUtterance(text="Opened Safari.", locale="en-US"),
                follow_up_reason=None,
            ),
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="open Safari",
                normalized_text="open Safari",
                locale_hint="en-US",
            ),
        ) as capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=dispatch_result,
        ) as dispatch_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch(
            "cli.build_default_tts_provider",
            return_value=tts_provider,
        ), patch(
            "cli.build_default_earcon_provider",
            return_value=earcon_provider,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_EARCONS": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=True)

        self.assertFalse(should_exit)
        self.assertTrue(speak_enabled)
        self.assertIn("voice: listening... speak now.", output)
        self.assertIn('recognized: "open Safari"', output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        dispatch_mock.assert_called_once()
        earcon_provider.play.assert_has_calls(
            [
                call("listening_start"),
                call("listening_stop"),
                call("speaking_start"),
            ]
        )
        tts_provider.speak.assert_called_once_with(
            SpeechUtterance(text="Opened Safari.", locale="en-US"),
        )

    def test_voice_command_stops_interruptible_tts_before_initial_capture(self) -> None:
        interaction_manager = MagicMock()
        tts_provider = MagicMock()
        dispatch_result = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="open Safari",
                normalized_transcript="open Safari",
                detected_locale="en-US",
                locale_hint="en-US",
                lifecycle_state="executing",
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=SpeechUtterance(text="Opened Safari.", locale="en-US"),
                follow_up_reason=None,
            ),
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="open Safari",
                normalized_text="open Safari",
                locale_hint="en-US",
            ),
        ) as capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=dispatch_result,
        ), patch(
            "cli.render_interaction_dispatch"
        ), patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch(
            "cli.build_default_tts_provider",
            return_value=tts_provider,
        ), patch(
            "cli.stop_speech_if_supported",
            return_value=False,
        ) as stop_mock:
            should_exit, speak_enabled, _output = self._run_command("voice", speak_enabled=True)

        self.assertFalse(should_exit)
        self.assertTrue(speak_enabled)
        stop_mock.assert_called_once_with(tts_provider)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )

    def test_voice_command_plays_error_earcon_for_voice_input_failure_when_enabled(self) -> None:
        interaction_manager = MagicMock()
        earcon_provider = MagicMock()
        voice_error = VoiceInputError(
            "MICROPHONE_UNAVAILABLE",
            "Microphone is unavailable.",
            hint="Try again in an active macOS desktop session.",
        )

        with patch(
            "cli.capture_voice_turn",
            side_effect=voice_error,
        ), patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch(
            "cli.build_default_earcon_provider",
            return_value=earcon_provider,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_EARCONS": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice: listening... speak now.", output)
        self.assertIn("voice: Microphone is unavailable.", output)
        self.assertIn("hint: Try again in an active macOS desktop session.", output)
        earcon_provider.play.assert_has_calls(
            [
                call("listening_start"),
                call("listening_stop"),
                call("error"),
            ]
        )

    def test_voice_follow_up_capture_stops_interruptible_tts_before_listening_again(self) -> None:
        interaction_manager = MagicMock()
        tts_provider = MagicMock()
        telemetry = MagicMock()
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="close telegram",
                normalized_transcript="close telegram",
                detected_locale="en-US",
                locale_hint="en-US",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Do you want me to close Telegram? Say yes or no.",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )
        second_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="sure",
                normalized_transcript="sure",
                detected_locale="en-US",
                locale_hint="en-US",
                lifecycle_state="executing",
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )
        follow_up_turn = cli.VoiceTurn(
            raw_transcript="sure",
            normalized_transcript="sure",
            detected_locale="en-US",
            locale_hint="en-US",
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="close telegram",
                normalized_text="close telegram",
                locale_hint="en-US",
            ),
        ), patch(
            "cli.capture_follow_up_voice_turn",
            return_value=follow_up_turn,
        ), patch(
            "cli.dispatch_voice_turn",
            side_effect=[first_dispatch, second_dispatch],
        ), patch(
            "cli.render_interaction_dispatch"
        ), patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch(
            "cli.build_default_tts_provider",
            return_value=tts_provider,
        ), patch(
            "cli.stop_speech_if_supported",
            return_value=False,
        ) as stop_mock, patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, _output = self._run_command(
                "voice",
                speak_enabled=True,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertTrue(speak_enabled)
        self.assertEqual(stop_mock.call_count, 2)
        self.assertEqual(stop_mock.call_args_list, [call(tts_provider), call(tts_provider)])

    def test_voice_command_reports_audio_policy_conflict_when_speech_cannot_be_interrupted(self) -> None:
        interaction_manager = MagicMock()
        telemetry = VoiceTelemetryCollector()
        voice_session_state = VoiceSessionState()
        tts_provider = MagicMock()
        audio_policy = HalfDuplexAudioPolicy()
        buffer = io.StringIO()

        with audio_policy.speaking_phase():
            with redirect_stdout(buffer), patch(
                "cli.capture_voice_turn"
            ) as capture_mock, patch(
                "cli._build_default_interaction_manager",
                return_value=interaction_manager,
            ):
                should_exit, speak_enabled = cli._handle_cli_command(
                    "voice",
                    runtime_manager=self.runtime_manager,
                    session_context=self.session_context,
                    speak_enabled=True,
                    tts_provider=tts_provider,
                    audio_policy=audio_policy,
                    telemetry=telemetry,
                    voice_session_state=voice_session_state,
                )

        output = buffer.getvalue()
        snapshot = telemetry.snapshot()
        last_event = voice_session_state.last_event
        self.assertFalse(should_exit)
        self.assertTrue(speak_enabled)
        self.assertIn("voice: Cannot interrupt active speech for capture.", output)
        self.assertEqual(snapshot.speech_interrupt_count, 0)
        self.assertEqual(snapshot.speech_interrupt_for_capture_count, 0)
        self.assertEqual(snapshot.speech_interrupt_conflict_count, 1)
        self.assertIsNotNone(last_event)
        assert last_event is not None
        self.assertEqual(last_event.event_kind, "interruption_conflict")
        self.assertEqual(last_event.interruption_reason, "initial_capture_start")
        self.assertEqual(last_event.interruption_error, "Cannot interrupt active speech for capture.")
        capture_mock.assert_not_called()

    def test_voice_command_records_initial_speech_interruption_in_telemetry_and_session_state(self) -> None:
        interaction_manager = MagicMock()
        telemetry = VoiceTelemetryCollector()
        voice_session_state = VoiceSessionState()
        tts_provider = MagicMock()
        audio_policy = HalfDuplexAudioPolicy()
        buffer = io.StringIO()

        with audio_policy.speaking_phase():
            with redirect_stdout(buffer), patch(
                "cli.capture_voice_turn",
                side_effect=VoiceInputError(
                    "EMPTY_RECOGNITION",
                    "No speech was recognized. Try again.",
                ),
            ), patch(
                "cli._build_default_interaction_manager",
                return_value=interaction_manager,
            ), patch(
                "cli.stop_speech_if_supported",
                return_value=True,
            ) as stop_mock:
                should_exit, speak_enabled = cli._handle_cli_command(
                    "voice",
                    runtime_manager=self.runtime_manager,
                    session_context=self.session_context,
                    speak_enabled=True,
                    tts_provider=tts_provider,
                    audio_policy=audio_policy,
                    telemetry=telemetry,
                    voice_session_state=voice_session_state,
                )

        snapshot = telemetry.snapshot()
        last_event = voice_session_state.last_event

        self.assertFalse(should_exit)
        self.assertTrue(speak_enabled)
        self.assertEqual(snapshot.speech_interrupt_count, 1)
        self.assertEqual(snapshot.speech_interrupt_for_capture_count, 1)
        self.assertIsNotNone(last_event)
        assert last_event is not None
        self.assertEqual(last_event.event_kind, "interruption")
        self.assertEqual(last_event.interruption_reason, "initial_capture_start")
        self.assertIsNone(last_event.detected_locale)
        stop_mock.assert_called_once_with(tts_provider)

    def test_capture_auto_follow_up_turn_records_speech_interruption_in_telemetry(self) -> None:
        telemetry = VoiceTelemetryCollector()
        tts_provider = MagicMock()
        audio_policy = HalfDuplexAudioPolicy()
        audio_policy.current_state = "speaking"
        buffer = io.StringIO()
        prior_turn = cli.VoiceTurn(
            raw_transcript="close telegram",
            normalized_transcript="close telegram",
            detected_locale="en-US",
            locale_hint="en-US",
            lifecycle_state="awaiting_follow_up",
            spoken_response="Do you want me to close Telegram? Say yes or no.",
            follow_up_reason="confirmation",
            follow_up_window_seconds=8.0,
        )
        follow_up_turn = cli.VoiceTurn(
            raw_transcript="sure",
            normalized_transcript="sure",
            detected_locale="en-US",
            locale_hint="en-US",
        )

        with patch(
            "cli.capture_follow_up_voice_turn",
            return_value=follow_up_turn,
        ), patch(
            "cli.stop_speech_if_supported",
            return_value=True,
        ) as stop_mock:
            with redirect_stdout(buffer):
                captured_turn = cli._capture_auto_follow_up_turn(
                    prior_turn,
                    telemetry=telemetry,
                    tts_provider=tts_provider,
                    audio_policy=audio_policy,
                )

        snapshot = telemetry.snapshot()

        self.assertIs(captured_turn, follow_up_turn)
        self.assertEqual(snapshot.speech_interrupt_count, 1)
        self.assertEqual(snapshot.speech_interrupt_for_capture_count, 1)
        self.assertEqual(stop_mock.call_args_list, [call(tts_provider)])

    def test_stop_voice_latency_filler_records_response_phase_interruption_in_telemetry(self) -> None:
        telemetry = VoiceTelemetryCollector()
        voice_session_state = VoiceSessionState()
        tts_provider = MagicMock()
        stop_event = Event()
        worker = Thread(
            target=lambda: stop_event.wait(0.1),
            daemon=True,
        )
        worker.start()

        with patch(
            "cli.stop_speech_if_supported",
            return_value=True,
        ) as stop_mock:
            cli._stop_voice_latency_filler(
                (stop_event, worker),
                tts_provider=tts_provider,
                telemetry=telemetry,
                voice_session_state=voice_session_state,
                interruption_locale="ru-RU",
            )

        snapshot = telemetry.snapshot()
        last_event = voice_session_state.last_event

        self.assertEqual(snapshot.speech_interrupt_count, 1)
        self.assertEqual(snapshot.speech_interrupt_for_capture_count, 0)
        self.assertEqual(snapshot.speech_interrupt_for_response_count, 1)
        self.assertIsNotNone(last_event)
        assert last_event is not None
        self.assertEqual(last_event.event_kind, "interruption")
        self.assertEqual(last_event.interruption_reason, "final_answer_start")
        self.assertEqual(last_event.detected_locale, "ru-RU")
        stop_mock.assert_called_once_with(tts_provider)

    def test_voice_command_normalizes_repeated_open_phrase(self) -> None:
        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Open Safari open Safari",
                normalized_text="Open Safari",
                locale_hint=None,
            ),
        ) as capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=SimpleNamespace(interaction=SimpleNamespace(visible_lines=(), speech_utterance=None)),
        ) as dispatch_mock, patch("cli.render_interaction_dispatch") as render_mock:
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn('recognized: "Open Safari"', output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        dispatch_mock.assert_called_once_with(
            capture_mock.return_value,
            interaction_manager=ANY,
            session_context=self.session_context,
            speak_enabled=False,
        )
        render_mock.assert_called_once()

    def test_voice_command_strips_jarvis_wake_prefix(self) -> None:
        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Jarvis close telegram",
                normalized_text="close telegram",
                locale_hint=None,
            ),
        ) as capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=SimpleNamespace(interaction=SimpleNamespace(visible_lines=(), speech_utterance=None)),
        ) as dispatch_mock, patch("cli.render_interaction_dispatch") as render_mock:
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn('recognized: "close telegram"', output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        dispatch_mock.assert_called_once_with(
            capture_mock.return_value,
            interaction_manager=ANY,
            session_context=self.session_context,
            speak_enabled=False,
        )
        render_mock.assert_called_once()

    def test_voice_command_strips_jarvis_wake_prefix_with_punctuation(self) -> None:
        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Jarvis, open telegram",
                normalized_text="open telegram",
                locale_hint=None,
            ),
        ) as capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=SimpleNamespace(interaction=SimpleNamespace(visible_lines=(), speech_utterance=None)),
        ) as dispatch_mock, patch("cli.render_interaction_dispatch") as render_mock:
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn('recognized: "open telegram"', output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        dispatch_mock.assert_called_once_with(
            capture_mock.return_value,
            interaction_manager=ANY,
            session_context=self.session_context,
            speak_enabled=False,
        )
        render_mock.assert_called_once()

    def test_voice_command_strips_hey_jarvis_prefix(self) -> None:
        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Hey Jarvis open safari",
                normalized_text="open safari",
                locale_hint=None,
            ),
        ) as capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=SimpleNamespace(interaction=SimpleNamespace(visible_lines=(), speech_utterance=None)),
        ) as dispatch_mock, patch("cli.render_interaction_dispatch") as render_mock:
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn('recognized: "open safari"', output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        dispatch_mock.assert_called_once_with(
            capture_mock.return_value,
            interaction_manager=ANY,
            session_context=self.session_context,
            speak_enabled=False,
        )
        render_mock.assert_called_once()

    def test_voice_command_strips_russian_wake_prefix_and_normalizes_command(self) -> None:
        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Джарвис, открой телеграм",
                normalized_text="open telegram",
                locale_hint="ru-RU",
            ),
        ) as capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=SimpleNamespace(interaction=SimpleNamespace(visible_lines=(), speech_utterance=None)),
        ) as dispatch_mock, patch("cli.render_interaction_dispatch") as render_mock:
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn('recognized: "open telegram"', output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        dispatch_mock.assert_called_once_with(
            capture_mock.return_value,
            interaction_manager=ANY,
            session_context=self.session_context,
            speak_enabled=False,
        )
        render_mock.assert_called_once()

    def test_voice_question_normalizes_russian_fixed_capabilities_prompt(self) -> None:
        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Что ты умеешь что ты умеешь",
                normalized_text="what can you do",
                locale_hint="ru-RU",
            ),
        ) as capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=SimpleNamespace(interaction=SimpleNamespace(visible_lines=(), speech_utterance=None)),
        ) as dispatch_mock, patch("cli.render_interaction_dispatch") as render_mock:
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn('recognized: "what can you do"', output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        dispatch_mock.assert_called_once_with(
            capture_mock.return_value,
            interaction_manager=ANY,
            session_context=self.session_context,
            speak_enabled=False,
        )
        render_mock.assert_called_once()

    def test_voice_question_keeps_general_russian_open_domain_prompt(self) -> None:
        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Кто президент Франции",
                normalized_text="Кто президент Франции",
                locale_hint="ru-RU",
            ),
        ) as capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=SimpleNamespace(interaction=SimpleNamespace(visible_lines=(), speech_utterance=None)),
        ) as dispatch_mock, patch("cli.render_interaction_dispatch") as render_mock:
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn('recognized: "Кто президент Франции"', output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        dispatch_mock.assert_called_once_with(
            capture_mock.return_value,
            interaction_manager=ANY,
            session_context=self.session_context,
            speak_enabled=False,
        )
        render_mock.assert_called_once()

    def test_voice_question_normalizes_russian_mixed_question_and_command(self) -> None:
        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Что ты умеешь и открой сафари",
                normalized_text="Что ты умеешь and open safari",
                locale_hint="ru-RU",
            ),
        ) as capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=SimpleNamespace(interaction=SimpleNamespace(visible_lines=(), speech_utterance=None)),
        ) as dispatch_mock, patch("cli.render_interaction_dispatch") as render_mock:
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn('recognized: "Что ты умеешь and open safari"', output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        dispatch_mock.assert_called_once_with(
            capture_mock.return_value,
            interaction_manager=ANY,
            session_context=self.session_context,
            speak_enabled=False,
        )
        render_mock.assert_called_once()

    def test_voice_question_normalizes_repeated_question_phrase(self) -> None:
        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="What can you do what can you do",
                normalized_text="What can you do",
                locale_hint=None,
            ),
        ) as capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=SimpleNamespace(interaction=SimpleNamespace(visible_lines=(), speech_utterance=None)),
        ) as dispatch_mock, patch("cli.render_interaction_dispatch") as render_mock:
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn('recognized: "What can you do"', output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        dispatch_mock.assert_called_once_with(
            capture_mock.return_value,
            interaction_manager=ANY,
            session_context=self.session_context,
            speak_enabled=False,
        )
        render_mock.assert_called_once()

    def test_voice_command_auto_captures_one_blocking_follow_up_reply(self) -> None:
        cases = [
            ("confirmation", "Закрыть Telegram?"),
            ("clarification", "Ответить сначала или открыть Safari?"),
        ]

        for reason, spoken_prompt in cases:
            with self.subTest(reason=reason):
                interaction_manager = MagicMock()
                first_dispatch = SimpleNamespace(
                    voice_turn=cli.VoiceTurn(
                        raw_transcript="Джарвис, закрой телеграм",
                        normalized_transcript="close telegram",
                        detected_locale="ru-RU",
                        locale_hint="ru-RU",
                        lifecycle_state="awaiting_follow_up",
                        spoken_response=spoken_prompt,
                        follow_up_reason=reason,
                        follow_up_window_seconds=8.0,
                    ),
                    interaction=SimpleNamespace(
                        visible_lines=(),
                        speech_utterance=None,
                    ),
                )
                second_dispatch = SimpleNamespace(
                    voice_turn=cli.VoiceTurn(
                        raw_transcript="Да",
                        normalized_transcript="confirm",
                        detected_locale="ru-RU",
                        locale_hint="ru-RU",
                        lifecycle_state="executing",
                    ),
                    interaction=SimpleNamespace(
                        visible_lines=(),
                        speech_utterance=None,
                    ),
                )

                with patch(
                    "cli.capture_voice_turn",
                    return_value=VoiceCaptureTurn(
                        raw_transcript="Джарвис, закрой телеграм",
                        normalized_text="close telegram",
                        locale_hint="ru-RU",
                    ),
                ) as capture_mock, patch(
                    "cli.capture_follow_up_voice_turn",
                    return_value=cli.VoiceTurn(
                        raw_transcript="Да",
                        normalized_transcript="confirm",
                        detected_locale="ru-RU",
                        locale_hint="ru-RU",
                    ),
                ) as follow_up_capture_mock, patch(
                    "cli.dispatch_voice_turn",
                    side_effect=[first_dispatch, second_dispatch],
                ) as dispatch_mock, patch(
                    "cli.render_interaction_dispatch"
                ) as render_mock, patch(
                    "cli._build_default_interaction_manager",
                    return_value=interaction_manager,
                ), patch.dict(
                    "os.environ",
                    {"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
                    clear=False,
                ):
                    should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

                self.assertFalse(should_exit)
                self.assertFalse(speak_enabled)
                self.assertIn("voice: listening... speak now.", output)
                self.assertIn('recognized: "close telegram"', output)
                self.assertIn("voice: follow-up... speak now.", output)
                self.assertIn('recognized: "confirm"', output)
                capture_mock.assert_called_once_with(
                    timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
                    audio_policy=ANY,
                )
                follow_up_capture_mock.assert_called_once_with(
                    voice_turn=first_dispatch.voice_turn,
                    audio_policy=ANY,
                )
                self.assertEqual(dispatch_mock.call_count, 2)
                dispatch_mock.assert_any_call(
                    capture_mock.return_value,
                    interaction_manager=interaction_manager,
                    session_context=self.session_context,
                    speak_enabled=False,
                )
                dispatch_mock.assert_any_call(
                    follow_up_capture_mock.return_value,
                    interaction_manager=interaction_manager,
                    session_context=self.session_context,
                    speak_enabled=False,
                )
                self.assertEqual(render_mock.call_count, 2)

    def test_voice_command_does_not_auto_capture_follow_up_after_short_answer(self) -> None:
        interaction_manager = MagicMock()
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Что ты умеешь?",
                normalized_transcript="what can you do",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Я могу открывать приложения и отвечать на вопросы.",
                follow_up_reason="short_answer",
                follow_up_window_seconds=6.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Что ты умеешь?",
                normalized_text="what can you do",
                locale_hint="ru-RU",
            ),
        ) as capture_mock, patch(
            "cli.capture_follow_up_voice_turn"
        ) as follow_up_capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=first_dispatch,
        ) as dispatch_mock, patch(
            "cli.render_interaction_dispatch"
        ) as render_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice: listening... speak now.", output)
        self.assertIn('recognized: "what can you do"', output)
        self.assertNotIn("voice: follow-up... speak now.", output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        follow_up_capture_mock.assert_not_called()
        dispatch_mock.assert_called_once_with(
            capture_mock.return_value,
            interaction_manager=interaction_manager,
            session_context=self.session_context,
            speak_enabled=False,
        )
        render_mock.assert_called_once()

    def test_voice_command_auto_captures_follow_up_after_short_answer_when_speech_is_enabled(self) -> None:
        interaction_manager = MagicMock()
        tts_provider = MagicMock()
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Что ты умеешь?",
                normalized_transcript="what can you do",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Я могу открывать приложения и отвечать на вопросы.",
                follow_up_reason="short_answer",
                follow_up_window_seconds=6.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=SpeechUtterance(
                    text="Я могу открывать приложения и отвечать на вопросы.",
                    locale="ru-RU",
                ),
            ),
        )
        second_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Скажи подробнее",
                normalized_transcript="Explain more",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="answering",
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Что ты умеешь?",
                normalized_text="what can you do",
                locale_hint="ru-RU",
            ),
        ) as capture_mock, patch(
            "cli.capture_follow_up_voice_turn",
            return_value=cli.VoiceTurn(
                raw_transcript="Скажи подробнее",
                normalized_transcript="Explain more",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
            ),
        ) as follow_up_capture_mock, patch(
            "cli.dispatch_voice_turn",
            side_effect=[first_dispatch, second_dispatch],
        ) as dispatch_mock, patch(
            "cli.render_interaction_dispatch"
        ) as render_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch(
            "cli.build_default_tts_provider",
            return_value=tts_provider,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=True)

        self.assertFalse(should_exit)
        self.assertTrue(speak_enabled)
        self.assertIn("voice: listening... speak now.", output)
        self.assertIn('recognized: "what can you do"', output)
        self.assertIn("voice: follow-up... speak now.", output)
        self.assertIn('recognized: "Explain more"', output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        follow_up_capture_mock.assert_called_once_with(
            voice_turn=first_dispatch.voice_turn,
            audio_policy=ANY,
        )
        self.assertEqual(dispatch_mock.call_count, 2)
        dispatch_mock.assert_any_call(
            capture_mock.return_value,
            interaction_manager=interaction_manager,
            session_context=self.session_context,
            speak_enabled=True,
        )
        dispatch_mock.assert_any_call(
            follow_up_capture_mock.return_value,
            interaction_manager=interaction_manager,
            session_context=self.session_context,
            speak_enabled=True,
        )
        render_mock.assert_called()

    def test_voice_command_auto_captures_second_follow_up_reply_when_conversation_stays_active(self) -> None:
        interaction_manager = MagicMock()
        telemetry = MagicMock()
        tts_provider = MagicMock()
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Что ты умеешь и открой сафари",
                normalized_transcript="what can you do and open safari",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Ответить или выполнить команду?",
                follow_up_reason="clarification",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=SpeechUtterance(
                    text="Ответить или выполнить команду?",
                    locale="ru-RU",
                ),
            ),
        )
        second_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Ответить",
                normalized_transcript="answer",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Я могу открывать приложения и отвечать на вопросы.",
                follow_up_reason="short_answer",
                follow_up_window_seconds=6.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=SpeechUtterance(
                    text="Я могу открывать приложения и отвечать на вопросы.",
                    locale="ru-RU",
                ),
            ),
        )
        third_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Скажи подробнее",
                normalized_transcript="Explain more",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="answering",
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )
        first_follow_up_turn = cli.VoiceTurn(
            raw_transcript="Ответить",
            normalized_transcript="answer",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )
        second_follow_up_turn = cli.VoiceTurn(
            raw_transcript="Скажи подробнее",
            normalized_transcript="Explain more",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Что ты умеешь и открой сафари",
                normalized_text="what can you do and open safari",
                locale_hint="ru-RU",
            ),
        ) as capture_mock, patch(
            "cli.capture_follow_up_voice_turn",
            side_effect=[first_follow_up_turn, second_follow_up_turn],
        ) as follow_up_capture_mock, patch(
            "cli.dispatch_voice_turn",
            side_effect=[first_dispatch, second_dispatch, third_dispatch],
        ) as dispatch_mock, patch(
            "cli.render_interaction_dispatch"
        ) as render_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch(
            "cli.build_default_tts_provider",
            return_value=tts_provider,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command(
                "voice",
                speak_enabled=True,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertTrue(speak_enabled)
        self.assertIn('recognized: "what can you do and open safari"', output)
        self.assertIn('recognized: "answer"', output)
        self.assertIn('recognized: "Explain more"', output)
        self.assertEqual(output.count("voice: follow-up... speak now."), 2)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        self.assertEqual(follow_up_capture_mock.call_count, 2)
        self.assertEqual(dispatch_mock.call_count, 3)
        dispatch_mock.assert_any_call(
            capture_mock.return_value,
            interaction_manager=interaction_manager,
            session_context=self.session_context,
            speak_enabled=True,
        )
        dispatch_mock.assert_any_call(
            first_follow_up_turn,
            interaction_manager=interaction_manager,
            session_context=self.session_context,
            speak_enabled=True,
        )
        dispatch_mock.assert_any_call(
            second_follow_up_turn,
            interaction_manager=interaction_manager,
            session_context=self.session_context,
            speak_enabled=True,
        )
        self.assertEqual(render_mock.call_count, 3)
        self.assertEqual(telemetry.record_capture.call_count, 3)
        self.assertEqual(telemetry.record_dispatch.call_count, 3)
        self.assertEqual(telemetry.record_follow_up_opened.call_count, 2)
        self.assertEqual(telemetry.record_follow_up_completed.call_count, 2)
        telemetry.record_follow_up_loop.assert_called_once_with(
            completed_turns=2,
            limit_hit=False,
        )

    def test_voice_command_follow_up_loop_stays_bounded_to_two_extra_turns(self) -> None:
        interaction_manager = MagicMock()
        telemetry = MagicMock()
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Закрой телеграм",
                normalized_transcript="close telegram",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Закрыть Telegram?",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )
        second_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Да",
                normalized_transcript="confirm",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Ты точно хочешь закрыть Telegram?",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )
        third_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Да",
                normalized_transcript="confirm",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Последнее подтверждение.",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )
        first_follow_up_turn = cli.VoiceTurn(
            raw_transcript="Да",
            normalized_transcript="confirm",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )
        second_follow_up_turn = cli.VoiceTurn(
            raw_transcript="Да",
            normalized_transcript="confirm",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Закрой телеграм",
                normalized_text="close telegram",
                locale_hint="ru-RU",
            ),
        ) as capture_mock, patch(
            "cli.capture_follow_up_voice_turn",
            side_effect=[first_follow_up_turn, second_follow_up_turn],
        ) as follow_up_capture_mock, patch(
            "cli.dispatch_voice_turn",
            side_effect=[first_dispatch, second_dispatch, third_dispatch],
        ) as dispatch_mock, patch(
            "cli.render_interaction_dispatch"
        ) as render_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command(
                "voice",
                speak_enabled=False,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        active_budget = cli.max_auto_follow_up_turns({"JARVIS_VOICE_CONTINUOUS_MODE": "1"})
        self.assertEqual(output.count("voice: follow-up... speak now."), active_budget)
        self.assertIn("voice: follow-up limit reached.", output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        self.assertEqual(follow_up_capture_mock.call_count, active_budget)
        self.assertEqual(dispatch_mock.call_count, 1 + active_budget)
        self.assertEqual(render_mock.call_count, 1 + active_budget)
        telemetry.record_follow_up_loop.assert_called_once_with(
            completed_turns=active_budget,
            limit_hit=True,
        )

    def test_voice_command_follow_up_limit_plays_error_earcon_when_enabled(self) -> None:
        interaction_manager = MagicMock()
        telemetry = MagicMock()
        earcon_provider = MagicMock()
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="close telegram",
                normalized_transcript="close telegram",
                detected_locale="en-US",
                locale_hint="en-US",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Do you want me to close Telegram? Say yes or no.",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )
        second_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="sure",
                normalized_transcript="sure",
                detected_locale="en-US",
                locale_hint="en-US",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Are you sure?",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )
        third_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="yes",
                normalized_transcript="yes",
                detected_locale="en-US",
                locale_hint="en-US",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Final confirmation.",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )
        first_follow_up_turn = cli.VoiceTurn(
            raw_transcript="sure",
            normalized_transcript="sure",
            detected_locale="en-US",
            locale_hint="en-US",
        )
        second_follow_up_turn = cli.VoiceTurn(
            raw_transcript="yes",
            normalized_transcript="yes",
            detected_locale="en-US",
            locale_hint="en-US",
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="close telegram",
                normalized_text="close telegram",
                locale_hint="en-US",
            ),
        ), patch(
            "cli.capture_follow_up_voice_turn",
            side_effect=[first_follow_up_turn, second_follow_up_turn],
        ), patch(
            "cli.dispatch_voice_turn",
            side_effect=[first_dispatch, second_dispatch, third_dispatch],
        ), patch(
            "cli.render_interaction_dispatch"
        ), patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch(
            "cli.build_default_earcon_provider",
            return_value=earcon_provider,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1", "JARVIS_VOICE_EARCONS": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command(
                "voice",
                speak_enabled=False,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice: follow-up limit reached.", output)
        self.assertEqual(
            [args[0] for args, _kwargs in earcon_provider.play.call_args_list].count("error"),
            1,
        )

    def test_voice_command_does_not_auto_capture_follow_up_when_continuous_flag_is_off(self) -> None:
        interaction_manager = MagicMock()
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Джарвис, закрой телеграм",
                normalized_transcript="close telegram",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Закрыть Telegram?",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Джарвис, закрой телеграм",
                normalized_text="close telegram",
                locale_hint="ru-RU",
            ),
        ) as capture_mock, patch(
            "cli.capture_follow_up_voice_turn"
        ) as follow_up_capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=first_dispatch,
        ) as dispatch_mock, patch(
            "cli.render_interaction_dispatch"
        ) as render_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "0"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertNotIn("voice: follow-up... speak now.", output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        follow_up_capture_mock.assert_not_called()
        dispatch_mock.assert_called_once_with(
            capture_mock.return_value,
            interaction_manager=interaction_manager,
            session_context=self.session_context,
            speak_enabled=False,
        )
        render_mock.assert_called_once()

    def test_voice_follow_up_listen_again_control_recaptures_once_before_dispatch(self) -> None:
        interaction_manager = MagicMock()
        telemetry = MagicMock()
        retry_control_turn = cli.VoiceTurn(
            raw_transcript="слушай снова",
            normalized_transcript="listen again",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )
        final_follow_up_turn = cli.VoiceTurn(
            raw_transcript="Да",
            normalized_transcript="confirm",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Джарвис, закрой телеграм",
                normalized_transcript="close telegram",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Закрыть Telegram?",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )
        second_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Да",
                normalized_transcript="confirm",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="executing",
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Джарвис, закрой телеграм",
                normalized_text="close telegram",
                locale_hint="ru-RU",
            ),
        ) as capture_mock, patch(
            "cli.capture_follow_up_voice_turn",
            side_effect=[
                retry_control_turn,
                final_follow_up_turn,
            ],
        ) as follow_up_capture_mock, patch(
            "cli.dispatch_voice_turn",
            side_effect=[first_dispatch, second_dispatch],
        ) as dispatch_mock, patch(
            "cli.render_interaction_dispatch"
        ) as render_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command(
                "voice",
                speak_enabled=False,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice: follow-up... speak now.", output)
        self.assertIn("voice: listening again... speak now.", output)
        self.assertNotIn('recognized: "listen again"', output)
        self.assertIn('recognized: "confirm"', output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        self.assertEqual(follow_up_capture_mock.call_count, 2)
        follow_up_capture_mock.assert_any_call(
            voice_turn=first_dispatch.voice_turn,
            audio_policy=ANY,
        )
        self.assertEqual(dispatch_mock.call_count, 2)
        dispatch_mock.assert_any_call(
            capture_mock.return_value,
            interaction_manager=interaction_manager,
            session_context=self.session_context,
            speak_enabled=False,
        )
        dispatch_mock.assert_any_call(
            final_follow_up_turn,
            interaction_manager=interaction_manager,
            session_context=self.session_context,
            speak_enabled=False,
        )
        self.assertEqual(render_mock.call_count, 2)
        self.assertEqual(telemetry.record_follow_up_opened.call_count, 2)
        telemetry.record_follow_up_control.assert_called_once_with(
            first_dispatch.voice_turn,
            retry_control_turn,
            action="listen_again",
        )
        telemetry.record_follow_up_completed.assert_called_once_with(
            first_dispatch.voice_turn,
            final_follow_up_turn,
        )

    def test_voice_follow_up_empty_recognition_retries_once_before_dispatch(self) -> None:
        interaction_manager = MagicMock()
        telemetry = MagicMock()
        empty_error = VoiceInputError(
            "EMPTY_RECOGNITION",
            "No speech was recognized. Try again.",
            hint="Speak right after the follow-up prompt.",
        )
        final_follow_up_turn = cli.VoiceTurn(
            raw_transcript="Да",
            normalized_transcript="confirm",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Джарвис, закрой телеграм",
                normalized_transcript="close telegram",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Закрыть Telegram?",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )
        second_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Да",
                normalized_transcript="confirm",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="executing",
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Джарвис, закрой телеграм",
                normalized_text="close telegram",
                locale_hint="ru-RU",
            ),
        ) as capture_mock, patch(
            "cli.capture_follow_up_voice_turn",
            side_effect=[empty_error, final_follow_up_turn],
        ) as follow_up_capture_mock, patch(
            "cli.dispatch_voice_turn",
            side_effect=[first_dispatch, second_dispatch],
        ) as dispatch_mock, patch(
            "cli.render_interaction_dispatch"
        ) as render_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command(
                "voice",
                speak_enabled=False,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice: follow-up... speak now.", output)
        self.assertIn("voice: didn't catch that. speak again.", output)
        self.assertNotIn("voice: No speech was recognized. Try again.", output)
        self.assertIn('recognized: "confirm"', output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        self.assertEqual(follow_up_capture_mock.call_count, 2)
        self.assertEqual(dispatch_mock.call_count, 2)
        self.assertEqual(render_mock.call_count, 2)
        self.assertEqual(telemetry.record_follow_up_opened.call_count, 2)
        telemetry.record_follow_up_completed.assert_called_once_with(
            first_dispatch.voice_turn,
            final_follow_up_turn,
        )

    def test_voice_follow_up_empty_recognition_retry_plays_error_earcon_when_enabled(self) -> None:
        interaction_manager = MagicMock()
        telemetry = MagicMock()
        earcon_provider = MagicMock()
        empty_error = VoiceInputError(
            "EMPTY_RECOGNITION",
            "No speech was recognized. Try again.",
            hint="Speak right after the follow-up prompt.",
        )
        final_follow_up_turn = cli.VoiceTurn(
            raw_transcript="Да",
            normalized_transcript="confirm",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Джарвис, закрой телеграм",
                normalized_transcript="close telegram",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Закрыть Telegram?",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )
        second_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Да",
                normalized_transcript="confirm",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="executing",
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Джарвис, закрой телеграм",
                normalized_text="close telegram",
                locale_hint="ru-RU",
            ),
        ), patch(
            "cli.capture_follow_up_voice_turn",
            side_effect=[empty_error, final_follow_up_turn],
        ), patch(
            "cli.dispatch_voice_turn",
            side_effect=[first_dispatch, second_dispatch],
        ), patch(
            "cli.render_interaction_dispatch"
        ), patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch(
            "cli.build_default_earcon_provider",
            return_value=earcon_provider,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1", "JARVIS_VOICE_EARCONS": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command(
                "voice",
                speak_enabled=False,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice: didn't catch that. speak again.", output)
        earcon_provider.play.assert_has_calls(
            [
                call("listening_start"),
                call("listening_stop"),
                call("listening_start"),
                call("listening_stop"),
                call("error"),
                call("listening_start"),
                call("listening_stop"),
            ]
        )

    def test_voice_follow_up_try_again_control_recaptures_once_before_dispatch(self) -> None:
        interaction_manager = MagicMock()
        telemetry = MagicMock()
        retry_control_turn = cli.VoiceTurn(
            raw_transcript="try again",
            normalized_transcript="try again",
            detected_locale="en-US",
            locale_hint="en-US",
        )
        final_follow_up_turn = cli.VoiceTurn(
            raw_transcript="sure",
            normalized_transcript="sure",
            detected_locale="en-US",
            locale_hint="en-US",
        )
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="close telegram",
                normalized_transcript="close telegram",
                detected_locale="en-US",
                locale_hint="en-US",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Do you want me to close Telegram? Say yes or no.",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )
        second_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="sure",
                normalized_transcript="sure",
                detected_locale="en-US",
                locale_hint="en-US",
                lifecycle_state="executing",
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="close telegram",
                normalized_text="close telegram",
                locale_hint="en-US",
            ),
        ) as capture_mock, patch(
            "cli.capture_follow_up_voice_turn",
            side_effect=[retry_control_turn, final_follow_up_turn],
        ) as follow_up_capture_mock, patch(
            "cli.dispatch_voice_turn",
            side_effect=[first_dispatch, second_dispatch],
        ) as dispatch_mock, patch(
            "cli.render_interaction_dispatch"
        ) as render_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command(
                "voice",
                speak_enabled=False,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice: follow-up... speak now.", output)
        self.assertIn("voice: listening again... speak now.", output)
        self.assertNotIn('recognized: "try again"', output)
        self.assertIn('recognized: "sure"', output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        self.assertEqual(follow_up_capture_mock.call_count, 2)
        self.assertEqual(dispatch_mock.call_count, 2)
        self.assertEqual(render_mock.call_count, 2)
        self.assertEqual(telemetry.record_follow_up_opened.call_count, 2)
        telemetry.record_follow_up_control.assert_called_once_with(
            first_dispatch.voice_turn,
            retry_control_turn,
            action="listen_again",
        )
        telemetry.record_follow_up_completed.assert_called_once_with(
            first_dispatch.voice_turn,
            final_follow_up_turn,
        )

    def test_voice_follow_up_empty_recognition_closes_after_one_retry(self) -> None:
        interaction_manager = MagicMock()
        telemetry = MagicMock()
        empty_error = VoiceInputError(
            "EMPTY_RECOGNITION",
            "No speech was recognized. Try again.",
            hint="Speak right after the follow-up prompt.",
        )
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Джарвис, закрой телеграм",
                normalized_transcript="close telegram",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Закрыть Telegram?",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Джарвис, закрой телеграм",
                normalized_text="close telegram",
                locale_hint="ru-RU",
            ),
        ) as capture_mock, patch(
            "cli.capture_follow_up_voice_turn",
            side_effect=[empty_error, empty_error],
        ) as follow_up_capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=first_dispatch,
        ) as dispatch_mock, patch(
            "cli.render_interaction_dispatch"
        ) as render_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command(
                "voice",
                speak_enabled=False,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice: follow-up... speak now.", output)
        self.assertIn("voice: didn't catch that. speak again.", output)
        self.assertIn("voice: no follow-up reply detected.", output)
        self.assertIn("voice: follow-up closed.", output)
        self.assertNotIn("voice: No speech was recognized. Try again.", output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        self.assertEqual(follow_up_capture_mock.call_count, 2)
        dispatch_mock.assert_called_once_with(
            capture_mock.return_value,
            interaction_manager=interaction_manager,
            session_context=self.session_context,
            speak_enabled=False,
        )
        render_mock.assert_called_once()
        self.assertEqual(telemetry.record_follow_up_opened.call_count, 2)
        telemetry.record_follow_up_completed.assert_not_called()

    def test_voice_follow_up_empty_recognition_close_plays_error_earcon_per_missed_attempt_when_enabled(self) -> None:
        interaction_manager = MagicMock()
        telemetry = MagicMock()
        earcon_provider = MagicMock()
        empty_error = VoiceInputError(
            "EMPTY_RECOGNITION",
            "No speech was recognized. Try again.",
            hint="Speak right after the follow-up prompt.",
        )
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Джарвис, закрой телеграм",
                normalized_transcript="close telegram",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Закрыть Telegram?",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Джарвис, закрой телеграм",
                normalized_text="close telegram",
                locale_hint="ru-RU",
            ),
        ), patch(
            "cli.capture_follow_up_voice_turn",
            side_effect=[empty_error, empty_error],
        ), patch(
            "cli.dispatch_voice_turn",
            return_value=first_dispatch,
        ), patch(
            "cli.render_interaction_dispatch"
        ), patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch(
            "cli.build_default_earcon_provider",
            return_value=earcon_provider,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1", "JARVIS_VOICE_EARCONS": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command(
                "voice",
                speak_enabled=False,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice: no follow-up reply detected.", output)
        self.assertIn("voice: follow-up closed.", output)
        self.assertEqual(
            [args[0] for args, _kwargs in earcon_provider.play.call_args_list].count("error"),
            2,
        )

    def test_voice_follow_up_stop_speaking_control_closes_window_without_dispatch(self) -> None:
        interaction_manager = MagicMock()
        telemetry = MagicMock()
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Джарвис, закрой телеграм",
                normalized_transcript="close telegram",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Закрыть Telegram?",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )
        dismiss_control_turn = cli.VoiceTurn(
            raw_transcript="замолчи",
            normalized_transcript="stop speaking",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Джарвис, закрой телеграм",
                normalized_text="close telegram",
                locale_hint="ru-RU",
            ),
        ) as capture_mock, patch(
            "cli.capture_follow_up_voice_turn",
            return_value=dismiss_control_turn,
        ) as follow_up_capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=first_dispatch,
        ) as dispatch_mock, patch(
            "cli.render_interaction_dispatch"
        ) as render_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command(
                "voice",
                speak_enabled=False,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice: follow-up... speak now.", output)
        self.assertIn("voice: follow-up closed.", output)
        self.assertNotIn('recognized: "stop speaking"', output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        follow_up_capture_mock.assert_called_once_with(
            voice_turn=first_dispatch.voice_turn,
            audio_policy=ANY,
        )
        dispatch_mock.assert_called_once_with(
            capture_mock.return_value,
            interaction_manager=interaction_manager,
            session_context=self.session_context,
            speak_enabled=False,
        )
        render_mock.assert_called_once()
        telemetry.record_follow_up_opened.assert_called_once_with(first_dispatch.voice_turn)
        telemetry.record_follow_up_control.assert_called_once_with(
            first_dispatch.voice_turn,
            dismiss_control_turn,
            action="dismiss_follow_up",
        )
        telemetry.record_follow_up_completed.assert_not_called()

    def test_voice_follow_up_listen_again_control_does_not_play_error_earcon_when_enabled(self) -> None:
        interaction_manager = MagicMock()
        telemetry = MagicMock()
        earcon_provider = MagicMock()
        retry_control_turn = cli.VoiceTurn(
            raw_transcript="listen again",
            normalized_transcript="listen again",
            detected_locale="en-US",
            locale_hint="en-US",
        )
        final_follow_up_turn = cli.VoiceTurn(
            raw_transcript="sure",
            normalized_transcript="sure",
            detected_locale="en-US",
            locale_hint="en-US",
        )
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="close telegram",
                normalized_transcript="close telegram",
                detected_locale="en-US",
                locale_hint="en-US",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Do you want me to close Telegram? Say yes or no.",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )
        second_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="sure",
                normalized_transcript="sure",
                detected_locale="en-US",
                locale_hint="en-US",
                lifecycle_state="executing",
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="close telegram",
                normalized_text="close telegram",
                locale_hint="en-US",
            ),
        ), patch(
            "cli.capture_follow_up_voice_turn",
            side_effect=[retry_control_turn, final_follow_up_turn],
        ), patch(
            "cli.dispatch_voice_turn",
            side_effect=[first_dispatch, second_dispatch],
        ), patch(
            "cli.render_interaction_dispatch"
        ), patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch(
            "cli.build_default_earcon_provider",
            return_value=earcon_provider,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1", "JARVIS_VOICE_EARCONS": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command(
                "voice",
                speak_enabled=False,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice: listening again... speak now.", output)
        self.assertEqual(
            [args[0] for args, _kwargs in earcon_provider.play.call_args_list].count("error"),
            0,
        )

    def test_voice_short_answer_cancel_control_closes_window_without_dispatch(self) -> None:
        interaction_manager = MagicMock()
        telemetry = MagicMock()
        tts_provider = MagicMock()
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Что ты умеешь?",
                normalized_transcript="what can you do",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Я могу открывать приложения и отвечать на вопросы.",
                follow_up_reason="short_answer",
                follow_up_window_seconds=6.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=SpeechUtterance(
                    text="Я могу открывать приложения и отвечать на вопросы.",
                    locale="ru-RU",
                ),
            ),
        )
        dismiss_control_turn = cli.VoiceTurn(
            raw_transcript="стоп",
            normalized_transcript="cancel",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Что ты умеешь?",
                normalized_text="what can you do",
                locale_hint="ru-RU",
            ),
        ) as capture_mock, patch(
            "cli.capture_follow_up_voice_turn",
            return_value=dismiss_control_turn,
        ) as follow_up_capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=first_dispatch,
        ) as dispatch_mock, patch(
            "cli.render_interaction_dispatch"
        ) as render_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch(
            "cli.build_default_tts_provider",
            return_value=tts_provider,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command(
                "voice",
                speak_enabled=True,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertTrue(speak_enabled)
        self.assertIn("voice: follow-up... speak now.", output)
        self.assertIn("voice: follow-up closed.", output)
        self.assertNotIn('recognized: "cancel"', output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        follow_up_capture_mock.assert_called_once_with(
            voice_turn=first_dispatch.voice_turn,
            audio_policy=ANY,
        )
        dispatch_mock.assert_called_once_with(
            capture_mock.return_value,
            interaction_manager=interaction_manager,
            session_context=self.session_context,
            speak_enabled=True,
        )
        render_mock.assert_called_once()
        telemetry.record_follow_up_opened.assert_called_once_with(first_dispatch.voice_turn)
        telemetry.record_follow_up_control.assert_called_once_with(
            first_dispatch.voice_turn,
            dismiss_control_turn,
            action="dismiss_follow_up",
        )
        telemetry.record_follow_up_completed.assert_not_called()

    def test_voice_follow_up_stop_speaking_control_does_not_play_error_earcon_when_enabled(self) -> None:
        interaction_manager = MagicMock()
        telemetry = MagicMock()
        earcon_provider = MagicMock()
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="close telegram",
                normalized_transcript="close telegram",
                detected_locale="en-US",
                locale_hint="en-US",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Do you want me to close Telegram? Say yes or no.",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )
        dismiss_control_turn = cli.VoiceTurn(
            raw_transcript="stop speaking",
            normalized_transcript="stop speaking",
            detected_locale="en-US",
            locale_hint="en-US",
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="close telegram",
                normalized_text="close telegram",
                locale_hint="en-US",
            ),
        ), patch(
            "cli.capture_follow_up_voice_turn",
            return_value=dismiss_control_turn,
        ), patch(
            "cli.dispatch_voice_turn",
            return_value=first_dispatch,
        ), patch(
            "cli.render_interaction_dispatch"
        ), patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch(
            "cli.build_default_earcon_provider",
            return_value=earcon_provider,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1", "JARVIS_VOICE_EARCONS": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command(
                "voice",
                speak_enabled=False,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice: follow-up closed.", output)
        self.assertEqual(
            [args[0] for args, _kwargs in earcon_provider.play.call_args_list].count("error"),
            0,
        )

    def test_voice_short_answer_not_now_control_closes_window_without_dispatch(self) -> None:
        interaction_manager = MagicMock()
        telemetry = MagicMock()
        tts_provider = MagicMock()
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="What can you do?",
                normalized_transcript="what can you do",
                detected_locale="en-US",
                locale_hint="en-US",
                lifecycle_state="awaiting_follow_up",
                spoken_response="I can open apps and answer questions.",
                follow_up_reason="short_answer",
                follow_up_window_seconds=6.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=SpeechUtterance(
                    text="I can open apps and answer questions.",
                    locale="en-US",
                ),
            ),
        )
        dismiss_control_turn = cli.VoiceTurn(
            raw_transcript="not now",
            normalized_transcript="not now",
            detected_locale="en-US",
            locale_hint="en-US",
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="What can you do?",
                normalized_text="what can you do",
                locale_hint="en-US",
            ),
        ) as capture_mock, patch(
            "cli.capture_follow_up_voice_turn",
            return_value=dismiss_control_turn,
        ) as follow_up_capture_mock, patch(
            "cli.dispatch_voice_turn",
            return_value=first_dispatch,
        ) as dispatch_mock, patch(
            "cli.render_interaction_dispatch"
        ) as render_mock, patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch(
            "cli.build_default_tts_provider",
            return_value=tts_provider,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, output = self._run_command(
                "voice",
                speak_enabled=True,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertTrue(speak_enabled)
        self.assertIn("voice: follow-up... speak now.", output)
        self.assertIn("voice: follow-up closed.", output)
        self.assertNotIn('recognized: "not now"', output)
        capture_mock.assert_called_once_with(
            timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=ANY,
        )
        follow_up_capture_mock.assert_called_once_with(
            voice_turn=first_dispatch.voice_turn,
            audio_policy=ANY,
        )
        dispatch_mock.assert_called_once_with(
            capture_mock.return_value,
            interaction_manager=interaction_manager,
            session_context=self.session_context,
            speak_enabled=True,
        )
        render_mock.assert_called_once()
        telemetry.record_follow_up_opened.assert_called_once_with(first_dispatch.voice_turn)
        telemetry.record_follow_up_control.assert_called_once_with(
            first_dispatch.voice_turn,
            dismiss_control_turn,
            action="dismiss_follow_up",
        )
        telemetry.record_follow_up_completed.assert_not_called()

    def test_voice_command_records_telemetry_for_follow_up_path(self) -> None:
        interaction_manager = MagicMock()
        telemetry = MagicMock()
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Джарвис, закрой телеграм",
                normalized_transcript="close telegram",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Закрыть Telegram?",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
                follow_up_reason="confirmation",
            ),
        )
        second_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Да",
                normalized_transcript="confirm",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="executing",
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
                follow_up_reason=None,
            ),
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Джарвис, закрой телеграм",
                normalized_text="close telegram",
                locale_hint="ru-RU",
            ),
        ) as capture_mock, patch(
            "cli.capture_follow_up_voice_turn",
            return_value=cli.VoiceTurn(
                raw_transcript="Да",
                normalized_transcript="confirm",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
            ),
        ) as follow_up_capture_mock, patch(
            "cli.dispatch_voice_turn",
            side_effect=[first_dispatch, second_dispatch],
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
            clear=False,
        ):
            should_exit, speak_enabled = cli._handle_cli_command(
                "voice",
                runtime_manager=self.runtime_manager,
                session_context=self.session_context,
                speak_enabled=False,
                interaction_manager=interaction_manager,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertEqual(telemetry.record_capture.call_count, 2)
        self.assertEqual(telemetry.record_dispatch.call_count, 2)
        telemetry.record_follow_up_opened.assert_called_once_with(first_dispatch.voice_turn)
        telemetry.record_follow_up_completed.assert_called_once_with(
            first_dispatch.voice_turn,
            follow_up_capture_mock.return_value,
        )
        telemetry.record_follow_up_loop.assert_called_once_with(
            completed_turns=1,
            limit_hit=False,
        )
        initial_capture_kwargs = telemetry.record_capture.call_args_list[0].kwargs
        self.assertEqual(initial_capture_kwargs["phase"], "initial")
        self.assertEqual(initial_capture_kwargs["voice_turn"], capture_mock.return_value)
        follow_up_capture_kwargs = telemetry.record_capture.call_args_list[1].kwargs
        self.assertEqual(follow_up_capture_kwargs["phase"], "follow_up")
        self.assertEqual(follow_up_capture_kwargs["voice_turn"], follow_up_capture_mock.return_value)

    def test_voice_short_answer_follow_up_records_telemetry_when_auto_captured(self) -> None:
        interaction_manager = MagicMock()
        telemetry = MagicMock()
        tts_provider = MagicMock()
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Что ты умеешь?",
                normalized_transcript="what can you do",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Я могу открывать приложения и отвечать на вопросы.",
                follow_up_reason="short_answer",
                follow_up_window_seconds=6.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=SpeechUtterance(
                    text="Я могу открывать приложения и отвечать на вопросы.",
                    locale="ru-RU",
                ),
                follow_up_reason="short_answer",
            ),
        )
        second_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Скажи подробнее",
                normalized_transcript="Explain more",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="answering",
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
                follow_up_reason=None,
            ),
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Что ты умеешь?",
                normalized_text="what can you do",
                locale_hint="ru-RU",
            ),
        ) as capture_mock, patch(
            "cli.capture_follow_up_voice_turn",
            return_value=cli.VoiceTurn(
                raw_transcript="Скажи подробнее",
                normalized_transcript="Explain more",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
            ),
        ) as follow_up_capture_mock, patch(
            "cli.dispatch_voice_turn",
            side_effect=[first_dispatch, second_dispatch],
        ), patch(
            "cli.render_interaction_dispatch"
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
            clear=False,
        ):
            should_exit, speak_enabled = cli._handle_cli_command(
                "voice",
                runtime_manager=self.runtime_manager,
                session_context=self.session_context,
                speak_enabled=True,
                interaction_manager=interaction_manager,
                telemetry=telemetry,
                tts_provider=tts_provider,
            )

        self.assertFalse(should_exit)
        self.assertTrue(speak_enabled)
        self.assertEqual(telemetry.record_capture.call_count, 2)
        self.assertEqual(telemetry.record_dispatch.call_count, 2)
        telemetry.record_follow_up_opened.assert_called_once_with(first_dispatch.voice_turn)
        telemetry.record_follow_up_completed.assert_called_once_with(
            first_dispatch.voice_turn,
            follow_up_capture_mock.return_value,
        )
        telemetry.record_follow_up_loop.assert_called_once_with(
            completed_turns=1,
            limit_hit=False,
        )
        initial_capture_kwargs = telemetry.record_capture.call_args_list[0].kwargs
        self.assertEqual(initial_capture_kwargs["phase"], "initial")
        self.assertEqual(initial_capture_kwargs["voice_turn"], capture_mock.return_value)
        follow_up_capture_kwargs = telemetry.record_capture.call_args_list[1].kwargs
        self.assertEqual(follow_up_capture_kwargs["phase"], "follow_up")
        self.assertEqual(follow_up_capture_kwargs["voice_turn"], follow_up_capture_mock.return_value)

    def test_speak_aliases_toggle_without_runtime_dispatch(self) -> None:
        cases = [
            ("speak on", False, True, "Speech output enabled."),
            ("/speak on", False, True, "Speech output enabled."),
            ("speak off", True, False, "Speech output disabled."),
            ("/speak off", True, False, "Speech output disabled."),
        ]

        for command, initial_speak, expected_speak, expected_line in cases:
            with self.subTest(command=command):
                with patch("cli._handle_runtime_input") as runtime_mock:
                    should_exit, speak_enabled, output = self._run_command(command, speak_enabled=initial_speak)

                self.assertFalse(should_exit)
                self.assertEqual(speak_enabled, expected_speak)
                self.assertIn(expected_line, output)
                runtime_mock.assert_not_called()

    def test_voice_failure_shows_message_and_hint(self) -> None:
        error = VoiceInputError(
            "PERMISSION_DENIED",
            "Speech recognition permission was denied.",
            hint="Check macOS Settings -> Privacy & Security -> Microphone / Speech Recognition.",
        )

        with patch("cli.capture_voice_turn", side_effect=error), patch("cli._handle_runtime_input") as runtime_mock:
            should_exit, speak_enabled, output = self._run_command("/voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice: Speech recognition permission was denied.", output)
        self.assertIn(
            "hint: Check macOS Settings -> Privacy & Security -> Microphone / Speech Recognition.",
            output,
        )
        runtime_mock.assert_not_called()

    def test_normal_command_reaches_runtime_path(self) -> None:
        with patch("cli.capture_voice_turn") as capture_mock, patch("cli._handle_runtime_input") as runtime_mock:
            should_exit, speak_enabled, output = self._run_command("open browser", speak_enabled=True)

        self.assertFalse(should_exit)
        self.assertTrue(speak_enabled)
        self.assertEqual(output, "")
        capture_mock.assert_not_called()
        runtime_mock.assert_called_once_with(
            "open browser",
            runtime_manager=self.runtime_manager,
            session_context=self.session_context,
            speak_enabled=True,
        )

    def test_help_reset_quit_are_intercepted_before_runtime(self) -> None:
        with patch("cli._handle_runtime_input") as runtime_mock:
            should_exit, speak_enabled, help_output = self._run_command("help", speak_enabled=False)
            self.assertFalse(should_exit)
            self.assertFalse(speak_enabled)
            self.assertIn("Shell commands:", help_output)

            should_exit, speak_enabled, reset_output = self._run_command("reset", speak_enabled=False)
            self.assertFalse(should_exit)
            self.assertFalse(speak_enabled)
            self.assertIn("Runtime reset.", reset_output)
            self.runtime_manager.clear_runtime.assert_called()
            self.session_context.clear_expired_or_resettable_context.assert_called_with(
                preserve_recent_context=False
            )

            should_exit, speak_enabled, quit_output = self._run_command("quit", speak_enabled=False)
            self.assertTrue(should_exit)
            self.assertFalse(speak_enabled)
            self.assertEqual(quit_output, "")

        runtime_mock.assert_not_called()

    def test_qa_helper_commands_are_intercepted_before_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_artifact = str(Path(tmpdir) / "missing_live_smoke_artifact.json")
            manual_artifact = Path(tmpdir) / "manual_beta_checklist.json"
            release_review_artifact = Path(tmpdir) / "beta_release_review.json"
            beta_readiness_artifact = Path(tmpdir) / "beta_readiness.json"
            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="deterministic",
                    rollout_stage="alpha_opt_in",
                    backend_selection_source="builtin_default",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=False,
                        fallback_enabled=True,
                        open_domain_enabled=False,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                    "JARVIS_QA_OPENAI_LIVE_ARTIFACT": missing_artifact,
                },
                clear=False,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=beta_readiness_artifact,
            ):
                should_exit, speak_enabled, backend_output = self._run_command("qa backend", speak_enabled=False)
                self.assertFalse(should_exit)
                self.assertFalse(speak_enabled)
                self.assertIn("qa backend: deterministic", backend_output)
                self.assertIn("rollout stage: alpha_opt_in", backend_output)
                self.assertIn("default question path: deterministic", backend_output)
                self.assertIn("backend selection source: builtin_default", backend_output)
                self.assertIn("llm provider: openai_responses", backend_output)

                should_exit, speak_enabled, model_output = self._run_command("qa model", speak_enabled=False)
                self.assertFalse(should_exit)
                self.assertFalse(speak_enabled)
                self.assertIn("qa model: gpt-5-nano", model_output)
                self.assertIn("reasoning effort: minimal", model_output)

                should_exit, speak_enabled, smoke_output = self._run_command("qa smoke", speak_enabled=False)
                self.assertFalse(should_exit)
                self.assertFalse(speak_enabled)
                self.assertIn("qa smoke command: scripts/run_openai_live_smoke.sh", smoke_output)
                self.assertIn("api key env: OPENAI_API_KEY (present)", smoke_output)
                self.assertIn("debug flag: JARVIS_QA_DEBUG (missing)", smoke_output)
                self.assertIn("live smoke artifact:", smoke_output)
                self.assertIn("(missing)", smoke_output)
                self.assertIn("open-domain live verification: no", smoke_output)

                should_exit, speak_enabled, gate_output = self._run_command("qa gate", speak_enabled=False)
                self.assertFalse(should_exit)
                self.assertFalse(speak_enabled)
                self.assertIn("qa gate candidate: llm_env", gate_output)
                self.assertIn("fallback: on", gate_output)
                self.assertIn("precheck: blocked", gate_output)
                self.assertIn("blocker: open-domain question answering is disabled", gate_output)
                self.assertIn("blocker: live smoke artifact is missing", gate_output)
                self.assertIn("smoke command: scripts/run_openai_live_smoke.sh llm_env", gate_output)
                self.assertIn(
                    "compare command: scripts/run_qa_rollout_gate.sh llm_env",
                    gate_output,
                )

                should_exit, speak_enabled, strict_gate_output = self._run_command("qa gate strict", speak_enabled=False)
                self.assertFalse(should_exit)
                self.assertFalse(speak_enabled)
                self.assertIn("qa gate candidate: llm_env_strict", strict_gate_output)
                self.assertIn("fallback: off", strict_gate_output)
                self.assertIn("precheck: blocked", strict_gate_output)
                self.assertIn("blocker: open-domain question answering is disabled", strict_gate_output)
                self.assertIn("smoke command: scripts/run_openai_live_smoke.sh llm_env_strict", strict_gate_output)
                self.assertIn(
                    "compare command: scripts/run_qa_rollout_gate.sh llm_env_strict",
                    strict_gate_output,
                )

                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)
                self.assertFalse(should_exit)
                self.assertFalse(speak_enabled)
                self.assertIn("qa beta stage: alpha_opt_in", beta_output)
                self.assertIn("qa beta default path: deterministic", beta_output)
                self.assertIn("qa beta recommended candidate: none", beta_output)
                self.assertIn("qa beta manual checklist artifact:", beta_output)
                self.assertIn("qa beta manual checklist pending items:", beta_output)
                self.assertIn("qa beta manual checklist helper command: qa checklist", beta_output)
                self.assertIn("qa beta manual checklist guide command: python3 -m qa.manual_beta_checklist", beta_output)
                self.assertIn("arbitrary_factual_question", beta_output)
                self.assertIn("provider_unavailable_path", beta_output)
                self.assertIn(
                    "qa beta release review pending checks: latency_review, cost_review, operator_signoff, product_approval",
                    beta_output,
                )
                self.assertIn("qa beta recorded candidate: none", beta_output)
                self.assertIn("qa beta decision artifact:", beta_output)
                self.assertIn("(missing)", beta_output)
                self.assertIn("qa beta decision artifact fresh: n/a", beta_output)
                self.assertIn("qa beta decision artifact consistent with latest evidence: n/a", beta_output)
                self.assertIn("qa beta decision: blocked until beta_question_default is explicitly approved", beta_output)
                self.assertIn("qa beta technical precheck: blocked", beta_output)
                self.assertIn("candidate llm_env: blocked", beta_output)
                self.assertIn("candidate llm_env_strict: blocked", beta_output)
                self.assertIn("manual checklist doc: docs/manual_verification_commands.md", beta_output)
                self.assertIn("decision gate doc: docs/llm_default_decision_gate.md", beta_output)

        runtime_mock.assert_not_called()

    def test_voice_readiness_helper_is_intercepted_before_runtime(self) -> None:
        readiness_record = SimpleNamespace(next_step_kind="complete_manual_voice_verification")

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.build_voice_readiness_record",
            return_value=readiness_record,
        ) as record_mock, patch(
            "cli.format_voice_readiness_record",
            return_value="VOICE READINESS SUMMARY",
        ) as format_mock:
            should_exit, speak_enabled, output = self._run_command("voice readiness", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("VOICE READINESS SUMMARY", output)
        record_mock.assert_called_once_with()
        format_mock.assert_called_once_with(readiness_record)
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_readiness_write_is_intercepted_and_blocked_before_runtime(self) -> None:
        readiness_record = SimpleNamespace(voice_ready=False)

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.build_voice_readiness_record",
            return_value=readiness_record,
        ) as record_mock, patch(
            "cli.format_voice_readiness_record",
            return_value="VOICE READINESS SUMMARY",
        ) as format_mock, patch(
            "cli.write_voice_readiness_artifact"
        ) as write_mock:
            should_exit, speak_enabled, output = self._run_command("voice readiness write", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("VOICE READINESS SUMMARY", output)
        self.assertIn("voice readiness is still blocked; refusing to write final artifact", output)
        record_mock.assert_called_once_with()
        format_mock.assert_called_once_with(readiness_record)
        write_mock.assert_not_called()
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_readiness_write_persists_artifact_before_runtime(self) -> None:
        readiness_record = SimpleNamespace(voice_ready=True)

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.build_voice_readiness_record",
            return_value=readiness_record,
        ) as record_mock, patch(
            "cli.write_voice_readiness_artifact",
            return_value="/tmp/voice_readiness.json",
        ) as write_mock:
            should_exit, speak_enabled, output = self._run_command("voice readiness write", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("wrote voice readiness artifact: /tmp/voice_readiness.json", output)
        record_mock.assert_called_once_with()
        write_mock.assert_called_once_with(readiness_record)
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_mode_helper_is_intercepted_before_runtime(self) -> None:
        mode_status = SimpleNamespace(max_auto_follow_up_turns=2)

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.build_voice_mode_status",
            return_value=mode_status,
        ) as status_mock, patch(
            "cli.format_voice_mode_status",
            return_value="VOICE MODE SUMMARY",
        ) as format_mock:
            should_exit, speak_enabled, output = self._run_command("voice mode", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("VOICE MODE SUMMARY", output)
        status_mock.assert_called_once_with()
        format_mock.assert_called_once_with(mode_status)
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_last_helper_is_intercepted_before_runtime(self) -> None:
        voice_session_state = MagicMock()

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.format_voice_last_event",
            return_value="VOICE LAST SUMMARY",
        ) as format_mock:
            should_exit, speak_enabled, output = self._run_command(
                "voice last",
                speak_enabled=False,
                voice_session_state=voice_session_state,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("VOICE LAST SUMMARY", output)
        format_mock.assert_called_once_with(voice_session_state)
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_tts_last_helper_is_intercepted_before_runtime(self) -> None:
        voice_session_state = MagicMock()

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.format_voice_tts_last_result",
            return_value="VOICE TTS LAST SUMMARY",
        ) as format_mock:
            should_exit, speak_enabled, output = self._run_command(
                "voice tts last",
                speak_enabled=False,
                voice_session_state=voice_session_state,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("VOICE TTS LAST SUMMARY", output)
        format_mock.assert_called_once_with(voice_session_state)
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_status_helper_is_intercepted_before_runtime(self) -> None:
        telemetry = MagicMock()
        session_status = SimpleNamespace(speak_enabled=True)

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.build_voice_session_status",
            return_value=session_status,
        ) as status_mock, patch(
            "cli.format_voice_session_status",
            return_value="VOICE STATUS SUMMARY",
        ) as format_mock:
            should_exit, speak_enabled, output = self._run_command(
                "voice status",
                speak_enabled=True,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertTrue(speak_enabled)
        self.assertIn("VOICE STATUS SUMMARY", output)
        telemetry.snapshot.assert_called_once_with()
        status_mock.assert_called_once_with(
            speak_enabled=True,
            telemetry_snapshot=telemetry.snapshot.return_value,
        )
        format_mock.assert_called_once_with(session_status)
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_tts_backend_helper_is_intercepted_before_runtime(self) -> None:
        tts_provider = MagicMock()
        backend_status = SimpleNamespace(backend_name="macos_say_legacy")

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.build_default_tts_provider",
            return_value=tts_provider,
        ) as provider_mock, patch(
            "cli.build_tts_backend_status",
            return_value=backend_status,
        ) as status_mock, patch(
            "cli.format_tts_backend_status",
            return_value="VOICE TTS BACKEND SUMMARY",
        ) as format_mock:
            should_exit, speak_enabled, output = self._run_command("voice tts backend", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("VOICE TTS BACKEND SUMMARY", output)
        provider_mock.assert_called_once_with()
        status_mock.assert_called_once_with(tts_provider)
        format_mock.assert_called_once_with(backend_status)
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_tts_voices_helper_is_intercepted_before_runtime(self) -> None:
        tts_provider = MagicMock()
        voice_inventory = SimpleNamespace(voices=())

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.build_default_tts_provider",
            return_value=tts_provider,
        ) as provider_mock, patch(
            "cli.build_tts_voice_inventory",
            return_value=voice_inventory,
        ) as inventory_mock, patch(
            "cli.format_tts_voice_inventory",
            return_value="VOICE TTS VOICES SUMMARY",
        ) as format_mock:
            should_exit, speak_enabled, output = self._run_command("voice tts voices", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("VOICE TTS VOICES SUMMARY", output)
        provider_mock.assert_called_once_with()
        inventory_mock.assert_called_once_with(tts_provider)
        format_mock.assert_called_once_with(voice_inventory)
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_tts_current_helper_is_intercepted_before_runtime(self) -> None:
        tts_provider = MagicMock()
        current_status = SimpleNamespace(resolutions=())

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.build_default_tts_provider",
            return_value=tts_provider,
        ) as provider_mock, patch(
            "cli.build_tts_current_status",
            return_value=current_status,
        ) as status_mock, patch(
            "cli.format_tts_current_status",
            return_value="VOICE TTS CURRENT SUMMARY",
        ) as format_mock:
            should_exit, speak_enabled, output = self._run_command("voice tts current", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("VOICE TTS CURRENT SUMMARY", output)
        provider_mock.assert_called_once_with()
        status_mock.assert_called_once_with(tts_provider)
        format_mock.assert_called_once_with(current_status)
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_tts_doctor_helper_is_intercepted_before_runtime(self) -> None:
        tts_provider = MagicMock()
        doctor_status = SimpleNamespace(guidance=())

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.build_default_tts_provider",
            return_value=tts_provider,
        ) as provider_mock, patch(
            "cli.build_tts_doctor_status",
            return_value=doctor_status,
        ) as status_mock, patch(
            "cli.format_tts_doctor_status",
            return_value="VOICE TTS DOCTOR SUMMARY",
        ) as format_mock:
            should_exit, speak_enabled, output = self._run_command("voice tts doctor", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("VOICE TTS DOCTOR SUMMARY", output)
        provider_mock.assert_called_once_with()
        status_mock.assert_called_once_with(tts_provider)
        format_mock.assert_called_once_with(doctor_status)
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_tts_say_helper_speaks_direct_russian_text_without_runtime(self) -> None:
        tts_provider = MagicMock()
        tts_provider.speak.return_value = TTSResult(
            ok=True,
            backend_name="yandex_speechkit",
            voice_id="yandex:ermil:good",
        )

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.build_default_tts_provider",
            return_value=tts_provider,
        ) as provider_mock:
            should_exit, speak_enabled, output = self._run_command("voice tts say ru Привет, мир", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice tts say: ok (yandex_speechkit, locale=ru-RU), voice=yandex:ermil:good", output)
        provider_mock.assert_called_once_with()
        tts_provider.speak.assert_called_once_with(SpeechUtterance(text="Привет, мир", locale="ru-RU"))
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_tts_say_helper_detects_locale_from_text(self) -> None:
        tts_provider = MagicMock()
        tts_provider.speak.return_value = TTSResult(ok=True, backend_name="local_piper", voice_id="piper-en")

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.build_default_tts_provider",
            return_value=tts_provider,
        ) as provider_mock:
            should_exit, speak_enabled, output = self._run_command("voice tts say Hello there", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice tts say: ok (local_piper, locale=en-US), voice=piper-en", output)
        provider_mock.assert_called_once_with()
        tts_provider.speak.assert_called_once_with(SpeechUtterance(text="Hello there", locale="en-US"))
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_tts_say_helper_requires_text(self) -> None:
        tts_provider = MagicMock()

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.build_default_tts_provider",
            return_value=tts_provider,
        ) as provider_mock:
            should_exit, speak_enabled, output = self._run_command("voice tts say ru", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice tts say usage: voice tts say [ru|en] <text>", output)
        provider_mock.assert_not_called()
        tts_provider.speak.assert_not_called()
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_command_records_last_dispatch_in_session_state(self) -> None:
        interaction_manager = MagicMock()
        voice_session_state = MagicMock()
        dispatch_result = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Открой телеграм",
                normalized_transcript="open telegram",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="executing",
                interaction_kind="command",
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Открой телеграм",
                normalized_text="open telegram",
                locale_hint="ru-RU",
            ),
        ), patch(
            "cli.dispatch_voice_turn",
            return_value=dispatch_result,
        ), patch(
            "cli.render_interaction_dispatch"
        ), patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ):
            should_exit, speak_enabled, _output = self._run_command(
                "voice",
                speak_enabled=False,
                voice_session_state=voice_session_state,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        voice_session_state.record_dispatch.assert_called_once_with(dispatch_result.voice_turn)

    def test_voice_follow_up_control_records_last_control_in_session_state(self) -> None:
        interaction_manager = MagicMock()
        voice_session_state = MagicMock()
        first_dispatch = SimpleNamespace(
            voice_turn=cli.VoiceTurn(
                raw_transcript="Закрой телеграм",
                normalized_transcript="close telegram",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                spoken_response="Закрыть Telegram?",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            ),
            interaction=SimpleNamespace(
                visible_lines=(),
                speech_utterance=None,
            ),
        )
        dismiss_control_turn = cli.VoiceTurn(
            raw_transcript="замолчи",
            normalized_transcript="stop speaking",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )

        with patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Закрой телеграм",
                normalized_text="close telegram",
                locale_hint="ru-RU",
            ),
        ), patch(
            "cli.capture_follow_up_voice_turn",
            return_value=dismiss_control_turn,
        ), patch(
            "cli.dispatch_voice_turn",
            return_value=first_dispatch,
        ), patch(
            "cli.render_interaction_dispatch"
        ), patch(
            "cli._build_default_interaction_manager",
            return_value=interaction_manager,
        ), patch.dict(
            "os.environ",
            {"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
            clear=False,
        ):
            should_exit, speak_enabled, _output = self._run_command(
                "voice",
                speak_enabled=False,
                voice_session_state=voice_session_state,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        voice_session_state.record_control.assert_called_once_with(
            first_dispatch.voice_turn,
            dismiss_control_turn,
            action="dismiss_follow_up",
        )

    def test_voice_gate_helper_is_intercepted_before_runtime(self) -> None:
        gate_report = SimpleNamespace(gate_status="blocked")

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.build_voice_readiness_gate_report",
            return_value=gate_report,
        ) as report_mock, patch(
            "cli.format_voice_readiness_gate_report",
            return_value="VOICE GATE SUMMARY",
        ) as format_mock:
            should_exit, speak_enabled, output = self._run_command("voice gate", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("VOICE GATE SUMMARY", output)
        report_mock.assert_called_once_with()
        format_mock.assert_called_once_with(gate_report)
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_telemetry_helper_is_intercepted_before_runtime(self) -> None:
        telemetry = MagicMock()

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.format_voice_telemetry_snapshot",
            return_value="VOICE TELEMETRY SUMMARY",
        ) as format_mock:
            should_exit, speak_enabled, output = self._run_command(
                "voice telemetry",
                speak_enabled=False,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("VOICE TELEMETRY SUMMARY", output)
        telemetry.snapshot.assert_called_once_with()
        format_mock.assert_called_once_with(telemetry.snapshot.return_value)
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_telemetry_artifact_helper_is_intercepted_before_runtime(self) -> None:
        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.load_voice_telemetry_snapshot",
            return_value=(Path("/tmp/qa/voice_telemetry.json"), "missing", None, None, None),
        ) as load_mock, patch(
            "cli.format_voice_telemetry_artifact_summary",
            return_value="VOICE TELEMETRY ARTIFACT SUMMARY",
        ) as format_mock:
            should_exit, speak_enabled, output = self._run_command("voice telemetry artifact", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("VOICE TELEMETRY ARTIFACT SUMMARY", output)
        load_mock.assert_called_once_with()
        format_mock.assert_called_once_with(
            artifact_path=Path("/tmp/qa/voice_telemetry.json"),
            artifact_status="missing",
            artifact_created_at=None,
            snapshot=None,
            artifact_error=None,
        )
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_telemetry_reset_is_intercepted_before_runtime(self) -> None:
        telemetry = MagicMock()

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock:
            should_exit, speak_enabled, output = self._run_command(
                "voice telemetry reset",
                speak_enabled=False,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("Voice telemetry reset.", output)
        telemetry.clear.assert_called_once_with()
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_voice_telemetry_write_is_intercepted_before_runtime(self) -> None:
        telemetry = MagicMock()

        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.capture_voice_turn"
        ) as capture_mock, patch(
            "cli.write_voice_telemetry_artifact",
            return_value=Path("/tmp/qa/voice_telemetry.json"),
        ) as write_mock:
            should_exit, speak_enabled, output = self._run_command(
                "voice telemetry write",
                speak_enabled=False,
                telemetry=telemetry,
            )

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("wrote voice telemetry artifact: /tmp/qa/voice_telemetry.json", output)
        telemetry.snapshot.assert_called_once_with()
        write_mock.assert_called_once_with(telemetry.snapshot.return_value)
        runtime_mock.assert_not_called()
        capture_mock.assert_not_called()

    def test_qa_smoke_reports_green_artifact_and_open_domain_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "openai_live_smoke.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-25T00:00:00+00:00",
                        "question": "Who is the president of France?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=False,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                    "JARVIS_QA_OPENAI_LIVE_ARTIFACT": str(artifact_path),
                },
                clear=False,
            ):
                should_exit, speak_enabled, smoke_output = self._run_command("qa smoke", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn(f"live smoke artifact: {artifact_path} (green)", smoke_output)
        self.assertIn("open-domain live verification: yes", smoke_output)
        runtime_mock.assert_not_called()

    def test_qa_gate_reports_green_matching_precheck(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "openai_live_smoke.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-25T00:00:00+00:00",
                        "question": "Who is the president of France?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 25, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=False,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                    "JARVIS_QA_OPENAI_LIVE_ARTIFACT": str(artifact_path),
                },
                clear=False,
            ):
                should_exit, speak_enabled, gate_output = self._run_command("qa gate", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa gate candidate: llm_env", gate_output)
        self.assertIn(f"live smoke artifact: {artifact_path} (green)", gate_output)
        self.assertIn("live smoke artifact fresh: yes (0.0h)", gate_output)
        self.assertIn("live smoke artifact matches profile: yes", gate_output)
        self.assertIn("open-domain live verification: yes", gate_output)
        self.assertIn("precheck: ready", gate_output)
        self.assertIn("smoke command: scripts/run_openai_live_smoke.sh llm_env", gate_output)
        self.assertIn(
            "compare command: scripts/run_qa_rollout_gate.sh llm_env",
            gate_output,
        )
        self.assertNotIn("blocker:", gate_output)
        runtime_mock.assert_not_called()

    def test_qa_gate_uses_candidate_default_artifact_path_without_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-25T00:00:00+00:00",
                        "question": "Who is the president of France?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 25, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                return_value=artifact_path,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=False,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, gate_output = self._run_command("qa gate", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn(f"live smoke artifact: {artifact_path} (green)", gate_output)
        self.assertIn("precheck: ready", gate_output)
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_ready_candidates_when_artifacts_are_fresh_and_matching(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact = Path(tmpdir) / "manual_beta_checklist.json"
            release_review_artifact = Path(tmpdir) / "beta_release_review.json"
            beta_readiness_artifact = Path(tmpdir) / "beta_readiness.json"

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=beta_readiness_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta stage: alpha_opt_in", beta_output)
        self.assertIn("qa beta technical precheck: ready (llm_env, llm_env_strict)", beta_output)
        self.assertIn("qa beta latest stability evidence: clean (llm_env, llm_env_strict)", beta_output)
        self.assertIn("qa beta recommended candidate: llm_env_strict", beta_output)
        self.assertIn("qa beta launch command: scripts/run_qa_question_beta.sh llm_env_strict", beta_output)
        self.assertIn("qa beta manual checklist artifact:", beta_output)
        self.assertIn("qa beta manual checklist pending items:", beta_output)
        self.assertIn("qa beta manual checklist helper command: qa checklist", beta_output)
        self.assertIn("qa beta manual checklist guide command: python3 -m qa.manual_beta_checklist", beta_output)
        self.assertIn("(missing)", beta_output)
        self.assertIn("qa beta manual checklist artifact fresh: n/a", beta_output)
        self.assertIn("qa beta release review artifact fresh: n/a", beta_output)
        self.assertIn(
            "qa beta release review pending checks: latency_review, cost_review, operator_signoff, product_approval",
            beta_output,
        )
        self.assertIn("qa beta recorded candidate: none", beta_output)
        self.assertIn("qa beta decision artifact:", beta_output)
        self.assertIn("(missing)", beta_output)
        self.assertIn("qa beta decision artifact fresh: n/a", beta_output)
        self.assertIn("qa beta decision artifact consistent with latest evidence: n/a", beta_output)
        self.assertIn("candidate llm_env: ready", beta_output)
        self.assertIn("candidate llm_env_strict: ready", beta_output)
        self.assertIn("stability=green(2/2)", beta_output)
        self.assertIn("stability-fresh=yes", beta_output)
        self.assertIn("fallback=on", beta_output)
        self.assertIn("fallback=off", beta_output)
        self.assertIn("next beta step: complete the manual beta checklist artifact before release sign-off.", beta_output)
        self.assertIn("manual checklist command: python3 -m qa.manual_beta_checklist --all-passed --write-artifact", beta_output)
        self.assertIn("qa beta manual checklist scenario guide:", beta_output)
        self.assertIn("  - arbitrary_factual_question: Arbitrary factual question", beta_output)
        self.assertIn("    input: who is the president of France?", beta_output)
        self.assertIn(
            "    env: JARVIS_QA_BACKEND=llm JARVIS_QA_LLM_ENABLED=true JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true",
            beta_output,
        )
        self.assertIn(
            "    expected: mode=question; answer-kind=open_domain_model; provenance=model_knowledge; no fake local sources",
            beta_output,
        )
        self.assertIn("note: this helper is offline; it does not run smoke, gate, or stability", beta_output)
        runtime_mock.assert_not_called()

    def test_cli_shell_exposes_release_decision_helper_commands(self) -> None:
        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.load_manual_beta_checklist_artifact",
            return_value=(Path("/tmp/manual_beta_checklist.json"), None, None),
        ), patch(
            "cli.build_manual_beta_checklist_record",
            return_value=object(),
        ) as checklist_build_mock, patch(
            "cli.format_manual_beta_checklist_record",
            return_value="CHECKLIST SUMMARY",
        ), patch(
            "cli.load_beta_release_review_artifact",
            return_value=(Path("/tmp/beta_release_review.json"), None, None),
        ), patch(
            "cli.build_beta_release_review_record",
            return_value=object(),
        ) as review_build_mock, patch(
            "cli.format_beta_release_review_record",
            return_value="RELEASE REVIEW SUMMARY",
        ), patch(
            "cli.build_beta_readiness_record",
            return_value=object(),
        ) as readiness_build_mock, patch(
            "cli.format_beta_readiness_record",
            return_value="READINESS SUMMARY",
        ):
            should_exit, speak_enabled, checklist_output = self._run_command("qa checklist", speak_enabled=False)
            self.assertFalse(should_exit)
            self.assertFalse(speak_enabled)
            self.assertIn("CHECKLIST SUMMARY", checklist_output)
            checklist_build_mock.assert_called_once_with(existing_payload=None)

            should_exit, speak_enabled, review_output = self._run_command("qa release review", speak_enabled=False)
            self.assertFalse(should_exit)
            self.assertFalse(speak_enabled)
            self.assertIn("RELEASE REVIEW SUMMARY", review_output)
            review_build_mock.assert_called_once_with(existing_payload=None)

            should_exit, speak_enabled, readiness_output = self._run_command("qa readiness", speak_enabled=False)
            self.assertFalse(should_exit)
            self.assertFalse(speak_enabled)
            self.assertIn("READINESS SUMMARY", readiness_output)
            readiness_build_mock.assert_called_once_with()

        runtime_mock.assert_not_called()

    def test_qa_beta_reports_stale_manual_checklist_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, _manual_created_at, _manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            manual_payload = json.loads(manual_artifact.read_text(encoding="utf-8"))
            manual_payload["created_at"] = "2026-03-24T00:00:00+00:00"
            manual_artifact.write_text(json.dumps(manual_payload, indent=2, sort_keys=True), encoding="utf-8")
            stale_manual_sha256 = hashlib.sha256(manual_artifact.read_bytes()).hexdigest()
            release_review_artifact, _release_review_created_at, _release_review_sha256 = (
                self._write_complete_beta_release_review(
                    tmpdir,
                    candidate_profile="llm_env_strict",
                    manual_created_at="2026-03-24T00:00:00+00:00",
                    manual_sha256=stale_manual_sha256,
                )
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta manual checklist artifact fresh: no (48.0h)", beta_output)
        self.assertIn("qa beta release review artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta release review artifact consistency reason: latest manual checklist artifact is stale",
            beta_output,
        )
        self.assertIn("next beta step: complete the manual beta checklist artifact before release sign-off.", beta_output)
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_failed_stability_blockers_from_latest_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 0,
                            "runs": [],
                            "blocker_counts": {
                                "open-domain answer pass rate is below threshold": 1,
                                "fallback frequency is above threshold": 1,
                            },
                            "failed_case_counts": {},
                            "fallback_case_counts": {
                                "route_mixed_interaction_answer_reply": 1,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 0,
                            "runs": [],
                            "blocker_counts": {
                                "open-domain answer pass rate is below threshold": 2,
                            },
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta recommended candidate: none", beta_output)
        self.assertIn("qa beta manual checklist artifact:", beta_output)
        self.assertIn("qa beta decision artifact fresh: n/a", beta_output)
        self.assertIn("qa beta decision artifact consistent with latest evidence: n/a", beta_output)
        self.assertIn("qa beta latest stability evidence: incomplete", beta_output)
        self.assertIn("candidate llm_env: ready", beta_output)
        self.assertIn("stability=failed(0/2)", beta_output)
        self.assertIn(
            "stability-blockers=open-domain answer pass rate is below threshold x1; fallback frequency is above threshold x1",
            beta_output,
        )
        self.assertIn(
            "stability-fallback-cases=route_mixed_interaction_answer_reply x1",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_release_review_artifact_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            release_review_artifact, _release_review_created_at, _release_review_sha256 = (
                self._write_complete_beta_release_review(
                    tmpdir,
                    candidate_profile="llm_env_strict",
                    manual_created_at=manual_created_at,
                    manual_sha256=manual_sha256,
                )
            )
            manual_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.manual_beta_checklist",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "checklist_id": "beta_question_default",
                            "passed_items": 7,
                            "total_items": 7,
                            "all_passed": True,
                            "items": {},
                            "notes": "rerun after release review",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta release review artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta release review artifact consistency reason: recorded manual checklist artifact fingerprint no longer matches the latest artifact",
            beta_output,
        )
        self.assertIn(
            "release review command: python3 -m qa.beta_release_review --candidate-profile llm_env_strict --latency-reviewed --cost-reviewed --operator-signoff --product-approval --write-artifact",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_uses_incremental_commands_for_partial_manual_and_release_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact = Path(tmpdir) / "manual_beta_checklist.json"
            manual_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.manual_beta_checklist",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "checklist_id": "beta_question_default",
                            "passed_items": 5,
                            "total_items": 7,
                            "all_passed": False,
                            "items": {
                                "arbitrary_factual_question": {"label": "Arbitrary factual question", "passed": True},
                                "arbitrary_explanation_question": {"label": "Arbitrary explanation question", "passed": True},
                                "casual_chat_question": {"label": "Casual chat question", "passed": True},
                                "blocked_state_question": {"label": "Blocked-state question", "passed": False},
                                "grounded_docs_question": {"label": "Grounded docs question", "passed": True},
                                "mixed_question_command": {"label": "Mixed question + command", "passed": True},
                                "provider_unavailable_path": {"label": "Provider unavailable path", "passed": False},
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )
            release_review_artifact = Path(tmpdir) / "beta_release_review.json"
            release_review_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.beta_release_review",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "review_id": "beta_question_default",
                            "candidate_profile": "llm_env_strict",
                            "candidate_selection_source": "explicit",
                            "completed_checks": 2,
                            "total_checks": 4,
                            "all_completed": False,
                            "manual_checklist_artifact_status": "complete",
                            "manual_checklist_artifact_completed": True,
                            "manual_checklist_items_passed": 7,
                            "manual_checklist_items_total": 7,
                            "manual_checklist_artifact_fresh": True,
                            "manual_checklist_artifact_created_at": "2026-03-26T00:00:00+00:00",
                            "manual_checklist_artifact_sha256": hashlib.sha256(manual_artifact.read_bytes()).hexdigest(),
                            "checks": {
                                "latency_review": {"label": "Latency review", "completed": True},
                                "cost_review": {"label": "Cost review", "completed": False},
                                "operator_signoff": {"label": "Operator sign-off", "completed": False},
                                "product_approval": {"label": "Product approval", "completed": True},
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

            self.assertFalse(should_exit)
            self.assertFalse(speak_enabled)
            self.assertIn(
                "manual checklist command: python3 -m qa.manual_beta_checklist --pass blocked_state_question --pass provider_unavailable_path --write-artifact",
                beta_output,
            )
            self.assertIn("qa beta manual checklist helper command: qa checklist", beta_output)
            self.assertIn("qa beta manual checklist guide command: python3 -m qa.manual_beta_checklist", beta_output)
            self.assertIn("qa beta manual checklist scenario guide:", beta_output)
            self.assertIn("  - blocked_state_question: Blocked-state question", beta_output)
            self.assertIn("    input: close Telegram -> what exactly do you need me to confirm?", beta_output)
            self.assertIn(
                "    expected: awaiting_confirmation first; then grounded read-only explanation of the current confirmation boundary",
                beta_output,
            )
            runtime_mock.assert_not_called()

            manual_payload = json.loads(manual_artifact.read_text(encoding="utf-8"))
            manual_payload["report"]["all_passed"] = True
            manual_payload["report"]["passed_items"] = 7
            for item_state in manual_payload["report"]["items"].values():
                item_state["passed"] = True
            manual_artifact.write_text(json.dumps(manual_payload, indent=2, sort_keys=True), encoding="utf-8")
            release_review_payload = json.loads(release_review_artifact.read_text(encoding="utf-8"))
            release_review_payload["report"]["manual_checklist_artifact_created_at"] = str(manual_payload["created_at"])
            release_review_payload["report"]["manual_checklist_artifact_sha256"] = hashlib.sha256(
                manual_artifact.read_bytes()
            ).hexdigest()
            release_review_artifact.write_text(
                json.dumps(release_review_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn(
            "release review command: python3 -m qa.beta_release_review --candidate-profile llm_env_strict --cost-reviewed --operator-signoff --write-artifact",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_uses_full_rerun_commands_for_stale_partial_supporting_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact = Path(tmpdir) / "manual_beta_checklist.json"
            manual_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.manual_beta_checklist",
                        "created_at": "2026-03-24T00:00:00+00:00",
                        "report": {
                            "checklist_id": "beta_question_default",
                            "passed_items": 5,
                            "total_items": 7,
                            "all_passed": False,
                            "items": {
                                "arbitrary_factual_question": {"label": "Arbitrary factual question", "passed": True},
                                "arbitrary_explanation_question": {"label": "Arbitrary explanation question", "passed": True},
                                "casual_chat_question": {"label": "Casual chat question", "passed": True},
                                "blocked_state_question": {"label": "Blocked-state question", "passed": False},
                                "grounded_docs_question": {"label": "Grounded docs question", "passed": True},
                                "mixed_question_command": {"label": "Mixed question + command", "passed": True},
                                "provider_unavailable_path": {"label": "Provider unavailable path", "passed": False},
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

            self.assertFalse(should_exit)
            self.assertFalse(speak_enabled)
            self.assertIn("qa beta manual checklist artifact fresh: no (48.0h)", beta_output)
            self.assertIn(
                "manual checklist command: python3 -m qa.manual_beta_checklist --all-passed --write-artifact",
                beta_output,
            )
            self.assertIn("qa beta manual checklist helper command: qa checklist", beta_output)
            self.assertIn("qa beta manual checklist guide command: python3 -m qa.manual_beta_checklist", beta_output)
            self.assertIn("qa beta manual checklist scenario guide:", beta_output)
            runtime_mock.assert_not_called()

            manual_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.manual_beta_checklist",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "checklist_id": "beta_question_default",
                            "passed_items": 7,
                            "total_items": 7,
                            "all_passed": True,
                            "items": {
                                "arbitrary_factual_question": {"label": "Arbitrary factual question", "passed": True},
                                "arbitrary_explanation_question": {"label": "Arbitrary explanation question", "passed": True},
                                "casual_chat_question": {"label": "Casual chat question", "passed": True},
                                "blocked_state_question": {"label": "Blocked-state question", "passed": True},
                                "grounded_docs_question": {"label": "Grounded docs question", "passed": True},
                                "mixed_question_command": {"label": "Mixed question + command", "passed": True},
                                "provider_unavailable_path": {"label": "Provider unavailable path", "passed": True},
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )
            release_review_artifact = Path(tmpdir) / "beta_release_review.json"
            release_review_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.beta_release_review",
                        "created_at": "2026-03-24T00:00:00+00:00",
                        "report": {
                            "review_id": "beta_question_default",
                            "candidate_profile": "llm_env_strict",
                            "candidate_selection_source": "explicit",
                            "completed_checks": 2,
                            "total_checks": 4,
                            "all_completed": False,
                            "manual_checklist_artifact_status": "complete",
                            "manual_checklist_artifact_completed": True,
                            "manual_checklist_items_passed": 7,
                            "manual_checklist_items_total": 7,
                            "manual_checklist_artifact_fresh": True,
                            "manual_checklist_artifact_created_at": "2026-03-26T00:00:00+00:00",
                            "manual_checklist_artifact_sha256": hashlib.sha256(manual_artifact.read_bytes()).hexdigest(),
                            "checks": {
                                "latency_review": {"label": "Latency review", "completed": True},
                                "cost_review": {"label": "Cost review", "completed": False},
                                "operator_signoff": {"label": "Operator sign-off", "completed": False},
                                "product_approval": {"label": "Product approval", "completed": True},
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta release review artifact fresh: no (48.0h)", beta_output)
        self.assertIn(
            "release review command: python3 -m qa.beta_release_review --candidate-profile llm_env_strict --latency-reviewed --cost-reviewed --operator-signoff --product-approval --write-artifact",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_recorded_beta_readiness_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            release_review_artifact, release_review_created_at, release_review_sha256 = self._write_complete_beta_release_review(
                tmpdir,
                candidate_profile="llm_env_strict",
                manual_created_at=manual_created_at,
                manual_sha256=manual_sha256,
            )
            beta_artifact = self._write_ready_beta_readiness_artifact(
                tmpdir,
                artifact_llm_env=artifact_llm_env,
                artifact_llm_env_strict=artifact_llm_env_strict,
                stability_llm_env=stability_llm_env,
                stability_llm_env_strict=stability_llm_env_strict,
                manual_created_at=manual_created_at,
                manual_sha256=manual_sha256,
                release_review_created_at=release_review_created_at,
                release_review_sha256=release_review_sha256,
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=beta_artifact,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta recorded candidate: llm_env_strict", beta_output)
        self.assertIn("qa beta recorded candidate selection: explicit", beta_output)
        self.assertIn("qa beta manual checklist artifact:", beta_output)
        self.assertIn("(complete(7/7))", beta_output)
        self.assertIn("qa beta release review artifact:", beta_output)
        self.assertIn("qa beta release review candidate: llm_env_strict", beta_output)
        self.assertIn("qa beta decision artifact:", beta_output)
        self.assertIn("(ready)", beta_output)
        self.assertIn("qa beta decision artifact fresh: yes", beta_output)
        self.assertIn("qa beta decision artifact consistent with latest evidence: yes", beta_output)
        self.assertIn(
            "qa beta recorded checks: manual=yes, review=yes, latency=yes, cost=yes, signoff=yes, approval=yes",
            beta_output,
        )
        self.assertIn("qa beta launch command: scripts/run_qa_question_beta.sh llm_env_strict", beta_output)
        self.assertIn(
            "qa beta decision: recorded as ready for explicit beta_question_default review; default remains unchanged",
            beta_output,
        )
        self.assertIn(
            "qa beta stage preview command: scripts/run_qa_question_stage_preview.sh beta_question_default",
            beta_output,
        )
        self.assertIn(
            "next beta step: offline beta evidence is already recorded; any rollout-stage or default-path change remains a separate explicit product decision.",
            beta_output,
        )
        self.assertNotIn("beta readiness command:", beta_output)
        runtime_mock.assert_not_called()

    def test_qa_beta_rejects_release_review_artifact_without_explicit_candidate_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            release_review_artifact, _release_review_created_at, _release_review_sha256 = self._write_complete_beta_release_review(
                tmpdir,
                candidate_profile="llm_env_strict",
                manual_created_at=manual_created_at,
                manual_sha256=manual_sha256,
            )
            release_review_payload = json.loads(release_review_artifact.read_text(encoding="utf-8"))
            del release_review_payload["report"]["candidate_selection_source"]
            release_review_artifact.write_text(json.dumps(release_review_payload), encoding="utf-8")

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=Path(tmpdir) / "beta_readiness.json",
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta release review candidate: llm_env_strict", beta_output)
        self.assertIn("qa beta release review candidate selection: none", beta_output)
        self.assertIn("qa beta release review artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta release review artifact consistency reason: recorded beta release review candidate selection source is missing",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_rejects_recorded_beta_readiness_artifact_without_explicit_candidate_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            release_review_artifact, release_review_created_at, release_review_sha256 = self._write_complete_beta_release_review(
                tmpdir,
                candidate_profile="llm_env_strict",
                manual_created_at=manual_created_at,
                manual_sha256=manual_sha256,
            )
            beta_artifact = self._write_ready_beta_readiness_artifact(
                tmpdir,
                artifact_llm_env=artifact_llm_env,
                artifact_llm_env_strict=artifact_llm_env_strict,
                stability_llm_env=stability_llm_env,
                stability_llm_env_strict=stability_llm_env_strict,
                manual_created_at=manual_created_at,
                manual_sha256=manual_sha256,
                release_review_created_at=release_review_created_at,
                release_review_sha256=release_review_sha256,
                include_candidate_selection_source=False,
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=beta_artifact,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta recorded candidate: llm_env_strict", beta_output)
        self.assertIn("qa beta recorded candidate selection: none", beta_output)
        self.assertIn("qa beta decision artifact fresh: yes", beta_output)
        self.assertIn("qa beta decision artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta decision artifact consistency reason: recorded candidate selection source is missing; final beta artifact requires explicit operator choice",
            beta_output,
        )
        self.assertIn(
            "qa beta decision: recorded beta readiness is stale against latest evidence; review must be repeated",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_snapshot_mismatch_even_when_recorded_candidate_is_still_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            release_review_artifact, release_review_created_at, release_review_sha256 = self._write_complete_beta_release_review(
                tmpdir,
                candidate_profile="llm_env_strict",
                manual_created_at=manual_created_at,
                manual_sha256=manual_sha256,
            )
            beta_artifact = Path(tmpdir) / "beta_readiness.json"
            beta_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.beta_readiness",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "stage": "alpha_opt_in",
                            "default_path": "deterministic",
                            "recommended_candidate": "llm_env_strict",
                            "chosen_candidate": "llm_env_strict",
                            "candidate_selection_source": "explicit",
                            "technical_ready_candidates": ["llm_env", "llm_env_strict"],
                            "manual_checklist_completed": True,
                            "manual_checklist_artifact_status": "complete",
                            "manual_checklist_artifact_completed": True,
                            "manual_checklist_items_passed": 7,
                            "manual_checklist_items_total": 7,
                            "manual_checklist_artifact_created_at": manual_created_at,
                            "manual_checklist_artifact_sha256": manual_sha256,
                            "release_review_artifact_status": "complete",
                            "release_review_artifact_completed": True,
                            "release_review_artifact_candidate": "llm_env_strict",
                            "release_review_checks_completed": 4,
                            "release_review_checks_total": 4,
                            "release_review_artifact_created_at": release_review_created_at,
                            "release_review_artifact_sha256": release_review_sha256,
                            "latency_review_completed": True,
                            "cost_review_completed": True,
                            "operator_signoff_completed": True,
                            "product_approval_completed": True,
                            "beta_ready": True,
                            "blockers": [],
                            "candidate_states": {
                                "llm_env_strict": {
                                    "candidate_profile": "llm_env_strict",
                                    "api_key_present": True,
                                    "fallback_enabled": False,
                                    "open_domain_enabled": True,
                                    "open_domain_verified": True,
                                    "technical_ready": True,
                                    "smoke_artifact_path": str(artifact_llm_env_strict),
                                    "smoke_artifact_status": "green",
                                    "smoke_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "smoke_artifact_sha256": "outdated-smoke-fingerprint",
                                    "smoke_artifact_fresh": True,
                                    "smoke_artifact_match": True,
                                    "smoke_artifact_age_hours": 1.0,
                                    "smoke_artifact_reason": None,
                                    "stability_artifact_path": str(stability_llm_env_strict),
                                    "stability_artifact_status": "green",
                                    "stability_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "stability_artifact_sha256": "outdated-stability-fingerprint",
                                    "stability_artifact_fresh": True,
                                    "stability_artifact_age_hours": 1.0,
                                    "stability_artifact_reason": None,
                                    "stability_gate_passes": 2,
                                    "stability_runs_requested": 2,
                                    "blockers": [],
                                }
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=beta_artifact,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta recommended candidate: llm_env_strict", beta_output)
        self.assertIn("qa beta recorded candidate: llm_env_strict", beta_output)
        self.assertIn("qa beta manual checklist artifact:", beta_output)
        self.assertIn("(complete(7/7))", beta_output)
        self.assertIn("qa beta decision artifact fresh: yes", beta_output)
        self.assertIn("qa beta decision artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta decision artifact consistency reason: recorded smoke artifact fingerprint for llm_env_strict no longer matches the latest artifact",
            beta_output,
        )
        self.assertIn(
            "qa beta decision: recorded beta readiness is stale against latest evidence; review must be repeated",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_manual_checklist_artifact_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, _manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            release_review_artifact, release_review_created_at, release_review_sha256 = self._write_complete_beta_release_review(
                tmpdir,
                candidate_profile="llm_env_strict",
                manual_created_at=manual_created_at,
                manual_sha256=_manual_sha256,
            )
            beta_artifact = Path(tmpdir) / "beta_readiness.json"
            beta_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.beta_readiness",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "stage": "alpha_opt_in",
                            "default_path": "deterministic",
                            "recommended_candidate": "llm_env_strict",
                            "chosen_candidate": "llm_env_strict",
                            "candidate_selection_source": "explicit",
                            "technical_ready_candidates": ["llm_env", "llm_env_strict"],
                            "manual_checklist_completed": True,
                            "manual_checklist_artifact_status": "complete",
                            "manual_checklist_artifact_completed": True,
                            "manual_checklist_items_passed": 7,
                            "manual_checklist_items_total": 7,
                            "manual_checklist_artifact_created_at": manual_created_at,
                            "manual_checklist_artifact_sha256": "outdated-manual-checklist-fingerprint",
                            "release_review_artifact_status": "complete",
                            "release_review_artifact_completed": True,
                            "release_review_artifact_candidate": "llm_env_strict",
                            "release_review_checks_completed": 4,
                            "release_review_checks_total": 4,
                            "release_review_artifact_created_at": release_review_created_at,
                            "release_review_artifact_sha256": release_review_sha256,
                            "latency_review_completed": True,
                            "cost_review_completed": True,
                            "operator_signoff_completed": True,
                            "product_approval_completed": True,
                            "beta_ready": True,
                            "blockers": [],
                            "candidate_states": {
                                "llm_env_strict": {
                                    "candidate_profile": "llm_env_strict",
                                    "api_key_present": True,
                                    "fallback_enabled": False,
                                    "open_domain_enabled": True,
                                    "open_domain_verified": True,
                                    "technical_ready": True,
                                    "smoke_artifact_path": str(artifact_llm_env_strict),
                                    "smoke_artifact_status": "green",
                                    "smoke_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "smoke_artifact_sha256": hashlib.sha256(artifact_llm_env_strict.read_bytes()).hexdigest(),
                                    "smoke_artifact_fresh": True,
                                    "smoke_artifact_match": True,
                                    "smoke_artifact_age_hours": 0.0,
                                    "smoke_artifact_reason": None,
                                    "stability_artifact_path": str(stability_llm_env_strict),
                                    "stability_artifact_status": "green",
                                    "stability_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "stability_artifact_sha256": hashlib.sha256(stability_llm_env_strict.read_bytes()).hexdigest(),
                                    "stability_artifact_fresh": True,
                                    "stability_artifact_age_hours": 0.0,
                                    "stability_artifact_reason": None,
                                    "stability_gate_passes": 2,
                                    "stability_runs_requested": 2,
                                    "blockers": [],
                                }
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=beta_artifact,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta decision artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta decision artifact consistency reason: recorded manual checklist artifact fingerprint no longer matches the latest artifact",
            beta_output,
        )
        self.assertIn(
            "qa beta decision: recorded beta readiness is stale against latest evidence; review must be repeated",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_ready_artifact_as_stale_when_latest_evidence_drifts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 0,
                            "runs": [],
                            "blocker_counts": {
                                "open-domain answer pass rate is below threshold": 1,
                            },
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            release_review_artifact, release_review_created_at, release_review_sha256 = self._write_complete_beta_release_review(
                tmpdir,
                candidate_profile="llm_env_strict",
                manual_created_at=manual_created_at,
                manual_sha256=manual_sha256,
            )
            beta_artifact = Path(tmpdir) / "beta_readiness.json"
            beta_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.beta_readiness",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "stage": "alpha_opt_in",
                            "default_path": "deterministic",
                            "recommended_candidate": "llm_env_strict",
                            "chosen_candidate": "llm_env_strict",
                            "candidate_selection_source": "explicit",
                            "technical_ready_candidates": ["llm_env", "llm_env_strict"],
                            "manual_checklist_completed": True,
                            "manual_checklist_artifact_status": "complete",
                            "manual_checklist_artifact_completed": True,
                            "manual_checklist_items_passed": 7,
                            "manual_checklist_items_total": 7,
                            "manual_checklist_artifact_created_at": manual_created_at,
                            "manual_checklist_artifact_sha256": manual_sha256,
                            "release_review_artifact_status": "complete",
                            "release_review_artifact_completed": True,
                            "release_review_artifact_candidate": "llm_env_strict",
                            "release_review_checks_completed": 4,
                            "release_review_checks_total": 4,
                            "release_review_artifact_created_at": release_review_created_at,
                            "release_review_artifact_sha256": release_review_sha256,
                            "latency_review_completed": True,
                            "cost_review_completed": True,
                            "operator_signoff_completed": True,
                            "product_approval_completed": True,
                            "beta_ready": True,
                            "blockers": [],
                            "candidate_states": {
                                "llm_env_strict": {
                                    "candidate_profile": "llm_env_strict",
                                    "api_key_present": True,
                                    "fallback_enabled": False,
                                    "open_domain_enabled": True,
                                    "open_domain_verified": True,
                                    "technical_ready": True,
                                    "smoke_artifact_path": str(artifact_llm_env_strict),
                                    "smoke_artifact_status": "green",
                                    "smoke_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "smoke_artifact_fresh": True,
                                    "smoke_artifact_match": True,
                                    "smoke_artifact_age_hours": 0.0,
                                    "smoke_artifact_reason": None,
                                    "stability_artifact_path": str(stability_llm_env_strict),
                                    "stability_artifact_status": "green",
                                    "stability_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "stability_artifact_fresh": True,
                                    "stability_artifact_age_hours": 0.0,
                                    "stability_artifact_reason": None,
                                    "stability_gate_passes": 2,
                                    "stability_runs_requested": 2,
                                    "blockers": [],
                                }
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=beta_artifact,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta recommended candidate: llm_env", beta_output)
        self.assertIn("qa beta recorded candidate: llm_env_strict", beta_output)
        self.assertIn("qa beta manual checklist artifact:", beta_output)
        self.assertIn("(complete(7/7))", beta_output)
        self.assertIn("qa beta decision artifact fresh: yes", beta_output)
        self.assertIn("qa beta decision artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta decision artifact consistency reason: recorded candidate llm_env_strict is not technically ready on latest artifacts",
            beta_output,
        )
        self.assertIn(
            "qa beta decision artifact drift: recorded candidate llm_env_strict differs from the latest recommended candidate llm_env",
            beta_output,
        )
        self.assertIn(
            "qa beta decision: recorded beta readiness is stale against latest evidence; review must be repeated",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_ready_artifact_as_stale_when_manual_checklist_ages_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            manual_payload = json.loads(manual_artifact.read_text(encoding="utf-8"))
            manual_payload["created_at"] = "2026-03-24T00:00:00+00:00"
            manual_artifact.write_text(json.dumps(manual_payload, indent=2, sort_keys=True), encoding="utf-8")
            stale_manual_created_at = "2026-03-24T00:00:00+00:00"
            stale_manual_sha256 = hashlib.sha256(manual_artifact.read_bytes()).hexdigest()
            release_review_artifact, release_review_created_at, release_review_sha256 = self._write_complete_beta_release_review(
                tmpdir,
                candidate_profile="llm_env_strict",
                manual_created_at=stale_manual_created_at,
                manual_sha256=stale_manual_sha256,
            )
            beta_artifact = Path(tmpdir) / "beta_readiness.json"
            beta_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.beta_readiness",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "stage": "alpha_opt_in",
                            "default_path": "deterministic",
                            "recommended_candidate": "llm_env_strict",
                            "chosen_candidate": "llm_env_strict",
                            "candidate_selection_source": "explicit",
                            "technical_ready_candidates": ["llm_env", "llm_env_strict"],
                            "manual_checklist_completed": True,
                            "manual_checklist_artifact_status": "complete",
                            "manual_checklist_artifact_completed": True,
                            "manual_checklist_items_passed": 7,
                            "manual_checklist_items_total": 7,
                            "manual_checklist_artifact_created_at": stale_manual_created_at,
                            "manual_checklist_artifact_sha256": stale_manual_sha256,
                            "release_review_artifact_status": "complete",
                            "release_review_artifact_completed": True,
                            "release_review_artifact_candidate": "llm_env_strict",
                            "release_review_checks_completed": 4,
                            "release_review_checks_total": 4,
                            "release_review_artifact_created_at": release_review_created_at,
                            "release_review_artifact_sha256": release_review_sha256,
                            "latency_review_completed": True,
                            "cost_review_completed": True,
                            "operator_signoff_completed": True,
                            "product_approval_completed": True,
                            "beta_ready": True,
                            "blockers": [],
                            "candidate_states": {
                                "llm_env_strict": {
                                    "candidate_profile": "llm_env_strict",
                                    "api_key_present": True,
                                    "fallback_enabled": False,
                                    "open_domain_enabled": True,
                                    "open_domain_verified": True,
                                    "technical_ready": True,
                                    "smoke_artifact_path": str(artifact_llm_env_strict),
                                    "smoke_artifact_status": "green",
                                    "smoke_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "smoke_artifact_sha256": hashlib.sha256(artifact_llm_env_strict.read_bytes()).hexdigest(),
                                    "smoke_artifact_fresh": True,
                                    "smoke_artifact_match": True,
                                    "smoke_artifact_age_hours": 0.0,
                                    "smoke_artifact_reason": None,
                                    "stability_artifact_path": str(stability_llm_env_strict),
                                    "stability_artifact_status": "green",
                                    "stability_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "stability_artifact_sha256": hashlib.sha256(stability_llm_env_strict.read_bytes()).hexdigest(),
                                    "stability_artifact_fresh": True,
                                    "stability_artifact_age_hours": 0.0,
                                    "stability_artifact_reason": None,
                                    "stability_gate_passes": 2,
                                    "stability_runs_requested": 2,
                                    "blockers": [],
                                }
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=beta_artifact,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta manual checklist artifact fresh: no (48.0h)", beta_output)
        self.assertIn("qa beta decision artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta decision artifact consistency reason: latest manual checklist artifact is stale",
            beta_output,
        )
        self.assertIn(
            "qa beta decision: recorded beta readiness is stale against latest evidence; review must be repeated",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_ready_artifact_as_stale_when_release_review_ages_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            release_review_artifact, _release_review_created_at, _release_review_sha256 = self._write_complete_beta_release_review(
                tmpdir,
                candidate_profile="llm_env_strict",
                manual_created_at=manual_created_at,
                manual_sha256=manual_sha256,
            )
            release_review_payload = json.loads(release_review_artifact.read_text(encoding="utf-8"))
            release_review_payload["created_at"] = "2026-03-24T00:00:00+00:00"
            release_review_artifact.write_text(
                json.dumps(release_review_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            stale_release_review_created_at = "2026-03-24T00:00:00+00:00"
            stale_release_review_sha256 = hashlib.sha256(release_review_artifact.read_bytes()).hexdigest()
            beta_artifact = Path(tmpdir) / "beta_readiness.json"
            beta_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.beta_readiness",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "stage": "alpha_opt_in",
                            "default_path": "deterministic",
                            "recommended_candidate": "llm_env_strict",
                            "chosen_candidate": "llm_env_strict",
                            "candidate_selection_source": "explicit",
                            "technical_ready_candidates": ["llm_env", "llm_env_strict"],
                            "manual_checklist_completed": True,
                            "manual_checklist_artifact_status": "complete",
                            "manual_checklist_artifact_completed": True,
                            "manual_checklist_items_passed": 7,
                            "manual_checklist_items_total": 7,
                            "manual_checklist_artifact_created_at": manual_created_at,
                            "manual_checklist_artifact_sha256": manual_sha256,
                            "release_review_artifact_status": "complete",
                            "release_review_artifact_completed": True,
                            "release_review_artifact_candidate": "llm_env_strict",
                            "release_review_checks_completed": 4,
                            "release_review_checks_total": 4,
                            "release_review_artifact_created_at": stale_release_review_created_at,
                            "release_review_artifact_sha256": stale_release_review_sha256,
                            "latency_review_completed": True,
                            "cost_review_completed": True,
                            "operator_signoff_completed": True,
                            "product_approval_completed": True,
                            "beta_ready": True,
                            "blockers": [],
                            "candidate_states": {
                                "llm_env_strict": {
                                    "candidate_profile": "llm_env_strict",
                                    "api_key_present": True,
                                    "fallback_enabled": False,
                                    "open_domain_enabled": True,
                                    "open_domain_verified": True,
                                    "technical_ready": True,
                                    "smoke_artifact_path": str(artifact_llm_env_strict),
                                    "smoke_artifact_status": "green",
                                    "smoke_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "smoke_artifact_sha256": hashlib.sha256(artifact_llm_env_strict.read_bytes()).hexdigest(),
                                    "smoke_artifact_fresh": True,
                                    "smoke_artifact_match": True,
                                    "smoke_artifact_age_hours": 0.0,
                                    "smoke_artifact_reason": None,
                                    "stability_artifact_path": str(stability_llm_env_strict),
                                    "stability_artifact_status": "green",
                                    "stability_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "stability_artifact_sha256": hashlib.sha256(stability_llm_env_strict.read_bytes()).hexdigest(),
                                    "stability_artifact_fresh": True,
                                    "stability_artifact_age_hours": 0.0,
                                    "stability_artifact_reason": None,
                                    "stability_gate_passes": 2,
                                    "stability_runs_requested": 2,
                                    "blockers": [],
                                }
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=beta_artifact,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta release review artifact fresh: no (48.0h)", beta_output)
        self.assertIn("qa beta decision artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta decision artifact consistency reason: latest beta release review artifact is stale",
            beta_output,
        )
        self.assertIn(
            "qa beta decision: recorded beta readiness is stale against latest evidence; review must be repeated",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_question_answer_output_includes_mode_answer_sources_and_warning(self) -> None:
        interaction_manager = MagicMock()
        interaction_manager.handle_input.return_value = SimpleNamespace(
            interaction_mode="question",
            answer_result=SimpleNamespace(
                answer_text="I can open apps and answer grounded questions.",
                sources=["/tmp/docs/product_rules.md", "/tmp/docs/question_answer_mode.md"],
                warning="Answer is limited to grounded local sources.",
            ),
            clarification_request=None,
            runtime_result=None,
            error=None,
        )

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli._handle_runtime_input(
                "What can you do?",
                runtime_manager=self.runtime_manager,
                session_context=self.session_context,
                speak_enabled=False,
                interaction_manager=interaction_manager,
            )

        output = buffer.getvalue()
        self.assertIn("mode: question", output)
        self.assertIn("summary: I can open apps and answer grounded questions.", output)
        self.assertIn("sources: Product Rules, Question Answer Mode", output)
        self.assertIn("paths: /tmp/docs/product_rules.md, /tmp/docs/question_answer_mode.md", output)
        self.assertIn("warning: Answer is limited to grounded local sources.", output)
        interaction_manager.handle_input.assert_called_once_with(
            "What can you do?",
            session_context=self.session_context,
        )

    def test_mixed_interaction_prints_routing_clarification(self) -> None:
        interaction_manager = MagicMock()
        interaction_manager.handle_input.return_value = SimpleNamespace(
            interaction_mode="clarification",
            answer_result=None,
            clarification_request=SimpleNamespace(
                message="Do you want an answer first or should I open Safari?"
            ),
            runtime_result=None,
            error=None,
        )

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli._handle_runtime_input(
                "What can you do and open Safari",
                runtime_manager=self.runtime_manager,
                session_context=self.session_context,
                speak_enabled=False,
                interaction_manager=interaction_manager,
            )

        output = buffer.getvalue()
        self.assertIn("mode: clarification", output)
        self.assertIn("clarify: Do you want an answer first or should I open Safari?", output)

    def test_question_answer_is_spoken_when_enabled(self) -> None:
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
        tts_provider = MagicMock()
        tts_provider.speak.return_value = TTSResult(
            ok=True,
            backend_name="yandex_speechkit",
            voice_id="yandex:ermil:good",
        )
        voice_session_state = cli.build_default_voice_session_state()

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli._handle_runtime_input(
                "What can you do?",
                runtime_manager=self.runtime_manager,
                session_context=self.session_context,
                speak_enabled=True,
                interaction_manager=interaction_manager,
                tts_provider=tts_provider,
                voice_session_state=voice_session_state,
            )

        tts_provider.speak.assert_called_once_with(
            SpeechUtterance(
                text=(
                    "I can open apps and answer grounded questions. I stay read-only. "
                    "Warning: Answer is limited to grounded local sources."
                ),
                locale="en-US",
            )
        )
        rendered_tts_last = cli.format_voice_tts_last_result(voice_session_state)
        self.assertIn("backend: yandex_speechkit", rendered_tts_last)
        self.assertIn("voice id: yandex:ermil:good", rendered_tts_last)

    def test_russian_voice_command_is_spoken_with_russian_locale_hint(self) -> None:
        interaction_manager = MagicMock()
        interaction_manager.handle_input.return_value = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "completed",
                "command_summary": "open_app: Telegram",
                "completion_result": "Completed open_app with 1 step(s).",
            },
            runtime_result=None,
            clarification_request=None,
            error=None,
        )
        tts_provider = MagicMock()
        tts_provider.speak.return_value = TTSResult(ok=True)

        buffer = io.StringIO()
        with redirect_stdout(buffer), patch(
            "cli.capture_voice_turn",
            return_value=VoiceCaptureTurn(
                raw_transcript="Джарвис, открой телеграм",
                normalized_text="open telegram",
                locale_hint="ru-RU",
            ),
        ):
            should_exit, speak_enabled = cli._handle_cli_command(
                "voice",
                runtime_manager=self.runtime_manager,
                session_context=self.session_context,
                speak_enabled=True,
                interaction_manager=interaction_manager,
                tts_provider=tts_provider,
            )

        self.assertFalse(should_exit)
        self.assertTrue(speak_enabled)
        tts_provider.speak.assert_called_once_with(
            SpeechUtterance(
                text="Открыл Telegram.",
                locale="ru-RU",
            )
        )

    def _write_complete_manual_beta_checklist(self, tmpdir: str) -> tuple[Path, str, str]:
        manual_artifact = Path(tmpdir) / "manual_beta_checklist.json"
        created_at = "2026-03-26T00:00:00+00:00"
        manual_artifact.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "runner": "qa.manual_beta_checklist",
                    "created_at": created_at,
                    "report": {
                        "checklist_id": "beta_question_default",
                        "passed_items": 7,
                        "total_items": 7,
                        "all_passed": True,
                        "items": {},
                        "notes": "",
                    },
                }
            ),
            encoding="utf-8",
        )
        return manual_artifact, created_at, hashlib.sha256(manual_artifact.read_bytes()).hexdigest()

    def _write_complete_beta_release_review(
        self,
        tmpdir: str,
        *,
        candidate_profile: str,
        manual_created_at: str,
        manual_sha256: str,
    ) -> tuple[Path, str, str]:
        review_artifact = Path(tmpdir) / "beta_release_review.json"
        created_at = "2026-03-26T00:00:00+00:00"
        review_artifact.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "runner": "qa.beta_release_review",
                    "created_at": created_at,
                    "report": {
                        "review_id": "beta_question_default",
                        "candidate_profile": candidate_profile,
                        "candidate_selection_source": "explicit",
                        "completed_checks": 4,
                        "total_checks": 4,
                        "all_completed": True,
                        "manual_checklist_artifact_status": "complete",
                        "manual_checklist_artifact_completed": True,
                        "manual_checklist_items_passed": 7,
                        "manual_checklist_items_total": 7,
                        "manual_checklist_artifact_created_at": manual_created_at,
                        "manual_checklist_artifact_sha256": manual_sha256,
                        "checks": {
                            "latency_review": {"label": "Latency review", "completed": True},
                            "cost_review": {"label": "Cost review", "completed": True},
                            "operator_signoff": {"label": "Operator sign-off", "completed": True},
                            "product_approval": {"label": "Product approval", "completed": True},
                        },
                        "notes": "",
                    },
                }
            ),
            encoding="utf-8",
        )
        return review_artifact, created_at, hashlib.sha256(review_artifact.read_bytes()).hexdigest()

    def _write_ready_beta_readiness_artifact(
        self,
        tmpdir: str,
        *,
        artifact_llm_env: Path,
        artifact_llm_env_strict: Path,
        stability_llm_env: Path,
        stability_llm_env_strict: Path,
        manual_created_at: str,
        manual_sha256: str,
        release_review_created_at: str,
        release_review_sha256: str,
        include_candidate_selection_source: bool = True,
    ) -> Path:
        beta_artifact = Path(tmpdir) / "beta_readiness.json"
        report = {
            "stage": "alpha_opt_in",
            "default_path": "deterministic",
            "recommended_candidate": "llm_env_strict",
            "chosen_candidate": "llm_env_strict",
            "technical_ready_candidates": ["llm_env", "llm_env_strict"],
            "manual_checklist_completed": True,
            "manual_checklist_artifact_status": "complete",
            "manual_checklist_artifact_completed": True,
            "manual_checklist_items_passed": 7,
            "manual_checklist_items_total": 7,
            "manual_checklist_artifact_created_at": manual_created_at,
            "manual_checklist_artifact_sha256": manual_sha256,
            "release_review_artifact_status": "complete",
            "release_review_artifact_completed": True,
            "release_review_artifact_candidate": "llm_env_strict",
            "release_review_checks_completed": 4,
            "release_review_checks_total": 4,
            "release_review_artifact_created_at": release_review_created_at,
            "release_review_artifact_sha256": release_review_sha256,
            "latency_review_completed": True,
            "cost_review_completed": True,
            "operator_signoff_completed": True,
            "product_approval_completed": True,
            "beta_ready": True,
            "blockers": [],
            "candidate_states": {
                "llm_env": {
                    "candidate_profile": "llm_env",
                    "api_key_present": True,
                    "fallback_enabled": True,
                    "open_domain_enabled": True,
                    "open_domain_verified": True,
                    "technical_ready": True,
                    "smoke_artifact_path": str(artifact_llm_env),
                    "smoke_artifact_status": "green",
                    "smoke_artifact_created_at": "2026-03-26T00:00:00+00:00",
                    "smoke_artifact_sha256": hashlib.sha256(artifact_llm_env.read_bytes()).hexdigest(),
                    "smoke_artifact_fresh": True,
                    "smoke_artifact_match": True,
                    "smoke_artifact_age_hours": 0.0,
                    "smoke_artifact_reason": None,
                    "stability_artifact_path": str(stability_llm_env),
                    "stability_artifact_status": "green",
                    "stability_artifact_created_at": "2026-03-26T00:00:00+00:00",
                    "stability_artifact_sha256": hashlib.sha256(stability_llm_env.read_bytes()).hexdigest(),
                    "stability_artifact_fresh": True,
                    "stability_artifact_age_hours": 0.0,
                    "stability_artifact_reason": None,
                    "stability_gate_passes": 2,
                    "stability_runs_requested": 2,
                    "blockers": [],
                },
                "llm_env_strict": {
                    "candidate_profile": "llm_env_strict",
                    "api_key_present": True,
                    "fallback_enabled": False,
                    "open_domain_enabled": True,
                    "open_domain_verified": True,
                    "technical_ready": True,
                    "smoke_artifact_path": str(artifact_llm_env_strict),
                    "smoke_artifact_status": "green",
                    "smoke_artifact_created_at": "2026-03-26T00:00:00+00:00",
                    "smoke_artifact_sha256": hashlib.sha256(artifact_llm_env_strict.read_bytes()).hexdigest(),
                    "smoke_artifact_fresh": True,
                    "smoke_artifact_match": True,
                    "smoke_artifact_age_hours": 0.0,
                    "smoke_artifact_reason": None,
                    "stability_artifact_path": str(stability_llm_env_strict),
                    "stability_artifact_status": "green",
                    "stability_artifact_created_at": "2026-03-26T00:00:00+00:00",
                    "stability_artifact_sha256": hashlib.sha256(stability_llm_env_strict.read_bytes()).hexdigest(),
                    "stability_artifact_fresh": True,
                    "stability_artifact_age_hours": 0.0,
                    "stability_artifact_reason": None,
                    "stability_gate_passes": 2,
                    "stability_runs_requested": 2,
                    "blockers": [],
                },
            },
            "notes": "",
        }
        if include_candidate_selection_source:
            report["candidate_selection_source"] = "explicit"
        beta_artifact.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "runner": "qa.beta_readiness",
                    "created_at": "2026-03-26T00:00:00+00:00",
                    "report": report,
                }
            ),
            encoding="utf-8",
        )
        return beta_artifact

    def _run_command(
        self,
        command: str,
        speak_enabled: bool,
        telemetry: object | None = None,
        voice_session_state: object | None = None,
    ) -> tuple[bool, bool, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            should_exit, updated_speak_enabled = cli._handle_cli_command(
                command,
                runtime_manager=self.runtime_manager,
                session_context=self.session_context,
                speak_enabled=speak_enabled,
                telemetry=telemetry,
                voice_session_state=voice_session_state,
            )
        return should_exit, updated_speak_enabled, buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
