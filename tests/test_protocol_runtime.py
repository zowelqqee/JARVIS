"""Runtime protocol smoke tests."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from context.session_context import SessionContext
from runtime.runtime_manager import RuntimeManager


def _successful_action_result(step: object, *, details: dict[str, object] | None = None) -> SimpleNamespace:
    action = getattr(getattr(step, "action", None), "value", getattr(step, "action", ""))
    target = getattr(step, "target", None)
    return SimpleNamespace(
        action=action,
        success=True,
        target=target,
        details=details if details is not None else {"stubbed": True},
        error=None,
    )


class ProtocolRuntimeTests(unittest.TestCase):
    """Protect the first protocol integration slice."""

    def setUp(self) -> None:
        self.runtime_manager = RuntimeManager()
        self.session_context = SessionContext()

    def test_clean_slate_protocol_requires_confirmation_then_runs(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            blocked_result = self.runtime_manager.handle_input("протокол чистый лист", self.session_context)
            approved_result = self.runtime_manager.handle_input("yes", self.session_context)

        self.assertEqual(blocked_result.runtime_state, "awaiting_confirmation")
        self.assertEqual(blocked_result.command_summary, "run_protocol: Clean Slate")
        self.assertEqual(approved_result.runtime_state, "completed")
        self.assertEqual(
            executed_actions,
            ["close_app", "close_app", "close_app", "close_app"],
        )
        self.assertEqual(approved_result.completion_summary, 'Завершил протокол "чистый лист".')

    def test_i_am_home_protocol_opens_home_soundtrack_and_names_last_project(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with tempfile.TemporaryDirectory() as tempdir:
            state_path = Path(tempdir) / "protocol_state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "last_workspace_path": "/tmp/demo",
                        "last_workspace_label": "demo",
                        "last_git_branch": "main",
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"JARVIS_PROTOCOL_STATE_PATH": str(state_path)}, clear=False):
                with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
                    result = self.runtime_manager.handle_input("я дома", self.session_context)
                    persisted = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "run_protocol: I Am Home")
        self.assertEqual(executed_actions, ["open_website"])
        self.assertEqual(
            result.completion_summary,
            "Приветствую, сэр. Последним у вас был проект demo, ветка main.",
        )
        self.assertEqual(persisted.get("last_protocol_id"), "i_am_home")

    def test_start_work_on_workspace_runs_prepare_workspace_and_remembers_path(self) -> None:
        executed_actions: list[str] = []

        with tempfile.TemporaryDirectory() as tempdir:
            workspace_path = Path(tempdir) / "demo"
            workspace_path.mkdir()
            state_path = Path(tempdir) / "protocol_state.json"
            state_path.write_text("{}", encoding="utf-8")

            def execute_stub(step: object) -> SimpleNamespace:
                action = getattr(getattr(step, "action", None), "value", "")
                executed_actions.append(action)
                if action == "open_folder":
                    return _successful_action_result(
                        step,
                        details={"path": str(workspace_path), "app": "Visual Studio Code"},
                    )
                return _successful_action_result(step)

            with patch.dict(os.environ, {"JARVIS_PROTOCOL_STATE_PATH": str(state_path)}, clear=False):
                with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
                    result = self.runtime_manager.handle_input("start work on demo", self.session_context)
                persisted = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "start_work: demo in Visual Studio Code")
        self.assertEqual(result.completion_summary, "Workspace ready: demo in Visual Studio Code.")
        self.assertEqual(executed_actions, ["open_app", "open_folder"])
        self.assertEqual(persisted.get("last_workspace_path"), str(workspace_path))
        self.assertEqual(persisted.get("last_workspace_label"), "demo")

    def test_bare_start_work_clarifies_then_continues_same_supervised_flow(self) -> None:
        executed_actions: list[str] = []

        with tempfile.TemporaryDirectory() as tempdir:
            workspace_path = Path(tempdir) / "demo workspace"
            workspace_path.mkdir()
            state_path = Path(tempdir) / "protocol_state.json"
            state_path.write_text("{}", encoding="utf-8")

            def execute_stub(step: object) -> SimpleNamespace:
                action = getattr(getattr(step, "action", None), "value", "")
                executed_actions.append(action)
                if action == "open_folder":
                    return _successful_action_result(
                        step,
                        details={"path": str(workspace_path), "app": "Visual Studio Code"},
                    )
                return _successful_action_result(step)

            with patch.dict(os.environ, {"JARVIS_PROTOCOL_STATE_PATH": str(state_path)}, clear=False):
                with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
                    blocked_result = self.runtime_manager.handle_input("start work", self.session_context)
                    completed_result = self.runtime_manager.handle_input("demo workspace", self.session_context)
                persisted = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(blocked_result.runtime_state, "awaiting_clarification")
        self.assertEqual(blocked_result.command_summary, "start_work: Visual Studio Code")
        self.assertEqual(blocked_result.visibility.get("clarification_question"), "What workspace should I prepare?")
        self.assertEqual(completed_result.runtime_state, "completed")
        self.assertEqual(completed_result.command_summary, "start_work: demo workspace in Visual Studio Code")
        self.assertEqual(completed_result.completion_summary, "Workspace ready: demo workspace in Visual Studio Code.")
        self.assertEqual(executed_actions, ["open_app", "open_folder"])
        self.assertEqual(persisted.get("last_workspace_path"), str(workspace_path))
        self.assertEqual(persisted.get("last_workspace_label"), "demo workspace")

    def test_resume_work_protocol_reopens_last_workspace_with_remembered_context(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with tempfile.TemporaryDirectory() as tempdir:
            workspace_path = Path(tempdir) / "demo"
            workspace_path.mkdir()
            state_path = Path(tempdir) / "protocol_state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "last_workspace_path": str(workspace_path),
                        "last_workspace_label": "demo",
                        "last_git_branch": "main",
                        "last_work_summary": "open_file: roadmap.md",
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"JARVIS_PROTOCOL_STATE_PATH": str(state_path)}, clear=False):
                with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
                    result = self.runtime_manager.handle_input("resume work", self.session_context)
                persisted = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "resume_work: last workspace")
        self.assertEqual(
            result.completion_summary,
            "Resumed work in demo in Visual Studio Code. Branch: main. Last file: roadmap.md.",
        )
        self.assertEqual(executed_actions, ["open_app", "open_folder"])
        self.assertEqual(persisted.get("last_protocol_id"), "resume_work")

    def test_resume_work_protocol_falls_back_to_workspace_only_when_extra_context_missing(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with tempfile.TemporaryDirectory() as tempdir:
            workspace_path = Path(tempdir) / "demo"
            workspace_path.mkdir()
            state_path = Path(tempdir) / "protocol_state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "last_workspace_path": str(workspace_path),
                        "last_workspace_label": "demo",
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"JARVIS_PROTOCOL_STATE_PATH": str(state_path)}, clear=False):
                with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
                    result = self.runtime_manager.handle_input("resume work", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "resume_work: last workspace")
        self.assertEqual(result.completion_summary, "Resumed work in demo in Visual Studio Code.")
        self.assertEqual(executed_actions, ["open_app", "open_folder"])

    def test_resume_work_fails_honestly_with_stale_remembered_workspace_path(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            state_path = Path(tempdir) / "protocol_state.json"
            # Write a state that has a workspace path that no longer exists on disk.
            stale_path = Path(tempdir) / "deleted_workspace"
            state_path.write_text(
                json.dumps(
                    {
                        "last_workspace_path": str(stale_path),
                        "last_workspace_label": "deleted_workspace",
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"JARVIS_PROTOCOL_STATE_PATH": str(state_path)}, clear=False):
                result = self.runtime_manager.handle_input("resume work", self.session_context)

        self.assertEqual(result.runtime_state, "failed")
        self.assertEqual(result.command_summary, "resume_work: last workspace")
        self.assertEqual(getattr(getattr(result.last_error, "code", None), "value", ""), "INSUFFICIENT_CONTEXT")
        failure_message = result.visibility.get("failure_message") or ""
        self.assertIn("deleted_workspace", failure_message)
        self.assertIn("no longer exists", failure_message)
        self.assertIn("start work on", failure_message.lower())
        self.assertEqual(result.visibility.get("next_step_hint"), "Start work on a workspace first.")

    def test_resume_work_fails_honestly_without_remembered_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            state_path = Path(tempdir) / "protocol_state.json"
            state_path.write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {"JARVIS_PROTOCOL_STATE_PATH": str(state_path)}, clear=False):
                result = self.runtime_manager.handle_input("resume work", self.session_context)

        self.assertEqual(result.runtime_state, "failed")
        self.assertEqual(result.command_summary, "resume_work: last workspace")
        self.assertEqual(getattr(getattr(result.last_error, "code", None), "value", ""), "INSUFFICIENT_CONTEXT")
        self.assertEqual(
            result.visibility.get("failure_message"),
            "No remembered workspace is available yet. Start work on a workspace first.",
        )
        self.assertEqual(result.visibility.get("next_step_hint"), "Start work on a workspace first.")

    def test_user_defined_protocol_runs_through_same_runtime_pipeline(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with tempfile.TemporaryDirectory() as tempdir:
            protocol_path = Path(tempdir) / "demo_focus.json"
            protocol_path.write_text(
                json.dumps(
                    {
                        "id": "demo_focus",
                        "title": "Demo Focus",
                        "enabled": True,
                        "triggers": [{"type": "exact", "phrase": "protocol demo focus"}],
                        "confirmation_policy": {"mode": "never"},
                        "steps": [{"action_type": "open_app", "inputs": {"app_name": "Notes"}}],
                        "completion_message": 'Completed protocol "Demo Focus".',
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"JARVIS_PROTOCOLS_DIR": tempdir}, clear=False):
                with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
                    result = self.runtime_manager.handle_input("protocol demo focus", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "run_protocol: Demo Focus")
        self.assertEqual(executed_actions, ["open_app"])
        self.assertEqual(result.completion_summary, 'Completed protocol "Demo Focus".')


class ClarificationRepairTests(unittest.TestCase):
    """Dialogue substrate: clarification repair (retry + cancel on repeated failure).

    We use a mocked apply_clarification that returns an identical clone so that
    clarification_was_applied() correctly returns False — simulating the real case
    where a MULTIPLE_MATCHES clarification receives a reply that doesn't match any
    candidate. The apply_clarification(cmd, "") shortcut returns an unpatched clone
    without touching any fields.
    """

    def setUp(self) -> None:
        self.runtime_manager = RuntimeManager()
        self.session_context = SessionContext()

    def _seed_clarification(self) -> None:
        """Put the runtime into awaiting_clarification via bare 'start work'."""
        from unittest.mock import patch
        result = self.runtime_manager.handle_input("start work", self.session_context)
        self.assertEqual(result.runtime_state, "awaiting_clarification", result.runtime_state)

    def _unpatched_apply(self, cmd: object, reply: str) -> object:
        """Return an identical clone (no fields changed) to simulate a no-patch reply."""
        from clarification.clarification_handler import apply_clarification as real_apply
        return real_apply(cmd, "")  # empty string → all apply functions skip → clone returned unchanged

    def test_no_patch_reply_triggers_re_ask_on_first_failure(self) -> None:
        from unittest.mock import patch
        self._seed_clarification()
        with patch("runtime.runtime_manager.apply_clarification", side_effect=self._unpatched_apply):
            result = self.runtime_manager.handle_input("xyz unrelated", self.session_context)
        self.assertEqual(result.runtime_state, "awaiting_clarification")
        clarify_msg = result.visibility.get("clarification_question", "")
        self.assertIn("I didn't catch that", clarify_msg)
        self.assertEqual(self.runtime_manager.clarification_retry_count, 1)

    def test_second_no_patch_reply_cancels_command(self) -> None:
        from unittest.mock import patch
        self._seed_clarification()
        with patch("runtime.runtime_manager.apply_clarification", side_effect=self._unpatched_apply):
            self.runtime_manager.handle_input("xyz unrelated", self.session_context)
            result = self.runtime_manager.handle_input("xyz unrelated", self.session_context)
        self.assertEqual(result.runtime_state, "cancelled")
        self.assertIn("couldn't understand", result.completion_summary or "")
        self.assertEqual(self.runtime_manager.clarification_retry_count, 0)

    def test_valid_reply_after_re_ask_resolves_clarification(self) -> None:
        import tempfile
        from pathlib import Path
        from unittest.mock import patch, call

        with tempfile.TemporaryDirectory() as tempdir:
            workspace_path = Path(tempdir) / "notes"
            workspace_path.mkdir()

            def execute_stub(step: object) -> SimpleNamespace:
                action = getattr(getattr(step, "action", None), "value", "")
                if action == "open_folder":
                    return _successful_action_result(
                        step, details={"path": str(workspace_path), "app": "Visual Studio Code"}
                    )
                return _successful_action_result(step)

            self._seed_clarification()
            # First reply: nothing patched → re-ask
            with patch("runtime.runtime_manager.apply_clarification", side_effect=self._unpatched_apply):
                self.runtime_manager.handle_input("xyz", self.session_context)
            self.assertEqual(self.runtime_manager.clarification_retry_count, 1)
            # Second reply: real valid path → resolves
            with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
                result = self.runtime_manager.handle_input(str(workspace_path), self.session_context)
        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(self.runtime_manager.clarification_retry_count, 0)

    def test_retry_count_resets_on_new_command(self) -> None:
        from unittest.mock import patch
        self._seed_clarification()
        with patch("runtime.runtime_manager.apply_clarification", side_effect=self._unpatched_apply):
            self.runtime_manager.handle_input("xyz", self.session_context)
        self.assertEqual(self.runtime_manager.clarification_retry_count, 1)
        # A new command clears the retry state.
        self.runtime_manager.handle_input("open Safari", self.session_context)
        self.assertEqual(self.runtime_manager.clarification_retry_count, 0)

    def test_retry_count_resets_on_clear_runtime(self) -> None:
        from unittest.mock import patch
        self._seed_clarification()
        with patch("runtime.runtime_manager.apply_clarification", side_effect=self._unpatched_apply):
            self.runtime_manager.handle_input("xyz", self.session_context)
        self.assertEqual(self.runtime_manager.clarification_retry_count, 1)
        self.runtime_manager.clear_runtime()
        self.assertEqual(self.runtime_manager.clarification_retry_count, 0)

    def test_last_clarification_message_saved_on_first_clarification(self) -> None:
        self._seed_clarification()
        self.assertIsNotNone(self.runtime_manager.last_clarification_message)
        self.assertIn("workspace", self.runtime_manager.last_clarification_message.lower())


class CorrectionTurnTests(unittest.TestCase):
    """Dialogue substrate: 'the other one' correction for exactly-2-candidate clarifications."""

    def setUp(self) -> None:
        self.runtime_manager = RuntimeManager()
        self.session_context = SessionContext()

    def test_correction_phrase_with_two_candidates_selects_other(self) -> None:
        from types import SimpleNamespace
        from clarification.clarification_handler import try_apply_correction

        from types import SimpleNamespace as NS
        import sys
        from pathlib import Path
        _TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
        if str(_TYPES_PATH) not in sys.path:
            sys.path.insert(0, str(_TYPES_PATH))
        from command import Command  # type: ignore
        from target import Target, TargetType  # type: ignore

        command = Command(
            raw_input="open safari",
            intent="open_app",
            targets=[
                Target(
                    type=TargetType.APPLICATION,
                    name="Safari",
                    path=None,
                    metadata={"ambiguous": True, "candidates": ["Safari", "Safari Technology Preview"]},
                )
            ],
            parameters={},
            confidence=0.7,
            requires_confirmation=False,
            execution_steps=[],
            status_message="",
        )
        result = try_apply_correction(command, "the other one")
        self.assertIsNotNone(result)
        self.assertEqual(result.targets[0].name, "Safari Technology Preview")
        self.assertFalse((result.targets[0].metadata or {}).get("ambiguous", False))

    def test_correction_with_three_candidates_returns_none(self) -> None:
        from clarification.clarification_handler import try_apply_correction
        import sys
        from pathlib import Path
        _TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
        if str(_TYPES_PATH) not in sys.path:
            sys.path.insert(0, str(_TYPES_PATH))
        from command import Command  # type: ignore
        from target import Target, TargetType  # type: ignore

        command = Command(
            raw_input="open notes",
            intent="open_app",
            targets=[
                Target(
                    type=TargetType.APPLICATION,
                    name="Notes",
                    path=None,
                    metadata={"ambiguous": True, "candidates": ["Notes", "Notes Pro", "Notes Lite"]},
                )
            ],
            parameters={},
            confidence=0.7,
            requires_confirmation=False,
            execution_steps=[],
            status_message="",
        )
        result = try_apply_correction(command, "the other one")
        self.assertIsNone(result)

    def test_non_correction_phrase_returns_none(self) -> None:
        from clarification.clarification_handler import try_apply_correction
        import sys
        from pathlib import Path
        _TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
        if str(_TYPES_PATH) not in sys.path:
            sys.path.insert(0, str(_TYPES_PATH))
        from command import Command  # type: ignore
        from target import Target, TargetType  # type: ignore

        command = Command(
            raw_input="open safari",
            intent="open_app",
            targets=[
                Target(
                    type=TargetType.APPLICATION,
                    name="Safari",
                    path=None,
                    metadata={"ambiguous": True, "candidates": ["Safari", "Safari Technology Preview"]},
                )
            ],
            parameters={},
            confidence=0.7,
            requires_confirmation=False,
            execution_steps=[],
            status_message="",
        )
        self.assertIsNone(try_apply_correction(command, "Safari Technology Preview"))
        self.assertIsNone(try_apply_correction(command, "open chrome"))
