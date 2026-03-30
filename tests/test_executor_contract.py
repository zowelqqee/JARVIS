"""Deterministic executor failure-shape contract tests for macOS MVP behavior."""

from __future__ import annotations

import unittest
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import patch

import executor.desktop_executor as desktop_executor
from action_result import ActionError
from step import Step, StepAction
from target import Target, TargetType


class ExecutorContractTests(unittest.TestCase):
    """Lock executor error-code routing and boundary behavior without desktop side effects."""

    def test_requires_confirmation_step_is_blocked(self) -> None:
        step = Step(
            id="step_1",
            action=StepAction.OPEN_APP,
            target=Target(type=TargetType.APPLICATION, name="Telegram"),
            requires_confirmation=True,
        )

        result = desktop_executor.execute_step(step)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "CONFIRMATION_REQUIRED")

    def test_open_website_invalid_url_fails_with_invalid_url(self) -> None:
        step = Step(
            id="step_1",
            action=StepAction.OPEN_WEBSITE,
            target=Target(type=TargetType.BROWSER, name="Safari"),
            parameters={"url": "example.com"},
        )

        with patch.object(desktop_executor.sys, "platform", "darwin"):
            result = desktop_executor.execute_step(step)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "INVALID_URL")

    def test_focus_app_not_running_returns_app_not_running(self) -> None:
        step = Step(
            id="step_1",
            action=StepAction.FOCUS_APP,
            target=Target(type=TargetType.APPLICATION, name="Safari"),
        )

        with patch.object(desktop_executor.sys, "platform", "darwin"), patch(
            "executor.desktop_executor._is_app_running",
            return_value=False,
        ):
            result = desktop_executor.execute_step(step)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "APP_NOT_RUNNING")

    def test_close_app_not_running_returns_app_not_running(self) -> None:
        step = Step(
            id="step_1",
            action=StepAction.CLOSE_APP,
            target=Target(type=TargetType.APPLICATION, name="Safari"),
        )

        with patch.object(desktop_executor.sys, "platform", "darwin"), patch(
            "executor.desktop_executor._is_app_running",
            return_value=False,
        ):
            result = desktop_executor.execute_step(step)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "APP_NOT_RUNNING")

    def test_open_app_permission_denied_maps_to_permission_denied(self) -> None:
        step = Step(
            id="step_1",
            action=StepAction.OPEN_APP,
            target=Target(type=TargetType.APPLICATION, name="Safari"),
        )

        with patch.object(desktop_executor.sys, "platform", "darwin"), patch(
            "executor.desktop_executor._run_command",
            return_value=CompletedProcess(
                args=["open", "-a", "Safari"],
                returncode=1,
                stdout="",
                stderr="Operation not permitted",
            ),
        ):
            result = desktop_executor.execute_step(step)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "PERMISSION_DENIED")

    def test_list_windows_permission_denied_propagates(self) -> None:
        step = Step(
            id="step_1",
            action=StepAction.LIST_WINDOWS,
            target=Target(type=TargetType.WINDOW, name="windows"),
        )

        with patch.object(desktop_executor.sys, "platform", "darwin"), patch(
            "executor.desktop_executor._list_visible_windows",
            return_value=([], ActionError(code="PERMISSION_DENIED", message="Access denied")),
        ):
            result = desktop_executor.execute_step(step)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "PERMISSION_DENIED")

    def test_list_windows_unknown_error_code_normalizes_to_execution_failed(self) -> None:
        step = Step(
            id="step_1",
            action=StepAction.LIST_WINDOWS,
            target=Target(type=TargetType.WINDOW, name="windows"),
        )

        with patch.object(desktop_executor.sys, "platform", "darwin"), patch(
            "executor.desktop_executor._list_visible_windows",
            return_value=([], ActionError(code="RANDOM_ERROR", message="Unexpected adapter failure")),
        ):
            result = desktop_executor.execute_step(step)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "EXECUTION_FAILED")

    def test_focus_window_remains_explicitly_unsupported(self) -> None:
        step = Step(
            id="step_1",
            action=StepAction.FOCUS_WINDOW,
            target=Target(type=TargetType.WINDOW, name="Some window"),
        )

        with patch.object(desktop_executor.sys, "platform", "darwin"):
            result = desktop_executor.execute_step(step)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "UNSUPPORTED_ACTION")

    def test_open_folder_launchservices_unavailable_returns_execution_failed_with_actionable_message(self) -> None:
        step = Step(
            id="step_1",
            action=StepAction.OPEN_FOLDER,
            target=Target(type=TargetType.FOLDER, name="tmp", path="/tmp"),
        )

        launchservices_error = (
            "The operation couldn’t be completed. "
            "(Error Domain=NSOSStatusErrorDomain Code=-10661 "
            "\"kLSExecutableIncorrectFormat: No compatible executable was found\")"
        )

        with patch.object(desktop_executor.sys, "platform", "darwin"), patch(
            "executor.desktop_executor._run_command",
            side_effect=[
                CompletedProcess(args=["open", "/tmp"], returncode=1, stdout="", stderr=launchservices_error),
                CompletedProcess(args=["open", "-a", "Finder", "/tmp"], returncode=1, stdout="", stderr=launchservices_error),
            ],
        ):
            result = desktop_executor.execute_step(step)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "EXECUTION_FAILED")
        self.assertIn("desktop session is unavailable", result.error.message)

    def test_open_app_launchservices_unavailable_does_not_report_app_unavailable(self) -> None:
        step = Step(
            id="step_1",
            action=StepAction.OPEN_APP,
            target=Target(type=TargetType.APPLICATION, name="Safari"),
        )

        launchservices_error = (
            "Unable to find application named 'Safari'. "
            "(Error Domain=NSOSStatusErrorDomain Code=-10661)"
        )

        with patch.object(desktop_executor.sys, "platform", "darwin"), patch(
            "executor.desktop_executor._run_command",
            return_value=CompletedProcess(
                args=["open", "-a", "Safari"],
                returncode=1,
                stdout="",
                stderr=launchservices_error,
            ),
        ):
            result = desktop_executor.execute_step(step)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "EXECUTION_FAILED")
        self.assertIn("desktop session is unavailable", result.error.message)

    def test_open_app_uses_bundle_path_fallback_when_name_lookup_fails(self) -> None:
        step = Step(
            id="step_1",
            action=StepAction.OPEN_APP,
            target=Target(type=TargetType.APPLICATION, name="Safari"),
        )

        with patch.object(desktop_executor.sys, "platform", "darwin"), patch(
            "executor.desktop_executor._resolve_app_bundle_path",
            return_value=Path("/Applications/Safari.app"),
        ), patch(
            "executor.desktop_executor._run_command",
            side_effect=[
                CompletedProcess(
                    args=["open", "-a", "Safari"],
                    returncode=1,
                    stdout="",
                    stderr="Unable to find application named 'Safari'",
                ),
                CompletedProcess(
                    args=["open", "-a", "/Applications/Safari.app"],
                    returncode=0,
                    stdout="",
                    stderr="",
                ),
            ],
        ):
            result = desktop_executor.execute_step(step)

        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertIsNotNone(result.details)
        self.assertTrue(bool(result.details.get("fallback_used")))
        self.assertEqual(result.details.get("app_bundle_path"), "/Applications/Safari.app")

    def test_open_file_with_explicit_app_uses_bundle_path_fallback(self) -> None:
        file_path = Path(__file__).resolve()
        step = Step(
            id="step_1",
            action=StepAction.OPEN_FILE,
            target=Target(type=TargetType.FILE, name=file_path.name, path=str(file_path)),
            parameters={"app": "Visual Studio Code"},
        )

        with patch.object(desktop_executor.sys, "platform", "darwin"), patch(
            "executor.desktop_executor._resolve_app_bundle_path",
            return_value=Path("/Applications/Visual Studio Code.app"),
        ), patch(
            "executor.desktop_executor._run_command",
            side_effect=[
                CompletedProcess(
                    args=["open", "-a", "Visual Studio Code", str(file_path)],
                    returncode=1,
                    stdout="",
                    stderr="Unable to find application named 'Visual Studio Code'",
                ),
                CompletedProcess(
                    args=["open", "-a", "/Applications/Visual Studio Code.app", str(file_path)],
                    returncode=0,
                    stdout="",
                    stderr="",
                ),
            ],
        ):
            result = desktop_executor.execute_step(step)

        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertIsNotNone(result.details)
        self.assertEqual(result.details.get("app"), "Visual Studio Code")
        self.assertEqual(result.details.get("app_bundle_path"), "/Applications/Visual Studio Code.app")
        self.assertTrue(bool(result.details.get("fallback_used")))

    def test_open_file_without_explicit_path_uses_named_lookup_fallback(self) -> None:
        file_path = Path(__file__).resolve()
        step = Step(
            id="step_1",
            action=StepAction.OPEN_FILE,
            target=Target(type=TargetType.FILE, name=file_path.name),
        )

        with patch.object(desktop_executor.sys, "platform", "darwin"), patch(
            "executor.desktop_executor._discover_named_path",
            return_value=file_path,
        ), patch(
            "executor.desktop_executor._run_command",
            return_value=CompletedProcess(args=["open", str(file_path)], returncode=0, stdout="", stderr=""),
        ):
            result = desktop_executor.execute_step(step)

        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertIsNotNone(result.details)
        self.assertEqual(result.details.get("path"), str(file_path))

    def test_open_folder_without_explicit_path_uses_named_lookup_fallback(self) -> None:
        folder_path = Path(__file__).resolve().parent
        step = Step(
            id="step_1",
            action=StepAction.OPEN_FOLDER,
            target=Target(type=TargetType.FOLDER, name=folder_path.name),
        )

        with patch.object(desktop_executor.sys, "platform", "darwin"), patch(
            "executor.desktop_executor._discover_named_path",
            return_value=folder_path,
        ), patch(
            "executor.desktop_executor._run_command",
            return_value=CompletedProcess(args=["open", str(folder_path)], returncode=0, stdout="", stderr=""),
        ):
            result = desktop_executor.execute_step(step)

        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertIsNotNone(result.details)
        self.assertEqual(result.details.get("path"), str(folder_path))

    def test_open_app_without_bundle_fallback_remains_app_unavailable(self) -> None:
        step = Step(
            id="step_1",
            action=StepAction.OPEN_APP,
            target=Target(type=TargetType.APPLICATION, name="MissingApp"),
        )

        with patch.object(desktop_executor.sys, "platform", "darwin"), patch(
            "executor.desktop_executor._resolve_app_bundle_path",
            return_value=None,
        ), patch(
            "executor.desktop_executor._run_command",
            return_value=CompletedProcess(
                args=["open", "-a", "MissingApp"],
                returncode=1,
                stdout="",
                stderr="Unable to find application named 'MissingApp'",
            ),
        ):
            result = desktop_executor.execute_step(step)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "APP_UNAVAILABLE")

    def test_open_app_bundle_not_launchable_returns_app_unavailable(self) -> None:
        step = Step(
            id="step_1",
            action=StepAction.OPEN_APP,
            target=Target(type=TargetType.APPLICATION, name="Safari"),
        )

        with patch.object(desktop_executor.sys, "platform", "darwin"), patch(
            "executor.desktop_executor._resolve_app_bundle_path",
            return_value=Path("/Applications/Safari.app"),
        ), patch(
            "executor.desktop_executor._run_command",
            side_effect=[
                CompletedProcess(
                    args=["open", "-a", "Safari"],
                    returncode=1,
                    stdout="",
                    stderr="Unable to find application named 'Safari'",
                ),
                CompletedProcess(
                    args=["open", "-a", "/Applications/Safari.app"],
                    returncode=1,
                    stdout="",
                    stderr="kLSNoExecutableErr: The executable is missing",
                ),
            ],
        ):
            result = desktop_executor.execute_step(step)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "APP_UNAVAILABLE")
        self.assertIn("not launchable", result.error.message)

    def test_discover_installed_app_bundle_matches_fuzzy_bundle_name(self) -> None:
        with TemporaryDirectory() as tmpdir:
            bundle_path = Path(tmpdir) / "YandexMusic.app"
            bundle_path.mkdir()

            with patch.object(desktop_executor, "_APP_SEARCH_DIRECTORIES", (Path(tmpdir),)):
                resolved = desktop_executor._discover_installed_app_bundle("Yandex Music")

        self.assertEqual(resolved, bundle_path)


if __name__ == "__main__":
    unittest.main()
