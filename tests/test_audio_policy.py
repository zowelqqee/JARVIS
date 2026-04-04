"""Unit coverage for the tiny half-duplex audio policy."""

from __future__ import annotations

import unittest

from voice.audio_policy import AudioPolicyError, HalfDuplexAudioPolicy


class AudioPolicyTests(unittest.TestCase):
    """Keep the current voice layer from overlapping listen and speak phases."""

    def test_capture_phase_returns_to_idle_after_exit(self) -> None:
        policy = HalfDuplexAudioPolicy()

        with policy.capture_phase():
            self.assertEqual(policy.current_state, "listening")

        self.assertEqual(policy.current_state, "idle")

    def test_speaking_phase_returns_to_idle_after_exit(self) -> None:
        policy = HalfDuplexAudioPolicy()

        with policy.speaking_phase():
            self.assertEqual(policy.current_state, "speaking")

        self.assertEqual(policy.current_state, "idle")

    def test_capture_phase_is_blocked_while_speaking(self) -> None:
        policy = HalfDuplexAudioPolicy()

        with policy.speaking_phase():
            with self.assertRaises(AudioPolicyError):
                with policy.capture_phase():
                    self.fail("capture phase should not start while speaking")

    def test_stop_speaking_for_capture_returns_to_idle_when_interruption_succeeds(self) -> None:
        policy = HalfDuplexAudioPolicy()

        with policy.speaking_phase():
            interrupted = policy.stop_speaking_for_capture(stop_active_speech=lambda: True)
            self.assertTrue(interrupted)
            self.assertEqual(policy.current_state, "idle")
            with policy.capture_phase():
                self.assertEqual(policy.current_state, "listening")

        self.assertEqual(policy.current_state, "idle")

    def test_stop_speaking_for_capture_raises_when_active_speech_cannot_be_interrupted(self) -> None:
        policy = HalfDuplexAudioPolicy()

        with policy.speaking_phase():
            with self.assertRaises(AudioPolicyError):
                policy.stop_speaking_for_capture(stop_active_speech=lambda: False)


if __name__ == "__main__":
    unittest.main()
