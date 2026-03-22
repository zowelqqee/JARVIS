"""Deterministic contract checks for voice input error normalization."""

from __future__ import annotations

import plistlib
import unittest
from subprocess import CompletedProcess
from unittest.mock import patch

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

    def test_permission_denied_with_noisy_prefix_keeps_structured_mapping(self) -> None:
        raw_message = (
            "2026-03-22 helper runtime warning from LaunchServices\n"
            "PERMISSION_DENIED|Speech recognition access was denied."
        )

        error = voice_input._voice_error_from_result(1, raw_message)

        self.assertEqual(error.code, "PERMISSION_DENIED")
        self.assertIn("denied", str(error).lower())
        self.assertIsNotNone(error.hint)

    def test_unknown_positive_exit_without_detail_reports_exit_code(self) -> None:
        error = voice_input._voice_error_from_result(7, "")

        self.assertEqual(error.code, "RECOGNITION_FAILED")
        self.assertIn("exit code 7", str(error))
        self.assertIsNone(error.hint)

    def test_capture_voice_input_rebuilds_and_retries_after_helper_crash(self) -> None:
        with patch.object(voice_input.sys, "platform", "darwin"), patch(
            "input.voice_input._ensure_helper_binary"
        ) as ensure_mock, patch(
            "input.voice_input.subprocess.run",
            side_effect=[
                CompletedProcess(args=["/tmp/jarvis_macos_voice_capture", "2.0"], returncode=-6, stdout="", stderr=""),
                CompletedProcess(
                    args=["/tmp/jarvis_macos_voice_capture", "2.0"],
                    returncode=0,
                    stdout="open browser\n",
                    stderr="",
                ),
            ],
        ):
            text = voice_input.capture_voice_input(timeout_seconds=2.0)

        self.assertEqual(text, "open browser")
        self.assertEqual(ensure_mock.call_count, 2)
        self.assertEqual(ensure_mock.call_args_list[0].args, ())
        self.assertEqual(ensure_mock.call_args_list[0].kwargs, {})
        self.assertEqual(ensure_mock.call_args_list[1].kwargs, {"force_rebuild": True})

    def test_capture_voice_input_does_not_retry_on_structured_permission_denied(self) -> None:
        with patch.object(voice_input.sys, "platform", "darwin"), patch(
            "input.voice_input._ensure_helper_binary"
        ) as ensure_mock, patch(
            "input.voice_input.subprocess.run",
            return_value=CompletedProcess(
                args=["/tmp/jarvis_macos_voice_capture", "2.0"],
                returncode=1,
                stdout="",
                stderr="PERMISSION_DENIED|Speech recognition access was denied.",
            ),
        ):
            with self.assertRaises(voice_input.VoiceInputError) as context:
                voice_input.capture_voice_input(timeout_seconds=2.0)

        self.assertEqual(getattr(context.exception, "code", ""), "PERMISSION_DENIED")
        self.assertEqual(ensure_mock.call_count, 1)
        self.assertEqual(ensure_mock.call_args.kwargs, {})

    def test_codesign_command_sets_stable_identifier(self) -> None:
        with patch("input.voice_input.subprocess.run", return_value=CompletedProcess(args=[], returncode=0)) as run_mock:
            voice_input._codesign_helper_binary()

        command = run_mock.call_args.args[0]
        self.assertIn("--identifier", command)
        self.assertIn("com.jarvis.voice.capture.helper", command)

    def test_voice_helper_plist_contains_required_bundle_and_privacy_keys(self) -> None:
        with voice_input._HELPER_INFO_PLIST.open("rb") as handle:
            data = plistlib.load(handle)

        self.assertEqual(data.get("CFBundleExecutable"), "jarvis_macos_voice_capture")
        self.assertEqual(data.get("CFBundleIdentifier"), "com.jarvis.voice.capture.helper")
        self.assertEqual(data.get("CFBundlePackageType"), "APPL")
        self.assertTrue(bool(data.get("NSMicrophoneUsageDescription")))
        self.assertTrue(bool(data.get("NSSpeechRecognitionUsageDescription")))


if __name__ == "__main__":
    unittest.main()
