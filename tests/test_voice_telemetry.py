"""Unit coverage for in-memory voice telemetry metrics."""

from __future__ import annotations

import tempfile
import unittest
import subprocess
from types import SimpleNamespace
from pathlib import Path

from input.voice_input import VoiceInputError
from voice.session import VoiceTurn
from voice.telemetry import (
    VoiceTelemetryCollector,
    format_voice_telemetry_artifact_summary,
    format_voice_telemetry_snapshot,
    load_voice_telemetry_artifact,
    load_voice_telemetry_snapshot,
    write_voice_telemetry_artifact,
)
from voice.tts_provider import SpeechUtterance, TTSResult


class VoiceTelemetryTests(unittest.TestCase):
    """Keep current voice metrics stable while the voice shell grows."""

    def test_snapshot_tracks_capture_dispatch_follow_up_and_tts_metrics(self) -> None:
        collector = VoiceTelemetryCollector()
        first_turn = VoiceTurn(
            raw_transcript="Джарвис, закрой телеграм",
            normalized_transcript="close telegram",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
            lifecycle_state="awaiting_follow_up",
            follow_up_reason="confirmation",
            follow_up_window_seconds=8.0,
        )
        follow_up_turn = VoiceTurn(
            raw_transcript="Да",
            normalized_transcript="confirm",
            detected_locale="ru-RU",
            locale_hint="ru-RU",
        )

        collector.record_capture(
            phase="initial",
            elapsed_seconds=0.4,
            voice_turn=first_turn,
        )
        collector.record_capture(
            phase="follow_up",
            elapsed_seconds=0.2,
            error=VoiceInputError("EMPTY_RECOGNITION", "No speech was recognized. Try again."),
        )
        collector.record_dispatch(
            first_turn,
            SimpleNamespace(
                interaction=SimpleNamespace(
                    interaction_result=SimpleNamespace(interaction_mode="command"),
                    follow_up_reason="confirmation",
                ),
                voice_turn=first_turn,
            ),
        )
        collector.record_dispatch(
            follow_up_turn,
            SimpleNamespace(
                interaction=SimpleNamespace(
                    interaction_result=SimpleNamespace(interaction_mode="clarification"),
                    follow_up_reason="clarification",
                ),
                voice_turn=follow_up_turn,
            ),
        )
        collector.record_follow_up_opened(first_turn)
        collector.record_follow_up_completed(first_turn, follow_up_turn)
        collector.record_tts_result(
            SpeechUtterance(text="Закрыть Telegram?", locale="ru-RU"),
            TTSResult(ok=False, attempted=True, error_code="TTS_FAILED"),
        )

        snapshot = collector.snapshot()

        self.assertEqual(snapshot.capture_attempts, 2)
        self.assertEqual(snapshot.dispatch_count, 2)
        self.assertEqual(snapshot.tts_attempts, 1)
        self.assertAlmostEqual(snapshot.recognition_latency_ms or 0.0, 300.0)
        self.assertAlmostEqual(snapshot.empty_recognition_rate, 0.5)
        self.assertAlmostEqual(snapshot.clarification_rate, 0.5)
        self.assertAlmostEqual(snapshot.confirmation_completion_rate, 1.0)
        self.assertAlmostEqual(snapshot.retry_rate, 0.5)
        self.assertAlmostEqual(snapshot.tts_failure_rate, 1.0)
        self.assertAlmostEqual(snapshot.average_spoken_response_length, float(len("Закрыть Telegram?")))

    def test_permission_denied_does_not_count_as_retryable_failure(self) -> None:
        collector = VoiceTelemetryCollector()

        collector.record_capture(
            phase="initial",
            elapsed_seconds=0.1,
            error=VoiceInputError("PERMISSION_DENIED", "Speech recognition access was denied."),
        )

        snapshot = collector.snapshot()

        self.assertEqual(snapshot.capture_attempts, 1)
        self.assertAlmostEqual(snapshot.retry_rate, 0.0)
        self.assertAlmostEqual(snapshot.empty_recognition_rate, 0.0)

    def test_skipped_tts_attempt_does_not_affect_failure_rate(self) -> None:
        collector = VoiceTelemetryCollector()

        collector.record_tts_result(
            SpeechUtterance(text="", locale="en-US"),
            TTSResult(ok=True, attempted=False),
        )

        snapshot = collector.snapshot()

        self.assertEqual(snapshot.tts_attempts, 0)
        self.assertAlmostEqual(snapshot.tts_failure_rate, 0.0)
        self.assertAlmostEqual(snapshot.average_spoken_response_length, 0.0)

    def test_clear_resets_recorded_events(self) -> None:
        collector = VoiceTelemetryCollector()
        collector.record_capture(
            phase="initial",
            elapsed_seconds=0.2,
            error=VoiceInputError("EMPTY_RECOGNITION", "No speech was recognized. Try again."),
        )

        collector.clear()
        snapshot = collector.snapshot()

        self.assertEqual(snapshot.capture_attempts, 0)
        self.assertEqual(snapshot.dispatch_count, 0)
        self.assertEqual(snapshot.tts_attempts, 0)
        self.assertEqual(collector.events, ())

    def test_format_voice_telemetry_snapshot_mentions_rates_and_counts(self) -> None:
        collector = VoiceTelemetryCollector()
        collector.record_capture(
            phase="initial",
            elapsed_seconds=0.3,
            error=VoiceInputError("EMPTY_RECOGNITION", "No speech was recognized. Try again."),
        )

        rendered = format_voice_telemetry_snapshot(collector.snapshot())

        self.assertIn("JARVIS Voice Telemetry", rendered)
        self.assertIn("capture attempts: 1", rendered)
        self.assertIn("empty recognition rate: 100.0%", rendered)
        self.assertIn("tts attempts: 0", rendered)

    def test_snapshot_can_be_written_and_reloaded_as_artifact(self) -> None:
        collector = VoiceTelemetryCollector()
        collector.record_capture(
            phase="initial",
            elapsed_seconds=0.25,
            error=VoiceInputError("EMPTY_RECOGNITION", "No speech was recognized. Try again."),
        )
        snapshot = collector.snapshot()

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_telemetry.json"
            written_path = write_voice_telemetry_artifact(snapshot, artifact_path=artifact_path)
            loaded_path, payload, error = load_voice_telemetry_artifact(artifact_path=artifact_path)

        self.assertEqual(written_path, artifact_path)
        self.assertEqual(loaded_path, artifact_path)
        self.assertIsNone(error)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["runner"], "voice.telemetry")
        self.assertEqual(payload["snapshot"]["capture_attempts"], 1)
        self.assertEqual(payload["snapshot"]["tts_attempts"], 0)

    def test_saved_artifact_summary_reports_missing_snapshot_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_telemetry.json"
            (
                loaded_path,
                artifact_status,
                artifact_created_at,
                snapshot,
                artifact_error,
            ) = load_voice_telemetry_snapshot(artifact_path=artifact_path)

        rendered = format_voice_telemetry_artifact_summary(
            artifact_path=loaded_path,
            artifact_status=artifact_status,
            artifact_created_at=artifact_created_at,
            snapshot=snapshot,
            artifact_error=artifact_error,
        )

        self.assertEqual(loaded_path, artifact_path)
        self.assertEqual(artifact_status, "missing")
        self.assertIsNone(snapshot)
        self.assertIsNone(artifact_error)
        self.assertIn("JARVIS Voice Telemetry Artifact", rendered)
        self.assertIn("artifact status: missing", rendered)
        self.assertIn("snapshot: n/a", rendered)

    def test_module_can_render_explicit_saved_artifact_path(self) -> None:
        collector = VoiceTelemetryCollector()
        collector.record_capture(
            phase="initial",
            elapsed_seconds=0.25,
            error=VoiceInputError("EMPTY_RECOGNITION", "No speech was recognized. Try again."),
        )
        snapshot = collector.snapshot()

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "voice_telemetry.json"
            write_voice_telemetry_artifact(snapshot, artifact_path=artifact_path)
            completed = subprocess.run(
                [
                    "python3",
                    "-m",
                    "voice.telemetry",
                    "--artifact-path",
                    str(artifact_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("JARVIS Voice Telemetry Artifact", completed.stdout)
        self.assertIn(f"artifact path: {artifact_path}", completed.stdout)
        self.assertIn("artifact status: ready", completed.stdout)
        self.assertIn("capture attempts: 1", completed.stdout)


if __name__ == "__main__":
    unittest.main()
