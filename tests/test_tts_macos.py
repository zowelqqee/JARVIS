"""Contract tests for the macOS TTS provider."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from voice.tts_macos import MacOSTTSProvider
from voice.tts_provider import SpeechUtterance


class MacOSTTSProviderTests(unittest.TestCase):
    """Protect provider behavior around voice selection and fallback."""

    def test_empty_utterance_is_skipped(self) -> None:
        provider = MacOSTTSProvider()

        with patch("voice.tts_macos.subprocess.run") as run_mock:
            result = provider.speak(SpeechUtterance(text="", locale="en-US"))

        self.assertTrue(result.ok)
        self.assertFalse(result.attempted)
        run_mock.assert_not_called()

    def test_russian_locale_uses_russian_voice(self) -> None:
        provider = MacOSTTSProvider()

        with patch("voice.tts_macos.sys.platform", "darwin"), patch(
            "voice.tts_macos.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stderr="", stdout=""),
        ) as run_mock:
            result = provider.speak(SpeechUtterance(text="Привет", locale="ru-RU"))

        self.assertTrue(result.ok)
        run_mock.assert_called_once_with(
            ["say", "-v", "Milena", "Привет"],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_voice_selection_falls_back_to_default_say_when_voice_fails(self) -> None:
        provider = MacOSTTSProvider()

        with patch("voice.tts_macos.sys.platform", "darwin"), patch(
            "voice.tts_macos.subprocess.run",
            side_effect=[
                SimpleNamespace(returncode=1, stderr="Voice not installed", stdout=""),
                SimpleNamespace(returncode=0, stderr="", stdout=""),
            ],
        ) as run_mock:
            result = provider.speak(SpeechUtterance(text="Привет", locale="ru-RU"))

        self.assertTrue(result.ok)
        self.assertEqual(run_mock.call_count, 2)
        self.assertEqual(run_mock.call_args_list[0].args[0], ["say", "-v", "Milena", "Привет"])
        self.assertEqual(run_mock.call_args_list[1].args[0], ["say", "Привет"])


if __name__ == "__main__":
    unittest.main()
