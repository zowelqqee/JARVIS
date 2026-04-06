"""Unit coverage for current-session voice status helpers."""

from __future__ import annotations

import unittest

from voice.status import (
    build_tts_backend_status,
    build_tts_current_status,
    build_tts_doctor_status,
    build_tts_voice_inventory,
    build_voice_session_status,
    format_tts_backend_status,
    format_tts_current_status,
    format_tts_doctor_status,
    format_tts_voice_inventory,
    format_voice_session_status,
)
from voice.telemetry import VoiceTelemetryCollector
from voice.tts_models import BackendCapabilities, BackendRuntimeStatus, VoiceDescriptor, VoiceResolutionTrace
from voice.voice_profiles import default_voice_profile_for_locale, fallback_voice_profile_ids


class VoiceStatusTests(unittest.TestCase):
    """Keep the operator-facing current-session voice status stable."""

    def test_build_tts_backend_status_reports_backend_capabilities(self) -> None:
        provider = _FakeTTSProvider()

        status = build_tts_backend_status(provider)

        self.assertEqual(status.backend_name, "macos_say_legacy")
        self.assertTrue(status.available)
        self.assertTrue(status.supports_voice_listing)
        self.assertTrue(status.supports_voice_resolution)
        self.assertTrue(status.is_fallback)
        self.assertEqual(len(status.diagnostics), 1)

    def test_format_tts_voice_inventory_lists_visible_voices(self) -> None:
        provider = _FakeTTSProvider()

        rendered = format_tts_voice_inventory(build_tts_voice_inventory(provider))

        self.assertIn("JARVIS TTS Voices", rendered)
        self.assertIn("backend: macos_say_legacy", rendered)
        self.assertIn("visible voice count: 2", rendered)
        self.assertIn("Milena (locale=ru-RU, gender=female, quality=default, source=say)", rendered)
        self.assertIn("Yuri (locale=ru-RU, gender=male, quality=default, source=say)", rendered)

    def test_format_tts_current_status_renders_profile_resolution(self) -> None:
        provider = _FakeTTSProvider()

        rendered = format_tts_current_status(build_tts_current_status(provider))

        self.assertIn("JARVIS TTS Current", rendered)
        self.assertIn("ru_assistant_male (ru-RU): Yuri", rendered)
        self.assertIn("ru_assistant_female (ru-RU): Milena", rendered)
        self.assertIn("en_assistant_male (en-US): Reed (English (US))", rendered)
        self.assertIn("en_assistant_female (en-US): Samantha", rendered)
        self.assertIn("profiles: ru_assistant_male -> ru_assistant_any", rendered)
        self.assertIn("resolved profile: ru_assistant_male", rendered)
        self.assertIn("backend: macos_say_legacy", rendered)

    def test_build_tts_current_status_keeps_profile_fallback_trace(self) -> None:
        provider = _ProfileFallbackFakeTTSProvider()

        status = build_tts_current_status(provider)
        resolution = next(item for item in status.resolutions if item.profile_id == "ru_assistant_male")

        self.assertIsNotNone(resolution.resolved_voice)
        self.assertEqual(resolution.resolved_voice.id, "Yuri")
        self.assertEqual(resolution.resolved_profile_id, "ru_assistant_any")
        self.assertEqual(resolution.backend_name, "macos_say_legacy")
        self.assertEqual(resolution.attempted_profile_ids, ("ru_assistant_male", "ru_assistant_any"))
        self.assertEqual(resolution.resolution_note, "resolved via fallback profile ru_assistant_any on macos_say_legacy")

    def test_format_tts_current_status_mentions_profile_fallback_trace(self) -> None:
        provider = _ProfileFallbackFakeTTSProvider()

        rendered = format_tts_current_status(build_tts_current_status(provider))

        self.assertIn("ru_assistant_male (ru-RU): Yuri", rendered)
        self.assertIn("profiles: ru_assistant_male -> ru_assistant_any", rendered)
        self.assertIn("fallback profile: ru_assistant_any", rendered)
        self.assertIn("backend: macos_say_legacy", rendered)

    def test_format_tts_backend_status_mentions_fallback_diagnostics(self) -> None:
        provider = _FallbackFakeTTSProvider()

        rendered = format_tts_backend_status(build_tts_backend_status(provider))

        self.assertIn("selection note: fallback active: using macos_say_legacy because macos_native is unavailable", rendered)
        self.assertIn("configured backends:", rendered)
        self.assertIn("- macos_native: unavailable (HOST_PING_FAILED: Native macOS TTS host ping failed.)", rendered)
        self.assertIn("- macos_say_legacy: selected", rendered)
        self.assertIn("guidance:", rendered)
        self.assertIn(
            "native macOS host could not start cleanly; check local `xcrun`/`swift` toolchain and Command Line Tools.",
            rendered,
        )

    def test_format_tts_backend_status_mentions_sdk_mismatch_detail_lines(self) -> None:
        provider = _SdkMismatchFallbackFakeTTSProvider()

        rendered = format_tts_backend_status(build_tts_backend_status(provider))

        self.assertIn("- macos_native: unavailable (HOST_SDK_MISMATCH: Native macOS Swift compiler and SDK appear mismatched; align Xcode and Command Line Tools.)", rendered)
        self.assertIn("detail: sdk toolchain: Apple Swift version 6.2 effective-5.10", rendered)
        self.assertIn("detail: active compiler: Apple Swift version 6.2.4 effective-5.10", rendered)
        self.assertIn("guidance:", rendered)
        self.assertIn(
            "native macOS host hit a Swift compiler/SDK mismatch; align Xcode and Command Line Tools, then rerun `xcrun swiftc -typecheck voice/native_hosts/macos_tts_host.swift`.",
            rendered,
        )
        self.assertIn(
            "confirm the active developer dir with `xcode-select -p`.",
            rendered,
        )

    def test_format_tts_current_status_mentions_fallback_diagnostics(self) -> None:
        provider = _FallbackFakeTTSProvider()

        rendered = format_tts_current_status(build_tts_current_status(provider))

        self.assertIn("selection note: fallback active: using macos_say_legacy because macos_native is unavailable", rendered)

    def test_format_tts_doctor_status_aggregates_backend_resolution_and_guidance(self) -> None:
        provider = _FallbackFakeTTSProvider()

        rendered = format_tts_doctor_status(build_tts_doctor_status(provider))

        self.assertIn("JARVIS TTS Doctor", rendered)
        self.assertIn("active backend: macos_say_legacy", rendered)
        self.assertIn("configured backends:", rendered)
        self.assertIn("- macos_native: unavailable (HOST_PING_FAILED: Native macOS TTS host ping failed.)", rendered)
        self.assertIn("profile resolution:", rendered)
        self.assertIn("- ru_assistant_male (ru-RU): Yuri", rendered)
        self.assertIn("voice preview:", rendered)
        self.assertIn("guidance:", rendered)
        self.assertIn("native macOS host could not start cleanly; check local `xcrun`/`swift` toolchain and Command Line Tools.", rendered)

    def test_format_tts_doctor_status_mentions_profile_fallback_trace(self) -> None:
        provider = _ProfileFallbackFakeTTSProvider()

        rendered = format_tts_doctor_status(build_tts_doctor_status(provider))

        self.assertIn("profile resolution:", rendered)
        self.assertIn("- ru_assistant_male (ru-RU): Yuri", rendered)
        self.assertIn("profiles: ru_assistant_male -> ru_assistant_any", rendered)
        self.assertIn("fallback profile: ru_assistant_any", rendered)
        self.assertIn("backend: macos_say_legacy", rendered)

    def test_format_tts_doctor_status_mentions_swift_toolchain_guidance(self) -> None:
        provider = _ToolchainMissingFallbackFakeTTSProvider()

        rendered = format_tts_doctor_status(build_tts_doctor_status(provider))

        self.assertIn("guidance:", rendered)
        self.assertIn(
            "native macOS host could not find a working Swift toolchain; check `xcrun`, `swift`, and the selected Command Line Tools.",
            rendered,
        )

    def test_format_tts_doctor_status_mentions_sdk_mismatch_guidance(self) -> None:
        provider = _SdkMismatchFallbackFakeTTSProvider()

        rendered = format_tts_doctor_status(build_tts_doctor_status(provider))

        self.assertIn("guidance:", rendered)
        self.assertIn(
            "native macOS host hit a Swift compiler/SDK mismatch; align Xcode and Command Line Tools, then rerun `xcrun swiftc -typecheck voice/native_hosts/macos_tts_host.swift`.",
            rendered,
        )
        self.assertIn(
            "confirm the active developer dir with `xcode-select -p`.",
            rendered,
        )
        self.assertIn(
            "make the selected developer dir match the Xcode or Command Line Tools bundle behind the `sdk toolchain` and `active compiler` detail lines above before retrying native smoke.",
            rendered,
        )
        self.assertIn("detail: sdk toolchain: Apple Swift version 6.2 effective-5.10", rendered)
        self.assertIn("detail: active compiler: Apple Swift version 6.2.4 effective-5.10", rendered)

    def test_format_tts_doctor_status_mentions_swift_bridging_guidance(self) -> None:
        provider = _SwiftBridgingFallbackFakeTTSProvider()

        rendered = format_tts_doctor_status(build_tts_doctor_status(provider))

        self.assertIn("guidance:", rendered)
        self.assertIn(
            "native macOS host hit a SwiftBridging module conflict; inspect local toolchain overlays and rerun `xcrun swiftc -typecheck voice/native_hosts/macos_tts_host.swift`.",
            rendered,
        )

    def test_build_voice_session_status_combines_mode_and_telemetry(self) -> None:
        telemetry = VoiceTelemetryCollector()
        telemetry.record_follow_up_loop(completed_turns=2, limit_hit=True)
        telemetry.record_follow_up_loop(completed_turns=1, limit_hit=False)
        telemetry.record_speech_interruption(
            reason="initial_capture_start",
            phase="capture",
        )
        telemetry.record_speech_interruption(
            reason="final_answer_start",
            phase="response",
        )
        telemetry.record_speech_interrupt_conflict(
            reason="follow_up_capture_start",
            phase="capture",
            error_message="Cannot interrupt active speech for capture.",
        )

        status = build_voice_session_status(
            speak_enabled=True,
            telemetry_snapshot=telemetry.snapshot(),
            environ={"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
        )

        self.assertTrue(status.speak_enabled)
        self.assertTrue(status.continuous_mode_enabled)
        self.assertEqual(status.max_auto_follow_up_turns, 2)
        self.assertEqual(status.telemetry_max_follow_up_chain_length, 2)
        self.assertEqual(status.telemetry_follow_up_limit_hit_count, 1)
        self.assertEqual(status.telemetry_speech_interrupt_count, 2)
        self.assertEqual(status.telemetry_speech_interrupt_for_capture_count, 1)
        self.assertEqual(status.telemetry_speech_interrupt_for_response_count, 1)
        self.assertEqual(status.telemetry_speech_interrupt_conflict_count, 1)

    def test_build_voice_session_status_uses_empty_snapshot_when_missing(self) -> None:
        status = build_voice_session_status(
            speak_enabled=False,
            telemetry_snapshot=None,
            environ={},
        )

        self.assertFalse(status.speak_enabled)
        self.assertFalse(status.continuous_mode_enabled)
        self.assertEqual(status.max_auto_follow_up_turns, 0)
        self.assertEqual(status.telemetry_capture_attempts, 0)
        self.assertEqual(status.telemetry_max_follow_up_chain_length, 0)

    def test_format_voice_session_status_mentions_speech_mode_and_chain_metrics(self) -> None:
        telemetry = VoiceTelemetryCollector()
        telemetry.record_follow_up_loop(completed_turns=2, limit_hit=True)
        telemetry.record_speech_interruption(
            reason="initial_capture_start",
            phase="capture",
        )
        telemetry.record_speech_interrupt_conflict(
            reason="follow_up_capture_start",
            phase="capture",
            error_message="Cannot interrupt active speech for capture.",
        )

        rendered = format_voice_session_status(
            build_voice_session_status(
                speak_enabled=True,
                telemetry_snapshot=telemetry.snapshot(),
                environ={"JARVIS_VOICE_CONTINUOUS_MODE": "1"},
            )
        )

        self.assertIn("JARVIS Voice Status", rendered)
        self.assertIn("speech output enabled: yes", rendered)
        self.assertIn("continuous mode enabled: yes", rendered)
        self.assertIn("max auto follow-up turns: 2", rendered)
        self.assertIn("telemetry max follow-up chain length: 2", rendered)
        self.assertIn("telemetry follow-up limit hit count: 1", rendered)
        self.assertIn("telemetry speech interrupt count: 1", rendered)
        self.assertIn("telemetry speech interrupt for capture count: 1", rendered)
        self.assertIn("telemetry speech interrupt for response count: 0", rendered)
        self.assertIn("telemetry speech interrupt conflict count: 1", rendered)

class _FakeTTSProvider:
    def __init__(self) -> None:
        self._voices = {
            "ru_assistant_male": VoiceDescriptor(
                id="Yuri",
                display_name="Yuri",
                locale="ru-RU",
                gender_hint="male",
                quality_hint="default",
                source="say",
            ),
            "ru_assistant_female": VoiceDescriptor(
                id="Milena",
                display_name="Milena",
                locale="ru-RU",
                gender_hint="female",
                quality_hint="default",
                source="say",
            ),
            "ru_assistant_any": VoiceDescriptor(
                id="Yuri",
                display_name="Yuri",
                locale="ru-RU",
                gender_hint="male",
                quality_hint="default",
                source="say",
            ),
            "en_assistant_male": VoiceDescriptor(
                id="Reed (English (US))",
                display_name="Reed (English (US))",
                locale="en-US",
                gender_hint="male",
                quality_hint="assistant",
                source="say",
            ),
            "en_assistant_female": VoiceDescriptor(
                id="Samantha",
                display_name="Samantha",
                locale="en-US",
                gender_hint="female",
                quality_hint="default",
                source="say",
            ),
            "en_assistant_any": VoiceDescriptor(
                id="Reed (English (US))",
                display_name="Reed (English (US))",
                locale="en-US",
                gender_hint="male",
                quality_hint="assistant",
                source="say",
            ),
        }

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            backend_name="macos_say_legacy",
            supports_stop=True,
            supports_voice_listing=True,
            supports_voice_resolution=True,
            supports_explicit_voice_id=True,
            supports_rate=True,
            is_fallback=True,
        )

    def is_available(self) -> bool:
        return True

    def list_voices(self, locale_hint: str | None = None) -> list[VoiceDescriptor]:
        voices: list[VoiceDescriptor] = []
        for profile_id in ("ru_assistant_male", "ru_assistant_female"):
            voice = self._voices.get(profile_id)
            if voice is not None:
                voices.append(voice)
        if not locale_hint:
            return voices
        language = str(locale_hint or "").split("-", maxsplit=1)[0].lower()
        return [voice for voice in voices if str(voice.locale or "").lower().startswith(language)]

    def resolve_voice(self, profile_id: str, locale: str | None = None) -> VoiceDescriptor | None:
        return self._voices.get(profile_id)

    def resolve_voice_trace(self, profile_id: str, locale: str | None = None) -> VoiceResolutionTrace:
        requested_profile_id = str(profile_id or default_voice_profile_for_locale(locale) or "").strip()
        attempted_profile_ids = fallback_voice_profile_ids(requested_profile_id or None, locale)
        if not attempted_profile_ids and requested_profile_id:
            attempted_profile_ids = (requested_profile_id,)
        for attempted_profile_id in attempted_profile_ids:
            voice = self._voices.get(attempted_profile_id)
            if voice is None:
                continue
            note = (
                f"resolved requested profile on {self.capabilities().backend_name}"
                if attempted_profile_id == requested_profile_id
                else f"resolved via fallback profile {attempted_profile_id} on {self.capabilities().backend_name}"
            )
            return VoiceResolutionTrace(
                requested_profile_id=requested_profile_id,
                locale=locale,
                attempted_profile_ids=attempted_profile_ids,
                resolved_profile_id=attempted_profile_id,
                backend_name=self.capabilities().backend_name,
                resolved_voice=voice,
                note=note,
            )
        return VoiceResolutionTrace(
            requested_profile_id=requested_profile_id,
            locale=locale,
            attempted_profile_ids=attempted_profile_ids,
            resolved_profile_id=None,
            backend_name=self.capabilities().backend_name,
            resolved_voice=None,
            note=(
                f"unresolved after trying profiles: {', '.join(attempted_profile_ids)} "
                f"on {self.capabilities().backend_name}"
            ),
        )


