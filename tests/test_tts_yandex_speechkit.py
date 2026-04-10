"""Contract tests for the optional Yandex SpeechKit TTS backend."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import unittest
from unittest.mock import ANY, MagicMock, patch
import wave

from voice.backends.yandex_speechkit import (
    YandexSpeechKitTTSBackend,
    _audio_bytes_from_response_body,
    yandex_speechkit_backend_configured,
    yandex_speechkit_backend_requested,
)
from voice.tts_manager import TTSManager
from voice.tts_models import BackendCapabilities, VoiceDescriptor
from voice.tts_provider import SpeechUtterance, TTSResult


class _FakeHTTPResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class _FallbackBackend:
    def __init__(self) -> None:
        self.spoken_utterances: list[SpeechUtterance] = []

    def speak(self, utterance: SpeechUtterance | None) -> TTSResult:
        if utterance is not None:
            self.spoken_utterances.append(utterance)
        return TTSResult(ok=True, backend_name="local_piper", voice_id="piper-en")

    def stop(self) -> bool:
        return False

    def list_voices(self, locale_hint: str | None = None) -> list[VoiceDescriptor]:
        return [VoiceDescriptor(id="piper-en", display_name="Piper English", locale=locale_hint or "en-US", source="piper")]

    def resolve_voice(self, profile: str | None, locale: str | None = None) -> VoiceDescriptor | None:
        return VoiceDescriptor(id="piper-en", display_name="Piper English", locale=locale or "en-US", source="piper")

    def is_available(self) -> bool:
        return True

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(backend_name="local_piper", supports_voice_resolution=True)


class YandexSpeechKitTTSBackendTests(unittest.TestCase):
    """Protect cloud backend configuration, payloads, and fallback behavior."""

    def test_backend_is_requested_only_by_explicit_flag(self) -> None:
        self.assertFalse(yandex_speechkit_backend_requested({"JARVIS_TTS_YANDEX_API_KEY": "secret"}))
        self.assertTrue(yandex_speechkit_backend_requested({"JARVIS_TTS_YANDEX_ENABLED": "1"}))
        self.assertTrue(yandex_speechkit_backend_requested({"JARVIS_TTS_YANDEX_ENABLED": "true"}))
        self.assertFalse(yandex_speechkit_backend_requested({"JARVIS_TTS_YANDEX_ENABLED": "0"}))

    def test_backend_is_visible_in_diagnostics_when_any_explicit_config_is_present(self) -> None:
        self.assertTrue(yandex_speechkit_backend_configured({"JARVIS_TTS_YANDEX_API_KEY": "secret"}))
        self.assertTrue(yandex_speechkit_backend_configured({"JARVIS_TTS_YANDEX_ENABLED": "0"}))
        self.assertFalse(yandex_speechkit_backend_configured({}))

    def test_backend_is_unavailable_without_auth(self) -> None:
        backend = YandexSpeechKitTTSBackend(
            environ={"JARVIS_TTS_YANDEX_ENABLED": "1"},
            player_command=("/usr/bin/true",),
        )

        self.assertFalse(backend.is_available())
        self.assertEqual(
            backend.availability_diagnostic(),
            (
                "YANDEX_AUTH_MISSING",
                "Yandex SpeechKit TTS requires `JARVIS_TTS_YANDEX_API_KEY` or `JARVIS_TTS_YANDEX_IAM_TOKEN`.",
            ),
        )

    def test_backend_exposes_configured_russian_voice(self) -> None:
        backend = YandexSpeechKitTTSBackend(
            environ={
                "JARVIS_TTS_YANDEX_ENABLED": "1",
                "JARVIS_TTS_YANDEX_API_KEY": "secret",
                "JARVIS_TTS_YANDEX_VOICE": "ermil",
                "JARVIS_TTS_YANDEX_ROLE": "good",
            },
            player_command=("/usr/bin/true",),
        )

        self.assertTrue(backend.is_available())
        voice = backend.resolve_voice("ru_assistant_male", "ru-RU")

        self.assertIsNotNone(voice)
        assert voice is not None
        self.assertEqual(voice.id, "yandex:ermil:good")
        self.assertEqual(voice.display_name, "Yandex SpeechKit ermil (good)")
        self.assertEqual(voice.locale, "ru-RU")
        self.assertEqual(backend.list_voices(locale_hint="en-US"), [])

    def test_speak_posts_v3_payload_and_plays_decoded_wav(self) -> None:
        audio = _wav_bytes(b"\x01\x02\x03\x04")
        response_body = json.dumps(
            {
                "result": {
                    "audioChunk": {
                        "data": base64.b64encode(audio).decode("ascii"),
                    }
                }
            }
        ).encode("utf-8")
        playback = MagicMock()
        playback.returncode = 0
        playback.communicate.return_value = ("", "")
        requests: list[object] = []
        playback_paths: list[Path] = []
        seen_contexts: list[object] = []

        def _urlopen(request: object, *, timeout: float, context: object) -> _FakeHTTPResponse:
            requests.append(request)
            seen_contexts.append(context)
            self.assertEqual(timeout, 7.0)
            return _FakeHTTPResponse(response_body)

        def _popen(command: list[str], **_: object) -> MagicMock:
            playback_paths.append(Path(command[-1]))
            self.assertEqual(Path(command[-1]).read_bytes(), audio)
            return playback

        backend = YandexSpeechKitTTSBackend(
            environ={
                "JARVIS_TTS_YANDEX_ENABLED": "1",
                "JARVIS_TTS_YANDEX_API_KEY": "secret",
                "JARVIS_TTS_YANDEX_FOLDER_ID": "folder-id",
                "JARVIS_TTS_YANDEX_VOICE": "ermil",
                "JARVIS_TTS_YANDEX_ROLE": "good",
                "JARVIS_TTS_YANDEX_SPEED": "1.05",
                "JARVIS_TTS_YANDEX_PITCH_SHIFT": "-80",
                "JARVIS_TTS_YANDEX_TIMEOUT_SECONDS": "7",
            },
            player_command=("/usr/bin/true",),
        )

        with patch("voice.backends.yandex_speechkit.urllib.request.urlopen", side_effect=_urlopen), patch(
            "voice.backends.yandex_speechkit.subprocess.Popen",
            side_effect=_popen,
        ) as popen_mock:
            result = backend.speak(SpeechUtterance(text="Привет, проверка.", locale="ru-RU"))

        self.assertTrue(result.ok)
        self.assertEqual(result.backend_name, "yandex_speechkit")
        self.assertEqual(result.voice_id, "yandex:ermil:good")
        self.assertEqual(len(requests), 1)
        self.assertEqual(len(seen_contexts), 1)
        self.assertIsNotNone(seen_contexts[0])
        request = requests[0]
        self.assertEqual(request.get_header("Authorization"), "Api-Key secret")
        self.assertEqual(request.get_header("X-folder-id"), "folder-id")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["text"], "Привет, проверка.")
        self.assertEqual(
            payload["hints"],
            [
                {"voice": "ermil"},
                {"role": "good"},
                {"speed": "1.05"},
                {"pitchShift": "-80"},
            ],
        )
        self.assertEqual(payload["outputAudioSpec"]["containerAudio"]["containerAudioType"], "WAV")
        popen_mock.assert_called_once_with(
            ["/usr/bin/true", ANY],
            stdout=ANY,
            stderr=ANY,
            text=True,
        )
        self.assertFalse(playback_paths[0].exists())

    def test_speak_splits_long_text_into_multiple_yandex_requests(self) -> None:
        first_audio = _wav_bytes(b"\x01\x02\x03\x04")
        second_audio = _wav_bytes(b"\x05\x06\x07\x08")
        response_bodies = [
            json.dumps({"result": {"audioChunk": {"data": base64.b64encode(first_audio).decode("ascii")}}}).encode("utf-8"),
            json.dumps({"result": {"audioChunk": {"data": base64.b64encode(second_audio).decode("ascii")}}}).encode("utf-8"),
        ]
        playback = MagicMock()
        playback.returncode = 0
        playback.communicate.return_value = ("", "")
        requests: list[object] = []
        playback_sizes: list[int] = []

        def _urlopen(request: object, *, timeout: float, context: object) -> _FakeHTTPResponse:
            requests.append(request)
            return _FakeHTTPResponse(response_bodies[len(requests) - 1])

        def _popen(command: list[str], **_: object) -> MagicMock:
            path = Path(command[-1])
            playback_sizes.append(path.stat().st_size)
            return playback

        backend = YandexSpeechKitTTSBackend(
            environ={
                "JARVIS_TTS_YANDEX_ENABLED": "1",
                "JARVIS_TTS_YANDEX_API_KEY": "secret",
                "JARVIS_TTS_YANDEX_VOICE": "ermil",
                "JARVIS_TTS_YANDEX_ROLE": "good",
            },
            player_command=("/usr/bin/true",),
        )
        long_text = (
            "Ормузский пролив — узкий водный путь между Персидским заливом и Ормузским заливом в Омане. "
            "Он служит важной морской дорогой для мирового судоходства и имеет стратегическое значение. "
            "Ширина пролива около шестидесяти километров в зависимости от точки."
        )

        with patch("voice.backends.yandex_speechkit.urllib.request.urlopen", side_effect=_urlopen), patch(
            "voice.backends.yandex_speechkit.subprocess.Popen",
            side_effect=_popen,
        ):
            result = backend.speak(SpeechUtterance(text=long_text, locale="ru-RU"))

        self.assertTrue(result.ok)
        self.assertEqual(result.backend_name, "yandex_speechkit")
        self.assertEqual(len(requests), 2)
        payload_texts = [json.loads(request.data.decode("utf-8"))["text"] for request in requests]
        self.assertTrue(all(len(text) <= 220 for text in payload_texts))
        self.assertEqual(len(playback_sizes), 1)
        self.assertGreater(playback_sizes[0], len(first_audio))

    def test_speak_rejects_non_russian_utterance_without_network_call(self) -> None:
        backend = YandexSpeechKitTTSBackend(
            environ={
                "JARVIS_TTS_YANDEX_ENABLED": "1",
                "JARVIS_TTS_YANDEX_API_KEY": "secret",
            },
            player_command=("/usr/bin/true",),
        )

        with patch("voice.backends.yandex_speechkit.urllib.request.urlopen") as urlopen_mock:
            result = backend.speak(SpeechUtterance(text="Open the folder.", locale="en-US"))

        self.assertFalse(result.ok)
        self.assertFalse(result.attempted)
        self.assertEqual(result.error_code, "UNSUPPORTED_LOCALE")
        urlopen_mock.assert_not_called()

    def test_speak_reports_tls_verification_error_with_recovery_hint(self) -> None:
        backend = YandexSpeechKitTTSBackend(
            environ={
                "JARVIS_TTS_YANDEX_ENABLED": "1",
                "JARVIS_TTS_YANDEX_API_KEY": "secret",
            },
            player_command=("/usr/bin/true",),
        )

        ssl_error = __import__("ssl").SSLCertVerificationError("unable to get local issuer certificate")
        with patch("voice.backends.yandex_speechkit.urllib.request.urlopen", side_effect=ssl_error):
            result = backend.speak(SpeechUtterance(text="Привет", locale="ru-RU"))

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "YANDEX_TLS_CERT_ERROR")
        self.assertIn("JARVIS_TTS_YANDEX_CA_BUNDLE", str(result.error_message))

    def test_audio_parser_accepts_newline_delimited_yandex_chunks(self) -> None:
        first = base64.b64encode(b"RIFF").decode("ascii")
        second = base64.b64encode(b"wave").decode("ascii")
        body = (
            json.dumps({"result": {"audioChunk": {"data": first}}})
            + "\n"
            + json.dumps({"result": {"audioChunk": {"data": second}}})
        ).encode("utf-8")

        self.assertEqual(_audio_bytes_from_response_body(body), b"RIFFwave")

    def test_manager_falls_back_without_network_for_english_utterance(self) -> None:
        yandex = YandexSpeechKitTTSBackend(
            environ={
                "JARVIS_TTS_YANDEX_ENABLED": "1",
                "JARVIS_TTS_YANDEX_API_KEY": "secret",
            },
            player_command=("/usr/bin/true",),
        )
        fallback = _FallbackBackend()
        manager = TTSManager(backends=[yandex, fallback])

        with patch("voice.backends.yandex_speechkit.urllib.request.urlopen") as urlopen_mock:
            result = manager.speak(SpeechUtterance(text="Open the folder.", locale="en-US"))

        self.assertTrue(result.ok)
        self.assertEqual(result.backend_name, "local_piper")
        self.assertEqual(result.voice_id, "piper-en")
        self.assertEqual(len(fallback.spoken_utterances), 1)
        urlopen_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()


def _wav_bytes(frames: bytes, *, frame_rate: int = 22050, sample_width: int = 2, channels: int = 1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(sample_width)
        writer.setframerate(frame_rate)
        writer.writeframes(frames)
    return buffer.getvalue()
