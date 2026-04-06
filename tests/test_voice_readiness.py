"""Offline voice-readiness helper tests."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from voice.session import VoiceTurn
from voice.readiness import (
    build_voice_readiness_record,
    format_voice_readiness_record,
    load_voice_readiness_artifact,
    write_voice_readiness_artifact,
)
from voice.telemetry import build_default_voice_telemetry, write_voice_telemetry_artifact


class VoiceReadinessTests(unittest.TestCase):
    """Keep the staged voice-rollout helper explicit and safe by default."""

    def test_build_record_is_blocked_until_manual_verification_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"

            record = build_voice_readiness_record(artifact_path=artifact_path)

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
            record = build_voice_readiness_record(
                manual_verified=True,
                notes="manual microphone check passed",
                artifact_path=artifact_path,
            )

            written_path = write_voice_readiness_artifact(record, artifact_path=artifact_path)
            loaded_path, payload, error = load_voice_readiness_artifact(artifact_path)
            reloaded_record = build_voice_readiness_record(artifact_path=artifact_path)

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

    def test_module_can_write_artifact_to_explicit_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_readiness.json"
            completed = subprocess.run(
                [
                    "python3",
                    "-m",
                    "voice.readiness",
                    "--artifact-path",
                    str(artifact_path),
                    "--manual-verified",
                    "--write-artifact",
                ],
                cwd=Path(__file__).resolve().parents[1],
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
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertIn(f"telemetry artifact path: {telemetry_artifact_path}", completed.stdout)
        self.assertIn("telemetry artifact status: missing", completed.stdout)


if __name__ == "__main__":
    unittest.main()
