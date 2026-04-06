"""Offline voice rollout gate helper tests."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_gate_is_blocked_until_voice_readiness_artifact_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            report = build_voice_readiness_gate_report(artifact_path=artifact_path)

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
            record = build_voice_readiness_record(
                manual_verified=True,
                artifact_path=artifact_path,
            )
            write_voice_readiness_artifact(record, artifact_path=artifact_path)

            report = build_voice_readiness_gate_report(artifact_path=artifact_path)

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
                "make the selected developer dir match the Xcode or Command Line Tools bundle behind the sdk toolchain detail above, then rerun the native typecheck",
            ],
        )
        self.assertIn(
            "native macOS TTS smoke is blocked (HOST_SDK_MISMATCH: Native macOS Swift compiler and SDK appear mismatched; align Xcode and Command Line Tools.)",
            report.blockers,
        )

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
            )
            write_voice_readiness_artifact(record, artifact_path=artifact_path)
            report = build_voice_readiness_gate_report(
                artifact_path=artifact_path,
                environ={"JARVIS_TTS_MACOS_NATIVE": "1"},
            )

        rendered = format_voice_readiness_gate_report(report)

        self.assertIn("native tts requested in current env: yes", rendered)
        self.assertIn("native tts smoke status: blocked", rendered)
        self.assertIn("native tts active backend: macos_say_legacy", rendered)
        self.assertIn(
            "native tts reason: HOST_SDK_MISMATCH: Native macOS Swift compiler and SDK appear mismatched; align Xcode and Command Line Tools.",
            rendered,
        )
        self.assertIn("native tts command: xcrun swiftc -typecheck voice/native_hosts/macos_tts_host.swift", rendered)
        self.assertIn("native tts detail: sdk toolchain: Apple Swift version 6.2 effective-5.10", rendered)
        self.assertIn("native tts detail: active compiler: Apple Swift version 6.2.4 effective-5.10", rendered)
        self.assertIn("next step: resolve_native_tts_sdk_mismatch", rendered)
        self.assertIn(
            "next step reason: align local Xcode and Command Line Tools so the active Swift compiler matches the installed SDK before native smoke",
            rendered,
        )
        self.assertIn("next step detail: confirm active developer dir with: xcode-select -p", rendered)
        self.assertIn(
            "next step detail: make the selected developer dir match the Xcode or Command Line Tools bundle behind the sdk toolchain detail above, then rerun the native typecheck",
            rendered,
        )

    def test_gate_shell_wrapper_reports_blocked_for_missing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            completed = subprocess.run(
                [
                    "zsh",
                    "scripts/run_voice_readiness_gate.sh",
                    "--artifact-path",
                    str(artifact_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
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
            record = build_voice_readiness_record(
                manual_verified=True,
                artifact_path=artifact_path,
            )
            write_voice_readiness_artifact(record, artifact_path=artifact_path)

            completed = subprocess.run(
                [
                    "zsh",
                    "scripts/run_voice_readiness_gate.sh",
                    "--artifact-path",
                    str(artifact_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
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
