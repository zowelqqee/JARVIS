"""Deterministic executor failure-shape contract tests for macOS MVP behavior."""

from __future__ import annotations

import unittest
from subprocess import CompletedProcess
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


if __name__ == "__main__":
    unittest.main()
