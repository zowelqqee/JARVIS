"""Deterministic contract checks for voice input error normalization."""

from __future__ import annotations

import unittest

from input import voice_input


class VoiceInputContractTests(unittest.TestCase):
    """Lock voice helper failure mapping used by the CLI."""

    def test_negative_exit_code_maps_to_voice_helper_crash(self) -> None:
        error = voice_input._voice_error_from_result(-6, "")

        self.assertEqual(error.code, "VOICE_HELPER_CRASH")
        self.assertIn("SIGABRT", str(error))
        self.assertIsNotNone(error.hint)
        self.assertIn("Privacy & Security", error.hint or "")

    def test_permission_denied_keeps_structured_hint(self) -> None:
        error = voice_input._voice_error_from_result(1, "PERMISSION_DENIED|Speech recognition access was denied.")

        self.assertEqual(error.code, "PERMISSION_DENIED")
        self.assertIn("denied", str(error).lower())
        self.assertIsNotNone(error.hint)
        self.assertIn("Privacy & Security", error.hint or "")

    def test_unknown_positive_exit_without_detail_reports_exit_code(self) -> None:
        error = voice_input._voice_error_from_result(7, "")

        self.assertEqual(error.code, "RECOGNITION_FAILED")
        self.assertIn("exit code 7", str(error))
        self.assertIsNone(error.hint)


if __name__ == "__main__":
    unittest.main()
