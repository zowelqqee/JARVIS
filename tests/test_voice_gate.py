"""Offline voice rollout gate helper tests."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from voice.gate import (
    build_voice_readiness_gate_report,
    format_voice_readiness_gate_report,
)
from voice.readiness import build_voice_readiness_record, write_voice_readiness_artifact


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
        self.assertEqual(report.next_step_kind, "voice_readiness_artifact_already_recorded")
        self.assertEqual(report.blockers, [])

    def test_format_mentions_gate_status_and_next_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            report = build_voice_readiness_gate_report(artifact_path=artifact_path)

        rendered = format_voice_readiness_gate_report(report)

        self.assertIn("JARVIS Voice Readiness Gate", rendered)
        self.assertIn("gate: blocked", rendered)
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
