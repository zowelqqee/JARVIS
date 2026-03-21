"""Minimal smoke coverage for JARVIS CLI shell behavior."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import cli
from input.voice_input import VoiceInputError


class CliSmokeTests(unittest.TestCase):
    """Protect the current CLI shell command behavior with small smoke tests."""

    def setUp(self) -> None:
        self.runtime_manager = MagicMock()
        self.session_context = MagicMock()

    def test_voice_aliases_capture_speech_before_runtime_dispatch(self) -> None:
        for command in ("voice", "/voice"):
            with self.subTest(command=command):
                with patch("cli.capture_voice_input", return_value="open browser") as capture_mock, patch(
                    "cli._handle_runtime_input"
                ) as runtime_mock:
                    should_exit, speak_enabled, output = self._run_command(command, speak_enabled=False)

                self.assertFalse(should_exit)
                self.assertFalse(speak_enabled)
                self.assertIn('recognized: "open browser"', output)
                capture_mock.assert_called_once_with()
                runtime_mock.assert_called_once_with(
                    "open browser",
                    runtime_manager=self.runtime_manager,
                    session_context=self.session_context,
                    speak_enabled=False,
                )

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

        with patch("cli.capture_voice_input", side_effect=error), patch("cli._handle_runtime_input") as runtime_mock:
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
        with patch("cli.capture_voice_input") as capture_mock, patch("cli._handle_runtime_input") as runtime_mock:
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

    def _run_command(self, command: str, speak_enabled: bool) -> tuple[bool, bool, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            should_exit, updated_speak_enabled = cli._handle_cli_command(
                command,
                runtime_manager=self.runtime_manager,
                session_context=self.session_context,
                speak_enabled=speak_enabled,
            )
        return should_exit, updated_speak_enabled, buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
