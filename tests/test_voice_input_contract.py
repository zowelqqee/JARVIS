"""Deterministic contract checks for voice input error normalization."""

from __future__ import annotations

import os
import plistlib
import tempfile
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

    def test_microphone_unavailable_keeps_structured_hint(self) -> None:
        error = voice_input._voice_error_from_result(1, "MICROPHONE_UNAVAILABLE|Microphone access is unavailable.")

        self.assertEqual(error.code, "MICROPHONE_UNAVAILABLE")
        self.assertIn("microphone", str(error).lower())
        self.assertIsNotNone(error.hint)
        self.assertIn("Privacy & Security", error.hint or "")

    def test_permission_prompt_required_keeps_structured_hint(self) -> None:
        error = voice_input._voice_error_from_result(
            1,
            "PERMISSION_PROMPT_REQUIRED|Speech recognition permission has not been requested yet.",
        )

        self.assertEqual(error.code, "PERMISSION_PROMPT_REQUIRED")
        self.assertIn("not been requested", str(error).lower())
        self.assertIsNotNone(error.hint)
        self.assertIn("Privacy & Security", error.hint or "")

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
                CompletedProcess(args=[str(voice_input._HELPER_BINARY), "2.0"], returncode=-6, stdout="", stderr=""),
                CompletedProcess(
                    args=[str(voice_input._HELPER_BINARY), "2.0"],
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

    def test_capture_voice_input_uses_russian_then_english_locale_chain_by_default(self) -> None:
        with patch.object(voice_input.sys, "platform", "darwin"), patch(
            "input.voice_input._ensure_helper_binary"
        ), patch(
            "input.voice_input.subprocess.run",
            return_value=CompletedProcess(
                args=[str(voice_input._HELPER_BINARY), "2.0", "ru-RU,en-US"],
                returncode=0,
                stdout="привет\n",
                stderr="",
            ),
        ) as run_mock:
            text = voice_input.capture_voice_input(timeout_seconds=2.0)

        self.assertEqual(text, "привет")
        command = run_mock.call_args.args[0]
        self.assertEqual(command[:3], [str(voice_input._HELPER_BINARY), "2.0", "ru-RU,en-US"])

    def test_capture_voice_input_respects_locale_override_env(self) -> None:
        with patch.object(voice_input.sys, "platform", "darwin"), patch(
            "input.voice_input._ensure_helper_binary"
        ), patch.dict("os.environ", {voice_input._VOICE_LOCALES_ENV: "en-US,ru-RU"}, clear=False), patch(
            "input.voice_input.subprocess.run",
            return_value=CompletedProcess(
                args=[str(voice_input._HELPER_BINARY), "2.0", "en-US,ru-RU"],
                returncode=0,
                stdout="hello\n",
                stderr="",
            ),
        ) as run_mock:
            text = voice_input.capture_voice_input(timeout_seconds=2.0)

        self.assertEqual(text, "hello")
        command = run_mock.call_args.args[0]
        self.assertEqual(command[:3], [str(voice_input._HELPER_BINARY), "2.0", "en-US,ru-RU"])

    def test_capture_voice_input_does_not_retry_on_structured_permission_denied(self) -> None:
        with patch.object(voice_input.sys, "platform", "darwin"), patch(
            "input.voice_input._ensure_helper_binary"
        ) as ensure_mock, patch(
            "input.voice_input.subprocess.run",
            return_value=CompletedProcess(
                args=[str(voice_input._HELPER_BINARY), "2.0"],
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

    def test_probe_voice_input_permissions_runs_helper_in_probe_mode(self) -> None:
        with patch.object(voice_input.sys, "platform", "darwin"), patch(
            "input.voice_input._ensure_helper_binary"
        ) as ensure_mock, patch(
            "input.voice_input.subprocess.run",
            return_value=CompletedProcess(
                args=[str(voice_input._HELPER_BINARY), "--probe-permissions"],
                returncode=0,
                stdout="VOICE_CAPTURE_PERMISSIONS_OK\n",
                stderr="",
            ),
        ) as run_mock:
            error = voice_input.probe_voice_input_permissions()

        self.assertIsNone(error)
        ensure_mock.assert_called_once_with()
        self.assertEqual(
            run_mock.call_args.args[0],
            [str(voice_input._HELPER_BINARY), voice_input._VOICE_PERMISSION_PROBE_ARG],
        )

    def test_probe_voice_input_permissions_maps_prompt_required_without_retry(self) -> None:
        with patch.object(voice_input.sys, "platform", "darwin"), patch(
            "input.voice_input._ensure_helper_binary"
        ) as ensure_mock, patch(
            "input.voice_input.subprocess.run",
            return_value=CompletedProcess(
                args=[str(voice_input._HELPER_BINARY), "--probe-permissions"],
                returncode=1,
                stdout="",
                stderr="PERMISSION_PROMPT_REQUIRED|Speech recognition permission has not been requested yet.",
            ),
        ):
            error = voice_input.probe_voice_input_permissions()

        self.assertIsNotNone(error)
        assert error is not None
        self.assertEqual(error.code, "PERMISSION_PROMPT_REQUIRED")
        ensure_mock.assert_called_once_with()

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

    def test_permission_target_details_expose_stable_bundle_id_and_runtime_dir(self) -> None:
        details = voice_input.voice_capture_permission_target_details()

        self.assertIn("voice capture helper bundle id: com.jarvis.voice.capture.helper", details)
        self.assertIn(
            f"voice capture helper runtime dir: {voice_input._HELPER_RUNTIME_DIR}",
            details,
        )
        self.assertIn(
            "privacy list name hint: jarvis_macos_voice_capture / com.jarvis.voice.capture.helper",
            details,
        )

    def test_voice_helper_primary_launch_target_stays_repo_local_raw_binary(self) -> None:
        with patch.object(voice_input.sys, "platform", "darwin"), patch(
            "input.voice_input._ensure_helper_binary"
        ), patch(
            "input.voice_input.subprocess.run",
            return_value=CompletedProcess(
                args=[str(voice_input._HELPER_BINARY), "2.0", "ru-RU,en-US"],
                returncode=0,
                stdout="привет\n",
                stderr="",
            ),
        ) as run_mock:
            voice_input.capture_voice_input(timeout_seconds=2.0)

        self.assertEqual(
            run_mock.call_args.args[0][0],
            str(voice_input._HELPER_BINARY),
        )

    def test_run_helper_via_open_bundle_uses_open_a_and_returns_captured_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "voice_out.txt")
            error_path = os.path.join(tmpdir, "voice_err.txt")
            output_fd = os.open(output_path, os.O_CREAT | os.O_RDWR, 0o600)
            error_fd = os.open(error_path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                with patch(
                    "input.voice_input.tempfile.mkstemp",
                    side_effect=[(output_fd, output_path), (error_fd, error_path)],
                ), patch(
                    "input.voice_input.subprocess.run",
                    return_value=CompletedProcess(args=["open"], returncode=0, stdout="", stderr=""),
                ) as run_mock:
                    os.write(output_fd, b"VOICE_CAPTURE_PERMISSIONS_OK\n")
                    os.lseek(output_fd, 0, os.SEEK_SET)
                    result = voice_input._run_helper_via_open_bundle(2.0, ("ru-RU", "en-US"))
            finally:
                try:
                    os.close(output_fd)
                except OSError:
                    pass
                try:
                    os.close(error_fd)
                except OSError:
                    pass

        assert result is not None
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "VOICE_CAPTURE_PERMISSIONS_OK")
        self.assertEqual(
            run_mock.call_args.args[0][:5],
            ["open", "-W", "-n", "-a", str(voice_input._HELPER_APP_BUNDLE)],
        )


if __name__ == "__main__":
    unittest.main()
