"""Offline voice rollout gate helper tests."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from input.voice_input import VoiceInputError
from voice.session import VoiceTurn
from voice.gate import (
    build_voice_readiness_gate_report,
    format_voice_readiness_gate_report,
)
from voice.readiness import build_voice_readiness_record, write_voice_readiness_artifact
from voice.tts_models import BackendCapabilities, BackendRuntimeStatus
from voice.telemetry import build_default_voice_telemetry, write_voice_telemetry_artifact


class VoiceReadinessGateTests(unittest.TestCase):
    """Keep the voice rollout gate explicit and blocked until readiness is recorded."""

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

    def test_gate_is_blocked_until_voice_readiness_artifact_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"
            report = build_voice_readiness_gate_report(
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )

        self.assertFalse(report.gate_ready)
        self.assertEqual(report.gate_status, "blocked")
        self.assertEqual(report.artifact_status, "missing")
        self.assertEqual(report.next_step_kind, "complete_manual_voice_verification")
        self.assertEqual(report.telemetry_artifact_status, "missing")
        self.assertIn("manual voice verification is not recorded", report.blockers)
        self.assertIn("voice readiness artifact status is missing", report.blockers)

    def test_gate_is_ready_after_matching_readiness_artifact_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"
            record = build_voice_readiness_record(
                manual_verified=True,
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )
            write_voice_readiness_artifact(record, artifact_path=artifact_path)

            report = build_voice_readiness_gate_report(
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )

        self.assertTrue(report.gate_ready)
        self.assertEqual(report.gate_status, "ready")
        self.assertEqual(report.artifact_status, "ready")
        self.assertEqual(report.telemetry_artifact_status, "missing")
        self.assertEqual(report.next_step_kind, "voice_readiness_artifact_already_recorded")
        self.assertEqual(report.blockers, [])

    def test_gate_can_report_ready_telemetry_artifact_without_affecting_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"
            record = build_voice_readiness_record(
                manual_verified=True,
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )
            write_voice_readiness_artifact(record, artifact_path=artifact_path)
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
                    raw_transcript="замолчи",
                    normalized_transcript="stop speaking",
                    detected_locale="ru-RU",
                    locale_hint="ru-RU",
                ),
                action="dismiss_follow_up",
            )
            telemetry.record_follow_up_loop(completed_turns=2, limit_hit=True)
            write_voice_telemetry_artifact(
                telemetry.snapshot(),
                artifact_path=telemetry_artifact_path,
            )

            report = build_voice_readiness_gate_report(
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )

        self.assertTrue(report.gate_ready)
        self.assertEqual(report.telemetry_artifact_path, str(telemetry_artifact_path))
        self.assertEqual(report.telemetry_artifact_status, "ready")
        self.assertEqual(report.telemetry_follow_up_relisten_count, 0)
        self.assertEqual(report.telemetry_follow_up_dismiss_count, 1)
        self.assertEqual(report.telemetry_max_follow_up_chain_length, 2)
        self.assertEqual(report.telemetry_follow_up_limit_hit_count, 1)
        self.assertEqual(report.telemetry_speech_interrupt_conflict_count, 0)
        self.assertEqual(
            report.telemetry_note,
            "latest session telemetry artifact is recorded (follow-up relisten=0, dismiss=1, max_chain=2, limit_hits=1, interrupt_conflicts=0)",
        )

    def test_format_mentions_gate_status_and_next_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"
            report = build_voice_readiness_gate_report(
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )

        rendered = format_voice_readiness_gate_report(report)

        self.assertIn("JARVIS Voice Readiness Gate", rendered)
        self.assertIn("gate: blocked", rendered)
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

    def test_gate_reports_native_tts_opt_in_blockers(self) -> None:
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
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )
            write_voice_readiness_artifact(record, artifact_path=artifact_path)
            report = build_voice_readiness_gate_report(
                artifact_path=artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "1"},
            )

        self.assertFalse(report.gate_ready)
        self.assertEqual(report.native_tts_status, "blocked")
        self.assertEqual(report.native_tts_active_backend, "macos_say_legacy")
        self.assertEqual(report.next_step_kind, "resolve_native_tts_sdk_mismatch")
        self.assertEqual(
            report.next_step_reason,
            "align local Xcode and Command Line Tools so the active Swift compiler matches the installed SDK before native smoke",
        )
        self.assertEqual(report.next_step_command, "xcrun swiftc -typecheck voice/native_hosts/macos_tts_host.swift")
        self.assertEqual(
            report.next_step_detail_lines,
            [
                "confirm active developer dir with: xcode-select -p",
                "make the selected developer dir match the Xcode or Command Line Tools bundle behind the sdk toolchain, active compiler, active developer dir, and active swiftc details above, then rerun the native typecheck",
            ],
        )
        self.assertIn(
            "native macOS TTS smoke is blocked (HOST_SDK_MISMATCH: Native macOS Swift compiler and SDK appear mismatched; align Xcode and Command Line Tools.)",
            report.blockers,
        )

    def test_gate_keeps_developer_dir_override_for_ready_native_smoke(self) -> None:
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
            write_voice_readiness_artifact(record, artifact_path=artifact_path)
            report = build_voice_readiness_gate_report(
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={
                    "JARVIS_TTS_MACOS_NATIVE": "1",
                    "DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer",
                },
            )

        self.assertTrue(report.gate_ready)
        self.assertEqual(report.native_tts_status, "ready")
        self.assertEqual(report.native_tts_active_backend, "macos_native")
        self.assertEqual(
            report.native_tts_command,
            "env DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer python3 cli.py",
        )
        self.assertEqual(
            report.native_tts_detail_lines,
            ["developer dir override: /Applications/Xcode.app/Contents/Developer"],
        )
        self.assertEqual(report.latest_capture_status, "not_recorded")

    def test_gate_surfaces_latest_live_capture_permission_blocker(self) -> None:
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
            report = build_voice_readiness_gate_report(
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={
                    "JARVIS_TTS_MACOS_NATIVE": "1",
                    "DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer",
                },
            )

        self.assertFalse(report.gate_ready)
        self.assertEqual(report.latest_capture_status, "blocked")
        self.assertEqual(
            report.latest_capture_reason,
            "PERMISSION_DENIED: Speech recognition access was denied.",
        )
        self.assertEqual(
            report.latest_capture_command,
            "env DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer python3 cli.py",
        )
        self.assertEqual(report.capture_preflight_status, "clear")
        self.assertEqual(report.next_step_kind, "complete_manual_voice_verification")
        self.assertNotIn("live voice capture is currently blocked", ", ".join(report.blockers))

    def test_format_mentions_native_tts_block_details(self) -> None:
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
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )
            write_voice_readiness_artifact(record, artifact_path=artifact_path)
            report = build_voice_readiness_gate_report(
                artifact_path=artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "1"},
            )

        rendered = format_voice_readiness_gate_report(report)

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
                elapsed_seconds=0.1,
                error=VoiceInputError(
                    "PERMISSION_DENIED",
                    "Speech recognition access was denied.",
                    hint="Check macOS Settings -> Privacy & Security -> Microphone / Speech Recognition.",
                ),
            )
            write_voice_telemetry_artifact(telemetry.snapshot(), artifact_path=telemetry_artifact_path)
            report = build_voice_readiness_gate_report(
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )

        rendered = format_voice_readiness_gate_report(report)

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

    def test_gate_preflights_live_capture_permissions_without_telemetry(self) -> None:
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
            report = build_voice_readiness_gate_report(
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )

        self.assertFalse(report.gate_ready)
        self.assertEqual(report.capture_preflight_status, "blocked")
        self.assertEqual(report.latest_capture_status, "not_recorded")
        self.assertEqual(report.next_step_kind, "grant_live_voice_permissions")
        self.assertEqual(
            report.next_step_reason,
            "allow macOS Speech Recognition and Microphone access for the current voice capture helper, then rerun live voice smoke",
        )
        self.assertIn(
            "voice capture helper bundle id: com.jarvis.voice.capture.helper",
            report.next_step_detail_lines,
        )
        self.assertIn(
            "live voice capture is currently blocked (PERMISSION_PROMPT_REQUIRED: Speech recognition permission has not been requested yet.)",
            report.blockers,
        )

    def test_gate_uses_developer_dir_override_in_native_follow_up_commands(self) -> None:
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
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )
            write_voice_readiness_artifact(record, artifact_path=artifact_path)
            report = build_voice_readiness_gate_report(
                artifact_path=artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "1"},
            )

        self.assertEqual(
            report.next_step_command,
            "env DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcrun swiftc -typecheck voice/native_hosts/macos_tts_host.swift",
        )
        self.assertIn(
            "current env override: DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer; if that override is intentional, keep using it on the next typecheck and CLI smoke, otherwise fix or unset it before retrying",
            report.next_step_detail_lines,
        )

    def test_gate_reports_timeout_native_tts_opt_in_blockers(self) -> None:
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
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )
            write_voice_readiness_artifact(record, artifact_path=artifact_path)
            report = build_voice_readiness_gate_report(
                artifact_path=artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "1"},
            )

        self.assertFalse(report.gate_ready)
        self.assertEqual(report.next_step_kind, "resolve_native_tts_host_timeout")
        self.assertEqual(
            report.next_step_reason,
            "inspect the current native macOS toolchain selection and rerun the native doctor helper before retrying smoke",
        )
        self.assertEqual(
            report.next_step_command,
            "printf 'voice tts doctor\\nquit\\n' | python3 cli.py",
        )
        self.assertEqual(
            report.next_step_detail_lines,
            [
                "confirm active developer dir with: xcode-select -p",
                "if the native host keeps timing out, compare the active developer dir and active swiftc details above, then rerun the native doctor helper before retrying smoke",
            ],
        )

    def test_gate_keeps_override_detail_for_compile_failed_native_blocker(self) -> None:
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
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )
            write_voice_readiness_artifact(record, artifact_path=artifact_path)
            report = build_voice_readiness_gate_report(
                artifact_path=artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "1"},
            )

        self.assertEqual(report.next_step_kind, "resolve_native_tts_compile_failure")
        self.assertEqual(
            report.next_step_command,
            "env DEVELOPER_DIR=/tmp/jarvis-invalid-developer-dir xcrun swiftc -typecheck voice/native_hosts/macos_tts_host.swift",
        )
        self.assertEqual(
            report.next_step_detail_lines,
            [
                "current env override: DEVELOPER_DIR=/tmp/jarvis-invalid-developer-dir; if that override is intentional, keep using it on the next typecheck and CLI smoke, otherwise fix or unset it before retrying",
            ],
        )

    def test_format_mentions_timeout_native_tts_block_details(self) -> None:
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
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )
            write_voice_readiness_artifact(record, artifact_path=artifact_path)
            report = build_voice_readiness_gate_report(
                artifact_path=artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "1"},
            )

        rendered = format_voice_readiness_gate_report(report)

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

    def test_gate_shell_wrapper_reports_blocked_for_missing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"
            completed = subprocess.run(
                [
                    "zsh",
                    "scripts/run_voice_readiness_gate.sh",
                    "--artifact-path",
                    str(artifact_path),
                    "--telemetry-artifact-path",
                    str(telemetry_artifact_path),
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

        self.assertEqual(completed.returncode, 1)
        self.assertIn("JARVIS Voice Readiness Gate", completed.stdout)
        self.assertIn("gate: blocked", completed.stdout)

    def test_gate_shell_wrapper_reports_ready_for_recorded_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            telemetry_artifact_path = Path(tmpdir) / "voice_telemetry.json"
            record = build_voice_readiness_record(
                manual_verified=True,
                artifact_path=artifact_path,
                telemetry_artifact_path=telemetry_artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "0"},
            )
            write_voice_readiness_artifact(record, artifact_path=artifact_path)

            completed = subprocess.run(
                [
                    "zsh",
                    "scripts/run_voice_readiness_gate.sh",
                    "--artifact-path",
                    str(artifact_path),
                    "--telemetry-artifact-path",
                    str(telemetry_artifact_path),
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
        self.assertIn("JARVIS Voice Readiness Gate", completed.stdout)
        self.assertIn("gate: ready", completed.stdout)

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
