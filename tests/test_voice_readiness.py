"""Offline voice-readiness helper tests."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from input.voice_input import VoiceInputError
from voice.session import VoiceTurn
from voice.readiness import (
    build_voice_readiness_record,
    format_voice_readiness_record,
    load_voice_readiness_artifact,
    write_voice_readiness_artifact,
)
from voice.tts_models import BackendCapabilities, BackendRuntimeStatus
from voice.telemetry import build_default_voice_telemetry, write_voice_telemetry_artifact


class VoiceReadinessTests(unittest.TestCase):
    """Keep the staged voice-rollout helper explicit and safe by default."""

    def setUp(self) -> None:
        self._default_tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._default_tmpdir.cleanup)
        self._default_telemetry_artifact_path = Path(self._default_tmpdir.name) / "voice_telemetry.json"
        self._telemetry_path_patch = patch(
            "voice.readiness.voice_telemetry_artifact_path",
            return_value=self._default_telemetry_artifact_path,
        )
        self._telemetry_path_patch.start()
        self.addCleanup(self._telemetry_path_patch.stop)
        self._probe_patch = patch("voice.readiness.probe_voice_input_permissions", return_value=None)
        self._probe_patch.start()
        self.addCleanup(self._probe_patch.stop)

    def test_build_record_is_blocked_until_manual_verification_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"

            record = build_voice_readiness_record(
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )

        self.assertFalse(record.voice_ready)
        self.assertEqual(record.artifact_status, "missing")
        self.assertTrue(record.advanced_follow_up_default_off)
        self.assertTrue(record.telemetry_available)
        self.assertTrue(record.follow_up_session_available)
        self.assertIn("manual voice verification is not recorded", record.blockers)
        self.assertEqual(record.next_step_kind, "complete_manual_voice_verification")
        self.assertEqual(
            record.next_step_command,
            "python3 -m voice.readiness --manual-verified --write-artifact",
        )

    def test_ready_record_can_be_written_and_reloaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"
            record = build_voice_readiness_record(
                manual_verified=True,
                notes="manual microphone check passed",
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )

            written_path = write_voice_readiness_artifact(record, artifact_path=artifact_path)
            loaded_path, payload, error = load_voice_readiness_artifact(artifact_path)
            reloaded_record = build_voice_readiness_record(
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )

        self.assertEqual(written_path, artifact_path)
        self.assertEqual(loaded_path, artifact_path)
        self.assertIsNone(error)
        self.assertIsNotNone(payload)
        self.assertTrue(record.voice_ready)
        self.assertEqual(reloaded_record.artifact_status, "ready")
        self.assertTrue(reloaded_record.manual_verification_recorded)
        self.assertTrue(reloaded_record.voice_ready)
        self.assertEqual(reloaded_record.next_step_kind, "voice_readiness_artifact_already_recorded")

    def test_ready_record_stays_ready_when_telemetry_artifact_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"

            record = build_voice_readiness_record(
                manual_verified=True,
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )

        self.assertTrue(record.voice_ready)
        self.assertEqual(record.telemetry_artifact_status, "missing")
        self.assertEqual(record.telemetry_artifact_command, "voice telemetry write")

    def test_ready_record_reports_telemetry_artifact_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"
            telemetry = build_default_voice_telemetry()
            prior_turn = VoiceTurn(
                raw_transcript="Что ты умеешь?",
                normalized_transcript="what can you do",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                follow_up_reason="short_answer",
                follow_up_window_seconds=6.0,
            )
            telemetry.record_follow_up_control(
                prior_turn,
                VoiceTurn(
                    raw_transcript="слушай снова",
                    normalized_transcript="listen again",
                    detected_locale="ru-RU",
                    locale_hint="ru-RU",
                ),
                action="listen_again",
            )
            telemetry.record_follow_up_control(
                prior_turn,
                VoiceTurn(
                    raw_transcript="замолчи",
                    normalized_transcript="stop speaking",
                    detected_locale="ru-RU",
                    locale_hint="ru-RU",
                ),
                action="dismiss_follow_up",
            )
            telemetry.record_follow_up_loop(completed_turns=2, limit_hit=True)
            written_telemetry_path = write_voice_telemetry_artifact(
                telemetry.snapshot(),
                artifact_path=telemetry_artifact_path,
            )

            record = build_voice_readiness_record(
                manual_verified=True,
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )

        self.assertEqual(written_telemetry_path, telemetry_artifact_path)
        self.assertEqual(record.telemetry_artifact_path, str(telemetry_artifact_path))
        self.assertEqual(record.telemetry_artifact_status, "ready")
        self.assertIsNotNone(record.telemetry_artifact_created_at)
        self.assertEqual(record.telemetry_follow_up_relisten_count, 1)
        self.assertEqual(record.telemetry_follow_up_dismiss_count, 1)
        self.assertEqual(record.telemetry_max_follow_up_chain_length, 2)
        self.assertEqual(record.telemetry_follow_up_limit_hit_count, 1)
        self.assertEqual(record.telemetry_speech_interrupt_conflict_count, 0)

    def test_format_mentions_flag_doc_and_next_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"
            record = build_voice_readiness_record(
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )

        rendered = format_voice_readiness_record(record)

        self.assertIn("JARVIS Voice Readiness", rendered)
        self.assertIn("advanced follow-up flag: JARVIS_VOICE_CONTINUOUS_MODE", rendered)
        self.assertIn("manual verification doc: docs/manual_voice_verification.md", rendered)
        self.assertIn(f"telemetry artifact path: {telemetry_artifact_path}", rendered)
        self.assertIn("telemetry artifact status: missing", rendered)
        self.assertIn("telemetry artifact command: voice telemetry write", rendered)
        self.assertIn("telemetry follow-up relisten count: n/a", rendered)
        self.assertIn("telemetry follow-up dismiss count: n/a", rendered)
        self.assertIn("telemetry max follow-up chain length: n/a", rendered)
        self.assertIn("telemetry follow-up limit hit count: n/a", rendered)
        self.assertIn("telemetry speech interrupt conflict count: n/a", rendered)
        self.assertIn("telemetry note: advisory only; record a session snapshot before live sign-off with voice telemetry write", rendered)
        self.assertIn("next step: complete_manual_voice_verification", rendered)

    def test_format_mentions_telemetry_follow_up_counts_when_artifact_is_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"
            telemetry = build_default_voice_telemetry()
            prior_turn = VoiceTurn(
                raw_transcript="Закрой телеграм",
                normalized_transcript="close telegram",
                detected_locale="ru-RU",
                locale_hint="ru-RU",
                lifecycle_state="awaiting_follow_up",
                follow_up_reason="confirmation",
                follow_up_window_seconds=8.0,
            )
            telemetry.record_follow_up_control(
                prior_turn,
                VoiceTurn(
                    raw_transcript="слушай снова",
                    normalized_transcript="listen again",
                    detected_locale="ru-RU",
                    locale_hint="ru-RU",
                ),
                action="listen_again",
            )
            telemetry.record_follow_up_loop(completed_turns=2, limit_hit=False)
            telemetry.record_speech_interrupt_conflict(
                reason="follow_up_capture_start",
                phase="capture",
                error_message="Cannot interrupt active speech for capture.",
            )
            write_voice_telemetry_artifact(
                telemetry.snapshot(),
                artifact_path=telemetry_artifact_path,
            )
            record = build_voice_readiness_record(
                manual_verified=True,
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
            )

        rendered = format_voice_readiness_record(record)

        self.assertIn("telemetry follow-up relisten count: 1", rendered)
        self.assertIn("telemetry follow-up dismiss count: 0", rendered)
        self.assertIn("telemetry max follow-up chain length: 2", rendered)
        self.assertIn("telemetry follow-up limit hit count: 0", rendered)
        self.assertIn("telemetry speech interrupt conflict count: 1", rendered)
        self.assertIn(
            "telemetry note: latest session telemetry artifact is recorded (follow-up relisten=1, dismiss=0, max_chain=2, limit_hits=0, interrupt_conflicts=1)",
            rendered,
        )

    def test_build_record_marks_native_tts_opt_in_as_blocked_when_backend_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "voice.readiness.sys.platform",
            "darwin",
        ), patch(
            "voice.readiness.build_default_tts_provider",
            return_value=_SdkMismatchNativeOptInProvider(),
        ):
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            record = build_voice_readiness_record(
                manual_verified=True,
                artifact_path=artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "1"},
            )

        self.assertFalse(record.voice_ready)
        self.assertTrue(record.native_tts_requested)
        self.assertEqual(record.native_tts_status, "blocked")
        self.assertEqual(record.native_tts_active_backend, "macos_say_legacy")
        self.assertEqual(
            record.native_tts_reason,
            "HOST_SDK_MISMATCH: Native macOS Swift compiler and SDK appear mismatched; align Xcode and Command Line Tools.",
        )
        self.assertEqual(record.native_tts_command, "xcrun swiftc -typecheck voice/native_hosts/macos_tts_host.swift")
        self.assertEqual(record.next_step_kind, "resolve_native_tts_sdk_mismatch")
        self.assertEqual(
            record.next_step_reason,
            "align local Xcode and Command Line Tools so the active Swift compiler matches the installed SDK before native smoke",
        )
        self.assertEqual(record.next_step_command, "xcrun swiftc -typecheck voice/native_hosts/macos_tts_host.swift")
        self.assertEqual(
            record.next_step_detail_lines,
            [
                "confirm active developer dir with: xcode-select -p",
                "make the selected developer dir match the Xcode or Command Line Tools bundle behind the sdk toolchain, active compiler, active developer dir, and active swiftc details above, then rerun the native typecheck",
            ],
        )
        self.assertIn(
            "native macOS TTS smoke is blocked (HOST_SDK_MISMATCH: Native macOS Swift compiler and SDK appear mismatched; align Xcode and Command Line Tools.)",
            record.blockers,
        )

    def test_build_record_keeps_developer_dir_override_for_ready_native_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "voice.readiness.sys.platform",
            "darwin",
        ), patch(
            "voice.readiness.build_default_tts_provider",
            return_value=_ReadyNativeOptInProvider(),
        ):
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"
            record = build_voice_readiness_record(
                manual_verified=True,
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={
                    "JARVIS_TTS_MACOS_NATIVE": "1",
                    "DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer",
                },
            )

        self.assertTrue(record.voice_ready)
        self.assertEqual(record.native_tts_status, "ready")
        self.assertEqual(record.native_tts_active_backend, "macos_native")
        self.assertEqual(
            record.native_tts_command,
            "env DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer python3 cli.py",
        )
        self.assertEqual(
            record.native_tts_detail_lines,
            ["developer dir override: /Applications/Xcode.app/Contents/Developer"],
        )
        self.assertEqual(record.latest_capture_status, "not_recorded")

    def test_build_record_surfaces_latest_live_capture_permission_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "voice.readiness.sys.platform",
            "darwin",
        ), patch(
            "voice.readiness.build_default_tts_provider",
            return_value=_ReadyNativeOptInProvider(),
        ):
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"
            telemetry = build_default_voice_telemetry()
            telemetry.record_capture(
                phase="initial",
                elapsed_seconds=0.1,
                error=VoiceInputError(
                    "PERMISSION_DENIED",
                    "Speech recognition access was denied.",
                    hint="Check macOS Settings -> Privacy & Security -> Microphone / Speech Recognition.",
                ),
            )
            write_voice_telemetry_artifact(telemetry.snapshot(), artifact_path=telemetry_artifact_path)
            record = build_voice_readiness_record(
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={
                    "JARVIS_TTS_MACOS_NATIVE": "1",
                    "DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer",
                },
            )

        self.assertFalse(record.voice_ready)
        self.assertEqual(record.latest_capture_status, "blocked")
        self.assertEqual(
            record.latest_capture_reason,
            "PERMISSION_DENIED: Speech recognition access was denied.",
        )
        self.assertEqual(
            record.latest_capture_hint,
            "Check macOS Settings -> Privacy & Security -> Microphone / Speech Recognition.",
        )
        self.assertEqual(
            record.latest_capture_command,
            "env DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer python3 cli.py",
        )
        self.assertEqual(record.capture_preflight_status, "clear")
        self.assertEqual(record.next_step_kind, "complete_manual_voice_verification")
        self.assertNotIn("live voice capture is currently blocked", ", ".join(record.blockers))

    def test_format_mentions_native_tts_block_details_when_opted_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "voice.readiness.sys.platform",
            "darwin",
        ), patch(
            "voice.readiness.build_default_tts_provider",
            return_value=_SdkMismatchNativeOptInProvider(),
        ):
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            record = build_voice_readiness_record(
                manual_verified=True,
                artifact_path=artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "1"},
            )

        rendered = format_voice_readiness_record(record)

        self.assertIn("native tts enabled in current env: yes", rendered)
        self.assertIn("native tts smoke status: blocked", rendered)
        self.assertIn("native tts active backend: macos_say_legacy", rendered)
        self.assertIn(
            "native tts reason: HOST_SDK_MISMATCH: Native macOS Swift compiler and SDK appear mismatched; align Xcode and Command Line Tools.",
            rendered,
        )
        self.assertIn("native tts command: xcrun swiftc -typecheck voice/native_hosts/macos_tts_host.swift", rendered)
        self.assertIn("native tts detail: sdk toolchain: Apple Swift version 6.2 effective-5.10", rendered)
        self.assertIn("native tts detail: active compiler: Apple Swift version 6.2.4 effective-5.10", rendered)
        self.assertIn("native tts detail: active developer dir: /Library/Developer/CommandLineTools", rendered)
        self.assertIn("native tts detail: active swiftc: /Library/Developer/CommandLineTools/usr/bin/swiftc", rendered)
        self.assertIn("next step: resolve_native_tts_sdk_mismatch", rendered)
        self.assertIn(
            "next step reason: align local Xcode and Command Line Tools so the active Swift compiler matches the installed SDK before native smoke",
            rendered,
        )
        self.assertIn("next step detail: confirm active developer dir with: xcode-select -p", rendered)
        self.assertIn(
            "next step detail: make the selected developer dir match the Xcode or Command Line Tools bundle behind the sdk toolchain, active compiler, active developer dir, and active swiftc details above, then rerun the native typecheck",
            rendered,
        )

    def test_format_mentions_latest_live_capture_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"
            telemetry = build_default_voice_telemetry()
            telemetry.record_capture(
                phase="initial",
                elapsed_seconds=0.2,
                error=VoiceInputError(
                    "PERMISSION_DENIED",
                    "Speech recognition access was denied.",
                    hint="Check macOS Settings -> Privacy & Security -> Microphone / Speech Recognition.",
                ),
            )
            write_voice_telemetry_artifact(telemetry.snapshot(), artifact_path=telemetry_artifact_path)
            record = build_voice_readiness_record(
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )

        rendered = format_voice_readiness_record(record)

        self.assertIn("latest recorded live capture status: blocked", rendered)
        self.assertIn(
            "latest recorded live capture reason: PERMISSION_DENIED: Speech recognition access was denied.",
            rendered,
        )
        self.assertIn("latest recorded live capture command: python3 cli.py", rendered)
        self.assertIn(
            "latest recorded live capture hint: Check macOS Settings -> Privacy & Security -> Microphone / Speech Recognition.",
            rendered,
        )

    def test_build_record_preflights_live_capture_permissions_without_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "voice.readiness.probe_voice_input_permissions",
            return_value=VoiceInputError(
                "PERMISSION_PROMPT_REQUIRED",
                "Speech recognition permission has not been requested yet.",
                hint="Check macOS Settings -> Privacy & Security -> Microphone / Speech Recognition.",
            ),
        ):
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"
            record = build_voice_readiness_record(
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )

        self.assertEqual(record.capture_preflight_status, "blocked")
        self.assertEqual(
            record.capture_preflight_reason,
            "PERMISSION_PROMPT_REQUIRED: Speech recognition permission has not been requested yet.",
        )
        self.assertEqual(record.latest_capture_status, "not_recorded")
        self.assertEqual(record.next_step_kind, "grant_live_voice_permissions")
        self.assertEqual(record.next_step_command, "python3 cli.py")
        self.assertEqual(
            record.next_step_reason,
            "allow macOS Speech Recognition and Microphone access for the current voice capture helper, then rerun live voice smoke",
        )
        self.assertIn(
            "voice capture helper bundle id: com.jarvis.voice.capture.helper",
            record.next_step_detail_lines,
        )
        self.assertIn(
            "voice capture helper runtime dir: /Users/arseniyabramidze/JARVIS/tmp/runtime/voice_capture",
            record.next_step_detail_lines,
        )
        self.assertIn(
            "live voice capture is currently blocked (PERMISSION_PROMPT_REQUIRED: Speech recognition permission has not been requested yet.)",
            record.blockers,
        )

    def test_build_record_uses_developer_dir_override_in_native_follow_up_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "voice.readiness.sys.platform",
            "darwin",
        ), patch(
            "voice.readiness.build_default_tts_provider",
            return_value=_SdkMismatchNativeOptInProviderWithDeveloperDirOverride(),
        ):
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            record = build_voice_readiness_record(
                manual_verified=True,
                artifact_path=artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "1"},
            )

        self.assertEqual(
            record.native_tts_command,
            "env DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcrun swiftc -typecheck voice/native_hosts/macos_tts_host.swift",
        )
        self.assertEqual(
            record.next_step_command,
            "env DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcrun swiftc -typecheck voice/native_hosts/macos_tts_host.swift",
        )
        self.assertIn(
            "current env override: DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer; if that override is intentional, keep using it on the next typecheck and CLI smoke, otherwise fix or unset it before retrying",
            record.next_step_detail_lines,
        )

    def test_build_record_treats_native_tts_as_enabled_by_default_on_darwin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "voice.readiness.sys.platform",
            "darwin",
        ), patch(
            "voice.readiness.build_default_tts_provider",
            return_value=_ReadyNativeOptInProvider(),
        ):
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            record = build_voice_readiness_record(
                manual_verified=True,
                artifact_path=artifact_path,
                environ={},
            )

        self.assertTrue(record.native_tts_requested)
        self.assertEqual(record.native_tts_status, "ready")
        self.assertEqual(record.native_tts_command, "python3 cli.py")

    def test_build_record_honors_explicit_native_tts_opt_out_on_darwin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "voice.readiness.sys.platform",
            "darwin",
        ):
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            record = build_voice_readiness_record(
                manual_verified=True,
                artifact_path=artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )

        self.assertFalse(record.native_tts_requested)
        self.assertEqual(record.native_tts_status, "not_requested")
        self.assertEqual(record.native_tts_reason, "native macOS backend is explicitly disabled in the current env")

    def test_build_record_specializes_timeout_native_opt_in_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "voice.readiness.sys.platform",
            "darwin",
        ), patch(
            "voice.readiness.build_default_tts_provider",
            return_value=_TimeoutNativeOptInProvider(),
        ):
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            record = build_voice_readiness_record(
                manual_verified=True,
                artifact_path=artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "1"},
            )

        self.assertFalse(record.voice_ready)
        self.assertEqual(record.native_tts_status, "blocked")
        self.assertEqual(record.next_step_kind, "resolve_native_tts_host_timeout")
        self.assertEqual(
            record.next_step_reason,
            "inspect the current native macOS toolchain selection and rerun the native doctor helper before retrying smoke",
        )
        self.assertEqual(
            record.next_step_command,
            "printf 'voice tts doctor\\nquit\\n' | python3 cli.py",
        )
        self.assertEqual(
            record.next_step_detail_lines,
            [
                "confirm active developer dir with: xcode-select -p",
                "if the native host keeps timing out, compare the active developer dir and active swiftc details above, then rerun the native doctor helper before retrying smoke",
            ],
        )

    def test_build_record_keeps_override_detail_for_compile_failed_native_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "voice.readiness.sys.platform",
            "darwin",
        ), patch(
            "voice.readiness.build_default_tts_provider",
            return_value=_CompileFailedNativeOptInProviderWithDeveloperDirOverride(),
        ):
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            record = build_voice_readiness_record(
                manual_verified=True,
                artifact_path=artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "1"},
            )

        self.assertEqual(record.next_step_kind, "resolve_native_tts_compile_failure")
        self.assertEqual(
            record.next_step_command,
            "env DEVELOPER_DIR=/tmp/jarvis-invalid-developer-dir xcrun swiftc -typecheck voice/native_hosts/macos_tts_host.swift",
        )
        self.assertEqual(
            record.next_step_detail_lines,
            [
                "current env override: DEVELOPER_DIR=/tmp/jarvis-invalid-developer-dir; if that override is intentional, keep using it on the next typecheck and CLI smoke, otherwise fix or unset it before retrying",
            ],
        )

    def test_format_mentions_timeout_native_tts_block_details_when_opted_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "voice.readiness.sys.platform",
            "darwin",
        ), patch(
            "voice.readiness.build_default_tts_provider",
            return_value=_TimeoutNativeOptInProvider(),
        ):
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            record = build_voice_readiness_record(
                manual_verified=True,
                artifact_path=artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "1"},
            )

        rendered = format_voice_readiness_record(record)

        self.assertIn("native tts reason: HOST_TIMEOUT: Native macOS TTS host ping timed out.", rendered)
        self.assertIn(
            "native tts command: printf 'voice tts doctor\\nquit\\n' | python3 cli.py",
            rendered,
        )
        self.assertIn("native tts detail: active developer dir: /Library/Developer/CommandLineTools", rendered)
        self.assertIn("native tts detail: active swiftc: /Library/Developer/CommandLineTools/usr/bin/swiftc", rendered)
        self.assertIn("next step: resolve_native_tts_host_timeout", rendered)
        self.assertIn(
            "next step detail: if the native host keeps timing out, compare the active developer dir and active swiftc details above, then rerun the native doctor helper before retrying smoke",
            rendered,
        )

    def test_module_can_write_artifact_to_explicit_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"
            completed = subprocess.run(
                [
                    "python3",
                    "-m",
                    "voice.readiness",
                    "--artifact-path",
                    str(artifact_path),
                    "--telemetry-artifact-path",
                    str(telemetry_artifact_path),
                    "--manual-verified",
                    "--write-artifact",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={
                    **dict(os.environ),
                    "JARVIS_VOICE_CAPTURE_PREFLIGHT": "0",
                    "JARVIS_TTS_MACOS_NATIVE": "0",
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0)
            self.assertTrue(artifact_path.exists())
            self.assertIn(f"wrote voice readiness artifact: {artifact_path}", completed.stdout)

    def test_module_accepts_explicit_telemetry_artifact_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"
            completed = subprocess.run(
                [
                    "python3",
                    "-m",
                    "voice.readiness",
                    "--artifact-path",
                    str(artifact_path),
                    "--telemetry-artifact-path",
                    str(telemetry_artifact_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={**dict(os.environ), "JARVIS_TTS_MACOS_NATIVE": "0"},
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertIn(f"telemetry artifact path: {telemetry_artifact_path}", completed.stdout)
        self.assertIn("telemetry artifact status: missing", completed.stdout)

class _SdkMismatchNativeOptInProvider:
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
                    "active developer dir: /Library/Developer/CommandLineTools",
                    "active swiftc: /Library/Developer/CommandLineTools/usr/bin/swiftc",
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


class _ReadyNativeOptInProvider:
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            backend_name="macos_native",
            supports_stop=True,
            supports_voice_listing=True,
            supports_voice_resolution=True,
            supports_explicit_voice_id=True,
            supports_rate=True,
            supports_volume=True,
        )

    def is_available(self) -> bool:
        return True

    def backend_diagnostics(self) -> tuple[BackendRuntimeStatus, ...]:
        return (
            BackendRuntimeStatus(
                backend_name="macos_native",
                available=True,
                selected=True,
                capabilities=self.capabilities(),
            ),
            BackendRuntimeStatus(
                backend_name="macos_say_legacy",
                available=True,
                selected=False,
                capabilities=BackendCapabilities(
                    backend_name="macos_say_legacy",
                    supports_stop=True,
                    supports_voice_listing=True,
                    supports_voice_resolution=True,
                    supports_explicit_voice_id=True,
                    supports_rate=True,
                    is_fallback=True,
                ),
            ),
        )


class _SdkMismatchNativeOptInProviderWithDeveloperDirOverride:
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
                    "developer dir override: /Applications/Xcode.app/Contents/Developer",
                    "active developer dir: /Applications/Xcode.app/Contents/Developer",
                    "active swiftc: /Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc",
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


class _TimeoutNativeOptInProvider:
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

    def backend_diagnostics(self) -> tuple[BackendRuntimeStatus, ...]:
        return (
            BackendRuntimeStatus(
                backend_name="macos_native",
                available=False,
                selected=False,
                error_code="HOST_TIMEOUT",
                error_message="Native macOS TTS host ping timed out.",
                detail_lines=(
                    "active developer dir: /Library/Developer/CommandLineTools",
                    "active swiftc: /Library/Developer/CommandLineTools/usr/bin/swiftc",
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


class _CompileFailedNativeOptInProviderWithDeveloperDirOverride:
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

    def backend_diagnostics(self) -> tuple[BackendRuntimeStatus, ...]:
        return (
            BackendRuntimeStatus(
                backend_name="macos_native",
                available=False,
                selected=False,
                error_code="HOST_COMPILE_FAILED",
                error_message="Native macOS TTS host failed to compile or start. First error: xcrun: error: missing DEVELOPER_DIR path: /tmp/jarvis-invalid-developer-dir",
                detail_lines=(
                    "developer dir override: /tmp/jarvis-invalid-developer-dir",
                    "active developer dir: /tmp/jarvis-invalid-developer-dir",
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


if __name__ == "__main__":
    unittest.main()
