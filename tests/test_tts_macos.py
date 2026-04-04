"""Contract tests for the macOS TTS provider."""

from __future__ import annotations

import unittest
from unittest.mock import ANY, MagicMock, patch

from voice.tts_macos import MacOSTTSProvider
from voice.tts_provider import SpeechUtterance


class MacOSTTSProviderTests(unittest.TestCase):
    """Protect provider behavior around voice selection and fallback."""

    def test_empty_utterance_is_skipped(self) -> None:
        provider = MacOSTTSProvider()

        with patch("voice.tts_macos.subprocess.Popen") as popen_mock:
            result = provider.speak(SpeechUtterance(text="", locale="en-US"))

        self.assertTrue(result.ok)
        self.assertFalse(result.attempted)
        popen_mock.assert_not_called()

    def test_russian_locale_uses_russian_voice(self) -> None:
        provider = MacOSTTSProvider()
        process = MagicMock()
        process.communicate.return_value = ("", "")
        process.returncode = 0

        with patch("voice.tts_macos.sys.platform", "darwin"), patch(
            "voice.tts_macos.subprocess.Popen",
            return_value=process,
        ) as popen_mock:
            result = provider.speak(SpeechUtterance(text="Привет", locale="ru-RU"))

        self.assertTrue(result.ok)
        popen_mock.assert_called_once_with(
            ["say", "-v", "Milena", "Привет"],
            stdout=ANY,
            stderr=ANY,
            text=True,
        )

    def test_voice_selection_falls_back_to_default_say_when_voice_fails(self) -> None:
        provider = MacOSTTSProvider()
        failing_process = MagicMock()
        failing_process.communicate.return_value = ("", "Voice not installed")
        failing_process.returncode = 1
        ok_process = MagicMock()
        ok_process.communicate.return_value = ("", "")
        ok_process.returncode = 0

        with patch("voice.tts_macos.sys.platform", "darwin"), patch(
            "voice.tts_macos.subprocess.Popen",
            side_effect=[
                failing_process,
                ok_process,
            ],
        ) as popen_mock:
            result = provider.speak(SpeechUtterance(text="Привет", locale="ru-RU"))

        self.assertTrue(result.ok)
        self.assertEqual(popen_mock.call_count, 2)
        self.assertEqual(popen_mock.call_args_list[0].args[0], ["say", "-v", "Milena", "Привет"])
        self.assertEqual(popen_mock.call_args_list[1].args[0], ["say", "Привет"])

    def test_stop_terminates_active_say_process(self) -> None:
        provider = MacOSTTSProvider()
        process = MagicMock()
        process.poll.return_value = None
        provider._current_process = process

        stopped = provider.stop()

        self.assertTrue(stopped)
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=0.2)
        self.assertIsNone(provider._current_process)

    def test_stop_returns_false_when_no_active_process_exists(self) -> None:
        provider = MacOSTTSProvider()

        self.assertFalse(provider.stop())


if __name__ == "__main__":
    unittest.main()