class _FallbackFakeTTSProvider(_FakeTTSProvider):
    def backend_diagnostics(self) -> tuple[BackendRuntimeStatus, ...]:
        return (
            BackendRuntimeStatus(
                backend_name="macos_native",
                available=False,
                selected=False,
                error_code="HOST_PING_FAILED",
                error_message="Native macOS TTS host ping failed.",
                capabilities=BackendCapabilities(
                    backend_name="macos_native",
                    supports_stop=True,
                    supports_voice_listing=True,
                    supports_voice_resolution=True,
                    supports_explicit_voice_id=True,
                    supports_rate=True,
                    supports_volume=True,
                ),
            ),
            BackendRuntimeStatus(
                backend_name="macos_say_legacy",
                available=True,
                selected=True,
                capabilities=self.capabilities(),
            ),
        )


class _ProfileFallbackFakeTTSProvider(_FakeTTSProvider):
    def __init__(self) -> None:
        super().__init__()
        del self._voices["ru_assistant_male"]


class _ToolchainMissingFallbackFakeTTSProvider(_FakeTTSProvider):
    def backend_diagnostics(self) -> tuple[BackendRuntimeStatus, ...]:
        return (
            BackendRuntimeStatus(
                backend_name="macos_native",
                available=False,
                selected=False,
                error_code="HOST_TOOLCHAIN_MISSING",
                error_message="Native macOS Swift toolchain is unavailable; check `xcrun`, `swift`, and Command Line Tools.",
                capabilities=BackendCapabilities(
                    backend_name="macos_native",
                    supports_stop=True,
                    supports_voice_listing=True,
                    supports_voice_resolution=True,
                    supports_explicit_voice_id=True,
                    supports_rate=True,
                    supports_volume=True,
                ),
            ),
            BackendRuntimeStatus(
                backend_name="macos_say_legacy",
                available=True,
                selected=True,
                capabilities=self.capabilities(),
            ),
        )


