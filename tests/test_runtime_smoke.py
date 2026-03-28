"""Minimal smoke coverage for the supervised JARVIS MVP runtime."""

from __future__ import annotations

import unittest
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace
from unittest.mock import patch

import executor.desktop_executor as desktop_executor
from context.session_context import SessionContext
from jarvis_error import ErrorCategory, ErrorCode, JarvisError
from parser.command_parser import parse_command
from runtime.runtime_manager import RuntimeManager
from step import Step, StepAction
from target import Target, TargetType
from ui.visibility_mapper import map_visibility


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


def _search_action_result(step: object, matches: list[dict[str, str]]) -> SimpleNamespace:
    action = getattr(getattr(step, "action", None), "value", getattr(step, "action", ""))
    target = getattr(step, "target", None)
    return SimpleNamespace(
        action=action,
        success=True,
        target=target,
        details={
            "query": "markdown files",
            "scope_path": "/tmp/demo",
            "matches": matches,
        },
        error=None,
    )


def _window_action_result(
    step: object,
    windows: list[dict[str, object]],
    filter_name: str | None = None,
) -> SimpleNamespace:
    action = getattr(getattr(step, "action", None), "value", getattr(step, "action", ""))
    target = getattr(step, "target", None)
    details: dict[str, object] = {
        "count": len(windows),
        "windows": windows,
    }
    if filter_name:
        details["filter"] = filter_name
    return SimpleNamespace(
        action=action,
        success=True,
        target=target,
        details=details,
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


class RuntimeSmokeTests(unittest.TestCase):
    """Protect the current supervised runtime flows with small smoke tests."""

    def setUp(self) -> None:
        self.runtime_manager = RuntimeManager()
        self.session_context = SessionContext()

    def test_happy_path_completes_with_stubbed_execution(self) -> None:
        with patch("runtime.runtime_manager.execute_step", side_effect=_successful_action_result):
            result = self.runtime_manager.handle_input("open Telegram and Safari", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertIsNotNone(result.completion_summary)
        self.assertEqual(len(result.completed_steps), 2)
        self.assertEqual(result.visibility.get("runtime_state"), "completed")
        self.assertNotIn("next_step_hint", result.visibility)

    def test_clarification_block_and_resume_preserves_command_context(self) -> None:
        with patch("runtime.runtime_manager.execute_step", side_effect=_successful_action_result):
            blocked_result = self.runtime_manager.handle_input("close window", self.session_context)
            resumed_result = self.runtime_manager.handle_input("Telegram", self.session_context)

        self.assertEqual(blocked_result.runtime_state, "awaiting_clarification")
        self.assertIsNotNone(blocked_result.clarification_request)
        self.assertEqual(resumed_result.runtime_state, "awaiting_confirmation")
        self.assertEqual(resumed_result.command_summary, "close_window: Telegram")
        self.assertEqual(getattr(self.runtime_manager.active_command.intent, "value", ""), "close_window")

    def test_clarification_state_allows_fresh_command_restart(self) -> None:
        with patch("runtime.runtime_manager.execute_step", side_effect=_successful_action_result):
            blocked_result = self.runtime_manager.handle_input("htlp", self.session_context)
            restarted_result = self.runtime_manager.handle_input("open telegram", self.session_context)

        self.assertEqual(blocked_result.runtime_state, "awaiting_clarification")
        self.assertEqual(restarted_result.runtime_state, "completed")
        self.assertEqual(restarted_result.command_summary, "open_app: Telegram")

    def test_run_alias_opens_application(self) -> None:
        with patch("runtime.runtime_manager.execute_step", side_effect=_successful_action_result):
            result = self.runtime_manager.handle_input("run telegram", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "open_app: Telegram")

    def test_russian_notes_alias_opens_notes_application(self) -> None:
        with patch("runtime.runtime_manager.execute_step", side_effect=_successful_action_result):
            result = self.runtime_manager.handle_input("open заметки", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "open_app: Notes")

    def test_confirmation_approval_executes_only_after_approval(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            blocked_result = self.runtime_manager.handle_input("close Telegram", self.session_context)
            self.assertEqual(executed_actions, [])

            approved_result = self.runtime_manager.handle_input("yes", self.session_context)

        self.assertEqual(blocked_result.runtime_state, "awaiting_confirmation")
        self.assertEqual(blocked_result.visibility.get("next_step_hint"), "Reply yes to continue or no to cancel.")
        self.assertEqual(blocked_result.visibility["next_step_hint"].count("\n"), 0)
        self.assertEqual(approved_result.runtime_state, "completed")
        self.assertEqual(executed_actions, ["close_app"])
        self.assertEqual(len(approved_result.completed_steps), 1)

    def test_confirmation_approval_executes_only_after_russian_approval(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            blocked_result = self.runtime_manager.handle_input("close Telegram", self.session_context)
            approved_result = self.runtime_manager.handle_input("да", self.session_context)

        self.assertEqual(blocked_result.runtime_state, "awaiting_confirmation")
        self.assertEqual(approved_result.runtime_state, "completed")
        self.assertEqual(executed_actions, ["close_app"])
        self.assertEqual(len(approved_result.completed_steps), 1)

    def test_confirmation_block_allows_fresh_command_restart(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            blocked_result = self.runtime_manager.handle_input("close Telegram", self.session_context)
            restarted_result = self.runtime_manager.handle_input("open Safari", self.session_context)

        self.assertEqual(blocked_result.runtime_state, "awaiting_confirmation")
        self.assertEqual(restarted_result.runtime_state, "completed")
        self.assertEqual(restarted_result.command_summary, "open_app: Safari")
        self.assertEqual(executed_actions, ["open_app"])

    def test_confirmation_denial_cancels_without_executing_blocked_step(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            blocked_result = self.runtime_manager.handle_input("close Telegram", self.session_context)
            denied_result = self.runtime_manager.handle_input("no", self.session_context)

        self.assertEqual(blocked_result.runtime_state, "awaiting_confirmation")
        self.assertEqual(denied_result.runtime_state, "cancelled")
        self.assertEqual(executed_actions, [])
        self.assertEqual(denied_result.completion_summary, "Confirmation denied. Command cancelled.")

    def test_confirmation_denial_cancels_without_executing_blocked_step_for_russian_reply(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            blocked_result = self.runtime_manager.handle_input("close Telegram", self.session_context)
            denied_result = self.runtime_manager.handle_input("нет", self.session_context)

        self.assertEqual(blocked_result.runtime_state, "awaiting_confirmation")
        self.assertEqual(denied_result.runtime_state, "cancelled")
        self.assertEqual(executed_actions, [])
        self.assertEqual(denied_result.completion_summary, "Confirmation denied. Command cancelled.")

    def test_empty_input_fails_with_visible_message(self) -> None:
        result = self.runtime_manager.handle_input("   ", self.session_context)

        self.assertEqual(result.runtime_state, "failed")
        self.assertIsNotNone(result.last_error)
        self.assertIsNotNone(result.visibility.get("failure_message"))

    def test_follow_up_after_completion_is_a_new_command(self) -> None:
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
        self.assertEqual(first_result.command_summary, f"open_folder: {repo_name}")
        self.assertEqual(second_result.command_summary, "open_app: Safari")
        self.assertEqual(len(first_result.completed_steps), 1)
        self.assertEqual(len(second_result.completed_steps), 1)
        self.assertEqual(executed_actions, ["open_folder", "open_app"])

    def test_browser_alias_completes_as_canonical_app_target(self) -> None:
        with patch("runtime.runtime_manager.execute_step", side_effect=_successful_action_result):
            result = self.runtime_manager.handle_input("open browser", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "open_app: Safari")
        self.assertEqual(len(result.completed_steps), 1)

    def test_list_windows_phrases_parse_and_execute(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _window_action_result(step, windows=[])

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            result = self.runtime_manager.handle_input("what's open", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "list_windows")
        self.assertEqual(executed_actions, ["list_windows"])

    def test_show_browser_windows_applies_application_filter(self) -> None:
        observed_targets: list[tuple[str, str]] = []

        def execute_stub(step: object) -> SimpleNamespace:
            target = getattr(step, "target", None)
            target_type = getattr(getattr(target, "type", None), "value", "")
            target_name = str(getattr(target, "name", ""))
            observed_targets.append((target_type, target_name))
            return _window_action_result(step, windows=[], filter_name=target_name)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            result = self.runtime_manager.handle_input("show browser windows", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "list_windows: Safari")
        self.assertEqual(observed_targets, [("application", "Safari")])

    def test_list_windows_visibility_caps_results(self) -> None:
        windows = [
            {"app_name": "Safari", "window_title": f"Tab {index}", "window_id": index}
            for index in range(1, 8)
        ]

        def execute_stub(step: object) -> SimpleNamespace:
            return _window_action_result(step, windows=windows)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            result = self.runtime_manager.handle_input("list windows", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        window_results = result.visibility.get("window_results") or {}
        self.assertEqual(window_results.get("total_windows"), 7)
        self.assertEqual(len(window_results.get("windows", [])), 5)
        self.assertEqual(result.visibility.get("completion_result"), "Found 7 visible windows.")

    def test_filtered_window_results_empty_summary_is_useful(self) -> None:
        def execute_stub(step: object) -> SimpleNamespace:
            return _window_action_result(step, windows=[], filter_name="Telegram")

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            result = self.runtime_manager.handle_input("show Telegram windows", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.visibility.get("completion_result"), "No visible Telegram windows found.")
        window_results = result.visibility.get("window_results") or {}
        self.assertEqual(window_results.get("filter"), "Telegram")
        self.assertEqual(window_results.get("total_windows"), 0)

    def test_list_windows_failure_message_is_honest(self) -> None:
        def execute_stub(step: object) -> SimpleNamespace:
            return _failed_action_result(step, code="UNSUPPORTED_ACTION", message="Window inspection unavailable")

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            result = self.runtime_manager.handle_input("show open windows for Safari", self.session_context)

        self.assertEqual(result.runtime_state, "failed")
        failure_message = result.visibility.get("failure_message") or ""
        self.assertIn("Could not list windows", failure_message)
        self.assertIn("Window inspection unavailable", failure_message)
        self.assertEqual(
            result.visibility.get("next_step_hint"),
            "Try again in an active macOS desktop session.",
        )

    def test_close_window_unsupported_failure_includes_safe_app_hint(self) -> None:
        def execute_stub(step: object) -> SimpleNamespace:
            action = getattr(getattr(step, "action", None), "value", "")
            if action == "close_window":
                return _failed_action_result(step, code="UNSUPPORTED_ACTION", message="close_window unsupported")
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            clarification = self.runtime_manager.handle_input("close window", self.session_context)
            confirmation = self.runtime_manager.handle_input("Telegram", self.session_context)
            result = self.runtime_manager.handle_input("yes", self.session_context)

        self.assertEqual(clarification.runtime_state, "awaiting_clarification")
        self.assertEqual(confirmation.runtime_state, "awaiting_confirmation")
        self.assertEqual(result.runtime_state, "failed")
        self.assertEqual(
            result.visibility.get("next_step_hint"),
            "Try using the app name instead of a window reference.",
        )

    def test_unsupported_window_management_phrase_fails_structured(self) -> None:
        result = self.runtime_manager.handle_input("keep VS Code and close the rest", self.session_context)

        self.assertEqual(result.runtime_state, "failed")
        self.assertIsNotNone(result.last_error)
        self.assertEqual(getattr(result.last_error.code, "value", ""), "UNSUPPORTED_ACTION")
        self.assertIsNone(result.clarification_request)

    def test_prepare_workspace_phrase_completes_with_default_targets(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            result = self.runtime_manager.handle_input("prepare workspace for JARVIS", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "prepare_workspace: Visual Studio Code, JARVIS, Safari")
        self.assertEqual(executed_actions, ["open_app", "open_folder", "open_app"])

    def test_open_project_name_in_code_normalizes_to_code_plus_folder_workspace_flow(self) -> None:
        executed_actions: list[str] = []
        open_folder_parameters: list[dict[str, object]] = []

        def execute_stub(step: object) -> SimpleNamespace:
            action = getattr(getattr(step, "action", None), "value", "")
            executed_actions.append(action)
            if action == "open_folder":
                open_folder_parameters.append(dict(getattr(step, "parameters", {}) or {}))
            return _successful_action_result(step)

        repo_name = Path.cwd().name
        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            result = self.runtime_manager.handle_input(f"open {repo_name} in code", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, f"prepare_workspace: Visual Studio Code, {repo_name}")
        self.assertEqual(executed_actions, ["open_app", "open_folder"])
        self.assertEqual(open_folder_parameters[-1].get("app"), "Visual Studio Code")

    def test_workspace_target_list_with_generic_folder_uses_context_folder_once(self) -> None:
        executed_actions: list[str] = []
        open_folder_targets: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            action = getattr(getattr(step, "action", None), "value", "")
            executed_actions.append(action)
            if action == "open_folder":
                open_folder_targets.append(str(getattr(getattr(step, "target", None), "name", "")))
            return _successful_action_result(step)

        repo_name = Path.cwd().name
        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            self.runtime_manager.handle_input(f"open {repo_name} folder", self.session_context)
            result = self.runtime_manager.handle_input(
                "open code, folder, and browser for this project",
                self.session_context,
            )

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, f"prepare_workspace: Visual Studio Code, {repo_name}, Safari")
        self.assertEqual(executed_actions, ["open_folder", "open_app", "open_folder", "open_app"])
        self.assertEqual(executed_actions[1:].count("open_folder"), 1)
        self.assertEqual(open_folder_targets[-1], repo_name)

    def test_workspace_followup_without_folder_context_blocks_cleanly(self) -> None:
        result = self.runtime_manager.handle_input("open code and browser for this folder", self.session_context)

        self.assertEqual(result.runtime_state, "awaiting_clarification")
        self.assertIsNotNone(result.last_error)
        self.assertEqual(getattr(result.last_error.code, "value", ""), "FOLLOWUP_REFERENCE_UNCLEAR")
        self.assertIsNotNone(result.clarification_request)

    def test_workspace_browser_and_folder_does_not_pass_browser_as_folder_app_hint(self) -> None:
        executed_actions: list[str] = []
        open_folder_parameters: list[dict[str, object]] = []

        def execute_stub(step: object) -> SimpleNamespace:
            action = getattr(getattr(step, "action", None), "value", "")
            executed_actions.append(action)
            if action == "open_folder":
                open_folder_parameters.append(dict(getattr(step, "parameters", {}) or {}))
            return _successful_action_result(step)

        repo_name = Path.cwd().name
        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            result = self.runtime_manager.handle_input(
                f"open browser and the {repo_name} folder",
                self.session_context,
            )

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(executed_actions, ["open_folder", "open_app"])
        self.assertEqual(open_folder_parameters[-1], {})

    def test_search_phrase_uses_recent_folder_context(self) -> None:
        with patch("runtime.runtime_manager.execute_step", side_effect=_successful_action_result):
            first_result = self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            result = self.runtime_manager.handle_input("find markdown files", self.session_context)

        self.assertEqual(first_result.runtime_state, "completed")
        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "search_local: Downloads")
        self.assertEqual(len(result.completed_steps), 1)

    def test_search_without_folder_context_blocks_cleanly(self) -> None:
        blocked_result = self.runtime_manager.handle_input("find markdown files", self.session_context)

        self.assertEqual(blocked_result.runtime_state, "awaiting_clarification")
        self.assertIsNotNone(blocked_result.clarification_request)
        self.assertIn("target", blocked_result.clarification_request.message.lower())
        self.assertEqual(
            blocked_result.visibility.get("next_step_hint"),
            "Try opening a folder first, then search inside it.",
        )

    def test_awaiting_clarification_includes_reply_format_hint(self) -> None:
        blocked_result = self.runtime_manager.handle_input("close window", self.session_context)

        self.assertEqual(blocked_result.runtime_state, "awaiting_clarification")
        self.assertEqual(blocked_result.visibility.get("next_step_hint"), "Reply with one window name.")
        self.assertEqual(blocked_result.visibility["next_step_hint"].count("\n"), 0)

    def test_ambiguous_target_block_includes_specificity_hint(self) -> None:
        blocked_result = self.runtime_manager.handle_input("open Telegram or Safari", self.session_context)

        self.assertEqual(blocked_result.runtime_state, "awaiting_clarification")
        self.assertIsNotNone(blocked_result.clarification_request)
        self.assertEqual(blocked_result.visibility.get("next_step_hint"), "Try a more specific app or file name.")

    def test_failed_followup_reference_unclear_uses_structured_hint(self) -> None:
        visibility = map_visibility(
            state="failed",
            command=SimpleNamespace(intent="search_local", targets=[]),
            error=JarvisError(
                category=ErrorCategory.VALIDATION_ERROR,
                code=ErrorCode.FOLLOWUP_REFERENCE_UNCLEAR,
                message="ignored for hint derivation",
                blocking=False,
                terminal=True,
            ),
        )

        self.assertEqual(visibility.get("next_step_hint"), "Try opening a folder first, then retry.")
        self.assertEqual(visibility["next_step_hint"].count("\n"), 0)

    def test_failed_target_not_found_uses_structured_hint(self) -> None:
        visibility = map_visibility(
            state="failed",
            command=SimpleNamespace(intent="open_file", targets=[]),
            error=JarvisError(
                category=ErrorCategory.VALIDATION_ERROR,
                code=ErrorCode.TARGET_NOT_FOUND,
                message="ignored for hint derivation",
                blocking=False,
                terminal=True,
            ),
        )

        self.assertEqual(visibility.get("next_step_hint"), "Try: open /full/path/to/file")
        self.assertEqual(visibility["next_step_hint"].count("\n"), 0)

    def test_failed_fallback_uses_generic_hint_when_no_specific_rule(self) -> None:
        visibility = map_visibility(
            state="failed",
            command=SimpleNamespace(intent="open_app", targets=[]),
            error=JarvisError(
                category=ErrorCategory.EXECUTION_ERROR,
                code=ErrorCode.STEP_FAILED,
                message="ignored for hint derivation",
                blocking=False,
                terminal=True,
            ),
        )

        self.assertEqual(visibility.get("next_step_hint"), "Try a more specific command.")
        self.assertEqual(visibility["next_step_hint"].count("\n"), 0)

    def test_open_code_for_this_project_reuses_recent_folder_context(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        repo_name = Path.cwd().name
        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            first_result = self.runtime_manager.handle_input(f"open {repo_name} folder", self.session_context)
            second_result = self.runtime_manager.handle_input("open code for this project", self.session_context)

        self.assertEqual(first_result.runtime_state, "completed")
        self.assertEqual(second_result.runtime_state, "completed")
        self.assertEqual(second_result.command_summary, f"prepare_workspace: Visual Studio Code, {repo_name}")
        self.assertEqual(executed_actions, ["open_folder", "open_app", "open_folder"])

    def test_open_latest_markdown_file_uses_active_folder_context(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            first_result = self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            second_result = self.runtime_manager.handle_input("open the latest markdown file", self.session_context)

        self.assertEqual(first_result.runtime_state, "completed")
        self.assertEqual(second_result.runtime_state, "completed")
        self.assertEqual(second_result.command_summary, "search_local: Downloads")
        self.assertEqual(len(second_result.completed_steps), 2)
        self.assertEqual(executed_actions, ["open_folder", "search_local", "open_file"])

    def test_open_last_markdown_file_uses_active_folder_context(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            first_result = self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            second_result = self.runtime_manager.handle_input("open the last markdown file", self.session_context)

        self.assertEqual(first_result.runtime_state, "completed")
        self.assertEqual(second_result.runtime_state, "completed")
        self.assertEqual(second_result.command_summary, "search_local: Downloads")
        self.assertEqual(len(second_result.completed_steps), 2)
        self.assertEqual(executed_actions, ["open_folder", "search_local", "open_file"])

    def test_open_latest_markdown_file_without_scope_blocks_cleanly(self) -> None:
        blocked_result = self.runtime_manager.handle_input("open the latest markdown file", self.session_context)

        self.assertEqual(blocked_result.runtime_state, "awaiting_clarification")
        self.assertIsNotNone(blocked_result.clarification_request)
        self.assertIn("target", blocked_result.clarification_request.message.lower())

    def test_prepare_workspace_for_current_repo_sets_folder_path(self) -> None:
        repo_name = Path.cwd().name
        command = parse_command(f"prepare workspace for {repo_name}", SessionContext())

        folder_targets = [
            target
            for target in list(getattr(command, "targets", []) or [])
            if getattr(getattr(target, "type", None), "value", "") == "folder"
        ]
        self.assertTrue(folder_targets)
        self.assertEqual(str(getattr(folder_targets[0], "path", "") or ""), str(Path.cwd()))

    def test_find_latest_markdown_file_remains_search_only(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            result = self.runtime_manager.handle_input("find the latest markdown file", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "search_local: Downloads")
        self.assertEqual(len(result.completed_steps), 1)
        self.assertEqual(executed_actions, ["open_folder", "search_local"])

    def test_open_most_recent_named_file_produces_search_then_open_steps(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            result = self.runtime_manager.handle_input("open the most recent file named roadmap", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "search_local: Downloads")
        self.assertEqual(len(result.completed_steps), 2)
        self.assertEqual(executed_actions, ["open_folder", "search_local", "open_file"])

    def test_search_visibility_shows_capped_results_and_count(self) -> None:
        many_matches = [
            {"name": f"note-{index}.md", "path": f"/tmp/demo/note-{index}.md", "type": "file"}
            for index in range(1, 8)
        ]

        def execute_stub(step: object) -> SimpleNamespace:
            action = getattr(getattr(step, "action", None), "value", "")
            if action == "search_local":
                return SimpleNamespace(
                    action=action,
                    success=True,
                    target=getattr(step, "target", None),
                    details={
                        "query": "markdown files",
                        "scope_path": "/tmp/demo",
                        "matches": many_matches,
                    },
                    error=None,
                )
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            result = self.runtime_manager.handle_input("find markdown files", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        search_results = result.visibility.get("search_results") or {}
        self.assertEqual(search_results.get("flow"), "search_only")
        self.assertEqual(search_results.get("total_matches"), 7)
        self.assertEqual(len(search_results.get("matches", [])), 5)
        self.assertEqual(result.visibility.get("completion_result"), "Found 7 matches in demo.")

    def test_open_latest_visibility_shows_search_then_open_on_success(self) -> None:
        def execute_stub(step: object) -> SimpleNamespace:
            action = getattr(getattr(step, "action", None), "value", "")
            if action == "search_local":
                return SimpleNamespace(
                    action=action,
                    success=True,
                    target=getattr(step, "target", None),
                    details={
                        "query": "latest markdown file",
                        "scope_path": "/tmp/demo",
                        "matches": [{"name": "roadmap.md", "path": "/tmp/demo/roadmap.md", "type": "file"}],
                    },
                    error=None,
                )
            if action == "open_file":
                return SimpleNamespace(
                    action=action,
                    success=True,
                    target=getattr(step, "target", None),
                    details={"path": "/tmp/demo/roadmap.md"},
                    error=None,
                )
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            result = self.runtime_manager.handle_input("open the latest markdown file", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.visibility.get("completion_result"), "Opened file: /tmp/demo/roadmap.md")
        done_steps = result.visibility.get("completed_steps") or []
        self.assertEqual(len(done_steps), 2)
        self.assertIn("search_local", done_steps[0])
        self.assertIn("open_file", done_steps[1])
        search_results = result.visibility.get("search_results") or {}
        self.assertEqual(search_results.get("flow"), "search_then_open")
        self.assertEqual(search_results.get("total_matches"), 1)

    def test_open_latest_failure_keeps_search_visibility_and_reason(self) -> None:
        def execute_stub(step: object) -> SimpleNamespace:
            action = getattr(getattr(step, "action", None), "value", "")
            if action == "search_local":
                return SimpleNamespace(
                    action=action,
                    success=True,
                    target=getattr(step, "target", None),
                    details={
                        "query": "latest markdown file",
                        "scope_path": "/tmp/demo",
                        "matches": [{"name": "roadmap.md", "path": "/tmp/demo/roadmap.md", "type": "file"}],
                    },
                    error=None,
                )
            if action == "open_file":
                return _failed_action_result(step, code="EXECUTION_FAILED", message="simulated open failure")
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            result = self.runtime_manager.handle_input("open the latest markdown file", self.session_context)

        self.assertEqual(result.runtime_state, "failed")
        failure_message = result.visibility.get("failure_message") or ""
        self.assertIn("Found a matching file, but could not open it", failure_message)
        self.assertIn("simulated open failure", failure_message)
        done_steps = result.visibility.get("completed_steps") or []
        self.assertEqual(len(done_steps), 1)
        self.assertIn("search_local", done_steps[0])
        search_results = result.visibility.get("search_results") or {}
        self.assertEqual(search_results.get("flow"), "search_then_open")
        self.assertEqual(search_results.get("total_matches"), 1)

    def test_search_follow_up_open_1_uses_recent_search_results(self) -> None:
        opened_paths: list[str] = []
        matches = [
            {"name": "roadmap.md", "path": "/tmp/demo/roadmap.md", "type": "file"},
            {"name": "notes.md", "path": "/tmp/demo/notes.md", "type": "file"},
        ]

        def execute_stub(step: object) -> SimpleNamespace:
            action = getattr(getattr(step, "action", None), "value", "")
            if action == "search_local":
                return _search_action_result(step, matches)
            if action == "open_file":
                opened_paths.append(str(getattr(getattr(step, "target", None), "path", "") or ""))
                return SimpleNamespace(
                    action=action,
                    success=True,
                    target=getattr(step, "target", None),
                    details={"path": opened_paths[-1]},
                    error=None,
                )
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            self.runtime_manager.handle_input("find markdown files", self.session_context)
            result = self.runtime_manager.handle_input("open 1", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "open_file: roadmap.md")
        self.assertEqual(opened_paths, ["/tmp/demo/roadmap.md"])

    def test_search_follow_up_open_second_result_uses_recent_search_results(self) -> None:
        opened_paths: list[str] = []
        matches = [
            {"name": "roadmap.md", "path": "/tmp/demo/roadmap.md", "type": "file"},
            {"name": "notes.md", "path": "/tmp/demo/notes.md", "type": "file"},
        ]

        def execute_stub(step: object) -> SimpleNamespace:
            action = getattr(getattr(step, "action", None), "value", "")
            if action == "search_local":
                return _search_action_result(step, matches)
            if action == "open_file":
                opened_paths.append(str(getattr(getattr(step, "target", None), "path", "") or ""))
                return SimpleNamespace(
                    action=action,
                    success=True,
                    target=getattr(step, "target", None),
                    details={"path": opened_paths[-1]},
                    error=None,
                )
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            self.runtime_manager.handle_input("find markdown files", self.session_context)
            result = self.runtime_manager.handle_input("open the second result", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(opened_paths, ["/tmp/demo/notes.md"])

    def test_recent_search_context_clears_after_unrelated_completed_command(self) -> None:
        matches = [
            {"name": "roadmap.md", "path": "/tmp/demo/roadmap.md", "type": "file"},
            {"name": "notes.md", "path": "/tmp/demo/notes.md", "type": "file"},
        ]

        def execute_stub(step: object) -> SimpleNamespace:
            action = getattr(getattr(step, "action", None), "value", "")
            if action == "search_local":
                return _search_action_result(step, matches)
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            self.runtime_manager.handle_input("find markdown files", self.session_context)
            self.runtime_manager.handle_input("open browser", self.session_context)
            result = self.runtime_manager.handle_input("open 1", self.session_context)

        self.assertEqual(result.runtime_state, "awaiting_clarification")
        self.assertIsNotNone(result.last_error)
        self.assertEqual(getattr(result.last_error.code, "value", ""), "TARGET_NOT_FOUND")

    def test_recent_search_context_persists_for_indexed_open_chain(self) -> None:
        opened_paths: list[str] = []
        matches = [
            {"name": "roadmap.md", "path": "/tmp/demo/roadmap.md", "type": "file"},
            {"name": "notes.md", "path": "/tmp/demo/notes.md", "type": "file"},
        ]

        def execute_stub(step: object) -> SimpleNamespace:
            action = getattr(getattr(step, "action", None), "value", "")
            if action == "search_local":
                return _search_action_result(step, matches)
            if action == "open_file":
                opened_paths.append(str(getattr(getattr(step, "target", None), "path", "") or ""))
                return SimpleNamespace(
                    action=action,
                    success=True,
                    target=getattr(step, "target", None),
                    details={"path": opened_paths[-1]},
                    error=None,
                )
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            self.runtime_manager.handle_input("find markdown files", self.session_context)
            first_open = self.runtime_manager.handle_input("open 1", self.session_context)
            second_open = self.runtime_manager.handle_input("open 2", self.session_context)

        self.assertEqual(first_open.runtime_state, "completed")
        self.assertEqual(second_open.runtime_state, "completed")
        self.assertEqual(opened_paths, ["/tmp/demo/roadmap.md", "/tmp/demo/notes.md"])

    def test_search_follow_up_open_1_without_recent_results_blocks_cleanly(self) -> None:
        result = self.runtime_manager.handle_input("open 1", self.session_context)

        self.assertEqual(result.runtime_state, "awaiting_clarification")
        self.assertIsNotNone(result.last_error)
        self.assertEqual(getattr(result.last_error.code, "value", ""), "TARGET_NOT_FOUND")
        self.assertIn("search", getattr(result.last_error, "message", "").lower())

    def test_search_follow_up_out_of_range_index_blocks_cleanly(self) -> None:
        matches = [
            {"name": "roadmap.md", "path": "/tmp/demo/roadmap.md", "type": "file"},
            {"name": "notes.md", "path": "/tmp/demo/notes.md", "type": "file"},
        ]

        def execute_stub(step: object) -> SimpleNamespace:
            action = getattr(getattr(step, "action", None), "value", "")
            if action == "search_local":
                return _search_action_result(step, matches)
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            self.runtime_manager.handle_input("find markdown files", self.session_context)
            result = self.runtime_manager.handle_input("open result 3", self.session_context)

        self.assertEqual(result.runtime_state, "awaiting_clarification")
        self.assertIsNotNone(result.last_error)
        self.assertEqual(getattr(result.last_error.code, "value", ""), "TARGET_NOT_FOUND")
        self.assertIn("out of range", getattr(result.last_error, "message", "").lower())

    def test_search_follow_up_that_file_requires_unambiguous_recent_result(self) -> None:
        many_matches = [
            {"name": "roadmap.md", "path": "/tmp/demo/roadmap.md", "type": "file"},
            {"name": "notes.md", "path": "/tmp/demo/notes.md", "type": "file"},
        ]
        single_match = [{"name": "roadmap.md", "path": "/tmp/demo/roadmap.md", "type": "file"}]
        opened_paths: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            action = getattr(getattr(step, "action", None), "value", "")
            if action == "search_local":
                query = str(getattr(step, "parameters", {}).get("query", "")).lower()
                if "single" in query:
                    return _search_action_result(step, single_match)
                return _search_action_result(step, many_matches)
            if action == "open_file":
                opened_paths.append(str(getattr(getattr(step, "target", None), "path", "") or ""))
                return SimpleNamespace(
                    action=action,
                    success=True,
                    target=getattr(step, "target", None),
                    details={"path": opened_paths[-1]},
                    error=None,
                )
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            self.runtime_manager.handle_input("find markdown files", self.session_context)
            ambiguous = self.runtime_manager.handle_input("open that file", self.session_context)

            self.runtime_manager.handle_input("cancel", self.session_context)
            self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            self.runtime_manager.handle_input("find single markdown file", self.session_context)
            resolved = self.runtime_manager.handle_input("open that file", self.session_context)

        self.assertEqual(ambiguous.runtime_state, "awaiting_clarification")
        self.assertIsNotNone(ambiguous.last_error)
        self.assertEqual(getattr(ambiguous.last_error.code, "value", ""), "MULTIPLE_MATCHES")
        self.assertEqual(resolved.runtime_state, "completed")
        self.assertEqual(opened_paths, ["/tmp/demo/roadmap.md"])

    def test_recent_target_open_same_folder_follow_up_works(self) -> None:
        opened_folder_paths: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            action = getattr(getattr(step, "action", None), "value", "")
            if action == "open_folder":
                opened_folder_paths.append(str(getattr(getattr(step, "target", None), "path", "") or ""))
                return SimpleNamespace(
                    action=action,
                    success=True,
                    target=getattr(step, "target", None),
                    details={"path": opened_folder_paths[-1]},
                    error=None,
                )
            if action == "search_local":
                return _search_action_result(
                    step,
                    [{"name": "roadmap.md", "path": "/tmp/demo/roadmap.md", "type": "file"}],
                )
            if action == "open_file":
                return SimpleNamespace(
                    action=action,
                    success=True,
                    target=getattr(step, "target", None),
                    details={"path": "/tmp/demo/roadmap.md"},
                    error=None,
                )
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            self.runtime_manager.handle_input("find markdown files", self.session_context)
            self.runtime_manager.handle_input("open 1", self.session_context)
            result = self.runtime_manager.handle_input("open the same folder", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertTrue(opened_folder_paths)
        self.assertEqual(opened_folder_paths[-1], "/tmp/demo")

    def test_recent_target_open_it_without_context_blocks_cleanly(self) -> None:
        result = self.runtime_manager.handle_input("open it", self.session_context)

        self.assertEqual(result.runtime_state, "awaiting_clarification")
        self.assertIsNotNone(result.last_error)
        self.assertEqual(getattr(result.last_error.code, "value", ""), "TARGET_NOT_FOUND")
        self.assertIn("recent target", getattr(result.last_error, "message", "").lower())

    def test_recent_target_close_it_after_open_browser_blocks_for_confirmation(self) -> None:
        with patch("runtime.runtime_manager.execute_step", side_effect=_successful_action_result):
            opened = self.runtime_manager.handle_input("open browser", self.session_context)
            close_request = self.runtime_manager.handle_input("close it", self.session_context)

        self.assertEqual(opened.runtime_state, "completed")
        self.assertEqual(close_request.runtime_state, "awaiting_confirmation")
        self.assertEqual(close_request.command_summary, "close_app: Safari")

    def test_recent_target_open_that_in_code_uses_recent_folder_context(self) -> None:
        executed_actions: list[str] = []
        open_folder_parameters: list[dict[str, object]] = []

        def execute_stub(step: object) -> SimpleNamespace:
            action = getattr(getattr(step, "action", None), "value", "")
            executed_actions.append(action)
            if action == "open_folder":
                open_folder_parameters.append(dict(getattr(step, "parameters", {}) or {}))
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            self.runtime_manager.handle_input("open Downloads folder", self.session_context)
            result = self.runtime_manager.handle_input("open that in code", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertTrue((result.command_summary or "").startswith("prepare_workspace:"))
        self.assertEqual(executed_actions, ["open_folder", "open_app", "open_folder"])
        self.assertEqual(open_folder_parameters[-1].get("app"), "Visual Studio Code")

    def test_open_this_file_in_code_uses_open_file_with_app_hint(self) -> None:
        executed_actions: list[str] = []
        open_file_parameters: list[dict[str, object]] = []

        def execute_stub(step: object) -> SimpleNamespace:
            action = getattr(getattr(step, "action", None), "value", "")
            executed_actions.append(action)
            if action == "open_file":
                open_file_parameters.append(dict(getattr(step, "parameters", {}) or {}))
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            self.runtime_manager.handle_input("open /tmp/demo/roadmap.md in code", self.session_context)
            result = self.runtime_manager.handle_input("open this file in code", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "open_file: roadmap.md")
        self.assertEqual(executed_actions, ["open_file", "open_file"])
        self.assertEqual(open_file_parameters[-1].get("app"), "Visual Studio Code")

    def test_executor_open_folder_with_missing_specified_app_fails_explicitly(self) -> None:
        step = Step(
            id="step_1",
            action=StepAction.OPEN_FOLDER,
            target=Target(type=TargetType.FOLDER, name="demo", path="/tmp/demo"),
            parameters={"app": "Definitely Missing App"},
        )

        with patch.object(desktop_executor.sys, "platform", "darwin"), patch(
            "executor.desktop_executor._resolve_existing_path",
            return_value=Path("/tmp/demo"),
        ), patch(
            "executor.desktop_executor._run_command",
            return_value=CompletedProcess(
                args=["open", "-a", "Definitely Missing App", "/tmp/demo"],
                returncode=1,
                stdout="",
                stderr='Unable to find application named "Definitely Missing App".',
            ),
        ):
            result = desktop_executor.execute_step(step)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertEqual(getattr(result.error, "code", ""), "APP_UNAVAILABLE")

    def test_executor_open_folder_uses_finder_fallback_when_default_open_fails(self) -> None:
        step = Step(
            id="step_1",
            action=StepAction.OPEN_FOLDER,
            target=Target(type=TargetType.FOLDER, name="demo", path="/tmp/demo"),
            parameters=None,
        )

        run_side_effects = [
            CompletedProcess(
                args=["open", "/tmp/demo"],
                returncode=1,
                stdout="",
                stderr="No application knows how to open URL file:///tmp/demo/",
            ),
            CompletedProcess(
                args=["open", "-a", "Finder", "/tmp/demo"],
                returncode=0,
                stdout="",
                stderr="",
            ),
        ]

        with patch.object(desktop_executor.sys, "platform", "darwin"), patch(
            "executor.desktop_executor._resolve_existing_path",
            return_value=Path("/tmp/demo"),
        ), patch(
            "executor.desktop_executor._run_command",
            side_effect=run_side_effects,
        ):
            result = desktop_executor.execute_step(step)

        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertEqual(result.details.get("app"), "Finder")
        self.assertTrue(bool(result.details.get("fallback_used")))


if __name__ == "__main__":
    unittest.main()
