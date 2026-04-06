"""Offline voice rollout gate helper tests."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from voice.session import VoiceTurn
from voice.gate import (
    build_voice_readiness_gate_report,
    format_voice_readiness_gate_report,
)
from voice.readiness import build_voice_readiness_record, write_voice_readiness_artifact
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


if __name__ == "__main__":
    unittest.main()
