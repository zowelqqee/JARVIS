"""Deterministic MVP use-case parity checks for supervised JARVIS flows."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from context.session_context import SessionContext
from runtime.runtime_manager import RuntimeManager


def _successful_action_result(step: object) -> SimpleNamespace:
    action = getattr(getattr(step, "action", None), "value", getattr(step, "action", ""))
    target = getattr(step, "target", None)
    return SimpleNamespace(
        action=action,
        success=True,
        target=target,
        details={"stubbed": True},
        error=None,
    )


def _failed_action_result(step: object, code: str, message: str) -> SimpleNamespace:
    action = getattr(getattr(step, "action", None), "value", getattr(step, "action", ""))
    target = getattr(step, "target", None)
    return SimpleNamespace(
        action=action,
        success=False,
        target=target,
        details=None,
        error=SimpleNamespace(code=code, message=message),
    )


class UseCaseParityTests(unittest.TestCase):
    """Lock documented use-case outcomes to deterministic runtime behavior."""

    def setUp(self) -> None:
        self.runtime_manager = RuntimeManager()
        self.session_context = SessionContext()

    def test_use_case_open_applications(self) -> None:
        with patch("runtime.runtime_manager.execute_step", side_effect=_successful_action_result):
            result = self.runtime_manager.handle_input("launch Telegram plus Safari", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "open_app: Telegram, Safari")
        self.assertEqual(
            [getattr(getattr(step, "action", None), "value", "") for step in result.completed_steps],
            ["open_app", "open_app"],
        )

    def test_use_case_open_file_or_folder(self) -> None:
        repo_name = Path.cwd().name
        with patch("runtime.runtime_manager.execute_step", side_effect=_successful_action_result):
            result = self.runtime_manager.handle_input(f"open {repo_name} folder", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, f"open_folder: {repo_name}")
        self.assertEqual(len(result.completed_steps), 1)

    def test_use_case_workspace_setup(self) -> None:
        with patch("runtime.runtime_manager.execute_step", side_effect=_successful_action_result):
            result = self.runtime_manager.handle_input("set up workspace for JARVIS", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertTrue((result.command_summary or "").startswith("prepare_workspace:"))
        self.assertGreaterEqual(len(result.completed_steps), 2)

    def test_use_case_window_management_is_explicitly_unsupported(self) -> None:
        result = self.runtime_manager.handle_input("close everything except VS Code", self.session_context)

        self.assertEqual(result.runtime_state, "failed")
        self.assertIsNotNone(result.last_error)
        self.assertEqual(getattr(result.last_error.code, "value", ""), "UNSUPPORTED_ACTION")

    def test_use_case_search_and_open(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            result = self.runtime_manager.handle_input("open the newest md file in this folder", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "search_local: Downloads")
        self.assertEqual(executed_actions, ["open_folder", "search_local", "open_file"])

    def test_use_case_clarification_flow_blocks_on_ambiguity(self) -> None:
        result = self.runtime_manager.handle_input("open Telegram or Safari", self.session_context)

        self.assertEqual(result.runtime_state, "awaiting_clarification")
        self.assertIsNotNone(result.clarification_request)
        self.assertEqual(getattr(result.last_error.code, "value", ""), "MULTIPLE_MATCHES")

    def test_use_case_safe_failure_reports_missing_target(self) -> None:
        def execute_stub(step: object) -> SimpleNamespace:
            action = getattr(getattr(step, "action", None), "value", "")
            if action == "open_app":
                return _failed_action_result(step, code="APP_UNAVAILABLE", message="Application not installed")
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            result = self.runtime_manager.handle_input("open SuperEditor", self.session_context)

        self.assertEqual(result.runtime_state, "failed")
        self.assertIsNotNone(result.last_error)
        self.assertEqual(getattr(result.last_error.code, "value", ""), "APP_UNAVAILABLE")
        self.assertIn("Application not installed", result.visibility.get("failure_message", ""))

    def test_use_case_context_follow_up(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        repo_name = Path.cwd().name
        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            first_result = self.runtime_manager.handle_input(f"open {repo_name} folder", self.session_context)
            second_result = self.runtime_manager.handle_input("now open browser too", self.session_context)

        self.assertEqual(first_result.runtime_state, "completed")
        self.assertEqual(second_result.runtime_state, "completed")
        self.assertEqual(second_result.command_summary, "open_app: Safari")
        self.assertEqual(executed_actions, ["open_folder", "open_app"])


if __name__ == "__main__":
    unittest.main()
