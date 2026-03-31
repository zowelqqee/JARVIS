"""Unit coverage for current-session voice status helpers."""

from __future__ import annotations

import unittest

from voice.status import build_voice_session_status, format_voice_session_status
from voice.telemetry import VoiceTelemetryCollector


class VoiceStatusTests(unittest.TestCase):
    """Keep the operator-facing current-session voice status stable."""

    def test_build_voice_session_status_combines_mode_and_telemetry(self) -> None:
        telemetry = VoiceTelemetryCollector()
        telemetry.record_follow_up_loop(completed_turns=2, limit_hit=True)
        telemetry.record_follow_up_loop(completed_turns=1, limit_hit=False)

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


if __name__ == "__main__":
    unittest.main()
