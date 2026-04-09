"""Unit tests for the backend-neutral TTS manager."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from voice.tts_manager import TTSManager, build_default_tts_manager
from voice.tts_models import BackendCapabilities, BackendRuntimeStatus, VoiceDescriptor
from voice.tts_provider import SpeechUtterance, TTSResult, stop_speech_if_supported


class _FakeBackend:
    def __init__(
        self,
        *,
        backend_name: str,
        available: bool = True,
        resolved_voice: VoiceDescriptor | None = None,
        resolved_voices_by_profile: dict[str, VoiceDescriptor] | None = None,
        speak_result: TTSResult | None = None,
        voices: list[VoiceDescriptor] | None = None,
        stop_result: bool = False,
        availability_diagnostic: tuple[str | None, str | None] | None = None,
        availability_detail_lines: tuple[str, ...] | None = None,
    ) -> None:
        self._backend_name = backend_name
        self._available = available
        self._resolved_voice = resolved_voice
        self._resolved_voices_by_profile = dict(resolved_voices_by_profile or {})
        self._speak_result = speak_result or TTSResult(ok=True)
        self._voices = list(voices or ([] if resolved_voice is None else [resolved_voice]))
        self._stop_result = stop_result
        self._availability_diagnostic = availability_diagnostic or (None, None)
        self._availability_detail_lines = tuple(availability_detail_lines or ())
        self.spoken_utterances: list[SpeechUtterance] = []

    def speak(self, utterance: SpeechUtterance | None) -> TTSResult:
        if utterance is not None:
            self.spoken_utterances.append(utterance)
        return self._speak_result

    def stop(self) -> bool:
        return self._stop_result

    def list_voices(self, locale_hint: str | None = None) -> list[VoiceDescriptor]:
        if not locale_hint:
            return list(self._voices)
        return [
            voice
            for voice in self._voices
            if str(voice.locale or "").lower().startswith(str(locale_hint or "").lower().split("-", maxsplit=1)[0])
        ]

    def resolve_voice(self, profile: str | None, locale: str | None = None) -> VoiceDescriptor | None:
        if profile in self._resolved_voices_by_profile:
            return self._resolved_voices_by_profile[profile]
        return self._resolved_voice

    def is_available(self) -> bool:
        return self._available

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            backend_name=self._backend_name,
            supports_stop=True,
            supports_voice_listing=True,
            supports_voice_resolution=True,
            supports_explicit_voice_id=True,
            is_fallback=self._backend_name != "primary",
        )

    def availability_diagnostic(self) -> tuple[str | None, str | None]:
        return self._availability_diagnostic

    def availability_detail_lines(self) -> tuple[str, ...]:
        return self._availability_detail_lines


class TTSManagerTests(unittest.TestCase):
    """Protect backend selection, profile resolution, and fallback behavior."""

    def test_manager_applies_default_profile_and_resolved_voice(self) -> None:
        backend = _FakeBackend(
            backend_name="primary",
            resolved_voice=VoiceDescriptor(
                id="Yuri",
                display_name="Yuri",
                locale="ru-RU",
                gender_hint="male",
                source="say",
            ),
        )
        manager = TTSManager(backends=[backend])

        result = manager.speak(SpeechUtterance(text="Привет", locale="ru-RU"))

        self.assertTrue(result.ok)
        self.assertEqual(result.backend_name, "primary")
        self.assertEqual(result.voice_id, "Yuri")
        self.assertEqual(len(backend.spoken_utterances), 1)
        spoken = backend.spoken_utterances[0]
        self.assertEqual(spoken.voice_profile, "ru_assistant_male")
        self.assertEqual(spoken.voice_id, "Yuri")

    def test_manager_falls_back_to_next_backend_after_failure(self) -> None:
        primary = _FakeBackend(
            backend_name="primary",
            resolved_voice=VoiceDescriptor(id="Yuri", display_name="Yuri", locale="ru-RU", source="say"),
            speak_result=TTSResult(ok=False, error_code="TTS_FAILED", error_message="primary failed"),
        )
        secondary = _FakeBackend(
            backend_name="secondary",
            resolved_voice=VoiceDescriptor(id="Milena", display_name="Milena", locale="ru-RU", source="say"),
            speak_result=TTSResult(ok=True),
        )
        manager = TTSManager(backends=[primary, secondary])

        result = manager.speak(SpeechUtterance(text="Привет", locale="ru-RU"))

        self.assertTrue(result.ok)
        self.assertEqual(result.backend_name, "secondary")
        self.assertEqual(result.voice_id, "Milena")
        self.assertEqual(len(primary.spoken_utterances), 1)
        self.assertEqual(len(secondary.spoken_utterances), 1)

    def test_manager_lists_voices_from_primary_available_backend_only(self) -> None:
        primary_voice = VoiceDescriptor(id="native-voice", display_name="Native Voice", locale="en-US", source="native")
        fallback_voice = VoiceDescriptor(id="legacy-voice", display_name="Legacy Voice", locale="en-US", source="say")
        primary = _FakeBackend(backend_name="primary", voices=[primary_voice])
        fallback = _FakeBackend(backend_name="fallback", voices=[fallback_voice])
        manager = TTSManager(backends=[primary, fallback])

        voices = manager.list_voices(locale_hint="en-US")

        self.assertEqual(voices, [primary_voice])

    def test_manager_resolve_voice_trace_reports_profile_fallback_chain(self) -> None:
        backend = _FakeBackend(
            backend_name="primary",
            resolved_voices_by_profile={
                "ru_assistant_any": VoiceDescriptor(
                    id="Yuri",
                    display_name="Yuri",
                    locale="ru-RU",
                    gender_hint="male",
                    source="say",
                )
            },
        )
        manager = TTSManager(backends=[backend])

        trace = manager.resolve_voice_trace("ru_assistant_male", "ru-RU")

        self.assertEqual(trace.requested_profile_id, "ru_assistant_male")
        self.assertEqual(trace.attempted_profile_ids, ("ru_assistant_male", "ru_assistant_any"))
        self.assertEqual(trace.resolved_profile_id, "ru_assistant_any")
        self.assertEqual(trace.backend_name, "primary")
        self.assertIsNotNone(trace.resolved_voice)
        self.assertEqual(trace.resolved_voice.id, "Yuri")
        self.assertEqual(trace.note, "resolved via fallback profile ru_assistant_any on primary")

    def test_manager_exposes_backend_diagnostics_with_selected_fallback(self) -> None:
        native = _FakeBackend(
            backend_name="macos_native",
            available=False,
            availability_diagnostic=("HOST_PING_FAILED", "Native macOS TTS host ping failed."),
        )
        legacy = _FakeBackend(backend_name="macos_say_legacy", available=True)
        manager = TTSManager(backends=[native, legacy])

        diagnostics = manager.backend_diagnostics()

        self.assertEqual(
            diagnostics,
            (
                BackendRuntimeStatus(
                    backend_name="macos_native",
                    available=False,
                    selected=False,
                    error_code="HOST_PING_FAILED",
                    error_message="Native macOS TTS host ping failed.",
                    capabilities=native.capabilities(),
                ),
                BackendRuntimeStatus(
                    backend_name="macos_say_legacy",
                    available=True,
                    selected=True,
                    error_code=None,
                    error_message=None,
                    capabilities=legacy.capabilities(),
                ),
            ),
        )

    def test_manager_exposes_backend_availability_detail_lines(self) -> None:
        native = _FakeBackend(
            backend_name="macos_native",
            available=False,
            availability_diagnostic=(
                "HOST_SDK_MISMATCH",
                "Native macOS Swift compiler and SDK appear mismatched; align Xcode and Command Line Tools.",
            ),
            availability_detail_lines=(
                "sdk toolchain: Apple Swift version 6.2 effective-5.10",
                "active compiler: Apple Swift version 6.2.4 effective-5.10",
            ),
        )
        legacy = _FakeBackend(backend_name="macos_say_legacy", available=True)
        manager = TTSManager(backends=[native, legacy])

        diagnostics = manager.backend_diagnostics()

        self.assertEqual(
            diagnostics[0].detail_lines,
            (
                "sdk toolchain: Apple Swift version 6.2 effective-5.10",
                "active compiler: Apple Swift version 6.2.4 effective-5.10",
            ),
        )

    def test_stop_remains_compatible_with_existing_cli_helper(self) -> None:
        backend = _FakeBackend(backend_name="primary", stop_result=True)
        manager = TTSManager(backends=[backend])

        self.assertTrue(stop_speech_if_supported(manager))

    def test_build_default_tts_manager_prefers_native_macos_backend_on_darwin_by_default(self) -> None:
        native_backend = _FakeBackend(backend_name="macos_native")
        legacy_backend = _FakeBackend(backend_name="macos_say_legacy")

        with patch(
            "voice.backends.macos_native.MacOSNativeTTSBackend",
            return_value=native_backend,
        ), patch(
            "voice.tts_macos.MacOSTTSProvider",
            return_value=legacy_backend,
        ):
            manager = build_default_tts_manager(
                platform="darwin",
                environ={"JARVIS_TTS_PIPER_ENABLED": "0"},
            )

        self.assertEqual(manager.backend_name(), "macos_native")

    def test_build_default_tts_manager_prefers_local_piper_when_configured(self) -> None:
        piper_backend = _FakeBackend(backend_name="local_piper")
        native_backend = _FakeBackend(backend_name="macos_native")
        legacy_backend = _FakeBackend(backend_name="macos_say_legacy")

        with patch(
            "voice.backends.piper.PiperTTSBackend",
            return_value=piper_backend,
        ), patch(
            "voice.backends.macos_native.MacOSNativeTTSBackend",
            return_value=native_backend,
        ), patch(
            "voice.tts_macos.MacOSTTSProvider",
            return_value=legacy_backend,
        ):
            manager = build_default_tts_manager(
                platform="darwin",
                environ={"JARVIS_TTS_PIPER_MODEL_RU": "/tmp/ru.onnx"},
            )

        self.assertEqual(manager.backend_name(), "local_piper")

    def test_build_default_tts_manager_prefers_local_piper_when_repo_runtime_is_configured(self) -> None:
        piper_backend = _FakeBackend(backend_name="local_piper")
        native_backend = _FakeBackend(backend_name="macos_native")
        legacy_backend = _FakeBackend(backend_name="macos_say_legacy")

        with patch(
            "voice.backends.piper.PiperTTSBackend",
            return_value=piper_backend,
        ), patch(
            "voice.backends.piper.piper_backend_requested",
            return_value=True,
        ), patch(
            "voice.backends.macos_native.MacOSNativeTTSBackend",
            return_value=native_backend,
        ), patch(
            "voice.tts_macos.MacOSTTSProvider",
            return_value=legacy_backend,
        ):
            manager = build_default_tts_manager(platform="darwin")

        self.assertEqual(manager.backend_name(), "local_piper")

    def test_build_default_tts_manager_honors_explicit_opt_out_on_darwin(self) -> None:
        with patch("voice.tts_macos.sys.platform", "darwin"):
            manager = build_default_tts_manager(
                platform="darwin",
                environ={
                    "JARVIS_TTS_MACOS_NATIVE": "0",
                    "JARVIS_TTS_PIPER_ENABLED": "0",
                },
            )

        self.assertEqual(manager.backend_name(), "macos_say_legacy")

    def test_build_default_tts_manager_prefers_native_macos_backend_when_explicitly_enabled(self) -> None:
        native_backend = _FakeBackend(backend_name="macos_native")
        legacy_backend = _FakeBackend(backend_name="macos_say_legacy")

        with patch(
            "voice.backends.macos_native.MacOSNativeTTSBackend",
            return_value=native_backend,
        ), patch(
            "voice.tts_macos.MacOSTTSProvider",
            return_value=legacy_backend,
        ):
            manager = build_default_tts_manager(
                platform="darwin",
                environ={
                    "JARVIS_TTS_MACOS_NATIVE": "1",
                    "JARVIS_TTS_PIPER_ENABLED": "0",
                },
            )

        self.assertEqual(manager.backend_name(), "macos_native")

    def test_build_default_tts_manager_honors_explicit_environ_opt_in(self) -> None:
        native_backend = _FakeBackend(backend_name="macos_native")
        legacy_backend = _FakeBackend(backend_name="macos_say_legacy")

        with patch(
            "voice.backends.macos_native.MacOSNativeTTSBackend",
            return_value=native_backend,
        ), patch(
            "voice.tts_macos.MacOSTTSProvider",
            return_value=legacy_backend,
        ):
            manager = build_default_tts_manager(
                platform="darwin",
                environ={
                    "JARVIS_TTS_MACOS_NATIVE": "1",
                    "JARVIS_TTS_PIPER_ENABLED": "0",
                },
            )

        self.assertEqual(manager.backend_name(), "macos_native")

    def test_build_default_tts_manager_falls_back_to_legacy_when_native_backend_is_unavailable_by_default(self) -> None:
        native_backend = _FakeBackend(backend_name="macos_native", available=False)
        legacy_backend = _FakeBackend(backend_name="macos_say_legacy")

        with patch("voice.backends.macos_native.MacOSNativeTTSBackend",
            return_value=native_backend,
        ), patch(
            "voice.tts_macos.MacOSTTSProvider",
            return_value=legacy_backend,
        ):
            manager = build_default_tts_manager(
                platform="darwin",
                environ={"JARVIS_TTS_PIPER_ENABLED": "0"},
            )

        self.assertEqual(manager.backend_name(), "macos_say_legacy")

    def test_build_default_tts_manager_is_unavailable_off_platform(self) -> None:
        manager = build_default_tts_manager(
            platform="linux",
            environ={"JARVIS_TTS_PIPER_ENABLED": "0"},
        )

        self.assertFalse(manager.is_available())
        self.assertEqual(manager.backend_name(), "unavailable")

    def test_build_default_tts_manager_skips_local_piper_when_explicitly_disabled(self) -> None:
        native_backend = _FakeBackend(backend_name="macos_native")
        legacy_backend = _FakeBackend(backend_name="macos_say_legacy")

        with patch(
            "voice.backends.macos_native.MacOSNativeTTSBackend",
            return_value=native_backend,
        ), patch(
            "voice.tts_macos.MacOSTTSProvider",
            return_value=legacy_backend,
        ):
            manager = build_default_tts_manager(
                platform="darwin",
                environ={
                    "JARVIS_TTS_PIPER_ENABLED": "0",
                    "JARVIS_TTS_PIPER_MODEL_RU": "/tmp/ru.onnx",
                },
            )

        self.assertEqual(manager.backend_name(), "macos_native")


if __name__ == "__main__":
    unittest.main()
