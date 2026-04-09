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

    def test_english_locale_prefers_lively_male_voice_with_rate(self) -> None:
        provider = MacOSTTSProvider()
        listing_process = MagicMock()
        listing_process.returncode = 0
        listing_process.stdout = (
            "Reed (English (US)) en_US    # Hello! My name is Reed.\n"
            "Samantha            en_US    # Hello! My name is Samantha.\n"
        )
        process = MagicMock()
        process.communicate.return_value = ("", "")
        process.returncode = 0

        with patch("voice.tts_macos.sys.platform", "darwin"), patch(
            "voice.tts_macos.subprocess.run",
            return_value=listing_process,
        ), patch("voice.tts_macos.subprocess.Popen", return_value=process) as popen_mock:
            result = provider.speak(SpeechUtterance(text="Hello there", locale="en-US"))

        self.assertTrue(result.ok)
        popen_mock.assert_called_once_with(
            ["say", "-v", "Reed (English (US))", "-r", "190", "Hello there"],
            stdout=ANY,
            stderr=ANY,
            text=True,
        )

    def test_russian_locale_uses_installed_russian_fallback_voice_with_rate(self) -> None:
        provider = MacOSTTSProvider()
        listing_process = MagicMock()
        listing_process.returncode = 0
        listing_process.stdout = "Milena              ru_RU    # Здравствуйте! Меня зовут Милена.\n"
        process = MagicMock()
        process.communicate.return_value = ("", "")
        process.returncode = 0

        with patch("voice.tts_macos.sys.platform", "darwin"), patch(
            "voice.tts_macos.subprocess.run",
            return_value=listing_process,
        ), patch(
            "voice.tts_macos.subprocess.Popen",
            return_value=process,
        ) as popen_mock:
            result = provider.speak(SpeechUtterance(text="Привет", locale="ru-RU"))

        self.assertTrue(result.ok)
        popen_mock.assert_called_once_with(
            ["say", "-v", "Milena", "-r", "184", "Привет"],
            stdout=ANY,
            stderr=ANY,
            text=True,
        )

    def test_russian_locale_prefers_male_voice_when_installed(self) -> None:
        provider = MacOSTTSProvider()
        listing_process = MagicMock()
        listing_process.returncode = 0
        listing_process.stdout = (
            "Yuri                ru_RU    # Здравствуйте! Меня зовут Юрий.\n"
            "Milena              ru_RU    # Здравствуйте! Меня зовут Милена.\n"
        )
        process = MagicMock()
        process.communicate.return_value = ("", "")
        process.returncode = 0

        with patch("voice.tts_macos.sys.platform", "darwin"), patch(
            "voice.tts_macos.subprocess.run",
            return_value=listing_process,
        ), patch("voice.tts_macos.subprocess.Popen", return_value=process) as popen_mock:
            result = provider.speak(SpeechUtterance(text="Привет", locale="ru-RU"))

        self.assertTrue(result.ok)
        self.assertEqual(popen_mock.call_args.args[0], ["say", "-v", "Yuri", "-r", "184", "Привет"])

    def test_voice_selection_falls_back_to_next_candidate_when_first_voice_fails(self) -> None:
        provider = MacOSTTSProvider()
        listing_process = MagicMock()
        listing_process.returncode = 0
        listing_process.stdout = (
            "Yuri                ru_RU    # Здравствуйте! Меня зовут Юрий.\n"
            "Milena              ru_RU    # Здравствуйте! Меня зовут Милена.\n"
        )
        failing_process = MagicMock()
        failing_process.communicate.return_value = ("", "Voice not installed")
        failing_process.returncode = 1
        ok_process = MagicMock()
        ok_process.communicate.return_value = ("", "")
        ok_process.returncode = 0

        with patch("voice.tts_macos.sys.platform", "darwin"), patch(
            "voice.tts_macos.subprocess.run",
            return_value=listing_process,
        ), patch(
            "voice.tts_macos.subprocess.Popen",
            side_effect=[failing_process, ok_process],
        ) as popen_mock:
            result = provider.speak(SpeechUtterance(text="Привет", locale="ru-RU"))

        self.assertTrue(result.ok)
        self.assertEqual(popen_mock.call_count, 2)
        self.assertEqual(popen_mock.call_args_list[0].args[0], ["say", "-v", "Yuri", "-r", "184", "Привет"])
        self.assertEqual(
            popen_mock.call_args_list[1].args[0],
            ["say", "-v", "Milena", "-r", "184", "Привет"],
        )

    def test_voice_selection_falls_back_to_default_say_when_preferred_voices_fail(self) -> None:
        provider = MacOSTTSProvider()
        listing_process = MagicMock()
        listing_process.returncode = 0
        listing_process.stdout = "Milena              ru_RU    # Здравствуйте! Меня зовут Милена.\n"
        failing_process = MagicMock()
        failing_process.communicate.return_value = ("", "Voice not installed")
        failing_process.returncode = 1
        ok_process = MagicMock()
        ok_process.communicate.return_value = ("", "")
        ok_process.returncode = 0

        with patch("voice.tts_macos.sys.platform", "darwin"), patch(
            "voice.tts_macos.subprocess.run",
            return_value=listing_process,
        ), patch(
            "voice.tts_macos.subprocess.Popen",
            side_effect=[failing_process, ok_process],
        ) as popen_mock:
            result = provider.speak(SpeechUtterance(text="Привет", locale="ru-RU"))

        self.assertTrue(result.ok)
        self.assertEqual(popen_mock.call_count, 2)
        self.assertEqual(
            popen_mock.call_args_list[0].args[0],
            ["say", "-v", "Milena", "-r", "184", "Привет"],
        )
        self.assertEqual(popen_mock.call_args_list[1].args[0], ["say", "-r", "184", "Привет"])

    def test_language_rate_override_is_applied(self) -> None:
        provider = MacOSTTSProvider()
        listing_process = MagicMock()
        listing_process.returncode = 0
        listing_process.stdout = "Milena              ru_RU    # Здравствуйте! Меня зовут Милена.\n"
        process = MagicMock()
        process.communicate.return_value = ("", "")
        process.returncode = 0

        with patch.dict("voice.tts_macos.os.environ", {"JARVIS_TTS_RU_RATE": "210"}, clear=False), patch(
            "voice.tts_macos.sys.platform",
            "darwin",
        ), patch(
            "voice.tts_macos.subprocess.run",
            return_value=listing_process,
        ), patch("voice.tts_macos.subprocess.Popen", return_value=process) as popen_mock:
            result = provider.speak(SpeechUtterance(text="Привет", locale="ru-RU"))

        self.assertTrue(result.ok)
        self.assertEqual(
            popen_mock.call_args.args[0],
            ["say", "-v", "Milena", "-r", "210", "Привет"],
        )

    def test_explicit_voice_id_is_used_before_profile_candidates(self) -> None:
        provider = MacOSTTSProvider()
        listing_process = MagicMock()
        listing_process.returncode = 0
        listing_process.stdout = (
            "Yuri                ru_RU    # Здравствуйте! Меня зовут Юрий.\n"
            "Milena              ru_RU    # Здравствуйте! Меня зовут Милена.\n"
        )
        process = MagicMock()
        process.communicate.return_value = ("", "")
        process.returncode = 0

        with patch("voice.tts_macos.sys.platform", "darwin"), patch(
            "voice.tts_macos.subprocess.run",
            return_value=listing_process,
        ), patch("voice.tts_macos.subprocess.Popen", return_value=process) as popen_mock:
            result = provider.speak(
                SpeechUtterance(
                    text="Привет",
                    locale="ru-RU",
                    voice_profile="ru_assistant_female",
                    voice_id="Yuri",
                )
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.voice_id, "Yuri")
        self.assertEqual(popen_mock.call_args.args[0], ["say", "-v", "Yuri", "-r", "184", "Привет"])

    def test_resolve_voice_uses_profile_order_against_installed_voices(self) -> None:
        provider = MacOSTTSProvider()
        listing_process = MagicMock()
        listing_process.returncode = 0
        listing_process.stdout = (
            "Yuri                ru_RU    # Здравствуйте! Меня зовут Юрий.\n"
            "Milena              ru_RU    # Здравствуйте! Меня зовут Милена.\n"
        )

        with patch("voice.tts_macos.sys.platform", "darwin"), patch(
            "voice.tts_macos.subprocess.run",
            return_value=listing_process,
        ):
            descriptor = provider.resolve_voice("ru_assistant_female", "ru-RU")

        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor.id, "Milena")
        self.assertEqual(descriptor.locale, "ru-RU")

    def test_resolve_voice_returns_raw_override_when_say_listing_does_not_include_it(self) -> None:
        provider = MacOSTTSProvider()
        listing_process = MagicMock()
        listing_process.returncode = 0
        listing_process.stdout = "Milena              ru_RU    # Здравствуйте! Меня зовут Милена.\n"

        with patch.dict("voice.tts_macos.os.environ", {"JARVIS_TTS_RU_VOICE": "Siri Voice 1"}, clear=False), patch(
            "voice.tts_macos.sys.platform",
            "darwin",
        ), patch(
            "voice.tts_macos.subprocess.run",
            return_value=listing_process,
        ):
            descriptor = provider.resolve_voice("ru_assistant_male", "ru-RU")

        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor.id, "Siri Voice 1")
        self.assertEqual(descriptor.display_name, "Siri Voice 1")
        self.assertEqual(descriptor.locale, "ru-RU")

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