class _SdkMismatchFallbackFakeTTSProvider(_FakeTTSProvider):
    def backend_diagnostics(self) -> tuple[BackendRuntimeStatus, ...]:
        return (
            BackendRuntimeStatus(
                backend_name="macos_native",
                available=False,
                selected=False,
                error_code="HOST_SDK_MISMATCH",
                error_message="Native macOS Swift compiler and SDK appear mismatched; align Xcode and Command Line Tools.",
                detail_lines=(
                    "sdk toolchain: Apple Swift version 6.2 effective-5.10",
                    "active compiler: Apple Swift version 6.2.4 effective-5.10",
                ),
                capabilities=BackendCapabilities(
                    backend_name="macos_native",
                    supports_stop=True,
                    supports_voice_listing=True,
                    supports_voice_resolution=True,
                    supports_explicit_voice_id=True,
                    supports_rate=True,
                    supports_volume=True,
                ),
            ),
            BackendRuntimeStatus(
                backend_name="macos_say_legacy",
                available=True,
                selected=True,
                capabilities=self.capabilities(),
            ),
        )


class _SwiftBridgingFallbackFakeTTSProvider(_FakeTTSProvider):
    def backend_diagnostics(self) -> tuple[BackendRuntimeStatus, ...]:
        return (
            BackendRuntimeStatus(
                backend_name="macos_native",
                available=False,
                selected=False,
                error_code="HOST_SWIFT_BRIDGING_CONFLICT",
                error_message="Native macOS Swift toolchain reported a SwiftBridging module conflict.",
                capabilities=BackendCapabilities(
                    backend_name="macos_native",
                    supports_stop=True,
                    supports_voice_listing=True,
                    supports_voice_resolution=True,
                    supports_explicit_voice_id=True,
                    supports_rate=True,
                    supports_volume=True,
                ),
            ),
            BackendRuntimeStatus(
                backend_name="macos_say_legacy",
                available=True,
                selected=True,
                capabilities=self.capabilities(),
            ),
        )


if __name__ == "__main__":
    unittest.main()
