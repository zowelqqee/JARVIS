"""Tests for the desktop speech service."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from desktop.backend.speech_service import DesktopSpeechService
from voice.tts_models import BackendCapabilities
from voice.tts_provider import SpeechUtterance, TTSResult


class _FakeProvider:
    def __init__(self) -> None:
        self.utterances: list[SpeechUtterance] = []

    def speak(self, utterance: SpeechUtterance | None) -> TTSResult:
        if utterance is not None:
            self.utterances.append(utterance)
        return TTSResult(ok=True, attempted=True, backend_name="fake_tts")

    def is_available(self) -> bool:
        return True

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(backend_name="fake_tts")


class DesktopSpeechServiceTests(unittest.TestCase):
    def test_loads_cli_tts_defaults_into_desktop_environment(self) -> None:
        with TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / "jarvis_tts.env"
            env_file.write_text(
                "\n".join(
                    [
                        "JARVIS_TTS_YANDEX_ENABLED=1",
                        "JARVIS_TTS_RU_BACKEND=yandex_speechkit",
                        "JARVIS_TTS_YANDEX_VOICE=ermil",
                    ]
                ),
                encoding="utf-8",
            )
            runtime_environ = {"JARVIS_TTS_ENV_FILE": str(env_file)}
            provider = _FakeProvider()
            service = DesktopSpeechService(
                provider_factory=lambda: provider,
                environ=runtime_environ,
            )

            snapshot = service.set_enabled(True)

            self.assertTrue(snapshot.enabled)
            self.assertEqual(runtime_environ["JARVIS_TTS_YANDEX_ENABLED"], "1")
            self.assertEqual(runtime_environ["JARVIS_TTS_RU_BACKEND"], "yandex_speechkit")
            self.assertEqual(runtime_environ["JARVIS_TTS_YANDEX_VOICE"], "ermil")

    def test_speaks_through_configured_provider(self) -> None:
        provider = _FakeProvider()
        service = DesktopSpeechService(provider_factory=lambda: provider, environ={})
        service.set_enabled(True)

        result = service.speak(SpeechUtterance(text="Привет", locale="ru-RU"))

        self.assertIsNotNone(result)
        self.assertTrue(result.ok)
        self.assertEqual(provider.utterances[-1].text, "Привет")


if __name__ == "__main__":
    unittest.main()
